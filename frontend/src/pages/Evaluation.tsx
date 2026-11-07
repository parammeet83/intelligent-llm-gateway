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

// A run's own summary only knows that run. For a day of a registered multi-day schedule (or a
// recovery of one), its "publishable" flag says nothing about the registered comparison, so the
// status comes from the registration recorded in the run's config snapshot instead.
function groupStatus(runs: EvalRun[]): { badge: string; note: string | null } {
  const snapshot = runs[0]?.config_snapshot;
  const schedule = snapshot?.execution_schedule;
  if (!schedule) {
    return { badge: runs[0]?.summary?.publishable ? "publishable" : "not publishable", note: null };
  }
  const recovery = snapshot?.execution_recovery;
  if (recovery) {
    const executed = recovery.executes.length;
    return {
      badge: "post-hoc recovery · not publishable",
      note:
        `Disclosed post-hoc recovery of day ${recovery.day}. These runs hold only the ${executed} combinations it executed; ` +
        `${recovery.carried_over} more were carried over from the interrupted runs, so the recovery accounts for ` +
        `${executed + recovery.carried_over} in total (see its report). Exploratory, not a confirmatory result.`,
    };
  }
  if (runs.some((r) => r.status === "failed")) {
    return { badge: "interrupted · incident record", note: `Day ${schedule.day} of ${schedule.days} was interrupted and is kept as an incident record, not a result.` };
  }
  return {
    badge: "not publishable",
    note: `Day ${schedule.day} of a registered ${schedule.days}-day schedule. A single day is not a confirmatory result on its own, and the registered four-day comparison was never completed.`,
  };
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
        <Badge tone={status.badge === "publishable" ? "ok" : "danger"}>{status.badge}</Badge>
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
                  <td className={td}>{run.strategy}<br /><span className="text-xs text-muted">{run.status}</span></td>
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

export function Evaluation() {
  const state = useApi(api.evalRuns);
  const groups = useMemo(() => {
    if (state.status !== "success") return [];
    const map = new Map<string, EvalRun[]>();
    for (const run of state.data.items) map.set(run.label, [...(map.get(run.label) ?? []), run]);
    return [...map.entries()];
  }, [state]);

  return (
    <section>
      <PageHeader
        title="Benchmark & Evaluation"
        description="All-premium baseline vs RouteWise routing on the 45-case suite, judged against pre-registered thresholds. Each group is one run label; a scheduled day or a recovery is exploratory and not a confirmatory result on its own."
      />
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        groups.length === 0 ? (
          <EmptyState title="No benchmark runs yet">Run `uv run python -m app.cli eval-run --label …` from the backend.</EmptyState>
        ) : (
          <div className="space-y-4">{groups.map(([label, runs]) => <RunGroup key={label} label={label} runs={runs} />)}</div>
        )
      ) : null}
    </section>
  );
}
