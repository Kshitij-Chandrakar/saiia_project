# C4.1 - Cloud Job Context Audit, Architecture, and Implementation Plan

Date: 2026-08-09

Scope: C4.1 audit and plan only. No C4.2+ runtime code, migrations, live database writes, desktop login, or desktop cloud sync were implemented.

## Verified Current-State Architecture

SAIIA currently has two separate job-context worlds:

- Desktop/local P3 runtime exists under the unauthenticated local backend route prefix `/api/job-context`.
- Migration history defines a Supabase `public.job_contexts` table, RLS policies, grants, and a one-active-per-user partial unique index.
- No authenticated cloud job-context FastAPI routes or React/Vite job-target management page exist yet.
- Current answer generation still loads local job context through `JobContextService`, not Supabase.

C4 should add authenticated cloud job-target CRUD and active-context retrieval for authenticated backend paths while preserving local desktop behavior until C5 intentionally connects Electron identity/session to cloud state.

## Verified Existing Local P3 Files, Routes, and Services

Source files verified:

- `backend/app/main.py`
- `backend/app/api/job_context.py`
- `backend/app/services/job_context_service.py`
- `backend/app/templates/profile_setup.html`
- `backend/app/api/generate.py`
- `backend/app/nlp/answer_planner.py`
- `backend/app/nlp/answer_generator.py`
- `backend/tests/test_answer_planner_problem1.py`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`

Historical claim verification:

| Claim | Current repository status |
| --- | --- |
| `GET /api/job-context` | Verified. `backend/app/main.py` registers `job_context.router` at `/api/job-context`; `backend/app/api/job_context.py` defines `@router.get("")`. |
| `POST /api/job-context` | Verified. `@router.post("")` saves through `JobContextService.save_context()`. |
| `DELETE /api/job-context` | Verified. `@router.delete("")` deletes local context. |
| `POST /api/job-context/extract` | Verified. `@router.post("/extract")` accepts `UploadFile`. |
| Local `tmp/job_context.json` persistence | Verified in code. `JobContextService.context_path` resolves to repo `tmp/job_context.json`; current workspace does not contain the file, so no-context is current local state. |
| JD text/file extraction | Partially verified. File extraction is supported by upload endpoint through `ResumeService.extract_text()`. There is no current text-only extraction endpoint. |
| Required-skills extraction | Verified in local extraction prompt and response schema as string field `required_skills`. |
| Responsibilities extraction | Verified in local extraction prompt and response schema as string field `responsibilities`. |
| Seniority extraction | Not verified in current local code. P3 tracker says done historically, but current `JobContextPayload` and extraction JSON keys do not include `seniority`. |
| Domain keyword extraction | Not verified in current local code. P3 tracker says done historically, but current local schema and extraction prompt do not include `domain_keywords`. |
| Company/position storage | Verified under local names `company_name` and `target_role`. Cloud schema uses `company` and `position`. |
| Answer-generation integration | Verified. `backend/app/api/generate.py` calls `job_context_service.get_context()` when `answer_plan.job_context_policy != "FORBIDDEN"`. |
| No-context generation fallback | Verified. `JobContextService.get_context()` returns `saved: false` if the file is absent, and focused tests cover planner/generation behavior without job context. |

Current local fields:

- `target_role`
- `company_name`
- `job_description`
- `required_skills`
- `responsibilities`
- `preferred_qualifications`
- `company_notes`
- `updated_at`
- `saved`

Local extraction behavior:

- Reuses `ResumeService.extract_text(filename, content)` for `.pdf`, `.docx`, and `.txt` handling.
- Calls Groq chat completions with JSON response format.
- Tells the model not to invent missing company or role facts.
- Returns extracted fields without saving them.
- Logs filename, extracted text length, and populated field names, not raw JD text.

Local generation behavior:

- `AnswerPlan.job_context_policy` gates whether local job context is fetched.
- Current route code passes job context to the generator only when `use_profile_context` is also true and the saved context has `saved: true`.
- `AnswerGenerator._build_prompt()` includes target role, company, JD summary, required skills, responsibilities, preferred qualifications, and company notes only when candidate context is included.
- Provider fallback paths intentionally pass no job context in some error/fallback branches.

## Migration-Defined Supabase `job_contexts` Schema/State

Verified in `supabase/migrations/20260731121714_create_base_cloud_schema.sql`:

```sql
create table if not exists public.job_contexts (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  company text not null default '',
  position text not null default '',
  job_description text not null default '',
  required_skills jsonb not null default '[]'::jsonb,
  responsibilities jsonb not null default '[]'::jsonb,
  seniority text not null default '',
  domain_keywords jsonb not null default '[]'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint job_contexts_required_skills_array check (jsonb_typeof(required_skills) = 'array'),
  constraint job_contexts_responsibilities_array check (jsonb_typeof(responsibilities) = 'array'),
  constraint job_contexts_domain_keywords_array check (jsonb_typeof(domain_keywords) = 'array')
);
```

Verified indexes/triggers:

- `job_contexts_user_id_idx` on `(user_id)`.
- `job_contexts_one_active_per_user_idx` unique on `(user_id) where is_active`.
- `set_job_contexts_updated_at` trigger calls `public.set_updated_at()` before update.

Verified ownership/RLS/grants:

- `user_id` references `auth.users(id) on delete cascade`.
- `supabase/migrations/20260731123545_enable_rls_and_storage.sql` enables RLS on `job_contexts`.
- RLS policies permit authenticated users to select, insert, update, and delete only rows where `user_id = auth.uid()`.
- Update policy uses both `USING` and `WITH CHECK`, preventing ownership transfer under authenticated client access.
- `supabase/migrations/20260801115446_grant_cloud_table_privileges.sql` grants select/insert/update/delete to both `authenticated` and `service_role`.
- C3 hardening migration revokes authenticated direct writes for `profiles`, `resumes`, and `resume_chunks`, but not for `job_contexts`.

This is migration-defined state only. Live deployed Supabase schema, RLS, grants, ownership behavior, and RPC privileges remain pending validation for C4.2; C4.1 did not query or mutate the live database.

## Schema Gap Analysis

C4 requirement vs current cloud schema:

| Requirement | Current cloud state | C4.2 action |
| --- | --- | --- |
| Company | Present as `company` | Reuse. |
| Position | Present as `position` | Reuse. |
| Raw job description | Present as `job_description` | Reuse as the full/raw JD text. |
| Required skills | Present as JSONB array | Reuse; normalize local comma/newline strings into arrays. |
| Responsibilities | Present as JSONB array | Reuse; normalize local prose/list text into arrays. |
| Seniority | Present as text | Reuse; local extractor must be extended in C4.2/4.3 without disrupting current local fields. |
| Domain keywords | Present as JSONB array | Reuse; local extractor must be extended for cloud extraction response. |
| Optional location | Missing | Migration required if C4 UI/API stores it. |
| Optional employment type | Missing | Migration required if C4 UI/API stores it. |
| Active/inactive state | Present as `is_active` | Reuse; adjust default behavior. |
| Source-file metadata | Missing | Migration required if uploaded JD metadata is retained. |

Recommended C4.2 migration:

- Add `location text not null default ''`.
- Add `employment_type text not null default ''`.
- Add `source_file_metadata jsonb not null default '{}'::jsonb`.
- Add check constraint `jsonb_typeof(source_file_metadata) = 'object'`.
- Change `is_active` default from `true` to `false` so multiple saved inactive targets are safe by default.
- Add a backend-only activation RPC, e.g. `public.activate_job_context(p_user_id uuid, p_job_context_id uuid)`, that deactivates other contexts for the same user and activates the selected row in one transaction.
- Lock the C4.2 access model to C3's backend-only mutation pattern: revoke direct authenticated `INSERT`, `UPDATE`, and `DELETE` on `public.job_contexts`; retain appropriate authenticated read access; grant write privileges to `service_role` for backend operations.
- Do not modify already-applied historical migrations in C4.2; add a new forward migration.
- Revoke `EXECUTE` on the activation RPC from `PUBLIC`, `anon`, and `authenticated`; grant `EXECUTE` only to `service_role`.

Do not create this migration in C4.1.

## Proposed Authenticated API Contracts

Register a new authenticated router at `/api/job-contexts`. Keep existing `/api/job-context` local router unchanged for desktop-local P3 until C5.

All routes must use `CurrentUserDep`; request bodies must not accept or trust `user_id`.

Cloud persisted `job_description` is the full/raw JD text. Authorized detail CRUD responses may return it to the owning authenticated user, but list responses must not return the raw full JD. Raw JD text must never appear in normal logs, error payloads, diagnostics, unauthenticated responses, or cross-user responses.

### Planned C4.2 Input Limits

Existing verified project limits to reuse:

- JD upload size: reuse `MAX_RESUME_FILE_BYTES = 5 * 1024 * 1024` from `backend/app/services/resume_service.py`.
- Supported JD upload types: reuse the existing PDF/DOCX/TXT document set from `ResumeService` and `CloudResumeService`.
- Sanitized source filename: reuse the cloud resume filename sanitizer ceiling of 120 characters including extension.

New C4.2 constants to define in the cloud job-context backend:

| Field | Limit |
| --- | ---: |
| `company` | 160 characters |
| `position` | 160 characters |
| `job_description` | 100,000 characters |
| `seniority` | 80 characters |
| `location` | 160 characters |
| `employment_type` | 80 characters |
| `required_skills`, `responsibilities`, `domain_keywords` item count | 50 items per array |
| Array item length | 160 characters |
| Metadata string value length | 256 characters |
| Metadata object size | 2,048 serialized UTF-8 bytes |
| Total JSON request body size | 128 KiB serialized UTF-8 bytes |
| Multipart body read limit | 6 MiB total request body before parsing |
| Multipart file size | 5 MiB file bytes, reusing `MAX_RESUME_FILE_BYTES` |
| Maximum extracted UTF-8 JD text | 100,000 bytes before prompt construction, response serialization, or persistence |
| Multipart non-file form fields | Bounded by the same per-field limits above and the 6 MiB total body limit |

These limits are C4.2 contract inputs, not C4.1 runtime behavior.

### `GET /api/job-contexts`

Returns all current user's saved job targets ordered by `is_active desc, updated_at desc`.

List responses return summary fields only. They must not include raw full `job_description`; use bounded summaries/derived display fields such as `job_description_preview` and counts instead.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "company": "",
      "position": "",
      "job_description_preview": "",
      "job_description_length": 0,
      "required_skills": [],
      "responsibilities": [],
      "seniority": "",
      "domain_keywords": [],
      "location": "",
      "employment_type": "",
      "is_active": false,
      "created_at": "",
      "updated_at": ""
    }
  ],
  "active_id": null
}
```

