-- Disposable synthetic candidate only. Not in the normal migration loader.
begin;
create table public.privacy_usage_retirements(
 account_id uuid primary key references auth.users on delete restrict,
 request_id uuid not null references public.privacy_deletion_requests(request_id) on delete restrict,
 accepted_at timestamptz not null, eligible_at timestamptz not null,
 classifier_version text not null default 'c15.closed.usage.v1' check(classifier_version='c15.closed.usage.v1'),
 revision bigint not null default 1, enabled boolean not null default false,
 completed boolean not null default false, expected_counts jsonb not null
);
create table public.privacy_usage_retirement_permits(transaction_id xid8 primary key,account_id uuid not null);
alter table public.privacy_usage_retirements enable row level security;
alter table public.privacy_usage_retirements force row level security;
alter table public.privacy_usage_retirement_permits enable row level security;
alter table public.privacy_usage_retirement_permits force row level security;
revoke all on public.privacy_usage_retirements,public.privacy_usage_retirement_permits from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_retirement_executor;
grant select,insert,update on public.privacy_usage_retirements to privacy_retirement_owner;
grant select,insert,delete on public.privacy_usage_retirement_permits to privacy_retirement_owner;
create policy usage_unit_owner on public.privacy_usage_retirements to privacy_retirement_owner using(true) with check(true);
create policy usage_permit_owner on public.privacy_usage_retirement_permits to privacy_retirement_owner using(true) with check(true);
grant select on public.billing_operations,public.subscription_payment_receipts,public.privacy_content_jobs,public.privacy_minimized_records to privacy_retirement_owner;
create policy usage_billing_read on public.billing_operations for select to privacy_retirement_owner using(true);
create policy usage_receipt_read on public.subscription_payment_receipts for select to privacy_retirement_owner using(true);
create policy usage_content_read on public.privacy_content_jobs for select to privacy_retirement_owner using(true);
create policy usage_minimized_read on public.privacy_minimized_records for select to privacy_retirement_owner using(true);
-- Shared catalogs and financial/audit/suppression/restore evidence are not members.
grant select,delete on public.privacy_auto_reply_payloads to privacy_retirement_owner;
create policy closed_usage_select on public.privacy_auto_reply_payloads for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.privacy_auto_reply_payloads for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_auto_replies to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_auto_replies for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_auto_replies for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_relay_connections to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_relay_connections for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_relay_connections for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_relay_frames to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_relay_frames for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_relay_frames for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_auto_runs to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_auto_runs for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_auto_runs for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_notes_versions to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_notes_versions for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_notes_versions for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_screen_results to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_screen_results for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_screen_results for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_screen_threads to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_screen_threads for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_screen_threads for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_resume_jobs to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_resume_jobs for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_resume_jobs for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_resume_active_sets to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_resume_active_sets for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_resume_active_sets for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_resume_history to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_resume_history for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_resume_history for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_scheduled_changes to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_scheduled_changes for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_scheduled_changes for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_handoff_limits to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_handoff_limits for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_handoff_limits for delete to privacy_retirement_owner using(true);
grant select,delete on public.subscription_binding_history to privacy_retirement_owner;
create policy closed_usage_select on public.subscription_binding_history for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.subscription_binding_history for delete to privacy_retirement_owner using(true);
grant select,delete on public.usage_events to privacy_retirement_owner;
create policy closed_usage_select on public.usage_events for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.usage_events for delete to privacy_retirement_owner using(true);
grant select,delete on public.usage_operations to privacy_retirement_owner;
create policy closed_usage_select on public.usage_operations for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.usage_operations for delete to privacy_retirement_owner using(true);
grant select,delete on public.usage_periods to privacy_retirement_owner;
create policy closed_usage_select on public.usage_periods for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.usage_periods for delete to privacy_retirement_owner using(true);
grant select,delete on public.account_plan_bindings to privacy_retirement_owner;
create policy closed_usage_select on public.account_plan_bindings for select to privacy_retirement_owner using(true);
create policy closed_usage_delete on public.account_plan_bindings for delete to privacy_retirement_owner using(true);
create function public.privacy_closed_usage_guard() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare subject uuid; begin
 subject:=coalesce((to_jsonb(new)->>'account_id')::uuid,(to_jsonb(old)->>'account_id')::uuid);
 if tg_table_name in ('subscription_auto_replies','privacy_auto_reply_payloads') then
  select account_id into subject from public.subscription_auto_runs where run_id=coalesce((to_jsonb(new)->>'run_id')::uuid,(to_jsonb(old)->>'run_id')::uuid);
 end if;
 if tg_op='INSERT' then
  perform 1 from auth.users where id=subject for no key update;
  if exists(select 1 from public.privacy_usage_retirements where account_id=subject and completed) then raise exception 'retired usage replay denied' using errcode='42501'; end if;
  return new;
 end if;
 if tg_op='DELETE' and session_user='privacy_retirement_executor' and current_setting('role',true)='none' and exists(select 1 from public.privacy_usage_retirement_permits where transaction_id=pg_current_xact_id() and account_id=subject) then return old; end if;
 raise exception 'immutable usage' using errcode='42501';
