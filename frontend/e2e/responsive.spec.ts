/**
 * Every page renders on desktop and mobile without horizontal page overflow, and the dashboard
 * screenshots used in the README are captured from the running app (desktop project only).
 */
import { expect, test } from "@playwright/test";
import { E2E_ADMIN_TOKEN } from "./constants.mjs";

const API = "http://127.0.0.1:8020/api/v1";
const PAGES = [
  { path: "/", heading: "Overview", shot: "overview" },
  { path: "/routing", heading: "Routing Decisions", shot: "routing-decisions" },
  { path: "/providers", heading: "Providers & Models", shot: "providers-models" },
  { path: "/tenants", heading: "Tenants & Budgets", shot: "tenants-budgets" },
  { path: "/usage", heading: "Usage & Cost", shot: "usage-cost" },
  { path: "/logs", heading: "Request Logs", shot: "request-logs" },
  { path: "/evaluation", heading: "Benchmark & Evaluation", shot: "evaluation" },
  { path: "/settings", heading: "Settings", shot: "settings" },
];

test.beforeAll(async ({ request }) => {
  // A little simulated traffic so charts and tables have something to show.
  const admin = { Authorization: `Bearer ${E2E_ADMIN_TOKEN}` };
  await request.post(`${API}/admin/tenants`, { headers: admin, data: { slug: "demo-co", name: "Demo Co (simulated traffic)", daily_budget_usd: "1.00" } });
  const key = (await (await request.post(`${API}/admin/tenants/demo-co/keys`, { headers: admin, data: { name: "demo" } })).json()).api_key;
  const prompts = [
    { prompt: "Is this review positive? 'Great battery.'", task_type: "classification" },
    { prompt: "Summarise: the deploy failed because the disk was full; we added an alert.", task_type: "summarization" },
    { prompt: "Prove the algorithm terminates, then derive its complexity step by step and compare trade-offs.", task_type: "reasoning" },
  ];
  for (const data of prompts) await request.post(`${API}/generate`, { headers: { Authorization: `Bearer ${key}` }, data });
});

test("all pages render without horizontal overflow", async ({ page }, info) => {
  await page.goto("/");
  await page.getByLabel("Admin token").fill(E2E_ADMIN_TOKEN);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  for (const { path, heading, shot } of PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} overflows horizontally on ${info.project.name}`).toBeLessThanOrEqual(1);
    if (info.project.name === "desktop") {
      await page.screenshot({ path: `../docs/screenshots/${shot}.png`, fullPage: false });
    }
  }
  if (info.project.name === "mobile") {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "../docs/screenshots/mobile-overview.png", fullPage: false });
  }
});

test("mobile navigation opens and closes", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "mobile only");
  await page.goto("/providers");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toBeVisible();
  await menu.click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
});
