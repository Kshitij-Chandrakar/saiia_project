# C1 Supabase Foundation

SAIIA has a backend-only Supabase configuration boundary, a repeatable
migration directory, the C1.2 base cloud schema migration, the C1.3 RLS/storage
foundation, and the C1.4 FastAPI auth-token verification dependency. C1 is
closed as a cloud foundation phase after C1.5 validation. No profile, resume,
job-context, session, billing, or usage-limit data is migrated in C1.

## Modes

Local-only mode is the default:

```text
SAIIA_CLOUD_MODE=local
```

In local-only mode, existing desktop features continue to use local files and
do not require Supabase credentials.

Cloud-enabled development mode is explicit:

```text
SAIIA_CLOUD_MODE=cloud
```

When cloud mode is enabled, the backend validates that every required Supabase
environment variable is present and reports missing variable names without
printing secret values.

## Backend Environment Variables

These values belong in local `.env` files or deployment secret managers only:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=
SUPABASE_RESUME_BUCKET=
SUPABASE_EXPORT_BUCKET=
```

`SUPABASE_SERVICE_ROLE_KEY` is backend-only. Do not expose it to React,
Electron renderer code, preload APIs, browser-extension code, logs, API
responses, screenshots, or public documentation.

Development and production must use separate Supabase projects, separate
storage buckets, separate environment files, and separate deployment secrets.

## Migration Approach

Future schema changes must be committed as SQL migration files under:

```text
supabase/migrations/
```

Use this naming convention:

```text
YYYYMMDDHHMMSS_descriptive_name.sql
```

Do not make production schema changes only through the Supabase dashboard. If a
dashboard action is required, mirror the resulting schema change in a committed
migration before considering the phase complete.

C1.2 adds the first base schema migration:

```text
supabase/migrations/20260731121714_create_base_cloud_schema.sql
```

It creates `profiles`, `resumes`, `resume_chunks`, `job_contexts`, and
`user_settings`.

C1.3 adds RLS policies and private storage buckets:

```text
supabase/migrations/20260731123545_enable_rls_and_storage.sql
```

C2.3 adds a follow-up privilege migration required by Supabase PostgREST access:

```text
supabase/migrations/20260801115446_grant_cloud_table_privileges.sql
```

It grants `USAGE` on `public` plus `SELECT`, `INSERT`, `UPDATE`, and `DELETE`
on the five C1.2 user-owned tables to `authenticated` and `service_role`. It
does not grant table privileges to `anon`.

## Secret Handling

`.env` and `.env.*` are ignored by Git. `.env.example` contains variable names
only and must not contain real project URLs, keys, tokens, passwords, or
identifiers.

The backend config module exposes only redacted configuration state. It never
returns key contents and does not create a Supabase client until a later phase
adds an approved SDK dependency and a concrete data-access path.

## C1.2 Base Schema

The base tables use UUID primary keys and Supabase Auth ownership:

```sql
user_id uuid not null references auth.users(id) on delete cascade
```

Created tables:

- `profiles`: one base profile per user, with JSONB list fields for skills,
  education, experience, projects, achievements, certifications, and tools.
- `resumes`: resume metadata and parser/index status only.
- `resume_chunks`: resume text chunks with a nullable JSONB `embedding`
  placeholder so pgvector is not required yet.
- `job_contexts`: job targeting context with a partial unique index allowing
  only one active job context per user.
- `user_settings`: one settings row per user, with JSONB overlay and
  notification preferences.

`updated_at` is maintained by a small shared trigger function on tables that
have an `updated_at` column.

RLS policies are deferred to C1.3. C1.2 prepares every user-owned table with
`user_id` and ownership indexes, but does not enable policies yet because
enabling RLS without policies can block all normal access during local schema
validation.

Storage buckets are deferred to C1.3. C1.2 stores only future storage path
metadata in `resumes`; it does not create buckets or upload files.

The C1.2 migration was applied successfully to the live `saiia-dev` Supabase
project before C1.3 began. The five base tables existed with zero rows at that
checkpoint.

## C1.3 RLS And Storage

C1.3 enables RLS on:

- `profiles`
- `resumes`
- `resume_chunks`
- `job_contexts`
- `user_settings`

Each table has authenticated-user policies for read, insert, update, and
delete. All policies require `user_id = auth.uid()`. Update policies use both
`USING` and `WITH CHECK`, so users can update only rows they already own and
cannot move a row to another user's `user_id`.

Supabase/PostgREST also requires ordinary table privileges in addition to RLS
policies. The C2.3 support migration grants table access to `authenticated` and
`service_role` only. Authenticated grants are safe only because the C1.3 RLS
policies restrict every row by `auth.uid()`. The service role bypasses RLS and
must remain backend-only; backend code must continue deriving `user_id` from a
verified Supabase JWT rather than trusting frontend input.

C1.3 creates two private Supabase Storage buckets:

- `resumes`
- `exports`

Both buckets are private and not public. The selected storage path convention
inside each bucket is:

```text
{user_id}/...
```

Examples:

```text
resumes bucket: {user_id}/resume.pdf
exports bucket: {user_id}/interview-summary.pdf
```

Storage policies allow authenticated users to read, insert, update, and delete
only objects where the first path segment matches `auth.uid()`. Audio,
screenshot, public, billing, usage, email, and payment buckets are not created.

C1.3 does not implement FastAPI token verification, login/signup, account
lifecycle, resume cloud upload, job-context sync, desktop cloud sync, sessions,
AI notes, Ask AI, billing, usage limits, email, payments, or website UI.

The C1.3 migration was applied successfully to the linked live `saiia-dev`
Supabase project. Migration history shows both C1.2 and C1.3 present remotely.
Linked database lint was re-run during C1.5 and completed without SAIIA schema
errors.

## C1.4 FastAPI Auth Verification

C1.4 adds a reusable backend dependency:

```text
backend/app/auth/supabase_auth.py
```

Use `get_current_user()` for future protected FastAPI routes. It reads
`Authorization: Bearer <token>`, verifies the Supabase access token, and returns
a safe `CurrentUser` object with `user_id`, optional `email`, optional `role`,
and a small safe claim subset. It never returns or stores the raw token.

Verification strategy:

- Prefer JWKS verification when `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG` is a JWKS
  URL or JWKS JSON.
- Fall back to legacy shared-secret verification only when that variable is an
  explicit JWT secret or JSON config containing `jwt_secret`/`secret`.
- Do not use `SUPABASE_SERVICE_ROLE_KEY` for JWT verification.
- Validate token signature, expiration, subject, issuer, and audience where
  configured. The default inferred issuer is `{SUPABASE_URL}/auth/v1`, and the
  default audience is `authenticated`.

Local-only mode still starts the desktop backend without Supabase auth
verification config. If a future protected dependency is called without usable
auth verification config, it returns a controlled `503` configuration error.
Invalid, malformed, expired, or missing bearer tokens return `401`.

C1.4 does not protect existing desktop-local routes yet and does not add
`/api/auth/*` endpoints. C2 owns login/signup/account lifecycle. C5 owns desktop
login and cloud synchronization.

## C1.5 Closure Audit

C1.5 verifies that:

- backend Supabase configuration exists and preserves local-only desktop mode
- C1.2 base schema exists and was applied to live `saiia-dev`
- C1.3 RLS policies and private storage buckets exist and were applied to live
  `saiia-dev`
- C1.4 FastAPI token verification foundation exists
- existing desktop-local routes are not forced through login
- no C2/C3/C5/session/billing/usage/email/payment/website work was started
- secrets remain outside Git and service-role values are not exposed

Live Supabase user-token smoke test passed after C1.5 closure validation. A
real Supabase Auth user access token was validated by the C1.4 FastAPI verifier.
The skipped-by-default test lives at:

```text
backend/tests/test_supabase_live_auth_smoke.py
```

It runs only when all of these local environment variables are intentionally
set:

```text
SAIIA_ENABLE_LIVE_AUTH_SMOKE=true
SAIIA_SMOKE_AUTH_EMAIL=
SAIIA_SMOKE_AUTH_PASSWORD=
```

The smoke also uses local `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and
`SUPABASE_JWT_SECRET_OR_JWKS_CONFIG`. It signs in locally through Supabase Auth,
passes the returned access token to the backend verifier, asserts a user id, and
does not print the token or password. It does not use
`SUPABASE_SERVICE_ROLE_KEY`, does not add auth routes, and does not create login
or signup UI.

The smoke-test user's password was treated as exposed after live validation and
should be changed immediately or the smoke-test user should be deleted.

C2 owns account lifecycle and any committed website/desktop login behavior.
C3 owns cloud resume upload. C5 owns desktop login and cloud synchronization.

Closure validation on 2026-07-31:

- `npx supabase migration list` showed C1.2 and C1.3 present locally and
  remotely for the linked project.
- `npx supabase db lint --linked --schema public,storage --level warning
  --fail-on error` completed without SAIIA schema errors. It reported only
  Supabase-owned storage function warnings.
- Local Supabase status and remote schema dump were Docker-gated in this
  workstation because Docker/Podman was not on PATH.
- Dashboard verification confirmed the five public tables, RLS status, own-row
  policies, private `resumes` bucket, private `exports` bucket, and
  `storage.objects` ownership policies.
- Live Supabase Auth user-token smoke test passed: the C1.4 FastAPI verifier
  accepted a real Supabase access token and returned a `CurrentUser.user_id`.
- No login/signup UI, `/api/auth/*` route, existing desktop route protection,
  cloud resume upload, desktop login, session, billing, usage, email, payment,
  or website UI work was added.
- Token, password, and service-role key values were not committed or printed.
- `python -m compileall backend/app`, focused Supabase tests, full backend
  tests, frontend build, Electron syntax checks, `git diff --check`, secret
  exposure scan, prohibited phase scan, and `graphify update .` passed for C1.5.

## Applying Migrations

Preferred local validation uses the project-local Supabase CLI:

```text
npx supabase --version
npx supabase db reset
```

For the linked development project, inspect migrations with:

```text
npx supabase migration list
```

Apply pending linked-project migrations only when intentionally targeting the
development Supabase project:

```text
npx supabase db push
```

Use a separate development Supabase project for cloud testing. Production
changes must come from committed migrations, not one-off dashboard edits.

For development-only inspection, the SQL can be pasted into the Supabase SQL
editor, but that is a fallback only. If a dashboard or SQL-editor change is
used during development, keep the committed migration as the source of truth
before promoting anything to production.