end $$;
alter function public.privacy_closed_usage_guard() owner to privacy_retirement_owner;
-- Preserve ordinary immutable UPDATE/DELETE and all existing TRUNCATE guards.
do $$ declare n text; begin select tgname into strict n from pg_trigger where tgrelid='public.usage_events'::regclass and tgfoid='public.catalog_reject_mutation()'::regprocedure and (tgtype & 1)=1; execute format('drop trigger %I on public.usage_events',n); end $$;
create trigger closed_usage_lifetime before update or delete on public.usage_events for each row execute function public.privacy_closed_usage_guard();
do $$ declare n text; begin select tgname into strict n from pg_trigger where tgrelid='public.subscription_binding_history'::regclass and tgfoid='public.catalog_reject_mutation()'::regprocedure and (tgtype & 1)=1; execute format('drop trigger %I on public.subscription_binding_history',n); end $$;
create trigger closed_usage_lifetime before update or delete on public.subscription_binding_history for each row execute function public.privacy_closed_usage_guard();
do $$ declare d text; begin
 d:=pg_get_functiondef('public.privacy_legacy_reply_guard()'::regprocedure);
 d:=replace(d,$fixed$if tg_op='UPDATE' then$fixed$, $fixed$if tg_op='DELETE' and session_user='privacy_retirement_executor' and current_user='privacy_retirement_owner' and exists(select 1 from public.privacy_usage_retirement_permits p join public.subscription_auto_runs r on r.account_id=p.account_id where p.transaction_id=pg_current_xact_id() and r.run_id=old.run_id) then return old; end if; if tg_op='UPDATE' then$fixed$); execute d;
 d:=pg_get_functiondef('public.privacy_auto_payload_guard()'::regprocedure);
 d:=replace(d,$fixed$if tg_op='DELETE' then raise exception 'payload erasure requires durable scope' using errcode='42501'; end if;$fixed$, $fixed$if tg_op='DELETE' then if session_user='privacy_retirement_executor' and current_user='privacy_retirement_owner' and exists(select 1 from public.privacy_usage_retirement_permits where transaction_id=pg_current_xact_id() and account_id=old.account_id) then return old; end if; raise exception 'payload erasure requires durable scope' using errcode='42501'; end if;$fixed$); execute d;
