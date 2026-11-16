-- Fixed accepted-task preflight; no Auth mutations, keys, LOGINs or activation.
begin;
create function public.privacy_auth_recovery_scope(p_request uuid,p_lease uuid,p_account uuid) returns boolean language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'recovery denied' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_account for no key update;
 if not exists(select 1 from public.privacy_followup_tasks t join public.privacy_deletion_requests r using(request_id) where t.request_id=p_request and r.account_id=p_account and r.state='accepted_restricted' and r.accepted_at is not null and t.kind='revoke_sessions' and t.state='running' and t.lease_id=p_lease and t.lease_until>clock_timestamp()) then raise exception 'recovery scope denied' using errcode='42501'; end if;
 -- Supported soft deletion removes contact/authentication data. It is unsafe to
 -- do that while the approved restricted billing contact channel needs it.
 return not exists(select 1 from public.billing_operations where account_id=p_account)
 and not exists(select 1 from public.subscription_payment_receipts where account_id=p_account)
 -- Never erase the only notification destination before the required accepted
 -- notice is durably sent. Minimized evidence carries no address or body.
 and (exists(select 1 from public.outbound_email_events where user_id=p_account and email_type='privacy_request_accepted' and status='sent' and metadata_json->>'privacy_request'=p_request::text)
 or exists(select 1 from public.privacy_minimized_records where account_id=p_account and event_kind='privacy_request_accepted' and outcome='sent'))
 and not exists(select 1 from public.outbound_email_events where user_id=p_account and email_type like 'privacy_%' and status in ('pending','sending','needs_reconciliation'));
end $$;
revoke all on function public.privacy_auth_recovery_scope(uuid,uuid,uuid) from public,anon,authenticated,service_role,privacy_cleanup_executor,privacy_preparation_executor,privacy_revocation_observer;
grant execute on function public.privacy_auth_recovery_scope(uuid,uuid,uuid) to usage_executor;
commit;
