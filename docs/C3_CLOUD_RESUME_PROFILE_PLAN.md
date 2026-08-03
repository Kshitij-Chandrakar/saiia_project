# C3 Cloud Resume and Profile Plan

SAIIA C3 starts after C2 auth surface closure. C3.1 is planning and audit only:
no upload runtime, no C4 job-context cloud sync, no C5 desktop login/cloud
sync, no sessions, billing, payments, email provider, admin console, or final
website UI.

## Status

```text
[~] C3.1 audit/design active
```

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
-> Save cloud profile
-> Build/rebuild user-owned resume index
-> Mark resume ready
```

## Resume State Contract

Resume "ready" and "current" states must be deterministic:

- **Ready state**: A resume is ready when `resumes.extraction_status = 'completed'` AND `resumes.review_status = 'confirmed'` AND `resumes.index_status = 'indexed'`. Only ready resumes are eligible for retrieval.
- **In-review state**: A resume is in-review when `resumes.extraction_status = 'completed'` AND `resumes.review_status IN ('pending', 'in_review')`. In-review resumes have extraction data available but are not yet confirmed.
- **Latest-ready selection**: `GET /api/resumes/current` returns the ready resume with the most recent `resumes.updated_at` (or `created_at` if `updated_at` is null) for the current user. If no ready resume exists, it returns the latest in-review resume. If neither exists, it returns null/404.
- **Previous resume retention**: When a new upload fails extraction or validation, the previous ready resume remains the current ready resume. A new upload only supersedes the previous ready resume when the new resume reaches ready state or is explicitly confirmed.
- **Failed upload handling**: If upload, extraction, or indexing fails, the resume row may be retained with `extraction_status = 'failed'` or `index_status = 'failed'`, but must never enter ready state. The previous confirmed profile and chunks remain active until a new resume is successfully confirmed and indexed.

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
  extraction status, profile confirmation, and chunk rebuild with explicit
  failure-safe behavior for C3 without adding a new database dependency.
- Because service role bypasses RLS, every C3 service method must require a
  `user_id` argument from `CurrentUserDep` and must filter by `user_id`.

### Operation Failure-Safe Guarantees

Each C3 operation must define idempotency, compensation, and status transitions:

- **Upload (`POST /api/resumes`)**: Idempotent by checking for existing `(user_id, storage_path)` before creating a new `resumes` row. If storage upload fails after metadata insert, the resume row remains with `extraction_status = null` or `'pending'` and is never marked ready. Retry behavior: frontend may retry upload; backend creates a new `resumes` row with a new `resume_id`. Partial failure: if metadata insert succeeds but storage upload fails, the resume row exists but cannot be extracted. Status: `extraction_status = 'pending'` or `'upload_failed'`.

- **Extract (`POST /api/resumes/{resume_id}/extract`)**: Idempotent by reading from existing storage and overwriting extraction status. If extraction fails (timeout, provider error, corrupt file), set `extraction_status = 'failed'` and preserve any previous ready resume. If extraction succeeds, set `extraction_status = 'completed'` and `review_status = 'pending'`. Retry behavior: safe to retry; extraction re-runs and updates status. Partial failure: if extraction starts but times out, set `extraction_status = 'failed'`. Never write extraction data to `profiles` unless confirmed.

- **Confirm (`POST /api/resumes/{resume_id}/confirm`)**: Idempotent by checking `review_status` before updating `profiles`. Only write to `profiles` if `extraction_status = 'completed'`. Set `review_status = 'confirmed'` after profile write succeeds. If profile write fails, leave `review_status = 'pending'` or `'in_review'` and allow retry. Partial failure: if profile write partially succeeds (unlikely with single-row upsert), retry should re-apply full profile data. Never overwrite a valid existing profile if extraction data is missing or failed.

- **Index/Rebuild (`POST /api/resumes/{resume_id}/index`)**: Preserve existing `resume_chunks` until rebuild succeeds. Workflow: (1) read existing chunks into memory or temporary state, (2) generate new chunks, (3) delete old chunks for `(user_id, resume_id)`, (4) insert new chunks, (5) set `index_status = 'indexed'`. If step 3 or 4 fails, set `index_status = 'failed'` and existing chunks remain (from before the delete). If delete succeeds but insert fails, chunks are lost; to prevent this, consider inserting new chunks first with a temporary marker, then deleting old chunks, then updating the marker (or accept that rebuild failure requires re-extraction). Idempotent by resume_id. Retry behavior: safe to retry; rebuild re-runs. Partial failure test: simulate insert failure after delete to verify recovery.

- **Delete (`DELETE /api/resumes/{resume_id}`)**: Delete in order: (1) storage object, (2) `resume_chunks`, (3) `resumes` row. If storage delete fails, log error but proceed with metadata/chunk delete (object may already be gone). If chunk delete fails, retry or leave orphaned chunks (cascade delete on `resumes` foreign key should handle this). Idempotent by checking existence before delete. Retry behavior: safe to retry; already-deleted resources return success. Never delete `profiles` row unless explicitly requested and confirmed by user.

Each operation must have tests covering: normal success, retry after partial failure, timeout/cancellation, and status transition verification.

## Endpoint Plan

Evaluate these endpoints for C3.2/C3.3; do not implement during C3.1.

```text
POST   /api/resumes
GET    /api/resumes/current
POST   /api/resumes/{resume_id}/extract
POST   /api/resumes/{resume_id}/confirm
POST   /api/resumes/{resume_id}/index
GET    /api/resumes/{resume_id}/status
DELETE /api/resumes/{resume_id}
```

Recommended behavior:

- `POST /api/resumes`: authenticate, validate file, create resume metadata row,
  upload the private file to Supabase Storage, and return safe resume metadata.
- `GET /api/resumes/current`: return the latest ready or in-review resume for
  the current user, without raw extracted text.
- `POST /api/resumes/{resume_id}/extract`: authenticate, check `user_id`,
  download/read the stored private file through backend storage, run existing
  extraction services, update `resumes.extraction_status` and
  `resumes.parser_metadata`, and return editable profile draft fields.
  **Extraction draft storage**: The editable extraction draft is
  request-scoped/ephemeral and not persisted to the database. Draft profile
  fields are returned in the response body for frontend review/editing only.
  Unconfirmed extraction data must never be written into `profiles` and must
  never overwrite an existing valid profile. Only user-confirmed data (via
  `POST /api/resumes/{resume_id}/confirm`) writes to `profiles`. If draft
  persistence is later required, add a `resumes.draft_profile` JSONB column with
  explicit ownership (`user_id`), lifecycle (cleared on confirm or expire), and
  access controls (never exposed outside the owning user's extract/confirm
  flow).
- `POST /api/resumes/{resume_id}/confirm`: authenticate, check `user_id`, save
  the user-reviewed profile fields to `profiles`, mark the resume review state,
  and avoid overwriting an existing valid profile if extraction failed or was
  never confirmed.
- `POST /api/resumes/{resume_id}/index`: authenticate, check `user_id`, rebuild
  `resume_chunks` for that resume, and set `index_status`.
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

## Extraction and Upload Timeout Policy

All extraction and upload operations must define end-to-end timeouts:

- **Upload timeout**: `POST /api/resumes` must complete file upload to Supabase Storage within 60 seconds (or configured limit). If timeout occurs, return HTTP 408 or 500, do not create a `resumes` row (or mark it `upload_failed`), and allow retry.

- **Extraction timeout**: `POST /api/resumes/{resume_id}/extract` must complete local text extraction, provider API calls (Affinda or fallback), and status updates within 120 seconds (or configured limit). If local extraction times out, set `extraction_status = 'failed'` and return safe error response. If provider API call times out, attempt local fallback if not already tried, then set `extraction_status = 'failed'` if all methods fail.

- **Cancellation propagation**: If the client cancels the request (connection closed), stop in-flight extraction work where possible (e.g., cancel provider API calls if the library supports it, stop local parsing loops). Set `extraction_status = 'cancelled'` or `'failed'`. Do not mark the resume as ready.

- **Timeout/cancellation result**: Any timeout or cancellation must prevent the resume from entering ready state. The resume row remains with `extraction_status IN ('failed', 'cancelled', 'timeout')` and `review_status` remains null or `'pending'`. Return a safe error response instructing the user to retry or upload a different file. Never write partial or incomplete extraction data to `profiles`.

- **Cloud status persistence**: On timeout or failure, persist the failure status to `resumes.extraction_status` and `resumes.parser_metadata` (with error details) so the user can view the failure reason via `GET /api/resumes/{resume_id}/status`. This prevents silent failures and allows retry decisions.

## Profile Mapping

Map current local profile fields into the C1 `profiles` table:

- `full_name` -> `profiles.full_name`
- `current_title` / `target_role` / `role` -> `profiles.headline`
- `professional_summary` -> `profiles.summary` (normalized summary text only; never full pasted resume)
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

**Raw resume text handling**: Do not save raw extracted resume text or full pasted resume content into `profiles.summary`. Only normalized, structured professional summary fields (e.g., 2-3 sentence career summaries extracted by the parser) should map to `profiles.summary`. Full resume text, if retained, must only go into `resume_chunks.chunk_text` (for retrieval) or remain in the private storage object. `profiles.summary` is for human-readable profile summaries, not raw document dumps.

## Review and Confirmation Rules

- Extraction results are drafts until the user confirms.
- Confirmed profile save must use the authenticated user's `user_id`.
- Frontend must never send a trusted `user_id`.
- Extraction failure must not overwrite an existing valid profile.
- A new upload may create a new `resumes` row and mark older resume/index
  state as superseded only when the new resume is confirmed or explicitly
  selected.
- If user uploads a new resume and extraction fails, the previous confirmed
  profile and indexed chunks remain active.

## Resume Chunk and Retrieval Plan

C3 cloud indexing should reuse the local chunking strategy where practical,
but persist chunks in `resume_chunks`:

- delete existing chunks for `(user_id, resume_id)` before rebuild
- insert new chunks with `user_id`, `resume_id`, `section`, `chunk_text`, and
  JSONB `metadata`
- keep `embedding` null/JSONB until a pgvector decision is made
- set `resumes.index_status` to `indexed`, `failed`, or `needs_rebuild`
- retrieval must filter by `user_id`
- retrieval may filter by active/latest confirmed `resume_id`
- never read chunks by `resume_id` alone

## Delete Behavior

Default delete for `DELETE /api/resumes/{resume_id}`:

- requires verified user
- checks `resumes.user_id = current_user.user_id`
- removes object from the private `resumes` bucket
- deletes `resume_chunks` for that user/resume
- deletes the `resumes` row
- leaves confirmed `profiles` row intact unless the request explicitly asks to
  clear profile-derived fields and that behavior is implemented/test-covered

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

## C3 Subphases

- C3.1 audit/design: inspect existing local resume/profile/index/auth/cloud
  behavior and document the implementation plan.
- C3.2 backend cloud resume API: add authenticated upload/status/extract/confirm
  route foundations and backend-only Supabase storage/table services.
- C3.3 frontend authenticated upload/review UI: add temporary authenticated UI
  for upload, extraction draft review, confirmation, and status.
- C3.4 cloud resume indexing/RAG ownership: persist user-owned chunks and add
  retrieval that filters by `user_id`.
- C3.5 delete/rebuild/status + closure: finish delete/rebuild/status behavior,
  run live/manual validation, and close C3.

## Implementation Checklist

- [ ] Add backend cloud resume service boundary.
- [ ] Add safe filename sanitizer.
- [ ] Add authenticated cloud upload endpoint.
- [ ] Store resume files in private Supabase Storage under
  `{user_id}/{resume_id}/{safe_filename}`.
- [ ] Insert/update `resumes` metadata with parser/extraction/index status.
- [ ] Reuse `ResumeParserService` for extraction.
- [ ] Return editable draft profile fields without marking them confirmed.
- [ ] Confirm reviewed profile into `profiles`.
- [ ] Build/rebuild `resume_chunks` filtered by `user_id` and `resume_id`.
- [ ] Add status and delete behavior.
- [ ] Preserve existing local desktop routes.
- [ ] Add focused backend tests and frontend auth/upload tests.
- [ ] Add manual live Supabase validation checklist for saiia-dev.

## Acceptance Criteria

C3 is complete only when:

- authenticated users can upload supported resume files
- unsupported/empty/corrupt/oversized/low-text files fail safely
- uploaded files are private and user-owned
- resume metadata rows are user-owned
- extraction draft is shown for review before profile replacement
- confirmed profile saves to the authenticated user's `profiles` row
- extraction failure does not overwrite an existing valid profile
- resume chunks are rebuilt under the authenticated `user_id`
- retrieval never crosses users
- delete removes expected file, metadata, and chunks
- existing local desktop resume/profile/RAG flow still works without login
- no service-role key reaches frontend or logs
- tests and manual validation pass

## Test Plan

Backend tests:

- missing/invalid token rejected for every `/api/resumes/*` route
- valid token uses `CurrentUser.user_id`
- frontend-supplied `user_id` is ignored/rejected
- file extension/MIME/size/empty/corrupt validation
- safe filename/path handling
- storage upload path includes current user and resume id
- service-role headers are backend-only and never returned
- extraction success creates draft/status without confirming profile
- extraction failure preserves existing profile
- confirm saves profile fields to the current user only
- chunk rebuild deletes/replaces only current user's chunks for that resume
- delete removes current user's file/metadata/chunks
- user A cannot access user B resume/status/chunks/profile

Frontend tests:

- upload/review UI requires an active Supabase session
- current session token is fetched at request time
- no raw token is stored in React state
- unsupported file state is visible
- review screen does not save until confirm
- status/delete/rebuild states are visible and safe
- `/` and `/profile-setup` remain unprotected

Manual validation:

**IMPORTANT: Use only synthetic/fixture resume data and approved test accounts. Never use real personal resume data for testing.**

- sign in to `http://localhost:5173/auth/dashboard` using an approved test account (e.g., `test-user-c3@example.com` or configured test account)
- upload synthetic TXT, PDF, DOCX resume fixtures (create test files with fake names, skills, experience) through the C3 UI
- verify private object path in Supabase Storage under `{test_user_id}/{resume_id}/`
- verify `resumes` row belongs to the test user (check `user_id` matches)
- verify review screen appears before profile save
- confirm profile and verify `profiles` row updates with test data only
- rebuild index and verify `resume_chunks.user_id` matches test user
- attempt a second user access check (sign in as different test user, verify cannot access first user's resume)
- delete resume and verify object/chunks/metadata removal
- confirm local `/profile-setup` still works without login
- **cleanup verification**: After all manual validation steps, verify complete cleanup of test data:
  - delete all storage objects under test user paths in `resumes` bucket
  - delete all `resumes` rows for test users
  - delete all `resume_chunks` rows for test users
  - delete or reset `profiles` rows for test users to empty/default state
  - document cleanup steps in validation notes

## Risks and Blockers

- Current C1 `profiles` table does not include every local compatibility field
  as a scalar column; C3 must map list-like/local fields into JSONB safely.
- `resumes` has no explicit `is_active` column. C3 must decide active/current
  behavior by latest confirmed resume or add a later migration only if needed.
- `resume_chunks.embedding` is JSONB placeholder; pgvector is not enabled.
  C3.4 should keep lexical/local-style retrieval unless a vector migration is
  explicitly approved.
- Supabase Storage uploads through REST need careful request handling and
  sanitized error logging.
- Service role bypasses RLS, so backend tests must prove user-id filtering.
- Local desktop generation still reads `GET /api/profile`; cloud profile usage
  in desktop belongs to C5, not C3.
