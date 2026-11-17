-- Stage 1C: public-owned objects only. No activation or credential/key seed.
begin;
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
commit;
