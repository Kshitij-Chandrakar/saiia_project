# Website fallback remediation: Batch 2

28 October 2026 (IST). **Local customer-website implementation and synthetic verification.** Covers F08, F09, F17 and F18 from [the original audit](WEBSITE_FLOW_AND_FALLBACK_AUDIT.md). [Batch 1](WEBSITE_FALLBACK_BATCH_1_IMPLEMENTATION.md), its preview build, screenshots and journals are preserved. No provider or installed-app acceptance was repeated.

## Implementation and local status

| Finding | Implemented behavior | Verification |
| --- | --- | --- |
| F08: callback | Removed “LOADING STATE”. Branded sign-in modal distinguishes SDK/session initialization, account verification and signup-preference persistence. At 15 seconds it says the result is unconfirmed and offers safe Back to sign in; waiting can still complete. Existing preference retry remains available only after a settled, eligible failure and reuses verified identity. | Built website: ordinary/late completion, preference failure/retry, repeated clicks, SDK token verification not replayed, account change and navigation/unmount. Native dialog Tab/Back focus and Escape exit verified. |
| F09: unsubscribe | Reuses Batch 1’s recovery layout, token ref, immediate URL scrubbing, three-attempt limit, 15-minute in-memory window and marketing/transactional distinction. Adds lightweight CSS progress, disabled Retry during submission, a 10-second slow state and an explicitly **uncertain** 15-second request-timeout state. No automatic resend. | Pending, slow, delayed success and timeout followed by manual retry; duplicate click protection and token-free URL. No success until the existing response confirms it. |
| F17: checkout | Visible **Recover existing checkout** action. Reads the existing account-scoped `billing.operation.<user-id>` identifier when present and calls GET status; otherwise calls GET current. A null result stays a no-existing-checkout state. Recovery never falls through to checkout creation. | Timeout, repeated clicks, current-operation recovery, exact saved-operation identifier, missing result, account change and old response invalidation. Every recorded billing recovery request is GET; no checkout/start/verify/cancel POST or provider script is used. |
| F18: guard | Preserves ordinary branded dashboard skeleton. At 15 seconds adds a contextual recovery panel without granting access or declaring sign-out. Manual session-check retry invalidates older attempts; supported current-user reads are aborted. Actual unauthenticated results still use the existing redirect contract. | Genuine installed-SDK session-refresh wait, delayed resolution, rejection/retry, repeated clicks, account switch, navigation, and no protected customer data before verification. Pending account bootstrap exposes waiting/Home, not a duplicate mutation. |

These are locally verified implementations, not actual OAuth, unsubscribe-provider, renewal/payment, public-hosting or release acceptance.

## Timeout and recovery decisions

### Callback

- **15 seconds is a presentation threshold**, consistent with the existing website recovery timeout scale. It does not reject the SDK promise, clear pending consent, declare sign-in failed or cancel an operation at the provider.
- The current Supabase client owns URL initialization/token handling. The inspected configuration uses the SDK’s default implicit flow; the UI does not call `verifyOtp` or `exchangeCodeForSession`, and this batch does not change flow configuration. A synthetic fragment callback exercises the actual installed SDK: one `/auth/v1/user` token verification, fragment cleanup, then preference retry with no second verification or token exchange. PKCE-provider acceptance is not claimed.
- Session lookup/SDK initialization, backend `GET /api/auth/me`, and consent/profile persistence are separate stages. The UI does not pretend it can distinguish individual internal SDK exchange substeps while `getSession()` is unresolved. Ordinary no-consent callbacks continue to the existing guard, which owns routine profile bootstrap.
- The cached verification promise and verified account are reused during eligible consent retry. Retry never replays URL credentials. Leaving or switching account invalidates the callback; its owned backend read is aborted. A microtask checks the latest effect owner so development Strict Mode reattachment does not abort its shared cached operation. SDK initialization itself is not claimed to be abortable.
- The native dialog retains real modal focus behavior. The former forced Tab loop and blocked Escape are removed. Back to sign in is present while pending as well as after failure, uses the existing safe-next allowlist, and Escape activates that same exit. Stalled announcements do not steal focus. An already-authenticated login may still perform its existing redirect; this is not stale callback navigation.

