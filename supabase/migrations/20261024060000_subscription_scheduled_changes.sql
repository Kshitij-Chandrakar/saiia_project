-- Backend-verified paid-period changes; no HTTP assignment or payment shortcut.
begin;
create table public.subscription_scheduled_changes (
 account_id uuid primary key references auth.users(id) on delete restrict,
 event_id uuid not null unique,
 binding_revision bigint not null check(binding_revision>0),
 effective_at timestamptz not null check(isfinite(effective_at)),
 target_offer_id uuid not null references public.catalog_offer_versions(offer_version_id) on delete restrict,
 target_fingerprint text not null check(target_fingerprint ~ '^[0-9a-f]{64}$'),
 target_price_id uuid references public.catalog_price_versions(price_id) on delete restrict,
 target_paid_until timestamptz,
 kind text not null check(kind in ('cancel','downgrade')),
 check((kind='cancel' and target_price_id is null and target_paid_until is null) or
       (kind='downgrade' and target_price_id is not null and target_paid_until is not null and isfinite(target_paid_until) and target_paid_until>effective_at))
);
alter table public.subscription_scheduled_changes enable row level security;
alter table public.subscription_scheduled_changes force row level security;
revoke all on public.subscription_scheduled_changes from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;

create function public.subscription_schedule_change(p_account uuid,p_event uuid,p_hash text,p_kind text,p_revision bigint,
 p_offer uuid,p_price uuid,p_until timestamptz) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; r public.subscription_payment_receipts; cfg public.subscription_configuration;
 o public.catalog_offer_versions; result jsonb; at_time timestamptz;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 if not found or not b.active then raise exception 'denied' using errcode='42501'; end if;
 select * into r from public.subscription_payment_receipts where event_id=p_event;
 if found then
   if r.account_id<>p_account or r.semantic_hash<>p_hash then raise exception 'identity conflict' using errcode='P0003'; end if;
   return r.result;
 end if;
 at_time:=clock_timestamp();
 if b.revision<>p_revision then raise exception 'revision conflict' using errcode='40001'; end if;
 if b.valid_until is null or b.valid_until<=at_time then raise exception 'paid period required' using errcode='22023'; end if;
 if p_kind='cancel' then
   if p_offer is not null or p_price is not null or p_until is not null then raise exception 'invalid cancellation' using errcode='22023'; end if;
   select * into cfg from public.subscription_configuration where singleton for share;
   select * into o from public.catalog_offer_versions where offer_version_id=cfg.free_offer_id;
   if o.offer_version_id is null or o.fingerprint<>cfg.free_fingerprint or o.canonical_json::jsonb->'terms'->>'pricing_mode'<>'free' then raise exception 'free configuration unavailable' using errcode='P0005'; end if;
 elsif p_kind='downgrade' then
   select * into o from public.catalog_offer_versions where offer_version_id=p_offer;
   if not found or o.canonical_json::jsonb->'terms'->>'pricing_mode'<>'priced' or
      p_until is null or not isfinite(p_until) or p_until<=b.valid_until or
      not exists(select 1 from public.catalog_price_versions where price_id=p_price and offer_version_id=p_offer) then
     raise exception 'verified future payment required' using errcode='22023'; end if;
 else raise exception 'invalid change' using errcode='22023'; end if;
 if o.fingerprint<>encode(sha256(convert_to(o.canonical_json,'UTF8')),'hex') then raise exception 'corrupt terms' using errcode='55000'; end if;
 -- A newer verified immediate upgrade/renewal supersedes an older schedule.
 delete from public.subscription_scheduled_changes where account_id=p_account and binding_revision<>b.revision;
 if exists(select 1 from public.subscription_scheduled_changes where account_id=p_account) then raise exception 'change already pending' using errcode='40001'; end if;
 insert into public.subscription_scheduled_changes values(p_account,p_event,b.revision,b.valid_until,o.offer_version_id,o.fingerprint,p_price,p_until,p_kind);
 result:=jsonb_build_object('event_id',p_event,'kind',p_kind,'effective_at',b.valid_until,'binding_revision',b.revision,'target_offer_id',o.offer_version_id);
 insert into public.subscription_payment_receipts values(p_event,p_account,p_hash,result,at_time);
 insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.scheduled_change',b.revision,session_user);
 return result;
end $$;

-- Preserve the accepted bootstrap/expiry implementation and wrap its exact
-- capability. Only the wrapper remains callable by the application principal.
alter function public.subscription_current(uuid,boolean) rename to subscription_current_base;
revoke all on function public.subscription_current_base(uuid,boolean) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
create function public.subscription_current(p_account uuid,p_bootstrap boolean default false) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare b public.account_plan_bindings; pending public.subscription_scheduled_changes; o public.catalog_offer_versions;
 at_time timestamptz; verified timestamptz;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select email_confirmed_at into verified from auth.users where id=p_account for no key update;
 if not found or verified is null then raise exception 'verification required' using errcode='42501'; end if;
 select * into b from public.account_plan_bindings where account_id=p_account for update;
 if found and not b.active then raise exception 'denied' using errcode='42501'; end if;
 select * into pending from public.subscription_scheduled_changes where account_id=p_account for update;
 at_time:=clock_timestamp();
 if found and pending.binding_revision=b.revision and pending.effective_at=b.valid_until and pending.effective_at<=at_time then
   select * into o from public.catalog_offer_versions where offer_version_id=pending.target_offer_id;
   if o.fingerprint<>pending.target_fingerprint or o.fingerprint<>encode(sha256(convert_to(o.canonical_json,'UTF8')),'hex') then raise exception 'invalid scheduled terms' using errcode='55000'; end if;
   -- If the verified replacement paid period has itself expired, base expiry
   -- resolves to Free. There is no grace or fabricated renewal.
   update public.account_plan_bindings set offer_version_id=pending.target_offer_id,price_id=pending.target_price_id,
     valid_from=pending.effective_at,valid_until=pending.target_paid_until,revision=revision+1,
     source_ref='verified.period_end_change',policy_version='subscriptions.approved.2026-10-24'
     where account_id=p_account returning * into b;
   insert into public.usage_events(account_id,event,fence,actor_principal) values(p_account,'binding.period_end_change',b.revision,session_user);
   delete from public.subscription_scheduled_changes where account_id=p_account;
 elsif pending.account_id is not null and pending.binding_revision<>b.revision then
   delete from public.subscription_scheduled_changes where account_id=p_account;
 end if;
 return public.subscription_current_base(p_account,p_bootstrap);
end $$;
revoke all on function public.subscription_schedule_change(uuid,uuid,text,text,bigint,uuid,uuid,timestamptz),public.subscription_current(uuid,boolean)
 from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_schedule_change(uuid,uuid,text,text,bigint,uuid,uuid,timestamptz) to usage_binding_executor;
grant execute on function public.subscription_current(uuid,boolean) to usage_executor;
commit;
