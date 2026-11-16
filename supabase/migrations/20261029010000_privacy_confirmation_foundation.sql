-- C15 stage 1. Additive/default closed. No key, activation, purge or Auth settings.
begin;
create table public.privacy_configuration (
 singleton boolean primary key default true check(singleton),
 enabled boolean not null default false,
 policy_version text not null default 'c15.2026-10-29.v1'
);
insert into public.privacy_configuration(singleton) values(true);
create table public.privacy_matching_keys (
 version integer primary key check(version>0),
 secret bytea not null check(octet_length(secret)>=32),
 current_key boolean not null default false
);
create unique index privacy_one_current_key on public.privacy_matching_keys(current_key) where current_key;
-- Permanent, pseudonymous personal data. Never exposed to application roles.
create table public.privacy_email_suppression (
 key_version integer not null references public.privacy_matching_keys(version) on delete restrict,
 digest bytea not null,
 created_at timestamptz not null default clock_timestamp(),
 primary key(key_version,digest)
);
create table public.privacy_deletion_requests (
 account_id uuid primary key references auth.users(id) on delete restrict,
 request_id uuid not null unique,
 session_id uuid not null,
 reauthenticated_at timestamptz not null,
 policy_version text not null,
 scope text not null check(scope='whole_account'),
 confirmation_hash text not null,
 status_hash text not null,
 email_key_version integer not null references public.privacy_matching_keys(version) on delete restrict,
 email_digest bytea not null,
 state text not null default 'awaiting_confirmation' check(state in ('awaiting_confirmation','accepted_restricted')),
 revision bigint not null default 1,
 created_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null,
 status_expires_at timestamptz not null default clock_timestamp()+interval '7 days',
 accepted_at timestamptz,
 primary_cleanup_target_at timestamptz,
 usage_retention_until timestamptz,
 security_retention_until timestamptz
);
create table public.privacy_followup_tasks (
 request_id uuid not null references public.privacy_deletion_requests(request_id) on delete restrict,
 kind text not null check(kind in ('revoke_sessions','personal_cleanup','billing_review')),
 state text not null default 'pending' check(state in ('pending','blocked')),
 due_at timestamptz not null,
 primary key(request_id,kind)
);
create table public.privacy_lifecycle_audit (
 id bigint generated always as identity primary key,
 request_id uuid not null,
 action text not null,
 recorded_at timestamptz not null default clock_timestamp()
);
create trigger privacy_audit_immutable before update or delete on public.privacy_lifecycle_audit
 for each row execute function public.catalog_reject_mutation();
create trigger privacy_audit_no_truncate before truncate on public.privacy_lifecycle_audit
 for each statement execute function public.catalog_reject_mutation();
do $$ declare t text; begin
 foreach t in array array['privacy_configuration','privacy_matching_keys','privacy_email_suppression','privacy_deletion_requests','privacy_followup_tasks','privacy_lifecycle_audit'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor',t);
 end loop;
end $$;

-- Auth currently lowercases email; ASCII-only matching deliberately fails closed
-- for international normalization until equivalence is verified on the target.
-- No Gmail dot/plus or provider alias folding.
create function public.privacy_normal_email(p_email text) returns text
language plpgsql immutable set search_path=pg_catalog as $$
begin
 if p_email is null or p_email !~ '^[ -~]+$' or length(p_email)>320 or position('@' in p_email)=0 then
  raise exception 'privacy email unavailable' using errcode='22023';
 end if;
 return lower(btrim(p_email) collate "C");
end $$;
create function public.privacy_email_denied(p_email text) returns boolean
language plpgsql security definer set search_path=pg_catalog,extensions,public as $$
declare normalized text; begin
 normalized:=public.privacy_normal_email(p_email);
 return exists(select 1 from public.privacy_matching_keys k join public.privacy_email_suppression s
  on s.key_version=k.version and s.digest=hmac(convert_to(normalized,'UTF8'),k.secret,'sha256'));
end $$;
-- Durable commit fence shared with subscription_deletion_prepare's Auth lock.
-- A BEFORE trigger also covers service-role writes which bypass RLS.
create function public.privacy_content_write_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare subject uuid; begin
 subject:=coalesce((to_jsonb(new)->>'user_id')::uuid,(to_jsonb(new)->>'account_id')::uuid);
 if tg_op='UPDATE' and coalesce(to_jsonb(new)->>'user_id',to_jsonb(new)->>'account_id') is distinct from coalesce(to_jsonb(old)->>'user_id',to_jsonb(old)->>'account_id') then raise exception 'owner immutable' using errcode='42501'; end if;
 if subject is null then raise exception 'privacy owner missing' using errcode='42501'; end if;
 perform 1 from auth.users where id=subject for no key update;
 if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject) then
  raise exception 'account restricted' using errcode='42501';
 end if;
 return new;
