# Next subscription milestone: account authority and usage

**25 October 2026 current acceptance:** See the [single current-status table](C11_C13_ACCEPTANCE_RUNBOOK.md#current-status--25-october-2026) and [hosted relay/privacy review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md). Synchronized timing and controlled JBL disconnect/reconnect are accepted and not repeated. Default-off relay/shared coordination and deletion preparation are locally implemented/tested; irreversible deletion, released desktop hosted transport, signed installation and target-specific staging remain open. Native account/relay: 69 passed (one browser case deselected); final boundary/usage suite: 178 passed; Node: 172 passed; unsigned packaged JWT/browser/Electron smoke: wrapper 1 passed, embedded Playwright 2 passed. Existing full lint remains 60 errors / 29 warnings, no new attributed error pairs. No overall C11/C13 closure or production acceptance.

Latest acceptance follow-up: [gate reconciliation, packaged/physical procedure and isolated staging preflight](C11_C13_ACCEPTANCE_RUNBOOK.md). Packaged native 48 passed; combined-process 235 passed. Short real-device PCM smoke is separate from outstanding physical reliability/installed/hosted acceptance. See current evidence; earlier failed records remain historical.

**C13.2 continuation - local implementation evidence (24 October 2026):** The missing Auto mic/system/Both gRPC lease integration, durable Screen classification/results/settlement, resume capacity/initial-history/replacement/active-set/reindex paths, native Notes/Ask AI/history/export gates and client account cleanup are implemented default-off. Actual Windows Electron main/preload/renderer now passes native-JWT Current plan/Upgrade/logout and synthetic STT acceptance; packaged installed-device acceptance is separate. Native integration: **48 passed**, including two actual-native Playwright browser/Electron subcases. Backend regressions: **662 + 105 passed**; existing catalog/admin Playwright: **57 passed**, plus the separately mocked resume chooser. The [current evidence](C13_2_IMPLEMENTATION_EVIDENCE.md) records final native/check/build counts, exact migrations, transport boundaries and remaining limits. No shared changes or production activation. **C11/C13 remain partial; C13.2 release acceptance is not inferred from isolated tests or a failing repository-wide lint.**

23 October 2026. **The closed C13.1 backend foundation is implemented and accepted locally under the subsequent explicit user authorization; see the implementation evidence below. Production remains unwired.** This consolidates work under the established **C13.1 ledger/measurement** and **C13.2 enforcement/visibility** labels. C11 is pricing/subscription foundation; C12 remains payments. The original proposed scope below is retained as design history, superseded where the actual implementation record says otherwise.

## Acceptance and demo closure

The user reports manually testing and accepting the isolated subscription demo. This is **user-reported isolated manual acceptance**, separate from automated results and from shared-environment/deployment acceptance. The user's statement is not independent evidence of every security/race case.

The documented `Set-Content tmp/subscription-demo.stop (Get-Date).ToString('O')` procedure was executed. Runner PID 24900 and its launcher child 31556 exited; the ready marker disappeared. Port 5187 and disposable PostgreSQL port 49231 no longer listen; no `postgres.exe` processes remain. The runner log ended **1 passed, 1 warning**, after its long-lived fixture returned. Its own disposable directory was removed by fixture cleanup. Retained runtime downloads and unrelated files were not deleted manually. The in-process API/bridge exits with the runner; there is no separately deployed demo backend.

Normal listeners remain `::1:5173` (PID 38624) and `127.0.0.1:8000` (PID 34584). Shared databases were not contacted. The optional normal-frontend pricing preview depends on the disposable demo: after shutdown it cannot supply demo cards. This is not evidence that normal public-catalog composition is configured; no fallback cards or normal configuration changes were made.

| Requested follow-up | Actual source status |
| --- | --- |
| Draft Close/Discard | Implemented in `SubscriptionAdmin.jsx`, `closeDraft`: explicit local discard, saved record retained, preview/errors/prompts cleared, import focus restored; active/uncertain mutations block Close. Red close icon is present. |
| Review popup | Implemented by `SubscriptionReviewModal.jsx` and workspace/lifecycle callers. Customer preview and publication review stay distinct; native dialog, focus/scroll handling, receipt/retry state preserved. |
| Admin operating guide | Complete at [SUBSCRIPTION_ADMIN_USER_GUIDE.md](SUBSCRIPTION_ADMIN_USER_GUIDE.md); documents current controls, unavailable policies and deployment prerequisites. |
| Offer discovery | Implemented for currently visible offers with Open/Create draft version. Full private scheduled/retired history discovery remains absent; known-ID reads remain. |

Prior automated evidence is preserved, not rerun or relabelled here: 52 workspace/lifecycle Playwright tests, 14 focused Node checks, production build, and the real synthetic JWT/native-database offer-read/local-successor flow in [the latest verification record](PUBLISHED_OFFERS_ADMIN_VERIFICATION.md). Review-specific evidence is in [the popup record](SUBSCRIPTION_REVIEW_MODAL_VERIFICATION.md). Known broader browser/module-reload/PDF failures remain open as recorded in the audit. This planning task adds no new runtime-test acceptance.

## Source-verified foundation and remaining C11 gates

- `commercial/catalog_contract.py`, registries and approved Free/Plus/Pro reference JSON provide immutable versioned terms, explicit unlimited/denied/missing distinctions, prices and separate allowance periods. Reuse canonical validators, version dispatch and fingerprints; never rewrite old snapshots.
- `catalog_store.py`, draft/review/lifecycle services, accepted SQL and `catalog_database.py` supply restricted pools, verified actors, current admin grants, durable retry results, CAS, immutable terms and transactional audit. Publication policy resolution **is implemented** in `publication_policy.py`; actual approved production policy rows/validity/references and deployment acceptance remain prerequisites. Older statements that the resolver code is absent are historical.
- `admission.py` uses `ClosedAuthority`: there is no successful production entitlement/reservation authority. Its `AdmissionContext.operation_id` binds account, operation, session and request identity. `session_generation.py`/the generation SQL already own claim/checkpoint/recovery; Ask AI has request-key claim/completion. These are integration points, not existing usage accounting.
- `boundary.py` permits only reviewed exact hosted methods/paths; unreviewed expensive HTTP/stream/WS/gRPC work remains blocked. Device microphone/system capture cannot be replaced by recording a hosted server's sound device. Trusted authenticated audio relay, shared stream/session state, provider secret placement, TLS/proxy/timeout/deployment acceptance remain open.
- `allowance_periods.py` implements pure IST boundary calculation. It has no durable accounts, counters, reservations or enforcement. No subscription/entitlement/usage authority tables were found in the catalog migrations; `subscription_admin_permissions` is admin authorization, not a customer's subscription.
- Remaining C11 acceptance includes the recorded C11.1 session-owner/RLS/EXECUTE/version and boundary acceptance, target-specific secure pool/grants/TLS/project acceptance, actual policy approvals and real catalog configuration. C11.4 public display is locally accepted, while authoritative account current-plan/customer state remains unfinished. Catalog-local success does not close these gates or supply entitlements. Shared schema/grant reports in the access runbook are separate from this task, which did not inspect that database.

## One functional milestone and delivery order

**C13.1** builds durable account-term references, usage operations, periods, atomic reservations, settlement/reconciliation and Auto run measurement. Its account binding supplies the previously missing input to **C13.2**'s authoritative entitlement resolver. This is the prerequisite completion of C11 customer-state contracts inside the accounting milestone, not a new C11 phase or a renaming of C13.

**C13.2** then connects that authority to each enabled backend operation and authenticated account projections, followed by Electron current-plan/usage and Upgrade integration. Enable no route merely because its UI is ready. C12 checkout/webhook/payment state follows the established order and remains separate. Catalog publishing alone never assigns a subscription or proves payment.

### Account binding and feature authority (proposed)

Store an account-owned, revisioned assignment referencing an existing immutable `catalog_offer_versions` row and, where applicable, its immutable price version. Verify exact schema/fingerprint when resolving it. Keep assignment source, effective range, trusted state, policy version and audit distinct from payment facts or complimentary grants. At most one effective binding for the applicable account scope; reject ambiguous overlap. The verified account UUID is server-derived. Preserve the original trusted Auth signup timestamp/IST anchor; changing the plan or restarting a device must not move it.

No automatic Free assignment, paid-state transition or infinite validity is implied. Unknown/missing/inactive/unsupported authority is distinct from denied feature and unavailable storage. An explicit valid synthetic assignment can exercise all plumbing while real initial assignment, expiry and migration decisions remain unresolved. Retirement removes offers from new sales, not an existing assignment's immutable reference. No self-service assignment route or new admin role system is proposed in the first scope.

Resolve feature permissions separately from quota, storage capacity, concurrency and operational/model readiness. All plans permit dynamically configured supported and operationally available models; catalog membership is not provider readiness. Unlimited bypasses a subscription amount comparison only, never authentication, ownership, input limits, concurrency, audit or provider controls. Missing allowance does not mean unlimited. An admin catalog permission is not customer feature access.

### Durable accounting and recovery (proposed)

Use Postgres as one shared account authority across workers/devices. Proposed objects below are designs, not created migrations. Keep account/assignment/policy revision, operation type, resource/turn identity, canonical semantic hash and period scope in durable records. Raw content, JWTs and credentials do not belong in ledger metadata.

Authorize/reserve under current binding and ordered account/period/operation locks; use conditional balances so used + reserved cannot exceed a finite allowance. Atomically record the durable operation and reservation. Commit before provider dispatch; record provider attempts separately from customer usage. Fence each dispatch/completion with a generation/owner token and bounded lease. Retries/reconnects/transport fallback resolve the same logical operation, not a new charge; changed semantics with the same key conflict. Recheck authority before replaying protected results.

Persist result and settle atomically where the existing result database transaction permits. Otherwise use durable result/checkpoint plus pending-settlement/outbox reconciliation before claiming final accounting completion. Audit the actual generation/My Answers/resume storage transaction boundaries before choosing that adapter. Save-only recovery reuses the saved/checkpointed result without provider dispatch or new usage. A lost response returns the durable result on same-key recovery. Never blindly repeat a timed-out write or promise exactly-once upstream execution.

Before-dispatch failures can release an undispatched reservation exactly once. After-dispatch cancellation, provider timeout, persistence failure or worker crash may be uncertain: fence stale workers and retain reconciliation state; lease expiry alone proves neither no provider cost nor no successful result. Do not silently convert an unresolved customer charging policy into a charge or refund. Explicit settlement policy is required for each such path. Reconciliation must repair aggregates from immutable events, with compensating records rather than deleted history.

Auto uses server-time renewable run leases and one durable logical run across reconnects. Reserve bounded running intervals; silence counts, stopped time does not, and Both has one clock. Device timers/speech deltas are diagnostics only. Split a run crossing a daily/monthly boundary into the correct periods; no destructive counter reset or rollover. Stop/acknowledgement/disconnect/renewal boundary and concurrent-run policy require decisions before live enforcement. Block further funded intake if authority/renewal is unavailable; do not invent an offline entitlement.

### Approved feature integration matrix

| Capability / actual integration point | Required milestone behavior |
| --- | --- |
| Auto (`assistant.auto`, `auto.authorized_running`); device capture, `api/system_audio.py`, recorder/stream code | Free 600 integer seconds/IST day; Plus 18,000/signup month; Pro explicit unlimited. Any number of starts within allowance; server lease clock, silence included, stopped time excluded, Both once. Authenticate hosted relay before activation. |
| Manual audio, transcription/answers; `api/generate.py`, `session_generation.py`, STT paths | Unlimited subscription usage for all three; still authorize feature/model/ownership and operational limits. Reuse generation identity/checkpoint; internal retry/fallback costs never become invented customer quotas. |
| Resume; `api/resumes.py`, `cloud/cloud_resume.py` | Free 1 stored, 1 successful replacement/month; Plus 5 stored/unlimited replacements; Pro unlimited both. Reserve capacity across concurrent uploads, distinguish initial upload, candidate/extract/confirm and successful replacement. Blob/metadata failure reconciliation is required; do not count every extraction as a replacement. Existing delete/rebuild operations must not reset spent replacement allowance. |
| Screen; `api/screen_context.py`, screen orchestration, `ScreenContextControls.jsx` | Free 5 analyses/month, follow-ups denied; Plus/Pro unlimited analyses/follow-ups. Classify actual New/Continue/Passage/Data operations. Continue is not automatically a follow-up; passage capture may create reference evidence without an analysis. Recovery/fallback reuses operation identity. Ambiguous charging/classification remains gated. |
| Clipboard; `cloud/interview_session_my_answers.py`, its owned-session API, `AnswerPanel.jsx` | Count successful NEW persisted user-written answers account-wide: Free 5/month, Plus 10/month, Pro unlimited. Reads, OS clipboard access and AI generations consume no saves. Same logical save cannot duplicate a row/debit. Retain prior entries across resets; preserve no individual edit/delete and separate account-wide privacy deletion. |
| Sketch; `api/answer_diagrams.py`, `services/answer_diagram_service.py`, `cloud/answer_diagrams.py` | Free excluded; Plus/Pro included subject to actual released readiness. Bind to authoritative completed-answer revision; preserve existing diagram claim/recovery/cache identities. A label or preview icon is never permission. |
| History/exports, `cloud/interview_notes.py`, `cloud/interview_ask_ai.py` | No subscription usage quota for shared benefits; retain account/session ownership, existing retention, safe input/concurrency and successful-turn recovery. |

Daily boundaries are midnight Asia/Kolkata; monthly boundaries are the original account signup day at midnight IST, clamped for short months and restored afterward, using existing `allowance_period`. Annual billing never changes monthly allowances into annual pools. Period reads include server time/start/end/reset and distinguish used/reserved/available without exposing provider cost records.

### Electron and website (C13.2, after server authority)

Add authenticated current-plan/usage DTOs using immutable assignment/version identity, effective state and supported schema; recheck server authority on every enabled operation regardless of cached UI. No tokens/private drafts in browser persistence, no client-written balances. Refresh/invalidate on account change/revocation and ignore stale responses. Cache cannot authorize work during unavailable authority.

Use existing `StartupSessionChoiceScreen.jsx` **Buy Credits** for current plan and Upgrade opening an allowlisted website route via reviewed Electron main/preload IPC. Do not accept arbitrary payment URLs. Full plans/comparison stay in the existing website pricing section; C12 decides usable checkout. A compatible Electron release is required for new relay/entitlement/usage UI, while catalog-only changes for already supported contracts need not create a new client feature. Offline and failover behavior remain explicit decisions, not locally granted access.

## Concrete first authorization scope: closed C13.1 persistence foundation

Implement one bounded backend/native-database foundation, internally callable and production-unwired:

1. Validated account assignment to immutable terms using synthetic records; resolver input/version integrity and trusted signup anchor. No default Free enrollment or real assignments.
2. Durable operation identity, finite/unlimited allowance periods, atomic integer reservations, idempotent settle/release and fenced uncertain/reconciliation transitions. Require explicit injected operation policy; unsupported/missing lifecycle decisions fail closed. No provider dispatch, production Auto leases or live route enforcement yet.
3. Reuse existing validators/error patterns, verified actor boundary and restricted connection lifecycle; transactionally check assignment revisions/authority. Preserve current `ClosedAuthority` and hosted settings. Do not extend catalog-admin rights to assignment administration.

Proposed affected files: new `backend/app/commercial/account_entitlements.py` and `usage_store.py` (contracts/service/adapter kept small), reuse `catalog_contract.py`/`allowance_periods.py` and reviewed pool patterns. Change `catalog_database.py` only if justified by explicit restricted composition; never relax existing catalog ACL assertions. New `backend/tests/test_account_entitlements_native.py`, `test_usage_store_native.py` reuse native disposable harness. Existing admission, generation, draft/lifecycle, period and registry tests remain regressions. API, Electron and provider-execution files are audit/integration targets for C13.2, not changes in this first scope.

Prepare **additive migration(s), timestamp assigned at implementation**, for account assignment/history and usage periods/operations/reservations/events (fence/reconciliation fields included). Proposed names must be checked against actual schema before writing. FK immutable offer/price versions with RESTRICT; retain historical terms, no cascading loss. Enforce unique operation scope, finite nonnegative integer balances, one terminal settlement, valid state transitions, restricted EXECUTE/fixed search path and atomic audit. RLS does not constrain service-role/superuser; no customer direct writes, actor overrides or client-controlled grants. Design account-deletion cleanup explicitly with existing privacy workflow rather than retaining personal records accidentally through new FKs. No payment/subscriber-migration tables or catalog rewrites. Apply exclusively to task-owned disposable PostgreSQL; shared migration approval is separate.

Acceptance for this first scope: native independent connections prove last-unit and capacity races (one winner), concurrent same-key replay (one mutation/audit), conflicting-key semantics rejection, current binding revocation/change ordering, forged-account/role denial, rollback consistency, immutable term references, unsupported/corrupt data safe failure, exact IST boundary/leap-year/29th-31st restoration, no rollover, explicit unlimited versus zero/missing/denied, stale-fence rejection, uncertain outcome/reconciliation and lost-response recovery. Verify migrations/ACLs against anon/authenticated/service-role and the restricted executor. Use barriers/bounded timeouts, synthetic actors and no remote credentials. Existing catalog fingerprints must remain unchanged. Domain mocks supplement failure injection but never replace native SQL evidence.

This first scope is **ready for implementation authorization**; it does not require commercial defaults. Customer lifecycle decisions gate live settlement/enforcement, not independent closed identity/storage work.

## Milestone acceptance, compatibility and rollback

Before enabling each C13.2 path: browser/Electron -> real JWT -> hosted owner/entitlement/reservation -> actual result persistence -> settlement must pass on disposable infrastructure. Include two devices/workers, last allowance, duplicates across HTTP/stream/fallback, replay after revocation, stop/reconnect/silence/Both, period crossing, cancellation/timeout/crash/persistence failures and save-only recovery. Verify resume capacity/replacement success atomicity, screen classification, Clipboard new-save idempotency/read retention and Sketch denial/inclusion. Ordinary accounts retain admin 404 and backend permission denial. Payments/providers must remain stubbed where not explicitly authorized; actual metering tests must distinguish synthetic clocks from live capture evidence.

Old catalog versions/fingerprints and existing subscriber references remain readable. New unsupported client/protocol versions fail safely; do not silently route to ungated company-key local execution. Rollback disables affected admission paths/composition and stops new leases, preserving assignments, immutable terms, reservations, events and reconciliation until outstanding work is resolved. Never roll back by deleting balances/history or restoring allowance from device state. Shared apply, deployed capture/TLS/grants and production activation require separate approval/evidence.

## Historical undecided matters (superseded 24 October 2026)

The six rows below are retained as 23 October history. All now have explicit decisions in [the canonical approved-policy record](SUBSCRIPTION_APPROVED_POLICIES.md); do not treat them as current blockers. Refund/proration/tax/trial decisions remain outside this C13.2 implementation.

| Decision | Why it blocks live behavior; independent work that can continue |
| --- | --- |
| Initial Free assignment and trusted paid/complimentary assignment source; expiry/grace/suspension rules | Catalog publication cannot enroll an account. Synthetic explicit-state assignments and durable references can be built now; no real default/expiry assumed. |
| Upgrade/downgrade/migration effective timing, retained usage/reservations and overlap handling | Do not mint fresh allowances by changing plans or rewrite grandfathered terms. First foundation can reject ambiguous bindings and test explicitly supplied policy. Refund/proration stays C12/pending. |
| Auto Stop acknowledgement, disconnect/renewal failure/reconnect boundary; allowed simultaneous runs/devices and their accounting | Required to know billable authorized time and when to stop intake. Shared identity/period/reservation/fencing code can proceed without selecting charge tails or offline grace. |
| Provider failure/cancellation/uncertain completion and post-success persistence failure charging/release | Technical uncertainty cannot decide customer charges. Durable pending reconciliation and explicit settlement policy interfaces can proceed now. |
| Screen New/Continue/Passage and follow-up classification; failed/new-analysis counting | Needed before debiting the five Free analyses or denying a Continue operation. Feature classification/operation identity can be designed and tested with explicit cases. |
| Resume successful replacement boundary and existing over-cap data treatment at plan change | Capacity/activation transactions need a defined success point; no automatic deletion or unapproved quota reset. Closed synthetic capacity tests can proceed. |

Operational lease sizes/lock timeouts, safe DTOs, row locks, unit validation and test barriers are engineering decisions, not reasons to ask for new commercial policies. Tax/trials/discounts, paid expiry, refunds, support operations and actual publication policy approvals remain recorded dependencies; none blocks the proposed closed persistence foundation.


## Implemented C13.1 closed foundation and actual acceptance

The user subsequently authorized this complete closed foundation. Implementation does not install successful production admission, expose routes, compose a production connection/policy, assign real subscriptions or implement live Auto capture/enforcement. The separate localhost public-only pricing process remains running and unchanged by this slice.

### Files, storage and authority

- `backend/app/commercial/account_entitlements.py`: existing verified-bearer actor and closed `DraftService` transaction boundary; exact canonical snapshot/version/hash/identity validation; current binding resolution; separate trusted `BindingProvisioner` with explicit source/policy/finite validity and CAS status changes. No default Free assignment, billing-state mapping, binding replacement, renewal or plan-migration policy.
- `backend/app/commercial/usage_store.py`: internally callable `UsageStore.reserve/read/transition`, and separately privileged `UsageReconciler.recover/reconcile/release_uncertain/audit/rebuild`. Required injected backend policy is absent by default; callback failure denies availability, never grants. It must approve classified operation/meter and transitions. The test callback is explicitly synthetic. Constructor/import has no connection, route or activation side effects.
- `backend/app/commercial/catalog_store.py`: adds only the safe `usage_allowance_exhausted` outcome and SQLSTATE P0004 mapping; existing transaction/error/retry conventions are reused.
- **Additive migration `supabase/migrations/20261023160000_account_usage_foundation.sql`**, prepared and applied **only in fresh task-owned PostgreSQL**. It adds `account_plan_bindings`, `usage_periods`, `usage_operations`, immutable `usage_events`, and `usage_binding_call`, `usage_account_read`, `usage_terms_read`, internal IST `usage_period_bounds`, `usage_call`. Existing migrations/snapshots/fingerprints were not rewritten. Its schema is not installed in the running local pricing database or any shared database by this work.

Shipped infrastructure principals are **usage_executor**, **usage_binding_executor**, **usage_reconciler**, all NOLOGIN/no members/no inheritance/no superuser/role-create/database-create/replication/RLS bypass. Only the necessary function EXECUTE is granted; all table privileges are revoked from public/anon/authenticated/service_role/catalog and usage principals, with forced RLS. SECURITY DEFINER functions have fixed `pg_catalog` search paths, fully qualified objects, session-user/role checks and no dynamic caller SQL. RLS alone is not the security argument: service-role has RLS bypass but no permitted mutation/table/function privileges. Owner/superuser ability to change functions, disable triggers or alter tables is privileged maintenance outside application guarantees.

The provisioning capability is **not** another human role system. `subscriptions.manage` cannot assign accounts or write usage. Future approved assignment sources must compose a separate trusted provisioning channel; none is configured. Assignment obtains the anchor from locked `auth.users.created_at`, not a client timestamp. Terms/price FKs restrict historical loss; one immutable-term binding per account prevents unapproved overlap/migration. Binding state/validity/source are not verified payment facts or a full subscription state machine. Historical catalog retirement/replacement does not change a binding.

### Transaction, retry and recovery guarantees

Each user service operation re-verifies the retained JWT and checks the current binding inside the same SQL transaction; no positive authorization cache. Lock order is binding, period, operation. The initial binding read locks for update to avoid shared-lock upgrade deadlocks. This deliberately serializes writes within an account; measure contention before finer locking. Existing transaction channel uses 5-second lock and 10-second statement limits; deployment pool/idle-transaction/overall request budgets remain C13.2 composition work. No DB transaction spans provider calls because none are dispatched here.

Meter allowance/mode, feature inclusion and reset cadence are derived in SQL from exact accepted immutable terms; no caller-supplied allowance/period/role fields exist. Legacy storage limits and V3 explicit storage capacities are supported; V2/V3 usage allowances preserve finite/unlimited/zero/missing distinctions. Unknown/missing/denied meters fail closed. IST SQL boundary arithmetic is tested against the existing Python helper, preserving the original signup anchor and independent daily/monthly scopes. Unlimited/capacity accumulation uses a lifetime scope ending at infinity; that is a balance scope only, **not** indefinite subscription validity. Validity is explicit and finite. No destructive resets or rollover; annual billing does not change cadence.

Operation scope reuses `AdmissionContext` account/operation/session-resource/request identity and canonical semantics hash. The original server-owned canonicalization remains the caller's responsibility; a hash is not proof of account/resource ownership or validated request content. C13.2 must retain existing owner/context checks before invoking this service. The unique SQL scope additionally binds meter, requested units and policy version; mismatched reuse conflicts. Completed/pending replay returns the recorded operation with **execution_permitted=false**, no extra reservation/event. Only the first committed dispatch transition returns true; a duplicate dispatch returns false. Upstream exactly-once execution is not promised. Recovery/superseding generation contexts are rejected by reserve; use existing operation reads/checkpoints, never a new execution claim.

State path: reserved -> dispatched -> checkpointed -> settled. Before-dispatch release is idempotent. Dispatch/cancel uncertainty or expired claims -> uncertain with a higher fence, retaining the reservation and existing checkpoint. A separate reconciler needs explicit policy plus evidence identity to settle or release uncertain work, including after customer revocation/expiry. Expiry alone never frees quota or permits redispatch. Reconciliation cannot replace a known checkpoint's result pointer. Settlement cannot exceed the reserve; repeat equal settlement/release is a no-op and conflicting settlement fails. Storage `vacate` releases settled capacity once; it does not refund replacement/new-save quota. This is a trusted storage-adapter hook, not a user delete capability.

All balance/operation/event mutations are atomic. Events contain account/operation identifiers, server principal, fence, deltas and server timestamp only; retry state is separate. No prompts, audio, user answers, credentials or tokens are stored. Opaque result/evidence UUIDs are pointers, **not result storage or independent proof of successful persistence**. C13.2 must bind them to actual existing result/checkpoint transactions or a durable pending-settlement/outbox. Reconciler audit compares aggregates against immutable deltas; rebuild repairs a drifted materialized balance under the same locks and writes a zero-delta repair event. It does not amend commercial outcomes. Transport uncertainty returns the existing safe uncertain error without blind writes/retries; an equal-key retry resolves the durable result.

### Executed verification

- **17 native C13.1 tests passed** on **PostgreSQL 17.11**, non-elevated portable Windows runtime. `test_usage_store_native.py` exercises actual Python services and independent direct connections as the three restricted principals (LOGIN enabled only by the disposable fixture); synthetic Auth users and actual signed JWT verification; explicit synthetic policies; accepted catalog creation/review/publication for test offers. No shared Supabase/PostgREST acceptance is claimed.
- Native cases: immutable binding/price references and idempotent assignment; no self-promotion/direct writes/service-role bypass; exact finite/zero/unlimited/missing behavior; last-unit and same-key races; conflicting identity; both revocation lock orderings; cross-account/forged actor denial; reserve and settlement rollback; capacity versus replacement; IST helper equivalence/period separation; checkpoint-only recovery, expiry/fencing and post-revocation reconciliation; explicit uncertain release; aggregate drift/rebuild; settlement and dispatch/release races; corrupt/unsupported terms; lost commit response without duplicate event; initial construction closed; bound terms remain unchanged after offer replacement/retirement. Concurrency uses barriers and observed PostgreSQL blocking with bounded waits, not sleeps to guess winners.
- **159 domain/catalog/store/registry/period checks passed**, including **13 new pure usage-contract cases**. **117 admission/admin/period checks passed** in a separate process (period tests overlap; do not sum as unique coverage).
- Existing native regressions: **12 adapter**, **23 draft-service**, **30 lifecycle-service** passed. Test-owned clusters clean up through the accepted fixture; retained runtime downloads and the running public-only preview are preserved.
- Scoped **Ruff E4/E7/E9/F/I, Black, strict mypy** (two new runtime modules, followed imports silent/third-party missing stubs ignored), syntax and whitespace checks passed. Tools reused the existing temporary verification-tool directory; no dependency/lockfile/.env changes. Historical broader browser/module-reload/PDF failures remain open; this is not a full-project or combined-process suite pass. Native harness still uses the previously documented unused-PDF test stub, which is not PDF verification. Existing pytest rewrite/SWIG warnings remain.

Native rerun from the project root, using the already-retained machine-specific runtime:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
& E:/deepfake_envs/SaIIA/python.exe "$env:TEMP/c113c-test-launch.py" backend/tests/test_usage_store_native.py --pg-bin C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin
```

The test runner creates its own fresh loopback cluster and never consumes a remote DSN. The source migration remains unapplied outside isolated tests. No normal configuration, admin grants, offers, provider/payment calls, Electron, activation, commits, pushes or deployment changed.

### Historical C13.1 handoff ? superseded by the current C13.2 evidence

See the **fixed [C11 closure checklist](C11_CLOSURE_CHECKLIST.md)**. C13.1 now supplies internal account binding and durable accounting evidence; it does not close C11 normalized subscription state, initial Free enrollment, client current-plan parity, live feature gates, pending session-owner native acceptance or deployment checks. Overall C11/C13 remain partial.

Next implementation is **C13.2 authoritative enforcement/visibility**, not another catalog microphase: compose reviewed account/usage channels and approved state/policy resolver; expose authenticated minimal current-plan/usage DTOs; integrate the existing owner/session/generation/Ask AI/Notes/result/checkpoint boundaries and each enabled resume/Screen/My Answers/diagram path; verify transactional storage activation/new-save/capacity accounting; then trusted Auto run identity/renewable elapsed-time slices spanning periods and authenticated device relay, followed by Electron Buy Credits current plan/usage plus allowlisted website Upgrade. Preserve full pricing on the website and default-off admission until each path has its bypass/concurrency/recovery tests.

No live Auto clock, heartbeats/renewals, audio relay, real provider-attempt cost records, result-store outbox/completion coupling, actual feature-handler enforcement, customer API or Electron work is implemented here. The low-level reserve/claim/fence/checkpoint machinery supports that integration without selecting stop/disconnect or charging rules. Account privacy deletion must reconcile these RESTRICT references with the existing account-wide workflow before live assignment; this slice does not authorize a new personal-data retention policy or purge privileged records.

Genuinely pending business choices remain the six rows above: initial source/state/expiry, upgrade/downgrade usage and timing, Auto stop/disconnect/concurrent-run accounting, failure/cancellation/uncertain-result charges, Screen classification/counting and successful resume replacement/over-cap treatment. Refund/tax/trial/support decisions stay in their own phases. Missing choices keep affected operations unavailable, not unlimited or free. Compatibility preserves V1/V2/V3 bytes; rollback leaves the unwired foundation disabled, preserves immutable history/outstanding reservations/events, and reconciles claims rather than resetting balances or dropping tables. Shared migration/provisioning/production enablement require separate authorization.


### Current hosted desktop continuation ? 25 October 2026

The default-off Electron hosted client now uses authenticated capabilities and the existing relay, main-owned bounded PCM forwarding, server leases and a single mixed Both stream. Native claim-once fencing prevents duplicate relay connection ownership. Isolated packaged acceptance exercises two workers, durable answers, Stop, worker failure/recovery and logout; see [implementation evidence](C13_2_IMPLEMENTATION_EVIDENCE.md) for exact logs and overlapping suite counts (51 backend native, 48 local native, 189 Node, 58 browser cases; hosted packaged wrapper 1/embedded 2). This supersedes earlier statements that desktop relay delivery is missing.

Real hosted-device acceptance is in progress: baseline Free/zero usage/zero reservations is operator-confirmed; capture is not yet accepted. Existing local synchronized timing/JBL acceptance remains valid and is not repeated. Shared TLS/staging, signed installation and irreversible account deletion remain open. No staging project has been designated; 50 migration candidates are a review inventory, not presumed pending. The deletion retention/unlink proposal is unapproved. C11/C13 remain open; C12 remains payment integration. No shared migration or production activation occurred.


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
