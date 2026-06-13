# PRD: SAIIA — Smart AI Interview Assistant

**Version:** 2.0  
**Updated:** 2026-06-11  
**Primary MVP Change:** Replace Ollama as the default answer-generation engine with Groq API, while keeping Ollama as an optional fallback.

---

## 1. Product Name

**SAIIA — Smart AI Interview Assistant**

---

## 2. Product Definition

SAIIA is a real-time AI interview helper for virtual interviews on platforms such as Zoom, Google Meet, Microsoft Teams, and similar meeting tools.

The user starts recording when an interviewer asks a question. SAIIA captures the audio, transcribes the question, classifies the question type, generates a concise personalized answer suggestion using the user profile, and displays the suggestion in a private desktop overlay.

SAIIA is not Dhiti.  
SAIIA is not a document Q&A assistant.  
SAIIA is not primarily a mock interview practice app.  
SAIIA is not a generic chatbot.  
SAIIA is a real-time interview support assistant.

---

## 3. One-Line Product Statement

**SAIIA listens to interview questions in real time and gives the candidate personalized answer suggestions through a private desktop overlay.**

---

## 4. Target User

The primary user is a job candidate attending or preparing for virtual interviews.

The user may be:

- Fresher
- Student
- Early-career developer
- Career switcher
- Candidate preparing for technical, HR, or behavioral interviews

---

## 5. Core Use Case

A user is attending a virtual interview.

The interviewer asks a question.

The user clicks **Start Recording**.

SAIIA records the question, transcribes it, classifies it, generates a short answer suggestion based on the user profile, and displays the answer in a local overlay visible to the user.

The answer should be short enough to speak naturally during the interview.

---

## 6. MVP Goal

The MVP goal is to demonstrate a working real-time interview assistant flow:

```text
Profile setup → Start recording → Transcription → Question classification → Groq answer generation → Overlay display
```

The MVP does not need:

- Advanced analytics
- Full mock interview reports
- Payments
- Admin dashboards
- Complex RAG
- Browser extension
- Mobile app
- Guaranteed invisibility during screen sharing

---

## 7. Main MVP Flow

1. User opens SAIIA.
2. User completes profile setup.
3. User enters:
   - Resume text or background
   - Target role
   - Company name
   - Skills
   - Experience/projects
4. User opens the main assistant screen.
5. User clicks **Start Recording**.
6. SAIIA records microphone audio.
7. User clicks **Stop Recording**.
8. Frontend sends the recorded audio to the backend.
9. Backend transcribes the audio using Whisper/STT.
10. Backend cleans and validates the transcript.
11. Backend classifies the question as:
   - HR
   - Technical
   - Behavioral
   - General fallback, if needed
12. Backend sends the transcript, category, and profile context to Groq.
13. Groq generates a concise personalized answer suggestion.
14. Backend returns the transcript, category, answer, confidence, and error state.
15. Frontend displays the answer in the Electron overlay.
16. User can hide/show the overlay with **Ctrl+H**.
17. User can drag the overlay and adjust font size.

---

## 8. Core MVP Features

### 8.1 Profile Setup

The app must allow the user to set up a profile before using SAIIA.

Required fields:

- Resume text or background
- Target role
- Company name
- Skills
- Experience/projects

Purpose:

The profile is used to personalize generated answers.

Example:

If the profile says the user knows Python, FastAPI, MongoDB, and React, SAIIA should generate answers that reference these technologies when relevant.

The answer must not invent experience that is not present in the profile.

---

### 8.2 Start/Stop Recording

The app must provide a clear recording control.

Required behavior:

- User clicks **Start Recording**.
- App captures microphone audio.
- User clicks **Stop Recording**.
- The recorded audio is sent to the backend.
- UI shows recording, loading, success, and error states.

MVP limitation:

Initial version may support microphone audio only. Full interviewer/system audio capture may be treated as future work if technically difficult.

---

### 8.3 Speech-to-Text Transcription

The backend must convert recorded audio into text.

Expected implementation:

- Whisper/STT pipeline
- Proper audio format handling
- Clear error handling if ffmpeg is missing
- Clear error if uploaded audio is empty or invalid

Known current issue:

