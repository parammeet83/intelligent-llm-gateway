from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_keys import verify_api_key
from app.core.config import BACKEND_ROOT
from app.db.models import ApiKey, PricingSnapshot, ProviderModel, Tenant
from app.providers.catalog import load_catalog
from app.seed import DEMO_TENANTS, run_seed
from tests.conftest import TEST_PEPPER

CATALOG = load_catalog(BACKEND_ROOT / "config" / "models.yaml")
PRICED = sum(1 for m in CATALOG.models if m.pricing is not None)


async def _count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_seed_creates_registry_tenants_and_hashed_keys(session: AsyncSession) -> None:
    report = await run_seed(session, CATALOG, TEST_PEPPER)

    assert report.models_created == len(CATALOG.models)
    assert report.pricing_created == PRICED
    assert report.tenants_created == len(DEMO_TENANTS)
    assert report.new_keys and set(report.new_keys) == {t["slug"] for t in DEMO_TENANTS}

    keys = (await session.scalars(select(ApiKey))).all()
    for key in keys:
        plaintext = next(v for v in report.new_keys.values() if v.startswith(key.key_prefix))
        assert plaintext not in key.key_hash
        assert verify_api_key(plaintext, key.key_hash, TEST_PEPPER)

    models = {m.key: m for m in (await session.scalars(select(ProviderModel))).all()}
    for spec in CATALOG.models:
        row = models[spec.key]
        # Priced models link to a snapshot; unpriced ones stay unlinked, never a $0 snapshot.
        assert (row.pricing_snapshot_id is not None) == (spec.pricing is not None)
    assert all(m.simulated for m in models.values() if m.provider == "mock")


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await run_seed(session, CATALOG, TEST_PEPPER)
    second = await run_seed(session, CATALOG, TEST_PEPPER)

    assert second.models_created == 0
    assert second.models_updated == len(CATALOG.models)
    assert second.pricing_created == 0
    assert second.tenants_created == 0
    assert second.new_keys == {}
    assert await _count(session, Tenant) == len(DEMO_TENANTS)
    assert await _count(session, ApiKey) == len(DEMO_TENANTS)
    assert await _count(session, PricingSnapshot) == PRICED


async def test_registry_only_seed(session: AsyncSession) -> None:
    report = await run_seed(session, CATALOG, TEST_PEPPER, demo_tenants=False)
    assert report.tenants_created == 0
    assert await _count(session, Tenant) == 0
    assert await _count(session, ProviderModel) == len(CATALOG.models)
