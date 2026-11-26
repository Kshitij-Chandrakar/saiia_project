# Isolated subscription publication demo

This explicitly launched test setup uses task-owned native PostgreSQL and synthetic JWT identities only. It never accepts a remote DSN. Normal localhost services, authentication, `.env` files, real permissions and offers remain unchanged.

## Enter the running demo

- Controls/account switch: **http://127.0.0.1:5187/__demo**
- Synthetic admin: **http://127.0.0.1:5187/__demo/as/admin** (redirects into `/auth/admin/subscriptions`)
- Ordinary synthetic user: **http://127.0.0.1:5187/__demo/as/ordinary** (the existing Page not found screen is expected)
- Published pricing: **http://127.0.0.1:5187/#pricing**
- Public API: **http://127.0.0.1:5187/api/catalog**
- Safe generated draft/offer IDs and verification summary: **http://127.0.0.1:5187/__demo/results**, also `tmp/subscription-demo-results.json`.

No passwords are required. The demo-only account selector supplies short-lived synthetic signed JWTs in memory. Backend JWT verification and authoritative database permissions still run. Only this explicitly selected Vite test configuration replaces the browser session source. The normal Vite configuration and normal Supabase authentication are untouched. Switching accounts uses a full navigation and clears editor state; use the demo controls link in the Isolated demo banner.

Do not use localhost:5173 or backend:8000 for this demo. The banner labels both the website and admin workspace **Isolated demo**. A separate loopback bridge has a dynamically allocated port; its API forwarding is limited to catalog/probe routes. Provider/payment/unrelated backend routes are not exposed.

## What startup demonstrates

The verification browser imports each approved Free/Plus/Pro definition through the real UI, assigns a unique `isolated-...` plan code, saves, closes, reopens, adds explicit disposable policy references, saves again, previews/reviews the exact saved revision and publishes. Main display names remain Free, Plus and Pro so the actual three-card layout is exercised. Their unique draft/plan/offer UUIDs identify disposable records; prices and allowances come from the approved fixtures and persisted public catalog, not fallback cards.

An additional **Disposable demo offer** is published, replaced with version 2, then retired. The three main offers stay visible. Open either recorded disposable offer ID to inspect immutable history. Two additional hidden/retired legacy archives belong to the reused migration-verification fixture; they are not customer offers.

Checkout remains disabled. The existing closed hosted AI boundary is used in this test process and unrelated routes are blocked at the bridge. Outbound provider/payment HTTP is forbidden by the accepted fixture. This is synthetic local acceptance, not Supabase/PostgREST or production acceptance.

## Manually walk through the workflow

1. Enter as synthetic admin. Find a main offer ID in the safe results page; paste it into **Open an offer by ID**, then **Open offer** to inspect its immutable published terms. Use **Create a new draft version** only when intentionally preparing a replacement. The save/reopen exercise happens before publication in startup verification.
2. To practice without modifying the three main cards, import another approved template and change **Plan code** to a new unique training code before saving. Give it an unmistakable disposable display name.
3. In Identity → **Policy references**, use the already-installed **test-only** values `synthetic.lifecycle` for Subscription policy and `synthetic.migration` for Subscriber migration policy. For Free, Features & limits → Limit policy reference is `synthetic.storage`. For each Plus/Pro price, Prices → Policy references uses `synthetic.tax` and `synthetic.rounding`. Never use these as real commercial approvals.
4. Enter **Change reason**, **Save draft**, retain its ID, **Close draft**, reopen by ID and check values. Click **Preview saved draft**.
5. Under **Review and publication**, choose **Publish a first offer**, enter a past **Offer starts at (IST)** within your intended test scenario and a **Lifecycle reason**. Enter IST directly; do not subtract 5 hours 30 minutes. Leave the optional end blank unless the offer should expire. Click **Review for publication** → inspect exact terms → **Confirm review**.
6. Click **Publish reviewed offer** → inspect confirmation → **Confirm publication**. Record offer and Operation IDs. Check `/api/catalog`, then `/#pricing`; reload for immediate refresh. New practice offers add cards until you retire them.
7. To replace only your additional practice offer, **Open offer** by its ID → **Create a new draft version** → edit/save/preview → select **Replace current offer** → obtain a fresh review → **Replace reviewed offer** → **Confirm replacement**. Old immutable terms remain.
8. To remove your additional practice offer from pricing, open its current version, supply Lifecycle reason → **Retire this offer** → **Confirm retirement**. This does not cancel subscriptions or payments.
9. Switch to ordinary user. The workspace must show the existing 404 view. Backend mutation permission remains denied, even if a caller constructs a request independently.

Do not discard an uncertain mutation. Use **Retry same save**, or lifecycle **Check pending operation** / **Retry same action**. After reload, use recorded Operation ID with **Check operation**; no write is automatically repeated. See the [full operator guide](SUBSCRIPTION_ADMIN_USER_GUIDE.md).

## Stop and restart

From a PowerShell at `E:/saiia_project/saiia_project`, stop only this task-owned runner:

