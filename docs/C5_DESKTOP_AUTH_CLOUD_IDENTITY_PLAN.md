# C5.1 - Desktop Authenticated Cloud Identity Audit and Plan

Date: 2026-08-09

Scope: C5.1 audit and plan only. No desktop authentication runtime, startup/session setup UI, backend route, Supabase migration, C4.4 generation integration, or C5 sync implementation was added.

## Implementation Status Addendum

This document remains the historical C5.1 audit/design plan and source of design intent. Later implementation status is:

- C5.1: audit/design plan completed.
- C5.2: desktop authenticated cloud identity implemented locally.
- C5.3: desktop auth status/login/logout UI implemented locally.
- C5.4: desktop cloud startup context plumbing implemented locally.

Still not implemented:

- Startup setup UI; this belongs to later C6.
- Resume/job target selection UI; this belongs to later C6.
- C4.4 generation integration.

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

Use Supabase Auth PKCE with custom protocol callback `saiia://auth/callback`, handled by the Electron main process. Do not mix this with Supabase OAuth integration documentation; C5.2 owns a Supabase Auth PKCE flow only.

Planned flow:

1. Desktop startup shows signed-out state.
2. User chooses login.
3. Electron main process starts Supabase Auth PKCE.
4. Main process increments/replaces the active login attempt generation.
5. Main process generates a PKCE `code_verifier`, derived `code_challenge`, `state`/nonce, exact `redirect_uri`, and expiry.
6. `code_challenge_method` must be `S256`.
7. Main process stores `code_verifier`, `code_challenge`, `state`/nonce, `redirect_uri`, expiry, and attempt generation together in one main-process pending-login record.
8. Electron opens the system browser or a locked auth window to Supabase Auth.
9. Supabase redirects to the registered desktop callback `saiia://auth/callback`.
10. Callback `redirect_uri` must exactly match the `redirect_uri` used when starting auth.
11. Electron main process handles the callback and requires the expected `code` and `state`.
12. Main process validates callback values against the pending-login record before exchange.
13. The pending-login record is atomically consumed before exchanging the code.
14. Main process exchanges the callback code with the original retained `code_verifier` from the consumed record.
15. After token exchange completes, before installing or persisting the session, main process re-checks that the consumed attempt generation is still the active generation.
16. If the generation no longer matches, main process discards the exchanged session and does not persist or cache it.
17. Only the latest active login attempt may commit a session.
18. Reused callbacks fail because the pending-login record has already been consumed.
19. Reused, expired, missing, or mismatched callback values are rejected before session exchange.
20. Main process stores the session securely.
21. Main process calls `GET /api/auth/me` to verify the backend accepts the access token.
22. Main process always calls `POST /api/auth/profile/bootstrap` after `GET /api/auth/me` succeeds.
23. Renderer receives only a safe connected-state payload.

Authorization-denial callback:

- If the callback has `error` and `state` but no `code`, such as `access_denied`, main process validates `state` against the pending-login record.
- When the denial state matches, main process atomically consumes the pending-login record.
- The renderer receives a cancellation/authentication-failure state.
- Token exchange is not attempted for denial callbacks.

Concurrent login behavior:

- Allow only one pending login at a time.
- A second `auth:start-login` attempt must atomically cancel/invalidate the previous pending-login record before creating a new one.
- Starting a new login increments/replaces the active attempt generation.
- Only the latest pending-login record is valid.
- If a callback from the old login arrives later, reject it because its state does not match the active pending-login record.
- Callbacks must consume only the active matching state.
- A consumed older attempt must still re-check attempt generation after exchange and before session commit.
- This overlapping login behavior must be deterministic when callbacks arrive out of order.

Why this path:

- It reuses Supabase Auth and existing backend JWT verification.
- It avoids asking users to copy tokens.
- It keeps refresh tokens out of the renderer.
- It does not require new backend login endpoints.
- Email-link or `token_hash` auth is not part of C5.2 unless approved later.

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

- Fall back to session-only login and require login again after restart.
- Do not write a plaintext session file.
- Do not write a plaintext refresh-token file.
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

- validate the sender is the expected `BrowserWindow`
- validate `event.senderFrame` exists and is not destroyed/missing
- validate the sender origin for the allowed dev Vite URL
- validate the sender origin and path for packaged `loadFile` mode
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
4. After `GET /api/auth/me` succeeds, always call `POST /api/auth/profile/bootstrap`.
5. Do not use local cache to skip profile bootstrap.
6. Profile bootstrap idempotently ensures `profiles` and `user_settings` rows exist.
7. If conditional bootstrap skipping is ever allowed later, it must come from an explicit server response, not a local cache assumption.
8. Treat `401` as expired/signed-out and trigger reauth.
9. Treat `503` cloud config failures as backend unavailable/cloud not configured.
10. Treat `502` from `POST /api/auth/profile/bootstrap` as a dedicated profile-bootstrap failure state.
11. Do not treat profile-bootstrap `502` as an invalid session.
12. Do not call Supabase REST/storage directly from the renderer.