### `POST /api/job-contexts`

Creates a saved inactive target by default. If `activate: true` is allowed in the request, activation must use the same transaction strategy as `/{id}/activate`.

Request fields:

- `company`
- `position`
- `job_description`
- `required_skills`
- `responsibilities`
- `seniority`
- `domain_keywords`
- `location`
- `employment_type`
- `source_file_metadata`
- optional `activate`

Validation:

- At least one meaningful field is required.
- Array fields must be arrays of bounded strings.
- `source_file_metadata` is server-derived only. Sanitized filename, detected MIME type, byte size, and extraction source must come from the received file or endpoint path.
- Reject client-provided metadata that conflicts with server-derived values.
- POST must be safe to retry, including `activate: true`. C4.2 must either require an idempotency key with server-side replay handling or implement a deterministic per-user deduplication rule over normalized create payloads. Recommendation: require an `Idempotency-Key` header for create requests and store/replay the first completed result for the verified user and normalized request hash.

### `GET /api/job-contexts/{id}`

Returns one context belonging to the verified user. Other-user IDs map to 404.

This is the only read endpoint that may return the full raw `job_description`, and only to the owning authenticated user.

### `PATCH /api/job-contexts/{id}`

Updates editable fields for the verified user's context. It must not accept `user_id`, `id`, `created_at`, `updated_at`, or arbitrary `is_active` changes. Activation stays in the activation endpoint.

