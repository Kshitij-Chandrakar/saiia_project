# TECHSTACK: SAIIA — Smart AI Interview Assistant

## 1. Purpose of This File

This file locks the technical stack for SAIIA so development stays focused and Codex does not introduce unnecessary tools, frameworks, databases, or architectural changes.

SAIIA is a real-time AI interview helper. The user records an interviewer question, the backend transcribes it, classifies it, generates a short personalized answer using the user profile, and the Electron overlay displays the answer.

This file should be treated as the source of truth for MVP technology decisions.

---

## 2. Core Product Rule

If a technology does not directly support this MVP flow, it should not be added:

```text
Profile setup → Start recording → Transcription → Question classification → Groq answer generation → Electron overlay display
```

Avoid adding advanced RAG, admin dashboards, analytics, payment systems, mock interview reports, browser extensions, or unnecessary databases during MVP stabilization.

---

## 3. Locked MVP Stack Summary

| Layer | Chosen Technology | Status |
|---|---|---|
| Desktop shell / overlay | Electron | Keep |
| Frontend | React + Vite | Keep |
| Backend | FastAPI | Keep |
| Backend language | Python | Keep |
| Speech-to-text | Whisper or faster-whisper | Use / stabilize |
| Audio processing dependency | ffmpeg | Required |
| Primary LLM provider | Groq API | Add |
| Primary LLM model | `llama-3.1-8b-instant` | Use first |
| Optional fallback LLM | Ollama + `llama3:8b` | Keep as fallback only |
| Profile storage for MVP | Existing simple profile storage / JSON | Keep unless already implemented differently |
| Database | No new database for MVP unless already present | Avoid scope creep |
| RAG / vector DB | Not required for MVP | Avoid |
| Packaging | Electron-based desktop app | Keep |
| Testing | Pytest for backend, existing frontend build checks | Keep / improve |

---

## 4. Frontend Stack

### 4.1 Framework

Use:

```text
React + Vite
```

Reason:

The existing project already uses React/Vite. Do not migrate to Next.js, Angular, Vue, Remix, or another framework for the MVP.

### 4.2 Frontend Responsibilities

The frontend is responsible for:

- Profile setup UI
- Recording start/stop controls
- Microphone permission handling
- Recording/loading/error states
- Sending audio to backend
- Showing transcript and generated answer where needed
- Communicating with the Electron overlay
- Font-size control for overlay
- Basic settings needed for demo

### 4.3 Frontend Rules

Do not change the frontend architecture unless required to fix a real bug.

Do not redesign the app heavily before the core pipeline works.

Do not introduce new state-management libraries unless there is a strong reason.

Avoid:

- Redux
- Zustand
- Next.js migration
- New design systems
- Unnecessary animation libraries
- Complex dashboard layouts

---

## 5. Desktop / Overlay Stack

### 5.1 Desktop Shell

Use:

```text
Electron
```

Reason:

SAIIA needs a desktop overlay window. Electron already exists in the project and should remain the MVP path.

### 5.2 Overlay Requirements

The Electron overlay must support:

- Separate overlay window
- Always-on-top behavior where supported
- Draggable overlay
- Ctrl+H hide/show hotkey
- Font-size adjustment
- Answer display
- Basic loading/error state

### 5.3 Overlay Privacy Rule

Do not claim that SAIIA is guaranteed invisible during screen sharing.

Safe wording:

```text
The overlay is a separate desktop window and can be hidden with Ctrl+H. Screen-sharing behavior depends on the OS and meeting app. For safest use, share only the interview window or browser tab, not the full desktop.
```

### 5.4 Overlay Scope Limits

Avoid for MVP:

- Browser extension overlay
- Kernel-level capture exclusion
- Screen-share invisibility guarantees
- Advanced stealth features
- Mobile overlay

---

## 6. Backend Stack

### 6.1 Backend Framework

Use:

```text
FastAPI
```

Reason:

