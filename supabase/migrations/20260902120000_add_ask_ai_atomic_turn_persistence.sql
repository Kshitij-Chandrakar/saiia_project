-- C9 follow-up: fence idempotent Ask AI turn completion and persist both messages atomically.

alter table public.interview_session_ask_ai_request_keys
  add column if not exists claim_token uuid default extensions.gen_random_uuid();

alter table public.interview_session_ask_ai_request_keys
  alter column claim_token set not null;

create or replace function public.complete_interview_session_ask_ai_turn(
  p_user_id uuid,
  p_session_id uuid,
  p_request_id text,
  p_claim_token uuid,
  p_question text,
  p_answer text,
  p_provider text,
  p_model text,
  p_generation_ms integer,
  p_metadata jsonb
)
returns table (
  user_message_id uuid,
  assistant_message_id uuid
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_request_key public.interview_session_ask_ai_request_keys%rowtype;
  v_user_message_id uuid;
  v_assistant_message_id uuid;
  v_turn_index integer;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  perform pg_advisory_xact_lock(hashtextextended(p_session_id::text || ':ask-ai', 0));

  if not exists (
    select 1
    from public.interview_sessions as s
    where s.id = p_session_id
      and s.user_id = p_user_id
  ) then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;

  select k.*
  into v_request_key
  from public.interview_session_ask_ai_request_keys as k
  where k.user_id = p_user_id
    and k.session_id = p_session_id
    and k.request_id = p_request_id
  for update;

  if v_request_key.id is null
     or v_request_key.status <> 'processing'
     or v_request_key.claim_token is distinct from p_claim_token then
    raise exception 'Ask AI request is no longer active' using errcode = 'P0002';
  end if;

  select coalesce(max(m.turn_index), 0) + 1
  into v_turn_index
  from public.interview_session_ask_ai_messages as m
  where m.session_id = p_session_id;

  insert into public.interview_session_ask_ai_messages (
    user_id, session_id, role, message_text, turn_index,
    provider, model, generation_ms, metadata
  )
  values (
    p_user_id, p_session_id, 'user', p_question, v_turn_index,
    null, null, null, coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into v_user_message_id;

  insert into public.interview_session_ask_ai_messages (
    user_id, session_id, role, message_text, turn_index,
    provider, model, generation_ms, metadata
  )
  values (
    p_user_id, p_session_id, 'assistant', p_answer, v_turn_index + 1,
    nullif(coalesce(p_provider, ''), ''),
    nullif(coalesce(p_model, ''), ''),
    p_generation_ms,
    coalesce(p_metadata, '{}'::jsonb)
  )
  returning id into v_assistant_message_id;

  update public.interview_session_ask_ai_request_keys as k
  set status = 'completed',
      user_message_id = v_user_message_id,
      assistant_message_id = v_assistant_message_id,
      error_code = null
  where k.id = v_request_key.id
    and k.status = 'processing'
    and k.claim_token = p_claim_token;

  if not found then
    raise exception 'Ask AI request is no longer active' using errcode = 'P0002';
  end if;

  return query select v_user_message_id, v_assistant_message_id;
end;
$$;

revoke all on function public.complete_interview_session_ask_ai_turn(
  uuid, uuid, text, uuid, text, text, text, text, integer, jsonb
) from public;
revoke all on function public.complete_interview_session_ask_ai_turn(
  uuid, uuid, text, uuid, text, text, text, text, integer, jsonb
) from anon;
revoke all on function public.complete_interview_session_ask_ai_turn(
  uuid, uuid, text, uuid, text, text, text, text, integer, jsonb
) from authenticated;
grant execute on function public.complete_interview_session_ask_ai_turn(
  uuid, uuid, text, uuid, text, text, text, text, integer, jsonb
) to service_role;