### `DELETE /api/job-contexts/{id}`

Deletes one verified-user context. If the deleted row was active, the result is valid no-context state; do not auto-activate another row.

### `POST /api/job-contexts/{id}/activate`

Activates one verified-user context and deactivates all others for that user in one database transaction.

Response should include the activated record and `active_id`.

### `POST /api/job-contexts/extract`

Extracts structured fields without saving.

Support both paste and file upload with one endpoint only if FastAPI form handling stays simple:

- `multipart/form-data` with optional `file` and/or `job_description_text`.
- At least one source is required.
- If both are provided, combine only if explicitly intended; otherwise prefer text and document behavior.

Response:

```json
{
  "company": "",
  "position": "",
  "job_description": "",
  "job_description_summary": "",
  "required_skills": [],
  "responsibilities": [],
  "seniority": "",
  "domain_keywords": [],
  "location": "",
  "employment_type": "",
  "source_file_metadata": {},
  "extracted_text_length": 0
}
```

Extraction must not persist a row. Existing saved context must survive extraction/provider failure.

`job_description` in the cloud extraction response should be the full/raw text that would be saved if the user confirms. If the reused local extractor produces a concise summary, expose that summary only as transient `job_description_summary`; do not add a persisted summary database column in C4.1 or C4.2 unless separately approved.

