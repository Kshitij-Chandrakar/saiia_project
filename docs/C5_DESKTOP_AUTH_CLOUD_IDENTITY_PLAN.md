# C5.1 - Desktop Authenticated Cloud Identity Audit and Plan

Date: 2026-08-09

Scope: C5.1 audit and plan only. No desktop authentication runtime, startup/session setup UI, backend route, Supabase migration, C4.4 generation integration, or C5 sync implementation was added.

## Verified Current State

Files reviewed:

- `frontend/electron/main.cjs`
- `frontend/electron/preload.cjs`
- `frontend/package.json`
- `frontend/src/App.jsx`
- `frontend/src/auth/AuthScreens.jsx`
- `frontend/src/auth/authApi.js`
- `frontend/src/auth/supabaseClient.js`
- `backend/app/main.py`
- `backend/app/auth/supabase_auth.py`
- `backend/app/api/auth.py`
- `backend/app/api/resumes.py`
- `backend/app/api/job_contexts.py`
- `docs/C2_AUTH_ARCHITECTURE_PLAN.md`
- `docs/C3_CLOUD_RESUME_PROFILE_PLAN.md`
- `docs/C4_CLOUD_JOB_CONTEXT_PLAN.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`

Observed architecture:

- The Electron app has one main process file, `frontend/electron/main.cjs`, and one preload file, `frontend/electron/preload.cjs`.
- Electron creates a main window and overlay window from the same React/Vite app.
- Electron windows use `contextIsolation: true` and `nodeIntegration: false`.
- The preload bridge exposes a narrow `electronAPI`/`saiia` surface for overlay state, toolbar actions, window capture, and screen capture.
- Current Electron IPC does not include auth, token storage, cloud API calls, or desktop user identity.
- The only current Electron disk persistence is overlay window state under `app.getPath('userData')`.
- Current website auth uses `@supabase/supabase-js` in `frontend/src/auth/supabaseClient.js` with `autoRefreshToken: true`, `detectSessionInUrl: true`, and `persistSession: true`.
- Current website auth pages call `supabase.auth.getSession()`, then pass the access token to backend helpers in `frontend/src/auth/authApi.js`.
- Backend cloud routes use `CurrentUserDep`, which verifies a Supabase bearer token in `backend/app/auth/supabase_auth.py`.
- Backend route ownership is derived from verified JWT identity, not client-submitted `user_id`.
- C3 cloud resume routes and C4.2 cloud job-context routes already follow the backend-only service-role access model.
- Local desktop routes and generation paths remain available without desktop cloud identity.

## Security Boundary

C5 must not put Supabase service-role keys, refresh tokens, or durable credentials in the renderer.

The desktop renderer may receive:

- safe user summary, such as `user_id`, `email`, and connection status
- non-secret setup state needed to render the startup/session setup UI
- short-lived operation results from backend calls

The desktop renderer must not receive:

- service-role key
- Supabase anon key if auth can be completed in the main process
- refresh token
- full JWT claims
- raw token diagnostics
- arbitrary backend request capability

The main process should own:

- desktop auth callback handling
- Supabase session refresh
- OS-protected token persistence
- logout/session clearing
- backend cloud API calls that require bearer tokens

## Recommended Desktop Login Flow

Use browser-based OAuth/PKCE or email-link auth with a custom protocol callback handled by Electron main process.

Planned flow:

1. Desktop startup shows signed-out state.
2. User chooses login.
3. Electron opens the system browser or a locked auth window to Supabase Auth.
4. Supabase redirects to a registered desktop callback such as `saiia://auth/callback`.
5. Electron main process handles the callback, validates state/nonce, exchanges the code for a Supabase session, and stores the session securely.
6. Main process calls `GET /api/auth/me` to verify the backend accepts the access token.
7. Main process calls `POST /api/auth/profile/bootstrap` if needed.
8. Renderer receives only a safe connected-state payload.

Why this path:

- It reuses Supabase Auth and existing backend JWT verification.
- It avoids asking users to copy tokens.
- It keeps refresh tokens out of the renderer.
- It does not require new backend login endpoints.

Fallback for development only:

- A temporary developer-only flow may be documented later if needed, but it must not normalize insecure token copy/paste as product behavior.

## Secure Token Storage

Use Electron main process plus OS-backed protection.

Preferred implementation:

- Store the Supabase session only from the main process.
- Encrypt the serialized session with Electron `safeStorage` where available.
- Write the encrypted blob under `app.getPath('userData')`.
- Keep the decrypted session in main-process memory only.
- On logout, delete the persisted encrypted session and clear in-memory state.

If `safeStorage` is unavailable:

- Do not persist refresh tokens silently.
- Fall back to session-only login and require login again after restart.
- Record the degraded state in UI without exposing token details.

