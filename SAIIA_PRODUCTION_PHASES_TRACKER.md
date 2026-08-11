# SAIIA Production Phases Tracker

**Product:** SAIIA â€” Smart AI Interview Assistant  
**Document Type:** Production phase checklist for developer + Codex  
**Version:** 1.1  
**Last updated:** 2026-08-09
**Purpose:** Track SAIIA after MVP and guide development toward a polished production-ready application.

---

## 0. Source of Truth

Production work must follow these documents:

- `SAIIA_PRODUCTION_PRD_CORE.md`
- `SAIIA_PRODUCTION_TECHSTACK.md`
- `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`

If this tracker and those documents ever conflict, the PRD Core, Production Tech Stack, Screen Intelligence Architecture, and Cloud Product Implementation Roadmap win according to their responsibilities. This tracker preserves historical desktop work and should not become a competing C0.9 execution plan.

### Tracker Update Rule

After each completed production phase:

- update the phase status in this file
- mark completed checklist items
- note blockers or deferrals clearly
- record the validation run for that phase

This tracker is the live execution log for the production build.


## Current Execution Alignment

Current active execution phase:

```text
C5.4 - Desktop cloud startup context plumbing implemented locally; desktop startup/session setup UI, C4.4 generation integration, cloud sync engine, and local/cloud data migration are not started
```

Screen Intelligence documentation:

```text
[x] C0.9.1 - Documentation and architecture lock complete
```

C0 status:

```text
[x] Done
```

C0.9 overall status:

```text
[~] Deferred by product-priority decision - C0.9.1, C0.9.2, C0.9.3, C0.9.4, and C0.9.5 complete; C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, controlled unsupported-content results, and Chrome/Edge real-page validation pending; C0.9.7 through C0.9.13 remain deferred after C2 auth surface closure
```

C1 current status:

```text
[x] Foundation complete - C1.1 complete; C1.2 base Supabase database schema migration complete and applied to live saiia-dev; C1.3 RLS/storage bucket migration complete and applied to live saiia-dev; C1.4 FastAPI auth-token verification dependency complete; C1.5 closure audit complete; live Supabase user-token smoke test passed; C2.1/C2.2/C2.3 complete and live revalidated; C2.4 complete; C2.5 auth surface closure complete
```

C2 current status:

```text
[x] Complete - C2.1 auth architecture audit, account-flow plan, and safe implementation boundary complete; C2.2 minimal Supabase auth UI and backend current-user endpoint complete; C2.3 authenticated profile bootstrap implemented in the existing React/Vite app and FastAPI backend and live revalidated after `20260801115446_grant_cloud_table_privileges.sql` fixed the PostgREST privilege blocker; C2.4 protected auth shell and account/session state handling complete; C2.5 Auth Surface Closure complete; no C3 cloud profile saving, cloud resume upload, C5 desktop login/cloud sync, sessions, billing, usage, email-provider integration, payment, admin console, or final website UI started
```

C3 current status:

```text
[x] Complete - C3.1 Cloud Resume/Profile Storage Planning + Audit complete; C3.2 Backend Cloud Resume API merged and live smoke-tested; C3.3 frontend authenticated upload/review UI implemented under `/auth/resume`; C3.4 cloud RAG/index activation implemented through backend chunk generation and ready-resume activation; C3.4.5 GPT-based resume extraction provider implemented; C3.5 delete/rebuild/status closure implemented; C4.1 audit/design complete after explicit approval; C4.2 backend plus migration implemented locally and live Supabase smoke validation passed on saiia-dev; C4.3 main website job-target UI cancelled/re-scoped; no C4 generation integration, C5, sessions, billing, payment, email provider, admin console, or final website UI started
```

C4 current status:

```text
[~] In progress - C4.1 Cloud Job Context Audit, Architecture, and Implementation Plan complete in `docs/C4_CLOUD_JOB_CONTEXT_PLAN.md`; C4.2 authenticated cloud Job Context backend plus required migration implemented locally with backend/migration tests passing and live Supabase smoke validation passed on saiia-dev; C4.3 main website `/job-contexts` UI cancelled/re-scoped by product decision; job target selection belongs in desktop startup/session setup with active resume, active job target/JD, answer model, audio source, and answer preferences after desktop cloud identity exists; no generation integration or C5 desktop sync has been implemented
```

C4.2 live validation record:

- Result: passed against linked Supabase project `saiia-dev` / `rbmxfazjbldmkomdpyzl` on 2026-08-09.
- Command/tests run: see the tracked sanitized artifact [docs/validation/C4_2_LIVE_SUPABASE_SMOKE_2026-08-09.md](docs/validation/C4_2_LIVE_SUPABASE_SMOKE_2026-08-09.md), which records the PowerShell inline Python smoke method, repository-root execution context, and assertion outcomes without secrets or private data.
- Smoke covered: migration columns, `is_active` database default false, idempotency table existence/RLS, service-role-only activation/create RPC exposure, blocked authenticated direct `INSERT`/`UPDATE`/`DELETE`, authenticated FastAPI create/list/detail/patch/activate/delete/no-context lifecycle, cross-user blocking, extraction consent rejection, and dual-source extraction rejection.
- Scope exclusions remain: no C4 generation integration and no C5 desktop sync.

C4.3 product decision record:

- Result: main website `/job-contexts` UI is cancelled/re-scoped and should not be committed as product UI.
- Replacement direction: job target/JD selection moves into the desktop app startup/session setup flow where the user chooses active resume, active job target/JD, answer model, audio source, and answer preferences before starting an interview session.
- Dependency: this belongs during or after C5, once desktop authenticated cloud identity is available, because the desktop app needs that identity before it can load cloud resumes and job contexts.
- Scope exclusions remain: no new desktop implementation, no C4.4 generation integration, no C5 desktop login/cloud sync, no backend runtime changes, and no migration changes.

C5.1 current status:

```text
[x] Audit/design complete - Desktop authenticated cloud identity audit/design is documented in `docs/C5_DESKTOP_AUTH_CLOUD_IDENTITY_PLAN.md`; at C5.1 time no desktop auth runtime existed, and later C5.2/C5.3/C5.4 implementation status is tracked below; startup/session setup UI, cloud sync engine, and C4.4 generation integration remain not implemented
```

C5.2 current status:

