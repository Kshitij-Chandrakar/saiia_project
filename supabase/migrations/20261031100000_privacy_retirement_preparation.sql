-- Local candidate only. No backfill, retirement DML, replacement legacy guards,
-- LOGINs, provider operations or production activation.
begin;
create role privacy_preparation_executor nologin nosuperuser nocreatedb nocreaterole noinherit;
create table public.privacy_retirement_configuration(singleton boolean primary key default true check(singleton),enabled boolean not null default false);
insert into public.privacy_retirement_configuration values(true,false);
create table public.privacy_auto_reply_payloads(
 run_id uuid not null references public.subscription_auto_runs on delete restrict,
 sequence bigint not null,
 account_id uuid not null references auth.users on delete restrict,
 format_version integer not null default 2 check(format_version=2),
 state text not null default 'available' check(state in ('available','erased')),
 response jsonb,
 private_checksum bytea,
 erasure_job uuid references public.privacy_content_jobs on delete restrict,
 primary key(run_id,sequence),
 check((state='available' and response is not null and private_checksum is not null and erasure_job is null) or (state='erased' and response is null and private_checksum is null and erasure_job is not null))
);
create table public.privacy_retirement_units(
 unit_id uuid primary key default gen_random_uuid(),
 account_id uuid not null references auth.users on delete restrict,
 request_id uuid references public.privacy_deletion_requests(request_id) on delete restrict,
 category text not null check(category in ('usage_recovery','security_audit','financial','shared','unclassified')),
 classifier_version text not null default 'c15.prepare.v1' check(classifier_version='c15.prepare.v1'),
 confirmation_at timestamptz,
 eligible_at timestamptz,
 revision bigint not null default 1,
 state text not null default 'prepared' check(state='prepared'),
 unique(account_id,category,classifier_version)
);
create table public.privacy_retirement_members(
 unit_id uuid not null references public.privacy_retirement_units on delete restrict,
 member_key text not null,
 kind text not null check(kind in ('auto_reply_v2','minimized_metadata_v1')),
 run_id uuid,
 sequence bigint,
 record_id uuid,
 expected_fence bigint,
 primary key(unit_id,member_key),
 check((kind='auto_reply_v2' and run_id is not null and sequence is not null and record_id is null and expected_fence is not null) or (kind='minimized_metadata_v1' and record_id is not null and run_id is null and sequence is null and expected_fence is null))
);
create table public.privacy_retirement_holds(
 unit_id uuid primary key references public.privacy_retirement_units on delete restrict,
 reason text not null check(reason in ('ownership','security','financial','operational')),
 review_at timestamptz not null check(isfinite(review_at)),
 active boolean not null,
 revision bigint not null
);
create table public.privacy_retirement_preparation_events(
 unit_id uuid not null references public.privacy_retirement_units on delete restrict,
 revision bigint not null,
 event text not null check(event in ('prepared','hold.set','hold.released')),
 recorded_at timestamptz not null default clock_timestamp(),
 primary key(unit_id,revision)
);
create trigger preparation_events_immutable before update or delete on public.privacy_retirement_preparation_events for each row execute function public.catalog_reject_mutation();
create trigger preparation_events_no_truncate before truncate on public.privacy_retirement_preparation_events for each statement execute function public.catalog_reject_mutation();
do $$ declare t text; begin
 foreach t in array array['privacy_retirement_configuration','privacy_auto_reply_payloads','privacy_retirement_units','privacy_retirement_members','privacy_retirement_holds','privacy_retirement_preparation_events'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,privacy_preparation_executor',t);
 end loop;
end $$;

create function public.privacy_auto_payload_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if tg_op='DELETE' then raise exception 'payload erasure requires durable scope' using errcode='42501'; end if;
 if tg_op='UPDATE' and (to_jsonb(new)-array['state','response','private_checksum','erasure_job'] is distinct from to_jsonb(old)-array['state','response','private_checksum','erasure_job'] or new.state<>'erased') then raise exception 'payload mutation denied' using errcode='42501'; end if;
 if new.state='erased' then
  if not exists(select 1 from public.privacy_content_jobs j join public.privacy_deletion_requests r on r.request_id=j.id where j.id=new.erasure_job and j.account_id=new.account_id and j.kind='account' and j.state='running' and j.lease_until>clock_timestamp() and r.state='accepted_restricted') then raise exception 'payload erasure scope denied' using errcode='42501'; end if;
 end if;
 return new;
end $$;
create trigger privacy_payload_integrity before update or delete on public.privacy_auto_reply_payloads for each row execute function public.privacy_auto_payload_guard();
create trigger privacy_payload_no_truncate before truncate on public.privacy_auto_reply_payloads for each statement execute function public.catalog_reject_mutation();

create function public.privacy_auto_reply_write() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; payload jsonb:=new.document; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'reply writer denied' using errcode='42501'; end if;
 select account_id into strict account from public.subscription_auto_runs where run_id=new.run_id;
 perform public.subscription_access_check(account);
 if jsonb_typeof(payload)<>'object' or payload-array['run_id','owner_token','sequence','fence','active','authorized_until','server_time','heartbeat_seconds']<>'{}' or not payload ?& array['run_id','sequence','fence','active','authorized_until','server_time'] or (payload->>'run_id')::uuid<>new.run_id or (payload->>'sequence')::bigint<>new.sequence then raise exception 'invalid private reply' using errcode='22023'; end if;
 insert into public.privacy_auto_reply_payloads(run_id,sequence,account_id,response,private_checksum) values(new.run_id,new.sequence,account,payload,sha256(convert_to(payload::text,'UTF8')));
 new.document:=jsonb_build_object('format_version',2);
 return new;
end $$;
create trigger privacy_auto_forward_write before insert on public.subscription_auto_replies for each row execute function public.privacy_auto_reply_write();

create function public.privacy_auto_payload_decode(private public.privacy_auto_reply_payloads,r public.subscription_auto_runs,p_sequence bigint) returns jsonb language plpgsql set search_path=pg_catalog as $$
begin
 if private.run_id is null then raise exception 'reply unavailable' using errcode='P1005'; end if;
 if private.account_id<>r.account_id or private.run_id<>r.run_id or private.sequence<>p_sequence then raise exception 'reply ownership denied' using errcode='42501'; end if;
 if private.state='erased' then raise exception 'reply erased' using errcode='P1001'; end if;
 if private.format_version is distinct from 2 then raise exception 'reply version unsupported' using errcode='P1004'; end if;
 if private.response is null or jsonb_typeof(private.response)<>'object' or private.response-array['run_id','owner_token','sequence','fence','active','authorized_until','server_time','heartbeat_seconds']<>'{}' or not private.response ?& array['run_id','sequence','fence','active','authorized_until','server_time'] then raise exception 'reply corrupt' using errcode='P1003'; end if;
 if private.response is null or private.private_checksum is distinct from sha256(convert_to(private.response::text,'UTF8')) or (private.response->>'run_id')::uuid<>r.run_id or (private.response->>'sequence')::bigint<>p_sequence then raise exception 'reply corrupt' using errcode='P1003'; end if;
 -- Reuse established live run/fence/lease validity; no new retention period.
 if private.response ? 'owner_token' and (not r.active or (private.response->>'owner_token')::uuid<>r.owner_token or (private.response->>'fence')::bigint<>r.fence or not exists(select 1 from public.usage_operations o where o.operation_id=r.slice_id and o.lease_until>clock_timestamp())) then raise exception 'reply expired' using errcode='P1002'; end if;
 return private.response;
exception when invalid_text_representation or invalid_datetime_format or datetime_field_overflow then raise exception 'reply corrupt' using errcode='P1003';
end $$;
create function public.privacy_auto_reply_read(p_account uuid,p_run uuid,p_sequence bigint) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare envelope jsonb; r public.subscription_auto_runs; private public.privacy_auto_reply_payloads; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'reply reader denied' using errcode='42501'; end if;
 perform public.subscription_access_check(p_account);
 select * into r from public.subscription_auto_runs where run_id=p_run and account_id=p_account;
 if not found then raise exception 'run missing' using errcode='P0002'; end if;
 select document into envelope from public.subscription_auto_replies where run_id=p_run and sequence=p_sequence;
 if envelope is null then raise exception 'reply unavailable' using errcode='P1005'; end if;
 if not envelope ? 'format_version' then return envelope; end if;
 if envelope<>jsonb_build_object('format_version',2) then raise exception 'reply version unsupported' using errcode='P1004'; end if;
 select * into private from public.privacy_auto_reply_payloads where run_id=p_run and sequence=p_sequence and account_id=p_account;
 if not found then raise exception 'reply unavailable' using errcode='P1005'; end if;
 return public.privacy_auto_payload_decode(private,r,p_sequence);
end $$;
do $$ declare definition text; old text:='select document into output from public.subscription_auto_replies where run_id=r.run_id and sequence=0;'; begin
 definition:=pg_get_functiondef('public.subscription_auto_call(uuid,text,jsonb)'::regprocedure);
 if strpos(definition,old)=0 or strpos(definition,'return reply.document;')=0 or strpos(definition,'public.subscription_current(p_account,false)')=0 then raise exception 'unsupported auto reader prerequisite'; end if;
 if strpos(pg_get_functiondef('public.subscription_current(uuid,boolean)'::regprocedure),'public.subscription_access_check(p_account)')=0 then raise exception 'unguarded subscription reader prerequisite'; end if;
 definition:=replace(definition,old,'output:=public.privacy_auto_reply_read(p_account,r.run_id,0);');
 definition:=replace(definition,'return reply.document;','return public.privacy_auto_reply_read(p_account,r.run_id,reply.sequence);');
 execute definition;
end $$;

-- Invoker-only: existing local cleanup connection owns its tables. No new
-- application cleanup principal/DML grant or retirement capability is installed.
create function public.privacy_auto_payload_erase(p_job uuid,p_lease uuid) returns integer language plpgsql set search_path=pg_catalog as $$
declare account uuid; removed integer; begin
 select j.account_id into account from public.privacy_content_jobs j join public.privacy_deletion_requests r on r.request_id=j.id and r.account_id=j.account_id where j.id=p_job and j.kind='account' and j.lease_id=p_lease and j.state='running' and j.lease_until>clock_timestamp() and r.state='accepted_restricted' for update of j;
 if not found then raise exception 'stale erasure scope' using errcode='40001'; end if;
 if exists(select 1 from public.privacy_auto_reply_payloads p join public.subscription_auto_runs r using(run_id) where p.account_id=account and r.account_id<>account) then raise exception 'sidecar ownership ambiguous' using errcode='42501'; end if;
 update public.privacy_auto_reply_payloads set response=null,private_checksum=null,state='erased',erasure_job=p_job where account_id=account and state='available';
 get diagnostics removed=row_count; return removed;
end $$;

create function public.privacy_retirement_prepare(p_account uuid,p_request uuid,p_category text) returns uuid language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare accepted timestamptz; v_unit uuid; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' or not (select enabled from public.privacy_retirement_configuration) then raise exception 'preparation unavailable' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_account for no key update;
 if not found then raise exception 'account unavailable' using errcode='42501'; end if;
 if p_request is not null then
  select accepted_at into accepted from public.privacy_deletion_requests where request_id=p_request and account_id=p_account and state='accepted_restricted';
  if not found then raise exception 'clock ownership denied' using errcode='42501'; end if;
 end if;
 insert into public.privacy_retirement_units(account_id,request_id,category,confirmation_at,eligible_at) values(p_account,p_request,p_category,accepted,case when p_category='usage_recovery' then accepted+interval '90 days' when p_category='security_audit' then accepted+interval '180 days' end) on conflict do nothing returning unit_id into v_unit;
 if v_unit is null then
  select unit_id into v_unit from public.privacy_retirement_units where account_id=p_account and category=p_category and request_id is not distinct from p_request;
  if v_unit is null then raise exception 'preparation identity conflict' using errcode='P0003'; end if;
  return v_unit;
 end if;
 insert into public.privacy_retirement_preparation_events(unit_id,revision,event) values(v_unit,1,'prepared');
 if p_category='usage_recovery' then
  insert into public.privacy_retirement_members(unit_id,member_key,kind,run_id,sequence,expected_fence) select v_unit,r.run_id::text||':'||a.sequence,'auto_reply_v2',r.run_id,a.sequence,r.fence from public.subscription_auto_runs r join public.subscription_auto_replies a using(run_id) where r.account_id=p_account and a.document=jsonb_build_object('format_version',2) limit 1001;
 end if;
 insert into public.privacy_retirement_members(unit_id,member_key,kind,record_id) select v_unit,m.id::text,'minimized_metadata_v1',m.id from public.privacy_minimized_records m where m.account_id=p_account and m.category=p_category limit 1001;
 return v_unit;
end $$;

create function public.privacy_retirement_reason(p_unit uuid) returns text language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare u public.privacy_retirement_units; m public.privacy_retirement_members; r public.subscription_auto_runs; payload public.privacy_auto_reply_payloads; minimal public.privacy_minimized_records; n integer:=0; begin
 select * into strict u from public.privacy_retirement_units where unit_id=p_unit;
 if not (select enabled from public.privacy_retirement_configuration) then return 'disabled'; end if;
 if u.category in ('financial','shared','unclassified') then return 'unsupported_category'; end if;
 if u.classifier_version<>'c15.prepare.v1' then return 'classifier_gap'; end if;
 if not exists(select 1 from public.privacy_deletion_requests where request_id=u.request_id and account_id=u.account_id and state='accepted_restricted' and accepted_at=u.confirmation_at) or u.eligible_at is null then return 'missing_clock'; end if;
 if u.eligible_at is distinct from (u.confirmation_at+(case u.category when 'usage_recovery' then interval '90 days' when 'security_audit' then interval '180 days' end)) then return 'clock_mismatch'; end if;
 if exists(select 1 from public.privacy_retirement_holds where unit_id=p_unit and active and review_at<=clock_timestamp()) then return 'hold_review_due'; end if;
 if exists(select 1 from public.privacy_retirement_holds where unit_id=p_unit and active) then return 'hold'; end if;
 -- Engineering bound, not a retention policy: partial membership never qualifies.
 if (select count(*) from(select 1 from public.privacy_retirement_members where unit_id=p_unit limit 1001) bounded)>1000 then return 'coverage_limit'; end if;
 for m in select * from public.privacy_retirement_members where unit_id=p_unit loop
  n:=n+1;
  if m.kind='auto_reply_v2' then
   if u.category<>'usage_recovery' then return 'mixed_class'; end if;
   select * into r from public.subscription_auto_runs where run_id=m.run_id;
   if not found or r.account_id<>u.account_id then return 'ownership'; end if;
   if r.fence<>m.expected_fence then return 'revision_stale'; end if;
   if r.active or exists(select 1 from public.usage_operations where resource_id=r.run_id and state in ('reserved','dispatched','checkpointed','uncertain') and lease_until>clock_timestamp()) then return 'active_writer'; end if;
   if not exists(select 1 from public.subscription_auto_replies where run_id=m.run_id and sequence=m.sequence and document=jsonb_build_object('format_version',2)) or exists(select 1 from public.subscription_auto_replies where run_id=m.run_id and document<>jsonb_build_object('format_version',2)) then return 'reader_compatibility'; end if;
   select * into payload from public.privacy_auto_reply_payloads where run_id=m.run_id and sequence=m.sequence;
   if not found or payload.account_id<>u.account_id then return 'ownership'; end if;
   if payload.state<>'erased' then return 'private_payload_present'; end if;
   if exists(select 1 from pg_constraint where contype='f' and confrelid='public.subscription_auto_replies'::regclass) then return 'dependency_gap'; end if;
  else
   select * into minimal from public.privacy_minimized_records where id=m.record_id;
   if not found then return 'source_already_removed'; end if;
   if minimal.account_id<>u.account_id then return 'ownership'; end if;
   if minimal.category<>u.category then return 'mixed_class'; end if;
   if minimal.confirmation_at<>u.confirmation_at or minimal.eligible_at is distinct from u.eligible_at then return 'clock_mismatch'; end if;
   if exists(select 1 from pg_constraint where contype='f' and confrelid='public.privacy_minimized_records'::regclass) then return 'dependency_gap'; end if;
   if minimal.state='leased' and minimal.lease_until>clock_timestamp() then return 'active_writer'; end if;
  end if;
 end loop;
 if n=0 then return 'coverage_gap'; end if;
 if exists(select 1 from public.subscription_auto_runs live_run join public.subscription_auto_replies a using(run_id) where u.category='usage_recovery' and live_run.account_id=u.account_id and a.document=jsonb_build_object('format_version',2) and not exists(select 1 from public.privacy_retirement_members x where x.unit_id=p_unit and x.run_id=live_run.run_id and x.sequence=a.sequence)) or exists(select 1 from public.privacy_minimized_records v where v.account_id=u.account_id and v.category=u.category and not exists(select 1 from public.privacy_retirement_members x where x.unit_id=p_unit and x.record_id=v.id)) then return 'coverage_changed'; end if;
 if u.eligible_at>clock_timestamp() then return 'not_due'; end if;
 return 'eligible_preparation_only';
end $$;
create function public.privacy_retirement_report(p_limit integer) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare output jsonb; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' then raise exception 'report denied' using errcode='42501'; end if;
 if p_limit is null or p_limit not between 1 and 100 then raise exception 'invalid report bound' using errcode='22023'; end if;
 select coalesce(jsonb_object_agg(reason,amount),'{}') into output from(select public.privacy_retirement_reason(unit_id) reason,count(*) amount from(select unit_id from public.privacy_retirement_units order by unit_id limit p_limit) bounded group by 1) grouped;
 return jsonb_build_object('counts',output,'classifier_version','c15.prepare.v1','complete_account_coverage',false,'scope_sources',jsonb_build_array('auto_reply_v2','minimized_metadata_v1'),'limit',p_limit,'coverage_gaps',(select count(*)>p_limit from public.privacy_retirement_units),'execution_enabled',false);
end $$;
create function public.privacy_retirement_hold(p_unit uuid,p_revision bigint,p_reason text,p_review timestamptz,p_active boolean) returns bigint language plpgsql security definer set search_path=pg_catalog as $$
declare next_revision bigint; begin
 if session_user<>'privacy_preparation_executor' or current_setting('role',true)<>'none' or not (select enabled from public.privacy_retirement_configuration) then raise exception 'hold denied' using errcode='42501'; end if;
 if p_review is null or not isfinite(p_review) or p_review<=clock_timestamp() then raise exception 'review required' using errcode='22023'; end if;
 update public.privacy_retirement_units set revision=revision+1 where unit_id=p_unit and revision=p_revision returning revision into next_revision;
 if next_revision is null then raise exception 'stale hold revision' using errcode='40001'; end if;
 insert into public.privacy_retirement_holds values(p_unit,p_reason,p_review,p_active,next_revision) on conflict(unit_id) do update set reason=excluded.reason,review_at=excluded.review_at,active=excluded.active,revision=excluded.revision;
 insert into public.privacy_retirement_preparation_events(unit_id,revision,event) values(p_unit,next_revision,case when p_active then 'hold.set' else 'hold.released' end);
 return next_revision;
end $$;
revoke all on function public.privacy_auto_payload_decode(public.privacy_auto_reply_payloads,public.subscription_auto_runs,bigint),public.privacy_auto_payload_guard(),public.privacy_auto_reply_write(),public.privacy_auto_reply_read(uuid,uuid,bigint),public.privacy_auto_payload_erase(uuid,uuid),public.privacy_retirement_prepare(uuid,uuid,text),public.privacy_retirement_reason(uuid),public.privacy_retirement_report(integer),public.privacy_retirement_hold(uuid,bigint,text,timestamptz,boolean) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.privacy_retirement_prepare(uuid,uuid,text),public.privacy_retirement_report(integer),public.privacy_retirement_hold(uuid,bigint,text,timestamptz,boolean) to privacy_preparation_executor;
commit;
