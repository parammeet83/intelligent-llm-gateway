"""Tenant authentication, API-key lifecycle, admin access, isolation, rate limits, budgets."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.admin import issue_session
from app.db.models import RequestAttempt, RequestLog, TenantBudgetPeriod
from app.db.session import create_engine
from app.providers.base import ProviderErrorKind
from app.providers.mock import MockProvider
from tests.api.conftest import (
    ACME_KEY,
    ADMIN,
    ADMIN_HEADERS,
    DOCFLOW_HEADERS,
    DOCFLOW_KEY,
    HEADERS,
    ClientFactory,
)

SIMPLE = {"prompt": "Is this review positive? 'Great product.'", "task_type": "classification"}


def _gen(client: TestClient, headers: dict[str, str], **extra: Any) -> Any:
    return client.post("/api/v1/generate", json={**SIMPLE, **extra}, headers=headers)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _query(url: str, statement: Any) -> list[Any]:
    async def run() -> list[Any]:
        engine = create_engine(url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(statement)).all())
        finally:
            await engine.dispose()

    return asyncio.run(run())


# --- tenant authentication ---------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},
        _bearer("not-a-key"),
        _bearer(ACME_KEY[:-1] + "X"),  # right prefix, wrong secret
        _bearer("rw_unknown1_" + "Z" * 32),  # well-formed, nonexistent
        _bearer(ADMIN),  # the admin token is not a tenant key
    ],
)
def test_generate_rejects_bad_credentials(
    make_client: ClientFactory, headers: dict[str, str]
) -> None:
    response = _gen(make_client(), headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.json()["error"]["message"] == "Invalid or missing credentials."


def test_valid_key_authenticates_and_tenant_comes_from_key(make_client: ClientFactory) -> None:
    client = make_client()
    assert _gen(client, HEADERS).json()["tenant"] == "acme-saas"
    assert _gen(client, DOCFLOW_HEADERS).json()["tenant"] == "docflow"


def test_suspended_tenant_is_rejected(make_client: ClientFactory) -> None:
    client = make_client()
    patched = client.patch(
        "/api/v1/admin/tenants/acme-saas", json={"status": "suspended"}, headers=ADMIN_HEADERS
    )
    assert patched.status_code == 200
    assert _gen(client, HEADERS).status_code == 401
    assert _gen(client, DOCFLOW_HEADERS).status_code == 200


# --- key lifecycle ------------------------------------------------------------------------


def test_key_create_list_revoke(make_client: ClientFactory) -> None:
    client = make_client()
    created = client.post(
        "/api/v1/admin/tenants/docflow/keys", json={"name": "ci"}, headers=ADMIN_HEADERS
    )
    assert created.status_code == 201
    body = created.json()
    new_key = body["api_key"]
    assert new_key.startswith(body["prefix"] + "_")
    assert _gen(client, _bearer(new_key)).json()["tenant"] == "docflow"

    listing = client.get("/api/v1/admin/tenants/docflow/keys", headers=ADMIN_HEADERS)
    assert new_key not in listing.text and "key_hash" not in listing.text
    assert {k["prefix"] for k in listing.json()["items"]} >= {body["prefix"]}

    revoked = client.post(f"/api/v1/admin/keys/{body['id']}/revoke", headers=ADMIN_HEADERS)
    assert revoked.json()["active"] is False
    assert _gen(client, _bearer(new_key)).status_code == 401
    assert _gen(client, DOCFLOW_HEADERS).status_code == 200  # other keys unaffected


def test_rotation_without_grace_revokes_old_key(make_client: ClientFactory) -> None:
    client = make_client()
    keys = client.get("/api/v1/admin/tenants/acme-saas/keys", headers=ADMIN_HEADERS).json()["items"]
    rotated = client.post(
        f"/api/v1/admin/keys/{keys[0]['id']}/rotate", json={}, headers=ADMIN_HEADERS
    )
    assert rotated.status_code == 201
    assert _gen(client, HEADERS).status_code == 401
    assert _gen(client, _bearer(rotated.json()["new_key"]["api_key"])).status_code == 200
    again = client.post(
        f"/api/v1/admin/keys/{keys[0]['id']}/rotate", json={}, headers=ADMIN_HEADERS
    )
    assert again.status_code == 409


def test_rotation_with_grace_keeps_old_key_until_expiry(make_client: ClientFactory) -> None:
    client = make_client()
    keys = client.get("/api/v1/admin/tenants/acme-saas/keys", headers=ADMIN_HEADERS).json()["items"]
    rotated = client.post(
        f"/api/v1/admin/keys/{keys[0]['id']}/rotate", json={"grace_s": 3600}, headers=ADMIN_HEADERS
    ).json()
    assert rotated["old_key"]["expires_at"] is not None
    assert _gen(client, HEADERS).status_code == 200
    assert _gen(client, _bearer(rotated["new_key"]["api_key"])).status_code == 200


# --- admin access -------------------------------------------------------------------------


def test_admin_disabled_without_token(make_client: ClientFactory) -> None:
    client = make_client(admin_token=None)
    response = client.get("/api/v1/admin/tenants", headers=ADMIN_HEADERS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_NOT_CONFIGURED"


@pytest.mark.parametrize(
    "headers", [{}, HEADERS, _bearer("rws_forged.signature"), _bearer(ADMIN + "x")]
)
def test_admin_endpoints_reject_non_admins(
    make_client: ClientFactory, headers: dict[str, str]
) -> None:
    client = make_client()
    for path in (
        "/api/v1/admin/tenants",
        "/api/v1/admin/usage",
        "/api/v1/admin/requests",
        "/api/v1/admin/config",
    ):
        assert client.get(path, headers=headers).status_code == 401


def test_admin_session_exchange_and_expiry(make_client: ClientFactory) -> None:
    client = make_client()
    session = client.post("/api/v1/admin/session", json={"token": ADMIN})
    assert session.status_code == 200
    token = session.json()["session_token"]
    assert ADMIN not in token
    assert client.get("/api/v1/admin/tenants", headers=_bearer(token)).status_code == 200
    expired, _ = issue_session(ADMIN, 300, now=0)
    assert client.get("/api/v1/admin/tenants", headers=_bearer(expired)).status_code == 401
    other, _ = issue_session("a-different-admin-token-value-1234567", 300)
    assert client.get("/api/v1/admin/tenants", headers=_bearer(other)).status_code == 401


def test_admin_login_is_throttled(make_client: ClientFactory) -> None:
    client = make_client()
    codes = [
        client.post("/api/v1/admin/session", json={"token": "wrong"}).status_code for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    assert client.post("/api/v1/admin/session", json={"token": ADMIN}).status_code == 429


def test_admin_config_has_no_secrets(make_client: ClientFactory) -> None:
    response = make_client().get("/api/v1/admin/config", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    for secret in (ADMIN, ACME_KEY, DOCFLOW_KEY, "test-pepper"):
        assert secret not in response.text
    assert response.json()["policy"]["version"] == "rw-2026.11-v1"


def test_tenant_crud(make_client: ClientFactory) -> None:
    client = make_client()
    created = client.post(
        "/api/v1/admin/tenants",
        json={"slug": "new-co", "name": "New Co", "rate_limit_rpm": 5, "daily_budget_usd": "0.5"},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201
    assert created.json()["budgets"][0]["limit_usd"] == "0.50000000"
    dup = client.post(
        "/api/v1/admin/tenants", json={"slug": "new-co", "name": "x"}, headers=ADMIN_HEADERS
    )
    assert dup.status_code == 409
    bad = client.post(
        "/api/v1/admin/tenants", json={"slug": "Bad Slug!", "name": "x"}, headers=ADMIN_HEADERS
    )
    assert bad.status_code == 422
    patched = client.patch(
        "/api/v1/admin/tenants/new-co", json={"clear_daily_budget": True}, headers=ADMIN_HEADERS
    )
    assert patched.json()["daily_budget_usd"] is None


# --- isolation ------------------------------------------------------------------------------


def test_tenants_cannot_see_each_others_data(make_client: ClientFactory) -> None:
    client = make_client()
    acme_id = _gen(client, HEADERS, request_id="acme-secret-1").json()["request_id"]
    docflow_id = _gen(client, DOCFLOW_HEADERS).json()["request_id"]

    own = client.get("/api/v1/me/requests", headers=DOCFLOW_HEADERS).json()
    assert [r["id"] for r in own["items"]] == [docflow_id]
    assert client.get(f"/api/v1/me/requests/{acme_id}", headers=DOCFLOW_HEADERS).status_code == 404
    assert client.get(f"/api/v1/me/requests/{acme_id}", headers=HEADERS).status_code == 200
    assert client.get(f"/api/v1/me/requests/{docflow_id}", headers=HEADERS).status_code == 404

    usage = client.get("/api/v1/me/usage", headers=DOCFLOW_HEADERS).json()
    assert usage["totals"]["requests"] == 1 and usage["by_tenant"] is None
    me = client.get("/api/v1/me", headers=DOCFLOW_HEADERS).json()
    assert me["slug"] == "docflow"
    assert "acme" not in client.get("/api/v1/me/requests", headers=DOCFLOW_HEADERS).text

    # Tenant keys can't reach admin data; admins see both.
    assert client.get("/api/v1/admin/requests", headers=DOCFLOW_HEADERS).status_code == 401
    everything = client.get("/api/v1/admin/requests", headers=ADMIN_HEADERS).json()
    assert {r["tenant"] for r in everything["items"]} == {"acme-saas", "docflow"}
    filtered = client.get("/api/v1/admin/requests?tenant=docflow", headers=ADMIN_HEADERS).json()
    assert [r["id"] for r in filtered["items"]] == [docflow_id]


def test_same_request_id_is_independent_per_tenant(make_client: ClientFactory) -> None:
    client = make_client()
    assert _gen(client, HEADERS, request_id="shared").status_code == 200
    assert _gen(client, DOCFLOW_HEADERS, request_id="shared").status_code == 200
    assert _gen(client, HEADERS, request_id="shared").status_code == 409


# --- rate limiting -------------------------------------------------------------------------


def test_rate_limit_rejects_and_logs_without_consuming_request_id(
    make_client: ClientFactory, seeded_url: str
) -> None:
    client = make_client()
    client.patch("/api/v1/admin/tenants/docflow", json={"rate_limit_rpm": 2}, headers=ADMIN_HEADERS)
    assert _gen(client, DOCFLOW_HEADERS).status_code == 200
    assert _gen(client, DOCFLOW_HEADERS).status_code == 200
    limited = _gen(client, DOCFLOW_HEADERS, request_id="retry-me")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    assert _gen(client, HEADERS).status_code == 200  # other tenants unaffected

    rows = _query(seeded_url, select(RequestLog.status, RequestLog.client_request_id))
    assert ("rejected_rate_limit", None) in [tuple(r) for r in rows]
    client.patch(
        "/api/v1/admin/tenants/docflow", json={"rate_limit_rpm": 100}, headers=ADMIN_HEADERS
    )
    assert _gen(client, DOCFLOW_HEADERS, request_id="retry-me").status_code == 200

    usage = client.get("/api/v1/admin/usage", headers=ADMIN_HEADERS).json()["totals"]
    assert usage["rejected_rate_limit"] == 1
    assert usage["rate_limit_rejection_rate"] > 0


# --- budgets --------------------------------------------------------------------------------


def test_budget_is_consumed_settled_and_then_exhausted(
    make_client: ClientFactory, seeded_url: str
) -> None:
    client = make_client()
    # Mock list prices are tiny; a budget just above one request's cost runs out quickly.
    client.patch(
        "/api/v1/admin/tenants/docflow",
        json={"daily_budget_usd": "0.0001", "clear_monthly_budget": True},
        headers=ADMIN_HEADERS,
    )
    spent: list[Decimal] = []
    while True:
        response = _gen(client, DOCFLOW_HEADERS)
        if response.status_code != 200:
            break
        spent.append(Decimal(response.json()["cost"]["estimated_list_cost_usd"]))
        assert len(spent) < 500, "budget never ran out"
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "BUDGET_EXHAUSTED"

    (period,) = _query(
        seeded_url,
        select(
            TenantBudgetPeriod.spent_usd,
            TenantBudgetPeriod.reserved_usd,
            TenantBudgetPeriod.limit_usd,
        )
        .join_from(
            TenantBudgetPeriod, RequestLog, TenantBudgetPeriod.tenant_id == RequestLog.tenant_id
        )
        .where(RequestLog.status == "succeeded")
        .limit(1),
    )
    assert Decimal(period.spent_usd) == sum(spent)  # spend == sum of settled request costs
    assert Decimal(period.reserved_usd) == 0  # every reservation released
    assert Decimal(period.spent_usd) <= Decimal(period.limit_usd)
    statuses = [r.status for r in _query(seeded_url, select(RequestLog.status))]
    assert "rejected_budget" in statuses
    me = client.get("/api/v1/me", headers=DOCFLOW_HEADERS).json()
    assert me["budgets"][0]["period"] == "daily"
    assert "shadow budget" in me["budget_basis"]


def test_timeout_without_usage_is_charged_to_the_budget_not_recorded_as_free(
    make_client: ClientFactory, seeded_url: str
) -> None:
    mock = MockProvider()
    for model_id in ("mock-small", "mock-medium", "mock-premium"):
        mock.script(model_id, [MockProvider.error(ProviderErrorKind.TIMEOUT)])  # no usage
    client = make_client({"mock": mock})
    client.patch(
        "/api/v1/admin/tenants/docflow",
        json={"daily_budget_usd": "1.00", "clear_monthly_budget": True},
        headers=ADMIN_HEADERS,
    )
    response = _gen(client, DOCFLOW_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"]["attempts"][0]["status"] == "timeout"
    # A partial sum would understate the list cost, so it's unknown rather than "estimated".
    assert body["cost"]["estimated_list_cost_usd"] is None
    assert body["cost"]["list_cost_status"] == "unavailable"

    (log,) = _query(seeded_url, select(RequestLog.decision, RequestLog.list_cost_status))
    execution = log.decision["execution"]
    assert execution["usage_unknown_attempts"] == 1
    charged = Decimal(execution["budget_charged_usd"])
    (success,) = _query(
        seeded_url,
        select(RequestAttempt.estimated_list_cost_usd).where(RequestAttempt.status == "succeeded"),
    )
    assert charged > Decimal(success.estimated_list_cost_usd)  # the timeout drew its worst case
    (period,) = _query(
        seeded_url, select(TenantBudgetPeriod.spent_usd, TenantBudgetPeriod.reserved_usd)
    )
    assert Decimal(period.spent_usd) == charged
    assert Decimal(period.reserved_usd) == 0


def test_budget_of_one_tenant_does_not_affect_another(make_client: ClientFactory) -> None:
    client = make_client()
    client.patch(
        "/api/v1/admin/tenants/docflow", json={"daily_budget_usd": "0"}, headers=ADMIN_HEADERS
    )
    assert _gen(client, DOCFLOW_HEADERS).status_code == 402
    assert _gen(client, HEADERS).status_code == 200


def test_admin_usage_and_request_detail(make_client: ClientFactory) -> None:
    client = make_client()
    rid = _gen(client, HEADERS).json()["request_id"]
    usage = client.get("/api/v1/admin/usage?days=1&bucket=hour", headers=ADMIN_HEADERS).json()
    assert usage["totals"]["succeeded"] == 1
    assert usage["by_tenant"][0]["tenant"] == "acme-saas"
    assert usage["timeseries"] and usage["latency_histogram"]
    detail = client.get(f"/api/v1/admin/requests/{rid}", headers=ADMIN_HEADERS).json()
    assert detail["attempts"][0]["reason_code"] == "PRIMARY"
    assert detail["decision"]["policy_version"] == "rw-2026.11-v1"
    assert client.get("/api/v1/admin/requests/not-a-uuid", headers=ADMIN_HEADERS).status_code == 404
