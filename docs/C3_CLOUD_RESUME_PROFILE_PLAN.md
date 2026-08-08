# C3 Cloud Resume and Profile Plan

SAIIA C3 starts after C2 auth surface closure. C3.1 is planning and audit only:
no upload runtime, no C4 job-context cloud sync, no C5 desktop login/cloud
sync, no sessions, billing, payments, email provider, admin console, or final
website UI.

## Status

```text
[x] C3.1 audit/design complete
[x] C3.2 backend cloud resume API implemented
[x] C3.3 frontend authenticated upload/review UI implemented
[x] C3.4 cloud resume indexing/RAG ownership implemented
[x] C3.4.5 GPT-based resume extraction provider implemented
[x] C3.5 delete/rebuild/status + closure implemented
```

C3.4 migration note: `20260804134140_add_cloud_resume_chunk_activation.sql`
has been applied to live `saiia-dev`, so it remains unchanged. Its
pre-launch `SET NOT NULL` and normal index creation are acceptable for the tiny
development dataset; future production-scale lock mitigation should use a
separate migration strategy. Follow-up function/RPC corrections use
`20260804151715_fix_cloud_resume_activation_profile_parsing.sql` and
`20260804162315_preserve_profile_fields_on_cloud_resume_activation.sql`
instead of rewriting applied history. The latest activation RPC preserves
existing profile values when a partial `confirmed_profile` omits fields, while
explicit submitted empty values may still clear the submitted fields.

C3 product goal:

```text
Authenticated user
-> Upload resume
-> Validate file
-> Store private resume file
-> Extract text
-> Parse structured profile
-> Show editable review screen
-> User confirms
-> Build/rebuild user-owned resume index
-> Activate cloud profile and ready resume
-> Mark resume ready
```

## Audit Findings

Backend local resume routes:

- `backend/app/api/resume.py` currently exposes local desktop resume endpoints
  under `/api/resume`.
- `POST /api/resume/extract` accepts `UploadFile`, reads bytes, and calls
  `ResumeParserService.extract_profile()`.
- `POST /api/resume/index`, `GET /api/resume/index/status`, and
  `DELETE /api/resume/index` use `ResumeIndexService`.
- These routes are intentionally unauthenticated today and serve the local
  desktop/profile-setup flow. C3 must not break or force-login this surface.

Resume extraction services:

- `backend/app/services/resume_service.py` already validates PDF/DOCX/TXT by
  extension, rejects empty files, enforces a 5 MB limit, extracts text with
  PyMuPDF, python-docx, or text decoding, and normalizes structured profile
  fields.
- `backend/app/services/resume_parser_service.py` already selects Affinda or
  local extraction, preserves local fallback behavior, reports parser metadata,
  missing fields, review-required state, and extracted text length.
- These services can be reused for C3. They must be wrapped by authenticated
  cloud endpoints instead of rewritten.

C3.4.5 GPT extraction provider:

- `RESUME_PARSER_PROVIDER=gpt` selects backend-only GPT structured extraction.
- `RESUME_GPT_PARSER_ENABLED=true` enables the provider when `OPENAI_API_KEY`
  and `RESUME_GPT_MODEL` are available.
- Default model: `RESUME_GPT_MODEL=gpt-5-mini`.
- Default timeout: `RESUME_GPT_TIMEOUT_SECONDS=20`.
- Default input cap: `RESUME_GPT_MAX_INPUT_CHARS=30000`.
- GPT receives deterministic local text extraction output only; raw
  PDF/DOCX bytes are not sent directly to GPT.
- If GPT config is missing, times out, returns invalid JSON, or fails schema
  validation, the parser falls back to local extraction and preserves the
  editable review flow.
- GPT/OpenAI keys stay backend-only. The frontend receives only normalized
  editable fields and provider/fallback metadata.

Local resume index behavior:

- `backend/app/services/resume_index_service.py` builds a local JSON index at
  `tmp/resume_index.json`.
- The local index chunks profile/resume sections, scores retrieval in memory,
  and has build/status/delete behavior.
- C3 must not reuse the single local file for cloud users. The chunking and
  scoring logic can be reused or extracted, but cloud persistence must write
  user-owned `resume_chunks` rows and retrieval must filter by `user_id`.

Local candidate profile behavior:

- `backend/app/main.py` stores the desktop-local profile in
  `backend/candidate_profile.json`.
- `POST /api/profile` saves local profile fields and attempts to build the
  local resume index.
- `GET /api/profile` loads the local desktop profile.
- `/profile-setup` serves `backend/app/templates/profile_setup.html`; that page
  uploads to `/api/resume/extract`, reviews an unsaved draft, saves to
  `/api/profile`, and uses local index build/delete endpoints.
