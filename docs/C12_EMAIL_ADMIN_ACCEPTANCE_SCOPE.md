# C12 email/admin acceptance 01 — prepared, external execution NOT authorized

**Final inbox evidence:** both labelled test receipts appear in the owner's Gmail Inbox and both show Delivered in the supplied Resend dashboard screenshot. Executed results (owner-held private record `C12_EMAIL_ADMIN_01_EXECUTION.md`; excluded from this checkout) distinguish these observations from HTTP acceptance and the untested signed callback. Session remains stopped at 2/2 attempts; no new scope is implied.

**Later execution:** owner separately approved this exact scope; actual execution and cleanup results (owner-held private record `C12_EMAIL_ADMIN_01_EXECUTION.md`; excluded from this checkout) record two real Resend HTTP 200 acceptances and seven native admin passes. Session is stopped; its two-send budget is exhausted. Historical preparation/approval language below is retained as the reviewed scope, not a new authorization. Delivery/inbox confirmation remains distinct and C12 remains open.

26 October 2026. C12 remains open. This preparation does not reopen any Razorpay window, reset its counters, send support requests or change C11/C13 staging acceptance. No real email was sent. Historical implementation-pending wording in older execution records is superseded by local implementation evidence (owner-held private record `C12_BILLING_EMAIL_ADMIN_LOCAL_ACCEPTANCE.md`; excluded from this checkout), not by a claim of actual delivery.

## Established configuration and missing inputs

The billing dispatcher is `BillingNotifications` → `ResendBillingProvider` in `backend/app/email/billing.py`. It reuses C10 settings, request contracts, `outbound_email_events` and its durable claim/retry lifecycle. Actual billing sending is **HTTPS Resend API**, separate from Supabase Auth SMTP.

**Owner-confirmed setup, 26 October 2026:** `intervucopilot.in` shows **Verified** in the Resend dashboard. Supabase Auth already uses configured Resend SMTP for signup verification and password reset. These newer user-confirmed facts supersede this document's earlier missing-domain/SMTP-setup assumption and the old unchecked runbook setup status. They do not constitute this harness's observation of billing-email delivery. Leave SMTP, auth email templates/settings and DNS unchanged; no new domain or SMTP setup is required.

Inspected process configuration and root/frontend dotenv files for **presence only**: no `RESEND_API_KEY` or transactional `EMAIL_FROM`; only the separate `EMAIL_PROVIDER_MODE` field was present in root dotenv. No values were printed, files changed or unrelated credential stores accessed. No existing Resend-specific masked credential workflow was found in the inspected scripts. The new wrapper follows the existing process-only masked-entry pattern.

Confirmed allowlist recipient: **`acceptance-recipient@example.invalid`**. Confirmed send-only billing sender: **`billing@intervucopilot.in`**. The owner explicitly confirmed both and requested **Reply-To unset**. No mailbox/reply availability is claimed. Reinspection found no configured transactional `EMAIL_FROM` or `EMAIL_REPLY_TO` in the process/root/backend/frontend dotenv configuration and no available `RESEND_API_KEY`; no secret values were printed. No existing configured billing sender supersedes this newly approved sender. The separate marketing default is not billing approval.

No setup identity questions remain. A verified domain authorizes sending, not mailbox existence. Missing credential **`RESEND_API_KEY`** is entered through the prepared masked local prompt after scope approval, never in chat. Existing Supabase SMTP configuration does not make its secret available to this local FastAPI process. A synthetic verified `auth.users` binding in this isolated harness is not proof of a production account's verification.

Configuration follow-up checks: **10 transport/adapter tests passed in 0.68 s**; PowerShell parser **0 errors**. Existing seven-test native admin acceptance, disposable database and uncertain-send cleanup evidence was inspected and retained; not repeated. No implementation, migration, SMTP, DNS or dotenv change was needed. Graphify queries before/after preparation confirmed the existing dispatcher/transport paths.

## One execution scope, pending execution approval only

