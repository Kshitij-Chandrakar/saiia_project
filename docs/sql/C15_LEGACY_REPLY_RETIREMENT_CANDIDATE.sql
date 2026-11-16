-- DISPOSABLE SYNTHETIC CANDIDATE ONLY. Never included in normal migration loader.
-- Explicit owner authorization required before any existing-history installation.
begin;
create role privacy_retirement_owner nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
create role privacy_retirement_executor nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
create table public.privacy_legacy_reply_retirements(
 run_id uuid primary key references public.subscription_auto_runs on delete restrict,
 account_id uuid not null references auth.users on delete restrict,
 request_id uuid not null references public.privacy_deletion_requests(request_id) on delete restrict,
 accepted_at timestamptz not null,
 eligible_at timestamptz not null,
 expected_count integer not null check(expected_count between 1 and 4096),
 revision bigint not null default 1,
 enabled boolean not null default false,
 completed boolean not null default false
);
create table public.privacy_retirement_permits(
 transaction_id xid8 primary key,
 run_id uuid not null,
 expected_count integer not null
);
create table public.privacy_legacy_retirement_attestations(
 id uuid primary key default gen_random_uuid(),
 category text not null check(category in ('usage_recovery','security_audit')),
 classifier_version text not null check(classifier_version in ('c15.legacy.reply.v1','c15.legacy.security.v1')),
 count integer not null,
 retired_at timestamptz not null default clock_timestamp()
);
create trigger legacy_attestation_immutable before update or delete on public.privacy_legacy_retirement_attestations for each row execute function public.catalog_reject_mutation();
create trigger legacy_attestation_no_truncate before truncate on public.privacy_legacy_retirement_attestations for each statement execute function public.catalog_reject_mutation();
revoke all on public.privacy_legacy_reply_retirements,public.privacy_retirement_permits,public.privacy_legacy_retirement_attestations from public,anon,authenticated,service_role,usage_executor,privacy_preparation_executor,privacy_cleanup_executor,privacy_retirement_executor;
alter table public.privacy_legacy_reply_retirements enable row level security;
alter table public.privacy_legacy_reply_retirements force row level security;
alter table public.privacy_retirement_permits enable row level security;
alter table public.privacy_retirement_permits force row level security;
alter table public.privacy_legacy_retirement_attestations enable row level security;
alter table public.privacy_legacy_retirement_attestations force row level security;
create policy legacy_unit_owner on public.privacy_legacy_reply_retirements to privacy_retirement_owner using(true) with check(true);
create policy legacy_permit_owner on public.privacy_retirement_permits to privacy_retirement_owner using(true) with check(true);
create policy legacy_attestation_owner on public.privacy_legacy_retirement_attestations to privacy_retirement_owner using(true) with check(true);
grant usage on schema public,auth to privacy_retirement_owner;
grant select(id),update(id) on auth.users to privacy_retirement_owner;
grant update(unit_id) on public.privacy_retirement_units to privacy_retirement_owner;
create policy legacy_unit_lock on public.privacy_retirement_units for update to privacy_retirement_owner using(true) with check(true);
grant select,update on public.privacy_legacy_reply_retirements to privacy_retirement_owner;
grant select,insert,delete on public.privacy_retirement_permits to privacy_retirement_owner;
grant insert on public.privacy_legacy_retirement_attestations to privacy_retirement_owner;
grant select on public.privacy_deletion_requests,public.subscription_auto_runs,public.usage_operations,public.privacy_retirement_holds,public.privacy_retirement_units,public.privacy_auto_reply_payloads to privacy_retirement_owner;
-- Row locks require UPDATE privilege; columns are constrained to no-op lock columns.
grant update(run_id) on public.subscription_auto_runs to privacy_retirement_owner;
grant update(request_id) on public.privacy_deletion_requests to privacy_retirement_owner;
grant select,delete on public.subscription_auto_replies to privacy_retirement_owner;
create policy legacy_reply_reader on public.subscription_auto_replies for select to privacy_retirement_owner using(true);
create policy legacy_reply_delete on public.subscription_auto_replies for delete to privacy_retirement_owner using(exists(select 1 from public.privacy_retirement_permits p where p.transaction_id=pg_current_xact_id() and p.run_id=subscription_auto_replies.run_id));
create policy legacy_run_reader on public.subscription_auto_runs for select to privacy_retirement_owner using(true);
create policy legacy_run_lock on public.subscription_auto_runs for update to privacy_retirement_owner using(true) with check(true);
create policy legacy_request_reader on public.privacy_deletion_requests for select to privacy_retirement_owner using(true);
create policy legacy_request_lock on public.privacy_deletion_requests for update to privacy_retirement_owner using(true) with check(true);
create policy legacy_operation_reader on public.usage_operations for select to privacy_retirement_owner using(true);
create policy legacy_hold_reader on public.privacy_retirement_holds for select to privacy_retirement_owner using(true);
create policy legacy_prepared_reader on public.privacy_retirement_units for select to privacy_retirement_owner using(true);
create policy legacy_payload_reader on public.privacy_auto_reply_payloads for select to privacy_retirement_owner using(true);
create function public.privacy_legacy_reply_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if tg_op='UPDATE' then
  if session_user<>'privacy_cleanup_executor' or current_user<>'privacy_retirement_owner' or current_setting('role',true)<>'none' or not(old.document ? 'owner_token') or (to_jsonb(new)-'document')<>(to_jsonb(old)-'document') or new.document is distinct from old.document-'owner_token' or not exists(select 1 from public.privacy_legacy_redaction_permits p join public.subscription_auto_runs r on r.account_id=p.account_id where p.transaction_id=pg_current_xact_id() and r.run_id=old.run_id) then raise exception 'immutable reply redaction denied' using errcode='42501'; end if;
  return new;
 end if;
 if tg_op<>'DELETE' or session_user<>'privacy_retirement_executor'  or current_user<>'privacy_retirement_owner' or current_setting('role',true)<>'none' then raise exception 'immutable reply' using errcode='42501'; end if;
 if not exists(select 1 from public.privacy_retirement_permits where transaction_id=pg_current_xact_id() and run_id=old.run_id) then raise exception 'retirement permit required' using errcode='42501'; end if;
 return old;
