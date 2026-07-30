# TECHSTACK: SAIIA Production-Ready Architecture

**Product:** SAIIA — Smart AI Interview Assistant  
**Scope:** Production stack for both PRD A Core Edition and PRD B Protected Commercial Edition  
**Version:** 1.1

**Last updated:** 2026-07-24  
---

## 1. Purpose

This file locks the recommended production stack for SAIIA.

It supports two product paths:

1. **Core Edition:** full production app without auth/billing/licensing.
2. **Protected Commercial Edition:** full production app with auth, subscriptions, usage limits, device activation, and license protection.

The stack must keep SAIIA modular so the commercial layer can be added later without rewriting the core app.

---

## 2. Architecture Rule

The desktop app is the client. The backend owns valuable logic.

```text
Electron/React Desktop App
        ↓
FastAPI Backend
        ↓
Services:
- transcription
- classification
- resume extraction
- RAG
- Screen Intelligence OCR and Extension extraction
- model routing
- answer generation
- future auth/billing/license checks
```

Do not put API keys or paid logic inside Electron/React.

---

## 3. Locked Core Stack

| Layer | Technology | Status |
|---|---|---|
| Desktop app | Electron | Keep |
| Frontend | React + Vite | Keep |
| Backend | FastAPI | Keep |
| Language | Python + JavaScript | Keep |
| STT | Whisper / faster-whisper | Use |
| Audio dependency | ffmpeg | Required |
| Fast LLM | Groq | Primary |
| Deep/refinement LLM | NVIDIA DeepSeek V4 Pro via NVIDIA NIM/OpenAI-compatible API | Add later |
| Local fallback | Ollama | Optional fallback |
| Resume extraction | PyMuPDF / python-docx / plain text parser | Add |
| OCR / vision | Current configured screen vision/OCR path with local OCR support/fallback | Keep and extend in C0.9 |
| RAG | ChromaDB or local vector store | Add |
| Embeddings | sentence-transformers or provider embeddings | Add |
| Local storage | JSON/SQLite initially | Upgrade |
| Production DB | PostgreSQL | PRD B |
| Auth | JWT access/refresh tokens | PRD B |
| Payments | Razorpay or Stripe | PRD B |
| Packaging | electron-builder | Add |
| Updates | electron-updater | Add |
| Testing | pytest + frontend build checks | Improve |

---

## 4. Frontend Stack

Use:

- React
- Vite
- Electron renderer
- existing CSS or lightweight CSS modules

Avoid unless necessary:

- Next.js migration
- Redux
- heavy animation libraries
- complex dashboard frameworks

Recommended structure:

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
    auth/       # PRD B
    billing/    # PRD B
    usage/      # PRD B
    license/    # PRD B
  services/
    apiClient.js
    interviewApi.js
    profileApi.js
    resumeApi.js
    ragApi.js
    screenApi.js
    providerApi.js
    authClient.js      # PRD B
    billingClient.js   # PRD B
```

---

## 5. Electron Stack

Use:

- Electron main process
- Electron preload bridge
- separate overlay BrowserWindow
- IPC state sync
- globalShortcut for Ctrl+H
- desktopCapturer for user-approved screen capture

Overlay requirements:

- always-on-top
- draggable
- Ctrl+H hide/show
- Show/Hide button sync
- font-size control
- position persistence
- compact mode
- refined answer display

Packaging later:

- electron-builder
- ASAR packaging
- signed Windows installer
- auto-update

---

## 6. Backend Stack

Use:

- FastAPI
- Pydantic
- Uvicorn
- python-dotenv
- httpx
- pytest

Live follow-up resolution:

- Implemented as deterministic Python logic in the backend.
- Uses existing in-memory per-mode question history supplied by the desktop client.
- Adds a deterministic follow-up intent compiler before Answer Planner execution so vague continuations become explicit internal tasks without changing the displayed interviewer wording.
- Carries safe structured metadata only: reference status/topic, requested action/output, resolved language, platform mode, context count, confidence, and timing.
- Uses no new external dependency, database, embeddings, vector store, provider, or model.
- Optional model-assisted resolution is configured off by default and is not part of the active C0 path.

Recommended structure:

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
    auth.py             # PRD B
    subscription.py     # PRD B
    usage.py            # PRD B
    license.py          # PRD B
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
    auth_service.py           # PRD B
    subscription_service.py   # PRD B
    usage_service.py          # PRD B
    license_service.py        # PRD B
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
    security.py          # PRD B
    permissions.py       # PRD B
  storage/
    profile_store.py
    resume_store.py
    session_store.py
    vector_store.py
  db/
    database.py          # PRD B / production
    models/
    migrations/
```

---

## 7. Provider Stack

Provider configuration remains backend-owned. Do not put API keys or paid model logic inside Electron, React, or the browser extension.

Current-state note from project records:

- final answers currently use the configured backend answer provider
- current records show OpenAI Responses API through `OPENAI_MODEL` as the active final-answer path
- Groq is available as emergency/rollback fallback where enabled
- Analyze Screen uses the configured backend vision provider with local OCR support/fallback
- Auto Mode uses the configured STT/streaming provider
- C0.9 must reuse existing provider services
- C0.9 must not migrate or replace final-answer, STT, or vision models

