# Website fallback remediation: Batch 3

28 October 2026 (IST). **Customer website, local implementation and synthetic verification only.** Covers F01/F02/F03/F15/F16 from the [historical audit](WEBSITE_FLOW_AND_FALLBACK_AUDIT.md). Earlier batches and provider journals are preserved. No payment, email, callback-provider, installed-app or staging acceptance was repeated. Razorpay remains paused.

## Implemented behavior

| Finding | Change | Evidence and limits |
| --- | --- | --- |
| F01 | Branded static base title and local mascot favicon; fixed route-title vocabulary for public, authentication, callback, preference, account and checkout entries. Case/trailing-slash aliases normalize without using query, hash, account or payment values. The root render fallback sets an explicit unavailable-page title. Dashboard cleanup no longer restores a stale customer title. | Production-browser direct entries/transitions, aliases, render failure, disabled/failed JavaScript and runtime-boundary checks; fixed-map privacy Node test. Password/reset/status/session titles are also source-inspected mappings, not renewed authentication acceptance. This does not establish SEO, social previews or deployed metadata. |
| F02 | The shared 404 now uses `WebsiteRecovery`, the approved mascot/wordmark, pale blue surface, navy copy and existing recovery controls. Home works; Back preserves the existing known-route history behavior, with Home for direct entry. History retains only pathname/key, not query/hash. Requested URLs and external referrers are never displayed or used as destinations. | Desktop/mobile production captures; direct Back, known in-app Back, Home, heading focus, blocked artwork and reduced-motion inspection. Missing legal pages and hosting-generated 404s remain unresolved separately. |
| F03 | Remaining customer secure-link missing/invalid/service-failure and verified-but-unfinished-setup branches use the earlier shared scaffold with relevant actions. Existing verified/expired confirmation designs are retained. Setup continuation preserves its retry state and saved consent. | Missing/unsupported links, service failure and unfinished setup browser-verified. Setup continuation succeeds after the synthetic failure clears; consent remains until successful persistence. No verification/redirect/API security semantics changed. |
| F15 | Website deletion, replacement upload and re-extraction use custom confirmations built on `ResumeDialog`. Explicit consequences/action labels, red destructive action, safe React filename text, initial Keep focus, native modal containment, Escape and trigger restoration. Confirmation is bound to the account, current records, file, draft and eligibility state; changed state or another operation rejects it. Repeated confirmation cannot submit twice. | All three variants browser-verified, including nested-dialog cancel, successful re-extraction, pending/error deletion, account change and preservation of edits/file after a failed replacement upload. Pure guard regression checks cover record/file/draft/eligibility changes. Existing authenticated API still decides server-side eligibility. |
| F16 | Omitted the unsupported decorative candidate/rating/review block from the website welcome step. Its escaped separator and “mock reviews” disappear with it; no replacement claim was invented. | Repository search found the numbers only in the component and historical audit, not approved supporting evidence. Browser welcome captures verify absence and existing Get Started control. Steps, progress, Skip and API behavior were not changed or reaccepted. Broader J04 remains separate. |

The shared recovery scaffold now hides failed decorative images instead of showing broken-image boxes. Essential copy, wordmark and actions remain usable without artwork. No competing layout, component dependency or generated illustration was needed.

## AuthShell inventory and runtime boundaries

`AuthShell`/`AuthLinks` were inspected before changing their callers:

| Branch | Customer website outcome |
| --- | --- |
| `EmailConfirmationPage` | Remaining customer failure/setup branches changed above; existing loading, verified and expired-link presentations retained. Legacy return remains for Electron. |
| `RequireAuth` | Earlier branded loading/stall, setup recovery and lookup-error branches preserved. Legacy shell occurs only after the website returns. |
| `AuthUnsubscribePage` / `AuthLogoutPage` | Existing website dispatch to `WebsiteUnsubscribe` / `WebsiteLogout` retained. Their legacy counterparts were not restyled. |
| Signup / forgotten-password / reset-password | Existing website components return before legacy shells. Electron/explicit desktop-handoff branches remain unchanged. |
| Callback / desktop auth status | Earlier website callback presentation and website status redirect retained. Legacy shells belong to the desktop-specific branch. |

The established **`window.electronAPI` preload boundary** controls Electron behavior. Its existing Vite title/favicon are deliberately retained before module startup; website metadata is not applied to that runtime. Native resume confirmations remain inside the explicit Electron branch. The shared onboarding component also retains its pre-existing desktop copy; removing website claims is not approval of those claims elsewhere.

The registered `/auth/admin/*` boundary retains its previous metadata and DashboardLayout behavior, including case-insensitive route aliases. No admin component or permission behavior was changed. Anonymous metadata-only boundary checks are not admin-operation acceptance. Existing browser desktop-handoff presentation was not redesigned.

