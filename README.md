# SAIIA

SAIIA is a Smart AI Interview Assistant for fast MVP demos and the current production-core build. It records a spoken interview question, transcribes it, classifies the question type, grounds the answer in the saved profile plus local resume context, optionally tailors the answer to a saved job description/company target, and shows that answer in a separate Electron overlay window.

## What SAIIA Is

- A profile-aware interview answer assistant
- A FastAPI + React + Electron MVP
- An AssemblyAI-first STT runtime with local Whisper fallback for transcription, Affinda-first resume parsing with local fallback, Groq-first answer generation, optional Ollama fallback, and paused-by-default NVIDIA support
- A performance-tuned live answer path with cached profile context, capped RAG retrieval, manual Groq STT, and demo-mode short answers
- A two-window app: main control panel plus overlay answer display

## What SAIIA Is Not

- Not a general document Q&A product
- Not an admin dashboard
- Not an analytics/reporting product
- Not a payments/auth product
- Not a guaranteed invisible screen-sharing tool

## MVP Flow

```text
Profile setup -> optional Affinda/local resume extraction + local resume indexing -> optional job/company context -> microphone recording -> transcription -> classification -> grounded Groq answer generation -> Electron overlay display
```

## Tech Stack

- Backend: FastAPI, AssemblyAI STT, Affinda resume parsing, local parser fallback, ffmpeg, Python
- Frontend: React, Vite
- Desktop shell: Electron
- Screen Analyze: Groq Vision (`meta-llama/llama-4-scout-17b-16e-instruct`) with RapidOCR fallback
- Primary LLM: Groq
- Experimental/paused refinement/router LLM: NVIDIA DeepSeek via NVIDIA NIM
- Optional fallback LLM: Ollama

## Setup

### 1. Install backend dependencies

