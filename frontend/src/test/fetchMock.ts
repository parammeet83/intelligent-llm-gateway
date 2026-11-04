import { vi } from "vitest";

type Reply = { status?: number; body: unknown; headers?: Record<string, string> } | "network-error";
type Route = Reply | ((request: { method: string; url: URL; body: unknown; auth: string | null }) => Reply);

export interface FetchCall {
  method: string;
  path: string;
  search: string;
  auth: string | null;
  body: unknown;
}

/** Stubs global fetch. Keys are "METHOD /path" or "/path" (any method); query strings are ignored. */
export function mockFetch(routes: Record<string, Route>) {
  const calls: FetchCall[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(typeof input === "string" ? input : (input as Request).url);
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const auth = headers.get("Authorization");
    calls.push({ method, path: url.pathname, search: url.search, auth, body });
    const route = routes[`${method} ${url.pathname}`] ?? routes[url.pathname];
    if (route === undefined) throw new Error(`unmocked request: ${method} ${url.pathname}`);
    const reply = typeof route === "function" ? route({ method, url, body, auth }) : route;
    if (reply === "network-error") throw new TypeError("Failed to fetch");
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json", ...reply.headers },
    });
  });
  return Object.assign(spy, { calls });
}

export const HEALTH_SIMULATED = {
  status: "ok",
  version: "0.1.0",
  environment: "development",
  providers: ["mock"],
  simulated_only: true,
};

export const READY = { status: "ready", checks: { database: "ok", migrations: "ok" } };

const stats = {
  requests: 3, succeeded: 2, failed: 1, success_rate: 0.6667, input_tokens: 30, output_tokens: 20, total_tokens: 50,
  actual_charge_usd: "0E-8", actual_charge_known_requests: 2, actual_charge_unknown_requests: 1, free_tier_requests: 2,
  estimated_list_cost_usd: "0.00012000", estimated_list_cost_known_requests: 2, estimated_list_cost_unknown_requests: 1,
  cost_per_successful_request_usd: "0.00006000", latency_p50_ms: 420, latency_p95_ms: 1900,
};

export const USAGE = {
  window: { since: "2026-11-01T00:00:00", until: "2026-11-04T00:00:00", bucket: "day" },
  truncated: false,
  totals: { ...stats, rejected_rate_limit: 1, rejected_budget: 0, rejected_policy: 0, pending: 0, fallback_rate: 0.3333, rate_limit_rejection_rate: 0.25, simulated_requests: 0 },
  by_status: { succeeded: 2, failed: 1 },
  by_provider: [{ ...stats, provider: "groq" }],
  by_model: [{ ...stats, model: "groq/openai/gpt-oss-20b" }],
  by_tier: [{ ...stats, tier: "medium", share: 1 }],
  by_tenant: [{ ...stats, tenant: "acme-saas" }],
  timeseries: [{ ...stats, bucket: "2026-11-03" }],
  latency_histogram: [{ bucket_ms: "<250", count: 0 }, { bucket_ms: "250-500", count: 1 }],
};

export const EMPTY_USAGE = {
  ...USAGE,
  totals: { ...USAGE.totals, requests: 0, succeeded: 0, failed: 0 },
  by_provider: [], by_model: [], by_tier: [], by_tenant: [], timeseries: [],
};

export const REQUEST = {
  id: "11111111-2222-3333-4444-555555555555", tenant: "acme-saas", client_request_id: "order-42", status: "succeeded",
  error_code: null, task_type: "classification", prompt_version: null, routing_tier: "medium", policy_version: "rw-2026.11-v1",
  provider: "groq", model: "openai/gpt-oss-20b", attempt_count: 2, fallback_used: true, simulated: false,
  input_tokens: 12, output_tokens: 5, latency_ms: 850, actual_charge_usd: "0E-8", cost_status: "free_tier",
  estimated_list_cost_usd: "0.00000240", list_cost_status: "estimated", reason_codes: ["LOW_COMPLEXITY", "TIER_ESCALATED"],
  score: 5.03, created_at: "2026-11-03T10:00:00+00:00", completed_at: "2026-11-03T10:00:01+00:00",
};
