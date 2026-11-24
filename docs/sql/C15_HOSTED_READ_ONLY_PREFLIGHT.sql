-- Run in the intended project's SQL editor. Catalog metadata only; no customer rows.
begin transaction read only;
select current_database(), current_user, version();
-- Required to choose the supported private-function bridge; never return Auth rows.
select has_schema_privilege(current_user,'auth','USAGE') as auth_usage,
 has_table_privilege(current_user,'auth.users','SELECT') as users_select,
 has_table_privilege(current_user,'auth.users','UPDATE') as users_update,
 has_table_privilege(current_user,'auth.sessions','SELECT') as sessions_select,
 has_table_privilege(current_user,'auth.identities','SELECT') as identities_select,
 has_table_privilege(current_user,'auth.mfa_factors','SELECT') as factors_select;
select version from supabase_migrations.schema_migrations order by version;
select n.nspname, c.relname, pg_get_userbyid(c.relowner) as owner,
 c.relrowsecurity, c.relforcerowsecurity,
 pg_has_role(current_user,c.relowner,'USAGE') as owner_authority
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where (n.nspname='auth' and c.relname in ('users','sessions','identities','mfa_factors'))
 or (n.nspname='storage' and c.relname in ('objects','buckets'));
select rolname, rolcanlogin, rolsuper, rolcreaterole, rolbypassrls, rolinherit
from pg_roles where rolname in ('postgres','supabase_auth_admin','supabase_storage_admin',
 'anon','authenticated','service_role','usage_executor','usage_binding_executor','usage_reconciler')
 or rolname like 'privacy_%' or rolname like 'admin_%';
select pg_get_userbyid(roleid) as granted_role, pg_get_userbyid(member) as member,
 admin_option from pg_auth_members
where pg_get_userbyid(roleid) ~ '^(privacy_|admin_|usage_)'
 or pg_get_userbyid(member) ~ '^(privacy_|admin_|usage_)';
select schemaname,tablename,policyname,roles,cmd,permissive,qual,with_check
from pg_policies where schemaname in ('auth','storage') order by schemaname,tablename,policyname;
select id,public,file_size_limit,allowed_mime_types from storage.buckets
where id in ('exports','resumes');
select n.nspname,p.proname,pg_get_userbyid(p.proowner) as owner,p.prosecdef,p.proconfig
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname in ('public','administration')
and (p.proname like 'privacy_%' or p.proname like 'administration_%');
rollback;
