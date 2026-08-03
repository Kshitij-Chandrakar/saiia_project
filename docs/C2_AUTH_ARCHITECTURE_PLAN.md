# C2 Authentication Architecture Plan

SAIIA C2 starts from the completed C1 cloud foundation. This document records
the C2.1 audit and the safe implementation boundary for authentication and
account lifecycle. C2.2 adds the first temporary auth screens inside the
existing React/Vite app plus a safe current-user backend endpoint. C2.3 adds
authenticated profile bootstrap. C2.4 adds a temporary protected auth shell and
session/account state handling. C2.5 closes the auth surface as a checkpoint
before C3. It does not start desktop login, cloud resume upload, sessions,
billing, usage, email-provider work, payments, or final website UI.

## C2.1 Audit Findings

Frontend structure:

- The current frontend is one React/Vite app under `frontend/`.
- The main browser entry point is `frontend/src/main.jsx`.
- `BrowserRouter` is already installed and wraps `<App />`.
- The current route surface in `frontend/src/App.jsx` is `/` and
  `/profile-setup`.
- There is no separate website/dashboard frontend in the repository today.
- The current frontend is also the Electron renderer used by the desktop app.
- `frontend/package.json` already includes `react-router-dom`.
- `@supabase/supabase-js` is installed for C2.2 browser auth.
- C2.2 adds `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` placeholders for
  frontend-safe Supabase Auth only.
- The renderer currently hardcodes `BACKEND_URL = 'http://localhost:8000'`.

Backend structure:

- The FastAPI app entry point is `backend/app/main.py`.
- Current routers are transcribe, auto STT, classify, generate, resume, system
  audio, job context, question detect, screen OCR, and debug when enabled.
- C1.4 auth verification lives in `backend/app/auth/supabase_auth.py`.
- `get_current_user()` reads `Authorization: Bearer <token>`, verifies the
  Supabase JWT, and returns `CurrentUser`.
- No existing desktop-local route is protected by `get_current_user()` yet.
- C2.2 adds `GET /api/auth/me` and no other backend auth route.

Profile and local storage:

- Local backend profile storage is `backend/candidate_profile.json`.
- `POST /api/profile` writes the local profile JSON and rebuilds the local
  resume index.
- `GET /api/profile` returns the local profile JSON.
- The profile setup HTML lives at `backend/app/templates/profile_setup.html`.
- The React `ProfileSetupForm` also writes a simplified `candidateProfile`
  value to browser `localStorage`.
- Local resume index storage is `tmp/resume_index.json`.
- Local job-context storage is `tmp/job_context.json`.

Cloud schema from C1:

- `profiles` has one row per Supabase Auth user via unique `user_id`.
- `profiles.summary` maps best to current `professional_summary` / `resume`.
- `profiles.headline` maps best to current `current_title` / `target_role` /
  `role`.
- `profiles.skills`, `technical_skills`, `soft_skills`, `education`,
  `experience`, `projects`, `achievements`, `certifications`, and
  `tools_frameworks` are JSONB arrays.
- `user_settings` has one row per user.
- `job_contexts` allows one active job context per user.
- `resumes` and `resume_chunks` are reserved for C3 resume cloud upload and RAG
  migration, not C2.1.

Environment and secrets:

- `.env.example` contains backend-only Supabase placeholders:
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG`, `SUPABASE_RESUME_BUCKET`, and
  `SUPABASE_EXPORT_BUCKET`.
- `.env` and `.env.*` are ignored by Git.
- `SUPABASE_SERVICE_ROLE_KEY` must remain backend-only and must never appear in
  React, Electron renderer, preload APIs, browser extension code, logs, API
  responses, frontend bundles, or public docs with a real value.
- Future frontend auth may use only Supabase URL and anon/publishable key.
- C2.2 frontend auth uses only `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY`. Backend-only `SUPABASE_SERVICE_ROLE_KEY` and
  `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG` remain outside the Vite bundle.
- The React/Vite frontend may use only `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY`; it must never use `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG`, smoke-test credentials, passwords, or
  raw bearer tokens as configuration.
- The backend auth verifier uses `SUPABASE_URL` and
  `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG`; JWKS URL configuration must use HTTPS.
  `SUPABASE_SERVICE_ROLE_KEY` stays backend-only for approved server-side
  Supabase REST work and is not a JWT verification secret.

Design boundary:

- External UI/UX designer owns final website Figma screens.
- C2 implementation can add functional auth screens when explicitly approved,
  but should avoid broad visual redesign before Figma handoff.
- Existing desktop audio, screen, overlay, provider routing, local resume RAG,
  and job-context behavior must remain unchanged until their phases.

## Recommended C2 Architecture

Use Supabase Auth as the account authority. The browser/dashboard client should
authenticate with Supabase using `@supabase/supabase-js` once C2.2 is approved.
The client receives a Supabase access token and sends it to backend cloud routes
as:

```text
Authorization: Bearer <access_token>
```

The backend must verify the token with the existing C1.4 `get_current_user()`
dependency. Backend routes must use `current_user.user_id`; they must not trust
any `user_id` supplied by the frontend.

Recommended browser token storage:

- Prefer Supabase JS default session management for the initial Vite browser
  auth flow.
- Keep service-role access out of the frontend.
- Do not store passwords, refresh tokens, reset tokens, or verification tokens
  in app logs.
- Reassess cookie-based server session hardening later if SAIIA gains a
  separate production web backend/domain.

Recommended backend endpoints for C2:

- `GET /api/auth/me`: protected by `get_current_user()`, returns safe identity
  only: `user_id`, optional `email`, optional `role`.
- `POST /api/auth/profile/bootstrap`: added in C2.3. It is protected by
  `get_current_user()` and creates missing `profiles` and `user_settings` rows
  for `current_user.user_id`.
- Do not add backend password login unless there is a specific need. Supabase
  client flows can handle signup/login/logout/session refresh/reset flows.
- Do not add C3 resume upload behavior in profile bootstrap.

Recommended profile bootstrap behavior:

- Read `current_user.user_id` from the verified token.
- Insert default `profiles` row if absent.
- Insert default `user_settings` row if absent.
- Make repeated calls idempotent.
- Return safe row existence/status fields, not service-role diagnostics.
- Use Supabase/Postgres access through an approved backend data-access boundary.

C2.3 backend access decision:

- Backend bootstrap uses Supabase REST with the existing backend-only
  `SUPABASE_SERVICE_ROLE_KEY`.
- This avoids adding a new Postgres client or Supabase Python SDK.
- The frontend never receives the service-role key and cannot choose `user_id`;
  the backend uses only the verified `current_user.user_id`.
- Live C2.3 validation found PostgREST was missing table privileges:
  `permission denied for table profiles`. The fix is the committed migration
  `supabase/migrations/20260801115446_grant_cloud_table_privileges.sql`.
- The migration grants `USAGE` on schema `public` and DML privileges on the
  five C1.2 user-owned tables to `authenticated` and `service_role`, with no
  `anon` grant. RLS remains enabled and own-row policies remain unchanged.

Redirect URL plan:

- Development site callback: `http://localhost:5173/auth/callback`
- Development password reset: `http://localhost:5173/auth/reset-password`
- Production callback/reset URLs must be configured in the production Supabase
  project only after the production domain is known.
- Redirect handlers must accept only an explicit allowlist of same-site auth
  paths. Avoid arbitrary `next=` redirects.

Protected route behavior:

- Public auth routes: signup, login, forgot password, reset password callback.
- Protected dashboard shell: requires an active Supabase session.
- Unknown/expired session: redirect to login with a generic message.
- Authenticated user visiting login/signup: redirect to dashboard.
- Existing desktop-local `/`, `/profile-setup`, and backend desktop routes stay
  unchanged until a later phase explicitly migrates them.

Future desktop login:

- C5 owns desktop login and cloud synchronization.
- Preferred direction is a secure browser-based auth handoff or embedded
  Supabase auth flow with explicit token handling rules.
- C2 should not bind the desktop app to login yet.

## C2 Implementation Order

1. C2.2: installed `@supabase/supabase-js`, added frontend env placeholders using
   `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`, and created a tiny auth
   client boundary.
2. C2.2: added basic auth routes/components for signup, login, forgot password,
   reset password, and callback, using existing React Router.
3. C2.2: added `GET /api/auth/me` using the C1.4 verifier.
4. C2.3: added profile bootstrap endpoint and tests after choosing the backend
   Supabase data-access approach.
5. C2.4: added protected dashboard route behavior and session/account state
   handling.
6. C2.5: close the auth surface by auditing C2.1-C2.4 docs, routes, env
   boundaries, protected-route behavior, bootstrap idempotency, token handling,
   open-redirect controls, and phase boundaries.
7. C2 final validation: run live signup/login/logout/email/reset/manual browser
   checks against `saiia-dev`.

