# Intervucopilot website flow and fallback audit

27 October 2026 (IST). **Inspection/reporting only. No application-code changes.** Admin pages and Electron screens are excluded. Razorpay remains paused. This is not renewed payment, email, security, installed-app or deployment acceptance.

## Method and evidence

The design reference is the existing Intervucopilot landing page, WebsiteLogin/WebsiteSignup, branded confirmation/password-reset dialogs and DashboardLayout/session viewer: existing wordmark/mascot, blue/navy palette, light rounded surfaces and consistent controls. No new design standard is proposed. `docs/WEBSITE_PASSWORD_RESET.md` and `docs/DASHBOARD_ONBOARDING.md` were inspected. No applicable AGENTS.md was found in the inspected project/parent/frontend paths.

Read the actual route tree, guards, navigation, customer components, styles, public assets and available hosting configuration. The README still describes the Vite starter; the actual package script was used: `npm run dev -- --host 127.0.0.1 --port 5299` from frontend. Chromium inspection used **1440×1000 desktop** and **390×844 mobile**. Browser-memory Supabase substitutes and intercepted API responses used synthetic users. Every API request was fulfilled locally; non-runtime external requests were aborted before dispatch. No real accounts, backend/database, payments, messages or remote writes were used.

Evidence: `tmp/website-flow-audit/`, containing **112 observation records and 114 screenshots**, plus recovery/navigation probes. Counts include diagnostic attempts, not distinct flows or passing tests. Representative screenshots were visually inspected; other states use rendered DOM/source evidence. **BC** = browser-confirmed under the stated trigger; **SC** = source-confirmed, not necessarily browser-observed; **UV** = unverified. A whole flow is never marked passed from one happy-path observation.

**Excluded diagnostic attempts:** initial `checkout-ready`/`checkout-confirmed` fixtures omitted `amount_minor`; resulting BigInt exceptions are not valid payment-flow findings. Corrected `checkout-*-valid` captures supersede them. The default error screen has separate deliberate render-fault evidence. Initial signup-legal/login-error selector mistakes were corrected in `corrected-observations.json`; failed selectors are not findings.

No public deployment/hosting configuration was supplied or inspected. Vite does not establish production CDN rewrites, error sanitization, TLS, offline caching or native browser-error appearance.

| Class | Control boundary |
| --- | --- |
| A | Application HTML/React/CSS/copy/recovery; recommendations below |
| B | Hosting/CDN/proxy 404/502/maintenance responses: UV, not the observed React 404 |
| C | Browser offline/DNS/TLS pages and native dialog chrome: not redesignable by React; app can replace its own confirm calls or handle offline after loading |
| D | Razorpay/bank/OTP/Google interfaces: not exercised and not website-controlled |

## Route and flow inventory

`frontend/src/main.jsx` creates one website data-router root (`path: '*'`, App), without a custom errorElement. App contains a flat Routes tree, not nested customer routes; guards/layouts are composed inside page components.

