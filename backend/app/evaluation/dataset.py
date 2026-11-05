"""Benchmark dataset loading and validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import REPO_ROOT
from app.routing.config import TaskType

EVAL_ROOT = REPO_ROOT / "evaluation"
DATASET_DIR = EVAL_ROOT / "datasets"
PREREGISTRATION = EVAL_ROOT / "preregistration.yaml"
REPORTS_DIR = EVAL_ROOT / "reports"

ScoringMethod = Literal[
    "choice", "exact", "regex", "numeric", "contains", "json", "code", "validator"
]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[SCT]\d{2}$")
    category: str
    difficulty: Literal["simple", "standard", "complex"]
    task_type: TaskType
    prompt: str = Field(min_length=10)
    response_format: Literal["text", "json"] = "text"
    max_output_tokens: int = Field(ge=16, le=8192)
    expected: str = Field(min_length=1)
    scoring: dict[str, Any]

    @model_validator(mode="after")
    def _scoring_shape(self) -> Self:
        method = self.scoring.get("method")
        required = {
            "choice": {"labels", "answer"},
            "exact": {"answer"},
            "regex": {"pattern"},
            "numeric": {"answer"},
            "code": {"tests"},
            "validator": {"name"},
        }
        if method not in {*required, "contains", "json"}:
            raise ValueError(f"{self.id}: unknown scoring method {method!r}")
        missing = required.get(str(method), set()) - set(self.scoring)
        if missing:
            raise ValueError(f"{self.id}: scoring missing {sorted(missing)}")
        if method == "choice" and self.scoring["answer"] not in self.scoring["labels"]:
            raise ValueError(f"{self.id}: answer not among labels")
        if method == "json" and self.response_format != "json":
            raise ValueError(f"{self.id}: json scoring requires response_format json")
        return self

    @property
    def needs_human_review(self) -> bool:
        return bool(self.scoring.get("needs_human_review"))


class Dataset(BaseModel):
    name: str
    cases: list[Case]
    meta: dict[str, Any]
    sha256: str
    # Review-status overlay (v5.2.2+): case IDs covered by a verified, pre-registered review
    # attestation (see apply_review_attestation). The metadata itself is never modified.
    attested_case_ids: frozenset[str] = frozenset()

    @property
    def reviewed_case_ids(self) -> set[str]:
        return set((self.meta.get("reviewed_by") or {}).keys()) | self.attested_case_ids

    @property
    def fully_reviewed(self) -> bool:
        return self.reviewed_case_ids >= {c.id for c in self.cases}

    @property
    def code_execution_cases(self) -> list[str]:
        return [c.id for c in self.cases if c.scoring.get("method") == "code"]


def load_dataset(name: str = "routewise_bench_v1", directory: Path = DATASET_DIR) -> Dataset:
    raw = (directory / f"{name}.jsonl").read_bytes()
    cases = [
        Case.model_validate(json.loads(line))
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case IDs")
    meta_path = directory / f"{name}.meta.yaml"
    meta = (
        yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    ) or {}
    dataset = Dataset(name=name, cases=cases, meta=meta, sha256=hashlib.sha256(raw).hexdigest())
    if meta.get("code_execution") is False and dataset.code_execution_cases:
        raise ValueError(f"{name} forbids code execution but has code cases")
    return dataset


def preregistration_path(dataset_name: str, directory: Path = EVAL_ROOT) -> Path:
    """`preregistration_<dataset>.yaml` if it exists, else the original `preregistration.yaml`
    (v1 predates per-dataset files)."""
    specific = directory / f"preregistration_{dataset_name}.yaml"
    return specific if specific.exists() else directory / PREREGISTRATION.name


def load_execution_revision(
    revision: str, dataset: Dataset, directory: Path = EVAL_ROOT
) -> tuple[Path, str]:
    """An execution revision (e.g. `routewise_bench_v5.1`) re-registers how an unchanged dataset is
    executed. Its file pins the dataset hash and the revision's own pre-registration hash; it is
    the root of the revision's hash chain (the immutable dataset meta isn't touched). Returns
    (pre-registration path, pinned pre-registration SHA-256)."""
    path = directory / f"{revision}.revision.yaml"
    if not path.exists():
        raise FileNotFoundError(f"unknown execution revision {revision!r} ({path.name})")
    rev = yaml.safe_load(path.read_text(encoding="utf-8"))
    if rev.get("dataset") != dataset.name or rev.get("dataset_sha256") != dataset.sha256:
        raise ValueError(f"{path.name} is registered for a different dataset or dataset version")
    prereg = rev["preregistration"]
    return directory / prereg["file"], str(prereg["sha256"])


def load_preregistration(
    path: Path = PREREGISTRATION,
    *,
    dataset: Dataset | None = None,
    pinned_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Load the pre-registration. With `dataset`, refuse one registered for another dataset, or one
    whose hash differs from the `preregistration_sha256` pinned in the dataset's metadata (so
    thresholds can't be edited silently after the fact)."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is required: the quality threshold must be registered before any run"
        )
    raw = path.read_bytes()
    prereg, sha = yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()
    if dataset is not None:
        if prereg.get("dataset") != dataset.name:
            raise ValueError(
                f"{path.name} is registered for {prereg.get('dataset')!r}, not {dataset.name!r}"
            )
        if prereg.get("dataset_sha256") not in (None, dataset.sha256):
            raise ValueError(f"{path.name} is registered for a different version of {dataset.name}")
        # An execution revision pins its own pre-registration; otherwise the dataset meta does.
        pinned = pinned_sha256 or dataset.meta.get("preregistration_sha256")
        if pinned and pinned != sha:
            raise ValueError(
                f"{path.name} changed since it was pinned "
                f"({'execution revision' if pinned_sha256 else dataset.name + '.meta.yaml'}); "
                "record a new pre-registration version instead of editing thresholds"
            )
    return prereg, sha


def apply_scoring_amendment(
    dataset: Dataset, prereg: dict[str, Any], directory: Path = EVAL_ROOT
) -> tuple[Dataset, dict[str, Any] | None]:
    """A scoring amendment (v5.2.1+) replaces the scoring spec of named cases without touching the
    dataset file. The pre-registration pins its SHA-256. It must name the dataset hash, the hash of
    the execution revision it amends, and each case's current scoring spec exactly, so it can only
    amend the dataset version it was written for. Returns (amended dataset, provenance); the
    dataset's own `sha256` stays that of the unchanged JSONL."""
    ref = prereg.get("scoring_amendment")
    if not ref:
        return dataset, None
    path = directory / ref["file"]
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != ref["sha256"]:
        raise ValueError(f"{path.name} changed since it was pre-registered")
    amendment = yaml.safe_load(raw)
    if (
        amendment.get("dataset") != dataset.name
        or amendment.get("dataset_sha256") != dataset.sha256
    ):
        raise ValueError(f"{path.name} is registered for a different dataset or dataset version")
    base = amendment["amends_revision"]
    base_raw = (directory / base["file"]).read_bytes()
    if hashlib.sha256(base_raw).hexdigest() != base["sha256"]:
        raise ValueError(f"{path.name}: amended revision {base['file']} changed")
    changes: dict[str, Any] = amendment["cases"]
    by_id = {c.id: c for c in dataset.cases}
    for case_id, change in changes.items():
        if case_id not in by_id:
            raise ValueError(f"{path.name}: unknown case {case_id}")
        if by_id[case_id].scoring != change["original_scoring"]:
            raise ValueError(f"{path.name}: {case_id} original scoring doesn't match the dataset")
    cases = [
        Case.model_validate({**c.model_dump(), "scoring": changes[c.id]["amended_scoring"]})
        if c.id in changes
        else c
        for c in dataset.cases
    ]
    provenance = {"file": ref["file"], "sha256": sha, "cases": sorted(changes)}
    return dataset.model_copy(update={"cases": cases}), provenance


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses duplicate mapping keys (PyYAML otherwise keeps the last one)."""


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise ValueError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_execution_schedule(
    dataset: Dataset, prereg: dict[str, Any], directory: Path = EVAL_ROOT
) -> dict[str, Any] | None:
    """A registered multi-day execution schedule (v5.2.3+): which cases run on which scheduled UTC
    day, so a run that can't fit one day's provider quota still runs every case under the same
    registered protocol. The pre-registration pins its SHA-256. Every dataset case must appear
    exactly once, each day's cases in dataset order. Returns None if none is registered."""
    ref = prereg.get("execution_schedule")
    if not ref:
        return None
    raw = (directory / ref["file"]).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != ref["sha256"]:
        raise ValueError(f"{ref['file']} changed since it was pre-registered")
    try:
        schedule = yaml.load(raw, Loader=_UniqueKeyLoader)  # noqa: S506 (a SafeLoader subclass)
    except (yaml.YAMLError, ValueError) as error:
        raise ValueError(f"{ref['file']}: unreadable ({error})") from None
    if schedule.get("dataset") != dataset.name or schedule.get("dataset_sha256") != dataset.sha256:
        raise ValueError(f"{ref['file']} is registered for a different dataset or dataset version")
    days = schedule.get("days")
    if not isinstance(days, dict) or sorted(days) != list(range(1, int(ref["days"]) + 1)):
        raise ValueError(f"{ref['file']}: days must be numbered 1..{ref['days']}")
    order = {c.id: i for i, c in enumerate(dataset.cases)}
    seen: list[str] = [cid for day in sorted(days) for cid in days[day]]
    duplicates = sorted({cid for cid in seen if seen.count(cid) > 1})
    missing, extra = set(order) - set(seen), set(seen) - set(order)
    if duplicates or missing or extra:
        raise ValueError(
            f"{ref['file']}: every case exactly once (duplicates {duplicates}, missing "
            f"{sorted(missing)}, unregistered {sorted(extra)})"
        )
    for day, ids in days.items():
        if [order[c] for c in ids] != sorted(order[c] for c in ids):
            raise ValueError(f"{ref['file']}: day {day} cases must be in dataset order")
    return {
        "file": ref["file"],
        "sha256": sha,
        "days": {int(d): list(ids) for d, ids in sorted(days.items())},
        "max_span_days": int(schedule["max_span_days"]),
    }