end $$;
-- Replace only the exact per-table row trigger transactionally; never alter
-- catalog_reject_mutation, disable triggers or replace the TRUNCATE guard.
do $$ declare n text; begin
 select tgname into strict n from pg_trigger where tgrelid='public.subscription_auto_replies'::regclass and tgfoid='public.catalog_reject_mutation()'::regprocedure and (tgtype & 1)=1;
 execute format('drop trigger %I on public.subscription_auto_replies',n);
end $$;
create trigger legacy_reply_mutation_guard before update or delete on public.subscription_auto_replies for each row execute function public.privacy_legacy_reply_guard();
create function public.privacy_retire_legacy_replies(p_run uuid,p_revision bigint) returns integer
language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare u public.privacy_legacy_reply_retirements; r public.subscription_auto_runs; confirmation timestamptz; removed integer; begin
 if session_user<>'privacy_retirement_executor' or current_setting('role',true)<>'none' then raise exception 'retirement denied' using errcode='42501'; end if;
 select * into strict u from public.privacy_legacy_reply_retirements where run_id=p_run;
 perform 1 from auth.users where id=u.account_id for no key update;
 perform 1 from public.privacy_retirement_units where account_id=u.account_id for share;
 select * into strict u from public.privacy_legacy_reply_retirements where run_id=p_run for update;
 if not u.enabled then raise exception 'retirement disabled' using errcode='42501'; end if;
 if u.revision<>p_revision then raise exception 'stale unit' using errcode='40001'; end if;
 if u.completed then return 0; end if;
 select accepted_at into confirmation from public.privacy_deletion_requests where request_id=u.request_id and account_id=u.account_id and state='accepted_restricted' for update;
 if confirmation is null or confirmation<>u.accepted_at or u.eligible_at<>confirmation+interval '90 days' or clock_timestamp()<u.eligible_at then raise exception 'retirement clock denied' using errcode='42501'; end if;
 select * into strict r from public.subscription_auto_runs where run_id=p_run for update;
 if r.account_id<>u.account_id or r.active or r.owner_token is not null then raise exception 'retirement ownership or writer denied' using errcode='42501'; end if;
 if exists(select 1 from public.usage_operations where account_id=u.account_id and state in ('reserved','dispatched','checkpointed','uncertain')) then raise exception 'recovery remains active' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_retirement_units x join public.privacy_retirement_holds h using(unit_id) where x.account_id=u.account_id and h.active) then raise exception 'retirement hold' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_auto_reply_payloads where run_id=p_run and state<>'erased') then raise exception 'private payload present' using errcode='42501'; end if;
 if exists(select 1 from pg_constraint where contype='f' and confrelid='public.subscription_auto_replies'::regclass) then raise exception 'dependency changed' using errcode='42501'; end if;
 if (select count(*) from public.subscription_auto_replies where run_id=p_run)<>u.expected_count then raise exception 'membership changed' using errcode='40001'; end if;
 insert into public.privacy_retirement_permits values(pg_current_xact_id(),p_run,u.expected_count);
 delete from public.subscription_auto_replies where run_id=p_run;
 get diagnostics removed=row_count;
 if removed<>u.expected_count or exists(select 1 from public.subscription_auto_replies where run_id=p_run) then raise exception 'retirement verification failed' using errcode='40001'; end if;
 insert into public.privacy_legacy_retirement_attestations(category,classifier_version,count) values('usage_recovery','c15.legacy.reply.v1',removed);
 update public.privacy_legacy_reply_retirements set completed=true where run_id=p_run;
 delete from public.privacy_retirement_permits where transaction_id=pg_current_xact_id();
 return removed;
