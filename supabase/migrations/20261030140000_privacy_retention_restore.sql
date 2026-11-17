-- Local candidate only: no activation, LOGIN or hosted configuration.
begin;
create role privacy_retention_executor nologin nosuperuser nocreatedb nocreaterole noinherit;
create table public.privacy_minimized_records (
 id uuid primary key default gen_random_uuid(),
 account_id uuid not null references auth.users(id) on delete restrict,
 source_kind text not null check(source_kind in ('security_email','ordinary_email','relay_recovery')),
 source_id uuid not null,
 category text not null check(category in ('usage_recovery','security_audit','unapproved')),
 event_kind text not null check(event_kind ~ '^[a-z][a-z0-9_.]{0,63}$'),
 outcome text not null check(outcome ~ '^[a-z][a-z0-9_]{0,63}$'),
 quantity bigint check(quantity>=0),
 occurred_at timestamptz,
 confirmation_at timestamptz not null,
 eligible_at timestamptz,
 lease_id uuid,
 lease_until timestamptz,
 attempts integer not null default 0,
 state text not null default 'retained' check(state in ('retained','leased','blocked')),
 unique(account_id,source_kind,source_id,event_kind),
 check((category='unapproved')=(eligible_at is null)),
 check((source_kind='security_email' and category='security_audit') or (source_kind='ordinary_email' and category='unapproved') or (source_kind='relay_recovery' and category='usage_recovery'))
);
create unique index privacy_minimized_unique_lease on public.privacy_minimized_records(lease_id) where lease_id is not null;
create table public.privacy_retention_attestations (
 day date not null,
 category text not null check(category in ('usage_recovery','security_audit')),
 removed_count bigint not null check(removed_count>0)
);
create trigger privacy_retention_attestation_immutable before update or delete on public.privacy_retention_attestations for each row execute function public.catalog_reject_mutation();
create trigger privacy_retention_attestation_no_truncate before truncate on public.privacy_retention_attestations for each statement execute function public.catalog_reject_mutation();
create table public.privacy_restore_state (
 singleton boolean primary key default true check(singleton),
 required boolean not null default false,
 ready boolean not null default false,
 checkpoint text
);
insert into public.privacy_restore_state(singleton) values(true);
create table public.privacy_restore_outbox (
 request_id uuid primary key,
 account_id uuid not null references auth.users(id) on delete restrict,
 created_at timestamptz not null default clock_timestamp(),
 checkpoint text
);
create table public.privacy_restored_subjects (
 account_id uuid primary key,
 request_id uuid not null
);
create table public.privacy_restored_sessions (
 account_id uuid not null,
 session_id uuid not null,
 primary key(account_id,session_id)
);
create table public.privacy_restored_replays (
 account_id uuid not null,
 key_version integer not null references public.privacy_matching_keys(version) on delete restrict,
 digest bytea not null,
 primary key(account_id,key_version,digest)
);
do $$ declare t text; begin
 foreach t in array array['privacy_minimized_records','privacy_retention_attestations','privacy_restore_state','privacy_restore_outbox','privacy_restored_subjects','privacy_restored_sessions','privacy_restored_replays'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,usage_executor,privacy_retention_executor',t);
 end loop;
end $$;
create function public.privacy_minimized_integrity() returns trigger
language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare accepted timestamptz; deadline timestamptz; begin
 if tg_op='DELETE' then
  if session_user<>'privacy_retention_executor' or old.eligible_at is null or old.eligible_at>clock_timestamp() then raise exception 'retention denied' using errcode='42501'; end if;
  return old;
 end if;
 if tg_op='UPDATE' then
  if to_jsonb(new)-array['lease_id','lease_until','attempts','state'] is distinct from to_jsonb(old)-array['lease_id','lease_until','attempts','state'] then raise exception 'immutable envelope' using errcode='55000'; end if;
  return new;
 end if;
 select accepted_at into accepted from public.privacy_deletion_requests where account_id=new.account_id and state='accepted_restricted';
 if accepted is null or new.confirmation_at<>accepted then raise exception 'confirmation clock required' using errcode='42501'; end if;
 deadline:=case new.category when 'usage_recovery' then accepted+interval '90 days' when 'security_audit' then accepted+interval '180 days' end;
 if new.eligible_at is distinct from deadline then raise exception 'retention clock mismatch' using errcode='42501'; end if;
 return new;
end $$;
create trigger privacy_minimized_integrity before insert or update or delete on public.privacy_minimized_records for each row execute function public.privacy_minimized_integrity();
create trigger privacy_minimized_no_truncate before truncate on public.privacy_minimized_records for each statement execute function public.catalog_reject_mutation();
create function public.privacy_retention_call(p_action text,p_lease uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare r public.privacy_minimized_records; begin
 if session_user<>'privacy_retention_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='claim' then
  update public.privacy_minimized_records set state='blocked' where eligible_at<=clock_timestamp() and lease_until<=clock_timestamp() and attempts>=5;
  select * into r from public.privacy_minimized_records where state<>'blocked' and eligible_at<=clock_timestamp() and (lease_until is null or lease_until<=clock_timestamp()) and attempts<5 order by eligible_at,id for update skip locked limit 1;
  if not found then return '{}'; end if;
  update public.privacy_minimized_records set state='leased',lease_id=p_lease,lease_until=clock_timestamp()+interval '30 seconds',attempts=attempts+1 where id=r.id;
  return jsonb_build_object('category',r.category,'lease_id',p_lease);
 elsif p_action='finish' then
  select * into r from public.privacy_minimized_records where state='leased' and lease_id=p_lease and lease_until>clock_timestamp() and eligible_at<=clock_timestamp() for update;
  if not found then raise exception 'stale retention lease' using errcode='40001'; end if;
  delete from public.privacy_minimized_records where id=r.id;
  insert into public.privacy_retention_attestations values(current_date,r.category,1);
  return jsonb_build_object('removed',true);
 end if;
 raise exception 'invalid retention action' using errcode='22023';
end $$;
revoke all on function public.privacy_retention_call(text,uuid),public.privacy_minimized_integrity() from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.privacy_retention_call(text,uuid) to privacy_retention_executor;
create function public.privacy_restore_accessible() returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select (not required or ready) and not exists(select 1 from public.privacy_restored_subjects where account_id=auth.uid()) from public.privacy_restore_state where singleton
$$;
revoke all on function public.privacy_restore_accessible() from public;
grant execute on function public.privacy_restore_accessible() to authenticated,service_role,usage_executor;
create function public.privacy_restore_write_fence() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if not public.privacy_restore_accessible() then raise exception 'restore quarantined' using errcode='42501'; end if;
 if exists(select 1 from public.privacy_restored_subjects where account_id=coalesce((to_jsonb(new)->>'user_id')::uuid,(to_jsonb(new)->>'account_id')::uuid)) then raise exception 'restored subject restricted' using errcode='42501'; end if;
 return new;
end $$;
do $$ declare t text; definition text; begin
 foreach t in array array['profiles','resumes','resume_chunks','job_contexts','user_settings','interview_sessions','interview_session_transcript_entries','interview_session_ai_notes','interview_session_ask_ai_messages','interview_session_my_answers','session_generation_turns','interview_answer_sources','interview_answer_diagrams','subscription_screen_results','subscription_notes_versions'] loop
  if to_regclass('public.'||t) is not null then
   execute format('create policy privacy_restore_read on public.%I as restrictive for all to authenticated using(public.privacy_restore_accessible()) with check(public.privacy_restore_accessible())',t);
   execute format('create trigger privacy_restore_fence before insert or update on public.%I for each row execute function public.privacy_restore_write_fence()',t);
  end if;
 end loop;
 create policy privacy_restore_storage on storage.objects as restrictive for all to authenticated using(public.privacy_restore_accessible()) with check(public.privacy_restore_accessible());
 definition:=pg_get_functiondef('public.subscription_access_check(uuid)'::regprocedure);
 definition:=regexp_replace(definition,'\mbegin\M',E'begin\n if not public.privacy_restore_accessible() or exists(select 1 from public.privacy_restored_subjects where account_id=p_account) then raise exception ''restore quarantined'' using errcode=''42501''; end if;','i');
 execute definition;
end $$;
create function public.privacy_restore_enqueue() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if new.state='accepted_restricted' then
  insert into public.privacy_restore_outbox(request_id,account_id) values(new.request_id,new.account_id) on conflict do nothing;
 end if;
 return new;
end $$;
create trigger privacy_restore_capture after insert or update on public.privacy_deletion_requests for each row execute function public.privacy_restore_enqueue();
create function public.privacy_restore_scope_enqueue() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if new.kind in ('session','history') then
  insert into public.privacy_restore_outbox(request_id,account_id) values(new.id,new.account_id) on conflict do nothing;
 end if;
 return new;
end $$;
create trigger privacy_restore_scope_capture after insert on public.privacy_content_jobs for each row execute function public.privacy_restore_scope_enqueue();
-- Keep the existing account/session/key fence, adding restored evidence that
-- deliberately has no Auth FK so an older dataset cannot erase deny evidence.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.privacy_session_erasure_fence()'::regprocedure);
 if strpos(definition,'public.privacy_erased_sessions e')=0 then raise exception 'unexpected session fence'; end if;
 definition:=replace(definition,'public.privacy_erased_sessions e','(select account_id,session_id from public.privacy_erased_sessions union select account_id,session_id from public.privacy_restored_sessions) e');
 definition:=replace(definition,'public.privacy_erased_session_keys e','(select account_id,key_version,digest from public.privacy_erased_session_keys union select account_id,key_version,digest from public.privacy_restored_replays) e');
 execute definition;
end $$;
revoke all on function public.privacy_restore_write_fence(),public.privacy_restore_enqueue(),public.privacy_restore_scope_enqueue() from public,anon,authenticated,service_role,usage_executor;
alter table public.outbound_email_events drop constraint outbound_email_events_type_check;
alter table public.outbound_email_events add constraint outbound_email_events_type_check check(email_type in (
 'welcome','account_security','ai_notes_ready','session_summary','transcript_export','marketing_product_update',
 'billing_payment','billing_renewal','billing_cancellation','billing_access_end',
 'privacy_request_accepted','privacy_primary_verified','privacy_attention_required'));
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.claim_outbound_email_event(uuid,uuid,text,text,text,jsonb,timestamptz)'::regprocedure);
 if strpos(definition,'''marketing_product_update''')=0 then raise exception 'unexpected email claim definition'; end if;
 execute regexp_replace(definition,'''marketing_product_update''','''marketing_product_update'',''privacy_request_accepted'',''privacy_primary_verified'',''privacy_attention_required''');
end $$;
create or replace function public.privacy_email_send_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.privacy_deletion_requests; begin
 if tg_op='INSERT' or (new.status='sending' and old.status is distinct from 'sending') then
  perform 1 from auth.users where id=new.user_id for no key update;
  if new.email_type in ('privacy_request_accepted','privacy_primary_verified','privacy_attention_required') then
   select * into r from public.privacy_deletion_requests where account_id=new.user_id and state='accepted_restricted' and request_id=(new.metadata_json->>'privacy_request')::uuid;
   if r.account_id is null or lower(new.recipient_email) is distinct from (select lower(email) from auth.users where id=new.user_id) then raise exception 'privacy notification denied' using errcode='42501'; end if;
   if new.email_type='privacy_primary_verified' and not exists(select 1 from public.privacy_content_jobs where id=r.request_id and state='primary_verified') then raise exception 'privacy notification state denied' using errcode='42501'; end if;
   if new.email_type='privacy_attention_required' and not exists(select 1 from public.privacy_content_jobs where id=r.request_id and state in ('blocked','failed')) and not exists(select 1 from public.privacy_followup_tasks where request_id=r.request_id and (state='blocked' or kind='billing_review' and due_at<=clock_timestamp())) then raise exception 'privacy notification state denied' using errcode='42501'; end if;
  elsif exists(select 1 from public.subscription_deletion_jobs where account_id=new.user_id) then raise exception 'account restricted' using errcode='42501'; end if;
 end if;
 return new;
end $$;
commit;
