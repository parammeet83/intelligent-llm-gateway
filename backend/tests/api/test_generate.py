"""End-to-end /api/v1/generate: auth, routing, execution, accounting, persistence, safety."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import RequestAttempt, RequestLog
from app.db.session import create_engine
from app.main import create_app
from tests.api.conftest import (
    ADMIN,
    DOCFLOW_HEADERS,
    HEADERS,
    ClientFactory,
    ScriptedUpstream,
    real_shaped_providers,
)
from tests.conftest import make_settings
from tests.providers.fakes import FAKE_GROQ_KEY, FAKE_OPENROUTER_KEY, json_response

SIMPLE = {"prompt": "Is this review positive? 'Great product.'", "task_type": "classification"}
SECRET_PROMPT = "my-very-private-prompt-text-42"
GPT20 = "openai/gpt-oss-20b"
GPT120 = "openai/gpt-oss-120b"


def db_rows(url: str) -> tuple[list[Any], list[Any]]:
    """Committed rows (SQLAlchemy Row objects: attribute access + `_asdict()`)."""

    async def load() -> tuple[list[Any], list[Any]]:
        engine = create_engine(url)
        try:
            async with engine.connect() as conn:
                logs = (
                    await conn.execute(select(RequestLog).order_by(RequestLog.created_at))
                ).all()
                attempts = (
                    await conn.execute(
                        select(RequestAttempt).order_by(
                            RequestAttempt.request_id, RequestAttempt.attempt_number
                        )
                    )
                ).all()
                return list(logs), list(attempts)
        finally:
            await engine.dispose()

    return asyncio.run(load())


def _real(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> TestClient:
    return make_client(real_shaped_providers(*upstreams))


# Authentication, authorization and tenant isolation: tests/api/test_auth_and_tenancy.py


# --- successful generation -----------------------------------------------------------------


def test_mock_generation_is_labelled_simulated_and_logged(
    make_client: ClientFactory, seeded_url: str
) -> None:
    response = make_client().post(
        "/api/v1/generate",
        json={**SIMPLE, "request_id": "r-1", "prompt_version": "v3"},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulated"] is True
    assert body["content"].startswith("[SIMULATED]")
    assert body["provider"] == "mock"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["client_request_id"] == "r-1"
    assert body["tenant"] == "acme-saas"
    assert body["routing"]["policy_version"] == "rw-2026.11-v1"
    assert "SIMULATED_PROVIDER" in body["routing"]["reason_codes"]
    assert body["cost"]["cost_status"] == "unavailable"
    assert body["cost"]["actual_charge_usd"] is None
    assert "Simulated" in body["cost"]["note"]
    assert body["fallback"]["used"] is False

    logs, attempts = db_rows(seeded_url)
    assert len(logs) == 1 and len(attempts) == 1
    log = logs[0]
    assert str(log.id) == body["request_id"]
    assert log.status == "succeeded"
    assert log.simulated is True
    assert log.prompt_version == "v3"
    assert log.prompt_sha256 and len(log.prompt_sha256) == 64
    assert log.decision["policy_version"] == "rw-2026.11-v1"
    assert log.decision["execution"]["outcome"] == "SUCCEEDED"
    assert attempts[0].reason_code == "PRIMARY"


def test_real_shaped_success_accounting(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
) -> None:
    groq_up, _ = upstreams
    response = _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulated"] is False
    assert (body["provider"], body["model"]) == ("groq", GPT20)
    assert body["content"] == f"answer from {GPT20}"
    assert body["usage"] == {
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
        "reasoning_tokens": None,  # the fake completion reports none
    }
    cost = body["cost"]
    assert cost["cost_status"] == "free_tier" and cost["actual_charge_usd"] == "0E-8"
    # 12 * 0.075/M + 5 * 0.30/M
    assert cost["estimated_list_cost_usd"] == "0.00000240"
    assert cost["list_cost_status"] == "estimated"
    assert cost["pricing_source_url"] == "https://console.groq.com/docs/models"
    assert "not money spent" in cost["note"]
    assert groq_up.calls == [GPT20]

    _, attempts = db_rows(seeded_url)
    assert attempts[0].pricing_snapshot_id is not None
    assert attempts[0].cost_status == "free_tier"


def test_routing_explanation_lists_exclusions(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    body = (
        _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS).json()
    )
    routing = body["routing"]
    assert routing["explanation"].startswith("Complexity score")
    excluded = {e["model"]: e["reasons"] for e in routing["excluded"]}
    assert "SIMULATED_EXCLUDED" in excluded["mock/mock-small"]
    assert "PROVIDER_DISABLED" in excluded["ollama/qwen2.5:1.5b"]
    assert routing["fallback_chain"][0] == f"groq/{GPT120}"


# --- failure modes ---------------------------------------------------------------------------


def test_timeout_then_retry_succeeds(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
) -> None:
    groq_up, _ = upstreams
    groq_up.script(GPT20, httpx.ReadTimeout("slow"))
    body = (
        _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS).json()
    )
    assert [a["reason_code"] for a in body["fallback"]["attempts"]] == [
        "PRIMARY",
        "RETRY_AFTER_TIMEOUT",
    ]
    assert body["fallback"]["used"] is False  # same model
    assert body["fallback"]["failed_attempts_without_usage"] == 1
    _, attempts = db_rows(seeded_url)
    assert [a.status for a in attempts] == ["timeout", "succeeded"]


def test_rate_limit_falls_back_without_retrying(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    groq_up, _ = upstreams
    groq_up.script(
        GPT20, json_response(429, {"error": {"message": "rate limit"}}, {"retry-after": "3"})
    )
    body = (
        _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS).json()
    )
    assert groq_up.calls == [GPT20, GPT120]
    assert [(a["model"], a["reason_code"]) for a in body["fallback"]["attempts"]] == [
        (GPT20, "PRIMARY"),
        (GPT120, "FALLBACK_AFTER_RATE_LIMITED"),
    ]
    assert body["fallback"]["used"] is True


def test_invalid_credentials_fall_back_to_other_provider(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    groq_up, or_up = upstreams
    groq_up.script(
        GPT20, json_response(401, {"error": {"message": f"Invalid API Key {FAKE_GROQ_KEY}"}})
    )
    or_up.default_usage = {"cost": 0}
    response = _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS)
    body = response.json()
    assert body["provider"] == "openrouter"
    assert groq_up.calls == [GPT20]  # remaining Groq models skipped after the auth failure
    assert {"model": f"groq/{GPT120}", "reason": "PROVIDER_AUTH_FAILED"} in body["fallback"][
        "skipped"
    ]
    assert body["cost"]["cost_status"] == "reported"  # OpenRouter reported usage.cost
    assert FAKE_GROQ_KEY not in response.text


def test_malformed_response_falls_back(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    groq_up, _ = upstreams
    groq_up.script(GPT20, httpx.Response(200, content=b"<html>oops</html>"))
    body = (
        _real(make_client, upstreams).post("/api/v1/generate", json=SIMPLE, headers=HEADERS).json()
    )
    assert body["model"] == GPT120
    assert body["fallback"]["attempts"][0]["status"] == "malformed_response"


def test_all_fallbacks_fail(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
) -> None:
    for upstream in upstreams:
        upstream.fail_with = 503
    client = _real(make_client, upstreams)
    response = client.post(
        "/api/v1/generate", json={**SIMPLE, "request_id": "all-fail"}, headers=HEADERS
    )
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "ALL_PROVIDERS_FAILED"
    attempts = error["details"]["fallback"]["attempts"]
    assert attempts and all(a["status"] == "server_error" for a in attempts)
    assert error["request_id"] == response.headers["X-Request-ID"]

    logs, rows = db_rows(seeded_url)
    assert logs[0].status == "failed" and logs[0].error_code == "ALL_PROVIDERS_FAILED"
    assert logs[0].attempt_count == len(rows) == len(attempts)


def test_circuit_breaker_excludes_failing_model_on_next_request(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    groq_up, _ = upstreams
    client = make_client(real_shaped_providers(*upstreams), circuit_failure_threshold=2)
    groq_up.script(GPT20, httpx.ReadTimeout("1"), httpx.ReadTimeout("2"))  # primary + retry
    client.post("/api/v1/generate", json=SIMPLE, headers=HEADERS)
    body = client.post("/api/v1/generate", json=SIMPLE, headers=HEADERS).json()
    assert "CIRCUIT_OPEN" in body["routing"]["reason_codes"]
    excluded = {e["model"]: e["reasons"] for e in body["routing"]["excluded"]}
    assert "CIRCUIT_OPEN" in excluded[f"groq/{GPT20}"]
    assert body["model"] == GPT120


# --- eligibility, budget, paid models ------------------------------------------------------


def test_budget_too_small_is_rejected_with_reasons(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
) -> None:
    response = _real(make_client, upstreams).post(
        "/api/v1/generate", json={**SIMPLE, "max_cost_usd": "0.00000001"}, headers=HEADERS
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "NO_ELIGIBLE_MODEL"
    reasons = {r for e in error["details"]["routing"]["excluded"] for r in e["reasons"]}
    assert {"BUDGET_CONSTRAINT", "PRICE_UNKNOWN"} <= reasons
    assert upstreams[0].calls == [] and upstreams[1].calls == []
    logs, _ = db_rows(seeded_url)
    assert logs[0].status == "rejected_policy"


def test_capability_constraint_rejects_impossible_request(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    response = _real(make_client, upstreams).post(
        "/api/v1/generate",
        json={
            **SIMPLE,
            "response_format": "json",
            "constraints": {"models": ["openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"]},
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    excluded = {
        e["model"]: e["reasons"] for e in response.json()["error"]["details"]["routing"]["excluded"]
    }
    assert "CAPABILITY_MISSING" in excluded["openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"]


def test_paid_model_in_registry_refuses_startup(seeded_url: str, tmp_path: Path) -> None:
    registry = tmp_path / "models.yaml"
    registry.write_text(
        "models:\n  - {provider: groq, model_id: x, display_name: x, tier: small, billing: paid,\n"
        "     context_window: 1000, max_output_tokens: 100, verified_on: 2026-11-03,\n"
        "     source_url: 'https://example.com'}\n",
        encoding="utf-8",
    )
    settings = make_settings(seeded_url, model_registry_path=registry, verify_model_catalog=False)
    with (
        pytest.raises(ValueError, match="paid models are enabled"),
        TestClient(create_app(settings)),
    ):
        pass


# --- idempotency -----------------------------------------------------------------------------


def test_duplicate_request_id_is_rejected_before_calling_provider(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
) -> None:
    client = _real(make_client, upstreams)
    first = client.post("/api/v1/generate", json={**SIMPLE, "request_id": "dup-1"}, headers=HEADERS)
    second = client.post(
        "/api/v1/generate", json={**SIMPLE, "request_id": "dup-1"}, headers=HEADERS
    )
    assert first.status_code == 200
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "DUPLICATE_REQUEST_ID"
    assert error["details"] == {
        "original_request_id": first.json()["request_id"],
        "original_status": "succeeded",
    }
    assert upstreams[0].calls == [GPT20]  # provider called once

    other_tenant = DOCFLOW_HEADERS
    assert (
        client.post(
            "/api/v1/generate", json={**SIMPLE, "request_id": "dup-1"}, headers=other_tenant
        ).status_code
        == 200
    )
    logs, _ = db_rows(seeded_url)
    assert len(logs) == 2


# --- validation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"task_type": "classification"},  # neither prompt nor messages
        {**SIMPLE, "messages": [{"role": "user", "content": "x"}]},  # both
        {**SIMPLE, "tenant_id": "docflow"},  # tenant comes from auth, never the body
        {**SIMPLE, "base_url": "https://evil.example"},  # no client-supplied endpoints
        {**SIMPLE, "task_type": "poetry"},
        {**SIMPLE, "max_output_tokens": 100_000},
        {**SIMPLE, "request_id": "has spaces"},
        {"messages": [{"role": "system", "content": "only system"}], "task_type": "chat"},
    ],
)
def test_invalid_requests_rejected(make_client: ClientFactory, payload: dict[str, Any]) -> None:
    response = make_client().post("/api/v1/generate", json=payload, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_validation_errors_do_not_echo_prompt(make_client: ClientFactory) -> None:
    response = make_client().post(
        "/api/v1/generate", json={"prompt": SECRET_PROMPT, "task_type": "nope"}, headers=HEADERS
    )
    assert response.status_code == 422
    assert SECRET_PROMPT not in response.text


def test_oversized_body_rejected(make_client: ClientFactory) -> None:
    response = make_client().post(
        "/api/v1/generate",
        content=b'{"prompt": "' + b"x" * 600_000 + b'", "task_type": "chat"}',
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


# --- secrets and content never leak ----------------------------------------------------------


def test_no_secret_or_prompt_leakage_in_logs_db_or_errors(
    make_client: ClientFactory,
    upstreams: tuple[ScriptedUpstream, ScriptedUpstream],
    seeded_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    groq_up, or_up = upstreams
    echo = f"bad key {FAKE_GROQ_KEY} {FAKE_OPENROUTER_KEY}"
    groq_up.script(GPT20, json_response(401, {"error": {"message": echo}}))
    or_up.script(
        "google/gemma-4-26b-a4b-it:free",
        json_response(500, {"error": {"code": 500, "message": echo}}),
    )
    client = _real(make_client, upstreams)
    response = client.post(
        "/api/v1/generate", json={"prompt": SECRET_PROMPT, "task_type": "chat"}, headers=HEADERS
    )
    out = capsys.readouterr()
    logs, attempts = db_rows(seeded_url)
    stored = (
        json.dumps([log.decision for log in logs])
        + repr([a._asdict() for a in attempts])
        + repr([log._asdict() for log in logs])
    )
    for haystack in (response.text, out.out, out.err, stored):
        assert FAKE_GROQ_KEY not in haystack
        assert FAKE_OPENROUTER_KEY not in haystack
        assert ADMIN not in haystack
        assert SECRET_PROMPT not in haystack


# --- catalog endpoints ------------------------------------------------------------------------


def test_models_and_providers_endpoints(
    make_client: ClientFactory, upstreams: tuple[ScriptedUpstream, ScriptedUpstream]
) -> None:
    client = _real(make_client, upstreams)
    models = client.get("/api/v1/models")
    providers = client.get("/api/v1/providers")
    assert models.status_code == providers.status_code == 200
    by_key = {f"{m['provider']}/{m['model_id']}": m for m in models.json()["models"]}
    assert by_key[f"groq/{GPT20}"]["list_price"]["input_usd_per_mtok"] == "0.075"
    assert by_key["groq/llama-3.1-8b-instant"]["list_price"] is None
    assert by_key["mock/mock-small"]["list_price"]["simulated"] is True
    names = {p["name"]: p for p in providers.json()["providers"]}
    assert names["openrouter"]["max_retries"] == 0
    assert names["groq"]["charge_basis"] == "free_tier"
    for text in (models.text, providers.text):
        assert FAKE_GROQ_KEY not in text and FAKE_OPENROUTER_KEY not in text