## Required Tests For C2 Implementation

Backend tests:

- Missing token on `/api/auth/me` returns `401`.
- Invalid/expired token on `/api/auth/me` returns `401`.
- Valid token returns safe identity only.
- Profile bootstrap uses `current_user.user_id`, not payload `user_id`.
- Profile bootstrap is idempotent.
- Service-role key is not used for JWT verification and is not returned.

Frontend tests/manual checks:

- Signup form handles invalid email/password.
- Login succeeds for verified user.
- Login failure uses generic account-safe error text.
- Logout clears local session and protected dashboard redirects.
- Forgot-password flow sends reset email.
- Reset-password callback updates password without logging tokens.
- Refreshing a protected page keeps or restores the session.

## C2.2 Implementation Status

- [x] Kept auth screens inside the existing React/Vite app on port 5173.
- [x] Added temporary routes: `/auth/signup`, `/auth/login`,
  `/auth/forgot-password`, `/auth/reset-password`, `/auth/callback`,
  `/auth/status`, and `/auth/logout`.
- [x] Added frontend Supabase client boundary in `frontend/src/auth/` using
  only `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- [x] Added `GET /api/auth/me` in FastAPI using the existing C1.4
  `get_current_user()` verifier.
- [x] `/api/auth/me` returns only `user_id`, optional `email`, and optional
  `role`.
- [x] Did not add backend signup/login endpoints, `/api/auth/profile/bootstrap`,
  cloud profile saving, cloud resume upload, desktop login, session history,
  billing, usage, email-provider integration, payments, or final website UI.
- [x] Existing `/`, `/profile-setup`, and Electron development behavior remain
  unprotected.

## C2.3 Implementation Status

- [x] Added `POST /api/auth/profile/bootstrap`.
- [x] Protected bootstrap with the existing C1.4 `get_current_user()` verifier.
- [x] Bootstrap derives `user_id` only from the verified Supabase access token.
- [x] Bootstrap creates a `profiles` row if missing and reuses it if present.
- [x] Bootstrap creates a `user_settings` row if missing and reuses it if
  present.
- [x] Bootstrap is idempotent through select-before-insert behavior and C1.2
  unique constraints on `profiles.user_id` and `user_settings.user_id`.
- [x] `/auth/status` includes a temporary `Prepare Profile` button that calls
  the bootstrap endpoint after login.
- [x] Did not migrate local profile JSON, upload resumes, write
  `resumes`/`resume_chunks`/`job_contexts`, protect desktop-local routes, add
  desktop login/cloud sync, sessions, billing, usage, email-provider
  integration, payments, or final website UI.

## C2.4 Implementation Status

- [x] Added temporary protected route `/auth/dashboard` in the existing
  React/Vite app.
- [x] Signed-out or expired-session users are redirected to `/auth/login` with a
  generic session message.
- [x] Already-authenticated users who open `/auth/login` or `/auth/signup` are
  redirected to `/auth/dashboard` after a safe Supabase session check.
- [x] Signed-in users see only safe account identity from `GET /api/auth/me`.
- [x] `/auth/dashboard` can run the existing C2.3 profile bootstrap action and
  report profile/settings readiness without storing the raw access token in
  React state.
- [x] Logout is guarded against duplicate clicks, handles Supabase sign-out
  failures with generic UI text while preserving profile readiness, clears the
  browser session only on success, and returns to `/auth/login`.
- [x] Existing `/` and `/profile-setup` remain unprotected for desktop-local
  development.
- [x] Did not add backend signup/login endpoints, backend session endpoints,
  cloud resume upload, desktop login/cloud sync, session history, billing,
  usage, email-provider integration, payments, or final website UI.

## C2.5 Auth Surface Closure

- [x] Reviewed C2.1, C2.2, C2.3, and C2.4 implementation status against the
  current frontend and backend files.
- [x] Confirmed current auth routes are documented:
  `/auth/signup`, `/auth/login`, `/auth/forgot-password`,
  `/auth/reset-password`, `/auth/callback`, `/auth/status`,
  `/auth/logout`, `/auth/dashboard`, `GET /api/auth/me`, and
  `POST /api/auth/profile/bootstrap`.
- [x] Confirmed frontend auth configuration is limited to
  `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- [x] Confirmed backend auth configuration keeps `SUPABASE_SERVICE_ROLE_KEY`
  backend-only and uses `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG` for JWT/JWKS
  verification with HTTPS-only JWKS URL handling.
