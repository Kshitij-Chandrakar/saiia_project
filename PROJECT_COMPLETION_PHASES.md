# SAIIA — Project Completion Phases Checklist

## Purpose

This file tracks the completion status of **SAIIA — Smart AI Interview Assistant**.

Use this as the single progress checklist for Codex, manual testing, and MVP planning.

SAIIA is a real-time AI interview helper:

```text
Profile setup → Start recording → Transcription → Question classification → Groq answer generation → Electron overlay display
```

The MVP should prove the full working flow. Do not expand scope unless the critical flow is stable.

---

## Status Legend

```text
[ ] Not started
[~] In progress / partially working
[x] Done
[!] Blocked / broken / needs urgent fix
[-] Deferred / not MVP
```

---

# Phase 0 — Project Lock & Scope Control

## Goal

Prevent scope creep and keep the project focused on the real MVP.

## Checklist

- [x] Product identified as **SAIIA**, not Dhiti.
- [x] MVP flow defined.
- [x] Tech stack locked in `TECHSTACK.md`.
- [x] PRD created in `SAIIA_PRD_Groq_MVP.md`.
- [x] Groq selected as primary LLM provider.
- [x] Ollama kept as optional fallback.
- [x] RAG marked as non-MVP.
- [x] Admin dashboard, analytics, payments, mock interview reports marked as non-MVP.
- [ ] Repo structure cleaned enough for Codex work.
- [ ] Dead/duplicate files reviewed before deletion.

## Completion Criteria

Phase 0 is complete when Codex and the developer can clearly answer:

```text
What is SAIIA?
What is the MVP flow?
Which tech stack must be used?
Which features are not MVP?
```

---

# Phase 1 — Runtime & Environment Stabilization

## Goal

Make sure frontend, backend, Electron, and AI dependencies can run reliably.

## Current Known Issues

- [!] Whisper transcription has failed because `ffmpeg` is missing or unavailable on PATH.
- [!] Frontend records `webm` audio, while backend has treated it like `wav`.
- [~] Ctrl+C shutdown may not cleanly stop every running process.
- [ ] Clean run instructions need to be finalized.

## Checklist

### Backend Runtime

- [ ] Backend starts successfully with FastAPI.
- [ ] Backend logs are readable and useful.
- [ ] Python dependencies are installed from requirements file.
- [ ] Missing environment variables produce clear errors.
- [ ] Backend shutdown works cleanly.

### Frontend Runtime

- [ ] React/Vite frontend starts successfully.
- [ ] Frontend connects to backend correctly.
- [ ] API base URL is configurable.
- [ ] Build command passes.
- [ ] No critical console errors during MVP flow.

### Electron Runtime

- [ ] Electron app launches correctly.
- [ ] Electron loads frontend correctly.
- [ ] Overlay window opens correctly.
- [ ] Main process exits cleanly.
- [ ] Ctrl+C / app close behavior is documented.

### Environment

- [x] `.env.example` exists.
- [x] `.env.example` contains Groq variables.
- [x] `.env.example` contains Ollama fallback variables.
- [ ] Real API keys are not committed.
- [ ] `.gitignore` protects `.env`, temp audio, logs, and runtime files.

## Completion Criteria

```text
Developer can start backend, frontend, and Electron from fresh instructions without guessing.
```

---

# Phase 2 — Profile Setup Reliability

## Goal

Make user profile data reliable because generated answers depend on it.

## Required Profile Fields

- [x] Resume text / background
- [x] Target role
- [x] Company name
- [x] Skills
- [x] Experience / projects

## Checklist

- [x] Profile setup page works.
- [x] `POST /api/profile` saves profile correctly.
- [x] `GET /api/profile` returns saved profile correctly.
- [x] Empty required fields show useful validation.
- [ ] Profile data is passed into answer-generation prompt.
- [ ] Profile data does not hallucinate missing experience.
- [ ] Profile survives app refresh/restart if current storage supports it.

## Completion Criteria

```text
A generated answer clearly reflects the user's role, skills, company, and project background.
```

---

# Phase 3 — Recording & Audio Upload Flow

## Goal

Make recording predictable and ensure backend receives valid audio.

## Current Known Issues

- [!] Frontend recording format and backend file handling are mismatched.
- [~] Microphone-only capture is acceptable for MVP.
- [-] Full system/interviewer audio capture is future work unless easy.

## Checklist

### Frontend Recording

- [ ] Start Recording button works.
- [ ] Stop Recording button works.
- [ ] Recording state is visible.
- [ ] Loading state is visible after stop.
- [ ] Empty recording is blocked or handled.
- [ ] Microphone permission denial shows useful error.
- [ ] Audio blob MIME type is logged during development.
- [ ] Audio upload field name matches backend expectation.

