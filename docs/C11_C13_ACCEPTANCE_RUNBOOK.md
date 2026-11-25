**Lint follow-up, 27 October 2026:** The frontend lint command now passes with 0 errors / 12 warnings; older 60/29 failure statements below are historical. Broader Node tests retain two pre-existing gRPC failures. [Exact results and remaining diagnostics](FRONTEND_LINT_CLOSURE_20261027.md). Other C11/C13 gates remain open.

# C11/C13 acceptance: isolated package and staging

**Latest verified status - 26 October 2026, 17:03 IST:** [Staging application acceptance](C13_2_STAGING_APPLICATION_ACCEPTANCE.md) passed all 11 scenario groups against cfmvqbjmnwklxqlpelxe using two isolated local workers and real staging Auth/JWT/Storage. Repeated audits verified 42 allowance periods; cleanup verified all five roles closed/passwords cleared/zero sessions. No migrations or accepted physical tests were repeated. Public HTTPS/WSS, signed installed Windows, deletion approval and the existing lint gate remain separate; C11/C13 remain open.


Updated 25 October 2026. This runbook reconciles the existing fixed gates; it adds no
commercial policy or C11 exit criterion. [Policies](SUBSCRIPTION_APPROVED_POLICIES.md)
and [evidence](C13_2_IMPLEMENTATION_EVIDENCE.md) remain authoritative.

## Current status — 25 October 2026

This is the authoritative current summary. The historical session records below
and in [physical results](C13_2_PHYSICAL_ACCEPTANCE_RESULTS.md) remain unchanged.
Do not repeat accepted physical timing/JBL checks unless a subsequent change
affects them. No new C11 exit criteria are introduced.

| Requirement / existing gate | Latest evidence | Remaining gap | Exact next action |
| --- | --- | --- | --- |
| Catalog, immutable bindings, feature gates and admin | Accepted catalog/admin tests retained; latest account/relay native run: 69 passed, 1 browser case deselected, 170.91s | Shared deployment unverified | Execute approved target-specific staging acceptance; do not reopen catalog implementation |
| Physical mic/system/Both, Stop and sleep | Existing operator/native passes retained; Both charged once; Stop and sleep stopped capture | Other devices/drivers and signed installation are not inferred | Use installed release checklist once signed artifact/test environment is available |
| Synchronized silence timing | 120-second synchronized trial: 120497561 microseconds settled, exactly equal to native SQL authorized interval and inside independent monotonic bounds with predeclared 50ms tolerance; indicator off | No outstanding local timing discrepancy for this trial | Retain evidence; do not repeat phone-stopwatch trial |
| JBL Bluetooth disconnect/reconnect | Captured JBL identity confirmed; track ended and disconnected, indicator disappeared; reserved zero; 69.553626 seconds unchanged while stopped; reconnect produced no tracks/authorization; logout API 401 | Other Bluetooth drivers, USB hardware and signed installation not proven | Retain this device-specific pass; do not repeat accepted trial |
| Lease expiry/restart/logout | Existing native/operator passes, same-account restart retained use, no auto-resume; final JBL session private API 401 | Installed/deployed lifecycle not proven | Run installed/staged equivalents after external prerequisites |
| Near-exhaustion residual | Physical 23082us residual with expired Start retained. Native actual relay test preserves unused tail/stopped balance, then holds an explicit synthetic silent authorization until its SQL deadline and verifies genuine exhausted denial with no new STT | Tiny remainder need not support safe capture; it is not forfeited or rounded away | Use current-plan balance; wait for normal period reset if residual cannot authorize capture. Never auto-loop new Starts or force zero |
| Hosted relay/shared coordination | Default-off Electron main/preload/compiled renderer now uses the authenticated relay for mic/system/Both through the existing PCM/answer client. Two packaged clients/two workers, durable answers, Stop, worker death/capture cleanup and deliberate recovery passed. Backend one-use stream claim rejects duplicate connection replay without stopping the original owner | Unsigned packaged hosted physical mic/system/Both, Stop/track cleanup and final logout 401 are now operator-observed; deployed WSS/TLS and signed installation remain unverified | Retain completed hosted physical and local timing/JBL evidence. Await an approved isolated staging target before remote preflight; then accept deployed WSS/TLS |
| Account deletion/immutable ledgers | Closed idempotent preparation barrier stops active runs; private API/RLS/storage denial, rollback, uncertain-commit replay and concurrent retries tested. Immutable records/Auth RESTRICT retained | Irreversible content purge and identity unlinking intentionally absent; retention/unlink decisions missing | Review concrete retention proposal below before authorizing purge implementation |
| Repository lint | 60 errors / 29 warnings; no new error rule/message pairs vs recorded HEAD attribution. Changed-file lint passes | Existing repository lint gate still fails | Owners resolve attributed pre-existing errors in separate scope; do not disable rules |
| Development/package vs signed installation | Unsigned compiled-file Electron physical sessions passed, including latest JBL interactive wrapper 1 pass / 47 deselected, embedded Playwright 2 pass (1206.25s) | Signing credentials/approved signed artifact and isolated Windows installation environment not supplied | Supply those dependencies, then execute existing installed/OS checklist |
| Isolated staging | 48 prior migration hashes verified; additive relay/privacy candidate makes 50. Read-only object/ACL/history preflight prepared | Owner now designates disposable cfmvqbjmnwklxqlpelxe; owner preflight complete: empty application schema; target-specific guarded 50-source bootstrap prepared for approval | Review the exact target-specific SQL/hash, Storage/ACL/history scope and recovery choice; approve before application |

