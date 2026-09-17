-- Session-scoped user-authored answers. These rows are intentionally separate
-- from AI transcript entries, notes, and exported session content.

create table if not exists public.interview_session_my_answers (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null references public.interview_sessions(id) on delete cascade,
  body text not null,
  position integer not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_my_answers_body_length check (char_length(body) between 1 and 24000),
  constraint interview_session_my_answers_position_positive check (position > 0)
);

create unique index if not exists interview_session_my_answers_session_position_idx
  on public.interview_session_my_answers (session_id, position);

create index if not exists interview_session_my_answers_user_created_idx
  on public.interview_session_my_answers (user_id, created_at asc, id asc);

alter table public.interview_session_my_answers enable row level security;
alter table public.interview_session_my_answers force row level security;

drop policy if exists interview_session_my_answers_select_own on public.interview_session_my_answers;
create policy interview_session_my_answers_select_own
  on public.interview_session_my_answers
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

drop policy if exists interview_session_my_answers_insert_own on public.interview_session_my_answers;
revoke insert, update, delete on table public.interview_session_my_answers from authenticated;
grant select on table public.interview_session_my_answers to authenticated;
grant select, insert on table public.interview_session_my_answers to service_role;

create or replace function public.create_interview_session_my_answer(
  p_user_id uuid,
  p_session_id uuid,
  p_body text
)
returns public.interview_session_my_answers
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  owned_session public.interview_sessions%rowtype;
  created_answer public.interview_session_my_answers%rowtype;
  lock_key bigint;
begin
  if p_body is null or char_length(btrim(p_body)) = 0 then
    raise exception 'answer body is required' using errcode = 'P0001';
  end if;
  if char_length(btrim(p_body)) > 24000 then
    raise exception 'answer body is too long' using errcode = 'P0001';
  end if;

  set local lock_timeout = '2s';
  set local statement_timeout = '5s';
  lock_key := hashtextextended(p_session_id::text, 0);
  perform pg_advisory_xact_lock(lock_key);

  select *
  into owned_session
  from public.interview_sessions as s
  where s.id = p_session_id
    and s.user_id = p_user_id
    and s.status = 'active'
  for update;

  if owned_session.id is null then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;

  insert into public.interview_session_my_answers (user_id, session_id, body, position)
  values (
    p_user_id,
    p_session_id,
    btrim(p_body),
    coalesce((select max(position) from public.interview_session_my_answers where session_id = p_session_id), 0) + 1
  )
  returning * into created_answer;

  return created_answer;
end;
$$;

revoke all on function public.create_interview_session_my_answer(uuid, uuid, text) from public;
revoke all on function public.create_interview_session_my_answer(uuid, uuid, text) from anon;
revoke all on function public.create_interview_session_my_answer(uuid, uuid, text) from authenticated;
grant execute on function public.create_interview_session_my_answer(uuid, uuid, text) to service_role;

comment on table public.interview_session_my_answers is
  'Immutable user-authored answers scoped to an owned active interview session; excluded from AI transcripts, notes, and exports.';
