import { useCallback, useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import type { KeyView, TenantView } from "../api/types";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Badge, Button, Card, Modal, PageHeader, TableWrap, td, th } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatUsd } from "../lib/format";

function BudgetBar({ limit, spent, reserved }: { limit: string; spent: string; reserved: string }) {
  const l = Number(limit);
  const pct = (v: string) => (l > 0 ? Math.min(100, (Number(v) / l) * 100) : 100);
  return (
    <div className="mt-1 h-2 w-full overflow-hidden rounded bg-sunken" aria-hidden="true">
      <div className="flex h-2">
        <div className="bg-accent" style={{ width: `${pct(spent)}%` }} />
        <div className="bg-warn" style={{ width: `${pct(reserved)}%` }} />
      </div>
    </div>
  );
}

/** Shows a newly issued key exactly once. */
function NewKeyModal({ secret, onClose }: { secret: string; onClose: () => void }) {
  return (
    <Modal title="New API key" onClose={onClose}>
      <p className="text-sm text-warn">Copy this key now. It isn't stored and can't be shown again.</p>
      <pre className="mt-3 overflow-x-auto rounded bg-sunken p-3 font-mono text-sm" data-testid="new-key">{secret}</pre>
      <div className="mt-3"><Button onClick={() => void navigator.clipboard?.writeText(secret)}>Copy</Button></div>
    </Modal>
  );
}

function KeysPanel({ tenant }: { tenant: TenantView }) {
  const load = useCallback((signal: AbortSignal) => api.keys(tenant.slug, signal), [tenant.slug]);
  const state = useApi(load);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<string | null>) {
    setError(null);
    try {
      const plaintext = await action();
      if (plaintext) setSecret(plaintext);
      state.reload();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Action failed.");
    }
  }

  return (
    <div className="mt-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">API keys</h3>
        <Button onClick={() => void act(async () => (await api.createKey(tenant.slug, "dashboard")).api_key)}>Create key</Button>
      </div>
      {error ? <p role="alert" className="mb-2 text-sm text-danger">{error}</p> : null}
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        state.data.items.length === 0 ? (
          <p className="text-sm text-muted">No keys.</p>
        ) : (
          <TableWrap>
            <table className="w-full">
              <thead><tr><th className={th}>Prefix</th><th className={th}>Name</th><th className={th}>State</th><th className={th}>Last used</th><th className={th}>Actions</th></tr></thead>
              <tbody>
                {state.data.items.map((k: KeyView) => (
                  <tr key={k.id}>
                    <td className={`${td} font-mono`}>{k.prefix}</td>
                    <td className={td}>{k.name}</td>
                    <td className={td}>{k.active ? <Badge tone="ok">active</Badge> : <Badge>{k.revoked_at ? "revoked" : "expired"}</Badge>}{k.active && k.expires_at ? <Badge tone="warn">expires {formatDateTime(k.expires_at)}</Badge> : null}</td>
                    <td className={td}>{formatDateTime(k.last_used_at)}</td>
                    <td className={td}>
                      {k.active ? (
                        <span className="flex gap-2">
                          <Button onClick={() => void act(async () => (await api.rotateKey(k.id, 0)).new_key.api_key)}>Rotate</Button>
                          <Button variant="danger" onClick={() => void act(async () => { await api.revokeKey(k.id); return null; })}>Revoke</Button>
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )
      ) : null}
      {secret ? <NewKeyModal secret={secret} onClose={() => setSecret(null)} /> : null}
    </div>
  );
}

function TenantCard({ tenant, onChanged }: { tenant: TenantView; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  async function toggleStatus() {
    await api.updateTenant(tenant.slug, { status: tenant.status === "active" ? "suspended" : "active" });
    onChanged();
  }
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{tenant.name}</p>
          <p className="font-mono text-xs text-muted">{tenant.slug}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={tenant.status === "active" ? "ok" : "danger"}>{tenant.status}</Badge>
          <Button onClick={() => void toggleStatus()}>{tenant.status === "active" ? "Suspend" : "Activate"}</Button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">Rate limit {tenant.rate_limit_rpm} req/min · {tenant.unrevoked_keys ?? 0} unrevoked key(s)</p>
      {tenant.budgets.length ? (
        <ul className="mt-3 space-y-3 text-sm">
          {tenant.budgets.map((b) => (
            <li key={b.period}>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="capitalize">{b.period} budget (from {b.period_start})</span>
                <span className="tabular-nums">{formatUsd(b.spent_usd)} spent · {formatUsd(b.reserved_usd)} reserved · {formatUsd(b.limit_usd)} limit</span>
              </div>
              <BudgetBar limit={b.limit_usd} spent={b.spent_usd} reserved={b.reserved_usd} />
            </li>
          ))}
          <li className="text-xs text-muted">Budgets limit estimated list-price cost (a shadow budget), not actual charges.</li>
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted">No budget configured (unlimited; unpriced models allowed).</p>
      )}
      <div className="mt-3"><Button onClick={() => setOpen((o) => !o)}>{open ? "Hide keys" : "Manage keys"}</Button></div>
      {open ? <KeysPanel tenant={tenant} /> : null}
    </Card>
  );
}

function CreateTenant({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState({ slug: "", name: "", rate_limit_rpm: "60", daily_budget_usd: "", monthly_budget_usd: "" });
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createTenant({
        slug: form.slug,
        name: form.name,
        rate_limit_rpm: Number(form.rate_limit_rpm),
        daily_budget_usd: form.daily_budget_usd || null,
        monthly_budget_usd: form.monthly_budget_usd || null,
      });
      setForm({ slug: "", name: "", rate_limit_rpm: "60", daily_budget_usd: "", monthly_budget_usd: "" });
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not create tenant.");
    }
  }
  const field = (key: keyof typeof form, label: string, extra: Record<string, string> = {}) => (
    <label className="text-sm">
      <span className="text-muted">{label}</span>
      <input aria-label={label} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} className="mt-1 w-full rounded-md border border-line bg-canvas px-2 py-1.5" {...extra} />
    </label>
  );
  return (
    <Card title="Create tenant">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {field("slug", "Slug", { required: "true", pattern: "[a-z0-9][a-z0-9-]{1,62}" })}
        {field("name", "Name", { required: "true" })}
        {field("rate_limit_rpm", "Rate limit (req/min)", { type: "number", min: "1" })}
        {field("daily_budget_usd", "Daily budget (USD, est.)", { inputMode: "decimal" })}
        {field("monthly_budget_usd", "Monthly budget (USD, est.)", { inputMode: "decimal" })}
        <div className="sm:col-span-2 lg:col-span-5"><Button type="submit" variant="primary">Create</Button></div>
      </form>
      {error ? <p role="alert" className="mt-2 text-sm text-danger">{error}</p> : null}
    </Card>
  );
}

export function Tenants() {
  const state = useApi(api.tenants);
  return (
    <section>
      <PageHeader title="Tenants & Budgets" description="Tenant status, rate limits, shadow budgets (spent and reserved), and API keys. New keys are shown once and never again." />
      <CreateTenant onCreated={state.reload} />
      <div className="mt-4">
        {state.status === "loading" ? <LoadingState /> : null}
        {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
        {state.status === "success" ? (
          state.data.items.length === 0 ? (
            <EmptyState title="No tenants yet">Create one above or run `python -m app.cli create-tenant`.</EmptyState>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {state.data.items.map((t) => <TenantCard key={t.id} tenant={t} onChanged={state.reload} />)}
            </div>
          )
        ) : null}
      </div>
    </section>
  );
}
