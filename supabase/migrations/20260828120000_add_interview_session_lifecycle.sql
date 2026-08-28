-- C6.3 durable interview session lifecycle and cloud session storage.
-- Adds authenticated, user-owned session history with backend-safe idempotent
-- creation and simple ended/abandoned lifecycle states.

create table if not exists public.interview_sessions (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  selected_resume_id uuid null references public.resumes(id) on delete set null,
  job_context_id uuid null references public.job_contexts(id) on delete set null,
  title text null,
  target_role text null,
  company_name text null,
  job_description_preview text null,
  status text not null default 'active',
  started_at timestamptz not null default timezone('utc', now()),
  ended_at timestamptz null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint interview_sessions_status_check check (status in ('active', 'ended', 'abandoned')),
  constraint interview_sessions_active_end_check check (
    (status = 'active' and ended_at is null) or
    (status in ('ended', 'abandoned') and ended_at is not null)
  )
);

create index if not exists interview_sessions_user_started_id_idx
  on public.interview_sessions (user_id, started_at desc, id desc);

create unique index if not exists interview_sessions_one_active_per_user_idx
  on public.interview_sessions (user_id)
  where status = 'active' and ended_at is null;

alter table public.interview_sessions enable row level security;
alter table public.interview_sessions force row level security;

drop policy if exists interview_sessions_select_own on public.interview_sessions;
create policy interview_sessions_select_own
  on public.interview_sessions
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists interview_sessions_insert_own on public.interview_sessions;
create policy interview_sessions_insert_own
  on public.interview_sessions
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists interview_sessions_update_own on public.interview_sessions;
create policy interview_sessions_update_own
  on public.interview_sessions
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists set_interview_sessions_updated_at on public.interview_sessions;
create trigger set_interview_sessions_updated_at
before update on public.interview_sessions
for each row execute function public.set_updated_at();

create table if not exists public.interview_session_idempotency_keys (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  status text not null default 'processing',
  interview_session_id uuid references public.interview_sessions(id) on delete set null,
  expires_at timestamptz not null default timezone('utc', now()) + interval '24 hours',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_idempotency_status_check check (status in ('processing', 'completed'))
);

create unique index if not exists interview_session_idempotency_user_key_idx
  on public.interview_session_idempotency_keys (user_id, idempotency_key);

create index if not exists interview_session_idempotency_expires_at_idx
  on public.interview_session_idempotency_keys (expires_at);

alter table public.interview_session_idempotency_keys enable row level security;
alter table public.interview_session_idempotency_keys force row level security;

drop trigger if exists set_interview_session_idempotency_updated_at on public.interview_session_idempotency_keys;
create trigger set_interview_session_idempotency_updated_at
before update on public.interview_session_idempotency_keys
for each row execute function public.set_updated_at();