| Boundary | Exact scope |
| --- | --- |
| Runtime | Existing `E:/deepfake_envs/SaIIA/python.exe`; `backend/tests/c12_email_acceptance.py` through `scripts/c12_email_acceptance.ps1`; existing psycopg driver under `%TEMP%/c113c-db-driver`. No normal application service changes. |
| Database | A **new** native PostgreSQL 17.11 cluster under `%TEMP%/c112d-disposable-<unique>/data`, host **127.0.0.1**, ephemeral exclusive port, database **postgres**, disposable installer `catalog_test_owner`; application calls use existing restricted executors. Exact created directory/port/account are persisted before dispatch. No input DSN; no shared, staging or Saiia-dev connection. |
| Sender / recipient | Confirmed `EMAIL_FROM=billing@intervucopilot.in`; domain Verified is owner-confirmed. Exactly **acceptance-recipient@example.invalid** may receive both messages. **Reply-To unset**, as explicitly requested. No mailbox/reply availability claim. |
| Credentials | One `Read-Host -AsSecureString` prompt for `RESEND_API_KEY`; BSTR cleared in `finally`. Key passed only in child process environment, removed in Python **before** PostgreSQL subprocesses start; adapter holds it in process memory only. No key arguments, dotenv edits, clipboard, screenshots or logs. Process exit clears remaining process memory; no physical-memory zeroing guarantee is claimed. |
| Duration | **15 minutes from immediately before first external POST**. UTC/IST start/deadline persisted. Stop new sends at deadline; cleanup afterward. No automatic extension. |
| Real send budget | **Maximum 2 POST attempts total, including any retries; automatic retries = 0.** One synthetic initial Plus monthly receipt and one distinct synthetic renewal receipt, each INR 470.82 including approved GST once. Stop on first failure/unknown result; do not send a deliberate failure. No real cancellation/access-end message. |
| External endpoint | **POST https://api.resend.com/emails only**. No backend GETs, DNS setup, Resend domain/key creation, Razorpay access or delivery webhook configuration. Owner views existing Resend dashboard and owned inbox manually. |
| Local admin | Seven listed scenarios below, existing website fixture and native API/SQL authority; reconciliation/email failure transport remains deterministic. No provider-backed reconciliation execution. |
| Evidence | Fixed actual journal `tmp/c12-email-admin-01/execution.json`: counters, mode, UTC/IST times, recipient hash, exact ephemeral DB identity, notification IDs/snapshots/states, provider message UUIDs, idempotency identities, HTTP status/unknown result and cleanup. No headers/key/full recipient in journal. Owner separately records redacted dashboard delivery status and inbox/rendering observation for each UUID. |
| Cleanup | Stop dispatch, save notification state **before** disposing database even on failure, close HTTP session, remove credential references/process environment, restore default-off mail/billing flags, dispose only owned cluster and probe its port closed. Preserve journal. No retries or journal deletion after unknown/crash. |
| Exclusions | No public ingress/tunnel/database ports, remote SQL, actual Razorpay mutations/reads, real customer assignments, invoice system/PDF, refunds, discounts, upgrade charges, arbitrary entitlement/usage edits, support submission, live billing, deployment, commits or pushes. |

Sender/domain/recipient setup is confirmed, **not permission to execute**. One approval of this exact two-send scope is required before actual sending. Numerical budgets from stopped Razorpay sessions confer no authorization. No domain/SMTP/DNS approval or setup is requested.

## Runnable commands

From repository root, preparation only (no key prompt or external transport):

```powershell
& .\scripts\c12_email_acceptance.ps1 `
  -PgBin 'C:\Users\chand\AppData\Local\Temp\c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9\pgsql\bin' `
  -Python 'E:\deepfake_envs\SaIIA\python.exe' `
  -DriverDirectory "$env:TEMP\c113c-db-driver"
```

The same command **only after scope approval** adds `-ExecuteApproved -Sender 'billing@intervucopilot.in' -Recipient 'acceptance-recipient@example.invalid' -SenderDomainVerified`. This exact command omits Reply-To, as requested. It requests the API key through one masked prompt. Do not put a key in the command. The actual journal has a fixed name and exclusive creation; a restart refuses to reset or resume it. The wrapper mutex prevents overlapping instances. Direct Python execution similarly refuses an existing journal.

Local admin matrix, with no external transport:

```powershell
$env:PYTHONPATH = "E:\saiia_project\saiia_project\backend;$env:TEMP\c113c-db-driver"
& 'E:\deepfake_envs\SaIIA\python.exe' backend/tests/c12_admin_acceptance.py `
  --pg-bin 'C:\Users\chand\AppData\Local\Temp\c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9\pgsql\bin'
```

