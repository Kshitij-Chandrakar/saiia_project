-- C13.2 additive account lifecycle and result/Auto integration. No configuration
-- rows, LOGINs, memberships, offers, account backfill or production activation.
begin;
alter table public.account_plan_bindings alter column valid_until drop not null;
do $$ declare r record; begin
 for r in select conname from pg_constraint where conrelid='public.account_plan_bindings'::regclass
 and contype='c' and pg_get_constraintdef(oid) like '%valid_until%' loop
 execute format('alter table public.account_plan_bindings drop constraint %I',r.conname);
 end loop;
end $$;
alter table public.account_plan_bindings add constraint account_binding_validity
  check (isfinite(valid_from) and valid_from>=signup_at and
    (valid_until is null or (isfinite(valid_until) and valid_until>valid_from)));
-- Downgrade retains usage even when it exceeds the new allowance. Admission
-- continues to compare requested <= allowance-used-reserved under its row lock.
do $$ declare r record; begin
 for r in select conname from pg_constraint where conrelid='public.usage_periods'::regclass
   and contype='c' and pg_get_constraintdef(oid) like '%used <= allowance%' loop
   execute format('alter table public.usage_periods drop constraint %I',r.conname);
 end loop;
end $$;
alter table public.usage_operations add column authorized_at timestamptz;
update public.usage_operations o set authorized_at=(select min(recorded_at) from public.usage_events e where e.operation_id=o.operation_id and event='reserve');
alter table public.usage_operations alter column authorized_at set default clock_timestamp();
alter table public.usage_operations alter column authorized_at set not null;
alter table public.usage_operations add column accepted_offer_id uuid references public.catalog_offer_versions(offer_version_id) on delete restrict;
update public.usage_operations o set accepted_offer_id=b.offer_version_id from public.account_plan_bindings b where b.binding_id=o.binding_id;
alter table public.usage_operations alter column accepted_offer_id set not null;
alter table public.usage_periods add column unit_scale bigint not null default 1 check(unit_scale in (1,1000000));
alter table public.usage_operations add column unit_scale bigint not null default 1 check(unit_scale in (1,1000000));

create table public.subscription_configuration (
  singleton boolean primary key default true check(singleton),
  free_offer_id uuid not null references public.catalog_offer_versions(offer_version_id) on delete restrict,
  free_fingerprint text not null check(free_fingerprint ~ '^[0-9a-f]{64}$'),
  verification_since timestamptz not null,
  policy_version text not null check(policy_version='subscriptions.approved.2026-10-24')
);
create table public.subscription_binding_history (
  account_id uuid not null references auth.users(id) on delete restrict,
  revision bigint not null,
  document jsonb not null,
  recorded_at timestamptz not null default clock_timestamp(),
  primary key(account_id,revision)
);
insert into public.subscription_binding_history select account_id,revision,to_jsonb(b),clock_timestamp() from public.account_plan_bindings b;
create table public.subscription_payment_receipts (
  event_id uuid primary key,
  account_id uuid not null references auth.users(id) on delete restrict,
  semantic_hash text not null check(semantic_hash ~ '^[0-9a-f]{64}$'),
  result jsonb not null,
  recorded_at timestamptz not null default clock_timestamp()
);
create function public.subscription_record_binding() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 insert into public.subscription_binding_history values(new.account_id,new.revision,to_jsonb(new),clock_timestamp());
 return new;
end $$;
create trigger subscription_binding_history after insert or update on public.account_plan_bindings
 for each row execute function public.subscription_record_binding();
create function public.subscription_operation_terms() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 select offer_version_id into new.accepted_offer_id from public.account_plan_bindings where account_id=new.account_id;
 select unit_scale into new.unit_scale from public.usage_periods where period_id=new.period_id;
 return new;
end $$;
create trigger subscription_operation_terms before insert on public.usage_operations
 for each row execute function public.subscription_operation_terms();