def schedule_day_cases(
    dataset: Dataset, schedule: dict[str, Any], day: int
) -> list[tuple[int, Case]]:
    """The (dataset index, case) pairs of one scheduled day, in dataset order. The index is the
    case's position in the full dataset, so the registered strategy order (alternating by case
    index) is the same as in a single-day run."""
    if day not in schedule["days"]:
        raise ValueError(f"schedule day {day} is not registered (days 1..{len(schedule['days'])})")
    index = {c.id: i for i, c in enumerate(dataset.cases)}
    by_id = {c.id: c for c in dataset.cases}
    return [(index[cid], by_id[cid]) for cid in schedule["days"][day]]


def scheduled_combinations(
    dataset: Dataset, schedule: dict[str, Any], day: int, strategies: list[str]
) -> list[tuple[str, str]]:
    """Every (case ID, strategy) of a scheduled day in the registered execution order: cases in
    dataset order, strategies alternating by the case's dataset index (as the runner does)."""
    return [
        (case.id, strategy)
        for index, case in schedule_day_cases(dataset, schedule, day)
        for strategy in (strategies if index % 2 == 0 else list(reversed(strategies)))
    ]


def load_execution_recovery(
    dataset: Dataset,
    prereg: dict[str, Any],
    schedule: dict[str, Any] | None,
    directory: Path = EVAL_ROOT,
) -> dict[str, Any] | None:
    """A registered, disclosed recovery of an interrupted scheduled day (v5.2.4+). The plan names
    the combinations whose genuine results were already persisted by the interrupted runs (carried
    over, never re-run) and the combinations still to execute. Together they must be the day's full
    registered matrix, each exactly once, and execution must follow the registered order. The
    pre-registration pins the plan's SHA-256."""
    ref = prereg.get("execution_recovery")
    if not ref:
        return None
    if schedule is None:
        raise ValueError("an execution recovery needs a registered execution schedule")
    raw = (directory / ref["file"]).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != ref["sha256"]:
        raise ValueError(f"{ref['file']} changed since it was pre-registered")
    try:
        plan = yaml.load(raw, Loader=_UniqueKeyLoader)  # noqa: S506 (a SafeLoader subclass)
    except (yaml.YAMLError, ValueError) as error:
        raise ValueError(f"{ref['file']}: unreadable ({error})") from None
    if plan.get("dataset") != dataset.name or plan.get("dataset_sha256") != dataset.sha256:
        raise ValueError(f"{ref['file']} is registered for a different dataset or dataset version")
    if plan.get("schedule_sha256") != schedule["sha256"]:
        raise ValueError(f"{ref['file']} was written for a different execution schedule")
    day = int(plan["day"])
    strategies = list(plan["strategies"])
    order = scheduled_combinations(dataset, schedule, day, strategies)
    carried = [(str(c["case_id"]), str(c["strategy"])) for c in plan["carried_over"]]
    execute = [(str(c["case_id"]), str(c["strategy"])) for c in plan["execute"]]
    combined = carried + execute
    if len(set(combined)) != len(combined) or set(combined) != set(order):
        raise ValueError(
            f"{ref['file']}: carried-over and to-execute combinations must be the day's "
            f"{len(order)} registered combinations, each exactly once"
        )
    if execute != [c for c in order if c in set(execute)]:
        raise ValueError(f"{ref['file']}: combinations must execute in the registered order")
    return {
        "file": ref["file"],
        "sha256": sha,
        "day": day,
        "strategies": strategies,
        "order": order,
        "execute": execute,
        "carried_over": list(plan["carried_over"]),
        "original_runs": dict(plan["original_runs"]),
    }


