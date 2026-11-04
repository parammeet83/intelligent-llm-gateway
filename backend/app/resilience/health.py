"""Per-model and per-provider health: circuit breakers, cooldowns, latency, availability.

In-memory, per process. On a single-instance free host that's the whole picture; across several
instances each would learn provider health independently (documented trade-off).

How each failure kind affects health:
  TIMEOUT / SERVER / NETWORK / MALFORMED -> counts toward the model's circuit breaker
  RATE_LIMITED                           -> model cooldown for Retry-After (or a default)
  QUOTA_EXHAUSTED                        -> provider cooldown (allowance won't return soon)
  AUTH                                   -> provider cooldown (an invalid key won't fix itself)
  MODEL_NOT_FOUND                        -> model marked unavailable until the next catalog refresh
  BAD_REQUEST                            -> no effect (the request was at fault, not the model)
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic

from app.providers.base import ProviderError, ProviderErrorKind

_BREAKER_KINDS = frozenset(
    {
        ProviderErrorKind.TIMEOUT,
        ProviderErrorKind.SERVER,
        ProviderErrorKind.NETWORK,
        ProviderErrorKind.MALFORMED,
    }
)

DEFAULT_RATE_LIMIT_COOLDOWN_S = 30.0
QUOTA_COOLDOWN_S = 3600.0
AUTH_COOLDOWN_S = 900.0


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Opens after `threshold` consecutive failures; after `open_s` lets one probe through."""

    threshold: int
    open_s: float
    clock: Callable[[], float] = monotonic
    failures: int = 0
    opened_at: float | None = None
    probe_in_flight: bool = False

    @property
    def state(self) -> BreakerState:
        if self.opened_at is None:
            return BreakerState.CLOSED
        if self.clock() - self.opened_at >= self.open_s:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def allows_call(self) -> bool:
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        return state is BreakerState.HALF_OPEN and not self.probe_in_flight

    def on_call_started(self) -> None:
        if self.state is BreakerState.HALF_OPEN:
            self.probe_in_flight = True

    def on_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.probe_in_flight = False

    def on_failure(self) -> None:
        if self.state is BreakerState.HALF_OPEN:
            self.opened_at = self.clock()  # failed probe: open again for a full period
            self.probe_in_flight = False
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


@dataclass
class LatencyWindow:
    size: int = 50
    samples: deque[int] = field(default_factory=deque)

    def add(self, latency_ms: int) -> None:
        self.samples.append(latency_ms)
        while len(self.samples) > self.size:
            self.samples.popleft()

    def percentile(self, pct: float) -> int | None:
        """Nearest-rank percentile over the window."""
        if not self.samples:
            return None
        ordered = sorted(self.samples)
        rank = max(1, math.ceil(pct / 100 * len(ordered)))
        return ordered[rank - 1]


@dataclass
class ModelHealth:
    breaker: CircuitBreaker
    latency: LatencyWindow = field(default_factory=LatencyWindow)
    cooldown_until: float = 0.0
    not_found: bool = False


class HealthRegistry:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        open_s: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._open_s = open_s
        self._clock = clock
        self._models: dict[str, ModelHealth] = {}
        self._provider_cooldown: dict[str, tuple[float, str]] = {}
        # provider -> live model IDs; a provider missing here means "not verified".
        self._catalog: dict[str, set[str]] = {}

    def _model(self, key: str) -> ModelHealth:
        if key not in self._models:
            self._models[key] = ModelHealth(
                breaker=CircuitBreaker(self._threshold, self._open_s, self._clock)
            )
        return self._models[key]

    # --- catalog ----------------------------------------------------------------------------

    def set_catalog(self, provider: str, model_ids: set[str] | None) -> None:
        if model_ids is None:
            self._catalog.pop(provider, None)
        else:
            self._catalog[provider] = model_ids
            for key, health in self._models.items():
                if key.startswith(f"{provider}/"):
                    health.not_found = False

    def catalog_status(self, provider: str, model_id: str) -> bool | None:
        """True = listed by the provider, False = missing, None = couldn't verify."""
        if provider not in self._catalog:
            return None
        return model_id in self._catalog[provider]

    # --- routing view -----------------------------------------------------------------------

    def exclusion(self, provider: str, model_id: str) -> str | None:
        """Why a model can't be called right now, as a reason code, or None if it can."""
        now = self._clock()
        until, reason = self._provider_cooldown.get(provider, (0.0, ""))
        if now < until:
            return reason
        if self.catalog_status(provider, model_id) is False:
            return "MODEL_UNAVAILABLE"
        health = self._models.get(f"{provider}/{model_id}")
        if health is None:
            return None
        if health.not_found:
            return "MODEL_UNAVAILABLE"
        if now < health.cooldown_until:
            return "RATE_LIMIT_COOLDOWN"
        if not health.breaker.allows_call():
            return "CIRCUIT_OPEN"
        return None

    def p95_ms(self, provider: str, model_id: str, min_samples: int) -> int | None:
        health = self._models.get(f"{provider}/{model_id}")
        if health is None or len(health.latency.samples) < min_samples:
            return None
        return health.latency.percentile(95)

    def breaker_state(self, provider: str, model_id: str) -> BreakerState:
        health = self._models.get(f"{provider}/{model_id}")
        return health.breaker.state if health else BreakerState.CLOSED

    # --- execution feedback -----------------------------------------------------------------

    def on_call_started(self, provider: str, model_id: str) -> None:
        self._model(f"{provider}/{model_id}").breaker.on_call_started()

    def record_success(self, provider: str, model_id: str, latency_ms: int) -> None:
        health = self._model(f"{provider}/{model_id}")
        health.breaker.on_success()
        health.latency.add(latency_ms)

    def record_failure(self, provider: str, model_id: str, error: ProviderError) -> None:
        health = self._model(f"{provider}/{model_id}")
        now = self._clock()
        if error.kind in _BREAKER_KINDS:
            health.breaker.on_failure()
        else:
            health.breaker.probe_in_flight = False
        if error.kind is ProviderErrorKind.RATE_LIMITED:
            health.cooldown_until = now + (error.retry_after_s or DEFAULT_RATE_LIMIT_COOLDOWN_S)
        elif error.kind is ProviderErrorKind.QUOTA_EXHAUSTED and error.sent:
            self._provider_cooldown[provider] = (now + QUOTA_COOLDOWN_S, "QUOTA_EXHAUSTED")
        elif error.kind is ProviderErrorKind.AUTH:
            self._provider_cooldown[provider] = (now + AUTH_COOLDOWN_S, "PROVIDER_AUTH_FAILED")
        elif error.kind is ProviderErrorKind.MODEL_NOT_FOUND:
            health.not_found = True

    def snapshot(self, provider: str, model_id: str, min_samples: int) -> dict[str, object]:
        health = self._models.get(f"{provider}/{model_id}")
        return {
            "listed_by_provider": self.catalog_status(provider, model_id),
            "circuit": self.breaker_state(provider, model_id).value,
            "exclusion": self.exclusion(provider, model_id),
            "latency_samples": len(health.latency.samples) if health else 0,
            "observed_p95_ms": self.p95_ms(provider, model_id, min_samples),
        }
