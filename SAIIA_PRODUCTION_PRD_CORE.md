# PRD A: SAIIA Production-Ready Product — Core Edition

**Product:** SAIIA — Smart AI Interview Assistant  
**PRD Type:** Production-ready product PRD without auth, billing, subscription, licensing, and anti-crack enforcement  
**Version:** 1.1  
**Last updated:** 2026-07-24  
**Status:** Post-MVP roadmap document

> This PRD keeps the system future-ready for commercial protection, but does not implement login, payment, usage limits, device licensing, or anti-crack systems yet.

---

## 1. Product Definition

SAIIA is a desktop AI interview assistant that helps candidates answer interview questions in real time. It listens to spoken questions, reads user-approved screen content when needed, understands the user from resume/profile/job context, generates concise answer suggestions using fast and deep AI models, and displays answers in a private Electron overlay.

SAIIA is not Dhiti, not a generic document Q&A assistant, not a generic chatbot, and not primarily a mock interview report system.

---

## 2. One-Line Product Statement

SAIIA helps candidates answer virtual interview questions in real time using audio, screen reading, resume grounding, model routing, and a private desktop overlay.

---

## 3. Target Users

Primary users:

- Students and freshers
- Early-career developers
- Job candidates
- Career switchers
- Candidates preparing for HR, technical, behavioral, coding, and system-design interviews

---

## 4. Product Goals

1. Generate fast, natural, interview-ready answers.
2. Personalize answers using resume, profile, target role, company, and job description.
3. Support manual audio input, auto-listen input, and source-selectable Screen Intelligence input.
4. Use Groq for instant live answers.
5. Use NVIDIA DeepSeek as a deeper backup/refinement or routed model.
6. Keep Ollama as optional local fallback.
7. Use resume RAG to reduce generic/hallucinated answers.
8. Provide a polished Electron overlay and main control panel.
9. Keep the architecture modular so commercial auth/billing/licensing can be added later without rewriting the app.
10. Provide an Analyze Screen source menu with exactly two visible actions: OCR and Extension.
11. Prefer one-click Extension DOM extraction for accessible coding webpages while preserving OCR as a screen capture/vision fallback.
12. For one-click OCR quiz/batch screenshots, answer all fully visible independent questions from one screenshot and one screen-model request, in top-to-bottom order, with no user question-selection step.

---

## 5. Non-Goals for This PRD

### 5.1 Commercial Features Deferred to PRD B

This PRD does not include:

- user login
- pricing/subscription plans
- payment integration
- usage limits
- license/device activation
- anti-crack enforcement
- commercial administration
- institution administration

Internal admin/support console planning is tracked as future phase C15.5 after privacy/export/retention/deletion rules are defined. It is not part of the normal candidate dashboard. Institution or commercial administration remains future/expanded scope unless separately approved.

Those commercial features belong to PRD B or later explicitly approved internal-admin scope.

### 5.2 Permanent Screen Intelligence Non-Goals

SAIIA must not support or claim:

- continuous hidden browser reading
- continuous hidden screen capture
- unrelated-tab reading
- arbitrary full-page scraping
- cookie/token extraction
- hidden test-case extraction
- hidden solution extraction
- parallel or per-question "Solve All" workflows
- solving incomplete, hidden, or partially visible questions
- silent source fallback
- universal browser support claims
- universal platform support claims

These are privacy, security, and product-boundary non-goals. They do not belong to PRD B.

---
## 6. Core Product Flows

### 6.1 Manual Audio Flow

```text
Profile setup
  -> Start recording
  -> configured production STT
  -> Question classification
  -> Resume/JD context retrieval
  -> configured primary answer provider
  -> configured fallback when enabled
  -> Electron overlay display
```

Final answers currently use the configured backend answer provider. Current project records show OpenAI Responses API through `OPENAI_MODEL` as the active final-answer path, with Groq available as emergency/rollback fallback where enabled. C0.9 must reuse existing provider services and must not migrate or replace final-answer, STT, or vision models.
### 6.2 Auto Listen Flow

```text
Enable Auto Listen
  → Voice Activity Detection
  → Silence detection
  → Transcription
  → Question detection
  → Duplicate filtering
  → Classification
  → Answer generation
  → Overlay update
```

### 6.3 Analyze Screen Flow

