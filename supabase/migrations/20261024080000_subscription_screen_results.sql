begin;
create table public.subscription_screen_threads (
 account_id uuid not null references auth.users(id) on delete cascade,
 session_id uuid not null references public.interview_sessions(id) on delete cascade,
 thread_key text not null,
 revision bigint not null default 0,
 busy uuid,
 primary key(account_id,session_id,thread_key)
);
create table public.subscription_screen_results (
 result_id uuid primary key default gen_random_uuid(),
 account_id uuid not null references auth.users(id) on delete cascade,
 session_id uuid not null references public.interview_sessions(id) on delete cascade,
 thread_key text not null,
 request_key text not null,
 request_aliases jsonb not null default '[]',
 semantic_hash text not null,
 turn_key text not null,
 kind text not null check(kind in ('question','reference','followup')),
 state text not null default 'processing' check(state in ('processing','completed','failed')),
 token uuid not null default gen_random_uuid(),
 lease_until timestamptz not null default clock_timestamp()+interval '60 seconds',
 usage_id uuid references public.usage_operations(operation_id) on delete restrict,
 response jsonb,
 created_at timestamptz not null default clock_timestamp(),
 unique(account_id,session_id,request_key)
);
-- Only trusted result transactions call this proof-bound helper. Usage and
-- audit remain in the accepted ledger; no second accounting system is created.
create function public.subscription_result_finish(p_account uuid,p_usage uuid,p_charge bigint,p_result uuid) returns void
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.usage_operations;
begin
 select * into o from public.usage_operations where operation_id=p_usage and account_id=p_account for update;
 if not found or o.state not in ('reserved','dispatched') or p_charge<0 or p_charge>o.requested then raise exception 'invalid settlement' using errcode='55000'; end if;
 update public.usage_periods set reserved=reserved-o.requested,used=used+p_charge where period_id=o.period_id;
 update public.usage_operations set state=case when p_charge>0 then 'settled' else 'released' end,
   charged=case when p_charge>0 then p_charge else null end,result_ref=case when p_charge>0 then p_result else null end,
   fence=fence+1 where operation_id=p_usage;
 insert into public.usage_events(account_id,operation_id,event,fence,actor_principal,used_delta,reserved_delta)
 values(p_account,p_usage,case when p_charge>0 then 'result.settle' else 'result.release' end,o.fence,session_user,p_charge,-o.requested);
end $$;

