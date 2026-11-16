-- A forged GUC alone grants nothing: every deletion checks the live DB lease,
-- subject, accepted scope and per-session membership again under RLS.
create function public.privacy_runtime_scope(p_job uuid,p_lease uuid) returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user not in ('privacy_content_executor','privacy_restore_executor') or current_setting('role',true)<>'none' then raise exception 'scope denied' using errcode='42501'; end if;
 if not exists(select 1 from public.privacy_content_jobs where id=p_job and lease_id=p_lease and state='running' and lease_until>clock_timestamp()) then raise exception 'stale scope' using errcode='42501'; end if;
 perform set_config('c15.runtime.job',p_job::text,true);perform set_config('c15.runtime.lease',p_lease::text,true);
end $$;
create function public.privacy_runtime_allows(p_account uuid,p_session uuid) returns boolean language sql security definer set search_path=pg_catalog as $$
 select (session_user='privacy_restore_executor' and exists(select 1 from public.privacy_restore_state where required and not ready) and (exists(select 1 from public.privacy_restored_subjects where account_id=p_account) or (p_session is not null and exists(select 1 from public.privacy_restored_sessions where account_id=p_account and session_id=p_session)))) or exists(select 1 from public.privacy_content_jobs j where j.id=nullif(current_setting('c15.runtime.job',true),'')::uuid and j.lease_id=nullif(current_setting('c15.runtime.lease',true),'')::uuid and j.account_id=p_account and j.state='running' and j.lease_until>clock_timestamp() and ((j.kind='account' and exists(select 1 from public.privacy_deletion_requests r where r.request_id=j.id and r.account_id=p_account and r.state='accepted_restricted')) or (j.kind='session' and j.resource_id=p_session) or (j.kind='history' and exists(select 1 from public.privacy_erased_sessions e where e.job_id=j.id and e.account_id=p_account and e.session_id=p_session))))
$$;
alter function public.privacy_runtime_scope(uuid,uuid) owner to privacy_runtime_owner;
alter function public.privacy_runtime_allows(uuid,uuid) owner to privacy_runtime_owner;
revoke all on function public.privacy_runtime_scope(uuid,uuid),public.privacy_runtime_allows(uuid,uuid) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.privacy_runtime_scope(uuid,uuid) to privacy_content_executor,privacy_restore_executor;
