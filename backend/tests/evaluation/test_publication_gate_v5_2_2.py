"""Revision routewise_bench_v5.2.2: the attestation-aware publication gate.

Self-contained (no imports from other test modules) so it runs from the clean-room review bundle.
No provider is called. Tampering tests work on copies in a temporary directory; the real
attestation, metadata and dataset are only read.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import Settings
from app.evaluation import dataset as dataset_mod
from app.evaluation import manifest as manifest_mod
from app.evaluation import runner as runner_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    apply_review_attestation,
    load_dataset,
    load_execution_revision,
    load_preregistration,
)
from app.evaluation.pacing import GROQ_QUOTA_V5_2
from app.providers.groq import GroqProvider

REVISION = "routewise_bench_v5.2.2"
V5 = load_dataset("routewise_bench_v5")
ATTESTATION = "reviews/routewise_bench_v5.2.1_HUMAN_REVIEW_ATTESTATION.yaml"
# Verified against the actual repository; preserved byte-for-byte.
PRESERVED = {
    "datasets/routewise_bench_v5.jsonl": (
        "76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd"
    ),
    "datasets/routewise_bench_v5.meta.yaml": (
        "262dde03c4018fe1f79c1fe8760f32cfcce3e1624284ea6b56eafed432806ada"
    ),
    "scoring_amendment_routewise_bench_v5.2.1.yaml": (
        "bab04a1a24f2f7d52538d49472edd52579ce08ded0ed10460225498b4a4c8431"
    ),
    "routewise_bench_v5.2.1.revision.yaml": (
        "42666d44eddac1a1b9395384ba92183be0f7025ac91d867e7261b64af265a6e7"
    ),
    "preregistration_routewise_bench_v5.2.1.yaml": (
        "2a78174bc1ebd7ea78e692d31ca1097623dd6edd144416a486fcdc15f5db9070"
    ),
    "experiment_manifest_routewise_bench_v5.2.1.yaml": (
        "dd6b29f870abf4b93fa7b21fba007ac05d115496bad30568414f16ab125b850e"
    ),
    "routewise_bench_v5.2.revision.yaml": (
        "59257813e1093d512f0f6fb6459e8ee40aebede789d55908f661dca4bb06d347"
    ),
    ATTESTATION: "b7099444ac312eef336ebacbdb6e93335ba366f9de452be88cb17a97524c59ed",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prereg() -> dict[str, Any]:
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, _ = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    return prereg


PREREG = _prereg()


# --- the real attestation -------------------------------------------------------------------------


def test_preserved_artefacts_are_byte_identical() -> None:
    for rel, want in PRESERVED.items():
        assert _sha(EVAL_ROOT / rel) == want, rel
    assert (EVAL_ROOT / ATTESTATION).stat().st_size == 9279


def test_the_metadata_alone_does_not_pass_the_gate() -> None:
    assert V5.meta["reviewed_by"] == {} and V5.fully_reviewed is False
    dataset, provenance = apply_review_attestation(V5, {"dataset": V5.name})
    assert dataset is V5 and provenance is None and not dataset.fully_reviewed


def test_the_pinned_attestation_marks_all_45_cases_reviewed_in_an_overlay() -> None:
    reviewed, provenance = apply_review_attestation(V5, PREREG)
    assert reviewed.fully_reviewed and reviewed.reviewed_case_ids == {c.id for c in V5.cases}
    assert reviewed.cases == V5.cases and reviewed.sha256 == V5.sha256
    # The loaded dataset and its metadata are not mutated.
    assert V5.fully_reviewed is False and V5.meta["reviewed_by"] == {}
    assert reviewed.meta == V5.meta and reviewed.meta["reviewed_by"] == {}
    assert provenance is not None
    assert provenance["sha256"] == PRESERVED[ATTESTATION]
    assert provenance["reviewer_role"] == "Project owner"
    assert provenance["cases_attested"] == 45
    assert provenance["approved_after_scoring_amendment"] == ["C12", "S15", "T11"]
    assert provenance["review_methods"] == {"T17": "translator_assisted_owner_review"}
    note = provenance["disclosures"]["T17"]
    assert "translator-assisted owner review" in note and "Google Translate" in note
    assert "no native-speaker or independent linguistic validation" in note


# --- tampering (copies in a temporary evaluation directory) ---------------------------------------


@pytest.fixture
def evaldir(tmp_path: Path) -> Path:
    for rel in PRESERVED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EVAL_ROOT / rel, tmp_path / rel)
    return tmp_path


def _attestation() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((EVAL_ROOT / ATTESTATION).read_text(encoding="utf-8"))
    return loaded


def _write(evaldir: Path, raw: bytes) -> dict[str, Any]:
    """Write a (modified) attestation and return a pre-registration that pins its new hash, so the
    content checks themselves are exercised, not just the hash pin."""
    (evaldir / ATTESTATION).write_bytes(raw)
    prereg = copy.deepcopy(PREREG)
    prereg["review_attestation"]["sha256"] = hashlib.sha256(raw).hexdigest()
    return prereg


def _apply(evaldir: Path, att: dict[str, Any]) -> Any:
    raw = yaml.safe_dump(att, sort_keys=False, allow_unicode=True).encode()
    return apply_review_attestation(V5, _write(evaldir, raw), evaldir)


def test_a_faithful_copy_in_another_directory_is_accepted(evaldir: Path) -> None:
    reviewed, _ = apply_review_attestation(V5, PREREG, evaldir)
    assert reviewed.fully_reviewed


def test_a_tampered_attestation_is_refused(evaldir: Path) -> None:
    path = evaldir / ATTESTATION
    path.write_bytes(
        path.read_bytes().replace(b"decision: approved\n", b"decision: approved \n", 1)
    )
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        apply_review_attestation(V5, PREREG, evaldir)


def test_only_the_pinned_bytes_are_accepted_whatever_the_file_name(evaldir: Path) -> None:
    other = evaldir / "reviews" / "other.yaml"
    shutil.copyfile(evaldir / ATTESTATION, other)
    prereg = copy.deepcopy(PREREG)
    prereg["review_attestation"]["file"] = "reviews/other.yaml"  # same bytes, different file
    reviewed, _ = apply_review_attestation(V5, prereg, evaldir)  # the hash pin is what counts
    assert reviewed.fully_reviewed
    other.write_bytes(other.read_bytes() + b"# appended\n")
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        apply_review_attestation(V5, prereg, evaldir)


def _mutated(mutate: Any) -> dict[str, Any]:
    att = _attestation()
    mutate(att)
    return att


def _set_decision(case_id: str, **fields: Any) -> Any:
    def mutate(att: dict[str, Any]) -> None:
        for key, value in fields.items():
            if value is None:
                att["decisions"][case_id].pop(key, None)
            else:
                att["decisions"][case_id][key] = value

    return mutate


ADVERSARIAL: dict[str, tuple[Any, str]] = {
    "wrong dataset hash": (
        lambda a: a["scope"].update(dataset_sha256="0" * 64),
        "different dataset",
    ),
    "wrong dataset name": (
        lambda a: a["scope"].update(dataset="routewise_bench_v4"),
        "different dataset",
    ),
    "wrong amendment hash": (
        lambda a: a["scope"]["scoring_amendment"].update(sha256="0" * 64),
        "different scoring amendment",
    ),
    "amendment cases incomplete": (
        lambda a: a["scope"]["scoring_amendment"]["cases"].pop("C12"),
        "different amended cases",
    ),
    "wrong metadata hash": (
        lambda a: a["scope"]["dataset_metadata"].update(sha256="0" * 64),
        "different dataset metadata",
    ),
    "missing case": (lambda a: a["decisions"].pop("S01"), r"missing \['S01'\]"),
    "additional case": (
        lambda a: a["decisions"].update(X99=dict(a["decisions"]["S01"])),
        r"unregistered \['X99'\]",
    ),
    "wrong case-line hash": (
        _set_decision("C05", case_line_sha256="0" * 64),
        "C05 was reviewed against a different version",
    ),
    "missing approval": (_set_decision("T04", decision=None), "T04 decision is None"),
    "rejected case": (_set_decision("T04", decision="rejected"), "T04 decision is 'rejected'"),
    "pending case": (_set_decision("T17", decision="pending"), "T17 decision is 'pending'"),
    "S15 approved without its amendment": (
        _set_decision("S15", decision="approved"),
        "S15 decision is 'approved'",
    ),
    "T11 wrong amendment condition": (
        _set_decision("T11", scoring_amendment_condition="currency symbols allowed"),
        "T11 doesn't reference its scoring amendment condition",
    ),
    "C12 missing amendment condition": (
        _set_decision("C12", scoring_amendment_condition=None),
        "C12 doesn't reference its scoring amendment condition",
    ),
    "unamended case claims an amendment": (
        _set_decision(
            "C01", decision="approved_after_scoring_amendment", scoring_amendment_condition="x"
        ),
        "C01 decision is 'approved_after_scoring_amendment'",
    ),
    "wrong reviewer role": (
        lambda a: a["reviewer"].update(role="Independent reviewer"),
        "reviewer role",
    ),
    "missing reviewer": (lambda a: a.pop("reviewer"), "reviewer role"),
    "missing owner confirmation": (
        lambda a: a["owner_confirmations"].update(reviewed_prompts_and_expected_answers=False),
        "missing owner confirmation reviewed_prompts_and_expected_answers",
    ),
    "different creation time": (
        lambda a: a.update(record_created_at_utc="2026-11-05T00:00:00Z"),
        "creation timestamp",
    ),
    "replaced attestation identity": (
        lambda a: a.update(attestation="human-review-attestation-other"),
        "is not the registered attestation",
    ),
    "wrong v5.2.1 revision reference": (
        lambda a: a["scope"]["revision"].update(sha256="0" * 64),
        "historical reference revision",
    ),
    "wrong v5.2.1 manifest reference": (
        lambda a: a["scope"]["experiment_manifest"].update(sha256="0" * 64),
        "historical reference experiment_manifest",
    ),
    "T17 method removed": (
        _set_decision("T17", review_method=None),
        "T17 review method differs",
    ),
    "T17 method upgraded": (
        _set_decision("T17", review_method="native_speaker_validation"),
        "T17 review method differs",
    ),
    "another case claims a method": (
        _set_decision("T16", review_method="translator_assisted_owner_review"),
        "T16 review method differs",
    ),
    "T17 disclosure claims native review": (
        lambda a: a["t17_disclosure"].update(native_or_proficient_speaker_review="yes"),
        "T17 translator-assisted disclosure",
    ),
    "T17 disclosure claims linguistic validation": (
        lambda a: a["t17_disclosure"].update(independent_linguistic_validation="done"),
        "T17 translator-assisted disclosure",
    ),
    "T17 disclosure wrong answer": (
        lambda a: a["t17_disclosure"].update(correct_answer="A"),
        "T17 translator-assisted disclosure",
    ),
    "T17 disclosure missing": (
        lambda a: a.pop("t17_disclosure"),
        "T17 translator-assisted disclosure",
    ),
    "summary inconsistent": (lambda a: a["summary"].update(approved=45), "summary"),
    "decisions not a mapping": (lambda a: a.update(decisions=[]), "has no decisions"),
    "scope missing": (lambda a: a.pop("scope"), "malformed"),
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_an_inconsistent_attestation_is_refused(evaldir: Path, name: str) -> None:
    mutate, message = ADVERSARIAL[name]
    with pytest.raises(ValueError, match=message):
        _apply(evaldir, _mutated(mutate))


def test_an_unmodified_round_trip_is_accepted(evaldir: Path) -> None:
    """Control for the adversarial cases: re-serialising the real content (new bytes, re-pinned)
    passes every content check, so each refusal above comes from its mutation."""
    reviewed, _ = _apply(evaldir, _attestation())
    assert reviewed.fully_reviewed


def test_a_duplicate_case_entry_is_refused(evaldir: Path) -> None:
    text = (evaldir / ATTESTATION).read_text(encoding="utf-8")
    block = text[text.index("  S01:\n") : text.index("  S02:\n")]
    raw = text.replace("  S02:\n", block + "  S02:\n", 1).encode()  # S01 appears twice
    with pytest.raises(ValueError, match="duplicate key 'S01'"):
        apply_review_attestation(V5, _write(evaldir, raw), evaldir)


def test_modified_metadata_is_refused(evaldir: Path) -> None:
    meta = evaldir / "datasets" / "routewise_bench_v5.meta.yaml"
    meta.write_bytes(
        meta.read_bytes().replace(
            b"reviewed_by: {}", b"reviewed_by: {S01: {reviewer: x, date: 2026-11-04}}"
        )
    )
    with pytest.raises(ValueError, match=r"meta\.yaml changed since it was pre-registered"):
        apply_review_attestation(V5, PREREG, evaldir)


def test_a_dataset_whose_loaded_metadata_differs_is_refused() -> None:
    edited = V5.model_copy(update={"meta": {**V5.meta, "reviewed_by": {"S01": {}}}})
    with pytest.raises(ValueError, match="loaded metadata"):
        apply_review_attestation(edited, PREREG)


def test_a_modified_dataset_is_refused(evaldir: Path) -> None:
    data = evaldir / "datasets" / "routewise_bench_v5.jsonl"
    data.write_bytes(data.read_bytes().replace(b"Priya", b"Priyanka", 1))
    with pytest.raises(ValueError, match="doesn't match the loaded dataset"):
        apply_review_attestation(V5, PREREG, evaldir)


def test_a_modified_scoring_amendment_is_refused(evaldir: Path) -> None:
    path = evaldir / "scoring_amendment_routewise_bench_v5.2.1.yaml"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="scoring amendment file doesn't match"):
        apply_review_attestation(V5, PREREG, evaldir)


# --- chain, manifest, CLI, runner, report ---------------------------------------------------------


def test_v5_2_2_chain_pins_the_metadata_and_the_attestation() -> None:
    rev = yaml.safe_load((EVAL_ROOT / f"{REVISION}.revision.yaml").read_text(encoding="utf-8"))
    att_sha = PRESERVED[ATTESTATION]
    meta_sha = PRESERVED["datasets/routewise_bench_v5.meta.yaml"]
    assert rev["review_attestation"] == {"file": ATTESTATION, "sha256": att_sha}
    assert PREREG["review_attestation"]["sha256"] == att_sha
    assert rev["dataset_metadata"]["sha256"] == PREREG["dataset_metadata"]["sha256"] == meta_sha
    assert rev["amends_revision"]["sha256"] == PRESERVED["routewise_bench_v5.2.1.revision.yaml"]
    assert PREREG["scoring_amendment"]["sha256"] == rev["scoring_amendment"]["sha256"]
    manifest_file = EVAL_ROOT / PREREG["experiment_manifest"]["file"]
    assert _sha(manifest_file) == PREREG["experiment_manifest"]["sha256"]
    manifest = manifest_mod.load_manifest(manifest_file)[0]
    assert manifest["schema"] == 6
    assert manifest["pinned"]["execution"]["attempt_quota"] == {"groq": GROQ_QUOTA_V5_2}
    files = manifest["pinned"]["files"]
    assert files["evidence/review_attestation"] == {
        "path": f"evaluation/{ATTESTATION}",
        "sha256": att_sha,  # LF-only file, so the LF-normalised hash equals the raw one
    }
    assert files["evidence/dataset_metadata"]["sha256"] == meta_sha
    assert (
        "publication" in PREREG
        and "pinned owner review attestation" in (PREREG["publication"]["rule"])
    )


def _intended(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "groq_enabled": True,
        "groq_api_key": "test-placeholder-key-0000000000000000",
        "groq_billing_plan": "free",
        "mock_provider_enabled": False,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _groq() -> dict[str, Any]:
    return {"groq": GroqProvider(api_key="test-placeholder", charge_basis="free_tier")}


STRATEGIES = ["baseline_premium", "routewise", "routewise_tier_first"]
PACING = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}


def test_v5_2_2_manifest_matches_the_intended_configuration() -> None:
    assert manifest_mod.check_manifest(PREREG, _intended(), _groq(), STRATEGIES, run_params=PACING)


def test_the_manifest_also_refuses_modified_evidence(evaldir: Path) -> None:
    shutil.copyfile(
        EVAL_ROOT / PREREG["experiment_manifest"]["file"],
        evaldir / PREREG["experiment_manifest"]["file"],
    )
    assert manifest_mod.check_manifest(
        PREREG, _intended(), _groq(), STRATEGIES, evaldir, run_params=PACING
    )
    meta = evaldir / "datasets" / "routewise_bench_v5.meta.yaml"
    meta.write_bytes(meta.read_bytes() + b"# edited\n")
    with pytest.raises(ValueError, match=r"files\.evidence/dataset_metadata\.sha256"):
        manifest_mod.check_manifest(
            PREREG, _intended(), _groq(), STRATEGIES, evaldir, run_params=PACING
        )


def test_schema_6_manifests_require_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        manifest_mod.build_manifest(_intended(), _groq(), STRATEGIES, schema=6, run_params=PACING)


@pytest.fixture
def intended_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from app.providers import registry

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no network call may happen in these tests")

    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: _intended())
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    monkeypatch.setattr(registry, "refresh_catalogs", no_network)


def _main(*argv: str) -> int:
    from app import cli

    return cli.main(list(argv))


def test_eval_validate_reports_the_attestation_and_fails_closed_without_a_budget(
    intended_cli: None, capsys: Any
) -> None:
    assert _main("eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION) == 1
    out = capsys.readouterr().out
    assert f"review attestation {ATTESTATION} sha256 b7099444ac31: valid; 45/45" in out
    assert "(fully reviewed: True)" in out
    assert "disclosure: T17: translator-assisted owner review" in out
    assert "valid; amends C12, S15, T11" in out
    assert "experiment_manifest_routewise_bench_v5.2.2.yaml: matches" in out
    assert "maximum provider attempts: 378" in out and "preflight: FAILED (fail closed)" in out


def test_eval_validate_v5_2_2_passes_with_a_verified_budget(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    argv = ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION]
    argv += ["--remaining-daily-tokens", "100000000", "--daily-budget-source", "test"]
    argv += ["--daily-budget-verified-at", datetime.now(UTC).isoformat()]
    assert _main(*argv, "--ledger", str(tmp_path / "ledger.json")) == 0
    assert "preflight: OK" in capsys.readouterr().out


def test_eval_validate_reports_an_invalid_attestation(
    intended_cli: None, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import cli

    real = cli._load_prereg

    def tampered(args: Any, dataset: Any) -> tuple[dict[str, Any], str, Any]:
        prereg, sha, path = real(args, dataset)
        prereg = copy.deepcopy(prereg)
        prereg["review_attestation"]["sha256"] = "0" * 64
        return prereg, sha, path

    monkeypatch.setattr(cli, "_load_prereg", tampered)
    assert _main("eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION) == 1
    out = capsys.readouterr().out
    assert "review attestation: INVALID" in out and "publication gate fails closed" in out


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


def test_eval_run_v5_2_2_refuses_without_a_budget_before_any_network_call(
    intended_cli: None, capsys: Any
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION) == 2
    assert "quota preflight failed" in capsys.readouterr().err


def test_eval_run_refuses_a_tampered_attestation_before_any_network_call(
    intended_cli: None, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import cli

    real = cli._load_prereg

    def tampered(args: Any, dataset: Any) -> tuple[dict[str, Any], str, Any]:
        prereg, sha, path = real(args, dataset)
        prereg = copy.deepcopy(prereg)
        prereg["review_attestation"]["sha256"] = "0" * 64
        return prereg, sha, path

    monkeypatch.setattr(cli, "_load_prereg", tampered)
    assert _main(*EVAL_RUN, "--revision", REVISION) == 2
    assert "changed since it was pre-registered" in capsys.readouterr().err


def test_the_cli_accepts_no_attestation_path(intended_cli: None, capsys: Any) -> None:
    with pytest.raises(SystemExit) as raised:
        _main(*EVAL_RUN, "--revision", REVISION, "--attestation", str(EVAL_ROOT / ATTESTATION))
    assert raised.value.code == 2
    assert "unrecognized arguments: --attestation" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("revision", "manifest"),
    [
        ("routewise_bench_v5.2.1", "experiment_manifest_routewise_bench_v5.2.1.yaml"),
        ("routewise_bench_v5.2", "experiment_manifest_routewise_bench_v5.2.yaml"),
        ("routewise_bench_v5.1", "experiment_manifest_routewise_bench_v5.1.yaml"),
    ],
)
def test_historical_revisions_are_refused(
    intended_cli: None, capsys: Any, revision: str, manifest: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", revision) == 2
    assert f"configuration differs from {manifest}" in capsys.readouterr().err


class _Stop(Exception):
    pass


async def test_the_runner_applies_the_attestation(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    real = dataset_mod.apply_review_attestation

    def spy(dataset: Any, prereg: dict[str, Any]) -> Any:
        seen.append(real(dataset, prereg))
        raise _Stop

    monkeypatch.setattr(runner_mod, "apply_review_attestation", spy)
    with pytest.raises(_Stop):
        await runner_mod.run_benchmark(
            settings=_intended(),
            db=None,  # type: ignore[arg-type]  # never reached
            providers=_groq(),
            dataset=V5,
            strategies=STRATEGIES,
            label="t",
            revision=REVISION,
        )
    ((reviewed, provenance),) = seen
    assert reviewed.fully_reviewed and provenance["sha256"] == PRESERVED[ATTESTATION]
    # The amendment was applied first: the runner passes the amended dataset on.
    by_id = {c.id: c.scoring for c in reviewed.cases}
    assert by_id["C12"] == {"method": "validator", "name": "meeting_schedule_hhmm"}


def _outcome(strategy: str, i: int) -> Any:
    from app.evaluation.runner import CaseOutcome

    return CaseOutcome(
        case_id=f"X{i:02d}",
        difficulty="simple",
        category="c",
        strategy=strategy,
        passed=True,
        score=1.0,
        needs_human_review=False,
        error_code=None,
        provider="groq",
        model="openai/gpt-oss-120b",
        answer_model="openai/gpt-oss-120b",
        tier="premium",
        latency_ms=100,
        estimated_list_cost_usd="0.00010000",
        list_cost_status="estimated",
        attempts=[
            {"attempt": 1, "provider": "groq", "model": "openai/gpt-oss-120b", "tier": "premium"}
        ],
    )


def _summary(*, review: dict[str, Any] | None, fully_reviewed: bool) -> dict[str, Any]:
    from app.evaluation.report import build_summary
    from app.evaluation.runner import BenchmarkResult

    _, amendment = dataset_mod.apply_scoring_amendment(V5, PREREG)
    return build_summary(
        BenchmarkResult(
            label="synthetic",
            simulated=False,
            dataset=V5.name,
            dataset_sha256=V5.sha256,
            dataset_fully_reviewed=fully_reviewed,
            preregistration=PREREG,
            preregistration_sha256="x" * 64,
            started_at="",
            finished_at="",
            config_snapshot={
                "manifest": {"expected_models": ["groq/openai/gpt-oss-120b"]},
                "execution_revision": REVISION,
                "scoring_amendment": amendment,
                "review_attestation": review,
            },
            run_ids={},
            outcomes=[_outcome(s, i) for s in ("baseline_premium", "routewise") for i in range(45)],
        )
    )


def test_the_report_records_provenance_and_discloses_t17() -> None:
    from app.evaluation.report import _markdown

    reviewed, review = apply_review_attestation(V5, PREREG)
    summary = _summary(review=review, fully_reviewed=reviewed.fully_reviewed)
    assert summary["review_attestation"] == review and summary["execution_revision"] == REVISION
    assert summary["scoring_amendment"]["cases"] == ["C12", "S15", "T11"]
    assert "dataset not fully human-reviewed" not in summary["publishable_reasons"]
    md = _markdown(summary)
    assert "45 cases attested by the project owner" in md and "b7099444ac31" in md
    assert "**Disclosure:** T17: translator-assisted owner review" in md
    assert "no native-speaker or independent linguistic validation" in md
    assert "for C12, S15, T11" in md


def test_without_the_attestation_the_report_is_not_publishable() -> None:
    summary = _summary(review=None, fully_reviewed=V5.fully_reviewed)
    assert summary["publishable"] is False
    assert "dataset not fully human-reviewed" in summary["publishable_reasons"]
