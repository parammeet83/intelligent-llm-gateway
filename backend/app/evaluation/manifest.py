"""Experiment manifest: the exact configuration a benchmark run is registered against.

A manifest pins file hashes (routing policy, model registry, scoring and reporting code), the
routing policy with its weights, every enabled model with its provider model ID and pricing
snapshot, provider retry/charge settings, and execution settings. The runner rebuilds it from the
live configuration before any network call and refuses to run if anything differs, so a result
can only ever be reported against the configuration that was registered in advance.

File hashes are taken over LF-normalised text, so a CRLF checkout doesn't change them.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from app.core.config import BACKEND_ROOT, REPO_ROOT, Settings
from app.providers.base import Provider
from app.providers.catalog import load_catalog
from app.routing.config import load_policy

EXECUTION_SETTINGS = (
    "request_deadline_s",
    "provider_timeout_s",
    "retry_backoff_base_s",
    "retry_backoff_cap_s",
    "circuit_failure_threshold",
    "circuit_open_s",
    "allow_paid_models",
    "verify_model_catalog",
    "groq_enabled",
    "groq_billing_plan",
    "openrouter_enabled",
    "ollama_enabled",
    "mock_provider_enabled",
)

_APP = BACKEND_ROOT / "app"

# Schema 1 (v3 manifests): evaluation code only. Kept exactly so v3 manifests stay comparable.
CODE_FILES = {
    "scorers": _APP / "evaluation" / "scorers.py",
    "report": _APP / "evaluation" / "report.py",
    "runner": _APP / "evaluation" / "runner.py",
    "dataset_loader": _APP / "evaluation" / "dataset.py",
}

# Schema 2 (v4+): every module on the execution path of a benchmark request.
CODE_FILES_V2 = {
    **CODE_FILES,
    "evaluation_stats": _APP / "evaluation" / "stats.py",
    "manifest": _APP / "evaluation" / "manifest.py",
    "routing_engine": _APP / "routing" / "engine.py",
    "routing_features": _APP / "routing" / "features.py",
    "routing_config": _APP / "routing" / "config.py",
    "provider_interface": _APP / "providers" / "base.py",
    "provider_http_and_usage_extraction": _APP / "providers" / "http.py",
    "provider_registry": _APP / "providers" / "registry.py",
    "model_catalog_loader": _APP / "providers" / "catalog.py",
    "executor_retries_fallbacks": _APP / "services" / "executor.py",
    "gateway_pipeline": _APP / "services" / "gateway.py",
    "gateway_factory": _APP / "services" / "factory.py",
    "health_circuit_breaker": _APP / "resilience" / "health.py",
    "cost_accounting": _APP / "accounting" / "cost.py",
    "budget_accounting": _APP / "accounting" / "budget.py",
    "rate_limiting": _APP / "tenancy" / "rate_limit.py",
    "api_schemas": _APP / "api" / "v1" / "schemas.py",
    "settings": _APP / "core" / "config.py",
}

# Schema 3 (v5+): adds the CLI (argument handling and preflight), quota pacing, error types, and the
# dependency lock file. Modules not listed don't affect execution configuration or results: logging,
# persistence (db/*, seed.py), the HTTP API layer and main.py (the benchmark runs in-process),
# dashboard aggregates (accounting/usage.py) and auth dataclasses. See the v5 changelog audit.
CODE_FILES_V3 = {
    **CODE_FILES_V2,
    "cli": _APP / "cli.py",
    "quota_pacing": _APP / "evaluation" / "pacing.py",
    "error_types": _APP / "core" / "errors.py",
    "dependency_lock": BACKEND_ROOT / "uv.lock",
}

# Schema 4 (v5.1+): every application module loaded on the benchmark execution path (the import
# closure of app.cli, app.evaluation.{runner,preflight,manifest,report} and app.providers.registry,
# checked by a test so it can't silently grow), plus project metadata and the dependency lock.
EXECUTION_MODULES_V4 = (
    "__init__.py",
    "accounting/__init__.py",
    "accounting/budget.py",
    "accounting/cost.py",
    "api/__init__.py",
    "api/v1/__init__.py",
    "api/v1/schemas.py",
    "auth/__init__.py",
    "auth/api_keys.py",
    "auth/keys.py",
    "cli.py",
    "core/__init__.py",
    "core/config.py",
    "core/errors.py",
    "core/logging.py",
    "db/__init__.py",
    "db/base.py",
    "db/models.py",
    "db/session.py",
    "evaluation/__init__.py",
    "evaluation/dataset.py",
    "evaluation/manifest.py",
    "evaluation/pacing.py",
    "evaluation/preflight.py",
    "evaluation/report.py",
    "evaluation/runner.py",
    "evaluation/scorers.py",
    "evaluation/stats.py",
    "providers/__init__.py",
    "providers/base.py",
    "providers/catalog.py",
    "providers/groq.py",
    "providers/http.py",
    "providers/mock.py",
    "providers/ollama.py",
    "providers/openrouter.py",
    "providers/registry.py",
    "resilience/__init__.py",
    "resilience/health.py",
    "routing/__init__.py",
    "routing/config.py",
    "routing/engine.py",
    "routing/features.py",
    "seed.py",
    "services/__init__.py",
    "services/executor.py",
    "services/factory.py",
    "services/gateway.py",
    "tenancy/__init__.py",
    "tenancy/rate_limit.py",
)
CODE_FILES_V4 = {
    **{f"app/{rel}": _APP / rel for rel in EXECUTION_MODULES_V4},
    "dependency_lock": BACKEND_ROOT / "uv.lock",
    "project_metadata": BACKEND_ROOT / "pyproject.toml",
}

EXECUTION_SETTINGS_V3 = (*EXECUTION_SETTINGS, "app_env")

# Environment variables that can reroute or alter provider HTTP traffic (httpx trust_env).
# Only their presence is recorded, never their values.
NETWORK_ENV = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)

# Adapter module per enabled provider (schema 2+).
PROVIDER_ADAPTERS = {
    "groq": _APP / "providers" / "groq.py",
    "openrouter": _APP / "providers" / "openrouter.py",
    "ollama": _APP / "providers" / "ollama.py",
    "mock": _APP / "providers" / "mock.py",
}


def text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(REPO_ROOT).as_posix()
        if resolved.is_relative_to(REPO_ROOT)
        else resolved.as_posix()
    )


def evidence_files(prereg: dict[str, Any]) -> dict[str, str]:
    """Schema 6 (v5.2.2+): the benchmark evidence the scoring and publication gate depend on (the
    dataset file, its metadata, the scoring amendment and the review attestation), located only
    through the pre-registration's own references. Paths are relative to the evaluation
    directory, like the pre-registration's, so a relocated copy (e.g. a review bundle) checks the
    same way."""
    files = {"evidence/dataset": f"datasets/{prereg['dataset']}.jsonl"}
    for key in (
        "dataset_metadata",
        "scoring_amendment",
        "review_attestation",
        "execution_schedule",
        "execution_recovery",
    ):
        if prereg.get(key):
            files[f"evidence/{key}"] = str(prereg[key]["file"])
    return files


def build_manifest(
    settings: Settings,
    providers: dict[str, Provider],
    strategies: list[str],
    *,
    schema: int = 1,
    run_params: dict[str, Any] | None = None,
    evidence: dict[str, str] | None = None,
    evidence_dir: Path = REPO_ROOT / "evaluation",
) -> dict[str, Any]:
    """`schema` 1 reproduces v3 manifests exactly. Schema 2 adds every execution-critical module
    and `execution.pacing` (concurrency, inter-request delay, case limit, code execution).
    Schema 3 adds the CLI, quota pacing, error types, the dependency lock, `execution.quota`
    (pinned provider limits and pacing rules) and `execution.runtime` (Python version, network
    environment variables present). Schema 6 = schema 5 plus the `evidence` files."""
    if schema >= 6 and not evidence:
        raise ValueError("schema 6 manifests pin the benchmark evidence files")
    from app.api.v1.schemas import GenerateRequest
    from app.evaluation.runner import STRATEGIES

    policy = load_policy(settings.routing_policy_path)
    catalog = load_catalog(settings.model_registry_path, allow_paid=settings.allow_paid_models)
    enabled = [m for m in catalog.models if m.enabled and m.provider in providers]
    files = {
        "routing_policy": Path(settings.routing_policy_path),
        "model_registry": Path(settings.model_registry_path),
        **{1: CODE_FILES, 2: CODE_FILES_V2, 3: CODE_FILES_V3}.get(schema, CODE_FILES_V4),
    }
    if schema in (2, 3):  # schema 4 already pins every adapter module
        files.update({f"provider_adapter_{n}": PROVIDER_ADAPTERS[n] for n in sorted(providers)})
    manifest: dict[str, Any] = {
        "files": {
            name: {
                "path": _display_path(path),
                "sha256": text_sha256(path),
            }
            for name, path in files.items()
        },
        "routing_policy": policy.model_dump(mode="json"),
        "models": [
            {
                "key": m.key,
                "provider": m.provider,
                "provider_model_id": m.model_id,
                "tier": m.tier,
                "billing": m.billing,
                "capabilities": list(m.capabilities),
                "reasoning_effort": m.reasoning_effort,
                "timeout_s": m.timeout_s,
                "verified_on": m.verified_on.isoformat() if m.verified_on else None,
                "pricing": None
                if m.pricing is None
                else {
                    "input_usd_per_mtok": str(m.pricing.input_usd_per_mtok),
                    "output_usd_per_mtok": str(m.pricing.output_usd_per_mtok),
                    "effective_date": m.pricing.effective_date.isoformat(),
                    "source_url": m.pricing.source_url,
                },
            }
            for m in enabled
        ],
        "expected_models": sorted(m.key for m in enabled),
        "providers": {
            name: {
                "simulated": p.simulated,
                "charge_basis": p.charge_basis,
                "max_retries": p.max_retries,
            }
            for name, p in sorted(providers.items())
        },
        "execution": {
            **{
                key: getattr(settings, key)
                for key in (EXECUTION_SETTINGS if schema < 3 else EXECUTION_SETTINGS_V3)
            },
            "temperature": GenerateRequest.model_fields["temperature"].default,
            "strategies": {
                name: {
                    "policy_overrides": STRATEGIES[name][0],
                    "request_overrides": STRATEGIES[name][1],
                }
                for name in sorted(strategies)
            },
        },
    }
    if schema >= 6 and evidence:
        manifest["files"].update(
            {
                name: {"path": f"evaluation/{rel}", "sha256": text_sha256(evidence_dir / rel)}
                for name, rel in evidence.items()
            }
        )
    if schema >= 2:
        manifest["execution"]["pacing"] = dict(run_params) if run_params is not None else None
    if schema >= 3:
        import os
        import sys

        from app.evaluation.pacing import GROQ_FREE_QUOTA, GROQ_QUOTA_V5_1, GROQ_QUOTA_V5_2

        if schema == 3:  # v5: one reservation per gateway request (superseded)
            manifest["execution"]["quota"] = (
                {"groq": copy.deepcopy(GROQ_FREE_QUOTA)} if "groq" in providers else {}
            )
        else:  # v5.1+: one reservation per provider attempt
            # schema 4 (v5.1) and schema 5 (v5.2, transactional ledger) differ only here;
            # schema 6 (v5.2.2) uses the v5.2 quota.
            quota = GROQ_QUOTA_V5_1 if schema == 4 else GROQ_QUOTA_V5_2
            manifest["execution"]["attempt_quota"] = (
                {"groq": copy.deepcopy(quota)} if "groq" in providers else {}
            )
        manifest["execution"]["runtime"] = {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            **({"implementation": sys.implementation.name} if schema >= 4 else {}),
            "network_env_present": {name: bool(os.environ.get(name)) for name in NETWORK_ENV},
        }
    return manifest


def diff(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Every path where two manifests differ."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out: list[str] = []
        for key in sorted(set(expected) | set(actual), key=str):
            out += diff(expected.get(key), actual.get(key), f"{path}.{key}" if path else str(key))
        return out
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [
            d
            for i, (e, a) in enumerate(zip(expected, actual, strict=True))
            for d in diff(e, a, f"{path}[{i}]")
        ]
    return [] if expected == actual else [path or "<root>"]


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def check_manifest(
    prereg: dict[str, Any],
    settings: Settings,
    providers: dict[str, Provider],
    strategies: list[str],
    directory: Path = REPO_ROOT / "evaluation",
    *,
    run_params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Verify the live configuration against the pre-registered manifest (if the
    pre-registration names one). Returns the manifest, or raises ValueError listing differences.

    For schema-2 manifests `run_params` (pacing) is part of the check. Without them (e.g. a
    dry `eval-validate`) everything except pacing is checked; the runner always passes them."""
    ref = prereg.get("experiment_manifest")
    if not ref:
        return None
    manifest, sha = load_manifest(directory / ref["file"])
    if sha != ref["sha256"]:
        raise ValueError(f"{ref['file']} changed since it was pre-registered")
    schema = int(manifest.get("schema", 1))
    pinned = manifest["pinned"]
    actual = build_manifest(
        settings,
        providers,
        strategies,
        schema=schema,
        run_params=run_params,
        evidence=evidence_files(prereg) if schema >= 6 else None,
        evidence_dir=directory,
    )
    if schema >= 2 and run_params is None:
        actual["execution"]["pacing"] = pinned["execution"].get("pacing")
    differences = diff(pinned, actual)
    if differences:
        shown = ", ".join(differences[:12]) + (" …" if len(differences) > 12 else "")
        raise ValueError(f"configuration differs from {ref['file']}: {shown}")
    return manifest
