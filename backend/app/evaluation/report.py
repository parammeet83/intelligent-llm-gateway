"""Benchmark metrics, pre-registered verdicts, and report files (JSON + Markdown)."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.db.models import EvaluationRun
from app.db.session import Database
from app.evaluation.runner import BenchmarkResult, CaseOutcome, outcome_dicts
from app.evaluation.stats import mean_difference, paired_bootstrap, percentile, wilson_interval

BASELINE = "baseline_premium"


def _scorable(o: CaseOutcome) -> bool:
    return o.passed is not None and not o.needs_human_review


def strategy_metrics(
    outcomes: list[CaseOutcome], limits: dict[str, Any], *, errors_are_missing: bool = False
) -> dict[str, Any]:
    """`errors_are_missing` (prereg-v3+): a request that returned no answer (provider error,
    timeout, rate limit) is excluded from the pass-rate denominator instead of counted as failed."""
    executed = [o for o in outcomes if o.error_code is None]
    scorable = [o for o in outcomes if _scorable(o) and not (errors_are_missing and o.error_code)]
    passes = sum(1 for o in scorable if o.passed)
    priced = [
        o for o in executed if o.list_cost_status == "estimated" and o.estimated_list_cost_usd
    ]
    total_cost = sum((Decimal(o.estimated_list_cost_usd or 0) for o in priced), Decimal(0))
    accepted_priced = [o for o in priced if o.passed and not o.needs_human_review]
    latencies = [o.latency_ms for o in executed if o.latency_ms is not None]
    ci = wilson_interval(passes, len(scorable))
    violations = {"cost": 0, "latency": 0}
    for o in executed:
        limit = limits.get(o.difficulty, {})
        if (
            o.estimated_list_cost_usd
            and "max_cost_usd" in limit
            and Decimal(o.estimated_list_cost_usd) > Decimal(str(limit["max_cost_usd"]))
        ):
            violations["cost"] += 1
        if (
            o.latency_ms is not None
            and "max_latency_ms" in limit
            and o.latency_ms > int(limit["max_latency_ms"])
        ):
            violations["latency"] += 1
    by_difficulty: dict[str, Any] = {}
    for level in ("simple", "standard", "complex"):
        group = [o for o in scorable if o.difficulty == level]
        by_difficulty[level] = {
            "scorable": len(group),
            "passed": sum(1 for o in group if o.passed),
            "pass_rate": round(sum(1 for o in group if o.passed) / len(group), 4)
            if group
            else None,
        }
    return {
        "cases": len(outcomes),
        "executed": len(executed),
        "failures": len(outcomes) - len(executed),
        "failure_rate": round((len(outcomes) - len(executed)) / len(outcomes), 4)
        if outcomes
        else None,
        "failure_codes": dict(Counter(o.error_code for o in outcomes if o.error_code)),
        "scorable": len(scorable),
        "not_auto_scorable": sum(1 for o in outcomes if o.passed is None),
        "needs_human_review": sum(1 for o in outcomes if o.needs_human_review),
        "passed": passes,
        # Availability is reported separately from quality.
        "answered": len(executed),
        "answer_rate": round(len(executed) / len(outcomes), 4) if outcomes else None,
        "pass_rate_basis": "conditional_on_answer_returned"
        if errors_are_missing
        else "all_cases_errors_count_as_failures",
        "pass_rate": round(passes / len(scorable), 4) if scorable else None,
        "pass_rate_unconditional": round(passes / len(outcomes), 4) if outcomes else None,
        "answer_model_distribution": dict(
            Counter(f"{o.provider}/{o.answer_model}" for o in executed if o.answer_model)
        ),
        "attempt_model_distribution": dict(
            Counter(f"{a.get('provider')}/{a.get('model')}" for o in outcomes for a in o.attempts)
        ),
        "attempt_status_distribution": dict(
            Counter(str(a.get("status")) for o in outcomes for a in o.attempts)
        ),
        "pass_rate_wilson_95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "by_difficulty": by_difficulty,
        "estimated_list_cost_total_usd": str(total_cost),
        "estimated_list_cost_per_request_usd": str(
            (total_cost / len(priced)).quantize(Decimal("0.00000001"))
        )
        if priced
        else None,
        "estimated_list_cost_per_accepted_answer_usd": str(
            (total_cost / len(accepted_priced)).quantize(Decimal("0.00000001"))
        )
        if accepted_priced
        else None,
        "requests_with_unknown_list_cost": len(executed) - len(priced),
        # Failed requests may still have consumed tokens and report no cost, so they're unknown
        # cost observations too (never zero).
        "unknown_cost_observations": (len(executed) - len(priced))
        + (len(outcomes) - len(executed)),
        "actual_charge_status": dict(Counter(o.cost_status for o in executed)),
        "input_tokens": sum(o.input_tokens or 0 for o in executed),
        "output_tokens": sum(o.output_tokens or 0 for o in executed),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "fallback_rate": round(sum(1 for o in executed if o.fallback_used) / len(executed), 4)
        if executed
        else None,
        "provider_distribution": dict(Counter(o.provider for o in executed)),
        "model_distribution": dict(Counter(f"{o.provider}/{o.model}" for o in executed)),
        "tier_distribution": dict(Counter(o.tier for o in executed)),
        "per_case_limit_violations": violations,
    }


def compare(
    baseline: list[CaseOutcome],
    candidate: list[CaseOutcome],
    prereg: dict[str, Any],
    base: dict[str, Any],
    cand: dict[str, Any],
    *,
    errors_are_missing: bool = False,
) -> dict[str, Any]:
    margin = float(prereg["quality_rule"]["non_inferiority_margin"])
    stats_cfg = prereg["statistics"]

    def usable(o: CaseOutcome) -> bool:
        return _scorable(o) and not (errors_are_missing and o.error_code)

    by_case_base = {o.case_id: o for o in baseline if usable(o)}
    pairs = [
        (1.0 if by_case_base[o.case_id].passed else 0.0, 1.0 if o.passed else 0.0)
        for o in candidate
        if usable(o) and o.case_id in by_case_base
    ]
    diff = mean_difference(pairs) if pairs else None
    ci = paired_bootstrap(
        pairs,
        mean_difference,
        resamples=int(stats_cfg["bootstrap_resamples"]),
        seed=int(stats_cfg["bootstrap_seed"]),
    )
    point_holds = diff is not None and diff >= -margin
    supported = ci is not None and ci[0] > -margin
    base_cpa = base["estimated_list_cost_per_accepted_answer_usd"]
    cand_cpa = cand["estimated_list_cost_per_accepted_answer_usd"]
    cost_lower = (
        base_cpa is not None and cand_cpa is not None and Decimal(cand_cpa) < Decimal(base_cpa)
    )
    ratio = (
        round(float(Decimal(cand_cpa) / Decimal(base_cpa)), 4)
        if base_cpa and cand_cpa and Decimal(base_cpa) > 0
        else None
    )
    # prereg-v3+: a cost claim needs CI-supported non-inferiority, and any unknown cost
    # observation (in either strategy) blocks it, because unknown is never treated as zero.
    cost_cfg = prereg.get("cost_rule") or {}
    quality_ok = supported if cost_cfg.get("requires_ci_supported_non_inferiority") else point_holds
    cost_blocked: list[str] = []
    if cost_cfg.get("unknown_cost_observations") == "block":
        unknown = {
            "baseline": base.get("unknown_cost_observations", 0),
            "candidate": cand.get("unknown_cost_observations", 0),
        }
        if any(unknown.values()):
            cost_blocked.append(f"unknown cost observations: {unknown}")
    if cost_cfg.get("requires_ci_supported_non_inferiority") and not supported:
        cost_blocked.append("quality non-inferiority not supported by the CI")
    return {
        "paired_cases": len(pairs),
        "pass_rate_difference": round(diff, 4) if diff is not None else None,
        "pass_rate_difference_bootstrap_95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "non_inferiority_margin": margin,
        "quality_rule_point_estimate_holds": point_holds,
        "non_inferiority_supported_by_ci": supported,
        "cost_per_accepted_answer_ratio": ratio,
        "cost_rule_holds": bool(quality_ok and cost_lower and not cost_blocked),
        "cost_rule_blocked_reasons": cost_blocked,
    }


def build_summary(result: BenchmarkResult) -> dict[str, Any]:
    limits = result.preregistration.get("per_case_limits", {})
    groups: dict[str, list[CaseOutcome]] = {}
    for o in result.outcomes:
        groups.setdefault(o.strategy, []).append(o)
    missing = (result.preregistration.get("run_validity") or {}).get("provider_errors") == "missing"
    metrics = {
        name: strategy_metrics(group, limits, errors_are_missing=missing)
        for name, group in groups.items()
    }
    comparisons = {
        name: compare(
            groups[BASELINE],
            group,
            result.preregistration,
            metrics[BASELINE],
            metrics[name],
            errors_are_missing=missing,
        )
        for name, group in groups.items()
        if name != BASELINE and BASELINE in groups
    }
    # Pre-registered guards (prereg-v2+): claims are blocked, not just annotated.
    blocked: list[str] = []
    # prereg-v4+: the baseline must only ever call premium-tier models (retries and fallbacks
    # included). The router guarantees this by construction; the report verifies it per attempt.
    if result.preregistration.get("baseline_tier_guard") == "premium_only":
        off_tier = sorted(
            {
                f"{a.get('provider')}/{a.get('model')} ({a.get('tier')})"
                for o in groups.get(BASELINE, [])
                for a in o.attempts
                if a.get("tier") != "premium"
            }
        )
        if off_tier:
            blocked.append(f"run invalid: baseline attempts outside the premium tier {off_tier}")
    # prereg-v3+: every answering model must be one the experiment manifest declared.
    expected_models = (result.config_snapshot.get("manifest") or {}).get("expected_models")
    if expected_models is not None:
        seen = {f"{o.provider}/{o.model}" for o in result.outcomes if o.error_code is None}
        unexpected = sorted(seen - set(expected_models))
        if unexpected:
            blocked.append(f"run invalid: models outside the experiment manifest {unexpected}")
    min_answered = (result.preregistration.get("run_validity") or {}).get("min_answered_fraction")
    if min_answered is not None:
        short = [
            n
            for n, m in metrics.items()
            if m["cases"] and m["executed"] / m["cases"] < min_answered
        ]
        if short:
            blocked.append(f"run invalid: fewer than {min_answered:.0%} answered for {short}")
    floor = (result.preregistration.get("baseline_floor") or {}).get("floor")
    base_rate = metrics.get(BASELINE, {}).get("pass_rate")
    if floor is not None and base_rate is not None and base_rate < floor:
        blocked.append(f"uninformative: baseline pass rate {base_rate} is below the {floor} floor")
    for comparison in comparisons.values():
        comparison["claims_allowed"] = not blocked
        comparison["claims_blocked_reasons"] = blocked
    publishable = (
        not result.simulated
        and result.dataset_fully_reviewed
        and not result.incomplete
        and not any(r.startswith("run invalid") for r in blocked)
    )
    return {
        "label": result.label,
        "simulated": result.simulated,
        "publishable": publishable,
        "publishable_reasons": [
            r
            for r, bad in (
                (
                    "simulated run (mock provider): pipeline check only, not a result",
                    result.simulated,
                ),
                ("dataset not fully human-reviewed", not result.dataset_fully_reviewed),
                ("run incomplete", result.incomplete),
            )
            if bad
        ]
        + [r for r in blocked if r.startswith("run invalid")],
        "dataset": result.dataset,
        "dataset_sha256": result.dataset_sha256,
        "preregistration_sha256": result.preregistration_sha256,
        "execution_revision": result.config_snapshot.get("execution_revision"),
        "scoring_amendment": result.config_snapshot.get("scoring_amendment"),
        "review_attestation": result.config_snapshot.get("review_attestation"),
        "execution_schedule": result.config_snapshot.get("execution_schedule"),
        "dataset_fully_reviewed": result.dataset_fully_reviewed,
        "incomplete": result.incomplete,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "run_ids": result.run_ids,
        "metrics": metrics,
        "comparisons_vs_baseline": comparisons,
        "cost_basis": "Estimated list-price (shadow) cost; free-tier calls are actually billed $0.",
    }


def _markdown(summary: dict[str, Any]) -> str:
    lines = [f"# Benchmark report: {summary['label']}", ""]
    if summary["simulated"]:
        lines += [
            "> **SIMULATED RUN.** Mock provider only. These numbers check that the pipeline works;",
            "> they say nothing about model quality, cost, or latency.",
            "",
        ]
    if not summary["publishable"]:
        lines += ["**Not publishable:** " + "; ".join(summary["publishable_reasons"]), ""]
    lines += [
        f"- Dataset `{summary['dataset']}` (sha256 `{summary['dataset_sha256'][:12]}…`)",
        f"- Pre-registration sha256 `{summary['preregistration_sha256'][:12]}…`",
        f"- Window {summary['started_at']} → {summary['finished_at']}",
        f"- Cost basis: {summary['cost_basis']}",
    ]
    amendment = summary.get("scoring_amendment")
    if amendment:
        lines.append(
            f"- Scoring amendment `{amendment['file']}` (sha256 `{amendment['sha256'][:12]}…`) "
            f"for {', '.join(amendment['cases'])}"
        )
    review = summary.get("review_attestation")
    if review:
        lines.append(
            f"- Human review: {review['cases_attested']} cases attested by the "
            f"{review['reviewer_role'].lower()} (`{review['file']}`, sha256 "
            f"`{review['sha256'][:12]}…`)"
        )
        lines += [f"  - **Disclosure:** {note}" for note in review["disclosures"].values()]
    schedule = summary.get("execution_schedule")
    if schedule and schedule.get("day") is not None:
        lines.append(
            f"- Execution schedule `{schedule['file']}`: day {schedule['day']} of "
            f"{schedule['days']} ({schedule['utc_date']} UTC); not an analysis on its own, "
            "pool all days with `eval-combine`"
        )
    lines += [
        "",
        "Pass rates are **conditional on an answer being returned** when the basis says so; answer "
        "availability is the separate *Answered* column.",
        "",
        "| Strategy | Answered (rate) | Pass rate (95% CI) | Basis | Est. cost / accepted "
        "| p50 / p95 ms | Fallback rate | Answering models | Attempted models |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, m in summary["metrics"].items():
        ci = m["pass_rate_wilson_95"]
        rate = (
            f"{m['pass_rate']:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]"
            if m["pass_rate"] is not None and ci
            else "n/a"
        )
        lines.append(
            f"| {name} | {m.get('answered')}/{m['cases']} ({m.get('answer_rate')}) | "
            f"{rate} ({m['passed']}/{m['scorable']}) | {m.get('pass_rate_basis')} | "
            f"{m['estimated_list_cost_per_accepted_answer_usd'] or 'n/a'} | "
            f"{m['latency_p50_ms']} / {m['latency_p95_ms']} | {m['fallback_rate']} | "
            f"{m.get('answer_model_distribution')} | {m.get('attempt_model_distribution')} |"
        )
    lines += ["", "## Pre-registered verdicts", ""]
    for name, c in summary["comparisons_vs_baseline"].items():
        lines.append(
            f"- **{name}**: pass-rate difference {c['pass_rate_difference']} (bootstrap 95% CI "
            f"{c['pass_rate_difference_bootstrap_95']}); quality point estimate holds: "
            f"{c['quality_rule_point_estimate_holds']}; non-inferiority supported by CI: "
            f"{c['non_inferiority_supported_by_ci']}; cost-per-accepted ratio "
            f"{c['cost_per_accepted_answer_ratio']}; cost rule holds: {c['cost_rule_holds']}."
        )
    return "\n".join(lines) + "\n"


async def store_summaries(db: Database, summary: dict[str, Any]) -> None:
    """Attach each strategy's metrics (and its comparison with the baseline) to its run row."""
    async with db.sessionmaker() as session:
        for name, run_id in summary["run_ids"].items():
            run = await session.get(EvaluationRun, uuid.UUID(run_id))
            if run is not None:
                run.summary = {
                    "metrics": summary["metrics"].get(name),
                    "comparison_vs_baseline": summary["comparisons_vs_baseline"].get(name),
                    "publishable": summary["publishable"],
                    "publishable_reasons": summary["publishable_reasons"],
                    "label": summary["label"],
                }
        await session.commit()