end $$;
create trigger closed_usage_no_reinsert before insert on public.privacy_auto_reply_payloads for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_auto_replies for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_relay_connections for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_relay_frames for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_auto_runs for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_notes_versions for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_screen_results for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_screen_threads for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_resume_jobs for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_resume_active_sets for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_resume_history for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_scheduled_changes for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_handoff_limits for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.subscription_binding_history for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.usage_events for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.usage_operations for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.usage_periods for each row execute function public.privacy_closed_usage_guard();
create trigger closed_usage_no_reinsert before insert on public.account_plan_bindings for each row execute function public.privacy_closed_usage_guard();
create function public.privacy_usage_financial(p_account uuid) returns boolean language sql security definer set search_path=pg_catalog as $$ select exists(select 1 from public.billing_operations where account_id=p_account) or exists(select 1 from public.subscription_payment_receipts where account_id=p_account) $$;
alter function public.privacy_usage_financial(uuid) owner to privacy_retirement_owner;
revoke all on function public.privacy_usage_financial(uuid) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_retirement_executor;
create function public.privacy_usage_counts(p_account uuid) returns jsonb language sql security definer set search_path=pg_catalog as $$ select jsonb_build_object(
'privacy_auto_reply_payloads',(select count(*) from public.privacy_auto_reply_payloads where account_id=p_account),
'subscription_auto_replies',(select count(*) from public.subscription_auto_replies where run_id in (select run_id from public.subscription_auto_runs where account_id=p_account)),
'subscription_relay_connections',(select count(*) from public.subscription_relay_connections where account_id=p_account),
'subscription_relay_frames',(select count(*) from public.subscription_relay_frames where account_id=p_account),
'subscription_auto_runs',(select count(*) from public.subscription_auto_runs where account_id=p_account),
'subscription_notes_versions',(select count(*) from public.subscription_notes_versions where account_id=p_account),
'subscription_screen_results',(select count(*) from public.subscription_screen_results where account_id=p_account),
'subscription_screen_threads',(select count(*) from public.subscription_screen_threads where account_id=p_account),
'subscription_resume_jobs',(select count(*) from public.subscription_resume_jobs where account_id=p_account),
'subscription_resume_active_sets',(select count(*) from public.subscription_resume_active_sets where account_id=p_account),
'subscription_resume_history',(select count(*) from public.subscription_resume_history where account_id=p_account),
'subscription_scheduled_changes',(select count(*) from public.subscription_scheduled_changes where account_id=p_account),
'subscription_handoff_limits',(select count(*) from public.subscription_handoff_limits where account_id=p_account),
'subscription_binding_history',(select count(*) from public.subscription_binding_history where account_id=p_account and (not public.privacy_usage_financial(p_account) or document->>'price_id' is null)),
'usage_events',(select count(*) from public.usage_events where account_id=p_account and not(public.privacy_usage_financial(p_account) and operation_id is null and used_delta=0 and reserved_delta=0 and event in ('binding.verified_payment','binding.scheduled_change','binding.period_end_change'))),
'usage_operations',(select count(*) from public.usage_operations where account_id=p_account),
'usage_periods',(select count(*) from public.usage_periods where account_id=p_account),
'account_plan_bindings',(select count(*) from public.account_plan_bindings where account_id=p_account and not public.privacy_usage_financial(p_account))) $$;
alter function public.privacy_usage_counts(uuid) owner to privacy_retirement_owner;
revoke all on function public.privacy_usage_counts(uuid) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_retirement_executor;
create function public.privacy_usage_schema_current() returns boolean language sql security definer set search_path=pg_catalog as $$ select (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.account_plan_bindings'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,active:bool,binding_id:uuid,offer_version_id:uuid,policy_version:text,price_id:uuid,revision:int8,signup_at:timestamptz,source_ref:text,valid_from:timestamptz,valid_until:timestamptz' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.billing_operations'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,amount:int8,cancel_requested:bool,consent_at:timestamptz,created_at:timestamptz,currency:text,fingerprint:text,interval_unit:text,last_checked_at:timestamptz,merchant:text,mode:text,offer_version_id:uuid,operation_id:uuid,price_id:uuid,provider_id:text,provider_plan:text,provider_state:text,result:jsonb,snapshot:text,state:text,total_count:int4' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.privacy_auto_reply_payloads'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,erasure_job:uuid,format_version:int4,private_checksum:bytea,response:jsonb,run_id:uuid,sequence:int8,state:text' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_auto_replies'::regclass and a.attnum>0 and not a.attisdropped)='action:text,document:jsonb,request_fence:int8,run_id:uuid,sequence:int8' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_auto_runs'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,active:bool,fence:int8,owner_token:uuid,owner_verifier:bytea,request_id:text,run_id:uuid,semantic_hash:text,sequence:int8,slice_id:uuid,started_at:timestamptz' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_binding_history'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,document:jsonb,recorded_at:timestamptz,revision:int8' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_handoff_limits'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,last_created_at:timestamptz' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_notes_versions'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,operation_id:uuid,result:jsonb' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_payment_receipts'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,event_id:uuid,recorded_at:timestamptz,result:jsonb,semantic_hash:text' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_relay_connections'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,created_at:timestamptz,run_id:uuid,session_id:uuid' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_relay_frames'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,bytes_received:int8,created_at:timestamptz,last_hash:text,last_sequence:int8,run_id:uuid,session_id:uuid,source:text' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_resume_active_sets'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,binding_revision:int8,resume_ids:_uuid' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_resume_history'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,first_ready_at:timestamptz' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_resume_jobs'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,replacement_of:uuid,resume_id:uuid,semantic_hash:text,usage_id:uuid' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_scheduled_changes'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,binding_revision:int8,effective_at:timestamptz,event_id:uuid,kind:text,target_fingerprint:text,target_offer_id:uuid,target_paid_until:timestamptz,target_price_id:uuid' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_screen_results'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,created_at:timestamptz,kind:text,lease_until:timestamptz,request_aliases:jsonb,request_key:text,response:jsonb,result_id:uuid,semantic_hash:text,session_id:uuid,state:text,thread_key:text,token:uuid,turn_key:text,usage_id:uuid' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.subscription_screen_threads'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,busy:uuid,revision:int8,session_id:uuid,thread_key:text' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.usage_events'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,actor_principal:text,event:text,event_id:uuid,fence:int8,operation_id:uuid,recorded_at:timestamptz,reserved_delta:int8,used_delta:int8' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.usage_operations'::regclass and a.attnum>0 and not a.attisdropped)='accepted_offer_id:uuid,account_id:uuid,authorized_at:timestamptz,binding_id:uuid,capacity_released:bool,charged:int8,claim_token:uuid,fence:int8,lease_until:timestamptz,operation:text,operation_id:uuid,period_id:uuid,policy_version:text,recovery_evidence:uuid,request_id:text,requested:int8,resource_id:uuid,result_ref:uuid,semantic_hash:text,state:text,unit_scale:int8' and (select string_agg(a.attname||':'||t.typname,',' order by a.attname) from pg_attribute a join pg_type t on t.oid=a.atttypid where a.attrelid='public.usage_periods'::regclass and a.attnum>0 and not a.attisdropped)='account_id:uuid,allowance:int8,capacity:bool,ends_at:timestamptz,meter:text,mode:text,period_id:uuid,reserved:int8,starts_at:timestamptz,unit_scale:int8,used:int8'  and (select coalesce(jsonb_agg(jsonb_build_array(n.nspname||'.'||child.relname,c.conname,pn.nspname||'.'||parent.relname,c.confdeltype::text,c.conkey::text,c.confkey::text) order by child.relname,c.conname),'[]'::jsonb)
 from pg_constraint c join pg_class child on child.oid=c.conrelid join pg_namespace n on n.oid=child.relnamespace
 join pg_class parent on parent.oid=c.confrelid join pg_namespace pn on pn.oid=parent.relnamespace
 where c.contype='f' and c.confupdtype='a' and not c.condeferrable and not c.condeferred and c.convalidated
 and c.confrelid=any(array['public.usage_events'::regclass,'public.usage_operations'::regclass,'public.usage_periods'::regclass,'public.account_plan_bindings'::regclass,'public.subscription_binding_history'::regclass,'public.subscription_auto_runs'::regclass,'public.subscription_auto_replies'::regclass,'public.subscription_relay_connections'::regclass,'public.subscription_relay_frames'::regclass,'public.subscription_notes_versions'::regclass,'public.subscription_screen_results'::regclass,'public.subscription_screen_threads'::regclass,'public.subscription_resume_jobs'::regclass,'public.subscription_resume_active_sets'::regclass,'public.subscription_resume_history'::regclass,'public.subscription_scheduled_changes'::regclass,'public.subscription_handoff_limits'::regclass,'public.privacy_auto_reply_payloads'::regclass]) )='[["public.privacy_auto_reply_payloads","privacy_auto_reply_payloads_run_id_fkey","public.subscription_auto_runs","r","{1}","{1}"],["public.privacy_legacy_reply_retirements","privacy_legacy_reply_retirements_run_id_fkey","public.subscription_auto_runs","r","{1}","{1}"],["public.subscription_auto_replies","subscription_auto_replies_run_id_fkey","public.subscription_auto_runs","r","{1}","{1}"],["public.subscription_auto_runs","subscription_auto_runs_slice_id_fkey","public.usage_operations","r","{9}","{1}"],["public.subscription_notes_versions","subscription_notes_versions_operation_id_fkey","public.usage_operations","a","{1}","{1}"],["public.subscription_relay_frames","subscription_relay_frames_run_id_fkey","public.subscription_auto_runs","r","{1}","{1}"],["public.subscription_resume_jobs","subscription_resume_jobs_usage_id_fkey","public.usage_operations","a","{5}","{1}"],["public.subscription_screen_results","subscription_screen_results_usage_id_fkey","public.usage_operations","r","{13}","{1}"],["public.usage_events","usage_events_account_id_fkey","public.account_plan_bindings","r","{2}","{1}"],["public.usage_events","usage_events_operation_id_fkey","public.usage_operations","r","{3}","{1}"],["public.usage_operations","usage_operations_account_id_fkey","public.account_plan_bindings","r","{2}","{1}"],["public.usage_operations","usage_operations_binding_id_fkey","public.account_plan_bindings","r","{3}","{2}"],["public.usage_operations","usage_operations_period_id_fkey","public.usage_periods","r","{4}","{1}"],["public.usage_periods","usage_periods_account_id_fkey","public.account_plan_bindings","r","{2}","{1}"]]'::jsonb $$;
