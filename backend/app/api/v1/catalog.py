"""Read-only model and provider information. No credentials or internal URLs are exposed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["catalog"])


@router.get("/models")
async def list_models(request: Request) -> dict[str, Any]:
    gateway = request.app.state.gateway
    min_samples = gateway.policy.latency.min_samples
    models = []
    for m in gateway.models:
        pricing = m.pricing
        models.append(
            {
                "provider": m.provider,
                "model_id": m.model_id,
                "display_name": m.display_name,
                "tier": m.tier,
                "billing": m.billing,
                "capabilities": m.capabilities,
                "context_window": m.context_window,
                "max_output_tokens": m.max_output_tokens,
                "enabled_in_registry": m.enabled,
                "provider_enabled": m.provider in gateway.providers,
                "preview": m.preview,
                "simulated": m.simulated,
                "verified_on": m.verified_on.isoformat() if m.verified_on else None,
                "source_url": m.source_url,
                "list_price": {
                    "input_usd_per_mtok": str(pricing.input_usd_per_mtok),
                    "output_usd_per_mtok": str(pricing.output_usd_per_mtok),
                    "effective_date": pricing.effective_date.isoformat(),
                    "source_url": pricing.source_url,
                    "simulated": pricing.simulated,
                }
                if pricing
                else None,
                "runtime": gateway.health.snapshot(m.provider, m.model_id, min_samples),
            }
        )
    return {"policy_version": gateway.policy.version, "models": models}


@router.get("/providers")
async def list_providers(request: Request) -> dict[str, Any]:
    gateway = request.app.state.gateway
    return {
        "providers": [
            {
                "name": name,
                "simulated": provider.simulated,
                "charge_basis": provider.charge_basis,
                "max_retries": provider.max_retries,
                "quota_available": provider.quota_available(),
                "catalog_verified": gateway.health.catalog_status(name, "") is not None,
            }
            for name, provider in sorted(gateway.providers.items())
        ]
    }
