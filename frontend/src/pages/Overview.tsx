import { useCallback, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Card, Kpi, PageHeader, Select } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { DAY_OPTIONS } from "../lib/options";
import { formatActualTotal, formatMs, formatNumber, formatPercent, formatUsd } from "../lib/format";

const CHECK_STYLES: Record<string, string> = { ok: "text-ok", pending: "text-warn", unavailable: "text-danger", unknown: "text-muted" };

export function Overview() {
  const [days, setDays] = useState("7");
  const usage = useApi(useCallback((s: AbortSignal) => api.usage({ days: Number(days), bucket: days === "1" ? "hour" : "day" }, s), [days]));
  const health = useApi(api.health);
  const ready = useApi(api.ready);

  return (
    <section>
      <PageHeader
        title="Overview"
        description="Request volume, reliability, latency and cost from the gateway's request log."
        actions={<Select label="Window" value={days} onChange={setDays} options={DAY_OPTIONS} />}
      />

      {usage.status === "loading" ? <LoadingState /> : null}
      {usage.status === "error" ? <ErrorState error={usage.error} onRetry={usage.reload} /> : null}
      {usage.status === "success" ? (
        usage.data.totals.requests === 0 ? (
          <EmptyState title="No requests in this window">Send a request to POST /api/v1/generate with a tenant API key.</EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Kpi label="Requests" value={formatNumber(usage.data.totals.requests)} hint={`${formatNumber(usage.data.totals.simulated_requests)} simulated`} />
              <Kpi label="Success rate" value={formatPercent(usage.data.totals.success_rate)} hint={`${usage.data.totals.failed} failed`} />
              <Kpi label="Latency p50 / p95" value={`${formatMs(usage.data.totals.latency_p50_ms)} / ${formatMs(usage.data.totals.latency_p95_ms)}`} hint="Successful requests, end to end" />
              <Kpi label="Fallback rate" value={formatPercent(usage.data.totals.fallback_rate)} hint={`Rate-limit rejections ${formatPercent(usage.data.totals.rate_limit_rejection_rate)}`} />
              <Kpi label="Est. list-price cost" value={formatUsd(usage.data.totals.estimated_list_cost_usd)} hint="Shadow cost at published prices; not money spent" />
              <Kpi label="Actual charges" value={formatActualTotal(usage.data.totals)} hint={`${usage.data.totals.free_tier_requests} free-tier · ${usage.data.totals.actual_charge_unknown_requests} unknown`} />
              <Kpi label="Tokens" value={formatNumber(usage.data.totals.total_tokens)} hint={`${formatNumber(usage.data.totals.input_tokens)} in · ${formatNumber(usage.data.totals.output_tokens)} out`} />
              <Kpi label="Rejected" value={formatNumber(usage.data.totals.rejected_budget + usage.data.totals.rejected_rate_limit + usage.data.totals.rejected_policy)} hint={`budget ${usage.data.totals.rejected_budget} · rate ${usage.data.totals.rejected_rate_limit} · policy ${usage.data.totals.rejected_policy}`} />
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <Card title="Requests over time" className="lg:col-span-2">
                <div className="h-64" role="img" aria-label="Requests over time, succeeded and failed">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={usage.data.timeseries}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} label={{ value: "requests", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="succeeded" stackId="a" fill="var(--color-ok)" name="Succeeded" />
                      <Bar dataKey="failed" stackId="a" fill="var(--color-danger)" name="Failed" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card title="Traffic by routing tier">
                {usage.data.by_tier.length ? (
                  <ul className="space-y-2 text-sm">
                    {usage.data.by_tier.map((t) => (
                      <li key={t.tier}>
                        <div className="flex justify-between"><span className="capitalize">{t.tier}</span><span>{formatPercent(t.share)} · {t.requests}</span></div>
                        <div className="mt-1 h-2 rounded bg-sunken"><div className="h-2 rounded bg-accent" style={{ width: `${(t.share ?? 0) * 100}%` }} /></div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">No routed requests yet.</p>
                )}
              </Card>
            </div>
          </>
        )
      ) : null}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card title="Gateway">
          {health.status === "loading" ? <LoadingState /> : null}
          {health.status === "error" ? <ErrorState error={health.error} onRetry={health.reload} /> : null}
          {health.status === "success" ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted">Status</dt><dd className="text-ok">{health.data.status}</dd>
              <dt className="text-muted">Version</dt><dd className="font-mono">{health.data.version}</dd>
              <dt className="text-muted">Environment</dt><dd>{health.data.environment}</dd>
              <dt className="text-muted">Providers</dt><dd>{health.data.providers.join(", ")}</dd>
              <dt className="text-muted">Responses</dt><dd>{health.data.simulated_only ? "Simulated (mock only)" : "Real providers enabled"}</dd>
            </dl>
          ) : null}
        </Card>
        <Card title="Readiness">
          {ready.status === "loading" ? <LoadingState /> : null}
          {ready.status === "error" ? <ErrorState error={ready.error} onRetry={ready.reload} /> : null}
          {ready.status === "success" ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted">Overall</dt>
              <dd className={ready.data.status === "ready" ? "text-ok" : "text-danger"}>{ready.data.status}</dd>
              {Object.entries(ready.data.checks).map(([name, value]) => (
                <div key={name} className="contents">
                  <dt className="capitalize text-muted">{name}</dt>
                  <dd className={CHECK_STYLES[value] ?? "text-muted"}>{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </Card>
      </div>
    </section>
  );
}
