-- C10.3B backend-owned transactional email event persistence and idempotency.
-- Supabase Auth verification/reset emails are not stored here.

create table if not exists public.outbound_email_events (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid null references public.interview_sessions(id) on delete set null,
  email_type text not null,
  recipient_email text not null,
  provider text null,
  provider_message_id text null,
  idempotency_key text not null,
  claim_token uuid null,
  reconciliation_token uuid null,
  row_version bigint not null default 1,
  sending_started_at timestamptz null,
  lease_expires_at timestamptz null,
  pending_expires_at timestamptz null,
  status text not null default 'pending',
  error_code text null,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint outbound_email_events_type_check check (email_type in (
    'welcome', 'account_security', 'ai_notes_ready', 'session_summary', 'transcript_export'
  )),
  constraint outbound_email_events_recipient_length_check check (
    char_length(recipient_email) between 3 and 254
  ),
  constraint outbound_email_events_idempotency_key_check check (
    char_length(idempotency_key) between 1 and 128
    and idempotency_key ~ '^[A-Za-z0-9._~:-]+$'
  ),
  constraint outbound_email_events_provider_message_id_check check (
    provider_message_id is null or char_length(provider_message_id) between 1 and 255
  ),
  constraint outbound_email_events_error_code_check check (
    error_code is null or error_code ~ '^[A-Za-z0-9_.:-]{1,80}$'
  ),
  constraint outbound_email_events_status_check check (status in (
    'pending', 'sending', 'sent', 'failed', 'canceled', 'needs_reconciliation', 'retry_blocked'
  )),
  constraint outbound_email_events_pending_lease_check check (
    status <> 'pending' or pending_expires_at is not null
  ),
  constraint outbound_email_events_sending_lease_check check (
    status <> 'sending' or (
      claim_token is not null
      and sending_started_at is not null
      and lease_expires_at is not null
    )
  ),
  constraint outbound_email_events_row_version_check check (row_version > 0),
  constraint outbound_email_events_metadata_object_check check (jsonb_typeof(metadata_json) = 'object'),
  constraint outbound_email_events_metadata_size_check check (octet_length(metadata_json::text) <= 4000)
);

-- NULLS NOT DISTINCT makes sessionless and session-bound scopes equally idempotent.
create unique index if not exists outbound_email_events_idempotency_uidx
  on public.outbound_email_events (
    user_id, email_type, recipient_email, session_id, idempotency_key
  ) nulls not distinct;

create index if not exists outbound_email_events_user_created_idx
  on public.outbound_email_events (user_id, created_at desc, id desc);

create index if not exists outbound_email_events_status_lease_idx
  on public.outbound_email_events (status, lease_expires_at, pending_expires_at);

alter table public.outbound_email_events enable row level security;
alter table public.outbound_email_events force row level security;

revoke all on table public.outbound_email_events from public;
revoke all on table public.outbound_email_events from anon;
revoke all on table public.outbound_email_events from authenticated;
grant select, insert, update, delete on table public.outbound_email_events to service_role;

drop trigger if exists set_outbound_email_events_updated_at on public.outbound_email_events;
create trigger set_outbound_email_events_updated_at
before update on public.outbound_email_events
for each row execute function public.set_updated_at();

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
  event_id uuid,
  status text,
  claim_token uuid,
  replayed boolean,
  conflict_reason text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
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
    'welcome', 'account_security', 'ai_notes_ready', 'session_summary', 'transcript_export'
  ) then
    raise exception 'email type is not a backend transactional email' using errcode = 'P0001';
  end if;
  if p_pending_expires_at is null or p_pending_expires_at <= timezone('utc', now()) then
    raise exception 'pending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  insert into public.outbound_email_events (
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
  returning id, outbound_email_events.status, outbound_email_events.claim_token
  into v_event_id, v_status, v_claim_token;

  if v_event_id is not null then
    return query select v_event_id, v_status, v_claim_token, false, null::text;
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

  return query select v_event_id, v_status, v_claim_token, v_replayed, v_conflict_reason;
end;
$$;

