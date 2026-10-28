# Website fallback remediation: Batch 1

28 October 2026 (IST). Local customer-website implementation and synthetic verification only. Covers **F04, F05, F06, F07, F10 and F11** from [the historical audit](WEBSITE_FLOW_AND_FALLBACK_AUDIT.md). Other audit findings and C11/C12/C13 acceptance remain separate. No provider acceptance was repeated.

## Implemented behavior

| Finding | Implementation | Local evidence |
| --- | --- | --- |
| F04 | Customer root `errorElement`, independent of the failing page and auth providers. Branded recovery with real Home navigation and explicit Reload, no repeating Retry. Error objects, stacks, auth URLs and payloads are not rendered or logged by the customer boundary. Payment uncertainty reminder appears only on checkout. | Deliberately malformed synthetic user makes the real, production-built resume route throw during rendering. Branded boundary, focus, no developer text, removal of static startup UI and Home navigation verified at both widths. This is fault injection, not a newly discovered valid-user defect. |
| F05 | Inline HTML/CSS/text before React: normal opening, explicit no-JavaScript instructions, detectable entry/module failure and manual Reload. Early error listener survives Vite's removal of entry-script attributes. Successful mount removes the static presentation and listener. Runtime `vite:preloadError` unmounts the customer tree into recovery without automatic replay/reload. | Production entry script blocked, then restored and reloaded; JavaScript-disabled context; 60-second simulated slow startup remains opening, not falsely failed; normal mounting; images blocked and runtime preload-error event. |
| F06 | Existing dashboard shell surrounds account-setup recovery. Customer copy, original mascot and visible blue Retry. Synchronous retry lock plus existing abort/active cleanup; gate remains keyed to verified account identity. Failure never grants completion. | 503 then successful Retry returns to saved step 2; repeated synchronous clicks produce one retry read. Late read after SPA navigation and after a real SDK synthetic sign-out notification cannot restore obsolete onboarding. |
| F07 | Fixed customer messages by recognized auth code/HTTP status, contextual safe fallback otherwise. Shared API retains original compatibility `message`, adds `status`/`code`; only website presentation normalizes it. Covers signup, credential/OAuth errors, bootstrap/guard, resume operations/access selection and sibling notes/Ask AI failure presentation. Local validation and known context-missing recovery remain intact. Website account-check failure is branded. | Unknown technical authentication, account and resume errors are hidden; recognized invalid credentials still produce useful wording. API machine fields and Electron message compatibility are tested. Notes/Ask AI/access-selection catches use the same tested mapper; not every operation was browser-triggered. |
| F10 | Website-only direct logout catches rejection and returned SDK errors, provides locked manual retry, and announces completion only after the SDK returns `error: null`. Pending promise is shared across Strict Mode effect reattachment. Late results cannot update a departed view. | Synthetic SDK logout failure then retry/completion, duplicate clicks and development Strict Mode. Existing menu logout and the sign-out service/scope are unchanged. |
| F11 | Layout effect scrubs token from visible URL; ref holds it only in the current view. One request at a time, 15-second request deadline, maximum **3 total attempts per view**, **15-minute in-memory retry window**, no automatic retry. Success or exhaustion clears the ref. Reload/lost token gives original-email guidance. | Failure then successful same-page retry, duplicate clicks, storage absence, scrubbed screenshot URL, pending/success notices, reload without token, exhausted attempts and expired retry window. Unexpected `success: false` cannot produce success UI. |

### Important contracts retained