```text
[~] Implemented locally - Electron main-process desktop auth session manager, Supabase Auth PKCE `saiia://auth/callback` flow, safeStorage-backed encrypted session persistence, narrow auth/cloud IPC, backend `/api/auth/me` verification, mandatory profile bootstrap, logout cleanup, user-switch cache clearing, session generation, stale response protection, and focused tests are implemented locally; no desktop startup/session setup UI, C4.4 generation integration, cloud sync engine, backend route changes, migrations, billing/account UI, or local/cloud data migration has been started
```

C5.3 current status:

```text
[~] Implemented locally - Desktop auth status/login/logout UI wiring is implemented in the Electron renderer using only existing safe `window.saiia` preload APIs; Login, Logout, Refresh status, safe connected identity display, token-expired/offline/backend-unavailable/bootstrap-failed guidance, and focused renderer/helper tests are present; no desktop startup/session setup UI, resume/job-target selection UI, C4.4 generation integration, cloud sync engine, backend route changes, migrations, billing/account UI, or local/cloud data migration has been started
```

C5.4 current status:

```text
[~] Implemented locally - Desktop cloud startup context plumbing is implemented through the existing Electron main-process auth/session manager and safe preload APIs; startup context now exposes safe auth/cloud summary state, profile/bootstrap readiness, active cloud resume readiness from `/api/resumes/current`, active cloud job-target readiness from preview-only `/api/job-contexts?limit=50`, local-only/offline fallback, and stale response protection tests; no desktop startup/session setup UI, resume/job-target selection UI, C4.4 generation integration, cloud sync engine, backend route changes, migrations, billing/account UI, or local/cloud data migration has been started
```

C15.5 future admin/support status:

```text
[-] Future / not started - Internal admin, support, and audit console is intentionally planned for C15.5 after C15 privacy/export/retention/deletion rules, not during C2, C3, or C5. Supabase Dashboard remains the temporary developer-only admin/debug tool until C15.5 is explicitly started.
```

Primary references:

- `SAIIA_PRODUCTION_PRD_CORE.md`
- `SAIIA_PRODUCTION_TECHSTACK.md`
- `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`

P6B, P8, and P9 records below are historical desktop work records. They are not the current execution authority and must not compete with the C0 -> C0.9 -> C1 roadmap order.
## 1. Why This File Exists

SAIIA MVP is complete and demo-ready.

The MVP proved this flow:

```text
Profile setup â†’ Recording â†’ Transcription â†’ Classification â†’ Groq answer generation â†’ Electron overlay display
```

This file tracks the next production phases so the project does not lose direction or fall into scope creep.

Use this file for:

- daily planning
- Codex prompts
- progress tracking
- deciding what to build next
- knowing what is done and what is deferred
- keeping SAIIA architecture future-ready

---

## 2. Status Legend

```text
[ ] Not started
[~] In progress
[x] Done
[!] Blocked / needs urgent attention
[-] Deferred / future
```

---

## 3. Core Product Rule

SAIIA must remain focused on this product promise:

```text
Understand the candidate â†’ understand the interview question â†’ generate a grounded answer â†’ show it quickly in a private overlay.
```

If a feature does not support this flow, it should not be prioritized.

---

## 4. Current Baseline

## V1.0 â€” Manual MVP

### Status

```text
[x] Complete and demo-ready
```

### Completed Capabilities

- [x] Profile setup
- [x] Required profile validation
- [x] Manual Start/Stop recording
- [x] Microphone audio capture
- [x] Audio upload to FastAPI backend
- [x] ffmpeg/Whisper transcription
- [x] WebM/WAV format handling
- [x] Fast rule-based classification
- [x] Groq answer generation
- [x] Ollama fallback support
- [x] Answer quality cleanup
- [x] Electron main window
- [x] Separate Electron overlay window
- [x] IPC state sync
- [x] Ctrl+H overlay hide/show
- [x] Show/Hide Overlay button
- [x] Overlay drag
- [x] Font-size control
- [x] Basic error handling
- [x] README
- [x] DEMO_SCRIPT.md
- [x] .gitignore hygiene
- [x] Phase tracker updated

### Known MVP Limitations

- [!] Manual Start/Stop flow only
- [!] Microphone-only audio capture
- [!] No resume upload/extraction yet
- [!] No resume RAG yet
- [!] No screen reading/OCR mode yet
- [!] No NVIDIA DeepSeek refinement yet
- [!] No auto-listen mode yet
- [!] No packaged installer yet
- [!] No auth/billing/licensing yet
- [!] No guaranteed invisibility during screen sharing

### Completion Criteria

```text
SAIIA MVP can be shown in a demo:
profile â†’ record â†’ transcribe â†’ classify â†’ Groq answer â†’ overlay.
```

---

# Production Roadmap Phases

---

# Phase P0 â€” Clean Baseline and Repository Safety

## Status

```text
[x] Done
```

## Goal

Create a safe, clean baseline before new production features are added.

## Why This Phase Matters

The MVP is working. Before adding resume upload, RAG, OCR, and multi-model routing, the project should be safe to push, review, and extend.

## Checklist

### Git and File Safety

- [x] Git initialized cleanly, if required.
- [x] `.gitignore` protects `.env`.
- [x] `.gitignore` protects audio files.
- [x] `.gitignore` protects logs.
- [x] `.gitignore` protects local profile data.
- [x] `.gitignore` protects build outputs.
- [x] `.gitignore` protects node_modules.
- [x] `.gitignore` protects virtual environments.
- [x] No real Groq key is committed.
- [x] No NVIDIA key is committed.
- [x] No resume files are committed.
- [x] No candidate profile JSON is committed.
- [x] No temporary audio files are committed.

### Documentation

- [x] README reflects current MVP.
- [x] DEMO_SCRIPT.md is accurate.
- [x] Production PRD Core file exists.
- [x] Production TECHSTACK file exists.
- [x] Production phases tracker exists.

### Phase Notes

- Protected commercial work remains planned for later phases.
- The current production build uses `SAIIA_PRODUCTION_PRD_CORE.md` and `SAIIA_PRODUCTION_TECHSTACK.md` as the active planning documents.

### Validation

- [x] `npm run build` passes.
- [x] Backend starts cleanly.
- [x] Electron starts cleanly.
- [x] One full manual demo run passes.

### P0 Validation Notes

- `npm run build` passed in `frontend/`.
- Electron dev startup reached a healthy running state and registered `Ctrl+H`.
- Backend startup passed in the active Conda SAIIA environment and also started cleanly on an alternate local port for validation.
- A manual MVP demo question passed using the saved candidate profile plus a live Groq generation path for `Tell me about yourself.`
- Existing docs remain intentionally untracked in Git for now because docs tracking is deferred by user instruction.

## Codex Rules

- Do not add new features in this phase.
- Do not change working MVP logic unless required for cleanup.
- Do not commit secrets.
- Do not remove working files blindly.

## Completion Criteria

```text
Project is clean, safe, and ready for production-phase development.
```

---

# Phase P1 â€” Resume Upload and Profile Extraction

## Status

```text
[x] Done
```

## Goal

Allow users to upload a resume PDF/DOCX/TXT and automatically extract SAIIA profile fields.

## Priority

Very high. This should be the first major product feature after MVP.

## User Story

As a candidate, I want to upload my resume so SAIIA can understand my background, skills, and projects without me manually typing everything.

## Backend Checklist

- [x] Add resume upload endpoint.
- [x] Accept PDF files.
- [x] Accept DOCX files.
- [x] Accept TXT files.
- [x] Validate file type.
- [x] Validate file size.
- [x] Extract text from PDF.
- [x] Extract text from DOCX.
- [x] Extract text from TXT.
- [x] Detect empty/scanned PDF.
- [x] Return useful error for unsupported files.
- [x] Return useful error for unreadable files.
- [x] Add resume extraction service.
- [x] Use Groq to convert extracted text into structured profile JSON.
- [x] Extract resume/background.
- [x] Extract skills.
- [x] Extract experience/projects.
- [x] Extract education.
- [x] Extract work experience.
- [x] Extract achievements/certifications if present.
- [x] Do not log full resume text by default.
- [x] Do not save uploaded resume permanently unless intended.

## Frontend Checklist

- [x] Add resume upload UI in profile setup.
- [x] Show supported file types.
- [x] Show upload loading state.
- [x] Show extraction loading state.
- [x] Display extracted profile preview.
- [x] Let user edit extracted fields.
- [x] Save profile only after user confirms.
- [x] Preserve manual profile setup fallback.
- [x] Show errors for invalid/empty/scanned files.

## API Expectations

Possible routes:

```text
POST /api/resume/upload
POST /api/resume/extract
GET  /api/resume/status
DELETE /api/resume
```

## Acceptance Criteria

- [x] User uploads a text-based PDF resume.
- [x] SAIIA extracts profile fields.
- [x] User reviews/edits extracted fields.
- [x] User saves profile.
- [x] Generated answers use extracted resume details.
- [x] Manual profile setup still works.

### P1 Validation Notes

- `POST /api/resume/extract` passed for TXT, PDF, and DOCX sample resumes.
- Unsupported file upload returned the expected error for `unsupported.png`.
- Empty file upload returned the expected error for `empty.txt`.
- Low-text/scanned-like PDF returned the required readable-text error.
- Invalid/corrupt PDF returned the expected unreadable-file error.
- Oversized TXT upload returned the expected file-size error.
- Extracted resume fields were saved only after explicit profile confirmation.
- Saved extracted profile data was used successfully by the existing Groq answer generation flow.
- Manual profile save still worked after the extraction changes.
- The MVP flow still passed using `question.wav` -> transcribe -> classify -> Groq answer.

---

# Phase P2 â€” Resume RAG Grounding

## Goal

Use resume RAG so SAIIA answers are grounded in the candidate's real resume.

## Status

```text
[x] Done
```

## Scope Rule

RAG is only for interview profile grounding.

Do not turn SAIIA into Dhiti or a general document Q&A assistant.

## Backend Checklist

- [x] Add resume chunking service.
- [x] Add embedding generation.
- [x] Add local vector storage.
- [x] Store chunk metadata.
- [x] Add retrieval service.
- [x] Retrieve chunks based on interview question.
- [x] Retrieve chunks based on question category.
- [x] Pass retrieved chunks into answer generation.
- [x] Add retrieval latency logs.
- [x] Add fallback when retrieval fails.
- [x] Avoid logging full resume chunks in normal logs.
- [x] Add delete/rebuild resume index support.

## Frontend Checklist

- [x] Show resume index status.
- [x] Show "Resume indexed" indicator.
- [x] Add "Rebuild resume index."
- [x] Add "Remove resume data."
- [x] Show answer source as resume-grounded when applicable.

## Prompt Requirements

Answer generator should receive:

```text
question
category
profile summary
retrieved resume snippets
target role
company
skills
job description context if available
```

## Acceptance Criteria

- [x] Technical answer references real resume skills/projects.
- [x] Behavioral answer uses real experience when available.
- [x] Sparse resume data does not create fake stories.
- [x] RAG does not add major latency.
- [x] Answers remain short and speakable.

### P2 Validation Notes

- Resume index builds locally into ignored `tmp/` storage using chunked profile/resume sections.
- `POST /api/resume/index`, `GET /api/resume/index/status`, and `DELETE /api/resume/index` all passed.
- Retrieval worked for:
  - `Tell me about yourself.`
  - `Explain your experience with FastAPI.`
  - `Tell me about a difficult bug.`
- Retrieval fallback also passed when the resume index was removed: generation still worked using saved profile data only.
- Manual profile setup still worked and could also be indexed with the new resume-grounding flow.
- The existing MVP flow still passed:
  - profile -> transcribe -> classify -> Groq answer -> overlay path
- Retrieval timing and retrieved chunk count were added without breaking the existing generation response shape.

---

# Phase P3 â€” Job Description and Company Context

## Status

```text
[x] Done
```

## Goal

Tailor answers to the target job and company.

## Checklist

- [x] Add job description input.
- [x] Add optional job description upload.
- [x] Extract required skills.
- [x] Extract responsibilities.
- [x] Extract seniority level when inferable.
- [x] Extract domain keywords when inferable.
- [x] Match resume skills to job requirements through answer tailoring.
- [x] Save job target context locally.
- [x] Use job context in answer generation.
- [x] Let user update role/company/JD anytime.

## Acceptance Criteria

- [x] Answers are tailored to the target role.
- [x] Answers mention relevant profile skills.
- [x] Irrelevant resume details are avoided.
- [x] Job context can be updated without breaking profile.

### P3 Validation Notes

- `GET /api/job-context`, `POST /api/job-context`, and `DELETE /api/job-context` all passed using local `tmp/job_context.json` storage.
- Optional `POST /api/job-context/extract` passed with a TXT job description using the reused file extraction path.
- Generation fallback passed with no saved job context: answers still used profile plus resume-grounded retrieval.
- Generation with saved job context passed: answers became more role/company-targeted without inventing fake projects or skills.
- P1 resume extraction still passed for `resume.txt`.
- P2 resume indexing and retrieval still passed, including `Explain your experience with FastAPI.`
- The current MVP backend flow still passed using `question.wav` -> transcribe -> classify -> generate.
- `python -m py_compile` passed for all touched backend files.
- `npm run build` passed in `frontend/`.
- Clean Electron shell validation passed in a fresh session before P4:
  - stale SAIIA backend/Vite/Electron processes were stopped
  - backend restarted cleanly on `http://127.0.0.1:8000`
  - `npm run electron:dev` started without a Vite port conflict
  - Electron stayed up and `Ctrl+H` registered successfully
  - a full manual flow still passed while the clean Electron session was running: profile/job context -> transcribe -> classify -> generate
  - Electron showed a live main window plus two active renderer processes consistent with the main window and overlay shell being loaded in the clean session

---

# Phase P4 â€” Multi-Model Strategy: Groq + NVIDIA DeepSeek + Ollama

## Status

```text
[x] Done
```

## Goal

Add NVIDIA DeepSeek as deeper backup/refinement model while keeping Groq as instant answer provider.

## Provider Strategy

```text
Groq = instant live answer
NVIDIA DeepSeek = deeper backup/refinement
Ollama = optional local fallback
```

## Modes

### Parallel Mode

- [x] Groq and NVIDIA can both participate in one request when refinement is enabled.
- [x] Groq answer appears first.
- [x] NVIDIA answer arrives later.
- [x] Overlay shows refined answer option.
- [x] Do not replace live answer abruptly while user may be speaking.

### Router Mode

- [x] HR questions route to Groq.
- [x] Behavioral questions route to Groq.
- [x] Simple technical questions route to Groq.
- [x] Deep coding/system design questions route to NVIDIA.
- [-] Resume/JD RAG-heavy questions route to NVIDIA.
- [x] Ollama fallback is available if cloud providers fail.

## Backend Checklist

- [x] Add NVIDIA provider.
- [x] Add NVIDIA env vars.
- [x] Add model router service.
- [x] Add parallel refinement orchestration.
- [x] Add provider timing logs.
- [x] Add provider failure handling.
- [x] Preserve Groq fast path.
- [x] Preserve Ollama fallback.
- [x] Never log NVIDIA API key.

## Frontend/Overlay Checklist

- [x] Show primary provider.
- [x] Show refinement provider if used.
- [x] Show â€œRefined answer available.â€
- [x] Let user choose refined answer.
- [x] Keep overlay simple and readable.

## Acceptance Criteria

- [x] Groq answer still appears fast.
- [x] NVIDIA can return deeper answer when enabled and available.
- [x] Refined answer does not confuse live workflow.
- [x] Router mode selects correct provider for deep questions.
- [x] Fallback errors are clear.

### P4 Validation Notes

- `python -m py_compile` passed for touched backend provider and generate files.
- `npm run build` passed in `frontend/`.
- With NVIDIA disabled, generation still worked through Groq with `primary_provider=groq` and `refinement_status=disabled`.
- With `ENABLE_NVIDIA_REFINEMENT=true` and `ENABLE_PARALLEL_REFINEMENT=true`, Groq returned immediately with `refinement_status=pending` plus a refinement job id.
- Polling `GET /generate/refinement/{job_id}` then moved the same request to `refinement_status=failed` safely when an invalid NVIDIA key was used, while keeping the Groq answer intact.
- Router fallback was validated with a deep technical/system-design prompt: the backend attempted NVIDIA first and then returned a Groq answer safely when NVIDIA failed.
- Resume grounding from P2 still worked with retrieved chunks in the generation response.
- Job context from P3 still remained threaded into generation.
- Ollama fallback was attempted with an invalid Groq key and local Ollama enabled, but the local Ollama generate path was unavailable in this environment, so full fallback success was not confirmed.
- A clean Electron shell session was revalidated for P4:
  - stale Vite/Electron processes were stopped
  - backend restarted cleanly on `http://127.0.0.1:8000`
  - Vite restarted cleanly on `http://localhost:5173` with no port conflict
  - Electron opened cleanly and registered `Ctrl+H`
  - overlay visibility toggled successfully through `Ctrl+H`
  - a live overlay screenshot confirmed the Groq answer still renders correctly
