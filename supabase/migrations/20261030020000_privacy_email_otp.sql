-- Approved mailbox-control fallback. Not Google reauthentication or MFA.
begin;
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
