-- C13.2 server clock accounting. No LOGIN, assignments or activation.
begin;
create table public.subscription_auto_runs (
  run_id uuid primary key,
  account_id uuid not null references auth.users(id) on delete restrict,
  request_id text not null check(request_id ~ '^[A-Za-z0-9._:-]{1,120}$'),
  semantic_hash text not null check(semantic_hash ~ '^[0-9a-f]{64}$'),
  owner_token uuid not null default gen_random_uuid(),
  fence bigint not null default 1,
  sequence bigint not null default 0 check(sequence>=0),
  active boolean not null default true,
  slice_id uuid references public.usage_operations(operation_id) on delete restrict,
  started_at timestamptz not null default clock_timestamp(),
  unique(account_id,request_id)
);
create unique index subscription_auto_one_active on public.subscription_auto_runs(account_id) where active;
create table public.subscription_auto_replies (
  run_id uuid not null references public.subscription_auto_runs(run_id) on delete restrict,
  sequence bigint not null,
  action text not null check(action in ('start','renew','stop')),
  request_fence bigint not null,
  document jsonb not null,
  primary key(run_id,sequence)
);
alter table public.subscription_auto_runs enable row level security;
alter table public.subscription_auto_runs force row level security;
alter table public.subscription_auto_replies enable row level security;
alter table public.subscription_auto_replies force row level security;
revoke all on public.subscription_auto_runs,public.subscription_auto_replies from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
create trigger immutable_rows before update or delete on public.subscription_auto_replies for each row execute function public.catalog_reject_mutation();
create trigger immutable_truncate before truncate on public.subscription_auto_replies for each statement execute function public.catalog_reject_mutation();

-- Internal only. A durable run is itself evidence of authorized elapsed time;
-- neither speech, chunks nor a client timer determine the charge.
create function public.subscription_auto_finish_slice(p_run uuid,p_at timestamptz) returns void
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_auto_runs; o public.usage_operations; v_charge bigint;
begin
 select * into strict r from public.subscription_auto_runs where run_id=p_run;
 select * into strict o from public.usage_operations where operation_id=r.slice_id;
 if o.state='settled' then return; end if;
 if o.state<>'dispatched' then raise exception 'invalid run checkpoint' using errcode='55000'; end if;
 v_charge:=least(o.requested,greatest(0,(extract(epoch from (least(p_at,o.lease_until)-o.authorized_at))*1000000)::bigint));
 update public.usage_periods set reserved=reserved-o.requested,used=used+v_charge where period_id=o.period_id;
 update public.usage_operations set state='settled',charged=v_charge,result_ref=r.run_id where operation_id=o.operation_id;
 insert into public.usage_events(account_id,operation_id,event,fence,actor_principal,used_delta,reserved_delta)
 values(r.account_id,o.operation_id,'auto.settle',o.fence,session_user,v_charge,-o.requested);
end $$;

create function public.subscription_auto_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; r public.subscription_auto_runs; old_run public.subscription_auto_runs;
 p public.usage_periods; o public.usage_operations; reply public.subscription_auto_replies;
 at_time timestamptz; until_time timestamptz; amount bigint; output jsonb; terms jsonb; allowed text[];