| Registered website entry | Component/guard and navigation | Evidence |
| --- | --- | --- |
| `/`, `/landing` | LandingPage; sections, account links and pricing | `/` BC; `/landing` SC alias |
| `/auth/login` | AuthLoginPage → WebsiteLogin; authenticated redirect to allowlisted next | Initial/legal/config/error BC; real login/OAuth UV |
| `/auth/signup` | AuthSignupPage → WebsiteSignup; consent and authenticated redirect | Initial/legal BC; submit/verification notice SC |
| `/auth/desktop-login` | Browser login/handoff with validated desktop state | Missing/invalid state BC; valid protocol handoff UV, Electron excluded |
| `/auth/forgot-password` | WebsitePasswordResetPage request dialog over login | Request BC; sent/resend SC |
| `/auth/reset-password` | Same component, verification stage | Missing/invalid entry BC; valid recovery/update SC |
| `/auth/confirm` | Recovery entry → reset; otherwise EmailConfirmationPage | Missing/unsupported/expired/service failure BC; success/bootstrap recovery SC |
| `/auth/callback` | AuthCallbackPage verifies session/bootstrap then safe next | Missing session/error URL/held verification BC; success/retry SC |
| `/auth/status` | Website redirects to dashboard | Anonymous redirect BC; DesktopAuthStatusPage is excluded |
| `/unsubscribe` | AuthUnsubscribePage; scrub token, submit preference | Missing/loading/success/error/reload BC |
| `/auth/onboarding` | RequireAuth → onboarding gate/content | First step and read failure BC; remaining steps SC |
| `/auth/dashboard` | RequireAuth → bootstrap → onboarding gate → keyed dashboard | Signed out/loading/backend/setup/onboarding errors and empty BC |
| `/auth/sessions` | Same guard/gate, sessions variant; details stay on same URL | Empty/failure/list, transcript/notes/chat errors BC |
| `/auth/resume` | RequireAuth → keyed resume page/DashboardLayout; no onboarding gate | Empty/failure/ready record/native delete confirm BC; edit/upload/extract/index SC |
| `/auth/checkout` | BillingCheckout has separate session/operation restore and consent UI | Anonymous/unavailable/prepared/pending/uncertain/confirmed/expired/refresh failure/timeout BC, synthetic only |
| `/auth/logout` | AuthLogoutPage sign-out effect, legacy shell | Success and rejected sign-out BC |
| Customer `*` | WebsiteNotFound + WebsiteRouteHistory | Unknown/direct legal URLs BC |

### Boundaries, standalone entry points and absent routes

- `/auth/admin/subscriptions` and `/auth/admin/billing`, including their internal states: **excluded, not visited**. Shared fallbacks are assessed through customer routes only.
- `/desktop`, `/profile-setup`, `?view=desktop`, `?view=overlay` resolve Electron-oriented views/overrides. **Not rendered/audited as website pages.** The browser accessibility of these entries and AuthLinks' `/desktop` link are navigation-boundary facts, not proof of a website design defect in Electron.
- No separate customer settings, account-profile, help, contact or legal-document router was found. `/terms` and `/privacy` were visited and hit the shared 404. Missing unimplemented features are not invented as required pages.
- Resume profile editing and session transcript/AI Notes/Ask AI/call details are in-page dialogs. No separate payment-success/failure/return URL exists; checkout restores its operation and renders status.
- `frontend/index.html` is the website bootstrap. Public assets include `vite.svg` and email artwork, not custom static 404/500/offline HTML. No repository hosting rewrite/error-page configuration was located. Development test HTML, browser-extension HTML and email preview HTML are not shipped customer website routes in this audit.

### Navigation traced

Header/footer anchors target real landing sections. Mobile menu → Pricing was browser-checked and closes correctly. Get Started/Create Free Account/login links have account destinations. Pricing Free → signup; eligible paid quote → checkout with offer/price IDs. Feature-off checkout says Checkout coming soon; this is not automatically a broken payment.

Protected entries redirect to login with a safe next route. Bootstrap precedes dashboard onboarding; incomplete onboarding redirects dashboard/sessions to onboarding, completed onboarding redirects its entry to dashboard. Sidebar links connect dashboard/sessions/resumes. Login opens password recovery inline. Session details/actions stay in the viewer. Account setup exposes Prepare Profile, not a settings page. Normal menu/logout handlers are separate from the direct logout route.

Legal/download/resource dead ends are detailed below. No support destination, monitored mailbox, released installer or legal document is invented.

## Confirmed findings

**P1:** broken/dead-end recovery, technical failure exposure or important dead navigation. **P2:** clear unfinished/unbranded state. No P0 incident is asserted. Screenshot links are relative to this report; matching desktop/mobile stems exist in the evidence directory.

### F01 — Starter title/favicon on public, auth and checkout pages — P2