- C3 cloud profile saving must not replace this local desktop flow until C5
  intentionally handles desktop login/cloud sync.

Frontend auth state:

- C2 auth screens live in `frontend/src/auth/AuthScreens.jsx`.
- `frontend/src/auth/authApi.js` fetches the current user and profile bootstrap
  with a Supabase access token fetched at request time.
- C3 cloud upload/review UI should follow the same pattern: fetch the current
  Supabase session at request time, pass `Authorization: Bearer <token>`, and
  never store raw access tokens in React state.

Supabase schema and storage:

- C1 created `profiles`, `resumes`, `resume_chunks`, `job_contexts`, and
  `user_settings`.
- `profiles.user_id` and `user_settings.user_id` are unique.
- `resumes` has `storage_path`, filename, MIME, size, parser status,
  extraction status, index status, and review flag.
- `resume_chunks` references `resumes(id)` with cascade delete and has
  `user_id`, `section`, `chunk_text`, nullable JSONB `embedding`, JSONB
  `metadata`, and `created_at`.
- C1.3 enabled RLS and own-row policies on all five tables.
- C1.3 created private `resumes` and `exports` buckets. Storage policy requires
  the first object path segment to equal `auth.uid()`.
- C2.3 granted PostgREST table privileges to `authenticated` and
  `service_role`; service role remains backend-only and bypasses RLS.

Backend auth boundary:

- `backend/app/auth/supabase_auth.py` provides `get_current_user()` and
  `CurrentUserDep`.
- C3 authenticated routes must derive `user_id` only from `CurrentUserDep`.
- Frontend-supplied `user_id` must be ignored or rejected.

## Required C3.2 Schema Contract

C3.2 must add explicit ready/current markers before implementing runtime upload
behavior. The current C1 `resumes` table has parser, extraction, index, and
review fields, but it does not yet have enough state to safely define the
current resume.

C3.2 implementation note: migration
`20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql` adds these
markers, backfills existing rows, adds named lifecycle constraints, adds the
one-active-resume partial unique index, and narrows direct authenticated write
permissions so browser clients cannot bypass backend lifecycle rules.

Required migration planning for C3.2:

C3.2 must add these columns before runtime writes depend on them. The migration
must be null-safe: add columns with safe defaults or temporary nullable state,
explicitly backfill existing rows, and apply `NOT NULL` constraints only after
the backfill has completed.

- `resumes.status`: top-level lifecycle status using exactly this enum:
  `uploaded`, `extracting`, `needs_review`, `indexing`, `ready`, `failed`,
  `timeout`, `cancelled`, `deleted`.
- `resumes.is_active`: boolean marker for the single active ready resume per
  user.
- `resumes.confirmed_at`: timestamp set only after the user confirms reviewed
  fields.
- `resumes.extraction_attempt`: integer or UUID attempt marker used to reject
  stale extraction/provider writes.
- `resumes.confirmed_profile`: JSONB server-owned candidate profile snapshot
  that stores reviewed normalized fields before activation.
- `resumes.active_chunk_generation`: generation ID for the chunk generation
  currently used by retrieval.
- failure fields with safe non-secret values only: `failure_code`,
  `failure_message`, `failed_at`, and `last_error_at`.

Required database constraints and indexes:

```sql
ALTER TABLE public.resumes
  ADD CONSTRAINT resumes_status_check
  CHECK (
    status IN (
      'uploaded',
      'extracting',
      'needs_review',
      'indexing',
      'ready',
      'failed',
      'timeout',
      'cancelled',
      'deleted'
    )
  );

ALTER TABLE public.resumes
  ADD CONSTRAINT resumes_active_ready_check
  CHECK (is_active = false OR status = 'ready');

CREATE UNIQUE INDEX resumes_one_active_per_user_idx
  ON public.resumes (user_id)
  WHERE is_active = true;
```

- Parser, extraction, provider, and index diagnostic statuses are separate
  fields and do not replace this top-level `resumes.status`.

State contract:

- Only `status='ready'` may have `is_active=true`.
- Only one active ready resume may exist per user.
- A new upload starts inactive.
- A resume may become active only after upload, extraction, user confirmation,
  and index build/rebuild succeed.
- Previous active resume remains active when a new upload, extraction,
  confirmation, or index rebuild fails.
- Failed, timed-out, or cancelled resumes must not become active.
- Retrieval should use the active ready resume unless a later C3
  endpoint explicitly supports choosing another owned resume.
- Deactivating the old resume and activating the new ready resume must happen
  atomically through a transactional RPC or direct database transaction, not
  separate REST calls.

Allowed top-level status transitions:

