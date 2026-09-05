-- C10.6A local-only signup consent and marketing preference foundation.
-- This migration is intentionally not applied to remote Supabase in C10.6A.

alter table public.user_settings
  add column if not exists terms_accepted boolean not null default false,
  add column if not exists terms_accepted_at timestamptz null,
  add column if not exists privacy_accepted boolean not null default false,
  add column if not exists privacy_accepted_at timestamptz null,
  add column if not exists marketing_email_opt_in boolean not null default false,
  add column if not exists marketing_email_opt_in_at timestamptz null,
  add column if not exists marketing_email_opt_out_at timestamptz null,
  add column if not exists consent_source text not null default 'profile_bootstrap',
  add column if not exists consent_version text null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_settings_consent_source_check'
      and conrelid = 'public.user_settings'::regclass
  ) then
    alter table public.user_settings
      add constraint user_settings_consent_source_check
      check (consent_source in ('signup', 'profile_bootstrap'));
  end if;
end
$$;

comment on column public.user_settings.terms_accepted is
  'C10.6A server-recorded Terms acceptance state.';
comment on column public.user_settings.privacy_accepted is
  'C10.6A server-recorded Privacy Policy acceptance state.';
comment on column public.user_settings.marketing_email_opt_in is
  'C10.6A explicit marketing opt-in; defaults to false and does not affect transactional email.';