```powershell
Set-Content tmp/subscription-demo.stop (Get-Date).ToString('O')
```

It stops its own Vite tree/bridge and removes only its own disposable database directory. Existing retained PostgreSQL runtime downloads and normal services are untouched. The demo also stops after eight hours; policy approval is test-only and bounded by the fixture's one-day window.

Restart in a dedicated terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/tests/start_subscription_demo.ps1
```

Wait for `ISOLATED DEMO VERIFIED` and `tmp/subscription-demo.ready`. Startup reruns the full browser demonstration, so allow time for native setup and verification. Each restart creates a fresh database and new IDs; the results file is replaced after successful verification. The process stays running to hold the disposable fixtures alive. Ctrl+C may interrupt cleanup; prefer the stop-file command. Never stop unknown PostgreSQL processes manually.

The startup script uses the already-retained machine-specific Python, PDF-import test stub, driver and PostgreSQL runtime documented in [the older manual runbook](CATALOG_LOCAL_MANUAL.md). Missing runtime files fail clearly; it does not install software or alter PATH. It refuses an occupied demo port 5187.

## Verification artifacts

- `tmp/subscription-demo-results.json`: safe current IDs and passed browser checks; no tokens/DSNs.
- `tmp/subscription-demo/`: monthly/yearly desktop, mobile pricing and admin screenshots.
- `tmp/subscription-demo.log`, `tmp/subscription-demo.stderr.log`, `tmp/subscription-demo-vite.log`: task-owned diagnostic logs. Request headers/cookies/tokens are not logged.

The browser uses no route mocks or hardcoded API success responses. The session source and permission-probe gateway are synthetic test composition; JWT verification, SQL permission functions, restricted application pools, domain validation, durable mutation records, lifecycle transactions and public projections are the real implementations.

### Actual acceptance, 23 October 2026

- Native PostgreSQL **17.11**: newly allocated loopback cluster and actual restricted application identity checked before demo offer writes. Existing legacy migration fixtures were identified separately. No shared DSN was accepted.
- Browser acceptance passed: four imports/save/reopen/preview/reviews/publications, extra-offer replacement and retirement, exactly three main public cards, monthly/yearly prices/savings, all Sketch/Clipboard information controls, disabled paid checkout and 390px overflow check.
- Ordinary identity: existing Page not found view; a structurally valid draft-create request returned HTTP **403** with `catalog_permission_denied`. Final database counts confirmed no extra plan from that attempt.
- A second fresh browser session independently entered as synthetic admin, saw the Isolated demo banner and opened a persisted published offer successfully.
- Public API returned HTTP **200** with the three main offers. Unrelated `/api/generate` at the bridge returned **404**. Normal `::1:5173` and `127.0.0.1:8000` listeners retained their original process IDs.
- **11** existing catalog/draft/lifecycle/money Node tests passed. Normal production build passed; existing large-chunk advisory remains. Python/JavaScript syntax and whitespace checks passed.
- Graphify query ran before changes. A targeted AST graph/query ran afterward; the full-project merge's shrink guard refused replacement, so its existing graph was preserved and the demo-only graph is under `tmp/subscription-demo-graph`.

The runner prints `ISOLATED DEMO VERIFIED` only after browser assertions and SQL counts pass. It then intentionally remains inside its live fixture for manual use; the enclosing pytest process has not exited while the demo is running. Screenshots are synthetic local evidence, not deployed acceptance. C12/C13 and real policy decisions remain outside this demo.

### IST admin inputs

Offer start/end fields now accept **IST (Asia/Kolkata)**, independent of the browser timezone. Confirmations and stored-offer availability display IST; the existing backend protocol still receives UTC instants. Enter your IST clock time directly and leave the optional end blank unless expiration is intentional. No historical timestamps were rewritten.

Verified: 14 Node checks and 42 workspace/lifecycle Playwright checks passed; the real demo browser running in the Los Angeles timezone sent `21:43:26 IST` as `16:13:26Z` through JWT/service/native PostgreSQL policy preview and showed IST in confirmation. Invalid end ordering was blocked before a request; no offer was published in that conversion test. Normal production build passed with its existing chunk warning. Run the opt-in check against the running demo from `frontend` with `node tests/catalog/lifecycle.ist.integration.mjs`. Screenshots: `tmp/subscription-demo/ist-fields-desktop.png` and `tmp/subscription-demo/ist-fields-mobile.png`.


### User manual acceptance and shutdown (23 October 2026)

The user reports successful manual testing and requested closure. The documented stop-file procedure was executed; the runner exited with `1 passed, 1 warning`, its ready marker and own disposable directory were cleaned up, and demo listeners/PostgreSQL stopped. Normal frontend/backend listeners remained running. This is isolated manual acceptance plus runner cleanup evidence, not shared deployment acceptance. The demo is **not currently running**; use the restart instructions above for a fresh disposable database/new IDs. No retained runtime downloads were deleted. See [the next consolidated milestone](SUBSCRIPTION_ENTITLEMENTS_USAGE_MILESTONE.md).
