-- Forward-only RPC fix; preserve the applied migrations and deferred CHECK validation.
begin;

create or replace function public.claim_outbound_email_event(
  p_user_id uuid,
  p_session_id uuid,
  p_email_type text,
  p_recipient_email text,
  p_idempotency_key text,
  p_metadata_json jsonb,
  p_pending_expires_at timestamptz
)
returns table (
  id uuid,
  user_id uuid,
  session_id uuid,
  email_type text,
  recipient_email text,
  provider text,
  provider_message_id text,
  idempotency_key text,
  claim_token uuid,
  reconciliation_token uuid,
  row_version bigint,
  sending_started_at timestamptz,
  lease_expires_at timestamptz,
  pending_expires_at timestamptz,
  status text,
  error_code text,
  metadata_json jsonb,
  created_at timestamptz,
  updated_at timestamptz,
  replayed boolean,
  conflict_reason text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
-- RETURNS TABLE creates output variables named like the conflict-target columns.
-- Resolve those index-column names as columns, only within this function.
#variable_conflict use_column
declare
  v_event_id uuid;
  v_status text;
  v_claim_token uuid;
  v_replayed boolean := false;
  v_conflict_reason text;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  if p_email_type not in (
    'welcome', 'account_security', 'ai_notes_ready', 'session_summary', 'transcript_export', 'marketing_product_update'
  ) then
    raise exception 'email type is not supported' using errcode = 'P0001';
  end if;
  if p_pending_expires_at is null or p_pending_expires_at <= timezone('utc', now()) then
    raise exception 'pending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  insert into public.outbound_email_events as inserted_event (
    user_id,
    session_id,
    email_type,
    recipient_email,
    idempotency_key,
    pending_expires_at,
    status,
    metadata_json
  )
  values (
    p_user_id,
    p_session_id,
    p_email_type,
    p_recipient_email,
    p_idempotency_key,
    p_pending_expires_at,
    'pending',
    coalesce(p_metadata_json, '{}'::jsonb)
  )
  on conflict (user_id, email_type, recipient_email, session_id, idempotency_key) do nothing
  returning inserted_event.id, inserted_event.status, inserted_event.claim_token
  into v_event_id, v_status, v_claim_token;

  if v_event_id is not null then
    return query
    select
      e.id, e.user_id, e.session_id, e.email_type, e.recipient_email,
      e.provider, e.provider_message_id, e.idempotency_key, e.claim_token,
      e.reconciliation_token, e.row_version, e.sending_started_at,
      e.lease_expires_at, e.pending_expires_at, e.status, e.error_code,
      e.metadata_json, e.created_at, e.updated_at,
      false, null::text
    from public.outbound_email_events as e
    where e.id = v_event_id;
    return;
  end if;

  select e.id, e.status, e.claim_token
  into v_event_id, v_status, v_claim_token
  from public.outbound_email_events as e
  where e.user_id = p_user_id
    and e.email_type = p_email_type
    and e.recipient_email = p_recipient_email
    and e.session_id is not distinct from p_session_id
    and e.idempotency_key = p_idempotency_key
  for update;

  if v_event_id is null then
    raise exception 'outbound email event was not found' using errcode = 'P0001';
  end if;

  if v_status = 'sent' then
    v_replayed := true;
  elsif v_status = 'pending' then
    v_conflict_reason := 'already_processing';
  elsif v_status = 'sending' then
    v_conflict_reason := 'already_processing';
  elsif v_status = 'needs_reconciliation' then
    v_conflict_reason := 'needs_reconciliation';
  elsif v_status = 'retry_blocked' then
    v_conflict_reason := 'retry_blocked';
  elsif v_status = 'failed' then
    v_conflict_reason := 'failed_requires_explicit_retry';
  else
    v_conflict_reason := 'event_not_retryable';
  end if;

  return query
  select
    e.id, e.user_id, e.session_id, e.email_type, e.recipient_email,
    e.provider, e.provider_message_id, e.idempotency_key, e.claim_token,
    e.reconciliation_token, e.row_version, e.sending_started_at,
    e.lease_expires_at, e.pending_expires_at, e.status, e.error_code,
    e.metadata_json, e.created_at, e.updated_at,
    v_replayed, v_conflict_reason
  from public.outbound_email_events as e
  where e.id = v_event_id;
end;
$$;


revoke all on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) from public, anon, authenticated;
grant execute on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) to service_role;
commit;