create function public.subscription_screen_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare t public.subscription_screen_threads; r public.subscription_screen_results; old public.subscription_screen_results;
 terms jsonb; operation jsonb; extra jsonb; v_response jsonb; charge integer; kind text; sid uuid; key text; thread text; at_time timestamptz;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 sid:=(p_doc->>'session_id')::uuid;thread:=p_doc->>'thread_key';key:=p_doc->>'request_key';
 if p_action not in ('read','history','fail','list') then
   perform public.subscription_current(p_account,false);
   select c.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions c using(offer_version_id) where b.account_id=p_account;
   if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='screen.analyze' and e->>'allowed'='true') then raise exception 'screen denied' using errcode='42501'; end if;
 else perform 1 from public.account_plan_bindings where account_id=p_account for update;
 end if;
 perform pg_advisory_xact_lock(hashtextextended(sid::text,0));
 perform 1 from public.interview_sessions where id=sid and user_id=p_account for update;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 if p_action='list' then
   return jsonb_build_object('items',(select coalesce(jsonb_agg(jsonb_build_object('result_id',result_id,'thread_id',thread_key,'response',response,'created_at',created_at)),'[]') from (select * from public.subscription_screen_results where account_id=p_account and session_id=sid and state='completed' order by created_at,result_id limit least(100,(p_doc->>'limit')::integer) offset greatest(0,(p_doc->>'offset')::integer)) x));
 end if;
 if p_action='history' then
   return jsonb_build_object('items',(select coalesce(jsonb_agg(to_jsonb(x) order by created_at,result_id),'[]') from public.subscription_screen_results x where account_id=p_account and session_id=sid and thread_key=thread and response is not null));
 end if;
 select * into r from public.subscription_screen_results where account_id=p_account and session_id=sid and request_key=key for update;
 if p_action='read' then
   if not found or r.response is null then raise exception 'not found' using errcode='P0002'; end if;
   return r.response;
 end if;
 if p_action='claim' then
   if found then
     if r.semantic_hash<>p_doc->>'semantic_hash' or r.thread_key<>thread then raise exception 'identity conflict' using errcode='P0003'; end if;
     if r.state='processing' and r.lease_until<=clock_timestamp() and r.response is null then
       if r.usage_id is not null then perform public.subscription_result_finish(p_account,r.usage_id,0,null); end if;
       update public.subscription_screen_results set state='failed',token=gen_random_uuid() where result_id=r.result_id returning * into r;
       update public.subscription_screen_threads set busy=null where account_id=p_account and session_id=sid and thread_key=thread and busy=r.result_id;
     end if;
     if not (r.request_aliases ? (p_doc->>'request_id')) then
       update public.subscription_screen_results set request_aliases=request_aliases||jsonb_build_array(p_doc->>'request_id') where result_id=r.result_id returning * into r;
     end if;
     return to_jsonb(r)||jsonb_build_object('claimed',false);
   end if;
   if not exists(select 1 from public.interview_sessions where id=sid and status='active') then raise exception 'inactive' using errcode='40001'; end if;
   insert into public.subscription_screen_threads(account_id,session_id,thread_key) values(p_account,sid,thread) on conflict do nothing;
   select * into strict t from public.subscription_screen_threads where account_id=p_account and session_id=sid and thread_key=thread for update;
   if t.revision<>(p_doc->>'revision')::bigint then raise exception 'stale context' using errcode='40001'; end if;
   if t.busy is not null then
     select * into old from public.subscription_screen_results where result_id=t.busy for update;
     if old.lease_until>clock_timestamp() then raise exception 'busy' using errcode='40001'; end if;
     -- Expired worker is fenced before releasing: no result/checkpoint exists,
     -- since storing the response and settling are one transaction.
     if old.response is not null then raise exception 'invalid recovery' using errcode='55000'; end if;
     if old.usage_id is not null then perform public.subscription_result_finish(p_account,old.usage_id,0,null); end if;
     update public.subscription_screen_results set state='failed',token=gen_random_uuid() where result_id=old.result_id;
   end if;
   kind:=case when p_doc->>'intent'='reference' then 'reference' when exists(select 1 from public.subscription_screen_results x where x.account_id=p_account and x.session_id=sid and x.thread_key=thread and x.response->>'outcome'='answered') then 'followup' else 'question' end;
   if kind='followup' and not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='screen.followups' and e->>'allowed'='true') then raise exception 'followup denied' using errcode='42501'; end if;
   if p_doc->>'intent'='new' and t.revision>0 then raise exception 'new thread required' using errcode='40001'; end if;
   if kind='question' then
     operation:=public.usage_call(p_account,'reserve',jsonb_build_object('operation','screen.question','resource_id',sid,'request_id',key,'semantic_hash',p_doc->>'semantic_hash','meter','screen.analyses','requested',1,'policy_version','subscriptions.approved.2026-10-24','lease_seconds',60));
     perform public.usage_call(p_account,'dispatch',jsonb_build_object('operation_id',operation->'operation_id','fence',operation->'fence','claim_token',operation->'claim_token'));
   end if;
   insert into public.subscription_screen_results(account_id,session_id,thread_key,request_key,request_aliases,semantic_hash,turn_key,kind,usage_id)
     values(p_account,sid,thread,key,jsonb_build_array(p_doc->>'request_id'),p_doc->>'semantic_hash',p_doc->>'turn_key',kind,(operation->>'operation_id')::uuid) returning * into r;
   update public.subscription_screen_threads set busy=r.result_id where account_id=p_account and session_id=sid and thread_key=thread;
   return to_jsonb(r)||jsonb_build_object('claimed',true);
 end if;
 if r.result_id is null or r.token<>(p_doc->>'token')::uuid then raise exception 'stale operation' using errcode='40001'; end if;
 if r.state<>'processing' then return to_jsonb(r); end if;
 select * into strict t from public.subscription_screen_threads where account_id=p_account and session_id=sid and thread_key=r.thread_key for update;
 if p_action='fail' then
   if r.usage_id is not null then perform public.subscription_result_finish(p_account,r.usage_id,0,null); end if;
   update public.subscription_screen_results set state='failed',token=gen_random_uuid() where result_id=r.result_id returning * into r;
 elsif p_action='complete' then
   if not exists(select 1 from public.interview_sessions where id=sid and user_id=p_account and status='active') then raise exception 'inactive session' using errcode='40001'; end if;
   if r.lease_until<=clock_timestamp() or t.busy<>r.result_id then raise exception 'stale worker' using errcode='40001'; end if;
   v_response:=p_doc->'response';
   if octet_length(v_response::text)>131072 or v_response->>'outcome' not in ('answered','reference_accepted','needs_more_content','needs_clarification','failed') then raise exception 'invalid result' using errcode='22023'; end if;
   if r.kind='reference' and v_response->>'outcome'='answered' then raise exception 'invalid reference result' using errcode='22023'; end if;
   if r.kind='followup' and not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='screen.followups' and e->>'allowed'='true') then raise exception 'followup denied' using errcode='42501'; end if;
   charge:=case when r.kind='question' and v_response->>'outcome'='answered' then jsonb_array_length(v_response->'items') else 0 end;
   if charge>1 then
     extra:=public.usage_call(p_account,'reserve',jsonb_build_object('operation','screen.question','resource_id',sid,'request_id',key||':extra','semantic_hash',r.semantic_hash,'meter','screen.analyses','requested',charge-1,'policy_version','subscriptions.approved.2026-10-24','lease_seconds',60));
     perform public.subscription_result_finish(p_account,(extra->>'operation_id')::uuid,charge-1,r.result_id);
   end if;
   update public.subscription_screen_results set state='completed',response=v_response where result_id=r.result_id returning * into r;
   if r.usage_id is not null then perform public.subscription_result_finish(p_account,r.usage_id,least(charge,1),r.result_id); end if;
   if v_response->'evidenceDelta'<>'null'::jsonb then update public.subscription_screen_threads set revision=revision+1 where account_id=p_account and session_id=sid and thread_key=r.thread_key; end if;
 else raise exception 'invalid action' using errcode='22023'; end if;
 update public.subscription_screen_threads set busy=null where account_id=p_account and session_id=sid and thread_key=r.thread_key and busy=r.result_id;
 return to_jsonb(r);
end $$;
alter table public.subscription_screen_threads enable row level security;
alter table public.subscription_screen_threads force row level security;
alter table public.subscription_screen_results enable row level security;
alter table public.subscription_screen_results force row level security;
revoke all on public.subscription_screen_threads,public.subscription_screen_results from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
revoke all on function public.subscription_result_finish(uuid,uuid,bigint,uuid),public.subscription_screen_call(uuid,text,jsonb) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_screen_call(uuid,text,jsonb) to usage_executor;
commit;
