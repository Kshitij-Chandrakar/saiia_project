-- Optional restricted authoritative observation. No Auth writes or activation.
begin;
create role privacy_revocation_observer nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
create role privacy_revocation_observer_owner nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
grant usage on schema public,auth to privacy_revocation_observer_owner;
grant select(request_id,account_id,state,accepted_at) on public.privacy_deletion_requests to privacy_revocation_observer_owner;
grant select(request_id,kind,state,lease_id,lease_until) on public.privacy_followup_tasks to privacy_revocation_observer_owner;
grant select(user_id) on auth.sessions to privacy_revocation_observer_owner;
create policy revocation_observer_requests on public.privacy_deletion_requests for select to privacy_revocation_observer_owner using(true);
create policy revocation_observer_tasks on public.privacy_followup_tasks for select to privacy_revocation_observer_owner using(true);
create function public.privacy_revocation_verified(p_request uuid,p_lease uuid,p_account uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'privacy_revocation_observer' or current_setting('role',true)<>'none' then raise exception 'observer denied' using errcode='42501'; end if;
 if not exists(select 1 from public.privacy_followup_tasks t join public.privacy_deletion_requests r using(request_id) where t.request_id=p_request and r.account_id=p_account and r.state='accepted_restricted' and r.accepted_at is not null and t.kind='revoke_sessions' and t.state='running' and t.lease_id=p_lease and t.lease_until>clock_timestamp()) then raise exception 'stale observer scope' using errcode='42501'; end if;
 return not exists(select 1 from auth.sessions where user_id=p_account);
end $$;
alter function public.privacy_revocation_verified(uuid,uuid,uuid) owner to privacy_revocation_observer_owner;
revoke all on function public.privacy_revocation_verified(uuid,uuid,uuid) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_revocation_verified(uuid,uuid,uuid) to privacy_revocation_observer;
commit;