end $$;
do $$ declare t text; begin
 foreach t in array array['profiles','resumes','resume_chunks','job_contexts','user_settings',
 'job_context_idempotency_keys','interview_sessions','interview_session_idempotency_keys',
 'interview_session_transcript_entries','interview_session_ai_notes','interview_session_ask_ai_messages',
 'interview_session_ask_ai_request_keys','interview_session_my_answers','session_generation_turns',
 'interview_answer_sources','interview_answer_diagrams','subscription_screen_threads','subscription_screen_results',
 'subscription_notes_versions','subscription_resume_jobs','subscription_resume_active_sets'] loop
  if to_regclass('public.'||t) is not null then
   execute format('create trigger privacy_content_fence before insert or update on public.%I for each row execute function public.privacy_content_write_guard()',t);
  end if;
 end loop;
end $$;

-- Storage metadata write fence. Already-issued signed URLs and bytes in flight
-- have independent expiry; this does not claim to revoke or erase those bytes.
create function public.privacy_storage_write_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare subject uuid; begin
 if new.bucket_id not in ('resumes','exports') then return new; end if;
 begin subject:=split_part(new.name,'/',1)::uuid;
 exception when invalid_text_representation then raise exception 'invalid private object owner' using errcode='42501'; end;
 perform 1 from auth.users where id=subject for no key update;
 if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject) then
  raise exception 'account restricted' using errcode='42501';
 end if;
 return new;
end $$;
create trigger privacy_storage_fence before insert or update on storage.objects
 for each row execute function public.privacy_storage_write_guard();