The old 120s phone observation versus 129.233757s ledger and first ambiguous
Bluetooth indicator observation are historical, superseded only by the controlled
trials above. Signed/installed, hosted and production acceptance remain separate.
No shared database, real assignment or activation occurred.

## What has actually passed

The [hosted relay/privacy review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md)
specifies the implemented desktop/relay protocol, remaining physical/TLS acceptance,
least-privilege SQL/hash, staging approval prerequisites, safe rollback,
and the retention/unlink proposal. It is not permission to deploy or purge.

Development Electron means `electron.exe` runs the repository main/preload.
Packaged Windows here means an **unsigned portable win-unpacked .exe**, containing
`app.asar` and a compiled renderer loaded from `file://`; it is not an installed,
signed NSIS release. The package deliberately uses the test-only
`electron-subscription.cjs` entry point: isolated encrypted userData, synthetic
Auth, no protocol registration, recorded external-browser intent. The shipped
main/preload and account services are reused. This is packaging/IPC evidence,
not unmodified installer/OS integration acceptance.

The native harness uses a task-owned PostgreSQL 17 cluster, restricted application
pool, real JWT verification, synthetic accounts and deterministic providers. The
bridge calls the real ASGI handlers in process; it is not a deployed HTTP/TLS
server. No captured audio is saved or transmitted to a real provider. The physical
setup leaves the actual device service intact but substitutes STT (discarding PCM)
and generation. No `.env` file, normal service or real account is modified.

## Fixed-gate reconciliation

All native case names below are in `backend/tests/test_subscription_integration_native.py`
unless another file is given. Native pass evidence is local, never shared acceptance.

| Existing gate | Exact pass criterion / current evidence | Status and next action |
| --- | --- | --- |
| Plans in DB / immutable history | `test_bound_history_survives_offer_replacement_and_retirement` in `test_usage_store_native.py`, catalog/lifecycle native tests: identical historical bytes after replacement/retirement, CAS and exact review binding | Locally satisfied. Repeat restricted-role/schema/history checks on approved staging; do not reopen catalog implementation. |
| Trusted subscription state | `test_current_api_bootstrap_and_cross_account_denial`, `test_verified_payment_preserved_bootstrap_and_expiry`, scheduled paid-period tests: exact pinned Free, paid preservation, expiry/schedule, unknown authority unavailable | Locally satisfied for approved Free/paid/end-of-period policies. Trial/past-due/refund/proration not invented. Real payment verification remains C12. |
| Backend gates | Native manual, Sketch, Screen, resume, Clipboard, auxiliary and Auto cases: Free/Plus/Pro finite/unlimited/denied; no provider on denial; durable replay cannot dispatch/debit | Locally satisfied for reviewed canonical paths; unreviewed transports closed. Default-off hosted relay/shared-state implementation is locally tested; new hosted physical device and deployed acceptance remain open. Do not enable hosted capture merely to run a test. |
| Current plan / client parity | `test_account_browser_real_jwt_native_database`: actual JWT account projection, real main/preload, current plan, Upgrade intent, transcription, logout; unit tests cover stale account responses | Development and unsigned-package smoke passed. Human must complete device checklist; signed installed release/real browser handoff not proven by recorded external intent. |
| No real payment dependency | Native providers are deterministic; checkout false, paid unlock requires trusted backend event, not UI state | Locally satisfied. Staging egress must explicitly block payments/providers; C12 is separate. |
| Safe initial Free / central transitions | Bootstrap duplicate/paid-preservation, `test_upgrade_keeps_consumed_monthly_allowance`, `test_scheduled_paid_period_change_preserves_usage_and_retries`, IST tests | Locally satisfied for synthetic accounts, not real assignment/backfill approval. Target config pins exact immutable Free and verification cutoff. |
| C11.1 ownership / boundaries | Native cross-account/role/turn/replay/pool tests plus `test_commercial_admission.py` exact-route denial tests | Local evidence retained. Historical combined-process failure was 234 pass/1 fail. The import-safety test now loads identical source in an isolated module, retaining all guards/assertions; the exact combined process passes 235/235. Target JWT/TLS/proxy/RLS/EXECUTE and each enabled transport need staged evidence. |
| Admin permission / write integrity | Draft/lifecycle native and browser cases: ordinary-user 404, backend denial, revocation before replay, CAS, retry identity, exact reviewed version | Locally accepted; no real grants touched. Staging uses disposable synthetic admin/ordinary subjects and original audited bootstrap/revoke procedure. |
| Existing deployment gates | Intended project/schema/history, restricted roles, no actor leakage, bounded pools, exact ingress, TLS/JWT, policy and catalog approval | NOT executed. An explicitly approved isolated staging target and precise preflight-derived change set are required. |

