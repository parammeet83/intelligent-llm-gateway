"""Usage, cost and reliability aggregates over request_logs.

Computed in Python from a bounded row set rather than with SQL percentile functions, so results
are identical on SQLite and PostgreSQL. Fine at portfolio scale (capped at MAX_ROWS per query;
the response says when the cap was hit).

Actual charges and estimated list costs are summed separately and never added together.
"""

from __future__ import annotations

import itertools
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequestLog, Tenant

MAX_ROWS = 50_000
Bucket = Literal["hour", "day"]
_ZERO = Decimal(0)


def percentile(values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(pct / 100 * len(ordered))) - 1]


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.00000001")))


class _Group:
    def __init__(self) -> None:
        self.requests = 0
        self.succeeded = 0
        self.failed = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.actual = _ZERO
        self.actual_known = 0
        self.actual_unknown = 0
        self.listed = _ZERO
        self.listed_known = 0
        self.listed_unknown = 0
        self.free_tier = 0
        self.latencies: list[int] = []

    def add(self, row: Any) -> None:
        self.requests += 1
        if row.status == "succeeded":
            self.succeeded += 1
            if row.latency_ms is not None:
                self.latencies.append(row.latency_ms)
        elif row.status == "failed":
            self.failed += 1
        self.input_tokens += row.input_tokens or 0
        self.output_tokens += row.output_tokens or 0
        if row.status in ("succeeded", "failed"):
            if row.cost_status in ("reported", "free_tier", "estimated"):
                self.actual += Decimal(row.actual_charge_usd or 0)
                self.actual_known += 1
                if row.cost_status == "free_tier":
                    self.free_tier += 1
            else:
                self.actual_unknown += 1
            if row.list_cost_status == "estimated":
                self.listed += Decimal(row.estimated_list_cost_usd or 0)
                self.listed_known += 1
            else:
                self.listed_unknown += 1

    def to_dict(self) -> dict[str, Any]:
        executed = self.succeeded + self.failed
        return {
            "requests": self.requests,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "success_rate": round(self.succeeded / executed, 4) if executed else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "actual_charge_usd": _money(self.actual),
            "actual_charge_known_requests": self.actual_known,
            "actual_charge_unknown_requests": self.actual_unknown,
            "free_tier_requests": self.free_tier,
            "estimated_list_cost_usd": _money(self.listed),
            "estimated_list_cost_known_requests": self.listed_known,
            "estimated_list_cost_unknown_requests": self.listed_unknown,
            "cost_per_successful_request_usd": _money(self.listed / self.succeeded)
            if self.succeeded and self.listed_known
            else None,
            "latency_p50_ms": percentile(self.latencies, 50),
            "latency_p95_ms": percentile(self.latencies, 95),
        }


_HISTOGRAM_EDGES = [250, 500, 1000, 2000, 5000, 10000, 30000]


def _histogram(latencies: list[int]) -> list[dict[str, Any]]:
    counts = [0] * (len(_HISTOGRAM_EDGES) + 1)
    for value in latencies:
        index = next(
            (i for i, edge in enumerate(_HISTOGRAM_EDGES) if value < edge), len(_HISTOGRAM_EDGES)
        )
        counts[index] += 1
    labels = [f"<{_HISTOGRAM_EDGES[0]}"]
    labels += [f"{a}-{b}" for a, b in itertools.pairwise(_HISTOGRAM_EDGES)]
    labels += [f">={_HISTOGRAM_EDGES[-1]}"]
    return [{"bucket_ms": label, "count": c} for label, c in zip(labels, counts, strict=True)]


def _bucket_key(created: datetime, bucket: Bucket) -> str:
    if bucket == "hour":
        return created.strftime("%Y-%m-%dT%H:00")
    return created.strftime("%Y-%m-%d")