- Finalized P4 scope:
  - Groq remains the immediate overlay answer path and the stable production provider
  - provider architecture for NVIDIA and Ollama exists without changing the Groq-first default path
  - NVIDIA refinement and routing are implemented but paused by default
  - refined answers are user-applied and do not auto-replace the live overlay answer when NVIDIA is re-enabled later
  - more aggressive RAG-specific routing remains deferred to a later tuning pass rather than blocking P4 completion
- Frontend refinement UX was completed with an explicit `Apply Refined Answer` action:
  - the control panel keeps `Provider` and `Primary` stable on the Groq-first path
  - a separate `Displayed answer` field now shows when the NVIDIA refined answer is the one currently pushed to the overlay
  - failed refinement continues to keep the Groq answer without changing the overlay unexpectedly
  - frontend polling now tracks only the latest active refinement job and ignores stale completions from older job ids
- NVIDIA refinement was tested but paused due to latency and timeout instability. Groq remains the production path until NVIDIA behavior is revisited.

---

# Phase P5 â€” Screen Reading / OCR Mode

## Goal

Let SAIIA read a user-approved screen/window/region when the interviewer says to solve a visible question.

## Product Rule

Screen reading must be user-triggered and permission-based.

SAIIA must not silently spy on the screen.

## Use Cases

- [ ] Coding problem on screen.
- [ ] Aptitude problem on screen.
- [ ] Written technical question.
- [ ] System design prompt.
- [ ] Browser-based problem statement.

## Electron Checklist

- [x] Add Read Screen button.
- [x] Add screen/window/region selection.
- [x] Capture screenshot with user action.
- [x] Avoid continuous hidden screen capture.
- [x] Do not store screenshot unless user explicitly enables debug mode.

## Backend/OCR Checklist

- [x] Add screen text extraction endpoint.
- [x] Add OCR service.
- [x] Choose a lightweight local OCR engine for the first Windows-friendly pass.
- [x] Return extracted text.
- [x] Detect no-readable-text case.
- [x] Allow user to edit extracted text before answer generation.
- [x] Classify screen-extracted question.
- [x] Generate answer from screen question.

## Frontend Checklist

- [x] Add Screen Read Mode UI.
- [x] Show extracted question preview.
- [x] Let user edit extracted text.
- [x] Add "Generate from screen text" button.
- [x] Show clear errors.

## Acceptance Criteria

- [x] User triggers screen read manually.
- [x] SAIIA extracts readable screen text.
- [x] User confirms extracted question.
- [x] Answer appears in overlay.
- [x] No hidden continuous screen capture occurs.

### P5 Progress Notes

- Implemented a new backend OCR route at `POST /api/screen/ocr`.
- Chosen OCR engine: `rapidocr-onnxruntime` for a lightweight local CPU path without adding a separate Tesseract install.
- Added native Electron screen capture support with `desktopCapturer` in the main process.
- Added preload IPC methods for screen capture source listing and one-shot capture through the safe desktop app bridge.
- Updated the main-window `Capture Question from Screen` flow to:
  - use Electron source selection and capture inside the desktop app
  - fall back to browser `getDisplayMedia` only for local dev rendering
  - send a single PNG frame to the backend and discard it after OCR
- Added an editable `Screen OCR Preview` panel and `Generate Answer from Screen Text` flow that reuses the existing classify and generate pipeline.
- Backend validation passed for:
  - readable sample image -> OCR success
  - blank image -> `Could not extract readable text.`
  - invalid file -> `Unsupported image format.`
- Pipeline validation passed for:
  - OCR-derived question -> classify success
  - OCR-derived question -> Groq answer generation success
  - resume grounding still active during OCR-based generation
- Electron shell validation passed for:
  - clean `npm run electron:dev` startup
  - no Vite port conflict after stale-process cleanup
  - `Ctrl+H registered for overlay hide/show`
- Remaining validation before marking P5 complete:
  - Electron runtime click-through for real source selection and OCR preview
  - visual overlay confirmation from a generated OCR-based answer
  - microphone-flow regression check after the Electron capture change

---

## Screen Intelligence Architecture Migration

Status:

```text
[x] C0.9.1 - Documentation and architecture lock complete
[~] C0.9 - Deferred by product-priority decision; C0.9.1, C0.9.2, C0.9.3, C0.9.4, and C0.9.5 complete; C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, controlled unsupported-content results, and Chrome/Edge real-page validation pending; C0.9.7 through C0.9.13 deferred
[x] C0.9.2 - Analyze Screen OCR/Extension menu, contextual result controls, and optimized one-click multi-question OCR complete
[x] C0.9.3 - Extraction Result Envelope and Normalized Question schema complete
[x] C0.9.4 - Screen Intelligence orchestrator, request ownership, and reliable active-window targeting complete
[x] C0.9.5 - Generic Chrome/Edge extension prototype
[~] C0.9.6 - Deferred with implementation present; Generic Coding-Page DOM Extraction implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example block grouping, sample/example metadata preservation, final extraction-quality fixes for explanation pairing, Input/Output and STDIN/Function tables, runtime panel exclusion, `Prints`/`Returns`, canonical editor counts, folded-code diagnostics, confidence calibration, false-negative/false-MCQ/false-visual detection fixes, and controlled unsupported-content results; Chrome/Edge real-page validation pending
[-] C0.9.7 through C0.9.13 - deferred
```

Previous architecture:

- P5 represents the current OCR baseline.
- Existing P5 OCR work must not be deleted.
- Historical validation results in this tracker remain preserved.

New architecture:

- Analyze Screen becomes a user-selected menu with exactly OCR and Extension actions.
- Extension is primary for accessible browser coding webpages through a generic paired Chrome/Edge extension.
- One click on Extension requests active-tab extraction from the preferred paired browser.
- OCR remains primary for other visible content and fallback for coding content unavailable through the extension.
- No silent fallback is allowed between Extension and OCR.
- Both paths return an Extraction Result Envelope containing one or more Normalized Questions.
- OCR quiz/batch results answer all fully visible independent questions from one screenshot and one screen-model request, with no selection step.
- C0.9.3 adds the shared contract as a backward-compatible `envelope` on the current OCR answer response; legacy fields remain available.
- C0.9.4 wraps the existing OCR path and temporary Extension-unavailable path in source-owned operation/request IDs, rejects stale/cancelled/superseded/duplicate commits, preserves one successful Analyze Screen history entry per OCR operation, and resolves normal Analyze Screen OCR to the focused external window rather than a stale Chrome target.
- Coding-language and submission-mode resolution follow `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`.
- Future implementation status must be recorded in C0.9 of `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`.

This section records the migration from OCR-only planning to dual-source Screen Intelligence. It intentionally references C0.9 rather than duplicating every implementation checklist item.

---
# Phase P6 â€” Overlay Product Polish

## Goal

Make the overlay feel professional, compact, and reliable.

## P6A â€” Transparent Runtime UI Foundation

### Status

```text
[~] In progress
```

### P6A Scope

- [x] Create a transparent glass-style diagnostics foundation for the main Electron window.
- [x] Split the runtime UI into dedicated `MainDiagnosticsWindow` and `OverlayWindow` React components.
- [x] Add shared `glass.css` styling tokens and layout primitives.
- [x] Add collapse / expand behavior for the main diagnostics panel.
- [x] Fix main-panel overflow with internal scrolling and bounded OCR preview areas.
- [x] Keep working runtime controls in the main diagnostics window for now.
- [x] Keep `Ctrl+H` overlay toggle wiring unchanged.
- [x] Preserve backend routes and existing P1-P5 frontend pipeline logic.

### P6A Notes

- The main diagnostics surface is now a frameless transparent Electron window with a glass panel shell rather than a standard dashboard layout.
- The floating overlay now renders through a dedicated component with clearer glass styling and answer metadata, while keeping the existing overlay state sync intact.
- The OCR source picker, OCR preview, answer preview, and runtime logs now sit inside scroll-safe glass cards so the panel remains reachable on smaller window heights.
- A small `PRODUCT.md` was added to capture the product register and runtime design intent required by the repo design-skill flow.
- P6A intentionally keeps these controls working in the diagnostics window:
  - Start Recording
  - Start Auto Mode
  - Capture Question from Screen
  - Generate Answer from Screen Text
  - Hide Overlay
- Moving live controls fully into the overlay remains deferred to later P6 subphases.

### P6A Validation Notes

- `npm run build` passed after the component split and glass styling work.
- `node --check frontend/electron/main.cjs` passed.
- Clean live startup passed again during P6A validation:
  - backend restarted cleanly on `http://127.0.0.1:8000`
  - Vite came up on `5173`
  - Electron launched
  - `Ctrl+H registered for overlay hide/show`
- Live Electron UI checks passed:
  - the main diagnostics window rendered as a transparent glass shell
  - content remained readable in both the main panel and the overlay
  - collapse / expand worked
  - internal scrolling worked
  - the OCR preview stayed reachable and did not cut the layout
- Live OCR flow passed in Electron:
  - `Capture Question from Screen` opened the Electron source picker
  - OCR preview appeared from a real captured window
  - OCR text was edited and `Generate Answer from Screen Text` completed
  - the generated answer appeared in the overlay
  - `provider=groq` and `refinement_status=disabled` were confirmed on the successful OCR request
- Overlay regression checks passed:
  - the overlay received a newly generated answer after a live request
  - `Ctrl+H` hid and re-showed the overlay after generation
  - after a forced backend-offline failure, the previous answer was cleared and the overlay showed an error instead of presenting stale content as a new answer
- Microphone pipeline behavior was validated end-to-end inside Electron using deterministic fake microphone input:
  - `Start Recording` -> transcribe -> classify -> generate -> overlay update completed
  - a successful retry confirmed `provider=groq` and `refinement_status=disabled`
  - the successful retry transcript landed as `What is Javasgript?`, but the generated answer still correctly answered JavaScript
- P6A is still blocked from closure because the exact requested human spoken microphone check was not performed with a physical mic:
  - current validation used Chromium fake microphone injection (`--use-file-for-fake-audio-capture`) rather than a literal spoken hardware-microphone pass
  - do not start P6B until one real spoken mic pass confirms the same end-to-end behavior

## Checklist

- [ ] Improve overlay layout.
- [x] Add compact mode.
- [x] Add opacity control.
- [ ] Add position presets.
- [ ] Persist overlay position.
- [ ] Persist font size.
- [ ] Persist opacity.
- [ ] Add refined answer display area.
- [x] Add loading state.
- [x] Add error state.
- [ ] Add copy answer button if useful.
- [x] Improve drag behavior.
- [ ] Improve text selection behavior.

## Screen Share Privacy Rule

SAIIA must not claim guaranteed invisibility.

Use this wording:

```text
Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, a window, or a browser tab.
```

## Acceptance Criteria

- [ ] Overlay looks product-ready.
- [ ] Overlay remains readable.
- [ ] Controls are reliable.
- [ ] Position and display settings persist.

## P6B â€” Floating Interview Toolbar

### Status

```text
[~] In progress
```

### P6B Notes