- **Entry/trigger/appearance:** normal navigation to landing, login/signup, callback, unsubscribe or checkout retains browser title “Vite + React”; index points to `/vite.svg`. DashboardLayout and WebsiteNotFound set branded titles, so this is not universal.
- **Why/source/control/evidence:** starter identity conflicts with the actual brand. `frontend/index.html`, page title setters. **A; BC title DOM + SC favicon.** Browser tab chrome is not represented by page screenshots; recorded titles are in observations.json.
- **Recovery/recommendation:** some later navigation changes title; otherwise none. Use existing brand base title/favicon and page titles without changing Electron metadata.

### F02 — Unbranded shared 404 — P2

- **Entry/trigger/appearance:** unknown URL, `/terms` or `/privacy` reaching React → dark generic “Page not found,” plain Home/Back, no wordmark/mascot/website shell.
- **Source/control/evidence:** WebsiteNotFound.jsx and website-not-found.css. **A; BC**, [desktop](../tmp/website-flow-audit/unknown-desktop.png), [mobile](../tmp/website-flow-audit/unknown-mobile.png). Not a hosting response.
- **Recovery/recommendation:** Return home exists; direct-entry Go back was verified to go home. Preserve safe actions in existing website styling. Fixed history whitelist behavior beyond those probes is SC, not claimed broken.

### F03 — Shared legacy AuthShell reappears on customer fallback states — P2

- **Entry/trigger/appearance:** malformed/missing confirmation, email-verification service failure, guard backend error, unsubscribe states and direct logout render a generic small card/old auth-link collection; secure-link variant uses a very faint legacy logo rather than current identity.
- **Why/source/control/evidence:** visually different from current login/signup/expired-email screens. AuthScreens.jsx::AuthShell/AuthLinks/EmailConfirmationPage/RequireAuth/AuthUnsubscribePage/AuthLogoutPage; auth.css. **A; BC**, [secure link](../tmp/website-flow-audit/confirm-missing-desktop.png), [guard mobile](../tmp/website-flow-audit/guard-backend-error-mobile.png), [preferences](../tmp/website-flow-audit/unsubscribe-error-mobile.png).
- **Recovery/recommendation:** route-specific links/Retry session check exist. Reuse one approved branded scaffold, preserving verification and account isolation. This is one shared visual finding, not many defects for the same component. Functional dead ends below are separate.

### F04 — Default developer error page on unhandled rendering failure — P1

- **Entry/trigger/appearance:** deliberately injected throwing login component → “Unexpected Application Error!”, exception/stack locations, “Hey developer,” ErrorBoundary implementation advice and mobile overflow.
- **Source/control/evidence:** main.jsx data-router root has no errorElement; no website ErrorBoundary located. **A; BC under explicit fault injection + SC**, [desktop](../tmp/website-flow-audit/render-error-desktop.png), [mobile](../tmp/website-flow-audit/render-error-mobile.png).
- **Recovery/recommendation:** no customer Home/Retry. Add a branded root boundary, safe recovery/private diagnostics. Observed in Vite development; exact production stack exposure is **UV**. Malformed audit checkout fixtures do not prove a valid-payment crash.

### F05 — Blocked entry script produces a blank page — P1

- **Entry/trigger/appearance:** HTML arrives but `/src/main.jsx` is blocked → empty document, no brand/progress/recovery.
- **Source/control/evidence:** index.html empty root, no static startup/noscript fallback. **A for delivered HTML, B/C if HTML cannot load; BC injected script failure**, [desktop](../tmp/website-flow-audit/javascript-unavailable-desktop.png), [mobile](../tmp/website-flow-audit/javascript-unavailable-mobile.png).
- **Recovery/recommendation:** browser reload only. Add branded startup/chunk-failure recovery using existing design. This is not an observed native offline/DNS page or production chunk-cache failure.

### F06 — Onboarding failure exposes migration wording and near-invisible Retry — P1

