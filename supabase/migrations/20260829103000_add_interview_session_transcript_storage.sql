-- C7 transcript storage, viewing, and download.
-- Stores text-only interview transcript entries under durable interview sessions.

create table if not exists public.interview_session_transcript_entries (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null references public.interview_sessions(id) on delete cascade,
  request_id text null,
  turn_index integer not null,
  source text null,
  question_text text not null,
  answer_text text not null,
  category text null,
  provider text null,
  model text null,
  generation_ms integer null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_transcript_turn_index_positive check (turn_index > 0),
  constraint interview_session_transcript_request_id_length check (request_id is null or char_length(request_id) between 1 and 120),
  constraint interview_session_transcript_question_length check (char_length(question_text) between 1 and 4000),
  constraint interview_session_transcript_answer_length check (char_length(answer_text) between 1 and 24000),
  constraint interview_session_transcript_metadata_object check (jsonb_typeof(metadata) = 'object'),
  constraint interview_session_transcript_metadata_size check (octet_length(metadata::text) <= 4000)
);

create index if not exists interview_session_transcript_session_turn_created_idx
  on public.interview_session_transcript_entries (session_id, turn_index asc, created_at asc, id asc);

create unique index if not exists interview_session_transcript_session_turn_idx
  on public.interview_session_transcript_entries (session_id, turn_index);

create unique index if not exists interview_session_transcript_session_request_idx
  on public.interview_session_transcript_entries (session_id, request_id)
  where request_id is not null;

alter table public.interview_session_transcript_entries enable row level security;
alter table public.interview_session_transcript_entries force row level security;

drop policy if exists interview_session_transcript_select_own on public.interview_session_transcript_entries;
create policy interview_session_transcript_select_own
  on public.interview_session_transcript_entries
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

drop policy if exists interview_session_transcript_insert_own on public.interview_session_transcript_entries;
create policy interview_session_transcript_insert_own
  on public.interview_session_transcript_entries
  for insert
  to authenticated
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.interview_sessions as s
      where s.id = session_id
        and s.user_id = auth.uid()
    )
  );

create or replace function public.create_interview_session_transcript_entry(
  p_user_id uuid,
  p_session_id uuid,
  p_request_id text,
  p_source text,
  p_question_text text,
  p_answer_text text,
  p_category text,
  p_provider text,
  p_model text,
  p_generation_ms integer,
  p_metadata jsonb
)
returns table (
  transcript_entry_id uuid,
  turn_index integer,
  replayed boolean,
  status text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  owned_session public.interview_sessions%rowtype;
  existing_entry public.interview_session_transcript_entries%rowtype;
  created_entry public.interview_session_transcript_entries%rowtype;
  lock_key bigint;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  lock_key := hashtextextended(p_session_id::text, 0);
  perform pg_advisory_xact_lock(lock_key);

  select *
  into owned_session
  from public.interview_sessions as s
  where s.id = p_session_id
    and s.user_id = p_user_id
  for update;

  if owned_session.id is null then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;

  if owned_session.status <> 'active'
    and (
      owned_session.ended_at is null
      or owned_session.ended_at < timezone('utc', now()) - interval '5 minutes'
    )
  then
    raise exception 'interview session is closed' using errcode = 'P0001';
  end if;

  if nullif(coalesce(p_request_id, ''), '') is not null then
    select *
    into existing_entry
    from public.interview_session_transcript_entries as e
    where e.session_id = p_session_id
      and e.request_id = p_request_id
    limit 1;

    if existing_entry.id is not null then
      return query
      select existing_entry.id, existing_entry.turn_index, true, 'completed'::text;
      return;
    end if;
  end if;

  insert into public.interview_session_transcript_entries (
    user_id,
    session_id,
    request_id,
    turn_index,
    source,
    question_text,
    answer_text,
    category,
    provider,
    model,
    generation_ms,
    metadata
  )
  values (
    p_user_id,
    p_session_id,
    nullif(coalesce(p_request_id, ''), ''),
    coalesce(
      (
        select max(e.turn_index)
        from public.interview_session_transcript_entries as e
        where e.session_id = p_session_id
      ),
      0
    ) + 1,
    nullif(coalesce(p_source, ''), ''),
    p_question_text,
    p_answer_text,
    nullif(coalesce(p_category, ''), ''),
    nullif(coalesce(p_provider, ''), ''),
    nullif(coalesce(p_model, ''), ''),
    p_generation_ms,
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning * into created_entry;

  return query
  select created_entry.id, created_entry.turn_index, false, 'completed'::text;
end;
$$;

grant select, insert on table public.interview_session_transcript_entries to authenticated;
grant select, insert, update, delete on table public.interview_session_transcript_entries to service_role;

revoke all on function public.create_interview_session_transcript_entry(
  uuid, uuid, text, text, text, text, text, text, text, integer, jsonb
) from public;
revoke all on function public.create_interview_session_transcript_entry(
  uuid, uuid, text, text, text, text, text, text, text, integer, jsonb
) from anon;
revoke all on function public.create_interview_session_transcript_entry(
  uuid, uuid, text, text, text, text, text, text, text, integer, jsonb
) from authenticated;
grant execute on function public.create_interview_session_transcript_entry(
  uuid, uuid, text, text, text, text, text, text, text, integer, jsonb
) to service_role;

comment on function public.create_interview_session_transcript_entry(
  uuid, uuid, text, text, text, text, text, text, text, integer, jsonb
) is
  'C7 backend-only transcript entry create RPC. Validates owned session access, allows a short late-write grace window, atomically assigns per-session turn_index, and replays duplicate request_id writes without storing screenshots, audio, resume chunks, or tokens.';