begin
 if current_setting('role',true)<>'none' or session_user<>'usage_executor' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='start' then allowed:=array['run_id','request_id','semantic_hash'];
 elsif p_action='status' then allowed:=array['run_id'];
 elsif p_action in ('renew','stop') then allowed:=array['run_id','owner_token','fence','sequence'];
 else raise exception 'invalid action' using errcode='22023'; end if;
 if jsonb_typeof(p_doc)<>'object' or p_doc-allowed<>'{}' or not p_doc ?& allowed then raise exception 'invalid fields' using errcode='22023'; end if;
 -- The common account lock also serializes plan transitions and devices.
 perform public.subscription_current(p_account,false);
 select * into strict b from public.account_plan_bindings where account_id=p_account for update;
 select canonical_json::jsonb->'terms' into terms from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
 if not exists(select 1 from jsonb_array_elements(terms->'entitlements') x where x->>'feature'='assistant.auto' and x->>'allowed'='true') then
  raise exception 'auto denied' using errcode='42501'; end if;
 at_time:=clock_timestamp();
 if p_action='status' then
  select * into r from public.subscription_auto_runs where run_id=(p_doc->>'run_id')::uuid and account_id=p_account for update;
  if not found then raise exception 'run missing' using errcode='P0002'; end if;
  select * into strict o from public.usage_operations where operation_id=r.slice_id;
  if r.active and o.lease_until<=at_time then
   perform public.subscription_auto_finish_slice(r.run_id,at_time);
   update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=r.run_id returning * into r;
  end if;
  select * into strict o from public.usage_operations where operation_id=r.slice_id;
  return jsonb_build_object('run_id',r.run_id,'sequence',r.sequence,'fence',r.fence,'active',r.active,
   'authorized_until',case when r.active then o.lease_until else o.authorized_at+o.charged*interval '1 microsecond' end,'server_time',at_time);
 end if;
 if p_action='start' then
  select * into r from public.subscription_auto_runs where account_id=p_account and request_id=p_doc->>'request_id' for update;
  if found then
   if r.run_id<>(p_doc->>'run_id')::uuid or r.semantic_hash<>p_doc->>'semantic_hash' then raise exception 'identity conflict' using errcode='P0003'; end if;
   select document into output from public.subscription_auto_replies where run_id=r.run_id and sequence=0;
   return output; -- Original expiry, never another authorization interval.
  end if;
  select * into old_run from public.subscription_auto_runs where account_id=p_account and active for update;
  if found then
   select * into strict o from public.usage_operations where operation_id=old_run.slice_id;
   if o.lease_until>at_time then raise exception 'auto already running' using errcode='40001'; end if;
   perform public.subscription_auto_finish_slice(old_run.run_id,at_time);
   update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=old_run.run_id;
  end if;
  insert into public.subscription_auto_runs(run_id,account_id,request_id,semantic_hash)
   values((p_doc->>'run_id')::uuid,p_account,p_doc->>'request_id',p_doc->>'semantic_hash') returning * into r;
 else
  select * into r from public.subscription_auto_runs where run_id=(p_doc->>'run_id')::uuid and account_id=p_account for update;
  if not found then raise exception 'run missing' using errcode='P0002'; end if;
  if r.owner_token<>(p_doc->>'owner_token')::uuid then raise exception 'wrong owner' using errcode='42501'; end if;
  select * into reply from public.subscription_auto_replies where run_id=r.run_id and sequence=(p_doc->>'sequence')::bigint;
  if found then
   if reply.action<>p_action or reply.request_fence<>(p_doc->>'fence')::bigint then raise exception 'identity conflict' using errcode='P0003'; end if;
   return reply.document;
  end if;
  if r.fence<>(p_doc->>'fence')::bigint or not r.active or (p_doc->>'sequence')::bigint<>r.sequence+1 then raise exception 'stale owner' using errcode='40001'; end if;
  select * into strict o from public.usage_operations where operation_id=r.slice_id;
  perform public.subscription_auto_finish_slice(r.run_id,at_time);
  if p_action='stop' or o.lease_until<=at_time then
   update public.subscription_auto_runs set active=false,fence=fence+1,sequence=sequence+1 where run_id=r.run_id returning * into r;
   output:=jsonb_build_object('run_id',r.run_id,'sequence',r.sequence,'fence',r.fence,'active',false,'authorized_until',least(at_time,o.lease_until),'server_time',at_time);
   insert into public.subscription_auto_replies values(r.run_id,r.sequence,p_action,(p_doc->>'fence')::bigint,output);
   return output;
  end if;
  update public.subscription_auto_runs set sequence=sequence+1 where run_id=r.run_id returning * into r;
 end if;
 perform public.subscription_account_usage(p_account);
 select * into p from public.usage_periods where account_id=p_account and meter='auto.authorized_running' and starts_at<=at_time and ends_at>at_time order by starts_at desc limit 1 for update;
 if not found or p.unit_scale<>1000000 then raise exception 'auto allowance unavailable' using errcode='P0005'; end if;
 until_time:=least(at_time+interval '15 seconds',p.ends_at,coalesce(b.valid_until,'infinity'));
 amount:=(extract(epoch from(until_time-at_time))*1000000)::bigint;
 if p.allowance is not null then amount:=least(amount,greatest(0,p.allowance-p.used-p.reserved)); end if;
 if amount<=0 then
  if p_action='start' then raise exception 'exhausted' using errcode='P0004'; end if;
  update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=r.run_id returning * into r;
  output:=jsonb_build_object('run_id',r.run_id,'sequence',r.sequence,'fence',r.fence,'active',false,'authorized_until',at_time,'server_time',at_time);
 else
  until_time:=at_time+amount*interval '1 microsecond';
  insert into public.usage_operations(account_id,binding_id,period_id,operation,resource_id,request_id,semantic_hash,policy_version,requested,state,lease_until,authorized_at)
   values(p_account,b.binding_id,p.period_id,'auto.running',r.run_id,r.run_id::text||':'||r.sequence,r.semantic_hash,'subscriptions.approved.2026-10-24',amount,'dispatched',until_time,at_time) returning * into o;
  update public.usage_periods set reserved=reserved+amount where period_id=p.period_id;
  insert into public.usage_events(account_id,operation_id,event,fence,actor_principal,reserved_delta)
   values(p_account,o.operation_id,'auto.reserve',o.fence,session_user,amount);
  update public.subscription_auto_runs set slice_id=o.operation_id where run_id=r.run_id;
  output:=jsonb_build_object('run_id',r.run_id,'owner_token',r.owner_token,'sequence',r.sequence,'fence',r.fence,'active',true,'authorized_until',until_time,'server_time',at_time,'heartbeat_seconds',5);
 end if;
 insert into public.subscription_auto_replies values(r.run_id,r.sequence,p_action,coalesce((p_doc->>'fence')::bigint,1),output);
 return output;