### Unsubscribe

- **10 seconds:** announce taking longer while retaining the active request and disabling Retry. **15 seconds:** the existing AbortController request deadline expires. The UI says the update may still finish, not that the preference update failed or was cancelled server-side.
- Only a manual eligible retry can submit again, using the same token in current-page memory. The server endpoint remains unchanged and retains its existing idempotent/non-disclosing preference semantics. A response containing `success: true` still uses Batch 1’s “if this link was valid” wording; server-side invalid/expired tokens cannot be distinguished from that response.
- The initial pending view already had useful text after Batch 1. This batch adds the missing visual progress and separates timeout uncertainty from ordinary retryable failure. Pending, failure, uncertain, missing/invalid and confirmed states retain the same layout. No localStorage/sessionStorage/token-link persistence was added. Leaving the view does not imply cancellation of an in-flight server update.

### Checkout

- **12 seconds:** retains the existing restoration deadline but changes the message to unconfirmed status and exposes recovery. Aborting the local request is not evidence that a charge or an operation failed.
- A full reload was **not** chosen as the new action: the inspected ordinary entry path may legitimately create a checkout after finding no reusable operation. The separate manual recovery path is GET-only and cannot enter that creation branch, even with offer/price query parameters still present.
- A synchronous controller lock prevents repeated recovery clicks. Account generation plus read sequence checks protect responses, and account change/unmount abort the local recovery read. Existing per-account storage is reused; no new sensitive URL/storage location was introduced.
- Payment confirmation, account-access refresh, consent, integer-paise totals, cancellation and provider authority are unchanged. Recovery of an operation does not assert paid access, and an absent operation does not authorize an automatic replacement.

### Protected routes

- **15 seconds:** keep the skeleton and add “Your account check is taking longer.” Timeout alone cannot redirect as signed out, authorize children, bootstrap a new account or expose a previous user.
- Session/account-read retries are manual, locked against repeated clicks and invalidate the previous effect generation. Where fetch supports cancellation, the current-user read gets an AbortSignal. SDK lookups are fenced rather than represented as cancelled.
- If the wait has reached account bootstrap/consent persistence, the panel offers waiting/Home instead of a retry that could duplicate the pending POST. Once an actual failure settles, the existing setup-recovery behavior remains available.
- Timers, auth subscriptions, logout listeners and owned read controllers are cleaned up on departure/retry. Later results must still pass the existing account/operation guards. No authentication or entitlement decision was weakened.

## Design and changed files

Reused the approved original mascot and wordmark through Batch 1’s `WebsiteRecovery` and existing `WebsiteLogin` presentation, `DashboardLoading` skeleton, local Website Inter fonts with Arial fallback, blue/navy palette, rounded controls and existing checkout surfaces. No new illustrations or remote assets were necessary. CSS progress rings are decorative and become stationary under reduced motion; all useful status and recovery text remains readable with images blocked.

- `frontend/src/auth/WebsiteProgress.jsx`, `website-progress.css`: scoped progress indicator/recovery panel and responsive dashboard-contained stalled presentation.
- `frontend/src/auth/WebsiteCallbackLoading.jsx`, `website-callback-loading.css`: branded native modal progress, stages and keyboard-safe exits.
- `frontend/src/auth/AuthScreens.jsx`: callback threshold, stage reporting and owned read cleanup; website guard stalled state/retry fencing. Electron’s legacy presentation and new cancellation/timer behavior remain separately guarded.
- `frontend/src/auth/authApi.js`, `authApi.test.js`: optional AbortSignal on current-user reads, unchanged default request semantics, focused forwarding assertion.
- `frontend/src/auth/WebsiteAccountActions.jsx`: unsubscribe progress/slow/uncertain outcomes; existing logout implementation and unsubscribe limits preserved.
- `frontend/src/auth/WebsiteRecovery.jsx`: opt-in progress and opt-out of repeated heading focus for unsubscribe stage changes. Defaults preserve Batch 1 states.
- `frontend/src/auth/BillingCheckout.jsx`: GET-only existing-operation recovery, pending lock and obsolete-read cleanup.
- `frontend/tests/website-progress/progress.spec.js`, `frontend/playwright.website-progress.config.js`: production and development Strict Mode fixtures. No package, lint configuration or authentication setting changes.
- `frontend/scripts/website-progress-preview.cjs`: isolated loopback synthetic review runtime.
- This report and a dated reference appended to the audit. No historical observation or acceptance journal is rewritten.

