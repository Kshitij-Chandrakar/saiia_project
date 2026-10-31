-- Additive C12. Requires C10 outbound events and its 20260924120000 claim fix.
-- No LOGINs, assignments, publication, provider configuration or enablement.
begin;
alter table public.outbound_email_events drop constraint outbound_email_events_type_check;
alter table public.outbound_email_events add constraint outbound_email_events_type_check check(email_type in (
 'welcome','account_security','ai_notes_ready','session_summary','transcript_export','marketing_product_update',
 'billing_payment','billing_renewal','billing_cancellation','billing_access_end')) not valid;
-- Preserve C10's claim implementation, including its ambiguity fix and leases.
do $$ declare original text; patched text; begin
 original:=pg_get_functiondef('public.claim_outbound_email_event(uuid,uuid,text,text,text,jsonb,timestamptz)'::regprocedure);
 if position('#variable_conflict use_column' in original)=0 then raise exception 'C10 ambiguity fix prerequisite missing'; end if;
 patched:=replace(original,'''marketing_product_update''','''marketing_product_update'', ''billing_payment'', ''billing_renewal'', ''billing_cancellation'', ''billing_access_end''');
 if original=patched then raise exception 'C10 claim prerequisite mismatch'; end if;
 execute patched;
end $$;

create table public.billing_notification_sources (
 id uuid primary key default gen_random_uuid(), business_key text not null unique,
 account_id uuid not null references auth.users on delete restrict,
 operation_id uuid not null references public.billing_operations on delete restrict,
 kind text not null check(kind in ('billing_payment','billing_renewal','billing_cancellation','billing_access_end')),
 payload jsonb not null, created_at timestamptz not null default clock_timestamp(),
 event_id uuid unique references public.outbound_email_events on delete restrict,
 attempts integer not null default 0 check(attempts between 0 and 3),
 delivery_state text not null default 'queued' check(delivery_state in ('queued','attempted','accepted','delivered','failed','unknown','dry_run')),
 next_attempt_at timestamptz not null default clock_timestamp()
);
create table public.billing_email_delivery_events(event_hash text primary key,recorded_at timestamptz not null default clock_timestamp());
alter table public.billing_email_delivery_events enable row level security;
revoke all on public.billing_email_delivery_events from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
alter table public.billing_notification_sources enable row level security;
revoke all on public.billing_notification_sources from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

create function public.billing_notification_enqueue(p_op uuid,p_kind text,p_key text,p_until timestamptz) returns void
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.billing_operations;
begin
 select * into strict o from public.billing_operations where operation_id=p_op;
 insert into public.billing_notification_sources(business_key,account_id,operation_id,kind,payload)
 values(p_key,o.account_id,o.operation_id,p_kind,jsonb_build_object('plan',o.snapshot::jsonb->'terms'->>'name',
  'amount_minor',o.amount::text,'currency',o.currency,'interval',o.interval_unit,'period_end',p_until,
  'offer_version_id',o.offer_version_id,'price_id',o.price_id)) on conflict(business_key) do nothing;
end $$;
revoke all on function public.billing_notification_enqueue(uuid,text,text,timestamptz) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

create function public.billing_notification_transition() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare kind text; op uuid;
begin
 if tg_table_name='billing_evidence' then
  if new.applied and not old.applied then
   -- Serialized by billing_call's account lock. Business identity is payment ID.
   kind:=case when exists(select 1 from public.billing_evidence e where e.operation_id=new.operation_id and e.applied and e.payment_id<>new.payment_id) then 'billing_renewal' else 'billing_payment' end;
   perform public.billing_notification_enqueue(new.operation_id,kind,'payment:'||new.payment_id,new.paid_until);
  end if;
 elsif tg_table_name='billing_operations' then
  -- Reliable narrow case: retrieved/validated provider terminal cancellation.
  -- Never infer scheduled cancellation from request/HTTP 200/Active status.
  if new.provider_state='cancelled' and old.provider_state is distinct from 'cancelled' and exists(select 1 from public.billing_evidence where operation_id=new.operation_id and applied) then
   perform public.billing_notification_enqueue(new.operation_id,'billing_cancellation','cancel:'||new.operation_id,
    (select max(paid_until) from public.billing_evidence where operation_id=new.operation_id and applied));
  end if;
 else
  if old.price_id is not null and new.price_id is null and old.valid_until<=clock_timestamp() then
   select operation_id into op from public.billing_operations where account_id=old.account_id and price_id=old.price_id order by created_at desc limit 1;
   if op is not null then perform public.billing_notification_enqueue(op,'billing_access_end','end:'||op||':'||old.valid_until::text,old.valid_until); end if;
  end if;
 end if;
 return new;