Website inspection reuses `frontend/tests/catalog/billing-admin.spec.js` and `billing-admin.playwright.config.js`: from `frontend`, run `npx playwright test --config tests/catalog/billing-admin.playwright.config.js`. It binds only 127.0.0.1:5293, refuses an existing listener, uses synthetic API fixtures, disables dotenv, has tracing off and shuts down its owned Vite process. Existing five browser checks and screenshots remain valid; no UI code was changed during this preparation. Browser fixtures prove presentation, not provider execution.

## Exact schema composition

Reuse `razorpay_local_runtime.local_runtime(..., billing_email=True)`; it now optionally resolves the existing `mail` fixture rather than adding a second bootstrap. Existing default billing runtime is unchanged. Its recursive fixture chain is the versioned authority for disposable auth/catalog/pricing/usage/C13/payment schema: `test_billing_native` → `test_subscription_integration_native` → existing usage/pricing/catalog fixture installers. This includes local synthetic auth/storage primitives; it is **not** a production/staging bootstrap recipe.

On that existing C11/C13/C12 chain, including `20261025020000_razorpay_checkout.sql` and `20261025030000_billing_gst_payable.sql`, the existing mail fixture installs exactly:

1. `20260904143000_add_outbound_email_events.sql`
2. `20260922120000_add_marketing_email_event_type.sql`
3. `20260924120000_fix_outbound_email_event_claim_ambiguous_user_id.sql`
4. `20261026010000_billing_notifications_admin.sql`

The last migration is unchanged: SHA-256 **C83D417D487F1E11A60B620E3B29AF9B4AEC044D70BD5198BF8268BE7E573C39**. Existing migration prerequisite checks fail closed. Synthetic role grants and recipient confirmation exist only in the fresh cluster. No remote migration is required for this scope. Operational rollback remains default-off workers/flags and retained durable evidence; no shared schema rollback is performed.

## Email and admin observations

Email: realistic signed **synthetic** Razorpay fixtures pass through existing backend payment verification and entitlement application, transactional source outbox and C10 dispatcher. Repeated event delivery creates no second payment event; distinct synthetic renewal has a separate business identity. The provider request contains both HTML and plain text, immutable plan/currency/period and integer-paise total. Subject/body prominently say **SYNTHETIC C12 TEST** / no new Razorpay payment. Queues begin empty and permit only the two payment kinds and one exact recipient. An unknown timeout stops intake; saved idempotency/event identity supports diagnosis without a blind resend. Definitive failure/retry/exhaustion remains substitute-only.