No applicable AGENTS.md was found in the inspected parent/project/frontend/source paths. Existing graph relationships were queried and then checked against current source; no graph rebuild or external model/provider request was needed.

## Exact verification

Evidence: `tmp/website-batch2/`; isolated production output: `tmp/website-batch2-production/`. Browser requests are fulfilled locally or blocked before external dispatch. Synthetic session identities, dates and checkout data are test fixtures, not new billing acceptance.

| Check | Result |
| --- | --- |
| `node --test src/auth/AuthScreens.test.js src/auth/authApi.test.js src/auth/customerErrors.test.js src/auth/websiteSessionLoss.test.js src/auth/passwordRecovery.test.js src/auth/signup_oauth_consent.test.js src/auth/onboardingApi.test.js` (frontend cwd) | **113/113 pass**, exit 0; `node-tests.log`. |
| `npm run build -- --outDir ../tmp/website-batch2-production` | Production build passes, exit 0; `build.log`. Process-only synthetic settings below; existing large-chunk warning remains, with no weakened warning limits. |
| `npx playwright test --config playwright.website-progress.config.js` | **36/36 pass**, exit 0, no retries/skips/flaky results; 18 scenarios at **1440×1000** and **390×844**; `results.json`. |
| Same config with `WEBSITE_PROGRESS_DEV=1` and `--grep 'callback preference retry\|actual SDK implicit\|guard repeat retry\|unsubscribe timeout'` | **8/8 pass**, exit 0; development Strict Mode, separate `results-dev.json`. Production screenshots are not overwritten by this run. |
| `npm run lint -- --format json --output-file ../tmp/website-batch2/lint.json` | **0 errors / 12 existing warnings**, exit 0. No suppressions, exclusions or rule changes. |
| `node --check scripts/website-progress-preview.cjs`, `node --check tests/website-progress/progress.spec.js`; scoped `git diff --check` | Exit 0; JSX/CSS bundled and exercised in production output. No configured frontend formatter or static type-check script exists; these are not called a TypeScript or formatter pass. |
| Separate review runtime | Four stalled scenes and their release/recovery paths verified with browser clocks; `preview-review.json`. |
| Preservation | **40 protected files unchanged**, including Batch 1 evidence/report and five payment/email/callback journals; `preserved-before.json`, `preserved-after.json`. Previous provider windows/counters remain untouched. |

The build uses process-only `VITE_SUPABASE_URL=http://127.0.0.1:5319`, `VITE_SUPABASE_ANON_KEY=synthetic-public-key`, `VITE_BACKEND_URL=http://127.0.0.1:5319`, `VITE_CONSENT_FEATURE_ENABLED=true`. Variables are cleared afterward; no `.env` is edited. No database, real account, sending credential, Razorpay script or external service is used.

Initial local failures were investigated rather than retried into a passing claim: duplicate email/tooltip locators were made specific, the Escape fixture was changed to hold an actually unresolved session instead of racing the legitimate authenticated-login redirect, and an attempted PKCE fixture was corrected to the **currently configured implicit SDK flow**. A new cleanup-ref lint warning was fixed without suppressing the rule. No full-CI, admin or Electron acceptance claim is made.

## Visual evidence and owner preview

