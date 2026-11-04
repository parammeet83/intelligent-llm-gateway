/**
 * End-to-end: tenant API key -> authenticated request -> routing decision -> provider response
 * -> cost/usage accounting -> database persistence -> dashboard visibility.
 * Runs against a real backend with the mock provider only (labelled simulated throughout).
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_ADMIN_TOKEN } from "./constants.mjs";

const API = "http://127.0.0.1:8020/api/v1";
const admin = { Authorization: `Bearer ${E2E_ADMIN_TOKEN}` };

async function tenantWithKey(request: APIRequestContext, slug: string, extra: Record<string, unknown> = {}) {
  const created = await request.post(`${API}/admin/tenants`, { headers: admin, data: { slug, name: slug, ...extra } });
  expect([201, 409]).toContain(created.status());
  const key = await request.post(`${API}/admin/tenants/${slug}/keys`, { headers: admin, data: { name: "e2e" } });
  expect(key.status()).toBe(201);
  return (await key.json()).api_key as string;
}

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Admin token").fill(E2E_ADMIN_TOKEN);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

async function openNav(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label }).click();
}

test("authenticated generation is routed, accounted, persisted and visible in the dashboard", async ({ page, request }, info) => {
  const slug = `e2e-${info.project.name}`;
  const key = await tenantWithKey(request, slug);
  const clientId = `e2e-${info.project.name}-${Date.now()}`;

  const generated = await request.post(`${API}/generate`, {
    headers: { Authorization: `Bearer ${key}` },
    data: { prompt: "Classify the sentiment: I love this phone.", task_type: "classification", request_id: clientId },
  });
  expect(generated.status()).toBe(200);
  const body = await generated.json();
  expect(body.simulated).toBe(true);
  expect(body.tenant).toBe(slug);
  expect(body.routing.policy_version).toBe("rw-2026.11-v1");
  expect(body.routing.reason_codes).toContain("SIMULATED_PROVIDER");
  expect(body.cost.list_cost_status).toBe("estimated");

  // Persisted and visible to the tenant itself...
  const mine = await (await request.get(`${API}/me/requests/${body.request_id}`, { headers: { Authorization: `Bearer ${key}` } })).json();
  expect(mine.attempts[0].reason_code).toBe("PRIMARY");

  // ...and in the dashboard.
  await signIn(page);
  await expect(page.getByText(/DEMO — simulated responses/)).toBeVisible();
  await openNav(page, "Request Logs");
  await page.getByLabel(/Search by request ID/).fill(clientId);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByText(slug).first().click();
  const dialog = page.getByRole("dialog", { name: "Request detail" });
  await expect(dialog.getByText(body.request_id)).toBeVisible();
  await expect(dialog.getByText("PRIMARY")).toBeVisible();
  await expect(dialog.getByText(/content is not stored/)).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  await openNav(page, "Usage & Cost");
  await expect(page.getByText("Est. list-price cost").first()).toBeVisible();
  await expect(page.getByText("Actual charges").first()).toBeVisible();
});

test("unauthorised access, duplicates and budget exhaustion are rejected", async ({ request }, info) => {
  const bad = await request.post(`${API}/generate`, { headers: { Authorization: "Bearer rw_notreal_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" }, data: { prompt: "hi", task_type: "chat" } });
  expect(bad.status()).toBe(401);
  expect((await request.get(`${API}/admin/tenants`)).status()).toBe(401);

  const key = await tenantWithKey(request, `e2e-budget-${info.project.name}`, { daily_budget_usd: "0" });
  const headers = { Authorization: `Bearer ${key}` };
  const exhausted = await request.post(`${API}/generate`, { headers, data: { prompt: "hi", task_type: "chat" } });
  expect(exhausted.status()).toBe(402);
  expect((await exhausted.json()).error.code).toBe("BUDGET_EXHAUSTED");

  const key2 = await tenantWithKey(request, `e2e-dup-${info.project.name}`);
  const h2 = { Authorization: `Bearer ${key2}` };
  const id = `dup-${Date.now()}`;
  expect((await request.post(`${API}/generate`, { headers: h2, data: { prompt: "hi", task_type: "chat", request_id: id } })).status()).toBe(200);
  expect((await request.post(`${API}/generate`, { headers: h2, data: { prompt: "hi", task_type: "chat", request_id: id } })).status()).toBe(409);

  // Tenant isolation over HTTP.
  const other = await (await request.get(`${API}/me/requests`, { headers })).json();
  expect(other.total).toBe(1); // only its own rejected request
});

test("admin pages require sign-in", async ({ page }) => {
  await page.goto("/usage");
  await expect(page.getByRole("heading", { name: "Administrator sign-in" })).toBeVisible();
  await page.getByLabel("Admin token").fill("wrong-token");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid or missing credentials");
});
