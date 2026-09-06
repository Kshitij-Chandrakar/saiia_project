# C6.1 - Desktop Startup UI / Session Setup Flow Audit and Plan

Date: 2026-08-12

Scope: audit/design only. No desktop startup UI runtime code, resume selection UI, job target/JD creation UI, backend route, Supabase migration, C4.4 generation integration, cloud/local migration, billing, or admin feature was implemented.

## Current-State Findings

Files and surfaces reviewed:

- `frontend/electron/desktop_auth_session.cjs`
- `frontend/electron/preload.cjs`
- `frontend/electron/main.cjs`
- `frontend/src/components/MainDiagnosticsWindow.jsx`
- `frontend/src/desktop_auth_ui.js`
- `backend/app/api/resumes.py`
- `backend/app/api/job_contexts.py`
- `docs/C5_DESKTOP_AUTH_CLOUD_IDENTITY_PLAN.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`

Observed current behavior:

- Electron main process owns desktop auth/session state and cloud startup context loading.
- Preload exposes narrow safe APIs only: `getAuthState`, `startAuthLogin`, `logoutAuth`, `getCloudStartupContext`, and `refreshCloudStartupContext`, plus existing local screen/overlay APIs.
- Renderer receives safe auth/cloud summaries only; it does not receive access tokens, refresh tokens, service-role keys, raw sessions, or generic cloud fetch.
- C5.4 startup context already returns safe `auth` and `cloud` summary state.
- C5.4 derives resume readiness from `GET /api/resumes/current`.
- C5.4 derives job-target readiness from preview-only `GET /api/job-contexts?limit=50`.
- Current desktop UI is still the runtime diagnostics/control panel. It contains local controls such as setup profile, recording, screen analysis, and the small C5.3/C5.4 cloud auth/readiness card.
- Signed-out and cloud-unavailable states preserve local desktop behavior.
- No startup wizard, session setup shell, resume picker, job target picker, JD create flow, or answer-model/audio/preference setup UI exists yet.

## Existing Startup Context Contract

C6.2 should start from the C5.4 safe context shape:

```json
{
  "auth": {
    "status": "signed-out | signing-in | connected | token-expired | offline | backend-unavailable | bootstrap-failed",
    "user_id": "safe user id or null",
    "email": "safe email or null",
    "error": "safe message or empty",
    "safeStorageAvailable": true
  },
  "cloud": {
    "available": true,
    "mode": "cloud | local-only | unavailable",
    "profileReady": true,
    "resumeReady": true,
    "jobContextReady": true,
    "lastError": "safe message or empty"
  }
}
```

Potential safe additions for later C6.2/C6.3:

- `resume`: safe summary only, such as `id`, `status`, `is_active`, and display label.
- `jobContext`: safe active summary only, such as `id`, `company`, `position`, and `is_active`; no full raw JD in startup summary.
- `sessionDefaults`: safe local defaults for answer model, language, audio source, and answer preferences if already locally configured.
- `canStartCloudSession`: boolean derived in main process or renderer from safe state.
- `canStartLocalSession`: boolean that remains true when local prerequisites are met.

Do not add tokens, raw Supabase sessions, service-role data, Authorization headers, full resume text, or full job descriptions to this contract.

## Startup Flow

### Signed Out

- Show intervuAI product header and a concise cloud status: signed out.
- Offer Login and Continue local-only.
- Show resume/job target cards as cloud unavailable/not selected, without blocking local-only mode.
- Start session may be allowed in local-only mode using existing local profile/job-context behavior, subject to existing local prerequisites.

### Signing In

- Show "Checking cloud" / "Complete login in your browser."
- Disable duplicate login actions.
- Keep local-only option available unless an auth operation must temporarily own focus.
- Do not show "Cloud unavailable" while signing in.

### Connected + Cloud Ready

- Show connected email.
- Show resume ready and job target ready.
- Enable cloud session start once required C6 session prerequisites are met.
- Also keep local-only explicit if product wants a deliberate offline-style run.

### Connected + Resume Missing

- Show connected email and "Resume not ready."
- Offer a future C6.3 action to select/upload/confirm a resume.
- Keep local-only available.
- Cloud session start should be blocked only if C6 requires cloud resume context for that mode.

### Connected + Job Target Missing

- Show connected email and "Job target not ready."
- Offer a future C6.3 action to select/create a job target or paste/upload JD.
- Keep no-job-context as a valid state for local/no-context operation.
- Do not block all session starts merely because job context is missing; block only cloud-personalized mode if the selected mode requires it.

### Token Expired

- Show "Session expired. Log in again."
- Clear stale user display.
- Offer Login and Continue local-only.
- Do not expose previous-user resume/job target information.

### Backend Unavailable