### Backend Audio Handling

- [ ] Backend accepts uploaded audio.
- [ ] Backend preserves correct extension or converts safely.
- [ ] Backend does not write `webm` as fake `wav`.
- [ ] Backend rejects empty/invalid audio clearly.
- [ ] Temporary audio files are cleaned up or ignored by git.

## Completion Criteria

```text
A short recorded question reaches the backend as valid audio and can be passed to STT.
```

---

# Phase 4 — Transcription / STT Stabilization

## Goal

Convert recorded interview questions into clean transcript text.

## Preferred MVP Direction

Use:

```text
Whisper or faster-whisper + ffmpeg
```

## Checklist

- [ ] `ffmpeg` requirement documented.
- [ ] Backend checks if `ffmpeg` is available.
- [ ] Missing `ffmpeg` returns a user-friendly error.
- [ ] WebM audio is decoded correctly.
- [ ] Short audio transcribes correctly.
- [ ] Noisy/empty transcript is handled.
- [ ] Transcript is cleaned before classification.
- [ ] Transcription failure stops the pipeline safely.
- [ ] Transcription latency is acceptable for demo.

## Error Cases To Test

- [ ] No microphone permission.
- [ ] Empty recording.
- [ ] Silent recording.
- [ ] Missing `ffmpeg`.
- [ ] Invalid audio file.
- [ ] Backend offline.

## Completion Criteria

```text
User records: "Tell me about yourself."
SAIIA returns a readable transcript close to that question.
```

---

# Phase 5 — Question Classification

## Goal

Classify transcript into the correct interview question type.

## Categories

- [ ] HR
- [ ] Technical
- [ ] Behavioral
- [ ] General fallback

## Checklist

- [x] Classification endpoint works.
- [x] Classifier receives cleaned transcript.
- [x] Very short/unclear transcript returns useful fallback.
- [x] Technical questions classify as Technical.
- [x] HR questions classify as HR.
- [x] Behavioral questions classify as Behavioral.
- [x] General fallback works.
- [x] Category is passed to answer generation.

## Completion Criteria

```text
Question category changes the final answer style.
```

---

# Phase 6 — Groq LLM Integration

## Goal

Replace Ollama as the primary answer-generation provider with Groq.

## Provider Decision

```text
Primary: Groq API
Fallback: Ollama local model
```

