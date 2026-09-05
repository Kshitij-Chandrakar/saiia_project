-- C10.6B local-only marketing unsubscribe token foundation.
-- Apply after 20260904170000_add_signup_consent_preferences.sql.
-- This migration is intentionally not applied to remote Supabase in C10.6B.

create table if not exists public.marketing_unsubscribe_tokens (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  recipient_email text not null,
  token_hash text not null,
  email_category text not null default 'marketing',
  created_at timestamptz not null default timezone('utc', now()),
  expires_at timestamptz not null,
  used_at timestamptz null,
  revoked_at timestamptz null,
  constraint marketing_unsubscribe_tokens_recipient_length_check check (
    char_length(recipient_email) between 3 and 254
  ),
  constraint marketing_unsubscribe_tokens_hash_check check (
    token_hash ~ '^[a-f0-9]{64}$'
  ),
  constraint marketing_unsubscribe_tokens_category_check check (
    email_category = 'marketing'
  ),
  constraint marketing_unsubscribe_tokens_expiry_check check (
    expires_at > created_at
  )
);

create unique index if not exists marketing_unsubscribe_tokens_hash_uidx
  on public.marketing_unsubscribe_tokens (token_hash);

create index if not exists marketing_unsubscribe_tokens_user_idx
  on public.marketing_unsubscribe_tokens (user_id, created_at desc);

alter table public.marketing_unsubscribe_tokens enable row level security;
alter table public.marketing_unsubscribe_tokens force row level security;

revoke all on table public.marketing_unsubscribe_tokens from public;
revoke all on table public.marketing_unsubscribe_tokens from anon;
revoke all on table public.marketing_unsubscribe_tokens from authenticated;
grant select, insert, update, delete on table public.marketing_unsubscribe_tokens to service_role;

create or replace function public.consume_marketing_unsubscribe_token(
  p_token_hash text
)
returns table (unsubscribed boolean)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_token_id uuid;
  v_user_id uuid;
begin
  if p_token_hash is null or p_token_hash !~ '^[a-f0-9]{64}$' then
    return query select false;
    return;
  end if;

  select t.id, t.user_id
  into v_token_id, v_user_id
  from public.marketing_unsubscribe_tokens as t
  where t.token_hash = p_token_hash
    and t.used_at is null
    and t.revoked_at is null
    and t.expires_at > timezone('utc', now())
  for update;

  if v_token_id is null then
    return query select false;
    return;
  end if;

  update public.user_settings as s
  set marketing_email_opt_in = false,
      marketing_email_opt_out_at = timezone('utc', now())
  where s.user_id = v_user_id;

  if not found then
    return query select false;
    return;
  end if;

  update public.marketing_unsubscribe_tokens as t
  set used_at = timezone('utc', now())
  where t.id = v_token_id
    and t.used_at is null
    and t.revoked_at is null;

  if not found then
    return query select false;
    return;
  end if;

  return query select true;
end;
$$;

revoke all on function public.consume_marketing_unsubscribe_token(text) from public;
revoke all on function public.consume_marketing_unsubscribe_token(text) from anon;
revoke all on function public.consume_marketing_unsubscribe_token(text) from authenticated;
grant execute on function public.consume_marketing_unsubscribe_token(text) to service_role;

comment on table public.marketing_unsubscribe_tokens is
  'C10.6B backend-only marketing opt-out tokens. Only SHA-256 token hashes are stored; raw tokens, URLs, prompts, transcript content, resume chunks, headers, and secrets are excluded.';