- `uploaded -> extracting`
- `uploaded -> failed`
- `uploaded -> deleted`
- `extracting -> needs_review`
- `extracting -> failed`
- `extracting -> timeout`
- `extracting -> cancelled`
- `extracting -> deleted`
- `needs_review -> indexing`
- `needs_review -> failed`
- `needs_review -> deleted`
- `indexing -> ready`
- `indexing -> failed`
- `indexing -> timeout`
- `indexing -> cancelled`
- `indexing -> deleted`
- `ready -> deleted`
- `failed -> deleted`
- `timeout -> deleted`
- `cancelled -> deleted`

Allowed compare-and-set retry transitions:

- `needs_review -> extracting`
- `failed -> extracting`
- `timeout -> extracting`
- `cancelled -> extracting`
- `failed -> indexing`, only when `confirmed_profile` and candidate
  chunks/generation preconditions are valid
- `timeout -> indexing`, only when `confirmed_profile` and candidate
  chunks/generation preconditions are valid
- `cancelled -> indexing`, only when `confirmed_profile` and candidate
  chunks/generation preconditions are valid

Retries must increment or replace `extraction_attempt` for extraction retry,
create a new `generation_id` for indexing retry, and use compare-and-set status
guards. Retries must never activate stale attempts/generations, overwrite
deleted records, or blindly overwrite terminal states. `deleted` is terminal.
The current C3.1 plan chooses existing-row retry with compare-and-set guards. If
C3.2 later chooses new-row retry instead, C3.2 must update endpoint,
idempotency, and test contracts before implementation.

## Architecture Decision

C3 should add authenticated cloud resume routes beside the existing local
desktop routes.

Selected route boundary:

- Keep existing local `/api/resume/*`, `/api/profile`, and `/profile-setup`
  behavior unchanged.
- Add a new authenticated cloud route group under `/api/resumes`.
- Use `CurrentUserDep` on every `/api/resumes/*` route.
- Use backend-only Supabase REST/storage access with `SUPABASE_SERVICE_ROLE_KEY`
  for table writes and storage object operations.
- Continue deriving all `user_id` values from verified JWTs before any
  service-role operation.

Why backend service-role access:

- Existing code already uses backend-only Supabase REST for C2.3 bootstrap.
- It avoids exposing service-role credentials to the browser.
- It lets the backend orchestrate metadata writes, storage upload/delete,
  extraction status, profile confirmation, and chunk rebuild without adding a
  new database dependency.
- Because service role bypasses RLS, every C3 service method must require a
  `user_id` argument from `CurrentUserDep` and must filter by `user_id`.

Failure-safe behavior:

- Supabase Storage writes and Supabase REST table writes are separate
  operations, not one atomic transaction.
- Each step must write safe status transitions so partial completion is
  visible and retryable.
- Upload failure after metadata creation should mark the `resumes` row failed
  or delete the unused metadata row; it must not leave an active resume.
- Metadata failure after storage upload should delete the uploaded object where
  possible, or mark it for cleanup/reconciliation without exposing the object.
- Confirm failure while writing `resumes.confirmed_profile` must be retryable
  and must not update `profiles` or activate a different resume.
- Index rebuild must build replacement chunks first or stage them safely; the
  existing active chunks must remain usable until the new rebuild succeeds.
- Delete should be idempotent: missing storage object, missing chunks, or
  already-deleted metadata should produce a safe final deleted/not-found state
  for the same user, not cross-user access.
- C3.2/C3.4 tests must cover partial failures for upload, confirm, rebuild,
  and delete.

Operation identity and idempotency:

- Upload operation identity is `resume_id` plus deterministic storage path.
- Extraction operation identity is `resume_id + extraction_attempt`.
- Chunk rebuild operation identity is `resume_id + generation_id`.
- Activation operation identity is `resume_id + generation_id`.
- Retries use the same operation identity where safe.
- Writes use compare-and-set status transitions.
- No retry may activate a stale resume, stale extraction attempt, or stale
  chunk generation.

Storage upload and reconciliation plan:

- Prefer metadata-first: create the `resumes` row with `status='uploaded'` and
  deterministic `storage_path` before uploading the file.
- If storage upload fails, mark the resume `failed` or `deleted` safely.
- If storage upload succeeds but status update fails, reconciliation can
  inspect the metadata row and object path and repair/fail safely.
- If an orphan storage object can exist, define a deterministic orphan sweeper
  by path prefix `{user_id}/{resume_id}/...` and require cleanup verification
  in live validation.

Confirmation/activation reconciliation:

- `POST /api/resumes/{resume_id}/confirm` writes reviewed normalized fields
  only to `resumes.confirmed_profile`; it does not update `profiles`.
- Profile upsert/update and resume activation are atomic during the C3.4
  `POST /api/resumes/{resume_id}/confirm` activation path after chunks are
  built.
