-- Local-only Stage 1B. No managed Auth schema DDL, activation or key seed.
begin;
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
commit;