- The unsubscribe backend intentionally returns a non-disclosing `success: true` even for an invalid/expired token. The UI therefore preserves **“if this link was valid”**, not a claim that a particular token/account was valid. It cannot distinguish server-side invalid/expired links from that response. The `success: false` fixture tests defensive handling of an unconfirmed response, not a new backend contract. HTTP failures remain retryable within the local bounds; transactional preferences are unchanged.
- The installed Supabase SDK clears its local session even if its default wider sign-out request fails. The first state therefore says **“Sign-out wasn’t confirmed”**. A retry may return success without another HTTP request because the browser is already signed out. Completion copy explicitly concerns **this browser**, never all devices. No authentication scope/security change was made.
- Customer router recovery is separate from `/auth/admin/*`; admin retains its existing default router error UI. Electron keeps its existing BrowserRouter and legacy action components. The early HTML check uses the preload-provided `electronAPI` before showing website startup UI. No Electron installation/acceptance was repeated.
- No tokens are persisted by the unsubscribe implementation. No token is placed in a recovery link, image URL, log, analytics or screenshot. Test network traces contain synthetic values only. Actual server expiry, authorization and unsubscribe semantics are unchanged.

## Design and accessibility

Reused `website-login/mascot.png`, the approved original mascot, and the existing `Website Inter` font with Arial/system fallback. Existing blue `#2563eb`, navy `#10234f`, pale blue `#eef4ff`, white surfaces, rounded controls and dashboard shell are retained. No generated or uploaded assets, alternate mascot, external image dependency or new package.

The mascot is decorative (`alt=""`); all meaning and recovery actions remain in text when artwork is blocked. The reused original PNG is unchanged, rather than creating another brand asset. Static startup deliberately uses a text wordmark and system font, with inline styles; it does not depend on images or downloaded fonts. No animation was introduced.

Headings receive focus on meaningful state changes. Controls have visible focus outlines; status copy has polite, atomic live announcements; existing website error feedback gets alert semantics where appropriate. Onboarding recovery is a section inside the existing dashboard main, not a nested main landmark. Source-color contrast calculations: body `#475569` on white **7.58:1**, white on blue button **5.17:1**, navy on pale blue **13.83:1**. This is not a full assistive-technology certification.

## Changed files

- `frontend/index.html`, `frontend/src/main.jsx`: early static presentation, mount handoff, customer/admin router split and customer chunk recovery.
- `frontend/src/auth/WebsiteRecovery.jsx`, `website-recovery.css`, `WebsiteRenderFailure.jsx`: shared branded recovery and mounting signal.
- `frontend/src/auth/WebsiteAccountActions.jsx`: website logout/unsubscribe lifecycle and retry UI; legacy Electron components retained in AuthScreens.
- `frontend/src/auth/AuthScreens.jsx`: website action routing, contextual safe errors, account recovery and user-bound onboarding prop.
- `frontend/src/auth/DashboardOnboarding.jsx`: dashboard recovery/duplicate retry lock with existing cancellation cleanup.
- `frontend/src/auth/customerErrors.js`, `authApi.js`: presentation mapping and preserved machine-readable metadata.
- `frontend/src/auth/WebsiteLogin.jsx`, `WebsiteSignup.jsx`, `ResumeAccessSelection.jsx`: safe website configuration/access messages; no form/auth/billing-policy changes.
- `frontend/src/auth/customerErrors.test.js`, `authApi.test.js`, `AuthScreens.test.js`: focused mapping/metadata coverage. One older source assertion expected direct raw Google error display; it now asserts the website-aware mapper, whose Electron compatibility is independently tested.
- `frontend/tests/website-fallback/fallback.spec.js`, `frontend/playwright.website-fallback.config.js`: isolated production-browser fixtures and separate Strict Mode smoke mode.
- `frontend/scripts/website-fallback-preview.cjs`: loopback-only synthetic review runtime; not part of the deployed application.
- This report; dated reference appended to the audit. Existing audit observations are preserved.

## Verification

Evidence directory: `tmp/website-batch1/`. Production build: `tmp/website-batch1-production/`. All backend/auth responses in the automated browser suite are fulfilled locally; non-static unknown external requests are aborted. The isolated build overrides the public Supabase URL/key and backend URL with **synthetic** loopback settings; no environment file or credential was changed. No database was needed.