- **Entry/trigger/appearance:** authenticated gate + failed onboarding GET → mostly blank card, “Account setup or the onboarding migration may not be ready,” no brand and very low-visibility Retry onboarding text.
- **Source/control/evidence:** DashboardOnboardingGate, onboardingApi.js and onboarding CSS. **A; BC**, [desktop](../tmp/website-flow-audit/onboarding-error-desktop.png), [mobile](../tmp/website-flow-audit/onboarding-error-mobile.png).
- **Recovery/recommendation:** Retry increments attempt in source. Reuse existing Account setup recovery/dashboard language and controls; remove migration terminology. Visual contrast issue observed; no formal WCAG measurement claimed.

### F07 — Technical backend/provider messages can reach customers verbatim — P1

- **Entry/trigger/appearance:** error detail/message from user verification, resume load or auth is displayed unchanged. Harmless fixtures showed “Synthetic upstream database connection failed,” “Synthetic resume backend unavailable,” and “Synthetic internal authentication service detail.”
- **Source/control/evidence:** authApi.js::parseJsonResponse propagates payload.detail; AuthScreens displays error.message in guard/resume and website credential/OAuth paths. **A; BC + SC**, [guard](../tmp/website-flow-audit/guard-backend-error-desktop.png), [resume](../tmp/website-flow-audit/resume-failed-mobile.png), [login](../tmp/website-flow-audit/login-error-corrected-desktop.png).
- **Recovery/recommendation:** some views have Retry; login retains form. Map known failures to approved customer wording, retaining safe validation and private diagnostics. No real production secret/error incident was observed. Session-detail errors already use safer normalized messages.

### F08 — Callback spinner exposes “LOADING STATE” and traps pending navigation — P2

- **Entry/trigger/appearance:** `/auth/callback`, held synthetic getSession → foreground “LOADING STATE / Signing you in… / Please wait,” Escape prevented, no pending Back/Retry.
- **Source/control/evidence:** WebsiteCallbackLoading.jsx and AuthCallbackPage. **A; BC pending, SC unbounded lookup branch**, [desktop](../tmp/website-flow-audit/callback-loading-desktop.png), [mobile](../tmp/website-flow-audit/callback-loading-mobile.png).
- **Recovery/recommendation:** settled error has Back to sign in; preference persistence has specific retry. Replace developer label and provide bounded safe pending recovery without replaying tokens/codes.

### F09 — Unsubscribe pending state has no loading indicator — P2

- **Entry/trigger/appearance:** synthetic token/request held → Email preferences, transactional notice and old links, but no processing/status message because loading starts with an empty message.
- **Source/control/evidence:** AuthUnsubscribePage. **A; BC**, [desktop](../tmp/website-flow-audit/unsubscribe-loading-desktop.png), [mobile](../tmp/website-flow-audit/unsubscribe-loading-mobile.png).
- **Recovery/recommendation:** no page deadline or pending recovery control. Add accessible progress and bounded failure/retry using only current in-memory identity/token.

### F10 — Direct logout failure never leaves “Signing out…” — P1

- **Entry/trigger/appearance:** direct `/auth/logout`, synthetic signOut rejection → unchanged pending card and unhandled rejected promise; no failure/Retry UI.
- **Source/control/evidence:** AuthLogoutPage awaits signOutWebsite without catch. **A; BC**, [desktop](../tmp/website-flow-audit/logout-failed-desktop.png), [mobile](../tmp/website-flow-audit/logout-failed-mobile.png).
- **Recovery/recommendation:** general links remain; refresh can repeat failure. Provide honest completion/failure and guarded retry. Dashboard/menu logout has its own guarded paths and is not universally broken.

### F11 — Failed unsubscribe cannot retry after URL cleanup — P1

