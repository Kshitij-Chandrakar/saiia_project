-- C15.5 preparation. Disabled, no subjects, LOGINs or real bootstrap.
begin;
create role admin_executor nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
create role admin_bootstrap_executor nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
create schema administration;
revoke all on schema administration from public,anon,authenticated,service_role;
create table administration.configuration (
 singleton boolean primary key default true check(singleton),
 enabled boolean not null default false, revision bigint not null default 1,
 bootstrap_subject uuid, bootstrap_consumed boolean not null default false,
 cutover boolean not null default false
);
insert into administration.configuration(singleton,enabled,revision) values(true,false,1);
create function administration.configuration_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin new.cutover:=old.cutover or new.enabled; return new; end$$;
create trigger configuration_cutover before update on administration.configuration for each row execute function administration.configuration_guard();
create table administration.memberships (
 subject uuid primary key, role text not null check(role in ('admin','super_admin')),
 status text not null check(status in ('active','suspended','revoked')),
 revision bigint not null check(revision>0),
 created_at timestamptz not null default clock_timestamp(),
 updated_at timestamptz not null default clock_timestamp()
);
create table administration.audit (
 id uuid primary key default gen_random_uuid(), action text not null,
 role_at_action text, outcome text not null,
 reason text check(reason in ('support','security','membership','commercial','campaign','privacy','bootstrap')),
 correlation uuid not null, recorded_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null default clock_timestamp()+interval '180 days'
);
create table administration.audit_references (
 event uuid primary key references administration.audit on delete restrict,
 actor uuid not null, target uuid
);
create table administration.reviews (
 id uuid primary key, actor uuid not null, session_id uuid not null,
 actor_revision bigint not null, action text not null check(action in ('membership')),
 target uuid not null, target_revision bigint not null, desired_role text not null,
 desired_status text not null, reason text not null, operation_id uuid not null,
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 consumed_at timestamptz,
 unique(actor,operation_id),
 check(desired_role in ('admin','super_admin')),
 check(desired_status in ('active','suspended','revoked')),
 check(reason in ('support','security','membership'))
);
create table administration.receipts (
 id uuid primary key, actor uuid not null, review_id uuid not null unique,
 action text not null, target uuid not null, revision bigint not null,
 state text not null, created_at timestamptz not null default clock_timestamp()
);
create function administration.immutable() returns trigger language plpgsql
set search_path=pg_catalog as $$begin raise exception 'immutable' using errcode='55000'; end$$;
create trigger audit_immutable before update or delete on administration.audit
for each row execute function administration.immutable();
create trigger audit_no_truncate before truncate on administration.audit
for each statement execute function administration.immutable();
create function administration.audit_action(p_actor uuid,p_role text,p_target uuid,p_action text,p_outcome text,p_reason text,p_correlation uuid)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare eid uuid;
begin
 insert into administration.audit(action,role_at_action,outcome,reason,correlation)
 values(p_action,p_role,p_outcome,p_reason,p_correlation) returning id into eid;
 insert into administration.audit_references values(eid,p_actor,p_target);
end$$;
create function administration.eligible(p_subject uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from auth.users u where u.id=p_subject and u.email_confirmed_at is not null
 and u.deleted_at is null and (u.banned_until is null or u.banned_until<=statement_timestamp()))
 and not exists(select 1 from public.privacy_deletion_requests where account_id=p_subject and accepted_at is not null)
$$;
create function administration.member(p_subject uuid) returns administration.memberships
language plpgsql security definer set search_path=pg_catalog as $$
declare m administration.memberships;
begin
 select * into m from administration.memberships where subject=p_subject for share;
 if m.status is distinct from 'active' or not administration.eligible(p_subject) then return null; end if;
 return m;