- Added a dedicated floating toolbar inside the overlay with:
  - SAIIA brand pill plus live status label
  - microphone and system-audio state toggles
  - `AI Answer`, `Analyze Screen`, and `Chat` actions
  - a local mm:ss session timer
  - a More menu for auto-generate, font size, overlay opacity, clear actions, main-panel open, and end-session
  - a collapse-to-pill state for the overlay
- Added safe Electron preload and main-process hooks for:
  - `Ctrl+Enter` -> toolbar AI answer trigger
  - `Ctrl+Shift+Enter` -> toolbar analyze-screen trigger
  - overlay opacity updates
  - opening the main diagnostics panel from the overlay
- Kept backend generation, STT, OCR services, RAG, and NVIDIA settings untouched in this phase.
- Left click-through and deeper screen-share protection as visible non-broken display states rather than risky partial implementations.

### P6B Validation Notes

- `npm run build` passed in `frontend/`.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.
- Toolbar runtime wiring now routes back into the existing main-window handlers for:
  - manual microphone recording
  - auto mode toggle
  - screen OCR capture flow
  - answer generation from the latest transcript or OCR text
- Live desktop validation is still required before P6B can be marked done:
  - confirm the floating toolbar appearance in the real Electron overlay window
  - confirm drag behavior by hand
  - confirm `Ctrl+H`, `Ctrl+Enter`, and `Ctrl+Shift+Enter` in a live Electron session
  - confirm OCR, microphone, and overlay update flows end to end after the toolbar changes

---

# Phase P7 â€” Main App UI and Onboarding Polish

## Status

```text
[~] In progress
```

## Goal

Make SAIIA understandable for a new user.

## Screens

- [ ] Welcome screen
- [x] Profile setup
- [x] Resume upload
- [x] Job target setup
- [x] Main interview control panel
- [ ] Settings
- [~] Troubleshooting/help

## Checklist

- [ ] Add first-run onboarding.
- [x] Explain Manual Mode.
- [ ] Explain Auto Listen Mode as future/experimental if not ready.
- [x] Explain Screen Read Mode.
- [ ] Add ready-for-interview checklist.
- [ ] Add backend health indicator.
- [x] Add Groq configured indicator.
- [x] Add NVIDIA configured indicator.
- [ ] Add ffmpeg available indicator.
- [x] Add microphone available indicator.
- [x] Add resume indexed indicator.
- [~] Improve empty states.
- [~] Improve loading states.
- [~] Improve error banners.

### P7 Progress Notes

- The profile setup experience is now a real product surface rather than a placeholder:
  - resume upload and extraction
  - extracted-field review before save
  - resume index build/rebuild/remove actions
  - optional job description/company extraction and save/delete actions
- The main interview control panel now exposes:
  - manual recording
  - Auto Mode
  - screen analysis
  - provider and timing diagnostics
  - refinement status and overlay controls
- The overlay now includes a floating runtime toolbar with:
  - recording and audio-source toggles
  - `AI Answer`, `Analyze Screen`, and chat actions
  - local timer, collapse state, and More menu actions
- Troubleshooting/help is partially present through inline runtime status, diagnostics metadata, and README troubleshooting coverage.
- Still missing before P7 can be marked done:
  - true first-run onboarding
  - a user-facing readiness checklist
  - a cleaner dedicated settings/help experience

## Acceptance Criteria

- [ ] New user can understand setup without reading code.
- [ ] App shows what is ready and what is missing.
- [ ] UI feels calm, clean, and serious.

---

# Phase P8 â€” Auto Listen Mode

## Status

```text
[~] In progress
```

## Goal

Automatically detect interviewer questions and generate answers without manual Start/Stop.

## Important Rule

Manual Mode must remain stable and available.

## Current Auto Mode Baseline

This phase now has both:

- a deterministic repeated-segment Auto Mode slice
- an AssemblyAI-streaming Auto Mode path with local fallback hooks

- [x] Add Auto Mode toggle in the main control panel.
- [x] Record repeated short microphone segments in Auto Mode.
- [x] Reuse `/transcribe`, `/classify`, and `/generate` for detected questions.
- [x] Add backend question-detect helper and route.
- [x] Reject empty, short, filler, duplicate, and recent transcripts before generation.
- [x] Add a short generation cooldown to reduce duplicate rapid answers.
- [x] Keep manual Start Recording flow intact.
- [x] Keep overlay IPC flow and `Ctrl+H` behavior unchanged.
- [x] Add backend WebSocket routes for streaming auto STT.
- [x] Add AssemblyAI streaming bridge for microphone Auto Mode.
- [x] Add system-audio Auto Mode streaming path.
- [x] Add local fallback/error handling when streaming fails.

### Current Validation Notes

- `POST /api/question-detect` accepted interview-style prompts such as `Tell me about your project.`, `Introduce yourself`, and `What are your skills?`
- `POST /api/question-detect` rejected filler/noise transcripts such as `okay yes` and `one second`.
- Manual generation still passed for `Tell me about yourself.`
- The existing P1 resume extraction, P2 resume index build/status, and P3 job context save/get paths still passed after the Auto Mode changes.
- `python -m py_compile` passed for touched backend files.
- `npm run build` passed in `frontend/`.
- Streaming Auto Mode wiring now exists in both backend and frontend for:
  - `/ws/auto-stt`
  - `/ws/system-auto-stt`
  - AssemblyAI streaming session events
  - Whisper/local fallback messaging when streaming fails
- Live production confidence is still limited because the full streaming path has not yet been closed out with a final real interview-session validation pass.

## Pipeline

```text
continuous audio stream
â†“
voice activity detection
â†“
speech segment buffering
â†“
silence detection
â†“
transcription
â†“
question detection
â†“
duplicate filtering
â†“
classification
â†“
answer generation
â†“
overlay update
```

## Checklist

- [x] Add Auto Listen toggle.
- [~] Add VAD.
- [~] Add silence threshold.
- [x] Add max segment duration.
- [x] Add question detector.
- [x] Add duplicate filter.
- [x] Add cooldown window.
- [x] Add listening status.
- [ ] Add pause/resume.
- [~] Add manual override.
- [x] Prevent repeated answers for same question.
- [x] Ignore non-question speech.

## Acceptance Criteria

- [~] Auto Listen detects clear interview questions.
- [~] Auto Listen ignores noise and random speech.
- [~] Overlay updates automatically.
- [x] Manual Mode still works.

---

# Phase P9 â€” Better Audio Capture

## Status

```text
[~] In progress
```

## Goal

Improve audio capture beyond basic microphone input.

## Checklist

- [ ] Add microphone selector.
- [ ] Add audio level meter.
- [ ] Add microphone test.
- [x] Show selected input device.
- [x] Explore system audio support.
- [ ] Document virtual audio cable option if needed.
- [~] Document meeting app limitations.
- [ ] Avoid claiming all interviewer audio is captured automatically.

### P9 Progress Notes

- System-audio capture is no longer just a future idea:
  - backend system-audio routes exist
  - frontend toggles and runtime status exist
  - manual system-audio record/stop flow exists
  - system-audio Auto Mode streaming path exists
- The UI already exposes selected source state for microphone vs system audio and warns when no source is selected.
- Remaining P9 work is mainly polish and operator controls:
  - device picking
  - input metering
  - test utilities
  - clearer user-facing docs about capture limitations

## Acceptance Criteria

- [ ] User can select correct microphone.
- [ ] User can test audio before interview.
- [ ] Audio limitations are clear.

---

# Phase P10 â€” Settings and Profile Management

## Status

```text
[~] In progress
```

## Goal

Let users manage SAIIA without editing `.env` or files manually.

## Settings Sections

- [x] Profile
- [x] Resume
- [x] Job target
- [~] Audio
- [~] Overlay
- [ ] AI providers
- [ ] Privacy
- [~] Troubleshooting

## Checklist

- [x] Edit profile.
- [x] Re-upload resume.
- [x] Delete resume data.
- [ ] Configure Groq key locally.
- [ ] Configure NVIDIA key locally.
- [~] Toggle NVIDIA refinement.
- [ ] Toggle Ollama fallback.
- [ ] Select Whisper model.
- [ ] Select audio input device.
- [~] Adjust overlay settings.
- [ ] Clear local data.

### P10 Progress Notes

- A meaningful part of settings/profile management already exists through the profile setup surface:
  - editable saved profile fields
  - resume re-upload and extraction review
  - resume index rebuild/remove
  - job target extract/save/delete
- Overlay runtime settings are partially exposed through the live UI:
  - font size controls
  - overlay opacity control
  - overlay visibility controls
- Provider configuration is still developer-facing through `.env`, so P10 is not complete.

## Acceptance Criteria

- [ ] User can configure core app behavior from UI.
- [ ] Sensitive data can be deleted.
- [ ] Non-developers do not need to edit `.env`.

---

# Phase P11 â€” Session History

## Goal

Store useful local interview history.

## Checklist

- [ ] Store transcript.
- [ ] Store question category.
- [ ] Store generated answer.
- [ ] Store refined answer.
- [ ] Store provider.
- [ ] Store latency.
- [ ] Store timestamp.
- [ ] Store input source: audio/screen/manual.
- [ ] Allow user to view history.
- [ ] Allow user to delete history.
- [ ] Allow export of session notes.
- [ ] Add privacy controls.

## Acceptance Criteria

- [ ] User can review past questions.
- [ ] User can delete sensitive history.
- [ ] History does not leak into Git/logs.

---

# Phase P12 â€” Performance and Reliability

## Goal

Make SAIIA fast and stable for repeated real usage.

## Metrics

- [ ] transcription_ms
- [ ] classification_ms
- [ ] retrieval_ms
- [ ] generation_ms
- [ ] refinement_ms
- [ ] total_pipeline_ms
- [ ] provider
- [ ] fallback_used
- [ ] input_source
- [ ] error_type

## Checklist

- [x] Add structured logs.
- [ ] Add debug mode.
- [x] Improve timeout handling.
- [ ] Improve retry behavior.
- [x] Cache profile context.
- [x] Cache resume retrieval context where safe.
- [ ] Avoid duplicate generation.
- [ ] Recover after backend restart.
- [ ] Recover after provider timeout.
- [ ] Show useful errors.

## Acceptance Criteria

- [ ] Typical answer appears quickly.
- [ ] Failures are recoverable.
- [ ] No stale answers appear after failure.
- [ ] Performance bottlenecks are visible.

## Latest Update - Performance Hotfix

- Added end-to-end live pipeline timing for recording, upload, transcription, classification, profile load, RAG, prompt build, Groq generation, frontend update, and total pipeline time.
- Cached `GET /api/profile` on both backend and frontend live-answer paths so profile JSON is not repeatedly reloaded or reparsed during interview answering.
- Kept Affinda out of the live answer path by using only the saved profile JSON plus a summarized prompt profile during answer generation.
- Limited live prompt context to focused profile fields such as name, education, role, top skills, and the strongest project/experience highlights.
- Added `PERFORMANCE_MODE=demo`, `ANSWER_MAX_WORDS`, `MANUAL_STT_PROVIDER`, `RAG_RETRIEVAL_LIMIT`, and `RAG_TIMEOUT_MS` for faster live runs.
- Manual recording now supports a low-latency Groq STT path while preserving the existing fallback behavior.
- The diagnostics panel now exposes the live timing breakdown so slow steps are visible without changing overlay layout.

---

# Phase P13 â€” Packaging and Installer

## Goal

Make SAIIA installable as a desktop app.