Track separately: queued → attempted → accepted; provider-dashboard delivered/bounced/rejected/unknown; owner-confirmed inbox receipt, spam placement and HTML/plain-text rendering. Provider acceptance is not inbox delivery. Manual dashboard evidence is sufficient for this bounded scope, without public callbacks; actual signed Resend callback acceptance remains a separate gap. Current [send reference](https://resend.com/docs/api-reference/emails/send-email) and [idempotency reference](https://resend.com/docs/dashboard/emails/idempotency-keys) checked during preparation: idempotency retention is 24 hours, not indefinite exactly-once delivery.

Admin matrix (existing native tests, synthetic identities, no Razorpay):

1. Unauthenticated 401 and ordinary/forged-role 403; durable permission denial; cross-account payment access denied.
2. Explicit billing-read/manage grants only in disposable fixture; inspection excludes contacts/secrets and makes zero provider calls.
3. Review binds exact actor/account/target/action/operation/current state; tampered operation rejected, stale revision rejected.
4. Concurrent identical confirmations produce one command. A replay of the same valid operation returns its idempotent existing result, **not a second execution**; altered/reused confirmation conflicts. Do not call safe idempotent replay a rejected HTTP response.
5. Eligible definitely failed notification can be retried through the existing worker. Unknown delivery cannot be retried; no deliberate real failure.
6. Reconciliation requested/queued is distinct from completion. Stubbed worker success, unknown timeout and revoked permission yield their actual local audit outcomes; no claim of provider execution.
7. Audit actor/action/target/outcome/time retained; pending ambiguous cancellation produces no confirmation email. Commercial overrides remain absent.

## Preparation results and recovery

- Native admin matrix: **7 passed, 27.67 s**.
- Transport-budget/allowlist/deadline/restart/redaction checks plus existing adapter/template tests: **10 passed, 0.75 s** final run.
- Two full standalone substitute runs succeeded: exactly two attempted/accepted fixture messages, no extra POST after repeated worker pass; PostgreSQL removed and port closed (`tmp/c12-email-preparation-01`, `-02`).
- Timeout-after-possible-acceptance run stopped after **one** attempt, source **unknown**, no renewal/retry; database removed/port closed (`tmp/c12-email-preparation-timeout`).
- Scoped Ruff checks/format and mypy passed; PowerShell parser zero errors. A Windows PowerShell native-stderr handling issue was found during wrapper verification and fixed to use the child exit code. **Final PowerShell wrapper passed**: two substituted sends, immutable amount/plan/period snapshots retained, credentials cleared, task-owned cluster removed and port **64525** closed. Journal: `tmp/c12-email-admin-preflight-a53977380cf94a91a370b34419aec906/execution.json`.
- No production source/UI changes; prior successful production build, browser and payment regression evidence retained rather than rerun without cause. No new real email, Razorpay or shared-database acceptance is claimed.
- Graphify queried before edits and rebuilt/queried afterward: 38 scoped code files, 610 nodes / 1,356 edges, zero semantic-model tokens. Extraction diagnostics report 244 dangling-endpoint edges and 27 collapsed directed endpoint pairs; graph is an incomplete navigation aid, not test evidence. Report/JSON/HTML remain in `graphify-out/c12-billing-email-admin/`.

The initial wrapper preflight aborted on Python startup stderr before its runtime was yielded. Its owned postmaster **14784** on **53281** was explicitly stopped with `pg_ctl -m fast -w stop`. Automatic approval review rejected recursive deletion; **stopped directory retained** at `C:\Users\chand\AppData\Local\Temp\c112d-disposable-7hr0utnu`. No email credential was loaded. Failed-preflight journal is preserved at `tmp/c12-email-admin-preflight/execution.json`. This retained directory is a cleanup exception, not a running service. Owner recovery, after verifying the exact path and no postmaster process: `Remove-Item -LiteralPath 'C:\Users\chand\AppData\Local\Temp\c112d-disposable-7hr0utnu' -Recurse -Force`. Do not delete other disposable clusters or reset journals.

Forced process termination/power loss cannot guarantee finally handlers run. Inspect the journal's exact directory, postmaster PID file and port before stopping/removing only that owned cluster; never restart sends after an uncertain attempt. Preserve counters and resolve the delivery outcome manually in Resend. If interruption happened during bootstrap before database identity was journaled, inspect creation time against the journal, as done for the exception above; do not guess another cluster.

## Remaining gates

The complete support draft (owner-held private record `C12_RAZORPAY_CANCELLATION_SUPPORT_DRAFT.md`; excluded from this checkout) is ready for owner review, unsent; all six cancellations remain unresolved. Four genuine Razorpay Test Mode payment/webhook/entitlement/account observations are preserved. Two real HTTP email acceptances and owner-confirmed inbox receipt are recorded above; signed delivery callbacks remain a separate unverified gate. Native admin/API and website fixture acceptance is local; actual provider-backed reconciliation remains untested. Actual provider recovery/renewal/expiry/max-term completion/fresh consent and installed Electron acceptance remain separate. Live seller/GST registration/customer-location/compliant tax-invoicing and activation prerequisites remain open; refunds/discounts/upgrade charges unavailable. C12 is **not complete**.

The bounded two-send scope is historical and exhausted, not a next-action authorization. Signed callback acceptance requires its separately authorized scope; do not resend these messages.

The `.invalid` recipient is a redacted placeholder, not a deliverable mailbox. Obtain the explicitly approved owned recipient securely from the owner and pass `-Recipient` / `--recipient`. Recovery must match the original journal digest. Historical examples do not renew approval or exhausted budgets.
