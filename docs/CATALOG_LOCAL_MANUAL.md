> Current preview: public-only `127.0.0.1:5188` via `start_catalog_preview.ps1`; checkout stays disabled. The older 5187 instructions below are historical and must not be used with the current switch. If 5188 stops, pricing is unavailable; there is no fallback to 5187.

# Local catalog diagnosis and manual setup

## Current localhost pricing: independent public-only service (23 October 2026)

This supersedes the historical 5187 proxy below. With the existing explicit `tmp/catalog-local-preview.enabled` switch, normal **http://localhost:5173/#pricing** now reads a separate loopback service on **5188**. The interactive admin demo remains stopped. Normal authentication, admin APIs and shared database configuration are unchanged.

Start from the repository root in a dedicated terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/tests/start_catalog_preview.ps1
```

Wait for `LOCAL CATALOG READY`; keep it running alongside normal development services. If Vite is not running, use `npm.cmd run dev` in `frontend`. The starter reuses the retained native test runtime, refuses an occupied 5188, and enables only the existing local preview switch. No .env changes. To stop this service:

```powershell
Set-Content tmp/catalog-preview.stop (Get-Date).ToString('O')
```

Restart creates fresh synthetic offers/IDs from approved definitions. The serving process has no automatic one/eight-hour timeout; restart it after an explicit stop or computer restart. Its fixture cleans up its own server/pools/cluster. Retained runtime downloads remain untouched.

The service verifies task-owned PostgreSQL and its restricted public reader, then prepares Free/Plus/Pro through accepted draft/review/publication APIs using synthetic actors and explicit isolated policies. It exposes only **GET /api/catalog**. Other methods, admin, AI and authentication paths return 404. The proxy strips credentials, and the bridge forwards no caller headers. Checkout remains disabled. No hardcoded response cards, shared migrations or real offers are used.

The website labels this **Local test pricing**. Normal authenticated admin changes use the normal backend/database and do not alter these separate disposable preview offers. Showing real shared published offers requires separately approved public-reader schema/grants/configuration and the publication workflow. Production builds do not use this proxy. An explicit `CATALOG_DEV_PROXY_TARGET` still overrides the test preview. If this service is stopped, the preview correctly becomes unavailable.

Actual browser acceptance: localhost catalog HTTP 200; native PostgreSQL 17.11; three cards; monthly 399/899 and annual 2,999/6,499; approximate 250/542; savings 37%/39%; disabled checkout; Clipboard focus/Escape tooltip; 390px no overflow. Public bridge write/admin/AI/alias rejection also passed. Two focused proxy/money checks passed. The initial ad-hoc PowerShell-piped browser assertion had a rupee encoding error; the file-based check passed with exact Unicode expectations. The long-lived native fixture is still serving, so setup assertions and separate browser acceptance passed, rather than a completed pytest suite.

Re-run from `frontend`: `node tests/catalog/local-preview.integration.mjs`. Screenshots: `tmp/catalog-preview/localhost-monthly.png`, `localhost-yearly.png`, `localhost-mobile.png`. Safe ready metadata and task-owned logs use `tmp/catalog-preview.ready`, `.log`, `.stderr.log`.

For the separately labelled interactive admin + pricing demo on **127.0.0.1:5187**, use [Isolated subscription publication demo](SUBSCRIPTION_ISOLATED_DEMO.md). It supplies explicit synthetic account switching and preserves normal localhost services. The historical public-only runner below remains separate.

## Explicit localhost pricing preview (23 October 2026)

The normal backend's public composition still returns 503. For local viewing only, the explicit task-owned switch `tmp/catalog-local-preview.enabled` makes normal Vite forward **GET /api/catalog only** to the running disposable demo on `127.0.0.1:5187`. The pricing section labels this **Isolated demo pricing**. Authentication/admin and other methods remain on their existing paths; cookies/authorization are stripped from the public demo request. An explicit `CATALOG_DEV_PROXY_TARGET` overrides this switch. No `.env` or shared database configuration changes.

With the isolated demo running, enable from the repository root with `New-Item -ItemType File -Force tmp/catalog-local-preview.enabled`, then open **http://localhost:5173/#pricing**. Remove only that task-owned marker to restore the normal backend target; the switch is read per request, so no restart is needed. Stopping the demo makes preview pricing unavailable again; there is no hardcoded fallback. Restart the demo using its linked runbook. Production builds do not use the development proxy or switch; real public catalog composition/publications remain separately required.

Verified in the actual localhost browser: three cards, demo label, monthly/yearly totals, disabled checkout and signed-out admin 404. All 12 targeted Node tests (including proxy scope/credential stripping) passed; production build passed with its existing chunk-size advisory. Screenshot: `tmp/subscription-demo/localhost-pricing.png`.

2026-10-23: first inspection had no listeners. Recheck after local services started found IPv6 ::1:5173 (normal frontend), IPv4 127.0.0.1:8000 (normal backend), and task-owned IPv4 127.0.0.1:5173 (manual frontend). Do not confuse localhost with IPv4: localhost currently selects the normal IPv6 frontend.

Actual normal requests: http://localhost:5173/api/catalog and http://127.0.0.1:8000/api/catalog both return HTTP 503, safe body {"detail":{"code":"catalog_unavailable"}}. This is unavailable composition, not a valid empty catalog (200/offers[]). The public handler deliberately suppresses raw exceptions. Default public enablement is false and DSN empty; no shared database/schema/grants/records were queried to override that boundary. Source also lacked a Vite catalog proxy; exact-path proxy now targets loopback 8000, overridable only for launched manual processes. Missing schema/grants/configuration cannot be distinguished further without inspecting the backend process's private configuration; none are claimed verified. Production policy and publication requirements remain unchanged.

The manual runner reuses the existing native fixtures, synthetic JWT/admin permission, explicit synthetic policy, accepted draft and lifecycle APIs. It publishes approved definitions only in a disposable cluster, starts a loopback bridge and Vite, and stays alive until stopped. No .env changes or production activation. Retry button now has explicit contrast, border, minimum target size and existing focus outline.

Start from repository root in PowerShell (retained runtime/driver already inspected):

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
New-Item -ItemType File -Force tmp/catalog-manual.request | Out-Null
& E:/deepfake_envs/SaIIA/python.exe "$env:TEMP/c113c-test-launch.py" backend/tests/test_pricing_browser_native.py --pg-bin C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin
```

Open **http://127.0.0.1:5173/#pricing**, not localhost. Run only one manual runner. Port 5173 IPv4 must be free; strict binding fails rather than killing another application. From a second PowerShell, stop:

```powershell
Set-Content tmp/catalog-manual.stop (Get-Date).ToString('O')
```

The runner stops only its own Vite process tree, shuts down its bridge and closes/removes its disposable cluster. It also exits after one hour. Retained PostgreSQL downloads are untouched. tmp/catalog-manual-vite.log contains frontend diagnostics, no DSN/token output.

Normal development still requires separately approved local catalog composition, restricted reader credentials, installed reviewed schema/grants and real published records (or this synthetic setup). Merely adding a proxy cannot turn default-disabled catalog storage into a live service. Do not point this runner at shared Supabase.

Browser verification: actual IPv4 manual URL returned catalog HTTP 200; three pricing cards (scoped to pricing), monthly Plus/Pro 399/899 and annual 2,999/6,499, Clipboard focus tooltip and disabled paid CTA verified with Playwright, without network mocks. Screenshot: tmp/catalog-manual-browser.png. Normal localhost/backend HTTP 503 remains an explicit normal-composition prerequisite.
