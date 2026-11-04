"""Fixtures for end-to-end API tests: seeded DB + app with injected, network-free providers."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT
from app.main import create_app
from app.providers.base import Provider
from app.providers.catalog import load_catalog
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.openrouter import FreeQuotaGuard, OpenRouterProvider
from app.seed import run_seed
from tests.conftest import TEST_PEPPER, make_settings
from tests.providers.fakes import FAKE_GROQ_KEY, FAKE_OPENROUTER_KEY, completion, json_response

ADMIN = "test-admin-token-0123456789-abcdefgh"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN}"}
# Fixed, well-formed test keys installed over the seeded demo keys (hashed with TEST_PEPPER).
ACME_KEY = "rw_acmetest_" + "A" * 32
DOCFLOW_KEY = "rw_docflowt_" + "D" * 32
HEADERS = {"Authorization": f"Bearer {ACME_KEY}"}
DOCFLOW_HEADERS = {"Authorization": f"Bearer {DOCFLOW_KEY}"}


async def _seed(url: str) -> None:
    from sqlalchemy import select

    from app.auth.api_keys import hash_api_key
    from app.db.models import ApiKey, Tenant
    from app.db.session import Database

    db = Database(url)
    try:
        async with db.sessionmaker() as session:
            await run_seed(
                session, load_catalog(BACKEND_ROOT / "config" / "models.yaml"), TEST_PEPPER
            )
            for slug, key in (("acme-saas", ACME_KEY), ("docflow", DOCFLOW_KEY)):
                row = await session.scalar(select(ApiKey).join(Tenant).where(Tenant.slug == slug))
                assert row is not None
                row.key_prefix = key[: len("rw_") + 8]
                row.key_hash = hash_api_key(key, TEST_PEPPER)
            await session.commit()
    finally:
        await db.dispose()


@pytest.fixture
def seeded_url(database_url: str) -> str:
    asyncio.run(_seed(database_url))
    return database_url


class ScriptedUpstream:
    """Fake provider HTTP API: per-model queues of responses; default = a normal completion."""

    def __init__(self) -> None:
        self.queues: defaultdict[str, deque[httpx.Response | Exception]] = defaultdict(deque)
        self.calls: list[str] = []
        self.default_usage: dict[str, Any] = {}
        # When set, every unscripted call fails with this HTTP status.
        self.fail_with: int | None = None

    def script(self, model: str, *items: httpx.Response | Exception) -> None:
        self.queues[model].extend(items)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        self.calls.append(model)
        if self.queues[model]:
            item = self.queues[model].popleft()
            if isinstance(item, Exception):
                raise item
            return item
        if self.fail_with is not None:
            return json_response(
                self.fail_with, {"error": {"code": self.fail_with, "message": "down"}}
            )
        return json_response(
            200, completion(f"answer from {model}", model=model, **self.default_usage)
        )


def real_shaped_providers(
    groq_up: ScriptedUpstream, or_up: ScriptedUpstream
) -> dict[str, Provider]:
    return {
        "groq": GroqProvider(
            api_key=FAKE_GROQ_KEY, charge_basis="free_tier", transport=httpx.MockTransport(groq_up)
        ),
        "openrouter": OpenRouterProvider(
            api_key=FAKE_OPENROUTER_KEY,
            quota=FreeQuotaGuard(per_minute=20, per_day=50),
            transport=httpx.MockTransport(or_up),
        ),
    }


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(seeded_url: str) -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def factory(providers: dict[str, Provider] | None = None, **overrides: Any) -> TestClient:
        options: dict[str, Any] = {
            "admin_token": ADMIN,
            "verify_model_catalog": False,
            "retry_backoff_base_s": 0.0,
            **overrides,
        }
        settings = make_settings(seeded_url, **options)
        client = TestClient(create_app(settings, providers=providers or {"mock": MockProvider()}))
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def upstreams() -> tuple[ScriptedUpstream, ScriptedUpstream]:
    return ScriptedUpstream(), ScriptedUpstream()