async def summarize(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    tenant_id: uuid.UUID | None = None,
    bucket: Bucket = "day",
    include_tenants: bool = False,
) -> dict[str, Any]:
    query = (
        select(
            RequestLog.tenant_id,
            RequestLog.status,
            RequestLog.created_at,
            RequestLog.latency_ms,
            RequestLog.input_tokens,
            RequestLog.output_tokens,
            RequestLog.actual_charge_usd,
            RequestLog.cost_status,
            RequestLog.estimated_list_cost_usd,
            RequestLog.list_cost_status,
            RequestLog.selected_provider,
            RequestLog.selected_model,
            RequestLog.routing_tier,
            RequestLog.fallback_used,
            RequestLog.simulated,
        )
        .where(RequestLog.created_at >= since, RequestLog.created_at < until)
        .order_by(RequestLog.created_at)
        .limit(MAX_ROWS + 1)
    )
    if tenant_id is not None:
        query = query.where(RequestLog.tenant_id == tenant_id)
    rows = (await session.execute(query)).all()
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    total = _Group()
    by_provider: defaultdict[str, _Group] = defaultdict(_Group)
    by_model: defaultdict[str, _Group] = defaultdict(_Group)
    by_tier: defaultdict[str, _Group] = defaultdict(_Group)
    by_tenant: defaultdict[str, _Group] = defaultdict(_Group)
    series: defaultdict[str, _Group] = defaultdict(_Group)
    statuses: defaultdict[str, int] = defaultdict(int)
    fallbacks = simulated = 0

    for row in rows:
        total.add(row)
        statuses[row.status] += 1
        series[_bucket_key(row.created_at, bucket)].add(row)
        if row.selected_provider and row.status in ("succeeded", "failed"):
            by_provider[row.selected_provider].add(row)
            by_model[f"{row.selected_provider}/{row.selected_model}"].add(row)
        if row.routing_tier and row.status in ("succeeded", "failed"):
            by_tier[row.routing_tier].add(row)
        if include_tenants:
            by_tenant[str(row.tenant_id)].add(row)
        fallbacks += 1 if row.fallback_used else 0
        simulated += 1 if row.simulated else 0

    executed = total.succeeded + total.failed
    tenant_names: dict[str, str] = {}
    if include_tenants and by_tenant:
        for tid, slug in (
            await session.execute(
                select(Tenant.id, Tenant.slug).where(
                    Tenant.id.in_([uuid.UUID(t) for t in by_tenant])
                )
            )
        ).all():
            tenant_names[str(tid)] = slug

    def grouped(groups: dict[str, _Group], key: str) -> list[dict[str, Any]]:
        return [{key: name, **g.to_dict()} for name, g in sorted(groups.items())]

    tier_traffic = {name: g.requests for name, g in by_tier.items()}
    tier_total = sum(tier_traffic.values())
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat(), "bucket": bucket},
        "truncated": truncated,
        "totals": {
            **total.to_dict(),
            "rejected_rate_limit": statuses.get("rejected_rate_limit", 0),
            "rejected_budget": statuses.get("rejected_budget", 0),
            "rejected_policy": statuses.get("rejected_policy", 0),
            "pending": statuses.get("pending", 0),
            "fallback_rate": round(fallbacks / executed, 4) if executed else None,
            "rate_limit_rejection_rate": round(
                statuses.get("rejected_rate_limit", 0) / total.requests, 4
            )
            if total.requests
            else None,
            "simulated_requests": simulated,
        },
        "by_status": dict(statuses),
        "by_provider": grouped(by_provider, "provider"),
        "by_model": grouped(by_model, "model"),
        "by_tier": [
            {
                "tier": name,
                "share": round(g.requests / tier_total, 4) if tier_total else None,
                **g.to_dict(),
            }
            for name, g in sorted(by_tier.items())
        ],
        "by_tenant": [
            {"tenant": tenant_names.get(tid, tid), **g.to_dict()}
            for tid, g in sorted(by_tenant.items())
        ]
        if include_tenants
        else None,
        "timeseries": grouped(series, "bucket"),
        "latency_histogram": _histogram(total.latencies),
    }


def window(days: int, *, now: datetime) -> tuple[datetime, datetime]:
    return now - timedelta(days=days), now + timedelta(seconds=1)