```text
Analyze Screen
  -> choose OCR or Extension
  -> selected extraction path
  -> OCR direct result or future Extraction Result Envelope
  -> one visible answer result
  -> classification
  -> resume/JD context
  -> answer generation
  -> overlay
```

Analyze Screen must open a source-selection menu with exactly two visible actions: OCR and Extension. Opening the menu must not capture the screen, take a screenshot, contact the extension for extraction, query the active tab, inject a content script, start OCR, start answer generation, clear the existing answer, create an extraction operation, or create a history entry.

The menu may display cached last-known status such as Extension connected, Extension disconnected, or Paired browser: Microsoft Edge. A status refresh may check connection health only; it must not query page content, inject the extractor, extract content, or start generation.

OCR reads user-approved visible screen content using screen capture, vision, and OCR. Extension reads the coding problem automatically from the active tab in the paired browser. There is no third Browser Page selection, no normal-flow tab picker, no URL paste step, and no required browser-extension icon click for every extraction.

For C0.9.2 one-click OCR, quiz/MCQ/aptitude screenshots with multiple fully visible independent questions must use one screenshot, one screen-model request, and one structured batch response containing all complete answers in top-to-bottom order. Incomplete question blocks are ignored. Coding screenshots still solve the single dominant complete coding problem. Future Extension and C0.9.3 contracts are defined in `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`.
### 6.4 Live Follow-Up Question Resolution

SAIIA must support bounded, in-memory follow-up resolution during the current desktop interview session.

Requirements:

- Preserve the interviewer's original wording for display.
- Resolve incomplete follow-ups into standalone internal questions before Answer Planner execution.
- Compile follow-up intent before planning so action changes such as `write a program of it`, `optimize it`, `convert it to Java`, `what is the time complexity`, or `explain this part` become explicit internal tasks.
- Keep the original interviewer wording visible in the UI while using the compiled task only for classification, planning, and generation.
- For concept-to-code follow-ups, preserve the referenced concept and produce a structured coding task with language, platform mode, and inherited constraints.
- Use only recent same-mode context: Answer uses Answer history, Analyze Screen uses Screen history, and Chat remains isolated.
- Prefer deterministic local resolution for pronouns, continuation phrases, comparisons, coding follow-ups, project follow-ups, behavioral follow-ups, and practical scenario follow-ups.
- Ask a concise clarification when no same-mode context exists or the reference is ambiguous.
- Preserve existing Context Policy Router behavior; resolution supplies meaning, not permission to use resume or job context.
- Keep follow-up context bounded and memory-only.
- Do not use cloud persistence, embeddings, vector stores, saved-session retrieval, or cross-device memory in this C0 feature.

Product invariants:

- Tab switching must not trigger follow-up resolution.
- Previous/Next history navigation must not trigger follow-up resolution or generation.
- Unresolved references must not be guessed.
- Persistent saved-session Ask AI memory remains deferred to C9.

---

## 7. Major Modules

## 7.1 Profile System

Required fields:

- resume/background
- target role
- target company
- skills
- experience/projects
- education
- work experience
- achievements
- preferred answer style

Requirements:

- manual profile editing
- validation before generation
- clear error for missing profile
- generated answers must not invent experience outside the profile/resume

---

## 7.2 Resume Upload and Extraction

Supported files:

- PDF
- DOCX
- TXT

Requirements:

- upload resume
- validate file type and size
- extract text
- detect empty/scanned PDFs
- use Groq to convert raw resume text into structured profile JSON
- show extracted fields for review
- allow user edits before saving
- never commit resume files or extracted profile data to Git

Extracted fields:

- summary
- skills
- technical stack
- education
- projects
- work experience
- certifications
- achievements
- role-fit summary

---

## 7.3 Resume RAG Grounding

Purpose: ground interview answers in the uploaded resume without passing the full resume into every prompt.

Scope rule: RAG is only for resume, job description, and interview context grounding. Do not turn SAIIA into a general document Q&A assistant.

Requirements:

- chunk resume text
- generate embeddings
- store local vector index
- retrieve relevant resume chunks per question
- pass top chunks into answer generation
- fallback to profile fields if retrieval is weak
- avoid logging full resume/profile text

---

## 7.4 Job Description and Company Context

Requirements:

