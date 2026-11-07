import { useMemo } from "react";
import { api } from "../api/client";
import type { EvalRun } from "../api/types";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Badge, Card, PageHeader, SimulatedBadge, TableWrap, td, th } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatMs, formatPercent, formatUsd } from "../lib/format";

function PassRateBar({ rate, ci }: { rate: number | null; ci: [number, number] | null }) {
  if (rate === null) return <span className="text-muted">—</span>;
  return (
    <div className="min-w-40">
      <div className="flex justify-between text-xs"><span>{formatPercent(rate)}</span>{ci ? <span className="text-muted">95% CI {formatPercent(ci[0], 0)}–{formatPercent(ci[1], 0)}</span> : null}</div>
      <div className="relative mt-1 h-2 rounded bg-sunken">
        {ci ? <div className="absolute h-2 rounded bg-accent/30" style={{ left: `${ci[0] * 100}%`, width: `${(ci[1] - ci[0]) * 100}%` }} /> : null}
        <div className="absolute h-2 w-0.5 bg-accent" style={{ left: `${rate * 100}%` }} />
      </div>
    </div>
  );
}

interface Accounting {
  expected: number;
  accounted: number;
  carried: number;
  executed: number;
  perStrategy: Record<string, { expected: number; carried: number; executed: number }>;
}

interface GroupStatus {
  execution: string;
  executionTone: "accent" | "warn" | "danger";
  publication: string;
  publishable: boolean;
  note: string | null;
  accounting: Accounting | null;
}

// A run's own summary only knows that run. For a day of a registered multi-day schedule (or a
// recovery of one), its "publishable" flag says nothing about the registered comparison, so both
// statuses come from the registration recorded in the run's config snapshot. Execution (did it
// run?) and publication eligibility (can it support a confirmatory claim?) are shown separately.
function groupStatus(runs: EvalRun[]): GroupStatus {
  const snapshot = runs[0]?.config_snapshot;
  const schedule = snapshot?.execution_schedule;
  const failed = runs.some((r) => r.status === "failed");
  const running = runs.some((r) => r.status === "running" || r.status === "pending");
  const execution = failed ? "interrupted" : running ? "in progress" : "completed";
  const executionTone = failed ? "danger" : running ? "warn" : "accent";
  if (!schedule) {
    const publishable = Boolean(runs[0]?.summary?.publishable);
    return { execution, executionTone, publication: publishable ? "publishable" : "not publishable", publishable, note: null, accounting: null };
  }
  const reasons = runs[0]?.summary?.publishable_reasons ?? [];
  const recovery = snapshot?.execution_recovery;
  const cases = schedule.case_ids?.length ?? 0;
  if (recovery) {
    const strategies = Object.keys(recovery.original_runs ?? {});
    const perStrategy: Accounting["perStrategy"] = {};
    for (const s of strategies) {
      const executed = recovery.executes.filter(([, strategy]) => strategy === s).length;
      perStrategy[s] = { expected: cases, executed, carried: cases - executed };
    }
    const executed = recovery.executes.length;
    const accounting = { expected: cases * strategies.length, accounted: executed + recovery.carried_over, carried: recovery.carried_over, executed, perStrategy };
    return {
      execution: "recovery completed",
      executionTone: failed ? "danger" : "accent",
      publication: "post-hoc recovery · exploratory · not publishable",
      publishable: false,
      note:
        `Disclosed post-hoc recovery of day ${recovery.day}: ${accounting.accounted}/${accounting.expected} combinations accounted for — ` +
        `${recovery.carried_over} carried over unchanged from the interrupted runs and ${executed} newly executed by this recovery. ` +
        "The metrics below cover only the newly executed combinations. Exploratory, not a confirmatory result.",
      accounting,
    };
  }
  const executedTotal = runs.reduce((n, r) => n + (r.summary?.metrics?.cases ?? 0), 0);
  const accounting = failed || !cases ? null : { expected: cases * runs.length, accounted: executedTotal, carried: 0, executed: executedTotal, perStrategy: {} };
  if (failed) {
    return {
      execution, executionTone, publication: "incident record · not a result", publishable: false, accounting,
      note: `Day ${schedule.day} of ${schedule.days} was interrupted and is kept as an incident record. It is incomplete and is not a result.`,
    };
  }
  const exploratory = reasons.some((r) => /exploratory/i.test(r));
  return {
    execution, executionTone, accounting, publishable: false,
    publication: exploratory ? "post-incident exploratory · not publishable" : "not publishable on its own",
    note: exploratory
      ? `Day ${schedule.day} of ${schedule.days}, run under a post-incident exploratory registration: not publishable as a confirmatory result.`
      : `Day ${schedule.day} of a registered ${schedule.days}-day schedule. A single day is not a confirmatory result on its own; it counts only within the complete registered comparison.`,
  };
}

