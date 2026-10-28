-- C12 additive preparation only. No LOGIN, credentials, assignments or enablement.
begin;
create table public.billing_operations (
 operation_id uuid primary key,
 account_id uuid not null references auth.users(id) on delete restrict,
 offer_version_id uuid not null references public.catalog_offer_versions on delete restrict,
 price_id uuid not null references public.catalog_price_versions on delete restrict,
 mode text not null check(mode='test'),
 merchant text not null,
 provider_plan text not null,
 total_count integer not null check(total_count>0),
 consent_at timestamptz,
 cancel_requested boolean not null default false,
 provider_state text,
 snapshot text not null,
 fingerprint text not null,
 amount bigint not null check(amount>0),
 currency text not null check(currency='INR'),
 interval_unit text not null check(interval_unit in ('month','year')),
 state text not null default 'prepared' check(state in ('prepared','creating','uncertain','ready','pending','confirmed','expired')),
 provider_id text unique,
 created_at timestamptz not null default clock_timestamp(),
 last_checked_at timestamptz,
 result jsonb
);
create unique index billing_one_pending_account on public.billing_operations(account_id) where state<>'expired';
create table public.billing_evidence (
 payment_id text primary key,
 operation_id uuid not null references public.billing_operations on delete restrict,
 evidence_hash text not null,
 event_id uuid not null unique,
 invoice_id text not null unique,
 paid_until timestamptz not null,
 applied boolean not null default false,
 recorded_at timestamptz not null default clock_timestamp()
);
create table public.billing_webhook_events (
 event_hash text primary key check(event_hash ~ '^[0-9a-f]{64}$'),
 merchant text not null,
 provider_id text not null,
 event_type text not null,
 recorded_at timestamptz not null default clock_timestamp()
);
alter table public.billing_webhook_events enable row level security;
revoke all on public.billing_webhook_events from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
alter table public.billing_operations enable row level security;
alter table public.billing_evidence enable row level security;
revoke all on public.billing_operations,public.billing_evidence from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