end $$;

create function public.subscription_auto_reap(p_account uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_auto_runs; o public.usage_operations;
begin
 if session_user not in ('usage_reconciler','usage_executor') or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from public.account_plan_bindings where account_id=p_account for update;
 select * into r from public.subscription_auto_runs where account_id=p_account and active for update;
 if not found then return false; end if;
 select * into strict o from public.usage_operations where operation_id=r.slice_id;
 if o.lease_until>clock_timestamp() then return false; end if;
 perform public.subscription_auto_finish_slice(r.run_id,clock_timestamp());
 update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=r.run_id;
 return true;
end $$;
create function public.subscription_auto_sweep(p_limit integer) returns integer
language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; changed integer:=0;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_limit is null or p_limit not between 1 and 100 then raise exception 'invalid batch' using errcode='22023'; end if;
 -- Read candidate IDs without reversing account -> run -> usage lock order.
 for account in select r.account_id from public.subscription_auto_runs r join public.usage_operations o on o.operation_id=r.slice_id
  where r.active and o.lease_until<=clock_timestamp() order by r.account_id limit p_limit loop
  if public.subscription_auto_reap(account) then changed:=changed+1; end if;
 end loop;
 return changed;
end $$;
revoke all on function public.subscription_auto_finish_slice(uuid,timestamptz),public.subscription_auto_call(uuid,text,jsonb),public.subscription_auto_reap(uuid)
 from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_auto_call(uuid,text,jsonb) to usage_executor;
revoke all on function public.subscription_auto_sweep(integer) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_auto_reap(uuid) to usage_reconciler,usage_executor;
grant execute on function public.subscription_auto_sweep(integer) to usage_executor;
commit;