| Command/check | Result |
| --- | --- |
| `node --test src/auth/AuthScreens.test.js src/auth/authApi.test.js src/auth/customerErrors.test.js src/auth/websiteSessionLoss.test.js src/auth/onboardingApi.test.js src/auth/passwordRecovery.test.js src/auth/signup_oauth_consent.test.js` (frontend cwd) | **112/112 pass**, exit 0; `tmp/website-batch1-node.log`. |
| `npm run build -- --outDir ../tmp/website-batch1-production` with process-only `VITE_SUPABASE_URL=http://127.0.0.1:5309`, `VITE_SUPABASE_ANON_KEY=synthetic-public-key`, `VITE_BACKEND_URL=http://127.0.0.1:5309` | Production-optimized build passes, exit 0; `tmp/website-batch1-build.log`. Variables cleared afterward. Existing large-chunk warning remains; no warning limit/config weakened. Vite notes the dedicated outDir is outside frontend and is not automatically emptied. |
| `npx playwright test --config playwright.website-fallback.config.js` | **32/32 pass**: 16 cases at **1440×1000** and **390×844**; `results.json`. No retries, skips or flaky results. |
| Same config with `WEBSITE_FALLBACK_DEV=1`, synthetic public env above, `--grep 'normal production startup\|onboarding retry\|logout rejects\|unsubscribe scrub'` | **8/8 pass**, development Strict Mode effect reattachment; `results-dev.json`. Separate output avoids overwriting production evidence. |
| `npm run lint -- --format json --output-file ../tmp/website-batch1-lint.json` | **0 errors / 12 existing warnings**, exit 0. No rules, exclusions or warning limits changed. |
| `node --check scripts/website-fallback-preview.cjs`, `node --check src/auth/customerErrors.js`, `node --check tests/website-fallback/fallback.spec.js` | Exit 0. JSX compiled by production build. |
| Scoped `git diff --check` for changed tracked files; syntax-check inline HTML scripts | Exit 0. Repository has no configured frontend formatter or static type-check command; these checks are not claimed as a TypeScript/formatter pass. |
| Local review runtime | Eight scenario links inspected, four recovery actions exercised and safe login rejection confirmed; `preview-review.json`. |
| Historical provider/payment/email evidence | Five journal hashes unchanged; `preserved-journals.json`. Prior audit captures and counters not reset. |

During development, selectors/API fixtures were corrected for actual login heading capitalization, Supabase error-code format, preserved login `next` query, and the SDK's local-session removal contract. Initial failed local runs were not called passing acceptance. No accepted external or installed tests were repeated. No full-CI claim is made.

### Screenshots

Production screenshots have desktop/mobile counterparts under `tmp/website-batch1/`; the representative states were visually inspected. Horizontal overflow assertions run on captured views. The startup screenshot also confirms the empty React root no longer adds a second dark viewport.

| State | Desktop | Mobile |
| --- | --- | --- |
| Root render recovery | [Desktop](../tmp/website-batch1/render-failure-desktop.png) | [Mobile](../tmp/website-batch1/render-failure-mobile.png) |
| Entry module failed | [Desktop](../tmp/website-batch1/entry-failure-desktop.png) | [Mobile](../tmp/website-batch1/entry-failure-mobile.png) |
| JavaScript disabled | [Desktop](../tmp/website-batch1/javascript-disabled-desktop.png) | [Mobile](../tmp/website-batch1/javascript-disabled-mobile.png) |
| Onboarding recovery | [Desktop](../tmp/website-batch1/onboarding-failure-desktop.png) | [Mobile](../tmp/website-batch1/onboarding-failure-mobile.png) |
| Safe account error | [Desktop](../tmp/website-batch1/safe-account-error-desktop.png) | [Mobile](../tmp/website-batch1/safe-account-error-mobile.png) |
| Safe resume error | [Desktop](../tmp/website-batch1/safe-resume-error-desktop.png) | [Mobile](../tmp/website-batch1/safe-resume-error-mobile.png) |
| Safe login error | [Desktop](../tmp/website-batch1/safe-login-error-desktop.png) | [Mobile](../tmp/website-batch1/safe-login-error-mobile.png) |
| Logout failure | [Desktop](../tmp/website-batch1/logout-failure-desktop.png) | [Mobile](../tmp/website-batch1/logout-failure-mobile.png) |
| Logout completion | [Desktop](../tmp/website-batch1/logout-complete-desktop.png) | [Mobile](../tmp/website-batch1/logout-complete-mobile.png) |
| Unsubscribe retry | [Desktop](../tmp/website-batch1/unsubscribe-failure-desktop.png) | [Mobile](../tmp/website-batch1/unsubscribe-failure-mobile.png) |
| Unsubscribe completion | [Desktop](../tmp/website-batch1/unsubscribe-complete-desktop.png) | [Mobile](../tmp/website-batch1/unsubscribe-complete-mobile.png) |
| Original link needed after reload | [Desktop](../tmp/website-batch1/unsubscribe-link-lost-desktop.png) | [Mobile](../tmp/website-batch1/unsubscribe-link-lost-mobile.png) |
| Decorative images blocked | [Desktop](../tmp/website-batch1/images-blocked-desktop.png) | [Mobile](../tmp/website-batch1/images-blocked-mobile.png) |