- **Entry/trigger/appearance:** failed `/unsubscribe?token=…` says try again later but has no Retry; reload now shows missing/invalid link after token scrub. Both widths verified in recovery-probes.json.
- **Source/control/evidence:** AuthUnsubscribePage/submitMarketingUnsubscribe. **A; BC**, [mobile](../tmp/website-flow-audit/unsubscribe-error-mobile.png).
- **Recovery/recommendation:** reopen original email link, not explained on page. Add in-memory retry or explicit guidance; preserve URL scrubbing rather than persisting/re-exposing the token.

### F12 — Legal links are unpublished or lead to marketing content — P1

- **Entry/trigger/appearance:** login/signup legal controls show unpublished notices; landing Privacy and Terms both scroll to `#privacy`, the “Your data. Your control.” marketing section. Direct legal paths hit F02.
- **Source/control/evidence:** WebsiteLogin, WebsiteSignup, LandingPage footer, App route tree. **A; BC + SC**, [login notice](../tmp/website-flow-audit/login-legal-desktop.png), [signup notice](../tmp/website-flow-audit/signup-legal-corrected-mobile.png), [footer](../tmp/website-flow-audit/landing-navigation-mobile.png).
- **Recovery/recommendation:** close notice/return to form/home; no document. Connect approved legal documents before presenting complete consent navigation. Owner-approved content is required; do not invent it or duplicate the 404 finding.

### F13 — Download/explanation CTAs are decorative divs — P1

- **Entry/trigger/appearance:** landing Desktop/FinalCTA shows “Download Desktop App (macOS • Windows),” “Download Desktop App” and “Learn How It Works,” styled like controls without links/handlers.
- **Source/control/evidence:** LandingPage Desktop/FinalCTA. **A; BC DOM + SC**, [desktop](../tmp/website-flow-audit/landing-download-desktop.png), [mobile](../tmp/website-flow-audit/landing-download-mobile.png). Recovery probes confirm both downloads lack interactive ancestors; no download was initiated.
- **Recovery/recommendation:** signup/header links still work. Connect approved released artifacts/workflow anchor or label availability honestly. Released OS URLs are an input; Electron screens remain out of scope.

### F14 — Footer documentation/security resources are inert — P2

- **Entry/trigger/appearance:** Documentation, Security & Compliance, API References and Security appear among real links but are noninteractive div/paragraph content. No independent help/contact route exists.
- **Source/control/evidence:** LandingPage Footer. **A; BC DOM + SC**, [desktop](../tmp/website-flow-audit/landing-navigation-desktop.png), [mobile](../tmp/website-flow-audit/landing-navigation-mobile.png).
- **Recovery/recommendation:** FAQ is a real anchor; these resources have none. Connect approved resources or remove/relabel unavailable navigation; do not invent a monitored support address.

### F15 — Resume actions use browser-native confirmations — P2

- **Entry/trigger/appearance:** Delete Resume on synthetic ready record emits native confirm “Delete this cloud resume (synthetic-audit.txt - confirmed)?” Upload over draft/re-extract also use window.confirm in source.
- **Source/control/evidence:** AuthScreens resume handlers. **A initiates / C renders chrome; BC delete event, SC other two**. Exact dialog event in extended-observations.json; [desktop](../tmp/website-flow-audit/resume-delete-dialog-desktop.png)/[mobile](../tmp/website-flow-audit/resume-delete-dialog-mobile.png) show underlying page, **not native chrome**.
- **Recovery/recommendation:** dialog was dismissed, no delete request. Reuse existing SessionConfirmation/ResumeDialog patterns while retaining confirmation/operation guards. No customer alert()/prompt() site found in the inspected website components; Electron sites excluded.

### F16 — Onboarding shows an escaped separator and unfinished review wording — P2

- **Entry/trigger/appearance:** first onboarding step shows literal `\u00b7` with “4.9” and “340,000+ mock reviews,” not a tool encoding artifact.
- **Source/control/evidence:** DashboardOnboarding JSX text. **A; BC + SC**, [desktop](../tmp/website-flow-audit/onboarding-desktop.png), [mobile](../tmp/website-flow-audit/onboarding-mobile.png).
- **Recovery/recommendation:** Get Started/Skip exist. Correct the separator/copy with approved content. The numbers' substantiation is a separate owner review, not established false here.