Before building any provider prompt, serializing an extraction response, or persisting a saved context, C4.2 must enforce the maximum extracted UTF-8 JD text limit. Oversized extracted text should fail with a safe validation error that does not echo the JD.

## Activation Transaction and Concurrency Strategy

Use the database as the concurrency boundary:

1. Backend verifies Supabase JWT and derives `current_user.user_id`.
2. Backend calls a service-role-only RPC with `p_user_id` and `p_job_context_id`.
3. RPC acquires a transaction-scoped serialization guard before changing active rows.
4. RPC verifies the target row exists for `p_user_id`.
5. RPC updates all `public.job_contexts` rows for `p_user_id` to `is_active = false` except target.
6. RPC updates target row to `is_active = true`.
7. RPC returns the activated row.

The existing partial unique index remains the final invariant. If concurrent activations for different targets race despite serialization, one transaction must win cleanly; the backend should map lock/uniqueness/state conflicts to `409` with a safe refresh-and-retry message.

Deleting an active context should be a simple owned-row delete. The partial unique index naturally allows zero active rows.

Preferred C4.2 serialization design:

- Use `pg_advisory_xact_lock(bigint)` with a PostgreSQL-supported bigint key derived from `p_user_id`, not the raw UUID.
- Derive the key as `hashtextextended(p_user_id::text, 0)` or an equivalent stable PostgreSQL bigint expression.
- Collision behavior: a hash collision would unnecessarily serialize two different users but must not permit cross-user data access or break correctness. Different users should otherwise activate in parallel.
- If advisory locking is rejected during C4.2 implementation, use an equivalent per-user row lock, such as locking an owned profile/settings row with `SELECT ... FOR UPDATE` before activation. That fallback requires proving the row exists or creating a dedicated lock row; do not silently skip serialization.

Timeout behavior:

- Set a short transaction-local `lock_timeout`, recommended 2 seconds.
- Set a transaction-local `statement_timeout`, recommended 5 seconds.
- Use a backend database/RPC call timeout, recommended 8 seconds.
- Map lock waits, uniqueness conflicts, and recoverable serialization conflicts to `409 Conflict` with a safe refresh-and-retry message.
- Map unsafe or unrecoverable database timeouts/connectivity failures to `503 Service Unavailable`.

Activation RPC privilege contract:

- `REVOKE EXECUTE ON FUNCTION public.activate_job_context(uuid, uuid) FROM PUBLIC;`
- `REVOKE EXECUTE ON FUNCTION public.activate_job_context(uuid, uuid) FROM anon;`
- `REVOKE EXECUTE ON FUNCTION public.activate_job_context(uuid, uuid) FROM authenticated;`
- `GRANT EXECUTE ON FUNCTION public.activate_job_context(uuid, uuid) TO service_role;`

## Extraction Reuse Strategy

Reuse current P3 logic; do not rewrite extraction because the target is cloud:

- Keep using `ResumeService.extract_text()` for PDF/DOCX/TXT file text extraction.
- Show a user notice before cloud extraction that raw JD text will be sent to the configured extraction provider.
- Require explicit user action/consent for extraction; save/create without extraction must remain possible for users who do not consent to provider processing.
- Preserve the existing local `JobContextExtractResponse` and local string fields:
  - `target_role`
  - `company_name`
  - `job_description`
  - `required_skills`
  - `responsibilities`
  - `preferred_qualifications`
  - `company_notes`
- Add a separate cloud extraction DTO/adapter so C4 does not break P3 behavior.
- The cloud adapter maps extracted/local values into:
  - `company`
  - `position`
  - `seniority`
  - `required_skills[]`
  - `responsibilities[]`
  - `domain_keywords[]`
  - optional `location`
  - optional `employment_type`
- Factor or adapt `JobContextService.build_context_fields()` behind that adapter so cloud extraction can return C4 fields:
  - map `target_role` to `position`
  - map `company_name` to `company`
  - add `seniority`
  - add `domain_keywords`
  - optionally add `location`
  - optionally add `employment_type`
- Keep cloud persisted `job_description` as the full/raw JD text; if the local extractor returns a concise description, map it to transient `job_description_summary` only.
- Normalize extracted skills/responsibilities/domain keywords into arrays for cloud storage, while preserving local P3 string fields.
- Keep "do not invent missing requirements" in the prompt and add tests that absent fields stay empty.
- Do not save extraction output until the user confirms.
- Avoid raw JD text in logs and exception messages.

Cloud extraction provider privacy boundary:

- Current local extraction uses Groq. C4.2 must document the configured provider behavior before enabling cloud extraction in UI copy and release notes.
- Verify and document Groq API retention/training behavior for the configured account/plan at implementation time.
- Use Zero Data Retention or equivalent provider-side retention controls if available for the deployed account.
- If Zero Data Retention is unavailable, the UI notice must say provider processing may be subject to the provider's API retention policy.
- App-side deletion must remove persisted raw JD text and server-derived source metadata from Supabase when a job context is deleted.
- Normal logs, errors, exceptions, diagnostics, and analytics must contain only safe metadata such as byte length, sanitized filename, MIME type, operation, status, and safe error code.

## Frontend Implementation Plan

Reuse C2/C3 authenticated React/Vite patterns in `frontend/src/auth/AuthScreens.jsx` and `frontend/src/auth/authApi.js`.

Smallest temporary C4.3 UI before C14 final Figma integration:

- Add `/auth/job-targets` route in `frontend/src/App.jsx`.
- Add a protected `AuthJobTargetsPage`.
- Add `authApi.js` functions mirroring cloud resume token/header style.
- Dashboard/auth nav can link to "Job targets".
- Page supports:
  - list saved targets
  - active target marker
  - empty/no-target state
  - create/edit form
  - paste JD text
  - optional JD file upload for extraction
  - extract without save
  - review/edit extracted fields
  - save
  - activate
  - delete
  - loading states for extraction/save/activation/delete
  - controlled, safe errors