Additional C13 acceptance: native Auto tests cover independent workers, silence,
Both once, Stop/disconnect/expiry/exhaustion; Screen covers classification, saved
results, cancellation/revocation/replay; resumes cover initial history, failed
replacement, concurrency and retained over-cap files; Clipboard covers exactly-once
committed saves; Notes/Ask/history/export remain unmetered with ownership. These
are not substituted for the physical checks below. Account-wide Auth deletion
against immutable RESTRICT ledgers is a separate unresolved technical privacy gate;
logout cleanup is not deletion acceptance. Do not delete real users to test it.

## Build and start the isolated physical setup

From a PowerShell terminal at the repository root:

```powershell
node frontend/scripts/prepare-subscription-acceptance.cjs
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
$pgBin='C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin'
& E:/deepfake_envs/SaIIA/python.exe backend/tests/run_subscription_acceptance.py --pg-bin $pgBin --physical
```

Prerequisites: existing npm dependencies, retained PostgreSQL runtime and psycopg
packages above, Windows PyAudioWPatch, working Windows microphone/default output.
`--physical --smoke` verifies package/panel/backend startup and exits without opening
a microphone or running loopback capture. Add `--capture-smoke` to open real
microphone, system and Both sequentially, assert PCM delivery and Stop, then exit. Omit `--physical` for automatic packaged
JWT/current-plan/IPC/logout smoke. No external server/database URI is accepted by
this launcher. It creates a fresh cluster, synthetic account and encrypted temporary
session. Physical-mode synthetic JWTs are bounded to one hour, aligned with
the 58-minute harness; ordinary short-lived auth tests are unchanged. Normal ports 5173/8000 and normal Auth remain untouched. Playwright owns
5186 and chooses loopback backend/gRPC/PG ports. If 5186 is occupied, stop only the
owner you recognize; the harness fails instead of reusing another service.

The package appears with the **Isolated physical acceptance** panel. Its buttons
use the original `createGrpcAutoSession`, microphone WebAudio capture, main IPC,
gRPC and actual backend loopback capture. They are test-only controls injected by
Playwright, not application entitlement bypasses. Saved terms are unchanged Free.
No synthetic transcript of your actual speech is produced: STT discards bytes.
Use safe counts/levels and native balances as evidence, not actual audio content.
The session lasts at most about 58 minutes; the harness tears down owned processes
and temporary userData afterward. Retained runtime downloads/package are preserved.

## Numbered physical checklist (HUMAN REQUIRED; not marked passed)

Record Windows build, input/output device names, package SHA256, time/plan balance
before and after, redacted screenshots of status and exact pass/fail. Avoid personal
speech/content and tokens. Read current plan/usage only while idle when comparing
settled balances; an active lease can reserve a bounded next slice.

1. Click **Read current plan / usage**. Expect the synthetic Free plan and finite
   daily Auto balance. Screenshot this starting balance. All main/Upgrade/logout
   smoke assertions have already run automatically before the panel appears.
2. Click **Start microphone**, permit mic access, stay silent for ~10 seconds,
   then **Stop**. The Windows capture indicator must end, and settled used time
   must advance for running silence. Speak only a neutral test phrase if checking
   non-zero levels; **Read safe status** shows metrics, never captured words.
3. Click **Start system**, play a local test tone, then **Stop**. Expect actual
   WASAPI loopback metrics and completed cleanup; no network provider call.
4. Click **Start both**, speak a neutral phrase and play a tone together. Stop
   after a measured interval. Both sources must be active; usage advances for
   elapsed running time once, not twice. Stopped time must not consume allowance.
5. While one run is active, in a second terminal execute:
   `Set-Content tmp/c132-physical.stop.control 'compete'`.
   A second packaged process with separate userData attempts the same account;
   the test expects `subscription_auto_busy`, closes only that client, and reports
   denial. Record the console result. Do not send this command while the first
   run is idle: that deliberately fails the concurrency assertion.
6. While active execute `Set-Content tmp/c132-physical.stop.control 'expire'`.
   The test-only wrapper stops its 5-second heartbeat timers. Within the server's
   maximum 15-second authorization window plus device cleanup, forwarding must
   stop; status reports expiry, and usage never exceeds authorized expiry. Take
   status and idle balance screenshots. This is heartbeat fault injection, not a
   demonstration that a renderer timer controls authorization.
