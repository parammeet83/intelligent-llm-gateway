import { api } from "../api/client";
import { ErrorState, LoadingState } from "../components/States";
import { Badge, Card, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";

function Pairs({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-muted">{key}</dt>
          <dd className="break-all font-mono text-xs">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Settings() {
  const state = useApi(api.config);
  return (
    <section>
      <PageHeader
        title="Settings"
        description="The active routing policy and non-secret runtime settings. Policy changes are made in backend/config/routing_policy.yaml with a version bump, so every decision stays attributable to a versioned policy; they are deliberately not editable here."
      />
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "error" ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
      {state.status === "success" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={`Routing policy ${state.data.policy.version}`}>
            <Pairs data={state.data.policy} />
          </Card>
          <div className="space-y-4">
            <Card title="Runtime">
              <p className="mb-2 text-sm">
                Environment <Badge>{state.data.environment}</Badge> · Providers {state.data.providers.join(", ")}{" "}
                {state.data.simulated_only ? <Badge tone="warn">simulated only</Badge> : <Badge tone="ok">real providers</Badge>}
              </p>
              <Pairs data={state.data.settings} />
            </Card>
            <Card title="Secrets">
              <p className="text-sm text-muted">Provider keys, the admin token and the API-key pepper are server-side secrets. They are never sent to the browser and are not shown here.</p>
            </Card>
          </div>
        </div>
      ) : null}
    </section>
  );
}