The existing transcription endpoint is present but unreliable because Whisper depends on ffmpeg, and ffmpeg may be missing or unavailable on PATH. There is also a format mismatch because the frontend records WebM audio while the backend may currently save or process it as WAV.

Required fix:

- Preserve the real uploaded audio format or convert it safely.
- Do not blindly write WebM bytes as a `.wav` file.
- Validate file size and duration before transcription.
- Return user-friendly errors.

Example error:

```text
Could not transcribe audio. Please check that ffmpeg is installed and available on PATH.
```

---

### 8.4 Question Recognition

SAIIA should treat the transcript as an interviewer question.

Required behavior:

- Clean transcript text.
- Remove empty/noisy transcript.
- Reject unclear transcript.
- Pass meaningful transcript to classifier and answer generator.

Example error:

```text
I could not clearly detect the question. Please try recording again.
```

---

### 8.5 Question Classification

SAIIA must classify the question into one of these categories:

- HR
- Technical
- Behavioral
- General fallback

Purpose:

The generated answer style should change based on category.

Expected behavior:

- Technical question → direct, structured, technically accurate answer.
- HR question → confident, professional, personality-focused answer.
- Behavioral question → STAR-style answer suggestion.
- General question → clear, concise spoken answer.

---

### 8.6 AI Answer Generation — Groq Primary Provider

SAIIA must generate a concise answer suggestion using Groq as the primary LLM provider.

Inputs:

- Transcribed question
- Question category
- Resume/profile text
- Target role
- Company name
- Skills
- Experience/projects

Primary provider:

```env
LLM_PROVIDER=groq
GROQ_MODEL=llama-3.1-8b-instant
```

Groq endpoint:

```text
POST https://api.groq.com/openai/v1/chat/completions
```

Request behavior:

- Use Groq Chat Completions API.
- Use timeout handling.
- Use safe retry/fallback only where appropriate.
- Never log the API key.
- Return errors in the existing backend response shape.

Recommended generation settings:

```json
{
  "temperature": 0.4,
  "max_tokens": 300
}
```

Answer requirements:

- Concise
- Interview-ready
- Personalized
- Natural and speakable
- Not too long
- Relevant to the question type
- Must not sound robotic
- Must not invent fake experience
- Must avoid overclaiming
- Must mention uncertainty if the profile lacks enough detail

Preferred answer style:

- 3–6 short bullets, or
- One short spoken-style paragraph

---

### 8.7 Ollama Fallback

Ollama should not be the primary provider anymore, but it may remain as a fallback.

Fallback environment variables:

```env
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_MODEL=llama3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

Fallback behavior:

- If `LLM_PROVIDER=groq`, call Groq first.
- If Groq fails and `ENABLE_OLLAMA_FALLBACK=true`, try Ollama.
- If Groq fails and fallback is disabled, return a clear error.
- If both Groq and Ollama fail, return a clear user-facing error.

Example user-facing error:

```text
Could not generate an answer right now. Please check your Groq API key, internet connection, or local fallback model.
```

---

### 8.8 Overlay Window

SAIIA must display the generated answer in a desktop overlay.

Required MVP behavior:

- Overlay appears as a separate Electron desktop window.
- Overlay can stay always-on-top.
- Overlay displays generated answer.
- Overlay is draggable.
- Overlay supports font-size adjustment.
- Overlay can be hidden/shown quickly.

Electron should remain the MVP overlay path.

---

### 8.9 Hotkey Control

Required hotkey:

```text
Ctrl+H
```

Behavior:

- If overlay is visible, hide it.
- If overlay is hidden, show it.
- Hotkey should work reliably from the Electron shell.
- The UI should also expose a manual hide/show option if practical.

---

### 8.10 Overlay Privacy During Screen Share

The overlay should be designed so it is not part of the shared interview window where technically supported.

Important product rule:

**SAIIA must not claim that the overlay is guaranteed invisible in every possible screen-sharing scenario.**

Screen-sharing behavior depends on:

- Operating system
- Zoom/Meet/Teams behavior
- Whether the user shares full screen
- Whether the user shares a specific window
- Whether the user shares a browser tab
- Whether the overlay is on another display

MVP-safe approach:

- Use a separate desktop overlay window.
- Encourage sharing only the interview window/tab, not the full desktop.
- Provide Ctrl+H emergency hide.
- Keep overlay draggable so the user can position it away from shared content.
- Treat stronger screen-capture exclusion as future work.

---

### 8.11 Error Handling

The app must show clear errors for:

- Microphone permission denied
- Empty recording
- ffmpeg missing
- Whisper transcription failure
- Backend offline
- Groq API key missing
- Groq API failure
- Groq timeout
- Ollama offline, if fallback is enabled
- LLM generation timeout
- Invalid profile data
- No transcript detected

Errors should be user-friendly and useful for debugging.

---

## 9. Current Codebase Status

According to the codebase audit, the project already has:

- FastAPI backend
- React/Vite frontend
- Electron shell
- Profile setup API
- Recording button
- Transcription endpoint
- Classification endpoint
- Answer generation endpoint
- Ollama/Llama3 integration
- Overlay-style Electron window
- Ctrl+H hotkey partially implemented
- Draggable overlay
- Font-size control

The current codebase is worth continuing.

The project should not be rebuilt from scratch.

Main current blockers:

- Broken transcription pipeline
- Missing ffmpeg/PATH handling
- Audio format mismatch between frontend and backend
- Mic-only recording instead of full interviewer/system audio
- Split profile flow
- Incomplete end-to-end reliability
- Technically risky overlay privacy behavior
- Ollama latency/reliability for real-time answer generation

New provider decision:

- Use Groq as primary answer-generation provider.
- Keep Ollama only as fallback.

---

## 10. What SAIIA Is Not

SAIIA is not:

- Dhiti
- A document assistant
- A RAG-first app
- A generic chatbot
- A mock interview app as the main product
- A full interview scoring/report system for MVP
- An admin dashboard project
- A payment/subscription app
- A complex analytics platform

---

## 11. RAG Decision

RAG is not a core MVP requirement for SAIIA.

For MVP, profile personalization can be done by directly injecting the user profile/resume text into the LLM prompt.

RAG may be added later if:

- Resume text becomes too long
- Multiple documents are uploaded
- Job descriptions are stored
- Company research data is added
- A large question bank is used

For the 15-day MVP, do not prioritize complex RAG.

---

## 12. MVP Feature Priority

### Critical

1. Fix transcription.
2. Fix audio upload format.
3. Make profile data reliable.
4. Add Groq provider for answer generation.
5. Preserve Ollama as optional fallback.
6. Generate answer from transcript and profile.
7. Show answer in overlay.
8. Make Ctrl+H hide/show reliable.
9. Add basic error handling.
10. Add clean run instructions.

### Important

1. Question classification.
2. Personalized prompt quality.
3. Draggable overlay.
4. Font-size control.
5. Groq health/config check.
6. Ollama fallback health check.
7. Better loading states.
8. Demo question mode.

### Optional

1. System audio capture.
2. Auto-hide during screen share.
3. Persist overlay position.
4. Persist font size.
5. Resume parsing.
6. Advanced answer templates.
7. Session history.
8. Streaming answer display.

### Avoid for MVP

1. Mock interview report system.
2. Advanced analytics dashboard.
3. Admin panel.
4. Payment system.
5. Complex RAG.
6. Over-polished animations.
7. Full cross-platform stealth guarantees.
8. Browser extension.
9. Mobile app.

---

## 13. Technical Architecture

### 13.1 Frontend

Current direction:

- React
- Vite
- Electron wrapper

Responsibilities:

- Profile setup UI
- Recording controls
- Display transcription state
- Display answer state
- Overlay UI
- Hotkey-driven visibility
- Font-size control
- Error messages

The frontend should not need major changes for Groq. Provider switching should happen in the backend.

---

### 13.2 Backend

Current direction:

- FastAPI

Responsibilities:

- Save profile
- Receive audio
- Transcribe audio
- Classify question
- Generate answer using configured LLM provider
- Return structured response
- Log errors clearly

---

### 13.3 AI Components

Expected components:

- Whisper/STT for transcription
- Lightweight classifier for HR/Technical/Behavioral classification
- Groq for answer generation
- Ollama as optional local fallback

---

### 13.4 Storage

MVP storage may remain simple:

- JSON profile storage is acceptable temporarily

Future storage:

- SQLite or MongoDB for persistent users/profiles/sessions

---

## 14. LLM Provider Architecture

Create a clean provider layer so SAIIA is not locked to one model vendor.

Recommended structure:

```text
backend/
  app/
    services/
      llm/
        __init__.py
        base.py
        groq_provider.py
        ollama_provider.py
        provider_factory.py
