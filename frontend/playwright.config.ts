import { defineConfig, devices } from "@playwright/test";

const API = "http://127.0.0.1:8020";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the tests share one backend database
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 860 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: `${API}/api/v1/ready`,
      timeout: 180_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      timeout: 180_000,
      reuseExistingServer: false,
      env: { VITE_API_BASE_URL: API },
    },
  ],
});
