-- Supported PostgreSQL column/RLS visibility for fixed private operations.
-- No managed-Auth trigger, ordinary-role grant, owner membership or BYPASSRLS.
begin;
create policy c15_runtime_auth_read on auth.users for select to privacy_runtime_owner using(true);
create policy c15_runtime_auth_lock on auth.users for update to privacy_runtime_owner using(true) with check(true);
create policy c15_identity_auth_read on auth.users for select to privacy_identity_owner using(true);
create policy c15_identity_auth_lock on auth.users for update to privacy_identity_owner using(true) with check(true);
create policy c15_identity_sessions_read on auth.sessions for select to privacy_identity_owner using(true);
create policy c15_identity_identities_read on auth.identities for select to privacy_identity_owner using(true);
create policy c15_identity_factors_read on auth.mfa_factors for select to privacy_identity_owner using(true);
create policy c15_revocation_sessions_read on auth.sessions for select to privacy_revocation_observer_owner using(true);
commit;
