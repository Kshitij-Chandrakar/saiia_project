-- C9 session-scoped Ask AI follow-up memory.
-- Stores text-only user/assistant messages for one owned interview session.

create table if not exists public.interview_session_ask_ai_messages (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null references public.interview_sessions(id) on delete cascade,
  role text not null,
  message_text text not null,
  turn_index integer not null,
  provider text null,
  model text null,
  generation_ms integer null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_ask_ai_role_check check (role in ('user', 'assistant')),
  constraint interview_session_ask_ai_turn_index_positive check (turn_index > 0),
  constraint interview_session_ask_ai_message_length check (char_length(message_text) between 1 and 12000),
  constraint interview_session_ask_ai_metadata_object check (jsonb_typeof(metadata) = 'object'),
  constraint interview_session_ask_ai_metadata_size check (octet_length(metadata::text) <= 4000),
  constraint interview_session_ask_ai_generation_ms_check check (
    generation_ms is null or (generation_ms >= 0 and generation_ms <= 3600000)
  )
);

create unique index if not exists interview_session_ask_ai_session_turn_idx
  on public.interview_session_ask_ai_messages (session_id, turn_index);

create index if not exists interview_session_ask_ai_session_created_idx
  on public.interview_session_ask_ai_messages (session_id, turn_index asc, created_at asc, id asc);

alter table public.interview_session_ask_ai_messages enable row level security;
alter table public.interview_session_ask_ai_messages force row level security;

drop policy if exists interview_session_ask_ai_select_own on public.interview_session_ask_ai_messages;
create policy interview_session_ask_ai_select_own
  on public.interview_session_ask_ai_messages
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

create or replace function public.create_interview_session_ask_ai_message(
  p_user_id uuid,
  p_session_id uuid,
  p_role text,
  p_message_text text,
  p_provider text,
  p_model text,
  p_generation_ms integer,
  p_metadata jsonb
)
returns table (
  ask_ai_message_id uuid,
  turn_index integer,
  status text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  owned_session public.interview_sessions%rowtype;
  created_message public.interview_session_ask_ai_messages%rowtype;
  lock_key bigint;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  lock_key := hashtextextended(p_session_id::text || ':ask-ai', 0);
  perform pg_advisory_xact_lock(lock_key);

  select *
  into owned_session
  from public.interview_sessions as s
  where s.id = p_session_id
    and s.user_id = p_user_id;

  if owned_session.id is null then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;

  insert into public.interview_session_ask_ai_messages (
    user_id,
    session_id,
    role,
    message_text,
    turn_index,
    provider,
    model,
    generation_ms,
    metadata
  )
  values (
    p_user_id,
    p_session_id,
    p_role,
    p_message_text,
    coalesce(
      (
        select max(m.turn_index)
        from public.interview_session_ask_ai_messages as m
        where m.session_id = p_session_id
      ),
      0
    ) + 1,
    nullif(coalesce(p_provider, ''), ''),
    nullif(coalesce(p_model, ''), ''),
    p_generation_ms,
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning * into created_message;

  return query
  select created_message.id, created_message.turn_index, 'completed'::text;
end;
$$;

grant select on table public.interview_session_ask_ai_messages to authenticated;
grant select, insert, update, delete on table public.interview_session_ask_ai_messages to service_role;

revoke all on function public.create_interview_session_ask_ai_message(
  uuid, uuid, text, text, text, text, integer, jsonb
) from public;
revoke all on function public.create_interview_session_ask_ai_message(
  uuid, uuid, text, text, text, text, integer, jsonb
) from anon;
revoke all on function public.create_interview_session_ask_ai_message(
  uuid, uuid, text, text, text, text, integer, jsonb
) from authenticated;
grant execute on function public.create_interview_session_ask_ai_message(
  uuid, uuid, text, text, text, text, integer, jsonb
) to service_role;

comment on function public.create_interview_session_ask_ai_message(
  uuid, uuid, text, text, text, text, integer, jsonb
) is
  'C9 backend-only Ask AI message create RPC. Validates owned session access and atomically assigns per-session turn_index without storing prompts, resume chunks, screenshots, audio, or tokens.';
