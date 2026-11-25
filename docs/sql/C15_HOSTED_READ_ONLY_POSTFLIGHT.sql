-- Run in Saiia-dev SQL Editor. Read-only metadata/configuration; no customer rows.
begin transaction read only;
set local statement_timeout = '15s';

with expected_versions(version) as (values
 ('20261029010000'),('20261029020000'),('20261030010000'),('20261030020000'),
 ('20261030120000'),('20261030140000'),('20261031100000'),('20261031120000'),
 ('20261101010000'),('20261101020000'),('20261101030000'),('20261101040000'),
 ('20261101050000'),('20261102010000'),('20261102020000'),('20261102025000'),
 ('20261102030000'),('20261102040000'),('20261102050000'),('20261102060000'),
 ('20261102070000'),('20261102080000'),('20261103010000'),('20261103020000'),
 ('20261103030000'),('20261103040000'),('20261103050000'),('20261103060000'),
 ('20261103070000'),('20261103080000'),('20261103090000'),('20261103100000'),
 ('20261103110000'),('20261103120000'),('20261103130000'),('20261105090000')
), private_functions(signature,expected_owner) as (values
 ('public.privacy_auto_credentials_erase(uuid,uuid)','privacy_payload_owner'),
 ('public.privacy_revocation_verified(uuid,uuid,uuid)','privacy_revocation_observer_owner'),
 ('public.privacy_identity_call(text,jsonb)','privacy_identity_owner'),
 ('public.privacy_runtime_call(text,text,jsonb)','privacy_runtime_owner'),
 ('public.privacy_notice_event(text,jsonb)','privacy_runtime_owner'),
 ('public.privacy_pending_notices()','privacy_runtime_owner')
), private_owners as (
 select distinct expected_owner as name from private_functions
), callers(name) as (values ('anon'),('authenticated'),('service_role'),('usage_executor'))
select jsonb_pretty(jsonb_build_object(
 'database',current_database(), 'query_role',current_user,
 'server_version',current_setting('server_version'),
 'migrations',jsonb_build_object(
   'expected', (select count(*) from expected_versions),
   'applied', (select count(*) from expected_versions e join supabase_migrations.schema_migrations m using(version)),
   'missing', (select coalesce(jsonb_agg(e.version order by e.version),'[]'::jsonb)
     from expected_versions e where not exists(
       select 1 from supabase_migrations.schema_migrations m where m.version=e.version))),
 'activation',jsonb_build_object(
   'privacy_configuration_rows',(select count(*) from public.privacy_configuration),
   'privacy_enabled',(select enabled from public.privacy_configuration where singleton),
   'admin_configuration_rows',(select count(*) from administration.configuration),
   'admin_enabled',(select enabled from administration.configuration where singleton),
   'admin_bootstrap_consumed',(select bootstrap_consumed from administration.configuration where singleton),
   'restore_required',(select required from public.privacy_restore_state where singleton),
   'restore_ready',(select ready from public.privacy_restore_state where singleton)),
 'private_functions',(select jsonb_agg(jsonb_build_object(
   'function',f.signature,'present',p.oid is not null,
   'owner',pg_get_userbyid(p.proowner),
   'owner_correct',coalesce(pg_get_userbyid(p.proowner)=f.expected_owner,false),
   'security_definer',p.prosecdef,'settings',p.proconfig)
   order by f.signature) from private_functions f
   left join pg_proc p on p.oid=to_regprocedure(f.signature)),
 'ordinary_private_execute_grants',(select coalesce(jsonb_agg(jsonb_build_object(
   'role',c.name,'function',f.signature)),'[]'::jsonb)
   from private_functions f cross join callers c
   where has_function_privilege(c.name,to_regprocedure(f.signature),'EXECUTE')),
 'private_owner_roles',(select jsonb_agg(jsonb_build_object(
   'role',o.name,'present',r.oid is not null,'login',r.rolcanlogin,
   'superuser',r.rolsuper,'create_role',r.rolcreaterole,'bypass_rls',r.rolbypassrls,
   'schema_create',case when r.oid is not null then has_schema_privilege(r.oid,'public','CREATE') end))
   from private_owners o left join pg_roles r on r.rolname=o.name),
 'private_owner_active_memberships',(select coalesce(jsonb_agg(jsonb_build_object(
   'role',o.name,'member',pg_get_userbyid(m.member),
   'inherit',m.inherit_option,'set',m.set_option)),'[]'::jsonb)
   from private_owners o join pg_roles r on r.rolname=o.name
   join pg_auth_members m on m.roleid=r.oid where m.inherit_option or m.set_option),
 'bridge_public_role_access',(select coalesce(jsonb_agg(c.name),'[]'::jsonb)
   from callers c where has_schema_privilege(c.name,'c15_auth','USAGE')),
 'bridge_functions',(select coalesce(jsonb_agg(jsonb_build_object(
   'function',p.proname,'owner',pg_get_userbyid(p.proowner),
   'security_definer',p.prosecdef,'settings',p.proconfig)),'[]'::jsonb)
   from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='c15_auth'),
 'buckets',(select coalesce(jsonb_agg(jsonb_build_object(
   'id',id,'public',public,'file_size_limit',file_size_limit,
   'allowed_mime_types',allowed_mime_types)),'[]'::jsonb)
   from storage.buckets where id in ('exports','resumes')),
 'export_access_policy',(select coalesce(jsonb_agg(jsonb_build_object(
   'policy',policyname,'roles',roles,'command',cmd,'permissive',permissive,
   'using',qual,'check',with_check)),'[]'::jsonb)
   from pg_policies where schemaname='storage' and tablename='objects'
   and policyname='privacy_export_application_download'),
 'private_tables_without_rls',(select coalesce(jsonb_agg(n.nspname||'.'||c.relname),'[]'::jsonb)
   from pg_class c join pg_namespace n on n.oid=c.relnamespace
   where c.relkind in ('r','p') and not c.relrowsecurity
   and ((n.nspname='public' and left(c.relname,8)='privacy_') or n.nspname='administration'))
)) as postflight_report;
rollback;