alter function public.privacy_usage_schema_current() owner to privacy_retirement_owner;
revoke all on function public.privacy_usage_schema_current() from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_retirement_executor;
create function public.privacy_prepare_usage_retirement(p_account uuid) returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare r public.privacy_deletion_requests; counts jsonb; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' then raise exception 'preparation denied' using errcode='42501'; end if;
 if public.privacy_usage_schema_current() is distinct from true then raise exception 'classifier schema drift' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_account for no key update;
 select * into strict r from public.privacy_deletion_requests where account_id=p_account and state='accepted_restricted' and accepted_at is not null;
 counts:=public.privacy_usage_counts(p_account);
 insert into public.privacy_usage_retirements(account_id,request_id,accepted_at,eligible_at,expected_counts) values(p_account,r.request_id,r.accepted_at,r.accepted_at+interval '90 days',counts) on conflict do nothing;
 return jsonb_build_object('state','prepared','category','usage_recovery');
end $$;
alter function public.privacy_prepare_usage_retirement(uuid) owner to privacy_retirement_owner;
revoke all on function public.privacy_prepare_usage_retirement(uuid) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_retirement_executor;
grant execute on function public.privacy_prepare_usage_retirement(uuid) to privacy_preparation_executor;
grant select,delete on public.privacy_legacy_reply_retirements,public.privacy_retirement_members to privacy_retirement_owner;
create policy usage_member_read on public.privacy_retirement_members for select to privacy_retirement_owner using(true);
create policy usage_member_retire on public.privacy_retirement_members for delete to privacy_retirement_owner using(true);
create function public.privacy_retire_usage(p_account uuid,p_revision bigint) returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare u public.privacy_usage_retirements; accepted timestamptz; total bigint; begin
 if session_user<>'privacy_retirement_executor' or current_setting('role',true)<>'none' then raise exception 'retirement denied' using errcode='42501'; end if;
 if public.privacy_usage_schema_current() is distinct from true then raise exception 'classifier schema drift' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_account for no key update;
 perform 1 from public.privacy_retirement_units where account_id=p_account for share;
 select * into strict u from public.privacy_usage_retirements where account_id=p_account for update;
 if not u.enabled or u.revision<>p_revision then raise exception 'disabled or stale unit' using errcode='42501'; end if;
 if u.completed then return jsonb_build_object('state','already_retired'); end if;
 select accepted_at into accepted from public.privacy_deletion_requests where account_id=p_account and request_id=u.request_id and state='accepted_restricted' for update;
 if accepted is null or accepted<>u.accepted_at or u.eligible_at<>accepted+interval '90 days' or clock_timestamp()<u.eligible_at then raise exception 'usage clock denied' using errcode='42501'; end if;

 if not exists(select 1 from public.privacy_content_jobs where id=u.request_id and account_id=p_account and state='primary_verified') then raise exception 'primary cleanup unverified' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_retirement_units x join public.privacy_retirement_holds h using(unit_id) where x.account_id=p_account and h.active) then raise exception 'retirement hold' using errcode='42501'; end if;
 if exists(select 1 from public.subscription_auto_runs where account_id=p_account and (active or owner_token is not null or owner_verifier is not null)) or exists(select 1 from public.usage_operations where account_id=p_account and state not in ('settled','released')) then raise exception 'active recovery' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_auto_reply_payloads where account_id=p_account and (state<>'erased' or response is not null or private_checksum is not null)) or exists(select 1 from public.subscription_notes_versions where account_id=p_account) or exists(select 1 from public.subscription_screen_results where account_id=p_account) then raise exception 'private payload remains' using errcode='42501'; end if;
 if exists(select 1 from public.usage_periods p where p.account_id=p_account and (p.reserved<>0 or p.used<>coalesce((select sum(e.used_delta) from public.usage_events e join public.usage_operations o using(operation_id) where o.period_id=p.period_id),0))) then raise exception 'accounting inconsistent' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_minimized_records where account_id=p_account and category='usage_recovery') then raise exception 'minimized retention pending' using errcode='42501'; end if;
 if public.privacy_usage_counts(p_account)<>u.expected_counts then raise exception 'membership changed' using errcode='40001'; end if;
 select sum(value::bigint) into total from jsonb_each_text(u.expected_counts);
 if total>50000 then raise exception 'retirement bound' using errcode='42501'; end if;
 insert into public.privacy_usage_retirement_permits values(pg_current_xact_id(),p_account);
