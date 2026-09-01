# C8 - AI Notes Generation

## Status

Implemented locally on 2026-08-29, pending manual live verification.

## Scope Included

- Supabase `interview_session_ai_notes` table for session-owned AI notes storage
- Authenticated AI notes APIs for fetch and explicit generation
- Notes generation from stored transcript entries when the user clicks Generate AI Notes
- Website dashboard AI notes view with loading, empty, and retry states
- Safe regenerate flow for existing notes
- Transcript-only note generation with bounded prompt input

## Explicitly Not Included

- C9 Ask AI memory
- chat-with-transcript
- transcript summarization beyond the stored notes output
- transcript vector memory or semantic retrieval
- audio storage
- screenshot or OCR image storage
- payments
- admin console
- major UI redesign

## Supabase Migration

- `supabase/migrations/20260829223000_add_interview_session_ai_notes.sql`

## Backend Service and Routes

Service:

- `backend/app/cloud/interview_notes.py`

Routes:

- `GET /api/interview-sessions/{session_id}/notes`
- `POST /api/interview-sessions/{session_id}/notes/generate`

## Notes Schema

Stored fields:

- `id`
- `user_id`
- `session_id`
- `status`
- `notes_markdown`
- `summary`
- `strengths`
- `improvement_areas`
- `technical_topics`
- `key_questions`
- `suggested_followups`
- `provider`
- `model`
- `generation_ms`
- `transcript_entry_count`
- `generated_at`
- `created_at`
- `updated_at`

Design decisions:

- one latest notes row per session via unique `session_id`
- backend-only write path using service-role backend access
- authenticated users can read only their own notes rows through RLS

## AI Generation Behavior

- Notes are generated only from stored transcript entries plus safe session metadata such as title, role, company, and job-description preview.
- If `session_id` is missing, there is no notes generation path because C8 is dashboard-driven and explicit.
- Missing or cross-user sessions return the existing session-not-found behavior.
- Empty transcripts return `409` with: `This session does not have transcript entries yet.`
- Provider failures return a safe backend error without exposing prompts, tokens, or raw provider payloads.
- Notes use careful wording such as "Based on this transcript" and do not make hiring decisions.

## Security Decisions

- `user_id` comes only from the verified JWT.
- Supabase RLS enforces ownership on reads.
- Authenticated direct insert/update is not granted for notes rows.
- Service-role access stays in the backend only.
- No auth tokens, raw prompts, resume chunks, screenshots, or audio are stored in notes.
- Prompt context is bounded by transcript-entry count and character limits before calling the model.

## Website Dashboard Behavior

- Each session card keeps transcript view and transcript downloads from C7.
- Each session card now adds `Generate AI Notes` and `View AI Notes`.
- `View AI Notes` fetches saved notes.
- `Generate AI Notes` explicitly creates or regenerates notes for that session.
- Failed notes load shows an error state with retry.
- Missing notes show a clear empty state instead of pretending notes already exist.

## Manual Verification Checklist

- Start backend
- Start Electron
- Login
- Create session
- Ask 2 questions
- End session
- Open website dashboard
- View transcript and confirm entries exist
- Click Generate AI Notes
- Confirm notes appear
- Refresh dashboard
- Confirm saved notes can be viewed again
- Verify no tokens in renderer console
- Verify notes row exists in Supabase

## Validation Summary

- `python -m compileall -q backend/app` passed
- `PYTHONPATH=backend pytest backend/tests -q` passed: `635 passed, 1 skipped`
- `node --test "src/*.test.js" "src/auth/*.test.js"` passed in `frontend/`: `197 passed`
- `npm run build` passed in `frontend/`
- `scripts/pre_commit_audit.ps1` passed

## Out-of-Scope Reminder

- C9 Ask AI memory is not started
- no transcript vector memory or chat-over-history is implemented in C8
