from app.providers.base import ProviderError, ProviderErrorKind
from app.resilience.health import (
    AUTH_COOLDOWN_S,
    DEFAULT_RATE_LIMIT_COOLDOWN_S,
    BreakerState,
    CircuitBreaker,
    HealthRegistry,
    LatencyWindow,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def state_of(breaker: CircuitBreaker) -> BreakerState:
    # A function call stops mypy narrowing the property across state changes.
    return breaker.state


def _err(kind: ProviderErrorKind, **kw: object) -> ProviderError:
    return ProviderError(kind=kind, message="x", provider="groq", **kw)  # type: ignore[arg-type]


def test_breaker_opens_after_threshold_and_half_opens_after_timeout() -> None:
    clock = Clock()
    breaker = CircuitBreaker(threshold=3, open_s=30, clock=clock)
    for _ in range(2):
        breaker.on_failure()
    assert state_of(breaker) is BreakerState.CLOSED
    breaker.on_failure()
    assert state_of(breaker) is BreakerState.OPEN
    assert not breaker.allows_call()

    clock.now = 30
    assert state_of(breaker) is BreakerState.HALF_OPEN
    assert breaker.allows_call()
    breaker.on_call_started()
    assert not breaker.allows_call()  # only one probe at a time


def test_failed_probe_reopens_and_successful_probe_closes() -> None:
    clock = Clock()
    breaker = CircuitBreaker(threshold=1, open_s=10, clock=clock)
    breaker.on_failure()
    clock.now = 10
    breaker.on_call_started()
    breaker.on_failure()
    assert state_of(breaker) is BreakerState.OPEN
    clock.now = 20
    breaker.on_call_started()
    breaker.on_success()
    assert state_of(breaker) is BreakerState.CLOSED
    assert breaker.failures == 0


def test_success_resets_consecutive_failures() -> None:
    breaker = CircuitBreaker(threshold=2, open_s=10)
    breaker.on_failure()
    breaker.on_success()
    breaker.on_failure()
    assert state_of(breaker) is BreakerState.CLOSED


def test_latency_percentile_nearest_rank() -> None:
    window = LatencyWindow(size=100)
    for value in range(1, 101):
        window.add(value)
    assert window.percentile(50) == 50
    assert window.percentile(95) == 95
    window = LatencyWindow(size=3)
    for value in (5, 10, 1000, 20):
        window.add(value)
    assert sorted(window.samples) == [10, 20, 1000]


def test_rate_limit_puts_only_that_model_in_cooldown() -> None:
    clock = Clock()
    health = HealthRegistry(clock=clock)
    health.record_failure("groq", "a", _err(ProviderErrorKind.RATE_LIMITED, retry_after_s=5.0))
    assert health.exclusion("groq", "a") == "RATE_LIMIT_COOLDOWN"
    assert health.exclusion("groq", "b") is None
    assert health.breaker_state("groq", "a") is BreakerState.CLOSED  # 429 isn't a breaker failure
    clock.now = 5
    assert health.exclusion("groq", "a") is None


def test_rate_limit_without_retry_after_uses_default_cooldown() -> None:
    clock = Clock()
    health = HealthRegistry(clock=clock)
    health.record_failure("groq", "a", _err(ProviderErrorKind.RATE_LIMITED))
    clock.now = DEFAULT_RATE_LIMIT_COOLDOWN_S - 1
    assert health.exclusion("groq", "a") == "RATE_LIMIT_COOLDOWN"


def test_invalid_credentials_lock_out_the_whole_provider() -> None:
    clock = Clock()
    health = HealthRegistry(clock=clock)
    health.record_failure("groq", "a", _err(ProviderErrorKind.AUTH, http_status=401))
    assert health.exclusion("groq", "a") == "PROVIDER_AUTH_FAILED"
    assert health.exclusion("groq", "other-model") == "PROVIDER_AUTH_FAILED"
    assert health.exclusion("openrouter", "x") is None
    clock.now = AUTH_COOLDOWN_S
    assert health.exclusion("groq", "a") is None


def test_local_quota_refusal_does_not_lock_provider() -> None:
    health = HealthRegistry()
    health.record_failure(
        "openrouter", "m:free", _err(ProviderErrorKind.QUOTA_EXHAUSTED, sent=False)
    )
    assert health.exclusion("openrouter", "m:free") is None


def test_bad_request_does_not_affect_health() -> None:
    health = HealthRegistry(failure_threshold=1)
    health.record_failure("groq", "a", _err(ProviderErrorKind.BAD_REQUEST))
    assert health.exclusion("groq", "a") is None


def test_catalog_marks_missing_models_unavailable() -> None:
    health = HealthRegistry()
    assert health.catalog_status("groq", "a") is None
    health.set_catalog("groq", {"a"})
    assert health.exclusion("groq", "a") is None
    assert health.exclusion("groq", "gone") == "MODEL_UNAVAILABLE"
    health.set_catalog("groq", None)  # refresh failed -> back to unverified, not excluded
    assert health.exclusion("groq", "gone") is None


def test_model_not_found_marks_unavailable_until_catalog_refresh() -> None:
    health = HealthRegistry()
    health.record_failure("groq", "a", _err(ProviderErrorKind.MODEL_NOT_FOUND))
    assert health.exclusion("groq", "a") == "MODEL_UNAVAILABLE"
    health.set_catalog("groq", {"a"})
    assert health.exclusion("groq", "a") is None


def test_p95_requires_minimum_samples() -> None:
    health = HealthRegistry()
    for latency in (100, 200, 300, 400):
        health.record_success("groq", "a", latency)
    assert health.p95_ms("groq", "a", min_samples=5) is None
    health.record_success("groq", "a", 500)
    assert health.p95_ms("groq", "a", min_samples=5) == 500
