-- C13.1 closed foundation. No LOGIN, role memberships, seeds or runtime activation.
begin;
create role usage_executor nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
create role usage_binding_executor nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
create role usage_reconciler nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;

create table public.account_plan_bindings (
  account_id uuid primary key references auth.users(id) on delete restrict,
  binding_id uuid not null unique,
  offer_version_id uuid not null references public.catalog_offer_versions(offer_version_id) on delete restrict,
  price_id uuid references public.catalog_price_versions(price_id) on delete restrict,
  signup_at timestamptz not null,
  valid_from timestamptz not null,
  valid_until timestamptz not null check(valid_until>valid_from and isfinite(valid_from) and isfinite(valid_until) and valid_from>=signup_at),
  source_ref text not null check(source_ref ~ '^[a-z][a-z0-9._:-]{0,119}$'),
  policy_version text not null check(policy_version ~ '^[a-z][a-z0-9._:-]{0,119}$'),
  revision bigint not null default 1 check(revision>0),
  active boolean not null default true
);
-- The first foundation deliberately cannot replace terms or renew a binding:
-- assignment/migration/expiry policy is unresolved. It can revoke/reactivate by CAS.
create table public.usage_periods (
  period_id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.account_plan_bindings(account_id) on delete restrict,
  meter text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null check(ends_at>starts_at),
  mode text not null check(mode in ('limited','unlimited')),
  capacity boolean not null,
  allowance bigint check(allowance>=0),
  used bigint not null default 0 check(used>=0),
  reserved bigint not null default 0 check(reserved>=0),
  check((mode='unlimited')=(allowance is null)),
  check(allowance is null or (used<=allowance and reserved<=allowance-used)),
  unique(account_id,meter,starts_at)
);
create table public.usage_operations (
  operation_id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.account_plan_bindings(account_id) on delete restrict,
  binding_id uuid not null references public.account_plan_bindings(binding_id) on delete restrict,
  period_id uuid not null references public.usage_periods(period_id) on delete restrict,
  operation text not null check(operation ~ '^[a-z][a-z0-9._:-]{0,119}$'),
  resource_id uuid not null,
  request_id text not null check(request_id ~ '^[A-Za-z0-9._:-]{1,120}$'),
  semantic_hash text not null check(semantic_hash ~ '^[0-9a-f]{64}$'),
  policy_version text not null check(policy_version ~ '^[a-z][a-z0-9._:-]{0,119}$'),
  requested bigint not null check(requested>0),
  charged bigint check(charged>=0 and charged<=requested),
  state text not null check(state in ('reserved','dispatched','checkpointed','uncertain','settled','released')),
  fence bigint not null default 1 check(fence>0),
  claim_token uuid not null default gen_random_uuid(),
  lease_until timestamptz not null,
  result_ref uuid,
  recovery_evidence uuid,
  capacity_released boolean not null default false,
  unique(account_id,operation,resource_id,request_id),
  check((state='settled')=(charged is not null)),
  check(state<>'settled' or result_ref is not null)
);
-- Immutable audit/events are separate from mutable operation retry state.
create table public.usage_events (
  event_id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.account_plan_bindings(account_id) on delete restrict,
  operation_id uuid references public.usage_operations(operation_id) on delete restrict,
  event text not null,
  fence bigint not null,
  actor_principal text not null,
  used_delta bigint not null default 0,
  reserved_delta bigint not null default 0,
  recorded_at timestamptz not null default clock_timestamp()
);
create trigger immutable_rows before update or delete on public.usage_events
  for each row execute function public.catalog_reject_mutation();
create trigger immutable_truncate before truncate on public.usage_events
  for each statement execute function public.catalog_reject_mutation();