create function public.privacy_request_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,extensions,public as $$
declare r public.privacy_deletion_requests; at_time timestamptz:=clock_timestamp(); email text; k public.privacy_matching_keys;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- No bootstrap, entitlements or private content on the restricted status path.
 if p_action='status' then
  select * into r from public.privacy_deletion_requests where request_id=(p_doc->>'request_id')::uuid;
 else
  perform 1 from auth.users where id=p_account for no key update;
  if not found then raise exception 'missing account' using errcode='42501'; end if;
  select * into r from public.privacy_deletion_requests where account_id=p_account for update;
 end if;
 if p_action='status' then
  if r.account_id is null or r.request_id is distinct from (p_doc->>'request_id')::uuid or r.status_hash is distinct from p_doc->>'status_hash' or r.status_expires_at<=at_time then raise exception 'denied' using errcode='42501'; end if;
 elsif p_action='challenge' then
  if not exists(select 1 from public.privacy_configuration where enabled and policy_version=p_doc->>'policy_version') or
     not exists(select 1 from public.privacy_matching_keys where current_key) then raise exception 'privacy unavailable' using errcode='P0005'; end if;
  if exists(select 1 from public.subscription_deletion_jobs where account_id=p_account) then raise exception 'account restricted' using errcode='42501'; end if;
  if (p_doc->>'reauthenticated_at')::timestamptz<at_time-interval '5 minutes' or (p_doc->>'reauthenticated_at')::timestamptz>at_time then raise exception 'reauth required' using errcode='42501'; end if;
  select public.privacy_normal_email(u.email) into email from auth.users u where u.id=p_account and u.email_confirmed_at is not null;
  if email is null or email is distinct from public.privacy_normal_email(p_doc->>'verified_email') then raise exception 'identity changed' using errcode='42501'; end if;
  select * into strict k from public.privacy_matching_keys where current_key;
  if r.account_id is not null and r.expires_at>at_time then
   if r.request_id=(p_doc->>'request_id')::uuid and r.session_id=(p_doc->>'session_id')::uuid and r.confirmation_hash=p_doc->>'confirmation_hash' and r.status_hash=p_doc->>'status_hash' then
    return jsonb_build_object('request_id',r.request_id,'state',r.state,'revision',r.revision,'policy_version',r.policy_version,'expires_at',r.expires_at);
   end if;
   raise exception 'confirmation exists' using errcode='P0003';
  end if;
  insert into public.privacy_deletion_requests(account_id,request_id,session_id,reauthenticated_at,policy_version,scope,confirmation_hash,status_hash,email_key_version,email_digest,expires_at)
   values(p_account,(p_doc->>'request_id')::uuid,(p_doc->>'session_id')::uuid,(p_doc->>'reauthenticated_at')::timestamptz,p_doc->>'policy_version','whole_account',p_doc->>'confirmation_hash',p_doc->>'status_hash',k.version,hmac(convert_to(email,'UTF8'),k.secret,'sha256'),at_time+interval '5 minutes')
   on conflict(account_id) do update set request_id=excluded.request_id,session_id=excluded.session_id,reauthenticated_at=excluded.reauthenticated_at,
    policy_version=excluded.policy_version,confirmation_hash=excluded.confirmation_hash,status_hash=excluded.status_hash,email_key_version=excluded.email_key_version,email_digest=excluded.email_digest,expires_at=excluded.expires_at,revision=privacy_deletion_requests.revision+1
   returning * into r;
  insert into public.privacy_lifecycle_audit(request_id,action) values(r.request_id,'deletion.challenge');
 elsif p_action='confirm' then
  if r.account_id is null or r.request_id is distinct from (p_doc->>'request_id')::uuid or r.session_id is distinct from (p_doc->>'session_id')::uuid or
   r.confirmation_hash is distinct from p_doc->>'confirmation_hash' or r.status_hash is distinct from p_doc->>'status_hash' or r.policy_version is distinct from p_doc->>'policy_version' or
   p_doc->>'scope' is distinct from 'whole_account' or p_doc->>'confirmation_text' is distinct from 'delete' then raise exception 'denied' using errcode='42501'; end if;
  -- Matching replay recovers the original acceptance even after expiry/revocation.
  if r.accepted_at is null then
   if r.expires_at<=at_time or r.reauthenticated_at<at_time-interval '5 minutes' or
      r.reauthenticated_at is distinct from (p_doc->>'reauthenticated_at')::timestamptz then raise exception 'confirmation expired' using errcode='42501'; end if;
   if not exists(select 1 from public.privacy_configuration where enabled and policy_version=r.policy_version) then raise exception 'privacy unavailable' using errcode='P0005'; end if;
   select u.email into email from auth.users u where u.id=p_account;
   email:=public.privacy_normal_email(email);
   select * into strict k from public.privacy_matching_keys where version=r.email_key_version;
   if hmac(convert_to(email,'UTF8'),k.secret,'sha256')<>r.email_digest or email is distinct from public.privacy_normal_email(p_doc->>'verified_email') then raise exception 'identity changed' using errcode='42501'; end if;
   -- A shared email lock serializes direct Auth creation with suppression insert.
   perform pg_advisory_xact_lock(hashtextextended(email,15715));
   insert into public.privacy_email_suppression(key_version,digest) values(k.version,hmac(convert_to(email,'UTF8'),k.secret,'sha256')) on conflict do nothing;
   perform public.subscription_deletion_prepare(p_account,r.request_id);
   update public.privacy_deletion_requests set state='accepted_restricted',accepted_at=at_time,revision=revision+1,
    primary_cleanup_target_at=at_time+interval '24 hours',usage_retention_until=at_time+interval '90 days',security_retention_until=at_time+interval '180 days'
    where account_id=p_account returning * into r;
   insert into public.privacy_followup_tasks(request_id,kind,due_at) values
    (r.request_id,'revoke_sessions',at_time),(r.request_id,'personal_cleanup',r.primary_cleanup_target_at),(r.request_id,'billing_review',at_time+interval '7 days');
   insert into public.privacy_lifecycle_audit(request_id,action) values(r.request_id,'deletion.accepted_restricted');
  end if;
 else raise exception 'invalid privacy action' using errcode='22023'; end if;
 return jsonb_build_object('request_id',r.request_id,'state',r.state,'revision',r.revision,'policy_version',r.policy_version,
  'expires_at',r.expires_at,'accepted_at',r.accepted_at,'primary_cleanup_target_at',r.primary_cleanup_target_at,
  'usage_retention_until',r.usage_retention_until,'security_retention_until',r.security_retention_until,
  'content_erased',false,'cleanup_state','pending','session_revocation','pending','billing_resolution','unverified');
end $$;