end $$;
alter function public.privacy_retire_legacy_replies(uuid,bigint) owner to privacy_retirement_owner;
revoke all on function public.privacy_retire_legacy_replies(uuid,bigint),public.privacy_legacy_reply_guard() from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_retire_legacy_replies(uuid,bigint) to privacy_retirement_executor;

-- Independent fixed 180-day security unit. Financial/shared records are excluded.
create table public.privacy_legacy_audit_retirements(
 request_id uuid primary key references public.privacy_deletion_requests(request_id) on delete restrict,
 account_id uuid not null references auth.users on delete restrict,
 accepted_at timestamptz not null, eligible_at timestamptz not null,
 expected_count integer not null check(expected_count between 1 and 4096),
 revision bigint not null default 1, enabled boolean not null default false,
 completed boolean not null default false
);
create table public.privacy_security_retirement_permits(transaction_id xid8 primary key,request_id uuid not null);
alter table public.privacy_legacy_audit_retirements enable row level security;
alter table public.privacy_legacy_audit_retirements force row level security;
alter table public.privacy_security_retirement_permits enable row level security;
alter table public.privacy_security_retirement_permits force row level security;
revoke all on public.privacy_legacy_audit_retirements,public.privacy_security_retirement_permits from public,anon,authenticated,service_role,usage_executor,privacy_preparation_executor,privacy_cleanup_executor,privacy_retirement_executor;
grant select,insert,update on public.privacy_legacy_audit_retirements to privacy_retirement_owner;
grant select,insert,delete on public.privacy_security_retirement_permits to privacy_retirement_owner;
grant select,delete on public.privacy_lifecycle_audit to privacy_retirement_owner;
grant select(kind,state,request_id) on public.privacy_followup_tasks to privacy_retirement_owner;
create policy legacy_audit_unit_owner on public.privacy_legacy_audit_retirements to privacy_retirement_owner using(true) with check(true);
create policy legacy_security_permit_owner on public.privacy_security_retirement_permits to privacy_retirement_owner using(true) with check(true);
create policy legacy_audit_read on public.privacy_lifecycle_audit for select to privacy_retirement_owner using(true);
create policy legacy_audit_delete on public.privacy_lifecycle_audit for delete to privacy_retirement_owner using(exists(select 1 from public.privacy_security_retirement_permits p where p.transaction_id=pg_current_xact_id() and p.request_id=privacy_lifecycle_audit.request_id));
create policy legacy_task_read on public.privacy_followup_tasks for select to privacy_retirement_owner using(true);
create function public.privacy_legacy_audit_guard() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare retired boolean; begin
 if tg_op='INSERT' then
  select completed into retired from public.privacy_legacy_audit_retirements where request_id=new.request_id for share;
  if coalesce(retired,false) and new.action='restore.restriction_replayed' then return null; end if;
  if coalesce(retired,false) then raise exception 'retired audit replay denied' using errcode='42501'; end if;
  return new;
 end if;
 if tg_op<>'DELETE' or session_user<>'privacy_retirement_executor' or current_setting('role',true)<>'none' or not exists(select 1 from public.privacy_security_retirement_permits where transaction_id=pg_current_xact_id() and request_id=old.request_id) then raise exception 'immutable audit' using errcode='42501'; end if;
 return old;
