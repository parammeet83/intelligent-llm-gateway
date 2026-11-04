// Starts a real RouteWise backend for end-to-end tests on a fresh, throwaway SQLite database.
// Environment variables override the developer's .env, so Neon is never touched and no real
// provider is enabled. Secrets here are test-only values.
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "..", "..", "backend");
const dataDir = join(tmpdir(), "routewise-e2e");
rmSync(dataDir, { recursive: true, force: true });
mkdirSync(dataDir, { recursive: true });

import { E2E_ADMIN_TOKEN } from "./constants.mjs";

const env = {
  ...process.env,
  APP_ENV: "test",
  DATABASE_URL: `sqlite+aiosqlite:///${join(dataDir, "e2e.db").replaceAll("\\", "/")}`,
  ADMIN_TOKEN: E2E_ADMIN_TOKEN,
  API_KEY_PEPPER: "e2e-pepper-not-a-real-secret-0123456789",
  CORS_ORIGINS: "http://127.0.0.1:4173",
  MOCK_PROVIDER_ENABLED: "true",
  GROQ_ENABLED: "false",
  OPENROUTER_ENABLED: "false",
  OLLAMA_ENABLED: "false",
  VERIFY_MODEL_CATALOG: "false",
  // Many sign-ins from one test client; the throttle itself is covered by backend tests.
  ADMIN_LOGIN_ATTEMPTS_PER_MIN: "100",
  LOG_LEVEL: "WARNING",
};

const run = (args) => {
  const result = spawnSync("uv", ["run", ...args], { cwd: backend, env, stdio: "inherit", shell: process.platform === "win32" });
  if (result.status !== 0) process.exit(result.status ?? 1);
};

run(["alembic", "upgrade", "head"]);
run(["python", "-m", "app.cli", "seed", "--no-demo"]);

const server = spawn("uv", ["run", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8020"], {
  cwd: backend,
  env,
  stdio: "inherit",
  shell: process.platform === "win32",
});
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