create or replace function public.create_interview_session_with_idempotency(
  p_user_id uuid,
  p_idempotency_key text,
  p_request_hash text,
  p_selected_resume_id uuid,
  p_job_context_id uuid,
  p_title text,
  p_target_role text,
  p_company_name text,
  p_job_description_preview text
)
returns table (
  interview_session_id uuid,
  replayed boolean,
  status text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  reservation public.interview_session_idempotency_keys%rowtype;
  existing_session public.interview_sessions%rowtype;
  created_session public.interview_sessions%rowtype;
  lock_key bigint;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  lock_key := hashtextextended(p_user_id::text, 0);
  perform pg_advisory_xact_lock(lock_key);

  delete from public.interview_session_idempotency_keys
  where expires_at < timezone('utc', now());

  insert into public.interview_session_idempotency_keys (
    user_id,
    idempotency_key,
    request_hash,
    status
  )
  values (
    p_user_id,
    p_idempotency_key,
    p_request_hash,
    'processing'
  )
  on conflict (user_id, idempotency_key) do nothing
  returning * into reservation;

  if reservation.id is null then
    select *
    into reservation
    from public.interview_session_idempotency_keys
    where user_id = p_user_id
      and idempotency_key = p_idempotency_key
    for update;

    if reservation.request_hash <> p_request_hash then
      raise exception 'interview session idempotency key conflict' using errcode = 'P0001';
    end if;

    if reservation.status = 'completed' and reservation.interview_session_id is not null then
      interview_session_id := reservation.interview_session_id;
      replayed := true;
      status := 'completed';
      return next;
      return;
    end if;

    raise exception 'interview session idempotency request in progress' using errcode = 'P0001';
  end if;

  if p_selected_resume_id is not null and not exists (
    select 1
    from public.resumes
    where id = p_selected_resume_id
      and user_id = p_user_id
  ) then
    raise exception 'selected resume was not found' using errcode = 'P0001';
  end if;

  if p_job_context_id is not null and not exists (
    select 1
    from public.job_contexts
    where id = p_job_context_id
      and user_id = p_user_id
  ) then
    raise exception 'job context was not found' using errcode = 'P0001';
  end if;

  select *
  into existing_session
  from public.interview_sessions
  where user_id = p_user_id
    and status = 'active'
    and ended_at is null
  order by started_at desc, id desc
  limit 1
  for update;

  if existing_session.id is not null then
    if existing_session.started_at >= timezone('utc', now()) - interval '2 minutes'
      and coalesce(existing_session.selected_resume_id, '00000000-0000-0000-0000-000000000000'::uuid)
        = coalesce(p_selected_resume_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and coalesce(existing_session.job_context_id, '00000000-0000-0000-0000-000000000000'::uuid)
        = coalesce(p_job_context_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and coalesce(existing_session.title, '') = coalesce(p_title, '')
      and coalesce(existing_session.target_role, '') = coalesce(p_target_role, '')
      and coalesce(existing_session.company_name, '') = coalesce(p_company_name, '')
      and coalesce(existing_session.job_description_preview, '') = coalesce(p_job_description_preview, '')
    then
      update public.interview_session_idempotency_keys
      set status = 'completed',
          interview_session_id = existing_session.id,
          expires_at = timezone('utc', now()) + interval '24 hours'
      where id = reservation.id;

      interview_session_id := existing_session.id;
      replayed := true;
      status := 'completed';
      return next;
      return;
    end if;

    update public.interview_sessions
    set status = 'abandoned',
        ended_at = timezone('utc', now())
    where id = existing_session.id
      and status = 'active'
      and ended_at is null;
  end if;

  insert into public.interview_sessions (
    user_id,
    selected_resume_id,
    job_context_id,
    title,
    target_role,
    company_name,
    job_description_preview,
    status,
    started_at,
    ended_at
  )
  values (
    p_user_id,
    p_selected_resume_id,
    p_job_context_id,
    nullif(coalesce(p_title, ''), ''),
    nullif(coalesce(p_target_role, ''), ''),
    nullif(coalesce(p_company_name, ''), ''),
    nullif(coalesce(p_job_description_preview, ''), ''),
    'active',
    timezone('utc', now()),
    null
  )
  returning * into created_session;

  update public.interview_session_idempotency_keys
  set status = 'completed',
      interview_session_id = created_session.id,
      expires_at = timezone('utc', now()) + interval '24 hours'
  where id = reservation.id;

  interview_session_id := created_session.id;
  replayed := false;
  status := 'completed';
  return next;
end;
$$;

grant select, insert, update on table public.interview_sessions to authenticated;
grant select, insert, update, delete on table public.interview_sessions to service_role;
grant select, insert, update, delete on table public.interview_session_idempotency_keys to service_role;

revoke all on function public.create_interview_session_with_idempotency(
  uuid, text, text, uuid, uuid, text, text, text, text
) from public;
revoke all on function public.create_interview_session_with_idempotency(
  uuid, text, text, uuid, uuid, text, text, text, text
) from anon;
revoke all on function public.create_interview_session_with_idempotency(
  uuid, text, text, uuid, uuid, text, text, text, text
) from authenticated;
grant execute on function public.create_interview_session_with_idempotency(
  uuid, text, text, uuid, uuid, text, text, text, text
) to service_role;

comment on function public.create_interview_session_with_idempotency(
  uuid, text, text, uuid, uuid, text, text, text, text
) is
  'C6.3 backend-only interview session create RPC. Uses per-user advisory locking, validates owned resume/job context ids, replays duplicate starts, abandons stale active sessions, and stores only safe job-description preview text.';
