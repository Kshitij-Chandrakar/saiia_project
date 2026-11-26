# C12-RZP-TEST-01 secure setup and single execution scope

Current execution follow-up: the user authorized this bounded session on 26 October 2026. See actual preflight, credential handoff and execution status (owner-held private record `C12_RZP_TEST_01_EXECUTION.md`; excluded from this checkout). Historical preparation-only wording below is not a request to repeat that approval.

26 October 2026. **Prepared, not executed.** No real credentials entered, provider calls, Dashboard changes, tunnel launch, public exposure or remote migrations. Live billing stays disabled. C11/C13 staging authorization remains separate.

## Inspection and prepared files

`backend/app/config.py` uses `load_dotenv()` without override, then process environment. No .env edit is needed. Billing also requires explicit enablement, restricted database configuration and an active subscription service. The adapter rejects live keys. Loading credentials alone cannot enable billing.

The existing POST `/api/billing/webhook` verifies raw-body signatures and trusted payment evidence. No tunnel launcher or path-only gateway existed; cloudflared, ngrok and zrok were absent from PATH. Nothing was installed.

- `scripts/c12_test_credentials.ps1`: masked prompts, process-only environment, no credential files/output; always sets billing false; rejects live keys. `-Clear` clears test values and the previous webhook secret.
- `scripts/c12_webhook_gateway.py`: existing FastAPI/stdlib only; exact POST webhook route, fixed upstream `127.0.0.1:8000`, no docs/redirect/arbitrary proxy destination, no forwarded authorization or payload logs. Preserves signed bytes/signature; 128 KiB cap, 10-second body deadline, 30-second upstream timeout. Acknowledges only backend success. HMAC verification remains in the backend.
- `backend/tests/test_c12_setup.py`: offline boundary tests; no provider, tunnel or database traffic.

## Exact owner steps after execution authorization

### 1. Create/retrieve dedicated Razorpay test credentials