end $$;
revoke all on function public.billing_notification_transition() from public,anon,authenticated,service_role;
create trigger billing_email_payment after update of applied on public.billing_evidence for each row execute function public.billing_notification_transition();
create trigger billing_email_cancellation after update of provider_state on public.billing_operations for each row execute function public.billing_notification_transition();
create trigger billing_email_access_end after update on public.account_plan_bindings for each row execute function public.billing_notification_transition();

-- Closed billing worker bridge to C10 lifecycle; no arbitrary recipient/event.
create function public.billing_notification_call(p_action text,p_id uuid default null,p_doc jsonb default '{}') returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare s public.billing_notification_sources; e public.outbound_email_events; recipient text; r record;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- C10 RPCs compare UTC timestamps; pin the transaction's interpretation.
 perform set_config('TimeZone','UTC',true);
 if p_action='delivery' then
  select n.* into s from public.billing_notification_sources n join public.outbound_email_events x on x.id=n.event_id where x.provider='resend' and x.provider_message_id=p_doc->>'message_id' for update of n;
  if not found then raise exception 'unknown delivery' using errcode='22023'; end if;
  if p_doc->>'state' not in ('delivered','failed') then raise exception 'invalid delivery' using errcode='22023'; end if;
  insert into public.billing_email_delivery_events(event_hash) values(encode(sha256(convert_to(p_doc->>'id','UTF8')),'hex')) on conflict do nothing;
  if found and (p_doc->>'state'='failed' or s.delivery_state<>'failed') then update public.billing_notification_sources set delivery_state=p_doc->>'state' where id=s.id; end if;
  return jsonb_build_object('received',true);
 end if;
 if p_action='list' then
  for r in select x.user_id,x.id from public.outbound_email_events x join public.billing_notification_sources n on n.event_id=x.id
   where n.delivery_state='unknown' and x.status='sending' and x.lease_expires_at<clock_timestamp() limit 10 for update of x skip locked loop
   perform public.reconcile_outbound_email_event(r.user_id,r.id);
  end loop;
  return coalesce((select jsonb_agg(id) from (select n.id from public.billing_notification_sources n where
   (n.delivery_state in ('queued','attempted') or (n.delivery_state='failed' and n.attempts<3 and n.next_attempt_at<=clock_timestamp()))
   and exists(select 1 from auth.users u where u.id=n.account_id and u.email_confirmed_at is not null and u.email is not null)
   order by n.created_at limit 10) x),'[]');
 end if;
 select * into s from public.billing_notification_sources where id=p_id for update;
 if not found then return null; end if;
 if p_action='claim' then
  if s.delivery_state in ('accepted','delivered','unknown','dry_run') or s.attempts>=3 or s.next_attempt_at>clock_timestamp() then return null; end if;
  -- Resolve only the current verified account address. Never checkout input.
  select email into recipient from auth.users where id=s.account_id and email_confirmed_at is not null and email is not null;
  if recipient is null then return null; end if;
  if s.event_id is null then
   select * into r from public.claim_outbound_email_event(s.account_id,null,s.kind,recipient,'billing:'||s.id,'{}',clock_timestamp()+interval '5 minutes');
   update public.billing_notification_sources set event_id=r.id where id=s.id returning * into s;
  end if;
  select * into e from public.outbound_email_events where id=s.event_id for update;
  if e.recipient_email<>recipient then
   update public.billing_notification_sources set delivery_state='unknown' where id=s.id;
   return null; -- verified identity changed after an attempt: manual reconciliation.
  end if;
  if e.status='sending' then
   if e.lease_expires_at<=clock_timestamp() then
    perform public.reconcile_outbound_email_event(s.account_id,e.id);
    update public.billing_notification_sources set delivery_state='unknown' where id=s.id;
   end if;
   return null;
  end if;
  if e.status='failed' then
   if e.error_code<>'provider_not_accepted' then return null; end if;
   perform public.retry_outbound_email_event(s.account_id,e.id,clock_timestamp()+interval '5 minutes',true);
  elsif e.status<>'pending' then return null;
  end if;
  if e.status='pending' and e.pending_expires_at<=clock_timestamp() then
   select * into r from public.reclaim_outbound_email_event_pending(s.account_id,e.id,clock_timestamp()+interval '60 seconds');
  else
   select * into r from public.begin_outbound_email_event_send(s.account_id,e.id,clock_timestamp()+interval '60 seconds');
  end if;
  update public.billing_notification_sources set attempts=attempts+1,delivery_state='attempted' where id=s.id;
  return jsonb_build_object('id',s.id,'kind',s.kind,'payload',s.payload,'recipient',recipient,'claim_token',r.claim_token,'idempotency_key','billing:'||s.id);
 elsif p_action='complete' then
  select * into e from public.outbound_email_events where id=s.event_id for update;
  if e.status<>'sending' or e.claim_token::text is distinct from p_doc->>'claim_token' then raise exception 'stale claim' using errcode='22023'; end if;
  if p_doc->>'state' in ('accepted','dry_run') then
   perform public.complete_outbound_email_event(s.account_id,e.id,e.claim_token,'sent',p_doc->>'provider',p_doc->>'message_id',null);
  elsif p_doc->>'state'='failed' then
   perform public.complete_outbound_email_event(s.account_id,e.id,e.claim_token,'failed',p_doc->>'provider',null,'provider_not_accepted');
  elsif p_doc->>'state'='unknown' then
   -- Leave C10's sending lease for its existing reconciliation lifecycle.
   null;
  else raise exception 'invalid state' using errcode='22023'; end if;
  update public.billing_notification_sources set delivery_state=p_doc->>'state',next_attempt_at=clock_timestamp()+interval '5 minutes' where id=s.id;
  return jsonb_build_object('state',p_doc->>'state');
 end if;
 raise exception 'invalid action' using errcode='22023';