- Preferred C3 plan: upsert the `profiles` row from
  `resumes.confirmed_profile` inside the same activation transaction, because
  a user may not have a cloud `profiles` row yet.
- If a later implementation does not upsert, it must verify that the profile
  update affects exactly one row and abort activation otherwise.
- Avoid any state where `profiles` is upserted/updated without the same
  transaction also updating resume/chunk activation state.
- C3.4 uses a backend-only transactional RPC behind
  `POST /api/resumes/{resume_id}/confirm` for profile upsert, ready status,
  active resume switch, and chunk-generation switch.

## Endpoint Plan

Evaluate these endpoints for C3.2/C3.3; do not implement during C3.1.

```text
POST   /api/resumes
GET    /api/resumes/current
GET    /api/resumes/review-candidate
POST   /api/resumes/{resume_id}/extract
POST   /api/resumes/{resume_id}/confirm
GET    /api/resumes/{resume_id}/status
DELETE /api/resumes/{resume_id}
```

C3.2 implemented the backend-only subset:

- `POST /api/resumes`
- `GET /api/resumes/current`
- `GET /api/resumes/review-candidate`
- `GET /api/resumes/{resume_id}/status`
- `POST /api/resumes/{resume_id}/extract`
- `POST /api/resumes/{resume_id}/confirm`

C3.2 intentionally did not add frontend upload/review UI, cloud index
activation, delete polish, desktop sync, sessions, billing, payment, email,
admin, or final website UI. C3.4 implements activation through
`POST /api/resumes/{resume_id}/confirm`; a separate `/index` route is not part
of the implemented C3.4 contract and may only be reconsidered later for C3.5
rebuild/delete/status work.

Recommended behavior:

- `POST /api/resumes`: authenticate, validate file, create resume metadata row,
  upload the private file to Supabase Storage, and return safe resume metadata.
- `GET /api/resumes/current`: return only the active ready resume where
  `user_id = current_user.user_id`, `is_active = true`, and `status = 'ready'`.
  It must not return `needs_review`, `uploaded`, `extracting`, or `indexing`
  candidates. If there is no active ready resume, return an empty/not-ready
  state.
- `GET /api/resumes/review-candidate`: return the latest `needs_review` resume
  for the current user ordered by `updated_at desc`. This endpoint never
  replaces `/api/resumes/current`.
- `POST /api/resumes/{resume_id}/extract`: authenticate, check `user_id`,
  download/read the stored private file through backend storage, run existing
  extraction services, update safe extraction status, and return editable
  request-scoped draft profile fields.
- `POST /api/resumes/{resume_id}/confirm`: authenticate, check `user_id`, verify
  server-owned preconditions, store reviewed normalized fields as
  `resumes.confirmed_profile`, build `resume_chunks` for that resume with a new
  `generation_id`, then activate the resume/profile/chunk generation
  atomically only after rebuild succeeds. The activation transaction
  upserts/updates `profiles` from `resumes.confirmed_profile`, sets the
  candidate resume `status='ready'`, sets candidate `is_active=true`,
  deactivates the previous active resume for the same user, and switches
  `active_chunk_generation`.
- `GET /api/resumes/{resume_id}/status`: authenticate, check `user_id`, return
  parser/extraction/index/review status.
- `DELETE /api/resumes/{resume_id}`: authenticate, check `user_id`, delete the
  private storage object, resume metadata, and chunks. Profile deletion should
  be explicit; default delete should not silently erase a confirmed profile.

## Storage Path Convention

Use the existing C1.3 policy-compatible convention:

```text
{user_id}/{resume_id}/{safe_filename}
```

The `resumes` bucket name comes from `SUPABASE_RESUME_BUCKET`, defaulting to
the configured `resumes` bucket. The database `resumes.storage_path` stores the
object path without bucket name.

Rules:

- `safe_filename` must be sanitized to a basename only.
- Strip path separators, drive letters, control characters, and confusing
  Unicode/path traversal content.
- Prefer `resume_id` in the path so new uploads do not collide.
- Never return signed URLs unless a later phase explicitly needs short-lived
  downloads.

## File Validation

Reuse `ResumeService.validate_upload()` for extension, empty file, and 5 MB
size checks unless C3 intentionally raises the limit to match the C1 storage
bucket 10 MB limit.

C3 backend upload validation must also verify:

- extension allowlist: `.pdf`, `.docx`, `.txt`
- MIME allowlist matching the C1.3 bucket policy
- non-empty content
- file size limit
- parseable PDF/DOCX/TXT content
- low-text/scanned PDFs produce safe review/failure state
- corrupt files fail without creating a ready resume
- dangerous filenames and path traversal are rejected or sanitized

## Timeout and Cancellation Rules

C3.2 must define one end-to-end extraction timeout covering:

- local text extraction
- parser provider call
- provider fallback
- safe cloud status update

Rules:

- Timeout or cancellation prevents `confirmed_at` from being set, prevents
  `status='ready'`, and prevents `is_active=true`.
- Where a provider or local task supports cancellation/stop, C3 should stop
  in-flight work after timeout/cancel.
- Where cancellation is not supported, the backend must ignore late completion
  for activation purposes if the resume has already timed out/cancelled.
- Timeout/cancel must persist a safe failed/timeout status and return a safe
  failure response for review UI.
- Timeout/cancel responses must not include raw provider payloads, raw resume
  text, tokens, or service-role details.
- The previous active resume/profile/chunks remain active when a new extraction
  times out or is cancelled.

Extraction attempt guard:

- Each extraction run increments or assigns `resumes.extraction_attempt`.
- Worker/provider/local extraction writes must include the attempt ID.
- Status updates, draft readiness, `resumes.confirmed_profile` writes, and
  chunk writes are accepted only when `user_id` matches, `resume_id` matches,
  attempt ID matches current `resumes.extraction_attempt`, and the resume is
  still in an allowed non-terminal state.
- Late writes after timeout, cancel, failure, or deletion must be rejected,
  including stale completed statuses and stale draft data.

## Profile Mapping

Map current local profile fields into the C1 `profiles` table:

- `full_name` -> `profiles.full_name`
- `current_title` / `target_role` / `role` -> `profiles.headline`
- normalized `professional_summary` -> `profiles.summary`
- `top_skills` / `skills` -> `profiles.skills` JSONB array
- `technical_skills` -> `profiles.technical_skills` JSONB array
- `soft_skills` -> `profiles.soft_skills` JSONB array
- `education`, `degree`, `branch`, `college`, `university`,
  `graduation_year` -> `profiles.education` JSONB array/object entries
- `experience` / `work_experience` -> `profiles.experience` JSONB array
- `projects` -> `profiles.projects` JSONB array
- `achievements` -> `profiles.achievements` JSONB array
- `certifications` -> `profiles.certifications` JSONB array
- `tools_frameworks` -> `profiles.tools_frameworks` JSONB array

Do not map the local compatibility `resume` field or raw extracted resume text
into `profiles.summary`. `profiles.summary` stores only the normalized
professional summary reviewed by the user. Full raw text stays in private resume
storage, request-scoped extraction memory, or user-owned `resume_chunks` only.

## Review and Confirmation Rules

- Extraction results are drafts until the user confirms.
- C3.2 extraction drafts are request-scoped.
- Do not persist unconfirmed extraction data into `profiles`.
- `POST /api/resumes/{resume_id}/extract` returns editable draft fields.
- `POST /api/resumes/{resume_id}/confirm` receives user-reviewed normalized
  fields.
- Before accepting reviewed fields, `POST /api/resumes/{resume_id}/confirm`
  must verify the resume belongs to the current user, `status='needs_review'`,
  the request attempt ID matches current `resumes.extraction_attempt`, the
  resume is not `failed`, `timeout`, `cancelled`, `deleted`, `uploaded`,
  `extracting`, `indexing`, or `ready`, and the stored file still exists if the
  confirmation flow needs it.
- Reject confirmation for pending, failed, stale, timeout, cancelled, deleted,
  mismatched-attempt, or already-active resumes.
- If the browser refreshes or loses the extraction draft before confirm, the
  user must re-run extraction; C3.2 should not depend on persisted unconfirmed
  profile drafts.
- Confirmed profile activation must use the authenticated user's `user_id`.
- Frontend must never send a trusted `user_id`.
- Extraction failure must not overwrite an existing valid profile.
- A new upload may create a new `resumes` row, but older active resume/index
  state changes only when the candidate resume becomes ready through atomic
  activation.
- If user uploads a new resume and extraction fails, the previous active
  profile and indexed chunks remain active.

## Profile Consistency With Active Resume

The single `profiles` row must not be updated independently before the
candidate resume becomes active.

Required contract:

- `POST /api/resumes/{resume_id}/extract` returns request-scoped editable draft
  fields.
- The frontend lets the user review/edit those fields.
- `POST /api/resumes/{resume_id}/confirm` validates server-owned preconditions
  and stores the reviewed normalized fields as `resumes.confirmed_profile`.
- C3.4 implements indexing/activation inside
  `POST /api/resumes/{resume_id}/confirm`: after confirmation writes the
  candidate snapshot, the backend builds replacement chunks and then performs
  one atomic activation transaction:
  upsert/update `profiles` from `resumes.confirmed_profile`, set candidate
  resume `status='ready'`, set candidate resume `is_active=true`, deactivate
  the previous active resume for the same user, and switch active chunk
  generation.