APPROVED = "approved"
APPROVED_AFTER_AMENDMENT = "approved_after_scoring_amendment"
TRANSLATOR_ASSISTED = "translator_assisted_owner_review"


def _sha_of(directory: Path, repo_path: str) -> str:
    """SHA-256 of a file named relative to the repository (`evaluation/...`)."""
    if not repo_path.startswith("evaluation/"):
        raise ValueError(f"unexpected path {repo_path!r}")
    return hashlib.sha256(
        (directory / repo_path.removeprefix("evaluation/")).read_bytes()
    ).hexdigest()


def apply_review_attestation(
    dataset: Dataset, prereg: dict[str, Any], directory: Path = EVAL_ROOT
) -> tuple[Dataset, dict[str, Any] | None]:
    """A human-review attestation (v5.2.2+) records the owner's review of every case in a separate
    file, so the immutable dataset metadata never has to be edited. The pre-registration pins the
    attestation's SHA-256 and the metadata's SHA-256; nothing else (no CLI path, no filename) can
    supply one. Everything the attestation claims is checked against the actual files. Returns
    (dataset with a review-status overlay, provenance); raises ValueError if anything is wrong,
    so the run is refused and the gate fails closed. Without a pinned attestation the review
    status comes from the metadata alone, as before."""
    ref = prereg.get("review_attestation")
    if not ref:
        return dataset, None
    try:
        return _verify_review_attestation(dataset, prereg, ref, directory)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"review attestation {ref.get('file')}: malformed ({error!r})") from None


