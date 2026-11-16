# C15 Stage 1B: local authentication and enforcement

29 October 2026, Asia/Calcutta. **Local implementation and synthetic verification only. Activation remains disabled; C15 is incomplete.** C15.5 and Razorpay execution remain paused. No real Auth/Storage/provider call, account deletion/export, email, refund, payment, remote migration/configuration, tunnel or deployment. No commit, push, merge or PR mutation.

The local recovery mechanisms are implemented. **Complete prevention of managed Auth identity creation/linking/email mutation is not established.** Supported hook checks and product denial are distinct from the Auth identity transaction. The real revocation adapter remains unwired because durable logout credentials have not been established. These are release blockers, not completed acceptance.

## Isolation and sources

Continued in `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`; origin `https://github.com/Kshitij-Chandrakar/saiia_project.git`. Verified the 41-file uncommitted Stage 1 entry state. Combined Stage 1/1B scope is **60 changed/untracked files**, including evidence and source planning documents, below the preferred 80-file limit. Existing unmerged runtime/billing dependencies remain as recorded in [Stage 1](C15_STAGE_1_LOCAL_IMPLEMENTATION.md); no review branch was changed.

No applicable AGENTS.md found in the repository or ancestors. Read Stage 1, audit, decision package, approved policies, deletion proposal, current roadmap and actual Auth/bootstrap/barrier/task code. Graphify queried the existing original-worktree graph (`auth privacy deletion session storage`, BFS, 63 nodes); graph positions are historical navigation, checked against source. No graph refresh, installation or extraction/provider activity. Ponytail guided reuse of the existing transaction helper, deletion barrier and installed Auth MFA API.

Original-worktree tracked/index binary diffs match the entry snapshot exactly. Stage 1 migration, report and evidence remain historical and unchanged. Stage 1B evidence is separate. Approved policies in [C15_APPROVED_POLICIES.md](C15_APPROVED_POLICIES.md) are unchanged; no policy is reopened or inferred. Exact canonical refund wording remains an identified publishing prerequisite from Stage 1, not a new decision about the approved no-refund policy or mandatory exceptions.

## Changed files and mechanisms

| File/group | Stage 1B change |
| --- | --- |
| `supabase/migrations/20261029020000_privacy_auth_recovery.sql` | Additive local migration: operation intent, wrapper around existing acceptance, key-outage denial, supported hooks, public-owned commit/RLS functions, revocation leases/retries/status. No DDL targeting managed Auth tables. |
| `backend/app/privacy.py` | Identity-derived `begin` action and signed password/TOTP method passed to SQL; existing confirmation/status boundary retained. |
| `backend/app/commercial/boundary.py` | Allow only the new exact POST begin ingress alongside existing privacy actions. |
| `backend/app/privacy_revocation.py` | Explicitly constructed one-task runner with injected fake Auth; no scheduler, provider client, credentials or activation wiring. |
| `frontend/src/auth/WebsiteSettings.jsx` | Begin before presence; Google-only verified-TOTP path and blocked no-factor path; same-proof uncertain-challenge recovery; truthful revocation status; initial heading focus for long mobile dialog. |
| `backend/tests/test_privacy_native.py` | Apply additive migration in disposable cluster; prepare intents; exercise begin through ASGI; runner accepts another suite. Historical evidence untouched. |
| `backend/tests/test_privacy_auth_recovery.py` | Ten native tests, including independent connections, fake Auth recovery, hooks/key ring and operation binding. |
| `frontend/tests/c15/{fixture.jsx,privacy.spec.js}` | Synthetic Google factors, wrong credentials/account, uncertain challenge, navigation and separate Stage 1B captures. No new dependency. |
| Decision package, production tracker, this report | Current status, exact limitations and next bounded stage. |
| `docs/assets/c15-stage1b/` and `docs/evidence/c15-stage1b/` | Six screenshots and nine check logs/results; no credentials or real customer data. |

