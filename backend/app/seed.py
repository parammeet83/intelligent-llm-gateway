"""Idempotent bootstrap: syncs the model registry and creates demo tenants.

Running it twice is safe. Existing tenants keep their keys; a new key is only generated (and
printed once) for a tenant that has none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_keys import generate_api_key
from app.db.models import ApiKey, PricingSnapshot, ProviderModel, RoutingPolicy, Tenant
from app.providers.catalog import RUNTIME_ONLY_FIELDS, Catalog
from app.routing.config import RoutingPolicyConfig

# Two demo tenants matching the portfolio framing on the spec card (S1-19).
DEMO_TENANTS = (
    {
        "slug": "acme-saas",
        "name": "Acme SaaS (multi-model product gateway)",
        "rate_limit_rpm": 60,
        "daily_budget_usd": Decimal("1.00"),
        "monthly_budget_usd": Decimal("20.00"),
    },
    {
        "slug": "docflow",
        "name": "DocFlow (document-processing pipeline)",
        "rate_limit_rpm": 30,
        "daily_budget_usd": Decimal("0.50"),
        "monthly_budget_usd": Decimal("10.00"),
    },
)


@dataclass
class SeedReport:
    models_created: int = 0
    models_updated: int = 0
    pricing_created: int = 0
    tenants_created: int = 0
    policy_created: bool = False
    new_keys: dict[str, str] | None = None  # tenant slug -> plaintext key (show once)


async def record_policy(
    session: AsyncSession, policy: RoutingPolicyConfig, report: SeedReport
) -> None:
    """Store the routing policy version; versions are immutable, so an edited config with an
    unchanged version is rejected rather than silently overwritten."""
    config = policy.model_dump(mode="json")
    existing = await session.scalar(
        select(RoutingPolicy).where(RoutingPolicy.version == policy.version)
    )
    if existing is not None:
        if existing.config != config:
            raise ValueError(
                f"routing policy {policy.version} changed without a version bump; "
                "update `version` in routing_policy.yaml"
            )
    else:
        session.add(RoutingPolicy(version=policy.version, config=config, is_active=True))
        report.policy_created = True
    await session.execute(
        update(RoutingPolicy).where(RoutingPolicy.version != policy.version).values(is_active=False)
    )
    if existing is not None:
        existing.is_active = True


async def sync_catalog(session: AsyncSession, catalog: Catalog, report: SeedReport) -> None:
    today = datetime.now(UTC).date()
    for spec in catalog.models:
        snapshot: PricingSnapshot | None = None
        if spec.pricing:
            snapshot = await session.scalar(
                select(PricingSnapshot).where(
                    PricingSnapshot.provider == spec.provider,
                    PricingSnapshot.model_id == spec.model_id,
                    PricingSnapshot.effective_date == spec.pricing.effective_date,
                )
            )
            if snapshot is None:
                # Snapshots are append-only; a changed price must come with a new effective_date.
                snapshot = PricingSnapshot(
                    provider=spec.provider,
                    model_id=spec.model_id,
                    input_usd_per_mtok=spec.pricing.input_usd_per_mtok,
                    output_usd_per_mtok=spec.pricing.output_usd_per_mtok,
                    effective_date=spec.pricing.effective_date,
                    retrieved_on=today,
                    source_url=spec.pricing.source_url,
                    simulated=spec.pricing.simulated,
                    notes=spec.pricing.notes,
                )
                session.add(snapshot)
                await session.flush()
                report.pricing_created += 1

        fields = spec.model_dump(exclude=set(RUNTIME_ONLY_FIELDS))
        model = await session.scalar(
            select(ProviderModel).where(
                ProviderModel.provider == spec.provider,
                ProviderModel.model_id == spec.model_id,
            )
        )
        if model is None:
            session.add(
                ProviderModel(**fields, pricing_snapshot_id=snapshot.id if snapshot else None)
            )
            report.models_created += 1
        else:
            for key, value in fields.items():
                setattr(model, key, value)
            model.pricing_snapshot_id = snapshot.id if snapshot else None
            report.models_updated += 1


async def seed_demo_tenants(session: AsyncSession, pepper: str, report: SeedReport) -> None:
    report.new_keys = {}
    for spec in DEMO_TENANTS:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if tenant is None:
            tenant = Tenant(**spec)
            session.add(tenant)
            await session.flush()
            report.tenants_created += 1
        has_key = await session.scalar(select(ApiKey.id).where(ApiKey.tenant_id == tenant.id))
        if has_key is None:
            key = generate_api_key(pepper)
            session.add(
                ApiKey(
                    tenant_id=tenant.id,
                    name="default",
                    key_prefix=key.prefix,
                    key_hash=key.key_hash,
                )
            )
            report.new_keys[tenant.slug] = key.plaintext


async def run_seed(
    session: AsyncSession,
    catalog: Catalog,
    pepper: str,
    *,
    demo_tenants: bool = True,
    policy: RoutingPolicyConfig | None = None,
) -> SeedReport:
    report = SeedReport()
    await sync_catalog(session, catalog, report)
    if policy is not None:
        await record_policy(session, policy, report)
    if demo_tenants:
        await seed_demo_tenants(session, pepper, report)
    await session.commit()
    return report