end$$;
create function administration.authenticator_ready(p_subject uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from auth.mfa_factors where user_id=p_subject and factor_type='totp' and status='verified')
$$;
create function public.administration_call(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m administration.memberships; t administration.memberships; v administration.reviews;
 receipt administration.receipts; target uuid; correlation uuid; page jsonb; revision bigint; count_sa bigint;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then
  raise exception 'denied' using errcode='42501'; end if;
 -- shortcut: one authority lock serializes reads; split read locks only after lock-order/load evidence.
 perform 1 from administration.configuration where singleton and enabled for update;
 if not found then return jsonb_build_object('error','unavailable'); end if;
 if p_action='_ready' then return jsonb_build_object('ready',true); end if;
 m:=administration.member(p_actor);
 if m.subject is null then
  perform administration.audit_action(p_actor,null,null,'admission','denied',null,gen_random_uuid());
  return jsonb_build_object('error','not_found');
 end if;
 if p_action='me' then return jsonb_build_object('subject_id',m.subject,'role',m.role,'revision',m.revision::text,'recovery_available',false); end if;
 if p_action='receipt' then
  select * into receipt from administration.receipts where id=(p_doc->>'id')::uuid and actor=p_actor;
  if not found or (receipt.action='membership' and m.role<>'super_admin') then return jsonb_build_object('error','not_found'); end if;
  return jsonb_build_object('operation_id',receipt.id,'action',receipt.action,'target',receipt.target,
   'state',receipt.state,'revision',receipt.revision::text,'requested_at',receipt.created_at);
 end if;
 if m.role<>'super_admin' then
  perform administration.audit_action(p_actor,m.role,null,'privileged_route','denied',null,gen_random_uuid());
  return jsonb_build_object('error','not_found');
 end if;
 if p_action='memberships' then
  select coalesce((select jsonb_agg(jsonb_build_object('subject_id',q.subject,'role',q.role,
   'status',q.status,'revision',q.revision::text,'created_at',q.created_at,'updated_at',q.updated_at) order by q.subject)
   from (select * from administration.memberships where subject>coalesce((p_doc->>'after')::uuid,'00000000-0000-0000-0000-000000000000'::uuid) order by subject limit 101) q),'[]') into page;
  return jsonb_build_object('items',jsonb_path_query_array(page,'$[0 to 99]'),'has_more',jsonb_array_length(page)>100,
   'next_cursor',case when jsonb_array_length(page)>100 then page->99->>'subject_id' else null end);
 end if;
 if p_action='audit' then
  perform administration.audit_action(p_actor,m.role,null,'audit.read','confirmed',null,gen_random_uuid());
  select coalesce((select jsonb_agg(jsonb_build_object('event_id',a.id,'action',a.action,
   'actor_role_at_action',a.role_at_action,'timestamp',a.recorded_at,'outcome',a.outcome,'reason_code',a.reason,
   'actor_ref',r.actor,'target_ref',r.target,'correlation_id',a.correlation) order by a.id)
   from (select * from administration.audit where id>coalesce((p_doc->>'after')::uuid,'00000000-0000-0000-0000-000000000000'::uuid) order by id limit 101) a
   join administration.audit_references r on r.event=a.id),'[]') into page;
  return jsonb_build_object('items',jsonb_path_query_array(page,'$[0 to 99]'),'has_more',jsonb_array_length(page)>100,
   'next_cursor',case when jsonb_array_length(page)>100 then page->99->>'event_id' else null end);
 end if;
 if p_action not in ('membership.review','membership.confirm') then return jsonb_build_object('error','not_found'); end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_actor) then
  return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='membership.review' then
  target:=(p_doc->>'target')::uuid; correlation:=(p_doc->>'operation_id')::uuid;
  if coalesce(p_doc->>'role','') not in ('admin','super_admin')
   or coalesce(p_doc->>'status','') not in ('active','suspended','revoked') or coalesce(p_doc->>'reason','') not in ('membership','support','security') then
   return jsonb_build_object('error','invalid'); end if;
  select * into t from administration.memberships where subject=target for update;
  if (p_doc->>'status'='active' and not administration.eligible(target))
   or (p_doc->>'status'<>'active' and t.subject is null) then return jsonb_build_object('error','invalid'); end if;
  if p_doc->>'role'='super_admin' and p_doc->>'status'='active' and not administration.authenticator_ready(target) then
   return jsonb_build_object('error','authenticator_not_ready'); end if;
  revision:=coalesce(t.revision,0);
  select * into v from administration.reviews where actor=p_actor and operation_id=correlation;
  if found then
   if v.target<>target or v.desired_role<>p_doc->>'role' or v.desired_status<>p_doc->>'status' or v.session_id<>p_session or v.reason<>p_doc->>'reason' then return jsonb_build_object('error','conflict'); end if;
  else
  if exists(select 1 from administration.receipts where id=correlation) then return jsonb_build_object('error','conflict'); end if;
   insert into administration.reviews(id,actor,session_id,actor_revision,action,target,target_revision,desired_role,desired_status,reason,operation_id)
    values(gen_random_uuid(),p_actor,p_session,m.revision,'membership',target,revision,p_doc->>'role',p_doc->>'status',p_doc->>'reason',correlation) returning * into v;
  end if;
  return jsonb_build_object('review_id',v.id,'operation_id',v.operation_id,'expires_at',v.expires_at,'target_revision',v.target_revision::text);
 end if;
 select * into v from administration.reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and session_id=p_session for update;
 if not found or p_doc->>'confirm' is distinct from 'true' then return jsonb_build_object('error','conflict'); end if;
 select * into receipt from administration.receipts where id=v.operation_id;
 if found then
  if receipt.actor<>p_actor or receipt.review_id<>v.id or receipt.action<>'membership' then return jsonb_build_object('error','conflict'); end if;
  return jsonb_build_object('operation_id',receipt.id,'state',receipt.state,'revision',receipt.revision::text); end if;
 if v.expires_at<=clock_timestamp() or v.actor_revision<>m.revision or v.consumed_at is not null then return jsonb_build_object('error','conflict'); end if;
 select * into t from administration.memberships where subject=v.target for update;
 if coalesce(t.revision,0)<>v.target_revision or (v.desired_status='active' and not administration.eligible(v.target)) then return jsonb_build_object('error','conflict'); end if;
 if v.desired_role='super_admin' and v.desired_status='active' and not administration.authenticator_ready(v.target) then return jsonb_build_object('error','authenticator_not_ready'); end if;
 select count(*) into count_sa from administration.memberships where role='super_admin' and status='active' and administration.eligible(subject) and administration.authenticator_ready(subject);
 if t.role='super_admin' and t.status='active' and administration.eligible(t.subject) and administration.authenticator_ready(t.subject)
  and (v.desired_role<>'super_admin' or v.desired_status<>'active') and count_sa<=1 then
  perform administration.audit_action(p_actor,m.role,v.target,'membership','last_super_admin',v.reason,v.operation_id);
  return jsonb_build_object('error','last_super_admin'); end if;
 insert into administration.memberships(subject,role,status,revision) values(v.target,v.desired_role,v.desired_status,1)
 on conflict(subject) do update set role=excluded.role,status=excluded.status,revision=administration.memberships.revision+1,updated_at=clock_timestamp()
 returning administration.memberships.revision into revision;
 update administration.reviews set consumed_at=clock_timestamp() where id=v.id;
 insert into administration.receipts values(v.operation_id,p_actor,v.id,'membership',v.target,revision,'confirmed',clock_timestamp());
 perform administration.audit_action(p_actor,m.role,v.target,'membership','confirmed',v.reason,v.operation_id);
 return jsonb_build_object('operation_id',v.operation_id,'state','confirmed','revision',revision::text);
