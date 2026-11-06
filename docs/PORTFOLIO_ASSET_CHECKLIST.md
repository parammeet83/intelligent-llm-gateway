# Portfolio asset checklist

What exists, what's missing, and exactly how to capture the missing screenshots yourself. Don't use generated or
mocked-up images of the app; capture the real thing.

## What already exists

[`docs/screenshots/`](screenshots/) has 9 PNGs, committed on 2026-11-04 (commit `63a86ee`):

| Desktop, 1366×860 | Mobile, 1082×2202 |
|---|---|
| `overview`, `routing-decisions`, `providers-models`, `tenants-budgets`, `usage-cost`, `request-logs`, `evaluation`, `settings` | `mobile-overview` |

They were captured automatically by Playwright (`frontend/e2e/responsive.spec.ts`) from a **local** run with
**mock-provider demo data**, before deployment and before any real benchmark run. So:
- They are honest, and labelled as simulated in the README.
- They don't show the production URL.
- `evaluation.png` shows only a simulated pipeline run, not the real Day 1–3 benchmark runs.

## Screenshots to capture manually

Save them in `docs/screenshots/production/`, using the file names below. Check each one against the rules at the
end before committing.

| # | File name | What to capture | Where | Notes |
|---|---|---|---|---|
| 1 | `01-landing-signin.png` | The dashboard's first screen: DEMO banner and administrator sign-in | https://routewise-dashboard.vercel.app in a private window | Shows the honest "simulated responses" banner. Don't type the token yet |
| 2 | `02-overview.png` | *Overview* after sign-in: KPIs, traffic by tier, gateway status | Dashboard → Overview | Include the DEMO banner; the totals include the real benchmark requests |
| 3 | `03-request-powershell.png` | The simple and complex requests from the [demo guide](DEMO_GUIDE.md#requests-for-steps-45), with `model`, `routing.score`, `required_tier` and `reason_codes` visible | PowerShell | **Crop out** the line where the key was pasted. The key must never appear |
| 4 | `04-routing-decision.png` | One request's full decision record: reason codes, score contributions, candidates table with exclusion reasons, attempts | Dashboard → Routing Decisions → click the complex request | The best "explainability" image |
| 5 | `05-request-logs.png` | Request Logs list, with the *simulated* badges visible | Dashboard → Request Logs | — |
| 6 | `06-usage-cost.png` | Usage & Cost charts (requests, tokens, list-price cost, latency) | Dashboard → Usage & Cost, last 7 days | Shows estimated cost separated from actual charges |
| 7 | `07-evaluation.png` | The real benchmark runs | Dashboard → Evaluation | **Caution:** the page shows a green "publishable" badge on `v5.2.3-day1` and `v5.2.4-day2-recovery-run`, which is misleading ([KNOWN_ISSUES.md](KNOWN_ISSUES.md)). Either capture only the `v5.2.5-day3` group, which correctly shows "not publishable", or put the image next to the day table from [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) |
| 8 | `08-health-ready.png` | Two browser tabs: `/api/v1/health` and `/api/v1/ready` | https://routewise-api-ggjk.onrender.com/api/v1/health and `/ready` | Wake the API first. Both responses are safe to show; they report `environment: production`, `providers: ["mock"]`, `simulated_only: true`, `migrations: ok` |
| 9 | `09-github-overview.png` | The repository home page with the README's status table | https://github.com/parammeet83/intelligent-llm-gateway | — |
| 10 | `10-github-ci.png` | A green GitHub Actions run with the four jobs (backend, frontend, e2e, secrets) | GitHub → Actions → latest run on `main` | — |
| 11 | `11-mobile-overview.png` (optional) | The Overview page on a phone | Phone browser, or Chrome DevTools → device toolbar → Pixel 7 | Shows the responsive layout |

### How to capture on Windows

- **A region:** `Win + Shift + S`, then *Rectangle*, then paste into Paint and save as PNG.
- **A full page in Chrome:** DevTools (`F12`) → `Ctrl + Shift + P` → type "Capture full size screenshot".
- **Window size:** use a desktop browser window about 1366–1440 px wide for consistent images.
- **Before capturing:**
  - Sign out of other accounts in the browser.
  - Close tabs that show email or other personal information.
  - Zoom to 100%.

## Optional assets

- A **60–90 s screen recording** of demo steps 3–6 (Overview, then two requests, then the decision record). Use
  the Windows Game Bar (`Win + G`) or OBS. Pause the recording while you paste the API key.
- A short **architecture image**: open the README on GitHub (it renders the Mermaid diagrams) and capture the
  *Architecture* diagram.

## Rules before you commit any image

- [ ] No API key, admin token, session token, `DATABASE_URL` or password is visible, including in the address bar
      and terminal history.
- [ ] No Render or Vercel dashboard pages showing environment variables.
- [ ] No personal email, browser profile name or unrelated tabs.
- [ ] Simulated data is labelled. Keep the DEMO banner in dashboard shots; don't crop it out.
- [ ] Benchmark images don't suggest a confirmatory result.
- [ ] After capturing, revoke the demo API key (*Tenants & Budgets*).

Then update the README's *Screenshots* section to point to `docs/screenshots/production/`, keeping a note that
production responses are simulated.