create function public.subscription_current(p_account uuid,p_bootstrap boolean default false) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; cfg public.subscription_configuration; o public.catalog_offer_versions;
  signup timestamptz; verified timestamptz; at_time timestamptz:=clock_timestamp();
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Auth row serializes concurrent bootstrap before an assignment row exists.
 -- NO KEY UPDATE serializes bootstrap but remains compatible with the Auth
 -- foreign-key KEY SHARE locks taken by existing usage/reconciliation events.
 select created_at,email_confirmed_at into signup,verified from auth.users where id=p_account for no key update;
 if not found or verified is null then raise exception 'verification required' using errcode='42501'; end if;
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 at_time:=clock_timestamp(); -- Validity is evaluated after waiting for authority.
 if found and not b.active then raise exception 'access denied' using errcode='42501'; end if;
 if not found then
   select * into cfg from public.subscription_configuration where singleton for share;
   if not found or not p_bootstrap or verified<cfg.verification_since then raise exception 'bootstrap unavailable' using errcode='P0005'; end if;
   select * into o from public.catalog_offer_versions where offer_version_id=cfg.free_offer_id;
   if not found or o.fingerprint<>cfg.free_fingerprint or o.canonical_json::jsonb->'terms'->>'pricing_mode'<>'free' then
     raise exception 'free configuration unavailable' using errcode='P0005'; end if;
   insert into public.account_plan_bindings(account_id,binding_id,offer_version_id,signup_at,valid_from,valid_until,source_ref,policy_version)
     values(p_account,gen_random_uuid(),o.offer_version_id,signup,at_time,null,'verified.free.bootstrap',cfg.policy_version) returning * into b;
   insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.bootstrap',b.revision,session_user);
 elsif b.valid_until is not null and b.valid_until<=at_time then
   select * into cfg from public.subscription_configuration where singleton for share;
   select * into o from public.catalog_offer_versions where offer_version_id=cfg.free_offer_id;
   if o.offer_version_id is null or o.fingerprint<>cfg.free_fingerprint or o.canonical_json::jsonb->'terms'->>'pricing_mode'<>'free' then
     raise exception 'free configuration unavailable' using errcode='P0005'; end if;
   update public.account_plan_bindings set offer_version_id=o.offer_version_id,price_id=null,valid_from=at_time,
     valid_until=null,revision=revision+1,source_ref='paid.period.expired',policy_version=cfg.policy_version,active=true
     where account_id=p_account returning * into b;
   insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.expire_to_free',b.revision,session_user);
 end if;
 if not b.active or at_time<b.valid_from then raise exception 'access denied' using errcode='42501'; end if;
 select * into strict o from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
 if o.fingerprint<>encode(sha256(convert_to(o.canonical_json,'UTF8')),'hex') then raise exception 'corrupt terms' using errcode='55000'; end if;
 return jsonb_build_object('binding',to_jsonb(b),'snapshot',o.canonical_json,'fingerprint',o.fingerprint,'at',at_time,
   'offer_version_id',o.offer_version_id,'plan_id',o.plan_id,'version',o.version);
end $$;

