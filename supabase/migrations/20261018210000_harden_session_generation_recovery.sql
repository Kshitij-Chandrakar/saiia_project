-- Additive recovery validation; admission and applied migration history are unchanged.
create or replace function public.session_generation_turn(
 p_operation text, p_user_id uuid, p_session_id uuid, p_request_id text,
 p_hash text, p_attempt integer, p_supersedes text, p_token uuid, p_payload jsonb
) returns jsonb language plpgsql security definer set search_path=public,extensions as $$
declare
 s public.interview_sessions%rowtype;
 t public.session_generation_turns%rowtype;
 entry_id uuid;
 r jsonb;
begin
 set local lock_timeout='2s'; set local statement_timeout='5s';
 if octet_length(coalesce(p_payload::text,''))>1048576 then return jsonb_build_object('error','payload_too_large'); end if;
 perform pg_advisory_xact_lock(hashtextextended(p_session_id::text,0));
 select * into s from public.interview_sessions where id=p_session_id and user_id=p_user_id for update;
 if s.id is null then return jsonb_build_object('error','session_not_found'); end if;
 select * into t from public.session_generation_turns where session_id=p_session_id and request_id=p_request_id for update;
 if s.status <> 'active' then
   update public.session_generation_turns set state='cancelled',payload=null,token=extensions.gen_random_uuid()
    where session_id=p_session_id and request_id=p_request_id and state in ('processing','checkpoint');
   return jsonb_build_object('error','session_ended');
 end if;
 if p_operation='recover' then
   if t.request_id is null or t.state in ('cancelled','uncertain','deleted') then
     return jsonb_build_object('error','generation_unrecoverable');
   end if;
   return jsonb_build_object('payload',t.payload);
 end if;
 if p_operation='claim' then
   if t.request_id is null then
     if p_attempt<>0 then return jsonb_build_object('error','attempt_conflict'); end if;
     if p_supersedes is not null then
       update public.session_generation_turns set state='cancelled',payload=null,token=extensions.gen_random_uuid()
        where session_id=p_session_id and user_id=p_user_id and request_id=p_supersedes
          and state in ('processing','checkpoint');
     end if;
     insert into public.session_generation_turns(session_id,user_id,request_id,payload_hash,state,payload)
       values(p_session_id,p_user_id,p_request_id,p_hash,'processing',p_payload) returning * into t;
     return jsonb_build_object('state','claimed','token',t.token);
   end if;
   if t.payload_hash<>p_hash then return jsonb_build_object('error','payload_conflict'); end if;
   if t.state='processing' and t.lease_until<=clock_timestamp() then
     -- Crash before checkpoint: completion cannot be proven. Fence the old worker;
     -- never automatically regenerate potentially completed upstream work.
     update public.session_generation_turns set state='uncertain',token=extensions.gen_random_uuid()
       where session_id=p_session_id and request_id=p_request_id returning * into t;
   end if;
   if t.state='failed' and p_attempt=t.attempt+1 then
     update public.session_generation_turns set state='processing',attempt=p_attempt,
       token=extensions.gen_random_uuid(),lease_until=clock_timestamp()+interval '120 seconds'
       where session_id=p_session_id and request_id=p_request_id returning * into t;
     return jsonb_build_object('state','claimed','token',t.token);
   end if;
   if p_attempt<>t.attempt then return jsonb_build_object('error','attempt_conflict'); end if;
   return jsonb_build_object('state',t.state,'token',case when t.state='checkpoint' then t.token end,'payload',t.payload);
 end if;
 if t.request_id is null or t.token is distinct from p_token then return jsonb_build_object('error','stale_attempt'); end if;
 if p_operation='check' then
   if t.state='processing' and t.lease_until<=clock_timestamp() then
     update public.session_generation_turns set state='uncertain',token=extensions.gen_random_uuid()
      where session_id=p_session_id and request_id=p_request_id;
     return jsonb_build_object('state','uncertain');
   end if;
   return jsonb_build_object('state',t.state);
 elsif p_operation='checkpoint' then
   if t.state<>'processing' or t.lease_until<=clock_timestamp() then return jsonb_build_object('error','stale_attempt'); end if;

   if char_length(coalesce(p_payload->>'question','')) not between 1 and 4000
      or char_length(coalesce(p_payload->'result'->>'answer','')) not between 1 and 24000
      or char_length(coalesce(p_payload->'result'->>'model','')) > 120
      or char_length(coalesce(p_payload->'result'->>'provider','')) > 80 then
     return jsonb_build_object('error','invalid_result');
   end if;

   update public.session_generation_turns set state='checkpoint',payload=p_payload
    where session_id=p_session_id and request_id=p_request_id;
 elsif p_operation='complete' then
   if t.state='completed' then return jsonb_build_object('state','completed','payload',t.payload); end if;
   if t.state<>'checkpoint' then return jsonb_build_object('error','stale_attempt'); end if;
   -- Quarantine older invalid checkpoints rather than retrying an impossible save.
   if char_length(coalesce(t.payload->>'question','')) not between 1 and 4000
      or char_length(coalesce(t.payload->'result'->>'answer','')) not between 1 and 24000
      or char_length(coalesce(t.payload->'result'->>'model','')) > 120
      or char_length(coalesce(t.payload->'result'->>'provider','')) > 80 then
     update public.session_generation_turns set state='failed',
       payload=jsonb_build_object('request',payload->'request'),token=extensions.gen_random_uuid()
       where session_id=p_session_id and request_id=p_request_id;
     return jsonb_build_object('error','invalid_result');
   end if;
   r:=t.payload->'result';
   select transcript_entry_id into entry_id from public.create_interview_session_transcript_entry(
     p_user_id,p_session_id,p_request_id,case when r->>'generate_source'='screen' then 'analyze_screen'
       when r->>'generate_source' in ('chat','answer','auto','analyze_screen') then r->>'generate_source' else 'unknown' end,t.payload->>'question',r->>'answer',
     r->>'generate_category',r->>'provider',r->>'model',coalesce((r->>'generation_ms')::numeric,0)::integer,
     jsonb_build_object('selected_model_key',r->>'selected_model_key','selected_provider',r->>'selected_provider',
       'selected_api_model',r->>'selected_api_model','actual_provider',r->>'actual_provider',
       'actual_api_model',r->>'actual_api_model','reported_model',r->>'reported_model',
       'fallback_used',r->'fallback_used','retry_attempt',p_attempt));
   update public.session_generation_turns set state='completed',transcript_id=entry_id
    where session_id=p_session_id and request_id=p_request_id;
 elsif p_operation in ('cancel','fail') then
   update public.session_generation_turns set state=case when p_operation='cancel' then 'cancelled' else 'failed' end,
     payload=case when p_operation='fail' then jsonb_build_object('request',payload->'request') else null end,
     token=extensions.gen_random_uuid()
     where session_id=p_session_id and request_id=p_request_id and
       (state='processing' or (p_operation='cancel' and state='checkpoint'));
 else return jsonb_build_object('error','invalid_operation');
 end if;
 return jsonb_build_object('state','ok');
end;
$$;
revoke all on function public.session_generation_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.session_generation_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb) to service_role;
