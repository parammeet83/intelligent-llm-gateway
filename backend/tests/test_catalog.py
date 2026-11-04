from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT
from app.providers.catalog import load_catalog

REAL = """
models:
  - provider: groq
    model_id: some-model
    display_name: Some model
    tier: medium
    billing: {billing}
    context_window: 8192
    max_output_tokens: 1024
    {provenance}
"""
PROVENANCE = "verified_on: 2026-11-03\n    source_url: https://example.com/docs"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_repository_registry_is_valid() -> None:
    catalog = load_catalog(BACKEND_ROOT / "config" / "models.yaml")
    tiers = {m.tier for m in catalog.models}
    assert tiers == {"small", "medium", "premium"}
    # Every mock model and every mock price is explicitly marked as simulated.
    for model in catalog.models:
        if model.provider == "mock":
            assert model.simulated
            assert model.pricing is None or model.pricing.simulated


def test_enabled_paid_model_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, REAL.format(billing="paid", provenance=PROVENANCE))
    with pytest.raises(ValueError, match="paid models are enabled"):
        load_catalog(path)


def test_real_model_requires_provenance(tmp_path: Path) -> None:
    path = _write(tmp_path, REAL.format(billing="free", provenance=""))
    with pytest.raises(ValidationError, match="verified_on and source_url"):
        load_catalog(path)


def test_real_model_cannot_use_simulated_pricing(tmp_path: Path) -> None:
    body = REAL.format(billing="free", provenance=PROVENANCE) + (
        "    pricing:\n"
        '      input_usd_per_mtok: "0.1"\n'
        '      output_usd_per_mtok: "0.2"\n'
        "      effective_date: 2026-11-03\n"
        "      source_url: simulated://x\n"
        "      simulated: true\n"
    )
    with pytest.raises(ValidationError, match="simulated pricing"):
        load_catalog(_write(tmp_path, body))


def test_reasoning_effort_requires_a_reasoning_model(tmp_path: Path) -> None:
    body = REAL.format(billing="free", provenance=PROVENANCE) + "    reasoning_effort: low\n"
    with pytest.raises(ValidationError, match="non-reasoning model"):
        load_catalog(_write(tmp_path, body))


def test_retired_groq_models_stay_disabled() -> None:
    # Shut down 2026-08-16 (Groq deprecations page); a live call returned 404 on 2026-11-04.
    models = {m.key: m for m in load_catalog(BACKEND_ROOT / "config" / "models.yaml").models}
    for key in ("groq/llama-3.1-8b-instant", "groq/llama-3.3-70b-versatile"):
        assert not models[key].enabled
    small = models["groq/openai/gpt-oss-20b"]
    assert small.enabled and small.tier == "small" and small.reasoning_effort == "low"


def test_duplicate_models_rejected(tmp_path: Path) -> None:
    one = REAL.format(billing="free", provenance=PROVENANCE)
    body = one + one.split("models:\n", 1)[1]
    with pytest.raises(ValidationError, match="duplicate"):
        load_catalog(_write(tmp_path, body))
