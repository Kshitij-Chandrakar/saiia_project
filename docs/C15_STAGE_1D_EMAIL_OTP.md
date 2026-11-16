# C15 Stage 1D: Google-only mailbox confirmation

30 October 2026, Asia/Calcutta. **Implemented locally and synthetically rehearsed; activation remains disabled and C15 incomplete.** Owner explicitly approved fresh email OTP as a Google-only deletion-confirmation fallback. This proves mailbox control, not Google reauthentication or MFA. No real email, remote configuration/migration, provider action, export/personal purge, production activation, commit or push. C15.5 and Razorpay remain paused.

## Scope and isolation

Continued in `E:/saiia_project/c15-stage1`, `work/c15-stage1`, origin `Kshitij-Chandrakar/saiia_project`, unchanged HEAD `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Entry: 78 uncommitted files. Cumulative: **87 files**, below the 100-file review limit. The next review slice is approximately **20 paths** (OTP API/SQL/UI, package builder/artifact, policy/tracker/report and five evidence files); earlier Stage 1–1C remain dependencies, not new unrelated changes. Prefer reviewing the existing foundation and this dependent slice separately when later authorized; no commits were made to manufacture a split.

Ponytail guided reuse of the existing intent, confirmation, account lock, key ring, private RPCs and recovery loop. No new dependency or competing account lifecycle. No applicable AGENTS.md found in the repository/ancestors. Original worktrees/PR branches and historical evidence were not edited by this stage; screenshots are opt-in and none were captured. The prior Stage 1C preview exception remains recorded there.

## Contract

- Caller is a verified authenticated subject. Backend reads Auth-signed `app_metadata.providers`, not client flags: only Google without an email/password provider qualifies. Actual provider metadata behavior remains a configured-Auth acceptance item.
- The existing five-minute `begin` intent binds subject, original session, request UUID, whole-account scope, policy version and confirmation/status capability hashes. OTP APIs cannot accept an arbitrary target account/email. SQL requires confirmed Auth email matching the verified identity; an address change invalidates proof.
- `otp_start` reserves a cryptographically random **eight-digit code**, stores only a keyed digest and keyed address fingerprint, then calls a trusted injected delivery function. There is **no real delivery adapter wired**. Missing delivery/key configuration fails closed. Production feature gates remain off.
- Code/address HMAC keys are derived with a dedicated domain from the existing versioned server key ring, separate in purpose from its AES encryption. MAC input binds subject, request and original session. Keys/hashes/codes are never returned by the public API, put in URLs, or persisted by the browser. The code exists only in server/delivery memory; tests use a private synthetic mailbox.
- Expiry is the earlier of five minutes from reservation and original intent expiry. At most **five guesses per code**, **one send per 60 seconds**, **three sends per rolling hour window**, and **ten sends per rolling 24-hour window**, per verified account. Limits are database-authoritative and serialize under the account lock. Windows are measured from their stored start, not calendar boundaries. Resend replaces the prior digest. Failed guesses return a safe rejected state so attempt increments commit rather than roll back. Limits also count uncertain/failed delivery reservations.
- Successful `otp_verify` consumes the code once, clears its digest and records server verification time plus a content-free audit event. Concurrent verifications produce only one success. It creates the existing confirmation challenge, **not an Auth session, JWT, MFA upgrade, deletion request acceptance or product restriction**.
- `otp_ready` recovers a committed verification after an uncertain response using the original subject/session/request capabilities. It cannot create proof. Refresh alone cannot satisfy this check.
- Final typed `delete` remains a separate POST. The UI clears text entered before mailbox verification, so it must be entered afterward. Confirmation derives proof from the private receipt, consumes it atomically with existing acceptance/barrier/suppression/audit/follow-up/credential capture, and preserves idempotent accepted replay. No OAuth callback or OTP response auto-deletes.
- Expired OTP rows are removed by existing recovery; obsolete rate rows are removed only after both their day/hour windows have ended. Key outage never permits verification. Accepted replay can recover through the existing accepted request even after the transient OTP receipt expires; status receipt scope/expiry remains unchanged. No policy-wide retention retirement was added.

The proof remains AAL1 mailbox control unless independently authenticated at a stronger level. Ordinary password/TOTP paths and transcript-only deletion remain unchanged. Saved-answer/session/account policy, billing exception, permanent suppression and approved 24h/90d/180d/export clocks are unchanged.

## Delivery and recovery limits

Reservation and delivery are separate boundaries. A crash/timeout can mean no delivery or delivery without acknowledgment. There is no automatic email retry and no false sent/deleted result. The UI allows entering a code that may have arrived after an uncertain send, checking an uncertain verification, or explicitly requesting another code subject to limits. Codes never confer product login or deletion-status access on their own.

`app.state.privacy_otp_sender` is trusted infrastructure injection used only by synthetic tests here. It is not a request field or public configuration API. A future production integration needs an approved, purpose-specific sender, safe logging/template/abuse controls and separately authorized delivery acceptance. Generic Supabase [signInWithOtp](https://supabase.com/docs/reference/javascript/auth-signinwithotp) / [verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp) are authentication flows; this implementation deliberately does not grant an application OTP AMR claim or invoke account creation/login to obtain deletion proof. The mailbox challenge is separately bound to the current deletion request.

## Changed paths

New: `backend/app/privacy_otp.py`, `backend/tests/test_privacy_email_otp.py`, `supabase/migrations/20261030020000_privacy_email_otp.sql`, this report and `docs/evidence/c15-stage1d/*`.

Updated: `backend/app/privacy.py`, `backend/app/auth/supabase_auth.py` (retain signed provider metadata), `backend/app/commercial/boundary.py` (three exact OTP POST ingresses), `frontend/src/auth/WebsiteSettings.jsx`, `frontend/src/auth/privacyApi.js`, `frontend/tests/c15/privacy.spec.js`, `scripts/c15_auth_package.py`, its pending SQL package, approved policies, decision package and tracker. Historical migration inputs/reports/journals remain unchanged. No managed Auth-table DDL was introduced.

## Validation and the Auth-engine boundary

The isolated rehearsal uses **a separate synthetic Auth issuer application**, the real backend JWT verifier/deletion ASGI routes, disposable native PostgreSQL, real HMAC/proof handling and an injected synthetic mailbox. No external Auth, SMTP, Google or email recipient is contacted. It verifies the integration protocol, **not the Supabase Auth engine**.

Docker, Supabase CLI and Go were absent from command inventory and standard installation locations. **A real isolated Supabase/Auth-engine rehearsal was not performed.** This part of the requested acceptance remains blocked on an available compatible local runtime; mocks are not substituted as evidence that configured hooks/provider behavior work. Hosted Auth acceptance also remains unperformed.

| Verification | Result |
| --- | --- |
| New native OTP/isolated synthetic issuer rehearsal | **6 passed**, 22.24s: owner/intent/session binding, separate final typed confirmation, replay/status recovery, committed guess limits, hourly/daily sends, resend invalidation, concurrent single use, expiry, unavailable delivery and cross-account denial. [native.txt](evidence/c15-stage1d/native.txt) |
| Supported-package/credential native regression | **16 passed**; [regression-native.txt](evidence/c15-stage1d/regression-native.txt). |
| Existing Auth/resume/transcript/migration regression | **99 passed**; [regression.txt](evidence/c15-stage1d/regression.txt). |
| Browser regression and Google-only fallback | **16 passed**; [browser.txt](evidence/c15-stage1d/browser.txt). Includes code followed by newly typed confirmation, no password/MFA requirement, keyboard/mobile checks and existing uncertain/stale-account behavior. |
| Scoped checks | Ruff lint/format and Mypy for the changed OTP implementation pass; Mypy uses the previous silent-import/missing-stub scope. ESLint for the changed UI/API/test files passes. |
| Frontend production build | **Passed**, Vite 7.0.6, 2,182 modules; [build.txt](evidence/c15-stage1d/build.txt). Existing >500kB bundle warning remains. |

Run the native rehearsal using `E:/deepfake_envs/SaIIA/python.exe backend/tests/test_privacy_native.py --pg-bin <existing-local-pg-bin> --suite backend/tests/test_privacy_email_otp.py`. Browser command remains `node node_modules/@playwright/test/cli.js test --config tests/c15/playwright.config.js` from frontend, with external requests intercepted and screenshot output disabled unless explicitly requested.

## Remaining activation gates and exact next action

The fallback choice is settled; no further policy approval is needed for this local implementation. Next: provide an isolated Supabase/Auth runtime pinned to the target version, apply the supported package only in a disposable pre-C15 environment, configure synthetic hooks/accounts and a local mail sink, then test real provider metadata, stale tokens, address changes, hook permissions/outages and the full OTP/confirmation/revocation sequence. Do not use the hosted project or real recipients as a substitute.

Keep UI/backend/SQL activation off until that rehearsal and separately authorized configured acceptance pass, the real purpose-specific sender is reviewed, and the still-open Auth creation/link/email commit guarantees are resolved. Full cleanup, Storage, retention/restore, backup/processors and status recovery gates from Stage 1C remain. No real account should accept deletion while these dependencies are incomplete.