Do not redesign the production website. Keep C4.3 UI functional and consistent with the existing auth/resume page.

## Active-Context Generation Integration Plan

C4.4 should make authenticated generation paths use only the verified user's active cloud context.

Current generation facts:

- `/generate/` and `/generate/stream` are currently not authenticated routes.
- Local generation receives a caller-supplied `profile` and local `tmp/job_context.json`.
- Cloud resume retrieval exists in `CloudResumeService.retrieve_active_resume_chunks()`, but current `generate.py` imports the local `resume_index_service` and does not use authenticated cloud resume retrieval.
- Job context is fetched only when `AnswerPlan.job_context_policy != "FORBIDDEN"`.
- Job context is passed to `AnswerGenerator` only when profile context is also enabled and context exists.

C4.4 requirements:

- Add authenticated generation path or service branch that receives `CurrentUserDep`.
- Retrieve exactly one active cloud context with `user_id = current_user.user_id` and `is_active = true`.
- If no active context exists, pass `None`/`saved: false` and preserve no-context generation.
- Never read inactive contexts for generation.
- Never accept `job_context_id` or `user_id` from the frontend as generation authority.
- Keep local desktop `/generate/` fallback unchanged until C5.
- Preserve planner policy gating: if job context is forbidden, do not fetch or inject cloud job context.
- Decide explicitly whether current "job context requires profile context" behavior is correct; document and test the chosen behavior before changing it.

## Local-vs-Cloud Transition Strategy

Before C5:

- Local desktop profile/job-context routes remain supported and unauthenticated.
- Cloud job-target routes are website/auth-only.
- No Electron Supabase login, desktop token persistence, account switching, sync engine, or cloud/local migration is added.
- Authenticated cloud generation may be added for website/backend flows, but desktop identity wiring waits for C5.

At C5:

- Electron gets a secure login/session design.
- Desktop can call authenticated cloud endpoints.
- Local `tmp/job_context.json` migration/sync rules are decided then.

## C4/C5 Boundary

C4 may:

- Build authenticated backend cloud job-context CRUD.
- Build authenticated web job-target management UI.
- Retrieve active cloud job context for authenticated generation services.
- Preserve valid no-context behavior.

C4 must not:

- Add Electron login.
- Persist Supabase tokens in desktop.
- Add desktop account switching.
- Add desktop cloud/local sync.
- Migrate local `tmp/job_context.json` into cloud automatically.
- Expose service-role key to frontend or Electron.

## Security and Privacy Considerations

Verified current security foundation:

- `get_current_user()` verifies Supabase JWTs and returns a safe `CurrentUser`.
- C3 cloud resume routes derive `user_id` only from `CurrentUserDep`.
- C3 cloud services use backend-only service-role REST calls and include `user_id` filters in queries/mutations.
- Frontend uses Supabase anon key only and sends access tokens to backend as `Authorization: Bearer`.
- Current cloud resume responses strip raw resume text from extraction responses.
- Current cloud resume logs avoid raw provider payloads and private resume text.

C4 concerns to address:

- `job_contexts` still has authenticated direct insert/update/delete grants and RLS write policies in migration-defined state; C4.2 must harden this to backend-only writes like C3 by adding a new migration that revokes authenticated direct writes while retaining appropriate authenticated reads.
- Current `is_active default true` is unsafe for multi-target creation because a second insert can violate the one-active partial unique index unless the backend overrides it.
- Existing local extraction logs uploaded filename. C4 should sanitize filenames before storing metadata or logging.
- Raw private JD text must not be logged, emitted in safe diagnostics, included in error payloads, or returned from unauthenticated/cross-user requests.
- Frontend must not send or choose `user_id`.
- Other-user IDs must return 404, not reveal existence.
- Activation race behavior must be covered by database uniqueness plus RPC transaction tests.
- JD file handling should enforce extension, MIME, non-empty content, and size limits similar to resume upload.
- Service-role key must remain backend-only and never appear in API responses, frontend source, Electron preload, or logs.

