-- C4.2 cloud job context lifecycle hardening.
-- Adds the missing job target fields, moves job-context writes behind the
-- backend service role, and provides transaction-safe activation/create RPCs.

alter table public.job_contexts
  add column if not exists location text not null default '',
  add column if not exists employment_type text not null default '',
  add column if not exists source_file_metadata jsonb not null default '{}'::jsonb;

alter table public.job_contexts
  alter column is_active set default false;

alter table public.job_contexts
  drop constraint if exists job_contexts_source_file_metadata_object;

alter table public.job_contexts
  add constraint job_contexts_source_file_metadata_object
  check (jsonb_typeof(source_file_metadata) = 'object');

create index if not exists job_contexts_user_updated_id_idx
  on public.job_contexts (user_id, updated_at desc, id desc);

create table if not exists public.job_context_idempotency_keys (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  status text not null default 'processing',
  job_context_id uuid references public.job_contexts(id) on delete set null,
  activated boolean not null default false,
  expires_at timestamptz not null default timezone('utc', now()) + interval '24 hours',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint job_context_idempotency_status_check check (status in ('processing', 'completed'))
);

create unique index if not exists job_context_idempotency_user_key_idx
  on public.job_context_idempotency_keys (user_id, idempotency_key);

create index if not exists job_context_idempotency_expires_at_idx
  on public.job_context_idempotency_keys (expires_at);

alter table public.job_context_idempotency_keys enable row level security;
alter table public.job_context_idempotency_keys force row level security;

drop trigger if exists set_job_context_idempotency_updated_at on public.job_context_idempotency_keys;
create trigger set_job_context_idempotency_updated_at
before update on public.job_context_idempotency_keys
for each row execute function public.set_updated_at();

create or replace function public.activate_job_context(
  p_user_id uuid,
  p_job_context_id uuid
)
returns setof public.job_contexts
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  activated_context public.job_contexts%rowtype;
  lock_key bigint;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  lock_key := hashtextextended(p_user_id::text, 0);
  perform pg_advisory_xact_lock(lock_key);

  if not exists (
    select 1
    from public.job_contexts
    where id = p_job_context_id
      and user_id = p_user_id
    for update
  ) then
    raise exception 'job context activation precondition failed' using errcode = 'P0001';
  end if;

  update public.job_contexts
  set is_active = false
  where user_id = p_user_id
    and is_active = true
    and id <> p_job_context_id;

  update public.job_contexts
  set is_active = true
  where id = p_job_context_id
    and user_id = p_user_id
  returning * into activated_context;

  if activated_context.id is null then
    raise exception 'job context activation update failed' using errcode = 'P0001';
  end if;

  return next activated_context;
end;
$$;

create or replace function public.create_job_context_with_idempotency(
  p_user_id uuid,
  p_idempotency_key text,
  p_request_hash text,
  p_company text,
  p_position text,
  p_job_description text,
  p_required_skills jsonb,
  p_responsibilities jsonb,
  p_seniority text,
  p_domain_keywords jsonb,
  p_location text,
  p_employment_type text,
  p_source_file_metadata jsonb,
  p_activate boolean
)
returns table (
  job_context_id uuid,
  replayed boolean,
  activated boolean,
  status text
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  reservation public.job_context_idempotency_keys%rowtype;
  created_context public.job_contexts%rowtype;
  lock_key bigint;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';

  delete from public.job_context_idempotency_keys
  where expires_at < timezone('utc', now());

  insert into public.job_context_idempotency_keys (
    user_id,
    idempotency_key,
    request_hash,
    status
  )
  values (
    p_user_id,
    p_idempotency_key,
    p_request_hash,
    'processing'
  )
  on conflict (user_id, idempotency_key) do nothing
  returning * into reservation;

  if reservation.id is null then
    select *
    into reservation
    from public.job_context_idempotency_keys
    where user_id = p_user_id
      and idempotency_key = p_idempotency_key
    for update;

    if reservation.request_hash <> p_request_hash then
      raise exception 'job context idempotency key conflict' using errcode = 'P0001';
    end if;

    if reservation.status = 'completed' and reservation.job_context_id is null then
      job_context_id := null;
      replayed := true;
      activated := reservation.activated;
      status := 'gone';
      return next;
      return;
    end if;

    if reservation.status = 'completed' and reservation.job_context_id is not null then
      job_context_id := reservation.job_context_id;
      replayed := true;
      activated := reservation.activated;
      status := 'completed';
      return next;
      return;
    end if;

    raise exception 'job context idempotency request in progress' using errcode = 'P0001';
  end if;

  insert into public.job_contexts (
    user_id,
    company,
    position,
    job_description,
    required_skills,
    responsibilities,
    seniority,
    domain_keywords,
    location,
    employment_type,
    source_file_metadata,
    is_active
  )
  values (
    p_user_id,
    coalesce(p_company, ''),
    coalesce(p_position, ''),
    coalesce(p_job_description, ''),
    coalesce(p_required_skills, '[]'::jsonb),
    coalesce(p_responsibilities, '[]'::jsonb),
    coalesce(p_seniority, ''),
    coalesce(p_domain_keywords, '[]'::jsonb),
    coalesce(p_location, ''),
    coalesce(p_employment_type, ''),
    coalesce(p_source_file_metadata, '{}'::jsonb),
    false
  )
  returning * into created_context;

  if p_activate then
    lock_key := hashtextextended(p_user_id::text, 0);
    perform pg_advisory_xact_lock(lock_key);

    update public.job_contexts
    set is_active = false
    where user_id = p_user_id
      and is_active = true
      and id <> created_context.id;

    update public.job_contexts
    set is_active = true
    where id = created_context.id
      and user_id = p_user_id
    returning * into created_context;
  end if;

  update public.job_context_idempotency_keys
  set status = 'completed',
      job_context_id = created_context.id,
      activated = p_activate,
      expires_at = timezone('utc', now()) + interval '24 hours'
  where id = reservation.id;

  job_context_id := created_context.id;
  replayed := false;
  activated := p_activate;
  status := 'completed';
  return next;
end;
$$;

revoke insert, update, delete on table public.job_contexts from authenticated;
grant select on table public.job_contexts to authenticated;
grant select, insert, update, delete on table public.job_contexts to service_role;
grant select, insert, update, delete on table public.job_context_idempotency_keys to service_role;

revoke all on function public.activate_job_context(uuid, uuid) from public;
revoke all on function public.activate_job_context(uuid, uuid) from anon;
revoke all on function public.activate_job_context(uuid, uuid) from authenticated;
grant execute on function public.activate_job_context(uuid, uuid) to service_role;

revoke all on function public.create_job_context_with_idempotency(
  uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean
) from public;
revoke all on function public.create_job_context_with_idempotency(
  uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean
) from anon;
revoke all on function public.create_job_context_with_idempotency(
  uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean
) from authenticated;
grant execute on function public.create_job_context_with_idempotency(
  uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean
) to service_role;

comment on function public.activate_job_context(uuid, uuid) is
  'C4.2 backend-only activation RPC. Verifies id and user_id before mutation, serializes per user with hashtextextended(user_id::text, 0), and leaves no-context as a valid state.';

comment on function public.create_job_context_with_idempotency(
  uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean
) is
  'C4.2 backend-only idempotent create RPC. Reservation, job row creation, optional activation, and safe replay reference persistence happen in one transaction without storing raw JD in idempotency rows.';