end $$;
alter function public.privacy_legacy_audit_guard() owner to privacy_retirement_owner;
do $$ declare n text; begin
 select tgname into strict n from pg_trigger where tgrelid='public.privacy_lifecycle_audit'::regclass and tgfoid='public.catalog_reject_mutation()'::regprocedure and (tgtype & 1)=1;
 execute format('drop trigger %I on public.privacy_lifecycle_audit',n);
end $$;
create trigger legacy_audit_mutation_guard before insert or update or delete on public.privacy_lifecycle_audit for each row execute function public.privacy_legacy_audit_guard();
create function public.privacy_prepare_legacy_security(p_request uuid) returns integer language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; accepted timestamptz; n integer; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' then raise exception 'preparation denied' using errcode='42501'; end if;
 select account_id,accepted_at into account,accepted from public.privacy_deletion_requests where request_id=p_request and state='accepted_restricted';
 if accepted is null then raise exception 'accepted clock required' using errcode='42501'; end if;
 perform 1 from auth.users where id=account for no key update;
 select count(*) into n from public.privacy_lifecycle_audit where request_id=p_request;
 insert into public.privacy_legacy_audit_retirements(request_id,account_id,accepted_at,eligible_at,expected_count) values(p_request,account,accepted,accepted+interval '180 days',n) on conflict do nothing;
 return n;
end $$;
alter function public.privacy_prepare_legacy_security(uuid) owner to privacy_retirement_owner;
create function public.privacy_retire_legacy_security(p_request uuid,p_revision bigint) returns integer language plpgsql security definer set search_path=pg_catalog as $$
declare u public.privacy_legacy_audit_retirements; accepted timestamptz; n integer; begin
 if session_user<>'privacy_retirement_executor' or current_setting('role',true)<>'none' then raise exception 'retirement denied' using errcode='42501'; end if;
 select * into strict u from public.privacy_legacy_audit_retirements where request_id=p_request;
 perform 1 from auth.users where id=u.account_id for no key update;
 perform 1 from public.privacy_retirement_units where account_id=u.account_id for share;
 select * into strict u from public.privacy_legacy_audit_retirements where request_id=p_request for update;
 if not u.enabled or u.revision<>p_revision then raise exception 'disabled or stale unit' using errcode='42501'; end if;
 if u.completed then return 0; end if;
 select accepted_at into accepted from public.privacy_deletion_requests where request_id=p_request and account_id=u.account_id and state='accepted_restricted' for update;
 if accepted is null or accepted<>u.accepted_at or u.eligible_at<>accepted+interval '180 days' or clock_timestamp()<u.eligible_at then raise exception 'security clock denied' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_followup_tasks where request_id=p_request and kind in ('revoke_sessions','personal_cleanup') and state in ('pending','running')) then raise exception 'writer remains active' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_retirement_units x join public.privacy_retirement_holds h using(unit_id) where x.account_id=u.account_id and h.active) then raise exception 'retirement hold' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_lifecycle_audit where request_id=p_request and action not in ('deletion.challenge','deletion.accepted_restricted','deletion.email_otp_reserved','deletion.email_otp_verified','sessions.succeeded','sessions.blocked','sessions.pending','content.scope_accepted','content.primary_verified','content.blocked','content.failed','restore.restriction_replayed')) then raise exception 'unclassified audit action' using errcode='42501'; end if;
 if exists(select 1 from pg_constraint where contype='f' and confrelid='public.privacy_lifecycle_audit'::regclass) then raise exception 'dependency changed' using errcode='42501'; end if;
 if (select count(*) from public.privacy_lifecycle_audit where request_id=p_request)<>u.expected_count then raise exception 'membership changed' using errcode='40001'; end if;
 insert into public.privacy_security_retirement_permits values(pg_current_xact_id(),p_request);
 delete from public.privacy_lifecycle_audit where request_id=p_request;
 get diagnostics n=row_count;
 if n<>u.expected_count then raise exception 'retirement verification failed' using errcode='40001'; end if;
 insert into public.privacy_legacy_retirement_attestations(category,classifier_version,count) values('security_audit','c15.legacy.security.v1',n);
 update public.privacy_legacy_audit_retirements set completed=true where request_id=p_request;
 delete from public.privacy_security_retirement_permits where transaction_id=pg_current_xact_id();
 return n;
