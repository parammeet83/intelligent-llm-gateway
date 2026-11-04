# Technical Requirements — RouteWise AI

| Area | Requirement | Implementation |
|---|---|---|
| Runtime | Python 3.12, async I/O end to end | FastAPI + Uvicorn, SQLAlchemy 2 async, asyncpg (Neon) / aiosqlite (tests), HTTPX |
| Data | Migration-managed PostgreSQL | Alembic `0001` (12 tables), `0002` (key expiry, budget reservations); drift check in tests and CI |
| Config | Environment only, validated at startup | pydantic-settings. Production refuses weak secrets, SQLite, paid models, Ollama |
| Providers | Independent adapters, trusted base URLs | Groq, OpenRouter (`:free` only), Ollama (localhost only), Mock (simulated) |
| Resilience | Timeouts, bounded retries, backoff with jitter, Retry-After, circuit breakers, deadline | `services/executor.py`, `resilience/health.py` |
| Routing | Deterministic, explainable, versioned | `routing/engine.py`; policy `rw-2026.11-v1` in YAML; decision record per request |
| Tenancy | Hashed keys, isolation, rate limits, atomic budgets | HMAC-SHA256 + pepper; fixed-window upsert; conditional-UPDATE reservations in a SAVEPOINT |
| Accounting | Actual vs estimated list cost, four statuses, pricing provenance | `accounting/cost.py`; append-only `pricing_snapshots` |
| Privacy | No prompt or response storage; redacted logs | SHA-256 + length only; JSON logs with redaction |
| API | Versioned, validated, single error envelope | `/api/v1`; `extra=forbid`; 512 KiB body cap |
| Frontend | React + TS + Vite + Tailwind + Recharts; responsive | 8 lazy-loaded pages; session token in `sessionStorage` |
| Evaluation | Reproducible, pre-registered, deterministic scoring | `app/evaluation/`; seeded bootstrap; config snapshot per run |
| Quality gates | Lint, types, tests, E2E, audits, secret scan | ruff, mypy strict, pytest, Vitest, Playwright, pip-audit, npm audit, detect-secrets (CI) |
| Deployment | Free tier, container | Dockerfile + `render.yaml` (Render free web service + static site) + Neon |

Non-functional targets: p95 gateway overhead dominated by provider latency (routing is pure CPU work, no I/O);
correctness of spend under concurrency (tested); fail-closed security defaults.
