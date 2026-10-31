begin;
create table public.subscription_notes_versions (
 operation_id uuid primary key references public.usage_operations(operation_id),
 account_id uuid not null references auth.users(id) on delete cascade,
 result jsonb not null
);
alter table public.subscription_notes_versions enable row level security;
alter table public.subscription_notes_versions force row level security;
revoke all on public.subscription_notes_versions from public,anon,authenticated,service_role,usage_executor;
-- Narrow native adapter over the existing session, transcript, Notes and Ask AI
-- tables. No new result store, quota or service-role authorization shortcut.
create function public.subscription_aux_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare sid uuid; terms jsonb; feature text; meter text; k public.interview_session_ask_ai_request_keys; n public.interview_session_ai_notes; o jsonb; result jsonb; body jsonb; created boolean;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform public.subscription_current(p_account,false);
 select c.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions c using(offer_version_id) where b.account_id=p_account;
 feature:=case when p_action like 'notes.%' then 'notes.generate' when p_action like 'ask.%' then 'session.ask_ai' else 'sessions.history' end;
 if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'=feature and e->>'allowed'='true') then raise exception 'denied' using errcode='42501'; end if;
 if p_action='sessions' then
   return jsonb_build_object('items',(select coalesce(jsonb_agg(to_jsonb(x)),'[]') from (select * from public.interview_sessions where user_id=p_account and (not p_doc ? 'statuses' or p_doc->'statuses' ? status) order by started_at desc,id limit least(200,(p_doc->>'limit')::integer) offset greatest(0,(p_doc->>'offset')::integer)) x));
 end if;
 sid:=(p_doc->>'session_id')::uuid;
 perform pg_advisory_xact_lock(hashtextextended(sid::text,0));
 perform 1 from public.interview_sessions where user_id=p_account and id=sid for update;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 if p_action='transcripts.clear' then
   return jsonb_build_object('deleted_count',public.delete_interview_session_transcript_entries(p_account,sid));
 end if;
 if p_action='transcripts' then
   return jsonb_build_object('items',(select coalesce(jsonb_agg(to_jsonb(x)),'[]') from (select * from public.interview_session_transcript_entries where user_id=p_account and session_id=sid order by turn_index,created_at,id limit least(200,(p_doc->>'limit')::integer) offset greatest(0,(p_doc->>'offset')::integer)) x));
 end if;
 if p_action='notes.read' then
   select * into n from public.interview_session_ai_notes where user_id=p_account and session_id=sid;
   if not found then raise exception 'not found' using errcode='P0002'; end if;
   return to_jsonb(n);
 end if;
 if p_action in ('notes.claim','notes.complete','notes.fail') then
   if not exists(select 1 from jsonb_array_elements(terms->'allowances') a where a->>'meter'='notes.generations' and a->>'mode'='unlimited') then raise exception 'unsupported allowance' using errcode='55000'; end if;
   if p_action='notes.claim' then
     o:=public.usage_call(p_account,'reserve',jsonb_build_object('operation','notes.generate','resource_id',sid,'request_id',p_doc->>'request_id','semantic_hash',p_doc->>'semantic_hash','meter','notes.generations','requested',1,'policy_version','subscriptions.approved.2026-10-24','lease_seconds',60));
     if o->>'state'='reserved' then
       return public.usage_call(p_account,'dispatch',jsonb_build_object('operation_id',o->'operation_id','fence',o->'fence','claim_token',o->'claim_token'))||jsonb_build_object('claimed',true);
     end if;
     if o->>'state'='settled' then
       select v.result into result from public.subscription_notes_versions v where operation_id=(o->>'operation_id')::uuid and account_id=p_account;
       if not found then raise exception 'result missing' using errcode='55000'; end if;
       return jsonb_build_object('claimed',false,'result',result);
     end if;
     if o->>'state'='dispatched' and (o->>'lease_until')::timestamptz<=clock_timestamp() and not exists(select 1 from public.subscription_notes_versions where operation_id=(o->>'operation_id')::uuid) then
       perform public.subscription_result_finish(p_account,(o->>'operation_id')::uuid,0,null);
       return jsonb_build_object('claimed',false,'failed',true);
     end if;
     if o->>'state'='released' then return jsonb_build_object('claimed',false,'failed',true); end if;
     raise exception 'outcome unresolved' using errcode='40001';
   end if;
   select to_jsonb(x) into o from public.usage_operations x where account_id=p_account and operation_id=(p_doc->>'operation_id')::uuid and resource_id=sid and operation='notes.generate' for update;
   if o is null or o->>'claim_token'<>p_doc->>'claim_token' or (o->>'fence')::bigint<>(p_doc->>'fence')::bigint then raise exception 'stale operation' using errcode='40001'; end if;
   if p_action='notes.fail' then
     if o->>'state' in ('reserved','dispatched') then perform public.subscription_result_finish(p_account,(o->>'operation_id')::uuid,0,null); end if;
     return jsonb_build_object('ok',true);
   end if;
   if o->>'state'<>'dispatched' or (o->>'lease_until')::timestamptz<=clock_timestamp() then raise exception 'expired operation' using errcode='40001'; end if;
   n:=jsonb_populate_record(null::public.interview_session_ai_notes,p_doc->'payload');
   insert into public.interview_session_ai_notes(user_id,session_id,status,notes_markdown,summary,strengths,improvement_areas,technical_topics,key_questions,suggested_followups,provider,model,generation_ms,transcript_entry_count,generated_at)
   values(p_account,sid,n.status,n.notes_markdown,n.summary,n.strengths,n.improvement_areas,n.technical_topics,n.key_questions,n.suggested_followups,n.provider,n.model,n.generation_ms,n.transcript_entry_count,n.generated_at)
   on conflict(session_id) do update set status=excluded.status,notes_markdown=excluded.notes_markdown,summary=excluded.summary,strengths=excluded.strengths,improvement_areas=excluded.improvement_areas,technical_topics=excluded.technical_topics,key_questions=excluded.key_questions,suggested_followups=excluded.suggested_followups,provider=excluded.provider,model=excluded.model,generation_ms=excluded.generation_ms,transcript_entry_count=excluded.transcript_entry_count,generated_at=excluded.generated_at returning * into n;
   perform public.subscription_result_finish(p_account,(o->>'operation_id')::uuid,1,n.id);
   insert into public.subscription_notes_versions values((o->>'operation_id')::uuid,p_account,to_jsonb(n));
   return to_jsonb(n);
 end if;
 if p_action like 'ask.%' then
   if not exists(select 1 from jsonb_array_elements(terms->'allowances') a where a->>'meter'='ask_ai.completed' and a->>'mode'='unlimited') then raise exception 'unsupported allowance' using errcode='55000'; end if;
   if p_action='ask.messages' then return jsonb_build_object('items',(select coalesce(jsonb_agg(to_jsonb(x)),'[]') from (select * from public.interview_session_ask_ai_messages where user_id=p_account and session_id=sid order by turn_index desc,id limit least(201,(p_doc->>'limit')::integer) offset greatest(0,(p_doc->>'offset')::integer)) x)); end if;
   if p_action='ask.message' then
     select to_jsonb(x) into result from public.interview_session_ask_ai_messages x where user_id=p_account and session_id=sid and id=(p_doc->>'message_id')::uuid;
     if result is null then raise exception 'not found' using errcode='P0002'; end if;return result;
   end if;
   select * into k from public.interview_session_ask_ai_request_keys where user_id=p_account and session_id=sid and request_id=p_doc->>'request_id' for update;
   if p_action='ask.claim' then
     created:=k.id is null;
     if created then insert into public.interview_session_ask_ai_request_keys(user_id,session_id,request_id,payload_hash) values(p_account,sid,p_doc->>'request_id',p_doc->>'payload_hash') returning * into k; end if;
     if k.payload_hash<>p_doc->>'payload_hash' then raise exception 'identity conflict' using errcode='P0003'; end if;
     return to_jsonb(k)||jsonb_build_object('claimed',created);
   end if;
   if k.id is null then raise exception 'not found' using errcode='P0002'; end if;
   if p_action='ask.key' then return to_jsonb(k); end if;
   if p_action='ask.expire' then
     if k.status='processing' and k.updated_at<(p_doc->>'stale_before')::timestamptz then
       update public.interview_session_ask_ai_request_keys set status='failed',claim_token=gen_random_uuid(),error_code='execution_expired' where id=k.id;
     end if;
     return jsonb_build_object('ok',true);
   end if;
   if p_action='ask.fail' then
     update public.interview_session_ask_ai_request_keys set status='failed',error_code='execution_failed' where id=k.id and status='processing' and claim_token=(p_doc->>'claim_token')::uuid;
     return to_jsonb(k);
   end if;
   if p_action='ask.complete' then
     select to_jsonb(x) into result from public.complete_interview_session_ask_ai_turn(p_account,sid,p_doc->>'request_id',(p_doc->>'claim_token')::uuid,p_doc->>'question',p_doc->>'answer',p_doc->>'provider',p_doc->>'model',(p_doc->>'generation_ms')::integer,p_doc->'metadata') x;
     return result;
   end if;
 end if;
 raise exception 'invalid action' using errcode='22023';
