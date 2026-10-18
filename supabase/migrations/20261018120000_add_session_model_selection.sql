-- Phase 2 storage only. Historical rows stay NULL; no transcript writes.
-- Existing grants: authenticated SELECT/INSERT/UPDATE on sessions; RPC service_role only.
-- Preserve those grants and RLS; enforce only model-field/owner invariants with triggers.
alter table public.interview_sessions add column selected_model_key text null;
alter table public.interview_sessions add constraint interview_sessions_model_key_check
  check (selected_model_key is null or selected_model_key in
    ('gpt-5.6-luna','gpt-5.6-terra','gpt-oss-120b','gemini-3.5-flash-lite','gemini-3.6-flash'));

-- Hard code-readiness gate. No caller parameter or environment switch can enable it.
-- A future routing migration must replace this function alongside actual routing.
create or replace function public.session_model_routing_ready()
returns boolean language sql stable set search_path = pg_catalog as $$ select false $$;
revoke all on function public.session_model_routing_ready() from public, anon, authenticated;
grant execute on function public.session_model_routing_ready() to service_role;

create or replace function public.protect_interview_session_model()
returns trigger language plpgsql security definer set search_path = public, pg_catalog as $$
begin
  if TG_OP = 'UPDATE' then
    if new.selected_model_key is distinct from old.selected_model_key or new.user_id is distinct from old.user_id then
      raise exception 'session selection and owner are immutable' using errcode = 'P0001';
    end if;
  elsif new.selected_model_key is not null then
    if coalesce(auth.role(), '') <> 'service_role' then
      raise exception 'model selection requires backend creation' using errcode = '42501';
    end if;
    if not public.session_model_routing_ready() then
      raise exception 'model-bound session creation is not available yet' using errcode = 'P0001';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.protect_interview_session_model() from public, anon, authenticated;
create trigger protect_interview_session_model before insert or update on public.interview_sessions
for each row execute function public.protect_interview_session_model();

create or replace function public.create_interview_session_with_model(
  p_user_id uuid,
  p_idempotency_key text,
  p_request_hash text,
  p_selected_resume_id uuid,
  p_job_context_id uuid,
  p_title text,
  p_target_role text,
  p_company_name text,
  p_job_description_preview text,
  p_selected_model_key text
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
  if p_selected_model_key is not null and not public.session_model_routing_ready() then
    raise exception 'model-bound session creation is not available yet' using errcode = 'P0001';
  end if;

  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  lock_key := hashtextextended(p_user_id::text, 0);
  perform pg_advisory_xact_lock(lock_key);

  delete from public.interview_session_idempotency_keys as k
  where k.expires_at < timezone('utc', now());

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
    select k.*
    into reservation
    from public.interview_session_idempotency_keys as k
    where k.user_id = p_user_id
      and k.idempotency_key = p_idempotency_key
    for update;

    if reservation.request_hash <> p_request_hash or (reservation.interview_session_id is not null and exists (
      select 1 from public.interview_sessions s where s.id = reservation.interview_session_id
        and s.selected_model_key is distinct from p_selected_model_key
    )) then
      raise exception 'interview session idempotency key conflict' using errcode = 'P0001';
    end if;

    if reservation.status = 'completed' and reservation.interview_session_id is not null then
      return query
      select reservation.interview_session_id, true, 'completed'::text;
      return;
    end if;

    raise exception 'interview session idempotency request in progress' using errcode = 'P0001';
  end if;

  if p_selected_resume_id is not null and not exists (
    select 1
    from public.resumes as r
    where r.id = p_selected_resume_id
      and r.user_id = p_user_id
  ) then
    raise exception 'selected resume was not found' using errcode = 'P0001';
  end if;

  if p_job_context_id is not null and not exists (
    select 1
    from public.job_contexts as j
    where j.id = p_job_context_id
      and j.user_id = p_user_id
  ) then
    raise exception 'job context was not found' using errcode = 'P0001';
  end if;

  select s.*
  into existing_session
  from public.interview_sessions as s
  where s.user_id = p_user_id
    and s.status = 'active'
    and s.ended_at is null
  order by s.started_at desc, s.id desc
  limit 1
  for update;

  if existing_session.id is not null then
    if existing_session.started_at >= timezone('utc', now()) - interval '2 minutes'
      and coalesce(existing_session.selected_resume_id, '00000000-0000-0000-0000-000000000000'::uuid)
        = coalesce(p_selected_resume_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and coalesce(existing_session.job_context_id, '00000000-0000-0000-0000-000000000000'::uuid)
        = coalesce(p_job_context_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and existing_session.selected_model_key is not distinct from p_selected_model_key
      and coalesce(existing_session.title, '') = coalesce(p_title, '')
      and coalesce(existing_session.target_role, '') = coalesce(p_target_role, '')
      and coalesce(existing_session.company_name, '') = coalesce(p_company_name, '')
      and coalesce(existing_session.job_description_preview, '') = coalesce(p_job_description_preview, '')
    then
      update public.interview_session_idempotency_keys as k
      set status = 'completed',
          interview_session_id = existing_session.id,
          expires_at = timezone('utc', now()) + interval '24 hours'
      where k.id = reservation.id;

      return query
      select existing_session.id, true, 'completed'::text;
      return;
    end if;

    update public.interview_sessions as s
    set status = 'abandoned',
        ended_at = timezone('utc', now())
    where s.id = existing_session.id
      and s.status = 'active'
      and s.ended_at is null;
  end if;

  insert into public.interview_sessions (
    user_id,
    selected_resume_id,
    job_context_id,
    title,
    target_role,
    company_name,
    job_description_preview,
    selected_model_key,
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
    p_selected_model_key,
    'active',
    timezone('utc', now()),
    null
  )
  returning * into created_session;

  update public.interview_session_idempotency_keys as k
  set status = 'completed',
      interview_session_id = created_session.id,
      expires_at = timezone('utc', now()) + interval '24 hours'
  where k.id = reservation.id;

  return query
  select created_session.id, false, 'completed'::text;
end;
$$;


revoke all on function public.create_interview_session_with_model(uuid,text,text,uuid,uuid,text,text,text,text,text) from public, anon, authenticated;
grant execute on function public.create_interview_session_with_model(uuid,text,text,uuid,uuid,text,text,text,text,text) to service_role;

-- Retain the old signature and payload/hash behavior for old servers and clients.
-- Delegate so its two-minute replay shortcut also distinguishes legacy/model-bound.
create or replace function public.create_interview_session_with_idempotency(
  p_user_id uuid, p_idempotency_key text, p_request_hash text,
  p_selected_resume_id uuid, p_job_context_id uuid, p_title text,
  p_target_role text, p_company_name text, p_job_description_preview text
) returns table(interview_session_id uuid, replayed boolean, status text)
language sql security definer set search_path = public, extensions as $$
  select * from public.create_interview_session_with_model(
    p_user_id,p_idempotency_key,p_request_hash,p_selected_resume_id,p_job_context_id,
    p_title,p_target_role,p_company_name,p_job_description_preview,null);
$$;
revoke all on function public.create_interview_session_with_idempotency(uuid,text,text,uuid,uuid,text,text,text,text) from public, anon, authenticated;
grant execute on function public.create_interview_session_with_idempotency(uuid,text,text,uuid,uuid,text,text,text,text) to service_role;