- paste/upload job description
- extract required skills, responsibilities, seniority, and domain keywords
- match resume/profile to job requirements
- use JD context during answer generation

---

## 7.5 Audio Pipeline

Production requirements:

- microphone selector
- audio level meter
- microphone test
- configurable Whisper/faster-whisper model
- ffmpeg availability check
- silence detection
- clear errors for mic permission, empty audio, invalid audio, ffmpeg missing, STT timeout, and no transcript

---

## 7.6 Auto Listen Mode

Manual mode remains default. Auto Listen Mode is an explicit user-enabled feature.

Requirements:

- voice activity detection
- silence threshold
- max segment duration
- question detector
- duplicate question filter
- cooldown window
- pause/resume control

States:

- Listening
- Speech detected
- Processing question
- Ignored non-question
- Answer ready
- Error

---

## 7.7 Screen Intelligence

Use case: interviewer says, "Solve the question shown on screen," or the candidate needs SAIIA to analyze a visible coding/problem prompt.

### Analyze Screen Source Menu

Clicking Analyze Screen must open a menu with exactly two user-facing actions:

- OCR: Read visible screen content using screen capture, vision, and OCR.
- Extension: Read the coding problem automatically from the active tab in the paired browser.

The menu itself must not start capture, extension extraction, answer generation, history creation, or result clearing. Browser Page may be used only as an internal architectural description; it must not appear as an additional user action after clicking Extension.

### OCR

OCR starts only after the user clicks OCR. In C0.9.2 one-click OCR, it creates one operation ID and one request ID, captures one approved active-window screenshot, sends one normal-path screen-model request, detects every fully visible independent question, solves every complete question in that same response, ignores incomplete question blocks, and creates at most one successful Analyze Screen history entry.

OCR can process diagrams, charts, graphs, PDFs, images, MCQs, aptitude questions, technical questions, debugging screenshots, output-prediction questions, system-design prompts, architecture diagrams, coding questions, multiple questions visible at once, meeting screen shares, remote desktops, native desktop applications, and browser pages inaccessible to the extension. OCR is allowed as a coding fallback.

### Extension

Extension starts only after the user clicks Extension. SAIIA immediately asks the paired extension to extract a coding problem from the active tab in the preferred paired supported browser. The user must not be asked to select Browser Page, choose the active tab manually, paste the page URL, click the browser extension icon every time, select Chrome or Edge on every operation, or grant the same permission again on every extraction.

Extension is coding-focused. MCQs, code-based MCQs, output-prediction questions, aptitude questions, technical/general questions, charts, diagrams, images, visual questions, article/tutorial pages, and editor-only pages must use OCR. If the extension sees unsupported content, it returns a controlled unsupported state and recommends OCR. It must not silently start OCR.

The Extension flow is:

```text
Analyze Screen
  -> Extension
  -> check paired extension
  -> extract active tab automatically
  -> generic coding-page DOM extraction
  -> Extraction Result Envelope
  -> Normalized Question
  -> answer generation
```

### Browser Installation and Pairing

The extension is installed and paired once with SAIIA during setup or settings. The user installs the SAIIA extension, grants required browser permission for active-page extraction, pairs the extension with the SAIIA desktop app, and may select a preferred browser. SAIIA stores only safe pairing and browser identity metadata.

No page extraction starts during pairing unless explicitly initiated by the user as a connection test. Normal Extension operations must not require another browser-side click after successful setup. Exact Manifest permission patterns remain an implementation decision for C0.9.5.

### Browser Support

Initial officially supported browsers are Google Chrome and Microsoft Edge. The architecture target is one Chromium Manifest V3 extension codebase where practical.

Potential future browsers such as Brave, Opera, Vivaldi, and other Chromium-based desktop browsers require explicit compatibility testing. SAIIA must not claim universal browser support, Firefox support, or Safari support initially. Each supported browser must be installed, paired, permission-approved, and tested separately before SAIIA lists it as officially supported.

### Multiple Browser Behavior

The user must not select a browser on every extraction. During setup or settings, SAIIA may store a preferred paired browser. Normal Extension behavior uses the preferred paired browser and extracts the active tab from that browser.

If the preferred browser is unavailable, SAIIA must not silently inspect another browser. It should show a reconnect or browser-settings action and preserve the previous valid answer. If several browsers are paired and no preferred browser is resolved, SAIIA must report `browser_ambiguous`, require setup/settings resolution, and avoid per-operation browser picking.