## Checklist

- [ ] Add electron-builder.
- [ ] Add app icon.
- [ ] Add app name/metadata.
- [ ] Package frontend and Electron.
- [ ] Decide backend packaging strategy.
- [ ] Decide ffmpeg strategy.
- [ ] Add first-run dependency checks.
- [ ] Create Windows installer.
- [ ] Test install on clean machine.
- [ ] Ensure installer does not include secrets/private data.

## Acceptance Criteria

- [ ] App can launch without developer commands.
- [ ] User sees clear setup errors.
- [ ] Installer is demo-ready.

---

# Phase P14 â€” Testing and QA

## Goal

Prevent regressions.

## Backend Tests

- [ ] Profile validation
- [ ] Resume extraction
- [ ] Resume RAG retrieval
- [ ] Audio validation
- [ ] Transcription errors
- [ ] Classifier categories
- [ ] Groq provider
- [ ] NVIDIA provider
- [ ] Ollama fallback
- [ ] Screen OCR
- [ ] Auto Listen question detector

## Frontend/Electron Tests

- [ ] Main app starts.
- [ ] Overlay starts.
- [ ] IPC sync works.
- [ ] Ctrl+H works.
- [ ] Show/Hide button works.
- [ ] Font-size sync works.
- [ ] Screen Read UI works.
- [ ] Settings UI works.

## Manual QA

- [ ] Fresh install test.
- [ ] Resume upload test.
- [ ] RAG answer test.
- [ ] Manual audio test.
- [ ] Auto Listen test.
- [ ] Screen Read test.
- [ ] Provider fallback test.
- [ ] Failure recovery test.

## Acceptance Criteria

- [ ] Core flows pass repeatedly.
- [ ] New changes do not break MVP.
- [ ] QA checklist passes before release.

---

# Phase P15 â€” Privacy and Security Hardening

## Goal

Protect sensitive local data.

## Sensitive Data

- [ ] Resume
- [ ] Profile
- [ ] Job description
- [ ] Interview questions
- [ ] Generated answers
- [ ] Screenshots
- [ ] Audio recordings
- [ ] API keys
- [ ] Session history

## Checklist

- [ ] Never log API keys.
- [ ] Avoid full resume/profile logs.
- [ ] Avoid storing temp audio longer than needed.
- [ ] Avoid storing screenshots unless required.
- [ ] Add delete local data option.
- [ ] Add clear cloud provider notice.
- [ ] Add privacy section in settings.
- [ ] Encrypt sensitive local data if practical.

## Acceptance Criteria

- [ ] User understands what is stored.
- [ ] User can delete sensitive data.
- [ ] Logs do not leak private content.

---

# Phase P16 â€” Auth, Billing, Usage Limits, and Licensing Preparation

## Goal

Prepare for the Protected Commercial Edition without building everything too early.

## Status

```text
[-] Future / very last major layer
```

## Rule

Do not delay product usefulness because of licensing.

But keep the architecture ready.

## Preparation Checklist

- [ ] Keep API keys in backend/server only.
- [ ] Keep answer generation in backend.
- [ ] Keep resume/RAG processing in backend.
- [ ] Add no-op feature gate service.
- [ ] Add future route placeholders only if useful.
- [ ] Avoid hardcoding paid plan logic in frontend.
- [ ] Keep expensive features easy to protect later.

## Future Modules

- [ ] Auth
- [ ] Subscription plans
- [ ] Usage limits
- [ ] Payment provider
- [ ] Device activation
- [ ] License validation
- [ ] Code signing
- [ ] Auto-update

## Future Protected Features

- [ ] answer_generation
- [ ] transcription_minutes
- [ ] resume_upload
- [ ] resume_rag
- [ ] screen_read
- [ ] auto_listen
- [ ] nvidia_refinement
- [ ] session_history

## Acceptance Criteria

- [ ] Core app can later wrap protected features with auth/subscription checks.
- [ ] No major rewrite is needed to move from Core PRD to Protected Commercial PRD.

---

# Phase P17 â€” Protected Commercial Edition

## Goal

Build the full commercial protection layer from PRD B.

## Build Order

### P17.1 Auth

- [ ] Register
- [ ] Login
- [ ] Logout
- [ ] Refresh token
- [ ] Current user endpoint
- [ ] Secure token storage

### P17.2 Usage Tracking

- [ ] Usage events
- [ ] Monthly usage counters
- [ ] Usage status endpoint
- [ ] Increment usage after expensive operations

### P17.3 Plans

- [ ] Free plan
- [ ] Student plan
- [ ] Pro plan
- [ ] Institution plan
- [ ] Plan feature table
- [ ] Backend feature checks

### P17.4 Payments

- [ ] Razorpay or Stripe checkout
- [ ] Webhook verification
- [ ] Subscription status updates
- [ ] Billing page

### P17.5 Device Licensing

- [ ] Device activation
- [ ] Device limits
- [ ] Device deactivation
- [ ] Device validation

### P17.6 App Protection

- [ ] ASAR packaging
- [ ] Minification
- [ ] Basic obfuscation
- [ ] Signed installer
- [ ] Auto-update
- [ ] Integrity checks

## Acceptance Criteria

- [ ] Users can log in.
- [ ] Plans control feature access.
- [ ] Usage limits are enforced server-side.
- [ ] Pro features are blocked for Free users by backend.
- [ ] Device limits work.
- [ ] Payment webhooks update subscriptions.
- [ ] Desktop app contains no valuable secrets.
- [ ] Cracked UI cannot access paid backend features without valid account/subscription.

---

## Latest Update — Groq STT Provider

- Added configurable STT routing with:
  - `STT_PROVIDER=groq`
  - `GROQ_STT_MODEL=whisper-large-v3-turbo`
  - `STT_FALLBACK_PROVIDER=whisper_local`
- Kept `/transcribe/` path and `text` field intact while extending the response with:
  - `transcription_provider`
  - `transcription_model`
  - `transcription_ms`
  - `fallback_used`
  - `fallback_reason`
- Kept local Whisper available as the fallback path and preserved ffmpeg-based local decode behavior.
- Added Groq STT validation outcomes:
  - `python -c "import ssl; print('ssl ok')"` passed
  - `python -c "from groq import Groq; print('groq ok')"` passed after adding the `groq` package
  - clean validation backend on `127.0.0.1:8001` returned `/transcribe/` success with `transcription_provider=groq`
  - invalid Groq key on `127.0.0.1:8002` fell back successfully to `whisper_local` with `fallback_used=true` and `fallback_reason=groq_api_key_invalid`
  - invalid Groq key with fallback disabled on `127.0.0.1:8004` returned a clear `500` error: `Groq STT authentication failed. Please update GROQ_API_KEY and try again.`
  - Electron microphone flow regression passed against the Groq STT backend by validating `Start Recording -> Stop -> transcript -> classify -> generate -> overlay`
- `npm run build` still passed after the backend STT provider changes.

## Latest Update — P6A.1 Human Answer Style + Overlay Reveal

- Tightened the Groq answer prompt so overlay answers now aim for:
  - a direct opening
  - 3 to 4 short bullets
  - one grounded example when evidence supports it
  - simple, speakable wording
  - no fake metrics, results, or extra experience claims
- Added banned-phrase pressure in both prompt and cleanup to suppress patterns like:
  - `Here is a possible answer`
  - `You can say`
  - `As an AI`
  - `In conclusion`
  - `Alternatively`
- Added a lightweight overlay-only answer reveal effect:
  - answers reveal progressively in the overlay
  - `Show full answer` instantly reveals the full text
  - a new answer cancels the previous reveal animation
  - reduced-motion preference skips the animation
- Validation for this scoped pass:
  - `npm run build` passed
  - direct Groq samples returned more human, bullet-based answers for HR, technical, behavioral, and coding prompts
  - overlay reveal was validated in Electron by checking partial text, `Show full answer`, and new-answer interruption behavior
- OCR, microphone wiring, Electron window structure, and the existing glass theme were intentionally left unchanged in this pass.

# Final Recommended Build Order

Use this order:

```text
P0  Clean baseline
P1  Resume upload and profile extraction
P2  Resume RAG grounding
P3  Job description context
P4  Multi-model Groq + NVIDIA strategy
P5  Screen Reading / OCR Mode
P6  Overlay polish
P7  Main app onboarding polish
P8  Auto Listen Mode
P9  Better audio capture
P10 Settings and profile management
P11 Session history
P12 Performance and reliability
P13 Packaging and installer
P14 Testing and QA
P15 Privacy and security hardening
P16 Auth/billing/license preparation
P17 Protected commercial edition
```

---

# Current Immediate Next Phase

```text
C0 is marked done. C1 - Supabase Cloud Foundation is complete after C1.5 closure validation. C2 - Authentication and Account Lifecycle is complete through C2.5 Auth Surface Closure. C3.1 Cloud Resume/Profile Storage Planning + Audit is complete. C3.2 Backend Cloud Resume API is merged and live smoke-tested. C3.3 frontend authenticated upload/review UI is implemented under `/auth/resume`. C3.4 cloud RAG/index activation is implemented through user-owned chunk generation, backend-only activation, and ready-current resume behavior. C3.4.5 GPT-based resume extraction provider is implemented. C3.5 delete/rebuild/status closure is implemented. C4 Job Target / JD Cloud Sync is in progress with C4.1 audit/design complete and C4.2 authenticated backend plus required migration implemented locally with tests passing and live Supabase smoke validation passed on saiia-dev. C4.3 main website job-target UI is cancelled/re-scoped; job target selection moves to desktop startup/session setup after desktop authenticated cloud identity exists. C5.1 desktop authenticated cloud identity audit/design is documented in `docs/C5_DESKTOP_AUTH_CLOUD_IDENTITY_PLAN.md`. C5.2 desktop authenticated cloud identity is implemented locally with Electron main-process auth/session handling and focused tests. C5.3 desktop auth status/login/logout UI wiring is implemented locally through existing safe preload APIs. C5.4 desktop cloud startup context plumbing is implemented locally through existing safe preload APIs and authenticated backend summary routes. No C4 generation integration, desktop startup/session setup UI, cloud sync engine, local/cloud data migration, session history, transcript storage, AI notes, Ask AI, billing, usage, email-provider integration, payment, licensing, admin console, or final website UI work has started.
```

P6B/P8/P9 consolidation records are preserved as historical desktop validation notes, not as the current execution authority.
## Latest Update - Resume Extraction + Answer Cleanup Fix

- Expanded resume extraction into structured profile fields including `full_name`, contact info, role/title, education breakdown, top skills, technical skills, projects, experience, achievements, tools/frameworks, and certifications.
- Kept full resume text separate as `raw_resume_text` for local RAG/indexing instead of feeding it directly into answer prompts.
- Added manual review warnings when name or education extraction is weak so the user can correct fields before saving.
- Tightened introduction-style answer generation so HR prompts use only the most relevant profile details and avoid noisy resume dumps.
- Added final answer cleanup to strip markdown bullets, duplicate markers, and banned meta phrases before overlay rendering.
- Validation update: `npm run build` passed after the resume/profile and answer cleanup changes.

## Latest Update - AssemblyAI STT Provider