Desktop/mobile screenshots were inspected for hierarchy, spacing, wrapping, overflow and reachable controls. The guard keeps its skeleton visible; callback keyboard focus is on a usable exit; unsubscribe stages retain a consistent layout; checkout recovery remains inside the existing checkout presentation. Text colors and primary controls reuse Batch 1’s contrast-checked colors. This is not a full screen-reader/cross-browser certification.

| State | Desktop | Mobile |
| --- | --- | --- |
| Callback stalled | [Desktop](../tmp/website-batch2/callback-stalled-desktop.png) | [Mobile](../tmp/website-batch2/callback-stalled-mobile.png) |
| Guard stalled | [Desktop](../tmp/website-batch2/guard-stalled-desktop.png) | [Mobile](../tmp/website-batch2/guard-stalled-mobile.png) |
| Unsubscribe pending | [Desktop](../tmp/website-batch2/unsubscribe-pending-desktop.png) | [Mobile](../tmp/website-batch2/unsubscribe-pending-mobile.png) |
| Unsubscribe slow | [Desktop](../tmp/website-batch2/unsubscribe-slow-desktop.png) | [Mobile](../tmp/website-batch2/unsubscribe-slow-mobile.png) |
| Unsubscribe unknown outcome | [Desktop](../tmp/website-batch2/unsubscribe-unknown-desktop.png) | [Mobile](../tmp/website-batch2/unsubscribe-unknown-mobile.png) |
| Checkout recovery | [Desktop](../tmp/website-batch2/checkout-stalled-desktop.png) | [Mobile](../tmp/website-batch2/checkout-stalled-mobile.png) |
| Images blocked / reduced motion | [Desktop](../tmp/website-batch2/callback-no-images-reduced-motion-desktop.png) | [Mobile](../tmp/website-batch2/callback-no-images-reduced-motion-mobile.png) |

**Open [Batch 2 review](http://127.0.0.1:5311/__review).** Keep this index tab open and open **one scenario at a time** using its links:

1. Callback: wait 15 seconds for stalled copy. Click **Release current responses** in the index tab to observe late completion. Back to sign in/Escape remain available without replaying tokens.
2. Protected route: wait 15 seconds. Observe the unchanged skeleton and recovery panel. Retry rechecks without granting access; release the response from the index to complete verification.
3. Unsubscribe: observe progress immediately, slower status at 10 seconds, uncertainty at 15 seconds. After releasing responses, use the now-enabled manual Retry if the prior request already timed out. The address bar has no token.
4. Checkout: wait 12 seconds, release responses in the index, then click **Recover existing checkout**. Only the existing synthetic pending operation is read. No provider payment interface is opened.

Use responsive tools at **390×844** for mobile. This runtime is intentionally left available for owner review on **127.0.0.1:5311 and 127.0.0.1:5319**. It is separate from Batch 1’s existing 5301/5309 preview and normal app origins. The review-only selector and release controls operate solely on local fixture responses, not real account/provider state.

Restart from repository root with `node frontend/scripts/website-progress-preview.cjs` after preparing the isolated build above. It uses synthetic browser state, permits only its loopback API in a preview-only CSP, does not forward requests, and rejects billing POSTs. Stop a manually started review process with Ctrl+C. Automated test browsers/listeners are closed. Do not expose this fixture server publicly.

## Remaining limits

Local evidence supports Batch 2 remediation of these application-controlled states. It does not establish real OAuth/provider recovery, email delivery, payment execution, native browser/hosting failures, Safari/Firefox behavior, or installed Electron/admin acceptance. SDK lookups and server-side work cannot be declared cancelled merely by leaving/aborting the browser request.

Other audit findings, legal/download/resource inputs, and checkout branding judgments remain outside this batch. C12 cancellations/support findings, actual renewal and reconciliation recovery, invoice issuance and production readiness remain separately open. No owner business input was needed to implement this batch; **visual review of the four previews is the next action**. No real payments/emails/provider calls, tunnel, migration, DNS/SMTP/auth configuration change, commit, push or deployment.
