"""Scoring amendment routewise_bench_v5.2.1: S15, T11 and C12 only.

Self-contained (no imports from other test modules) so it runs from the clean-room review bundle.
No provider is called. The dataset file is never modified: the amendment replaces three scoring
specs at run time, and every other case must score exactly as before.
"""

from __future__ import annotations

import hashlib
import json
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
    apply_scoring_amendment,
    load_dataset,
    load_execution_revision,
    load_preregistration,
)
from app.evaluation.pacing import GROQ_QUOTA_V5_2
from app.evaluation.scorers import score
from app.providers.groq import GroqProvider

REVISION = "routewise_bench_v5.2.1"
V5 = load_dataset("routewise_bench_v5")
V5_SHA = "76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd"
# The corrected v5.2 chain this amendment builds on (kept unchanged as historical evidence).
V5_2_CHAIN = {
    "routewise_bench_v5.2.revision.yaml": (
        "59257813e1093d512f0f6fb6459e8ee40aebede789d55908f661dca4bb06d347"
    ),
    "preregistration_routewise_bench_v5.2.yaml": (
        "2c713e734ed418c31874cffec541831402dc689de56fab18f5c4643fb589976b"
    ),
    "experiment_manifest_routewise_bench_v5.2.yaml": (
        "00302285a3d2a1d5d35361fd8eede9065cfc774940e6ade022828c25089aef10"
    ),
}
AMENDED = {"S15", "T11", "C12"}


def _prereg() -> dict[str, Any]:
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, _ = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    return prereg


PREREG = _prereg()
AMENDED_V5, PROVENANCE = apply_scoring_amendment(V5, PREREG)
ORIGINAL = {c.id: c.scoring for c in V5.cases}
NEW = {c.id: c.scoring for c in AMENDED_V5.cases}


def _passes(case_id: str, output: str, *, original: bool = False) -> bool | None:
    return score(output, (ORIGINAL if original else NEW)[case_id]).passed


# --- the amendment changes exactly three specs and nothing else -----------------------------------


def test_exactly_s15_t11_and_c12_are_amended() -> None:
    assert {cid for cid in ORIGINAL if ORIGINAL[cid] != NEW[cid]} == AMENDED
    assert PROVENANCE is not None and PROVENANCE["cases"] == sorted(AMENDED)
    assert [c.id for c in AMENDED_V5.cases] == [c.id for c in V5.cases]
    for before, after in zip(V5.cases, AMENDED_V5.cases, strict=True):
        assert before.model_dump(exclude={"scoring"}) == after.model_dump(exclude={"scoring"})
    assert AMENDED_V5.sha256 == V5.sha256 == V5_SHA and AMENDED_V5.meta == V5.meta


def test_the_amended_specs_are_the_agreed_ones() -> None:
    assert NEW["S15"] == {**ORIGINAL["S15"], "field_types": {"age": "integer"}}
    assert ORIGINAL["T11"]["currency_symbols"] == ["$"]
    assert NEW["T11"] == {**ORIGINAL["T11"], "currency_symbols": []}
    assert ORIGINAL["C12"] == {"method": "validator", "name": "meeting_schedule"}
    assert NEW["C12"] == {"method": "validator", "name": "meeting_schedule_hhmm"}


def test_applying_the_amendment_does_not_mutate_the_loaded_dataset() -> None:
    fresh = load_dataset("routewise_bench_v5")
    assert {c.id: c.scoring for c in fresh.cases} == ORIGINAL
    assert {c.id: c.scoring for c in V5.cases} == ORIGINAL


GENERIC_OUTPUTS = [
    "33",
    "$33",
    "B",
    "ANSWER: B",
    "yes",
    "",
    '{"name": "Priya", "age": 34.0}',
    '{"A": "9:30", "B": "10:30", "C": "9:00"}',
    "```python\ndef f():\n    return 1\n```",
    "The answer is 42.",
]


@pytest.mark.parametrize("case_id", sorted(set(ORIGINAL) - AMENDED))
def test_no_other_case_scores_differently(case_id: str) -> None:
    assert NEW[case_id] == ORIGINAL[case_id]
    for output in [*GENERIC_OUTPUTS, V5.cases[[c.id for c in V5.cases].index(case_id)].expected]:
        assert score(output, NEW[case_id]) == score(output, ORIGINAL[case_id])