## Working local previews for owner verification

Open **[Batch 1 review index](http://127.0.0.1:5301/__review)**. Select **one scenario at a time** because the tiny local fixture server shares a scenario selector. This is an isolated synthetic review origin, not a real account or live billing runtime.

1. Rendering failure: inspect branding, Home and Reload. The deliberate bad-data fixture persists until a different scenario is selected; Reload does not pretend to repair that fixture.
2. Entry-script failure: Reload removes the one-shot local block and opens the real login page.
3. Onboarding: Retry returns to saved synthetic step 2.
4. Sign-out: inspect honest failure, then Retry; completion concerns this browser only.
5. Unsubscribe: inspect failure and token-free address bar, then Retry; reload afterward requests the original link.
6. Link lost: inspect original-email instructions.
7. Account check: inspect safe branded account-verification failure. Login scenario lets you submit clearly synthetic fields to see the safe unknown-error message.

To inspect JavaScript-disabled HTML, disable JavaScript in browser developer tools and reload a preview page, then re-enable it before continuing. Use responsive tools at **390×844** for mobile. Screenshots above remain available independently of the running preview.

Restart from repository root with `node frontend/scripts/website-fallback-preview.cjs` after preparing the isolated production build as above. It binds **only 127.0.0.1:5301 and 127.0.0.1:5309**, refuses provider forwarding, seeds only synthetic browser state, and applies a preview-only CSP that blocks external connections/fonts. It must never be exposed publicly. Normal app/auth storage on other origins is untouched. Stop a manually started preview with Ctrl+C; this task leaves the review runtime running intentionally for owner verification. Automated test browsers/listeners are closed.

## Limits and remaining work

- HTML must arrive for the static fallback to exist. It cannot replace browser-owned offline/DNS/TLS pages or hosting/proxy errors. No public deployment, CSP policy or CDN/chunk-cache behavior was accepted here.
- Entry download failures were actually intercepted in production output. Runtime lazy-chunk handling was verified with Vite's documented event shape locally; the current website has no lazy-route deployment to exercise against a CDN. No service worker, offline cache or deployment change was introduced.
- Chromium desktop/mobile and source/DOM checks do not establish Safari, Firefox, screen-reader or public-hosting acceptance. No Electron/admin screen acceptance was performed; their separate branches were preserved by source inspection and compatibility tests.
- Remaining original findings include starter metadata/favicon (F01), 404 (F02), other legacy AuthShell states (F03), callback pending recovery (F08), legal/download/resource links (F12–F14), native resume dialogs (F15), onboarding review copy (F16), checkout timeout control (F17) and stalled guard lookup (F18). F09 overlaps the progress/status UI required by F11 and now receives that status; no broad second-batch closure is claimed. Checkout design judgments and owner-approved legal/download/resource content remain separate.
- No owner decision was needed for this local batch. Owner visual review is the next action. C12 cancellation/support/renewal uncertainty, invoices and release readiness remain unchanged. No real payments, emails, provider calls, tunnel, migration, credential/configuration changes, commit, push or deployment.
