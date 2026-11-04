import { useCallback, useState, type FormEvent } from "react";
import { api, type RequestFilters } from "../api/client";
import { ReasonCodes, RequestDetailModal } from "../components/RequestDetail";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Badge, Button, CostCell, PageHeader, Pagination, Select, SimulatedBadge, StatusBadge, TableWrap, td, th } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatMs } from "../lib/format";

const PAGE = 25;
const STATUSES = ["", "succeeded", "failed", "pending", "rejected_rate_limit", "rejected_budget", "rejected_policy"];

/**
 * Shared by "Request Logs" (operational view) and "Routing Decisions" (why each model was chosen).
 */
export function RequestTable({ mode }: { mode: "logs" | "routing" }) {
  const [filters, setFilters] = useState<RequestFilters>({ limit: PAGE, offset: 0, sort: "-created_at" });
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const load = useCallback((signal: AbortSignal) => api.requests(filters, signal), [filters]);
  const state = useApi(load);
  const update = (patch: Partial<RequestFilters>) => setFilters((f) => ({ ...f, ...patch, offset: patch.offset ?? 0 }));

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    update({ q: search.trim() || undefined });
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <form onSubmit={submitSearch} className="flex gap-2">
          <input
            aria-label="Search by request ID, client request ID or model"
            placeholder="Request ID, client ID or model"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64 max-w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
          />
          <Button type="submit">Search</Button>
        </form>
        <Select label="Status" value={filters.status ?? ""} onChange={(v) => update({ status: v || undefined })} options={STATUSES.map((s) => ({ value: s, label: s || "Any" }))} />
        <Select label="Tier" value={filters.tier ?? ""} onChange={(v) => update({ tier: v || undefined })} options={["", "small", "medium", "premium"].map((t) => ({ value: t, label: t || "Any" }))} />
        {mode === "routing" ? (
          <Select label="Fallback" value={filters.fallback === undefined ? "" : String(filters.fallback)} onChange={(v) => update({ fallback: v === "" ? undefined : v === "true" })} options={[{ value: "", label: "Any" }, { value: "true", label: "Used" }, { value: "false", label: "Not used" }]} />
        ) : (
          <Select label="Sort" value={filters.sort ?? "-created_at"} onChange={(v) => update({ sort: v })} options={[{ value: "-created_at", label: "Newest" }, { value: "created_at", label: "Oldest" }, { value: "-latency_ms", label: "Slowest" }, { value: "-estimated_list_cost_usd", label: "Highest est. cost" }]} />
        )}
      </div>

      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        state.data.items.length === 0 ? (
          <EmptyState title="No matching requests">Requests appear here once tenants call POST /api/v1/generate.</EmptyState>
        ) : (
          <>
            <TableWrap>
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={th}>Time</th>
                    <th className={th}>Tenant</th>
                    <th className={th}>Status</th>
                    {mode === "routing" ? (
                      <>
                        <th className={th}>Score</th>
                        <th className={th}>Tier</th>
                        <th className={th}>Reason codes</th>
                        <th className={th}>Fallback</th>
                      </>
                    ) : (
                      <>
                        <th className={th}>Request ID</th>
                        <th className={th}>Attempts</th>
                        <th className={th}>Latency</th>
                        <th className={th}>Est. list cost</th>
                      </>
                    )}
                    <th className={th}>Model</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((r) => (
                    <tr key={r.id} className="cursor-pointer hover:bg-sunken" onClick={() => setSelected(r.id)}>
                      <td className={td}>{formatDateTime(r.created_at)}</td>
                      <td className={td}>{r.tenant}</td>
                      <td className={td}><StatusBadge status={r.status} /></td>
                      {mode === "routing" ? (
                        <>
                          <td className={td}>{r.score ?? "—"}</td>
                          <td className={td}>{r.routing_tier ?? "—"}</td>
                          <td className={`${td} whitespace-normal`}><ReasonCodes codes={r.reason_codes} /></td>
                          <td className={td}>{r.fallback_used ? <Badge tone="warn">yes</Badge> : "no"}</td>
                        </>
                      ) : (
                        <>
                          <td className={`${td} font-mono text-xs`}>
                            <button type="button" className="text-accent underline" onClick={(e) => { e.stopPropagation(); setSelected(r.id); }}>
                              {r.id.slice(0, 8)}
                            </button>
                            {r.client_request_id ? <span className="ml-1 text-muted">({r.client_request_id})</span> : null}
                          </td>
                          <td className={td}>{r.attempt_count}</td>
                          <td className={td}>{formatMs(r.latency_ms)}</td>
                          <td className={td}><CostCell kind="list" amount={r.estimated_list_cost_usd} status={r.list_cost_status} /></td>
                        </>
                      )}
                      <td className={td}>{r.provider ? `${r.provider}/${r.model}` : "—"} {r.simulated ? <SimulatedBadge /> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <Pagination total={state.data.total} limit={state.data.limit} offset={state.data.offset} onChange={(offset) => setFilters((f) => ({ ...f, offset }))} />
          </>
        )
      ) : null}
      {selected ? <RequestDetailModal id={selected} onClose={() => setSelected(null)} /> : null}
    </>
  );
}

export function RequestLogs() {
  return (
    <section>
      <PageHeader title="Request Logs" description="Every gateway request with status, attempts and duration. Prompt and response content is never stored; only a hash." />
      <RequestTable mode="logs" />
    </section>
  );
}

export function RoutingDecisions() {
  return (
    <section>
      <PageHeader title="Routing Decisions" description="Why each request went to its model: complexity score, required tier, reason codes, excluded candidates and the fallback path. Select a row for the full decision record." />
      <RequestTable mode="routing" />
    </section>
  );
}