- If indexing or activation fails, the previous active resume, previous profile
  fields, and previous chunks remain unchanged; the candidate remains
  non-active and is marked failed/retryable as appropriate.
- Do not persist unconfirmed extraction draft data into `profiles`.

## Resume Chunk and Retrieval Plan

C3 cloud indexing should reuse the local chunking strategy where practical,
but persist chunks in `resume_chunks`:

- C3.4 must add `resume_chunks.generation_id`.
- C3.2/C3.4 must add `resumes.active_chunk_generation`.
- Rebuild creates chunks with a new `generation_id`.
- Retrieval filters by `user_id`, active `resume_id`, and
  `generation_id = resumes.active_chunk_generation`.
- preserve existing chunks until a new rebuild succeeds
- replace chunks for `(user_id, resume_id)` only after the replacement set is
  successfully built, or use a safe staging/delete-in-transaction pattern if a
  later database path supports it
- insert new chunks with `user_id`, `resume_id`, `section`, `chunk_text`, and
  JSONB `metadata`
- keep `embedding` null/JSONB until a pgvector decision is made
- set `resumes.index_status` to `indexed`, `failed`, or `needs_rebuild`
- retrieval must filter by `user_id`
- retrieval must filter by the active ready `resume_id`
- never read chunks by `resume_id` alone

Chunk cutover must be atomic:

- Use a transactional RPC that inserts/switches/deactivates in one database
  transaction, or use generation identifiers with an atomic active-generation
  switch.
- Old chunks remain readable until the new generation is complete and switched
  active.
- Failed rebuilds must leave old chunks active.

## Delete Behavior

Default delete for `DELETE /api/resumes/{resume_id}`:

- requires verified user
- checks `resumes.user_id = current_user.user_id`
- removes object from the private `resumes` bucket
- deletes `resume_chunks` for that user/resume
- keeps a tombstoned `resumes` metadata row with `status = 'deleted'`,
  `is_active = false`, and no active chunk generation
- retains `resumes.confirmed_profile` on the tombstoned metadata row until C15
  privacy/retention/deletion rules define broader erasure behavior
- leaves the confirmed `profiles` row intact unless a later C15-governed
  request explicitly clears profile-derived fields and that behavior is
  implemented/test-covered

Account deletion and broader retention belong to C15.

## Local Desktop Compatibility

C3 must preserve:

- `/profile-setup`
- `/api/profile`
- `/api/resume/extract`
- `/api/resume/index`
- `/api/resume/index/status`
- `DELETE /api/resume/index`
- local `candidate_profile.json`
- local `tmp/resume_index.json`
- current answer generation profile/RAG behavior

C5 owns desktop login and cloud synchronization. Until C5, the desktop-local
flow remains usable without login.

## Security Rules