## Required Automated Tests

Backend unit/route tests:

- Cloud job-context routes reject missing/invalid JWT.
- Create derives `user_id` from verified token and ignores request `user_id`.
- List returns only service-owned user rows from fake service.
- List responses exclude raw full `job_description` and source metadata that could reveal private JD contents.
- Get/update/delete map other-user/missing rows to 404.
- Create validates at least one meaningful field.
- Create rejects payloads over the 128 KiB JSON body limit.
- Multipart extraction rejects bodies over the 6 MiB read limit and files over the 5 MiB file limit.
- Extraction rejects extracted UTF-8 JD text over 100,000 bytes before prompt construction, response serialization, or persistence.
- Create with the same idempotency key and identical normalized payload returns/replays the same result without duplicate rows.
- Retried create with `activate: true` is idempotent and leaves exactly one active context.
- Reusing an idempotency key with a conflicting payload is rejected safely.
- Array fields normalize and reject oversized/invalid values.
- Extract from pasted text returns editable fields and does not save.
- Extract from file reuses text extraction and validates file metadata.
- File extraction metadata is server-derived; conflicting client-provided metadata is rejected.
- Extraction/provider failure does not overwrite existing saved context.
- Activate calls backend-only service/RPC and maps conflicts to 409.
- Concurrent activation of two different targets for the same user serializes through the advisory lock or equivalent mechanism, leaves exactly one active row, and maps stale/conflicting requests to a safe 409 where applicable.
- Concurrent activation for different users runs independently except for documented advisory-hash collision behavior.
- Lock timeout and recoverable serialization conflicts map to 409; unrecoverable DB timeout/connectivity maps to 503.
- Delete active context returns valid no-context state.
- Response/error bodies do not include service-role key or raw JD text.
- Cloud extraction requires user consent/notice before sending raw JD to Groq or any configured provider.

Migration tests:

- `job_contexts` has `location`, `employment_type`, `source_file_metadata` if migration is added.
- `is_active` default is false after migration.
- One-active partial unique index remains.
- Activation RPC exists, is service-role-only, and is not executable by `anon` or `authenticated`.
- Activation RPC migration explicitly revokes execute from `PUBLIC`, `anon`, and `authenticated`, and grants execute only to `service_role`.
- Direct authenticated job-context `INSERT`, `UPDATE`, and `DELETE` are revoked; authenticated read access remains appropriate for own-row reads.
- Activation RPC uses a PostgreSQL-supported serialization key or row-lock strategy; tests cover same-user serialization and different-user parallelism.

Generation tests:

- Authenticated generation fetches active cloud context for the verified user only.
- No active cloud context preserves no-context fallback.
- Inactive contexts are never injected.
- Planner-forbidden job context does not trigger cloud context fetch.
- Other user's active context cannot be used.
- Existing local desktop generation tests still pass.

Frontend tests:

- Protected job-target page redirects signed-out users.
- API helpers require access token and include bearer header.
- UI does not store access token in component state beyond existing Supabase session usage.
- Extract review form remains editable before save.
- Delete/activate buttons handle pending states and safe errors.

## Required Live Supabase Validation

Do not run during C4.1. Run after C4.2 migration/backend implementation in the dev Supabase project:

- Apply migration to dev only.
- Verify columns, defaults, constraints, and partial unique index.
- Verify RLS remains enabled.
- Verify authenticated direct writes are blocked and authenticated own-row reads still work.
- Verify service-role backend can create/list/update/delete for verified user.
- Verify user A cannot select/update/delete user B context.
- Verify activation RPC leaves exactly one active row after concurrent/repeated activation attempts.
- Verify deleting the active row leaves zero active rows and no error.

