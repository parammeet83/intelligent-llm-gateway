"""Builds the enabled provider adapters from settings.

Base URLs are fixed per provider (or, for Ollama, a validated localhost URL). Clients can never
supply one. Credentials are read from settings only and passed straight to the adapter.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import Settings
from app.providers.base import Provider
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.openrouter import FreeQuotaGuard, OpenRouterProvider
from app.resilience.health import HealthRegistry

logger = logging.getLogger(__name__)


def build_providers(settings: Settings) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    if settings.mock_provider_enabled:
        providers["mock"] = MockProvider()
    if settings.groq_enabled and settings.groq_api_key:
        providers["groq"] = GroqProvider(
            api_key=settings.groq_api_key.get_secret_value(),
            charge_basis="free_tier" if settings.groq_billing_plan == "free" else "unavailable",
        )
    if settings.openrouter_enabled and settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(
            api_key=settings.openrouter_api_key.get_secret_value(),
            quota=FreeQuotaGuard(
                per_minute=settings.openrouter_free_rpm, per_day=settings.openrouter_free_rpd
            ),
        )
    if settings.ollama_enabled:
        providers["ollama"] = OllamaProvider(base_url=settings.ollama_base_url)
    if not providers:
        raise RuntimeError("No providers enabled. Set MOCK_PROVIDER_ENABLED=true for local dev.")
    return providers


async def refresh_catalogs(providers: dict[str, Provider], health: HealthRegistry) -> None:
    """Record which models each provider currently lists. Failures leave status 'unverified'."""

    async def one(name: str, provider: Provider) -> None:
        ids = await provider.list_model_ids()
        health.set_catalog(name, ids)
        logger.info(
            "model_catalog_refreshed",
            extra={"provider": name, "verified": ids is not None, "count": len(ids or ())},
        )
        if isinstance(provider, OpenRouterProvider):
            await provider.sync_quota()

    await asyncio.gather(*(one(n, p) for n, p in providers.items() if not p.simulated))
