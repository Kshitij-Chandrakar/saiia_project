# SAIIA

SAIIA is a Smart AI Interview Assistant for fast MVP demos and the current production-core build. It records a spoken interview question, transcribes it, classifies the question type, grounds the answer in the saved profile plus local resume context, optionally tailors the answer to a saved job description/company target, and shows that answer in a separate Electron overlay window.

## What SAIIA Is

- A profile-aware interview answer assistant
- A FastAPI + React + Electron MVP
- An AssemblyAI-first STT runtime with local Whisper fallback for transcription, Affinda-first resume parsing with local fallback, OpenAI-default answer generation, configurable Groq answers (`ANSWER_PROVIDER=groq`), optional local Ollama fallback for the Groq path
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
Profile setup -> optional Affinda/local resume extraction + local resume indexing -> optional job/company context -> microphone recording -> transcription -> classification -> grounded answer generation (OpenAI by default; Groq with ANSWER_PROVIDER=groq) -> Electron overlay display
```

## Tech Stack

- Backend: FastAPI, AssemblyAI STT, Affinda resume parsing, local parser fallback, ffmpeg, Python
- Frontend: React, Vite
- Desktop shell: Electron
- Screen Analyze: Groq Vision (`meta-llama/llama-4-scout-17b-16e-instruct`) with RapidOCR fallback
- Default answer-generation provider: OpenAI; select Groq with `ANSWER_PROVIDER=groq`
- Optional local fallback LLM for the Groq answer path: Ollama (`ENABLE_OLLAMA_FALLBACK=true`)

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
ANSWER_PROVIDER=openai
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

### OpenAI Whisper for manual recordings

Manual capture defaults to batch STT through `/transcribe/` after stopping. Live preview requires explicit `MANUAL_LIVE_STT_PROVIDER=assemblyai_streaming` on the backend (default: `none`), along with the existing AssemblyAI streaming configuration. `/transcribe/config` exposes only provider names to the frontend. `MANUAL_STT_PROVIDER=whisper_local` always disables external manual preview, even with the live setting enabled. OpenAI Whisper manual capture remains batch-only unless you opt in to AssemblyAI preview; streaming failure uses the configured manual batch provider. Restart the backend after changing these settings.

An active interview session always requires connected cloud authentication, even without a selected resume or job context. When cloud/auth is unavailable, reconnect to continue, or explicitly end the session and clear cloud selections before using local generation. Requests never silently drop the session ID.

Set `MANUAL_STT_PROVIDER=openai_whisper` and a server-side `OPENAI_API_KEY` to use the OpenAI Whisper API for manual uploads to `/transcribe/`. `OPENAI_STT_MODEL` defaults to `whisper-1`; `OPENAI_STT_TIMEOUT_SECONDS` defaults to 30 seconds, with automatic SDK retries disabled. The existing Groq manual provider remains selectable.

```env
MANUAL_STT_PROVIDER=openai_whisper
OPENAI_STT_MODEL=whisper-1
OPENAI_STT_TIMEOUT_SECONDS=30
STT_FALLBACK_PROVIDER=whisper_local
```

On API failure, local Whisper remains the fallback when enabled. Empty transcripts return `no_speech=true`. Keep ffmpeg and the local Whisper runtime available. Existing `.env` files are not changed automatically.

Auto/live AssemblyAI WebSocket transcription is unchanged. System-audio `/stop` and `/capture-chunk` also use manual transcription mode and therefore inherit this provider selection. The `/transcribe/` response fields are unchanged.

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

## Answer Provider Configuration

OpenAI is the default answer-generation provider. Select Groq with `ANSWER_PROVIDER=groq`. Supported answer providers are `openai`, `groq`, and `ollama`, selected through `ANSWER_PROVIDER`. Unsupported values fall back to OpenAI unless `PRIMARY_LLM_PROVIDER=ollama` selects the existing local compatibility path.

NVIDIA generation, routing/refinement flags, credentials, and `/api/debug/nvidia-test` have been retired. Historical roadmap and tracker entries describe earlier experiments; setting their old flags does not enable NVIDIA.

`REFINEMENT_JOB_TIMEOUT_SECONDS` defaults independently to 50 seconds and can still be overridden explicitly.

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
- OpenAI as the default production answer-generation provider; Groq can be selected with `ANSWER_PROVIDER=groq`, with optional local Ollama fallback when `ENABLE_OLLAMA_FALLBACK=true`
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

## Known Limitations

- Recording is manual start/stop for this MVP.
- The current Auto Mode is a lightweight repeated-segment listener, not full streaming speech detection.
- Auto Mode uses deterministic transcript filtering, so interview-like background voices may still be processed if they sound like real questions.
- This is a microphone-only MVP.
- SAIIA does not guarantee screen-share invisibility.
- It requires an AssemblyAI API key plus internet access for the primary STT path and an OpenAI API key for the default answer path (a Groq API key when `ANSWER_PROVIDER=groq`), unless local-only settings are used.
- `ffmpeg` is required for transcription.
- Production-grade continuous listening, speaker separation, and wake-word behavior are still future work.

Manual answer generation can continue locally when cloud connectivity is unavailable and no cloud resume or job context is selected. An incidental startup session is omitted in that case. Selected cloud resumes and interview sessions still require valid authentication; sign in again or clear cloud selections to generate locally. Cloud job context is loaded through an authorized interview session. Generation diagnostics report whether authentication is required and whether a token was attached, without logging token values.

### Experimental gRPC realtime foundation (G1)

G1 is a standalone, loopback-only `grpc.aio` transport skeleton, disabled by default.
REST/WebSocket remain the current production path. FastAPI startup does not start gRPC,
and Electron has no gRPC client. Enabling the flag does not redirect existing traffic.

Install the pinned dependencies from `backend/requirements.txt`. To run locally in PowerShell:

```powershell
cd backend
$env:GRPC_REALTIME_ENABLED = "true"
python -m app.grpc_server --host 127.0.0.1 --port 50051
```

Configuration: `GRPC_REALTIME_ENABLED=false`, `GRPC_REALTIME_HOST=127.0.0.1`,
`GRPC_REALTIME_PORT=50051`, `GRPC_MAX_MESSAGE_MB=4` (allowed message limit: 1?64 MiB).
This unauthenticated foundation refuses non-loopback addresses and must not be exposed
through a public proxy. It grants no cloud/session ownership or access to application data.
Remote access requires a future authenticated/TLS phase.

The versioned `intervuai.realtime.v1.InterviewRealtimeService.StreamInterview` RPC is
bidirectional. `start_session` returns `ready`/foundation status; `ping` returns `pong`.
Audio requires a started matching session and returns `not_implemented`; no audio is
transcribed, stored, or logged. `manual_stop` returns `not_implemented`.
`cancel` and `end_session` acknowledge and close the stream. Half-close also ends cleanly.
This readiness exchange is the G1 health check; no separate standard health RPC is provided.
Messages reserve transcript/question/answer events for future phases. IDs are caller-supplied
transport correlation values, not authenticated interview-session records.

Regenerate the checked-in bindings from the repository root:

```powershell
python backend/scripts/generate_grpc.py
```

Source: `backend/protos/interview_realtime.proto`; generated package:
`backend/app/grpc_generated/`. The script fixes the generated sibling import for package use.
G1 intentionally has no STT, generation, provider migration, auth integration, Electron client,
or changes to existing provider defaults.

### Experimental Electron gRPC client (G2)

G2 adds a main-process `grpc-js`/`proto-loader` client and diagnostics-only IPC.
It is disabled by default and never replaces REST/WebSocket or connects on startup.
Set the following backend-only/main-process environment settings, then restart Electron:

```dotenv
ELECTRON_GRPC_REALTIME_ENABLED=true
ELECTRON_GRPC_REALTIME_HOST=127.0.0.1
ELECTRON_GRPC_REALTIME_PORT=50051
```

Start G1 in a separate PowerShell terminal:

```powershell
cd backend
$env:GRPC_REALTIME_ENABLED = "true"
python -m app.grpc_server --host 127.0.0.1 --port 50051
```

Open the existing runtime diagnostics panel. Under **Experimental gRPC ? handshake only**,
click **Connect**, then **Ping**. Expect connection `connected` and last ping `pong`.
**Close** releases the stream/channel. A stopped backend produces a generic safe error;
no upstream metadata or session identifiers are exposed to the renderer.
When disabled, the section shows status only and has no connect controls.
Only `127.0.0.1`, `localhost`, and `::1` are allowed; remote access is intentionally unavailable
until a future authenticated/TLS phase. This creates an isolated diagnostic session, not a
cloud interview session. No credentials are sent or used by this skeleton.

The backend proto remains the source of truth. `npm run grpc:sync-proto` (in `frontend`)
automatically copies it into `electron/protos/` for packaging; `electron:build` runs this first.
The checked-in copy is tested for equality. No generated or duplicated handwritten schema is required.

IPC exposes only `grpcRealtime:getStatus`, `grpcRealtime:connect`, `grpcRealtime:ping`,
and `grpcRealtime:close`, with existing trusted-renderer validation. Current limits are
handshake/ping only: no microphone/system audio, STT, answer generation, provider migration,
or Electron authentication changes.

### Experimental gRPC microphone transport (G3)

G3 extends G2 with an explicit diagnostics-only microphone test. It is disabled by default:
`ELECTRON_GRPC_AUDIO_ENABLED=false`. To test, start the standalone G1/G3 server using the
command above, keep FastAPI running separately as usual, and launch Electron with:

```powershell
cd frontend
$env:ELECTRON_GRPC_REALTIME_ENABLED = "true"
$env:ELECTRON_GRPC_AUDIO_ENABLED = "true"
$env:ELECTRON_GRPC_REALTIME_HOST = "127.0.0.1"
$env:ELECTRON_GRPC_REALTIME_PORT = "50051"
npm run electron:dev
```

In runtime diagnostics, Connect, verify Ping, then click **Start experimental gRPC mic test**.
Grant microphone permission. **Stop gRPC mic test** closes local capture and sends `manual_stop`.
Close/unmount/disconnection also releases microphone tracks and Web Audio resources.
Do not run the diagnostic test concurrently with normal microphone capture.

The test reuses the existing mono 16 kHz linear16 PCM capture/conversion. Main validates chunks
(up to 64 KiB, even byte length) and accepts them only with both flags enabled and a connected
session. Only one chunk is awaiting acknowledgement; incoming chunks are skipped under
backpressure instead of accumulating audio. Counts reflect acknowledged chunks/bytes,
not all microphone samples. Server totals are scoped to each gRPC stream. Polling shows
sent/received counts and fixed safe status/error messages. No audio is logged or written to disk.
G3 adds narrowly validated `grpcRealtime:audioChunk` and `grpcRealtime:manualStop` IPC;
it does not expose arbitrary gRPC messages or credentials.

Audio reaches the backend for validation/counting only. There is no STT, answer generation,
system audio, provider migration, or replacement of REST/WebSocket/manual/auto flows.
Sarvam and AssemblyAI integrations are unchanged. Regenerate Python bindings and run
`npm run grpc:sync-proto` after changing the source proto.

### G4 experimental gRPC microphone STT

Disabled by default (`GRPC_STT_ENABLED=false`). Start the standalone backend with
`GRPC_REALTIME_ENABLED=true` and `GRPC_STT_ENABLED=true`, using
`python -m app.grpc_server --host 127.0.0.1 --port 50051` from `backend`.
Configure the existing backend-only `ASSEMBLYAI_API_KEY`. This opt-in test sends
microphone PCM to AssemblyAI through the existing streaming bridge.

Enable `ELECTRON_GRPC_REALTIME_ENABLED=true` and `ELECTRON_GRPC_AUDIO_ENABLED=true`
for Electron. Connect in Experimental gRPC diagnostics, then start the mic test.
The panel shows provider, partial/final counts, and only the current transcript.
Stop sends ForceEndpoint/Terminate, drains for up to 1.5 seconds, and closes the
provider connection. A later mic test starts a fresh provider connection.

Audio is limited to 64 KiB per chunk; output buffering is bounded. Transcripts
are carried in transcript events and the current preview only, never logged.
No answer generation or system audio is connected. REST/WebSocket remains the
production path; its provider routing and defaults are unchanged.