```

### 14.1 Provider Interface

All providers should expose the same behavior:

```python
class LLMProvider:
    async def generate_answer(
        self,
        *,
        profile: dict,
        question: str,
        category: str,
    ) -> str:
        ...
```

### 14.2 Provider Factory

Provider selection should be controlled by environment variables:

```env
LLM_PROVIDER=groq
```

Possible values:

```text
groq
ollama
```

If the configured provider is unknown, fail with a clear backend error.

---

## 15. Environment Variables

Add these to `.env.example`:

```env
# LLM provider
LLM_PROVIDER=groq

# Groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=20

# Ollama fallback
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_TIMEOUT_SECONDS=60

# Transcription
WHISPER_MODEL=base
FFMPEG_PATH=
```

Rules:

- Never commit a real Groq API key.
- `.env` must stay ignored by Git.
- `.env.example` should contain placeholders only.

---

## 16. API Expectations

Existing routes should be preserved unless absolutely necessary:

- `POST /api/profile`
- `GET /api/profile`
- `POST /transcribe/`
- `POST /classify/`
- `POST /generate/`

Expected future unified route:

- `POST /api/interview/assist`

This future route could handle:

```text
Audio/transcript → classify → generate → return answer
```

For MVP stabilization, keep current routes first unless the existing split flow is causing serious reliability problems.

---

## 17. Backend Response Format

Preferred successful response:

```json
{
  "transcript": "Tell me about yourself.",
  "category": "HR",
  "answer": "I am a backend-focused developer with experience in Python, FastAPI, MongoDB, and React...",
  "confidence": "medium",
  "provider": "groq",
  "model": "llama-3.1-8b-instant",
  "fallback_used": false,
  "error": null
}
```

Failure response:

```json
{
  "transcript": "",
  "category": null,
  "answer": "",
  "confidence": "low",
  "provider": "groq",
  "model": "llama-3.1-8b-instant",
  "fallback_used": false,
  "error": "Could not transcribe audio. Please check ffmpeg installation."
}
```

If frontend already expects a smaller response shape, preserve backward compatibility and add new fields only if safe.

---

## 18. Prompt Requirements

The Groq prompt must keep SAIIA focused on interview answer suggestions.

### 18.1 System Prompt Requirements

The system prompt should say:

- You are SAIIA, an interview answer assistant.
- Generate concise, natural answer suggestions for the candidate.
- Use only the provided user profile.
- Do not invent experience, projects, jobs, education, or skills.
- Keep the answer easy to speak aloud.
- Do not write long essays.
- Match the answer style to the category.

### 18.2 Category Behavior

HR:

- Confident
- Professional
- Personality-focused
- Short spoken-style answer

Technical:

- Direct
- Structured
- Technically accurate
- Mention known skills from profile only

Behavioral:

- STAR-style
- Situation, Task, Action, Result
- Concise and realistic

General:

- Natural
- Helpful
- Short

---

## 19. Answer Quality Requirements

Generated answers should:

- Sound natural.
- Be short enough to speak.
- Match the candidate profile.
- Avoid hallucinated projects or experience.
- Avoid overclaiming.
- Mention uncertainty if profile lacks enough detail.
- Be role-specific.
- Be category-specific.

Generated answers should not:

- Be too long.
- Sound like a written essay.
- Invent fake experience.
- Include irrelevant technical jargon.
- Give generic motivational advice.
- Repeat the question unnecessarily.

---

## 20. Logging Requirements

Backend logs should include:

- Selected LLM provider
- Selected model
- Request latency
- Whether fallback was used
- Error reason
- Transcript length
- Category

Backend logs must not include:

- Groq API key
- Full resume/profile text unless explicitly needed for debug mode
- Sensitive user data in normal logs

---

## 21. Test Requirements

Add or update tests for:

1. Groq provider builds a valid request.
2. Missing `GROQ_API_KEY` returns a clear config error.
3. Groq timeout returns a clear error.
4. Groq failure falls back to Ollama if fallback is enabled.
5. Groq failure does not fall back if fallback is disabled.
6. Existing response shape remains compatible with frontend.
7. Prompt does not generate fake experience when profile is incomplete.
8. Transcription rejects empty audio.
9. WebM audio is not incorrectly saved as WAV without conversion.
10. Ctrl+H overlay toggle still works after backend changes.

---

## 22. Demo Success Criteria

A successful MVP demo should show:

1. User opens SAIIA.
2. User sets profile.
3. User starts recording.
4. User asks or plays an interview question.
5. SAIIA transcribes the question.
6. SAIIA classifies the question.
7. SAIIA generates a personalized answer using Groq.
8. Answer appears in overlay.
9. User toggles overlay with Ctrl+H.
10. User adjusts font size or drags overlay.

Minimum successful demo:

```text
Profile setup + record question + transcription + Groq-generated answer + overlay display
```

---

## 23. 15-Day Build Strategy

### Days 1–3: Runtime Stabilization

- Fix ffmpeg/transcription issue.
- Fix audio format mismatch.
- Fix Electron entry mismatch if present.
- Fix lint/build dependency issue if present.
- Confirm backend/frontend/Electron launch.

### Days 4–6: Transcription and Audio Flow

- Stabilize MediaRecorder upload.
- Add clear transcription errors.
- Test with short audio.
- Decide mic-only MVP or system-audio path.
- Ensure failed transcription stops the flow.

### Days 7–9: Groq AI Pipeline

- Add Groq provider.
- Add provider factory.
- Add environment variables.
- Connect transcript → classify → Groq generate.
- Improve prompts using profile.
- Add answer category behavior.
- Add Groq timeout/failure handling.
- Keep Ollama fallback optional.

### Days 10–12: Overlay

- Stabilize Electron overlay.
- Keep always-on-top behavior.
- Confirm Ctrl+H works.
- Confirm drag and font-size work.
- Avoid overclaiming screen-share invisibility.

### Days 13–15: Demo Readiness

- Remove dead/confusing paths if safe.
- Write setup/run instructions.
- Test full flow repeatedly.
- Prepare demo script.
- Prepare final project explanation.

---

## 24. Major Risks

### 24.1 Transcription Risk

Whisper requires ffmpeg for decoding audio. If ffmpeg is missing, transcription fails.

### 24.2 Audio Capture Risk

Browser microphone capture may not capture interviewer/system audio. This may limit MVP realism.

### 24.3 Groq Dependency Risk

Groq requires:

- Internet connection
- Valid API key
- Available Groq service
- Rate limits not exceeded

Mitigation:

- Keep Ollama fallback.
- Show clear errors.
- Add demo question/manual text mode if needed.

### 24.4 Latency Risk

Groq should reduce LLM latency compared with local Ollama, but transcription may still be slow depending on local Whisper model and hardware.

### 24.5 Overlay Privacy Risk

No overlay implementation can guarantee invisibility across all screen-sharing modes.

### 24.6 Cross-Platform Risk

Electron supports desktop overlays, but behavior differs across Windows, macOS, and Linux.

### 24.7 Scope Risk

Adding mock interviews, analytics, RAG, admin dashboards, payments, or reports will delay the real MVP.

---

## 25. Codex Implementation Rules

Codex must follow these rules:

1. Do not rebuild the project from scratch.
2. Do not rename the product to Dhiti.
3. Do not convert SAIIA into a document assistant.
4. Do not add complex RAG for MVP.
5. Do not change frontend routes unless necessary.
6. Do not break Electron overlay behavior.
7. Do not remove Ollama immediately; keep it as fallback.
8. Do not commit real API keys.
9. Do not claim guaranteed invisibility during screen share.
10. Preserve current API response shape expected by frontend.
11. Make small, testable changes.
12. Add clear logs and errors.
13. Run backend/frontend validation after changes.

---

## 26. Final Product Rule

Whenever there is confusion, follow this rule:

**SAIIA is a real-time AI interview helper that listens to interviewer questions and shows personalized answer suggestions in a private desktop overlay.**

If a feature does not support this flow, it is not MVP priority.