## Reauthentication contract and assurance

1. POST `begin` derives the account and original session from a verified signed JWT. It stores request UUID, policy/scope, original session, confirmation/status capability hashes and server time under the existing account lock. Matching replay recovers the same intent; another operation/session conflicts until expiry. Five-minute intent validity.
2. Password reauthentication uses existing `signInWithPassword`. Google-only users can verify an **already enrolled, verified TOTP factor** with installed `auth.mfa.challengeAndVerify`; they are not asked to set a password. The SDK's factor listing uses authenticated `getUser`. No MFA enrollment or account-recovery feature was added.
3. Backend requires Auth-signed AMR timestamp, `session_id` and hook-stamped issuance method `password` or `totp`; TOTP also requires AAL2. Proof must be within five minutes and strictly after the operation's starting second. `begin` returns the next whole-second `not_before`; UI waits for it before prompting Auth. Client time is only scheduling, never authority. Refresh, iat, OAuth SSO, account chooser and user metadata cannot substitute for presence.
4. TOTP upgrades the original session. Password may return a new session, but the same verified subject and operation capability are required. SQL binds the first proof session/time to that intent; changed proof, another request/subject/session or expired intent is rejected. The old Stage 1 SQL entry point is private and loses executor access; the wrapper is authoritative.
5. Explicit challenge retry after an uncertain response retains the same request/proof in memory and performs **no automatic final confirmation**. Accepted confirmation still requires exact `delete`, bound session/policy/scope and atomic Stage 1 consumption. Uncertain acceptance uses the separate scoped status receipt. Account switch/unmount discards stale responses; credentials and TOTP codes are cleared after attempts. No deletion credential/confirmation is added to URLs or persistent browser storage. The ordinary existing Supabase SDK session persistence is unchanged.

