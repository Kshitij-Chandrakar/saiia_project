-- Configured admission lives in the backend; no per-model SQL allowlist/sync.
-- Existing keys/transcripts are untouched. NULL snapshots are Phase 2/3 compatibility rows.
alter table public.interview_sessions add column selected_model_binding jsonb;
alter table public.interview_sessions drop constraint interview_sessions_model_key_check;

create or replace function public.valid_session_model_binding(b jsonb)
returns boolean language sql immutable set search_path=pg_catalog as $$
 select coalesce(jsonb_typeof(b)='object' and b->'version'='1'::jsonb
 and (select count(*) from jsonb_object_keys(b))=6
 and b ?& array['version','provider','api_model','profile','effort','output_limit']
 and jsonb_typeof(b->'api_model')='string'
 and b->>'api_model' ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$'
 and position('..' in b->>'api_model')=0
 and (b->>'provider'<>'gemini' or position('/' in b->>'api_model')=0)
 and jsonb_typeof(b->'output_limit')='number'
 and b->>'output_limit' ~ '^[0-9]{1,6}$'
 and (b->>'output_limit')::numeric between 1 and 128000
 and case b->>'profile'
 when 'openai-responses' then b->>'provider'='openai' and b->>'effort'=''
 when 'openai-reasoning' then b->>'provider'='openai' and b->>'effort'=any(array['none','low','medium','high','xhigh','max'])
 when 'groq-chat' then b->>'provider'='groq' and b->>'effort'=''
 when 'groq-oss' then b->>'provider'='groq' and b->>'effort'=any(array['low','medium','high'])
 when 'gemini-content' then b->>'provider'='gemini' and b->>'effort'=''
 when 'gemini-thinking' then b->>'provider'='gemini' and b->>'effort'=any(array['minimal','low','medium','high'])
 else false end, false)
$$;
revoke all on function public.valid_session_model_binding(jsonb) from public,anon;
grant execute on function public.valid_session_model_binding(jsonb) to authenticated,service_role;
alter table public.interview_sessions add constraint interview_sessions_model_binding_check check (
 (selected_model_key is null or char_length(selected_model_key) between 1 and 240)
 and (selected_model_binding is null or (selected_model_key is not null and public.valid_session_model_binding(selected_model_binding))));

create or replace function public.protect_interview_session_model()
returns trigger language plpgsql security definer set search_path=public,pg_catalog as $$
begin
 if TG_OP='UPDATE' then
  if new.selected_model_key is distinct from old.selected_model_key
    or new.selected_model_binding is distinct from old.selected_model_binding
    or new.user_id is distinct from old.user_id then
   raise exception 'session selection and owner are immutable' using errcode='P0001';
  end if;
 elsif new.selected_model_key is not null or new.selected_model_binding is not null then
  if coalesce(auth.role(),'')<>'service_role' then
   raise exception 'model selection requires backend creation' using errcode='42501';
  end if;
  if not public.session_model_routing_ready() then
   raise exception 'model-bound session creation is not available yet' using errcode='P0001';
  end if;
  if new.selected_model_key is null or not public.valid_session_model_binding(new.selected_model_binding) then
   raise exception 'model binding is required' using errcode='P0001';
  end if;
 end if;
 return new;
end;
$$;
revoke all on function public.protect_interview_session_model() from public,anon,authenticated;

create or replace function public.create_interview_session_with_binding(
  p_user_id uuid,
  p_idempotency_key text,
  p_request_hash text,
  p_selected_resume_id uuid,
  p_job_context_id uuid,
  p_title text,
  p_target_role text,
  p_company_name text,
  p_job_description_preview text,
  p_selected_model_key text,
  p_selected_model_binding jsonb
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
        and (s.selected_model_key is distinct from p_selected_model_key or s.selected_model_binding is distinct from p_selected_model_binding)
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
      and existing_session.selected_model_binding is not distinct from p_selected_model_binding
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
    selected_model_binding,
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
    p_selected_model_binding,
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

revoke all on function public.create_interview_session_with_binding(uuid,text,text,uuid,uuid,text,text,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.create_interview_session_with_binding(uuid,text,text,uuid,uuid,text,text,text,text,text,jsonb) to service_role;
-- Older unbound RPC callers retain their existing behavior. Older bound creation
-- (without a complete snapshot) fails closed; historical bound reads still work.