create or replace function public.begin_outbound_email_event_send(
  p_user_id uuid,
  p_event_id uuid,
  p_lease_expires_at timestamptz
)
returns table (event_id uuid, status text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
begin
  if p_lease_expires_at is null or p_lease_expires_at <= timezone('utc', now()) then
    raise exception 'sending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  update public.outbound_email_events as e
  set status = 'sending',
      claim_token = extensions.gen_random_uuid(),
      sending_started_at = timezone('utc', now()),
      lease_expires_at = p_lease_expires_at,
      pending_expires_at = null,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'pending'
    and e.pending_expires_at is not null
    and e.pending_expires_at > timezone('utc', now())
  returning e.id into v_event_id;

  if v_event_id is null then
    raise exception 'outbound email event is not claimable' using errcode = 'P0001';
  end if;
  return query select v_event_id, 'sending'::text;
end;
$$;

create or replace function public.reclaim_outbound_email_event_pending(
  p_user_id uuid,
  p_event_id uuid,
  p_lease_expires_at timestamptz
)
returns table (event_id uuid, status text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
begin
  if p_lease_expires_at is null or p_lease_expires_at <= timezone('utc', now()) then
    raise exception 'sending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  update public.outbound_email_events as e
  set status = 'sending',
      claim_token = extensions.gen_random_uuid(),
      sending_started_at = timezone('utc', now()),
      lease_expires_at = p_lease_expires_at,
      pending_expires_at = null,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'pending'
    and e.pending_expires_at is not null
    and e.pending_expires_at < timezone('utc', now())
  returning e.id into v_event_id;

  if v_event_id is null then
    raise exception 'outbound email pending lease is not expired or is missing' using errcode = 'P0001';
  end if;
  return query select v_event_id, 'sending'::text;
end;
$$;

create or replace function public.complete_outbound_email_event(
  p_user_id uuid,
  p_event_id uuid,
  p_claim_token uuid,
  p_status text,
  p_provider text,
  p_provider_message_id text,
  p_error_code text
)
returns table (event_id uuid, status text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
begin
  if p_status not in ('sent', 'failed', 'canceled') then
    raise exception 'event completion status is invalid' using errcode = 'P0001';
  end if;

  update public.outbound_email_events as e
  set status = p_status,
      provider = nullif(coalesce(p_provider, ''), ''),
      provider_message_id = nullif(coalesce(p_provider_message_id, ''), ''),
      error_code = nullif(coalesce(p_error_code, ''), ''),
      claim_token = null,
      sending_started_at = null,
      lease_expires_at = null,
      reconciliation_token = null,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'sending'
    and e.claim_token = p_claim_token
  returning e.id into v_event_id;

  if v_event_id is null then
    raise exception 'outbound email event claim is no longer active' using errcode = 'P0002';
  end if;
  return query select v_event_id, p_status;
end;
$$;

create or replace function public.retry_outbound_email_event(
  p_user_id uuid,
  p_event_id uuid,
  p_pending_expires_at timestamptz,
  p_retryable boolean
)
returns table (event_id uuid, status text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
begin
  if not p_retryable then
    raise exception 'permanent outbound email failures are not retryable' using errcode = 'P0001';
  end if;
  if p_pending_expires_at is null or p_pending_expires_at <= timezone('utc', now()) then
    raise exception 'pending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  update public.outbound_email_events as e
  set status = 'pending',
      provider = null,
      provider_message_id = null,
      error_code = null,
      claim_token = null,
      reconciliation_token = null,
      sending_started_at = null,
      lease_expires_at = null,
      pending_expires_at = p_pending_expires_at,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'failed'
  returning e.id into v_event_id;

  if v_event_id is null then
    raise exception 'outbound email event is not eligible for retry' using errcode = 'P0001';
  end if;
  return query select v_event_id, 'pending'::text;
end;
$$;

create or replace function public.reconcile_outbound_email_event(
  p_user_id uuid,
  p_event_id uuid
)
returns table (event_id uuid, status text, reconciliation_token uuid)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
  v_reconciliation_token uuid;
begin
  update public.outbound_email_events as e
  set status = 'needs_reconciliation',
      reconciliation_token = extensions.gen_random_uuid(),
      claim_token = null,
      sending_started_at = null,
      lease_expires_at = null,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'sending'
    and e.lease_expires_at is not null
    and e.lease_expires_at < timezone('utc', now())
  returning e.id, e.reconciliation_token
  into v_event_id, v_reconciliation_token;

  if v_event_id is null then
    raise exception 'outbound email event is not ready for reconciliation' using errcode = 'P0001';
  end if;
  return query select v_event_id, 'needs_reconciliation'::text, v_reconciliation_token;
end;
$$;

create or replace function public.resolve_outbound_email_event_reconciliation(
  p_user_id uuid,
  p_event_id uuid,
  p_reconciliation_token uuid,
  p_outcome text,
  p_provider_state text,
  p_retryable boolean,
  p_lease_expires_at timestamptz,
  p_provider text,
  p_provider_message_id text,
  p_error_code text
)
returns table (event_id uuid, status text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
  v_status text;
  v_claim_token uuid;
begin
  if p_outcome not in ('sent', 'failed', 'retry', 'retry_blocked') then
    raise exception 'reconciliation outcome is invalid' using errcode = 'P0001';
  end if;
  if p_provider_state not in ('sent', 'permanent_failure', 'not_sent', 'unknown') then
    raise exception 'provider state is invalid' using errcode = 'P0001';
  end if;
  if p_outcome = 'sent' and p_provider_state <> 'sent' then
    raise exception 'unconfirmed event cannot be marked sent' using errcode = 'P0001';
  end if;
  if p_outcome = 'failed' and p_provider_state <> 'permanent_failure' then
    raise exception 'only permanent provider failures can be marked failed' using errcode = 'P0001';
  end if;
  if p_outcome = 'retry' and (p_provider_state <> 'not_sent' or not p_retryable) then
    raise exception 'only confirmed retryable not-sent events can be retried' using errcode = 'P0001';
  end if;
  if p_outcome = 'retry_blocked' and p_provider_state <> 'unknown' then
    raise exception 'retry_blocked requires unknown provider state' using errcode = 'P0001';
  end if;
  if p_outcome = 'retry' and (p_lease_expires_at is null or p_lease_expires_at <= timezone('utc', now())) then
    raise exception 'sending lease is required and must be in the future' using errcode = 'P0001';
  end if;

  if p_outcome = 'retry' then
    v_status := 'sending';
    v_claim_token := extensions.gen_random_uuid();
  elsif p_outcome = 'sent' then
    v_status := 'sent';
  elsif p_outcome = 'failed' then
    v_status := 'failed';
  else
    v_status := 'retry_blocked';
  end if;

  update public.outbound_email_events as e
  set status = v_status,
      provider = nullif(coalesce(p_provider, ''), ''),
      provider_message_id = nullif(coalesce(p_provider_message_id, ''), ''),
      error_code = nullif(coalesce(p_error_code, ''), ''),
      claim_token = v_claim_token,
      reconciliation_token = null,
      sending_started_at = case when p_outcome = 'retry' then timezone('utc', now()) else null end,
      lease_expires_at = case when p_outcome = 'retry' then p_lease_expires_at else null end,
      row_version = e.row_version + 1
  where e.id = p_event_id
    and e.user_id = p_user_id
    and e.status = 'needs_reconciliation'
    and e.reconciliation_token = p_reconciliation_token
  returning e.id into v_event_id;

  if v_event_id is null then
    raise exception 'reconciliation claim is no longer active' using errcode = 'P0002';
  end if;
  return query select v_event_id, v_status;
end;
$$;

revoke all on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) from public;
revoke all on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) from anon;
revoke all on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) from authenticated;
grant execute on function public.claim_outbound_email_event(uuid, uuid, text, text, text, jsonb, timestamptz) to service_role;

revoke all on function public.begin_outbound_email_event_send(uuid, uuid, timestamptz) from public;
revoke all on function public.begin_outbound_email_event_send(uuid, uuid, timestamptz) from anon;
revoke all on function public.begin_outbound_email_event_send(uuid, uuid, timestamptz) from authenticated;
grant execute on function public.begin_outbound_email_event_send(uuid, uuid, timestamptz) to service_role;

revoke all on function public.reclaim_outbound_email_event_pending(uuid, uuid, timestamptz) from public;
revoke all on function public.reclaim_outbound_email_event_pending(uuid, uuid, timestamptz) from anon;
revoke all on function public.reclaim_outbound_email_event_pending(uuid, uuid, timestamptz) from authenticated;
grant execute on function public.reclaim_outbound_email_event_pending(uuid, uuid, timestamptz) to service_role;

revoke all on function public.complete_outbound_email_event(uuid, uuid, uuid, text, text, text, text) from public;
revoke all on function public.complete_outbound_email_event(uuid, uuid, uuid, text, text, text, text) from anon;
revoke all on function public.complete_outbound_email_event(uuid, uuid, uuid, text, text, text, text) from authenticated;
grant execute on function public.complete_outbound_email_event(uuid, uuid, uuid, text, text, text, text) to service_role;

revoke all on function public.retry_outbound_email_event(uuid, uuid, timestamptz, boolean) from public;
revoke all on function public.retry_outbound_email_event(uuid, uuid, timestamptz, boolean) from anon;
revoke all on function public.retry_outbound_email_event(uuid, uuid, timestamptz, boolean) from authenticated;
grant execute on function public.retry_outbound_email_event(uuid, uuid, timestamptz, boolean) to service_role;

revoke all on function public.reconcile_outbound_email_event(uuid, uuid) from public;
revoke all on function public.reconcile_outbound_email_event(uuid, uuid) from anon;
revoke all on function public.reconcile_outbound_email_event(uuid, uuid) from authenticated;
grant execute on function public.reconcile_outbound_email_event(uuid, uuid) to service_role;

revoke all on function public.resolve_outbound_email_event_reconciliation(
  uuid, uuid, uuid, text, text, boolean, timestamptz, text, text, text
) from public;
revoke all on function public.resolve_outbound_email_event_reconciliation(
  uuid, uuid, uuid, text, text, boolean, timestamptz, text, text, text
) from anon;
revoke all on function public.resolve_outbound_email_event_reconciliation(
  uuid, uuid, uuid, text, text, boolean, timestamptz, text, text, text
) from authenticated;
grant execute on function public.resolve_outbound_email_event_reconciliation(
  uuid, uuid, uuid, text, text, boolean, timestamptz, text, text, text
) to service_role;

comment on table public.outbound_email_events is
  'C10.3B backend-only transactional email event claims. Supabase Auth emails are excluded; metadata is safe-only and no raw prompts, transcripts, resume chunks, tokens, headers, or secrets are stored.';