end $$;
revoke all on function public.subscription_aux_call(uuid,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.subscription_aux_call(uuid,text,jsonb) to usage_executor;
create function public.subscription_result_sweep(p_limit integer) returns integer
language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; r public.subscription_screen_results; o public.usage_operations; total integer:=0;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' or p_limit not between 1 and 50 then raise exception 'denied' using errcode='42501'; end if;
 for account in select account_id from (
   select account_id from public.subscription_screen_results where state='processing' and lease_until<=clock_timestamp()
   union select account_id from public.usage_operations where operation='notes.generate' and state='dispatched' and lease_until<=clock_timestamp()
 ) pending order by account_id limit p_limit loop
   perform 1 from public.account_plan_bindings where account_id=account for update skip locked;
   if not found then continue; end if;
   for r in select * from public.subscription_screen_results where account_id=account and state='processing' and lease_until<=clock_timestamp() order by result_id limit 50 for update loop
     if r.response is not null then raise exception 'corrupt recovery' using errcode='55000'; end if;
     if r.usage_id is not null then perform public.subscription_result_finish(account,r.usage_id,0,null); end if;
     update public.subscription_screen_results set state='failed',token=gen_random_uuid() where result_id=r.result_id;
     update public.subscription_screen_threads set busy=null where account_id=account and busy=r.result_id;
     total:=total+1;
   end loop;
   for o in select * from public.usage_operations where account_id=account and operation='notes.generate' and state='dispatched' and lease_until<=clock_timestamp() order by operation_id limit 50 for update loop
     if exists(select 1 from public.subscription_notes_versions where operation_id=o.operation_id) then raise exception 'corrupt recovery' using errcode='55000'; end if;
     perform public.subscription_result_finish(account,o.operation_id,0,null);
     total:=total+1;
   end loop;
 end loop;
 return total;
end $$;
revoke all on function public.subscription_result_sweep(integer) from public,anon,authenticated,service_role;
grant execute on function public.subscription_result_sweep(integer) to usage_executor;
commit;