The backend already uses FastAPI. It is suitable for audio upload, transcription, classification, answer generation, and structured JSON responses.

### 6.2 Backend Responsibilities

The backend is responsible for:

- Saving and loading user profile data
- Receiving recorded audio
- Validating audio file presence and size
- Converting/normalizing audio format where needed
- Running transcription
- Cleaning transcript text
- Classifying the question
- Calling Groq for answer generation
- Falling back to Ollama if configured
- Returning structured responses
- Logging useful errors without leaking secrets

### 6.3 Existing API Routes

Preserve existing routes unless there is a strong reason to add a unified endpoint.

Current expected routes:

```text
POST /api/profile
GET /api/profile
POST /transcribe/
POST /classify/
POST /generate/
```

Optional future route:

```text
POST /api/interview/assist
```

The unified route should not be added until the current route chain is stable.

---

## 7. Speech-to-Text Stack

### 7.1 Chosen STT Path

Use one of these:

```text
Whisper
```

or:

```text
faster-whisper
```

For MVP, the priority is reliability, not experimentation.

### 7.2 Required Audio Dependency

Use:

```text
ffmpeg
```

ffmpeg must be installed and available on PATH, or the backend must produce a clear error.

### 7.3 Current Known Problem to Fix

The frontend records audio as WebM, but the backend has treated it like WAV in the past.

Codex must verify and fix:

```text
MediaRecorder output format → backend file extension → ffmpeg decode → Whisper input
```

### 7.4 Accepted MVP Audio Scope

MVP can support microphone input only.

System/interviewer audio capture can be treated as future work if it delays the MVP.

### 7.5 STT Error Handling Required

The backend must return useful errors for:

- Empty audio
- Invalid audio file
- ffmpeg missing
- unsupported audio format
- Whisper/faster-whisper failure
- transcript too short or unclear

---

## 8. Question Classification Stack

### 8.1 Classification Categories

Use these categories:

```text
HR
Technical
Behavioral
General
```

`General` is only a fallback.

### 8.2 MVP Classification Method

Classification can be lightweight for MVP.

Acceptable options:

- Rule-based classifier
- Small LLM classification step
- Existing classifier if already present

Do not add a heavy ML training pipeline for MVP.

### 8.3 Classification Behavior

The category should influence answer style:

- HR: confident, professional, personality-focused
- Technical: direct, structured, technically accurate
- Behavioral: STAR-style when possible
- General: concise and practical

---

## 9. LLM Stack

### 9.1 Primary LLM Provider

Use:

```text
Groq API
```

Groq is the primary answer-generation provider for SAIIA MVP.

### 9.2 Primary Model

Use first:

```text
llama-3.1-8b-instant
```

Reason:

SAIIA needs fast response generation because the answer appears during a live interview scenario.

### 9.3 Fallback Provider

Keep Ollama as optional fallback only:

```text
Ollama + llama3:8b
```

Ollama should not be removed immediately because it is useful for offline fallback and demo resilience.

### 9.4 LLM Provider Environment Variables

Use these variables:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=20
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
```

Never commit real API keys.

### 9.5 Recommended Provider Structure

Recommended backend structure:

```text
backend/
  app/
    services/
      llm/
        base.py
        groq_provider.py
        ollama_provider.py
        provider_factory.py
```

If the existing codebase has a different structure, Codex may adapt this pattern without unnecessary rewrites.

### 9.6 Provider Behavior

Required behavior:

```text
If LLM_PROVIDER=groq:
  call Groq
  if Groq succeeds:
    return answer
  if Groq fails and ENABLE_OLLAMA_FALLBACK=true:
    call Ollama fallback
  if both fail:
    return clear error
