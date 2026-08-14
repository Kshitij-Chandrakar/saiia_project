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