## Rollback Strategy

- Backend route rollback: unregister `/api/job-contexts` and keep local `/api/job-context` untouched.
- Migration rollback: drop added columns and activation RPC only after confirming no C4 data needs preservation; alternatively leave additive nullable/default columns in place if harmless.
- Frontend rollback: remove `/auth/job-targets` route/link/API helpers; existing auth/resume/desktop pages remain unaffected.
- Generation rollback: disable authenticated cloud generation branch and fall back to existing local generation path.
- Config rollback: no provider or STT/OpenAI/Groq config changes are required for C4.

## Proposed C4 Subphases

C4.1 - Audit, architecture, and implementation plan

- Complete in this document.
- No runtime behavior added.

C4.2 - Authenticated cloud Job Context backend + required migration

- Add migration if gaps are accepted.
- Add backend-only service/client.
- Add authenticated FastAPI routes.
- Add backend and migration tests.
- Do not build frontend management UI yet.
- Do not integrate generation yet except service method shape if needed.

C4.3 - Authenticated job-target/JD frontend management + extraction/review

- Add temporary functional React/Vite UI under authenticated auth routes.
- Add frontend API helpers and tests.
- Keep C14 visual redesign deferred.

C4.4 - Active cloud context retrieval + authenticated generation integration

- Add authenticated generation path/service branch.
- Use only verified user's active cloud context.
- Preserve local desktop fallback until C5.

C4.5 - Delete/activate/no-context lifecycle, live validation, security/regression closure

- Complete edge cases, live Supabase validation, regression suite, and status docs.

This structure matches the roadmap and keeps C5 out of C4.

## Exact C4.2 Implementation Scope

C4.2 should implement only:

- Supabase migration for schema gaps and activation RPC.
- Revoke authenticated direct `INSERT`/`UPDATE`/`DELETE` on `job_contexts` in a new forward migration while retaining appropriate authenticated read access and service-role writes.
- Backend cloud job-context models, client, service, and routes.
- Extraction service reuse for cloud extraction response shape.
- Unit tests and migration tests.
- Route registration.
- Status documentation update after validation.

C4.2 should not implement:

- React job-target UI.
- Generation integration.
- Desktop login/sync.
- Local-to-cloud migration.
- Provider/STT/OpenAI/Groq configuration changes.

## Files Expected to Change in C4.2

Likely:

- `supabase/migrations/<timestamp>_add_cloud_job_context_lifecycle.sql`
- `backend/app/cloud/cloud_job_context.py`
- `backend/app/api/job_contexts.py`
- `backend/app/main.py`
- `backend/tests/test_cloud_job_context_routes.py`
- `backend/tests/test_cloud_job_context.py`
- `backend/tests/test_supabase_migrations.py`

Possible small reuse edits:

- `backend/app/services/job_context_service.py`

Not expected in C4.2:

- `frontend/src/App.jsx`
- `frontend/src/auth/AuthScreens.jsx`
- `frontend/src/auth/authApi.js`
- `backend/app/api/generate.py`
- Electron files

## Risks and Open Questions

- Backend-only writes are locked for C4.2; the remaining implementation detail is the exact new migration filename and RPC body.
- `job_description` is locked as raw/full JD text for cloud persistence. The local extractor summary remains backward-compatible and may be exposed only as transient `job_description_summary`.
- Should `responsibilities` be an array of bullets or a single prose summary? Current cloud schema requires JSONB array; current local extraction returns a string.
- Should job context be injected when job policy allows it but profile policy forbids profile? Current generation code effectively requires profile context too. C4.4 must decide intentionally.
- Should uploaded JD files be retained in Supabase Storage? Current C4 requirements only need source-file metadata "if uploaded"; storing JD files adds privacy and retention scope. Recommendation: do not retain JD files in C4.2/C4.3 unless explicitly required.
- Live Supabase state was not queried in C4.1; schema verification is from migration history and tests only.
