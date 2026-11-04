import { useMemo, useState } from "react";
import { api } from "../api/client";
import { ErrorState, LoadingState } from "../components/States";
import { Badge, Card, PageHeader, Select, SimulatedBadge, TableWrap, td, th } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatMs, formatNumber } from "../lib/format";

export function Providers() {
  const providers = useApi(api.providers);
  const models = useApi(api.models);
  const [provider, setProvider] = useState("");
  const [tier, setTier] = useState("");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    if (models.status !== "success") return [];
    const term = search.trim().toLowerCase();
    return models.data.models.filter(
      (m) => (!provider || m.provider === provider) && (!tier || m.tier === tier) && (!term || m.model_id.toLowerCase().includes(term) || m.display_name.toLowerCase().includes(term)),
    );
  }, [models, provider, tier, search]);

  return (
    <section>
      <PageHeader title="Providers & Models" description="Enabled providers, their billing basis and quota state, and the model registry with list prices (with sources) and live health." />

      {providers.status === "loading" ? <LoadingState /> : null}
      {providers.status === "error" ? <ErrorState error={providers.error} onRetry={providers.reload} /> : null}
      {providers.status === "success" ? (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {providers.data.providers.map((p) => (
            <Card key={p.name}>
              <div className="flex items-center justify-between">
                <p className="font-semibold">{p.name}</p>
                {p.simulated ? <SimulatedBadge /> : <Badge tone="ok">live</Badge>}
              </div>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-muted">Charge basis</dt><dd>{p.charge_basis}</dd>
                <dt className="text-muted">Same-model retries</dt><dd>{p.max_retries}</dd>
                <dt className="text-muted">Quota</dt><dd className={p.quota_available ? "text-ok" : "text-danger"}>{p.quota_available ? "available" : "exhausted"}</dd>
                <dt className="text-muted">Model list</dt><dd>{p.simulated ? "n/a" : p.catalog_verified ? "verified" : "unverified"}</dd>
              </dl>
            </Card>
          ))}
        </div>
      ) : null}

      <Card title="Model registry">
        <div className="mb-3 flex flex-wrap gap-3">
          <input aria-label="Search models" placeholder="Search models" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56 max-w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm" />
          <Select label="Provider" value={provider} onChange={setProvider} options={["", "groq", "openrouter", "ollama", "mock"].map((v) => ({ value: v, label: v || "Any" }))} />
          <Select label="Tier" value={tier} onChange={setTier} options={["", "small", "medium", "premium"].map((v) => ({ value: v, label: v || "Any" }))} />
        </div>
        {models.status === "loading" ? <LoadingState /> : null}
        {models.status === "error" ? <ErrorState error={models.error} onRetry={models.reload} /> : null}
        {models.status === "success" ? (
          <TableWrap>
            <table className="w-full">
              <thead>
                <tr>
                  <th className={th}>Model</th><th className={th}>Tier</th><th className={th}>Status</th><th className={th}>List price in / out (per M tokens)</th>
                  <th className={th}>Context</th><th className={th}>Capabilities</th><th className={th}>Health</th><th className={th}>Observed p95</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={`${m.provider}/${m.model_id}`}>
                    <td className={td}><span className="font-medium">{m.display_name}</span><br /><span className="font-mono text-xs text-muted">{m.provider}/{m.model_id}</span></td>
                    <td className={td}>{m.tier}</td>
                    <td className={td}>
                      {!m.provider_enabled ? <Badge>provider off</Badge> : !m.enabled_in_registry ? <Badge>disabled</Badge> : <Badge tone="ok">enabled</Badge>}{" "}
                      {m.preview ? <Badge tone="warn">preview</Badge> : null} {m.simulated ? <SimulatedBadge /> : null}
                    </td>
                    <td className={td}>
                      {m.list_price ? (
                        <a href={m.list_price.source_url.startsWith("http") ? m.list_price.source_url : undefined} target="_blank" rel="noreferrer" className="underline decoration-dotted" title={`Effective ${m.list_price.effective_date}`}>
                          ${m.list_price.input_usd_per_mtok} / ${m.list_price.output_usd_per_mtok}
                        </a>
                      ) : (
                        <span className="text-muted">no published price</span>
                      )}
                    </td>
                    <td className={td}>{formatNumber(m.context_window)}</td>
                    <td className={`${td} whitespace-normal`}>{m.capabilities.join(", ") || "—"}</td>
                    <td className={td}>
                      {m.runtime.exclusion ? <Badge tone="danger">{m.runtime.exclusion}</Badge> : <Badge tone={m.runtime.circuit === "closed" ? "ok" : "warn"}>{m.runtime.circuit}</Badge>}
                      {m.runtime.listed_by_provider === false ? <Badge tone="danger">not listed</Badge> : null}
                    </td>
                    <td className={td}>{m.runtime.observed_p95_ms !== null ? formatMs(m.runtime.observed_p95_ms) : <span className="text-muted">{m.runtime.latency_samples} samples</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        ) : null}
        <p className="mt-3 text-xs text-muted">List prices are published pay-as-you-go prices used only for shadow-cost estimates; free-tier calls are billed $0. Latency is shown only after 5 measured calls.</p>
      </Card>
    </section>
  );
}
