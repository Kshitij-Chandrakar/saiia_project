# C15 Stage 1: local confirmation and restriction foundation

29 October 2026, Asia/Calcutta. **Implemented and substitute-tested locally, default off. C15 remains incomplete. C15.5 implementation and Razorpay execution remain paused.** No real account/export/deletion, remote SQL/Auth configuration, provider call, email/payment, tunnel or deployment was performed. No commit, push, merge or PR mutation.

## Scope and isolation

Repository origin verified as `https://github.com/Kshitij-Chandrakar/saiia_project.git`. Isolated worktree: `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. The original dirty `dev/current-work` worktree was not switched, stashed or edited. The new branch has no implementation commits. Review branches/worktrees and existing acceptance journals/counters were not changed.

Baseline includes unmerged catalog/usage/runtime/billing dependencies. The prior audit records matching source blobs on review catalog API `99a4129`, runtime `d9789a5`, clients `fb6ac3d`, billing `8683669`; their presence here is not merged or deployed acceptance. Only the four explicitly linked C15/C15.5 audit/planning source documents are carried from the original untracked planning packet; no unrelated dirty code/roadmap/tracker additions were copied. Tracker/roadmap edits in this isolated tree are C15-only append/update entries against the committed baseline.

Read repository/ancestor instruction inventory, existing Graphify graph, C15 audit/scope/owner decisions/deletion proposal/approved subscription policies/current roadmap; traced actual Auth/probe/bootstrap, shared deletion barrier, restricted DB pool, session/generation/RLS/Storage, billing/email worker/callback and existing dashboard/test code. No applicable AGENTS.md found. Graphify query used existing graph only, not rebuild/provider extraction; its historical source positions were checked against actual code. Ponytail guided reuse of the existing barrier/transaction helper, native dialog and installed dependencies; Impeccable context/product register and existing dashboard tokens were read; Playwright used isolated synthetic fixtures, role selectors, independent parallel tests and failure traces.

## Approved policy versus implemented behavior

[C15 approved policies](C15_APPROVED_POLICIES.md) records the owner's explicit Stage 1 instruction and supersedes the earlier proposals only for approved choices. No-undo/reauth/confirmation; permanent exact-email signup suppression; 24h primary cleanup target; 90d minimized usage and 180d security clocks from accepted confirmation; minimum billing exception with Product Owner/seven-day review; session/account privacy scope; 24h-after-ready export expiry are recorded. The last two scopes/expiry are policy only in this stage, not new erase/export endpoints.

Controlled retirement of immutable records is **not approved or implemented**. Recovery-copy/provider retention and full export fields are unresolved. No-refund is reaffirmed with mandatory exceptions preserved; a canonical published sentence with those exceptions was not found at the inspected baseline, so the UI does not invent a blanket no-refund legal statement. Operational test “no refunds” boundaries are not customer refund policy. No refund/cancel operation was added.

Implemented now: confirmation request/status API, signed presence/session checks, one-time atomic acceptance/replay recovery, existing barrier activation, durable pending follow-ups, permanent versioned keyed email matching, prepared Auth hooks/commit guards, personal-write fences, no-entitlement-restore billing handling and website Settings/Danger Zone/dialog/scoped status. No unrestricted destructive purge worker; no full-session erase API; no archive builder, retirement worker or desktop wipe.

## State machine and transaction

`awaiting_confirmation` becomes `accepted_restricted` once, with revision increment and accepted timestamp. Five-minute expiry is server-clock enforced. An expired unaccepted challenge can be replaced after reauthentication. Accepted state has no undo/restore transition. Same bound request replay returns the original accepted result without repeating side effects, including after uncertain commit acknowledgement. UI uncertainty checks status rather than asserting success or generating a new operation.

Acceptance transaction serializes on the same Auth-row lock used by `subscription_deletion_prepare`; checks subject/session/reauth/policy/exact scope/text/capabilities and the verified, challenge-bound email. It inserts permanent suppression, invokes the existing barrier (stops/fences Auto, removes handoffs), records accepted request/deadlines, appends audit and creates three durable pending tasks: revoke_sessions, personal_cleanup and billing_review. No captured content in task/audit payloads. A changed email requires a new valid confirmation; key version/digest bind the suppression target without retaining a second raw email.

Status always reports `content_erased:false`, cleanup pending, session revocation pending and billing unverified. It does not call a provider or bootstrap an account. Approved category dates are stored but expiry/physical cleanup is **not implemented**. Pending session-revocation task is initiation for a later controlled executor, not proof of global Auth revocation. Frontend immediately leaves product UI, stops auto-refresh, clears attributable local state and requests local SDK logout; remote/global revocation remains pending.

## API and identity boundary

Three POST actions under `/api/privacy/deletion/{action}`: challenge, confirm and status. Backend `C15_ENABLED`, persistent `C15_RESTRICTIONS_REQUIRED` enforcement and subscription infrastructure must be enabled, and SQL `privacy_configuration.enabled` must permit the matching policy. All new flags default off. Disabling new requests does not disable status or the enforcement flag; removing subscription composition while enforcement is required fails closed instead of falling back to private legacy reads. Challenge/confirm derive subject from verified JWT, never client account IDs; extra fields are rejected. Fixed whole_account scope/policy, exact lowercase `delete`, bounded body/capabilities, no-store responses and safe opaque errors. No public email-enumeration endpoint.

Challenge/confirm require signed session_id, AMR password/TOTP timestamp within five minutes, and Auth-hook-stamped issuance method. Refresh-only, missing/stale evidence and OAuth-only login are denied. TOTP requires signed AAL2. Status uses only request ID plus a random 256-bit scoped capability in a POST body, never a URL/full product credential; stored hash expires after seven days. The same request can be recovered without login/product access. Safe receipt lives in tab sessionStorage; no password/access/refresh token is stored by privacy code. Capability renewal/recovery beyond seven days is not implemented and is an activation dependency.

Actual installed Supabase SDK exposes password login and MFA APIs, but ordinary `reauthenticate()`/OAuth round trips do not establish a generic account-deletion user-presence guarantee. Backend supports password/TOTP proof; UI currently implements password verification only. Google-only accounts need a separately completed verified MFA or provider-auth-time reauthentication path and acceptance. They cannot bypass via silent Google SSO. No new password-setting/recovery feature was invented.

The [Custom Access Token hook contract](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook) documents signed issuance/session/AMR fields and authentication_method, including token_refresh; the prepared hook preserves required claims and stamps only that server-owned issuance method. [Before User Created](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook) is the supported signup-policy integration, including OAuth signup. These capabilities were documentation-checked, not invoked against an account. Existing configured hooks must be composed/reviewed, never silently replaced.

## Suppression matching and key lifecycle

Restricted tables store key version + HMAC-SHA256 digest, not an unsalted email hash. Only minimal matching identifiers persist; confirmation requests reference the subject and key-bound email digest, not another email copy. A key must exist before challenge acceptance. No real key is seeded; tests use an explicitly synthetic disposable key. No key/digest/email/capability is logged by the new API.

Normalization is trimmed ASCII email lowercased under C collation. No Gmail dot/plus alias folding and no promise all aliases are banned. [Supabase Auth source](https://github.com/supabase/auth/blob/master/internal/models/user.go) was inspected for its email normalization boundary; actual deployed Auth version/equivalence must be confirmed before activation. International email equivalence is unresolved, so unsupported normalization fails closed instead of inventing Unicode behavior.

Key rotation keeps every historical matching key: old suppression rows reference their key version; lookup tests all retained versions. Losing or modifying an old secret loses matching capability; no irreversible key destruction is acceptable while permanent suppression depends on it. Keys require restricted encrypted recovery/backup handling and tested restore consistency with the suppression journal. Restoration before suppression existed must not reopen signup. These records are pseudonymous personal data with permanent suppression as the explicitly disclosed exception.

Prepared before-create/token hooks deny suppressed identities/new token issuance. Auth users email-change/creation commit guards serialize email matching with acceptance; identity linking and new Auth sessions are guarded; metadata/contact-change writes on a restricted Auth identity are denied. These managed-schema integrations are native-tested substitutes only; actual Supabase role/trigger compatibility and hook configuration remain a remote prerequisite. No remote Auth setting or schema was changed.

## Protected ingress and commit inventory

| Surface | Reused/new protection | Verified limit |
| --- | --- | --- |
| Website/private HTTP/bootstrap/reconnect | Existing get_current_user → HostedCoordination → subscription_access_check; suppression check extends that authority; dedicated identity-only confirmation/status path | Old signed product token denied after barrier. This is not global JWT invalidation. No competing is_admin/account-status authority. |
| Direct DB and Storage RLS | Existing restrictive subscription_deletion_barrier policies intersect ownership; future privacy tables have no user policies/table grants | Existing native barrier regressions verify direct-row/Storage denial. Migration inventory must catch future tables and configured bucket IDs. |
| Service-role writes | BEFORE INSERT/UPDATE commit fences on profile/resume/chunks/JD/settings, session/idempotency/transcript/notes/chat/saved-answer/generation/source/diagram/screen/notes-version/resume-job/active-set tables, shared Auth lock | Native multiconnection write-first versus delete-first and late notes/chat/generation tests. Owner reassignment is denied. Scope is tables actually registered by migration, not every future table. |
| File uploads/export objects | Resumes/exports Storage metadata insert/update fence and existing account barriers; no export API in this stage | A Storage service can have bytes already in flight outside a DB transaction. Actual object-service/copy/cache/signed-URL acceptance remains blocking. No “all bytes instantly revoked” claim. |
| gRPC/active streams/Auto | Existing verified cloud context, account/lease/frame authorization, stop/fence in deletion preparation; existing idle-socket authorization polling | Already in-flight provider calls/bytes cannot be recalled; no new commits/authorization after barrier. Physical/external tests not repeated. |
| Extraction/index/notes/Ask AI/saved answers/screen/answer checkpoints | Existing generation/ownership guards plus shared DB commit fences | Preflight alone is insufficient; late persistence is rejected. Existing Clear Transcript semantics/RPC were not changed. |
| Auth signup/Google/linking/email changes | Prepared supported hooks, Auth commit guards, exact-email HMAC and shared email lock; profile/bootstrap also protected | Real hooks/managed schema/normalization acceptance not configured. No claim frontend-only checks solve direct Supabase signup. |
| Handoffs/queued private jobs | Existing preparation removes handoffs, stops/fences work; commits hit account guard; durable privacy follow-ups stay pending | No destructive/revocation executor here. Device-local queues and full Electron cleanup remain later work. |
| Payment callbacks/reconciliation | Existing signatures/dedup/evidence path preserved; restricted payment apply records no entitlement grant; new notification enqueue suppressed | Fake late signed event/replay retains one evidence record per event and unchanged plan binding. Follow-up also verifies normal pre-deletion paid activation and blocks a previously queued email after deletion. No cancellation/refund called. Necessary financial reconciliation remains distinct from product access. |
| Email callbacks/sends | Existing verified delivery receipt path unchanged; restricted account blocks new outbound event/send claims; new billing notifications suppressed | An already-dispatched external message cannot be recalled. Existing in-flight cases need disclosed reconciliation, not blind resend. No email sent here. |
| Local browser stale responses | Account-generation fence, unmount/navigation before logout, double-submit ref, SDK signout, attributable auth/billing/profile/remembered-email clearing | Untagged legacy profile/local files and offline devices are not guessed/wiped. SDK signout broadcasts to other tabs; configured runtime acceptance remains necessary. |

## Prepared migration, activation and rollback

`supabase/migrations/20261029010000_privacy_confirmation_foundation.sql`, additive, no key/LOGIN/runtime enablement or destructive purge. It adds privacy config/keys/suppression/requests/tasks/audit, append-only audit guards, commit fences and hook functions; reuses `subscription_deletion_jobs` as product access authority. Only disposable native PostgreSQL was used. C10/C12/catalog/usage and current cloud migrations are dependencies; apply in reviewed order. No general staff memberships/invites/permissions/admin console introduced.

Activation remains blocked on: complete controlled personal cleanup and actual revocation execution; production Auth hook/managed-schema enforcement and verified normalization; Google-only reauth UX/acceptance; configured Storage bytes/URL/caches and all private boundaries; key lifecycle and independently recoverable deletion/suppression journal; safe status-capability renewal; reviewed minimal billing/contact treatment and canonical refund wording; operational capacity for approved target; actual retention/restore/processor facts. UI `VITE_C15_ENABLED` and backend `C15_ENABLED` stay false/unset, SQL enabled=false, with no real key. Native fixtures alone set synthetic switches and keys.

Disable new feature entry/confirmations on rollback; preserve accepted requests, restrictions, suppression, tasks and audits. Do not drop tables/triggers or restore an old snapshot that reenables suppressed subjects. Requests already accepted have no undo, even if UI is rolled back. A schema mismatch/failure is unavailable, never successful deletion. This stage has no Auth/file purge to reverse. Later irreversible cleanup has no data-restoring rollback.

## Verification and previews

| Check | Exact local result |
| --- | --- |
| New actual JWT/ASGI + disposable native PostgreSQL suite | **20 passed**. Confirmation/concurrency/lost-commit, stale/refresh/OAuth proof, exact email/signup/linking and signup-hook/acceptance race, changed email after challenge, Auth metadata/session denial, private write race and late notes/chat/generation, old product token/status-only recovery and fail-closed rollback, late signed billing event dedup/no binding restore/no notification. Strengthened billing case separately rerun afterward: **1 passed, 19 deselected**, proving ordinary pre-deletion paid activation, late renewal evidence without access restoration, and no dispatch of a queued pre-deletion email. |
| Focused existing auth/routes/resume/transcript/migration regressions | **99 passed**. No external acceptance repeated. |
| Existing native hosted deletion/handoff regressions | **6 passed, 19 deselected**. Existing barrier rollback, RLS/Storage, handoff and uncertain/concurrent recovery preserved. |
| Playwright Chromium isolated synthetic fixture | **8 passed**, two parallel workers. Profile menu/settings, default-off, exact text/reauth, expiry, focus trapping/restoration, duplicate submit, unknown status recovery, account switching, desktop/mobile overflow/previews. |
| Scoped ESLint, new UI/API/tests plus DashboardLayout | **0 errors, 0 warnings**. Touched existing App/AuthScreens/authApi: **0 errors**, one existing App hook dependency warning. |
| Ruff 0.17.3, explicit Python 3.10 target, new backend/test | Check passed; format check passed. Compileall passed. |
| Scoped mypy | **Success, no issues in one source file**, pure-Python mypy 1.18.2, follow-imports=silent/ignore-missing-imports. Latest tool's native parser was blocked by Windows Application Control; used normal pure-Python distribution, no control/security setting changed. This is not whole-repository typing. |
| Vite production build | Passed; existing large-chunk warning remains. No asset generation/illustration. |
| Diff/scope | **41 changed files**, including carried-forward planning sources, nine verification artifacts and four screenshots; git diff --check passed. Original dirty tracked diff preserved. No application tests/providers against real data. Evidence logs below include benign SWIG/Pytest/Node warning output, not failed assertions. |

Runner: `python backend/tests/test_privacy_native.py --pg-bin <existing-disposable-PostgreSQL-bin>`. Other tests: `python -m pytest backend/tests/test_supabase_auth.py backend/tests/test_auth_routes.py backend/tests/test_cloud_resume_routes.py backend/tests/test_interview_session_transcript_routes.py backend/tests/test_supabase_migrations.py -q`; existing native tests run with the same explicit local-bin pytest option and `-k 'deletion or shared_handoff'`. Browser: from frontend, `node node_modules/@playwright/test/cli.js test --config tests/c15/playwright.config.js`. The fixture loads no .env and routes external network away; no synthetic auth token is accepted by a real service.

Desktop/mobile images are real browser captures of synthetic UI/API state, not production erasure acceptance:

| Desktop | Mobile |
| --- | --- |
| ![Desktop settings](assets/c15-stage1/desktop-settings.png) | ![Mobile settings](assets/c15-stage1/mobile-settings.png) |
| ![Desktop confirmation](assets/c15-stage1/desktop-dialog.png) | ![Mobile confirmation](assets/c15-stage1/mobile-dialog.png) |

Exact logs: [native suite](evidence/c15-stage1/c15-native-results.txt), [strengthened billing follow-up](evidence/c15-stage1/c15-billing-followup-results.txt), [regressions](evidence/c15-stage1/c15-regression-results.txt), [barrier regressions](evidence/c15-stage1/c15-barrier-regression-results.txt), [browser](evidence/c15-stage1/c15-browser-results.txt), [typing](evidence/c15-stage1/c15-typing-results.txt), [build](evidence/c15-stage1/c15-build-results.txt), [ESLint](evidence/c15-stage1/c15-js-checks.txt), [existing-file lint](evidence/c15-stage1/c15-existing-eslint.json). Intermediate failing runs were corrected; these links contain final results.

## Changed-file manifest

- Backend existing: `app/auth/supabase_auth.py`, `app/commercial/boundary.py`, `app/config.py`, `app/main.py`.
- Backend new: `app/privacy.py`, `tests/test_privacy_native.py`.
- One migration: `20261029010000_privacy_confirmation_foundation.sql`.
- Frontend existing: `src/App.jsx`, `src/auth/AuthScreens.jsx`, `DashboardLayout.jsx`, `authApi.js`, `dashboard.css`.
- Frontend new: `src/auth/WebsiteSettings.jsx`, `privacyApi.js`, `privacy.css`; `tests/c15/fixture.html`, `fixture.jsx`, `vite.config.js`, `playwright.config.js`, `privacy.spec.js`.
- Documentation: this report, canonical C15 policy, carried-forward planning/audit documents and their scoped disposition updates, C15 tracker/roadmap entries; four screenshots and nine final verification artifacts. No package/lockfile/runtime dependency change. Temporary dev tools and shared installed node_modules junction are local verification infrastructure, not deliverable code or a repository dependency change.

## Remaining C15 work

Inventory-driven physical cleanup/outbox executor and safe retries for every personal derivative; remote session revocation; own-account archive/expiry implementation and unresolved export fields; approved controlled-retirement design; verified financial/legal retention; backup/log/processor copy inventory and restore rehearsal; full-session/individual notes/chat/settings privacy operations; complete browser/Electron/offline attribution and cleanup; production Auth/Storage/MFA/key/status recovery acceptance; center details and sensitive logging closure. Preserve all accepted payment/email/admin evidence and Razorpay pause. C15 is **not complete or ready to activate**.
