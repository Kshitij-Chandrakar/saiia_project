-- Additive/default disabled. Auth mutation remains the supported private API.
begin;
create role privacy_identity_executor nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
create role privacy_identity_owner nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
alter table public.privacy_followup_tasks drop constraint privacy_followup_tasks_kind_check;
alter table public.privacy_followup_tasks add constraint privacy_followup_tasks_kind_check check(kind in ('revoke_sessions','personal_cleanup','billing_review','identity_cleanup'));
grant usage on schema public to privacy_identity_owner;
grant select on public.privacy_deletion_requests,public.privacy_followup_tasks,public.billing_operations,public.subscription_payment_receipts,public.outbound_email_events,public.privacy_minimized_records to privacy_identity_owner;
grant insert,update on public.privacy_followup_tasks to privacy_identity_owner;



create policy identity_request_read on public.privacy_deletion_requests for select to privacy_identity_owner using(true);
create policy identity_task_control on public.privacy_followup_tasks to privacy_identity_owner using(true) with check(true);
create policy identity_billing_read on public.billing_operations for select to privacy_identity_owner using(true);
create policy identity_receipt_read on public.subscription_payment_receipts for select to privacy_identity_owner using(true);
create policy identity_notice_read on public.outbound_email_events for select to privacy_identity_owner using(true);
create policy identity_minimized_read on public.privacy_minimized_records for select to privacy_identity_owner using(true);
create function public.privacy_enqueue_identity() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
 if new.kind='revoke_sessions' then insert into public.privacy_followup_tasks(request_id,kind,due_at) values(new.request_id,'identity_cleanup',new.due_at) on conflict do nothing; end if;
 return new;
end $$;
alter function public.privacy_enqueue_identity() owner to privacy_identity_owner;
revoke all on function public.privacy_enqueue_identity() from public,anon,authenticated,service_role,usage_executor,privacy_identity_executor;
create trigger privacy_identity_outbox after insert on public.privacy_followup_tasks for each row execute function public.privacy_enqueue_identity();
grant execute on function public.privacy_email_denied(text) to privacy_identity_owner;
-- Pinned GoTrue soft-delete retains structural identity rows, clears identity_data
-- and replaces provider_id with a 43-character base64url digest. These identifiers
-- remain pseudonymous; verified personal-field cleanup is not physical row erasure.
create function public.privacy_identity_absent(p_account uuid) returns boolean language sql security definer set search_path=pg_catalog as $$
 select exists(select 1 from auth.users where id=p_account and deleted_at is not null and raw_user_meta_data='{}' and raw_app_meta_data='{}' and encrypted_password is null and (case when email is null or position('@' in email)=0 then true else not public.privacy_email_denied(email) end)) and not exists(select 1 from auth.sessions where user_id=p_account) and not exists(select 1 from auth.identities where user_id=p_account and (identity_data is distinct from '{}'::jsonb or provider_id !~ '^[A-Za-z0-9_-]{43}$')) and not exists(select 1 from auth.mfa_factors where user_id=p_account)