- Show "Cloud temporarily unavailable."
- Do not force logout.
- Preserve local-only path.
- If safe cached cloud summaries exist, label them as stale/last-known only in a later implementation; do not silently treat them as fresh.

### Offline

- Show offline/local-only mode.
- Do not force logout for transient network failures.
- Allow local-only session if local prerequisites are satisfied.
- Offer Refresh cloud status.

### Bootstrap Failed

- Show "Profile setup could not be completed."
- Offer Refresh status and Logout.
- Keep local-only available.
- Do not proceed with cloud session start until bootstrap recovers.

### User Chooses Local-Only Mode

- Make the choice explicit.
- Use existing local desktop behavior and local/no-context fallback.
- Do not mix stale cloud resume/job target data into local-only session.
- The UI should make clear cloud history/sync may not be available for that session until later phases define sync.

## Minimal Startup Screen Structure

C6.2 should build a small startup shell, not a dashboard:

- Header: intervuAI name, short current mode/status.
- Cloud account status card: signed out/signing in/connected/token expired/offline/backend unavailable/bootstrap failed.
- Resume readiness card: ready, missing, unavailable, or local-only.
- Job target / JD readiness card: ready, missing, unavailable, or no-context allowed.
- Local-only option: explicit action or mode toggle.
- Basic session options: only if already available locally and needed to start safely; defer complex preference editing.
- Start session button: disabled only when the selected mode lacks required prerequisites.
- Safe recovery messages: login, refresh, logout, continue local-only.

Avoid a large account dashboard, billing panel, session history view, or resume/JD editor in C6.2.

## Proposed C6 Subphases

### C6.1 - Audit and Plan

- Create this plan.
- Update roadmap/tracker.
- No runtime code.

### C6.2 - Basic Startup Shell UI

- Add a startup/session setup shell in the Electron renderer using existing C5.4 context.
- Use only safe preload APIs.
- Show auth/cloud readiness, local-only option, and basic Start Session path.
- Do not implement resume/job target selection or creation yet.
- Add renderer/helper tests for state rendering, accessibility labels, and no token leakage.

### C6.3 - Resume and Job Target Selection / Lightweight Create Flow

- Add safe selection of existing active/available cloud resume and job target using existing backend capabilities where possible.
- Add job target/JD lightweight create/update only if the required safe main-process/backend adapter is available or explicitly approved.
- Keep raw JD out of list/startup summaries.
- Preserve no-job-context as valid.

### C6.4 - Validation, Fallback, Stale-State Tests, and Polish

- Harden logout/user-switch stale-state behavior in the startup shell.
- Validate local-only and offline paths.
- Add keyboard navigation, aria-live updates, loading/error states, and retry behavior.
- Verify no C4.4 generation integration has slipped in unless explicitly started later.

## Security and Privacy Requirements

- Renderer must use only safe preload APIs; no direct Supabase access from renderer.
- Do not expose `access_token`, `refresh_token`, service-role key, Authorization header, raw session, or full JWT claims to React state or UI.
- Do not expose full resume text or full raw job description in startup context.
- No generic cloud fetch should be added to preload.
- Electron IPC handlers must remain narrow and validated in main process.
- Previous-user resume/job target summaries must clear after logout, token expiry, and user switch.
- Offline/backend-unavailable states must not force logout.
- Local-only mode must remain available and must not silently mix stale cloud context.

## UX Requirements

- Status messages should tell the user what to do next.
- Signing-in must not display "Cloud unavailable."
- Start session should be blocked only when the selected mode lacks required prerequisites.
- Local-only should be visible, understandable, and safe.
- Loading, refresh, login, logout, and error states should be explicit.
- Keyboard navigation must reach all startup actions.
- Use readable labels and `aria-live="polite"` for changing status messages.
- Avoid nested cards and dense dashboard composition; this screen is a pre-session setup, not account management.

## Required Tests for Later Implementation

- Signed-out startup renders login and local-only actions.
- Signing-in renders "Checking cloud" and disables duplicate login.
- Connected/cloud-ready enables cloud start when session prerequisites are satisfied.
- Connected/missing resume shows recovery action and preserves local-only.
- Connected/missing job target shows recovery action and preserves no-context/local-only path.
- Token-expired clears stale user/resume/job target display.
- Backend unavailable/offline do not force logout and keep local-only available.
- Bootstrap failed offers refresh/logout and blocks cloud start.
- Logout and user switch clear previous-user startup data.
- Renderer uses only preload APIs and never imports Supabase client.
- Startup UI and preload tests must prove that token, session, and Authorization header values are not exposed. Token-shaped fixture keys and sentinel values are allowed in negative tests.
- Keyboard and aria-live behavior are covered.

## C6.2A implementation record

As of 2026-09-06, the first signed-out/token-expired desktop startup login screen is implemented against the Figma `Login - Version B` frame at node `78:451` in file `AjlJbD9X8xHbGUtRcUdXrf`.

