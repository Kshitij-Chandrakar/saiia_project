# SAIIA Cloud Product Implementation Roadmap

**Product:** SAIIA â€” Smart AI Interview Assistant  
**Document type:** Detailed implementation roadmap and execution source of truth  
**Track:** Desktop stabilization â†’ Cloud account system â†’ Website integration â†’ Session intelligence â†’ Subscription and release  
**Version:** 1.1  
**Last updated:** 2026-08-09
**Created:** 2026-07-10  
**Current active phase:** C6.2A - Startup Login Screen implemented locally with a dev/local memory-only desktop handoff store; production shared atomic TTL-backed handoff storage is deferred to C16.1 Production Auth Hardening; broader startup shell, resume/job-target selection UI, C4.4 generation integration, cloud sync engine, and local/cloud data migration are not started
**Primary owner:** Project developer  
**Implementation support:** Codex / engineering assistant  
**UI/UX responsibility:** External UI/UX designer provides Figma designs only  

---

## 1. Purpose of This File

This document defines the step-by-step implementation plan for the next major SAIIA build track.

It exists to prevent:

- phase confusion
- scope drift
- duplicate implementation
- accidental rewrites
- missing backend work
- frontend/backend ownership confusion
- premature pricing work
- hallucinated future requirements
- marking a phase complete without validation

This roadmap covers the work that the developer and Codex will implement. It does **not** assign backend, database, authentication, email, payment, AI, or integration work to the UI/UX designer.

The UI/UX designer will only provide:

- Figma screens
- navigation flows
- component states
- responsive layouts
- design tokens
- interaction references
- loading, success, empty, and error states

The developer will implement and integrate everything else.

---

## 2. Relationship to Existing SAIIA Documents

Use these documents together:

1. `SAIIA_PRODUCTION_PRD_CORE.md`
2. `SAIIA_PRODUCTION_TECHSTACK.md`
3. `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`
4. `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md` - this file
5. `SAIIA_PRODUCTION_PHASES_TRACKER.md`

### Source-of-truth rule

- The Production PRD defines user-visible product behavior and requirements.
- The Production Tech Stack defines approved technologies and technical boundaries.
- The Screen Intelligence Architecture defines detailed OCR/Extension architecture, pairing, active-tab extraction, Extraction Result Envelope, Normalized Question, language/submission-mode resolution, SaaS integration, privacy, and security rules.
- This file controls implementation order, phase ownership, prerequisites, deliverables, tests, and exit gates.
- The existing Production Phases Tracker records completed desktop/core work and references this roadmap for C0.9 implementation status.

If a conflict appears:

1. product and privacy rules win
2. production PRD wins for product behavior
3. production tech stack wins for approved technologies
4. screen intelligence architecture wins for OCR and Extension architecture details
5. this roadmap wins for phase order and implementation gates
6. the tracker preserves historical completed work and must not become a competing roadmap
## 3. Product Direction

SAIIA will become one connected product with three major surfaces.

```text
Public Website
    â†“
User Account Dashboard
    â†“
Desktop Interview Assistant
```

### Public website responsibilities

- explain SAIIA
- show features and pricing
- allow signup/login
- provide app download
- provide help and legal information

### User dashboard responsibilities

- resume upload and profile review
- job/company context
- interview session history
- transcripts
- AI notes
- Ask AI about a session
- usage and subscription
- settings, privacy, exports, and deletion

### Desktop app responsibilities

- real-time interview session controls
- microphone and system-audio capture
- question transcription
- question classification
- personalized answer generation
- overlay answer display
- session creation and synchronization
- transcript/answer event upload
- offline-safe behavior where practical

### Backend responsibilities

- authentication verification
- data ownership enforcement
- resume extraction and RAG
- job-context extraction
- transcription and answer generation
- interview session storage
- transcript storage
- follow-up context resolution
- AI notes generation
- feature gates and usage limits
- payment webhooks
- email events
- privacy and deletion operations

---

## 4. Locked Architectural Direction

The intended production architecture is:

```text
Website Frontend
        |
        | authenticated HTTPS requests
        v
FastAPI Backend
        |
        +------------------+
        |                  |
        v                  v
Supabase              AI / Email / Payment Providers
Auth                  STT provider
Postgres              LLM provider
Storage               Resend
Vector support        Stripe or Razorpay
        ^
        |
Electron Desktop App
```

### Locked technology direction

- Desktop shell: Electron
- Existing desktop frontend: React + Vite
- Website frontend: implementation should follow the approved project tech stack and final Figma handoff
- Backend: FastAPI
- Authentication: Supabase Auth
- Primary cloud database: Supabase Postgres
- File storage: Supabase Storage
- Resume vector data: Supabase-compatible vector storage or an approved equivalent
- Email: Resend
- Payment provider: Stripe or Razorpay through a provider abstraction
- AI answer generation: configured cloud provider through backend only
- STT: current configured production path with fallback strategy
- Tests: Pytest for backend plus existing frontend/Electron validation

### Non-negotiable architecture rules

- API keys must never be stored in the website or Electron renderer.
- Paid feature checks must happen in the backend.
- The website and desktop app must use the same user identity.
- The website and desktop app must use the same saved profile and job context.
- Every user-owned database record must contain a valid `user_id`.
- Row Level Security must protect user data.
- Raw screenshots and audio must not be stored by default.
- Local fallback may exist, but cloud data must not silently mix between users.
- Do not rebuild the current desktop application from scratch.

---

## 5. Status Legend

```text
[ ] Not started
[~] In progress
[x] Done
[!] Blocked / urgent issue
[-] Deferred
```

---

## 6. Global Build Rules

These rules apply to every phase.

### Scope control

- Work on one active phase at a time.
- Do not start the next phase before the current phase exit gate passes.
- A small prerequisite from a later phase may be added only when documented.
- Do not add unrelated features while fixing a blocker.

### Code-change rules

- Prefer the smallest safe change.
- Preserve existing working routes and response fields where practical.
- Avoid framework migrations.
- Avoid broad refactors during feature implementation.
- Do not rename SAIIA.
- Do not bring Dhiti architecture into SAIIA.
- Do not add a new service without a clear requirement.

### Completion rules

A phase is not complete until:

- implementation is present
- tests pass
- manual validation passes where required
- error states are tested
- security checks are performed
- documentation is updated
- this roadmap is updated
- changed files are reported

### Privacy rules

Never place the following in logs, Git, screenshots, reports, or test fixtures:

- real API keys
- passwords or tokens
- full private resumes
- private transcripts
- real interview audio
- private screenshots
- payment secrets
- provider webhook secrets
- raw authentication tokens

### Honest product wording

Do not claim:

- guaranteed invisibility during screen sharing
- guaranteed correctness of AI answers
- unlimited usage unless the backend truly enforces it
- complete offline support unless every dependency works offline
- support for every coding language/platform before validation exists

---

## 7. Overall Build Order

```text
C0  Desktop core stabilization
C0.9 Screen Intelligence OCR/Extension source selection and Browser Extension foundation
C1  Supabase cloud foundation
C2  Authentication and account lifecycle
C3  Resume upload and cloud profile
C4  Job target and job-description cloud sync
C5  Desktop login and cloud synchronization
C6  Interview session lifecycle and storage
C7  Transcript storage, viewing, and download
C8  AI Notes generation
C9  Ask AI and follow-up context memory
C10 Resend email system
C11 Pricing and subscription foundation
C12 Payment provider integration
C13 Usage limits and backend feature gates
C14 Final Figma website implementation and integration
C15 Privacy, export, retention, and deletion
C15.5 Internal admin, support, and audit console
C16 QA, deployment, packaging readiness, and release
```

C15.5 is a conditional release gate: it must be completed before C16 only if SAIIA needs internal staff/admin/support operations for that release. If not required, the deferral decision must be recorded before C16 acceptance.

---

# C0 â€” Desktop Core Stabilization

## Status

```text
[x] Done
```

## Goal

Create a stable desktop baseline before cloud accounts, website integration, history, pricing, or payments are added.

C0 is a feature freeze. Work must improve:

- reliability
- performance
- observability
- error recovery
- interaction correctness
- regression coverage

Do not add cloud features during C0.

## Why C0 must happen first

Cloud integration will increase the number of dependencies and failure points. If the desktop runtime is unstable before adding accounts and synchronization, debugging will become significantly harder.

The desktop app must first prove that it can:

- launch reliably
- capture audio reliably
- generate answers reliably
- display answers reliably
- recover from provider failure
- maintain overlay controls
- avoid duplicate requests
- preserve manual mode
- handle screen/OCR failures without blocking the rest of the app

## C0 scope

### C0.1 Overlay interaction stability

Fix and validate:

- Show button
- expand/collapse arrow
- clear/delete button
- close button
- copy button, if present
- answer panel drag region
- text selection
- mouse-event handling
- `setIgnoreMouseEvents`
- `pointer-events`
- `-webkit-app-region`
- z-index and invisible overlays
- stable collapsed and expanded window bounds

### C0.2 Answer reveal behavior

Required behavior:

- answer is revealed progressively in the overlay
- Answer, Analyze Screen, and Chat panels keep separate display ownership
- selecting a panel tab must not start generation by itself
- Chat answers must not appear in Answer; Screen answers must not appear in Answer or Chat
- preferred live path uses `/generate/stream` and forwards OpenAI Responses API text deltas as NDJSON
- rollback `/generate/` path may still return the full answer at once
- simulated frontend word/line timers must not be used in the true-streaming path
- outer Electron window must not resize on every reveal step
- long answers must scroll inside a fixed expanded panel
- â€œShow full answerâ€ must immediately reveal the rest
- new answers must abort old provider streams
- collapse/re-expand must not delete or restart the answer

### C0.3 Provider and rate-limit reliability

Fix:

- primary-generation 429 handling
- correction-pass 429 handling
- provider cooldown
- retry-after parsing
- compact coding prompts
- conditional correction passes
- clean fallback behavior
- no generic 500 when a controlled 429/503 is appropriate
- no loss of usable primary code when correction fails
- no noisy Ollama failure when fallback is disabled or unavailable

### C0.4 Request deduplication

Ensure:

- one user action creates one generation request
- Auto Mode cannot overlap requests for the same question
- repeated screen-analysis actions do not create uncontrolled parallel generation
- stale responses cannot replace newer answers
- request IDs or generation versions protect the UI

### C0.5 Audio regression validation

Validate:

- manual microphone recording
- microphone Auto Mode
- manual system-audio capture
- system-audio Auto Mode
- selected source state
- silence handling
- duplicate filtering
- cooldown behavior
- reconnect/error state for streaming STT
- manual mode remains available

### C0.6 Screen/OCR decision

OCR is kept as a user-triggered fallback for:

- image-based questions
- native windows
- PDFs/screenshots
- content where structured extraction is unavailable

Do not keep expanding OCR rules for supported browser coding sites during C0.

Record this product rule:

```text
Structured extraction first where available.
Vision/OCR fallback otherwise.
```

A browser/DOM coding-problem extractor is now planned for C0.9 as part of Screen Intelligence. It must be generic and must not block C0 closure unless it is required for a currently advertised C0 feature.

### C0.7 Logging and observability

Each request should have:

- request/session ID
- input source
- platform, when known
- question type
- selected provider/model
- transcription timing
- classification timing
- retrieval timing
- generation timing
- total timing
- fallback status
- validation status
- correction status
- safe error type
- cooldown/rate-limit details

Do not log full private content by default.

### C0.8 Error handling

User-facing errors must be specific and actionable.

Examples:

- backend unavailable
- microphone permission denied
- no speech detected
- transcription provider unavailable
- generation provider rate-limited
- retry after X seconds
- fallback unavailable
- screen text could not be extracted
- answer generated but not fully verified

### C0 tests

Backend:

- provider success
- primary 429
- correction 429
- cooldown
- fallback disabled
- fallback unavailable
- request deduplication
- answer cleanup
- coding validation checks currently supported

Frontend/Electron:

- app launch
- overlay open
- all visible controls clickable
- collapse/expand
- stable bounds
- progressive reveal
- copy/clear/close
- Ctrl+H
- main panel open/close
- manual microphone flow
- system-audio flow
- Auto Mode flow
- stale answer protection

### C0 exit criteria

C0 is complete only when:

- no known critical overlay-control bug remains
- no known repeated-resize bug remains
- no uncontrolled duplicate generation remains
- provider 429 errors are handled clearly
- a correction failure does not discard usable primary output
- manual microphone flow passes
- system-audio flow passes
- Auto Mode passes a live validation session
- Ctrl+H remains reliable
- frontend build passes
- Electron syntax checks pass
- backend compile/tests pass
- OCR is formally frozen as fallback rather than allowed to block unrelated work

### C0 out of scope

- Supabase
- website implementation
- login/signup
- cloud resume
- cloud session history
- AI Notes
- Ask AI
- pricing
- payments
- usage limits
- commercial licensing

---

# C0.9 - Screen Intelligence Source Selection and Browser Extension Foundation

## Status

```text
[~] Deferred by product-priority decision - C0.9.1, C0.9.2, C0.9.3, C0.9.4, and C0.9.5 complete; C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, controlled unsupported-content results, and Chrome/Edge real-page validation pending; C0.9.7 through C0.9.13 remain deferred after C1 completion while C2 authentication/account lifecycle is active
```

## Purpose

Implement the Analyze Screen OCR/Extension source-selection architecture. On 2026-07-31, the project made an explicit product-priority decision to defer the remaining C0.9 validation/application work and begin C1 cloud foundation work.

C0.9 remains intentionally not fully complete. C0.9.1 documentation is complete. C0.9.2 OCR/Extension menu, contextual result controls, and optimized multi-question one-click OCR are complete. C0.9.3 contracts are complete. C0.9.4 operation ownership and reliable active-window targeting are complete. C0.9.5 adds the standalone Chrome/Edge Manifest V3 extension prototype with automated validation and Chrome/Edge manual validation passing. C0.9.6 implements platform-agnostic Generic Coding-Page DOM Extraction: coding pages can return ready envelopes, false-negative coding scope detection is guarded by normalized evidence, raw list/label candidates no longer control MCQ scope, decorative visuals no longer force coding pages to OCR, accessible Monaco/Ace/CodeMirror/textarea/contenteditable editor DOM can report editor presence and starter code independently, official Sample/Example/Test Case entries stay in one `examples` array with kind, label, and index metadata while custom input/output panels are excluded, semantic sample/example blocks attach child Input/Output/Explanation sections to the correct parent, official Input/Output and STDIN/Function tables normalize without orphan `unknown` examples, `Prints`/`Returns` map to output contracts, canonical editor counts avoid nested surfaces, folded editor DOM reports partial-code diagnostics, and confidence is capped below perfect when warnings exist. MCQs, code-based MCQs, output-prediction, technical/general, true visual/chart/diagram, tutorial/article, and editor-only pages return controlled unsupported results that recommend OCR. Automated validation passes; Chrome/Edge real-page validation remains pending. C0.9.7 through C0.9.13 are deferred.

## Build-order placement

```text
C0
-> C0.9
-> C1
-> C2 ...
```

Do not renumber C1-C16.

## Subphases

- [x] C0.9.1 - Documentation and architecture lock
- [x] C0.9.2 - Analyze Screen OCR/Extension menu, contextual result controls, and optimized one-click multi-question OCR
- [x] C0.9.3 - Extraction Result Envelope and Normalized Question schema
- [x] C0.9.4 - Screen Intelligence orchestrator, request ownership, and reliable active-window targeting
- [x] C0.9.5 - Generic Chrome/Edge extension prototype
- [~] C0.9.6 - Deferred with implementation present; Generic Coding-Page DOM Extraction implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, false-negative/false-MCQ/false-visual detection fixes, and controlled unsupported-content results; Chrome/Edge real-page validation pending
- [-] C0.9.7 - Coding language and submission-mode resolution deferred
- [-] C0.9.8 - Electron-to-extension local bridge deferred
- [-] C0.9.9 - OCR multiple-question detection and selection deferred
- [-] C0.9.10 - Explicit fallback and error states deferred
- [-] C0.9.11 - Security and privacy hardening deferred
- [-] C0.9.12 - Regression and manual validation deferred
- [-] C0.9.13 - Production Native Messaging planning deferred

Do not implement Native Messaging in the first prototype unless separately approved. Do not claim the extension or bridge are implemented.

C0.9.3 contract foundation now adds the backend Extraction Result Envelope and
Normalized Question schema, maps the existing OCR response into `envelope`
while preserving legacy fields, and adds frontend normalization helpers for
new and older screen responses. OCR UI, prompts, providers, screenshot count,
screen-model request count, and operation-based history remain unchanged.
C0.9.3 is formally complete. C0.9.4 adds operation/request/source ownership around the existing OCR path and the temporary Extension-unavailable path while preserving one screenshot, one screen-model request, current providers, stale-result rejection, cancellation safety, one history entry per successful OCR operation, and reliable active-window targeting across multiple Chrome windows.

## Prerequisites

- existing C0 critical stability work remains protected
- mode isolation is stable
- Analyze Screen persistence exists
- request/stale-response ownership exists or is audited
- current OCR path is preserved
- current generation pipeline is preserved

## Deliverables

- Analyze Screen menu with exactly OCR and Extension
- one-click Extension active-tab extraction from the paired browser
- generic Chrome/Edge browser extension prototype
- Extraction Result Envelope and Normalized Question schema
- source router
- language and submission-mode resolver
- OCR multi-question batch answers from one screenshot and one screen-model request
- explicit fallback
- extension status states
- history source metadata
- privacy and security controls
- automated tests
- Electron manual validation

## Out of scope

- Firefox/Safari
- parallel or per-question Solve All workflows
- solving incomplete or partially visible questions
- extension-store publication
- final signed Native Messaging installer registration
- hidden website API reverse engineering
- hidden test-case extraction
- cloud session persistence changes beyond compatibility hooks
- pricing/payment changes

## Exit criteria

C0.9 is complete only when:

- menu opens without starting an operation
- Extension starts only after user selection
- OCR starts only after user selection
- Extension extracts complete active-tab coding problems from varied test fixtures after one Extension click
- generic extractor works independently of named platforms
- selected language and submission mode are resolved correctly
- OCR handles MCQs, aptitude, technical/general, visual/chart/diagram, output-prediction, and coding fallback; Extension does not silently fall back to OCR
- OCR quiz/batch screenshots answer all fully visible independent questions in screen order
- no silent fallback exists between OCR and Extension
- old/stale operations cannot overwrite new ones
- previous valid answer survives failure/cancellation
- no private browser data is extracted
- backend/frontend/Electron tests pass
- documentation is updated
- manual validation passes

