-- PENDING: fresh C15 install candidate; default off, no keys. Not remote authorization.
-- Do not combine with historical C15 migration execution. See Stage 1C report.
begin;
-- C15 stage 1. Additive/default closed. No key, activation, purge or Auth settings.
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
    policy_version=excluded.policy_version,confirmation_hash=excluded.confirmation_hash,status_hash=excluded.status_hash,status_expires_at=excluded.status_expires_at,email_key_version=excluded.email_key_version,email_digest=excluded.email_digest,expires_at=excluded.expires_at,revision=privacy_deletion_requests.revision+1
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
-- Local-only Stage 1B. No managed Auth schema DDL, activation or key seed.
create table public.privacy_reauth_intents (
 account_id uuid primary key references auth.users(id) on delete restrict,
 request_id uuid not null unique,
 original_session uuid not null,
 confirmation_hash text not null,
 status_hash text not null,
 policy_version text not null,
 started_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 proof_session uuid,
 proof_at timestamptz
);
alter table public.privacy_reauth_intents enable row level security;
alter table public.privacy_reauth_intents force row level security;
revoke all on public.privacy_reauth_intents from public,anon,authenticated,service_role,usage_executor;

-- Every protected hook/check needs a usable key ring. Losing keys is an outage,
-- never evidence that an address is allowed. Historic keys remain necessary.
create or replace function public.privacy_email_denied(p_email text) returns boolean
language plpgsql security definer set search_path=pg_catalog,extensions,public as $$
declare normalized text; begin
 if not exists(select 1 from public.privacy_matching_keys where current_key) then
  if not exists(select 1 from public.privacy_configuration where enabled) and not exists(select 1 from public.privacy_email_suppression) and not exists(select 1 from public.privacy_deletion_requests where state='accepted_restricted') then return false; end if;
  raise exception 'privacy dependency unavailable' using errcode='P0005';
 end if;
 normalized:=public.privacy_normal_email(p_email);
 return exists(select 1 from public.privacy_matching_keys k join public.privacy_email_suppression s
  on s.key_version=k.version and s.digest=hmac(convert_to(normalized,'UTF8'),k.secret,'sha256'));
end $$;