# --- S15: age must be a JSON integer --------------------------------------------------------------


@pytest.mark.parametrize(
    "output",
    [
        '{"name": "Priya", "age": 34}',
        '```json\n{"name": "Priya", "age": 34}\n```',
        '{"age": 34, "name": "Priya"}',
        '{"name": "Priya", "age": 34, "note": "unchanged: extra keys were and are allowed"}',
    ],
)
def test_s15_accepts_an_integer_age(output: str) -> None:
    assert _passes("S15", output)


@pytest.mark.parametrize("age", ["34.0", "3.4e1", "340e-1", "34.00"])
def test_s15_rejects_a_float_age_that_v5_2_accepted(age: str) -> None:
    output = f'{{"name": "Priya", "age": {age}}}'
    assert _passes("S15", output, original=True)  # the defect being corrected
    assert not _passes("S15", output)


@pytest.mark.parametrize(
    "age", ['"34"', "true", "null", "[34]", '{"years": 34}', "34.5", "33", "-34", '" 34 "']
)
def test_s15_rejects_other_non_integer_or_wrong_ages(age: str) -> None:
    assert not _passes("S15", f'{{"name": "Priya", "age": {age}}}')


@pytest.mark.parametrize("output", ['{"name": "Priya"}', "Priya is 34", '["Priya", 34]', ""])
def test_s15_rejects_missing_age_and_non_objects(output: str) -> None:
    assert not _passes("S15", output)


# --- T11: number only, no currency symbol ---------------------------------------------------------


@pytest.mark.parametrize(
    "output", ["33", "33.", "33.0", "33.00", " 33 \n", "**33**", "`33`", "_33_"]
)
def test_t11_accepts_the_bare_number(output: str) -> None:
    assert _passes("T11", output)


@pytest.mark.parametrize("output", ["$33", "$33.00", "**$33**"])
def test_t11_rejects_a_dollar_sign_that_v5_2_accepted(output: str) -> None:
    assert _passes("T11", output, original=True)  # the defect being corrected
    assert not _passes("T11", output)


@pytest.mark.parametrize(
    "output",
    [
        "$ 33",
        "33$",
        "US$33",
        "USD 33",
        "33 USD",
        "€33",
        "£33",
        "¥33",
        chr(0xFF04) + "33",  # fullwidth dollar sign
        "\\$33",
        "33 dollars",
        "The final price is 33.",
        "33%",
        "+33",
        "3.3e1",
        "thirty-three",
        "33.5",
        "32",
        "33\n33",
    ],
)
def test_t11_rejects_anything_but_the_bare_number(output: str) -> None:
    assert not _passes("T11", output)


# --- C12: strict HH:MM ----------------------------------------------------------------------------

# Non-ASCII digits that Python's int() accepts: 09:30 in Arabic-Indic and in fullwidth digits.
ARABIC_INDIC = (
    "".join(chr(c) for c in (0x0660, 0x0669)) + ":" + "".join(chr(c) for c in (0x0663, 0x0660))
)
FULLWIDTH_DIGITS = (
    "".join(chr(c) for c in (0xFF10, 0xFF19)) + ":" + "".join(chr(c) for c in (0xFF13, 0xFF10))
)
VALID_SCHEDULE = {"A": "09:30", "B": "10:30", "C": "09:00"}


def _schedule(**values: Any) -> str:
    return json.dumps({**VALID_SCHEDULE, **values})


@pytest.mark.parametrize(
    "output",
    [
        _schedule(),
        f"```json\n{_schedule()}\n```",
        json.dumps({"C": "09:00", "B": "10:30", "A": "09:30"}),
        _schedule(note="unchanged: extra keys were and are allowed"),
    ],
)
def test_c12_accepts_a_valid_schedule_in_strict_hhmm(output: str) -> None:
    assert _passes("C12", output)


@pytest.mark.parametrize(
    "value", ["9:30", " 09:30", "09:30 ", "+9:30", ARABIC_INDIC, FULLWIDTH_DIGITS]
)
def test_c12_rejects_loose_times_that_v5_2_accepted(value: str) -> None:
    output = _schedule(A=value)  # A at 09:30 is otherwise a valid schedule
    assert _passes("C12", output, original=True)  # the defect being corrected
    assert not _passes("C12", output)


