"""Routing policy configuration (config/routing_policy.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Tier = Literal["small", "medium", "premium"]
TIER_ORDER: dict[str, int] = {"small": 0, "medium": 1, "premium": 2}
TaskType = Literal[
    "classification", "extraction", "chat", "qa", "summarization", "creative", "code", "reasoning"
]


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens_per_1k: float = Field(ge=0)
    input_tokens_max: float = Field(ge=0)
    output_over_1024: float = Field(ge=0)
    output_over_4096: float = Field(ge=0)
    json_output: float = Field(ge=0)
    multi_step_per_match: float = Field(ge=0)
    multi_step_max: float = Field(ge=0)
    constraint_per_match: float = Field(ge=0)
    constraint_max: float = Field(ge=0)
    reasoning_per_match: float = Field(ge=0)
    reasoning_max: float = Field(ge=0)
    math_per_match: float = Field(ge=0)
    math_max: float = Field(ge=0)
    code_block: float = Field(ge=0)


class TierThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medium: float
    premium: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not 0 < self.medium < self.premium <= 100:
            raise ValueError("tier thresholds must satisfy 0 < medium < premium <= 100")
        return self


class LatencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_samples: int = Field(ge=1)


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_estimate_safety_factor: float = Field(ge=1.0)


class RoutingPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    tier_thresholds: TierThresholds
    task_type_priors: dict[TaskType, float]
    weights: Weights
    high_quality_floor: Tier
    selection: Literal["cheapest_capable", "lowest_tier_first"] = "cheapest_capable"
    fallback_only_providers: list[str] = Field(default_factory=list)
    latency: LatencyConfig
    budget: BudgetConfig

    @model_validator(mode="after")
    def _all_task_types(self) -> Self:
        missing = set(TaskType.__args__) - set(self.task_type_priors)  # type: ignore[attr-defined]
        if missing:
            raise ValueError(f"task_type_priors missing: {sorted(missing)}")
        return self


def load_policy(path: Path) -> RoutingPolicyConfig:
    return RoutingPolicyConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