- Every `/api/resumes/*` cloud route requires a verified Supabase JWT.
- Backend derives `user_id` only from `get_current_user()`.
- Backend service-role key remains backend-only.
- Frontend may use only `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- Frontend must never receive storage service credentials or service-role keys.
- Do not log raw resume text, raw access tokens, refresh tokens, passwords, or
  service-role values.
- All table queries and storage paths must include current `user_id`.
- User A must never access user B resume files, metadata, chunks, profile, or
  extraction drafts.
- Raw extracted text must not be returned broadly; review responses should
  return editable structured fields and only the minimum text needed for user
  confirmation.
- C3.2 must revoke or narrow authenticated-role direct `INSERT`, `UPDATE`, and
  `DELETE` permissions for `resumes`, `resume_chunks`, `profiles`, and resume
  storage objects before cloud resume runtime is enabled.
- A browser using `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` must not be
  able to directly mutate resume lifecycle state, chunks, resume-derived
  profile fields, or storage objects in ways that bypass backend rules.
- Permitted mutations must go through the FastAPI backend with
  `get_current_user()` or an authorized RPC boundary with strict server-side
  ownership, status, attempt, and generation checks.
- Direct browser reads may remain only where safe, explicitly scoped by RLS,
  and not broad enough to expose raw resume text or cross-user data.

## C3 Subphases

- C3.1 audit/design: inspect existing local resume/profile/index/auth/cloud
  behavior and document the implementation plan.
- C3.2 backend cloud resume API: add authenticated upload/status/extract/confirm
  route foundations and backend-only Supabase storage/table services.
- C3.3 frontend authenticated upload/review UI: add temporary authenticated UI
  for upload, extraction draft review, confirmation, and status. Implemented
  under `/auth/resume`; it consumes C3.2 routes, confirms reviewed fields, and
  does not send `raw_resume_text`.
- C3.4 cloud resume indexing/RAG ownership: implemented through the existing
  confirm route. It persists user-owned chunks with `generation_id`, activates
  the ready resume through a backend-only transactional RPC, and adds a
  service-level retrieval method that filters by `user_id`, active resume, and
  active chunk generation.
- C3.4.5 GPT-based resume extraction provider: implemented backend-only GPT
  structured extraction after deterministic local text extraction, before the
  existing editable review/confirm/indexing flow. Default model is
  `gpt-5-mini`; missing GPT config or provider failures fall back to local
  extraction.
- C3.5 delete/rebuild/status + closure: implemented authenticated delete,
  rebuild-index, truthful status/current/review behavior, frontend controls,
  focused tests, and manual smoke checklist.

## Implementation Checklist

- [x] Add backend cloud resume service boundary.
- [x] Add safe filename sanitizer.
- [x] Add authenticated cloud upload endpoint.
- [x] Store resume files in private Supabase Storage under
  `{user_id}/{resume_id}/{safe_filename}`.
- [x] Add C3.2 migration/backfill/constraints for `resumes.status`,
  `is_active`, `confirmed_at`, `extraction_attempt`, `confirmed_profile`,
  `active_chunk_generation`, and safe failure fields before runtime writes.
- [x] Revoke or narrow direct authenticated-role mutation permissions for
  resume lifecycle tables, profile resume-derived fields, chunks, and storage.
- [x] Insert/update `resumes` metadata with parser/extraction/index status.
- [x] Reuse `ResumeParserService` for extraction.
- [x] Add GPT structured extraction provider for higher-quality editable
  resume drafts without exposing API keys to frontend.
- [x] Return editable draft profile fields without marking them confirmed.
- [x] Confirm reviewed normalized fields into `resumes.confirmed_profile` only.
- [x] Upsert/update `profiles` only inside the atomic activation transaction
  after indexing succeeds.
- [x] Build/rebuild `resume_chunks` filtered by `user_id` and `resume_id`.
- [x] Add status behavior.
- [x] Add delete behavior.
- [x] Preserve existing local desktop routes.
- [x] Add focused backend tests.
- [x] Add frontend auth/upload tests during C3.3.
- [x] Add manual live Supabase validation checklist for saiia-dev.

## Acceptance Criteria

C3 is complete only when:

- authenticated users can upload supported resume files
- unsupported/empty/corrupt/oversized/low-text files fail safely
- uploaded files are private and user-owned
- resume metadata rows are user-owned
- extraction draft is shown for review before profile replacement
- confirmed profile updates the authenticated user's `profiles` row only during
  the atomic activation transaction after indexing succeeds
- extraction failure does not overwrite an existing valid profile
- resume chunks are rebuilt under the authenticated `user_id`
- retrieval never crosses users
- delete marks resume metadata deleted/inactive and removes the expected
  storage object and user-owned chunks
- existing local desktop resume/profile/RAG flow still works without login
- no service-role key reaches frontend or logs
- tests and manual validation pass

## Test Plan

Backend tests:

- missing/invalid token rejected for every `/api/resumes/*` route
- valid token uses `CurrentUser.user_id`
- frontend-supplied `user_id` is ignored/rejected
- C3.2 migration exposes `status`, `is_active`, `confirmed_at`,
  `extraction_attempt`, `confirmed_profile`, `active_chunk_generation`, and
  safe failure fields before upload runtime is enabled
- C3.2 migration backfills existing rows before applying `NOT NULL`
  constraints
- top-level status check constraint allows only `uploaded`, `extracting`,
  `needs_review`, `indexing`, `ready`, `failed`, `timeout`, `cancelled`, and
  `deleted`
- named `resumes_status_check` and `resumes_active_ready_check` constraints
  exist
- allowed status transitions use compare-and-set success/failure checks
- retry transitions increment/replace `extraction_attempt` or create a new
  `generation_id`, and never overwrite deleted records
- stale retry cannot overwrite terminal states
- partial unique index enforces one active resume per user
- check constraint enforces `is_active = false or status = 'ready'`
- old active resume deactivation and new ready resume activation happen in one
  transactional RPC or direct database transaction
- `/api/resumes/current` returns only `is_active=true` and `status='ready'`
- `/api/resumes/review-candidate` returns latest `needs_review` candidate and
  does not replace current resume
- previous active resume remains active when new upload/extract/confirm/index
  fails or times out
- file extension/MIME/size/empty/corrupt validation
- safe filename/path handling
- storage upload path includes current user and resume id
- service-role headers are backend-only and never returned
- extraction success returns request-scoped draft fields without confirming
  profile
- stale extraction attempt rejected
- extraction failure preserves existing profile
- extraction timeout/cancel persists safe failed/timeout status and prevents
  ready/active state
- confirm writes reviewed fields to `resumes.confirmed_profile`, builds chunks,
  and activates only through the C3.4 backend-only transaction
- confirm does not update `profiles` through loose REST writes
- activation upserts/updates `profiles` inside the same transaction that marks
  the candidate resume ready/active and switches the active chunk generation
- confirm rejected unless current status is `needs_review` with matching
  attempt ID
- confirm requires reviewed normalized fields and does not trust raw extraction
  state from the frontend
- chunk rebuild preserves current chunks until replacement succeeds
- chunk rebuild failure keeps old active generation
- activation transaction keeps previous profile/resume/chunks on failure
- partial failure tests cover upload, confirm, rebuild, and delete
- upload partial failure cleanup/reconciliation
- delete is idempotent and user-owned
- user A cannot access user B resume/status/chunks/profile
- authenticated anon-key direct insert to `resumes` is rejected
- authenticated anon-key direct update to `resumes.status` or
  `resumes.is_active` is rejected
- authenticated anon-key direct insert, update, or delete to `resume_chunks` is
  rejected
- authenticated anon-key direct update to resume-derived `profiles` fields is
  rejected unless it goes through the approved backend/RPC path
- direct browser storage object mutation is rejected or limited to the
  backend-only upload path
- backend/RPC mutation path works with a verified JWT and server-side user
  ownership checks

Frontend tests:

- upload/review UI requires an active Supabase session
- current session token is fetched at request time
- no raw token is stored in React state
- unsupported file state is visible
- review screen does not save until confirm
- status/delete/rebuild states are visible and safe
- `/` and `/profile-setup` remain unprotected

Manual validation:

- sign in to `http://localhost:5173/auth/dashboard`
- use only synthetic resume fixtures created for testing; do not upload real
  resume data, real candidate PII, or customer data
- for C3.4.5 GPT parser validation, use fixed sanitized synthetic resume
  fixtures only; do not use real resumes or real candidate PII
- record expected field-level values for each GPT fixture before testing:
  email, phone, top/technical/soft skills, education, experience, projects,
  achievements, and certifications
- C3.4.5 GPT validation passes only when the extracted values match the
  fixture criteria, `professional_summary` excludes header/contact text,
  achievements come only from explicit achievements/awards/honors sections,
  planned/in-progress work is not rewritten as completed work, and known weak
  fields improve over local fallback
- C3.4.5 GPT validation fails if GPT misses fields that are explicit in the
  fixture, invents unsupported facts, copies contact lines into summaries,
  duplicates training/projects into achievements, or performs no measurable
  improvement over local fallback for the known weak fields
- use only approved Supabase dev test accounts
- upload synthetic TXT, PDF, DOCX resumes through the C3 UI
- verify private object path in Supabase Storage
- verify `resumes` row belongs to the test user
- verify review screen appears before profile save
- confirm profile and verify `profiles` row does not update until successful
  index/activation
- rebuild index and verify `resume_chunks.user_id`
- verify rebuild keeps the current resume ready and changes
  `active_chunk_generation`
- verify successful activation updates or creates the test user's `profiles`
  row atomically with the active ready resume switch
- attempt a second user access check
- delete resume and verify cleanup of storage objects, `resumes`,
  `resume_chunks`, test profile rows, and candidate `confirmed_profile` or
  draft/candidate data if present during validation
- verify `GET /api/resumes/current` returns `ready:false` after deletion
- upload a fresh synthetic resume after deletion and confirm the flow still
  reaches ready state
- verify API responses and UI do not expose `raw_resume_text`, access tokens,
  service-role values, provider raw responses, or full chunk text
- confirm local `/profile-setup` still works without login

## Risks and Blockers

- Current C1 `profiles` table does not include every local compatibility field
  as a scalar column; C3 must map list-like/local fields into JSONB safely.
- `resumes` has no explicit `status`, `is_active`, or `confirmed_at` columns.
  C3.2 must add explicit ready/current markers before upload runtime is
  implemented.
- `resume_chunks.embedding` is JSONB placeholder; pgvector is not enabled.
  C3.4 should keep lexical/local-style retrieval unless a vector migration is
  explicitly approved.
- Supabase Storage uploads through REST need careful request handling and
  sanitized error logging.
- GPT resume extraction sends bounded text-only resume content from backend to
  OpenAI; no raw prompts, resume text, access tokens, service-role keys, or API
  keys may be logged or exposed to frontend.
- C1 currently grants authenticated owned-row/table and storage mutation paths;
  C3.2 must narrow those direct mutations before browser upload UI is enabled
  so users cannot bypass backend lifecycle, attempt, generation, and activation
  guards.
- Service role bypasses RLS, so backend tests must prove user-id filtering.
- Local desktop generation still reads `GET /api/profile`; cloud profile usage
  in desktop belongs to C5, not C3.