@pytest.mark.parametrize(
    "value",
    [
        "09:30:00",
        "09.30",
        "0930",
        "09:30 AM",
        "09:30\n",
        "T09:30",
        "09" + chr(0xFF1A) + "30",  # fullwidth colon
        "9:3",
        "09:60",
        "24:00",
        9.5,
        930,
        None,
        ["09", "30"],
    ],
)
def test_c12_rejects_non_hhmm_values(value: Any) -> None:
    assert not _passes("C12", _schedule(A=value))


@pytest.mark.parametrize(
    "output",
    [
        json.dumps({"A": "10:00", "B": "09:30", "C": "09:00"}),  # B before A
        json.dumps({"A": "09:00", "B": "10:30", "C": "09:30"}),  # overlap
        json.dumps({"A": "09:30", "B": "10:30", "C": "10:00"}),  # C ends after 10:00
        json.dumps({"A": "09:30", "B": "11:00", "C": "09:00"}),  # B ends after 11:00
        json.dumps({"A": "09:30", "B": "10:30"}),  # C missing
        "not json",
    ],
)
def test_c12_schedule_constraints_are_unchanged(output: str) -> None:
    assert not _passes("C12", output)
    assert not _passes("C12", output, original=True)


# --- the amendment can only amend what it was written for -----------------------------------------


def _write_amendment(directory: Path, amendment: dict[str, Any]) -> dict[str, Any]:
    raw = yaml.safe_dump(amendment, sort_keys=False).encode()
    (directory / "amendment.yaml").write_bytes(raw)
    base = amendment["amends_revision"]["file"]
    (directory / base).write_bytes((EVAL_ROOT / base).read_bytes())
    return {
        "scoring_amendment": {"file": "amendment.yaml", "sha256": hashlib.sha256(raw).hexdigest()}
    }


def _real_amendment() -> dict[str, Any]:
    path = EVAL_ROOT / PREREG["scoring_amendment"]["file"]
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def test_a_faithful_copy_applies_and_matches_the_registered_amendment(tmp_path: Path) -> None:
    amended, _ = apply_scoring_amendment(
        V5, _write_amendment(tmp_path, _real_amendment()), tmp_path
    )
    assert {c.id: c.scoring for c in amended.cases} == NEW


def test_an_edited_amendment_file_is_refused(tmp_path: Path) -> None:
    prereg = _write_amendment(tmp_path, _real_amendment())
    (tmp_path / "amendment.yaml").write_bytes((tmp_path / "amendment.yaml").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        apply_scoring_amendment(V5, prereg, tmp_path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda a: a.update(dataset_sha256="0" * 64), "different dataset"),
        (lambda a: a.update(dataset="routewise_bench_v4"), "different dataset"),
        (lambda a: a["cases"]["T11"]["original_scoring"].update(answer=34), "original scoring"),
        (lambda a: a["cases"].update(X99=a["cases"]["S15"]), "unknown case X99"),
        (lambda a: a["amends_revision"].update(sha256="0" * 64), "amended revision"),
    ],
)
def test_a_mismatched_amendment_is_refused(tmp_path: Path, mutate: Any, message: str) -> None:
    amendment = _real_amendment()
    mutate(amendment)
    with pytest.raises(ValueError, match=message):
        apply_scoring_amendment(V5, _write_amendment(tmp_path, amendment), tmp_path)


def test_a_preregistration_without_an_amendment_scores_as_written() -> None:
    dataset, provenance = apply_scoring_amendment(V5, {"version": "x"})
    assert dataset is V5 and provenance is None


# --- chain, manifest, CLI -------------------------------------------------------------------------


def _sha(name: str) -> str:
    return hashlib.sha256((EVAL_ROOT / name).read_bytes()).hexdigest()