### Fallback Policy

No silent fallback is allowed. If Extension extraction fails, SAIIA must not automatically run OCR. It must show: "The coding problem could not be extracted from the active browser tab." with actions Use OCR and Cancel. OCR begins only after the user clicks Use OCR. OCR must not silently switch to Extension.

### Connection and Error States

Extension states should include `extension_not_installed`, `extension_installed_not_paired`, `extension_connected`, `extension_disconnected`, `browser_not_running`, `browser_ambiguous`, `permission_not_granted`, `permission_revoked`, `requesting_active_tab`, `restricted_url`, `unsupported_page`, `extraction_started`, `extraction_complete`, `extraction_incomplete`, `no_coding_problem_found`, `connection_lost`, `operation_cancelled`, and `stale_result_rejected`.

No error state may silently start OCR.

### Multiple Questions

When one-click OCR sees multiple fully visible independent quiz, MCQ, aptitude, or general questions, SAIIA must not show a selection screen. It must answer all complete questions from the same screenshot and same screen-model request, preserve visible question numbers and top-to-bottom order, ignore partially visible questions, and display the answers together. This is not parallel Solve All and must not create one model call or one history entry per question.

For coding pages, OCR must solve the single dominant complete coding problem and must not treat sample cases, editor fragments, navigation text, or discussion items as separate questions.

### Coding Language and Submission Mode

Coding-language resolution and submission-mode resolution must use the priority and conflict rules defined in `SAIIA_SCREEN_INTELLIGENCE_ARCHITECTURE.md`. SAIIA must not randomly default to Python and must not silently combine conflicting languages or rewrite a visible platform stub without user confirmation or explicit force override.

### User Permission and Privacy

Screen Intelligence must be user-triggered and permission-based. Extension extraction begins only after Analyze Screen -> Extension. SAIIA must not continuously inspect tabs, extract on browser startup, extract on tab change, extract when the Analyze Screen menu opens, read unrelated tabs, read cookies/tokens, extract hidden test cases or hidden solutions, execute page code, upload complete raw HTML, log full private page content by default, send API keys from the extension, or call the AI model directly from the extension.
## 7.8 Question Classification

Supported normalized question types should include:

- coding
- debugging
- output_prediction
- mcq
- diagram
- chart
- architecture
- system_design
- technical
- aptitude
- general
- unknown

During implementation, Codex must audit the real enums and preserve backward compatibility. Where existing names differ, document a compatibility mapping rather than silently renaming production values.

Classifier must be fast and category should influence answer style and model routing.

---
## 7.9 Provider Strategy

Provider identity is a backend configuration concern unless it is explicitly part of a product requirement.

Current-state note:

- final answers currently use the configured backend answer provider
- current records show OpenAI Responses API through `OPENAI_MODEL` as the active final-answer path
- Groq is available as emergency/rollback fallback where enabled
- Analyze Screen uses the configured backend vision provider with local OCR support/fallback
- Auto Mode uses the configured STT/streaming provider
- C0.9 must reuse existing provider services
- C0.9 must not migrate or replace final-answer, STT, or vision models

Default product flow:

```text
Audio or Screen Intelligence input
  -> configured production STT or extraction provider
  -> classification
  -> configured primary answer provider
  -> configured fallback when enabled
  -> overlay
```

Historical provider-validation records must remain preserved in the roadmap and tracker.

---
## 7.10 Answer Generation Rules

Answers must be:

- concise
- speakable
- natural
- personalized
- category-aware
- resume-grounded
- job-target-aware

Answers must not:

- invent fake experience
- overclaim skills
- include meta phrases like “Here is an answer”
- produce long essays
- expose hidden prompt text

---

## 7.11 Electron Overlay

Requirements:

- separate overlay window
- always-on-top where supported
- Ctrl+H hide/show
- Show/Hide button sync
- draggable overlay
- font-size control
- opacity control
- position presets
- compact mode
- loading/error state
- refined-answer area
- persist overlay position/settings

Privacy wording:

```text
Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, a window, or a browser tab.
```

---

## 7.12 Main App UI

Screens:

- Welcome
- Profile setup
- Resume upload
- Job target setup
- Main interview control panel
- Settings
- History
- Troubleshooting

