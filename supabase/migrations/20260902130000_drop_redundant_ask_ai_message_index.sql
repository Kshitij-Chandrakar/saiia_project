-- C9 follow-up: the unique session/turn index covers the message ordering lookup.
drop index if exists public.interview_session_ask_ai_session_created_idx;