def _verify_review_attestation(
    dataset: Dataset, prereg: dict[str, Any], ref: dict[str, Any], directory: Path
) -> tuple[Dataset, dict[str, Any]]:
    def fail(message: str) -> ValueError:
        return ValueError(f"review attestation {ref.get('file')}: {message}")

    # 1. The exact registered bytes; the metadata is the pinned file and is what was loaded.
    raw = (directory / ref["file"]).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != ref["sha256"]:
        raise fail("changed since it was pre-registered")
    meta_ref = prereg["dataset_metadata"]
    meta_raw = (directory / meta_ref["file"]).read_bytes()
    if hashlib.sha256(meta_raw).hexdigest() != meta_ref["sha256"]:
        raise ValueError(f"{meta_ref['file']} changed since it was pre-registered")
    if yaml.safe_load(meta_raw) != dataset.meta:
        raise ValueError(f"the loaded metadata for {dataset.name} is not {meta_ref['file']}")
    try:
        att = yaml.load(raw, Loader=_UniqueKeyLoader)  # noqa: S506 (a SafeLoader subclass)
    except (yaml.YAMLError, ValueError) as error:
        raise fail(f"unreadable ({error})") from None
    scope = att["scope"]

    # 2. Identity, reviewer and confirmations, exactly as registered.
    if att.get("attestation") != ref["attestation"]:
        raise fail("is not the registered attestation")
    if (att.get("reviewer") or {}).get("role") != ref["reviewer_role"]:
        raise fail(f"reviewer role is not {ref['reviewer_role']!r}")
    if str(att.get("record_created_at_utc")) != ref["record_created_at_utc"]:
        raise fail("creation timestamp differs from the registered one")
    confirmations = att.get("owner_confirmations") or {}
    for key in ref["required_confirmations"]:
        if confirmations.get(key) is not True:
            raise fail(f"missing owner confirmation {key}")

    # 3. The dataset, the metadata, the scoring amendment and the historical chain it reviewed.
    data_raw = (directory / "datasets" / f"{dataset.name}.jsonl").read_bytes()
    if hashlib.sha256(data_raw).hexdigest() != dataset.sha256:
        raise ValueError(f"{dataset.name}.jsonl doesn't match the loaded dataset")
    if (
        scope.get("dataset") != dataset.name
        or scope.get("dataset_sha256") != dataset.sha256
        or scope.get("dataset_file") != f"evaluation/datasets/{dataset.name}.jsonl"
    ):
        raise fail("was written for a different dataset or dataset version")
    if (scope.get("dataset_metadata") or {}).get("sha256") != meta_ref["sha256"]:
        raise fail("was written against different dataset metadata")
    amend_ref = prereg.get("scoring_amendment") or {}
    att_amend = scope.get("scoring_amendment") or {}
    if not amend_ref or att_amend.get("sha256") != amend_ref.get("sha256"):
        raise fail("references a different scoring amendment")
    if _sha_of(directory, att_amend["file"]) != amend_ref["sha256"]:
        raise fail("the referenced scoring amendment file doesn't match its hash")
    amendment = yaml.safe_load((directory / amend_ref["file"]).read_bytes())
    amended_cases = att_amend.get("cases") or {}
    if set(amended_cases) != set(amendment["cases"]):
        raise fail("lists different amended cases than the scoring amendment")
    for key, registered in ref["historical_references"].items():
        claimed = scope.get(key) or {}
        if claimed.get("sha256") != registered or _sha_of(directory, claimed["file"]) != registered:
            raise fail(f"historical reference {key} doesn't match")

    # 4. Every case exactly once, explicitly approved, bound to its exact dataset line.
    lines = [ln for ln in data_raw.decode("utf-8").splitlines() if ln.strip()]
    line_sha = {
        str(json.loads(ln)["id"]): hashlib.sha256(ln.encode("utf-8")).hexdigest() for ln in lines
    }
    decisions = att.get("decisions")
    if not isinstance(decisions, dict):
        raise fail("has no decisions")
    missing, extra = set(line_sha) - set(decisions), set(decisions) - set(line_sha)
    if missing or extra:
        raise fail(f"case set differs (missing {sorted(missing)}, unregistered {sorted(extra)})")
    methods: dict[str, str] = ref.get("review_methods") or {}
    for case_id, entry in decisions.items():
        if not isinstance(entry, dict):
            raise fail(f"{case_id} has no decision")
        want = APPROVED_AFTER_AMENDMENT if case_id in amended_cases else APPROVED
        if entry.get("decision") != want:
            raise fail(f"{case_id} decision is {entry.get('decision')!r}, expected {want!r}")
        condition = entry.get("scoring_amendment_condition")
        if case_id in amended_cases and condition != amended_cases[case_id]:
            raise fail(f"{case_id} doesn't reference its scoring amendment condition")
        if case_id not in amended_cases and condition is not None:
            raise fail(f"{case_id} references a scoring amendment it isn't covered by")
        if entry.get("case_line_sha256") != line_sha[case_id]:
            raise fail(f"{case_id} was reviewed against a different version of the case")
        if entry.get("review_method") != methods.get(case_id):
            raise fail(f"{case_id} review method differs from the registered one")
    summary = att.get("summary") or {}
    counts = {
        APPROVED: sum(1 for e in decisions.values() if e["decision"] == APPROVED),
        APPROVED_AFTER_AMENDMENT: len(amended_cases),
        "rejected": 0,
        "pending": 0,
        "total": len(decisions),
    }
    if summary != counts:
        raise fail(f"summary {summary} doesn't match the decisions {counts}")

    # 5. Translator-assisted reviews carry an explicit disclosure that claims no more than that.
    by_id = {c.id: c for c in dataset.cases}
    disclosures: dict[str, str] = {}
    for case_id, method in methods.items():
        if method != TRANSLATOR_ASSISTED:
            raise fail(f"unknown review method {method!r}")
        note = att.get(f"{case_id.lower()}_disclosure") or {}
        if (
            note.get("case") != case_id
            or note.get("native_or_proficient_speaker_review") != "none"
            or note.get("independent_linguistic_validation") != "none"
            or not by_id[case_id].expected.startswith(f"{note.get('correct_answer')}.")
        ):
            raise fail(f"{case_id} translator-assisted disclosure is missing or inconsistent")
        disclosures[case_id] = (
            f"{case_id}: translator-assisted owner review ({note.get('method')}); "
            "no native-speaker or independent linguistic validation"
        )

    provenance = {
        "file": ref["file"],
        "sha256": sha,
        "attestation": ref["attestation"],
        "reviewer_role": ref["reviewer_role"],
        "record_created_at_utc": ref["record_created_at_utc"],
        "dataset_metadata_sha256": meta_ref["sha256"],
        "cases_attested": len(decisions),
        "approved_after_scoring_amendment": sorted(amended_cases),
        "review_methods": dict(sorted(methods.items())),
        "disclosures": disclosures,
    }
    return dataset.model_copy(update={"attested_case_ids": frozenset(decisions)}), provenance