7. Click **Stop** after the prior expiry, start a new run, then execute `Set-Content tmp/c132-physical.stop.control 'restart'` while active.
   Playwright terminates only its packaged process and relaunches it with the
   same isolated userData and still-running native backend/database. Verify no
   old capture resumes, Current plan remains authoritative, and previously used
   allowance is retained. A new run may be temporarily busy until old authorization
   settles/expires. This exercises abrupt client disconnect/restart, not an OS sleep
   or backend process crash. Capture fails if it silently falls back to unmetered work.
8. Repeat Steps 2-4 after unplug/replug of the selected device and after Windows
   sleep/resume. The device indicator and forwarding must stop on failure; a stale
   owner cannot silently extend its lease. Capture/report hardware-specific errors.
9. For physical exhaustion, run the synthetic Free account for its remaining daily
   budget, including silence. At exhaustion all capture/forwarding must stop;
   another Start must be denied. Record final balance/status. Do not alter a real
   allowance to shorten the test. Automated native tests separately preconsume a
   synthetic budget and verify last-unit accounting deterministically.
10. Click **Logout and stop** during capture. Audio must stop, account-owned state
    must clear, and current-plan requests must no longer succeed. No other account
    can reuse the old capability. Actual Free/Plus/Pro transition/isolation and
    stale-response cases have native/Node evidence; manually switching real accounts
    is not authorized by this harness. Screenshot only the logged-out state.
11. End the harness with `Set-Content tmp/c132-physical.stop 'done'`. It checks logout
    again and closes owned servers/cluster/package. `Ctrl+C` is emergency stop;
    inspect owned process handles if interrupted before finally cleanup completes.
    Restart with the same launch command for a **new** disposable cluster/account;
    use Step 7, not a new harness invocation, to verify usage survives desktop restart.

Short real-device capture/Stop smoke has passed on this machine: Realtek microphone
array, Realtek speakers, one WASAPI loopback device. **The first combined/Both
attempt timed out at the unchanged 15-second PCM assertion; a subsequent complete
mic/system/Both attempt passed.** The test panel could start the next source before the prior asynchronous Stop
finished, leaving the new Start ignored. Controls now serialize actions and
Playwright waits for action completion; the synchronized three-source run passed
(25.76s native wrapper, embedded Playwright 2 passed). Original failed attempts
remain recorded. Long-duration/device-change reliability still requires the
operator checklist; the synchronized smoke does not establish it. This is not silence,
long-duration exhaustion, unplug/sleep, or manual acceptance. No assertion was
weakened and no provider received PCM. Earlier runs with dropped launcher flags
were development Electron only, superseded by the explicit packaged/file-URL
assertion run. The launcher restores only its synthetic C132 options after the
offline environment boundary; it does not preserve real provider/config secrets.

No checkbox is automatically closed by running setup. Installer signature,
protocol registration, real external-browser opening, backend crash/power failure,
physical account-switch UI and hosted relay remain separate acceptance. The
fixture intentionally intercepts the browser destination instead of opening it.

## Lint investigation

The initial 853 errors included 784 generated-bundle errors. `dist-electron` is
now excluded alongside `dist`; no source rules were disabled. Fixed nine actual
subscription catalog/pricing issues: four obsolete pricing image imports, two
unused bindings, and three control-character regex sites. One shared character
predicate preserves all 0-31/angle-bracket rejection; a regression covers every
ASCII control plus Unicode display text. Full source lint still fails with
**60 errors / 29 warnings**. All remaining error rule/message pairs match linting
`git show HEAD:frontend/<file>` using the current config. The attribution artifact
is [C13_2_LINT_ATTRIBUTION.json](C13_2_LINT_ATTRIBUTION.json). This is evidence of
pre-existing errors, not permission to disable rules or claim the lint gate passed.

## Isolated staging: preflight, approval, application and rollback

**No staging target is selected/connected in this task.** Do not reuse Saiia-dev or
customer accounts. Exact unapplied migrations cannot be truthfully listed without
that target's history AND schema; repository versions alone do not establish it.

1. Environment administrator supplies an empty/disposable **isolated staging**
   project identifier, owner, PostgreSQL version and rollback snapshot. Confirm
   it has no real customer accounts/offers, no payment/provider egress, and can be
   destroyed. Keep activation off. Confirm normal/production secrets are absent.
2. Run [read-only preflight](sql/C11_C13_STAGING_PREFLIGHT.sql) in its SQL Editor.
   Return only history/object/role/function-ACL output, never credentials, JWTs or
   connection strings. If history is absent, stop for format/schema inspection.