```

### 9.7 Groq API Style

Use Groq's OpenAI-compatible Chat Completions API.

Expected endpoint:

```text
POST https://api.groq.com/openai/v1/chat/completions
```

Use either:

- Groq Python SDK, or
- `httpx` against the OpenAI-compatible endpoint

Prefer the simplest reliable implementation.

### 9.8 LLM Request Settings

Recommended settings:

```text
temperature: 0.3 to 0.5
max_tokens: 250 to 400
timeout: 20 seconds
```

The answer must be short enough to speak naturally.

### 9.9 Answer Generation Rules

Generated answers must be:

- concise
- natural
- personalized
- interview-ready
- based on the user's provided profile
- suitable for speaking aloud
- category-aware
- honest when the profile lacks details

Generated answers must not:

- invent fake projects
- invent fake experience
- sound like a long essay
- overclaim skills
- expose hidden prompt text
- include irrelevant technical jargon
- repeat the question unnecessarily

---

## 10. Prompting Rules

### 10.1 System Prompt Goal

The system prompt should define SAIIA as:

```text
A real-time interview answer assistant that generates concise, natural, personalized answer suggestions for the candidate.
```

### 10.2 Prompt Inputs

The answer-generation prompt should include:

- transcribed question
- question category
- resume/background
- target role
- company name
- skills
- experience/projects

### 10.3 Output Style

Preferred output:

- 3–6 short bullets, or
- one short spoken-style paragraph

Behavioral answers may use compact STAR structure.

Technical answers should be practical and direct.

HR answers should sound confident and human.

---

## 11. Storage Stack

### 11.1 MVP Storage

Use the existing profile storage mechanism.

If the project currently stores profile data in JSON, keep it for MVP.

Do not introduce MongoDB, PostgreSQL, Supabase, Firebase, Prisma, or a new auth/database system just for MVP.

### 11.2 Future Storage

Future versions may use:

- SQLite for local desktop persistence
- MongoDB/PostgreSQL for multi-user cloud version
- encrypted local storage for sensitive profile/resume data

But not during MVP stabilization.

---

## 12. Configuration Files

### 12.1 Backend `.env.example`

Required variables:

```env
# Backend
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

# LLM
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=20
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b

# STT
STT_PROVIDER=whisper
WHISPER_MODEL=base
FFMPEG_PATH=

