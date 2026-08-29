# C7 - Transcript Storage, Viewing, and Download

## Status

Implemented locally. Manual live verification is still pending.

## Scope Included

- transcript entries table
- authenticated transcript APIs
- generation-to-transcript storage when `session_id` is present
- website dashboard transcript view
- `.txt` and `.md` transcript download
- safe failure behavior
- no transcript storage when `session_id` is absent

## Explicitly Not Included

- C8 AI Notes
- C9 Ask AI memory
- transcript summarization
- audio storage
- screenshot or OCR image storage
- payments
- admin console
- major UI redesign

## Supabase Migration

This phase adds:

- `supabase/migrations/20260829103000_add_interview_session_transcript_storage.sql`

## Backend Routes

- `POST /api/interview-sessions/{session_id}/transcript-entries`
- `GET /api/interview-sessions/{session_id}/transcript-entries`
- `GET /api/interview-sessions/{session_id}/transcript/download?format=txt`
- `GET /api/interview-sessions/{session_id}/transcript/download?format=md`

## Backend Service

Transcript storage and export behavior live in:

- `backend/app/cloud/interview_transcripts.py`

## Generation Behavior

- A transcript entry is stored only when `session_id` is present on the generation request.
- If `session_id` is invalid or belongs to another user, the request is rejected safely.
- If transcript storage has a transient failure, normal answer generation still succeeds and the transcript store failure is handled as a non-fatal side effect.
- If `session_id` is absent, generation continues with no transcript write attempt.
- Stored transcript entries are text-only. No raw audio, screenshots, OCR images, resume chunks, auth tokens, or service-role secrets are stored.

## Security Decisions

- `user_id` comes only from the verified JWT.
- Supabase RLS enforces per-user ownership.
- The renderer does not receive the service-role key.
- Transcript rows store text-only entries.
- Transcript fields are bounded for size.
- Metadata is limited to safe structured values only.

## Website Behavior

- Each dashboard session can show `View transcript`.
- Each dashboard session can show `Download .txt`.
- Each dashboard session can show `Download .md`.
- Failed transcript loads render an explicit error state instead of a misleading empty state.

## Manual Verification Checklist

- Start Session
- ask 2 questions
- End Session
- open dashboard
- View transcript
- Download `.txt`
- Download `.md`
- verify no tokens in renderer console
- verify transcript entries in Supabase

## Validation Summary

Latest local validation snapshot:

- backend compile passed
- backend tests passed: `598 passed, 1 skipped`
- frontend tests passed: `195 passed`
- frontend build passed
- `pre_commit_audit` passed

## Notes

- This document covers C7 only.
- C8 AI Notes is not started.
- C9 Ask AI memory is not started.