Environment variables and provider choices must not be changed during the C0.9 documentation or Extension foundation work unless a separate provider task approves it.

Historical Groq, NVIDIA, Ollama, OpenRouter, and OpenAI validation records remain preserved in the roadmap and tracker.

---
## 8. Provider Routing Strategy

Product flow should use provider-neutral wording unless a provider is explicitly required:

```text
Input
  -> configured production STT or extraction provider
  -> classification
  -> configured primary answer provider
  -> configured fallback when enabled
  -> overlay
```

Provider routing, fallback, and feature gates remain backend responsibilities.

---
## 9. Resume Extraction Stack

PDF:

- PyMuPDF (`pymupdf`) first
- pdfplumber as alternative

DOCX:

- python-docx

TXT:

- native Python text reading

Scanned PDF:

- detect low text
- show useful error first
- OCR fallback where configured

---

## 10. RAG Stack

Recommended first version:

- ChromaDB local
- sentence-transformers embeddings
- SQLite/JSON metadata

Alternative lightweight version:

- chunked JSON store
- simple embedding index
- SQLite metadata

RAG scope:

- resume grounding
- job description grounding
- interview session context

Do not build a general document Q&A assistant.

---

## 11. Extension and DOM Extraction Stack

Planned stack for the user-facing Extension action:

- Manifest V3
- Google Chrome and Microsoft Edge as initial official browser targets
- one Chromium extension codebase where practical
- extension service worker
- content script or injected extractor only after the Electron-triggered Extension action
- `chrome.scripting` / equivalent Chromium scripting API where required
- tabs access only where required
- browser host access granted by the user during setup or pairing
- connected extension service worker
- Electron-to-extension `extract_active_tab` command
- generic DOM extractor
- semantic heading parser
- candidate container scorer
- visible-element filter
- MathJax/KaTeX/MathML recovery where practical
- Monaco/CodeMirror/Ace detection where accessible
- strict message schemas
- Extraction Result Envelope schema validation
- localhost-only authenticated local bridge for prototype
- Native Messaging for production
- no API keys in the extension
- no complete raw HTML upload

This architecture does not rely only on temporary `activeTab` permission granted by clicking the browser extension icon. Automatic extraction initiated from Electron requires previously granted page access after setup or pairing. Exact Manifest permission patterns are an implementation decision to verify during C0.9.5.

C0.9.5 implementation note: the standalone prototype uses Manifest V3 with `scripting` and `storage`, optional `http://*/*` and `https://*/*` host permissions requested by explicit user gesture, no `tabs` permission, no static content scripts, no Electron/backend bridge, and a development-only popup action for controlled active-tab extraction testing. Chrome/Edge browser UI validation passed.

C0.9.6 implementation note: the generic active-tab extractor is scoped to coding pages only. It performs on-demand local DOM inspection, generic coding-region scoring, split coding workspace handling, nested/duplicate candidate collapse, semantic section extraction, problem-title ranking, sample/example metadata preservation in the shared `examples` array, example/format separation, coding-only scope classification, bounded DOM readiness, generic code/option/visual-context extraction, accessible Monaco/Ace/CodeMirror/textarea/contenteditable starter-code extraction, independent editor-present/code-available evidence, and safe development diagnostics. MCQs, code-based MCQs, output-prediction, technical/general, visual/chart/diagram, tutorial/article, and editor-only pages return controlled unsupported results that recommend OCR. It remains platform-agnostic, treats input/output/constraints/examples as optional for coding extraction, adds no Electron bridge, makes no backend/provider/network calls, and persists no extracted page content. Chrome/Edge real-page validation remains pending.

The primary extractor must be generic. Platform-specific adapters may be added later only as optional accuracy improvements and must not be required for the core extractor to function.

Prototype communication:

```text
Electron Analyze Screen -> Extension
-> localhost-only authenticated bridge
-> paired extension
-> extract_active_tab
-> Extraction Result Envelope
-> normalized question pipeline
```

Production communication:

```text
Electron Analyze Screen -> Extension
-> Electron main process
-> Native Messaging host
-> extension service worker
-> active-tab extraction in the paired supported browser
-> authenticated FastAPI backend
-> answer pipeline
-> overlay
-> cloud session storage when enabled
```

The content script must not communicate directly with the native application. Native Messaging is planned for production and is not implemented by this documentation task. Production Native Messaging configuration must allow the exact approved extension IDs for each supported browser/store build.

Open implementation decisions include exact Chrome extension ID, Edge extension ID, Manifest host-permission pattern, whether host permission is broad at install or requested during pairing, exact local bridge implementation, bridge port, bridge owner, pairing-token format, preferred-browser setup UI, reconnect mechanism, and browser-extension publication phase.
## 12. OCR and Screen Intelligence Stack

Electron capture:

- Electron `desktopCapturer`
- user-approved screen/window/region selection
- screenshot capture
- no continuous hidden capture
- no screenshot persistence by default

Vision/OCR path:

- vision/layout detection
- OCR text extraction
- one-click OCR direct structured batch response for fully visible independent questions
- one screenshot and one screen-model request in the normal C0.9.2 OCR path
- normalized common contract
- OCR can process coding fallback

For C0.9.2 one-click OCR, the backend may extend the screen response with backward-compatible `result_mode`, `items`, `question_count`, and `incomplete_question_count` fields without changing the one-screenshot, one-screen-model-request path. C0.9.3 adds the common Extraction Result Envelope and Normalized Question schema around that response. C0.9.4 routes OCR and the temporary Extension-unavailable path through source-owned `operation_id`, `request_id`, and `source_type` metadata so stale, cancelled, superseded, or duplicate screen results cannot create history or overwrite newer Screen state.

Recommended planned project structure:

```text
browser-extension/
  manifest.json
  service-worker.js
  content-script.js
  extractors/
    generic-coding-extractor.js
    candidate-container-scorer.js
    semantic-section-extractor.js
    sample-extractor.js
    code-editor-extractor.js
    math-recovery.js
    language-detector.js
    extraction-validator.js
  schemas/
    normalized-problem-schema.js
  tests/

backend/app/
  services/
    screen_intelligence_orchestrator.py
    analysis_source_router_service.py
    coding_language_resolver.py
    normalized_question_service.py
    multiple_question_detector_service.py
  models/
    screen_intelligence.py
```

These are planned names, not mandatory implementation paths. Codex must audit the real repository before implementing and reuse equivalent existing services when present.

Dependency rule:

- Do not add a new package when existing browser APIs and current project libraries are sufficient.
- Do not add a platform-specific scraping SDK as the core architecture.
## 13. Auto Listen Stack

Use:

- browser/electron audio stream
- VAD
- silence detection
- max segment duration
- duplicate question filter
- cooldown window
- question detector

Possible VAD options:

- WebRTC VAD
- Silero VAD
- simple RMS threshold first

Start simple. Do not break manual mode.

---

## 14. Storage Stack

Core Edition:

- JSON for simple config
- SQLite for sessions/profile/resume metadata
- local vector index for resume RAG

Protected Commercial Edition:

- PostgreSQL
- SQLAlchemy
- Alembic migrations
- optional Redis for cache/rate limits later

---

## 15. Auth/Billing/License Stack — PRD B Only

Auth:

- JWT access token
- refresh token
- passlib/bcrypt or argon2
- secure Electron token storage

Payments:

- Razorpay for India-first launch
- Stripe for global launch
- Paddle/Lemon Squeezy as merchant-of-record option

Device license:

- device ID hash
- devices table
- device limit by plan
- device validation endpoint

Installer protection:

- electron-builder
- code signing certificate
- electron-updater
- ASAR packaging
- minification
- basic obfuscation
- integrity checks

---

## 16. Environment Variables

Core:

```env
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

STT_PROVIDER=whisper
WHISPER_MODEL=tiny.en
FFMPEG_PATH=

LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=20

ENABLE_NVIDIA_REFINEMENT=false
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro
NVIDIA_TIMEOUT_SECONDS=45
ENABLE_PARALLEL_REFINEMENT=false
ENABLE_ROUTER_MODE=false

ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_TIMEOUT_SECONDS=60

USE_ZERO_SHOT_CLASSIFIER=false
LOG_LEVEL=INFO
```

PRD B:

```env
JWT_SECRET=
ACCESS_TOKEN_MINUTES=30
REFRESH_TOKEN_DAYS=30
DATABASE_URL=
ENCRYPTION_SECRET=

PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

ENABLE_DEVICE_LICENSE=true
```

---

## 17. Testing Stack

Backend:

- pytest
- FastAPI TestClient
- provider mock tests
- resume parser tests
- RAG retrieval tests
- auth permission tests for PRD B
- payment webhook tests for PRD B

Frontend:

- npm run build
- manual Electron QA
- optional Vitest later

Manual QA:

- profile setup
- resume upload
- resume extraction
- RAG grounding
- manual recording
- auto listen
- screen read
- Groq generation
- NVIDIA refinement
- Ollama fallback
- overlay controls
- error handling

---

## 18. Security Rules

Always:

- keep API keys in backend/server
- never commit `.env`
- never commit resume/audio/screenshot files
- avoid logging full resume/profile
- avoid storing temp audio/screenshots longer than needed
- backend must enforce future permissions
- use honest privacy wording

---

## 19. Recommended Build Order

```text
1. Clean baseline
2. Resume upload and extraction
3. Resume RAG
4. Job description context
5. Multi-model Groq + NVIDIA strategy
6. Current OCR baseline
7. Overlay polish
8. Main UI polish
9. Auto Listen Mode
10. Better audio capture
11. Screen Intelligence OCR/Extension source selection and Extension foundation
12. Settings and history
13. Packaging
14. QA and reliability
15. Auth
16. Usage tracking
17. Subscription plans
18. Payments
19. Device licensing
20. Code signing and auto-update
```

---

## 20. Final Stack Rule

Use boring, reliable tools first.

Only add a technology if it directly supports:

```text
understand candidate
understand question
generate grounded answer
show it quickly in overlay
protect paid value later
```
