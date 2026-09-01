-- C9 Ask AI request idempotency keys.
-- Keeps replay control backend-owned without exposing prompts or transcript payloads.

create table if not exists public.interview_session_ask_ai_request_keys (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null references public.interview_sessions(id) on delete cascade,
  request_id text not null,
  status text not null default 'processing',
  user_message_id uuid null references public.interview_session_ask_ai_messages(id) on delete set null,
  assistant_message_id uuid null references public.interview_session_ask_ai_messages(id) on delete set null,
  payload_hash text null,
  error_code text null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_ask_ai_request_key_status_check check (status in ('processing', 'completed', 'failed')),
  constraint interview_session_ask_ai_request_key_request_id_length check (char_length(request_id) between 1 and 128),
  constraint interview_session_ask_ai_request_key_request_id_format check (request_id ~ '^[A-Za-z0-9._~-]+$'),
  constraint interview_session_ask_ai_request_key_payload_hash_length check (payload_hash is null or char_length(payload_hash) <= 128),
  constraint interview_session_ask_ai_request_key_error_code_length check (error_code is null or char_length(error_code) <= 80),
  constraint interview_session_ask_ai_request_key_unique unique (user_id, session_id, request_id)
);

create index if not exists interview_session_ask_ai_request_key_session_idx
  on public.interview_session_ask_ai_request_keys (user_id, session_id, created_at desc);

alter table public.interview_session_ask_ai_request_keys enable row level security;
alter table public.interview_session_ask_ai_request_keys force row level security;

drop policy if exists interview_session_ask_ai_request_key_select_own on public.interview_session_ask_ai_request_keys;
create policy interview_session_ask_ai_request_key_select_own
  on public.interview_session_ask_ai_request_keys
  for select
  to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1
      from public.interview_sessions as s
      where s.id = session_id
        and s.user_id = auth.uid()
    )
  );

grant select on table public.interview_session_ask_ai_request_keys to authenticated;
grant select, insert, update, delete on table public.interview_session_ask_ai_request_keys to service_role;

comment on table public.interview_session_ask_ai_request_keys is
  'C9 backend-owned Ask AI request idempotency keys. Stores request ids, status, and message ids only; no prompts, transcript payloads, resume chunks, screenshots, audio, tokens, or secrets.';