## Source-of-truth references

- Product requirements: `SAIIA_PRODUCTION_PRD_CORE.md`
- Approved stack: `SAIIA_PRODUCTION_TECHSTACK.md`
- Detailed architecture: `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`
- Historical desktop baseline: `SAIIA_PRODUCTION_PHASES_TRACKER.md`

---
# C1 â€” Supabase Cloud Foundation

## Status

```text
[x] Foundation complete - C1.1 Supabase configuration, migration foundation, and repository audit complete; C1.2 base Supabase database schema migration complete and applied to live saiia-dev; C1.3 RLS/storage bucket migration complete and applied to live saiia-dev; C1.4 FastAPI auth-token verification dependency complete; C1.5 closure audit complete; live Supabase user-token smoke test passed; C2.1, C2.2, C2.3, C2.4, and C2.5 are complete; C3.1 planning/audit is active after explicit approval to start C3
```

## Goal

Create the secure cloud foundation shared by the website, backend, and desktop app.

## Prerequisite

C0 is complete. C0.9 remains deferred by explicit product-priority decision; C0.9.6 Chrome/Edge real-page validation remains pending and C0.9.7 through C0.9.13 remain deferred after C1 completion while C2 is active.

## Primary deliverables

- Supabase project configured
- development environment configuration
- backend Supabase integration
- base database schema
- RLS policies
- storage buckets
- migration process
- authentication-token verification in FastAPI
- local-development setup instructions

## Environment variables

Backend variables should include placeholders similar to:

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=
SUPABASE_RESUME_BUCKET=resumes
SUPABASE_EXPORT_BUCKET=exports
```

Rules:

- service-role key is backend-only
- anon/public key may be used only where appropriate
- no production secret in frontend Git
- separate development and production environments

## Initial database schema

Create migrations for:

### `profiles`

- `id`
- `user_id`
- `full_name`
- `headline`
- `summary`
- `skills`
- `technical_skills`
- `soft_skills`
- `education`
- `experience`
- `projects`
- `achievements`
- `certifications`
- `tools_frameworks`
- `profile_completion`
- `created_at`
- `updated_at`

### `resumes`

- `id`
- `user_id`
- `storage_path`
- `original_filename`
- `mime_type`
- `file_size`
- `parser_provider`
- `parser_status`
- `extraction_status`
- `index_status`
- `review_required`
- `created_at`
- `updated_at`

### `resume_chunks`

- `id`
- `user_id`
- `resume_id`
- `section`
- `chunk_text`
- `embedding`
- `metadata`
- `created_at`

### `job_contexts`

- `id`
- `user_id`
- `company`
- `position`
- `job_description`
- `required_skills`
- `responsibilities`
- `seniority`
- `domain_keywords`
- `is_active`
- `created_at`
- `updated_at`

### `user_settings`

- `id`
- `user_id`
- `preferred_answer_length`
- `preferred_answer_style`
- `default_audio_source`
- `overlay_settings`
- `notification_preferences`
- `marketing_consent`
- `created_at`
- `updated_at`

Additional tables will be added in later phases rather than created prematurely.

C1.2 implementation status:

- [x] Created `supabase/migrations/20260731121714_create_base_cloud_schema.sql`
- [x] Created base `profiles`, `resumes`, `resume_chunks`, `job_contexts`, and `user_settings` tables
- [x] Used `user_id uuid not null references auth.users(id) on delete cascade` on every user-owned table
- [x] Added ownership indexes, one-profile/one-settings uniqueness, and one-active-job-context partial uniqueness
- [x] Kept `resume_chunks.embedding` as nullable JSONB so pgvector is not required before the C3 resume cloud/RAG decision
- [x] Deferred RLS policies to C1.3 to avoid enabling RLS without access policies during local validation
- [x] Deferred Supabase Storage bucket creation to C1.3
- [x] Did not create session, transcript, AI answer, subscription, usage, email, payment, or account-lifecycle tables

C1.3 implementation status:

- [x] Created `supabase/migrations/20260731123545_enable_rls_and_storage.sql`
- [x] Enabled RLS on `profiles`, `resumes`, `resume_chunks`, `job_contexts`, and `user_settings`
- [x] Added authenticated own-row select, insert, update, and delete policies for each C1.2 user-owned table
- [x] Used both `USING` and `WITH CHECK` on update policies to prevent ownership transfer
- [x] Created private `resumes` and `exports` Supabase Storage buckets
- [x] Added storage object policies for authenticated access only under the user's own top-level `{user_id}/...` folder
- [x] Did not create public buckets, audio buckets, screenshot buckets, auth UI, FastAPI token verification, upload flows, sessions, billing, usage, email, payment, or website UI

C2.3 privilege support migration:

- [x] Created `supabase/migrations/20260801115446_grant_cloud_table_privileges.sql`
- [x] Granted `USAGE` on schema `public` to `authenticated` and `service_role`
- [x] Granted `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on `profiles`, `user_settings`, `resumes`, `resume_chunks`, and `job_contexts` to `authenticated` and `service_role`
- [x] Did not grant user-owned tables to `anon`
- [x] Kept C1.3 RLS enabled and own-row policies unchanged
- [x] Documented that authenticated grants rely on RLS `auth.uid()` ownership checks
- [x] Documented that `service_role` is backend-only and bypasses RLS, so backend code must derive `user_id` from a verified JWT

C1.4 implementation status:

- [x] Created reusable FastAPI auth dependency in `backend/app/auth/supabase_auth.py`
- [x] Added `get_current_user()` and safe `CurrentUser` identity object
- [x] Supports JWKS URL/JWKS JSON verification first and legacy JWT-secret verification only when explicitly configured
- [x] Rejects missing, non-Bearer, malformed, expired, invalid-signature, and missing-subject tokens
- [x] Returns controlled `503` when auth verification config is missing and the dependency is called
- [x] Does not use `SUPABASE_SERVICE_ROLE_KEY` for JWT verification
- [x] Does not protect existing desktop-local routes yet
- [x] Does not create `/api/auth/*`, login/signup UI, desktop login, resume cloud upload, sessions, billing, usage, email, payment, or website UI

C1.5 closure status:

- [x] Verified C1.1 backend-only Supabase configuration and local-only mode behavior
- [x] Verified C1.2 migration file for `profiles`, `resumes`, `resume_chunks`, `job_contexts`, and `user_settings`
- [x] Recorded that C1.2 is applied to live `saiia-dev`
- [x] Verified C1.3 migration file for RLS, own-row policies, private `resumes`/`exports` buckets, and storage ownership policies
- [x] Recorded user dashboard verification that C1.3 is applied to live `saiia-dev`
- [x] Verified C1.4 auth verifier tests and that no existing desktop-local route is protected yet
- [x] Added skipped-by-default live Supabase user-token smoke test for C2 integration readiness
- [x] Live Supabase user-token smoke test passed with a real Supabase Auth user access token validated by the C1.4 FastAPI verifier
- [x] Confirmed no login/signup UI, `/api/auth/*` route, existing desktop route protection, cloud resume upload, desktop login, sessions, billing, usage, email, payment, or website UI was added
- [x] Confirmed token, password, and service-role key values were not committed or printed
- [x] Treated the smoke-test user password as exposed; password should be changed immediately or the smoke-test user should be deleted
- [x] Confirmed no C2/C3/C5/session/billing/usage/email/payment/website work was started

## Storage buckets

### `resumes`

- private bucket
- user-owned folders
- signed access only
- allowed file types
- file-size limits
- delete on resume deletion/account deletion

### `exports`

- private or short-lived files
- generated transcript/notes exports
- automatic expiry or cleanup policy where practical

Do not create permanent audio/screenshot buckets by default.

## Row Level Security

Required policies:

- user can read own rows
- user can insert own rows
- user can update own rows
- user can delete own rows
- no user can access another user's records
- service role can perform trusted backend operations
- storage access must follow ownership rules

## FastAPI auth dependency

Create a reusable dependency such as:

```python
get_current_user()
```

It should:

- read bearer token
- validate token
- return stable user identity
- reject expired/invalid tokens
- avoid logging raw token
- support website and desktop clients

## Migration policy

- every schema change requires a migration
- no manual production-only table edits
- seed only non-sensitive reference data
- migrations must be reversible where practical
- database changes must be documented in this file or a schema file

## C1 tests

- valid token accepted
- invalid token rejected
- missing token rejected
- user A cannot access user B profile
- resume storage path ownership enforced
- service role not exposed
- migration applies cleanly
- backend starts without cloud secrets only in clearly defined local mode, if supported

## C1 exit criteria

- backend can authenticate a Supabase user
- base schema exists
- RLS is active
- user ownership tests pass
- resume and export buckets exist
- secrets are documented and protected
- migration process is repeatable

---

# C2 â€” Authentication and Account Lifecycle

## Status

```text
[x] Auth surface closure complete - C2.1 auth architecture audit complete; C2.2 minimal Supabase auth UI and backend current-user endpoint complete; C2.3 authenticated profile bootstrap implemented and live revalidated after follow-up Supabase table privilege migration fixed the PostgREST privilege blocker; C2.4 protected auth shell and account/session state handling complete; C2.5 auth surface closure checkpoint complete; no C3 cloud resume upload, C5 desktop login/cloud sync, session history, billing, usage, email-provider integration, payment, admin console, or final website UI started
```

## Goal

Implement complete user account lifecycle for the website and prepare the same identity for the desktop app.

## Scope

- signup
- login
- logout
- email verification
- forgot password
- reset password
- session refresh
- current-user endpoint
- account state handling
- protected routes
- basic onboarding state

## Account states

Support:

- unregistered
- registered but unverified
- verified and active
- password reset pending
- signed out
- disabled/deleted
- session expired

## Backend endpoints

Possible backend routes:

```text
GET  /api/auth/me
POST /api/auth/session/validate
POST /api/auth/logout
POST /api/auth/profile/bootstrap
```

Supabase client flows may handle signup/login directly, but backend-owned data access must always validate the token.

## Website behavior

Design integration must include:

- signup form
- login form
- email-verification message
- resend verification
- forgot-password form
- reset-password form
- expired-link state
- protected-dashboard redirect
- loading and error states

## Email verification plan

Resend will be used as the email delivery provider in the final architecture.

Implementation may use:

- Supabase Auth with Resend-backed SMTP/custom email delivery, or
- backend-controlled transactional templates where required

The exact method must be documented when implemented.

## Profile bootstrap

After a verified user first enters the dashboard:

- create `profiles` row if missing
- create `user_settings` row if missing
- assign default plan later through subscription foundation
- do not duplicate rows on repeated login

## Security

- use secure session handling
- avoid localStorage for long-lived sensitive tokens where a safer platform mechanism is available
- protect against open redirects
- rate-limit auth-related backend endpoints
- do not reveal whether an email exists more than necessary
- record security-relevant events without logging secrets

## C2.1 implementation status

- [x] Created `docs/C2_AUTH_ARCHITECTURE_PLAN.md`
- [x] Audited existing React/Vite/Electron frontend entry points and routing
- [x] Audited existing FastAPI route registration and C1.4 auth dependency
- [x] Audited local profile, resume-index, and job-context storage
- [x] Confirmed `@supabase/supabase-js` is not installed yet
- [x] Confirmed frontend has no current `VITE_*` Supabase env usage
- [x] Proposed C2 endpoint, profile bootstrap, redirect URL, token handling, and protected-route plan
- [x] Did not add login/signup UI, `/api/auth/*` routes, existing desktop route protection, desktop login, cloud resume upload, sessions, billing, usage, email, payment, or website UI

## C2.2 implementation status

- [x] Added `@supabase/supabase-js` to the existing React/Vite frontend package
- [x] Added frontend-safe placeholders `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
- [x] Added temporary auth routes in the existing Vite app on port 5173:
  `/auth/signup`, `/auth/login`, `/auth/forgot-password`,
  `/auth/reset-password`, `/auth/callback`, `/auth/status`, and
  `/auth/logout`
- [x] Added frontend Supabase auth client boundary under `frontend/src/auth/`
- [x] Added `GET /api/auth/me` using the existing C1.4 FastAPI
  `get_current_user()` verifier
- [x] `/api/auth/me` returns only `user_id`, optional `email`, and optional
  `role`
- [x] Documented development Supabase Auth setup:
  Site URL `http://localhost:5173`, redirect URLs
  `http://localhost:5173/auth/callback` and
  `http://localhost:5173/auth/reset-password`
- [x] Did not add C2.3 profile bootstrap, backend signup/login endpoints, cloud
  profile saving, cloud resume upload, desktop login/cloud sync, sessions,
  billing, usage, email-provider integration, payments, or final website UI

## C2.3 implementation status

- [x] Added `POST /api/auth/profile/bootstrap`
- [x] Protected the endpoint with the existing C1.4 `get_current_user()` verifier
- [x] Bootstrap uses only verified `current_user.user_id`; frontend-supplied
  `user_id` is ignored
- [x] Selected Supabase REST with backend-only service-role access because
  `requests` already exists and no Postgres/Supabase Python client dependency
  was installed
- [x] Creates missing `profiles` and `user_settings` rows and reuses existing
  rows on repeated calls
- [x] Relies on C1.2 unique constraints for idempotency:
  `profiles_user_id_key` and `user_settings_user_id_key`
- [x] Handles concurrent duplicate/conflict inserts by re-reading the row before
  returning `created=false`; if the row is still missing, the existing safe
  bootstrap error is raised
- [x] Added a temporary `Prepare Profile` action on `/auth/status`
- [x] Added a follow-up Supabase privilege migration after live C2.3 validation
  found PostgREST returned `permission denied for table profiles`
- [x] Live bootstrap revalidation is complete after
  `20260801115446_grant_cloud_table_privileges.sql` fixed the live Supabase
  privilege blocker
- [x] Did not migrate local profile JSON, save cloud profile content, upload
  resumes, write `resumes`, `resume_chunks`, or `job_contexts`, protect
  desktop-local routes, add desktop login/cloud sync, sessions, billing, usage,
  email-provider integration, payments, or final website UI

## C2.4 implementation status

- [x] Added temporary protected route `/auth/dashboard` inside the existing
  React/Vite app.
- [x] Signed-out or expired-session users opening `/auth/dashboard` redirect to
  `/auth/login` with the fixed generic message `Session expired or signed out.
  Please log in.`
- [x] Login succeeds to `/auth/dashboard` by default, and safe `next` routes
  are allowlisted to `/auth/dashboard` and `/auth/status`.
- [x] Already-authenticated users opening `/auth/login` or `/auth/signup`
  redirect through the same safe next-route handling.
- [x] `/auth/dashboard` displays safe identity from `GET /api/auth/me` and can
  run the existing C2.3 profile bootstrap action.
- [x] Logout is guarded against duplicate clicks, handles resolved or thrown
  Supabase sign-out errors with generic UI text, preserves profile readiness on
  logout failure, and navigates to `/auth/login` only after sign-out success.
- [x] `Prepare Profile` is disabled while either bootstrap or logout is
  pending, and the shared bootstrap handler also blocks while logout is
  pending.
- [x] Existing `/` and `/profile-setup` remain intentionally unprotected for
  desktop-local development.
- [x] Did not add backend signup/login endpoints, backend session endpoints,
  cloud resume upload, desktop login/cloud sync, session history, billing,
  usage, email-provider integration, payments, admin console, or final website
  UI.

## C2.5 auth surface closure status

- [x] Audited C2.1, C2.2, C2.3, and C2.4 implementation status against current
  frontend, backend, and documentation.