## Changed files and assets

- `frontend/index.html`: website base title/favicon with shared-runtime preservation.
- `frontend/src/websiteMetadata.js`, `websiteMetadata.test.js`: fixed safe title vocabulary and privacy/alias tests.
- `frontend/src/WebsiteNotFound.jsx`: shared branded presentation, metadata application and token-free history bookkeeping.
- `frontend/src/auth/DashboardLayout.jsx`: customer title ownership handed to route metadata; admin behavior retained.
- `frontend/src/auth/WebsiteRenderFailure.jsx`: safe error-state title.
- `frontend/src/auth/WebsiteRecovery.jsx`: hide failed decorative artwork.
- `frontend/src/auth/AuthScreens.jsx`: remaining secure-link scaffold and state-bound website confirmations; failed upload preserves the prior draft until a replacement is accepted.
- `frontend/src/auth/WebsiteResumes.jsx`, `website-resumes.css`: reuse dialog primitive, unique nested labels, confirmation copy/actions/focus/wrapping.
- `frontend/src/auth/resumeConfirmation.js`, `resumeConfirmation.test.js`: small client-state confirmation guard and race coverage.
- `frontend/src/auth/AuthScreens.test.js`: replace the obsolete native-dialog text assertion with the new confirmation contract; existing lifecycle assertions retained.
- `frontend/src/auth/DashboardOnboarding.jsx`: website decorative claim omitted.
- `frontend/public/website-favicon.png`: **64 × 43 PNG, 3,843 bytes**, resized/optimized from the approved `website-login/mascot.png`. No new character or remote asset.
- `frontend/playwright.website-branding.config.js`, `frontend/tests/website-branding/branding.spec.js`: isolated production/StrictMode browser checks.
- `frontend/scripts/website-branding-preview.cjs`: loopback-only synthetic review server; not an application route or provider proxy.
- This report and an appended historical-audit remediation reference.

Existing local Website Inter typography, approved mascot, blue/navy palette, controls and responsive recovery/dialog layouts were reused. Decorative recovery artwork keeps empty alt text; the wordmark and instructions remain text. No package, ESLint-rule, billing, auth-provider, consent-policy, DNS or SMTP changes.

## Verification

All browser API responses were local substitutes. Other external requests were aborted. No real user, resume mutation, provider, database or email was involved. The explicit render-fault fixture is not evidence of a real account failure.

| Command/check | Final result |
| --- | --- |
| `npm run build -- --outDir ../tmp/website-batch3-production` with synthetic loopback Vite configuration | **Exit 0**. Existing large-chunk advisory and external-output-directory notice remain. No warning limits changed. |
| `npx playwright test -c playwright.website-branding.config.js` | **Exit 0; 38/38**, 19 cases at each **1440×1000** and **390×844**; no retries, skipped, flaky or unexpected cases. Production build, not Vite development. |
| Same config with `WEBSITE_BRANDING_DEV=true`, grep `resume delete is\|delete submission\|account switch\|draft replacement` | **Exit 0; 8/8** local StrictMode lifecycle checks. No production screenshots overwritten. |
| `node --test --test-reporter=tap src/websiteMetadata.test.js src/auth/resumeConfirmation.test.js src/auth/AuthScreens.test.js src/auth/authApi.test.js src/auth/customerErrors.test.js src/auth/websiteSessionLoss.test.js src/auth/passwordRecovery.test.js src/auth/signup_oauth_consent.test.js src/auth/onboardingApi.test.js` | **Exit 0; 115/115**, no skips. |
| `npm run lint -- --format json --output-file ../tmp/website-batch3/lint.json` | **Exit 0; 0 errors / 12 existing warnings**. No new diagnostics in Batch 3 files; no rules/suppressions changed. |
| `node --check` on the new metadata/confirmation helpers, preview script and browser test | **Exit 0**. JSX parsed by production build and lint. |
| Scoped `git diff --check` | **Exit 0**. No configured standalone formatter/typecheck script exists; no TypeScript or full-CI pass is claimed. |
| Interactive synthetic review server | Six review links; 404, invalid/service confirmation, resume deletion, draft replacement/re-extraction and onboarding exercised. Upload fixture deliberately fails locally; no forwarding. |

Browser coverage includes confirmation cancellation and focus restoration, Tab containment, long HTML-like filenames rendered as text, repeated confirmation, pending failure, successful explicit retry, account switching, root-error privacy, startup failure/reload, no-JavaScript readability, saved consent on setup recovery, unsubscribe memory retry and logout uncertainty/completion. Guard tests independently reject changed resume records, file, draft, phase and pending-operation state. They do not substitute for server authorization.

