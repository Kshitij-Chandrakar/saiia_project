-- Saiia-dev SQL Editor. Metadata/counts only; never returns keys or customer rows.
begin transaction read only;
set local statement_timeout = '15s';
with required_roles(name) as (values
 ('usage_executor'),('privacy_content_executor'),('privacy_restore_executor'),
 ('privacy_cleanup_executor'),('privacy_identity_executor'),
 ('privacy_revocation_observer'),('privacy_retention_executor'),
 ('admin_executor'),('admin_bootstrap_executor'),('admin_retention_executor'),
 ('admin_dispatch_executor'),('admin_restore_executor')
)
select jsonb_pretty(jsonb_build_object(
 'runtime_roles',(select jsonb_agg(jsonb_build_object(
   'role',e.name,'present',r.oid is not null,'login',r.rolcanlogin,
   'superuser',r.rolsuper,'create_role',r.rolcreaterole,
   'bypass_rls',r.rolbypassrls,'inherit',r.rolinherit) order by e.name)
   from required_roles e left join pg_roles r on r.rolname=e.name),
 'runtime_memberships',(select coalesce(jsonb_agg(jsonb_build_object(
   'granted_role',pg_get_userbyid(m.roleid),'member',pg_get_userbyid(m.member),
   'admin',m.admin_option,'inherit',m.inherit_option,'set',m.set_option)),'[]'::jsonb)
   from pg_auth_members m join required_roles e on e.name=pg_get_userbyid(m.roleid)),
 'active_suppression_key_count',(select count(*) from public.privacy_matching_keys where current_key),
 'privacy_enabled',(select enabled from public.privacy_configuration where singleton),
 'admin_enabled',(select enabled from administration.configuration where singleton),
 'admin_bootstrap_consumed',(select bootstrap_consumed from administration.configuration where singleton),
 'admin_bootstrap_subject_bound',(select bootstrap_subject is not null from administration.configuration where singleton),
 'restore_required',(select required from public.privacy_restore_state where singleton),
 'restore_ready',(select ready from public.privacy_restore_state where singleton)
)) as runtime_readiness_report;
rollback;