end $$;
alter function public.privacy_retire_legacy_security(uuid,bigint) owner to privacy_retirement_owner;
revoke all on function public.privacy_prepare_legacy_security(uuid),public.privacy_retire_legacy_security(uuid,bigint),public.privacy_legacy_audit_guard() from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_prepare_legacy_security(uuid) to privacy_preparation_executor;
grant execute on function public.privacy_retire_legacy_security(uuid,bigint) to privacy_retirement_executor;

grant insert on public.privacy_legacy_reply_retirements to privacy_retirement_owner;
create function public.privacy_prepare_legacy_replies(p_run uuid,p_request uuid) returns integer language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; accepted timestamptz; n integer; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' then raise exception 'preparation denied' using errcode='42501'; end if;
 select account_id,accepted_at into account,accepted from public.privacy_deletion_requests where request_id=p_request and state='accepted_restricted';
 if accepted is null then raise exception 'accepted clock required' using errcode='42501'; end if;
 perform 1 from auth.users where id=account for no key update;
 if not exists(select 1 from public.subscription_auto_runs where run_id=p_run and account_id=account) then raise exception 'run ownership denied' using errcode='42501'; end if;
 select count(*) into n from public.subscription_auto_replies where run_id=p_run;
 insert into public.privacy_legacy_reply_retirements(run_id,account_id,request_id,accepted_at,eligible_at,expected_count) values(p_run,account,p_request,accepted,accepted+interval '90 days',n) on conflict do nothing;
 return n;
end $$;
alter function public.privacy_prepare_legacy_replies(uuid,uuid) owner to privacy_retirement_owner;
revoke all on function public.privacy_prepare_legacy_replies(uuid,uuid) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor;
grant execute on function public.privacy_prepare_legacy_replies(uuid,uuid) to privacy_preparation_executor;

