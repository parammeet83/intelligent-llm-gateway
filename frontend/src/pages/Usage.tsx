import { useCallback, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { GroupStats } from "../api/types";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, Kpi, PageHeader, Select, TableWrap, td, th } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatActualTotal, formatMs, formatNumber, formatPercent, formatUsd } from "../lib/format";
import { DAY_OPTIONS } from "../lib/options";

function GroupTable({ rows, label }: { rows: (GroupStats & { name: string })[]; label: string }) {
  if (!rows.length) return <p className="text-sm text-muted">No data.</p>;
  return (
    <TableWrap>
      <table className="w-full">
        <thead>
          <tr>
            <th className={th}>{label}</th><th className={th}>Requests</th><th className={th}>Success</th><th className={th}>Tokens</th>
            <th className={th}>Est. list cost</th><th className={th}>Actual charges</th><th className={th}>p95</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td className={`${td} font-mono text-xs`}>{r.name}</td>
              <td className={td}>{formatNumber(r.requests)}</td>
              <td className={td}>{formatPercent(r.success_rate)}</td>
              <td className={td}>{formatNumber(r.total_tokens)}</td>
              <td className={td}>{formatUsd(r.estimated_list_cost_usd)}{r.estimated_list_cost_unknown_requests ? <span className="text-xs text-muted"> (+{r.estimated_list_cost_unknown_requests} unpriced)</span> : null}</td>
              <td className={td}>{formatActualTotal(r)}<span className="text-xs text-muted"> ({r.free_tier_requests} free-tier, {r.actual_charge_unknown_requests} unknown)</span></td>
              <td className={td}>{formatMs(r.latency_p95_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export function Usage() {
  const [days, setDays] = useState("7");
  const tenants = useApi(api.tenants);
  const [tenant, setTenant] = useState("");
  const load = useCallback(
    (signal: AbortSignal) => api.usage({ days: Number(days), bucket: days === "1" ? "hour" : "day", tenant: tenant || undefined }, signal),
    [days, tenant],
  );
  const state = useApi(load);
  const tenantOptions = [{ value: "", label: "All tenants" }, ...(tenants.status === "success" ? tenants.data.items.map((t) => ({ value: t.slug, label: t.slug })) : [])];

  return (
    <section>
      <PageHeader
        title="Usage & Cost"
        description="Actual provider charges and estimated list-price (shadow) cost, shown side by side and never added together."
        actions={
          <>
            <Select label="Tenant" value={tenant} onChange={setTenant} options={tenantOptions} />
            <Select label="Window" value={days} onChange={setDays} options={DAY_OPTIONS} />
          </>
        }
      />
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        state.data.totals.requests === 0 ? (
          <EmptyState title="No usage in this window" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Kpi label="Actual charges" value={formatActualTotal(state.data.totals)} hint={`${state.data.totals.actual_charge_known_requests} known · ${state.data.totals.actual_charge_unknown_requests} unknown`} />
              <Kpi label="Free-tier requests" value={formatNumber(state.data.totals.free_tier_requests)} hint="Billed $0 under free-plan terms" />
              <Kpi label="Est. list-price cost" value={formatUsd(state.data.totals.estimated_list_cost_usd)} hint={`${state.data.totals.estimated_list_cost_unknown_requests} request(s) unpriced`} />
              <Kpi label="Est. cost per success" value={formatUsd(state.data.totals.cost_per_successful_request_usd)} hint="Shadow cost; not money spent" />
            </div>
            {state.data.truncated ? <p className="mt-2 text-xs text-warn">Showing the first 50,000 requests of this window.</p> : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card title="Estimated list-price cost over time (USD)">
                <div className="h-60" role="img" aria-label="Estimated list-price cost over time">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={state.data.timeseries.map((t) => ({ bucket: t.bucket, cost: Number(t.estimated_list_cost_usd) }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${v.toPrecision(2)}`} label={{ value: "USD (est.)", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip formatter={(v) => formatUsd(String(v))} />
                      <Line type="monotone" dataKey="cost" stroke="var(--color-accent)" name="Est. list cost" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card title="Token usage over time">
                <div className="h-60" role="img" aria-label="Input and output tokens over time">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={state.data.timeseries}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} label={{ value: "tokens", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="input_tokens" stackId="t" fill="var(--color-accent)" name="Input" />
                      <Bar dataKey="output_tokens" stackId="t" fill="var(--color-ok)" name="Output" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card title="Latency distribution (successful requests)">
                <div className="h-56" role="img" aria-label="Latency histogram">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={state.data.latency_histogram}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="bucket_ms" tick={{ fontSize: 10 }} label={{ value: "ms", position: "insideBottomRight", fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} label={{ value: "requests", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="count" fill="var(--color-accent)" name="Requests" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-sm text-muted">p50 {formatMs(state.data.totals.latency_p50_ms)} · p95 {formatMs(state.data.totals.latency_p95_ms)}</p>
              </Card>
              <Card title="By routing tier">
                <GroupTable label="Tier" rows={state.data.by_tier.map((r) => ({ ...r, name: r.tier }))} />
              </Card>
            </div>
            <div className="mt-4 space-y-4">
              <Card title="By provider"><GroupTable label="Provider" rows={state.data.by_provider.map((r) => ({ ...r, name: r.provider }))} /></Card>
              <Card title="By model"><GroupTable label="Model" rows={state.data.by_model.map((r) => ({ ...r, name: r.model }))} /></Card>
              {state.data.by_tenant ? <Card title="By tenant"><GroupTable label="Tenant" rows={state.data.by_tenant.map((r) => ({ ...r, name: r.tenant }))} /></Card> : null}
            </div>
          </>
        )
      ) : null}
    </section>
  );
}