end $$;
revoke all on function public.billing_notification_call(text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_notification_call(text,uuid,jsonb) to usage_binding_executor;

-- Reuse existing explicit permission ledger; catalog-only admins gain nothing.
alter table public.subscription_admin_permissions drop constraint subscription_admin_permissions_permission_check;
alter table public.subscription_admin_permissions add constraint subscription_admin_permissions_permission_check check(permission in ('subscriptions.manage','billing.read','billing.manage'));
create table public.billing_admin_audit (
 id bigint generated always as identity primary key, actor uuid not null, target uuid,
 action text not null, outcome text not null, operation_id uuid, recorded_at timestamptz not null default clock_timestamp()
);
create table public.billing_admin_commands (
 id uuid primary key, actor uuid not null, account_id uuid not null references auth.users,
 action text not null check(action in ('reconcile','retry_notification')), target uuid not null,
 expected text not null, state text not null default 'requested' check(state in ('requested','pending','confirmed','failed','unknown')),
 started_at timestamptz,
 created_at timestamptz not null default clock_timestamp()
);
create table public.billing_admin_reviews (
 id uuid primary key default gen_random_uuid(),actor uuid not null,account_id uuid not null,
 operation_id uuid not null,action text not null,target uuid not null,revision text not null,
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes'
);
alter table public.billing_admin_reviews enable row level security;
revoke all on public.billing_admin_reviews from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
alter table public.billing_admin_audit enable row level security;
alter table public.billing_admin_commands enable row level security;
revoke all on public.billing_admin_audit,public.billing_admin_commands from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

create function public.billing_admin_snapshot(p_account uuid) returns jsonb language sql security definer set search_path=pg_catalog as $$
 select jsonb_build_object('operations',coalesce((select jsonb_agg(jsonb_build_object('id',operation_id,'state',state,'provider_state',provider_state,'cancel_requested',cancel_requested,'cancellation_state',case when provider_state='cancelled' then 'confirmed' when cancel_requested then 'unknown' else 'none' end,'amount_minor',amount::text,'currency',currency) order by operation_id) from public.billing_operations where account_id=p_account),'[]'),
 'notifications',coalesce((select jsonb_agg(jsonb_build_object('id',n.id,'kind',n.kind,'state',n.delivery_state,'attempts',n.attempts,'retryable',n.delivery_state='failed' and n.attempts<3 and exists(select 1 from public.outbound_email_events e where e.id=n.event_id and e.status='failed' and e.error_code='provider_not_accepted')) order by n.id) from public.billing_notification_sources n where n.account_id=p_account),'[]'),
 'commands',coalesce((select jsonb_agg(jsonb_build_object('id',id,'action',action,'state',state) order by id) from public.billing_admin_commands where account_id=p_account),'[]'))
$$;
revoke all on function public.billing_admin_snapshot(uuid) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

create function public.billing_admin_call(p_actor uuid,p_action text,p_account uuid,p_doc jsonb default '{}') returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
#variable_conflict use_variable
declare snapshot jsonb; fingerprint text; cmd public.billing_admin_commands; permitted boolean; target uuid; review_id uuid;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select exists(select 1 from public.subscription_admin_permissions where subject_id=p_actor and active and permission=(case when p_action in ('inspect','access') then 'billing.read' else 'billing.manage' end)) into permitted;
 if p_action='access' then return jsonb_build_object('read',permitted,'manage',exists(select 1 from public.subscription_admin_permissions where subject_id=p_actor and active and permission='billing.manage')); end if;
 if not permitted then
  insert into public.billing_admin_audit(actor,target,action,outcome) values(p_actor,p_account,p_action,'denied');
  return jsonb_build_object('error','denied'); -- return, so denial audit commits.
 end if;
 if p_doc ? 'operation_id' then perform pg_advisory_xact_lock(hashtextextended(p_doc->>'operation_id',0)); end if;
 -- Serializes all commands for this account without invoking provider/current.
 perform 1 from auth.users where id=p_account for update;
 snapshot:=public.billing_admin_snapshot(p_account);
 fingerprint:=encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
 if p_action='inspect' then
  insert into public.billing_admin_audit(actor,target,action,outcome) values(p_actor,p_account,p_action,'confirmed');
  return snapshot||jsonb_build_object('revision',fingerprint);
 end if;
 if p_action='review' then
  if p_doc->>'action' not in ('reconcile','retry_notification') then return jsonb_build_object('error','denied'); end if;
  insert into public.billing_admin_reviews(actor,account_id,operation_id,action,target,revision)
   values(p_actor,p_account,(p_doc->>'operation_id')::uuid,p_doc->>'action',(p_doc->>'target')::uuid,fingerprint) returning id into review_id;
  return jsonb_build_object('review_id',review_id,'revision',fingerprint,'action',p_doc->>'action','target',p_doc->>'target','operation_id',p_doc->>'operation_id');
 end if;
 if p_action not in ('reconcile','retry_notification') then
  insert into public.billing_admin_audit(actor,target,action,outcome) values(p_actor,p_account,p_action,'denied');
  return jsonb_build_object('error','denied');
 end if;
 target:=(p_doc->>'target')::uuid;
 select * into cmd from public.billing_admin_commands where id=(p_doc->>'operation_id')::uuid;
 if found then
  if cmd.actor=p_actor and cmd.account_id=p_account and cmd.target=target and cmd.action=p_action and cmd.expected=p_doc->>'revision' then return jsonb_build_object('id',cmd.id,'state',cmd.state); end if;
  insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(p_actor,p_account,p_action,'identity_conflict',cmd.id);
  return jsonb_build_object('error','conflict');
 end if;
 if not exists(select 1 from public.billing_admin_reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and account_id=p_account and operation_id=(p_doc->>'operation_id')::uuid and action=p_action and billing_admin_reviews.target=target and revision=fingerprint and expires_at>clock_timestamp()) or
  p_doc->>'confirm' is distinct from 'true' or p_doc->>'revision' is distinct from fingerprint or
  (p_action='reconcile' and not exists(select 1 from public.billing_operations where account_id=p_account and operation_id=target)) or
  (p_action='retry_notification' and not exists(select 1 from public.billing_notification_sources n join public.outbound_email_events e on e.id=n.event_id where n.account_id=p_account and n.id=target and n.delivery_state='failed' and n.attempts<3 and e.error_code='provider_not_accepted')) then
  insert into public.billing_admin_audit(actor,target,action,outcome) values(p_actor,p_account,p_action,'stale_or_ineligible');
  return jsonb_build_object('error','conflict');
 end if;
 insert into public.billing_admin_commands(id,actor,account_id,action,target,expected) values((p_doc->>'operation_id')::uuid,p_actor,p_account,p_action,target,fingerprint) returning * into cmd;
 insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(p_actor,p_account,p_action,'requested',cmd.id);
 return jsonb_build_object('id',cmd.id,'state',cmd.state);
end $$;
revoke all on function public.billing_admin_call(uuid,text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_admin_call(uuid,text,uuid,jsonb) to usage_binding_executor;

create function public.billing_admin_work(p_id uuid default null,p_outcome text default null) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare cmd public.billing_admin_commands;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_id is null then
  -- Never redispatch an uncertain command after worker death.
  for cmd in update public.billing_admin_commands set state='unknown' where state='pending' and started_at<clock_timestamp()-interval '5 minutes' returning * loop
   insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(cmd.actor,cmd.account_id,cmd.action,'unknown',cmd.id);
  end loop;
  select * into cmd from public.billing_admin_commands where state='requested' order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  if not exists(select 1 from public.subscription_admin_permissions where subject_id=cmd.actor and permission='billing.manage' and active) then
   update public.billing_admin_commands set state='failed' where id=cmd.id;
   insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(cmd.actor,cmd.account_id,cmd.action,'denied',cmd.id);
   return null;
  end if;
  update public.billing_admin_commands set state='pending',started_at=clock_timestamp() where id=cmd.id;
  insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(cmd.actor,cmd.account_id,cmd.action,'pending',cmd.id);
  if cmd.action='retry_notification' then update public.billing_notification_sources set next_attempt_at=clock_timestamp() where id=cmd.target and delivery_state='failed' and attempts<3; end if;
  return to_jsonb(cmd);
 end if;
 select * into cmd from public.billing_admin_commands where id=p_id for update;
 if not found or cmd.state<>'pending' or p_outcome not in ('confirmed','failed','unknown') then raise exception 'invalid completion' using errcode='22023'; end if;
 update public.billing_admin_commands set state=p_outcome where id=p_id;
 insert into public.billing_admin_audit(actor,target,action,outcome,operation_id) values(cmd.actor,cmd.account_id,cmd.action,p_outcome,cmd.id);
 return jsonb_build_object('state',p_outcome);
end $$;
revoke all on function public.billing_admin_work(uuid,text) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_admin_work(uuid,text) to usage_binding_executor;
commit;