- [x] Confirmed frontend-safe Supabase env usage is limited to
  `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- [x] Confirmed backend auth env rules: `SUPABASE_URL` identifies the project,
  `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG` verifies access tokens with HTTPS-only
  JWKS URL handling where JWKS is used, and `SUPABASE_SERVICE_ROLE_KEY` remains
  backend-only and is not used as the JWT verification secret.
- [x] Confirmed C2 backend auth route surface is limited to `GET /api/auth/me`
  and `POST /api/auth/profile/bootstrap`; no backend signup/login endpoints
  were added.
- [x] Confirmed route behavior: `/auth/dashboard` is protected; `/auth/login`
  and `/auth/signup` redirect authenticated users to `/auth/dashboard` or a
  safe allowlisted next route; `/auth/status` works; logout clears the browser
  Supabase session on success; `/` and `/profile-setup` remain unprotected.
- [x] Confirmed C2.3 profile bootstrap is idempotent and derives `user_id` only
  from the verified backend `CurrentUser`.
- [x] Confirmed no raw token, refresh token, password, service-role value, or
  full JWT payload is intentionally stored in React state, logs, tests, or docs.
- [x] Confirmed safe next-route handling avoids external/open redirects.
- [x] Confirmed no C3 cloud resume upload, C5 desktop login/cloud sync, session
  history, billing, usage, email-provider integration, payment, admin console,
  or final website UI was started.

## C2 tests

- signup
- duplicate signup
- verification required
- verified login
- wrong password
- forgot-password request
- reset-password completion
- expired token
- logout
- protected route rejection
- profile bootstrap idempotency

## C2 exit criteria

- user can sign up, verify, log in, and log out
- password reset works
- protected dashboard requires authentication
- backend returns current user safely
- profile bootstrap works exactly once
- auth errors are user-friendly

---

# C3 â€” Resume Upload and Cloud Profile

## Status

```text
[x] C3.5 cloud resume delete/rebuild/status closure implemented after C3.4.5 GPT-based resume extraction provider
```

## Goal

Move resume upload, extraction review, profile saving, and resume indexing into the authenticated website/cloud workflow while preserving current extraction logic.

## C3 subphases

- C3.1 audit/design
- C3.2 backend cloud resume API
- C3.3 frontend authenticated upload/review UI
- C3.4 cloud resume indexing/RAG ownership
- C3.4.5 GPT-based resume extraction provider
- C3.5 delete/rebuild/status + closure

## C3.1 planning status

- [x] Started after explicit user approval to begin C3.
- [x] Audited existing local resume extraction, profile saving, local index,
  Supabase schema/storage, and C2 auth boundary.
- [x] Created `docs/C3_CLOUD_RESUME_PROFILE_PLAN.md`.
- [x] Confirmed C3.1 does not implement upload runtime, cloud profile saving,
  cloud resume indexing, C4, C5, sessions, billing, payment, email provider,
  admin console, or final website UI.

## C3.2 backend status

- [x] Added Supabase migration
  `20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql` for
  resume lifecycle columns, named constraints, one-active-resume index, and
  direct authenticated write hardening.
- [x] Added authenticated backend cloud resume routes under `/api/resumes`.
- [x] Added backend-only Supabase REST/storage service for upload, current
  resume lookup, review candidate lookup, status, extraction, and confirmation.
- [x] Reused existing resume parser services for extraction.
- [x] Confirmation writes only to `resumes.confirmed_profile`; it does not
  update `profiles`, set active, or mark ready.
- [x] Existing `/api/resume/*`, `/api/profile`, and `/profile-setup` local
  desktop flows remain intentionally unchanged.
- [x] C3.2 backend API merged and live smoke-tested.
- [x] C3.3 frontend upload/review UI implemented at `/auth/resume`.
- [x] C3.4 cloud chunk generation/RAG activation implemented.
- [x] C3.4.5 GPT-based resume extraction provider implemented.
- [x] C3.5 delete/rebuild/status closure implemented.

## Existing capability to reuse

The current product already has:

- PDF/DOCX/TXT extraction
- local extraction fallback
- structured profile fields
- resume review
- resume index build
- retrieval-based grounding
- delete/rebuild behavior

Do not rewrite these services unless required for multi-user safety.

## User flow

```text
Authenticated user
â†’ Upload resume
â†’ Validate file
â†’ Store private file
â†’ Extract text
â†’ Parse structured profile
â†’ Show review/edit screen
â†’ User confirms
â†’ Save profile
â†’ Build/rebuild resume index
â†’ Mark resume ready
```

## Backend endpoints

Possible routes:

```text
POST   /api/resumes
GET    /api/resumes/current
POST   /api/resumes/{resume_id}/extract
POST   /api/resumes/{resume_id}/confirm
GET    /api/resumes/{resume_id}/status
DELETE /api/resumes/{resume_id}
POST   /api/resumes/{resume_id}/rebuild-index
```

C3.2 implemented the backend subset for upload/status/extract/confirm. C3.4
implements chunk generation and activation through the existing confirm route;
no separate C3.4 `/index` route is implemented. C3.5 implements authenticated
`DELETE /api/resumes/{resume_id}` and
`POST /api/resumes/{resume_id}/rebuild-index` plus frontend lifecycle controls.

## Upload validation

Validate:

- authenticated ownership
- allowed file types
- MIME type
- extension
- file size
- empty file
- corrupt file
- scanned/low-text PDF
- duplicate upload behavior
- malicious filename/path
- parsing timeout

## Profile review

User must be able to edit:

- name
- role/headline
- summary
- education
- skills
- technical skills
- soft skills
- projects
- experience
- achievements
- certifications
- tools/frameworks

Do not make extracted values authoritative until user confirms.

## Storage rules

- original resume stored privately
- extracted raw text should not be exposed broadly
- raw text may be retained only for approved RAG/index use
- profile fields stored separately
- old resume/index behavior must be defined when a new resume is uploaded
- delete must remove file, metadata, chunks, and derived profile data according to user choice

## RAG/indexing

- chunks must be user-owned
- retrieval must filter by `user_id`
- retrieval may optionally filter by active resume
- embeddings must never cross user boundaries
- index status must be visible
- index rebuild must be idempotent
- extraction failure must not overwrite a previously valid profile

## C3 tests

- valid PDF/DOCX/TXT
- unsupported file
- empty file
- corrupt file
- oversized file
- scanned-like file
- user A cannot access user B resume
- confirm required before profile replacement
- index build
- index rebuild
- delete
- retrieval uses correct user
- extraction failure preserves existing profile

## C3 exit criteria

- authenticated user uploads and confirms resume
- cloud profile is saved
- private resume storage works
- resume index is built
- retrieval returns only current user's data
- deletion removes expected data
- website shows accurate status

---

# C4 â€” Job Target and Job-Description Cloud Sync

## Status

```text
[~] In progress - C4.1 cloud job-context audit, architecture, and implementation plan complete in `docs/C4_CLOUD_JOB_CONTEXT_PLAN.md`; C4.2 authenticated backend job-context API plus required migration implemented locally with backend/migration tests passing and live Supabase smoke validation passed on saiia-dev; C4.3 main website `/job-contexts` UI cancelled/re-scoped by product decision; job target selection belongs in desktop startup/session setup with active resume, active job target/JD, answer model, audio source, and answer preferences after desktop cloud identity exists; no C4 generation integration or C5 desktop sync has been implemented
```

Latest C4.2 live validation:

- Result: passed against linked Supabase project `saiia-dev` / `rbmxfazjbldmkomdpyzl` on 2026-08-09.
- Command/tests run: see the tracked sanitized artifact [docs/validation/C4_2_LIVE_SUPABASE_SMOKE_2026-08-09.md](docs/validation/C4_2_LIVE_SUPABASE_SMOKE_2026-08-09.md), which records the PowerShell inline Python smoke method, repository-root execution context, and assertion outcomes without secrets or private data.
- Smoke covered: migration columns, `is_active` database default false, idempotency table existence/RLS, service-role-only activation/create RPC exposure, blocked authenticated direct `INSERT`/`UPDATE`/`DELETE`, authenticated FastAPI create/list/detail/patch/activate/delete/no-context lifecycle, cross-user blocking, extraction consent rejection, and dual-source extraction rejection.
- Scope exclusions remain: no C4 generation integration and no C5 desktop sync.

Latest C4.3 product decision:

- Result: main website `/job-contexts` UI is cancelled/re-scoped and should not be committed as product UI.
- Replacement direction: job target/JD selection moves into the desktop app startup/session setup flow where the user chooses active resume, active job target/JD, answer model, audio source, and answer preferences before starting an interview session.
- Dependency: this belongs during or after C5, once desktop authenticated cloud identity is available, because the desktop app needs that identity before it can load cloud resumes and job contexts.
- Scope exclusions remain: no new desktop implementation, no C4.4 generation integration, no C5 desktop login/cloud sync, no backend runtime changes, and no migration changes.

## Goal

Store and synchronize company, target role, and job-description context for answer personalization.

## Superseded website flow

The earlier C4.3 website flow where a `/job-contexts` page creates and manages job targets is superseded. The production website remains limited to account/cloud setup surfaces for this area: login/signup, cloud resume setup, auth status, and later billing/account work.

Do not implement or commit a main website job-target management page for C4.3.

## Replacement desktop direction

Job target/JD setup belongs in the desktop app startup/session setup flow after desktop cloud identity exists. That future setup flow should eventually let the user choose the interview session inputs before starting:

- existing cloud resume
- existing cloud job target
- lightweight job target/JD create or update from company, position, and pasted/uploaded JD
- answer model
- language/audio source
- answer preferences

This desktop setup UI is deferred until during or after C5, once desktop authenticated cloud identity is available. It is not implemented by C4.2 or C4.3.

## Data requirements

Store:

- company
- position
- raw job description
- required skills
- responsibilities
- seniority
- domain keywords
- optional location/employment type
- active/inactive state
- source file metadata, if uploaded

## Backend routes

Possible routes:

```text
GET    /api/job-contexts
POST   /api/job-contexts
GET    /api/job-contexts/{id}
PATCH  /api/job-contexts/{id}
DELETE /api/job-contexts/{id}
POST   /api/job-contexts/{id}/activate
POST   /api/job-contexts/extract
```

## Rules

- only one active context is required initially
- support future multiple saved job targets without redesign
- do not invent requirements not present in the JD
- user can edit extracted fields
- generation must use active context only
- no job context must remain a valid fallback state

## C4 tests

Completed C4.2 backend coverage:

- create/list/detail/patch/delete/activate backend routes
- extraction from text/file with consent and source validation
- ownership/RLS/RPC/idempotency behavior
- active context uniqueness and no-context state after delete

Deferred coverage:

- desktop startup job target selection/create/edit after desktop cloud identity exists
- C4.4 active-context generation integration
- generation uses only the verified user's active context
- unrelated context is not used

## C4 exit criteria

Completed C4.2 backend criteria:

- authenticated backend job-context APIs are implemented
- required migration, RLS/RPC grants, backend-only writes, and idempotency are implemented
- live Supabase smoke validation passed on saiia-dev
- active context is stored securely

Superseded C4.3 website criteria:

- website `/job-contexts` job-target create/manage UI is cancelled and must not be treated as an active C4 requirement

Deferred criteria:

- desktop startup job-target selection/create/edit moves to a later desktop setup phase during or after C5, once desktop authenticated cloud identity is available
- desktop/backend generation can retrieve the active job context in C4.4 or later
- no-context generation fallback remains preserved when generation integration is implemented

---

# C5 â€” Desktop App Login and Cloud Synchronization

## Status

```text
[~] In progress - C5.1 Desktop Authenticated Cloud Identity Audit and Plan created in `docs/C5_DESKTOP_AUTH_CLOUD_IDENTITY_PLAN.md`; C5.2 desktop authenticated cloud identity implemented locally with Electron main-process Supabase Auth PKCE, safeStorage-backed session persistence, narrow auth/cloud IPC, backend `/api/auth/me` verification, mandatory profile bootstrap, logout cleanup, and race-condition tests; C5.3 desktop auth status/login/logout UI wiring implemented locally through the existing safe preload APIs; C5.4 desktop cloud startup context plumbing implemented locally with safe auth/cloud summary state, resume readiness, job-target readiness, offline/local-only fallback, and stale-response tests; desktop startup/session setup UI, C4.4 generation integration, cloud sync engine, and local/cloud data migration are not started
```

## Goal

Connect the Electron desktop app to the same account, profile, resume context, settings, and shared cloud job-target record selected in the desktop startup/session setup flow.

## Login options

Choose and document one secure flow:

- embedded desktop login
- browser-based OAuth/deep-link callback
- device-code-style flow
- secure handoff from website

Do not create an insecure custom token copy/paste flow unless it is an intentional temporary developer-only mode.

## C5.1 audit/design status

- [x] Audited current Electron main/preload structure and IPC boundaries.
- [x] Audited current website Supabase auth/session handling.
- [x] Audited backend JWT-protected route pattern through `CurrentUserDep`.
- [x] Confirmed current Electron app has no desktop auth, token storage, or cloud API identity.
- [x] Selected main-process-owned desktop session handling as the planned security boundary.
- [x] Planned OS-protected token persistence with Electron `safeStorage` where available.
- [x] Planned narrow auth/cloud IPC with no raw token exposure to the renderer.
- [x] Kept startup/session setup UI deferred until a later C5 implementation step.
- [x] Did not implement desktop login, cloud sync, backend route changes, migrations, C4.4 generation integration, or frontend UI.

## C5.2 implementation status

- [x] Added Electron main-process desktop auth session manager.
- [x] Added Supabase Auth PKCE request/callback handling for `saiia://auth/callback`.
- [x] Added Electron `safeStorage` encrypted session persistence with session-only fallback when encryption is unavailable.
- [x] Added narrow auth/cloud IPC and preload bridge methods without raw token exposure or generic fetch.
- [x] Added backend `/api/auth/me` verification and mandatory `POST /api/auth/profile/bootstrap` after verification.
- [x] Added logout cleanup, user-switch cache clearing, session generation, and stale cloud-response cache-write protection.
- [x] Added focused Electron auth/session/IPC tests.
- [x] Did not build desktop startup/session setup UI, resume/job-target selection UI, C4.4 generation integration, Supabase migrations, backend routes, billing/account UI, or local/cloud data migration.

## C5.3 implementation status

- [x] Added a small desktop auth status surface in the Electron renderer.
- [x] Wired Login, Logout, and Refresh status actions only through the existing safe `window.saiia` preload API.
- [x] Displayed only safe status, email/user identity when connected, and safe recovery guidance for signed-out, token-expired, offline, backend-unavailable, and bootstrap-failed states.
- [x] Added focused renderer/helper tests for auth status rendering, action wiring, token non-exposure, and local/no-auth desktop availability.
- [x] Did not build desktop startup/session setup UI, resume/job-target selection UI, C4.4 generation integration, Supabase migrations, backend routes, billing/account UI, or local/cloud data migration.

## C5.4 implementation status

- [x] Extended Electron main-process startup context plumbing to return safe `auth` and `cloud` summary state through the existing narrow cloud startup IPC.
- [x] Used existing authenticated backend routes only: `GET /api/auth/me`, `POST /api/auth/profile/bootstrap`, `GET /api/resumes/current`, and preview-only `GET /api/job-contexts?limit=50`.
- [x] Derived conservative `profileReady`, `resumeReady`, and `jobContextReady` flags without exposing raw tokens, raw sessions, full resumes, or full job descriptions to the renderer.
- [x] Preserved signed-out local-only behavior and offline/backend-unavailable fallback without forcing logout for transient cloud failures.
- [x] Added stale startup-context response protection tests for logout and user-switch races plus focused renderer/helper tests for cloud readiness display.
- [x] Did not build desktop startup/session setup UI, resume/job-target selection UI, C4.4 generation integration, Supabase migrations, backend routes, billing/account UI, cloud sync engine, or local/cloud data migration.

## Secure session storage

Desktop tokens must be stored using a safe Electron/OS approach where practical.

Rules:

- never expose service-role key
- renderer receives only what it needs
- preload bridge is narrow and explicit
- logout clears local session
- token refresh is handled
- expired sessions return user to login

## Sync data

Desktop should fetch:

- profile
- active resume/index status
- active job context
- user settings
- current plan/feature access, once available

Desktop may cache:

- non-secret profile summary
- last successful sync timestamp
- settings required for launch
- offline-safe data, if encrypted or appropriately protected

## Sync behavior

- sync on login
- sync on app launch
- sync on explicit refresh
- sync after website changes, through polling/realtime/manual refresh
- do not silently overwrite newer server data with stale local data
- define server as source of truth after cloud migration
- preserve local fallback until migration is complete

## UI states

- signed out
- signing in
- connected
- syncing
- sync complete
- offline
- token expired
- resume missing
- job target missing
- plan restricted

## C5 tests

- desktop login
- restart persistence
- token refresh
- logout
- expired token
- cloud profile fetch
- job context fetch
- website change reflected in desktop
- offline fallback
- user switch does not leak cached data
- local-to-cloud migration behavior

## C5 exit criteria

- website and desktop use the same account
- desktop safely retrieves cloud context
- logout clears user data
- user switching is safe
- offline behavior is documented
- existing answer generation remains functional

---

# C6 â€” Interview Session Lifecycle and Storage

## Status

```text
[~] In progress - C6.1 desktop startup/session setup UI audit and plan complete in `docs/C6_DESKTOP_STARTUP_UI_SESSION_SETUP_PLAN.md`; C6.2A Startup Login Screen implemented locally for signed-out/token-expired desktop startup using existing safe preload auth APIs; C6.2A uses a dev/local memory-only desktop handoff store, and production shared atomic TTL-backed handoff storage is deferred to C16.1 Production Auth Hardening; broader startup shell, resume/job-target selection UI, backend session routes, Supabase migrations, C4.4 generation integration, cloud sync engine, and local/cloud data migration are not implemented
```

## Goal

Create a durable interview session model that connects desktop activity with website history.

Before durable session storage is implemented, the desktop app needs a small startup/session setup surface that lets the user choose cloud or local-only mode, see auth/cloud readiness, and understand whether resume/job-target context is ready. C6.1 plans that startup shell only; C6.2+ will implement it.

## C6.1 startup/session setup planning status

- [x] Audited the current Electron runtime UI, C5.4 startup context shape, safe preload APIs, auth/cloud states, local-only behavior, and existing resume/job-context backend capabilities.
- [x] Defined startup flows for signed-out, signing-in, connected/cloud-ready, missing resume, missing job target, token-expired, backend-unavailable, offline, bootstrap-failed, and explicit local-only states.
- [x] Defined a minimal startup screen structure: header, cloud account status, resume readiness, job target/JD readiness, local-only option, Start Session action, and safe recovery messages.
- [x] Preserved renderer security boundaries: preload-only cloud access, no tokens/raw sessions, no direct Supabase renderer access, no generic cloud fetch.
- [x] Kept C6.1 documentation-only; no startup UI runtime, resume/job-target selection UI, backend route, migration, C4.4 generation integration, cloud/local migration, billing, or admin work was implemented.

## C6 implementation split

- C6.2A: implement the first desktop startup login screen using the provided Figma reference and existing safe preload auth login API.
- C6.2B: implement the broader basic desktop startup shell UI using existing C5.4 context.
- C6.3: wire resume/job target selection or lightweight creation flow.
- C6.4: validation, fallback behavior, stale-state tests, accessibility, and polish.

## Session lifecycle

```text
created
â†’ active
â†’ paused, optional
â†’ ended
â†’ processing notes, optional
â†’ completed
â†’ deleted
```

## `interview_sessions` table

Recommended fields:

- `id`
- `user_id`
- `company`
- `position`
- `job_context_id`
- `started_at`
- `ended_at`
- `duration_seconds`
- `status`
- `question_count`
- `answer_count`
- `source_summary`
- `notes_status`
- `transcript_status`
- `created_at`
- `updated_at`

## Desktop behavior

- explicit Start Session action
- session ID created before events are stored
- questions/answers associated with session ID
- End Session finalizes metadata
- crash/restart recovery for active session
- optional auto-end after inactivity
- user can discard an accidental session

## Event model

Store interview events separately from summary tables.

Possible event types:

- session_started
- question_detected
- transcript_finalized
- answer_generated
- answer_failed
- screen_question_detected
- source_changed
- session_paused
- session_resumed
- session_ended

An event log may be implemented internally, but avoid overengineering if ordered transcript messages are sufficient.

## Idempotency

Every desktop event upload should include an idempotency key or client event ID.

This prevents duplicates during retries or reconnects.

## C6 API routes

Possible routes:

```text
POST  /api/sessions
GET   /api/sessions
GET   /api/sessions/{session_id}
PATCH /api/sessions/{session_id}
POST  /api/sessions/{session_id}/end
DELETE /api/sessions/{session_id}
```

## C6 tests

- create session
- list own sessions
- cannot access another user's session
- active-to-ended transition
- duplicate start retry
- duplicate event retry
- crash recovery
- delete
- empty session behavior
- session metadata accuracy

## C6 exit criteria

- desktop creates and ends sessions
- sessions appear on website
- ownership is enforced
- duplicate retries do not create duplicate sessions
- session metadata is reliable

---

# C7 â€” Transcript Storage, Viewing, and Download

## Status

```text
[ ] Not started
```

## Goal

Store the ordered conversation and make it available in the website Transcript tab.

## `transcript_messages` table

Recommended fields:

- `id`
- `user_id`
- `session_id`
- `client_event_id`
- `sequence_number`
- `speaker`
- `message_type`
- `text`
- `resolved_text`
- `category`
- `input_source`
- `provider`
- `model`
- `started_at`
- `ended_at`
- `created_at`

### Speaker values

- interviewer
- user
- assistant
- system

### Message type values

- question
- transcript
- generated_answer
- follow_up
- note
- error

### Input source values

- microphone
- system_audio
- screen
- manual
- imported

## Transcript ordering

Use:

- server sequence number, or
- client timestamp plus server timestamp and conflict handling

Do not rely only on UI arrival order.

## `ai_answers` table

Recommended fields:

- `id`
- `user_id`
- `session_id`
- `transcript_message_id`
- `question_text`
- `resolved_question_text`
- `answer_text`
- `category`
- `provider`
- `model`
- `profile_context_used`
- `job_context_used`
- `resume_chunk_ids`
- `latency_ms`
- `verified_status`
- `created_at`

## Website Transcript tab

Must support:

- ordered conversation
- timestamps
- question/answer distinction
- copy message
- search transcript
- filter by source/category, optional
- download
- delete session/transcript
- loading, empty, and error states

## Download formats

Initial:

- TXT
- Markdown or structured text

Later/optional:

- PDF
- DOCX
- JSON export

Exports must not expose internal prompts or hidden diagnostics unless explicitly intended.

## Export generation

Prefer backend-generated exports for consistent formatting.

Possible routes:

```text
GET /api/sessions/{id}/transcript
GET /api/sessions/{id}/transcript/export?format=txt
```

## C7 tests

- ordered message storage
- duplicate event protection
- transcript retrieval
- session ownership
- answer association
- TXT export
- empty transcript
- deleted session
- special characters
- large transcript pagination

## C7 exit criteria

- full session conversation is visible
- messages are ordered correctly
- download works
- ownership is enforced
- duplicate uploads do not duplicate content
- transcript can be deleted

---

# C8 â€” AI Notes Generation

## Status

```text
[ ] Not started
```

## Goal

Generate and store a structured summary of an interview session.

## AI Notes output

The notes should include, when supported by the transcript:

- company
- position
- overall summary
- questions asked
- topics covered
- important technical concepts
- strengths shown
- weak or unclear areas
- suggested revision topics
- unanswered or incomplete questions
- optional action items

Do not create unsupported claims about interviewer sentiment.

## `ai_notes` table

Recommended fields:

- `id`
- `user_id`
- `session_id`
- `version`
- `status`
- `summary`
- `questions`
- `topics`
- `strengths`
- `weaknesses`
- `revision_topics`
- `action_items`
- `provider`
- `model`
- `source_message_count`
- `generated_at`
- `created_at`
- `updated_at`

## Generation behavior

- notes are generated only for the session owner
- transcript is the primary source
- resume/job context may help label relevance but must not rewrite what occurred
- incomplete transcript must be marked accordingly
- regeneration creates a new version or deliberately replaces the previous version
- rate limits and failures must not corrupt existing notes

## API routes

Possible routes:

```text
POST /api/sessions/{id}/notes/generate
GET  /api/sessions/{id}/notes
POST /api/sessions/{id}/notes/regenerate
GET  /api/sessions/{id}/notes/export
```

## Background processing

For short sessions, synchronous generation may be acceptable initially.

For long sessions, design status values:

- pending
- generating
- complete
- failed

Do not add a heavy job queue unless needed. A lightweight background task may be used first.

## C8 tests

- successful notes generation
- empty transcript
- short transcript
- long transcript
- provider timeout
- provider rate limit
- regeneration
- ownership
- no unsupported sentiment claim
- saved previous notes survive failed regeneration

## C8 exit criteria

- user can generate notes
- notes appear in AI Notes tab
- notes are stored
- regeneration works
- failure is recoverable
- notes can be downloaded or copied

---

# C9 â€” Ask AI and Follow-Up Context Memory

## Status

```text
[ ] Not started
```

## Goal

Allow the user to ask questions about a saved interview session and correctly resolve follow-up references.

## Example

```text
Question 1: What is supervised learning?
Follow-up: What are its examples?
Resolved query: What are examples of supervised learning?
```

## Context sources

Ask AI may use:

- session transcript
- generated answers
- AI notes
- active job context
- user profile/resume context, when relevant
- previous Ask AI messages in the same thread

## Data model

### `ask_ai_threads`

- `id`
- `user_id`
- `session_id`
- `title`
- `created_at`
- `updated_at`

### `ask_ai_messages`

- `id`
- `user_id`
- `thread_id`
- `role`
- `content`
- `resolved_query`
- `context_message_ids`
- `provider`
- `model`
- `created_at`

## Follow-up resolver

Create a `follow_up_question_resolver` or equivalent.

Responsibilities:

- detect pronouns and elliptical follow-ups
- inspect recent topic/question context
- produce a resolved query
- preserve original user wording
- avoid changing clear standalone questions
- return uncertainty when multiple references are possible

Suggested resolution order:

1. deterministic heuristic
2. recent session/topic lookup
3. small model-assisted rewrite only when necessary
4. ask user for clarification when ambiguity remains

## Retrieval

For long sessions:

- retrieve relevant transcript messages
- include recent conversation turns
- optionally use AI Notes as a compact summary
- avoid sending entire transcript every time
- record which messages supported the answer

## Ask AI response rules

- answer the user's question
- distinguish session facts from general knowledge
- do not claim something occurred if it is absent from transcript
- cite or reference session moments in the UI where practical
- preserve privacy
- control token usage

## API routes

Possible routes:

```text
POST /api/sessions/{id}/ask
GET  /api/sessions/{id}/ask/threads
GET  /api/ask/threads/{thread_id}
DELETE /api/ask/threads/{thread_id}
```

## C9 tests

- standalone question
- pronoun follow-up
- topic continuation
- ambiguous follow-up
- unrelated new question
- long session retrieval
- no transcript evidence
- ownership
- thread persistence
- deletion

## C9 exit criteria

- Ask AI works on a session
- follow-ups resolve correctly in tested cases
- unsupported transcript claims are avoided
- threads persist
- long sessions use bounded context

---

# C10 â€” Resend Email System

## Status

```text
[ ] Not started
```

## Goal

Create a reliable email layer for authentication, transactional messages, and consent-based promotional communication.

## Email categories

### Transactional

- email verification
- welcome
- password reset, if custom
- login/security notification, optional
- interview summary ready
- payment success
- payment failure
- subscription renewal/cancellation
- data export ready

### Promotional

- product updates
- offers
- feature announcements
- educational content

Promotional email requires explicit consent and unsubscribe support.

## Configuration

Backend environment variables may include:

```env
RESEND_API_KEY=
RESEND_FROM_EMAIL=
RESEND_REPLY_TO=
RESEND_WEBHOOK_SECRET=
APP_PUBLIC_URL=
```

## `email_events` table

Recommended fields:

- `id`
- `user_id`
- `email_type`
- `recipient_hash_or_safe_reference`
- `provider_message_id`
- `status`
- `failure_reason`
- `created_at`
- `updated_at`

Do not store full email bodies unless required.

## Templates

Create versioned templates for:

- verification
- welcome
- interview notes ready
- payment confirmation
- payment failure
- cancellation
- marketing message

Templates should include:

- SAIIA branding
- clear CTA
- safe links
- support contact
- unsubscribe link for marketing
- no secrets in query strings

## Delivery rules

- idempotency for repeated events
- retry only transient failures
- avoid duplicate welcome/payment emails
- respect consent
- record provider status
- validate email webhook signatures if used

## C10 tests

- transactional send mock
- invalid email
- provider failure
- duplicate event
- marketing consent false
- unsubscribe
- webhook verification
- template rendering
- no secret leakage

## C10 exit criteria

- required emails send reliably
- marketing consent is enforced
- duplicate sends are prevented
- events are logged safely
- templates are reviewed

---

# C11 â€” Pricing and Subscription Foundation

## Status

```text
[ ] Not started
```

## Goal

Create plan definitions, subscription records, and backend feature-gate architecture before connecting real payments.

## Important rule

This phase does not process money yet.

It creates the stable contract that payment integration will update.

## Plan model

Initial conceptual plans:

- Free
- Student
- Pro
- Institution

Final prices and exact limits are business decisions and must not be hardcoded before approval.

## `plans` table

Recommended fields:

- `id`
- `code`
- `name`
- `description`
- `billing_interval`
- `price_minor`
- `currency`
- `features`
- `limits`
- `is_active`
- `display_order`
- `created_at`
- `updated_at`

## `subscriptions` table

Recommended fields:

- `id`
- `user_id`
- `plan_id`
- `provider`
- `provider_customer_id`
- `provider_subscription_id`
- `status`
- `current_period_start`
- `current_period_end`
- `cancel_at_period_end`
- `trial_end`
- `created_at`
- `updated_at`

## Subscription statuses

Support:

- free
- trialing
- active
- past_due
- paused
- canceled
- expired
- incomplete

## Feature-gate service

Create backend service:

```text
can_use_feature(user_id, feature_code)
get_feature_limit(user_id, feature_code)
get_subscription_status(user_id)
```

Feature codes may include:

- answer_generation
- transcription_minutes
- resume_upload
- resume_rag
- screen_read
- auto_listen
- session_history
- transcript_export
- ai_notes
- ask_ai
- priority_models

## Rules

- frontend display is informational
- backend is authoritative
- free plan assigned safely
- no paid access from frontend flags alone
- plan change logic is centralized
- desktop and website receive the same entitlement result

## API routes

Possible routes:

```text
GET /api/plans
GET /api/billing/subscription
GET /api/billing/entitlements
```

## C11 tests

- default free plan
- active plan
- canceled plan
- expired plan
- feature allowed
- feature blocked
- plan configuration change
- desktop and website entitlement parity
- no client-side bypass

## C11 exit criteria

- plans are represented in database
- subscription status is represented
- backend feature gates work
- current plan is visible to clients
- no real payment dependency exists yet

---

# C12 â€” Payment Provider Integration

## Status

```text
[ ] Not started
```

## Goal

Connect a real payment provider and synchronize payment state into SAIIA subscriptions.

## Provider decision gate

Choose:

- Razorpay for India-first billing
- Stripe for global-first billing
- or a provider abstraction supporting both

The final provider decision must be recorded before implementation.

## Provider abstraction

Recommended interface:

```text
create_customer
create_checkout
create_subscription
cancel_subscription
resume_subscription
get_subscription
verify_webhook
map_provider_status
```

## Backend routes

Possible routes:

```text
POST /api/billing/checkout
POST /api/billing/customer-portal
POST /api/billing/cancel
POST /api/billing/resume
POST /api/billing/webhook/{provider}
GET  /api/billing/invoices
```

## Webhook rules

- verify signature
- reject replay/invalid payload
- idempotently process events
- update subscription from provider event
- never trust redirect page alone
- log safe event metadata
- send email after confirmed state change
- handle out-of-order events

## `payment_events` table

Recommended fields:

- `id`
- `provider`
- `provider_event_id`
- `event_type`
- `user_id`
- `subscription_id`
- `status`
- `processed_at`
- `failure_reason`
- `created_at`

## Website states

- checkout loading
- payment success pending confirmation
- payment confirmed
- payment failed
- subscription active
- past due
- cancel at period end
- canceled
- invoice history

## Security

- payment secrets backend-only
- webhook secret protected
- no card data stored by SAIIA
- do not unlock feature until backend confirms subscription state
- log no sensitive payment details

## C12 tests

- checkout creation
- successful webhook
- invalid signature
- duplicate webhook
- out-of-order event
- failed payment
- cancellation
- renewal
- provider timeout
- entitlement update
- payment success email

## C12 exit criteria

- payment can create/update subscription
- webhook is authoritative
- duplicate events are safe
- feature gates update correctly
- billing states are visible
- payment secrets remain backend-only

---

# C13 â€” Usage Limits and Backend Feature Enforcement

## Status

```text
[ ] Not started
```

## Goal

Track expensive operations and enforce plan limits consistently.

## `usage_events` table

Recommended fields:

- `id`
- `user_id`
- `feature_code`
- `units`
- `session_id`
- `request_id`
- `provider`
- `model`
- `metadata`
- `created_at`

## `usage_monthly` table

Recommended fields:

- `id`
- `user_id`
- `period_start`
- `period_end`
- `feature_code`
- `used_units`
- `updated_at`

## Usage units

Examples:

- answer generation count
- transcription seconds/minutes
- Auto Mode minutes
- screen analyses
- AI Notes generations
- Ask AI messages
- resume extraction count
- export count

## Enforcement flow

```text
Authenticated request
â†’ Check entitlement
â†’ Check current usage
â†’ Reserve or authorize unit
â†’ Perform operation
â†’ Record successful usage
â†’ Roll back reservation on failure, if used
â†’ Return updated usage
```

## Rules

- do not count failed provider operations as successful usage unless business policy says otherwise
- prevent duplicate usage events using request ID
- define monthly reset behavior
- handle subscription upgrades/downgrades
- provide clear limit-reached errors
- backend must block over-limit requests
- desktop and website display current usage

## API routes

Possible routes:

```text
GET /api/usage
GET /api/usage/limits
```

## C13 tests

- free plan limit
- paid plan limit
- usage increment
- failed operation
- duplicate request
- monthly reset
- upgrade mid-period
- downgrade
- blocked feature
- website/desktop parity

## C13 exit criteria

- limits are backend-enforced
- usage is accurate
- duplicate events are prevented
- users see current usage
- plan changes affect access predictably

---

# C14 â€” Final Figma Website Implementation and Integration

## Status

```text
[ ] Not started
```

## Goal

Implement the approved Figma design and connect every production website screen to real backend data.

## Important clarification

Website integration may begin incrementally in C2â€“C13 using functional screens.

C14 is the final design-complete integration phase:

- visual parity
- navigation consistency
- responsive behavior
- complete states
- accessibility
- backend integration review
- removal of temporary developer UI

## Required website areas

### Public

- landing
- features
- how it works
- pricing
- FAQ
- contact/support
- privacy
- terms

### Auth

- signup
- login
- verify email
- forgot password
- reset password

### Dashboard

- profile status
- resume status
- job target
- desktop connection
- recent sessions
- current plan
- usage

### Resume and profile

- upload
- extraction loading
- review/edit
- save
- index status
- rebuild
- delete

### Job target

- company
- position
- JD paste/upload
- extracted fields
- save/delete

### Sessions

- list
- filters
- session detail
- AI Notes
- Transcript
- Ask AI

### Desktop connection

- download app
- connected device status
- sync status
- last sync

### Billing

- plans
- current subscription
- checkout result
- invoices
- cancel/renew

### Settings

- account
- profile
- notifications
- privacy
- billing
- export
- delete account

## Design integration requirements

- use approved typography and color tokens
- reusable components
- loading skeletons
- empty states
- success states
- field errors
- global error boundary
- responsive desktop/tablet/mobile behavior
- keyboard navigation
- focus states
- semantic labels
- accessible contrast
- no fake data in production screens

## API integration rules

- central API client
- auth token refresh
- consistent error format
- request cancellation
- loading state cleanup
- no service-role key in browser
- no direct sensitive operations without backend validation
- optimistic updates only where safe

## C14 tests

- navigation
- auth redirect
- resume flow
- job flow
- session list/detail
- transcript
- AI Notes
- Ask AI
- plan/usage
- billing
- settings
- responsive layouts
- keyboard accessibility
- error states

## C14 exit criteria

- approved Figma screens are implemented
- all production flows use real data
- temporary dev UI is removed
- responsive and accessibility checks pass
- backend integrations are complete

---

# C15 â€” Privacy, Export, Retention, and Deletion

## Status

```text
[ ] Not started
```

## Goal

Give users meaningful control over sensitive data and document what is stored.

## Sensitive data inventory

- profile
- resume file
- extracted resume text
- resume chunks/embeddings
- job descriptions
- interview sessions
- transcripts
- generated answers
- AI Notes
- Ask AI messages
- settings
- usage records
- payment references
- email events
- device/session metadata

## Privacy center

Website settings must explain:

- what is stored
- why it is stored
- which cloud providers process data
- retention behavior
- how to export
- how to delete
- marketing consent

## Export

Support user data export containing approved user-owned data.

Possible formats:

- JSON archive
- transcript TXT/Markdown
- notes export
- resume/profile summary

Do not include:

- secrets
- internal prompts
- provider credentials
- other users' data
- internal security metadata

## Deletion actions

- delete resume
- delete resume-derived chunks
- delete job context
- delete one session
- delete all session history
- delete AI Notes
- delete Ask AI threads
- clear settings
- delete account

## Account deletion workflow

- re-authentication
- confirmation
- optional waiting period
- cancel active subscription or instruct user
- remove/revoke tokens
- delete or anonymize data according to policy
- remove private files
- preserve only legally required billing records, if applicable
- send confirmation email

## Retention rules

Define and document:

- temporary audio retention
- screenshot retention
- failed upload cleanup
- export file expiry
- deleted-account cleanup
- audit/payment record retention

Default principle:

```text
Do not keep raw audio or screenshots longer than required for the immediate operation.
```

## Audit logging

Track sensitive operations such as:

- account login
- password change
- data export
- resume deletion
- session deletion
- account deletion
- subscription change

Do not store private content in audit logs.

## C15 tests

- export own data
- cannot export another user's data
- delete resume and chunks
- delete session
- delete all history
- revoke token
- account deletion
- storage cleanup
- retention cleanup
- marketing consent update

## C15 exit criteria

- privacy center exists
- export works
- deletion works
- storage cleanup works
- policies are documented
- sensitive logging review passes

---

# C15.5 — Internal Admin, Support, and Audit Console

## Status

```text
[ ] Not started - future conditional release phase
```

C15.5 is required before C16 only if SAIIA needs internal staff/admin/support operations for that release. If the product decision is that no internal admin/support console is needed before release, C16 may pass with C15.5 explicitly deferred, but that decision must be recorded in the open decisions register and final acceptance must mark C15.5 as deferred/not required for that release.

## Goal

Build a secure internal admin/support console where trusted SAIIA admins can manage support, account state, billing/usage visibility, privacy operations, and admin membership.

This is internal/admin tooling, not part of the normal candidate/user dashboard. It must not be implemented before C15.5, and it must not become a shortcut around RLS, user ownership, privacy rules, or backend authorization checks.

## Why C15.5 comes after C15

Admin access touches sensitive user data: profiles, resumes, transcripts, sessions, billing, usage, privacy/export/delete workflows, and audit logs. C15 defines the privacy, export, retention, and deletion rules first, and C15.5 admin tools must follow those rules.

Admin support must not be added during C2, C3, or C5 because early admin shortcuts would create privilege and security debt before user ownership, storage, privacy, and deletion behavior are complete.

## Scope

- admin authentication verification
- admin RBAC
- admin invitation/add-admin flow
- admin list/suspend/remove/role-change flow
- user search and account support
- safe user/account summary view
- profile/resume/session/billing/usage metadata views
- privacy/export/delete support tools
- break-glass workflow for raw sensitive data
- audit log for every admin action
- system health/config summary view
- tests and manual validation

## Out of scope

- public admin signup
- frontend-only admin flags
- service-role access from browser
- unaudited raw resume/transcript access
- direct payment-state override
- deleting audit logs from admin UI
- admin access before C15.5
- institution/multi-tenant organization administration unless separately approved
- sales CRM, analytics warehouse, or marketing admin unless separately approved

## Admin roles

Use a role-based model, not a single `is_admin` boolean.

- `owner`: can manage all admins, ownership, highest-risk settings, and last-owner recovery.
- `super_admin`: can manage most admin/support operations, but cannot remove the last owner.
- `support_admin`: can help users and view internal support metadata, but cannot access raw resume/transcript data by default.
- `billing_admin`: can view billing/usage and support billing issues; payment provider webhooks remain authoritative.
- `privacy_admin`: can manage export/delete workflows and privacy review tasks.
- `security_auditor`: can view audit/security events, but cannot mutate user data.
- `readonly_admin`: can view high-level operational dashboards only.

Rules:

- owner can manage all admins and ownership
- super_admin can manage most admin/support operations but cannot remove the last owner
- support_admin can help users but cannot access raw resume/transcript by default
- billing_admin can view billing/usage and support billing issues but payment webhook remains authoritative
- privacy_admin can manage export/delete workflows
- security_auditor can view audit/security events but not mutate user data
- readonly_admin can view high-level operational dashboards only

## Permissions model

Future C15.5 permission groups:

```text
admins:read
admins:self_read
admins:invite
admins:update_role
admins:suspend
admins:transfer_ownership
admins:revoke_non_owner
users:read
users:update_status
users:security_status_update
users:billing_status_update
users:force_logout
users:password_reset
support_notes:create
support_notes:read
support_notes:metadata_read
support_notes:delete_review
profile:metadata_read
resume:metadata_read
resume:retry_extraction
resume:rebuild_index
resume:raw_read_break_glass
sessions:metadata_read
transcripts:summary_read
transcripts:raw_read_break_glass
billing:read
billing:support_action
plans:read
plans:update
usage:read
usage:adjust
privacy:read
privacy:export_trigger
privacy:delete_review
privacy:delete_confirm
audit:read
break_glass:request
break_glass:approve
system:read
system:flags_update
```

This permissions map is future planning only and must not be implemented before C15.5.

Role-to-permission matrix:

| Role | Planned permission groups |
|---|---|
| owner | all C15.5 permissions, including admins:transfer_ownership and break-glass approval, with last-owner protection |
| super_admin | admins:self_read, admins:read, admins:invite, admins:update_role for non-owner roles, admins:suspend, admins:revoke_non_owner, users:read, users:update_status, users:security_status_update, users:billing_status_update, users:force_logout, users:password_reset, support_notes:read, support_notes:metadata_read, support_notes:create, support_notes:delete_review, profile:metadata_read, resume:metadata_read, resume:retry_extraction, resume:rebuild_index, sessions:metadata_read, transcripts:summary_read, billing:read, billing:support_action, plans:read, usage:read, usage:adjust, privacy:read, privacy:export_trigger, privacy:delete_review, privacy:delete_confirm, audit:read, break_glass:request, break_glass:approve, system:read, system:flags_update |
| support_admin | admins:self_read, users:read, users:update_status limited to active/support_locked/user_requested_hold transitions, users:password_reset, support_notes:read, support_notes:metadata_read, support_notes:create, profile:metadata_read, resume:metadata_read, resume:retry_extraction, resume:rebuild_index, sessions:metadata_read, transcripts:summary_read, break_glass:request, system:read |
| billing_admin | admins:self_read, users:read, users:billing_status_update, support_notes:read, support_notes:create, billing:read, billing:support_action, plans:read, usage:read, usage:adjust, audit:read |
| privacy_admin | admins:self_read, users:read, users:update_status for user_requested_hold only, support_notes:read, support_notes:create, support_notes:delete_review, profile:metadata_read, resume:metadata_read, sessions:metadata_read, transcripts:summary_read, privacy:read, privacy:export_trigger, privacy:delete_review, privacy:delete_confirm, audit:read, break_glass:request, break_glass:approve |
| security_auditor | admins:self_read, users:read at audit-safe metadata level, support_notes:metadata_read, audit:read, system:read |
| readonly_admin | admins:self_read, users:read at high-level metadata only, support_notes:metadata_read, billing:read summary only, usage:read summary only, audit:read summary only, system:read |

Route-to-permission matrix:

| Planned route | Required permission |
|---|---|
| GET /api/admin/me | admins:self_read |
| GET /api/admin/admins | admins:read |
| POST /api/admin/admins/invite | admins:invite |
| GET /api/admin/admin-invites | admins:read |
| POST /api/admin/admin-invites/{invite_id}/revoke | admins:invite |
| POST /api/admin/admin-invites/accept | valid invite plus authenticated matching user; no role claim trusted from frontend |
| PATCH /api/admin/admins/{admin_user_id}/role | admins:update_role; generic role route cannot create or remove owner role |
| PATCH /api/admin/admins/{admin_user_id}/suspend | admins:suspend; generic route rejects owner targets when unsafe |
| PATCH /api/admin/admins/{admin_user_id}/restore | admins:suspend |
| DELETE /api/admin/admins/{admin_user_id} | admins:revoke_non_owner; generic route rejects owner targets |
| POST /api/admin/admins/{admin_user_id}/transfer-ownership | admins:transfer_ownership |
| GET /api/admin/users | users:read |
| GET /api/admin/users/{user_id} | users:read |
| PATCH /api/admin/users/{user_id}/status | transition-specific permission: users:update_status, users:security_status_update, users:billing_status_update, privacy:delete_review, or privacy:delete_confirm |
| POST /api/admin/users/{user_id}/force-logout | users:force_logout |
| POST /api/admin/users/{user_id}/send-password-reset | users:password_reset |
| GET /api/admin/users/{user_id}/support-notes/metadata | support_notes:metadata_read |
| GET /api/admin/users/{user_id}/support-notes | support_notes:read |
| POST /api/admin/users/{user_id}/support-note | support_notes:create |
| POST /api/admin/users/{user_id}/support-notes/{note_id}/redact | support_notes:delete_review |
| POST /api/admin/users/{user_id}/support-notes/{note_id}/delete-review | support_notes:delete_review |
| GET /api/admin/users/{user_id}/profile/summary | profile:metadata_read |
| GET /api/admin/users/{user_id}/resumes | resume:metadata_read |
| GET /api/admin/users/{user_id}/resume-status | resume:metadata_read |
| POST /api/admin/users/{user_id}/resume/retry-extraction | resume:retry_extraction |
| POST /api/admin/users/{user_id}/resume/rebuild-index | resume:rebuild_index |
| GET /api/admin/users/{user_id}/sessions | sessions:metadata_read |
| GET /api/admin/sessions/{session_id}/metadata | sessions:metadata_read |
| GET /api/admin/sessions/{session_id}/transcript-summary | transcripts:summary_read |
| POST /api/admin/break-glass/request | break_glass:request |
| POST /api/admin/break-glass/{request_id}/approve | break_glass:approve |
| GET /api/admin/users/{user_id}/resume/raw with `X-SAIIA-Break-Glass-Grant` header | resume:raw_read_break_glass plus valid single-use break-glass grant |
| GET /api/admin/sessions/{session_id}/transcript/raw with `X-SAIIA-Break-Glass-Grant` header | transcripts:raw_read_break_glass plus valid single-use break-glass grant |
| GET /api/admin/users/{user_id}/subscription | billing:read |
| GET /api/admin/users/{user_id}/usage | usage:read |
| POST /api/admin/users/{user_id}/usage-adjustment | usage:adjust |
| GET /api/admin/plans | plans:read |
| PATCH /api/admin/plans/{plan_id} | plans:update |
| GET /api/admin/privacy/requests | privacy:read |
| GET /api/admin/users/{user_id}/privacy-summary | privacy:read |
| POST /api/admin/users/{user_id}/trigger-export | privacy:export_trigger |
| POST /api/admin/users/{user_id}/trigger-delete-review | privacy:delete_review |
| POST /api/admin/users/{user_id}/confirm-delete | privacy:delete_review plus valid one-time approved delete request |
| GET /api/admin/audit-logs | audit:read |
| GET /api/admin/security/events | audit:read |
| GET /api/admin/system/health | system:read |
| GET /api/admin/system/config-summary | system:read |
| PATCH /api/admin/system/flags/{flag_key} | system:flags_update |

Role-based field projection rules for `GET /api/admin/users` and `GET /api/admin/users/{user_id}`:

| Role | Server-side user projection |
|---|---|
| support_admin | id, email, account_status, created_at, last_seen_at if available, support-safe profile summary, resume/status metadata only; no billing details, no privacy/delete request details unless needed for support, no raw resume/transcript/session content, no internal security flags |
| security_auditor | id, account_status, admin/security event references, audit-safe metadata only; no email unless explicitly required for investigation, no support note body, no billing/payment details, no raw resume/transcript/session content |
| readonly_admin | aggregate/high-level metadata only, id or pseudonymized id where possible, account_status summary; no email by default, no support note body, no billing/payment details, no raw resume/transcript/session content, no privacy/delete request details |
| owner/super_admin | broader admin detail view according to permission checks, still no raw sensitive data without break-glass |

User projection rules:

- `users:read` is necessary but not sufficient
- backend must apply role-based field projection server-side
- `/api/admin/me` verifies the Supabase token, loads exactly one active admin_membership server-side, and returns only the caller's own admin identity, role, status, permissions, and safe UI flags
- suspended, revoked, or invited memberships cannot access the admin surface

## Database planning

Future C15.5-owned tables:

`admin_memberships`:

- id
- user_id references auth.users(id)
- role
- status: active | suspended | revoked | invited
- invited_by_user_id
- created_at
- updated_at
- last_admin_action_at
- revoked_at
- revoked_by_user_id
- revocation_reason

Membership cardinality:

- one authoritative admin membership per user
- `user_id` must be unique
- no multiple active/suspended/revoked rows for the same user
- role/status updates must be transactional
- concurrent role/status changes must serialize or conflict safely
- permission resolution loads exactly one active membership server-side
- suspended/revoked membership grants no permissions
- account deletion or admin removal transitions membership to revoked or pseudonymized revoked according to C15 retention rules

`admin_invites`:

- id
- email
- role
- invite_token_hash
- invited_by_user_id
- expires_at
- accepted_at
- revoked_at
- created_at

`admin_audit_logs`:

- id
- actor_user_id
- actor_role
- action
- target_type
- target_user_id
- target_record_id
- reason
- metadata
- ip_hash_or_safe_ref
- user_agent_safe_ref
- created_at

`admin_support_notes`:

- id
- target_user_id
- author_admin_user_id
- author_admin_role
- body
- visibility: internal_support | privacy_review | billing_review
- status: active | redacted | deletion_pending | deleted
- retention_class
- related_audit_log_id
- created_at
- updated_at
- redacted_at
- deleted_at
- deletion_reviewed_by_admin_user_id

`admin_break_glass_requests`:

- id
- actor_user_id
- target_user_id
- target_record_id
- target_record_type: resume | session | transcript | other approved type
- data_type
- reason
- status: requested | approved | denied | expired | used
- approved_by_user_id
- grant_hash_or_safe_ref
- expires_at
- created_at
- used_at

`admin_delete_review_requests`:

- id
- target_user_id
- requested_by_admin_user_id
- approved_by_admin_user_id
- status: requested | approved | denied | expired | consumed | cancelled
- reason
- approval_reason
- expires_at
- approved_at
- consumed_at
- created_at
- updated_at
- related_audit_log_id
- consumed_by_admin_user_id

`admin_system_flags`:

- id
- key
- value
- updated_by_user_id
- updated_at

Rules:

- no service-role keys stored
- no raw JWTs stored
- no passwords stored
- invite tokens stored hashed only
- audit logs append-only from application behavior and database enforcement
- destructive actions require reason
- admin_support_notes body length capped, for example 2,000 or 4,000 characters
- admin_support_notes must not contain raw resume, transcript, audio, screenshot, token, key, or password content
- admin_support_notes are user-targeted and author-owned by admin id
- admin_support_notes fall under C15 retention/export/delete governance
- normal users must not read admin_support_notes through RLS or normal user routes
- admin_support_notes reads/writes require admin route, backend RBAC, audit logging, and reason where sensitive
- admin_support_notes deletion/redaction follows C15 privacy/legal retention rules
- support-note creation must create or link an admin_audit_logs row
- admin_support_notes are internal operational records
- C15 user exports omit raw internal support notes by default
- C15 user exports may include only redacted or summarized support-note metadata when legally or product-required
- support-note redaction/delete review requires `support_notes:delete_review`, reason, audit log, and C15 retention/legal check
- RLS must deny normal user access and require backend/admin-controlled access

Support-note visibility-to-role matrix:

| Visibility | Role access |
|---|---|
| internal_support | support_admin may read/create only internal_support; super_admin may read/create with reason/audit; owner may read/create with audit |
| privacy_review | privacy_admin may read/create only privacy_review; super_admin may read/create with reason/audit; owner may read/create with audit |
| billing_review | billing_admin may read/create only billing_review; super_admin may read/create with reason/audit; owner may read/create with audit |

Additional support-note visibility rules:

- `support_notes:read` is necessary but not sufficient
- `support_notes:create` is necessary but not sufficient
- backend must enforce both permission and visibility-to-role matrix
- cross-visibility access is denied by default
- `security_auditor` may read all visibility metadata/audit view only, with no create or mutate permission
- `readonly_admin` may read high-level metadata only, with no body access unless explicitly approved later
- normal users cannot read support notes

User account status model:

```text
active
support_locked
user_requested_hold
disabled_by_security
pending_deletion
deleted
billing_restricted
```

`support_admin` status transitions:

- allowed: active -> support_locked
- allowed: support_locked -> active
- allowed: active -> user_requested_hold
- allowed: user_requested_hold -> active
- not allowed: disabled_by_security
- not allowed: pending_deletion
- not allowed: deleted
- not allowed: billing_restricted
- not allowed: any security-risk, deletion, privacy, or billing status transition

Status transition rules:

- `users:update_status` is necessary but not sufficient
- route handler must enforce the transition table server-side
- active <-> support_locked requires `users:update_status`; allowed roles are support_admin, super_admin, owner
- active <-> user_requested_hold requires `users:update_status`; allowed roles are support_admin, privacy_admin, super_admin, owner; reason and audit are required
- any -> disabled_by_security requires `users:security_status_update`; owner/super_admin may mutate; security_auditor may recommend only unless later approved; step-up and audit are required
- disabled_by_security -> active requires `users:security_status_update`; allowed roles are owner or super_admin; step-up and audit are required
- any -> billing_restricted requires `users:billing_status_update`; allowed roles are billing_admin, super_admin, owner; audit is required
- billing_restricted -> active requires `users:billing_status_update`; allowed roles are billing_admin, super_admin, owner; audit is required
- any -> pending_deletion requires `privacy:delete_review`; allowed roles are privacy_admin, super_admin, owner; pending approved delete-review request tied to target_user_id, step-up/re-auth, and audit are required
- pending_deletion -> deleted requires `privacy:delete_confirm`; allowed roles are privacy_admin, super_admin, owner; approved unexpired unconsumed delete-review request tied to target_user_id, atomic request consumption, and audit are required

`admin_audit_logs` immutability rules:

- append-only must be enforced at the database layer, not only by application behavior
- no normal UPDATE or DELETE policy
- no-update/no-delete behavior must be validated for normal admin and user-access paths
- no admin UI update/delete action
- service-role maintenance must not silently mutate logs
- exceptional maintenance must use a restricted, documented, separately audited maintenance path
- correction or superseding log entries are preferred over editing old logs

`admin_system_flags` allowlisted flag catalog:

- every mutable flag key must be defined in a future allowlisted flag catalog
- each catalog entry must define key, type, allowed values/range, protected flag, required permission, step-up requirement for high-risk flags, and audit reason requirement
- supported value types are boolean, string enum, integer bounded, and json schema
- unknown flag keys are rejected
- invalid typed values are rejected
- protected flags cannot be changed through normal admin UI
- security/lifecycle-critical flags require stricter approval or are read-only
- `PATCH /api/admin/system/flags/{flag_key}` must validate against the catalog server-side before persistence

C15.5 retention/delete/anonymization plan:

| Table | ON DELETE behavior | Identifier handling | Retention/export/delete behavior |
|---|---|---|---|
| admin_memberships | restrict physical delete while audit records reference membership; status becomes revoked/pseudonymized where required by C15 | retain or pseudonymized user_id/admin_id according to C15 retention window | not exported to normal users except required metadata; account deletion preserves audit-safe membership history only |
| admin_invites | invite rows expire/revoke instead of hard delete during active retention | invite email may be hashed/pseudonymized after expiry window | excluded from user export by default; deleted or pseudonymized per C15 retention rules |
| admin_audit_logs | append-only; no normal ON DELETE path | actor/target references retained only as long as C15 allows, then pseudonymized where needed | audit preservation required; export only audit-safe metadata when legally/product-required |
| admin_support_notes | redacted/deletion_pending/deleted states instead of raw hard delete until retention review completes | target_user_id and author_admin_user_id retained or pseudonymized per C15 | raw internal notes omitted from C15 user exports by default; redacted metadata only when required; deletion review audited |
| admin_break_glass_requests | expire/use/deny states preserved as audit-safe records | actor/target identifiers pseudonymized after retention window where allowed | retain audit-safe metadata only; raw sensitive payload never stored |
| admin_system_flags | global admin records; no user-owned delete behavior; changes recorded through audit log | should not contain personal data | admin_system_flags remain unchanged by user/account deletion and are not part of user export/delete except audit references if required |

User-linked admin records are `admin_memberships`, `admin_invites`, `admin_audit_logs`, `admin_support_notes`, and `admin_break_glass_requests`. Global admin records are `admin_system_flags`. Account deletion tests must cover user-linked admin records and must verify deleting a user with admin records does not mutate global `admin_system_flags`.

## Future API route plan

These routes are future C15.5-owned planning only.

Admin identity:

```text
GET /api/admin/me
```

Admin membership:

```text
GET /api/admin/admins
POST /api/admin/admins/invite
GET /api/admin/admin-invites
POST /api/admin/admin-invites/{invite_id}/revoke
POST /api/admin/admin-invites/accept
PATCH /api/admin/admins/{admin_user_id}/role
PATCH /api/admin/admins/{admin_user_id}/suspend
PATCH /api/admin/admins/{admin_user_id}/restore
DELETE /api/admin/admins/{admin_user_id}
POST /api/admin/admins/{admin_user_id}/transfer-ownership
```

User support:

```text
GET /api/admin/users
GET /api/admin/users/{user_id}
PATCH /api/admin/users/{user_id}/status
POST /api/admin/users/{user_id}/force-logout
POST /api/admin/users/{user_id}/send-password-reset
GET /api/admin/users/{user_id}/support-notes/metadata
GET /api/admin/users/{user_id}/support-notes
POST /api/admin/users/{user_id}/support-note
POST /api/admin/users/{user_id}/support-notes/{note_id}/redact
POST /api/admin/users/{user_id}/support-notes/{note_id}/delete-review
```

Profile/resume support:

```text
GET /api/admin/users/{user_id}/profile/summary
GET /api/admin/users/{user_id}/resumes
GET /api/admin/users/{user_id}/resume-status
POST /api/admin/users/{user_id}/resume/retry-extraction
POST /api/admin/users/{user_id}/resume/rebuild-index
```

Sessions/transcripts:

```text
GET /api/admin/users/{user_id}/sessions
GET /api/admin/sessions/{session_id}/metadata
GET /api/admin/sessions/{session_id}/transcript-summary
```

Break-glass:

```text
POST /api/admin/break-glass/request
POST /api/admin/break-glass/{request_id}/approve
GET /api/admin/users/{user_id}/resume/raw
Header: X-SAIIA-Break-Glass-Grant: <single-use grant>

GET /api/admin/sessions/{session_id}/transcript/raw
Header: X-SAIIA-Break-Glass-Grant: <single-use grant>
```

Billing/usage:

```text
GET /api/admin/users/{user_id}/subscription
GET /api/admin/users/{user_id}/usage
POST /api/admin/users/{user_id}/usage-adjustment
GET /api/admin/plans
PATCH /api/admin/plans/{plan_id}
```

Privacy/export/delete:

```text
GET /api/admin/privacy/requests
GET /api/admin/users/{user_id}/privacy-summary
POST /api/admin/users/{user_id}/trigger-export
POST /api/admin/users/{user_id}/trigger-delete-review
POST /api/admin/users/{user_id}/confirm-delete
```

Audit/system:

```text
GET /api/admin/audit-logs
GET /api/admin/security/events
GET /api/admin/system/health
GET /api/admin/system/config-summary
PATCH /api/admin/system/flags/{flag_key}
```

No `/api/admin` route may trust frontend role claims alone. Every admin route must verify the Supabase user token, load admin membership server-side, check role permission, and write an audit log for sensitive actions.

## Future frontend route plan

Future C15.5-owned admin frontend routes:

```text
/admin
/admin/users
/admin/users/:userId
/admin/admins
/admin/invites
/admin/audit
/admin/billing
/admin/usage
/admin/privacy
/admin/system
/admin/break-glass
```

UI states:

- not admin
- admin suspended
- loading permissions
- permission denied
- break-glass required
- destructive confirmation
- audit reason required
- action succeeded
- action failed
- invite expired
- last-owner protection

## Admin invite/add-admin flow

1. owner/super_admin enters invite email and role
2. backend validates actor permission
3. backend creates hashed invite token
4. invitation email is sent through the approved email system when available
5. invitee must authenticate through Supabase
6. backend matches invite email to authenticated user
7. admin_membership is created/activated
8. audit log is written
9. invite expires or can be revoked

Rules:

- only owner can invite owner
- super_admin can invite non-owner roles if allowed
- no self-promotion
- no last-owner removal
- no public admin registration
- all admin role changes audited

Invite accept contract:

- validate invite_token_hash
- validate authenticated email matches invite email
- require accepted_at is null
- require revoked_at is null
- require expires_at > now
- create or activate admin_membership
- set accepted_at
- write audit log
- all accept steps must happen in one transaction
- concurrent acceptance cannot create duplicate membership
- replay after accepted_at is rejected
- revoked or expired invite is rejected
- invite role cannot bypass owner/super_admin invitation rules

## Ownership transfer rules

- only an active owner can transfer ownership
- target must be an active authenticated admin account
- target role must become owner or be promoted atomically during transfer
- last-owner protection must remain enforced
- no self-demotion that leaves zero owners
- MFA/step-up authentication is required before transfer
- reason is required
- audit log is required
- ownership transfer cannot be authorized from frontend role claims
- backend must reload admin membership server-side before transfer
- transfer must be atomic with audit log creation
- failed transfer must not partially change roles
- generic role route cannot create owner role
- generic role route cannot remove owner role
- suspend/delete routes cannot suspend/delete an owner if that violates last-owner protection
- every ownership change must use `POST /api/admin/admins/{admin_user_id}/transfer-ownership`

## Break-glass sensitive-data access

- raw resume text and raw transcripts are not visible by default
- support/admin views show metadata and summaries first
- raw sensitive access requires break-glass request
- break-glass requires reason
- high-risk access requires approval by owner/super_admin/privacy_admin depending on data type
- break-glass expires
- every use is audited
- UI must clearly mark sensitive access
- access should be minimized and time-limited
- raw access must atomically validate authenticated actor, target_user_id, target_record_id, data_type, approval status, expiry, and unused state
- authorization is single-use and must be consumed or marked used atomically in the same transaction as the access grant/check
- replay and concurrent reuse must be rejected
- requester cannot approve their own request
- approver must have `break_glass:approve` and the required role for the data type
- raw access actor must match the approved actor or a documented approved access subject
- target mismatch and data-type mismatch must be rejected
- raw access must use `X-SAIIA-Break-Glass-Grant` header, never a URL query parameter
- the `X-SAIIA-Break-Glass-Grant` header must be treated as sensitive
- logs, traces, analytics, error reports, request dumps, and audit metadata must redact this header
- never place break-glass grant IDs in URLs, query strings, browser history, or frontend route params
- audit logs should record a safe grant reference/hash, not the raw grant value
- resume raw access must validate target_user_id plus target_record_id matching resume_id or the current resume record
- transcript raw access must validate target_user_id plus target_record_id matching session_id
- the `X-SAIIA-Break-Glass-Grant` header must be atomically checked against actor, target_user_id, target_record_id, target_record_type/data_type, approval status, expiry, and unused state

## Billing/usage admin rules

- payment provider webhook remains authoritative
- admin cannot simply mark a payment successful
- admin may view subscription/usage state
- usage adjustments require reason and audit log
- plan edits require high privilege
- billing actions should avoid exposing card/payment secrets

## Privacy/delete admin rules

- privacy/delete workflows depend on C15
- admin can help trigger export/delete review
- destructive deletion requires confirmation and reason
- user-owned files, rows, and derived data cleanup must follow C15 rules
- billing/legal retention exceptions must be documented
- trigger-delete-review creates a pending delete review request tied to target_user_id
- confirm-delete requires a pending approved request
- confirm-delete requires target_user_id match
- confirm-delete requires authenticated actor match or authorized privacy_admin/super_admin/owner according to policy
- confirm-delete requires explicit confirmation or step-up/re-authentication
- confirm-delete requires request not expired and not already-consumed
- confirm-delete consumes the request atomically during successful deletion confirmation
- missing, mismatched, expired, already-consumed, or replayed requests are rejected
- audit log is written for trigger, approval, confirmation, cancellation, and failure
- `privacy:delete_review` is necessary but not sufficient
- trigger-delete-review creates `admin_delete_review_requests` in requested state
- approval moves requested -> approved
- confirm-delete requires approved, unexpired, unconsumed `admin_delete_review_requests` tied to target_user_id
- missing, mismatched, expired, denied, cancelled, consumed, or replayed delete-review requests are rejected
- every `admin_delete_review_requests` state transition writes an audit log

## Security rules

- no service-role key in frontend
- no frontend-only `admin=true` flag
- no localStorage role authority
- no unaudited admin action
- no raw resume/transcript access by default
- no admin can delete audit logs from the UI
- no last-owner deletion
- no open admin registration
- no admin invite without owner/super_admin permission
- no destructive action without reason
- no cross-user user data access without admin route, permission check, and audit log
- no admin data access from normal user routes
- no payment status override without provider/webhook consistency
- MFA or step-up authentication is required by default for high-risk admin actions
- C15.5 implementation must enforce MFA/step-up auth for high-risk actions or document a threat-model exception with compensating controls before build starts

High-risk actions requiring MFA/step-up by default:

- admin role changes
- admin invite and ownership changes
- break-glass approval
- break-glass raw access/use
- privacy delete confirmation
- account suspension/restore when high risk
- usage adjustments
- plan updates
- system flag updates

## Tests

- route-to-permission matrix coverage
- role-based field projection hides forbidden user fields for support_admin, security_auditor, and readonly_admin
- `/api/admin/me` works for every active admin role with `admins:self_read`
- `/api/admin/me` rejects suspended/revoked/invited memberships
- each role only has assigned permissions
- support-note cross-visibility access denied by default
- support_admin status transitions limited to support_locked and user_requested_hold flows
- authorized and denied disabled_by_security status transitions
- authorized and denied billing_restricted status transitions
- pending_deletion requires approved delete-review request
- deleted requires atomic confirm-delete request consumption
- non-admin rejected
- suspended admin rejected
- readonly admin cannot mutate
- support admin cannot access billing mutation
- billing admin cannot access raw resumes
- privacy admin can trigger export/delete workflows but cannot bypass confirmation
- super_admin can invite support_admin
- owner can invite owner
- last owner cannot be removed
- invite token expires
- invite token is hashed
- revoked invite cannot be used
- every sensitive action creates audit log
- raw resume requires break-glass
- raw transcript requires break-glass
- break-glass expires
- break-glass self-approval rejected
- break-glass target binding enforced
- break-glass data-type binding enforced
- break-glass resume target mismatch rejected
- break-glass transcript/session target mismatch rejected
- break-glass replay rejected
- break-glass concurrent-use rejected
- expired and already-used break-glass approvals rejected
- audit-log UPDATE rejected
- audit-log DELETE rejected
- restricted maintenance path audited
- support-note ownership verified
- support-note read permission enforced
- support-note create permission enforced
- support-note redaction/delete-review permission enforced
- support-note retention/deletion verified
- support-note raw sensitive data prohibited
- normal user support-note access rejected
- support-note C15 user exports follow the documented redacted-metadata decision
- support-note audit link exists
- one authoritative admin membership per user enforced by unique user_id
- concurrent role changes serialize or conflict safely
- conflicting active/suspended membership rows rejected
- generic role patch to owner rejected
- generic role patch removing owner rejected
- unsafe owner suspend/delete blocked
- generic delete owner rejected
- generic suspend owner rejected when unsafe
- every owner change requires transfer-ownership route
- unknown flag rejected
- invalid flag value rejected
- protected flag mutation rejected
- valid allowlisted flag update accepted
- accepted-invite replay rejected
- concurrent invite acceptance cannot create duplicate membership
- missing delete request rejected
- delete request target mismatch rejected
- expired delete request rejected
- denied delete request rejected
- cancelled delete request rejected
- already-consumed delete request rejected
- delete request replay rejected
- concurrent confirm-delete cannot consume the same request twice
- successful delete confirmation consumes request atomically
- deleting a user with admin records does not mutate global admin_system_flags
- owner can transfer ownership to eligible admin
- non-owner cannot transfer ownership
- super_admin cannot transfer ownership unless explicitly approved later
- ownership transfer requires MFA/step-up
- ownership transfer writes audit log
- last-owner protection blocks unsafe ownership transfer
- failed ownership transfer does not partially change roles
- ownership-transfer route requires `admins:transfer_ownership`
- MFA/step-up required for high-risk actions
- destructive delete requires reason
- service-role key absent from frontend bundle
- normal user routes/RLS behavior unaffected
- admin cannot access another user's data through normal user endpoints
- admin access through normal user endpoints rejected
- payment webhook remains authoritative

## Manual validation

- create first owner safely
- invite support admin
- accept invite
- login as support admin
- verify allowed user support views
- verify forbidden billing/privacy/raw data actions
- login as billing admin
- verify billing/usage visibility
- login as privacy admin
- trigger export/delete review flow
- attempt last-owner removal and confirm blocked
- attempt raw resume/transcript access without break-glass and confirm blocked
- approve break-glass and confirm access expires
- attempt break-glass self-approval and confirm blocked
- attempt break-glass replay/concurrent reuse and confirm blocked
- attempt break-glass target/data-type mismatch and confirm blocked
- attempt admin_audit_logs UPDATE and DELETE through normal admin paths and confirm blocked
- verify restricted audit-log maintenance path creates a separate audit record
- create support note and verify admin ownership, retention class, and audit link
- verify support-note read/create/redaction/delete-review permissions by role
- verify support-note visibility-to-role matrix and cross-visibility denial
- verify normal users cannot read support notes
- verify C15 user exports omit raw internal support notes and include only redacted metadata when required
- verify support-note retention/deletion review is audited
- verify support notes reject raw sensitive resume/transcript/audio/screenshot content
- transfer ownership from owner to eligible admin and verify audit log
- attempt ownership transfer as non-owner and super_admin and confirm blocked
- attempt generic role patch to create/remove owner and confirm blocked
- attempt unsafe owner suspend/delete and confirm blocked
- attempt ownership transfer without MFA/step-up and confirm blocked
- attempt unsafe last-owner transfer and confirm blocked
- simulate failed ownership transfer and confirm no partial role change
- accept admin invite once, then verify accepted_at replay is rejected
- simulate concurrent invite acceptance and verify one membership only
- verify unknown/protected/invalid system flag updates are rejected
- verify privacy confirm-delete rejects missing, mismatched, expired, already-consumed, and replayed requests
- verify successful privacy confirm-delete consumes the approved request atomically
- verify account deletion behavior for user-linked admin records
- verify deleting a user with admin records does not mutate global admin_system_flags
- verify MFA/step-up challenge for high-risk actions
- verify normal user routes cannot access admin data
- verify audit logs for every action

## C15.5 exit criteria

C15.5 is complete only if it is required for the release and all criteria below pass. If it is not required, it must remain clearly deferred/not required in the release decision record and final acceptance.

- admin roles exist
- role-to-permission and route-to-permission matrices are implemented and validated
- support-note visibility-to-role matrix is implemented and validated
- support_admin status transition table is implemented and validated
- admin_memberships has one authoritative membership per user and concurrent role/status changes are safe
- admin_memberships uses revoked, not deleted, for admin removal/account-deletion retention state
- admin_system_flags use an allowlisted flag catalog with unknown/protected/invalid updates rejected
- admin_system_flags remain unchanged by user/account deletion
- privacy delete confirmation requires and atomically consumes a valid pending approved request
- admin invite acceptance is atomic, exactly-once, replay-safe, and concurrency-safe
- admin invite/add-admin flow works
- admin routes are protected by backend RBAC
- admin frontend exists
- all admin actions are audited
- audit logs are database-enforced append-only, with UPDATE/DELETE rejection validated
- restricted maintenance path is separately audited
- support notes are implemented with ownership, retention/deletion, sensitive-content prohibition, and audit linkage
- support-note read/create/redaction/delete-review permissions are validated
- C15 user exports omit raw internal support notes by default and include only redacted metadata when required
- ownership transfer is implemented with `admins:transfer_ownership`, owner-only authorization, MFA/step-up, atomic role change, audit logging, and last-owner protection
- raw sensitive data access requires break-glass
- break-glass is single-use, target-bound, data-type-bound, expiry-bound, self-approval-safe, and replay/concurrent-use-safe
- MFA/step-up authentication is enforced for high-risk actions or an approved threat-model exception with compensating controls is recorded
- billing/usage/user support views work
- privacy/export/delete support tools work
- service-role key never reaches frontend
- last-owner protection works
- tests pass
- manual validation passes
- docs are updated
- no normal user route was weakened

## C15.5 subphases

- C15.5.1 — Admin architecture and threat model
- C15.5.2 — Admin schema and RBAC permissions
- C15.5.3 — Admin verification dependency and audit logging
- C15.5.4 — Admin invite/add-admin flow
- C15.5.5 — User/support management APIs
- C15.5.6 — Billing/usage/privacy admin APIs
- C15.5.7 — Admin frontend console
- C15.5.8 — Admin security closure and manual validation

---

# C16 â€” QA, Deployment, Packaging Readiness, and Release

## Status

```text
[ ] Not started
```

## Goal

Validate the complete product and release a stable website, backend, database configuration, and desktop build path.

## Environments

At minimum:

- local development
- staging
- production

Each environment must have:

- separate secrets
- separate database or isolated project
- separate payment mode
- separate email configuration
- safe logging
- documented URLs

## Backend deployment

Requirements:

- HTTPS
- environment configuration
- health endpoint
- database migration on deploy
- timeout/retry configuration
- structured logging
- error monitoring
- CORS policy
- secure headers
- rate limits
- backup/restore plan

## Website deployment

Requirements:

- production build
- environment variables
- auth redirects
- custom domain
- error pages
- analytics only with privacy review
- sitemap/metadata where relevant
- legal pages
- support contact

## Desktop release readiness

Requirements:

- production API base URL
- secure token storage
- login flow
- updater strategy, if implemented
- installer plan
- code signing plan
- clean uninstall behavior
- no bundled secrets
- first-run dependency checks
- crash recovery
- logs accessible to user without exposing secrets

## QA matrix

### Authentication

- signup
- verification
- login
- logout
- password reset
- expired session
- desktop login

### Profile/resume

- upload
- extraction
- confirmation
- indexing
- replacement
- deletion

### Job context

- create
- edit
- activate
- delete
- desktop sync

### Live interview

- manual microphone
- system audio
- Auto Mode
- overlay
- provider failure
- rate limit
- network interruption

### Sessions

- create
- resume after interruption
- end
- transcript
- notes
- Ask AI
- delete

### Subscription

- free access
- paid access
- limit reached
- checkout
- webhook
- cancellation
- failed payment

### Privacy

- export
- delete
- account deletion
- user isolation

## Reliability testing

- repeated 30â€“60 minute desktop session
- provider timeouts
- backend restart
- internet loss/recovery
- token expiry
- duplicate event retries
- large transcript
- long resume
- concurrent website/desktop use

## Security review

- secrets scan
- dependency audit
- RLS verification
- webhook verification
- auth bypass test
- IDOR/ownership test
- upload validation
- CORS review
- rate-limit review
- logging review

## C16.1 - Production Auth Hardening

### Desktop Website-Login Handoff Production Hardening

Goal: replace the C6.2A process-local desktop handoff memory store with a production-safe shared atomic TTL-backed store before any multi-worker, multi-instance, or public production deployment.

Current C6.2A status:

- Website login succeeds.
- Backend creates a short-lived desktop handoff code.
- Electron receives `saiia://auth/callback?handoff_code=...&state=...`.
- Electron main process exchanges the handoff code.
- Renderer never receives raw tokens.
- Current handoff records are short-lived, one-time-use, bounded per user, and rate-limited.
- Current handoff code dictionary keys are SHA-256 hashes, not raw handoff codes.
- Current handoff storage is process-local memory and is dev/local only.

Known limitation:

- The memory store is lost on backend restart.
- Multiple backend workers or instances cannot share handoff records.
- Concurrent requests can bypass non-atomic check-then-insert limits.
- Process-local limits and rate limits do not protect deployment-wide traffic.

Production requirements:

1. Use a shared store: Supabase/Postgres TTL-backed table plus atomic RPC/transaction, or Redis with atomic TTL operations.
2. Preserve a short TTL: 2-5 minutes maximum handoff lifetime.
3. Preserve one-time use: a handoff code can be exchanged only once.
4. Store only safe identifiers: store SHA-256 hash of the handoff code and never store the raw handoff code as a lookup key.
5. Maintain token safety: never place `access_token` or `refresh_token` in URLs, never expose raw session/tokens to Electron renderer/preload, and never log tokens, refresh tokens, raw handoff codes, or code hashes.
6. Make creation atomic: prune expired records, check the per-user active handoff limit, check the per-user create rate limit, insert the new handoff, and update the creation timestamp in one shared-store transaction/operation.
7. Make exchange atomic: validate code hash, validate state, validate expiry, mark consumed/delete the record, and return session data only to Electron main process atomically.
8. Ensure deployment safety across backend restarts, multiple backend workers, and multiple backend instances.
9. Ensure expired handoff records do not accumulate by TTL, scheduled cleanup, or expiry-filtered RPC/delete.
10. Add tests for valid create/exchange, reused handoff rejection, expired handoff rejection, mismatched state rejection, raw handoff code not stored, active handoff limit, create rate limit, concurrent duplicate create requests not bypassing limits, concurrent duplicate exchange requests not both succeeding, and multi-worker/multi-instance behavior through integration tests or explicit deployment test documentation.

Acceptance criteria:

- C6.2A memory-only handoff store is clearly marked as dev/local only.
- Production release checklist blocks release until shared atomic handoff store is implemented.
- No production documentation claims the memory store is production-safe.
- The roadmap/tracker shows this as a required production hardening item before public release.

## Documentation

Required:

- production setup
- local development
- environment variables
- migrations
- deployment
- desktop run/build
- payment setup
- Resend setup
- Supabase setup
- backup/restore
- troubleshooting
- privacy/data deletion
- release checklist

## C16 exit criteria

- C16.1 Production Auth Hardening is complete, including shared atomic TTL-backed desktop website-login handoff storage.
- staging end-to-end flow passes
- production deployment passes smoke test
- database/RLS tests pass
- payment test mode passes
- website and desktop use production backend correctly
- release checklist is signed off
- known limitations are documented
- rollback plan exists

---

## 8. Cross-Phase Database Map

The complete expected database direction is:

```text
auth.users
    |
    +-- profiles
    +-- resumes
    |      +-- resume_chunks
    +-- job_contexts
    +-- user_settings
    +-- interview_sessions
    |      +-- transcript_messages
    |      +-- ai_answers
    |      +-- ai_notes
    |      +-- ask_ai_threads
    |             +-- ask_ai_messages
    +-- subscriptions
    +-- usage_events
    +-- usage_monthly
    +-- email_events
    +-- payment_events
    +-- user-linked branch (future C15.5)
    +-- admin_memberships          (future C15.5)
    +-- admin_invites              (future C15.5)
    +-- admin_audit_logs           (future C15.5)
    +-- admin_support_notes        (future C15.5)
    +-- admin_break_glass_requests (future C15.5)
    +-- admin_delete_review_requests (future C15.5)

global admin branch
    +-- admin_system_flags         (future C15.5)
```

Not every table must be created in C1. Create each table in the phase that owns it, using migrations. The admin-owned tables above belong to future C15.5, not the C1 cloud foundation. `admin_system_flags` is not user-owned, user/account deletion must not mutate it, and any user reference on it must be an audit-safe or pseudonymized reference if needed.

---

## 9. Cross-Phase API Map

Expected API groups:

```text
/api/auth/*
/api/profile/*
/api/resumes/*
/api/job-contexts/*
/api/sessions/*
/api/sessions/{id}/transcript/*
/api/sessions/{id}/notes/*
/api/sessions/{id}/ask/*
/api/plans
/api/billing/*
/api/usage/*
/api/settings/*
/api/privacy/*
/api/admin/*     (future C15.5 only)
```

Existing desktop routes such as transcription, classification, and generation must remain compatible until an intentional migration is completed.

---

## 10. Follow-Up Question Memory Design

This requirement must not be forgotten.

### Core behavior

When a follow-up depends on an earlier topic:

```text
Earlier: What is supervised learning?
Follow-up: What are its examples?
```

SAIIA should resolve it as:

```text
What are examples of supervised learning?
```

### Stored fields

For each answer request, keep:

- original question
- resolved question
- previous relevant question
- previous relevant answer
- detected topic
- session ID
- confidence of resolution

### Failure behavior

If reference is ambiguous:

- do not invent
- ask for clarification, or
- provide a cautious interpretation

### Performance rule

Do not send the full interview transcript on every follow-up. Use:

- recent turns
- retrieved relevant messages
- compact session summary
- AI Notes where appropriate

---

## 11. Subscription Responsibility Map

```text
Website UI
    â†’ shows plans, checkout, usage, billing state

Payment Provider
    â†’ collects payment and manages provider-side subscription

FastAPI Backend
    â†’ creates checkout, verifies webhook, updates subscription,
      enforces feature access and usage limits

Supabase
    â†’ stores users, plans, subscriptions, usage, and payment references

Resend
    â†’ sends verification, payment, renewal, cancellation,
      and consent-based marketing email

Desktop App
    â†’ displays plan/access state and requests backend authorization
```

The desktop app must never unlock paid features from a local frontend flag alone.

---

## 12. UI/UX Designer Boundary

The designer is responsible for:

- Figma screens
- user flows
- component variants
- responsive states
- loading/empty/error/success designs
- handoff notes
- design tokens
- prototype interactions

The designer is not responsible for:

- Supabase configuration
- database schema
- backend routes
- FastAPI implementation
- RLS
- Resend integration
- resume extraction
- RAG
- session storage
- follow-up resolver
- AI Notes generation
- payment webhooks
- feature gates
- usage limits
- deployment
- desktop synchronization

---

## 13. Phase Update Template

After each implementation phase, append or update:

```markdown
## Phase Update â€” Cx

**Status:** [x] Done  
**Date:** YYYY-MM-DD

### Files changed
- ...

### Database migrations
- ...

### API routes added/changed
- ...

### Functional validation
- ...

### Automated tests
- ...

### Manual tests
- ...

### Security/privacy validation
- ...

### Known limitations
- ...

### Deferred items
- ...

### Next phase
- Cy
```

---

## 14. Codex Prompt Rules

Before giving Codex a phase prompt:

1. Tell it the exact active phase.
2. Tell it to inspect the existing implementation.
3. Tell it not to rewrite unrelated systems.
4. List protected files/features.
5. Require the smallest safe change.
6. Require tests.
7. Require compile/build checks.
8. Require a files-changed report.
9. Require roadmap update.
10. Do not mix two large phases in one prompt.

Recommended wording:

```text
Work only on Phase Cx.
Do not begin Cy.
Make the smallest safe implementation.
Preserve existing desktop flows.
Report files changed, tests run, and remaining blockers.
```

---

## 15. Open Decisions Register

These decisions are intentionally not locked yet.

### Payment provider

- Razorpay
- Stripe
- provider abstraction supporting both

Decision required before C12.

### Website implementation stack

Follow the Production Tech Stack and final Figma handoff. Do not migrate the desktop frontend because of the website.

Decision must be confirmed before full C14 work.

### Vector implementation

Prefer Supabase-compatible vector storage unless testing shows a clear issue.

Decision finalized during C3.

### Desktop login method

- embedded login
- browser/deep-link
- device-code style

Decision finalized during C5.

### Export formats

- TXT/Markdown first
- PDF/DOCX later if required

Decision finalized during C7/C15.

### Data retention

Exact retention periods require product/privacy decision before C15 completion.

### Admin role set

Owner, super_admin, support_admin, billing_admin, privacy_admin, security_auditor, and readonly_admin are the planned starting roles. Final permissions require C15.5 threat modeling.

### Raw sensitive-data access policy

Decide which raw resume/transcript fields can ever be viewed by staff, and which must stay inaccessible even through break-glass.

### Break-glass approval policy

Decide which roles can approve high-risk sensitive-data access and how long approvals remain valid.

### Admin invite ownership policy

Decide first-owner bootstrap, owner-only role grants, invite expiry, and last-owner recovery rules.

### Support/admin retention and audit-log retention policy

Decide how long admin audit logs, support notes, invite records, and break-glass records are retained.

### C15.5 conditional release gate

Decide whether internal admin/support operations are required for the target release. If not required, record C15.5 as deferred/not required for that release before C16 final acceptance.

---

## 16. Major Risks and Mitigations

### Risk: desktop instability delays cloud work

Mitigation: C0 feature freeze and exit gate.

### Risk: cross-user data leakage

Mitigation: RLS, ownership checks, automated user-isolation tests.

### Risk: duplicate transcript/session events

Mitigation: client event IDs and idempotency.

### Risk: provider rate limits

Mitigation: prompt compaction, cooldown, retry-after handling, plan usage limits.

### Risk: long transcript cost

Mitigation: retrieval, summaries, bounded context, AI Notes reuse.

### Risk: payment state mismatch

Mitigation: webhook is authoritative, idempotent event processing.

### Risk: UI and backend drift

Mitigation: API contracts, shared types where practical, C14 integration audit.

### Risk: premature commercialization slows core product

Mitigation: pricing foundation only after session intelligence works.

### Risk: sensitive-data over-retention

Mitigation: privacy inventory, deletion flow, no raw audio/screenshots by default.

### Risk: admin privilege escalation

Mitigation: backend-only admin membership checks, role permissions, no frontend-only admin authority, and last-owner protection.

### Risk: unaudited staff access

Mitigation: audit every sensitive admin action, require reasons for destructive actions, and make audit logs append-only from application behavior.

### Risk: support/admin data overexposure

Mitigation: metadata-first support views, break-glass for raw sensitive data, and least-privilege admin roles.

### Risk: last-owner lockout

Mitigation: explicit last-owner removal prevention and documented first-owner/recovery process.

### Risk: break-glass misuse

Mitigation: reason-required, approval-gated, time-limited break-glass access with audit logging for every request, approval, and use.

---

## 17. Final Product Acceptance

The C0â€“C16 track is complete when:

- desktop app is stable
- account creation and login work
- resume upload and cloud profile work
- resume grounding is user-isolated
- job context syncs
- desktop app uses cloud identity/context
- interview sessions are saved
- transcript is viewable and downloadable
- AI Notes are generated and stored
- Ask AI supports follow-up context
- Resend emails work
- plans and subscriptions are stored
- payment webhooks work
- usage limits are backend-enforced
- approved Figma website is integrated
- users can export/delete data
- admin/support console exists with audited RBAC if required for internal operations before release; otherwise C15.5 is explicitly recorded as deferred/not required for that release
- staging and production QA pass
- known limitations are documented
- no major rewrite is required for release

---

## 18. Current Next Action

```text
C0 remains complete. C0.9 is not fully complete: C0.9.6 has implementation present with Chrome/Edge real-page validation pending, and C0.9.7 through C0.9.13 are deferred by explicit product-priority decision.
C1 Supabase Cloud Foundation is complete after C1.5 closure validation. C2 auth surface closure is complete through C2.5. C3.1 planning, C3.2 backend cloud resume API, C3.3 frontend authenticated upload/review UI, C3.4 cloud resume indexing/RAG activation, C3.4.5 GPT-based resume extraction provider, and C3.5 delete/rebuild/status closure are complete through implementation. C4 - Job Target / JD Cloud Sync is in progress with C4.1 audit/design complete and C4.2 authenticated backend plus required migration implemented locally with tests passing and live Supabase smoke validation passed on saiia-dev. C4.3 main website job-target UI is cancelled/re-scoped; job target selection moves to desktop startup/session setup after desktop authenticated cloud identity exists. No C4 generation integration, C5 desktop login/cloud sync, session history, billing, usage, email-provider integration, payment, admin console, or final website UI work has started.
C5.1 desktop authenticated cloud identity audit/design is documented in `docs/C5_DESKTOP_AUTH_CLOUD_IDENTITY_PLAN.md`. C5.2 desktop authenticated cloud identity is implemented locally with Electron main-process auth/session handling and focused tests. C5.3 desktop auth status/login/logout UI wiring is implemented locally using existing safe preload APIs. C5.4 desktop cloud startup context plumbing is implemented locally using existing authenticated backend summary routes and safe preload APIs. C6.2A Startup Login Screen is implemented locally with a dev/local memory-only desktop handoff store; production shared atomic TTL-backed handoff storage is deferred to C16.1 Production Auth Hardening and blocks public production release. Broader desktop startup/session setup UI, cloud sync engine, local/cloud data migration, C4.4 generation integration, session history, billing, usage, email-provider integration, payment, admin console, and final website UI work have not started.
```

The completed C0.9.2 manual validation covered:

- click Analyze Screen and confirm only the OCR/Extension menu opens
- Escape and outside click close the menu without changing the saved result
- Extension selection shows the controlled unavailable state without OCR or generation
- OCR selection starts the existing screen-capture flow exactly once
- multi-question MCQ screenshots answer all fully visible complete questions in screen order
- incomplete visible question blocks are ignored
- incorrect checked/highlighted MCQ options are ignored
- coding screenshots solve one dominant complete coding problem
- Stop during OCR preserves the previous valid screen result
- Ctrl+Shift+Enter opens the same source menu
- Answer, Analyze Screen, and Chat state remain isolated

### C0 Answer Intelligence Stabilization - Problem 1

Status: implemented with automated validation, desktop-core scope only. Not marked fully resolved until manual desktop flows pass.

### C0.9.2 One-Click OCR Stabilization - 2026-07-24

Implemented the locked one-click OCR path for Analyze Screen:

- OCR now captures one active-window screenshot and sends one direct screen-model request.
- The active OCR path no longer uses multi-screenshot sequence capture, crop/full-image double calls, OCR text merging, HackerRank enrichment, editable preview, or Generate-from-preview actions.
- The configured screen-capable model returns the final answer directly from the screenshot.
- Failures preserve the previous valid answer and show a controlled unreadable-question message with explicit retry/extension actions.
- Successful OCR creates one Analyze Screen history entry; failed/cancelled OCR creates no successful history entry.
- Provider-facing status text is provider-neutral in the frontend.
- Stabilization patch: direct-screen prompting now ignores selected/highlighted MCQ UI state, answers all fully visible independent quiz/MCQ/general questions in top-to-bottom order from one screenshot and one screen-model request, ignores incomplete visible question blocks, preserves coding pages as one dominant complete coding problem, and reports safe timing/count metadata for capture, image preparation, upload, screen-model time, response parse, overlay render, questions answered, incomplete questions ignored, model request count, fallback count, and correction count.
- UI stabilization patch: Analyze Screen result controls are contextual. Non-code results show only Analyze Screen and Extension. Copy Code appears only when valid formatted code exists. Copy Answer, Clear Result, Analyze Again, and Try OCR Again were removed from the Analyze Screen result action row. Answer and Chat controls remain unchanged.

Automated validation:

- `python -m compileall -q backend/app` passed.
- `PYTHONPATH=backend pytest -q backend/tests` passed: 281 tests.
- `node --test frontend/src/*.test.js` passed: 43 tests.
- `npm run build` passed.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.

Manual Electron validation is complete for live screenshot count, screen-model request count, time to answer, Stop cancellation, multi-question MCQ order/count behavior, incomplete-question ignoring, MCQ selection-marker independence, coding-page dominance, unreadable-screenshot behavior, contextual result controls, and overlay resize/status behavior.
C0.9.3 is complete.

Added deterministic answer planning before generation so SAIIA can distinguish pure technical, resume/project, role-fit, behavioral, personal, coding/debugging/output, MCQ, screen, system-design, and general answers. The planner now controls whether profile context, resume RAG, job context, and general knowledge are required, allowed, or forbidden.

Current implementation keeps the existing `/generate/` contract and Groq provider path, adds optional metadata, and avoids Problem 2 work such as answer variation, previous-answer similarity, or random wording changes.

Validation results:

- backend compile checks passed
- focused answer-planner/generation tests passed: `49 passed`
- full backend tests: `163 passed`, `1 failed` in pre-existing `test_coding_quality_gate.py::test_runner_and_import_only_editor_does_not_force_stub_mode`
- frontend build passed
- manual desktop flow smoke checks still pending

---

### C0 GPT-5.4 Mini Answer Intelligence Stabilization

Status: implemented with mocked provider validation, desktop-core scope only. Not signed off until live OpenAI and manual desktop flows pass.

This pass changes final answer intelligence only. It does not modify screen vision, STT, OCR, Electron capture, overlay design, Supabase, authentication, billing, deployment, or Problem 2 repeated-answer variation.

Implemented:

- Added backend-only OpenAI answer configuration using one model variable: `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`.
- Added an official OpenAI SDK Responses API provider for primary answer generation.
- Routed primary answer generation, conditional semantic validation, and conditional targeted correction through the same fixed OpenAI snapshot.
- Kept Groq as emergency/rollback fallback with `ANSWER_FALLBACK_PROVIDER=groq`.
- Disabled unconditional Llama Versatile refinement by default with `ENABLE_ALWAYS_ON_REFINEMENT=false` and `REFINEMENT_ENABLED=false`.
- Preserved the existing `/generate/` request/response contract and added optional safe metadata for reasoning effort, validation timing, correction timing, and fallback reason.
- Reused the existing immutable `AnswerPlan` and context-policy gating.

Validation results:

- `python -m compileall -q backend/app` passed.
- Focused OpenAI provider/pipeline tests passed: `5 passed`.
- Focused answer-planner/generation tests passed: `58 passed`.
- Full backend tests: `172 passed`, `1 failed` in pre-existing `test_coding_quality_gate.py::test_runner_and_import_only_editor_does_not_force_stub_mode`.
- `npm run build` passed in `frontend/`.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.

Rollback:

- Set `ANSWER_PROVIDER=groq` to switch primary answer generation back to Groq.
- Set `ANSWER_PROVIDER=openai` and `OPENAI_MODEL=gpt-5.4-mini-2026-03-17` to restore OpenAI primary.
- Set `ENABLE_SEMANTIC_VALIDATION=false` to disable semantic validation.
- Set `ENABLE_CONDITIONAL_CORRECTION=false` to disable targeted correction.
- Set `ENABLE_ANSWER_PROVIDER_FALLBACK=false` to disable Groq fallback.
- Keep `REFINEMENT_ENABLED=false` to avoid optional legacy refinement jobs.

Known limitations:

- `OPENAI_API_KEY` remains a placeholder and must be supplied locally for live OpenAI testing.
- Manual microphone, system-audio, screen-generate, overlay reveal, and live fallback smoke tests are still pending.
- Problem 2 remains deferred.

---

### C0 GPT-5.4 Mini Closure Pass - 2026-07-16

Status: backend/provider gates closed; desktop manual gates remain pending.

Scope:

- Final answer intelligence only.
- No STT, OCR, screen-vision, Electron window, Supabase, authentication, billing, deployment, or Problem 2 work.
- No new provider or framework was added beyond the official OpenAI SDK integration already used for this phase.

Provider and pipeline:

- Previous primary provider/model: Groq answer generation.
- Previous refinement provider/model: legacy Groq Llama Versatile refinement where enabled.
- New primary provider/model: OpenAI Responses API with `gpt-5.4-mini-2026-03-17`.
- Public model configuration remains one variable: `OPENAI_MODEL`.
- The same snapshot is used for primary generation, conditional semantic validation, and conditional targeted correction.
- Successful OpenAI generation does not call Groq or Llama Versatile.
- Groq fallback remains available through `ANSWER_FALLBACK_PROVIDER=groq`.
- Unconditional refinement remains disabled through `REFINEMENT_ENABLED=false` and `ENABLE_ALWAYS_ON_REFINEMENT=false`.

Closure fixes:

- Corrected runner-only coding quality gate behavior.
- Preserved OpenAI timing metadata in `/generate/` responses.
- Normalized no-correction status to `not_needed`.
- Added deterministic technical completeness checks for shallow RAG/process answers.
- Added deterministic comparison checks for misleading false-superiority answers.
- Revalidated corrected technical answers with Real-life example and completeness rules.
- Cleared deterministic warning metadata after a valid semantic validation result.

Validation:

- Backend compile: passed.
- Full backend tests: `177 passed`, `5 warnings`.
- Focused OpenAI/provider/planner/context/prompt/validation/correction/fallback/API compatibility tests: `107 passed`, `5 warnings`.
- OpenAI plus coding closure tests: `54 passed`.
- Frontend build: passed.
- Electron syntax checks: passed for `main.cjs` and `preload.cjs`.
- Standalone frontend formatting/request-state checks: passed.
- Secret scan of public docs/code placeholders: no API key pattern found.

Live provider validation:

- Local runtime confirmed `ANSWER_PROVIDER=openai`.
- Local runtime confirmed `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`.
- Local runtime confirmed no separate GPT answer/validator/correction model variables.
- Live OpenAI smoke returned safe metadata with provider/model, reasoning effort, timings, validation status, and fallback status.
- Forced OpenAI failure used Groq fallback when enabled.
- Forced OpenAI failure returned a controlled provider error when fallback was disabled.

Pending manual desktop validation:

- Manual microphone flow.
- Microphone Auto Mode.
- Manual system-audio flow.
- System-audio Auto Mode.
- Analyze Screen to generate flow.
- Overlay progressive reveal.
- Show Full Answer.
- Ctrl+H.
- Current overlay resize behavior.
- Desktop proof that optional correction failure preserves the visible primary answer.

Rollback:

- Groq primary: `ANSWER_PROVIDER=groq`.
- OpenAI primary: `ANSWER_PROVIDER=openai` and `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`.
- Disable semantic validation: `ENABLE_SEMANTIC_VALIDATION=false`.
- Disable correction: `ENABLE_CONDITIONAL_CORRECTION=false`.
- Disable fallback: `ENABLE_ANSWER_PROVIDER_FALLBACK=false`.
- Disable legacy refinement jobs: `REFINEMENT_ENABLED=false`.

Problem 2 repeated-answer variation remains deferred.

---

### C0 Answer Generation Problem 2 - Controlled Repeated-Answer Variation

Status: implemented with automated backend validation and live OpenAI smoke validation; manual Electron overlay validation remains pending.

Date: 2026-07-16

Scope:

- Final answer generation only.
- No Supabase, cloud history, account memory, embeddings, external similarity API, new provider, frontend redesign, STT, OCR, screen-vision, or Electron-window work.
- Problem 1 GPT-5.4 mini answer intelligence remains the baseline.

Implementation:

- Added local repetition normalization for capitalization, punctuation, whitespace, and common prompt prefixes such as `Explain` and `Can you explain`.
- Added near-duplicate detection using local token overlap and `difflib.SequenceMatcher`.
- Added an in-memory bounded temporary answer history with TTL.
- Added hashed context fingerprinting so profile/job/resume-context changes do not reuse unrelated answer history.
- Added answer-type-specific variation profiles and locked dimensions.
- Added compact repeated-question prompt instructions only after repetition is detected.
- Added local similarity checking after the normal Problem 1 validation/correction pipeline.
- Added one optional OpenAI targeted variation rewrite only when a repeated prose answer remains too similar.
- Added revalidation for rewritten answers before accepting them.
- Preserved coding, MCQ, debugging, and output-prediction correctness over novelty.

Configuration:

- `ENABLE_CONTROLLED_ANSWER_VARIATION=true`
- `VARIATION_HISTORY_LIMIT=3`
- `VARIATION_CACHE_TTL_SECONDS=7200`
- `ENABLE_VARIATION_REWRITE=true`
- Rollback: `ENABLE_CONTROLLED_ANSWER_VARIATION=false`.

Provider behavior:

- `OPENAI_MODEL` remains `gpt-5.4-mini-2026-03-17`.
- No second GPT model was configured.
- Successful OpenAI generation does not call Groq or Llama for variation.
- Variation rewrite, when needed, uses the same OpenAI snapshot.
- Unconditional Llama Versatile refinement remains disabled.

API compatibility:

- Existing response fields remain intact.
- Optional safe metadata was added for repetition and variation status.
- Previous answers, normalized questions, raw fingerprints, full prompts, resume chunks, and provider payloads are not exposed.

Validation:

- Backend compile passed.
- Focused Problem 2/OpenAI tests: `20 passed`, `5 warnings`.
- Focused regression suite: `118 passed`, `5 warnings`.
- Full backend tests: `188 passed`, `5 warnings`.
- Frontend build passed.
- Electron syntax checks passed.
- Public docs/code placeholder secret scan pending final closeout.

Live smoke:

- Repeated prose answers were validated with the real configured OpenAI provider for technical, comparison, RAG, HR, role-fit, personal, behavioral, resume/project, and FastAPI-experience prompts.
- Coding, MCQ, and output-prediction repeated-answer exceptions were validated with screen-style question routing.
- Typical live latency was about 1.7s to 4.8s for most repeated prose cases.
- Slowest observed validation case was about 8.0s when a direct coding smoke triggered extra validation/correction work.
- Live repeated cases did not need rewrite because the primary repeated outputs were already below similarity thresholds.
- Mocked tests cover the exact-duplicate path that triggers one rewrite and the failure paths that preserve the primary answer.

Known limitations:

- History is process-local and resets on backend restart.
- No cloud/session-level cross-device memory is implemented.
- The local near-duplicate heuristic is conservative by design.
- Manual overlay regression for reveal, Show Full Answer, Ctrl+H, resize, and stale-response handling still needs a desktop pass.

---

### Analyze Screen Persistent Result and Explicit Reanalysis - 2026-07-17

Change:

- Analyze Screen tab selection now behaves as navigation, not repeated execution.
- Initial empty Analyze Screen selection may start the first analysis.
- Returning from Answer or Chat to Analyze Screen restores the saved extracted question and answer.
- New captures are started only through the internal Analyze Again or Retry Analysis actions.
- Clear Result clears only Analyze Screen state.
- A failed reanalysis no longer destroys a previous valid screen result.

Validation:

- Focused frontend tests: `15 passed`.
- `npm run build`: passed.
- `node --check frontend/electron/main.cjs`: passed.
- `node --check frontend/electron/preload.cjs`: passed.

Rollback:

- Revert the frontend files changed in this section to restore the previous toolbar-executes-analysis behavior.

No backend provider, screen vision, OCR, GPT model, prompt, Problem 1, or Problem 2 changes were introduced.

---

### Analyze Screen OpenAI Nano Vision Migration - 2026-07-17

Change:

- Analyze Screen vision extraction now defaults to the backend OpenAI Responses API path.
- Primary screen vision model is `gpt-5-nano-2025-08-07`.
- Configured screen fallback model is `gpt-5.4-nano-2026-03-17`.
- RapidOCR remains available as local OCR prepass and final fallback.
- The final answer-generation model remains unchanged: `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`.

Compatibility:

- Existing Electron active-window capture is preserved.
- Existing Analyze Screen persistent-result and Analyze Again behavior is preserved.
- Existing `/api/screen/analyze-active-window` response fields are preserved.
- Provider-neutral metadata was added for OpenAI fallback model, local OCR usage, selected vision detail, and primary/fallback timings.
- Legacy `groq_vision_*` diagnostics remain for compatibility but are not used to describe OpenAI calls.

Rollback:

- `SCREEN_VISION_PROVIDER=openrouter` restores the previous OpenRouter-compatible route.
- `SCREEN_VISION_PROVIDER=groq` restores the Groq-compatible route.
- `ENABLE_SCREEN_VISION_FALLBACK=false` disables the GPT-5.4 nano fallback pass.
- `ENABLE_LOCAL_OCR_PREPASS=false` disables local OCR supporting evidence.
- `ENABLE_RAPIDOCR_FALLBACK=false` disables final OCR fallback.

Validation:

- Backend compile passed.
- Focused screen-vision tests passed: `29 passed`, `5 warnings`.
- Full backend tests passed: `196 passed`, `5 warnings`.
- Frontend build passed.
- Electron syntax checks passed.

Known limitations:

- Live screenshot scenarios are pending final desktop pass.
- Live provider validation requires a backend-only `OPENAI_API_KEY`.

---

### In-Session Question and Answer History Navigation - 2026-07-18

Change:

- Floating Answer panel now keeps separate current-session histories for Answer and Analyze Screen results.
- Header navigation displays the active position as `current / total` with Previous and Next controls.
- Selecting a previous or next entry restores saved state only; it does not restart microphone transcription, screen capture, OCR, classification, answer generation, validation, correction, or variation.
- Analyze Screen history is isolated from Answer mode, and Chat remains a separate conversation surface.
- History uses existing Electron overlay state synchronization and remains in memory only.

Validation:

- Focused frontend tests passed: `13 passed`.
- `npm run build`: passed.
- Electron syntax checks passed for `frontend/electron/main.cjs` and `frontend/electron/preload.cjs`.

Rollback:

- Revert the history helper, Answer panel header controls, and `App.jsx` history wiring to return to the previous single-current-answer display.

---

### C0 - Live Follow-Up Question Resolution - 2026-07-18

Scope:

- Current-session memory only.
- Same-mode recent-turn context only.
- Original and resolved question tracking.
- Deterministic resolution before Answer Planner execution.
- Clarification for ambiguous or context-free references.
- No cloud persistence.

This C0 feature is a live-interview prerequisite only. It does not implement the persistent C9 Ask AI system.

C9 remains responsible for:

- saved sessions
- stored threads
- `ask_ai_messages`
- transcript retrieval
- AI Notes
- persistence after restart
- cross-device access
- cloud ownership

Rollback:

- Set `ENABLE_LIVE_FOLLOWUP_RESOLUTION=false` to pass the original question directly into the existing planner and generation pipeline.

Validation:

- Focused resolver and streaming tests passed: `14 passed`, `5 warnings`.
- Frontend history test passed: `8 passed`.

---

### C0 - Question Detection, Coding Answer Contract, and Toolbar Stop - 2026-07-18

Scope:

- Accept common definition/explanation question openings from live transcripts.
- Route explicit coding implementation requests into the existing coding Answer Plan.
- Strengthen the existing coding prompt format without changing GPT model/provider routing.
- Add a red circular Stop control between Chat and the timer using the existing toolbar action IPC.

Implementation notes:

- Definition detection is punctuation-independent and tolerates conservative leading filler such as `uh` or `okay`.
- Empty definition commands remain rejected so filler/noise does not trigger generation.
- Coding output now requests `### Approach`, `### Code`, `### Time Complexity`, and `### Space Complexity`.
- Lightweight code coloring was added in the existing screen answer code block renderer without a new dependency.
- Stop cancels active generation/audio state without clearing the current answer or transcript.

Validation:

- Backend compile passed.
- Focused backend tests passed: `26 passed`, `5 warnings`.
- Full backend tests passed: `235 passed`, `5 warnings`.
- Frontend tests passed: `26 passed`.
- Frontend build passed.
- Electron syntax checks passed.

Known limitations:

- Existing Python code validation remains Python-only; non-Python coding requests skip that Python-specific validator.
- Live desktop validation for the new Stop button remains pending.

---

### C0 - Follow-Up Intent Compiler and Structured Coding Continuations - 2026-07-19

SAIIA now resolves live follow-ups beyond topic substitution. A question like `Can you write a program of it?` after `What is an array?` keeps the original wording visible, but internally compiles to an explicit coding task for the referenced concept before Answer Planner execution.

What changed:

- Added a backend deterministic follow-up intent compiler.
- Preserved same-mode bounded context and existing request ownership.
- Added safe compiler metadata for requested action, output type, resolved language, platform mode, topic, confidence, and timing.
- Added structured coding-answer payload support for approach, language, code, time complexity, and space complexity.
- Reused the existing final answer model, provider fallback, streaming path, Problem 1 validation, Problem 2 variation, and frontend overlay design.

Validation:

- Focused backend tests: `26 passed`, `5 warnings`.
- Full backend tests: `243 passed`, `5 warnings`.
- Frontend tests: `28 passed`.
- Backend compile: passed.
- Frontend build: passed.
- Electron syntax checks: passed.

Known limitations:

- Manual desktop validation remains pending for the exact array follow-up scenario.
- Non-Python display is supported, but no new non-Python judge or sample runner was added.

---

### C0 - Streaming Internal Metadata Sanitization - 2026-07-22

SAIIA separates internal metadata from answer text during live streaming.
Category classification stays in structured metadata/status state, while
provider deltas are filtered by a per-request chunk-safe sanitizer before
emission.

Implementation contract:

- Do not encode category, type, mode, intent, or answer_type inside generated
  answer bodies.
- Preserve live backend-to-frontend streaming and existing JSON event protocol.
- Sanitize split control markers without buffering the full answer.
- Preserve normal bracket syntax, code indexing, nested arrays, and unknown
  markers.
- Store clean history answers with category as a separate field.
- Keep stale/cancelled request protections scoped by request ID and mode.

Validation and rollback:

- Regression coverage includes backend sanitizer chunks, stream metadata,
  history serialization, frontend metadata separation, cancellation, and stale
  request behavior.
- Rollback by reverting the sanitizer module, stream route wiring, prompt
  marker-contract removal, frontend fallback stripping, and doc note.

---

## 19. Final Rule

When future instructions conflict or become unclear, return to this sequence:

```text
Stabilize the desktop
â†’ establish secure cloud identity
â†’ migrate profile and job context
â†’ connect desktop and website
â†’ store sessions and transcripts
â†’ generate notes
â†’ add contextual Ask AI
â†’ add email
â†’ add plans and payments
â†’ enforce usage
â†’ complete UI integration
â†’ harden privacy
â†’ test and release
```

Do not skip foundational phases to build visible features faster.