$$;
alter function public.privacy_identity_absent(uuid) owner to postgres;
grant execute on function public.privacy_identity_absent(uuid) to privacy_identity_owner;
revoke all on function public.privacy_identity_absent(uuid) from public,anon,authenticated,service_role,usage_executor,privacy_identity_executor;
create function public.privacy_identity_call(p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare t public.privacy_followup_tasks; account uuid; reason text; verified boolean; begin
 if session_user<>'privacy_identity_executor' or current_setting('role',true)<>'none' then raise exception 'identity denied' using errcode='42501'; end if;
 if p_action='claim' then
  update public.privacy_followup_tasks set state='blocked',safe_error='attempts_exhausted',lease_id=null,lease_until=null where kind='identity_cleanup' and state='running' and attempts>=5 and lease_until<=clock_timestamp();
  select x.* into t from public.privacy_followup_tasks x where x.kind='identity_cleanup' and x.attempts<5 and ((x.state in ('pending','blocked') and x.due_at<=clock_timestamp() and coalesce(x.safe_error,'')<>'attempts_exhausted') or (x.state='running' and x.lease_until<=clock_timestamp())) and exists(select 1 from public.privacy_followup_tasks v where v.request_id=x.request_id and v.kind='revoke_sessions' and v.state='succeeded') order by x.due_at,x.request_id for update skip locked limit 1;
  if t.request_id is null then return '{}'::jsonb; end if;
  select account_id into account from public.privacy_deletion_requests where request_id=t.request_id and state='accepted_restricted' and accepted_at is not null;
  if account is null then raise exception 'accepted request required' using errcode='42501'; end if;
  if exists(select 1 from public.billing_operations where account_id=account) or exists(select 1 from public.subscription_payment_receipts where account_id=account) then reason:='billing_contact_required';
  elsif not(exists(select 1 from public.outbound_email_events where user_id=account and email_type='privacy_request_accepted' and status='sent' and metadata_json->>'privacy_request'=t.request_id::text) or exists(select 1 from public.privacy_minimized_records where account_id=account and event_kind='privacy_request_accepted' and outcome='sent')) or exists(select 1 from public.outbound_email_events where user_id=account and email_type like 'privacy_%' and status in ('pending','sending','needs_reconciliation')) then reason:='privacy_notice_pending'; end if;
  if reason is not null then update public.privacy_followup_tasks set state='blocked',safe_error=reason,due_at=clock_timestamp()+interval '1 minute',lease_id=null,lease_until=null where request_id=t.request_id and kind=t.kind; return '{}'::jsonb; end if;
  update public.privacy_followup_tasks set state='running',attempts=attempts+1,lease_id=(p_doc->>'lease_id')::uuid,lease_until=clock_timestamp()+interval '30 seconds',safe_error=null where request_id=t.request_id and kind=t.kind;
  return jsonb_build_object('request_id',t.request_id,'account_id',account,'lease_id',p_doc->>'lease_id');
 end if;
 select account_id into account from public.privacy_deletion_requests where request_id=(p_doc->>'request_id')::uuid and state='accepted_restricted' and accepted_at is not null;
 if account is null or account is distinct from (p_doc->>'account_id')::uuid then raise exception 'identity scope denied' using errcode='42501'; end if;
 perform 1 from c15_auth.lock_user(account);
 select * into t from public.privacy_followup_tasks where request_id=(p_doc->>'request_id')::uuid and kind='identity_cleanup' for update;
 if t.state<>'running' or t.lease_id is distinct from (p_doc->>'lease_id')::uuid or t.lease_until<=clock_timestamp() then raise exception 'identity lease denied' using errcode='42501'; end if;
 verified:=public.privacy_identity_absent(account);
 if p_action='verify' then return jsonb_build_object('verified',verified); end if;
 if p_action<>'finish' then raise exception 'identity action denied' using errcode='42501'; end if;
 update public.privacy_followup_tasks set state=case when verified then 'succeeded' when attempts>=5 then 'blocked' else 'pending' end,safe_error=case when verified then null when attempts>=5 then 'attempts_exhausted' else 'identity_unverified' end,lease_id=null,lease_until=null,due_at=clock_timestamp()+interval '1 minute' where request_id=t.request_id and kind=t.kind;
 return jsonb_build_object('identity_cleanup',case when verified then 'succeeded' when t.attempts>=5 then 'blocked' else 'pending' end,'verified',verified,'full_account_erasure',false);
end $$;
alter function public.privacy_identity_call(text,jsonb) owner to privacy_identity_owner;
revoke all on function public.privacy_identity_call(text,jsonb) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_identity_call(text,jsonb) to privacy_identity_executor;
alter function public.privacy_request_call(uuid,text,jsonb) rename to privacy_request_before_identity;
revoke all on function public.privacy_request_before_identity(uuid,text,jsonb) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_request_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb; identity_state text; reason text; begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 result:=public.privacy_request_before_identity(p_account,p_action,p_doc);
 select state,safe_error into identity_state,reason from public.privacy_followup_tasks where request_id=(result->>'request_id')::uuid and kind='identity_cleanup';
 return result||jsonb_build_object('identity_cleanup',coalesce(identity_state,'not_scheduled'),'identity_cleanup_reason',reason,'full_account_erasure',false);
end $$;
grant execute on function public.privacy_request_before_identity(uuid,text,jsonb) to privacy_identity_owner;
alter function public.privacy_request_call(uuid,text,jsonb) owner to privacy_identity_owner;
revoke all on function public.privacy_request_call(uuid,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.privacy_request_call(uuid,text,jsonb) to usage_executor;
commit;