- [x] Confirmed `/auth/dashboard` is protected, `/auth/login` and
  `/auth/signup` redirect authenticated users to a safe next route or
  `/auth/dashboard`, `/auth/status` remains available for auth diagnostics,
  logout clears the browser Supabase session on success, and `/` plus
  `/profile-setup` intentionally remain unprotected for desktop-local
  development.
- [x] Confirmed C2.3 profile bootstrap remains idempotent, creates/reuses only
  `profiles` and `user_settings`, and derives `user_id` only from the verified
  backend `CurrentUser`.
- [x] Confirmed auth code does not store raw access tokens in React state and
  does not expose passwords, refresh tokens, service-role keys, or full JWT
  payloads in API responses.
- [x] Confirmed safe next-route handling is allowlisted to `/auth/dashboard`
  and `/auth/status`, avoiding external/open redirects.
- [x] Confirmed no backend signup/login endpoints were added; Supabase browser
  auth owns signup/login/reset flows in this temporary C2 surface.
- [x] Confirmed no C3 cloud resume upload, C5 desktop login/cloud sync,
  session history, billing, usage, email-provider integration, payments, admin
  console, or final website UI was started.

## Supabase Dashboard Setup For C2.2

Set the development auth URLs in the `saiia-dev` Supabase project:

- Site URL: `http://localhost:5173`
- Redirect URL: `http://localhost:5173/auth/callback`
- Redirect URL: `http://localhost:5173/auth/reset-password`

Do not add production redirect URLs until the production domain is known.

## Manual Validation After C2.3

- Apply the C2.3 privilege migration to the `saiia-dev` project before retrying
  live profile bootstrap:
  `npx supabase db push`.
- Confirm C1 remains marked complete and only C2.1/C2.2/C2.3 are completed in
  C2.
- Confirm `GET /api/auth/me` and `POST /api/auth/profile/bootstrap` exist in
  FastAPI docs.
- Confirm the desktop app still opens `/` and `/profile-setup` without login.
- Confirm `.env.example` does not contain smoke-test credentials or real
  Supabase values.
- Confirm `http://localhost:5173/auth/login` loads in the browser.
- With local-only dev credentials in `.env`, test signup, email verification,
  login, logout, forgot password, reset password, and auth callback handling.
- Confirm `/auth/status` can call `/api/auth/me` after login without displaying
  the raw access token.
- On `/auth/status`, click `Prepare Profile` and confirm the page reports the
  profile/settings bootstrap result.
- In Supabase Dashboard, verify one `profiles` row and one `user_settings` row
  exist for the authenticated test user. Click `Prepare Profile` again and
  confirm duplicate rows are not created.
- If bootstrap still returns a generic 502, check backend logs for the sanitized
  Supabase REST table, operation, status code, and truncated response body.
- Confirm the smoke-test user's password from C1.5 was changed or the user was
  deleted.

## Manual Validation After C2.4

- Open `http://localhost:5173/auth/dashboard` while signed out and confirm it
  redirects to `/auth/login` with a session-expired/signed-out message.
- While already signed in, open `http://localhost:5173/auth/login` and
  `http://localhost:5173/auth/signup`; both should redirect to
  `/auth/dashboard`.
- Log in with the existing dev Supabase test user and open
  `http://localhost:5173/auth/dashboard`.
- Confirm the page shows only the safe user email or user id and optional role.
- Click `Prepare Profile` and confirm it reports profile/settings readiness
  without duplicate rows.
- Click `Logout` and confirm the button enters a pending state and the app
  returns to `/auth/login` on success.
- Simulate a sign-out failure and confirm the dashboard/status page shows
  `Sign out failed. Please try again.` without clearing profile readiness.
- Confirm `http://localhost:5173/` and
  `http://localhost:5173/profile-setup` still open without login.
- Confirm no raw access token, refresh token, password, or service-role value is
  displayed in the browser.

## Manual Validation After C2.5

- Run the C2.2/C2.3/C2.4 browser checks once more against `saiia-dev` before
  beginning C3.
- Confirm signup, email verification, login, `/auth/dashboard`,
  `Prepare Profile`, `/auth/status`, logout, forgot-password, reset-password,
  and `/auth/callback` still behave as documented.
- Confirm `/` and `/profile-setup` remain open without login.
- Confirm browser developer tools do not show raw access tokens, refresh
  tokens, passwords, or service-role values in rendered UI or console output.
- Confirm no duplicate `profiles` or `user_settings` rows are created for the
  same Supabase Auth user.
