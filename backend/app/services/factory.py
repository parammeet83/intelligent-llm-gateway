"""One place that assembles the gateway pipeline (used by the API and the benchmark runner)."""

from __future__ import annotations

from app.core.config import Settings
from app.db.session import Database
from app.providers.base import Provider
from app.providers.catalog import load_catalog
from app.resilience.health import HealthRegistry
from app.routing.config import RoutingPolicyConfig, load_policy
from app.services.executor import Executor
from app.services.gateway import GatewayService


def build_gateway(
    settings: Settings,
    db: Database,
    providers: dict[str, Provider],
    *,
    policy: RoutingPolicyConfig | None = None,
) -> GatewayService:
    catalog = load_catalog(settings.model_registry_path, allow_paid=settings.allow_paid_models)
    health = HealthRegistry(
        failure_threshold=settings.circuit_failure_threshold, open_s=settings.circuit_open_s
    )
    return GatewayService(
        db=db,
        models=catalog.models,
        policy=policy or load_policy(settings.routing_policy_path),
        health=health,
        providers=providers,
        executor=Executor(
            providers,
            health,
            deadline_s=settings.request_deadline_s,
            default_timeout_s=settings.provider_timeout_s,
            backoff_base_s=settings.retry_backoff_base_s,
            backoff_cap_s=settings.retry_backoff_cap_s,
        ),
    )