3. Compare results with [ordered 50-candidate manifest](sql/C11_C13_STAGING_MANIFEST.json).
   It includes only cloud/session prerequisites and catalog/usage additions, not
   unrelated email/marketing/onboarding migrations. `MISSING_HISTORY_REVIEW_SCHEMA`
   is a review candidate, NOT an instruction to apply. Inspect objects and original
   SQL/recorded statements before classifying unapplied versus drift. Check hashes
   against repository files and stop on mismatch. Original migration bytes remain
   unchanged. Existing objects without history require deliberate repair review;
   never replay a CREATE ROLE/table batch blindly.
4. Produce a concrete target-specific approval packet: target ID, ordered missing
   filenames/versions/hashes, prerequisite/drift result, exact SQL copied from those
   files, ACL changes, synthetic account IDs, rollback and immutable-data impact.
   Request approval for THIS packet. Do not run the old core batch again: its prior
   application is user-reported and its baseline guard intentionally rejects reuse.
   No migration command/hosted activation is authorized until this packet is approved.
5. After approval only, environment administrator applies each exact reviewed
   source file in manifest order through the approved migration runner, with
   ON_ERROR_STOP, bounded waits and preserved migration-history records. Use
   `psql -X --set ON_ERROR_STOP=1 --file <approved-file>` with credentials in secure
   service/password storage, never command text/logs. Review transaction boundaries
   already present in SQL; do not blindly wrap nested BEGIN/COMMIT or record a failed
   migration as applied. In SQL Editor use the exact approved batch with audited
   history recording. Re-run preflight after every failure before continuing.
6. Runtime identities must remain exactly the accepted roles: `usage_executor`,
   `catalog_draft_executor`, `catalog_public_reader`; no superuser, BYPASSRLS,
   CREATEDB/CREATEROLE/REPLICATION, memberships or direct private-table privileges.
   Shipped roles are NOLOGIN. If staging approves direct LOGIN provisioning, use
   the existing exact executor role plus prompted secret (`ALTER ROLE <reviewed-role>
   LOGIN;` then psql `\password <reviewed-role>`), not a member/wrapper role that fails
   pool identity checks. Binding/reconciliation authority stays server-controlled;
   do not grant it to Auth users, catalog admins or service-role gateway clients.
   Do not broaden EXECUTE when a missing migration caused a pool check failure.
7. Configure process-only staging secrets: `SUBSCRIPTIONS_DSN`, `SUBSCRIPTIONS_ENABLED`,
   `CATALOG_DRAFTS_DSN`, `CATALOG_DRAFTS_ENABLED`, `CATALOG_LIFECYCLE_ENABLED`,
   `CATALOG_PUBLIC_DSN`, `CATALOG_PUBLIC_ENABLED`, verified Supabase Auth URL/key and
   JWT project configuration using the existing secret store. Keep all flags false
   initially. Runtime startup preflights enforce schema/ACLs, exact role and bounded
   pooling; PostgreSQL 17 transaction timeout support must match tested composition.
8. Use a separate staging Auth tenant with ephemeral synthetic admin, ordinary,
   Free/Plus/Pro subjects and known UUIDs; record verification/signup times. Use only
   the existing audited admin bootstrap for temporary `subscriptions.manage`.
   Create synthetic uniquely named drafts through import/save/reopen/preview/review/
   lifecycle, with explicit versioned test policy and exact synthetic immutable Free
   binding configuration. No arbitrary Free lookup or existing-account backfill.
   Paid transitions use trusted fixture events only, never a customer/admin API.
9. Before any enabled route is accepted, repeat the runbook's named native cases as
   staged equivalents with real staging JWT/HTTPS and two workers: current-plan/
   ownership, revocation before replay, CAS/conflicting retry, result checkpoint/
   settlement recovery, pool identity reset/exhaustion, exact method/path ingress,
   ordinary-user 404/backend 403, no-store/private DTO and no outbound provider/payment.
   Capture redacted HTTP status/error code, migration/hash/role proof and count deltas.
   The local runner ALWAYS creates PostgreSQL locally; it does not accept a staging
   DSN and must not be described as a hosted acceptance runner. Staged automation/
   actual relay must be reviewed against the approved deployment, not guessed.
10. The new hosted WS relay/shared coordination is implemented and isolated-native
    tested, but default-off. Follow the protocol/deployment packet below; TLS/proxy,
    new hosted physical client checks and actual staged multi-worker acceptance
    remain prerequisites. Legacy WS/gRPC and unknown/alias routes stay denied.
11. Rollback: close intake/flags first, stop capture, reconcile outstanding bounded
    leases/results, and retain ledgers/bindings/history for recovery. Restore compatible
    code/config; do not drop accounting tables, reset balances or rewrite snapshots.
    Use the staging snapshot/destroy the whole isolated project if schema rollback
    is required. Never use destructive down-migrations against shared/customer state.
12. Cleanup: revoke synthetic admin access through existing audited procedure,
    stop pools/workers and revoke approved LOGIN credentials, retain redacted evidence,
    then destroy disposable staging. Do not remove immutable rows to make Auth-user
    DELETE succeed: RESTRICT/privacy lifecycle needs reviewed handling. No real
    account deletion/subscription assignment is part of this test lifecycle.

