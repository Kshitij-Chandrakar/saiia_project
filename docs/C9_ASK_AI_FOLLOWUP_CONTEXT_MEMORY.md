# C9 - Ask AI and Follow-up Context Memory

## Status

Implemented locally / pending manual live verification.

## Scope Included

- Session-scoped Ask AI message storage.
- Authenticated Ask AI APIs for asking questions and listing saved messages.
- Ask AI context built only from the selected interview session.
- Context includes stored transcript entries, saved AI notes when available, safe session metadata, and recent Ask AI messages.
- Website dashboard Ask AI panel with message history, input, loading state, and retry/error handling.
- Safe empty-context behavior when a session has no transcript or notes.

## Explicitly Not Included

- Global user memory.
- Transcript vector memory or semantic transcript search.
- Chat-over-all-history across sessions.
- C10 email system.
- Payments, pricing, usage gates, or admin console.
- Browser extension work.
- Major dashboard or website redesign.

## Supabase Migration

- `supabase/migrations/20260901103000_add_interview_session_ask_ai_messages.sql`

The migration creates `interview_session_ask_ai_messages` with RLS enabled and forced. Authenticated users can read only messages for sessions they own. Direct authenticated inserts are not granted; backend/service-role creation uses `public.create_interview_session_ask_ai_message`.

## Backend Routes

- `POST /api/interview-sessions/{session_id}/ask-ai`
- `GET /api/interview-sessions/{session_id}/ask-ai/messages`

## Backend Service

- `backend/app/cloud/interview_ask_ai.py`

The service validates the session owner, bounds question/context sizes, fetches transcript entries, optionally fetches saved AI notes, includes recent Ask AI messages for follow-up continuity, calls the configured OpenAI model, and stores user/assistant messages.

## Context Rules

- `user_id` comes from the verified JWT only.
- `session_id` must belong to the authenticated user.
- Transcript entries are limited by count and per-field length.
- AI notes are included only for the same session when requested and available.
- Recent Ask AI messages are limited and session-scoped.
- No unrelated sessions or global memory are used.
- Empty transcript with no notes returns a clear conflict response.

## Security Decisions

- RLS ownership policy protects reads.
- Backend/service-role path owns message creation.
- No auth tokens, service-role keys, raw prompts, resume chunks, screenshots, or audio are stored.
- Stored content is text-only user and assistant messages plus small safe metadata.
- Provider errors are mapped to safe user-facing messages.

## Website Behavior

- Each dashboard session card keeps transcript and AI Notes controls.
- Each session card adds an `Ask AI` button.
- Opening Ask AI loads saved messages for that session only.
- Sending a question stores a user message and assistant response.
- Switching sessions clears prior Ask AI panel state so messages do not leak across cards.
- Failed loads or sends show an error and retry affordance.

## Manual Verification Checklist

- Start backend.
- Start Electron.
- Login.
- Create a session.
- Ask 2 interview questions.
- End session.
- Open dashboard.
- View transcript.
- Generate AI Notes.
- Open Ask AI.
- Ask: `What should I improve?`
- Ask: `Give me a better answer for the second question`
- Confirm answers are based on the same session transcript/notes.
- Refresh dashboard.
- Reopen Ask AI.
- Confirm message history persists.
- Create a session with no transcript entries and confirm Ask AI shows an insufficient context error.
- Verify no auth token or service-role key is exposed in browser/Electron console.
- Verify no raw OpenAI prompt, resume chunks, screenshots, or audio are stored.

## Validation Summary

Latest local validation during implementation:

- Backend compile passed.
- Backend tests passed: 660 passed, 1 skipped.
- Frontend tests passed: 199 passed.
- Frontend build passed.
- `git diff --check` passed.
- `scripts/pre_commit_audit.ps1` passed.