function accountedFor(status: GroupStatus, strategy: string) {
  const a = status.accounting?.perStrategy[strategy];
  if (!a) return null;
  return (
    <>
      <br />
      <span className="text-xs text-muted">{`${a.carried + a.executed}/${a.expected} accounted: ${a.carried} carried over + ${a.executed} executed`}</span>
    </>
  );
}

function RunGroup({ label, runs }: { label: string; runs: EvalRun[] }) {
  const simulated = runs.some((r) => r.simulated);
  const reasons = runs[0]?.summary?.publishable_reasons ?? [];
  const status = groupStatus(runs);
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{label}</h2>
        {simulated ? <SimulatedBadge /> : <Badge tone="ok">live providers</Badge>}
        <Badge tone={status.executionTone} title="Execution status">{status.execution}</Badge>
        <Badge tone={status.publishable ? "ok" : "danger"} title="Publication eligibility">{status.publication}</Badge>
        {status.accounting ? (
          <Badge title="Registered combinations accounted for">{`${status.accounting.accounted}/${status.accounting.expected} combinations accounted for`}</Badge>
        ) : null}
        <span className="text-xs text-muted">{formatDateTime(runs[0]?.started_at)} · dataset {runs[0]?.dataset_version} · prereg {runs[0]?.preregistration_sha256.slice(0, 10)}</span>
      </div>
      {simulated ? (
        <p className="mb-3 rounded border border-warn/40 bg-warn/10 p-2 text-sm">
          Simulated run on the mock provider. It checks that the benchmark pipeline works; it is not a measurement of quality, cost or latency.
        </p>
      ) : null}
      {status.note ? <p className="mb-3 rounded border border-warn/40 bg-warn/10 p-2 text-sm">{status.note}</p> : null}
      {reasons.length ? <p className="mb-3 text-sm text-muted">Not publishable: {reasons.join("; ")}.</p> : null}
      <TableWrap>
        <table className="w-full">
          <thead>
            <tr>
              <th className={th}>Strategy</th><th className={th}>Pass rate</th><th className={th}>Failures</th><th className={th}>Est. cost / accepted</th>
              <th className={th}>p50 / p95</th><th className={th}>Fallback</th><th className={th}>Tiers</th><th className={th}>vs baseline (pre-registered)</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const m = run.summary?.metrics;
              const c = run.summary?.comparison_vs_baseline;
              return (
                <tr key={run.id}>
                  <td className={td}>{run.strategy}<br /><span className="text-xs text-muted">{run.status}</span>{accountedFor(status, run.strategy)}</td>
                  <td className={td}>{m ? <PassRateBar rate={m.pass_rate} ci={m.pass_rate_wilson_95} /> : "—"}<span className="text-xs text-muted">{m ? ` ${m.passed}/${m.scorable} scorable` : ""}</span></td>
                  <td className={td}>{m ? `${m.failures}/${m.cases}` : "—"}</td>
                  <td className={td}>{m ? formatUsd(m.estimated_list_cost_per_accepted_answer_usd) : "—"}</td>
                  <td className={td}>{m ? `${formatMs(m.latency_p50_ms)} / ${formatMs(m.latency_p95_ms)}` : "—"}</td>
                  <td className={td}>{m ? formatPercent(m.fallback_rate) : "—"}</td>
                  <td className={`${td} whitespace-normal text-xs`}>{m ? Object.entries(m.tier_distribution).map(([t, n]) => `${t}: ${n}`).join(", ") : "—"}</td>
                  <td className={`${td} whitespace-normal text-xs`}>
                    {c ? (
                      <>
                        Δ pass rate {c.pass_rate_difference ?? "—"} (CI {c.pass_rate_difference_bootstrap_95?.join(" to ") ?? "—"})<br />
                        quality rule: {c.quality_rule_point_estimate_holds ? "holds" : "fails"}; CI support: {c.non_inferiority_supported_by_ci ? "yes" : "no"}; cost rule: {c.cost_rule_holds ? "holds" : "fails"}
                      </>
                    ) : run.strategy === "baseline_premium" ? "baseline" : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
    </Card>
  );
}

// Page-level facts, derived from the persisted run snapshots: which registered schedules have an
// interrupted day (so their confirmatory comparison can't be completed), and the dataset's review status.
function scheduleIncidents(groups: [string, EvalRun[]][]): string[] {
  return groups
    .filter(([, runs]) => runs[0]?.config_snapshot?.execution_schedule && !runs[0]?.config_snapshot?.execution_recovery && runs.some((r) => r.status === "failed"))
    .map(([label, runs]) => {
      const snap = runs[0]?.config_snapshot;
      const s = snap?.execution_schedule;
      return `${snap?.execution_revision ?? "A registered schedule"}: day ${s?.day} of ${s?.days} was interrupted (${label}), so its ${s?.days}-day confirmatory comparison is incomplete. Later days and recoveries ran under separate exploratory registrations.`;
    });
}

function reviewStatus(runs: EvalRun[]): string {
  const snap = runs.find((r) => r.config_snapshot?.review_attestation)?.config_snapshot;
  const att = snap?.review_attestation;
  if (!att) return runs.some((r) => r.config_snapshot?.dataset_fully_reviewed) ? "Dataset review: marked fully reviewed, no attestation recorded." : "Dataset review: no human-review attestation recorded.";
  const disclosures = Object.values(att.disclosures ?? {});
  return `Dataset review: ${att.cases_attested} cases attested by the ${att.reviewer_role.toLowerCase()} (attestation ${att.sha256.slice(0, 12)})${snap?.dataset_fully_reviewed ? ", fully reviewed" : ""}.${disclosures.length ? ` Disclosure: ${disclosures.join(" ")}` : ""}`;
}

export function Evaluation() {
  const state = useApi(api.evalRuns);
  const groups = useMemo(() => {
    if (state.status !== "success") return [];
    const map = new Map<string, EvalRun[]>();
    for (const run of state.data.items) map.set(run.label, [...(map.get(run.label) ?? []), run]);
    return [...map.entries()];
  }, [state]);
  const incidents = scheduleIncidents(groups);
  const review = state.status === "success" && state.data.items.length ? reviewStatus(state.data.items) : null;

  return (
    <section>
      <PageHeader
        title="Benchmark & Evaluation"
        description="All-premium baseline vs RouteWise routing on the 45-case suite, judged against pre-registered thresholds. Each group is one run label, with its execution status and its publication eligibility shown separately."
      />
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        groups.length === 0 ? (
          <EmptyState title="No benchmark runs yet">Run `uv run python -m app.cli eval-run --label …` from the backend.</EmptyState>
        ) : (
          <div className="space-y-4">
            {review ? <p className="text-sm text-muted">{review}</p> : null}
            {incidents.map((text) => (
              <p key={text} className="rounded border border-danger/40 bg-danger/10 p-2 text-sm" role="note">{text}</p>
            ))}
            {groups.map(([label, runs]) => <RunGroup key={label} label={label} runs={runs} />)}
          </div>
        )
      ) : null}
    </section>
  );
}