### F17 — Checkout timeout gives reload instructions without a recovery control — P2

- **Entry/trigger/appearance:** held checkout restoration for >12 seconds → “Reload to recover your payment status”; only Back to pricing is available when operation is absent.
- **Source/control/evidence:** BillingCheckout restoration timer/conditional controls. **A; BC after real local timeout**, [desktop](../tmp/website-flow-audit/checkout-timeout-desktop.png), [mobile](../tmp/website-flow-audit/checkout-timeout-mobile.png).
- **Recovery/recommendation:** browser reload exists; Back to pricing works as an affordance. Provide visible recovery bound to restoring existing operation, never automatically create another payment or declare timeout a failed charge.

### F18 — Guard lookup can remain on a skeleton without stalled-request recovery — P2

- **Entry/trigger/appearance:** protected-page session lookup never settles → otherwise branded loading shell continues without pending retry/sign-in escape.
- **Source/control/evidence:** RequireAuth loadUser/DashboardLoading. **A; BC held state + SC no bound around getSession/user lookup**, [desktop](../tmp/website-flow-audit/guard-loading-desktop.png), [mobile](../tmp/website-flow-audit/guard-loading-mobile.png).
- **Recovery/recommendation:** settled failures have recovery; pending has browser reload. Preserve skeleton and add bounded stalled-session handling. Held lookup is a simulation, not a deployed outage. Password recovery has its own 15-second deadline and is not grouped into this finding.

## Design judgments requiring review

These are observations, not additional confirmed functional defects.

| ID | Observed state | Judgment/input and recommendation | Evidence |
| --- | --- | --- | --- |
| J01 | Checkout is a standalone summary card without established wordmark/mascot/header | Brand omission is observable; whether minimal checkout is intentional needs review. Reuse existing brand header if approved; retain consent and totals. | BillingCheckout; BC, [desktop](../tmp/website-flow-audit/checkout-prepared-valid-desktop.png), [mobile](../tmp/website-flow-audit/checkout-prepared-valid-mobile.png) |
| J02 | Confirmed-payment notice says plan updated while failed account read says access temporarily unavailable | This does not prove entitlement wrong: confirmed operation and unavailable refresh are different facts. Consider clearer independent wording, without changing billing authority. | BC synthetic operation + subscription 503, [desktop](../tmp/website-flow-audit/checkout-confirmed-valid-desktop.png) |
| J03 | Empty sessions is a plain notice; Account setup exposes Prepare Profile | These are inside the branded dashboard, not unbranded pages. Review contextual next steps and customer-oriented wording. | sessions-empty captures; AuthScreens SC/BC |
| J04 | Login artwork says Resume indexed / 4.2 MB parsed; trust numbers and footer entity/year are hardcoded; website illustration says INTERVU AI HUD | Review approved illustrative/marketing/legal copy and naming. Claims are not established false by this audit; no live telemetry/legal entity is invented. | WebsiteLogin, DashboardOnboarding, LandingPage; BC/SC |
| J05 | Pricing empty/unavailable states are brief text within branded landing; unavailable has Retry, availability-off says Checkout coming soon | Review richer guidance without inventing available plans or treating feature-off as failed payment. | CatalogPricing; empty/unavailable BC, other branches SC |

## Coverage matrix

**Inspected does not mean passed.** BC uses local substitutes; SC branches were inspected but not all rendered. No flow is approved solely because its happy path works.