end$$;
-- Bootstrap requires separately verified existing UUID AND exact verified email.
-- No email-derived signup rule; this function does not create Auth identities.
create function public.administration_bootstrap(p_subject uuid,p_verified_email text,p_confirmation uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'admin_bootstrap_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton for update;
 if not exists(select 1 from administration.configuration where bootstrap_subject=p_subject and not bootstrap_consumed)
  or exists(select 1 from administration.memberships) or p_confirmation is null or not administration.eligible(p_subject) or not administration.authenticator_ready(p_subject)
  or not exists(select 1 from auth.users where id=p_subject and email=p_verified_email and email_confirmed_at is not null)
 then return jsonb_build_object('error','bootstrap_denied'); end if;
 insert into administration.memberships(subject,role,status,revision) values(p_subject,'super_admin','active',1);
 update administration.configuration set bootstrap_consumed=true;
 perform administration.audit_action(p_subject,'super_admin',p_subject,'bootstrap','confirmed','bootstrap',p_confirmation);
 return jsonb_build_object('state','confirmed','subject_id',p_subject);
end$$;
do $$declare t text; begin
 foreach t in array array['configuration','memberships','audit','audit_references','reviews','receipts'] loop
  execute format('alter table administration.%I enable row level security',t);
  execute format('revoke all on administration.%I from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor',t);
 end loop;
end$$;
revoke all on all functions in schema administration from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
revoke all on function public.administration_call(uuid,uuid,timestamptz,text,jsonb),public.administration_bootstrap(uuid,text,uuid) from public,anon,authenticated,service_role;
grant execute on function public.administration_call(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
grant execute on function public.administration_bootstrap(uuid,text,uuid) to admin_bootstrap_executor;
commit;