create or replace function public.privacy_before_user_created(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare email text; begin
 email:=public.privacy_normal_email(event->'user'->>'email');
 perform pg_advisory_xact_lock(hashtextextended(email,15715));
 if public.privacy_email_denied(email) then return jsonb_build_object('error',jsonb_build_object('http_code',403,'message','Account unavailable')); end if;
 return '{}'::jsonb;
exception when sqlstate 'P0005' then
 return jsonb_build_object('error',jsonb_build_object('http_code',503,'message','Authentication temporarily unavailable'));
end $$;
create or replace function public.privacy_access_token_hook(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare claims jsonb:=event->'claims'; begin
 if exists(select 1 from public.subscription_deletion_jobs where account_id=(event->>'user_id')::uuid) or public.privacy_email_denied(claims->>'email') then
  return jsonb_build_object('error',jsonb_build_object('http_code',403,'message','Account unavailable'));
 end if;
 return jsonb_build_object('claims',claims||jsonb_build_object('c15_auth_method',event->>'authentication_method'));
exception when sqlstate 'P0005' then
 return jsonb_build_object('error',jsonb_build_object('http_code',503,'message','Authentication temporarily unavailable'));
end $$;

create or replace function public.subscription_account_accessible() returns boolean
language plpgsql stable security definer set search_path=pg_catalog as $$
declare subject uuid:=auth.uid(); begin
 if subject is null or exists(select 1 from public.subscription_deletion_jobs where account_id=subject) then return false; end if;
 return not public.privacy_email_denied((select email from auth.users where id=subject));
end $$;

-- Public-owned commit fences also reject stale/restored identities under a new
-- UUID. Auth's managed tables are not changed by this migration.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.privacy_content_write_guard()'::regprocedure);
 definition:=replace(definition,'return new;',
  'if public.privacy_email_denied((select email from auth.users where id=subject)) then raise exception ''account unavailable'' using errcode=''42501''; end if; return new;');
 execute definition;
 definition:=pg_get_functiondef('public.privacy_storage_write_guard()'::regprocedure);
 definition:=replace(definition,'if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject) then',
  'if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject) or public.privacy_email_denied((select email from auth.users where id=subject)) then');
 execute definition;
end $$;

-- Preserve Stage 1's atomic acceptance/barrier/outbox. Its former entry point
-- becomes inaccessible; the wrapper requires an operation begun BEFORE presence.
alter function public.privacy_request_call(uuid,text,jsonb) rename to privacy_request_v1;
revoke all on function public.privacy_request_v1(uuid,text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_request_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare i public.privacy_reauth_intents; result jsonb; t text; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action in ('begin','challenge') then
  perform 1 from auth.users where id=p_account for no key update;
  if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=p_account) then raise exception 'denied' using errcode='42501'; end if;
  if not exists(select 1 from public.privacy_configuration where enabled and policy_version=p_doc->>'policy_version') then raise exception 'unavailable' using errcode='P0005'; end if;
  if public.privacy_email_denied((select email from auth.users where id=p_account)) then raise exception 'denied' using errcode='42501'; end if;
  select * into i from public.privacy_reauth_intents where account_id=p_account for update;
  if p_action='begin' then
   if i.account_id is null or i.expires_at<=clock_timestamp() then
    insert into public.privacy_reauth_intents(account_id,request_id,original_session,confirmation_hash,status_hash,policy_version)
     values(p_account,(p_doc->>'request_id')::uuid,(p_doc->>'session_id')::uuid,p_doc->>'confirmation_hash',p_doc->>'status_hash',p_doc->>'policy_version')
     on conflict(account_id) do update set request_id=excluded.request_id,original_session=excluded.original_session,
      confirmation_hash=excluded.confirmation_hash,status_hash=excluded.status_hash,policy_version=excluded.policy_version,
      started_at=clock_timestamp(),expires_at=clock_timestamp()+interval '5 minutes',proof_session=null,proof_at=null returning * into i;
   end if;
  end if;
  if i.account_id is null or i.request_id is distinct from (p_doc->>'request_id')::uuid or
   i.confirmation_hash is distinct from p_doc->>'confirmation_hash' or i.status_hash is distinct from p_doc->>'status_hash' or
   i.policy_version is distinct from p_doc->>'policy_version' or p_doc->>'scope' is distinct from 'whole_account' or
   i.expires_at<=clock_timestamp() then raise exception 'denied' using errcode='42501'; end if;
  if p_action='begin' then
   if i.original_session is distinct from (p_doc->>'session_id')::uuid then raise exception 'denied' using errcode='42501'; end if;
   return jsonb_build_object('state','reauthentication_required','not_before',date_trunc('second',i.started_at)+interval '1 second','expires_at',i.expires_at);
  end if;
  if (p_doc->>'reauthenticated_at')::timestamptz<=date_trunc('second',i.started_at) or
   (p_doc->>'reauthenticated_at')::timestamptz>=i.expires_at then raise exception 'presence predates operation' using errcode='42501'; end if;
  -- TOTP must upgrade the original session. Password signs in a fresh session.
  if p_doc->>'proof_method'='totp' and i.original_session is distinct from (p_doc->>'session_id')::uuid then raise exception 'session mismatch' using errcode='42501'; end if;
  if i.proof_session is not null and (i.proof_session is distinct from (p_doc->>'session_id')::uuid or i.proof_at is distinct from (p_doc->>'reauthenticated_at')::timestamptz) then raise exception 'proof already consumed' using errcode='42501'; end if;
  update public.privacy_reauth_intents set proof_session=(p_doc->>'session_id')::uuid,proof_at=(p_doc->>'reauthenticated_at')::timestamptz where account_id=p_account;
 end if;
 if p_action='confirm' and not exists(select 1 from public.privacy_deletion_requests where account_id=p_account and accepted_at is not null) then
  perform public.privacy_email_denied((select email from auth.users where id=p_account));
 end if;
 result:=public.privacy_request_v1(p_account,p_action,p_doc);
 select state into t from public.privacy_followup_tasks where request_id=(result->>'request_id')::uuid and kind='revoke_sessions';
 return result||jsonb_build_object('session_revocation',coalesce(t,'pending'));
end $$;
revoke all on function public.privacy_request_call(uuid,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.privacy_request_call(uuid,text,jsonb) to usage_executor;

alter table public.privacy_followup_tasks drop constraint privacy_followup_tasks_state_check;
alter table public.privacy_followup_tasks add constraint privacy_followup_tasks_state_check check(state in ('pending','blocked','running','succeeded'));
alter table public.privacy_followup_tasks add column attempts integer not null default 0,
 add column lease_id uuid, add column lease_until timestamptz, add column safe_error text;

-- Only revocation can be leased. No cleanup processor or identity deletion.
create function public.privacy_revocation_call(p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare t public.privacy_followup_tasks; subject uuid; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='claim' then
  update public.privacy_followup_tasks set state='blocked',safe_error='attempts_exhausted',lease_id=null,lease_until=null
   where kind='revoke_sessions' and attempts>=5 and state='running' and lease_until<=clock_timestamp();
  select * into t from public.privacy_followup_tasks where kind='revoke_sessions' and attempts<5 and
   ((state='pending' and due_at<=clock_timestamp()) or (state='running' and lease_until<=clock_timestamp()))
   order by due_at,request_id for update skip locked limit 1;
  if t.request_id is null then return '{}'::jsonb; end if;
  update public.privacy_followup_tasks set state='running',attempts=attempts+1,lease_id=(p_doc->>'lease_id')::uuid,
   lease_until=clock_timestamp()+interval '30 seconds',safe_error=null
   where request_id=t.request_id and kind=t.kind returning * into t;
  select account_id into strict subject from public.privacy_deletion_requests where request_id=t.request_id and accepted_at is not null;
  return jsonb_build_object('request_id',t.request_id,'account_id',subject,'lease_id',t.lease_id,'attempt',t.attempts);
 elsif p_action='finish' then
  select * into t from public.privacy_followup_tasks where request_id=(p_doc->>'request_id')::uuid and kind='revoke_sessions' for update;
  if t.state is distinct from 'running' or t.lease_id is distinct from (p_doc->>'lease_id')::uuid or t.lease_until<=clock_timestamp() then raise exception 'stale lease' using errcode='42501'; end if;
  if p_doc->>'outcome' not in ('succeeded','transient','timeout','credential_unavailable') or p_doc->>'outcome' is null then raise exception 'invalid outcome' using errcode='22023'; end if;
  update public.privacy_followup_tasks set state=case when p_doc->>'outcome'='succeeded' then 'succeeded' when attempts>=5 or p_doc->>'outcome'='credential_unavailable' then 'blocked' else 'pending' end,
   safe_error=case when p_doc->>'outcome'='succeeded' then null else p_doc->>'outcome' end,
   due_at=clock_timestamp()+make_interval(secs=>least(3600,30*(2^attempts)::integer)),lease_id=null,lease_until=null
   where request_id=t.request_id and kind=t.kind returning * into t;
  insert into public.privacy_lifecycle_audit(request_id,action) values(t.request_id,'sessions.'||t.state);
  return jsonb_build_object('state',t.state);
 end if;
 raise exception 'invalid action' using errcode='22023';
end $$;
revoke all on function public.privacy_revocation_call(text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.privacy_revocation_call(text,jsonb) to usage_executor;

-- Stage 1's product authority previously skipped suppression when keys vanished.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.subscription_access_check(uuid)'::regprocedure);
 definition:=replace(definition,'exists(select 1 from public.privacy_matching_keys) and public.privacy_email_denied','public.privacy_email_denied');
 execute definition;
end $$;
-- Stage 1C: public-owned objects only. No activation or credential/key seed.
-- Account locks protect existing UUIDs; the shared normalized-email lock also
-- fences a stale/imported identity under another UUID at public commit time.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.privacy_content_write_guard()'::regprocedure);
 definition:=replace(definition,'if public.privacy_email_denied',
  'perform pg_advisory_xact_lock(hashtextextended(public.privacy_normal_email((select email from auth.users where id=subject)),15715)); if public.privacy_email_denied');
 execute definition;
 definition:=pg_get_functiondef('public.privacy_storage_write_guard()'::regprocedure);
 definition:=replace(definition,'if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject)',
  'perform pg_advisory_xact_lock(hashtextextended(public.privacy_normal_email((select email from auth.users where id=subject)),15715)); if not exists(select 1 from auth.users where id=subject) or exists(select 1 from public.subscription_deletion_jobs where account_id=subject)');
 execute definition;
end $$;
create table public.privacy_revocation_credentials (
 request_id uuid primary key references public.privacy_deletion_requests(request_id) on delete restrict,
 key_version text not null check(key_version ~ '^[A-Za-z0-9]{1,32}$'),
 expires_at timestamptz not null,
 ciphertext text not null check(length(ciphertext) between 40 and 24000)
);
alter table public.privacy_revocation_credentials enable row level security;
alter table public.privacy_revocation_credentials force row level security;
revoke all on public.privacy_revocation_credentials from public,anon,authenticated,service_role,usage_executor;

alter function public.privacy_request_call(uuid,text,jsonb) rename to privacy_request_v2;
revoke all on function public.privacy_request_v2(uuid,text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_request_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare result jsonb; c jsonb:=p_doc->'revocation_credential'; was_accepted boolean; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='confirm' then
  perform 1 from auth.users where id=p_account for no key update;
  select accepted_at is not null into was_accepted from public.privacy_deletion_requests where account_id=p_account;
  if not coalesce(was_accepted,false) and (c is null or jsonb_typeof(c)<>'object' or
   (c->>'expires_at')::bigint is null or to_timestamp((c->>'expires_at')::bigint)<=clock_timestamp()+interval '20 seconds' or
   to_timestamp((c->>'expires_at')::bigint)>clock_timestamp()+interval '5 minutes') then raise exception 'credential unavailable' using errcode='P0005'; end if;
 end if;
 result:=public.privacy_request_v2(p_account,p_action,p_doc-'revocation_credential');
 if p_action='confirm' and not coalesce(was_accepted,false) then
  insert into public.privacy_revocation_credentials(request_id,key_version,expires_at,ciphertext)
   values((result->>'request_id')::uuid,c->>'key_version',to_timestamp((c->>'expires_at')::bigint),c->>'ciphertext');
 end if;
 return result;
end $$;
revoke all on function public.privacy_request_call(uuid,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.privacy_request_call(uuid,text,jsonb) to usage_executor;

alter function public.privacy_revocation_call(text,jsonb) rename to privacy_revocation_v1;
revoke all on function public.privacy_revocation_v1(text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_revocation_call(p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare result jsonb; t public.privacy_followup_tasks; c public.privacy_revocation_credentials; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Expiry removes ciphertext even if no browser returns. Independent of claims.
 delete from public.privacy_revocation_credentials where expires_at<=clock_timestamp();
 if p_action='expire' then return '{}'::jsonb; end if;
 if p_action='credential' then
  select * into t from public.privacy_followup_tasks where request_id=(p_doc->>'request_id')::uuid and kind='revoke_sessions' for update;
  if t.state is distinct from 'running' or t.lease_id is distinct from (p_doc->>'lease_id')::uuid or t.lease_until<=clock_timestamp() or
   not exists(select 1 from public.privacy_deletion_requests where request_id=t.request_id and account_id=(p_doc->>'account_id')::uuid and accepted_at is not null) then raise exception 'denied' using errcode='42501'; end if;
  select * into c from public.privacy_revocation_credentials where request_id=t.request_id;
  if c.request_id is null then return '{}'::jsonb; end if;
  return jsonb_build_object('key_version',c.key_version,'expires_at',extract(epoch from c.expires_at)::bigint,'ciphertext',c.ciphertext);
 end if;
 result:=public.privacy_revocation_v1(p_action,p_doc);
 delete from public.privacy_revocation_credentials credential_row using public.privacy_followup_tasks task_row
  where credential_row.request_id=task_row.request_id and task_row.kind='revoke_sessions' and task_row.state in ('succeeded','blocked');
 return result;
end $$;
revoke all on function public.privacy_revocation_call(text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.privacy_revocation_call(text,jsonb) to usage_executor;

-- Supported SQL hooks: ACL is the caller boundary, input is Auth-supplied JSON.
-- No HTTP endpoint, signature secret or arbitrary public lookup is introduced.
create function public.privacy_hook_validate(event jsonb,is_token boolean) returns void
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'supabase_auth_admin' then raise exception 'hook denied' using errcode='42501'; end if;
 if jsonb_typeof(event) is distinct from 'object' or octet_length(event::text)>32768 then raise exception 'invalid hook event' using errcode='22023'; end if;
 if is_token then
  if jsonb_typeof(event->'claims') is distinct from 'object' or not (event->'claims' ?& array['iss','aud','exp','iat','sub','role','aal','session_id','email','phone','is_anonymous']) or
   event->>'user_id' is distinct from event->'claims'->>'sub' or
   jsonb_typeof(event->'authentication_method') is distinct from 'string' then raise exception 'invalid hook event' using errcode='22023'; end if;
  perform (event->>'user_id')::uuid,(event->'claims'->>'session_id')::uuid;
 else
  if jsonb_typeof(event->'user') is distinct from 'object' or event->'user'->>'id' is null or event->'user'->>'email' is null then raise exception 'invalid hook event' using errcode='22023'; end if;
  perform (event->'user'->>'id')::uuid;
 end if;
end $$;
create function public.privacy_auth_before_create(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
begin
 perform public.privacy_hook_validate(event,false);
 return public.privacy_before_user_created(event);
end $$;
create function public.privacy_auth_token(event jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
begin
 perform public.privacy_hook_validate(event,true);
 return public.privacy_access_token_hook(event);
end $$;
revoke all on function public.privacy_hook_validate(jsonb,boolean) from public,anon,authenticated,service_role,usage_executor,supabase_auth_admin;
revoke all on function public.privacy_before_user_created(jsonb),public.privacy_access_token_hook(jsonb) from supabase_auth_admin;
revoke all on function public.privacy_auth_before_create(jsonb),public.privacy_auth_token(jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.privacy_auth_before_create(jsonb),public.privacy_auth_token(jsonb) to supabase_auth_admin;
grant usage on schema public to supabase_auth_admin;
revoke create on schema public from public,anon,authenticated,service_role,usage_executor,supabase_auth_admin;
-- SQL hooks have a provider 2s deadline. Fail closed under lock contention.
alter function public.privacy_auth_before_create(jsonb) set lock_timeout='750ms';
alter function public.privacy_auth_token(jsonb) set lock_timeout='750ms';
create function public.privacy_credential_protocol() returns integer language sql immutable as $$select 1$$;
revoke all on function public.privacy_credential_protocol() from public,anon,authenticated,service_role;
grant execute on function public.privacy_credential_protocol() to usage_executor;
-- Approved mailbox-control fallback. Not Google reauthentication or MFA.
create table public.privacy_email_otp (
 account_id uuid primary key references auth.users(id) on delete restrict,
 request_id uuid not null, session_id uuid not null, code_hash text,
 email_fingerprint text not null, key_version text not null,
 expires_at timestamptz not null, sent_at timestamptz not null,
 attempts integer not null default 0, verified_at timestamptz, consumed_at timestamptz
);
create table public.privacy_email_otp_limits (
 account_id uuid primary key references auth.users(id) on delete restrict,
 hour_start timestamptz not null default clock_timestamp(), hour_count integer not null default 0,
 day_start timestamptz not null default clock_timestamp(), day_count integer not null default 0
);
alter table public.privacy_email_otp enable row level security;
alter table public.privacy_email_otp force row level security;
alter table public.privacy_email_otp_limits enable row level security;
alter table public.privacy_email_otp_limits force row level security;
revoke all on public.privacy_email_otp,public.privacy_email_otp_limits from public,anon,authenticated,service_role,usage_executor,supabase_auth_admin;

alter function public.privacy_request_call(uuid,text,jsonb) rename to privacy_request_v3;
revoke all on function public.privacy_request_v3(uuid,text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_request_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
declare i public.privacy_reauth_intents; o public.privacy_email_otp; l public.privacy_email_otp_limits;
 result jsonb; actual_email text; at_time timestamptz:=clock_timestamp(); accepted boolean;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action not in ('otp_start','otp_verify','otp_ready') and not (p_action='confirm' and p_doc->>'proof_method'='email_otp') then
  return public.privacy_request_v3(p_account,p_action,p_doc);
 end if;
 perform 1 from auth.users where id=p_account for no key update;
 if not found then raise exception 'denied' using errcode='42501'; end if;
 select * into i from public.privacy_reauth_intents where account_id=p_account for update;
 if i.request_id is distinct from (p_doc->>'request_id')::uuid or i.original_session is distinct from (p_doc->>'session_id')::uuid or
  i.confirmation_hash is distinct from p_doc->>'confirmation_hash' or i.status_hash is distinct from p_doc->>'status_hash' or
  i.policy_version is distinct from p_doc->>'policy_version' or p_doc->>'scope' is distinct from 'whole_account' then raise exception 'denied' using errcode='42501'; end if;
 select * into o from public.privacy_email_otp where account_id=p_account for update;
 select accepted_at is not null into accepted from public.privacy_deletion_requests where account_id=p_account;
 if p_action='confirm' and coalesce(accepted,false) then
  return public.privacy_request_v3(p_account,'confirm',p_doc||jsonb_build_object('reauthenticated_at',(select reauthenticated_at from public.privacy_deletion_requests where account_id=p_account)));
 end if;
 if not coalesce(accepted,false) then
  if i.expires_at<=at_time or exists(select 1 from public.subscription_deletion_jobs where account_id=p_account) then raise exception 'expired' using errcode='42501'; end if;
  select public.privacy_normal_email(email) into actual_email from auth.users where id=p_account and email_confirmed_at is not null;
  if actual_email is null or actual_email is distinct from public.privacy_normal_email(p_doc->>'verified_email') or public.privacy_email_denied(actual_email) then raise exception 'denied' using errcode='42501'; end if;
 end if;
 if p_action='otp_start' then
  if coalesce(accepted,false) or o.verified_at is not null and o.expires_at>at_time then raise exception 'denied' using errcode='42501'; end if;
  insert into public.privacy_email_otp_limits(account_id) values(p_account) on conflict do nothing;
  select * into l from public.privacy_email_otp_limits where account_id=p_account for update;
  if l.hour_start<=at_time-interval '1 hour' then l.hour_start:=at_time;l.hour_count:=0; end if;
  if l.day_start<=at_time-interval '1 day' then l.day_start:=at_time;l.day_count:=0; end if;
  if o.sent_at>at_time-interval '60 seconds' or l.hour_count>=3 or l.day_count>=10 then return jsonb_build_object('state','otp_limited'); end if;
  update public.privacy_email_otp_limits set hour_start=l.hour_start,hour_count=l.hour_count+1,day_start=l.day_start,day_count=l.day_count+1 where account_id=p_account;
  if p_doc->>'otp_hash' is null or p_doc->>'email_fingerprint' is null or p_doc->>'otp_key_version' is null then raise exception 'unavailable' using errcode='P0005'; end if;
  insert into public.privacy_email_otp(account_id,request_id,session_id,code_hash,email_fingerprint,key_version,expires_at,sent_at)
   values(p_account,i.request_id,i.original_session,p_doc->>'otp_hash',p_doc->>'email_fingerprint',p_doc->>'otp_key_version',least(i.expires_at,at_time+interval '5 minutes'),at_time)
   on conflict(account_id) do update set request_id=excluded.request_id,session_id=excluded.session_id,code_hash=excluded.code_hash,
    email_fingerprint=excluded.email_fingerprint,key_version=excluded.key_version,expires_at=excluded.expires_at,sent_at=excluded.sent_at,attempts=0,verified_at=null,consumed_at=null;
  insert into public.privacy_lifecycle_audit(request_id,action) values(i.request_id,'deletion.email_otp_reserved');
  return jsonb_build_object('state','otp_reserved','expires_at',least(i.expires_at,at_time+interval '5 minutes'));
 end if;
 if o.request_id is distinct from i.request_id or o.session_id is distinct from i.original_session then raise exception 'denied' using errcode='42501'; end if;
 if not coalesce(accepted,false) and (o.expires_at<=at_time or o.email_fingerprint is distinct from p_doc->'email_fingerprints'->>o.key_version or o.consumed_at is not null) then raise exception 'expired' using errcode='42501'; end if;
 if p_action='otp_verify' then
  if coalesce(accepted,false) or o.verified_at is not null or o.attempts>=5 then return jsonb_build_object('state','otp_rejected'); end if;
  update public.privacy_email_otp set attempts=attempts+1 where account_id=p_account;
  -- Return, not RAISE: failed-attempt accounting must commit.
  if o.code_hash is distinct from p_doc->'otp_hashes'->>o.key_version then return jsonb_build_object('state','otp_rejected'); end if;
  result:=public.privacy_request_v3(p_account,'challenge',p_doc||jsonb_build_object('proof_method','email_otp','reauthenticated_at',at_time));
  update public.privacy_email_otp set verified_at=at_time,code_hash=null where account_id=p_account;
  insert into public.privacy_lifecycle_audit(request_id,action) values(i.request_id,'deletion.email_otp_verified');
  return result||jsonb_build_object('expires_at',o.expires_at);
 end if;
 if o.verified_at is null then raise exception 'proof required' using errcode='42501'; end if;
 if p_action='otp_ready' then
  if coalesce(accepted,false) then raise exception 'denied' using errcode='42501'; end if;
  select jsonb_build_object('state',state,'expires_at',least(expires_at,o.expires_at),'request_id',request_id) into result from public.privacy_deletion_requests where account_id=p_account;
  return result;
 end if;
 result:=public.privacy_request_v3(p_account,'confirm',p_doc||jsonb_build_object('reauthenticated_at',o.verified_at));
 update public.privacy_email_otp set consumed_at=coalesce(consumed_at,at_time),code_hash=null where account_id=p_account;
 return result;
end $$;
revoke all on function public.privacy_request_call(uuid,text,jsonb) from public,anon,authenticated,service_role,supabase_auth_admin;
grant execute on function public.privacy_request_call(uuid,text,jsonb) to usage_executor;

-- Expire transient OTP proof/rate rows through existing recovery, not a new job.
alter function public.privacy_revocation_call(text,jsonb) rename to privacy_revocation_v2;
revoke all on function public.privacy_revocation_v2(text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_revocation_call(p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 delete from public.privacy_email_otp where expires_at<=clock_timestamp();
 delete from public.privacy_email_otp_limits where day_start<=clock_timestamp()-interval '1 day' and hour_start<=clock_timestamp()-interval '1 hour';
 return public.privacy_revocation_v2(p_action,p_doc);
end $$;
revoke all on function public.privacy_revocation_call(text,jsonb) from public,anon,authenticated,service_role,supabase_auth_admin;
grant execute on function public.privacy_revocation_call(text,jsonb) to usage_executor;
commit;