## Repeatable non-physical backend acceptance

Use the existing runner with `--backend` as documented in the [review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md#repeatable-local-automated-checks). Final run: 50 passed, 104.70s, exit 0. No Electron/capture or accepted physical checks are opened by this mode.

## Exact remaining actions

| Gate | Required next action |
| --- | --- |
| Physical Windows | Retain accepted mic/system/Both, synchronized timing, sleep/expiry/restart/logout and controlled JBL observations. Do not repeat those checks without an affecting change. USB/other drivers remain unverified, not substituted by JBL evidence. |
| Signed installed Windows / OS behavior | Supply/build an authorized signed installer in isolated Windows test user/VM; run device, protocol/external browser, sleep and upgrade/uninstall checks. Unsigned portable smoke does not satisfy it. |
| Repository lint | Owners resolve the 60 proven pre-existing errors (or authorize that separate cleanup); keep current rules and rerun full lint. Subscription regressions identified here are fixed. |
| Historical combined-process isolation | Resolved locally: exact original four-suite process passes 235/235. Historical failed runs remain recorded. |
| Target database / hosted | Identify an isolated staging target and return read-only preflight results; then approve the exact diff/roles/configuration packet. No shared execution performed. |
| Hosted audio relay | Desktop hosted integration and native/packaged execution are tested. Finish newly prepared physical hosted source checks and approved TLS/staged two-worker acceptance; activation stays off. |
| Account deletion / immutable ledger | Preparation/access barrier is locally tested. Review the explicit proposed durations/identity decisions in SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md before irreversible purge; preserve RESTRICT and immutable events. |

Overall C11/C13 and full C13.2 release acceptance remain open. No real payments,
provider calls, subscription assignments, production enablement, commit, push or
deployment is performed by this runbook or its local setup.


## New desktop hosted physical checks (accepted local trials are retained)

The maintained command `run_subscription_acceptance.py --pg-bin <local-pg-bin> --hosted --physical`
opens an unsigned isolated packaged window backed by two independent loopback relay workers,
a disposable native PostgreSQL cluster, real device APIs and synthetic providers discarding PCM.
The title identifies hosted physical acceptance; no synchronized 120-second button is offered.
No fake media is enabled in this physical mode. The stop procedure remains
`Set-Content tmp/c132-physical.stop (Get-Date).ToString('O')`.

Guide one action at a time: initial plan/usage baseline; authorized mic Start/status then Stop;
Windows system loopback Start/status then Stop; Both Start/status then Stop; capture/forwarding
cleanup after logout. Only these newly changed hosted OS boundaries need operator observation.
Do not repeat the accepted synchronized timing or JBL unplug trial merely to fill a checkbox.
Record source identity, indicator/status/track changes, PCM delivery and zero settled reservation.
Physical hosted lease/network failure remains separately observable with the existing isolated
fault controls; automated two-worker/crash/fencing/recovery evidence does not become a physical pass.
The current window was prepared at 11:32:13 IST, 25 October 2026; its one-hour synthetic Auth
and 58-minute wrapper are bounded. Never infer results after expiry or reset a balance to continue.

Staging owner response: no isolated project exists yet; do NOT connect to Saiia-dev or apply
remote changes. Keep the target-specific unapplied list UNKNOWN until a new reference ID and
explicit disposable confirmation are supplied. The review packet remains ready for that preflight.


### Staging target designated ? 25 October 2026

Owner confirms **intervucopilot-staging / cfmvqbjmnwklxqlpelxe** is newly created,
disposable and contains no real customer accounts/data; authorizes **read-only
preflight only**. This supersedes prior no-target statements, not migration or
activation approval. No authorized connector/browser session was available; owner
will run the target-specific SQL Editor preflight. Exact unapplied migrations and
compatibility remain unknown pending results. See the [target review packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md).
All 50 candidate hashes were verified locally; none is presumed unapplied.
Accepted local/hosted capture evidence is preserved. Signed installation and
irreversible deletion-policy approval remain open; no remote changes occurred.


### Hosting retention feasibility and staging result ? 25 October 2026

Owner-returned read-only preflight confirms PostgreSQL 17.11, no migration history,
no public application structure/executor roles and all 24 checked application
objects absent. pgcrypto/uuid-ossp installed; vector available but not installed.
No remote writes or activation. Plan-tier/PITR/backups/log drains/storage inventory
were not included and remain unverified. The deletion proposal now explicitly
states 24h/90d/180d/30d are unapproved objectives, not verified guarantees. Current
immutable plaintext ledger UUIDs cannot expire at 90d by deleting an Auth mapping;
a reviewed bounded-retention design or a revised permanent-retention decision is
required. Separate audit/replay-marker/deletion-evidence/backup rules remain pending.
See [hosting feasibility and immutability analysis](SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md#hosting-feasibility-review--25-october-2026-not-policy-approval).
Accepted local/hosted physical capture evidence is preserved; no tests repeated.


Hosting evidence update (25 October 2026): owner reports staging Free Plan and
Backups page says project backups not included. PITR unchecked; log retention/drains,
external backups and backend/frontend hosts unknown. Placeholder template entries
are not confirmations. No absence-of-copies or deletion-deadline claim is made.
See the updated deletion proposal and target review packet for recovery preparation;
no included-backup rollback is assumed. No remote writes, purge, activation or
repetition of accepted physical tests occurred.


### Target-specific staging application packet ready - 25 October 2026

Confirmed target **intervucopilot-staging / cfmvqbjmnwklxqlpelxe**, disposable with
no customer data. Owner confirms Free, scheduled backups not included, PITR not
enabled, frontend/backend local only (neither deployed). Log TTL/drains/external
backups unknown. No absence-of-copies/deletion-deadline promise.

Owner-returned preflight establishes no history, no public application structure,
no executor roles and all 24 checked application objects absent. The complete
fresh-schema integration needs the 50 dependency-ordered repository sources;
this is reconciled with schema evidence, not a blind pending-manifest inference.
Pgvector is NOT required; base vectors are JSONB. Earlier vector prerequisite is
superseded. See [review and acceptance packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md),
[ordered original hashes](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_MIGRATIONS.md),
[guarded approval-only SQL](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_APPLICATION_PENDING_APPROVAL.sql),
[exact ACL clauses](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_ACL_REVIEW.txt) and
[read-only postflight](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_POSTFLIGHT.sql).

Batch SHA256 `b5a26cf185cb70d66230376176b966edab50883cb66dfc9e8e0ef4c660e0d3fb`.
Includes explicitly reviewed history initialization, base RLS/Storage buckets,
catalog and usage/result/relay/privacy-preparation schema. No seeds, LOGIN changes,
human grants, subscriptions, activation or irreversible deletion.

Native exact-batch verification PASS: all 50 sources, original source hashes and
stored source text checked, atomic rollback after late injected P0001, five closed
roles and relay ACL, zero bindings/offers/config/policies/usage, read-only
postflight, and replay guard. Log `tmp/c132-exact-staging-batch-native.log`;
checker `backend/tests/check_staging_packet_native.py`. Supabase platform interfaces
are explicit minimal local fixtures; managed-owner privileges/network/hosted TLS
are NOT inferred. Scoped Black/Ruff pass; initial new-helper lint findings were
corrected without rule suppression. No frontend changes/build needed. No accepted
physical capture tests repeated. Repository-wide lint baseline unchanged/not rerun.

Next approvals: exact target+batch+Storage/ACL/history scope and recovery choice;
then separate direct-role credential provisioning/synthetic Auth/policies/local
staging composition; then selected host/budget/HTTPS/WSS deployment packet. No
assumed snapshot: approve encrypted export/restore or specifically scoped empty
project recreation before schema writes. Do not drop ledgers or platform internals.
Deletion durations and bounded-retention versus permanent immutability decisions
remain provisional. C11/C13 and hosted/signed release acceptance remain OPEN.


### Pre-COMMIT hardening and managed-owner checks - 25 October 2026

The prior count-only staging envelope is superseded by exact expected-version-set
assertion plus five closed-role/membership checks, private buckets, all 35 private
tables' RLS/direct ACLs (source-defined FORCE exception for publication policies),
23 exact function ACL/SECURITY DEFINER/owner/search-path checks, immutable triggers,
restrictive privacy barriers and zero seeded authority. No original migration,
permission, policy, fingerprint or commercial term was changed. Final batch SHA256
`926af0c4d71865bec91784c87071928639acc5a676ef794df20e3186ce144635`. Previous batch hash is no longer the approval target.

Final local checker PASS: 16 injected invariant violations fail pre-COMMIT with
full schema/history/role/bucket rollback; separate post-assertion late failure and
healthy full 50-source/postflight/replay checks pass under both superuser and
NOSUPERUSER migration-owner fixtures. Missing Storage-owner or existing BYPASSRLS
authority fails closed; no repair/broadening grant. PostgreSQL17 automatic creator
ADMIN-only metadata is checked explicitly (SET/INHERIT false); executors inherit
no role. The [read-only owner probe](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_OWNER_PREFLIGHT.sql)
is tested locally but still awaits actual target output. No remote SQL performed.

Read-only metadata cannot verify all managed platform hooks or actual policy DDL;
local fixtures are not target acceptance. Target migration-owner role attributes,
Storage inherited ownership and existing schema/Auth privileges must be reviewed
before execution. Do not change owner/BYPASSRLS/memberships to make the batch pass.
See [current packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md) and
[assertion source](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_PRECOMMIT_ASSERTIONS.sql).

Logs: `tmp/c132-precommit-final-native.log`, `tmp/c132-precommit-black.log`,
`tmp/c132-precommit-ruff.log`. Initial new-envelope false-positive on the later
private connection-claim table is retained in debug logs; assertions now match
unchanged source: this table has forced RLS/no direct client ACL and an authority
checking RPC, not the earlier migration's restrictive policy. No source policy
was removed or broadened. Black/Ruff pass. No frontend build needed for SQL/test/
documentation-only change. Accepted physical capture evidence is retained; no
repeat. Shared application/activation, deployment/signed acceptance and deletion
policy remain pending; C11/C13 are not closed.


### Supported Storage-policy mechanism found - 25 October 2026

The prior ownership-only interpretation is superseded: official Supabase
supautils policy_grants permits configured postgres policy DDL on storage.objects
without inherited table ownership. This is unrelated to BYPASSRLS/bucket DML.
Exact source review: base migration's four DROP/four CREATE plus one COMMENT;
privacy migration's restrictive CREATE; no ALTER TABLE storage.objects or owner/
RLS changes. COMMENT support arrived in supautils 3.3.0. Upstream configuration is
not proof of this project's installed settings. Owner's earlier result did not
include registered hook/version/config; actual managed behavior remains unverified.

Prepared minimal correction: early fail-closed existing-authority guard in the
atomic batch, read-only target hook metadata preflight, exact operator procedure,
and optional rollback-only restrictive policy probe requiring separate remote DDL
approval. No source migration or permission grant was changed; no split needed
if the documented existing hook is present. Do not change membership/ownership,
weaken RLS or substitute permissive barriers. See [procedure](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_STORAGE_POLICY_PROCEDURE.md).
Final current batch hash is recorded in [packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md); prior hashes
are superseded. Local exact-batch and new guard/probe tests are separate from
actual Supautils-hook/deployment acceptance. Accepted capture tests retained, no
repeat; no remote writes or activation occurred. C11/C13 remain open.


### Final evidence-backed Storage guard and consolidated approval - 25 October 2026

Operator's actual managed CREATE/COMMENT/DROP trial and separate cleanup are accepted
with unchanged owner/RLS and no probe policy. Registered configuration-file grant
is confirmed; version row absent. The final guard now accepts that specifically
reviewed postgres/current-session/Storage-owner/RLS context with the existing
registered grant, without inventing a version or changing privileges. Old/invalid
present versions, unregistered/changed settings, pending restart or a different
actor are not silently accepted. Target identity remains an operator Dashboard
check, not a fake SQL-derived project reference. No more target probes requested.

Final batch SHA256 `1c61333c737c1291c56a03112603af9ff5e09225755d5e73acdd5fbe8be17a24`. Replacing only its new authority guard with the previous
guard reproduces the exact prior f4fc28bc... batch hash. All other baseline,
transaction, source bodies/history and security bytes are unchanged; pre-COMMIT
assertion SHA256 remains f6e7873a5deb71d37ce64022e49159d7f60f317fc7751fcf735f36dd05f685ca.
All 50 original source hashes are unchanged; packet/hash/link checks pass.

Local exact-batch checker passes: healthy/postflight/replay and late-failure rollback
under both owner fixtures; 16 corruption/rollback cases; unsupported/no-hook and
missing-authority denial; fake GUC denial; nine temporary-metadata guard decision
cases (reviewed missing version and known supported version allow, seven negative
cases deny). These fixtures evaluate the actual DO predicate against synthetic
metadata, not a simulated positive Supautils execution. Actual managed behavior
comes from prior operator evidence. Log `tmp/c132-policy-evidence-guard-final-native.log`.
Black/Ruff pass. No frontend change/build needed. No accepted capture tests repeated.

Current [packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md#final-execution-and-one-consolidated-approval)
contains exact execution instructions and ONE consolidated approval covering
cfmvqbjmnwklxqlpelxe, final hash, all 50 sources/history/Storage/ACL/NOLOGIN schema
scope, and recovery A (operator-controlled encrypted export/verified restore) or
B (owner-led empty-target recreation if later necessary, no assumed backup).
Migration approval does not authorize services, LOGINs, human grants, offers,
subscriptions, deletion or deployment. No remote full-batch execution/activation
is authorized/performed; C11/C13 remain open. Existing postflight is required after
approved COMMIT, not a new pre-execution probe. Concrete failure/drift only triggers
further investigation; no additional operator test is being requested now.


### Post-schema staging activation packet ? 25 October 2026

The staging schema and postflight are accepted on operator evidence; do not rerun
the batch. See [C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_ACTIVATION.md](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_ACTIVATION.md) for the single
separate activation approval, exact temporary roles, synthetic identity/offer
scope, secure process configuration, test-source matrix and credential cleanup.
Preparation is not activation or a managed acceptance pass. No accepted physical
test was repeated. Public HTTPS/WSS, deletion policy and signed Windows remain
independent pending gates.