Screenshots were visually inspected for the shared recovery page, mobile confirmations, onboarding, blocked images and enlarged text. Enlarged-text fixtures use 28px body/buttons and 36px headings; this is **text enlargement, not a claim of OS/browser zoom acceptance**. The dialog body scrolls while recovery actions remain reachable. Native browser modal containment is reused. No new animation was introduced; reduced-motion/blocked-artwork cases remain readable.

During harness preparation, assertions referring to a Reload *button* and a plural preference-success heading were corrected to the existing link and singular copy. The obsolete source assertion for native confirmation text was updated because replacing that UI is the intended change. Final results above have no failures.

## Review the pages

Open **[the running local review index](http://127.0.0.1:5321/__review)** and use **one scenario at a time**. Everything uses synthetic local data. The index explains the draft steps. No normal account sign-in is required.

To restart later, from the repository root:

```powershell
node frontend/scripts/website-branding-preview.cjs
```

Requires the prepared `tmp/website-batch3-production` build. Binds only **127.0.0.1:5321** (website) and **127.0.0.1:5329** (synthetic API). CSP restricts connections to those local origins. It never forwards API requests. Close a manually started server with Ctrl+C. Earlier Batch 1/2 preview services were not stopped.

| State | Desktop | Mobile |
| --- | --- | --- |
| Branded 404 | [Screenshot](../tmp/website-batch3/not-found-desktop.png) | [Screenshot](../tmp/website-batch3/not-found-mobile.png) |
| Artwork blocked / reduced motion | [Screenshot](../tmp/website-batch3/not-found-images-blocked-desktop.png) | [Screenshot](../tmp/website-batch3/not-found-images-blocked-mobile.png) |
| Invalid secure link | [Screenshot](../tmp/website-batch3/confirmation-invalid-desktop.png) | [Screenshot](../tmp/website-batch3/confirmation-invalid-mobile.png) |
| Verification service unavailable | [Screenshot](../tmp/website-batch3/confirmation-service-error-desktop.png) | [Screenshot](../tmp/website-batch3/confirmation-service-error-mobile.png) |
| Verified email, unfinished setup | [Screenshot](../tmp/website-batch3/confirmation-account-setup-desktop.png) | [Screenshot](../tmp/website-batch3/confirmation-account-setup-mobile.png) |
| Delete confirmation | [Screenshot](../tmp/website-batch3/resume-delete-desktop.png) | [Screenshot](../tmp/website-batch3/resume-delete-mobile.png) |
| Failed deletion retains resume | [Screenshot](../tmp/website-batch3/resume-delete-failed-desktop.png) | [Screenshot](../tmp/website-batch3/resume-delete-failed-mobile.png) |
| Replace draft | [Screenshot](../tmp/website-batch3/resume-replace-desktop.png) | [Screenshot](../tmp/website-batch3/resume-replace-mobile.png) |
| Extract again | [Screenshot](../tmp/website-batch3/resume-extract-again-desktop.png) | [Screenshot](../tmp/website-batch3/resume-extract-again-mobile.png) |
| Enlarged confirmation text | [Screenshot](../tmp/website-batch3/resume-enlarged-text-desktop.png) | [Screenshot](../tmp/website-batch3/resume-enlarged-text-mobile.png) |
| Onboarding welcome | [Screenshot](../tmp/website-batch3/onboarding-desktop.png) | [Screenshot](../tmp/website-batch3/onboarding-mobile.png) |
| Failed entry module | [Screenshot](../tmp/website-batch3/entry-failure-desktop.png) | [Screenshot](../tmp/website-batch3/entry-failure-mobile.png) |

Evidence: `tmp/website-batch3/results.json`, `results-dev.json`, `node-tests.log`, `lint.json`, `build.log`, `preview-review.json`, task-before copies/diff and preservation manifests. Original acceptance journals and Batch 1/2 evidence hashes remain unchanged. Preview services are intentionally left running for review; browser test contexts are closed and no credentials or database were created.

## Remaining scope

Batch 3 is ready for owner visual review. **F12 legal destinations, F13 download/explanation controls and F14 resource links remain open**, with approved documents/artifact URLs/resource destinations still needed for their later batch. J01–J05 remain separate design/content judgments, apart from the affected onboarding claim removal. No input was needed to implement this batch.

Public hosting/CDN fallbacks, real browser-owned network errors, third-party interfaces, cross-browser/assistive-technology and installed Electron acceptance are not established by these local Chromium fixtures. Existing passed acceptance is preserved, not repeated. C12 cancellation/support, actual renewal/reconciliation recovery, invoice work and production readiness remain separate and open. No phase is marked complete by this website batch.