Health indicators:

- backend connected
- Groq configured
- NVIDIA configured
- ffmpeg available
- microphone available
- resume indexed

---

## 7.13 Settings

Sections:

- Profile
- Resume
- Job description
- Audio
- Overlay
- AI providers
- Privacy
- Troubleshooting

---

## 7.14 Session History

Store locally:

- transcript
- category
- generated answer
- refined answer
- provider
- source type: audio/screen/manual
- timestamp
- latency
- retrieved context metadata

User can view, delete, export, or clear session history.

---

## 8. Future-Ready Commercial Hooks

Even though this PRD does not implement auth/billing/licensing, expensive features must be easy to protect later.

Feature keys:

- answer_generation
- transcription
- resume_upload
- resume_rag
- screen_read
- auto_listen
- nvidia_refinement
- session_history

For now, feature gates can be no-op:

```python
def check_feature_access(feature_key: str):
    return True
```

PRD B will replace this with real user, subscription, usage, and device checks.

---

## 9. Recommended Backend Structure

```text
backend/app/
  api/
    transcribe.py
    classify.py
    generate.py
    profile.py
    resume.py
    rag.py
    screen.py
    interview.py
  services/
    audio_service.py
    transcription_service.py
    classifier_service.py
    answer_service.py
    resume_service.py
    rag_service.py
    screen_capture_service.py
    ocr_service.py
    question_detector_service.py
    model_router_service.py
  providers/
    base.py
    groq_provider.py
    nvidia_provider.py
    ollama_provider.py
    provider_factory.py
  core/
    config.py
    logging.py
    errors.py
    feature_gate.py
    privacy.py
  storage/
    profile_store.py
    resume_store.py
    session_store.py
    vector_store.py
```

---

## 10. Recommended Frontend Structure

```text
frontend/src/
  features/
    interview/
    profile/
    resume/
    rag/
    screen/
    overlay/
    settings/
    history/
    providers/
  services/
    apiClient.js
    interviewApi.js
    profileApi.js
    resumeApi.js
    ragApi.js
    screenApi.js
    providerApi.js
```

---

## 11. Acceptance Criteria

SAIIA Core Edition is production-ready when:

- manual audio flow works
- auto listen works
- Analyze Screen menu opens without starting an operation
- Analyze Screen shows only OCR and Extension as visible source actions
- Extension extraction starts after one Extension click and requests active-tab extraction from the paired browser
- no third Browser Page selection exists in the normal user flow
- no manual active-tab picker exists in the normal user flow
- extension setup/pairing and browser permission approval are one-time setup/settings activities
- Chrome and Edge are the initial officially supported browsers
- OCR works with user approval
- OCR remains available for coding fallback
- multiple visible questions use an Extraction Result Envelope and require user selection before answer generation
- Normalized Question includes coding submission mode metadata
- language resolution follows the documented priority rules and handles conflicts safely
- no silent fallback occurs between Extension and OCR
- previous valid Analyze Screen answer survives failed reanalysis, generation failure, cancellation, and stopped operations
- stale Analyze Screen results cannot overwrite newer results
- both Screen Intelligence paths produce the shared Extraction Result Envelope and Normalized Question contracts
- resume upload and extraction work
- resume RAG grounds answers
- job description targeting works
- configured primary answer provider gives answers
- configured fallback works when enabled
- overlay is polished and reliable
- settings and session history work
- app is packaged
- errors are clear
- privacy limitations are honest

These Screen Intelligence requirements are planned requirements, not completed implementation claims.
## 12. Streaming Metadata Rule

Internal metadata must never be rendered as answer content. Category, mode,
type, intent, and answer_type travel as structured metadata/status fields, not
as generated answer text.

Streaming answer deltas must be passed through a chunk-safe internal marker
sanitizer before emission. The sanitizer removes only known control markers
such as `[[category:technical]]`, including split marker chunks, while
preserving normal bracket syntax, code indexing, and nested arrays.

History stores the clean answer plus the separate category field. Stale and
cancelled request protections remain owned by request ID and mode. Rollback:
restore the previous answer prompt contract and remove the sanitizer wiring,
then rerun streaming/history regression tests.

---

## 13. Final Product Rule

Every feature must support:

```text
Understand the candidate → understand the question → generate a grounded answer → show it privately and quickly.
```