1. Open the [Dashboard](https://dashboard.razorpay.com/) yourself. Select the dedicated acceptance merchant and **Test Mode**. Check the mode indicator before every change.
2. Navigate to **Account & Settings → Website and app settings → API Keys → Generate Key**. If keys already exist, retrieve them from your secure vault. Do not regenerate shared keys or invalidate other integrations; stop if a dedicated usable pair is unavailable.
3. Store the displayed pair directly in your password manager. Key ID must start `rzp_test_`; the secret is shown at generation. Avoid credential CSV downloads and never paste values into chat or shell commands. Confirm that merchant's exact `acc_...` account ID from its Dashboard/account information; do not infer it from the key.
4. Generate a separate webhook secret in your password manager, at least 32 random characters. Retain the same value for local entry and the webhook form; do not reuse the API secret.

Official [API key guidance](https://razorpay.com/docs/payments/dashboard/account-settings/api-keys/) permits test keys without website activation. Navigation may vary; remain in the Test Mode API Keys section.

### 2. Enter through hidden local input

Use a dedicated, non-transcribed PowerShell terminal on your machine, outside assistant tool output. From the repository root:

```powershell
& .\scripts\c12_test_credentials.ps1
```

Paste each value at its masked prompt. Only a status message is printed. Billing remains **false**. Later start the approved backend as a child of this same terminal; other windows/running processes do not receive these values. Settings are read at startup.

Masked entry prevents echo/history literals. The existing configuration mechanism still requires plaintext values in backend process memory/environment; it does not protect against a privileged local process. Do not dump environment/settings, enable tracing/transcripts, use persistent machine/user variables, or put secrets in frontend/VITE variables or .env files. No secret belongs in screenshots.

The loader does not collect owner database passwords, auth signing keys or tunnel tokens. Stop backend children before clearing their parent's credentials. No real input was requested during preparation; only synthetic values were tested.

### 3. Local database/runtime preflight

Use a fresh task-owned disposable native PostgreSQL 17 cluster and the existing reviewed native prerequisites. Record its resolved directory/loopback port. Apply **once locally**:

1. `supabase/migrations/20261025020000_razorpay_checkout.sql`
2. `supabase/migrations/20261025030000_billing_gst_payable.sql`

Hashes and rollback guidance: GST evidence (owner-held private record `C12_GST_IMPLEMENTATION_EVIDENCE.md`; excluded from this checkout). No remote SQL or staging bootstrap is included. Use restricted `usage_executor` and `usage_binding_executor` pools; prepare eight disposable verified identities, immutable synthetic offers and Free bootstrap only in this cluster.

Review a redacted runtime manifest before enabling billing: local DB path/port, synthetic auth issuer, restricted roles, offer/price IDs and API ports. Do not launch the ordinary main app against unreviewed inherited/.env settings or staging auth. This setup task has not verified a separately running real-provider acceptance composition. The existing offline substitute runner stays offline; adding keys does not convert it into provider acceptance.

Website: `127.0.0.1:5173`; backend: `127.0.0.1:8000`. Keep billing false until the named session starts. Then use `automatic`, payable policy `billing.inr.gst18.v1` and reviewed server-only plan mappings. No live adapter is introduced.

### 4. Temporary HTTPS webhook

Proposed simplest transport: **Cloudflare Quick Tunnel**, with no domain purchase, DNS change or persistent service. Download its matching Windows portable executable from [official installation/releases](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) to `%LOCALAPPDATA%\C12Tools\cloudflared.exe` after authorization. No download occurred during preparation.

In a clean terminal without payment credentials, from the repository root, set `$PreparedPython` to the executable in your prepared Python environment:

```powershell
& $PreparedPython -m uvicorn scripts.c12_webhook_gateway:app --host 127.0.0.1 --port 8012 --no-access-log --limit-concurrency 16 --backlog 16 --timeout-keep-alive 2
```

Confirm locally that `/`, `/docs`, `/api/account/subscription`, GET webhook and trailing-slash variants cannot reach backend routes. Missing signature fails. Keep the main backend on loopback. In another clean terminal, after authorization:

```powershell
& "$env:LOCALAPPDATA\C12Tools\cloudflared.exe" tunnel --url http://127.0.0.1:8012
```

Record the one generated `https://<random>.trycloudflare.com` URL before registration; append `/api/billing/webhook`. Never tunnel ports 8000, 5173 or PostgreSQL. Do not enable request/body inspection. Cloudflare terminates public TLS and handles synthetic webhook data; this external processor is part of the approval scope. Use no real customer data.

[Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) describes temporary URLs and testing limitations. Razorpay [blocks several domains](https://razorpay.com/docs/webhooks/validate-test/), including ngrok.io, localhost and webhook.site. trycloudflare.com is absent from the published list; **Dashboard acceptance is not guaranteed**. If rejected, stop; do not switch services or widen exposure. The scope below covers one dynamically allocated hostname under this domain, avoiding a second unchanged approval merely to record its exact value.

### 5. Register one test webhook

In the dedicated merchant's **Test Mode** Dashboard, open **Account & Settings → Website and app settings → Webhooks → Add New Webhook**. Enter the exact recorded HTTPS URL, independent secret from your password manager and owner's test alert email. Enable only:

`subscription.authenticated`, `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`, `subscription.updated`.

Create only during the approved session. Razorpay documents `754081` for test-mode webhook setup/edit/delete prompts; this is not an account-login OTP. [Official webhook setup](https://razorpay.com/docs/webhooks/setup-edit-payments/). Invalid signatures must never acknowledge success. Actual delivery is unverified until executed.

## Single consolidated execution scope — awaiting authorization

One owner-operated C12-RZP-TEST-01 session, maximum **60 minutes of test activity**, dedicated owner-selected test merchant, eight synthetic identities and one new disposable loopback PostgreSQL cluster:

1. Dedicated test-key generation/retrieval and hidden entry, portable Cloudflare tool download, one temporary tunnel and one generated `*.trycloudflare.com` hostname pointing only to the gateway; one test webhook registration. No shared-key regeneration, DNS change or persistent tunnel service.
2. Local fixture prerequisites and the two C12 migrations above; restricted synthetic-auth/runtime composition and exact mappings. No remote migrations, existing cluster changes or staging reuse. Record the redacted manifest before provider mutations.
3. At most **4 test plans, 8 subscription creations, 8 period-end cancellation attempts total, 500 backend provider GETs**. No blind mutation retry after uncertain dispatch. These are operator stop budgets, not a new global runtime limiter. At time/read limits stop new tests; cleanup uses only remaining mutation budget. Report unresolved resources rather than silently expanding limits.
4. Final INR plan amounts **47082 / 353882 / 106082 / 766882 paise** for Plus monthly/yearly and Pro monthly/yearly. Interval/quantity 1; no additional provider tax, add-ons, offers, trials or upfront charges. Maximum **12 monthly / 5 yearly cycles**, subject to provider validation and explicit consent; no automatic replacement mandate.
5. Website review/consent, success and dismissal/failure per price, duplicates/two tabs, signed delivery in both callback/webhook orders, bounded recovery and authoritative website/Electron account refresh, then period-end cancellation. Official test instruments only. Actual renewal/completion cases remain pending if the same configured intervals cannot be exercised within the session; substitute evidence is separate.
6. Redacted results and cleanup below. No live keys/payments, real assignments, refunds/capture mutations, discounts, upgrade/proration, account purges, deployment, commits, pushes or remote changes.

Record the merchant ID and allocated exact URL locally during execution. Secrets never go in chat. Stop on failed local-runtime isolation, provider mandate validation or URL validation; do not improvise broader scope. This proposed session-generated-host scope supersedes the earlier requirement to name a pre-existing host before tunnel allocation, only if approved.

## Cleanup within the same scope

1. Stop new checkout. Reconcile uncertainty by IDs/notes and reads. Request period-end cancellation for every created subscription, counting all attempts in the eight-attempt budget. Verify scheduled/cancelled states; preserve paid-period ends. No refunds or immediate cancellation shortcuts.
2. Disable/delete the one webhook, then stop tunnel and gateway with Ctrl+C. Confirm closure. Leave no active untracked mandate; provider plans/invoices may remain test records where deletion is unavailable.
3. Stop backend/workers. In their parent terminal run `& .\scripts\c12_test_credentials.ps1 -Clear`, then close it. Parent cleanup cannot erase a running child's memory. Revoke/rotate the dedicated test pair as appropriate through the owner's Dashboard, without touching shared/live credentials.
4. Retain redacted results and uncertainty evidence, then use native harness cleanup for only the resolved newly created cluster. Its eight local identities disappear with it. Remove process-local auth/DB configuration; no remote account deletion.
5. Record deterministic, actual-provider, pending and cleanup results separately. Unresolved cancellation, open webhook or open tunnel prevents a cleaned-up acceptance claim.

## Preparation verification

Offline gateway tests: **8 passed, 0.44 s**. PowerShell parser and synthetic hidden-input/default-off/clear/live-prefix rejection passed. Ruff lint/format, gateway mypy and Git whitespace checks passed. Existing Python import deprecation warnings remain. No real secrets, public services or provider calls were needed; no production/frontend build was necessary.

Graphify queried before/after. Final partial structural graph: 356 nodes / 791 edges, 18 files, no model extraction tokens; 104 dangling endpoints and 16 collapsed directed pairs remain. Query vocabulary: `webhook forward billing`. Report: `graphify-out/c12-secure-setup/GRAPH_REPORT.md`; query: `tmp/c12-setup-after-query.txt`. PowerShell is represented structurally only where supported; its parser/synthetic checks provide execution evidence.

Next action: authorize this single execution scope or specify a scope correction. Enter credentials locally only after authorization.

Set `$PreparedPython` to your prepared Python executable before the Uvicorn example. Source: [checkout migration](../supabase/migrations/20261025020000_razorpay_checkout.sql) and [GST migration](../supabase/migrations/20261025030000_billing_gst_payable.sql). Obtain the private execution record from the owner before operational use. Disabling billing ingress/workers stops new admission, not provider obligations. Never drop ledger/history records as rollback.

- `20261025020000_razorpay_checkout.sql`: canonical-LF SHA-256 `d53c967f0353177105339ddbc06f54f84f53cb39c972800ab91a33425a7a49c1`.

Cleanup-only recovery retains private immutable `cleanup-database-<sha256>.dump` snapshots beside the existing session budget when pending reconciliation fails. Bytes are published before the atomic journal pointer changes; failed pointer updates preserve the previous snapshot. Earlier fixed-name snapshots remain readable only when their recorded digest matches. Unreferenced snapshots are private recovery leftovers, never public evidence. `--cleanup-only --pg-bin <prepared-runtime>` restores only this verified synthetic snapshot into a newly disposable local runtime, reuses the billing service's pending/reconcile operations and preserves the original provider counters. Missing or mismatched snapshots remain blocked; no new checkout intake is opened. The snapshot contains synthetic billing state/provider references, is not public evidence and must never be committed. Older sessions without a snapshot cannot be reconstructed by guessing. Unresolved process cleanup remains separately blocked.

- `20261025030000_billing_gst_payable.sql`: canonical-LF SHA-256 `a726445fc1f9c052ffd6c9c76f663743840a9bb73a4aa94cc024ef06bd59696b`.
