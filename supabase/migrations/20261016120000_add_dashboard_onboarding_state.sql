-- Local review only: do not apply without deployment approval.
-- Match the explicit transaction convention used by recent data migrations.
begin;

alter table public.user_settings
  add column onboarding_current_step smallint not null default 1,
  add column onboarding_completed_at timestamptz,
  add constraint user_settings_onboarding_current_step_range
    check (onboarding_current_step between 1 and 5);

-- auth.users is authoritative: profile/settings bootstrap may not have run.
-- Eligibility cutoff is the auth.users snapshot visible to this statement.
-- Pause account creation during rollout if the cutoff must equal deployment
-- completion; a concurrent uncommitted signup is not visible to this snapshot.
insert into public.user_settings (
  user_id,
  onboarding_current_step,
  onboarding_completed_at
)
select u.id, 1, now()
from auth.users as u
on conflict (user_id) do update
set onboarding_completed_at = coalesce(
  public.user_settings.onboarding_completed_at,
  excluded.onboarding_completed_at
)
where public.user_settings.onboarding_completed_at is null;

-- Future bootstrap inserts specify only user_id: defaults remain step 1 / NULL.
-- Do not repeat this backfill after rollout: it intentionally completes every
-- account visible at the eligibility cutoff, not just accounts with settings.
commit;