create function public.billing_call(p_account uuid,p_action text,p_id uuid,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.billing_operations; v public.catalog_visibility; s public.catalog_offer_versions;
 p public.catalog_price_versions; b public.account_plan_bindings; e public.billing_evidence; outcome jsonb;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Lock ordering matches C13: account before payment. Serializes tabs/events.
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 if not found or not b.active or not exists(select 1 from auth.users where id=p_account and email_confirmed_at is not null) then raise exception 'denied' using errcode='42501'; end if;
 select * into o from public.billing_operations where operation_id=p_id for update;
 if found and o.account_id<>p_account then raise exception 'denied' using errcode='42501'; end if;
 if p_action='prepare' then
  if o.operation_id is not null then
   if o.offer_version_id<>(p_doc->>'offer_version_id')::uuid or o.price_id<>(p_doc->>'price_id')::uuid or o.merchant<>p_doc->>'merchant' then raise exception 'identity conflict' using errcode='P0003'; end if;
   return to_jsonb(o);
  end if;
  select * into o from public.billing_operations where account_id=p_account and state<>'expired' for update;
  if found then
   if o.offer_version_id<>(p_doc->>'offer_version_id')::uuid or o.price_id<>(p_doc->>'price_id')::uuid or o.merchant<>p_doc->>'merchant' then raise exception 'checkout pending' using errcode='P0003'; end if;
   return to_jsonb(o);
  end if;
  -- Upgrade/proration and early repurchase charges have no approved rule.
  if b.price_id is not null and b.valid_until>clock_timestamp() then raise exception 'paid change unavailable' using errcode='22023'; end if;
  select * into v from public.catalog_visibility where offer_version_id=(p_doc->>'offer_version_id')::uuid for share;
  if not found or v.state<>'visible' or v.valid_from>clock_timestamp() or v.valid_until<=clock_timestamp() then raise exception 'offer unavailable' using errcode='22023'; end if;
  select * into s from public.catalog_offer_versions where offer_version_id=v.offer_version_id;
  select * into p from public.catalog_price_versions where price_id=(p_doc->>'price_id')::uuid and offer_version_id=s.offer_version_id;
  if not found or p.currency<>'INR' or p.exponent<>2 or p.amount_minor<=0 or p.billing_count<>1 or
    jsonb_array_length(coalesce(s.canonical_json::jsonb->'terms'->'discounts','[]'))>0 or p.document->>'tax_policy_ref' is distinct from p_doc->>'total_policy_ref' or coalesce(p_doc->>'total_policy_ref','')='' then raise exception 'commercial terms unavailable' using errcode='22023'; end if;
  if (p_doc->>'total_count')::integer > (case when p.billing_unit='month' then 12 else 5 end) then raise exception 'mandate term mismatch' using errcode='22023'; end if;
  insert into public.billing_operations(operation_id,account_id,offer_version_id,price_id,mode,merchant,provider_plan,total_count,snapshot,fingerprint,amount,currency,interval_unit)
   values(p_id,p_account,s.offer_version_id,p.price_id,'test',p_doc->>'merchant',p_doc->>'provider_plan',(p_doc->>'total_count')::integer,s.canonical_json,s.fingerprint,p.amount_minor,p.currency,p.billing_unit) returning * into o;
 elsif o.operation_id is null then raise exception 'not found' using errcode='42501';
 elsif p_action='claim' then
  if p_doc->>'consent' is distinct from 'true' then raise exception 'consent required' using errcode='22023'; end if;
  if o.state='prepared' then
   update public.billing_operations set state='creating',consent_at=clock_timestamp() where operation_id=p_id returning * into o;
   return to_jsonb(o)||jsonb_build_object('dispatch',true);
  end if;
 elsif p_action='uncertain' then
  update public.billing_operations set state='uncertain' where operation_id=p_id and state='creating' returning * into o;
 elsif p_action='attach' then
  if o.provider_id is not null and o.provider_id<>p_doc->>'provider_id' then raise exception 'provider conflict' using errcode='P0003'; end if;
  update public.billing_operations set provider_id=p_doc->>'provider_id',state='ready' where operation_id=p_id and state in ('creating','uncertain','ready') returning * into o;
 elsif p_action='record' then
  if o.provider_id is distinct from p_doc->>'provider_id' then raise exception 'provider conflict' using errcode='P0003'; end if;
  select * into e from public.billing_evidence where payment_id=p_doc->>'payment_id';
  if found then
   if e.operation_id<>p_id or e.evidence_hash<>p_doc->>'evidence_hash' then raise exception 'evidence conflict' using errcode='P0003'; end if;
  else
   insert into public.billing_evidence(payment_id,operation_id,evidence_hash,event_id,invoice_id,paid_until)
   values(p_doc->>'payment_id',p_id,p_doc->>'evidence_hash',(p_doc->>'event_id')::uuid,p_doc->>'invoice_id',(p_doc->>'paid_until')::timestamptz);
  end if;
 elsif p_action in ('apply','recover') then
  update public.billing_operations set last_checked_at=clock_timestamp() where operation_id=p_id;
  for e in select * from public.billing_evidence where operation_id=p_id and not applied order by paid_until for update loop
   if e.paid_until>clock_timestamp() and (b.valid_until is null or b.price_id is null or e.paid_until>b.valid_until) then
    outcome:=public.subscription_payment_apply(p_account,e.event_id,o.offer_version_id,o.price_id,e.paid_until,e.evidence_hash);
    select * into b from public.account_plan_bindings where account_id=p_account;
    update public.billing_operations set state='confirmed',result=outcome where operation_id=p_id returning * into o;
   end if;
   update public.billing_evidence set applied=true where payment_id=e.payment_id;
  end loop;
 elsif p_action='cancel_claim' then
  if not o.cancel_requested then
   update public.billing_operations set cancel_requested=true where operation_id=p_id returning * into o;
   return to_jsonb(o)||jsonb_build_object('dispatch',true);
  end if;
 elsif p_action='provider_state' then
  update public.billing_operations set provider_state=p_doc->>'status' where operation_id=p_id returning * into o;
  if o.state='ready' and o.provider_state in ('authenticated','active','pending','halted') then
   update public.billing_operations set state='pending' where operation_id=p_id returning * into o;
  end if;
  if o.provider_state in ('cancelled','completed','expired') then
   if b.price_id=o.price_id and b.valid_until>clock_timestamp() and not exists(select 1 from public.subscription_scheduled_changes where account_id=p_account) then
    perform public.subscription_schedule_change(p_account,p_id,encode(sha256(convert_to(p_id::text||':cancel','UTF8')),'hex'),'cancel',b.revision,null,null,null);
   elsif b.valid_until is null or b.valid_until<=clock_timestamp() then
    update public.billing_operations set state='expired' where operation_id=p_id returning * into o;
   end if;
  end if;
 elsif p_action<>'read' then raise exception 'invalid action' using errcode='22023';
 end if;
 return to_jsonb(o);
end $$;
revoke all on function public.billing_call(uuid,text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_call(uuid,text,uuid,jsonb) to usage_binding_executor;
create function public.billing_pending() returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 return coalesce((select jsonb_agg(to_jsonb(x)) from (select operation_id,account_id,provider_id,merchant,state from public.billing_operations where state<>'expired' order by last_checked_at nulls first,created_at limit 50) x),'[]');
end $$;
revoke all on function public.billing_pending() from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_pending() to usage_binding_executor;
create function public.billing_lookup(p_provider text) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 return (select jsonb_build_object('account_id',account_id,'operation_id',operation_id,'merchant',merchant) from public.billing_operations where provider_id=p_provider);
end $$;
revoke all on function public.billing_lookup(text) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_lookup(text) to usage_binding_executor;
create function public.billing_event(p_hash text,p_merchant text,p_provider text,p_type text) returns boolean language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 insert into public.billing_webhook_events values(p_hash,p_merchant,p_provider,p_type,clock_timestamp()) on conflict do nothing;
 return true;
end $$;
revoke all on function public.billing_event(text,text,text,text) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_event(text,text,text,text) to usage_binding_executor;
create function public.billing_current(p_account uuid) returns uuid language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 return (select operation_id from public.billing_operations where account_id=p_account order by created_at desc limit 1);
end $$;
revoke all on function public.billing_current(uuid) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_current(uuid) to usage_binding_executor;
commit;