| Flow/state family | Browser-confirmed inspection | Source coverage / blocked or unverified limits |
| --- | --- | --- |
| Landing/navigation | Desktop/mobile, footer/Desktop section, hash targets and mobile Pricing menu | /landing alias SC; carousel/FAQ source reviewed, not every position clicked |
| Pricing | Empty/unavailable and recovery affordance | Loading/10-second abort, populated quote cards, monthly/yearly and disabled/available CTA SC; accepted payment/pricing tests not repeated |
| Login | Initial, missing configuration, legal notice, failed credentials | Authenticated redirect, Google start/failure branches SC; real login/OAuth UV |
| Signup | Initial/legal notice | Required fields/minLength/consent, submission error, duplicate-submit guard, verification modal, already-authenticated redirect SC; no signup/email sent |
| Email confirmation | Missing/unsupported, expired email and simulated service failure | Verified success/continue/bootstrap retry SC; no real token exchange |
| Password recovery | Request dialog, invalid/missing-link dialog | Sent/resend, new-password validation, uncertain update, cleanup/retry and success SC; actual verified recovery/provider delivery UV |
| Callback | Missing session, error query, held lookup | Safe-next success and consent-persistence retry SC; no real code exchange |
| Browser desktop-login | Missing/invalid handoff state | Valid handoff/protocol launch UV; actual Electron screens excluded |
| Guard/session | Anonymous redirect, held lookup, backend error, bootstrap failure | Expiry/cross-account cleanup source reviewed; real token refresh/expiry UV |
| Dashboard | Empty sessions/resume and setup recovery | Nonempty overview/counters/readiness branches SC; no real account |
| Onboarding | First step and onboarding GET failure | Steps 2–5, file/job-context/session actions, skip/completion SC; no remote mutations |
| Resume/profile | Empty, backend error, ready record, native confirm dismissed | File validation/upload/replacement/manual review/extract/index/retry/concurrency SC; no actual upload/index/deletion |
| Session list | Empty/failure/one synthetic ended record | Search/filter/sort/pagination and menu branches source reviewed; not every menu clicked |
| Transcript | Missing/unavailable record with Retry and download controls in branded viewer | Successful/empty content, download failure, deletion eligibility and custom confirmation SC; no download/delete |
| AI Notes | Missing/unavailable with Retry in branded viewer | Empty/saved/generating/error/retry SC; no actual AI generation |
| Ask AI | Failed history with Retry/input/send controls | Empty/history/suggestions/send failure/clear-view/duplicate guards SC; no AI calls |
| Call details | Tab/fields source reviewed | Not separately screenshotted; complete rendered metadata UV |
| Settings/account/profile | Account setup tool and resume profile flow inventoried | No independent website settings/profile route; Electron profile setup excluded |
| Checkout | Anonymous/unavailable, valid prepared/pending/uncertain/confirmed/expired fixtures, failed refresh and 12s timeout | Terms change, dismiss/provider failure and cancellation notices SC; no provider script opened and no payment acceptance repeated |
| Return/account refresh | Operation restoration/status and synthetic failed account read | Successful paid refresh remains historical accepted evidence, not repeated |
| Logout | Direct completion and rejected sign-out | Other guarded logout controls SC, not all labeled broken |
| Unsubscribe | Missing/success/error/pending, scrub then reload | External email/provider one-click flow UV; intercepted POST only |
| Unknown/direct/refresh | Unknown/legal URLs, direct Go back, unsubscribe reload | Other deep entries loaded through Vite; public CDN refresh handling UV |
| App rendering failure | Forced component exception, desktop/mobile | Exact production error text/stack behavior UV |
| Missing JavaScript | Blocked entry script after HTML | Production chunks/cache/service-worker behavior UV |
| Offline/network/timeouts | Local 503, held calls, blocked JS and actual checkout timeout | Browser-owned offline/DNS/TLS UI not observed or controlled by React before HTML loads |
| Native dialogs/validation | Resume-delete confirm event dismissed, underlying page captured | Native dialog chrome not screenshot-verified; replace/re-extract SC. Normal browser required-field bubbles are not automatically unbranded defects |
| Hosting/proxy (B) | Blocked/unverified | No deployment/config access; local Vite behavior is not a production response audit |
| Third parties (D) | Not exercised | Razorpay/bank/OTP/Google interfaces not app-controlled; no provider contact |
| Admin/Electron | Excluded | No internal admin state or Electron screen audited/changed |

