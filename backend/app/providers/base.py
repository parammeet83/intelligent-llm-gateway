"""Provider adapter interface and error taxonomy.

Routing and execution code depends only on this module, never on a provider's HTTP API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Literal

Role = Literal["system", "user", "assistant"]
ReasoningEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ProviderRequest:
    model_id: str
    messages: tuple[ChatMessage, ...]
    max_output_tokens: int
    temperature: float = 0.0
    response_format: Literal["text", "json"] = "text"
    timeout_s: float = 30.0
    # Set from the model registry for reasoning models; adapters that don't support it ignore it.
    reasoning_effort: ReasoningEffort | None = None


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    # A dollar amount the provider itself reported for this call. Token counts alone are never
    # a charge: Groq reports tokens but not dollars, so this stays None for Groq.
    reported_charge_usd: Decimal | None = None
    # The part of output_tokens spent on hidden reasoning, when the provider reports it.
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class RateLimitState:
    """Parsed `x-ratelimit-*` headers. Groq: `*-requests` are per day, `*-tokens` per minute."""

    model_id: str
    observed_at: float  # time.monotonic()
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_s: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_s: float | None = None


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    provider: str
    model_id: str
    usage: ProviderUsage
    latency_ms: int
    simulated: bool
    finish_reason: str | None = None


class ProviderErrorKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH = "auth_error"
    BAD_REQUEST = "bad_request"
    MODEL_NOT_FOUND = "model_not_found"
    SERVER = "server_error"
    MALFORMED = "malformed_response"
    NETWORK = "network_error"


# Transient failures worth one more try against the *same* model.
# Rate limits are deliberately excluded: retrying a 429 burns free-tier allowance
# (OpenRouter is assumed to count failed requests toward its daily quota), so they go
# straight to fallback.
_RETRYABLE = frozenset(
    {ProviderErrorKind.TIMEOUT, ProviderErrorKind.SERVER, ProviderErrorKind.NETWORK}
)

# Failures specific to one provider/model, where trying a *different* candidate can succeed.
# BAD_REQUEST is excluded: it usually means the request itself is invalid.
_FALLBACK_ELIGIBLE = _RETRYABLE | {
    ProviderErrorKind.RATE_LIMITED,
    ProviderErrorKind.QUOTA_EXHAUSTED,
    ProviderErrorKind.AUTH,
    ProviderErrorKind.MODEL_NOT_FOUND,
    ProviderErrorKind.MALFORMED,
}

# request_attempts.status values (DB CHECK constraint). Finer detail goes in error_code.
ATTEMPT_STATUS_FOR_KIND: dict[ProviderErrorKind, str] = {
    ProviderErrorKind.TIMEOUT: "timeout",
    ProviderErrorKind.RATE_LIMITED: "rate_limited",
    ProviderErrorKind.QUOTA_EXHAUSTED: "rate_limited",
    ProviderErrorKind.AUTH: "auth_error",
    ProviderErrorKind.BAD_REQUEST: "bad_request",
    ProviderErrorKind.MODEL_NOT_FOUND: "bad_request",
    ProviderErrorKind.SERVER: "server_error",
    ProviderErrorKind.MALFORMED: "malformed_response",
    ProviderErrorKind.NETWORK: "network_error",
}

# Rejections returned before any generation, so no tokens were consumed. Every other failure
# (timeout, 5xx, a network error after sending, a malformed body) may have consumed tokens the
# provider never reported: that usage is unknown, not zero.
REJECTED_BEFORE_GENERATION = frozenset(
    {
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.QUOTA_EXHAUSTED,
        ProviderErrorKind.AUTH,
        ProviderErrorKind.BAD_REQUEST,
        ProviderErrorKind.MODEL_NOT_FOUND,
    }
)


@dataclass
class ProviderError(Exception):
    kind: ProviderErrorKind
    message: str
    provider: str
    http_status: int | None = None
    retry_after_s: float | None = None
    # Tokens a failed call still consumed (e.g. an empty completion cut off by max tokens).
    usage: ProviderUsage | None = None
    # False when the request never left the gateway (e.g. local quota guard), so no
    # provider allowance was consumed.
    sent: bool = True
    details: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(f"{self.provider}: {self.kind.value}: {self.message}")

    @property
    def retryable(self) -> bool:
        return self.kind in _RETRYABLE

    @property
    def fallback_eligible(self) -> bool:
        return self.kind in _FALLBACK_ELIGIBLE

    @property
    def code(self) -> str:
        return self.kind.value.upper()


ChargeBasis = Literal["free_tier", "unavailable"]


class Provider(ABC):
    """A configured, trusted LLM endpoint. Base URLs come from settings, never from clients."""

    name: str
    simulated: bool = False
    # How to label the actual charge when the provider doesn't report a dollar amount:
    # "free_tier" only where the provider's billing terms establish $0 for this usage.
    charge_basis: ChargeBasis = "unavailable"
    # Same-model retries allowed for transient errors. Quota-sensitive providers use 0.
    max_retries: int = 1
    # Most recent rate-limit state reported by the provider's response headers (if any), for
    # quota-aware pacing. Account-level counts only; never exposed to tenants.
    last_rate_limit: RateLimitState | None = None

    @abstractmethod
    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...

    async def list_model_ids(self) -> set[str] | None:
        """Model IDs the provider currently serves, or None if that can't be determined."""
        return None

    def quota_available(self) -> bool:
        """False when a local guard knows the provider's free allowance is used up."""
        return True

    async def aclose(self) -> None:
        return None


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token for English). Used only where the provider
    doesn't report usage; such values are never labelled as reported."""
    return max(1, (len(text) + 3) // 4)