## Session Refresh and Logout

Main process should refresh before cloud calls when the access token is expired or near expiry.

Rules:

- Refresh token stays in main process storage/memory.
- Only one refresh should run at a time.
- Transient network or `503` refresh failure preserves encrypted credentials, preserves cached cloud data, and returns offline/backend-unavailable state.
- Invalid or expired refresh token clears encrypted credentials, clears in-memory session state, clears cached profile/settings/startup/resume/job-context data, and exposes signed-out/token-expired state.
- `401` invalid/expired session, `502` profile-bootstrap failure, and `503` backend/cloud unavailable must be distinct states.
- Logout must attempt Supabase sign-out where possible.
- Logout must always run local cleanup in a finally-style path, even if remote Supabase sign-out fails due to network or service error.
- Local cleanup deletes encrypted session storage and clears in-memory session state.
- Local cleanup also clears cached profile, settings, startup context, resume context, and cloud job context.
- User switch must clear the previous user's cached cloud data before exposing the new connected state.
- Restart after logout must not expose old cached cloud data.
- App restart should restore only if secure persisted session exists and can be refreshed.
- Offline startup with a saved session should show offline/last-known-safe state, not pretend cloud sync succeeded.

Cloud request/cache-write rules:

- Every cloud request must be tagged with the current session generation and `user_id`.
- At request start, capture `session_generation` and `user_id`.
- Response handling must use only those captured values, not mutable current values.
- Logout increments or invalidates the session generation before cleanup.
- User switch increments or invalidates the session generation before exposing new user state.
- Cloud responses may update cache only if their session generation and `user_id` still match current state.
- Generation/user validation and cache write must happen as one serialized/atomic operation with logout cleanup and user-switch cleanup.
- If logout or user switch happens between validation and attempted write, the write must be rejected.
- Stale delayed responses after logout or user switch must be discarded.
- Active requests may also be cancelled, but cache writes must still validate session generation and `user_id`.

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
- When `safeStorage` is unavailable, session-only login does not persist a session or refresh token to disk.
- Preload does not expose raw tokens or generic cloud fetch.
- Login callback rejects missing state.
- Login callback rejects missing code only when no valid authorization error is present.
- Login callback accepts `error` plus matching state plus no code as the authorization-denial/cancellation path.
- Login callback rejects mismatched state/nonce.
- Login callback rejects expired state.
- Login callback rejects reused callback/state.
- Login callback validates only the active pending-login record.
- Overlapping login attempts where callbacks arrive out of order reject the old callback and accept only the latest active state.
- Login A consumes its record, login B starts before A exchange completes, A exchange completes later, A session is discarded, and only B can commit if B callback succeeds.
- Authorization-denial callback with `access_denied` consumes the matching pending-login record and skips token exchange.
- Session exchange is not attempted after an invalid callback.
- Request/exchange layer requires `code_challenge_method` to be `S256`.
- Request/exchange layer rejects code_challenge_method mismatch.
- Request/exchange layer uses the exact stored `redirect_uri`.
- Request/exchange layer uses the original stored `code_verifier` during exchange.
- Request/exchange layer rejects verifier mismatch.
- Auth/cloud IPC rejects unexpected `BrowserWindow`.
- Auth/cloud IPC rejects unexpected frame.
- Auth/cloud IPC rejects unexpected origin.
- Auth/cloud IPC rejects destroyed or missing `senderFrame`.
- Backend verification calls include bearer access token.
- `401` maps to signed-out/token-expired state and clears invalid session.
- `502` from profile bootstrap enters profile-bootstrap failure state, not invalid-session state.
- Transient refresh failure preserves secure session and cached cloud data.
- Invalid refresh failure clears credentials and cached cloud data.
- Delayed cloud response after logout cannot repopulate cache.
- Delayed cloud response from previous user cannot overwrite cache after user switch.
- Interleaving where logout or user switch happens between cache validation and write is rejected.
- Valid current-user response can still update cache.
- Logout clears Supabase session, local encrypted session file, and cached cloud startup/profile/settings/context data.
- Failed remote Supabase sign-out still clears local credentials and cached user data.
- Previous user data is unavailable after logout.
- Previous user data is unavailable after app restart.
- Previous user data is unavailable after login as another user.
- Renderer receives safe user summary only.
- Offline startup preserves local mode and does not claim cloud sync success.
- No-auth desktop can still use existing local/no-context behavior.

## Open Questions

- Confirm final Supabase redirect URL and custom protocol registration for packaged builds.
- Decide whether login opens system browser or an Electron auth window.
- Decide when local profile/JD data should be migrated or left local.