- The existing `StartupLoginScreen` auth state, browser-login action, polling, error/retry, close action, and narrow preload boundary were preserved.
- The local exported assets are `login-mascot.png`, `login-logo.svg`, `login-arrow.svg`, `login-security.svg`, `login-close.svg`, `login-bg-ellipse-left.svg`, `login-bg-ellipse-right.svg`, `login-bg-group-left.svg`, and `login-bg-group-right.svg` under `frontend/src/assets/startup-login/`.
- The login presentation uses the Figma `430 x 460` card, header/content spacing, typography, colors, button, security note, support link, and decorative layers. The existing waiting, session-choice, session-setup, runtime, diagnostics, and Electron IPC flows were not redesigned.
- The close control remains a semantic, keyboard-accessible button using the existing validated `startup:close` IPC path; its header stacking context was raised above the full-card main layer so the icon and padded button area are clickable without changing the Figma geometry.
- Focused startup tests, all frontend tests, and the Vite production build passed. A real Electron smoke check verified icon-area and padded-area mouse clicks plus focused `Enter` and `Space` activation close the startup window. Screenshot comparison, browser authentication, Windows display-scaling checks, and packaged-app verification remain manual follow-ups.

The same `StartupLoginScreen` now renders the pending browser-handoff state from Figma node `70:1051` in file `AjlJbD9X8xHbGUtRcUdXrf` as soon as the existing login operation enters `SIGNING_IN`/`loginPending`.

- The state uses the existing 430 x 460 shell and local shared mascot, logo, close, and decorative assets, plus the exact exported `login-open-browser.svg` asset under `frontend/src/assets/startup-login/`.
- The visible copy is `Opening Your Browser`, `We’re securely connecting you to Intervu AI Sign In.`, and `Your browser will open automatically.`; three 12px dots use scoped CSS-only 1.2-second staggered rise/color animation and become static under `prefers-reduced-motion`.
- The existing browser launch, polling, success transition, failure/retry behavior, close IPC, and renderer security boundary were preserved. The pending state does not launch authentication on mount or add a duplicate request path.
- Focused and all frontend tests plus the Vite build passed. Real Electron smoke verification covered screen 1 pointer transition into the pending state, pending-state text/dot computed styles, reduced-motion output, and close while pending. Browser authentication completion, screenshot comparison, Windows scaling, and packaged-app checks remain manual.

## C6.2B authenticated home/session-choice presentation record

As of 2026-09-06, the authenticated desktop home/Create state is corrected against the Figma `Main/Home State - Create / History` frame at node `60:816` in file `AjlJbD9X8xHbGUtRcUdXrf`.

- The target logical frame is `428 x 462` with a `428 x 65` header, `380px` content columns, `24px` content padding, `16px` card gap, and straight card action separators. The Electron startup home layout now uses those dimensions directly; it does not use CSS scaling or a global zoom change. Auth/session-setup remain on their existing `504 x 462` layout and runtime sizing is unchanged.
- Exact local Figma exports are used from `frontend/src/assets/startup-choice/`: `choice-brand.svg`, `choice-clock.svg`, `choice-menu.svg`, `choice-collapse.svg`, `choice-close.svg`, `choice-stars.svg`, `choice-history.svg`, `choice-free-stars.svg`, `choice-wallet.svg`, `choice-card-arrow.svg`, `choice-shield.svg`, and `choice-arrow.svg`. The shield uses the matching exported vector from the Figma asset bundle because the separately returned shield URL was unavailable.
- Existing authenticated gating, Create/Past Sessions handlers, Start Session transition, close behavior, and narrow preload boundary were preserved. No authoritative balance source is currently exposed to this screen, so unknown availability is rendered as `-- / -- min` and `Time availability unavailable` rather than the Figma example balance.
- Focused startup tests, all frontend tests (`210` passed), the Vite build, and Electron syntax checks passed. A real Electron smoke check at device scale `1.25` measured the rendered home root at `428 x 462` and verified local asset dimensions, single-line time layout, and straight separators. Pointer/keyboard close and pending-auth checks remain covered by the existing smoke path; browser authentication completion, screenshot-equivalence review, Windows 100%/125%/150% scaling, packaged-app behavior, and unavailable placeholder controls remain manual follow-ups.

## C6.2C authenticated Past Sessions presentation record

As of 2026-09-06, the authenticated desktop Past Sessions tab is implemented against the Figma `Past Sessions` frame at node `71:1207` in file `AjlJbD9X8xHbGUtRcUdXrf`.