No raw customer JSON or actual production stack/PII disclosure was observed. Synthetic error strings and deliberate render-fault stacks establish handling paths only. Transcript/notes/Ask AI errors remained inside the branded viewer with retries: [transcript mobile](../tmp/website-flow-audit/transcript-missing-mobile.png), [notes desktop](../tmp/website-flow-audit/notes-missing-desktop.png). These are useful existing design references, not duplicate generic-page findings.

## Evidence index, preservation and cleanup

- `tmp/website-flow-audit/observations.json`: 35 initial scenarios × two widths; DOM titles/text/links/errors and synthetic request paths.
- `extended-observations.json`: 19 more × two widths; deliberate render/script faults, valid-contract checkout states and native dialog records.
- `corrected-observations.json`: successful signup/legal and login/error observations after selector corrections.
- `recovery-probes.json`: unsubscribe reload, direct Go back, inert landing-control semantics and mobile menu behavior.
- `audit-manifest.json`: methods, viewport sizes, limitations and invalid-fixture exclusions. Screenshot stems have desktop/mobile counterparts. No screenshots of real customer accounts/providers were taken.
- `preserved-journals.json`: five historical payment/email/callback journals retain their recorded hashes; no old acceptance counts or baseline evidence were reset.
- Browser contexts closed. Task-owned Vite listener on **127.0.0.1:5299 stopped**, with no listener afterward. No database was created. Existing normal services were not stopped. No source/package/auth/DNS/SMTP settings changed. Only this report and local inspection evidence were created.

## Recommended order and missing inputs

1. P1 recovery foundations: root render/startup fallback, safe technical-message mapping and visible onboarding failure recovery, using approved patterns.
2. P1 dead ends: direct logout and unsubscribe retry; legal/download navigation. Preserve auth privacy, billing idempotency and uncertain-payment behavior.
3. P2 consistency: shared AuthShell, 404, base metadata, pending labels/statuses, native resume confirmations and onboarding copy. Review checkout branding separately.
4. Later implementation inputs: approved legal documents; actual released installer URLs/OS availability; approved documentation/help/security destinations and monitored contact if desired; approved marketing/legal wording. No additional input was needed to finish this inspection.

Public hosting inspection needs an explicitly supplied deployment/configuration scope. Browser-owned and third-party screens cannot be redesigned by application code. **No redesign is implemented and no C11/C12/C13 acceptance is marked complete by this report.**

### Subsequent remediation reference

28 October 2026 (IST): Batch 1 local implementation and verification for F04/F05/F06/F07/F10/F11 is recorded in [WEBSITE_FALLBACK_BATCH_1_IMPLEMENTATION.md](WEBSITE_FALLBACK_BATCH_1_IMPLEMENTATION.md). The original observations and evidence above remain historical; this reference does not rewrite their triggers or claim the remaining batches or public hosting passed.

28 October 2026 (IST): Batch 2 branded progress and stalled-request recovery for F08/F09/F17/F18 is recorded in [WEBSITE_FALLBACK_BATCH_2_IMPLEMENTATION.md](WEBSITE_FALLBACK_BATCH_2_IMPLEMENTATION.md). This is local synthetic verification only; the original findings remain historical and other website/provider/release acceptance is not marked complete.

28 October 2026 (IST): Batch 3 website branding, remaining customer secure-link fallbacks, resume confirmations and onboarding claim correction for F01/F02/F03/F15/F16 are recorded in [WEBSITE_FALLBACK_BATCH_3_IMPLEMENTATION.md](WEBSITE_FALLBACK_BATCH_3_IMPLEMENTATION.md). Original observations above are preserved. F12/F13/F14, hosting limitations and separate design judgments remain open; this is not provider, installed-app or release acceptance.