```powershell
cd e:\saiia_project\saiia_project
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```powershell
cd e:\saiia_project\saiia_project\frontend
npm install
```

### 3. Configure environment

Copy `.env.example` to `.env` in the repo root and fill in placeholders only on your local machine.

Required MVP variables:

```env
LLM_PROVIDER=groq
STT_PROVIDER=assemblyai
MANUAL_STT_PROVIDER=groq
STT_FALLBACK_PROVIDER=whisper_local
RESUME_PARSER_PROVIDER=affinda
RESUME_PARSER_FALLBACK=local
AFFINDA_API_KEY=
AFFINDA_WORKSPACE=
AFFINDA_DOCUMENT_TYPE=
AFFINDA_COLLECTION=
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_STT_MODEL=whisper-large-v3-turbo
GROQ_TIMEOUT_SECONDS=20
ENABLE_NVIDIA_REFINEMENT=false
ENABLE_PROVIDER_ROUTER=false
ENABLE_PARALLEL_REFINEMENT=false
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro
NVIDIA_TIMEOUT_SECONDS=45
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_TIMEOUT_SECONDS=60
PERFORMANCE_MODE=demo
ANSWER_MAX_WORDS=120
RAG_RETRIEVAL_LIMIT=2
RAG_TIMEOUT_MS=120
WHISPER_MODEL=tiny.en
FFMPEG_PATH=
USE_ZERO_SHOT_CLASSIFIER=false
SCREEN_VISION_PROVIDER=groq
SCREEN_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
SCREEN_VISION_TIMEOUT_MS=10000
SCREEN_VISION_MAX_IMAGE_WIDTH=1600
SCREEN_VISION_FALLBACK_OCR=true
SCREEN_ANALYZE_DEBUG_SAVE=false
SCREEN_FULL_CAPTURE_ENABLED=true
SCREEN_FULL_CAPTURE_MAX_SCROLLS=4
SCREEN_FULL_CAPTURE_SCROLL_AMOUNT=0.75
SCREEN_FULL_CAPTURE_WAIT_MS=250
SCREEN_FULL_CAPTURE_RESTORE_SCROLL=true
```

## ffmpeg Setup

SAIIA needs `ffmpeg` for microphone audio decoding.

Option 1:
Install `ffmpeg` and make sure `ffmpeg` is available on your system `PATH`.

Option 2:
Set `FFMPEG_PATH` in `.env` to the folder or binary path for `ffmpeg`.

Examples:

```env
FFMPEG_PATH=C:\ffmpeg\bin
```

or

```env
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
```

## STT Setup

Set your local AssemblyAI API key in `.env`.

```env
ASSEMBLYAI_API_KEY=your_local_key_here
ASSEMBLYAI_STT_MODEL=best
STT_PROVIDER=assemblyai
STT_FALLBACK_PROVIDER=whisper_local
```

Never commit the real key.

If AssemblyAI STT is unavailable and `STT_FALLBACK_PROVIDER=whisper_local`, SAIIA falls back to local Whisper without changing the `/transcribe` endpoint path.

For lower live-answer latency in manual recording mode, SAIIA can use Groq STT just for short manual clips while keeping AssemblyAI available for other modes:

```env
MANUAL_STT_PROVIDER=groq
STT_PROVIDER=assemblyai
STT_FALLBACK_PROVIDER=whisper_local
```

## Resume Parser Setup

Set your local Affinda credentials in `.env` if you want Affinda to be the primary resume parser.

```env
RESUME_PARSER_PROVIDER=affinda
AFFINDA_API_KEY=your_local_key_here
AFFINDA_WORKSPACE=
AFFINDA_DOCUMENT_TYPE=
AFFINDA_COLLECTION=
RESUME_PARSER_FALLBACK=local
```

`AFFINDA_DOCUMENT_TYPE` is the preferred setting. If it is blank, SAIIA falls back to `AFFINDA_COLLECTION` for backward compatibility. If the Affinda key, workspace, or document type is missing, the Affinda request fails, or the Affinda result is incomplete, SAIIA falls back to the existing local parser and keeps the extracted profile editable before save.

## Groq API Key Setup

Set your local Groq API key in `.env`.

```env
GROQ_API_KEY=your_local_key_here
```

Never commit the real key.

## Optional NVIDIA Setup

NVIDIA is optional and currently paused by default for the real-time interview flow. SAIIA still works with Groq only.

Use these local `.env` flags only if you want router/refinement behavior:

```env
ENABLE_NVIDIA_REFINEMENT=false
ENABLE_PROVIDER_ROUTER=false
ENABLE_PARALLEL_REFINEMENT=false
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro
NVIDIA_TIMEOUT_SECONDS=45
```

Recommended behavior:

- Keep `LLM_PROVIDER=groq` for the default fast path.
- Keep `STT_PROVIDER=assemblyai` with `STT_FALLBACK_PROVIDER=whisper_local` for the default transcription path plus local fallback.
- Keep `ENABLE_NVIDIA_REFINEMENT=false`, `ENABLE_PARALLEL_REFINEMENT=false`, and `ENABLE_PROVIDER_ROUTER=false` for the stable production path.
- NVIDIA can be re-enabled later for experimentation with env flags after latency and timeout behavior is improved.
- Ollama fallback remains available if Groq fails and local Ollama is running.

## `/transcribe` Response

`POST /transcribe/` still returns a `text` field and now also reports which STT provider handled the request:

```json
{
  "text": "What is JavaScript?",
  "transcription_provider": "assemblyai",
  "transcription_model": "best",
  "transcription_ms": 1234.56,
  "fallback_used": false,
  "fallback_reason": null,
  "no_speech": false,
  "reason": null
}
```

When no speech is detected, `/transcribe/` returns `text=""` with `no_speech=true` so Auto Mode can safely wait for the next question without showing an error.

Example fallback response:

```json
{
  "text": "What is JavaScript?",
  "transcription_provider": "whisper_local",
  "transcription_model": "tiny.en",
  "transcription_ms": 2500.12,
  "fallback_used": true,
  "fallback_reason": "groq_stt_failed"
}
```

## How To Run

### Start the backend

```powershell
cd e:\saiia_project\saiia_project\backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Start the frontend + Electron app

```powershell
cd e:\saiia_project\saiia_project\frontend
npm run electron:dev
```

### Production-style frontend build check

```powershell
cd e:\saiia_project\saiia_project\frontend
npm run build
```

## Using SAIIA

1. Open the Electron app.
2. Click `Setup Profile` and complete the required profile fields manually or use resume upload for PDF, DOCX, or TXT extraction.
3. Optionally save job description and company context to tailor answers for a target role.
4. Use `Start Recording` for manual mode, or turn on `Auto Mode` for repeated short microphone segments.
5. Ask a short interview question.
6. In manual mode, stop recording and wait for transcript, classification, retrieval, and answer generation.
7. In Auto Mode, SAIIA filters each short transcript first and only generates when the transcript looks like an interview-style question.
8. For visible on-screen questions, click `Analyze Screen`. SAIIA captures the active external window, runs Groq Vision first, and uses RapidOCR only as fallback if Vision fails or times out.
9. Read the full answer from the overlay window.
10. Use `Ctrl+H` or the `Show/Hide Overlay` button to toggle overlay visibility.

## Demo Script

See [DEMO_SCRIPT.md](./DEMO_SCRIPT.md).

## MVP Status

SAIIA MVP is complete and demo-ready.

## Production-Core Status

The current production-core track includes:

- Resume upload and profile extraction for PDF, DOCX, and TXT
- Structured resume extraction for name, contact info, education, top skills, technical skills, soft skills, projects, experience, achievements, and certifications with Affinda-first parsing, local fallback, and manual review warnings when extraction is weak
- Local resume grounding through `tmp/resume_index.json`
- Optional saved job/company context through `tmp/job_context.json`
- Lightweight Auto Mode with repeated short microphone segments and deterministic question filtering
- User-triggered Screen Read Mode with local OCR preview and editable question confirmation
- AssemblyAI STT as the default transcription path, with local Whisper fallback
- Groq-first answer generation as the production path, with optional Ollama fallback and paused-by-default NVIDIA support
- Cleaner introduction-style answers that use focused profile data and strip markdown leaks before rendering in the overlay
- Performance-focused live answering with cached profile loading, summarized prompt context, capped RAG retrieval, pipeline timing diagnostics, and demo-mode shorter answers

## Live Performance Mode

For the fastest interview flow, set:

```env
PERFORMANCE_MODE=demo
ANSWER_MAX_WORDS=120
MANUAL_STT_PROVIDER=groq
RAG_RETRIEVAL_LIMIT=2
RAG_TIMEOUT_MS=120
```

In this mode SAIIA:

- reuses the saved profile instead of reparsing resumes during live answers
- sends only summarized profile context to generation
- keeps RAG lightweight and skips slow retrieval chunks
- shows detailed pipeline timing in diagnostics
- prefers shorter, overlay-ready answers

## Troubleshooting

### Backend offline

Symptom:
The app says it cannot reach the backend.

Fix:
Start the FastAPI backend on `http://localhost:8000` and retry.

### Port 5173 already in use

Symptom:
`npm run electron:dev` fails because Vite uses `--strictPort`.

Fix:
Stop the old Vite process using port `5173`, then rerun Electron.

### Port 8000 already in use

Symptom:
Backend startup fails or requests hit the wrong process.

Fix:
Stop the old backend process using port `8000`, then restart FastAPI.

### ffmpeg missing

Symptom:
Transcription fails with an `ffmpeg` error.

Fix:
Install `ffmpeg` or set `FFMPEG_PATH` correctly in `.env`.

### AssemblyAI key missing

Symptom:
AssemblyAI transcription fails or falls back immediately.

Fix:
Set `ASSEMBLYAI_API_KEY` in local `.env` and restart the backend.

### AssemblyAI STT fallback triggered

Symptom:
`/transcribe` returns `fallback_used=true` with `transcription_provider=whisper_local`.

Fix:
Check `ASSEMBLYAI_API_KEY`, internet access, and `ASSEMBLYAI_STT_MODEL`. If you want local-only transcription, set `STT_PROVIDER=whisper_local`.

### Groq key missing

Symptom:
Groq generation fails with an API key error.

Fix:
Set `GROQ_API_KEY` in local `.env` and restart the backend.

### Ctrl+H already registered by another app

Symptom:
The overlay hotkey does not register on launch.

Fix:
Close the conflicting app or use the `Show/Hide Overlay` button from the main control window.

### Auto Mode hears speech but does not answer

Symptom:
Auto Mode transcribes a short segment but no answer appears.

Fix:
Auto Mode only generates when the transcript looks like an interview-style question. Very short speech, filler phrases, repeated prompts, and recent duplicates are intentionally ignored.

### Screen OCR returns no usable text

Symptom:
Screen Read Mode captures the screen, but OCR returns an empty or weak result.

Fix:
Use a clearer, text-heavy screen region, increase zoom if needed, and review the editable OCR preview before generation. SAIIA does not store screenshots and only captures after the user clicks the button.

### Ollama fallback unavailable

Symptom:
Groq fails and fallback also fails.

Fix:
Start Ollama locally, verify `OLLAMA_BASE_URL`, or set `ENABLE_OLLAMA_FALLBACK=false` if fallback is not needed.

### NVIDIA refinement unavailable

Symptom:
Generation still works, but refinement metadata shows a failed NVIDIA attempt.

Fix:
Check `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_MODEL`, and `ENABLE_NVIDIA_REFINEMENT`. If NVIDIA is not needed, keep it disabled.

### Temporary NVIDIA debug route unavailable

Symptom:
`/api/debug/nvidia-test` returns 404.

Fix:
That route is intentionally guarded and only mounts when `DEBUG=true`. It is a temporary backend-only diagnostic endpoint and should stay disabled in normal runs.

## Known Limitations

- Recording is manual start/stop for this MVP.
- The current Auto Mode is a lightweight repeated-segment listener, not full streaming speech detection.
- Auto Mode uses deterministic transcript filtering, so interview-like background voices may still be processed if they sound like real questions.
- This is a microphone-only MVP.
- SAIIA does not guarantee screen-share invisibility.
- It requires an AssemblyAI API key plus internet access for the primary STT path and a Groq API key for the answer path, unless local fallback-only settings are used.
- NVIDIA refinement/router behavior is implemented but paused by default due to latency and timeout instability in the live interview flow.
- `ffmpeg` is required for transcription.
- Production-grade continuous listening, speaker separation, and wake-word behavior are still future work.
