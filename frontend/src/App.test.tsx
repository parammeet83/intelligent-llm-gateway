import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { session } from "./api/client";
import { App } from "./App";
import { NAV_ITEMS } from "./pages/nav";
import { EMPTY_USAGE, HEALTH_SIMULATED, READY, REQUEST, USAGE, mockFetch } from "./test/fetchMock";

const SESSION = "rws_test.session";
const ADMIN_TOKEN = "super-secret-admin-token";

function renderAt(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const base = { "/api/v1/health": { body: HEALTH_SIMULATED }, "/api/v1/ready": { body: READY } };

describe("shell and authentication", () => {
  it("links to all eight dashboard pages", () => {
    mockFetch(base);
    renderAt();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link")).toHaveLength(8);
    for (const item of NAV_ITEMS) expect(within(nav).getByRole("link", { name: item.label })).toBeInTheDocument();
  });

  it("shows the DEMO banner only while every provider is simulated", async () => {
    mockFetch(base);
    const { unmount } = renderAt("/providers-missing");
    expect(await screen.findByText(/DEMO — simulated responses/)).toBeInTheDocument();
    unmount();
    mockFetch({ ...base, "/api/v1/health": { body: { ...HEALTH_SIMULATED, providers: ["groq"], simulated_only: false } } });
    renderAt("/providers-missing");
    await screen.findByText("Page not found");
    await waitFor(() => expect(screen.queryByText(/DEMO — simulated responses/)).not.toBeInTheDocument());
  });

  it("requires sign-in for admin pages and never stores the admin token", async () => {
    const fetchSpy = mockFetch({
      ...base,
      "POST /api/v1/admin/session": ({ body }) =>
        (body as { token: string }).token === ADMIN_TOKEN
          ? { body: { session_token: SESSION, expires_at: 9999999999 } }
          : { status: 401, body: { error: { code: "UNAUTHORIZED", message: "Invalid or missing credentials.", request_id: null, details: {} } } },
      "/api/v1/admin/usage": { body: USAGE },
    });
    renderAt();
    expect(await screen.findByRole("heading", { name: "Administrator sign-in" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Admin token"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or missing credentials.");

    await userEvent.clear(screen.getByLabelText("Admin token"));
    await userEvent.type(screen.getByLabelText("Admin token"), ADMIN_TOKEN);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();

    expect(sessionStorage.getItem("rw_admin_session")).toBe(SESSION);
    expect(JSON.stringify(sessionStorage)).not.toContain(ADMIN_TOKEN);
    // The heading renders before the page's data request fires, so wait for the request itself.
    await waitFor(() => expect(fetchSpy.calls.some((c) => c.path === "/api/v1/admin/usage")).toBe(true));
    const usageCall = fetchSpy.calls.find((c) => c.path === "/api/v1/admin/usage");
    expect(usageCall?.auth).toBe(`Bearer ${SESSION}`);
  });

  it("returns to sign-in when the session is rejected", async () => {
    session.set(SESSION);
    mockFetch({
      ...base,
      "/api/v1/admin/usage": { status: 401, body: { error: { code: "UNAUTHORIZED", message: "Invalid or missing credentials.", request_id: null, details: {} } } },
    });
    renderAt();
    expect(await screen.findByRole("heading", { name: "Administrator sign-in" })).toBeInTheDocument();
    expect(sessionStorage.getItem("rw_admin_session")).toBeNull();
  });

  it("signs out", async () => {
    session.set(SESSION);
    mockFetch({ ...base, "/api/v1/admin/usage": { body: USAGE } });
    renderAt();
    await screen.findByRole("heading", { name: "Overview" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Administrator sign-in" })).toBeInTheDocument();
  });

  it("toggles the mobile menu", async () => {
    mockFetch(base);
    renderAt("/x");
    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close" })).toHaveAttribute("aria-expanded", "true");
  });
});

describe("overview", () => {
  it("renders live metrics and keeps estimates distinct from actual charges", async () => {
    session.set(SESSION);
    mockFetch({ ...base, "/api/v1/admin/usage": { body: USAGE } });
    renderAt();
    expect(await screen.findByText("Est. list-price cost")).toBeInTheDocument();
    expect(screen.getByText("Actual charges")).toBeInTheDocument();
    expect(screen.getByText(/Shadow cost at published prices; not money spent/)).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText("420 ms / 1.90 s")).toBeInTheDocument();
  });

  it("shows an empty state with no traffic", async () => {
    session.set(SESSION);
    mockFetch({ ...base, "/api/v1/admin/usage": { body: EMPTY_USAGE } });
    renderAt();
    expect(await screen.findByText("No requests in this window")).toBeInTheDocument();
  });

  it("shows an error state with retry when the API fails", async () => {
    session.set(SESSION);
    const spy = mockFetch({ ...base, "/api/v1/admin/usage": "network-error" });
    renderAt();
    const alert = await screen.findByText("Could not reach the RouteWise API.");
    const before = spy.calls.length;
    await userEvent.click(within(alert.closest("[role=alert]") as HTMLElement).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(spy.calls.length).toBeGreaterThan(before));
  });
});

describe("request logs and routing decisions", () => {
  const detail = {
    ...REQUEST,
    prompt_sha256: "ab".repeat(32),
    input_chars: 40,
    decision: {
      explanation: "Complexity score 5.03/100 -> small tier; required tier small.",
      reason_codes: ["LOW_COMPLEXITY", "TIER_ESCALATED"],
      score: 5.03,
      contributions: [{ feature: "task_type_prior", points: 5, detail: "classification" }],
      candidates: [
        { provider: "groq", model_id: "openai/gpt-oss-20b", tier: "medium", eligible: true, exclusions: [], worst_case_list_cost_usd: "0.0001", observed_p95_ms: null, simulated: false },
        { provider: "mock", model_id: "mock-small", tier: "small", eligible: false, exclusions: ["SIMULATED_EXCLUDED"], worst_case_list_cost_usd: "0.00001", observed_p95_ms: null, simulated: true },
      ],
      execution: { outcome: "SUCCEEDED", skipped: [] },
    },
    attempts: [
      { attempt: 1, provider: "groq", model: "openai/gpt-oss-20b", reason_code: "PRIMARY", status: "timeout", error_code: "TIMEOUT", http_status: null, retry_after_s: null, input_tokens: null, output_tokens: null, latency_ms: 30000, actual_charge_usd: "0E-8", cost_status: "free_tier", estimated_list_cost_usd: null, list_cost_status: "unavailable", simulated: false, started_at: "2026-11-03T10:00:00" },
      { attempt: 2, provider: "groq", model: "openai/gpt-oss-120b", reason_code: "FALLBACK_AFTER_TIMEOUT", status: "succeeded", error_code: null, http_status: null, retry_after_s: null, input_tokens: 12, output_tokens: 5, latency_ms: 800, actual_charge_usd: "0E-8", cost_status: "free_tier", estimated_list_cost_usd: "0.00000240", list_cost_status: "estimated", simulated: false, started_at: "2026-11-03T10:00:30" },
    ],
  };

  it("lists requests, filters, paginates and opens the full decision", async () => {
    session.set(SESSION);
    const spy = mockFetch({
      ...base,
      "/api/v1/admin/requests": { body: { total: 30, limit: 25, offset: 0, items: [REQUEST] } },
      [`/api/v1/admin/requests/${REQUEST.id}`]: { body: detail },
    });
    renderAt("/routing");
    expect(await screen.findByText("TIER_ESCALATED")).toBeInTheDocument();
    expect(screen.getByText("1–25 of 30")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Tier"), "medium");
    await waitFor(() => expect(spy.calls.some((c) => c.search.includes("tier=medium"))).toBe(true));
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(spy.calls.some((c) => c.search.includes("offset=25"))).toBe(true));

    await userEvent.click((await screen.findAllByText("acme-saas"))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Request detail" });
    expect(within(dialog).getByText("FALLBACK_AFTER_TIMEOUT")).toBeInTheDocument();
    expect(within(dialog).getByText("SIMULATED_EXCLUDED")).toBeInTheDocument();
    expect(within(dialog).getByText(/content is not stored/)).toBeInTheDocument();
  });

  it("searches by request ID on the logs page", async () => {
    session.set(SESSION);
    const spy = mockFetch({ ...base, "/api/v1/admin/requests": { body: { total: 0, limit: 25, offset: 0, items: [] } } });
    renderAt("/logs");
    expect(await screen.findByText("No matching requests")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Search by request ID/), "order-42");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(spy.calls.some((c) => c.search.includes("q=order-42"))).toBe(true));
  });
});

describe("providers, tenants, usage, evaluation, settings", () => {
  it("shows providers and the model registry without signing in", async () => {
    mockFetch({
      ...base,
      "/api/v1/providers": { body: { providers: [{ name: "mock", simulated: true, charge_basis: "unavailable", max_retries: 1, quota_available: true, catalog_verified: false }] } },
      "/api/v1/models": {
        body: {
          policy_version: "rw-2026.11-v1",
          models: [
            { provider: "groq", model_id: "openai/gpt-oss-20b", display_name: "GPT-OSS 20B (Groq)", tier: "medium", billing: "free", capabilities: ["json_mode"], context_window: 131072, max_output_tokens: 65536, enabled_in_registry: true, provider_enabled: false, preview: false, simulated: false, verified_on: "2026-11-03", source_url: "https://console.groq.com/docs/models", list_price: { input_usd_per_mtok: "0.075", output_usd_per_mtok: "0.30", effective_date: "2026-11-03", source_url: "https://console.groq.com/docs/models", simulated: false }, runtime: { listed_by_provider: null, circuit: "closed", exclusion: null, latency_samples: 0, observed_p95_ms: null } },
            { provider: "groq", model_id: "llama-3.1-8b-instant", display_name: "Llama 3.1 8B", tier: "small", billing: "free", capabilities: [], context_window: 131072, max_output_tokens: 131072, enabled_in_registry: true, provider_enabled: false, preview: false, simulated: false, verified_on: "2026-11-03", source_url: null, list_price: null, runtime: { listed_by_provider: null, circuit: "closed", exclusion: null, latency_samples: 0, observed_p95_ms: null } },
          ],
        },
      },
    });
    renderAt("/providers");
    expect(await screen.findByText("GPT-OSS 20B (Groq)")).toBeInTheDocument();
    expect(screen.getByText("$0.075 / $0.30")).toBeInTheDocument();
    expect(screen.getByText("no published price")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Tier"), "small");
    expect(screen.queryByText("GPT-OSS 20B (Groq)")).not.toBeInTheDocument();
  });

  it("shows tenant budgets and reveals a new key exactly once", async () => {
    session.set(SESSION);
    const tenant = {
      id: "t1", slug: "acme-saas", name: "Acme", status: "active", rate_limit_rpm: 60, daily_budget_usd: "1.00", monthly_budget_usd: null,
      budget_basis: "estimated list-price cost (shadow budget), not actual charges", created_at: null, unrevoked_keys: 1,
      budgets: [{ period: "daily", period_start: "2026-11-04", limit_usd: "1.00", spent_usd: "0.25", reserved_usd: "0.05", remaining_usd: "0.70" }],
    };
    mockFetch({
      ...base,
      "/api/v1/admin/tenants": { body: { items: [tenant] } },
      "GET /api/v1/admin/tenants/acme-saas/keys": { body: { tenant: "acme-saas", items: [{ id: "k1", name: "default", prefix: "rw_abcdefgh", created_at: null, last_used_at: null, revoked_at: null, expires_at: null, active: true }] } },
      "POST /api/v1/admin/tenants/acme-saas/keys": { status: 201, body: { id: "k2", name: "dashboard", prefix: "rw_newkey01", api_key: "rw_newkey01_SECRETSECRETSECRETSECRET12", warning: "", created_at: null, last_used_at: null, revoked_at: null, expires_at: null, active: true } },
    });
    renderAt("/tenants");
    expect(await screen.findByText(/\$0\.25 spent · \$0\.05 reserved · \$1\.00 limit/)).toBeInTheDocument();
    expect(screen.getByText(/Budgets limit estimated list-price cost \(a shadow budget\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Manage keys" }));
    expect(await screen.findByText("rw_abcdefgh")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByTestId("new-key")).toHaveTextContent("rw_newkey01_SECRETSECRETSECRETSECRET12");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText(/SECRETSECRET/)).not.toBeInTheDocument();
  });

  it("separates actual charges from estimated list cost on the usage page", async () => {
    session.set(SESSION);
    mockFetch({ ...base, "/api/v1/admin/usage": { body: USAGE }, "/api/v1/admin/tenants": { body: { items: [] } } });
    renderAt("/usage");
    expect(await screen.findByText("Free-tier requests")).toBeInTheDocument();
    expect(screen.getByText("Est. list-price cost")).toBeInTheDocument();
    expect(screen.getByText("groq/openai/gpt-oss-20b")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Estimated list-price cost over time" })).toBeInTheDocument();
  });

  it("labels simulated benchmark runs as not publishable", async () => {
    session.set(SESSION);
    const metrics = { cases: 45, executed: 45, failures: 0, failure_rate: 0, scorable: 38, passed: 0, pass_rate: 0, pass_rate_wilson_95: [0, 0.09], by_difficulty: {}, estimated_list_cost_total_usd: "0", estimated_list_cost_per_request_usd: null, estimated_list_cost_per_accepted_answer_usd: null, input_tokens: 0, output_tokens: 0, latency_p50_ms: 1, latency_p95_ms: 2, fallback_rate: 0, provider_distribution: {}, model_distribution: {}, tier_distribution: { premium: 45 }, not_auto_scorable: 6, needs_human_review: 1 };
    mockFetch({
      ...base,
      "/api/v1/admin/evaluation/runs": {
        body: { items: [{ id: "r1", label: "pipeline-check", strategy: "baseline_premium", dataset_version: "routewise_bench_v1", policy_version: "rw-2026.11-v1", simulated: true, status: "completed", preregistration_sha256: "30df1259ef43aa", summary: { metrics, comparison_vs_baseline: null, publishable: false, publishable_reasons: ["simulated run (mock provider): pipeline check only, not a result"], label: "pipeline-check" }, started_at: "2026-11-04T10:00:00", finished_at: null }] },
      },
    });
    renderAt("/evaluation");
    expect(await screen.findByText("pipeline-check")).toBeInTheDocument();
    expect(screen.getByText("not publishable")).toBeInTheDocument();
    expect(screen.getByText(/it is not a measurement of quality/)).toBeInTheDocument();
  });

  it("never badges a scheduled day or a recovery as publishable, and discloses the recovery's full count", async () => {
    session.set(SESSION);
    const metrics = { cases: 10, executed: 10, failures: 0, failure_rate: 0, scorable: 10, passed: 10, pass_rate: 1, pass_rate_wilson_95: [0.72, 1], by_difficulty: {}, estimated_list_cost_total_usd: "0.001", estimated_list_cost_per_request_usd: "0.0001", estimated_list_cost_per_accepted_answer_usd: "0.0001", input_tokens: 1, output_tokens: 1, latency_p50_ms: 1, latency_p95_ms: 2, fallback_rate: 0, provider_distribution: {}, model_distribution: {}, tier_distribution: { premium: 10 }, not_auto_scorable: 0, needs_human_review: 0 };
    const run = (id: string, label: string, status: string, publishable: boolean | null, snapshot: object) => ({
      id, label, strategy: "baseline_premium", dataset_version: "routewise_bench_v5", policy_version: "rw-2026.11-v1", simulated: false, status,
      preregistration_sha256: "test-prereg-hash",
      summary: publishable === null ? null : { metrics, comparison_vs_baseline: null, publishable, publishable_reasons: [], label },
      config_snapshot: snapshot, started_at: "2026-11-05T09:09:00", finished_at: null,
    });
    const schedule = (day: number) => ({ execution_schedule: { day, days: 4 } });
    mockFetch({
      ...base,
      "/api/v1/admin/evaluation/runs": {
        body: {
          items: [
            run("d1", "v5.2.3-day1", "completed", true, schedule(1)),
            run("d2", "v5.2.3-day2", "failed", null, schedule(2)),
            run("rec", "v5.2.4-day2-recovery-run", "completed", true, {
              ...schedule(2),
              execution_recovery: { day: 2, executes: Array.from({ length: 25 }, (_, i) => i), carried_over: 11 },
            }),
          ],
        },
      },
    });
    renderAt("/evaluation");
    expect(await screen.findByText("v5.2.4-day2-recovery-run")).toBeInTheDocument();
    expect(screen.queryByText("publishable")).not.toBeInTheDocument(); // no green badge on any group
    expect(screen.getByText("post-hoc recovery · not publishable")).toBeInTheDocument();
    expect(screen.getByText(/only the 25 combinations it executed; 11 more were carried over .* accounts for 36 in total/)).toBeInTheDocument();
    expect(screen.getByText("interrupted · incident record")).toBeInTheDocument();
    expect(screen.getByText(/Day 1 of a registered 4-day schedule\. A single day is not a confirmatory result/)).toBeInTheDocument();
    expect(screen.queryByText(/pending human review/)).not.toBeInTheDocument();
  });

  it("shows an empty evaluation state", async () => {
    session.set(SESSION);
    mockFetch({ ...base, "/api/v1/admin/evaluation/runs": { body: { items: [] } } });
    renderAt("/evaluation");
    expect(await screen.findByText("No benchmark runs yet")).toBeInTheDocument();
  });

  it("shows the routing policy and no secrets on the settings page", async () => {
    session.set(SESSION);
    mockFetch({
      ...base,
      "/api/v1/admin/config": { body: { environment: "development", policy: { version: "rw-2026.11-v1", selection: "cheapest_capable" }, providers: ["mock"], simulated_only: true, settings: { allow_paid_models: false } } },
    });
    renderAt("/settings");
    expect(await screen.findByText("Routing policy rw-2026.11-v1")).toBeInTheDocument();
    expect(screen.getByText("cheapest_capable")).toBeInTheDocument();
    expect(screen.getByText(/never sent to the browser/)).toBeInTheDocument();
  });
});
