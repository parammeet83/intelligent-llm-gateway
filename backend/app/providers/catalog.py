"""Loads and validates config/models.yaml (the model registry source of truth)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Tier = Literal["small", "medium", "premium"]


class PricingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)
    effective_date: date
    source_url: str
    simulated: bool = False
    notes: str | None = None


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    display_name: str
    tier: Tier
    billing: Literal["free", "paid"]
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    simulated: bool = False
    verified_on: date | None = None
    source_url: str | None = None
    # No pricing = no verified list price. Never treated as $0 for a strict budget check.
    pricing: PricingSpec | None = None
    # Runtime-only settings (not persisted to provider_models).
    preview: bool = False
    timeout_s: float | None = Field(default=None, gt=0)
    # Sent with every call to this model (reasoning models only; needs the `reasoning` capability).
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    notes: str | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model_id}"

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        if self.simulated != (self.provider == "mock"):
            raise ValueError(f"{self.model_id}: only mock models may be (and must be) simulated")
        if not self.simulated and (self.verified_on is None or not self.source_url):
            raise ValueError(f"{self.model_id}: real models need verified_on and source_url")
        if self.pricing and self.pricing.simulated and not self.simulated:
            raise ValueError(f"{self.model_id}: simulated pricing on a real model")
        if self.reasoning_effort and "reasoning" not in self.capabilities:
            raise ValueError(f"{self.model_id}: reasoning_effort set on a non-reasoning model")
        return self


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelSpec]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        keys = [(m.provider, m.model_id) for m in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate (provider, model_id) in model registry")
        return self


RUNTIME_ONLY_FIELDS = frozenset({"pricing", "preview", "timeout_s", "reasoning_effort", "notes"})


def load_catalog(path: Path, *, allow_paid: bool = False) -> Catalog:
    catalog = Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if not allow_paid:
        paid = [m.model_id for m in catalog.models if m.billing == "paid" and m.enabled]
        if paid:
            raise ValueError(f"paid models are enabled but paid usage is disabled: {paid}")
    return catalog