- Replaced Groq STT as the default `/transcribe/` provider with AssemblyAI while keeping Groq as the answer generation provider.
- Added AssemblyAI STT routing with local Whisper fallback when `ASSEMBLYAI_API_KEY` is missing or AssemblyAI transcription fails.
- Preserved the existing manual recording flow, Auto Mode loop, OCR flow, profile/resume grounding, and job-context flow.
- Extended `/transcribe/` responses with `no_speech` and `reason` so silence can be handled without crashing Auto Mode.
- Auto Mode silence now returns to `Waiting for a question...` without clearing the last valid answer or triggering classify/generate.
- Validation update: backend compile checks passed, `assemblyai` import was verified locally, and `npm run build` still passed.

## Latest Update - Streaming Auto STT + System Audio Runtime

- Added AssemblyAI streaming as the active Auto Mode transport path with backend WebSocket routes for:
  - `/ws/auto-stt`
  - `/ws/system-auto-stt`
- Added frontend streaming session handling, reconnect/error states, and fallback messaging when streaming fails.
- Added system-audio capture support across manual mode and Auto Mode flows, while keeping microphone-only mode intact.
- Preserved the existing classify/generate pipeline, resume grounding, job-context tailoring, and overlay update behavior around the new audio paths.

## Latest Update - P7A Affinda Resume Parser Integration

- Added an Affinda-first resume parser path on the backend using REST, without exposing credentials to the frontend or changing overlay, STT, OCR, or Groq answer generation flows.
- Kept the existing local resume extraction service as the fallback when the Affinda key, workspace, document type, request, or parse result is unavailable or incomplete.
- Extended the structured profile schema to preserve aliases like `branch`, `college`, and `university` alongside the existing `branch_specialization` and `college_university` fields for compatibility, and added `soft_skills`.
- Updated `/api/resume/extract` to return parser metadata, fallback state, missing fields, review-required state, and the normalized editable `profile` payload.
- Preserved local resume indexing and grounding by keeping `raw_resume_text` separate for RAG/index use instead of dumping it into the answer prompt.
- Updated the profile setup page to consume the richer extraction response and show clearer provider/fallback/manual-review messaging before save.

## Latest Update - Personal Question Story Routing

- Added a dedicated personal-question routing pass with subtypes for childhood, memories, difficult phases, failures, achievements, hobbies, books/movies/music, preferences, role models, values, helping someone, creative hypotheticals, and sensitive personal prompts.
- Replaced the old one-or-two-sentence personal prompt contract with a creative/hybrid personal narrative prompt that allows safe, believable low-risk details while blocking unsupported sensitive claims.
- Personal questions now suppress resume RAG, technical skills, projects, education, certifications, and job context unless the question explicitly connects the personal topic to career or professional growth.
- Added non-breaking generation metadata fields for `answer_mode`, `personal_subtype`, `personal_context_used`, `creative_generation_used`, and `target_word_range`.
- Added category-aware personal validation and a safe repair fallback for under-length, one-sentence, meta, professionalized, or unsupported-sensitive personal answers.
- Preserved professional grounding: technical/project questions such as `Tell me about your FastAPI project.` still use resume snippets, and conceptual questions such as `Explain authentication.` still use the technical route.
- Validation update:
  - backend compileall passed for `backend/app`
  - focused backend tests passed: `87 passed`
  - frontend answer-format test passed: `3 passed`
  - `npm run build` passed in `frontend/`
  - manual prompt sweep confirmed personal childhood routing has no resume context, authentication remains conceptual, and FastAPI project prompts retain resume context.

## Latest Update - Analyze Screen OpenRouter Vision Provider

- Replaced the configured primary Analyze Screen vision provider with OpenRouter while preserving Groq as an optional `SCREEN_VISION_PROVIDER=groq` compatibility path.
- Set the default screen vision model to `google/gemma-4-31b-it`, with model selection still environment-driven so `google/gemma-4-31b-it:free` can be used for development without hardcoding it.
- Added backend-only OpenRouter configuration for API key, base URL, optional attribution headers, timeout seconds, and RapidOCR fallback via `ENABLE_RAPIDOCR_FALLBACK`.
- Strengthened the screenshot extraction prompt to treat screenshot text as untrusted data, ignore SAIIA/browser/meeting/editor chrome, preserve task details, and return strict structured JSON.
- Added Pydantic validation for model output, balanced JSON-object extraction, Markdown fence cleanup, confidence clamping, allowed question-type enforcement, and empty-question rejection.
- Preserved the existing `/api/screen/analyze-active-window` response fields while adding provider-neutral metadata: `vision_latency_ms`, `vision_fallback_used`, `vision_fallback_reason`, `vision_http_status`, `vision_error`, `vision_timeout`, `vision_retry_after`, and `extraction_confidence`.
- Preserved the existing Electron capture flow, active-window selection, SAIIA hide-before-capture behavior, frontend Analyze Screen request flow, `/generate/` final-answer route, regular Groq answer generation, audio paths, Auto Mode, overlay layout, and shortcuts.
- Validation update:
  - backend compileall passed for `backend/app`
  - focused OpenRouter screen-vision tests passed: `23 passed`
  - broader existing backend tests ran with one unrelated pre-existing failure in `test_coding_quality_gate.py::test_runner_and_import_only_editor_does_not_force_stub_mode`
  - `npm run build` passed in `frontend/`
  - live synthetic OpenRouter extraction passed for HackerRank-style coding, LeetCode-style coding, MCQ, terminal error, code-output, chart, architecture diagram, interview question, no-question screen, and SAIIA-overlay screen
  - live RapidOCR fallback passed when OpenRouter was unavailable through a missing API key

## Latest Update - C0 Answer Intelligence Stabilization - Problem 1

- Status: implemented with automated validation; not marked fully resolved because manual desktop live flows were not run in this turn.
- Date: 2026-07-15.
- Scope: Answer Generation Problem 1 only. Problem 2 answer variation/similarity/randomization remains deferred.
- Architecture added: deterministic `AnswerPlan` with answer type, profile/job/general-knowledge context policies, prompt hints, non-breaking response metadata, and cheap validation metadata.
- Files changed: `backend/app/nlp/answer_planner.py`, `backend/app/nlp/answer_generator.py`, `backend/app/api/generate.py`, `backend/tests/test_answer_planner_problem1.py`, `backend/tests/test_non_coding_answer_quality.py`, this tracker, and the cloud roadmap.
- Protected flows: regular Groq answer generation provider, screen capture, STT/audio, Auto Mode, Electron window structure, overlay layout, resume parsing/indexing internals, job context storage, cloud/auth/billing.
- Validation results:
  - backend compileall passed for `backend/app`
  - focused answer-planner, non-coding quality, and answer reliability tests passed: `49 passed`
  - full backend test run: `163 passed`, `1 failed` in pre-existing `test_coding_quality_gate.py::test_runner_and_import_only_editor_does_not_force_stub_mode`
  - `npm run build` passed in `frontend/`
  - Electron syntax checks were not run because Electron files were not touched
  - manual desktop/audio/screen flows were not run in this turn
- Known limitations:
  - semantic LLM validation remains conditional/future-hardening; current patch adds deterministic validation metadata without adding another LLM call to every answer.
  - manual live desktop flows still need final user-side verification after automated checks.

## Latest Update - C0 GPT-5.4 Mini Answer Intelligence Stabilization

### Mode State Isolation - Answer / Analyze Screen / Chat - 2026-07-17

- Previous bug: selecting Answer after Chat or Analyze Screen could reuse shared `transcript`/`answer` state and trigger an unwanted duplicate generation.
- Root cause: toolbar tab selection was mixed with execution (`Answer` clicked `ai-answer`), while the floating panel rendered one global answer state for all modes.
- Fix: Answer tab selection is navigation-only; generated answers are tagged with `answerDisplayMode=answer|screen|chat`.
- Overlay behavior: the floating panel keeps lightweight per-mode snapshots and renders the snapshot belonging to the selected tab.
- Ownership: Chat submissions update Chat-owned display state; screen generations update Screen-owned display state; microphone/Answer actions update Answer-owned display state.
- Streaming isolation: provider stream deltas are associated with the initiating display mode before the stream clears or appends visible text.
- Validation: focused frontend tests, Vite build, and Electron syntax checks passed. Manual Electron mode-switch sequences still need user-side verification.

- True streaming update: added `/generate/stream` using NDJSON events (`start`, `delta`, optional `replace`, `metadata`, `done`, `error`) so OpenAI Responses API text deltas can reach the overlay before full generation finishes.
- Streaming model/provider: unchanged `ANSWER_PROVIDER=openai` with `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`; no second GPT model or provider was added.
- Validation compatibility: backend accumulates the streamed primary answer, then runs the existing deterministic validation, conditional correction, and controlled variation path; accepted post-processing changes are sent once as `replace`.
- Fallback policy: Groq fallback can emit a complete compatible answer only when OpenAI fails before visible text; after partial OpenAI text, the partial answer is preserved with a controlled error event.
- Rollback: set `ENABLE_TRUE_ANSWER_STREAMING=false` and keep using the existing non-streaming `/generate/` endpoint.
- Privacy: stream events exclude API keys, prompts, hidden reasoning, raw retrieved chunks, and authorization data.
- Status: implemented with mocked provider validation; not marked fully complete because live OpenAI/manual desktop flows were not run in this turn.
- Date: 2026-07-16.
- Previous answer provider path: Groq primary via `PRIMARY_LLM_PROVIDER`/`LLM_PROVIDER`, coding path via `CODING_GROQ_MODEL`, optional Groq Llama Versatile refinement through `REFINEMENT_GROQ_MODEL=llama-3.3-70b-versatile`.
- New answer provider path: `ANSWER_PROVIDER=openai` using the official OpenAI Python SDK Responses API and fixed `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`.
- One-model rule: the same `OPENAI_MODEL` is used for primary answer generation, conditional semantic validation, and conditional targeted correction; no second GPT model variable was added.
- Fallback: Groq remains available only through `ANSWER_FALLBACK_PROVIDER=groq` and `ENABLE_ANSWER_PROVIDER_FALLBACK=true`; rollback is `ANSWER_PROVIDER=groq`.
- Refinement: unconditional Llama Versatile refinement is disabled by default through `ENABLE_ALWAYS_ON_REFINEMENT=false` and `REFINEMENT_ENABLED=false`.
- Reasoning routing: simple HR/personal/resume/technical-concept answers use low reasoning, comparisons/process/coding/debugging/output/system-design use medium, simple MCQ can use none; high/xhigh are not used by default.
- Context routing: existing immutable `AnswerPlan` remains the single planner and continues to gate resume/profile/job context before generation and fallback.
- API compatibility: existing `/generate/` fields remain intact; optional metadata now includes reasoning effort, deterministic/semantic validation timing, correction timing, and fallback reason.
- Files changed for this scoped pass:
  - `backend/app/config.py`
  - `backend/app/nlp/answer_generator.py`
  - `backend/app/api/generate.py`
  - `.env.example`
  - `backend/tests/test_openai_answer_pipeline.py`
  - `.env` local placeholder/config only; no secret value added
  - this tracker and the cloud roadmap
- Validation results:
  - `python -m compileall -q backend/app` passed
  - focused OpenAI/provider tests passed: `5 passed`
  - focused answer-planner/generation tests passed: `58 passed`
  - full backend tests: `172 passed`, `1 failed` in pre-existing `test_coding_quality_gate.py::test_runner_and_import_only_editor_does_not_force_stub_mode`
  - `npm run build` passed in `frontend/`
  - `node --check frontend/electron/main.cjs` passed
  - `node --check frontend/electron/preload.cjs` passed
