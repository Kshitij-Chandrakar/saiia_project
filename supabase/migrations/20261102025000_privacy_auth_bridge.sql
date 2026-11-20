-- Fixed postgres-owned bridges; never alter managed Auth policies or ownership.
begin;
create schema c15_auth authorization postgres;
revoke all on schema c15_auth from public,anon,authenticated,service_role;
grant usage on schema c15_auth to privacy_runtime_owner,privacy_identity_owner,privacy_revocation_observer_owner;
create function c15_auth.user_fields(p_account uuid)
returns table(id uuid,email varchar,email_confirmed_at timestamptz,deleted_at timestamptz)
language sql stable security definer set search_path=pg_catalog as $$
 select u.id,u.email,u.email_confirmed_at,u.deleted_at from auth.users u where u.id=p_account
$$;
create function c15_auth.lock_user(p_account uuid) returns table(id uuid)
language sql volatile security definer set search_path=pg_catalog as $$
 select u.id from auth.users u where u.id=p_account for no key update
$$;
create function c15_auth.has_sessions(p_account uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from auth.sessions where user_id=p_account)
$$;
create function c15_auth.users_oid() returns oid
language sql stable security definer set search_path=pg_catalog as $$ select 'auth.users'::regclass::oid $$;
alter function c15_auth.user_fields(uuid) owner to postgres;
alter function c15_auth.lock_user(uuid) owner to postgres;
alter function c15_auth.has_sessions(uuid) owner to postgres;
alter function c15_auth.users_oid() owner to postgres;
revoke all on all functions in schema c15_auth from public,anon,authenticated,service_role;
grant execute on function c15_auth.user_fields(uuid),c15_auth.users_oid() to privacy_runtime_owner;
grant execute on function c15_auth.lock_user(uuid) to privacy_runtime_owner,privacy_identity_owner;
grant execute on function c15_auth.has_sessions(uuid) to privacy_revocation_observer_owner;
commit;