- The history frame uses a `428 x 514` logical Electron layout with a `428 x 65` header, `24px` content padding, `380px` columns, `64px` session rows, `15px` row gaps, `40px` company avatars, and a `380 x 38` View All Sessions control. Create remains on the existing `428 x 462` layout; setup and runtime sizing are unchanged.
- Past rows come from the authenticated `/api/interview-sessions` route through the narrow Electron main/preload APIs with `limit=3`, `page=1`, and the server-side `ended,abandoned` status filter. The backend derives ownership from the verified JWT, orders by `started_at.desc,id.desc`, and the renderer applies safe missing-field fallbacks without loading transcripts, notes, resumes, or raw job descriptions.
- Exact Past-frame exports are used locally for the Past create sparkle, selected history icon, and View All arrow: `choice-past-stars.svg`, `choice-past-history.svg`, and `choice-past-view-all-arrow.svg` under `frontend/src/assets/startup-choice/`; the shared header/window assets are reused only where their exported bytes match.
- Loading, empty, retryable error, and token-expired recovery states are explicit. History requests are bounded and stale responses are ignored on unmount; View All Sessions reuses the existing trusted dashboard opener without putting credentials in the URL.
- Focused backend session, route, Electron manager, and startup source tests passed during implementation. Live authenticated history rendering, screenshot comparison, Windows 100%/125%/150% scaling, and packaged-app verification remain manual follow-ups.

## C6.2D authenticated home collapse-to-mascot presentation record

As of 2026-09-06, the authenticated desktop home window has a collapse-to-mascot presentation using the existing upper-arrow control.

- The transparent, frameless main BrowserWindow stays mounted so the Create/Past Sessions tab, account-scoped data, and authentication state are preserved. Main-process validated `startup:collapse` and `startup:restore` IPC own the transition; no second window, persistence, new hotkey, or generic IPC bridge was added.
- On collapse, the current expanded logical bounds and minimum size are saved once. The window moves to a clamped `144 x 144` mascot presentation near the prior upper-right position, with the existing transparent `frontend/src/assets/startup-login/login-mascot.png` rendered at `120 x 120` inside a tight no-drag, keyboard-accessible restore button. Restore returns the saved logical bounds and focus, clamping only if the display work area changed.
- Authenticated collapse is rejected unless the main-process auth state is connected. Auth reset/expiry sizing expands the compact window before showing the existing login recovery screen, so collapse does not preserve stale identity or trap the user in mascot mode.
- The dependency-free transition controller has focused saved-bounds/idempotence, display-clamping, and native-failure rollback tests. Live Electron mascot transparency, ten-cycle/rapid-click behavior, Windows scaling, multi-display recovery, and auth-expiry-while-collapsed checks remain manual follow-ups.

## C6.2E authenticated home account dropdown presentation record

As of 2026-09-06, the shared authenticated home header has an account dropdown opened by the existing three-dot control.

- The compact dark menu shows the safe authenticated email from the existing startup auth summary, plus Dashboard and Log out actions. Account text is informational only, long emails are safely truncated for layout with the full value available to assistive technology, and actions are disabled until the safe identity is ready.
- Dashboard reuses the existing validated `dashboard:open` main-process route derived from trusted configuration. It does not accept renderer URLs or append credentials; launch failures stay in the menu as a retryable safe message.
- Log out reuses the existing validated `auth:logout` lifecycle. The main process clears local credentials/session state and resets the startup flow; the renderer clears the account email and menu state without deleting cloud history or signing out unrelated browser devices.
- The menu is scoped to the home component, uses existing `lucide-react` account/dashboard/logout icons, supports outside-click/Escape/arrow-key navigation, has no-drag interaction regions, and closes on tab changes, collapse, logout, and identity changes. No new window, route, persistence, migration, or generic IPC bridge was added.
- Focused source and full frontend tests plus the production build passed. An authenticated live menu check requires a legitimate local sign-in; the available Electron session was signed out/token-expired, so Dashboard provider/account matching and real logout were not claimed as live-verified.

## Risks and Open Gaps

- C6.2A website-login desktop handoff currently uses a dev/local process-memory store. Production shared atomic TTL-backed handoff storage is deferred to C16.1 Production Auth Hardening and must block public production release until implemented.
- Current C5.4 context only exposes readiness booleans plus limited internal summaries; C6.3 may need a safe main-process adapter for selecting a specific resume/job target.
- Existing backend job-context detail can return raw JD to an owner, but startup summary must not use that route unless an edit flow explicitly needs it.
- Current roadmap C6 also covers durable interview session storage; startup UI should be the front door to that work, not a replacement for session persistence.
- Cloud sync/local migration remains undefined and must not be implied by C6.2.
- Answer generation still has no C4.4 active cloud context integration; startup UI must not claim cloud-personalized generation until that phase exists.

## Out of Scope for C6.1

- Startup UI runtime code.
- Resume selection UI.
- Job target/JD creation UI.
- Backend routes.
- Supabase migrations.
- C4.4 generation integration.
- Cloud/local data migration.
- Billing/admin features.
