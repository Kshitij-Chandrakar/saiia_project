-- Fixed privacy-only adapter over the existing durable email contracts.
begin;
grant privacy_runtime_owner to current_user with inherit true, set true;
grant create on schema public to privacy_runtime_owner;
create function public.privacy_notice_event(p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb; begin
 if session_user<>'privacy_content_executor' or current_setting('role',true)<>'none' or octet_length(p_doc::text)>8192 then raise exception 'notice denied' using errcode='42501'; end if;
 if p_action='claim_outbound_email_event' then
  if p_doc->>'p_email_type' not in ('privacy_request_accepted','privacy_primary_verified','privacy_attention_required') then raise exception 'notice type denied' using errcode='42501'; end if;
 else
  if not exists(select 1 from public.outbound_email_events where id=(p_doc->>'p_event_id')::uuid and user_id=(p_doc->>'p_user_id')::uuid and email_type in ('privacy_request_accepted','privacy_primary_verified','privacy_attention_required')) then raise exception 'notice scope denied' using errcode='42501'; end if;
 end if;
 case p_action
 when 'claim_outbound_email_event' then select to_jsonb(event) into result from public.claim_outbound_email_event((p_doc->>'p_user_id')::uuid,(p_doc->>'p_session_id')::uuid,(p_doc->>'p_email_type')::text,(p_doc->>'p_recipient_email')::text,(p_doc->>'p_idempotency_key')::text,(p_doc->'p_metadata_json'),(p_doc->>'p_pending_expires_at')::timestamptz) event;
 when 'begin_outbound_email_event_send' then select to_jsonb(event) into result from public.begin_outbound_email_event_send((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid,(p_doc->>'p_lease_expires_at')::timestamptz) event;
 when 'reclaim_outbound_email_event_pending' then select to_jsonb(event) into result from public.reclaim_outbound_email_event_pending((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid,(p_doc->>'p_lease_expires_at')::timestamptz) event;
 when 'complete_outbound_email_event' then select to_jsonb(event) into result from public.complete_outbound_email_event((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid,(p_doc->>'p_claim_token')::uuid,(p_doc->>'p_status')::text,(p_doc->>'p_provider')::text,(p_doc->>'p_provider_message_id')::text,(p_doc->>'p_error_code')::text) event;
 when 'retry_outbound_email_event' then select to_jsonb(event) into result from public.retry_outbound_email_event((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid,(p_doc->>'p_pending_expires_at')::timestamptz,(p_doc->>'p_retryable')::boolean) event;
 when 'reconcile_outbound_email_event' then select to_jsonb(event) into result from public.reconcile_outbound_email_event((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid) event;
 when 'resolve_outbound_email_event_reconciliation' then select to_jsonb(event) into result from public.resolve_outbound_email_event_reconciliation((p_doc->>'p_user_id')::uuid,(p_doc->>'p_event_id')::uuid,(p_doc->>'p_reconciliation_token')::uuid,(p_doc->>'p_outcome')::text,(p_doc->>'p_provider_state')::text,(p_doc->>'p_retryable')::boolean,(p_doc->>'p_lease_expires_at')::timestamptz,(p_doc->>'p_provider')::text,(p_doc->>'p_provider_message_id')::text,(p_doc->>'p_error_code')::text) event;
 else raise exception 'notice operation denied' using errcode='42501'; end case;
 return result;
end $$;
alter function public.privacy_notice_event(text,jsonb) owner to privacy_runtime_owner;
revoke all on function public.privacy_notice_event(text,jsonb) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_restore_executor;
grant execute on function public.privacy_notice_event(text,jsonb) to privacy_content_executor;
grant execute on function public.claim_outbound_email_event(uuid,uuid,text,text,text,jsonb,timestamptz) to privacy_runtime_owner;
grant execute on function public.begin_outbound_email_event_send(uuid,uuid,timestamptz) to privacy_runtime_owner;
grant execute on function public.reclaim_outbound_email_event_pending(uuid,uuid,timestamptz) to privacy_runtime_owner;
grant execute on function public.complete_outbound_email_event(uuid,uuid,uuid,text,text,text,text) to privacy_runtime_owner;
grant execute on function public.retry_outbound_email_event(uuid,uuid,timestamptz,boolean) to privacy_runtime_owner;
grant execute on function public.reconcile_outbound_email_event(uuid,uuid) to privacy_runtime_owner;
grant execute on function public.resolve_outbound_email_event_reconciliation(uuid,uuid,uuid,text,text,boolean,timestamptz,text,text,text) to privacy_runtime_owner;
create function public.privacy_pending_notices() returns jsonb language sql security definer set search_path=pg_catalog as $$
 select coalesce(jsonb_agg(to_jsonb(candidate)),'[]') from (
 select r.account_id, stage.name as stage
 from public.privacy_deletion_requests r join lateral c15_auth.user_fields(r.account_id) u on true
 left join public.privacy_content_jobs j on j.id=r.request_id
 cross join lateral (
  select 'accepted'::text name where
   not exists(select 1 from public.outbound_email_events e where e.user_id=r.account_id and e.idempotency_key='privacy.'||r.request_id::text||'.accepted' and e.status='sent')
   and not exists(select 1 from public.privacy_minimized_records m where m.account_id=r.account_id and m.event_kind='privacy_request_accepted' and m.outcome='sent')
  union all
  select case when j.state='primary_verified' then 'primary_verified' else 'attention_required' end
  where j.state in ('primary_verified','blocked','failed')
   and not exists(select 1 from public.outbound_email_events e where e.user_id=r.account_id and e.idempotency_key='privacy.'||r.request_id::text||'.'||case when j.state='primary_verified' then 'primary_verified' else 'attention_required' end and e.status='sent')
  limit 1
 ) stage
 where r.state='accepted_restricted' and public.privacy_runtime_contact_available(u.id)
 order by r.accepted_at limit 16) candidate
$$;
alter function public.privacy_pending_notices() owner to privacy_runtime_owner;
revoke all on function public.privacy_pending_notices() from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor,privacy_restore_executor;
grant execute on function public.privacy_pending_notices() to privacy_content_executor;
revoke create on schema public from privacy_runtime_owner;
revoke privacy_runtime_owner from current_user;
commit;
