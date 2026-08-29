-- C6.3 follow-up fix for live interview session idempotent create RPC.
-- Replaces the function with fully qualified table aliases so output-column
-- names like `status` do not collide with unqualified SQL references.

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

    if reservation.request_hash <> p_request_hash then
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

  update public.interview_session_idempotency_keys as k
  set status = 'completed',
      interview_session_id = created_session.id,
      expires_at = timezone('utc', now()) + interval '24 hours'
  where k.id = reservation.id;

  return query
  select created_session.id, false, 'completed'::text;
end;
$$;

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
  'C6.3 follow-up fix: fully qualified interview session idempotent create RPC that avoids ambiguous output-column references and preserves backend-only replay behavior.';