Installed `@supabase/auth-js` is **2.111.0**. Its `GoTrueClient._challengeAndVerify` calls challenge then verify; `listFactors` uses `getUser`; `GoTrueAdminApi.signOut` requires a JWT and sends POST logout with scope. Reviewed current primary [MFA reference](https://supabase.com/docs/reference/javascript/auth-mfa-challengeandverify) and [token-hook contract](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook), which describes signed issuance methods and required claims. This is installed-source/documentation verification, not configured Auth acceptance.

**Google-only without an existing verified authenticator stays unavailable.** OAuth alone cannot establish this assurance from the currently verified signals. There is no new OAuth deletion round trip, callback state or auto-delete callback; the existing ordinary Google login/callback is unchanged. OAuth cancellation/provider-auth-time behavior is therefore not claimed tested for deletion. A future supported fresh-presence method and configured synthetic acceptance are needed for those accounts. The UI explicitly explains the block without requiring a password.

## Auth entry-point coverage

| Entry point/source | Local control/evidence | Remote/unknown boundary |
| --- | --- | --- |
| Password signup, `AuthScreens.jsx` → direct `auth.signUp` | `privacy_before_user_created` accepts unaffected email, denies suppressed normalized email. No application wrapper is treated as authoritative. | Must configure and compose supported Before User Created hook; actual configured signup transaction not tested. |
| First Google identity/signup, `startGoogleLogin` → Auth | Same supported before-create hook; token hook denies suppressed email. | Identity creation after a hook check can race if the managed Auth insert commits later. No supported end-to-end commit guarantee established. |
| Existing password/Google login | Token hook denies restricted UUID or suppressed email independently of signup; public product authority rejects old tokens. | Hook must run for actual password/OAuth issuance and error correctly. Provider SSO remains insufficient deletion reauth. |
| Session refresh | Hook denies restriction/suppression; `token_refresh` cannot provide fresh presence. | Existing JWT remains independently valid cryptographically; product checks remain required. |
| Linking/unlinking and email changes | Website has no general link/email-change UI found; installed SDK/direct Auth exposes these capabilities. Token hook rejects suppressed resulting email; public content/RLS checks use current Auth email. | No documented before-link/before-email-mutation hook verified. Token denial does not establish that the identity/email mutation itself was prevented. Keep activation blocked. |
| Profile/settings bootstrap, `api/auth.py`, `cloud/profile_bootstrap.py` | Existing verified-user access check plus public-owned commit fence; stale restored UUID with suppressed email is denied by public authority/RLS/write checks. | Actual managed Auth creation trigger ordering must be tested; do not assume API preflight alone is enough. |
| Desktop handoff/exchange/reconnect | Existing shared handoffs and subscription barrier remain authoritative; accepted deletion invalidates handoffs; old JWT denied. | Packaged/offline device acceptance and local owned-data cleanup remain later work. |
| Direct DB/Storage | Existing restrictive policy calls strengthened `subscription_account_accessible`; public content and private-Storage metadata fence functions additionally check suppression. Service writes cannot bypass content triggers. | Real Storage byte writes, in-flight bytes, signed capability expiry/cache and managed-schema permissions not accepted remotely. |
| Late workers/billing/email | Existing Stage 1 account locks/barrier prevent payload commits or paid/bootstrap restoration; minimal verified billing facts remain; ordinary notifications blocked. | No provider cancellation/refund executed. Historical accepted payment/email evidence not repeated. |
| Restored stale identity under new UUID | Token hook and public checks compare current normalized email across retained key versions, not only deleted UUID. | Missing/stale suppression journal or keys after restore cannot be recovered from an old DB snapshot alone; isolated restore replay remains required. |

The [Before User Created hook](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook) and [Custom Access Token hook](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook) are supported preparation points. **Stage 1's prepared Auth-table triggers are not accepted as supported production enforcement.** This stage neither extends nor alters those managed-table triggers. Their old native tests remain historical substitute evidence. Do not apply the Stage 1/1B migration chain to Supabase as a deployment-ready package: a reviewed supported-only deployment packaging/integration path must first resolve those old triggers, identity/link/email mutation coverage and the hook-to-insert race. No unsupported Auth internals were modified in Stage 1B.

The native hook race test proves that hook checking and suppression insertion share an email advisory lock while their transactions overlap. It explicitly does **not** prove that a later managed Auth INSERT is in that same transaction. Product denial remains closed after acceptance; prevention of every possible Auth identity row creation is unverified.

## Suppression, outage and key lifecycle

Stage 1's permanent restricted identifier remains versioned HMAC-SHA256 with server-only random keys. It is pseudonymous personal data. ASCII trim/lower only; no Gmail dot/plus folding, alias expansion or historical-address ban. Unsupported international equivalence fails closed. Actual deployed Auth email-equivalence/version still needs synthetic acceptance before claiming compatibility.

Stage 1B fixes the missing-current-key bypass: protected begin/challenge/unaccepted confirmation, hooks, product authority, public content commits and restrictive RLS fail closed. Hook dependency outage returns safe 503; suppressed identity returns generic unavailable/403. No public email lookup endpoint, raw email/digest/key logging or customer-facing identifier was added. Accepted status/replay remains recoverable while dependencies fail; restrictions are never removed.

Rotation adds a new version/current key, retains every historic key with suppression/request references, and matches across retained versions. Existing FK restrictions prevent deleting referenced keys. Native tests switch current key, preserve old suppression and verify normal unaffected matching; removing the current flag produces outage rather than allowance. Production provisioning requires protected secret access, restricted backup/restore of the key ring and suppression journal, health checks and reviewed atomic rotation. Key corruption/compromise is not detectable merely from a nonempty key table: restore/integrity controls remain required. Because only digests are retained, destroying an old key cannot preserve old exact-email matching without an approved replacement strategy. No automatic key retirement or finite suppression-evidence expiry is promised.

## Revocation lifecycle and recovery

Only existing `revoke_sessions` tasks are executable. `personal_cleanup`/`billing_review` remain pending durable work; no destructive worker exists.

`pending → running → succeeded`, or `running → pending` with retry, or `running → blocked`. Claim uses independent transaction, `FOR UPDATE SKIP LOCKED`, unique lease UUID and 30-second lease. At most five claims. Retry delays are bounded exponential (60/120/240/480 seconds after failures before exhaustion; hard cap 3600). Expired leases can be reclaimed; expired fifth lease becomes blocked. Finish must match request/current lease, running state and unexpired deadline. Stale workers cannot record completion. Persisted failure categories are only `transient`, `timeout`, `credential_unavailable` or `attempts_exhausted`; external text/credentials are never persisted. A separate audit event records each acknowledged outcome.

The injected revoker must have an actual network timeout shorter than its lease and report success only after supported **global refresh-session** revocation. Native tests use fake callbacks only. A crash after remote success can repeat global logout after lease expiry; this is retry-safe at-least-once intent, not exactly-once external execution. DB acknowledgement failure leaves the lease recoverable. Credential unavailability blocks the task for follow-up, while account restrictions and all cleanup obligations persist. Successful revocation updates safe status only; it does not erase content, delete Auth, remove billing linkage or imply cancellation.

**Real adapter blocker:** the [documented admin signOut](https://supabase.com/docs/reference/javascript/auth-admin-signout) and installed SDK require the target user's valid JWT and global scope; an account UUID alone is not that credential. This stage intentionally stores no target JWT/refresh token in durable tasks and installs no provider client/scheduler. A reviewed secure credential mechanism with expiry/recovery, or another verified supported account-wide revocation API, is needed before wiring a production worker. Do not use managed Auth table deletion as an invented revocation API. The existing browser local logout is separate and does not satisfy global revocation.

[Supabase signout documentation](https://supabase.com/docs/guides/auth/signout) describes refresh-session invalidation and independent access-JWT lifetime. Already-issued JWTs/signed Storage URLs do not become globally invalid merely because logout succeeded. Existing HTTP/gRPC/RLS/commit fences remain authoritative; signed URLs and bytes require actual Storage acceptance. No immediate global revocation claim is made.

## Verification and evidence

All data are synthetic. Tests use actual local PostgreSQL transactions/independent connections, local ASGI/JWT verification, fake Auth and intercepted browser requests; no configured Supabase/Google/provider acceptance is implied.

| Check | Exact result / evidence |
| --- | --- |
| New native auth/recovery suite | **10 passed**, 31.58s; [native-auth.txt](evidence/c15-stage1b/native-auth.txt). Operation-before-proof, proof/session replay, AAL2 TOTP, native concurrent claims, stale lease/restart/exhaustion, success-before-crash replay, timeout sanitization, unavailable credential, key outage/rotation, normal/suppressed hooks and overlapping hook/confirmation lock. |
| Stage 1 native/JWT/API/billing regression | **20 passed**, 43.18s; [native-stage1-regression.txt](evidence/c15-stage1b/native-stage1-regression.txt). Own-account denial, old-token restriction, concurrent confirms/uncertain commits, late content/billing/email, preserved scopes. Run before final added confirm key-outage check; new suite directly exercises that check. |
| Focused existing Auth/resume/transcript/migration regressions | **99 passed**, 9.52s; [regressions.txt](evidence/c15-stage1b/regressions.txt). |
| Browser | **16 passed**, 11.5s; [browser.txt](evidence/c15-stage1b/browser.txt). Password/Google factor and no-factor, wrong credentials/account, duplicate click, expiry, same-proof uncertain challenge/status, account switch, navigation, keyboard containment/restoration, desktop/mobile. No new OAuth redirect path to cancel; modal cancellation/unmount tested. |
| Ruff | Four scoped Python files pass lint and formatting; [lint](evidence/c15-stage1b/lint.txt), [format](evidence/c15-stage1b/format.txt). |
| ESLint | Three changed UI/test files, zero errors/warnings; [eslint.json](evidence/c15-stage1b/eslint.json). |
| Mypy | Two backend implementation files, no issues; [typing.txt](evidence/c15-stage1b/typing.txt). Existing silent-import/ignore-missing-import scope, not whole-repository typing. |
| Production frontend build | Vite 7.0.6, 2,182 modules, success in 4.53s; [build.txt](evidence/c15-stage1b/build.txt). Existing >500kB bundle warning remains. |

Native runners: `E:/deepfake_envs/SaIIA/python.exe backend/tests/test_privacy_native.py --pg-bin <existing-local-pg-bin>`; add `--suite backend/tests/test_privacy_auth_recovery.py` for Stage 1B. Each runner creates its own disposable cluster; no remote URL. Browser: from frontend, `node node_modules/@playwright/test/cli.js test --config tests/c15/playwright.config.js`, loopback port 5396, two workers, external requests aborted. Python SWIG deprecations/pytest rewrite warning and Node color warnings remain non-failing; PowerShell's stderr formatting appears in logs without changing successful exit results. One early new-suite failure was shared-cluster queue interference; tests now explicitly isolate earlier fake revocation tasks before each case. No production behavior was weakened to satisfy it.

Desktop/mobile synthetic previews (mobile dialog scrolls internally; initial heading/warning remains at top):

| Desktop | Mobile |
| --- | --- |
| [Settings](assets/c15-stage1b/desktop-settings.png) | [Settings](assets/c15-stage1b/mobile-settings.png) |
| [Password confirmation](assets/c15-stage1b/desktop-dialog.png) | [Password confirmation](assets/c15-stage1b/mobile-dialog.png) |
| [Google authenticator](assets/c15-stage1b/desktop-google-dialog.png) | [Google authenticator](assets/c15-stage1b/mobile-google-dialog.png) |

## Remote prerequisites and rollback limits

No following step was performed or is authorized by this report:

1. Resolve supported-only migration packaging and all Auth creation/link/email mutation races before configuring anything. Identify deployed Auth version/capabilities, existing hooks and hook transaction semantics. Compose existing claims/hooks; preserve required claims. No unsupported managed-table DDL.
2. Securely provision/version the key ring and durable suppression/restore journal before enforcement is exposed. Current-key outage deliberately denies protected operations; applying these functions without prerequisites can deny normal users. Configure supported before-create and token hooks only in a separately authorized environment, with documented private grants and safe errors.
3. Verify configured synthetic password/signup, new/existing Google identity, TOTP AMR/session claims, refreshed/old tokens, direct Auth bypass attempts, link/email mutation, normal unaffected users, case/whitespace/international rules, signup/deletion races and restored stale identities. A mocked hook response cannot close these gates.
4. Establish supported global revocation credentials/recovery and a bounded adapter; verify scope and retry semantics using separately authorized synthetic accounts. Keep worker composition off until then.
5. Complete durable primary cleanup within the approved target, Storage byte/capability acceptance, retention-controlled retirement, device cleanup, backup/processor inventory and restore suppression; preserve truthful status and billing exception. Receipt recovery beyond seven days also remains unresolved implementation work.

Backend `C15_ENABLED`, frontend `VITE_C15_ENABLED` and SQL `privacy_configuration.enabled` remain default off; no production worker is wired. `C15_RESTRICTIONS_REQUIRED` must persist for accepted requests even if the request UI is rolled back. Rollback disables new requests/UI/worker claims, never removes barriers, suppression keys/journal or accepted follow-up tasks. There is no undo or data-restoring rollback for accepted deletion. Do not revert strengthened authority functions to a missing-key bypass or restore old personal data into service.

Next bounded stage: **supported-only Auth integration packaging and revocation credential composition**, with native/fake tests first and separately authorized configured synthetic acceptance later. Full export and destructive cleanup remain unimplemented. Subsequent cleanup, retention/restore and privacy-center stages remain as sequenced in the decision package; no C15 phase completion is claimed.
