import { useCallback } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatMs, formatNumber } from "../lib/format";
import { ErrorState, LoadingState } from "./States";
import { Badge, CostCell, Modal, SimulatedBadge, StatusBadge, TableWrap, td, th } from "./ui";

export function ReasonCodes({ codes }: { codes: string[] }) {
  if (!codes.length) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {codes.map((code) => (
        <Badge key={code} tone={code.startsWith("NO_") || code.includes("EXHAUSTED") ? "danger" : "accent"}>
          {code}
        </Badge>
      ))}
    </span>
  );
}

export function RequestDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const load = useCallback((signal: AbortSignal) => api.request(id, signal), [id]);
  const state = useApi(load);

  return (
    <Modal title="Request detail" onClose={onClose}>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        <div className="space-y-5 text-sm">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
            <div><dt className="inline text-muted">Request ID </dt><dd className="inline break-all font-mono">{state.data.id}</dd></div>
            <div><dt className="inline text-muted">Tenant </dt><dd className="inline">{state.data.tenant}</dd></div>
            <div><dt className="inline text-muted">Status </dt><dd className="inline"><StatusBadge status={state.data.status} /> {state.data.error_code}</dd></div>
            <div><dt className="inline text-muted">Created </dt><dd className="inline">{formatDateTime(state.data.created_at)}</dd></div>
            <div><dt className="inline text-muted">Model </dt><dd className="inline">{state.data.provider ? `${state.data.provider}/${state.data.model}` : "—"} {state.data.simulated ? <SimulatedBadge /> : null}</dd></div>
            <div><dt className="inline text-muted">Latency </dt><dd className="inline">{formatMs(state.data.latency_ms)}</dd></div>
            <div><dt className="inline text-muted">Actual charge </dt><dd className="inline"><CostCell kind="actual" amount={state.data.actual_charge_usd} status={state.data.cost_status} /></dd></div>
            <div><dt className="inline text-muted">List-price estimate </dt><dd className="inline"><CostCell kind="list" amount={state.data.estimated_list_cost_usd} status={state.data.list_cost_status} /></dd></div>
            <div className="sm:col-span-2"><dt className="inline text-muted">Prompt SHA-256 </dt><dd className="inline break-all font-mono text-xs">{state.data.prompt_sha256 ?? "—"}</dd> <span className="text-xs text-muted">(content is not stored)</span></div>
          </dl>

          {state.data.decision?.explanation ? (
            <div>
              <h3 className="mb-1 font-medium">Routing explanation</h3>
              <p className="text-muted">{state.data.decision.explanation}</p>
              <div className="mt-2"><ReasonCodes codes={state.data.decision.reason_codes ?? []} /></div>
            </div>
          ) : null}

          {state.data.decision?.contributions?.length ? (
            <div>
              <h3 className="mb-1 font-medium">Complexity score: {state.data.decision.score}/100</h3>
              <ul className="space-y-0.5">
                {state.data.decision.contributions.map((c) => (
                  <li key={c.feature} className="flex justify-between gap-4 border-b border-line py-1">
                    <span>{c.feature} <span className="text-muted">({c.detail})</span></span>
                    <span className="tabular-nums">+{c.points}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div>
            <h3 className="mb-1 font-medium">Attempts</h3>
            {state.data.attempts.length ? (
              <TableWrap>
                <table className="w-full">
                  <thead><tr><th className={th}>#</th><th className={th}>Model</th><th className={th}>Reason</th><th className={th}>Status</th><th className={th}>Tokens in/out</th><th className={th}>Latency</th><th className={th}>Est. list cost</th></tr></thead>
                  <tbody>
                    {state.data.attempts.map((a) => (
                      <tr key={a.attempt}>
                        <td className={td}>{a.attempt}</td>
                        <td className={td}>{a.provider}/{a.model}</td>
                        <td className={td}><Badge>{a.reason_code}</Badge></td>
                        <td className={td}>{a.status}{a.error_code ? ` (${a.error_code})` : ""}</td>
                        <td className={td}>{formatNumber(a.input_tokens)} / {formatNumber(a.output_tokens)}</td>
                        <td className={td}>{formatMs(a.latency_ms)}</td>
                        <td className={td}><CostCell kind="list" amount={a.estimated_list_cost_usd} status={a.list_cost_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            ) : (
              <p className="text-muted">No provider was called.</p>
            )}
            {state.data.decision?.execution?.skipped.length ? (
              <p className="mt-2 text-xs text-muted">
                Skipped: {state.data.decision.execution.skipped.map((s) => `${s.model} (${s.reason})`).join(", ")}
              </p>
            ) : null}
          </div>

          {state.data.decision?.candidates?.length ? (
            <div>
              <h3 className="mb-1 font-medium">Candidates considered</h3>
              <TableWrap>
                <table className="w-full">
                  <thead><tr><th className={th}>Model</th><th className={th}>Tier</th><th className={th}>Worst-case est.</th><th className={th}>Eligible / excluded because</th></tr></thead>
                  <tbody>
                    {state.data.decision.candidates.map((c) => (
                      <tr key={`${c.provider}/${c.model_id}`}>
                        <td className={td}>{c.provider}/{c.model_id}</td>
                        <td className={td}>{c.tier}</td>
                        <td className={td}>{c.worst_case_list_cost_usd ? `$${c.worst_case_list_cost_usd}` : "unpriced"}</td>
                        <td className={td}>{c.eligible ? <Badge tone="ok">eligible</Badge> : <ReasonCodes codes={c.exclusions} />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
