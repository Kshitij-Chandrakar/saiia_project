-- C7 follow-up for the already-applied transcript storage migration.
-- Locks transcript entry creation to the backend RPC/service-role path only.

revoke insert on table public.interview_session_transcript_entries from authenticated;

drop policy if exists interview_session_transcript_insert_own on public.interview_session_transcript_entries;