# App
LOG_LEVEL=INFO
```

### 12.2 Frontend `.env.example`

Required variables:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 12.3 Secret Rules

Never commit:

- `.env`
- real Groq API key
- real user resume/profile data
- recorded interview audio
- local transcripts from real users
- generated private answer logs containing user data

---

## 13. Testing Stack

### 13.1 Backend Tests

Use:

```text
pytest
```

Backend tests should cover:

- profile save/load
- audio upload validation
- missing audio error
- missing ffmpeg error handling
- transcription failure handling
- transcript too short handling
- classifier category output
- Groq provider success mock
- missing Groq API key error
- Groq timeout error
- Ollama fallback behavior
- final response shape

### 13.2 Frontend Checks

Use existing frontend checks/build commands.

At minimum:

```bash
npm run build
```

The build must pass before calling a change complete.

### 13.3 Electron Checks

Manual demo checks are required for Electron:

- app launches
- overlay opens
- overlay receives generated answer
- Ctrl+H toggles visibility
- drag works
- font size changes
- app closes cleanly

---

## 14. Logging Rules

Backend logs should include:

- selected LLM provider
- selected model
- transcription start/end
- transcript length
- classification category
- LLM latency
- fallback used or not
- user-friendly error reason

Logs must not include:

- Groq API key
- full resume text unless in debug mode
- sensitive user profile data
- full interview transcript by default

---

## 15. API Response Shape

Preferred successful response:

```json
{
  "transcript": "Tell me about yourself.",
  "category": "HR",
  "answer": "I am a backend-focused developer with experience in Python, FastAPI, MongoDB, and React...",
  "confidence": "medium",
  "provider": "groq",
  "fallback_used": false,
  "error": null
}
```

Preferred failure response:

```json
{
  "transcript": "",
  "category": null,
  "answer": "",
  "confidence": "low",
  "provider": null,
  "fallback_used": false,
  "error": "Could not transcribe audio. Please check ffmpeg installation."
}
```

Preserve existing frontend-compatible response fields if the current app expects a different shape.

---

## 16. Dependencies Policy

### 16.1 Allowed Backend Dependencies

Allowed if needed:

```text
fastapi
uvicorn
python-multipart
pydantic
httpx
groq
openai
whisper
faster-whisper
pytest
python-dotenv
```

Use either `groq`, `openai`, or `httpx` for Groq calls. Do not install all three unless needed.

### 16.2 Allowed Frontend Dependencies

Use existing React/Vite dependencies.

Avoid adding new frontend libraries unless they fix a specific MVP problem.

### 16.3 Avoid Adding

Avoid for MVP:

```text
LangChain
LlamaIndex
ChromaDB
Pinecone
Redis
Celery
Kafka
Supabase
Firebase
Prisma
Next.js
Redux
Tailwind migration if not already used
Docker requirement for local MVP
```

These may be useful later, but they are not needed for the 15-day SAIIA MVP.

---

## 17. Development Commands

Codex must inspect the actual repo before finalizing commands.

Expected examples:

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Electron

```bash
cd frontend
npm run electron:dev
```

The exact Electron command must match the existing package.json.

---

## 18. Security and Privacy Rules

SAIIA handles sensitive user data:

- resume details
- personal background
- interview questions
- generated answers
- target company
- target role

Therefore:

- Do not log secrets.
- Do not commit real user data.
- Do not store audio longer than needed for MVP unless explicitly required.
- Make API errors user-friendly.
- Make it clear that Groq is a cloud provider and requires internet.
- Keep Ollama fallback optional for local/offline demo.

---

## 19. Future Tech Options

These are future options only, not MVP requirements.

### 19.1 Better Local LLM

Potential future local stack:

```text
llama.cpp / llama-cpp-python with CUDA
```

### 19.2 NVIDIA Path

Potential future NVIDIA stack:

```text
NVIDIA Riva for ASR/STT
TensorRT-LLM or NVIDIA NIM for optimized inference
```

Not required for MVP.

### 19.3 Better Audio Capture

Future work:

- system audio capture
- meeting-app-specific audio routing
- virtual audio device support
- streaming transcription

Not required for MVP.

---

## 20. Codex Implementation Rules

Codex must follow these rules:

1. Do not rebuild the project from scratch.
2. Do not migrate frontend frameworks.
3. Do not remove Electron overlay.
4. Do not remove Ollama until Groq is stable.
5. Do not add RAG for MVP.
6. Do not add admin dashboards.
7. Do not add payment/auth systems.
8. Do not introduce a new database unless absolutely necessary.
9. Preserve current routes where possible.
10. Add Groq through a clean provider abstraction.
11. Keep all API keys in `.env` only.
12. Update `.env.example` without real secrets.
13. Add useful tests for the provider switch.
14. Run backend and frontend validation after changes.
15. Keep answers short, natural, and profile-grounded.

---

## 21. Final Locked MVP Architecture

```text
Electron Desktop App
        |
        v
React/Vite UI
        |
        v
FastAPI Backend
        |
        +--> Profile storage
        |
        +--> Audio upload validation
        |
        +--> ffmpeg audio decoding
        |
        +--> Whisper/faster-whisper transcription
        |
        +--> HR/Technical/Behavioral classification
        |
        +--> Groq LLM answer generation
        |        |
        |        +--> optional Ollama fallback
        |
        v
Structured answer response
        |
        v
Electron private overlay
```

---

## 22. Final Rule

Whenever there is confusion, follow this rule:

```text
SAIIA is a real-time AI interview helper that listens to interviewer questions and shows personalized answer suggestions in a private Electron overlay.
```

If a tool, library, or feature does not support this flow, it is not MVP priority.
