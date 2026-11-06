"""ORM models. See docs/DATABASE_SCHEMA.md for the rationale behind each table.

Enumerated values are stored as short strings guarded by CHECK constraints rather than native
PostgreSQL enums, so adding a value is a one-line migration instead of an ALTER TYPE.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow

TIERS = ("small", "medium", "premium")
BILLING_CLASSES = ("free", "paid")
# Provenance of `actual_charge_usd`.
#   reported    - the provider returned a dollar charge for this call (e.g. OpenRouter usage.cost)
#   free_tier   - $0, established by the provider's free-plan billing terms (no charge reported)
#   estimated   - computed from verified prices because the provider bills but doesn't report
#   unavailable - unknown (e.g. simulated call, failed call with no billing signal)
COST_STATUSES = ("reported", "estimated", "free_tier", "unavailable")
# Provenance of `estimated_list_cost_usd` (the shadow cost used for budgets and benchmarks).
LIST_COST_STATUSES = ("estimated", "unavailable")
REQUEST_STATUSES = (
    "pending",
    "succeeded",
    "failed",
    "rejected_auth",
    "rejected_rate_limit",
    "rejected_budget",
    "rejected_policy",
)
ATTEMPT_STATUSES = (
    "succeeded",
    "timeout",
    "rate_limited",
    "auth_error",
    "bad_request",
    "server_error",
    "malformed_response",
    "network_error",
    "circuit_open",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(_in("status", ("active", "suspended")), name="status"),
        CheckConstraint("rate_limit_rpm > 0", name="rate_limit_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    rate_limit_rpm: Mapped[int] = mapped_column(default=60, server_default=text("60"))
    # Shadow budgets, enforced on estimated list-price cost. NULL = no limit for that period.
    daily_budget_usd: Mapped[Decimal | None]
    monthly_budget_usd: Mapped[Decimal | None]
    cache_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="tenant")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    # Public, non-secret identifier shown in dashboards and logs (e.g. "rw_k3j9x2ab").
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    # HMAC-SHA256(pepper, full_key), hex. The plaintext key is never stored.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    # Set when a key is rotated with a grace period: valid until then, rejected after.
    expires_at: Mapped[datetime | None]

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")


class TenantBudgetPeriod(Base):
    """Per-period spend ledger. A row is created lazily for each (tenant, period, start)."""

    __tablename__ = "tenant_budgets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "period", "period_start"),
        CheckConstraint(_in("period", ("daily", "monthly")), name="period"),
        CheckConstraint("spent_usd >= 0", name="spent_nonnegative"),
        CheckConstraint("reserved_usd >= 0", name="reserved_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    period: Mapped[str] = mapped_column(String(8))
    period_start: Mapped[date] = mapped_column(Date)
    limit_usd: Mapped[Decimal]
    spent_usd: Mapped[Decimal] = mapped_column(default=Decimal(0), server_default=text("0"))
    reserved_usd: Mapped[Decimal] = mapped_column(default=Decimal(0), server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RateLimitWindow(Base):
    """Fixed-window request counter. Atomic upsert, so it works across instances without Redis."""

    __tablename__ = "rate_limit_windows"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    window_start: Mapped[datetime] = mapped_column(primary_key=True)
    request_count: Mapped[int] = mapped_column(default=0)


class PricingSnapshot(Base):
    """A published list price for a model, as observed on a given date. Rows are never edited:
    a price change is a new row with a new effective_date."""

    __tablename__ = "pricing_snapshots"
    __table_args__ = (
        UniqueConstraint("provider", "model_id", "effective_date"),
        CheckConstraint("input_usd_per_mtok >= 0", name="input_nonnegative"),
        CheckConstraint("output_usd_per_mtok >= 0", name="output_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(200))
    input_usd_per_mtok: Mapped[Decimal]
    output_usd_per_mtok: Mapped[Decimal]
    effective_date: Mapped[date] = mapped_column(Date)
    retrieved_on: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(500))
    # True only for fabricated prices used by the mock provider.
    simulated: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ProviderModel(TimestampMixin, Base):
    """The model registry, synced from config/models.yaml by the seed command."""

    __tablename__ = "provider_models"
    __table_args__ = (
        UniqueConstraint("provider", "model_id"),
        CheckConstraint(_in("tier", TIERS), name="tier"),
        CheckConstraint(_in("billing", BILLING_CLASSES), name="billing"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(16))
    billing: Mapped[str] = mapped_column(String(8))
    context_window: Mapped[int]
    max_output_tokens: Mapped[int]
    capabilities: Mapped[list[Any]] = mapped_column(default=list)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    simulated: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    verified_on: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(500))
    pricing_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pricing_snapshots.id", ondelete="SET NULL")
    )

    pricing: Mapped[PricingSnapshot | None] = relationship()

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model_id}"


class RoutingPolicy(Base):
    __tablename__ = "routing_policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), unique=True)
    config: Mapped[dict[str, Any]]
    is_active: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class _CostColumns:
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    actual_charge_usd: Mapped[Decimal | None]
    cost_status: Mapped[str] = mapped_column(String(16), default="unavailable")
    estimated_list_cost_usd: Mapped[Decimal | None]
    list_cost_status: Mapped[str] = mapped_column(String(16), default="unavailable")
    latency_ms: Mapped[int | None]
    simulated: Mapped[bool] = mapped_column(default=False)


class RequestLog(_CostColumns, Base):
    """One row per client request. Totals here are the *settled* figures for the request,
    never a sum that double-counts retried attempts."""

    __tablename__ = "request_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_request_id"),
        CheckConstraint(_in("status", REQUEST_STATUSES), name="status"),
        CheckConstraint(_in("cost_status", COST_STATUSES), name="cost_status"),
        CheckConstraint(_in("list_cost_status", LIST_COST_STATUSES), name="list_cost_status"),
        Index("ix_request_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_request_logs_created", "created_at"),
        Index("ix_request_logs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # RESTRICT: request history is an audit trail; tenants are suspended, not deleted.
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    client_request_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64))
    task_type: Mapped[str | None] = mapped_column(String(32))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    # Content is not stored by default: only a hash and its size.
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    input_chars: Mapped[int | None]
    routing_tier: Mapped[str | None] = mapped_column(String(16))
    policy_version: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[dict[str, Any] | None]
    selected_provider: Mapped[str | None] = mapped_column(String(32))
    selected_model: Mapped[str | None] = mapped_column(String(200))
    attempt_count: Mapped[int] = mapped_column(default=0)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    # Shadow-budget reservation held by this request: [{"period", "period_start", "amount"}].
    # Cleared on settlement; a leftover on an old pending row is charged by `app.cli reconcile`.
    budget_reservation: Mapped[list[Any] | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None]

    attempts: Mapped[list[RequestAttempt]] = relationship(
        back_populates="request", order_by="RequestAttempt.attempt_number"
    )


class RequestAttempt(_CostColumns, Base):
    """One row per provider call (including retries and fallbacks)."""

    __tablename__ = "request_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", "attempt_number"),
        CheckConstraint(_in("status", ATTEMPT_STATUSES), name="status"),
        CheckConstraint(_in("cost_status", COST_STATUSES), name="cost_status"),
        CheckConstraint(_in("list_cost_status", LIST_COST_STATUSES), name="list_cost_status"),
        Index("ix_request_attempts_provider_started", "provider", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("request_logs.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int]
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(200))
    # Why this attempt happened, e.g. PRIMARY, RETRY, FALLBACK_AFTER_TIMEOUT.
    reason_code: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24))
    error_code: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None]
    retry_after_s: Mapped[float | None]
    pricing_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pricing_snapshots.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]

    request: Mapped[RequestLog] = relationship(back_populates="attempts")


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("dataset_version", "case_key"),
        CheckConstraint(_in("difficulty", ("simple", "standard", "complex")), name="difficulty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_version: Mapped[str] = mapped_column(String(32))
    case_key: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    difficulty: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]]
    acceptance: Mapped[dict[str, Any]]
    eval_method: Mapped[str] = mapped_column(String(32))
    max_cost_usd: Mapped[Decimal | None]
    max_latency_ms: Mapped[int | None]


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(_in("status", ("running", "completed", "failed")), name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(100))
    strategy: Mapped[str] = mapped_column(String(32))
    dataset_version: Mapped[str] = mapped_column(String(32))
    policy_version: Mapped[str | None] = mapped_column(String(64))
    config_snapshot: Mapped[dict[str, Any]]
    preregistration_sha256: Mapped[str] = mapped_column(String(64))
    simulated: Mapped[bool]
    status: Mapped[str] = mapped_column(String(16), default="running")
    summary: Mapped[dict[str, Any] | None]
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]


class BenchmarkExecutionClaim(Base):
    """One row per (revision, scheduled day) ever started (v5.2.5+). The unique constraint makes a
    second start of the same scheduled day impossible, even from two concurrent processes: only
    one insert can succeed. Claims are never deleted, so a failed or interrupted day stays
    claimed."""

    __tablename__ = "benchmark_execution_claims"
    __table_args__ = (UniqueConstraint("revision", "schedule_day"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision: Mapped[str] = mapped_column(String(64))
    schedule_day: Mapped[int]
    label: Mapped[str] = mapped_column(String(100))
    claimed_at: Mapped[datetime] = mapped_column(default=utcnow)


class EvaluationResult(_CostColumns, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id"),
        CheckConstraint(_in("cost_status", COST_STATUSES), name="cost_status"),
        CheckConstraint(_in("list_cost_status", LIST_COST_STATUSES), name="list_cost_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="RESTRICT")
    )
    request_log_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("request_logs.id", ondelete="SET NULL")
    )
    passed: Mapped[bool | None]
    score: Mapped[float | None]
    provider: Mapped[str | None] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(200))
    routing_tier: Mapped[str | None] = mapped_column(String(16))
    fallback_used: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    scorer_details: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
