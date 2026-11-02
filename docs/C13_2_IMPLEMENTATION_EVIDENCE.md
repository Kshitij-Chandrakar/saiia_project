# C13.2 implementation and acceptance evidence

**Latest verified status - 26 October 2026, 17:03 IST:** [Staging application acceptance](C13_2_STAGING_APPLICATION_ACCEPTANCE.md) passed all 11 scenario groups against cfmvqbjmnwklxqlpelxe using two isolated local workers and real staging Auth/JWT/Storage. Repeated audits verified 42 allowance periods; cleanup verified all five roles closed/passwords cleared/zero sessions. No migrations or accepted physical tests were repeated. Public HTTPS/WSS, signed installed Windows, deletion approval and the existing lint gate remain separate; C11/C13 remain open.



**Current acceptance status — 25 October 2026:** The single
[current-status table](C11_C13_ACCEPTANCE_RUNBOOK.md#current-status--25-october-2026)
supersedes older blanket pending statements. Synchronized timing and controlled
JBL disconnect/reconnect passed; retain their raw/operator evidence without
repeating them. Default-off hosted relay/shared handoff and deletion preparation
are implemented and native-tested; desktop hosted transport is now integrated and packaged-tested. Irreversible deletion, new hosted physical OS checks, signed installation and staging acceptance remain distinct open gates.
Latest continuation: **51 backend native passed; 48 local native passed; 189 focused Node passed; 58 browser regressions passed** (overlapping suites, not additive). Packaged hosted acceptance: wrapper **1 passed**, embedded Playwright **2 passed**, including two workers and worker failure. Earlier counts below remain historical.
Scoped checks: scoped Ruff/ESLint and backend typing pass. Full lint
remains **60 errors / 29 warnings**, no new error pairs against recorded attribution.
Staging target cfmvqbjmnwklxqlpelxe is confirmed and owner-preflighted; migration/activation approval is pending. C11/C13 remain open.

## Acceptance follow-up (24 October 2026)

This heading and older counts below are historical. The current continuation
results and remaining gates are recorded in the 25 October section at the end.

The [acceptance runbook](C11_C13_ACCEPTANCE_RUNBOOK.md) now maps every fixed C11
gate to its exact local evidence and distinguishes development Electron, unsigned
portable Windows packaging, physical-device checks, shared schema and hosted
acceptance. Existing phase labels/policies remain unchanged.

- **48 native tests passed (110.43s)** after selecting the actual packaged exe;
  embedded Playwright **2 passed**, asserting `app.isPackaged=true` and a compiled
  `file://` renderer. Real main/preload/JWT/pool/PG/current plan/Upgrade intent/
  transcription/logout. Package is unsigned `win-unpacked`, not signed/installed.
- Physical setup smoke and one real **mic/system/Both PCM + Stop** attempt passed
  with synthetic STT discarding PCM. Two early Both attempts timed out at the unchanged PCM assertion: the test
  panel allowed Start before asynchronous Stop cleanup finished. Serialized panel
  controls and action-completion assertions fix that setup race. The final real
  three-source synchronized run passed (25.76s wrapper, Playwright 2 passed).
  Device/sleep/long-duration reliability is **not** closed. Manual silence,
  device changes/sleep, exhaustion and fault controls remain operator acceptance.
- Test-only package launcher, bounded loopback device service and accessible local
  panel are runnable with the exact commands/stop/restart checklist in the runbook.
  An initial discovery showed the offline conftest removed packaged launcher flags;
  those earlier attempts were dev-mode only. The corrected runner restores only
  synthetic C132 options after the offline boundary and asserts packaged/file URL.
- **235 combined-process tests passed**: `test_catalog_contract.py`,
  `test_catalog_store.py`, `test_commercial_admission.py`, `test_admin_access.py`.
  Root cause was the import-safety test reloading the shared module and invalidating
  exception-class identity in already-collected admin imports. It now executes the
  same source under an isolated module name with the same environment/network
  guards and assertions. Historical 234/1 results remain historical, not erased.
- **55 catalog/admin/lifecycle/pricing browser tests passed** in this scoped rerun;
  **14 catalog/money Node tests passed**, including all 32 ASCII control characters,
  angle brackets and Unicode. Earlier 57 browser/279 Node records are retained as
  separate evidence, not claimed rerun here. Production build passed (4.01s).
- Fixed **nine subscription catalog/pricing lint errors**. Generated `dist-electron`
  output is excluded along with `dist`; no source rule disabled. Full source lint
  still fails **60 errors / 29 warnings**. Every remaining error rule/message matches
  HEAD under the same config: [attribution](C13_2_LINT_ATTRIBUTION.json). No unrelated
  code rewrite. Focused changed JS lint, Python Black/Ruff and Node syntax passed.
- [Ordered staging candidates/hashes](sql/C11_C13_STAGING_MANIFEST.json) and
  [read-only preflight](sql/C11_C13_STAGING_PREFLIGHT.sql) are prepared. There are
  48 dependency candidates, **not 48 known unapplied migrations**. No isolated staging
  target/history has been supplied, connected, modified or activated; actual missing
  SQL must be reconciled with target objects/history, approved and applied separately.
- Post-change Graphify: **82 files / 1,525 nodes / 4,633 directed edges / 65 communities**;
  SQL extractor missing, **563 dangling endpoint edges**. Other extraction losses
  remain in the report. This is not a graph-health or SQL-acceptance pass.

[Packaged screenshot](assets/subscriptions/c132-packaged-current-plan.png).
Package artifact: `tmp/c132-packaged/win-unpacked/Intervucopilot Isolated Acceptance.exe`.
Executable SHA256 `5CC8C0FB38D138DB863E05C6279676147FDE820998D8968C1203F44A9F6EE6D3`;
app.asar SHA256 `7AF9BD03C09B6D1360EB53F7B5C1969F4830286099E03B0154441F0A2489E125`.
Rebuilding intentionally produces a new hash; collect it for each manual run.
Logs: `tmp/c132-acceptance-native-final.log`, `tmp/c132-combined-isolation.log`,
`tmp/c132-acceptance-browser.log`, `tmp/c132-physical-capture-smoke.log`,
`tmp/c132-physical-first-failure.md`, `tmp/c132-physical-capture-repeat.log`,
`tmp/c132-physical-capture-synchronized.log`, `tmp/c132-acceptance-eslint-final.json`.

Remaining gates: operator long-duration physical/combined reliability, signed installed/OS
integration, pre-existing repository lint, authorized isolated staging/JWT/TLS/ACL
acceptance, implemented hosted device relay/shared-stream infrastructure, and the
existing Auth-deletion/immutable-ledger privacy workflow. No new business policy
requested. The setup smoke does not close these gates. Overall C11/C13 remain open.

## Previous implementation handoff (preserved evidence)

24 October 2026. The previously missing execution integrations are implemented
locally and remain **default-off**. C11 and C13 are not declared complete.
The final native run passed **48 tests**, including two real-native browser/Electron cases. Remaining acceptance limits are recorded below; historical
partial runs are not deployment acceptance.

The [canonical approved policies](SUBSCRIPTION_APPROVED_POLICIES.md) remain the
business authority. No prices, quotas, model allocations or reset policies changed.
No shared migrations, real subscriptions, publication, provider/payment calls,
`.env` changes, commits, pushes or deployment were performed.

## Execution and persistence matrix

| Feature / transport | Implemented path | Local evidence / boundary |
| --- | --- | --- |
| Verified Free bootstrap / current account | Existing profile-bootstrap route and `GET /api/account/subscription` use verified JWT subject and the same exact immutable binding resolver. Auth supplies original signup and verification time. Pinned Free offer/fingerprint and rollout cutoff; idempotent, no expiry, paid binding preserved. Missing authority/configuration fails closed. | Native JWT/API/pool tests. No backfill or actual assignments. Explicit states and no-store DTO; checkout remains false. |
| Manual answers, buffered and streamed HTTP | Current permission and explicit unlimited `answers.completed`, native owned session and original generation-turn claim/checkpoint/complete. Actual transcript persistence, completed replay and save-only recovery reuse original state machine. | Actual planner plus deterministic provider/native transcript; duplicate/conflict/revocation/checkpoint tests retained. Default `ClosedAuthority` is unchanged when the opt-in is off. |
| Manual audio upload | Canonical `POST /transcribe/` requires verified account and explicit unlimited `audio.transcribed` under the opt-in. Manual mode only; Auto/fallback labels cannot obtain authorization. Bounded 25 MiB operational input. Desktop main retains bearer and sends multipart via validated IPC; allowlisted result and account-generation checks. | Native JWT/API with deterministic STT; Node validates forged IPC fields and late results. Actual Electron main/preload also exercises this route. STT substitutes are not live microphone/provider evidence. |
| Auto mic / system / Both | The canonical authenticated local gRPC Auto path grants a server-held lease before opening STT/capture. Database account lock/unique ownership, owner token, fence, source and current permission checks. Each answer uses the original durable native turn/transcript coordinator with the server-held capability. | Two independent gRPC workers over native PostgreSQL; synthetic PCM/STT and real JWT. Mic/system/Both dispatch, competing start, heartbeat, Stop, disconnect, silent expiry and last-allowance exhaustion. No renderer timer supplies usage. |
| Auto accounting / recovery | Maximum 15-second server leases, five-second main-process liveness pings, integer microseconds, period/paid-expiry clamping, fenced heartbeat sequence. Count authorized elapsed silence; Both has one run/slice. Stop/disconnect/expiry settles elapsed time and releases unused authorization. Current-account reads/lifecycle sweep reconcile expiry. | Existing native ownership/replay/revocation/period tests plus transport acceptance. Backend monotonic deadlines are conservative: a small unused tail may remain; it is never charged as stopped time. Last-allowance test explicitly settles a synthetic silent tail at its returned SQL deadline before asserting exhausted restart. |
| Screen New / Passage / Data / clarification / follow-up | Canonical `POST /api/screen/analyze-context`: owned session, server-owned saved thread history and revision, validated image/context provenance, feature checks and original provider formatter. Passage/reference alone does not reserve an analysis. A new successfully answered item charges one; multiple answered items require corresponding atomic capacity. Free follow-ups are denied even when client answer history is hidden; paid follow-ups are allowed. | Native API/provider substitute tests cover five analyses/exhaustion, Passage-to-question, actual clarification, paid/denied follow-ups, rollback, concurrency and lost acknowledgement. Screen/Sketch are distinct services. |
| Screen durable results / retries | Saved response and settlement commit together. Stable operation/clarification phase identity excludes changing transport request ID. Server aliases bind clarification to a saved needs-clarification response; retries return the exact saved content with the current transport envelope and do not regenerate/debit. `GET /api/screen/sessions/{UUID}/results` provides paginated owner-only validated DTOs. | Native independent concurrent requests, replay and lost-commit acknowledgement, owner read, stale worker fencing/reaper. No images or answer text enter usage/audit metadata. Personal Screen responses are in owner-owned result storage. |
| Resume upload / capacity | Existing upload, extraction, reviewed-profile and indexing services are retained. Native metadata insertion serializes ready/pending capacity across devices. Stable same-key file identity/hash and object readback handle retries without another stored slot. Stored cap differs from replacement allowance; explicit unlimited remains explicit. | Actual authenticated upload/extract/confirm routes, native original resume/profile/chunk schema and activation RPC, synthetic object store/parser and real existing indexer. Concurrent Free uploads yield one candidate. No real Supabase Storage/PDF/provider acceptance is claimed. |
| Resume initial upload / replacement | Permanent successful-upload history survives file deletion. Only indexed activation reserves and settles a replacement, in the activation transaction and its current IST monthly period. Failed indexing never charges or replaces the old usable file. Same reviewed activation identity recovers a lost acknowledgement without reindex/charge; conflicting review is rejected. | Native initial-versus-replacement, delete/reupload, failed index, rollback, duplicate upload, uncertain activation/readback tests. Review can span a period without charging the original upload period. |
| Resume downgrade / active set / reindex | Preserve excess ready files; new uploads blocked while above cap. `POST /api/resumes/active-set` selects owned ready files within current cap and pins selection to current binding revision. Grounding checks this set; stale plan selection is not reused. Website Resumes exposes an over-cap chooser, and readiness DTOs mark denied files non-generatable. Rebuild uses original chunks with native fenced generation activation, no replacement debit. | Native paid-to-Free selection and retained files; desktop/narrow chooser Playwright fixture. Native checks remain mandatory. No automatic file deletion is introduced by downgrade. |
| Clipboard / My Answers | Existing owner/session lock, stable key/hash, reserve -> existing answer insert -> settle in one native transaction. Only committed new saves count. Immutable for every plan; reads/period reset/downgrade preserve existing answers. | Existing native concurrency, lost response, conflict, exhaustion and ownership tests. Main retains pending retry identity after uncertain errors. No OS clipboard-read quota and no individual edit/delete feature added. |
| AI Notes | Existing Notes generator/formatter and original current Notes table, native owner/transcript reads, current feature and explicit unlimited allowance. Existing usage operation identity claims once. Native Notes row/version result and settlement commit together; prior-key replay returns the prior exact result even after regeneration. | Actual JWT/API/native tests with deterministic generator, duplicate/conflicting identities, historical replay, crash sweep. No Notes quota invented. Website retains same key for uncertain retry; explicit successful new generation gets a new key. |
| Ask AI | Existing Ask AI context/generator and durable request-key/atomic message-pair primitives, now through a narrow native adapter. Owner and current explicit-unlimited feature checks before claim/replay/completion. Stale claim can be fenced/failed but is never silently redispatched. | Actual JWT/API/native generator substitute, message persistence, equivalent/conflicting retries and current authority. Ask AI is not the deferred customer-support chatbot. |
| History / transcript exports | Current registered feature gate plus native owner session/transcript reads. Existing pagination and export formatter; approved unlimited means no added quota. Clear Transcript reuses the existing permanent-delete function and its existing eligibility policy. | Native history/export and cross-owner checks; existing session/transcript regressions. Historical read access is not a new provider dispatch. Direct client transcript inserts are explicitly closed in account mode. |
| Job contexts / registered feature inventory | Existing authenticated owner-specific job-context handlers are preceded by `job_context.manage` or `job_context.extract` authority. Existing operational consent, provider readiness and request safeguards remain separate. Manual answer/grounding/model eligibility still uses configured catalog and original readiness checks. | Existing regression/ownership boundaries; no new subscription quota or support promise. Native subscription tests do not claim live job-document extraction acceptance. |
| Electron current plan / Upgrade / cleanup | Real main keeps bearer; existing Buy Credits displays authoritative current plan/Auto availability. Upgrade opens only the trusted website `/#pricing`. Refresh on focus/15 seconds and account boundaries. Main signals immediate plan invalidation on auth/context changes and closes gRPC; stale account responses/audio are ignored and private question/answer state is cleared. | Actual Windows Electron main + secure stored synthetic login + existing preload + renderer + real JWT/API/native DB, including Upgrade and logout. Node heartbeat and stale-result tests. No pricing cards in Electron. No packaged installed-app or physical audio acceptance is claimed. |
| Alternate / legacy transports | Opt-in rejects legacy Auto WebSockets, unauthenticated/local/manual gRPC, legacy screen/resume/job-context/audio-system paths, direct transcript insert and unsupported source dispatch before provider work. Canonical gRPC remains loopback-only; hosted remote gRPC stays closed. | Native bypass tests and existing admission/transport regressions. Unsupported paths are unavailable, never a commercial bypass. Legacy opt-off behavior is retained. |

## Recovery, identity and transaction guarantees

Account lock precedes resource state; current binding and exact supported terms
are rechecked at mutation boundaries. Application principal has function EXECUTE
only, no superuser, RLS bypass, role memberships or direct accounting table rights.
Existing object/chunk services retain their backend storage credential; it is not
subscription authorization. Native wrappers are not exposed as public PostgREST RPCs.

Screen response/charge, resume activation/profile/charge and Notes result/charge
are atomic. No successful response is shown before confirmation. A failed or lost
acknowledgement is not permission to generate again. Same-key read/replay resolves
committed results; old processing attempts are not redispatched. A five-second,
50-account bounded recovery sweep fences expired Screen/Notes workers and releases
only when atomic storage proves no saved result exists. Multiple sweepers serialize
on account; stale completion is rejected. Clipboard and existing answer/Sketch
checkpoints retain their previously accepted recovery behavior.

Auto server capability never reaches the renderer. Permission loss denies new
renewal/dispatch and cleanup can settle after JWT expiry without granting access.
Audio forwarding is bounded by the server-held monotonic deadline; Stop/disconnect
revokes forwarding before slower device cleanup. Five-second heartbeat checks and
the 15-second maximum authorization bound are technical failure windows, not quotas.
No charge beyond SQL authorization expiry. A lost initial lease acknowledgement may
leave a durable bounded authorization to reconcile; it never opens provider capture
without a confirmed grant. Native SQL, not device timers/audio sample counts, owns usage.

Cancellation without a committed Screen result releases its reservation; a completed
result replay cannot charge again. Clarification is linked to the original retained
question turn; transport request changes do not manufacture new billable generations.
Resume candidate review is not a successful replacement; activation alone charges.
Neither deleting a file nor restarting a client restores initial-upload history.

## Prepared migration scope and default-off composition

Previously prepared migrations `20261024010000` through `20261024060000` remain
unchanged: account integration, Auto ledger, Clipboard, Sketch, manual execution,
and verified paid-period scheduling. This continuation adds:

1. `20261024070000_subscription_auto_transport.sql`: source-bound backend lease
   authorization/disconnect and original turn-function wrappers.
2. `20261024080000_subscription_screen_results.sql`: owner thread/result/retry
   provenance, original usage-ledger settlement helper, safe result retrieval.
3. `20261024090000_subscription_resume_settlement.sql`: permanent initial history,
   staged upload identity, capacity/active set, original indexed activation with
   transactional replacement settlement and fenced reindex.
4. `20261024100000_subscription_auxiliary_execution.sql`: wrappers for original
   history/Notes/Ask AI storage, exact historical Notes retry results and bounded
   result recovery sweep.

They require the existing resume activation, transcript permanent-delete,
Notes and atomic Ask AI migrations; native tests apply those actual repository
prerequisites rather than claiming minimal fake tables establish compatibility.
No shipped LOGIN, role membership, real user, offer or binding seed. New tables
use forced RLS, private functions fixed search paths and restricted EXECUTE.
No shared migration was applied and no applied historical migration was rewritten.

`SUBSCRIPTIONS_ENABLED=false` and empty `SUBSCRIPTIONS_DSN` remain defaults.
The existing secure backend configuration mechanism supplies a restricted
`usage_executor` direct connection only when explicitly enabled. Pool max four,
wait one second, max eight queued waits, connect three seconds, lock five seconds,
statement ten seconds, transaction twenty seconds on PostgreSQL 17. Rollback/reset
and role/ACL checks precede reuse. No imports connect; no actor connection GUC leaks.

Rollout: apply reviewed prerequisites/additions only after separate target approval;
preflight roles/functions/exact pinned Free configuration/JWT project and run the
acceptance below before opting in. Real paid transitions still require C12 evidence.
Rollback: disable this opt-in and new intake, stop capture, preserve bindings,
immutable terms/results/events and reconcile outstanding work. Do not reset usage,
drop ledgers or silently assign Free. Re-enable only with compatible schema/code.

## Verification and limitations

Actual final results:

| Check | Result |
| --- | --- |
| C13.2 native integration | **48 passed** (105.04s), PostgreSQL 17.11; includes real JWT and actual Windows Electron main/preload/renderer, not merely a browser preload mock |
| Native-run Playwright subcases | **2 passed**: browser renderer/manual persistence and actual Electron Current plan/Upgrade/transcription/logout |
| Backend regression groups | **662 + 105 passed** (separate runs; no assertion weakening) |
| Existing native usage / catalog adapter | **17 + 12 passed**, separate disposable clusters |
| Catalog/admin browser regressions | **57 passed** |
| Resume chooser browser | **1 passed**, mocked identity/data explicitly, desktop and 390px |
| Focused Node/client regressions | **279 passed** |
| Production frontend build | **Passed**, existing large-chunk advisory retained |
| Black / Ruff E4,E7,E9,F,I | **Passed**, eight focused commercial/native-test files |
| Strict mypy | **Passed**, seven commercial integration modules, silent followed imports/ignored missing third-party stubs as in the accepted tooling convention |
| Changed UI/fixture ESLint / Electron syntax / Python API syntax | **0 lint errors; 4 existing hook warnings in the setup screen**. Electron/Python syntax passed; no lint rules disabled |
| Full repository ESLint | **Failed: 853 errors, 33 warnings across 24 error-containing files**. Tooling now executes; broad existing vendor/unused/undefined/prototype issues were not rewritten to hide failure |
| Whitespace | `git diff --check` passed; scoped added-file whitespace checked separately |

Evidence is retained under `tmp/c132-*.log`; screenshots are under `docs/assets/subscriptions/`.

- Native integration: actual PostgreSQL 17.11, restricted independent connections,
  actual JWT verification and deterministic providers/object storage/PCM.
- Broader backend regressions: **662 passed** in one process, including Screen,
  resume routes/services, Notes, Ask AI, gRPC, session generation, Sketch,
  catalog/admission/IST-period/usage contracts.
- Existing catalog/admin Playwright regressions: **57 passed**. Resume active-set
  chooser: **1 passed**, explicitly mocked auth/API. The real-native browser and
  Windows Electron cases run inside the native suite and are separately identified.
- Existing native usage **17 passed**, adapter **12 passed** in fresh disposable
  clusters. Earlier draft/lifecycle native evidence remains historical, not rerun
  deployment evidence.
- Restored the dependencies already imported by ESLint: explicit `@eslint/js`,
  `globals`, React Hooks/Refresh plugins in manifest and lockfile. Node test/config
  globals are scoped correctly. No rules disabled. Full-repository lint now runs
  and exposes existing errors; it is not a pass. Scoped changed component/fixture
  lint, strict typing, formatter and production build results are recorded below.
- No PDF acceptance: retained test launcher stubs unused `fitz` imports and raises
  if PDF execution is attempted. Synthetic TXT resume acceptance is real native
  metadata/profile/index/settlement evidence, not live Supabase object storage.
- No installed release executable was found in repository artifacts or the usual
  local Programs application directories. The actual installed Electron runtime
  dependency did run the real main/preload/renderer. Packaged release, real Windows
  mic/default-output devices, disconnect/sleep and live provider acceptance still
  require the manual procedure below. They are not fabricated from browser fixtures.
- Historical older browser/PDF/combined-process reload failures remain historical
  failed evidence. The current 662-case process and additional 105-case process passed; that does not relabel the
  separate older failure as passed. No timeout budgets/assertions were weakened.

Screenshots: [actual Electron](assets/subscriptions/c132-electron-current-plan.png),
[native-backed renderer desktop](assets/subscriptions/c132-current-plan-desktop.png),
[narrow renderer](assets/subscriptions/c132-current-plan-mobile.png),
[resume chooser desktop](assets/subscriptions/c132-resume-access-desktop.png),
[resume chooser narrow](assets/subscriptions/c132-resume-access-mobile.png).
The chooser screenshots use fixtures; the Electron screenshot uses the native JWT path.

## Repeatable local acceptance

From the repository root on this machine (retained runtime; normal `.env` untouched):

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
& E:/deepfake_envs/SaIIA/python.exe "$env:TEMP/c113c-test-launch.py" backend/tests/test_subscription_integration_native.py --pg-bin C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin
```

The runner owns its PostgreSQL cluster, ephemeral API bridge, synthetic auth and
Playwright frontend at `127.0.0.1:5186`. It stops them after acceptance. It neither
uses nor reconfigures the normal `localhost:5173` environment. Do not point the
restricted runtime at a shared database or use real tokens/accounts for this test.
Set `$env:PWDEBUG='1'` before the command to step the browser/Electron tests;
remove it afterward. `Ctrl+C` stops an interactive run; harness finally blocks
close owned servers/cluster. Retained runtime downloads are not deleted.

1. Inspect the native-backed Current plan/Auto balance in Buy Credits; click Upgrade.
   The test captures the trusted website intent without launching payment URLs.
2. Inspect actual Electron IPC transcription with the deterministic STT substitute,
   then logout and verify protected plan text disappears immediately.
3. Follow native test HTTP steps for Screen capture/reference/clarification, same-key
   retry, failed result and owner-only saved-result retrieval.
4. For resumes, use synthetic TXT import -> extraction -> reviewed confirmation,
   retry a committed activation, then simulate trusted paid expiry. Retained files
   remain; select the permitted set through the website/owned active-set API.
5. Run two gRPC workers/devices in the Auto cases: second start denied, silent time
   counts once, Stop/disconnect/expiry fence the first owner, last allowance is bounded.
6. Follow Notes/Ask AI tests to compare saved exact-key replay with deliberate new
   generation. No provider is called on completed replay.

Before installed release acceptance: package only reviewed local code, isolate
userData and synthetic backend/configuration, and keep payments/commercial admission
closed. With deterministic local provider transport, test mic, system and Both on
Windows devices; confirm capture indicator stops on Stop, lease loss, network loss,
sleep/resume and logout/account switch. Confirm only one account-wide run, stale
owners cannot resume, consumed usage survives restart, paid expiry preserves data,
and Upgrade opens the trusted website. No real subscriptions/backfill or live calls
are authorized by these instructions. Shared/hosted/JWT/TLS deployment acceptance
remains a separate explicitly authorized gate.

The fixed [C11 checklist](C11_CLOSURE_CHECKLIST.md) retains its original scope.
Payments are C12; deployment/support and live operations are not inferred from
local catalog or C13.2 results. The prior combined-process class-reload failure
remains **234 pass / 1 fail** in its historical command; it was not rerun or
relabeled as resolved by these different passing groups.

## Post-change Graphify

Fresh scoped AST extraction: **73 files, 1,459 nodes, 4,523 directed edges,
59 communities** in `tmp/c132-graph/graphify-out/`. The root historical graph
was not replaced. SQL extraction is unavailable (`tree_sitter_sql` absent);
diagnostics report **521 dangling endpoint edges and 231 collapsed directed
edges**. No graph-health or SQL-acceptance pass is claimed. Native tests provide
SQL acceptance. No semantic/LLM extraction was performed (0 input/output tokens).

## Files changed in this continuation

- Backend commercial adapters: `subscription_auto.py`, `subscription_screen.py`,
  `subscription_resume.py`, `subscription_auxiliary.py`, `subscription_execution.py`,
  `subscription_service.py`, `subscription_database.py`, `boundary.py`.
- Existing backend paths: `api/generate.py`, `api/screen_context.py`, `api/resumes.py`,
  `api/transcribe.py`, `api/interview_sessions.py`, `cloud/cloud_resume.py`,
  `grpc_cloud_context.py`, `grpc_server.py`, `main.py`.
- Four additive migrations `20261024070000` through `20261024100000` listed above;
  `backend/tests/test_subscription_integration_native.py` covers the integrated paths.
- Electron main/preload/auth/gRPC client; renderer `App.jsx`, existing startup
  choice/setup components; website auth/resume API, onboarding upload and retry
  state; new `ResumeAccessSelection.jsx` and scoped resume styling.
- Frontend manifest/lock/ESLint configuration, focused Node tests, actual-native
  browser/Electron and resume chooser Playwright tests/fixtures; screenshots above.
- This record, fixed C11 checklist, canonical policies, milestone, implementation
  plan, readiness audit, tracker/roadmap and admin guide. Unrelated dirty work is
  preserved; this is not an attribution of all repository changes to this task.

## Acceptance status

All independent implementation in this continuation is delivered and locally
verified with synthetic identities/providers and disposable native storage.
**C13.2 release acceptance remains open** for packaged/installed Windows physical
capture and the full repository lint gate; shared/hosted/JWT/TLS/deployment gates
remain explicitly unverified. No installed release artifact was available, and
unrelated lint failures were not weakened or silently fixed. The pre-existing
account-wide Auth-deletion/immutable-ledger privacy prerequisite also remains a
separate release concern; owner logout/account-switch cleanup is implemented and
tested, not a claim that Auth deletion bypasses C13.1 RESTRICT/history protections.
There is no new business-policy decision requested and no real activation/backfill
performed. Overall C11/C13 are not closed.

## Guided physical follow-up: subscription busy guidance

See [operator results](C13_2_PHYSICAL_ACCEPTANCE_RESULTS.md). A packaged second
client was denied but its error was masked by generic STT guidance; this exposed
a real main-process presentation defect. Restricted database enforcement was
unchanged. Recognized subscription errors now retain safe allowlisted codes and
static guidance, never raw server error text. Added startup regression: focused
gRPC Node suite 51 passed. Actual package/native physical concurrency rerun
passed (wrapper 1 passed, embedded Playwright 2 passed): microphone active,
second packaged client exact subscription_auto_busy, mic/system/Both PCM/Stop,
JWT/current plan/Upgrade/logout. Earlier failed attempt remains in session3 log.
No assertion relaxed. Interactive and automated second-client paths share the
same assertions. Physical panel owner-track cleanup on error is separate from
backend authorization. Current guided lease/device/restart/exhaustion checks
remain pending in the live results record; no overall phase closure inferred.

## Guided physical restart follow-up

[Operator record](C13_2_PHYSICAL_ACCEPTANCE_RESULTS.md) retains the failed manual
restart/harness attempts and subsequent corrected AUTOMATED packaged pass.
Windows process-wrapper/disposed-handle and racing child-termination issues were
fixed in the test harness, not backend accounting. Verify process death explicitly,
then same offer, retained non-zero settled use, zero reservation and no capture
after relaunch. Parallel browser/Desktop tests now have distinct synthetic Auth
accounts, preserving the browser's exact untouched allowance assertion.
Final restart acceptance: native wrapper 1 passed (25.96s), Playwright 2 passed;
physical mic/system/Both and actual native/JWT/IPC retained. The prior operator
lease-expiry result is separately passed with exact server deadline accounting.
The currently open guided panel awaits operator post-restart observation; sleep/
device changes, exhaustion/final logout and installed/shared gates remain open.


## Session 7 independent acceptance preparation

Authoritative current summary is the runbook current-status table. Fresh full
ESLint: 60 errors / 29 warnings; zero current error rule/message/file pairs outside
C13_2_LINT_ATTRIBUTION.json. Focused Electron spec ESLint and Node syntax passed.
All 48 migration manifest hashes match repository bytes. No staging target has
been selected or connected; target-specific unapplied SQL remains unknown.

Graphify refreshed after the scoped test cleanup change using Python311 (the
older default Graphify API rejected root=; this failed invocation was corrected,
not treated as a pass). Final extraction command exited 0: 82 files, 1526 nodes,
4634 directed edges, 66 communities; 564 dangling edges and 233 collapsed directed
endpoint edges, missing SQL extractor. AST-only, zero LLM tokens; neither graph
health nor SQL acceptance is claimed. See tmp/c132-session7-graphify.log and the
scoped tmp/c132-graph/graphify-out/GRAPH_REPORT.md.

Current package executable SHA256:
5CC8C0FB38D138DB863E05C6279676147FDE820998D8968C1203F44A9F6EE6D3.
Current app.asar SHA256:
8D7C65D9A3A61DC76A1C353B96B978E3317F64BD270B4147C9C62EABD5388B73.
These identify the unsigned portable fixture, not a signed installed release.

Hosted source inspection: grpc_server.InterviewRealtimeService.CheckHealth and
StreamInterview explicitly deny hosted mode; CommercialBoundaryMiddleware denies
legacy WebSockets in subscription/hosted modes. Session-generation TurnStore uses
durable backend RPC, and account Auto leases are database-backed. Neither is an
implemented hosted audio relay or shared live-stream router. api/auth.py explicitly
retains a local-only in-memory desktop handoff store; multi-worker handoff needs
separate hardening. Existing provider websocket forwarding is not authority-aware
hosted capture acceptance. No routes were opened.

Privacy inspection: account_plan_bindings -> auth.users is ON DELETE RESTRICT;
usage_events mutation/truncation is rejected. Source search found no completed
account-wide deletion orchestrator/API. Required additional implementation must
preserve ledger integrity while fulfilling an approved identity/data retention
and deletion workflow, with disposable-user tests for outstanding operations,
reconciliation, access revocation, personal-content deletion and retained audit
minimization. Do not weaken immutable triggers/FKs or conflate logout with deletion.
No deletion migration is prepared without that reviewed contract.

Session 7 focused native Auto rerun: 6 passed / 42 deselected in 37.27s
(tmp/c132-session7-native-auto.log). Covers mic/system/Both Stop, disconnect,
expiry and final-tail exhaustion denial with synthetic device/provider substitutes
and independent disposable native database; not human physical acceptance.
Windows Get-AuthenticodeSignature returned NotSigned for the current portable exe.
No signed installed-release acceptance inferred. Four updated acceptance documents
have no trailing whitespace. Current live physical environment remains running
for the requested operator stopwatch check.


Session 7 final operator/teardown update: active-capture logout observed microphone
indicator off and API401. Interactive package/browser wrapper 1 passed /
47 deselected (499.15s), Playwright2 passed. Harness, desktop and session7 PG are
stopped; normal5188 and pre-existing October23 PG cluster retained. Longer silent
run Stop was observed, but stopwatch120s vs native exact129.233757s remains an
unresolved measurement-alignment gap. Native timestamps and charged duration
agree exactly; do not claim that resolves physical start/stop timing. See the
current-status table and detailed operator results; no overall phase closure.


Operator timing clarification: user reports a possible mistake/delay during the
two-minute measurement. Manual duration comparison is inconclusive rather than
a demonstrated accounting defect; native authorized/charged durations match.
No exact physical timing pass inferred. Current runbook table updated; original
results retained. No runtime or allowance changes.

### Controlled JBL Bluetooth disconnect acceptance — 25 October 2026
Operator plus diagnostic evidence now confirms automatic microphone teardown on JBL Tune 770NC disconnect, zero remaining reservation, and unchanged stopped usage (69.553626 seconds). Detailed before/after track/device events and historical ambiguous trial remain in [physical acceptance results](C13_2_PHYSICAL_ACCEPTANCE_RESULTS.md). This is unsigned isolated packaged-device evidence, not signed/installed or hosted acceptance.


## Final local continuation verification - 25 October 2026

Accepted synchronized physical timing and controlled JBL disconnect/reconnect
were NOT repeated. Historical failures remain in the physical results and logs.
The accepted JBL interactive wrapper completed 1 passed / 47 deselected,
1206.25 seconds, embedded Playwright 2 passed (`tmp/c132-bluetooth-retest.log`).

### Runtime changes retained and verified

- `hosted_audio.py` and `hosted_coordination.py`: default-off authenticated client
  PCM relay, existing session/lease/fence/durable-turn execution, shared encrypted
  auth handoff, account access barrier and closed deletion preparation. No second
  entitlement/permission/metering authority. The relay rejects non-object Start
  JSON safely before dispatch; strict frame sizes/sequences and operational rate
  limits fail closed. Legacy hosted WS/gRPC remain denied.
- `20261024110000_subscription_relay_privacy.sql`: four private tables, restricted
  functions, current/usage guard and restrictive authenticated privacy policies.
  No applied migration was edited. Existing pool preflight checks the additions.
- `supabase_auth.py`, `api/auth.py`, boundary/main/config and internal gRPC relay
  composition retain verified identity and no-store/error boundaries. Valid JWTs
  for absent resource/account rows retain original owned-resource 404 behavior;
  the deletion guard denies marked accounts, not every unknown resource lookup.
- The earlier combined native run had 66 passed / 1 failed / 1 deselected:
  resume unknown-subject read returned 403 instead of the established 404. The
  guard was corrected; the original assertion was retained. Final 69-case run
  includes that regression and passes. No weakening/relabeling of that failure.
- Native WASAPI stop interruption, cached device-readiness refresh, and lazy
  microphone ended-event handling were implemented before the accepted JBL trial.
  Capture-loss never auto-falls back; their accepted physical evidence is retained.
- Electron expired guidance now says check remaining allowance and explains that
  a tiny remaining balance may not support safe capture. It no longer recommends
  blindly starting a new run. Node checks preserve the exact allowlisted error and
  one startup transport attempt; no automatic write/Start retry was added.

### Near-exhaustion interpretation

The physical 23082us residual is NOT rounded away, forfeited or called genuine
exhaustion. The server monotonic deadline is anchored before the SQL round trip;
validation/capture startup may consume that conservative authorization window.
`subscription_auto_expired` therefore differs from `subscription_auto_exhausted`.
No capture/dispatch is allowed after the conservative deadline. SQL settles only
its actual authorized interval; stopped time cannot eliminate the residual.

`test_hosted_near_exhaustion_tail_is_not_forfeited_or_charged_while_stopped`
exercises the actual WS/lease path with one second remaining: bounded expiry,
used <= allowance, zero reserved after stop, unchanged stopped usage, no generated
answer. To separately test genuine exhaustion it deliberately obtains an ACTIVE
synthetic silent authorization and holds it to its SQL deadline, then asserts
`subscription_auto_exhausted` and no additional STT creation. This is NOT a
production cleanup instruction and not a forced counter update. Native worker
concurrency tests retain single-run ownership; SQL/Python period comparisons
cover IST days, signup anchors, leap years and historical retry/new-period identity.
No quota reset/minimum charge/automatic restart policy was introduced.

### Exact executable results

| Check | Result | Raw evidence |
| --- | --- | --- |
| Account + relay actual service/native integration | 69 passed, 1 browser case deselected; 170.91s | `tmp/c132-final-native.log` |
| Final hosted/usage/period/admission/admin/native audio regressions | 178 passed; 103.07s; includes latest malformed Start guard | `tmp/c132-final-boundaries2.log` |
| Read-only staging preflight on disposable PostgreSQL + ordered source hashes | 1 passed, 23 deselected; 11.85s; deliberately missing history with present objects is reported, no ledger/history write | `tmp/c132-final-preflight-test.log` |
| Focused Node account/Auto/catalog/retry tests | 172 passed | `tmp/c132-final-node.log` |
| Browser workspace/lifecycle/presentation/pricing/resume chooser fixtures | 58 passed, 1 skipped; 54.2s | `tmp/c132-final-browser.log` |
| Actual JWT/native PG browser + unsigned Electron main/preload renderer | Wrapper 1 passed / 47 deselected, 20.34s; embedded Playwright 2 passed, 7.1s; no physical capture | `tmp/c132-final-packaged.log` |
| Production renderer, panel and unsigned package build | Exit 0; existing large-bundle and unsigned package metadata warnings retained | `tmp/c132-final-build.log` |
| Black | Seven selected changed/new Python files unchanged by --check | `tmp/c132-final-black-check.log` |
| Ruff, Python 3.10 target | All checks passed for five relay/privacy/new acceptance files | `tmp/c132-final-ruff.log` |
| mypy | No issues in two relay/coordination source modules | `tmp/c132-final-mypy.log` |
| Changed-file ESLint | Exit 0 | `tmp/c132-final-scoped-eslint.log` |
| Full ESLint | 60 errors / 29 warnings; zero new error rule/message pairs versus existing HEAD attribution | `tmp/c132-final-eslint.json`, `docs/C13_2_LINT_ATTRIBUTION.json` |

Browser fixture success is not native persistence evidence; the separate native
and real JWT/package runs supply that. The optional pricing visual case skipped
because CATALOG_VISUAL_URL was absent; it is not relabeled passed. No new visual
pricing acceptance was needed for these backend/guidance changes. A mistyped
initial regression command referenced a nonexistent test filename and collected
no tests; the corrected command/result above is authoritative, not a claimed pass.

### Graphify and external acceptance packet

Fresh scoped AST graph: 92 files, 1629 nodes, 5038 directed edges, 73 communities
(after final preflight-test extraction refresh). Query traversed
SharedHandoff / AccountAutoLease / HostedCoordination / hosted_audio to existing
service/execution nodes. Root historical graph was preserved. SQL extraction is
incomplete (tree_sitter_sql absent), 612 dangling endpoints and 270 collapsed
same-endpoint edges were reported; this is NOT a clean graph-health or runtime
correctness pass. Skill/package version warning (0.9.1 vs 0.9.29) is retained;
no global skill/tool install was changed. Artifacts: `tmp/c132-graph/graphify-out/`
and `tmp/c132-final-graph-query.log`.

[Relay/privacy review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md) contains exact
protocol, roles/configuration, migration/hash, rollback, privacy inventory and
concrete retention/unlink proposal. Previous 48 migration hashes match source;
manifest now contains 49 CANDIDATES, not 49 unapplied migrations. No exact isolated
staging target exists in the supplied context; no remote connection was attempted.
The new migration SHA256 is
`0ab2802ca886767c8d68fb525903460eaabd04c417305fad20e4cad162525166`.

| Remaining requirement | Current limitation | Concrete next action |
| --- | --- | --- |
| Hosted released-client/deployed end-to-end | Server relay and real protocol clients tested; shipped Electron capture still uses loopback gRPC, not released WSS/mixing composition | Review/implement compatible desktop hosted transport delivery, then accept over approved staging WSS/TLS with two workers before enabling hosted capture |
| Irreversible deletion | Preparation/revocation/barrier passes; purge/outbox/Auth unlink remains intentionally unavailable | Approve precise content/ledger retention and stable-identity unlink semantics from review proposal, then implement resumable purge without removing immutable protections |
| Staging schema/roles/hosted acceptance | No identified disposable target; exact unapplied set unknown | Owner identifies isolated project and returns read-only history/object/ACL preflight; approve resulting exact change set before writes |
| Signed/installed Windows | Current artifact explicitly NotSigned; no approved signed build/test VM supplied | Supply authorized signing/build artifact and isolated Windows installation environment; execute existing OS checklist |
| Repository lint | Existing attributed 60 errors / 29 warnings | Owners resolve baseline in separate authorized cleanup without weakening rules |

C11/C13 and C13.2 release acceptance remain OPEN. This local continuation does not
claim hosted activation, complete deletion or installed acceptance. No shared
migration, real assignment/deletion, production setting, provider/payment call,
real offer publication, .env edit, commit, push or deployment occurred.


### Repeatable backend runner and final source checks
The existing `backend/tests/run_subscription_acceptance.py` now supports
`--backend`: closed relay/privacy, usage and IST native acceptance without opening
Electron or requiring a packaged executable. Final execution **50 passed in
104.70s**, exit 0 (`tmp/c132-final-backend-runner.log`). These overlap earlier
suite counts and must not be summed as unique cases. The runner accepts only a
local PostgreSQL binary directory, never a remote DSN, and rejects combining
backend mode with physical/full packaged modes. Scoped runner Ruff passes.
Commands are in the [review packet](C13_HOSTED_RELAY_PRIVACY_REVIEW.md).

Final document checks: five current evidence/runbook/checklist/review files decode
as UTF-8, their local links exist, and all 49 migration hashes match source.
Graphify was refreshed after the runner/test changes: **92 files, 1629 nodes,
5038 edges, 73 communities**; extraction limitations above remain unchanged.
Normal unrelated preview listener 127.0.0.1:5188 was preserved; task-owned physical
session ended after the accepted logout, and automated test workers/clusters were
cleaned by their fixtures. No request to repeat accepted physical trials was made.


## Desktop hosted transport continuation - 25 October 2026

This supersedes the prior desktop-hosted-client implementation gap only. Accepted
synchronized timing/JBL evidence was retained and NOT repeated. C11/C13 remain open;
C12 payments is not started. The owner explicitly confirms no isolated staging
project is designated: no Saiia-dev/remote connection or change is permitted.

### Implemented path and boundaries

`App.jsx`/`createGrpcAutoSession` now selects the explicit default-off hosted path
without acquiring a microphone before authorization. Existing preload IPC channels
are reused unchanged. `GrpcRealtimeClient` keeps auth in main and selects
`hosted_audio_transport.cjs`, adapting existing answer/retry/recovery DTOs rather
than adding an answer/entitlement engine. Destination is trusted process configuration
only: HTTPS/WSS, certificate checking, no embedded credentials/query/hash/path or
redirects. A private test-entry constructor injection alone permits loopback WS;
no renderer or NODE_ENV flag grants that exception.

Authenticated/no-store exact GET `/api/account/audio/capabilities` verifies protocol
and deployment designation/current authority before a socket/capture is opened.
The WS route requires designation as well as existing authority/schema/operational
flags. Ready/PCM/Pong/Stop use the reviewed relay protocol. Optional selected resume
and job-context IDs are passed into existing server-owned context validation;
unknown fields remain rejected. No catalog, permission or metering authority is
replaced. Missing configuration/version/schema/grants/current access fails closed.

The `ws` direct dependency is pinned to 8.22.0 for parser-enforced 4 MiB input bounds,
redirect refusal, five-second handshake and disabled compression. Capability bodies
are limited to 4096 bytes while streaming, audio waits one acknowledgment at a time,
WS bufferedAmount is capped at 12800 bytes, pings are bounded, and existing stale-frame
rules apply to every hosted source. There is no automatic socket reconnect/PCM replay
or unmetered transport fallback. Local gRPC/manual routes remain intact when hosted
audio is off; existing authenticated manual transcription/answer regressions pass.

`hosted_audio_capture.js` reuses existing Web Audio PCM capture. Mic/system/Both
start only after ready, Both mixes once, and Windows loopback permission is restricted
to the current main frame and one current authorized system/Both run. Only audio
crosses IPC/relay; the required low-frame-rate display track is never forwarded.
Stop, input loss, account cleanup and connection loss stop all owned tracks and
AudioContexts. An AbortSignal also releases an already opened mic while system
selection is pending and stops a late-acquired source after cancellation. Main pushes
hosted close/failure snapshots promptly. Server leases remain the accounting authority.

### Duplicate connection replay defect resolved

Review found that replaying the same stream ID could otherwise return the original
Auto lease to a second connection. Additive migration
`20261025010000_subscription_relay_connections.sql` claims the stream once BEFORE
lease/STT creation. A losing replay returns `subscription_relay_replay`, cannot open
another pipeline and cannot stop the original lease. Native two-process tests now
assert the exact replay denial and successful original forwarding afterward, then
worker death, deadline recovery and rejection of the old stream. Immutable SQL
history and existing Auto lease/idempotency primitives remain unchanged.

The private RLS-forced claim table and fixed-search-path SECURITY DEFINER function
are usage_executor-only with no LOGIN/membership/direct-table grant. New migration
SHA256: `14d30cb9b0bc46755f6ce2ef3b23108176b558774ffc8df1ab9660f1795509da`.
All 50 candidate source hashes match. This is NOT an unapplied/shared change list.
The prior 49 migrations were not rewritten.

### Latest acceptance and raw results

| Execution | Actual evidence |
| --- | --- |
| Maintained backend runner with readiness/claim/fencing/rollback/recovery | 51 passed, 105.98s (`tmp/c132-hosted-backend-ready.log`); earlier same suite 51 passed, 107.32s retained |
| All canonical local native integrations, including actual JWT browser/Electron | 48 passed, 126.93s (`tmp/c132-hosted-local-regressions.log`) |
| New actual packaged desktop hosted path | Wrapper 1 passed / 47 deselected, 55.51s; embedded Playwright 2 passed, 35.5s (`tmp/c132-hosted-release-native.log`) |
| Earlier complete hosted packaged run | Wrapper 1 passed / 47 deselected, 52.83s; embedded 2 passed; retained raw `tmp/c132-hosted-packaged-verified.log` |
| Node capture/transport/account/catalog/recovery | 189 passed (`tmp/c132-hosted-all-node.log`) |
| Existing workspace/lifecycle/presentation/pricing/resume chooser fixtures | 58 passed, 55.0s (`tmp/c132-hosted-browser-regressions.log`) |
| Build | Unsigned package/compiled renderer exit 0 (`tmp/c132-hosted-release-build.log`); subsequent normal production web build exit 0 (`tmp/c132-hosted-web-final-build.log`) |
| Source checks | Eight scoped Python files Black clean; scoped Ruff clean; mypy two relay source modules clean; changed JS ESLint clean; existing full lint 60 errors / 29 warnings, zero new attributed pairs |

Counts overlap and must not be summed. Packaged tests use actual main/preload/
compiled renderer, real WS/HTTP/native PostgreSQL and two subprocess workers, with
Chrome fake microphone/synthetic loopback and deterministic providers. They prove
mic/system/Both PCM dispatch -> durable saved answer -> settlement, competing second
packaged client on worker two denied, worker one termination stops renderer capture,
native lease expiry clears reservation, deliberate restart on worker two, five distinct
saved answers and final logout denial. The native fixture verifies exact persisted
answer count and zero remaining reservation. Media substitutes are NOT physical OS
permission/loopback acceptance or deployed HTTPS/TLS evidence.

Early integrated attempts are preserved, not relabeled: capability GET was initially
blocked by the account allowlist; after exact-path correction the focused native
case passed. Next, system PCM was blocked by a local-only main guard; it was narrowed
to local transport only. Native logs `c132-desktop-hosted-native*.log` retain those
failed assertions; final runs above pass without weakening them. Node safe-status
allowlist was extended by exactly the non-sensitive clientAudioRelay boolean.

The currently prepared physical hosted package precedes a final error-wording-only
renderer refinement; capture/authorization behavior is identical. That copy refinement
has Node and production web-build evidence; rebuild the unsigned package after the
live manual session closes rather than overwriting its in-use app.asar.

### Graphify before / after and query

Before-change graph retained at `tmp/c132-hosted-before/graphify-out` (92 files,
1629 nodes/5038 edges). Before query: `tmp/c132-desktop-before-query.log`.
After source extraction: `tmp/c132-desktop-after-graphify.log`; after query:
`tmp/c132-desktop-after-query.log`. Both queries traverse the existing Auto lease,
subscription authority, main client and new capture/relay/claim nodes. A final graph
refresh follows remaining copy/fixture changes. SQL extraction remains incomplete
(tree_sitter_sql absent); dangling/collapsed edges and tool/skill version warning
are retained, not a clean graph-health claim. Native tests supply SQL correctness.

### Outstanding human / external evidence

The new isolated hosted physical window is ready (11:32:13 IST, 25 October 2026,
58-minute lifetime, real device APIs/no live provider, disposable database). The operator supplied the baseline: Free v1, zero used, zero reserved, 600 seconds allowance and checkout disabled.
Hosted microphone capture is the next pending physical check; no capture is inferred. The existing synchronized timing
and controlled JBL trial remain passed and are not repeated. Source-specific hosted
OS permission/loopback/Stop checks will be guided one action at a time.

A concrete deletion decision proposal now exists at
[SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md](SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md):
24-hour primary personal purge/no post-confirmation undo; minimized usage retention
90 days/security audit 180 days with explicit pseudonymous UUID linkage; inaccessible
backup expiry maximum 30 days subject to verified environment capability. These are
UNAPPROVED proposals, not implemented policy. The tested preparation barrier remains
unchanged; no irreversible purge/Auth unlink/ledger rewrite is enabled.

No isolated staging target is designated. Await its new reference ID/disposable
confirmation before read-only history/object preflight; then approve the exact diff.
The 50-candidate packet specifies roles/configuration/rollback. Signed/installed
Windows still requires an approved signed artifact/signing material and isolated
installation environment; the tested artifact is explicitly NotSigned. Overall
C11/C13 and C13.2 release acceptance remain OPEN; no shared migration, real assignment/
deletion, production activation, real payment/provider call, .env edit, commit, push
or deployment occurred.


Hosted physical launcher follow-up (25 October 2026, 11:48:53 IST): replacement packaged window reached readiness only after assertions of `clientAudioRelay=true`, healthy capabilities and Auto availability passed. The prior unconditional missing local-port override is repaired in `frontend/tests/catalog/subscription-electron.integration.spec.js`; scoped ESLint passes. Actual microphone capture remains pending operator response. The failed startup and cleanup are preserved in the physical results, not counted as capture acceptance. Graphify source refresh and before/after queries were run; final query exited zero, with existing missing SQL parser/version and graph-integrity limitations retained. Logs: `tmp/c132-hosted-physical-port-fixed.log`, `tmp/c132-hosted-port-after-graph.log`, `tmp/c132-hosted-port-after-query.log`.


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

Target preflight verification: canonical backend native suite **51 passed / 191.97s** (`tmp/c132-target-preflight-native.log`), followed by final single-JSON SQL focused native regression **1 passed / 50 deselected / 12.67s** (`tmp/c132-target-json-preflight-native.log`). Tests execute target preflight before migration history exists and with empty history plus installed objects, preserve usage counts and create no history relation during inspection. These local suites overlap. No target schema result is inferred. Graphify before/after query and source refresh completed; existing SQL-parser/version/graph-integrity limitations remain. Signature check still reports NotSigned.


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

Final staging packet static checks: all 50 original migration hashes unchanged;
final batch hash matches both packet documents; packet links resolve. Graphify
before/after queries and refreshed source graph exited zero (`tmp/c132-migration-packet-*`).
Known missing SQL parser, skill/package version warning and dangling/collapsed-edge
limitations remain; no claim of SQL graph completeness or clean graph health.
Native exact-batch execution provides SQL evidence. No remote changes occurred.


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

Graphify before/after queries and source refresh completed for pre-COMMIT hardening; final query exit zero. Known missing SQL parser/version/graph integrity warnings retained. SQL correctness comes from actual native batch tests, not graph extraction. Final packet/source-hash/link checks pass.


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

Storage-policy final local verification: `tmp/c132-storage-policy-final-native.log`
passes full exact-batch/late-failure/postflight/replay under both existing owner
fixtures, 16 pre-COMMIT mutations, owner/hook negative path and deficient BYPASSRLS.
New metadata probe tested read-only; rollback DDL trial leaves Storage owner/RLS,
policies and memberships exactly unchanged. Fake unregistered hook GUCs cannot
pass. The actual Supautils library is absent locally; no positive managed-hook
execution claimed. Black/Ruff passed. Final batch SHA256
`f4fc28bc04f69b7dc72b2829ca644cfcbe452a99f9e380ff87f0bf0edb05818f`;
all original source hashes and packet links verified. No remote writes.

Storage-policy Graphify before/after queries and source refresh completed, final query exit zero. SQL-parser/version/integrity limitations remain; native SQL tests, not graph extraction, provide correctness evidence.


### Managed Storage policy-grant preflight returned - 25 October 2026

Owner returned read-only target metadata for cfmvqbjmnwklxqlpelxe: effective/session
postgres; Storage RLS enabled; owner supabase_storage_admin; inherited ownership
false. Registered supautils.policy_grants exists with context sighup, source
configuration file, no pending restart, and explicitly includes postgres on
storage.objects. **Existing policy-grant configuration is now confirmed.**

No supautils.version row was returned. The probe's comment_version_supported=false
is therefore *unknown/not established*, not proof that COMMENT is unsupported.
policy_ddl_route=UNVERIFIED_STOP_NO_WRITES and behavior_verified=false remain accurate.
Do not infer a minimum version from current upstream configuration or from the
policy_grants row. No actual CREATE/DROP/COMMENT behavior has been tested remotely.

Next behavioral check is the already-prepared restrictive rollback-only policy
probe, requiring separate explicit remote DDL authorization even though it rolls
back. It exercises the exact required CREATE/COMMENT/DROP operations and verifies
cleanup without adding memberships, changing ownership or weakening RLS. Do not
execute the full batch or modify configuration to fabricate a version. A successful
probe would justify preparing a narrowly reviewed alternative to the current
version-based guard; it does not automatically authorize or make the present guard
pass. On failure, ROLLBACK, retain error/metadata and prepare the smallest supported
amendment (such as separately reviewed optional-comment omission if specifically
that operation is denied), never omit security policies. Current batch hash and
approval remain unchanged and execution remains stopped. No remote writes occurred
by the agent; accepted local/hosted capture evidence remains preserved.


### Narrow rollback-probe authorization - 25 October 2026

Owner explicitly authorizes manually running ONLY the prepared rollback-only
Storage policy probe in cfmvqbjmnwklxqlpelxe. Approved immutable probe SHA256:
`8101d7a1c5be3a89fb7b1242560d87ab6ba6bc7a5e0be70bc5a2fcf527c1cdf6`.
Its preparatory header predates this narrow approval; original file bytes retained.
The probe has lock timeout 5s, statement timeout 15s, idle-in-transaction timeout
20s; no COMMIT. Agent has not executed it. Operator execution/result is PENDING.
A separate read-only verification file is prepared to confirm probe absence,
Storage owner unchanged and RLS enabled after rollback. Any open/aborted
transaction requires explicit ROLLBACK before further work. On failure return
exact redacted error; do not retry, COMMIT, drop an existing policy or run repairs.
If the probe policy remains visible, stop for investigation without deleting it.
Do not report successful behavior/rollback until actual returned evidence.
No authorization for full migration, privilege/membership/owner changes,
activation or Saiia-dev is inferred.


### Operator rollback-policy probe result received - 25 October 2026

Returned row: effective_user=postgres, session_user=postgres,
storage_owner=supabase_storage_admin, rls_enabled=true, probe_absent=true.
This matches the approved probe's final SELECT (which includes session_user),
not the separate verification SELECT. It supports that policy CREATE/COMMENT/DROP
reached the final SELECT if the approved script ran in full; no error was supplied.
Owner/RLS are unchanged and the probe is absent at that point. The SELECT occurs
before the script's final ROLLBACK, so this row alone does not establish completion
of that ROLLBACK or a fresh post-rollback observation. Separate read-only cleanup
result and any SQL Editor error/rollback status remain pending. Do not yet clear
the full-batch authority guard or infer migration/activation approval. No remote
SQL was executed by the agent.


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

Final guard Graphify before/after queries and source refresh completed (exit zero). Existing SQL-parser/version/graph-integrity warnings remain; native SQL/decision tests supply correctness, not SQL graph extraction. No remote execution.


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

The accepted schema application and all five executor connection smoke/cleanup passes are complete; older blanket migration/connection blockers are historical. [Current application acceptance](C13_2_STAGING_APPLICATION_ACCEPTANCE.md) records 11 local two-worker application groups, injected-startup cleanup, 91 focused tests, 51 backend regressions and 15 execution regressions. Real staging application acceptance awaits its secure-input run and actual evidence. Physical passes are retained. Public HTTPS/WSS, signed installed Windows and irreversible deletion remain separate gates. C11/C13 are not complete.
