# SAIIA

SAIIA is a Smart AI Interview Assistant for fast MVP demos. It records a spoken interview question, transcribes it, classifies the question type, generates a concise answer suggestion from the user's profile, and shows that answer in a separate Electron overlay window.

## What SAIIA Is

- A profile-aware interview answer assistant
- A FastAPI + React + Electron MVP
- A Groq-first answer generation flow with optional Ollama fallback
- A two-window app: main control panel plus overlay answer display

## What SAIIA Is Not

- Not a RAG product
- Not an admin dashboard
- Not an analytics/reporting product
- Not a payments/auth product
- Not a guaranteed invisible screen-sharing tool

## MVP Flow

```text
Profile setup -> microphone recording -> transcription -> classification -> Groq answer generation -> Electron overlay display
```

## Tech Stack

- Backend: FastAPI, Whisper, ffmpeg, Python
- Frontend: React, Vite
- Desktop shell: Electron
- Primary LLM: Groq
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
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=20
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_TIMEOUT_SECONDS=60
WHISPER_MODEL=tiny.en
FFMPEG_PATH=
USE_ZERO_SHOT_CLASSIFIER=false
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

## Groq API Key Setup

Set your local Groq API key in `.env`.

```env
GROQ_API_KEY=your_local_key_here
```

Never commit the real key.

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
2. Click `Setup Profile` and complete all required fields.
3. Use `Start Recording`.
4. Ask a short interview question.
5. Stop recording and wait for transcript, classification, and answer generation.
6. Read the full answer from the overlay window.
7. Use `Ctrl+H` or the `Show/Hide Overlay` button to toggle overlay visibility.

## Demo Script

See [DEMO_SCRIPT.md](./DEMO_SCRIPT.md).

## MVP Status

SAIIA MVP is complete and demo-ready.

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

### Groq key missing

Symptom:
Generation fails with a Groq API key error.

Fix:
Set `GROQ_API_KEY` in local `.env` and restart the backend.

### Ctrl+H already registered by another app

Symptom:
The overlay hotkey does not register on launch.

Fix:
Close the conflicting app or use the `Show/Hide Overlay` button from the main control window.

### Ollama fallback unavailable

Symptom:
Groq fails and fallback also fails.

Fix:
Start Ollama locally, verify `OLLAMA_BASE_URL`, or set `ENABLE_OLLAMA_FALLBACK=false` if fallback is not needed.

## Known Limitations

- Recording is manual start/stop for this MVP.
- This is a microphone-only MVP.
- SAIIA does not guarantee screen-share invisibility.
- It requires a Groq API key and internet access for the primary demo flow.
- `ffmpeg` is required for transcription.
- Auto-listen mode is future work.