def write_report(result: BenchmarkResult, directory: Path) -> tuple[Path, dict[str, Any]]:
    summary = build_summary(result)
    name = ("simulated-" if result.simulated else "") + result.label
    out = directory / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "summary.md").write_text(_markdown(summary), encoding="utf-8")
    with (out / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in outcome_dicts(result):
            handle.write(json.dumps(row) + "\n")
    return out, summary


def combine_scheduled_reports(
    day_dirs: list[Path],
    *,
    dataset: Any,
    prereg: dict[str, Any],
    prereg_sha: str,
    revision: str,
    label: str,
    directory: Path,
) -> tuple[Path, dict[str, Any]]:
    """Pool the per-day reports of a registered multi-day schedule (v5.2.3+) into the single
    pre-registered analysis: every case of every strategy, paired by case, the same statistics.

    Refuses (ValueError) anything that isn't exactly one report per registered day of this
    revision's schedule, with the registered cases, distinct UTC dates in day order, and the same
    scoring amendment, review attestation and simulated status. Nothing is dropped: an incomplete
    day, or a day span longer than registered, makes the combined comparison incomplete (never
    publishable) instead of being excluded."""
    from datetime import date

    from app.core.config import REPO_ROOT
    from app.evaluation.dataset import load_execution_schedule
    from app.evaluation.manifest import load_manifest

    schedule = load_execution_schedule(dataset, prereg)
    if schedule is None:
        raise ValueError("this pre-registration registers no execution schedule")
    days: dict[int, tuple[Path, dict[str, Any], list[CaseOutcome]]] = {}
    for path in day_dirs:
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        if summary.get("preregistration_sha256") != prereg_sha:
            raise ValueError(f"{path.name}: not run under this pre-registration")
        if summary.get("execution_revision") != revision:
            raise ValueError(f"{path.name}: not a run of {revision}")
        info = summary.get("execution_schedule") or {}
        if info.get("sha256") != schedule["sha256"]:
            raise ValueError(f"{path.name}: not run under the registered execution schedule")
        day = info.get("day")
        if not isinstance(day, int):
            raise ValueError(f"{path.name}: no scheduled day recorded")
        if day in days:
            raise ValueError(f"scheduled day {day} supplied twice")
        if info.get("case_ids") != schedule["days"].get(day):
            raise ValueError(f"{path.name}: cases differ from scheduled day {day}")
        lines = (path / "results.jsonl").read_text(encoding="utf-8").splitlines()
        outcomes = [CaseOutcome(**json.loads(line)) for line in lines if line.strip()]
        if {o.case_id for o in outcomes} - set(info["case_ids"]):
            raise ValueError(f"{path.name}: results include cases outside scheduled day {day}")
        days[day] = (path, summary, outcomes)
    missing = sorted(set(schedule["days"]) - set(days))
    if missing:
        raise ValueError(f"missing scheduled days {missing}: every day must be pooled")
    ordered = [days[d] for d in sorted(days)]
    dates = [s["execution_schedule"]["utc_date"] for _, s, _ in ordered]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError(f"scheduled days must run on distinct UTC dates in day order: {dates}")
    for key in ("simulated", "scoring_amendment", "review_attestation"):
        if len({json.dumps(s.get(key), sort_keys=True) for _, s, _ in ordered}) != 1:
            raise ValueError(f"scheduled days differ in {key}")
    violations: list[str] = []
    span = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    if span > schedule["max_span_days"]:
        violations.append(
            f"days span {span} days, above the registered {schedule['max_span_days']}"
        )
    strategies = sorted({o.strategy for _, _, outs in ordered for o in outs})
    for d, (path, _, outs) in zip(sorted(days), ordered, strict=True):
        have = {(o.case_id, o.strategy) for o in outs}
        want = {(c, st) for c in schedule["days"][d] for st in strategies}
        if have != want or len(outs) != len(want):
            violations.append(f"day {d} ({path.name}) lacks a result for some case and strategy")
    first = ordered[0][1]
    order = {c.id: i for i, c in enumerate(dataset.cases)}
    outcomes = sorted(
        (o for _, _, outs in ordered for o in outs),
        key=lambda o: (order.get(o.case_id, len(order)), strategies.index(o.strategy)),
    )
    manifest, _ = load_manifest(REPO_ROOT / "evaluation" / prereg["experiment_manifest"]["file"])
    result = BenchmarkResult(
        label=label,
        simulated=bool(first["simulated"]),
        dataset=dataset.name,
        dataset_sha256=dataset.sha256,
        dataset_fully_reviewed=all(s.get("dataset_fully_reviewed") for _, s, _ in ordered),
        preregistration=prereg,
        preregistration_sha256=prereg_sha,
        started_at=ordered[0][1]["started_at"],
        finished_at=ordered[-1][1]["finished_at"],
        config_snapshot={
            "manifest": {"expected_models": manifest["pinned"]["expected_models"]},
            "execution_revision": revision,
            "scoring_amendment": first.get("scoring_amendment"),
            "review_attestation": first.get("review_attestation"),
            "execution_schedule": {
                "file": schedule["file"],
                "sha256": schedule["sha256"],
                "days": len(schedule["days"]),
                "utc_dates": dates,
            },
        },
        run_ids={
            f"day{d}:{k}": v
            for d, (_, s, _) in zip(sorted(days), ordered, strict=True)
            for k, v in s.get("run_ids", {}).items()
        },
        outcomes=outcomes,
        incomplete=bool(violations) or any(s.get("incomplete") for _, s, _ in ordered),
    )
    summary = build_summary(result)
    limits = prereg.get("per_case_limits", {})
    missing_rule = (prereg.get("run_validity") or {}).get("provider_errors") == "missing"
    summary["schedule_violations"] = violations
    summary["schedule_days"] = [
        {
            "day": d,
            "report": path.name,
            "utc_date": s["execution_schedule"]["utc_date"],
            "started_at": s["started_at"],
            "finished_at": s["finished_at"],
            "incomplete": bool(s.get("incomplete")),
            "cases": len(schedule["days"][d]),
            # Descriptive only (drift check); the registered analysis pools all days.
            "per_strategy": {
                name: {k: m[k] for k in ("answered", "pass_rate", "answer_model_distribution")}
                for name, m in (
                    (
                        st,
                        strategy_metrics(
                            [o for o in outs if o.strategy == st],
                            limits,
                            errors_are_missing=missing_rule,
                        ),
                    )
                    for st in strategies
                )
            },
        }
        for d, (path, s, outs) in zip(sorted(days), ordered, strict=True)
    ]
    out = directory / (("simulated-" if result.simulated else "") + label)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = _markdown(summary).rstrip("\n").split("\n")
    md += ["", "## Scheduled days (descriptive; the verdicts above pool all days)", ""]
    md += [
        "| Day | UTC date | Cases | Strategy pass rates | Answering models |",
        "|---|---|---|---|---|",
    ]
    for row in summary["schedule_days"]:
        rates = "; ".join(f"{k} {v['pass_rate']}" for k, v in row["per_strategy"].items())
        models = "; ".join(
            f"{k}: {v['answer_model_distribution']}" for k, v in row["per_strategy"].items()
        )
        md.append(f"| {row['day']} | {row['utc_date']} | {row['cases']} | {rates} | {models} |")
    md += [f"- **Schedule violation:** {v}" for v in violations]
    (out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with (out / "results.jsonl").open("w", encoding="utf-8") as handle:
        day_of = {c: d for d, ids in schedule["days"].items() for c in ids}
        for row_dict in outcome_dicts(result):
            handle.write(
                json.dumps({**row_dict, "schedule_day": day_of[row_dict["case_id"]]}) + "\n"
            )
    return out, summary