Do not add a new native credential dependency in C5.1. If later product requirements need stronger cross-platform credential storage than `safeStorage`, evaluate `keytar` or OS credential APIs in a separate implementation step.

## IPC Boundaries

Add only narrow auth/session IPC in C5 implementation:

- `auth:get-state`
- `auth:start-login`
- `auth:logout`
- `cloud:get-startup-context`
- `cloud:refresh-startup-context`

IPC handlers must:

- validate arguments
- return safe DTOs only
- avoid exposing generic `fetch` or arbitrary URL calls
- avoid sending raw access or refresh tokens to renderer
- map expired-session errors to a signed-out/token-expired state
- avoid logging token values, raw resumes, or raw job descriptions

Keep existing screen/overlay IPC separate from auth IPC.

## Backend API Call Pattern

Desktop should call the existing FastAPI backend, not Supabase tables directly.

Main process call pattern:

1. Load or refresh Supabase session in main process.
2. Attach `Authorization: Bearer <access_token>` to backend cloud routes.
3. Use existing backend endpoints:
   - `GET /api/auth/me`
   - `POST /api/auth/profile/bootstrap`
   - C3 resume routes under `/api/resumes`
   - C4.2 job-context routes under `/api/job-contexts`
4. Treat `401` as expired/signed-out and trigger reauth.
5. Treat `503` cloud config failures as backend unavailable/cloud not configured.
6. Do not call Supabase REST/storage directly from the renderer.

## Session Refresh and Logout

Main process should refresh before cloud calls when the access token is expired or near expiry.

Rules:

- Refresh token stays in main process storage/memory.
- Only one refresh should run at a time.
- Failed refresh clears the session and returns token-expired state.
- Logout must call Supabase sign-out where possible, then clear local secure storage.
- App restart should restore only if secure persisted session exists and can be refreshed.
- Offline startup with a saved session should show offline/last-known-safe state, not pretend cloud sync succeeded.

## Offline, No-Auth, and Local Behavior

No auth remains a supported state.

Before desktop cloud identity exists or when the user is signed out:

- Existing local desktop profile/JD/generation behavior remains available.
- Local `/api/job-context` remains the desktop-local P3 route.
- Local generation must not silently mix cloud resume or cloud job context.
- Cloud-only actions should show signed-out/offline states.

After desktop cloud identity exists:

- Server remains the source of truth for cloud resume, job target, and settings.
- Local fallback remains explicit until a later migration step deliberately transfers ownership.
- No cloud/local merge should happen without a specific migration plan.

## Future Startup/Session Setup UI

Do not build this in C5.1.

Later desktop startup/session setup should let the user choose:

- active cloud resume
- active cloud job target/JD
- lightweight job target/JD create or update from company, position, and pasted/uploaded JD
- answer model
- language
- audio source
- answer preferences

This UI depends on desktop authenticated cloud identity and belongs during or after C5 implementation.

## Threat Model

Primary risks:

- Refresh token exposure in renderer or logs.
- Service-role key leakage into frontend/Electron.
- Renderer gaining arbitrary authenticated backend request capability.
- Cross-user cloud data access from stale or swapped sessions.
- Expired-session behavior falling back to the wrong user or mixing local/cloud context.
- Raw resume/JD content appearing in diagnostics.

Controls:

- Main-process-owned session.
- OS-protected token persistence.
- Narrow preload IPC.
- Existing backend `CurrentUserDep` verification for every cloud route.
- Backend-only service-role access to Supabase.
- Safe DTOs for renderer.
- Explicit signed-out/offline/no-context states.

## C5.2 Proposed Scope

C5.2 should implement the smallest desktop cloud identity slice:

- main-process auth session manager
- secure session persistence with `safeStorage`
- custom protocol callback registration and state/nonce validation
- login/logout IPC
- backend `/api/auth/me` verification from main process
- safe connected/signed-out/token-expired renderer state
- tests for token non-exposure, logout clearing, expired-session mapping, and IPC argument validation

Out of scope for C5.2 unless explicitly approved:

- startup/session setup UI
- cloud/local data migration
- C4.4 generation integration
- direct renderer Supabase data access
- billing/account UI

## Required Tests

- Electron main session manager stores refresh token only in encrypted main-process storage.
- Preload does not expose raw tokens or generic cloud fetch.
- Login callback rejects missing or mismatched state.
- Backend verification calls include bearer access token.
- `401` maps to signed-out/token-expired state and clears invalid session.
- Logout clears Supabase session and local encrypted session file.
- Renderer receives safe user summary only.
- Offline startup preserves local mode and does not claim cloud sync success.
- No-auth desktop can still use existing local/no-context behavior.

## Open Questions

- Confirm final Supabase redirect URL and custom protocol registration for packaged builds.
- Decide whether login opens system browser or an Electron auth window.
- Decide whether to persist sessions on machines where `safeStorage` is unavailable.
- Decide when local profile/JD data should be migrated or left local.
