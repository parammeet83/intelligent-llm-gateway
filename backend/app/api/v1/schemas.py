"""Request/response schemas for /api/v1/generate and the catalog endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.routing.config import TaskType, Tier

MAX_MESSAGE_CHARS = 32_000
MAX_TOTAL_CHARS = 100_000


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Restrict routing to these providers / "provider/model" keys. Never a URL.
    providers: list[str] | None = Field(default=None, max_length=10)
    models: list[str] | None = Field(default=None, max_length=20)


class GenerateRequest(BaseModel):
    # extra="forbid": unknown fields (e.g. tenant_id, base_url) are rejected, not ignored.
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = Field(default=None, min_length=1, max_length=MAX_MESSAGE_CHARS)
    messages: list[Message] | None = Field(default=None, min_length=1, max_length=50)
    task_type: TaskType
    quality: Literal["low", "standard", "high"] = "standard"
    priority: Literal["low", "normal", "high"] = "normal"
    preferred_tier: Tier | None = None
    allow_downgrade: bool = False
    latency_target_ms: int | None = Field(default=None, ge=100, le=120_000)
    max_cost_usd: Decimal | None = Field(default=None, ge=0, le=10, max_digits=12, decimal_places=8)
    max_output_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    response_format: Literal["text", "json"] = "text"
    request_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:\-]+$"
    )
    prompt_version: str | None = Field(default=None, max_length=64)
    constraints: Constraints | None = None

    @model_validator(mode="after")
    def _one_input(self) -> Self:
        if (self.prompt is None) == (self.messages is None):
            raise ValueError("provide exactly one of `prompt` or `messages`")
        if self.messages is not None:
            if not any(m.role == "user" for m in self.messages):
                raise ValueError("`messages` must include at least one user message")
            if sum(len(m.content) for m in self.messages) > MAX_TOTAL_CHARS:
                raise ValueError(f"total message content exceeds {MAX_TOTAL_CHARS} characters")
        return self


class Usage(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    # Included in output_tokens; only when the provider reports it.
    reasoning_tokens: int | None = None


class Cost(BaseModel):
    actual_charge_usd: str | None
    cost_status: str
    estimated_list_cost_usd: str | None
    list_cost_status: str
    pricing_effective_date: str | None
    pricing_source_url: str | None
    note: str


class AttemptSummary(BaseModel):
    attempt: int
    provider: str
    model: str
    reason_code: str
    status: str
    error_code: str | None
    latency_ms: int


class Fallback(BaseModel):
    used: bool
    attempts: list[AttemptSummary]
    skipped: list[dict[str, str]]
    failed_attempts_without_usage: int


class Routing(BaseModel):
    policy_version: str
    task_type: str
    score: float
    computed_tier: str
    required_tier: str
    reason_codes: list[str]
    explanation: str
    contributions: list[dict[str, Any]]
    fallback_chain: list[str]
    excluded: list[dict[str, Any]]


class GenerateResponse(BaseModel):
    request_id: str
    client_request_id: str | None
    tenant: str
    simulated: bool
    content: str
    finish_reason: str | None
    provider: str
    model: str
    # The model ID the provider's response body reported as having generated the answer.
    provider_reported_model: str | None = None
    tier: str
    routing: Routing
    usage: Usage
    latency_ms: int
    provider_latency_ms: int
    cost: Cost
    fallback: Fallback