def test_v5_2_1_chain_holds_and_depends_on_the_unchanged_dataset_and_v5_2() -> None:
    assert V5.sha256 == V5_SHA
    for name, want in V5_2_CHAIN.items():
        assert _sha(name) == want  # corrected v5.2 chain preserved
    rev = yaml.safe_load((EVAL_ROOT / f"{REVISION}.revision.yaml").read_text(encoding="utf-8"))
    assert rev["dataset_sha256"] == PREREG["dataset_sha256"] == V5_SHA
    base = V5_2_CHAIN["routewise_bench_v5.2.revision.yaml"]
    assert rev["amends_revision"]["sha256"] == PREREG["amends_revision"]["sha256"] == base
    amendment = _real_amendment()
    assert amendment["amends_revision"]["sha256"] == base
    assert amendment["dataset_sha256"] == V5_SHA
    ref = PREREG["scoring_amendment"]
    assert rev["scoring_amendment"] == {"file": ref["file"], "sha256": ref["sha256"]}
    assert _sha(ref["file"]) == ref["sha256"]
    assert _sha(PREREG["experiment_manifest"]["file"]) == PREREG["experiment_manifest"]["sha256"]
    manifest = manifest_mod.load_manifest(EVAL_ROOT / PREREG["experiment_manifest"]["file"])[0]
    assert manifest["schema"] == 5
    assert manifest["pinned"]["execution"]["attempt_quota"] == {"groq": GROQ_QUOTA_V5_2}


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


def test_v5_2_1_manifest_matches_the_intended_configuration(intended_cli: None) -> None:
    assert manifest_mod.check_manifest(PREREG, _intended(), _groq(), STRATEGIES, run_params=PACING)


def test_eval_validate_v5_2_1_reports_the_amendment_and_fails_closed_without_a_budget(
    intended_cli: None, capsys: Any
) -> None:
    assert _main("eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION) == 1
    out = capsys.readouterr().out
    assert f"scoring amendment {PREREG['scoring_amendment']['file']} sha256" in out
    assert "valid; amends C12, S15, T11" in out
    assert "experiment_manifest_routewise_bench_v5.2.1.yaml: matches" in out
    assert "maximum provider attempts: 378" in out and "preflight: FAILED (fail closed)" in out


def test_eval_validate_v5_2_1_passes_with_a_verified_budget(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    argv = ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION]
    argv += ["--remaining-daily-tokens", "100000000", "--daily-budget-source", "test"]
    argv += ["--daily-budget-verified-at", datetime.now(UTC).isoformat()]
    assert _main(*argv, "--ledger", str(tmp_path / "ledger.json")) == 0
    assert "preflight: OK" in capsys.readouterr().out


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


def test_eval_run_v5_2_1_refuses_without_a_budget_before_any_network_call(
    intended_cli: None, capsys: Any
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION) == 2
    assert "quota preflight failed" in capsys.readouterr().err


def test_eval_run_refuses_a_tampered_amendment_before_any_network_call(
    intended_cli: None, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import cli

    real = cli._load_prereg

    def tampered(args: Any, dataset: Any) -> tuple[dict[str, Any], str, Any]:
        prereg, sha, path = real(args, dataset)
        ref = {**prereg["scoring_amendment"], "sha256": "0" * 64}
        return {**prereg, "scoring_amendment": ref}, sha, path

    monkeypatch.setattr(cli, "_load_prereg", tampered)
    assert _main(*EVAL_RUN, "--revision", REVISION) == 2
    assert "changed since it was pre-registered" in capsys.readouterr().err


def test_v5_2_is_refused_on_current_code(intended_cli: None, capsys: Any) -> None:
    assert _main(*EVAL_RUN, "--revision", "routewise_bench_v5.2") == 2
    err = capsys.readouterr().err
    assert "configuration differs from experiment_manifest_routewise_bench_v5.2.yaml" in err


class _Stop(Exception):
    pass


async def test_the_runner_scores_with_the_amended_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_benchmark applies the pinned amendment before anything else touches the cases."""
    seen: list[Any] = []
    real = dataset_mod.apply_scoring_amendment

    def spy(dataset: Any, prereg: dict[str, Any]) -> Any:
        result = real(dataset, prereg)
        seen.append(result)
        raise _Stop

    monkeypatch.setattr(runner_mod, "apply_scoring_amendment", spy)
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
    ((dataset, provenance),) = seen
    assert {c.id: c.scoring for c in dataset.cases} == NEW
    assert provenance == PROVENANCE