- Known limitations:
  - `OPENAI_API_KEY` is configured as an empty backend-only placeholder, so live OpenAI validation needs the real key supplied locally.
  - manual microphone, system-audio, screen-to-generate, overlay reveal, and live OpenAI-to-Groq fallback flows still need desktop validation before this phase can be signed off.
  - Problem 2 repeated-answer variation remains deferred.

### C0 GPT-5.4 Mini Answer Intelligence Stabilization - Closure Pass

Date: 2026-07-16

Status: backend/provider closure passed with automated and live-provider validation. Full desktop sign-off is still pending manual Electron flow validation.

Closed acceptance failures:

- Fixed `coding_quality_gate` classification so import-only plus `if __name__ == "__main__": pass` runner text no longer forces stub mode.
- Preserved OpenAI primary generation metadata by keeping `primary_generation_ms` for OpenAI responses instead of falling back only to legacy Groq timing.
- Changed successful no-correction status to `correction_status=not_needed`.
- Added deterministic technical completeness and comparison checks for shallow RAG/process answers and false superiority claims.
- Revalidated corrected technical answers with the same Real-life example and technical-completeness rules used for primary answers.
- Cleared deterministic warning metadata when conditional semantic validation confirms the answer is valid.

Final provider state:

- Previous primary answer provider: Groq.
- Previous refinement behavior: optional legacy Llama Versatile refinement.
- New primary answer provider: OpenAI Responses API.
- Fixed model snapshot: `gpt-5.4-mini-2026-03-17`.
- One-model rule: generation, semantic validation, and correction all use `OPENAI_MODEL`.
- Groq remains only as emergency fallback through `ANSWER_FALLBACK_PROVIDER=groq`.
- Llama Versatile unconditional refinement remains disabled by default.

Validation results:

- `python -m compileall -q backend/app` passed.
- Focused tests passed: `107 passed`, `5 warnings`.
- Full backend test suite passed: `177 passed`, `5 warnings`.
- Focused OpenAI/coding closure tests passed: `54 passed`.
- `npm run build` passed in `frontend/`.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.
- Standalone frontend answer/request-state checks passed.
- Live OpenAI smoke confirmed `provider=openai`, `model=gpt-5.4-mini-2026-03-17`, `fallback_used=false`, safe timing metadata present.
- Forced OpenAI failure confirmed Groq fallback works when enabled.
- Forced OpenAI failure with fallback disabled returned a controlled provider error.

Live backend scenarios checked:

- Authentication concept.
- Authentication vs authorization comparison.
- Hashing vs encryption comparison.
- REST vs GraphQL comparison.
- RAG challenges.
- Rate limiting.
- Caching.
- Supervised learning.
- Personal childhood answer.
- Binary-search coding answer.
- URL-shortener system-design answer.

Still pending before full phase sign-off:

- Manual microphone to answer overlay.
- Microphone Auto Mode.
- Manual system-audio answer flow.
- System-audio Auto Mode.
- Analyze Screen to final answer overlay.
- Overlay progressive reveal, Show Full Answer, Ctrl+H, and current resize behavior in the running Electron app.
- Desktop live verification that optional correction failure never clears the visible primary answer.

Rollback:

- Set `ANSWER_PROVIDER=groq` to restore Groq primary generation.
- Set `ANSWER_PROVIDER=openai` and `OPENAI_MODEL=gpt-5.4-mini-2026-03-17` to restore OpenAI primary.
- Set `ENABLE_SEMANTIC_VALIDATION=false` to disable semantic validation.
- Set `ENABLE_CONDITIONAL_CORRECTION=false` to disable targeted correction.
- Set `ENABLE_ANSWER_PROVIDER_FALLBACK=false` to disable Groq fallback.
- Keep `REFINEMENT_ENABLED=false` and `ENABLE_ALWAYS_ON_REFINEMENT=false` to avoid unconditional legacy refinement.

### C0 Answer Generation Problem 2 - Controlled Repeated-Answer Variation

Date: 2026-07-16

Status: implemented with backend automated tests and live OpenAI repeated-question validation. Full desktop sign-off is still pending manual overlay validation.

Architecture:

- Reused the existing Answer Planner, context-policy routing, provider abstraction, deterministic validation, semantic validation, correction pipeline, final formatter, and `/generate/` route.
- Added a process-local, memory-only, bounded temporary answer history.
- Added local deterministic repetition detection using normalized question text, answer type, and a hashed context fingerprint.
- Added deterministic answer-type variation profiles.
- Added local answer similarity using standard-library text similarity and token overlap.
- Added one optional targeted OpenAI variation rewrite only when a repeated valid prose answer is still too similar.
- Coding, debugging, output-prediction, and MCQ answers do not force novelty; correctness stays locked.

Configuration:

- `ENABLE_CONTROLLED_ANSWER_VARIATION=true`
- `VARIATION_HISTORY_LIMIT=3`
- `VARIATION_CACHE_TTL_SECONDS=7200`
- `ENABLE_VARIATION_REWRITE=true`
- Rollback: set `ENABLE_CONTROLLED_ANSWER_VARIATION=false`.

Privacy behavior:

- History is memory-only and clears on backend restart.
- No previous answers are exposed in API responses.
- No normalized question, raw context fingerprint source, resume chunks, prompts, API keys, or provider payloads are logged.
- Context fingerprints are SHA-256 hashes of the relevant profile/snippet/job context scope.

API metadata added:

- `repetition_detected`
- `repetition_count`
- `variation_enabled`
- `variation_profile`
- `variation_applied`
- `variation_rewrite_used`
- `variation_status`
- `similarity_score`
- `previous_answer_count`
- `variation_ms`

Validation results:

- `python -m compileall -q backend/app` passed.
- Focused Problem 2 + OpenAI pipeline tests: `20 passed`, `5 warnings`.
- Focused Problem 1/Problem 2 regression set: `118 passed`, `5 warnings`.
- Full backend tests: `188 passed`, `5 warnings`.
- `npm run build` passed in `frontend/`.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.

Live repeated-question validation:

- OpenAI key available locally.
- Model confirmed: `gpt-5.4-mini-2026-03-17`.
- Repeated technical, comparison, RAG challenge, HR, role-fit, personal, behavioral, resume-project, and FastAPI-experience questions returned varied prose without Groq or Llama calls.
- Coding, MCQ, and output-prediction repeated safely with no rewrite and correct deterministic answer type routing.
- Typical live repeated-question latency was about 1.7s to 4.8s for most prose cases.
- Slowest observed live case was the direct coding smoke at about 8.0s when additional validation/correction phases were triggered.
- Repeated prose cases normally used one primary OpenAI call; variation rewrite was not needed in the live sample because primary outputs were already sufficiently different.
- Mocked tests confirmed exact duplicate prose triggers exactly one `variation_rewrite` call and rewrite failure preserves the valid primary answer.

Known limitations:

- The temporary history is process-local, not shared across backend restarts or multiple backend processes.
- Near-duplicate detection is intentionally conservative and local; ambiguous phrasing may not be treated as repeated.
- Manual Electron overlay validation for progressive reveal, Show Full Answer, Ctrl+H, resize behavior, and stale response protection was not run in this pass.

---

## Analyze Screen Persistent Result and Explicit Reanalysis - 2026-07-17

Scope:

- Fixed the Analyze Screen restart-on-return bug in the frontend overlay state flow.
- Top toolbar Analyze Screen selection is now navigation-first.
- A first empty idle Analyze Screen click may start the initial analysis.
- Returning to Analyze Screen with a saved result, active request, or error no longer starts another capture.
- Added internal Analyze Screen panel actions for Analyze Screen, Analyze Again, Retry Analysis, and Clear Result.
- Reanalysis keeps the previous valid screen answer visible while the new capture/generation runs.
- Reanalysis failure preserves the previous valid screen answer and shows a screen-owned error.

Root cause:

- The toolbar click path mixed navigation and execution by calling the generic `analyze-screen` action from tab selection.
- Screen generation and failure paths cleared screen answer state too early, so reanalysis could blank a valid previous result.

Files changed:

- `frontend/src/screen_mode_state.js`
- `frontend/src/screen_mode_state.test.js`
- `frontend/src/components/OverlayWindow.jsx`
- `frontend/src/components/AnswerPanel.jsx`
- `frontend/src/App.jsx`

Validation:

- Focused frontend tests: `15 passed`.
- Frontend build: passed.
- Electron syntax checks: `frontend/electron/main.cjs` passed, `frontend/electron/preload.cjs` passed.

Known limitations:

- Manual Electron sequences A-F still need a desktop pass to confirm request-count evidence from the live capture path.
- No backend, model, OCR, provider, Problem 1, or Problem 2 behavior was changed.

---

## Analyze Screen OpenAI Nano Vision Migration - 2026-07-17

Scope:

- Migrated the configured primary Analyze Screen vision provider from OpenRouter Gemma to backend-only OpenAI Responses API vision.
- New primary screen model: `gpt-5-nano-2025-08-07`.
- New configured screen fallback model: `gpt-5.4-nano-2026-03-17`.
- Preserved OpenRouter and Groq compatibility paths for rollback/configuration.
- Preserved RapidOCR as local OCR prepass and final fallback.
- Preserved Electron capture, Analyze Screen persistent-result state, final answer generation, Problem 1, Problem 2, audio, overlay, and UI behavior.

Provider behavior:

- Normal OpenAI screen path uses one full-window cloud vision call.
- The old crop-plus-full double-cloud behavior is skipped for `SCREEN_VISION_PROVIDER=openai`.
- GPT-5.4 nano fallback runs only for controlled primary failures such as low confidence, malformed JSON, missing MCQ options, incomplete coding extraction, empty output, timeout, rate limit, auth/permission error, model access error, or server/network failure.
- RapidOCR final fallback runs when cloud extraction is unavailable or unusable.
- Conservative local OCR short-circuit may skip cloud only for simple high-confidence text questions; visual, coding, MCQ, debugging, output, and architecture cases still use cloud vision.

Configuration:

- `SCREEN_VISION_PROVIDER=openai`
- `SCREEN_VISION_MODEL=gpt-5-nano-2025-08-07`
- `SCREEN_VISION_FALLBACK_MODEL=gpt-5.4-nano-2026-03-17`
- `ENABLE_SCREEN_VISION_FALLBACK=true`
- `ENABLE_LOCAL_OCR_PREPASS=true`
- `ENABLE_LOCAL_OCR_SHORT_CIRCUIT=true`
- `ENABLE_RAPIDOCR_FALLBACK=true`
- Rollback options: `SCREEN_VISION_PROVIDER=openrouter` or `SCREEN_VISION_PROVIDER=groq`.

Files changed:

- `backend/app/config.py`
- `backend/app/services/screen_vision_service.py`
- `backend/app/api/screen_ocr.py`
- `backend/tests/test_screen_vision_openai.py`
- `backend/tests/test_screen_vision_openrouter.py`
- `.env.example`

Validation:

- Backend compile passed: `python -m compileall -q backend/app`.
- Focused screen-vision tests passed: `29 passed`, `5 warnings`.
- Full backend tests passed: `196 passed`, `5 warnings`.
- Frontend build passed: `npm run build`.
- Electron syntax checks passed: `node --check frontend/electron/main.cjs` and `node --check frontend/electron/preload.cjs`.

Known limitations:

- Live Analyze Screen scenarios still need a desktop pass against real screenshots.
- Live provider latency and real screenshot accuracy require an `OPENAI_API_KEY` configured in the backend environment.
- No screenshots, image base64, API keys, prompts, or private OCR payloads are logged by default.

---

## C0.9.2 One-Click OCR Stabilization - 2026-07-24