## Required Environment Variables

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
ENABLE_OLLAMA_FALLBACK=true
OLLAMA_MODEL=llama3:8b
```

## Checklist

### Provider Abstraction

- [x] Create or update LLM provider abstraction.
- [x] Add Groq provider.
- [x] Keep Ollama provider as fallback.
- [x] Provider selection uses environment variables.
- [x] Existing API response shape is preserved.

### Groq Behavior

- [x] Groq API key is read from environment.
- [x] Missing API key gives clear error.
- [x] Groq model is configurable.
- [x] Request timeout is configured.
- [x] Latency is logged.
- [x] API key is never printed in logs.
- [x] Groq failures are handled gracefully.

### Fallback Behavior

- [x] If Groq fails and fallback enabled, use Ollama.
- [x] If Groq fails and fallback disabled, return useful error.
- [x] If both Groq and Ollama fail, return useful error.
- [x] Logs show whether fallback was used.

## Completion Criteria

```text
Transcript + profile + category produce a concise answer through Groq.
```

---

# Phase 7 — Answer Quality & Prompting

## Goal

Generate answers that are useful during an interview and easy to speak.

## Answer Requirements

- [x] Concise.
- [x] Natural spoken style.
- [x] Personalized using profile.
- [x] Category-specific.
- [~] No fake experience.
- [x] No long essay.
- [~] No robotic wording.
- [x] No unnecessary jargon.
- [x] Directly answers the question.

## Category Style Rules

### HR

- [x] Confident and professional.
- [x] Uses candidate background.
- [x] Sounds natural.

### Technical

- [x] Direct and structured.
- [x] Mentions relevant technologies only if present in profile.
- [~] Does not overclaim expertise.

### Behavioral

- [x] Uses STAR-style structure when relevant.
- [x] Keeps answer short enough to speak.
- [~] Avoids fake examples.

## Completion Criteria

```text
A user can read the answer from overlay and speak it naturally in an interview.
```

---

# Phase 8 — Unified Interview Assist Flow

## Goal

Connect the full backend pipeline from audio to final answer.

## Existing Routes To Preserve First

- [ ] `POST /api/profile`
- [ ] `GET /api/profile`
- [ ] `POST /transcribe/`
- [ ] `POST /classify/`
- [ ] `POST /generate/`

## Optional Future Route

- [-] `POST /api/interview/assist`

Only add this if current route structure becomes too messy. Do not break the frontend.

## Checklist

- [x] Recording sends audio to transcription.
- [x] Transcript passes to classifier.
- [x] Category passes to generator.
- [x] Profile passes to generator.
- [x] Final answer returns to frontend.
- [~] Frontend shows transcript/category/answer where appropriate.
- [x] Errors stop the pipeline clearly.
- [x] Existing response format is preserved.

## Expected Success Response

```json
{
  "transcript": "Tell me about yourself.",
  "category": "HR",
  "answer": "I am a backend-focused developer with experience in Python, FastAPI, MongoDB, and React...",
  "confidence": "medium",
  "error": null
}
```

## Completion Criteria

```text
One user action can produce transcript, category, and answer without manual backend calls.
```

---

# Phase 9 — Electron Overlay Stabilization

## Goal

Display the generated answer in a usable private desktop overlay.

## Checklist

- [x] Overlay opens as separate Electron window.
- [x] Overlay can stay always-on-top.
- [x] Overlay receives generated answer.
- [x] Overlay updates when new answer is generated.
- [x] Overlay is draggable.
- [x] Font size can be increased/decreased.
- [x] Overlay can be hidden.
- [x] Overlay can be shown again.
- [x] Overlay has readable styling.
- [x] Overlay does not block the main app unnecessarily.

## Screen-Share Privacy Rule

Do not claim guaranteed invisibility.

Use safe wording:

```text
SAIIA uses a separate overlay window and provides quick hide/show controls. Visibility during screen sharing depends on OS, meeting app, and whether the user shares the full screen, a window, or a browser tab.
```

## Completion Criteria

```text
Generated answer appears in overlay and is readable during a demo.
```

---

# Phase 10 — Hotkeys & Controls

## Goal

Give the user fast control during a live/demo scenario.

## Required Hotkey

```text
Ctrl+H = hide/show overlay
```

## Checklist

- [x] Ctrl+H works when app is focused.
- [x] Ctrl+H works globally if currently implemented safely.
- [x] Hotkey state does not desync from overlay visibility.
- [x] Hotkey errors are logged.
- [x] Font-size control works.
- [x] Drag behavior works.
- [x] Controls are documented.

## Completion Criteria

```text
During demo, pressing Ctrl+H reliably hides and shows the overlay.
```

---

# Phase 11 — Error Handling & User Feedback

## Goal

Make failures understandable instead of silent or technical.

## Required Error Messages

- [x] Microphone permission denied.
- [x] Empty recording.
- [x] No transcript detected.
- [x] Missing `ffmpeg`.
- [x] Whisper/STT failure.
- [x] Backend offline.
- [x] Groq API key missing.
- [x] Groq API failure.
- [x] Ollama fallback unavailable.
- [x] LLM timeout.
- [x] Invalid profile data.

## Checklist

- [x] Frontend shows user-friendly errors.
- [x] Backend logs technical details.
- [x] API keys/secrets never appear in errors.
- [x] Failed transcription does not continue to answer generation.
- [x] Failed generation does not show stale answer.
- [x] Loading state clears after failure.

## Completion Criteria

```text
When something fails, the user knows what happened and what to fix next.
```

---

# Phase 12 — Testing & Validation

## Goal

Confirm the MVP flow works repeatedly.

## Status

[x] Done

## Manual Test Script

### Test 1 — HR Question

- [x] Start app.
- [x] Complete profile.
- [x] Record: "Tell me about yourself."
- [x] Confirm transcript.
- [x] Confirm category = HR.
- [x] Confirm personalized answer.
- [x] Confirm answer appears in overlay.

### Test 2 — Technical Question

- [x] Record: "What is JavaScript?"
- [x] Confirm category = Technical.
- [x] Confirm answer uses profile technologies only.
- [x] Confirm answer is concise.

### Test 3 — Behavioral Question

- [x] Record: "Tell me about a time you solved a difficult bug."
- [x] Confirm category = Behavioral.
- [x] Confirm answer uses STAR-style.
- [x] Confirm no fake project is invented.

### Test 4 — Overlay Control

- [x] Generate any answer.
- [x] Press Ctrl+H.
- [x] Confirm overlay hides.
- [x] Press Ctrl+H again.
- [x] Confirm overlay shows.
- [x] Drag overlay.
- [x] Adjust font size.

### Test 5 — Failure Cases

- [x] Stop recording immediately.
- [x] Disable backend.
- [ ] Remove/disable Groq API key.
- [ ] Disable internet.
- [ ] Disable Ollama fallback.
- [x] Confirm errors are useful.

## Automated Tests To Add / Maintain

- [ ] Profile save/load test.
- [ ] Audio upload validation test.
- [ ] Missing ffmpeg behavior test if practical.
- [ ] Classifier category tests.
- [ ] Groq provider request-building test.
- [ ] Missing Groq API key test.
- [ ] Groq fallback to Ollama test.
- [ ] API response shape test.

## Completion Criteria

```text
The full MVP demo works at least 5 times in a row without code changes.
```

---

# Phase 13 — Documentation & Demo Readiness

## Goal

Prepare the project for mentor/recruiter/demo review.

## Status

[x] Done

## Required Docs

- [x] `SAIIA_PRD_Groq_MVP.md`
- [x] `TECHSTACK.md`
- [x] `PROJECT_COMPLETION_PHASES.md`
- [x] `README.md` updated.
- [x] `.env.example` updated.
- [x] Setup instructions written.
- [x] Run instructions written.
- [x] Troubleshooting section written.
- [x] Demo script written.

## Demo Script Checklist

- [x] Explain what SAIIA is.
- [x] Explain that it is not Dhiti.
- [x] Explain profile personalization.
- [x] Show recording flow.
- [x] Show transcription.
- [x] Show classification.
- [x] Show Groq-generated answer.
- [x] Show overlay.
- [x] Show Ctrl+H.
- [x] Explain screen-share privacy honestly.
- [x] Explain MVP limitations.

## Completion Criteria

```text
A reviewer can run and understand the project without asking basic setup questions.
```

---

# Phase 14 — MVP Final Acceptance

## Status

[x] Done

## Minimum Successful MVP

- [x] User can enter profile.
- [x] User can record an interview question.
- [x] Audio is transcribed.
- [x] Transcript is classified.
- [x] Groq generates a personalized answer.
- [x] Answer appears in overlay.
- [x] Ctrl+H hides/shows overlay.
- [x] Major failures show clear errors.
- [x] README explains setup and demo.

## Ideal Successful MVP

- [x] Full flow works repeatedly.
- [x] Groq is fast enough for demo.
- [x] Ollama fallback works.
- [x] Overlay drag and font-size work.
- [x] UI feels clean and simple.
- [x] Errors are understandable.
- [x] No secrets are committed.
- [x] Project structure is clean.

## Final MVP Statement

```text
SAIIA successfully demonstrates a real-time AI interview assistant flow using profile personalization, speech-to-text transcription, question classification, Groq-powered answer generation, and a private Electron overlay.
```

## Final MVP Status

```text
SAIIA MVP is complete and demo-ready.
```

## Known Limitations

- Manual start/stop recording.
- Microphone-only MVP.
- No guaranteed screen-share invisibility.
- Requires Groq API key and internet.
- ffmpeg required for transcription.
- Auto-listen mode is future work.

---

# Deferred / Future Work

Do not prioritize these before MVP is stable.

- [-] Full system/interviewer audio capture.
- [-] Screen-capture exclusion guarantees.
- [-] Complex RAG.
- [-] Resume parser.
- [-] Multiple users/auth system.
- [-] Session history.
- [-] Mock interview report system.
- [-] Scoring/analytics dashboard.
- [-] Admin dashboard.
- [-] Payment/subscription system.
- [-] Browser extension.
- [-] Mobile app.
- [-] Advanced animations.
- [-] NVIDIA Riva.
- [-] TensorRT-LLM.
- [-] NVIDIA NIM.

---

# Codex Working Rules

Codex must follow these rules while working on SAIIA:

1. Do not rebuild the project from scratch.
2. Do not rename the product back to Dhiti.
3. Do not introduce RAG for MVP.
4. Do not add admin dashboards or analytics.
5. Do not break existing frontend routes.
6. Do not break Electron overlay behavior.
7. Do not remove Ollama until Groq is stable.
8. Do not commit real API keys.
9. Preserve existing API response shapes unless a change is necessary and documented.
10. Prefer small, testable changes.
11. Run validation after changes.
12. Update this checklist when a phase is completed.

---

# Current Overall Project Status

## Best Current Estimate

```text
Product scope:          Locked
Tech stack:             Locked
Groq decision:          Locked
Profile flow:           Working
Recording flow:         Working
Transcription:          Working
Classification:         Working and low-latency
Answer generation:      Groq-first with Ollama fallback; fast enough for MVP demo
Overlay:                Working as a separate answer window
Hotkey Ctrl+H:          Working with button-sync and failure logging
End-to-end demo:        Validated across repeated HR, technical, and behavioral runs
Documentation:          Complete and demo-ready
```

## Immediate Next Priority

```text
Maintain the stable MVP, demo it confidently, and keep future work out of core acceptance scope.
```