-- Owner approved 1 Nov: exact credential-field redaction in this disposable
-- candidate. No JSON patch/table/predicate is accepted from a caller.
create table public.privacy_legacy_redaction_permits(transaction_id xid8 primary key,account_id uuid not null,job_id uuid not null,lease_id uuid not null);
create table public.privacy_legacy_redaction_attestations(id uuid primary key default gen_random_uuid(),classifier_version text not null check(classifier_version='c15.legacy.auto-token.v1'),field_path text not null check(field_path='$.owner_token'),rows integer not null check(rows between 1 and 4096),redacted_at timestamptz not null default clock_timestamp());
alter table public.privacy_legacy_redaction_permits enable row level security;
alter table public.privacy_legacy_redaction_permits force row level security;
alter table public.privacy_legacy_redaction_attestations enable row level security;
alter table public.privacy_legacy_redaction_attestations force row level security;
revoke all on public.privacy_legacy_redaction_permits,public.privacy_legacy_redaction_attestations from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_retirement_executor,privacy_preparation_executor;
grant select,insert,delete on public.privacy_legacy_redaction_permits to privacy_retirement_owner;
grant insert on public.privacy_legacy_redaction_attestations to privacy_retirement_owner;
grant update(document) on public.subscription_auto_replies to privacy_retirement_owner;
grant select on public.privacy_content_jobs to privacy_retirement_owner;
grant update(id) on public.privacy_content_jobs to privacy_retirement_owner;
create policy legacy_redaction_permit_owner on public.privacy_legacy_redaction_permits to privacy_retirement_owner using(true) with check(true);
create policy legacy_redaction_attestation_owner on public.privacy_legacy_redaction_attestations to privacy_retirement_owner using(true) with check(true);
create policy legacy_redaction_job_read on public.privacy_content_jobs for select to privacy_retirement_owner using(true);
create policy legacy_redaction_job_lock on public.privacy_content_jobs for update to privacy_retirement_owner using(true) with check(true);
create policy legacy_redaction_update on public.subscription_auto_replies for update to privacy_retirement_owner using(exists(select 1 from public.privacy_legacy_redaction_permits p join public.subscription_auto_runs r on r.account_id=p.account_id where p.transaction_id=pg_current_xact_id() and r.run_id=subscription_auto_replies.run_id)) with check(true);
create trigger legacy_redaction_attestation_immutable before update or delete on public.privacy_legacy_redaction_attestations for each row execute function public.catalog_reject_mutation();
create trigger legacy_redaction_attestation_no_truncate before truncate on public.privacy_legacy_redaction_attestations for each statement execute function public.catalog_reject_mutation();
create function public.privacy_redact_legacy_auto(p_job uuid,p_lease uuid) returns integer language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; j public.privacy_content_jobs; n integer; expected integer; begin
 if session_user<>'privacy_cleanup_executor' or current_setting('role',true)<>'none' then raise exception 'redaction denied' using errcode='42501'; end if;
 select account_id into account from public.privacy_content_jobs where id=p_job and kind='account';
 if account is null then raise exception 'redaction scope denied' using errcode='42501'; end if;
 perform 1 from auth.users where id=account for no key update;
 select * into j from public.privacy_content_jobs where id=p_job for update;
 if j.account_id<>account or j.kind<>'account' or j.state<>'running' or j.lease_id is distinct from p_lease or j.lease_until<=clock_timestamp() or not exists(select 1 from public.privacy_deletion_requests where request_id=p_job and account_id=account and state='accepted_restricted' and accepted_at is not null) then raise exception 'stale redaction lease' using errcode='42501'; end if;
 perform 1 from public.subscription_auto_runs where account_id=account for update;
 if exists(select 1 from public.subscription_auto_runs where account_id=account and (active or owner_token is not null or owner_verifier is not null)) then raise exception 'active run authority remains' using errcode='42501'; end if;
 if exists(select 1 from public.subscription_auto_replies a join public.subscription_auto_runs r using(run_id) where r.account_id=account and a.document ? 'owner_token' and (jsonb_typeof(a.document)<>'object' or a.document-array['run_id','owner_token','sequence','fence','active','authorized_until','server_time','heartbeat_seconds']<>'{}')) then raise exception 'unclassified private reply' using errcode='42501'; end if;
 select count(*) into expected from public.subscription_auto_replies a join public.subscription_auto_runs r using(run_id) where r.account_id=account and a.document ? 'owner_token';
 if expected>4096 then raise exception 'redaction coverage bound' using errcode='42501'; end if;
 if expected=0 then return 0; end if;
 insert into public.privacy_legacy_redaction_permits values(pg_current_xact_id(),account,p_job,p_lease);
 update public.subscription_auto_replies a set document=a.document-'owner_token' from public.subscription_auto_runs r where a.run_id=r.run_id and r.account_id=account and a.document ? 'owner_token';
 get diagnostics n=row_count;
 if n<>expected or exists(select 1 from public.subscription_auto_replies a join public.subscription_auto_runs r using(run_id) where r.account_id=account and a.document ? 'owner_token') or not exists(select 1 from public.privacy_content_jobs where id=p_job and lease_id=p_lease and state='running' and lease_until>clock_timestamp()) then raise exception 'redaction verification failed' using errcode='40001'; end if;
 insert into public.privacy_legacy_redaction_attestations(classifier_version,field_path,rows) values('c15.legacy.auto-token.v1','$.owner_token',n);
 delete from public.privacy_legacy_redaction_permits where transaction_id=pg_current_xact_id();
 return n;
end $$;
alter function public.privacy_redact_legacy_auto(uuid,uuid) owner to privacy_retirement_owner;
revoke all on function public.privacy_redact_legacy_auto(uuid,uuid) from public,anon,authenticated,service_role,usage_executor,privacy_preparation_executor,privacy_retirement_executor;
grant execute on function public.privacy_redact_legacy_auto(uuid,uuid) to privacy_cleanup_executor;
commit;
