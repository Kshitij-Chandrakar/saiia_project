# Fixed C11 closure checklist

**Evidence status - 26 October 2026:** The [application acceptance continuation](#26-october-2026-application-acceptance-continuation) records 11 local two-worker scenario groups. A separate local operational record reports staging Auth/JWT/Storage acceptance at 17:03 IST, 42 allowance periods and five-role cleanup, but that record and its execution artifacts are excluded from this PR. Staging acceptance is therefore not independently verifiable from this committed checklist; it is not certified here. Public HTTPS/WSS, signed installed Windows, deletion approval and applicable lint/build checks remain separate gates; C11/C13 remain open.



**Current acceptance status — 25 October 2026:** The single
[current-status table](C11_C13_ACCEPTANCE_RUNBOOK.md#current-status--25-october-2026)
supersedes older blanket pending statements. Synchronized timing and controlled
JBL disconnect/reconnect passed; retain their raw/operator evidence without
repeating them. Default-off hosted relay/shared handoff and deletion preparation
are implemented and native-tested; desktop hosted transport is now implemented and isolated-package tested; hosted physical mic/system/Both/Stop/logout checks are operator-observed; irreversible deletion, signed installation and staging acceptance remain distinct open gates.
Latest continuation: **51 backend native passed; 48 local native passed; 189 focused Node passed; 58 browser regressions passed** (overlapping suites, not additive). Packaged hosted acceptance: wrapper **1 passed**, embedded Playwright **2 passed**, including two workers and worker failure. Earlier counts below remain historical.
Scoped checks: scoped Ruff/ESLint and backend typing pass. Full lint
remains **60 errors / 29 warnings**, no new error pairs against recorded attribution.
Staging target cfmvqbjmnwklxqlpelxe is confirmed and owner-preflighted; migration/activation approval is pending. C11/C13 remain open.

**Latest acceptance reconciliation (24 October 2026):** [Exact gate matrix,
packaged/physical checklist and staging approval procedure](C11_C13_ACCEPTANCE_RUNBOOK.md).
All existing fixed rows below retain their scope. Native integration **48 passed**
with actual packaged/file renderer; exact previously failing combined process now
**235 passed** after import-test isolation repair. Short real mic/system/Both
PCM/Stop smoke passed once; earlier test-panel sequencing timeouts are recorded, action serialization fixed,
and the final three-source synchronized smoke passed. Longer physical reliability remains open.
Unsigned portable packaging is not signed installed acceptance. Subscription lint
regressions are fixed; **60 pre-existing source errors / 29 warnings** remain, with
[HEAD attribution](C13_2_LINT_ATTRIBUTION.json). Physical/operator, installed,
shared/hosted and privacy gates remain open. No shared target/change set approved
or executed; 48 ordered migration candidates are not presumed unapplied.

## Previous reconciliation (historical context)

**C13.2 continuation - local implementation evidence (24 October 2026):** The missing Auto mic/system/Both gRPC lease integration, durable Screen classification/results/settlement, resume capacity/initial-history/replacement/active-set/reindex paths, native Notes/Ask AI/history/export gates and client account cleanup are implemented default-off. Actual Windows Electron main/preload/renderer now passes native-JWT Current plan/Upgrade/logout and synthetic STT acceptance; packaged installed-device acceptance is separate. Native integration: **48 passed**, including two actual-native Playwright browser/Electron subcases. Backend regressions: **662 + 105 passed**; existing catalog/admin Playwright: **57 passed**, plus the separately mocked resume chooser. The [current evidence](C13_2_IMPLEMENTATION_EVIDENCE.md) records final native/check/build counts, exact migrations, transport boundaries and remaining limits. No shared changes or production activation. **C11/C13 remain partial; C13.2 release acceptance is not inferred from isolated tests or a failing repository-wide lint.**

Source reconciliation: 23 October 2026. **C11 remains partial.** This checklist fixes the acceptance scope to the existing roadmap's C11 goal, rules, tests and five exit criteria, plus the already-recorded C11.1 security acceptance. It does not add payments, support tooling or a completed usage engine to C11. C12 remains payments; C13 remains usage/enforcement.

Sources: [roadmap C11](../SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md#c11--pricing-and-subscription-foundation), [implementation plan](C11_C13_SUBSCRIPTION_IMPLEMENTATION_PLAN.md), [readiness audit](C11_SUBSCRIPTION_READINESS_AUDIT.md), and [the consolidated milestone](SUBSCRIPTION_ENTITLEMENTS_USAGE_MILESTONE.md). Earlier historical table entries do not override later implementation evidence. Phase closure must identify local implementation acceptance separately from deployment/production acceptance.

## Required behavior and exact acceptance

Named future tests in the historical specification below are scenario labels, not claims of passing test functions. The current named-case mapping immediately below identifies implemented acceptance; no new exit criterion is added.

Current named-case evidence (all in `test_subscription_integration_native.py` unless stated):

| Existing gate | Actual acceptance cases / latest evidence | Remaining acceptance |
| --- | --- | --- |
| Trusted state / no self assignment | `test_current_api_bootstrap_and_cross_account_denial`, `test_verified_payment_preserved_bootstrap_and_expiry`, `test_account_api_aliases_and_corrupt_authority_fail_closed` | Approved staging JWT/schema/configuration |
| Central plan transitions / preserved usage | `test_upgrade_keeps_consumed_monthly_allowance`, `test_scheduled_paid_period_change_preserves_usage_and_retries`, `test_paid_expiry_preserves_over_cap_data_and_cross_scope_audit` | Verified payment transport remains C12; shared transition acceptance unverified |
| Actual backend gates | `test_native_screen_success_replay_exhaustion_and_forged_context`, `test_native_resume_initial_replacement_delete_history_and_retries`, `test_actual_clipboard_store_atomic_replay_exhaustion_and_ownership`, `test_native_auxiliary_notes_ask_history_export_and_replay`, manual/Sketch/Auto cases in evidence | Enabled hosted paths require approved deployment/client delivery; irreversible privacy workflow remains gated |
| Client current plan and privacy | `test_account_browser_real_jwt_native_database`: packaged wrapper 1 pass, embedded browser/Electron 2 pass (20.34s); native account-switch/ownership and Node cleanup tests retained | Signed installation and real browser/OS protocol handoff |
| Identity, replay and cross-worker isolation | Native account/relay 69 pass; final boundary/usage regression 178 pass; `test_actual_two_process_relay_worker_crash_and_recovery` and `test_hosted_answer_is_durable_and_frame_replay_cannot_regenerate` in `test_hosted_subscription_native.py` | Actual staging WSS/TLS/roles/two-worker configuration |
| Migration review / deployment | Read-only preflight on disposable native PostgreSQL and ordered manifest hash test 1 pass; 50 candidates, not presumed missing | Identify isolated target; reconcile history AND objects and approve exact diff before applying |

| Fixed gate / required behavior | Implementation dependency | Exact acceptance test | Current evidence / C13.1 contribution / remaining work |
| --- | --- | --- | --- |
| **Plans represented in database**: stable identity, immutable accepted terms/prices, exact review binding, atomic lifecycle and public-safe publication | Existing C11.2/3/4 contracts, migrations, services, admin and public reader | Existing `test_catalog_store_native.py`; `test_lifecycle_service_native.py`; `test_bound_history_survives_offer_replacement_and_retirement` in `test_usage_store_native.py`: record canonical bytes, replace/retire, then assert binding still resolves identical bytes and original allowance | Catalog locally accepted; new binding-history test passes. No catalog rebuild required. Target-specific deployment acceptance remains separate. |
| **Subscription status represented**: trusted account binding and centralized state; unknown state must fail closed; original accepted terms retained | Closed C13.1 assignment foundation plus approved source and normalized state mapping for C13.2/C12 | Existing new `test_binding_exact_terms_and_no_self_assignment`, `test_expiry_stale_claim_policy_failure_and_terminal_immutability`; future `test_subscription_state_mapping`: explicit Free/active/canceled/expired/unknown fixture states, safe deterministic access and no client status override | **Partly satisfied internally by C13.1**: immutable offer/price reference, explicit validity/source/policy, Auth signup anchor, current active flag/revision. This is not a complete normalized billing subscription state machine. C13.2 adds verified new-account Free and paid expiry-to-Free locally, with no real assignments. Verified scheduled cancel/downgrade now exists internally; there is no customer billing portal/C12 verification, and past_due/trial semantics are not claimed. Approved lifecycle decisions are in [the canonical record](SUBSCRIPTION_APPROVED_POLICIES.md). |
| **Backend feature gates work**: authoritative allowed/denied/unavailable result; feature permission separate from quota/capacity/model readiness; no frontend grant | C13.2 resolver/admission integration using C13.1 current binding and atomic usage authority | Future `test_entitlement_gate_matrix`: for every enabled registered feature, exercise allowed/denied/missing/unavailable binding through actual authenticated execution handler; forged actor/role/model flags fail; provider spy records zero calls on rejection. Replay and save-only requests cannot dispatch or debit again | C13.1 validates snapshot and current account authority and derives registered meter allowances in SQL; `test_zero_missing_denied_and_approved_paid_bindings` and quota/retry tests pass. **C13.2 integrates the canonical Clipboard, manual answer, Sketch, Screen, resume, Notes/Ask AI, history/export and Auto paths**. See the current feature/transport matrix and named native tests in the evidence record. Legacy/unreviewed transports remain explicitly closed and default ClosedAuthority is retained. Local gate evidence advances; shared/hosted execution remains unaccepted. |
| **Current plan visible to clients**: website/account/Electron receive the same account-owned version and state; full pricing stays website-only | C13.2 authenticated current-plan/usage DTO and client integration; existing Buy Credits/Upgrade boundary | Future `test_current_plan_client_parity`: same signed-in account/version on website and Electron; account switch/logout clears state; stale responses ignored; storage failure is unavailable, not Free. Upgrade opens allowlisted website URL; no Electron pricing cards | **Partially integrated in C13.2**: authenticated current-plan/feature/usage API, retained-bearer desktop main method, renderer current plan/Auto availability and trusted Upgrade IPC. Native JWT/API plus Playwright synthetic-preload renderer evidence is in [the C13.2 record](C13_2_IMPLEMENTATION_EVIDENCE.md). Actual Windows Electron main/preload/renderer is now native-JWT tested, including Upgrade, IPC transcription and logout. Packaged installed-device and shared/deployment parity remain unverified; public pricing alone does not close this gate. |
| **No real payment dependency**: foundational catalog/account reads and synthetic assignments work without payment calls; no frontend paid unlock | Existing closed code and explicit synthetic test policy; C12 is separate | Existing `test_lost_commit_recovery_and_closed_construction`, constructor/domain checks, native fixture outbound guard and admission tests; future C13.2 current-plan smoke with payment transport disabled | Satisfied for isolated catalog/C13.1 foundation. Paid checkout remains disabled. Completed payments are **not** a C11 closure prerequisite. |
| **Safe Free assignment and centralized plan change** (existing C11 rules/tests): server-owned initial policy and no usage reset through plan changes | Business-approved initial source and migration timing, then centralized assignment transition service; immutable history retained | Future `test_initial_free_assignment_once`: concurrent sign-ins assign once without app/device resets. Future `test_plan_change_preserves_terms_and_usage`: concurrent changes/CAS/replay, no overlapping effective grants or fresh quota minted without approved policy | **Partially satisfied locally in C13.2**: verified new-account Free bootstrap is idempotent/no-expiry and preserves existing paid bindings; trusted payment transition and paid expiry-to-Free are internally tested; Clipboard usage survives an upgrade. Scheduled downgrade/cancel is now internally native-tested; existing IST/cadence/ownership tests are retained and canonical Auto Stop/disconnect/expiry/exhaustion is now native transport-tested. Shared/deployed transitions remain unverified. The [approved lifecycle policies](SUBSCRIPTION_APPROVED_POLICIES.md) are resolved; no real assignment/backfill was performed. |
| **C11.1 trusted identity/ownership/boundary acceptance**: correct user/session/resource ownership; RLS and EXECUTE restrictions; unknown HTTP/WS/gRPC denied; shared admin revocation | Existing admission/session generation SQL plus accepted admin storage; reviewed native session ownership fixture and supported CI runtime | Existing `test_all_registered_unreviewed_routes_and_future_routes_are_denied`, `test_actual_buffered_http_admission_denials`, `test_boundary_aliases_never_redirect_or_dispatch` in `test_commercial_admission.py`; remaining exact native case: two distinct signed-in users against owned session/turn SQL, prove foreign claim/checkpoint/result/save-only denial under anon/authenticated/service-role gateway roles and current schema versions | 117 scoped admission/admin/period checks pass in this task. C13.1 adds independent account-role/cross-account/revocation tests; C13.2 adds actual owned native session/turn, Screen/resume and cross-worker Auto checks. These do not resolve the separate historical runtime/CI or hosted relay acceptance gap. |
| **Admin permission and catalog-write integrity** (already established C11.3): current authoritative permission, exact saved revision, durable retries, ordinary-user 404/backend denial | Existing accepted admin probe/draft/lifecycle implementation and reviewed target grants | Existing draft/lifecycle native tests; workspace 52-test historical browser record; new usage role tests ensure `subscriptions.manage`/catalog executor cannot assign plans or mutate usage | Locally accepted, not reopened. New accounting principals have NOLOGIN/no memberships in shipped SQL. Full private offer-history listing is not added to C11 closure; currently visible discovery/known-ID reads remain as implemented. |

## Deployment acceptance is separately recorded

These are the pre-existing deployment/launch gates, not new local feature work: intended project/schema/migration/role/function ACL verification; production JWT/project binding; TLS/trusted proxy/origin/secret handling; bounded pools and identity isolation; approved publication policies; real catalog configuration approval; hosted capture relay and shared stream state before enabling funded audio. Exact acceptance is an authorized target preflight plus ordinary/admin cross-account browser/JWT/API checks, restricted-role SQL checks and multi-worker capture/revocation tests for each enabled route. This task performed **none** of those shared/deployed checks.

Payments, provider sandbox acceptance, C13 live measurement/enforcement, and support operations keep their own phase/release gates. They must not be silently added to the five C11 local exits. Conversely, completing C12/C13 does not automatically mark C11 closed: the fixed rows above still require their own evidence.

## Closure rule

Current continuation evidence advances the fixed local gates above without adding new C11 scope. Local backend, Electron executable and browser evidence is linked; full repository lint and packaged/shared acceptance limits remain explicit. No overall C11/C13 closure is claimed.

Historical C13.1 handoff (superseded for current implementation status):

After C13.1: catalog remains locally accepted; internal account binding and atomic usage persistence are locally verified. Subscription-state policy, initial assignment/plan-change policy, authenticated current-plan/client parity, actual feature-gate integration and remaining C11.1 acceptance are still open. The next bounded implementation is **C13.2** using those foundations, with unsupported policy paths kept closed. A later closure review records pass/fail evidence for each row; no production checkbox is inferred from disposable tests.

### Physical Bluetooth evidence update — 25 October 2026

The controlled unsigned packaged JBL Tune 770NC trial now passes automatic disconnect teardown: the captured track was verified as Bluetooth before removal; its ended event was followed by disconnected application status, no captured tracks, and operator-confirmed Windows indicator removal. The post-disconnect ledger had reserved zero and remained exactly 69.553626 seconds used across a requested twenty-second idle interval. This supersedes the earlier ambiguous Bluetooth trial for this device only. See [physical results](C13_2_PHYSICAL_ACCEPTANCE_RESULTS.md). No signed/installed, hosted, other-device or overall C11/C13 gate is closed by this observation.


### Final continuation status - 25 October 2026

See the [relay/privacy review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md) for exact migration scope/hash, role/configuration/rollback prerequisites, retained records and retention/unlink proposal. The authoritative current-status table includes accepted synchronized timing/JBL evidence and replaces superseded pending statements. No physical trial was repeated in this continuation. Final automated evidence: 69 native account/relay cases; 178 boundary/usage cases; 1 read-only preflight/hash case; 172 Node cases; 58 browser fixtures passed/1 optional visual skipped; packaged real JWT/PostgreSQL/browser/Electron wrapper 1 pass, embedded 2 pass. Production build, scoped formatting/lint and two-source-module typing pass. Existing full lint remains 60 errors/29 warnings with no new attributed error pairs. Graphify refreshed with extraction limits recorded. These local results do not close signed/installed, shared/hosted release or irreversible deletion acceptance; overall C11/C13 remain OPEN.


### Hosted physical acceptance completed ? operator evidence, 25 October 2026

Following the isolated launcher port repair, actual unsigned packaged Electron main/preload/compiled renderer captured microphone, Windows system loopback and Both through the hosted relay with synthetic providers and disposable PostgreSQL. Operator safe status showed live source tracks, valid 16 kHz PCM and connected forwarding with no failure for all three. Explicit Stop removed the microphone indicator for mic/Both; system Stop was followed by disconnected status and no tracks. Final usage was 135.540248 seconds, reserved zero; checkout remained disabled. Logout then returned `{ "ok": false, "status": 401 }`, and the operator confirmed the capture indicator stayed off. Detailed source observations and the initial failed launcher attempt remain in the physical results.

This closes the newly requested isolated hosted mic/system/Both startup/Stop/logout physical checks only. No new independent timing, Bluetooth disconnect, signed-installed Windows or deployed WSS/TLS acceptance is inferred. Previously accepted synchronized timing/JBL trials were not repeated. Staging target designation, signed installation, unapproved deletion retention/unlink policy and existing repository lint remain open. C11/C13 are not marked complete. The documented stop marker was issued after the final observation; teardown result is recorded separately.

Hosted physical harness teardown: `tmp/c132-hosted-physical-port-fixed.log` records wrapper **1 passed / 47 deselected, 507.46s**, embedded Playwright **2 passed**. Stop-marker shutdown exited zero; the isolated Electron processes and relay Python workers exited, and session-owned PostgreSQL processes stopped. The pre-existing preview Python PID 20512 and older PostgreSQL processes were preserved. This automated teardown evidence is separate from the operator capture observations.


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
restrictive privacy barriers and zero-seeded authority. No original migration,
permission, policy, fingerprint or commercial term was changed. Final batch SHA256
`926af0c4d71865bec91784c87071928639acc5a676ef794df20e3186ce144635`. Previous batch hash is no longer the approval target.

Final local checker PASS: 16 injected invariant violations fail pre-COMMIT with
full schema/history/role/bucket rollback; separate post-assertion late failure and
healthy full 50-source/postflight/replay checks pass under both superuser and
NOSUPERUSER migration-owner fixtures. Missing Storage-owner or existing BYPASSRLS
authority fails closed; no repair/broadening grant. PostgreSQL 17 automatic creator
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


## Actual managed-owner preflight returned - 25 October 2026

Owner supplied `owner_preflight` from staging SQL Editor. Effective/session user
postgres; NOSUPERUSER, INHERIT, CREATEDB, CREATEROLE and BYPASSRLS; all listed
schema/Auth-reference/bucket DML requirements true. pgcrypto is owned by postgres
in extensions; migration-history schema absent. `createrole_self_grant` is empty.
These confirm the modeled role attributes and ordinary object privileges.

However, Auth users and Storage buckets/objects belong to their respective
supabase_auth_admin/supabase_storage_admin roles. Inherited owner authority is
false for all three. Auth ownership is not required by this batch: it does not
alter Auth tables; REFERENCES/SELECT/USAGE suffice for its FKs/baseline checks.
Storage ownership IS a compatibility gap: existing sources create/drop/comment
Storage policies, and the privacy migration creates a restrictive Storage policy.
Bucket INSERT/UPDATE permissions and BYPASSRLS do not by themselves establish
permission to modify policies. The local missing-storage-owner fixture fails closed.
Managed platform-specific hooks could differ from stock PostgreSQL, but no
supported exception has been established from this read-only result.

Therefore actual target compatibility is NOT cleared. Do not execute batch
926af0c4d71865bec91784c87071928639acc5a676ef794df20e3186ce144635 yet.
Do not grant superuser/BYPASSRLS/membership, change Storage ownership, disable RLS
or omit the restrictive policy to work around this. Next action: establish the
Supabase-supported policy-migration mechanism for this project's SQL Editor
postgres role (platform documentation/support or an explicitly authorized isolated
platform test). If that requires splitting platform-owned policy DDL from the
application transaction, prepare/retest a revised phased change set and request
fresh approval; the existing atomicity evidence cannot be extended to that design.
No remote write, privilege change or migration was performed by the agent.


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


### Separate post-rollback verification received - 25 October 2026

Owner returned the separate read-only verification row (without session_user):
effective_user=postgres, storage_owner=supabase_storage_admin, rls_enabled=true,
probe_absent=true. This matches the prepared separate cleanup query. Together
with the prior approved probe result, operator evidence supports successful
CREATE/COMMENT/DROP in the actual managed SQL Editor context and post-script
cleanup with no retained probe policy or changed owner/RLS. No error was reported.
The agent did not execute remote SQL or directly observe SQL Editor transaction
messages; acceptance is operator-reported behavior plus separate cleanup evidence.

The policy-DDL compatibility gap is now behaviorally resolved for this tested
project/session. Missing version metadata must not override actual observed
COMMENT support. The current full batch still contains the earlier version-based
authority guard and may reject this project because version metadata was absent.
It must be revised, locally retested and rehashed for a narrowly scoped,
evidence-backed precondition before any full-batch approval/execution. Do not
fabricate a version, configure supautils or silently run the current batch.
The existing probe approval does not authorize the full batch, role/login changes,
activation, Saiia-dev changes, publication or irreversible deletion. Accepted
capture evidence remains unchanged.


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


### Final schema-only manual application authorized - 25 October 2026

Owner reconfirms cfmvqbjmnwklxqlpelxe is empty/disposable with no data to preserve,
and explicitly authorizes manual execution of final 50-migration batch SHA256
`1c61333c737c1291c56a03112603af9ff5e09225755d5e73acdd5fbe8be17a24`.
Scope: migrations, migration-history initialization, private buckets/policies,
closed NOLOGIN roles and exact ACLs. Recovery B selected: operator-led recreation
of this staging project only if necessary; Saiia-dev excluded. No activation,
LOGIN provisioning, offers/subscriptions, account deletion or deployment authorized.
After successful COMMIT, existing read-only postflight and review are authorized.
On error: explicit ROLLBACK, stop and retain error evidence; no blind retries.
Approved batch bytes rechecked and matched. Original SQL preparatory header
predates approval; file remains unchanged to preserve approved hash.

Current status: operator-returned postflight reviewed successfully on 25 October
2026 for the approved schema-only application. Exact 50-version set matches with
no extras; five roles remain closed; resumes/exports buckets are private; relay
executor access/private-table/authenticated-denial checks pass. Permissions,
bindings, offers, publication policies, configuration and usage events are all
zero. Raw operator evidence: docs/sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_POSTFLIGHT_RESULT.json.
This supersedes the prior application-pending status. Evidence is operator-run,
not an agent SQL connection or direct observation of COMMIT. The operator also
explicitly confirmed SQL Editor success. Schema-only application is accepted on
this operator confirmation plus passing postflight. Do not rerun the batch.
Activation, LOGIN provisioning, offers/subscriptions, account deletion and deployment
remain unauthorized. C11/C13 remain open for remaining runtime/hosted/installed
acceptance and policy gates. Accepted physical/capture evidence remains preserved.


### Bounded staging activation prepared ? 25 October 2026

Schema application/postflight remains passed; migrations are not rerun.
[Concrete activation packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_ACTIVATION.md) and its artifact hash manifest
are prepared for one consolidated approval: five existing direct role LOGINs
(maximum 24 hours), four synthetic Auth accounts, audited synthetic admin grant,
three immutable test-only offers, explicit synthetic policies and paid events,
two isolated local workers, acceptance and credential revocation. No activation
or remote connection was performed. New credential SQL passed a disposable native
role-lifecycle test; scoped Black/Ruff passed. Real JWT/managed executor testing
requires approval and privately supplied staging connectivity/credentials.
Public HTTPS/WSS, unapproved deletion/retention policy and signed/installed Windows
remain separate pending gates; no C11/C13 closure is claimed. Existing accepted
physical tests remain intact and were not repeated.


### Activation approved; execution blocked before provisioning ? 25 October 2026

Owner approved the exact activation packet/manifest and cleanup for a maximum
24-hour staging-only session. All approved artifact/input hashes match; frozen
packet/manifest remain unchanged. Conservative intake cutoff: **26 October 2026
18:38:53 IST (13:08:53 UTC)**, recorded from first inspection after approval.
No intake/worker is currently running. Do not start or continue intake after that
cutoff under this session approval; no reconfirmation is needed merely to use the
existing authorization within its window.

Read-only local/network preparation found both reserved loopback ports free, no
authorized SQL connector or staging credential environment, and no staging reference
in existing .env files (not used). System DNS resolves the direct database's AAAA,
but explicit IPv6 TCP fails with network-unreachable; Python getaddrinfo returns
11004. This is a direct IPv6 connectivity limitation, not evidence that the project
is absent. No database authentication was attempted. No secrets printed.

No remote write, LOGIN/password provisioning, Auth creation, admin grant, offer,
binding, worker, migration rerun or live provider call occurred. Specified staging
JWT/catalog/entitlement/concurrency/recovery tests are **NOT RUN**. No session-owned
resources exist to clean up; no cleanup failure occurred, but remote baseline was
not re-inspected or certified. Accepted schema and physical evidence are retained.

Required execution inputs: IPv6-capable direct TLS connectivity to the approved
database plus privately supplied staging DB/Auth credentials/CA/signing config.
Never send secrets in chat. No silent pooler username/role change, paid connectivity
addon or use of normal/Saiia-dev credentials. Raw safe record:
[activation execution result](sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_ACTIVATION_EXECUTION_RESULT.json).
Public HTTPS/WSS, deletion policy and signed Windows remain separately pending;
no C11/C13 closure is claimed.


### IPv4 session-pooler inspection ? 25 October 2026

[Compatibility report](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_SESSION_POOLER_REVIEW.md): official Supabase
documents custom roles/session affinity; current application DSN allowlists reject
qualified pooler usernames and reference-options routing before connection. Six
local no-network cases reproduced this with checks unchanged. No backend code or
approved packet/manifest changed. Direct IPv6-capable execution remains the
no-code alternative; an adapter would require separate implementation/tests while
retaining exact SQL role/ACL/reset enforcement. Managed identity/transactions/
session settings are NOT yet verified; no staging acceptance pass or remote write.
Existing bounded approval retained; no reconfirmation requested for unchanged scope.


### Session-pooler adapter implemented ? 25 October 2026

[Current implementation/evidence](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_SESSION_POOLER_IMPLEMENTATION.md)
supersedes the prior no-code DSN incompatibility finding. Trusted explicit adapter
pins the actual Dashboard host/project, preserves qualified wire user and exact
unsuffixed SQL identity/ACL/membership guards, TLS verify-full and session-only
5432. Direct compatibility retained; binding/reconciler helpers covered. 47 routing
tests and all five direct native role/session checks passed. Actual endpoint TLS
passed with operator-supplied Dashboard CA. Private credentialed console is pending
verified completion/cleanup; full staging acceptance NOT claimed. Interrupted
console history retained; recovery-first path prevents blind reprovisioning.
Full catalog API suite currently 8 passed/32 fixture errors due unrelated
billing_service datetime.UTC import under Python3.10. Normal services and billing
code untouched. Original approved artifacts/migration batch remain unchanged.
Public HTTPS/WSS, deletion policy and signed Windows remain separate pending gates.


Windows console follow-up: inherited PAGER=cat caused the reported display errors
after operator-reported recovery COMMIT. Native psql pager=off now explicit on all
invocations; disposable Windows client check passed. The pending password was for
maintenance-role read-only cleanup verification. Corrected console starts with
read-only state assertion and stops on failure; actual staging role state/smoke
remains pending private operator input. No staging success inferred from COMMIT.


### Managed read-only credential state verified ? 25 October 2026

Operator supplied screenshot from the corrected -VerifyFirst console showing
closed_roles_passwords_cleared_and_no_executor_sessions=true, successful read-only
ROLLBACK, and the launcher's Read-only check PASSED message. All five executors
are NOLOGIN with NULL passwords, expired validity and no executor sessions. This
supersedes the earlier unknown recovery-state finding. No provisioning or smoke
pass is inferred: the next displayed Password prompt is maintenance postgres for
SESSION_PROVISION.psql, before five hidden executor-password prompts. Staging
connection/session acceptance remains pending. No migrations rerun.

### Single-prompt workflow and managed smoke failure — 25 October 2026

The old repeated psql prompts are superseded by
`backend/tests/start_staging_session_smoke.ps1`, which runs one private Python
process. It asks once for the staging maintenance password, generates five
independent strong passwords in memory, provisions only the existing executors,
and always attempts cleanup. No credentials are written to arguments, result
files or application logs. A process-held lock rejects overlapping workflows.
The fixed approval deadline remains 2026-10-26 13:08:53 UTC.

Actual managed result at 2026-10-25 17:08:32 UTC: provisioning committed; the first
role's session smoke failed an unlabeled AssertionError. No role smoke passed.
Cleanup was independently verified: all five roles NOLOGIN, passwords NULL,
validity expired, no elevated flags/memberships and zero executor sessions.
Historical sanitized evidence: `tmp/c132-single-prompt-failed-20261025T170832.json`.
The red wrapper error indicates failed acceptance, not failed cleanup.

A diagnostic-only follow-up preserves every assertion and records the exact
constant session-check name without returning driver values or secrets. Local
verification: 56 unit tests passed; fresh disposable PostgreSQL verified all five
generated SCRAM passwords, direct session semantics, successful workflow and
injected-failure cleanup. Scoped Ruff passes with target Python 3.10 (the actual
launcher interpreter); Black passes. Repository default Python 3.11 upgrade lint
requests datetime.UTC, unavailable on the installed 3.10 runtime; no rules disabled.
Graphify extraction/query rerun; parser/version and graph-integrity warnings remain
and are not evidence of SQL/runtime correctness.

The diagnostic staging run is awaiting the operator's single hidden password.
Full synthetic JWT/catalog/entitlement acceptance remains pending successful
session smoke. No migrations rerun, accounts/offers created or activation enabled.
Public HTTPS/WSS, deletion-policy approval and signed/installed Windows acceptance
remain separate open gates. Existing accepted capture tests are retained.

Secure cleanup-only recovery (within the existing approval window):
`powershell -File backend/tests/start_staging_session_smoke.ps1 -Ca "C:\Users\chand\Downloads\prod-ca-2021 (1).crt" -CleanupOnly`
After the deadline stop remote work and report unresolved cleanup; do not silently
extend the approval. Credentials from an exited process cannot be reused.

### Timeout-reset defect isolated and corrected — 25 October 2026

Managed diagnostic run at 17:15:28 UTC failed specifically at
`reset_timeout_statement`; all earlier identity, ACL, local commit/rollback,
session affinity, failed-transaction cleanup and private-actor clearing assertions
passed for catalog_draft_executor. Cleanup again verified all five closed roles,
NULL passwords and zero executor sessions. No smoke acceptance pass is claimed.
Historical result: `tmp/c132-session-timeout-failed-20261025T171528.json`.

Catalog RESET ALL previously relied on connection-startup timeout defaults.
The fix shares the existing usage-pool explicit SET timeout restoration with the
catalog and maintenance reset paths: statement 10s, lock 5s, idle transaction 15s,
transaction 20s. It preserves RESET ALL, exact role/ACL checks, TLS verification,
all acceptance assertions and direct compatibility; it changes no database ACLs.
Local verification after correction: 56 unit passes, scoped Python-3.10 Ruff pass,
and fresh native PostgreSQL pass including all five SCRAM authentications and
success/failure cleanup (`tmp/c132-reset-fix-native.log`). The corrected managed
run is pending the operator's hidden input; no unattended retries are enabled.

### Three managed role passes; usage checkout timeout — 25 October 2026

Managed run at 17:20:03 UTC passed catalog_draft_executor, catalog_public_reader
and usage_binding_executor identity/ACL, transaction, session reset and checked
reuse. usage_executor returned PoolTimeout; usage_reconciler was not attempted.
Two catalog pool shutdown workers exceeded the old two-second join budget.
Final cleanup verified all five NOLOGIN/NULL-password/expired roles and zero
executor sessions. Historical safe result: `tmp/c132-pool-timeout-20261025T172003.json`.
This supersedes the zero-role-pass finding, not the pending full acceptance gate.

Inspection found per-table/per-function network round trips in usage checks and
per-table round trips in catalog checks. These are now evaluated in SQL arrays
with bool_and, requiring literal true; missing objects, unexpected table access
and absent executor function grants still fail closed. No identities, role flags,
memberships, ACL lists or timeout assertions were removed. The smoke reports safe
pool-open/session-check stages and allows a bounded 20-second worker shutdown,
matching the existing transaction timeout, instead of reporting a pass while a
normal reset is still completing. Checkout, connection and SQL deadlines remain.

Verification: 56 unit passes; fresh disposable PostgreSQL passes all five SCRAM
password authentications, direct runtime pools, success/failure cleanup, and new
negative tests for unauthorized table SELECT and missing EXECUTE on each runtime
role. Scoped tooling passes; Graphify refreshed/queried with its known extraction
warnings. Corrected managed run pending hidden input. No migrations, fixture/data
writes or permission expansions occurred on staging.

### Current failure reconciliation and launcher verification — 26 October 2026

Latest managed result (25 October 17:25:01 UTC) failed at
CONNECT_STAGING_MAINTENANCE before provisioning: OperationalError. Its cleanup-only
connection attempt also failed (OperationalError), so cleanup was NOT reverified.
The old connection wrapper discarded the driver cause; authentication versus TLS
versus routing/network cannot be established from this result. No provisioning,
migrations or business writes occurred in that invocation. Preserve this as
`tmp/c132-maintenance-connect-failed-20261025T172501.json`.

This is distinct from the preceding 17:20:03 UTC run: three role smokes passed,
usage_executor returned PoolTimeout, usage_reconciler was not attempted, and all
five roles/passwords/sessions were verified clean. That is the latest verified
remote cleanup, not proof of a fresh read after the later connection failure.
The PowerShell line-31 error was a wrapper, not the underlying failing SQL stage.

Runner now records failed_stage and allowlisted cause categories (authentication,
TLS, routing, timeout, DNS/refusal/capacity or explicitly unclassified). No driver
message substring is returned. One hidden maintenance password remains in the
running process; five strong executor passwords are automatically generated and
reused. Cleanup reconnect uses that same in-memory password and never repeats
provisioning. A per-invocation UUID/result file prevents stale-result acceptance.
The launcher verifies target/run identity and reports precise safe stage/cause,
separating failed acceptance with verified cleanup from unverified cleanup.

Local evidence: 69 tests passed, including real native PowerShell launcher runs
with no-network child fixtures for success, smoke error, cleanup error, mismatched
run identity and missing result. CLI tests prove one hidden prompt on both success
and failure, secret-free result/output, and cleanup. Disposable PostgreSQL verifies
five generated SCRAM passwords, runtime ACL denials, success/injected-failure
cleanup. Logs: `tmp/c132-launcher-orchestration-unit.log` and
`tmp/c132-launcher-orchestration-native.log`. Scoped Python-3.10 Ruff passes.
Pinned staging endpoint TCP/TLS chain and hostname passed read-only today without
login or writes; this does not retrospectively identify the failed connection.

No remote workflow retried during diagnosis/local verification. Approval cutoff
remains 26 October 2026 18:38:53 IST (13:08:53 UTC). Next controlled run must first
read the exact five-role state, recover/verify credentials if necessary, and stop
on errors. Cleanup-only recovery remains -CleanupOnly with one hidden local
password within that deadline. No migrations rerun or normal services changed.

### Managed session-pooler smoke accepted — 26 October 2026, 13:54:56 IST

Verified saved result for run d9e56e69-ff77-4af3-a08d-222b3f52526a on the sole
approved target cfmvqbjmnwklxqlpelxe: all FIVE executor roles passed actual identity,
ACL, transaction/session-setting reset and checked pool reuse tests. error and
cleanup_error are null. Operator also reported finished and supplied the console
COMPLETE screenshot. The displayed UNREPORTED stage/cause represents null failure
fields on success, not an additional error.

Final database verification: all five roles NOLOGIN, passwords NULL, validity
expired, no elevated flags or memberships, zero executor sessions. The controller
process exited; no matching workflow Python process remains. Credentials were
held only in that process; cleanup_verified=true. No migrations rerun and no
accounts or offers created. Evidence: tmp/c132-session-d9e56e69-ff77-4af3-a08d-222b3f52526a.json
and tmp/c132-single-prompt-result.json (recorded UTC 08:24:56.733274).

This supersedes the earlier connection/session-smoke pending/failure status only;
historical failures remain documented. Synthetic Auth/JWT, business catalog,
Free/Plus/Pro entitlement/concurrency/recovery acceptance has NOT run remotely in
this smoke. Public HTTPS/WSS, deletion-policy approval and signed/installed Windows
remain separate gates. C11/C13 overall completion is not claimed. No retry of this
passed smoke is required unless affected by a subsequent change.

## 26 October 2026 application acceptance continuation

The accepted schema application and all five executor connection smoke/cleanup passes are complete; older blanket migration/connection blockers are historical. The recorded local application acceptance covers 11 local two-worker application groups, injected-startup cleanup, 91 focused tests, 51 backend regressions and 15 execution regressions. A separate excluded local operational record reports a later staging pass; its execution artifacts are not part of this PR. Staging acceptance remains unverified from the committed inputs, rather than being claimed complete or described as an unexecuted run here. Physical passes are retained. Public HTTPS/WSS, signed installed Windows and irreversible deletion remain separate gates. C11/C13 are not complete.