Change:

- Replaced the active Analyze Screen OCR path with a locked one-click flow: OCR -> one active-window screenshot -> one direct screen-model request -> final answer.
- Removed the active path's duplicate work: no sequence capture, no multi-image loop, no extracted-text merge, no platform enrichment, no preview/edit step, and no second `/generate` request after extraction.
- Added `/api/screen/analyze-active-window-answer` for the direct screenshot-to-answer flow while preserving the older extraction endpoint for compatibility.
- Analyze Screen UI now shows passive status/final answer only; Try OCR Again and Use Extension remain explicit user actions.
- Previous valid screen answers are preserved on unreadable/failure paths.
- Successful OCR creates one Analyze Screen history entry; failed/cancelled OCR creates none.
- Stabilization patch: the direct screen prompt now solves MCQs independently of checked/highlighted/hover/focus/submitted UI state, answers all fully visible independent quiz/MCQ/general questions in top-to-bottom order from one screenshot and one screen-model request, skips incomplete cut-off questions, and keeps coding pages to the single dominant complete coding problem.
- Added safe OCR timing/count metadata for image preparation, upload, screen-model latency, response parse, overlay render, screenshot count, screen-model request count, questions answered, incomplete questions ignored, automatic fallback count, and correction count.
- UI stabilization patch: Analyze Screen result controls are contextual. Non-code results show only Analyze Screen and Extension. Copy Code appears only when valid formatted code exists. Copy Answer, Clear Result, Analyze Again, and Try OCR Again were removed from the Analyze Screen result action row. Answer and Chat controls remain unchanged.
- C0.9.3 is complete.

Validation:

- `python -m compileall -q backend/app` passed.
- `PYTHONPATH=backend pytest -q backend/tests` passed: 281 tests.
- `node --test frontend/src/*.test.js` passed: 43 tests.
- `npm run build` passed.
- `node --check frontend/electron/main.cjs` passed.
- `node --check frontend/electron/preload.cjs` passed.

Known limitations:

- Manual Electron OCR validation is complete for live screenshot count, screen-model request count, multi-question MCQ order/count behavior, incomplete-question ignoring, MCQ selection-marker independence, coding-page dominance, Stop cancellation, unreadable-screenshot handling, measured time to answer, contextual result controls, and overlay resize/status behavior.

---

## In-Session Question and Answer History Navigation - 2026-07-18

Change:

- Added bounded in-memory question history for Answer mode and Analyze Screen mode.
- Added compact Previous/Next controls in the floating Answer panel question header.
- New completed Answer and Analyze Screen results are appended and selected automatically.
- Navigating history restores saved question, answer, and safe metadata without calling transcription, capture, classification, generation, validation, correction, or variation.
- Chat remains separate from this Q/A history.

Validation:

- Focused frontend tests passed: `13 passed`.
- `npm run build`: passed.
- `node --check frontend/electron/main.cjs`: passed.
- `node --check frontend/electron/preload.cjs`: passed.

Known limitations:

- History is current-session memory only and is not written to disk or cloud storage.
- Manual Electron click-through validation is still recommended for final acceptance.

---

## C0.x - Live Follow-Up Question Resolution - 2026-07-18

Status: implemented with automated validation; live manual scenarios pending.

Audit findings:

- The frontend submits all live questions through the existing generation path.
- The backend builds the Answer Plan from the submitted question before context routing.
- Per-mode in-memory history now provides a safe recent-context source for Answer and Analyze Screen.
- History navigation does not call generation, so it is not a resolver trigger.

Architecture:

- Follow-up resolution runs before Answer Planner and before context retrieval.
- The resolver is deterministic, backend-owned, same-mode only, bounded to recent context, and memory-only.
- The original question remains visible; the resolved standalone question is used internally for planning and generation.
- Ambiguous or context-free follow-ups return a clarification through the existing answer response path without calling a model.
- Rollback: set `ENABLE_LIVE_FOLLOWUP_RESOLUTION=false`.

Files changed:

- `backend/app/nlp/followup_resolver.py`
- `backend/app/api/generate.py`
- `backend/app/config.py`
- `backend/tests/test_live_followup_resolver.py`
- `backend/tests/test_answer_streaming.py`
- `frontend/src/App.jsx`
- `frontend/src/question_history.js`
- `frontend/src/question_history.test.js`
- `.env.example`
- `SAIIA_PRODUCTION_PRD_CORE.md`
- `SAIIA_PRODUCTION_TECHSTACK.md`
- `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`

Deterministic patterns:

- Pronoun follow-ups such as `its`, `it`, `that`, and `they`.
- Property follow-ups such as examples, benefits, disadvantages, limitations, and challenges.
- Comparison follow-ups such as authentication versus authorization.
- Coding follow-ups such as optimization and time complexity.
- Project, behavioral, personal, and practical scenario continuations.

Validation:

- Backend compile passed: `python -m compileall -q backend/app`.
- Focused follow-up/backend streaming tests passed: `14 passed`, `5 warnings`.
- Frontend question-history tests passed: `8 passed`.

Known limitations:

- Deterministic resolution is intentionally conservative and may ask clarification instead of guessing.
- Model-assisted resolution remains disabled.
- Live microphone, screen, and coding follow-up scenarios still need desktop validation.

---

## C0.x - Question Detection, Coding Answer Contract, and Toolbar Stop - 2026-07-18

Status: implemented with automated validation; live Electron regression pass pending.

Change:

- Question detection now accepts definition/explanation phrases such as `what do you mean by authentication`, `what is meant by dependency injection`, `what does polymorphism mean`, and filler-prefixed variants.
- Incomplete/noise prompts such as `explain`, `define`, `describe`, and `what do you mean by` remain rejected.
- Manual coding implementation requests now enter the existing coding Answer Plan path.
- Coding prompts now require the requested programming language, concise approach, fenced code, useful comments, time complexity, and space complexity.
- The floating toolbar now includes a red circular Stop button between Chat and the timer.
- Stop uses existing cancellation state and does not clear the current answer like End Session.

Files changed:

- `backend/app/api/question_detect.py`
- `backend/app/nlp/classifier.py`
- `backend/app/nlp/answer_planner.py`
- `backend/app/api/generate.py`
- `backend/app/nlp/coding_quality_gate.py`
- `backend/app/nlp/answer_generator.py`
- `frontend/src/App.jsx`
- `frontend/src/components/OverlayWindow.jsx`
- `frontend/src/components/AnswerPanel.jsx`
- `frontend/src/styles/glass.css`
- `backend/tests/test_definition_question_detection.py`
- `backend/tests/test_coding_implementation_intent.py`
- `frontend/src/toolbar_stop_button.test.js`

Validation:

- Backend compile passed: `python -m compileall -q backend/app`.
- Focused backend tests passed: `26 passed`, `5 warnings`.
- Nearby backend regression tests passed: `145 passed`, `5 warnings`.
- Full backend tests passed: `235 passed`, `5 warnings`.
- Frontend tests passed: `26 passed`.
- `npm run build`: passed.
- `node --check frontend/electron/main.cjs`: passed.
- `node --check frontend/electron/preload.cjs`: passed.

Known limitations:

- Non-Python coding answers are prompted and rendered with the requested language, but the existing judge/sample runner remains Python-only and is skipped for non-Python requests.
- Manual Electron validation is still required for final acceptance of the Stop button during live microphone/system/screen operations.

---

## C0.x - Follow-Up Intent Compiler and Structured Coding Continuations - 2026-07-19

Scope:

- Fix vague same-session follow-ups such as `Can you write a program of it?` after `What is an array?`.
- Preserve the interviewer's original wording in history and overlay while compiling a clearer internal task for classification, planning, and generation.
- Reuse the existing follow-up resolver, Answer Planner, OpenAI/Groq provider routing, streaming path, request IDs, and per-mode history.
- Add structured coding-answer metadata so code can render independently of malformed Markdown fences.

Implementation notes:

- Added deterministic follow-up intent compilation with requested action, requested output, resolved language, platform mode, referenced topic, confidence, and timing metadata.
- Concept-to-code follow-ups now compile into explicit standalone demo tasks such as a Python array program with no stdin contract, instead of the previous weak `in the context of array` phrasing.
- Coding continuations can distinguish implementation, optimization, language conversion, complexity analysis, and explanation requests.
- The backend returns optional `coding_answer` structure while preserving existing `answer` response fields.
- The floating overlay renders structured code through the existing highlighted code path after streaming completes.

Validation:

- Focused backend follow-up/coding/resolver tests passed: `26 passed`, `5 warnings`.
- Full backend tests passed: `243 passed`, `5 warnings`.
- Frontend tests passed: `28 passed`.
- Backend compile passed: `python -m compileall -q backend/app`.
- Frontend build passed: `npm run build`.
- Electron syntax checks passed for `frontend/electron/main.cjs` and `frontend/electron/preload.cjs`.

Known limitations:

- Manual Electron validation of the exact array follow-up flow is still pending.
- Existing Python sample/code validation remains Python-specific; structured rendering supports non-Python code display but does not add a new non-Python judge.

### Execution Mode

```text
Current build track: Production Core Edition
Primary references: SAIIA_PRODUCTION_PRD_CORE.md + SAIIA_PRODUCTION_TECHSTACK.md
Tracker policy: update this file after every completed phase
```

---

# Codex Working Rules

Codex must follow these rules:

1. Do not break the completed MVP.
2. Do not rewrite the app from scratch.
3. Do not rename SAIIA to Dhiti.
4. Do not turn SAIIA into a generic document Q&A assistant.
5. Do not add billing/licensing before product features are stable.
6. Do not put API keys in frontend/Electron.
7. Do not commit `.env`, resumes, audio, screenshots, logs, or profile data.
8. Keep changes small and testable.
9. Update this tracker after every phase.
10. Run validation after changes.
11. Keep Manual Mode working even after Auto Listen Mode is added.
12. Keep Groq fast path working even after NVIDIA is added.
13. Keep Screen Reading user-triggered and permission-based.
14. Keep auth/billing/license as future modular layer until PRD B implementation.

---

# Final Product Acceptance

SAIIA should be considered production-ready when:

- resume upload works
- resume extraction works
- resume RAG grounds answers
- job description context works
- manual audio mode works
- auto listen mode works
- screen reading works
- Groq fast answers work
- NVIDIA refinement works
- overlay is polished
- settings are complete
- app is packaged
- QA passes
- privacy rules are clear
- future commercial protection can be added without rewrite

---

### C0 - Streaming Internal Metadata Sanitization - 2026-07-22

SAIIA now treats category/type/mode/intent markers as internal metadata only.
The answer-generation contract no longer asks the model to emit
`[[category:...]]`, and the backend streaming route runs every answer delta
through a bounded chunk-safe sanitizer before sending it to the overlay.

Regression scope:

- Category remains available through structured metadata/status UI fields.
- Split control markers are removed before visible streaming.
- Matrix indexing, nested arrays, code blocks, and unknown bracketed text are
  preserved.
- History stores clean answers plus a separate category field.
- Request ID, cancellation, stale-response, Previous/Next, Regenerate, Chat,
  Analyze Screen, and non-streamed fallback paths remain protocol-compatible.

Rollback:

- Revert `backend/app/nlp/internal_marker_sanitizer.py`, the stream wiring in
  `backend/app/api/generate.py`, the prompt contract edits in
  `backend/app/nlp/answer_generator.py`, and the frontend fallback/history
  cleanup changes. Then rerun focused streaming/history tests.