delete from public.privacy_auto_reply_payloads where account_id=p_account;
delete from public.subscription_auto_replies where run_id in (select run_id from public.subscription_auto_runs where account_id=p_account);
delete from public.subscription_relay_connections where account_id=p_account;
delete from public.subscription_relay_frames where account_id=p_account;
delete from public.privacy_legacy_reply_retirements where account_id=p_account;
delete from public.privacy_retirement_members m using public.privacy_retirement_units prepared_unit where m.unit_id=prepared_unit.unit_id and prepared_unit.account_id=p_account and prepared_unit.category='usage_recovery';
delete from public.subscription_auto_runs where account_id=p_account;
delete from public.subscription_notes_versions where account_id=p_account;
delete from public.subscription_screen_results where account_id=p_account;
delete from public.subscription_screen_threads where account_id=p_account;
delete from public.subscription_resume_jobs where account_id=p_account;
delete from public.subscription_resume_active_sets where account_id=p_account;
delete from public.subscription_resume_history where account_id=p_account;
delete from public.subscription_scheduled_changes where account_id=p_account;
delete from public.subscription_handoff_limits where account_id=p_account;
delete from public.subscription_binding_history where account_id=p_account and (not public.privacy_usage_financial(p_account) or document->>'price_id' is null);
delete from public.usage_events where account_id=p_account and not(public.privacy_usage_financial(p_account) and operation_id is null and used_delta=0 and reserved_delta=0 and event in ('binding.verified_payment','binding.scheduled_change','binding.period_end_change'));
delete from public.usage_operations where account_id=p_account;
delete from public.usage_periods where account_id=p_account;
delete from public.account_plan_bindings where account_id=p_account and not public.privacy_usage_financial(p_account);
if exists(select 1 from public.account_plan_bindings where account_id=p_account and not public.privacy_usage_financial(p_account)) or exists(select 1 from public.usage_events where account_id=p_account and not(public.privacy_usage_financial(p_account) and operation_id is null and used_delta=0 and reserved_delta=0 and event in ('binding.verified_payment','binding.scheduled_change','binding.period_end_change'))) then raise exception 'absence unverified' using errcode='40001'; end if;
 insert into public.privacy_retention_attestations(day,category,removed_count) select current_date,'usage_recovery',total where total>0;
 update public.privacy_usage_retirements set completed=true,expected_counts='{}' where account_id=p_account;
 delete from public.privacy_usage_retirement_permits where transaction_id=pg_current_xact_id();
 return jsonb_build_object('state','retired','removed',total,'financial_records_retired',false,'financial_parent_exception',public.privacy_usage_financial(p_account));
end $$;
grant insert on public.privacy_retention_attestations to privacy_retirement_owner;
create policy usage_attestation_insert on public.privacy_retention_attestations for insert to privacy_retirement_owner with check(true);
alter function public.privacy_retire_usage(uuid,bigint) owner to privacy_retirement_owner;
revoke all on function public.privacy_retire_usage(uuid,bigint) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_retire_usage(uuid,bigint) to privacy_retirement_executor;
commit;