create or replace function public.usage_account_read(p_account uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; o public.catalog_offer_versions;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 if not found or not b.active or clock_timestamp()<b.valid_from or (b.valid_until is not null and clock_timestamp()>=b.valid_until) then
   raise exception 'authority unavailable' using errcode='42501'; end if;
 select * into strict o from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
 if o.fingerprint<>encode(sha256(convert_to(o.canonical_json,'UTF8')),'hex') then raise exception 'corrupt terms' using errcode='55000'; end if;
 return jsonb_build_object('binding',to_jsonb(b),'snapshot',o.canonical_json,'fingerprint',o.fingerprint,'at',clock_timestamp(),
   'offer_version_id',o.offer_version_id,'plan_id',o.plan_id,'version',o.version);
end $$;

-- Only a separate backend-verified payment capability can call this. C12 must
-- supply the verifier; no HTTP route, default verifier or login is provisioned.
create function public.subscription_payment_apply(p_account uuid,p_event uuid,p_offer uuid,p_price uuid,p_until timestamptz,p_hash text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; r public.subscription_payment_receipts; at_time timestamptz:=clock_timestamp();
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 if not found or not b.active then raise exception 'binding required' using errcode='42501'; end if;
 at_time:=clock_timestamp();
 select * into r from public.subscription_payment_receipts where event_id=p_event;
 if found then
   if r.account_id<>p_account or r.semantic_hash<>p_hash then raise exception 'payment identity conflict' using errcode='P0003'; end if;
   return r.result;
 end if;
 if p_until is null or not isfinite(p_until) or p_until<=at_time or not exists(
   select 1 from public.catalog_price_versions where price_id=p_price and offer_version_id=p_offer) then
   raise exception 'invalid verified payment' using errcode='22023'; end if;
 update public.account_plan_bindings set offer_version_id=p_offer,price_id=p_price,valid_from=at_time,valid_until=p_until,
   active=true,revision=revision+1,source_ref='verified.payment',policy_version='subscriptions.approved.2026-10-24'
   where account_id=p_account returning * into b;
 insert into public.subscription_payment_receipts values(p_event,p_account,p_hash,to_jsonb(b),at_time);
 insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.verified_payment',b.revision,session_user);
 return to_jsonb(b);
end $$;

-- Cross-plan scopes retain consumption by operation authorization time. This
-- handles daily->monthly Auto and unlimited->finite monthly quotas without
-- granting a new pool. Storage is lifetime capacity. No data is removed.
create function public.subscription_balance(p_period uuid) returns bigint[]
language sql security definer set search_path=pg_catalog as $$
 select array[coalesce(sum(e.used_delta::numeric*target.unit_scale/o.unit_scale),0)::bigint,coalesce(sum(e.reserved_delta::numeric*target.unit_scale/o.unit_scale),0)::bigint]
 from public.usage_periods target left join public.usage_operations o on o.account_id=target.account_id
   and o.authorized_at>=target.starts_at and o.authorized_at<target.ends_at
 left join public.usage_periods origin on origin.period_id=o.period_id and origin.meter=target.meter
 left join public.usage_events e on e.operation_id=o.operation_id and origin.period_id is not null
 where target.period_id=p_period
$$;
create function public.subscription_refresh_period(p_period uuid) returns void
language plpgsql security definer set search_path=pg_catalog as $$
declare totals bigint[];
begin
 totals:=public.subscription_balance(p_period);
 update public.usage_periods set used=totals[1],reserved=totals[2] where period_id=p_period;
end $$;

create function public.subscription_account_usage(p_account uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb:='[]'; b public.account_plan_bindings; terms jsonb; item jsonb; bounds timestamptz[]; p public.usage_periods; scale bigint; cap boolean; at_time timestamptz;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform public.usage_account_read(p_account);
 at_time:=clock_timestamp();
 select * into b from public.account_plan_bindings where account_id=p_account;
 select canonical_json::jsonb->'terms' into terms from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
 for item in select x from jsonb_array_elements(coalesce(terms->'allowances','[]')||coalesce(terms->'storage_allowances','[]')||coalesce(terms->'limits','[]')) x loop
   if item->>'meter' is null then continue; end if;
   cap:=item->>'kind'='storage' or exists(select 1 from jsonb_array_elements(coalesce(terms->'storage_allowances','[]')) x where x->>'meter'=item->>'meter');
   if item->>'mode' is null and not cap then continue; end if;
   bounds:=public.usage_period_bounds(at_time,b.signup_at,coalesce(item->'period'->>'unit','lifetime'));
   scale:=case when item->>'meter'='auto.authorized_running' then 1000000 else 1 end;
   insert into public.usage_periods(account_id,meter,starts_at,ends_at,mode,capacity,allowance,unit_scale)
     values(p_account,item->>'meter',bounds[1],bounds[2],coalesce(item->>'mode','limited'),coalesce(cap,false),(item->>'amount')::bigint*scale,scale)
     on conflict(account_id,meter,starts_at) do update set ends_at=excluded.ends_at,mode=excluded.mode,allowance=excluded.allowance,unit_scale=excluded.unit_scale;
   select * into strict p from public.usage_periods where account_id=p_account and meter=item->>'meter' and starts_at=bounds[1] for update;
   perform public.subscription_refresh_period(p.period_id);
   select * into p from public.usage_periods where period_id=p.period_id;
   result:=result||jsonb_build_array(jsonb_build_object('meter',p.meter,'mode',p.mode,'unit',item->>'unit','unit_scale',p.unit_scale,
     'allowance',p.allowance::text,'used',p.used::text,'reserved',p.reserved::text,'starts_at',p.starts_at,
     'ends_at',case when isfinite(p.ends_at) then to_jsonb(p.ends_at) else 'null'::jsonb end));
 end loop;
 return result;
end $$;

do $$ declare t text; begin
 foreach t in array array['subscription_configuration','subscription_binding_history','subscription_payment_receipts'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler',t);
 end loop;
 foreach t in array array['subscription_binding_history','subscription_payment_receipts'] loop
  execute format('create trigger immutable_rows before update or delete on public.%I for each row execute function public.catalog_reject_mutation()',t);
  execute format('create trigger immutable_truncate before truncate on public.%I for each statement execute function public.catalog_reject_mutation()',t);
 end loop;
end $$;
revoke all on function public.subscription_record_binding(),public.subscription_operation_terms(),public.subscription_current(uuid,boolean),
 public.subscription_payment_apply(uuid,uuid,uuid,uuid,timestamptz,text),public.subscription_balance(uuid),public.subscription_refresh_period(uuid),
 public.subscription_account_usage(uuid) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_current(uuid,boolean),public.subscription_account_usage(uuid) to usage_executor;
grant execute on function public.subscription_payment_apply(uuid,uuid,uuid,uuid,timestamptz,text) to usage_binding_executor;

-- Preserve the original state machine; refresh cross-plan balances before admission.
create or replace function public.usage_call(p_account uuid,p_action text,p_document jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; o public.usage_operations; p public.usage_periods;
  terms jsonb; a jsonb; periods timestamptz[]; capacity boolean:=false;
  v_now timestamptz:=clock_timestamp(); amount bigint; old_state text; delta bigint:=0;
  allowed text[]; event_name text; sum_used bigint; sum_reserved bigint;
begin
  if current_setting('role',true)<>'none' or
    (session_user<>'usage_executor' and not(session_user='usage_reconciler' and p_action in ('recover','reconcile','reconcile_release','audit','rebuild'))) then
    raise exception 'usage denied' using errcode='42501';
  end if;
  if p_action in ('reconcile','reconcile_release') and session_user<>'usage_reconciler' then raise exception 'usage denied' using errcode='42501'; end if;
  if p_action='rebuild' and session_user<>'usage_reconciler' then raise exception 'usage denied' using errcode='42501'; end if;
  -- Global lock order: binding -> period -> operation, for every path including
  -- replay/revocation/reconciliation. Account-wide serialization is deliberate.
  select * into b from public.account_plan_bindings where account_id=p_account for update;
  if not found then raise exception 'missing account binding' using errcode='42501'; end if;
  if session_user='usage_executor' then perform public.usage_account_read(p_account); end if;
  v_now:=clock_timestamp();
  if p_action='reserve' then
    allowed:=array['operation','resource_id','request_id','semantic_hash','meter','requested','policy_version','lease_seconds'];
  elsif p_action='read' then allowed:=array['operation_id'];
  elsif p_action='dispatch' then allowed:=array['operation_id','fence','claim_token'];
  elsif p_action='checkpoint' then allowed:=array['operation_id','fence','claim_token','result_ref'];
  elsif p_action='settle' then allowed:=array['operation_id','fence','claim_token','charged','policy_version'];
  elsif p_action='release' then allowed:=array['operation_id','fence','claim_token','policy_version'];
  elsif p_action='vacate' then allowed:=array['operation_id','fence','claim_token','policy_version'];
  elsif p_action='uncertain' then allowed:=array['operation_id','fence','claim_token'];
  elsif p_action='recover' then allowed:=array['operation_id'];
  elsif p_action='reconcile' then allowed:=array['operation_id','fence','charged','result_ref','evidence','policy_version'];
  elsif p_action='reconcile_release' then allowed:=array['operation_id','fence','evidence','policy_version'];
  elsif p_action in ('audit','rebuild') then allowed:=array['period_id'];
  else raise exception 'invalid action' using errcode='22023'; end if;
  if jsonb_typeof(p_document) is distinct from 'object' or p_document - allowed <> '{}'::jsonb or not p_document ?& allowed then raise exception 'invalid fields' using errcode='22023'; end if;
  if p_action in ('audit','rebuild') then
    select * into strict p from public.usage_periods where period_id=(p_document->>'period_id')::uuid and account_id=p_account for update;
    select totals[1],totals[2] into sum_used,sum_reserved
      from (select public.subscription_balance(p.period_id) totals) balance;
    if (p.used,p.reserved) is distinct from (sum_used,sum_reserved) then
      if p_action='audit' then raise exception 'balance drift' using errcode='55000'; end if;
      update public.usage_periods set used=sum_used,reserved=sum_reserved where period_id=p.period_id;
      insert into public.usage_events(account_id,operation_id,event,fence,actor_principal)
        values(p_account,null,'aggregate.rebuild',b.revision,session_user);
      return jsonb_build_object('consistent',true,'repaired',true,'used',sum_used,'reserved',sum_reserved);
    end if;
    return jsonb_build_object('consistent',true,'used',p.used,'reserved',p.reserved);
  end if;
  if p_action='reserve' then
    select * into o from public.usage_operations where account_id=p_account and operation=p_document->>'operation'
      and resource_id=(p_document->>'resource_id')::uuid and request_id=p_document->>'request_id';
    if found then
      if (o.semantic_hash,o.policy_version,o.requested) is distinct from
        (p_document->>'semantic_hash',p_document->>'policy_version',(p_document->>'requested')::bigint)
        or not exists(select 1 from public.usage_periods where period_id=o.period_id and meter=p_document->>'meter') then
        raise exception 'request conflict' using errcode='P0003';
      end if;
      return to_jsonb(o)||jsonb_build_object('execution_permitted',false); -- No execution claim, new period or event on replay.
    end if;
    select canonical_json::jsonb->'terms' into terms from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
    select x into a from jsonb_array_elements(terms->'allowances') x where x->>'meter'=p_document->>'meter';
    if a is null then
      select x into a from jsonb_array_elements(terms->'storage_allowances') x where x->>'meter'=p_document->>'meter';
      capacity:=a is not null;
    end if;
    if a is null then
      select jsonb_build_object('mode','limited','amount',x->'amount','feature',x->'feature','period',null) into a
        from jsonb_array_elements(terms->'limits') x where x->>'meter'=p_document->>'meter' and x->>'kind'='storage';
      capacity:=a is not null;
    end if;
    if a is null or not exists(select 1 from jsonb_array_elements(terms->'entitlements') x
      where x->>'feature'=a->>'feature' and x->>'allowed'='true') then raise exception 'meter denied' using errcode='42501'; end if;
    if a->>'mode' not in ('limited','unlimited') or (a->>'mode'='limited' and a->>'amount' is null) then
      raise exception 'unsupported allowance' using errcode='55000'; end if;
    periods:=public.usage_period_bounds(v_now,b.signup_at,coalesce(a->'period'->>'unit','lifetime'));
    insert into public.usage_periods(account_id,meter,starts_at,ends_at,mode,capacity,allowance)
      values(p_account,p_document->>'meter',periods[1],periods[2],a->>'mode',capacity,(a->>'amount')::bigint) on conflict(account_id,meter,starts_at) do update set mode=excluded.mode,allowance=excluded.allowance,ends_at=excluded.ends_at;
    select * into strict p from public.usage_periods where account_id=p_account and meter=p_document->>'meter' and starts_at=periods[1] for update;
    if (p.mode,p.allowance,p.capacity,p.ends_at) is distinct from (a->>'mode',(a->>'amount')::bigint,capacity,periods[2]) then
      raise exception 'allowance migration unavailable' using errcode='55000'; end if;
    perform public.subscription_refresh_period(p.period_id);
    select * into p from public.usage_periods where period_id=p.period_id;
    amount:=(p_document->>'requested')::bigint;
    if amount is null or amount<=0 or (p_document->>'lease_seconds')::int not between 1 and 300 then
      raise exception 'invalid reservation' using errcode='22023'; end if;
    if p.allowance is not null and amount>p.allowance-p.used-p.reserved then raise exception 'allowance exhausted' using errcode='P0004'; end if;
    insert into public.usage_operations(account_id,binding_id,period_id,operation,resource_id,request_id,semantic_hash,policy_version,requested,state,lease_until)
      values(p_account,b.binding_id,p.period_id,p_document->>'operation',(p_document->>'resource_id')::uuid,p_document->>'request_id',
        p_document->>'semantic_hash',p_document->>'policy_version',amount,'reserved',v_now+make_interval(secs=>(p_document->>'lease_seconds')::int)) returning * into o;
    update public.usage_periods set reserved=reserved+amount where period_id=p.period_id;
    insert into public.usage_events(account_id,operation_id,event,fence,actor_principal,reserved_delta)
      values(p_account,o.operation_id,'reserve',o.fence,session_user,amount);
    return to_jsonb(o)||jsonb_build_object('execution_permitted',false);
  end if;
  -- Resolve identity without locking operation before its period.
  select period_id into p.period_id from public.usage_operations where operation_id=(p_document->>'operation_id')::uuid and account_id=p_account;
  if not found then raise exception 'operation not found' using errcode='P0002'; end if;
  select * into p from public.usage_periods where period_id=p.period_id for update;
  select * into strict o from public.usage_operations where operation_id=(p_document->>'operation_id')::uuid and account_id=p_account for update;
  old_state:=o.state;
  if p_action='read' then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
  if p_action='recover' then
    if o.state in ('settled','released','uncertain') then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
    if o.lease_until>v_now then raise exception 'lease live' using errcode='40001'; end if;
    -- Never grant another dispatch: even an expired dispatched claim may have run.
    update public.usage_operations set state='uncertain',fence=fence+1 where operation_id=o.operation_id returning * into o;
  else
    if o.fence is distinct from (p_document->>'fence')::bigint or (session_user='usage_executor' and o.claim_token is distinct from (p_document->>'claim_token')::uuid) then
      raise exception 'stale worker' using errcode='40001'; end if;
    if p_action in ('settle','release','reconcile','reconcile_release','vacate') and o.policy_version is distinct from p_document->>'policy_version' then
      raise exception 'policy mismatch' using errcode='22023'; end if;
    if p_action='dispatch' then
      if o.state='dispatched' then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
      if o.state<>'reserved' or o.lease_until<=v_now then raise exception 'invalid dispatch' using errcode='40001'; end if;
      update public.usage_operations set state='dispatched' where operation_id=o.operation_id returning * into o;
    elsif p_action='checkpoint' then
      if o.state in ('checkpointed','settled') and o.result_ref=(p_document->>'result_ref')::uuid then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
      if o.state<>'dispatched' or o.lease_until<=v_now then raise exception 'invalid checkpoint' using errcode='40001'; end if;
      update public.usage_operations set state='checkpointed',result_ref=(p_document->>'result_ref')::uuid where operation_id=o.operation_id returning * into o;
      if o.result_ref is null then raise exception 'result required' using errcode='22023'; end if;
    elsif p_action='uncertain' then
      if o.state='uncertain' then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
      if o.state not in ('dispatched','checkpointed') then raise exception 'invalid uncertainty' using errcode='40001'; end if;
      update public.usage_operations set state='uncertain',fence=fence+1 where operation_id=o.operation_id returning * into o;
    elsif p_action='reconcile_release' then
      if p_document->>'evidence' is null then raise exception 'evidence required' using errcode='22023'; end if;
      if o.state='released' and o.recovery_evidence=(p_document->>'evidence')::uuid then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
      if o.state<>'uncertain' then raise exception 'invalid reconciliation' using errcode='40001'; end if;
      update public.usage_periods set reserved=reserved-o.requested where period_id=o.period_id;
      update public.usage_operations set state='released',recovery_evidence=(p_document->>'evidence')::uuid where operation_id=o.operation_id returning * into o;
    elsif p_action='vacate' then
      if not p.capacity or o.state<>'settled' then raise exception 'not settled capacity' using errcode='40001'; end if;
      if o.capacity_released then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
      delta:=-o.charged;
      update public.usage_periods set used=used+delta where period_id=o.period_id;
      update public.usage_operations set capacity_released=true where operation_id=o.operation_id returning * into o;
    elsif p_action in ('settle','reconcile','release') then
      if p_action='release' then
        if o.state='released' then return to_jsonb(o)||jsonb_build_object('execution_permitted',false); end if;
        if o.state<>'reserved' then raise exception 'cannot release dispatched work' using errcode='40001'; end if;
      else
        amount:=(p_document->>'charged')::bigint;
        if amount is null or amount<0 or amount>o.requested then raise exception 'invalid settlement' using errcode='22023'; end if;
        if o.state='settled' then
          if o.charged<>amount or (p_action='reconcile' and (o.result_ref is distinct from (p_document->>'result_ref')::uuid or o.recovery_evidence is distinct from (p_document->>'evidence')::uuid)) then
            raise exception 'settlement conflict' using errcode='P0003'; end if;
          return to_jsonb(o)||jsonb_build_object('execution_permitted',false);
        end if;
        if (p_action='settle' and (o.state<>'checkpointed' or o.lease_until<=v_now))
          or (p_action='reconcile' and (o.state<>'uncertain' or p_document->>'evidence' is null or p_document->>'result_ref' is null)) then
          raise exception 'invalid settlement state' using errcode='40001'; end if;
        if p_action='reconcile' then
          if o.result_ref is not null and o.result_ref is distinct from (p_document->>'result_ref')::uuid then
            raise exception 'checkpoint conflict' using errcode='P0003';
          end if;
          o.result_ref:=(p_document->>'result_ref')::uuid;o.recovery_evidence:=(p_document->>'evidence')::uuid;
        end if;
        delta:=amount;
      end if;
      update public.usage_periods set reserved=reserved-o.requested,used=used+delta where period_id=o.period_id;
      update public.usage_operations set state=case when p_action='release' then 'released' else 'settled' end,
        charged=case when p_action='release' then null else delta end,result_ref=o.result_ref,recovery_evidence=o.recovery_evidence
        where operation_id=o.operation_id returning * into o;
    end if;
  end if;
  event_name:=p_action;
  insert into public.usage_events(account_id,operation_id,event,fence,actor_principal,used_delta,reserved_delta)
    values(p_account,o.operation_id,event_name,o.fence,session_user,delta,case when p_action in ('settle','reconcile','release','reconcile_release') then -o.requested else 0 end);
  return to_jsonb(o)||jsonb_build_object('execution_permitted',p_action='dispatch' and old_state='reserved');
end $$;

commit;