-- Hooks must be configured in Supabase separately. They are not public APIs.
create function public.privacy_before_user_created(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare email text; begin
 email:=public.privacy_normal_email(event->'user'->>'email');
 perform pg_advisory_xact_lock(hashtextextended(email,15715));
 if public.privacy_email_denied(email) then return jsonb_build_object('error',jsonb_build_object('http_code',403,'message','Account unavailable')); end if;
 return '{}'::jsonb;
end $$;
create function public.privacy_access_token_hook(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare claims jsonb:=event->'claims'; begin
 if exists(select 1 from public.subscription_deletion_jobs where account_id=(event->>'user_id')::uuid) or public.privacy_email_denied(claims->>'email') then
  return jsonb_build_object('error',jsonb_build_object('http_code',403,'message','Account unavailable'));
 end if;
 -- Signed issuance method prevents token_refresh from posing as user presence.
 return jsonb_build_object('claims',claims||jsonb_build_object('c15_auth_method',event->>'authentication_method'));
end $$;
-- Auth-table commit guard closes the gap between hook check and insert, including
-- email changes. Configuring supported hooks remains mandatory for token denial.
create function public.privacy_auth_email_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare email text; begin
 if tg_op='UPDATE' and new.email is not distinct from old.email then return new; end if;
 if not exists(select 1 from public.privacy_matching_keys) then return new; end if;
 if new.email is null or new.email='' then return new; end if;
 email:=public.privacy_normal_email(new.email);
 perform pg_advisory_xact_lock(hashtextextended(email,15715));
 if public.privacy_email_denied(email) or exists(select 1 from public.subscription_deletion_jobs where account_id=new.id) then raise exception 'account unavailable' using errcode='42501'; end if;
 return new;
end $$;
create trigger privacy_auth_email_fence before insert or update of email on auth.users
 for each row execute function public.privacy_auth_email_guard();

create function public.privacy_identity_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare email text; begin
 perform 1 from auth.users where id=new.user_id for no key update;
 if exists(select 1 from public.subscription_deletion_jobs where account_id=new.user_id) then raise exception 'account unavailable' using errcode='42501'; end if;
 email:=to_jsonb(new)->'identity_data'->>'email';
 if email is not null and exists(select 1 from public.privacy_matching_keys) then
  email:=public.privacy_normal_email(email);
  perform pg_advisory_xact_lock(hashtextextended(email,15715));
  if public.privacy_email_denied(email) then raise exception 'account unavailable' using errcode='42501'; end if;
 end if;
 return new;
end $$;
do $$ begin
 if to_regclass('auth.identities') is not null then
  create trigger privacy_identity_fence before insert or update on auth.identities for each row execute function public.privacy_identity_guard();
 end if;
 if to_regclass('auth.sessions') is not null then
  create trigger privacy_new_session_fence before insert on auth.sessions for each row execute function public.privacy_identity_guard();
 end if;
end $$;

create function public.privacy_auth_metadata_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if exists(select 1 from public.subscription_deletion_jobs where account_id=new.id) and (
  to_jsonb(new)->'raw_user_meta_data' is distinct from to_jsonb(old)->'raw_user_meta_data' or
  to_jsonb(new)->'email_change' is distinct from to_jsonb(old)->'email_change' or
  to_jsonb(new)->'phone' is distinct from to_jsonb(old)->'phone') then
  raise exception 'account restricted' using errcode='42501';
 end if;
 return new;
end $$;
create trigger privacy_auth_metadata_fence before update on auth.users
 for each row execute function public.privacy_auth_metadata_guard();

create function public.privacy_email_send_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if tg_op='INSERT' or (new.status='sending' and old.status is distinct from 'sending') then
  perform 1 from auth.users where id=new.user_id for no key update;
  if exists(select 1 from public.subscription_deletion_jobs where account_id=new.user_id) then raise exception 'account restricted' using errcode='42501'; end if;
 end if;
 return new;
end $$;
do $$ begin
 if to_regclass('public.outbound_email_events') is not null then
  create trigger privacy_email_send_fence before insert or update on public.outbound_email_events for each row execute function public.privacy_email_send_guard();
 end if;
end $$;

do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace and proname like 'privacy_%' loop
  execute format('revoke all on function %s from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor',f.signature);
 end loop;
end $$;
grant execute on function public.privacy_request_call(uuid,text,jsonb) to usage_executor;
-- Supabase owns this role; local tests provide its synthetic equivalent.
grant execute on function public.privacy_before_user_created(jsonb),public.privacy_access_token_hook(jsonb) to supabase_auth_admin;

-- Extend existing authority, do not add a competing account-access registry.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.subscription_access_check(uuid)'::regprocedure);
 definition:=replace(definition,'return true;',
  'if exists(select 1 from public.privacy_matching_keys) and public.privacy_email_denied((select email from auth.users where id=p_account)) then raise exception ''access denied'' using errcode=''42501''; end if; return true;');
 execute definition;
 -- Keep verified financial evidence/recovery, never restore a deleted binding.
 definition:=pg_get_functiondef('public.subscription_payment_apply(uuid,uuid,uuid,uuid,timestamptz,text)'::regprocedure);
 definition:=regexp_replace(definition,'\mbegin\M',E'begin\n if session_user<>''usage_binding_executor'' or current_setting(''role'',true)<>''none'' then raise exception ''denied'' using errcode=''42501''; end if;\n perform 1 from auth.users where id=p_account for no key update;\n if exists(select 1 from public.subscription_deletion_jobs where account_id=p_account) then return jsonb_build_object(''account_restricted'',true,''access_granted'',false); end if;','i');
 execute definition;
 if to_regprocedure('public.billing_notification_enqueue(uuid,text,text,timestamptz)') is not null then
  definition:=pg_get_functiondef('public.billing_notification_enqueue(uuid,text,text,timestamptz)'::regprocedure);
  definition:=replace(definition,'insert into public.billing_notification_sources',
   'perform 1 from auth.users where id=o.account_id for no key update; if exists(select 1 from public.subscription_deletion_jobs where account_id=o.account_id) then return; end if; insert into public.billing_notification_sources');
  execute definition;
 end if;
end $$;
commit;