do $$ declare t text; begin
  foreach t in array array['account_plan_bindings','usage_periods','usage_operations','usage_events'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('alter table public.%I force row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor',t);
  end loop;
end $$;

-- Privileged infrastructure only; catalog permission grants confer no access.
create function public.usage_binding_call(p_account uuid,p_action text,p_document jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; o public.catalog_offer_versions; signup timestamptz;
begin
  if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then
    raise exception 'usage denied' using errcode='42501';
  end if;
  if p_action='assign' then
    if p_document - array['binding_id','offer_version_id','price_id','valid_from','valid_until','source_ref','policy_version'] <> '{}'::jsonb then
      raise exception 'invalid binding' using errcode='22023';
    end if;
    -- The Auth row is authoritative; no caller-controlled signup anchor.
    select created_at into signup from auth.users where id=p_account for share;
    if signup is null then raise exception 'missing account' using errcode='P0002'; end if;
    select * into o from public.catalog_offer_versions where offer_version_id=(p_document->>'offer_version_id')::uuid;
    if not found then raise exception 'missing terms' using errcode='P0002'; end if;
    if p_document->>'price_id' is not null and not exists(select 1 from public.catalog_price_versions
      where price_id=(p_document->>'price_id')::uuid and offer_version_id=o.offer_version_id) then
      raise exception 'invalid price reference' using errcode='22023';
    end if;
    if coalesce(o.canonical_json::jsonb->'terms'->>'pricing_mode','')='priced' and p_document->>'price_id' is null then
      raise exception 'price required' using errcode='22023';
    end if;
    insert into public.account_plan_bindings(account_id,binding_id,offer_version_id,price_id,signup_at,valid_from,valid_until,source_ref,policy_version)
      values(p_account,(p_document->>'binding_id')::uuid,o.offer_version_id,(p_document->>'price_id')::uuid,signup,
        (p_document->>'valid_from')::timestamptz,(p_document->>'valid_until')::timestamptz,p_document->>'source_ref',p_document->>'policy_version')
      on conflict(account_id) do nothing;
    if found then
      insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.assign',1,session_user);
    end if;
    select * into b from public.account_plan_bindings where account_id=p_account for share;
    if (b.binding_id,b.offer_version_id,b.price_id,b.valid_from,b.valid_until,b.source_ref,b.policy_version) is distinct from
      ((p_document->>'binding_id')::uuid,(p_document->>'offer_version_id')::uuid,(p_document->>'price_id')::uuid,
       (p_document->>'valid_from')::timestamptz,(p_document->>'valid_until')::timestamptz,p_document->>'source_ref',p_document->>'policy_version') then
      raise exception 'binding conflict' using errcode='40001';
    end if;
  elsif p_action='status' then
    if p_document - array['expected_revision','active'] <> '{}'::jsonb or jsonb_typeof(p_document->'active')<>'boolean' then
      raise exception 'invalid status' using errcode='22023';
    end if;
    select * into b from public.account_plan_bindings where account_id=p_account for update;
    if not found then raise exception 'missing binding' using errcode='P0002'; end if;
    if b.revision<>(p_document->>'expected_revision')::bigint then raise exception 'revision conflict' using errcode='40001'; end if;
    update public.account_plan_bindings set active=(p_document->>'active')::boolean,revision=revision+1 where account_id=p_account returning * into b;
    insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.status',b.revision,session_user);
  else raise exception 'invalid action' using errcode='22023'; end if;
  return to_jsonb(b);
end $$;

-- A closed read channel also returns exact immutable bytes for Python validation.
create function public.usage_account_read(p_account uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; o public.catalog_offer_versions;
begin
  if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'usage denied' using errcode='42501'; end if;
  select * into b from public.account_plan_bindings where account_id=p_account for update;
  if not found or not b.active or not (clock_timestamp()>=b.valid_from and clock_timestamp()<b.valid_until) then
    raise exception 'authority unavailable' using errcode='42501';
  end if;
  select * into strict o from public.catalog_offer_versions where offer_version_id=b.offer_version_id;
  if o.fingerprint<>encode(sha256(convert_to(o.canonical_json,'UTF8')),'hex') then raise exception 'corrupt terms' using errcode='55000'; end if;
  return jsonb_build_object('binding',to_jsonb(b),'snapshot',o.canonical_json,'fingerprint',o.fingerprint,'at',clock_timestamp(),
    'offer_version_id',o.offer_version_id,'plan_id',o.plan_id,'version',o.version);
end $$;

create function public.usage_terms_read(p_offer uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.catalog_offer_versions;
begin
  if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'usage denied' using errcode='42501'; end if;
  select * into o from public.catalog_offer_versions where offer_version_id=p_offer;
  if not found then raise exception 'terms not found' using errcode='P0002'; end if;
  return jsonb_build_object('snapshot',o.canonical_json,'fingerprint',o.fingerprint,
    'offer_version_id',o.offer_version_id,'plan_id',o.plan_id,'version',o.version);
end $$;

-- IST calendar helper. Derives boundaries from Auth anchor/server time, never
-- accepts a client period or destructive reset. Infinity is only a storage/
-- unmetered accumulation scope, not subscription lifetime/validity.
create function public.usage_period_bounds(p_now timestamptz,p_signup timestamptz,p_cadence text)
returns timestamptz[] language plpgsql immutable set search_path=pg_catalog as $$
declare local_now timestamp:=p_now at time zone 'Asia/Kolkata'; m date; anchor int; a timestamp; z timestamp;
begin
  if p_now<p_signup then raise exception 'invalid anchor' using errcode='22023'; end if;
  if p_cadence='day' then a:=date_trunc('day',local_now);z:=a+interval '1 day';
  elsif p_cadence='month' then
    anchor:=extract(day from p_signup at time zone 'Asia/Kolkata');m:=date_trunc('month',local_now)::date;
    a:=m+(least(anchor,extract(day from (m+interval '1 month - 1 day')))::int-1);
    if local_now<a then m:=(m-interval '1 month')::date; end if;
    a:=m+(least(anchor,extract(day from (m+interval '1 month - 1 day')))::int-1);
    m:=(m+interval '1 month')::date;
    z:=m+(least(anchor,extract(day from (m+interval '1 month - 1 day')))::int-1);
  elsif p_cadence='lifetime' then return array[p_signup,'infinity'::timestamptz];
  else raise exception 'unsupported period' using errcode='22023'; end if;
  return array[a at time zone 'Asia/Kolkata',z at time zone 'Asia/Kolkata'];
end $$;

create function public.usage_call(p_account uuid,p_action text,p_document jsonb) returns jsonb
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
    select coalesce(sum(used_delta),0)::bigint,coalesce(sum(reserved_delta),0)::bigint into sum_used,sum_reserved
      from public.usage_events e join public.usage_operations u using(operation_id) where u.period_id=p.period_id;
    if (p.used,p.reserved) is distinct from (sum_used,sum_reserved) then
      if p_action='audit' then raise exception 'balance drift' using errcode='55000'; end if;
      update public.usage_periods set used=sum_used,reserved=sum_reserved where period_id=p.period_id;
      select * into strict o from public.usage_operations where period_id=p.period_id order by operation_id limit 1;
      insert into public.usage_events(account_id,operation_id,event,fence,actor_principal)
        values(p_account,o.operation_id,'aggregate.rebuild',o.fence,session_user);
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
      values(p_account,p_document->>'meter',periods[1],periods[2],a->>'mode',capacity,(a->>'amount')::bigint) on conflict do nothing;
    select * into strict p from public.usage_periods where account_id=p_account and meter=p_document->>'meter' and starts_at=periods[1] for update;
    if (p.mode,p.allowance,p.capacity,p.ends_at) is distinct from (a->>'mode',(a->>'amount')::bigint,capacity,periods[2]) then
      raise exception 'allowance migration unavailable' using errcode='55000'; end if;
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

revoke all on function public.usage_binding_call(uuid,text,jsonb),public.usage_account_read(uuid),public.usage_terms_read(uuid),
  public.usage_period_bounds(timestamptz,timestamptz,text),public.usage_call(uuid,text,jsonb)
  from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant usage on schema public to usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.usage_binding_call(uuid,text,jsonb),public.usage_terms_read(uuid) to usage_binding_executor;
grant execute on function public.usage_account_read(uuid),public.usage_call(uuid,text,jsonb) to usage_executor;
grant execute on function public.usage_call(uuid,text,jsonb) to usage_reconciler;
commit;
