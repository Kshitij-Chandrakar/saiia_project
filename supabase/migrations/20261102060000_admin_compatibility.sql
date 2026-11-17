-- Single-authority cutover when enabled. No existing subject is promoted.
begin;
create function administration.permission(p_subject uuid,p_permission text) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare m administration.memberships;
begin
 if not (select cutover or enabled from administration.configuration where singleton) then
  return exists(select 1 from public.subscription_admin_permissions where subject_id=p_subject and permission=p_permission and active);
 end if;
 perform 1 from administration.configuration where singleton for share;
 if not (select enabled from administration.configuration where singleton) then return false; end if;
 m:=administration.member(p_subject);
 -- Legacy billing mutations are not blanket-granted by either product role.
 return m.subject is not null and (p_permission='billing.read' or (p_permission='subscriptions.manage' and m.role='super_admin'));
end$$;
revoke all on function administration.permission(uuid,text) from public,anon,authenticated,service_role,admin_executor;
create or replace function public.catalog_locked_actor() returns public.subscription_admin_permissions
language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; subject uuid; m administration.memberships;
begin
 if session_user='authenticator' and current_setting('role',true)='authenticated' then subject:=auth.uid();
 elsif session_user='catalog_draft_executor' and current_setting('role',true)='none' then subject:=nullif(current_setting('catalog.draft_actor',true),'')::uuid;
 else raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton for share;
 if (select cutover or enabled from administration.configuration where singleton) then
  if not (select enabled from administration.configuration where singleton) then raise exception 'denied' using errcode='42501'; end if;
  m:=administration.member(subject);
  if m.subject is null or m.role<>'super_admin' then raise exception 'denied' using errcode='42501'; end if;
  g.subject_id:=m.subject; g.permission:='subscriptions.manage'; g.revision:=m.revision;
  g.active:=true; g.approved_by:=m.subject; g.reason:='membership';
 else
  select * into g from public.subscription_admin_permissions where subject_id=subject and permission='subscriptions.manage' and active for share;
  if not found then raise exception 'denied' using errcode='42501'; end if;
 end if;
 return g;
end$$;
create or replace function public.subscription_admin_self_probe() returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare r bigint; m administration.memberships;
begin
 if session_user<>'authenticator' or current_setting('role',true)<>'authenticated' or auth.uid() is null then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton for share;
 if (select cutover or enabled from administration.configuration where singleton) then
  m:=administration.member(auth.uid());
  if m.subject is not null and m.role='super_admin' and (select enabled from administration.configuration where singleton) then r:=m.revision; end if;
 else
  select revision into r from public.subscription_admin_permissions where subject_id=auth.uid() and permission='subscriptions.manage' and active;
 end if;
 return jsonb_build_object('contract_version','admin.access.v1','subject_id',auth.uid(),
  'permissions',case when r is null then '[]'::jsonb else '["subscriptions.manage"]'::jsonb end,'permission_revision',r::text);
end$$;
-- Exact reviewed legacy function substitutions, not caller-supplied SQL.
do $$declare definition text; old_check text; begin
 select pg_get_functiondef('public.billing_admin_call(uuid,text,uuid,jsonb)'::regprocedure) into definition;
 old_check:='exists(select 1 from public.subscription_admin_permissions where subject_id=p_actor and active and permission=(case when p_action in (''inspect'',''access'') then ''billing.read'' else ''billing.manage'' end))';
 if position(old_check in definition)=0 then raise exception 'billing compatibility source mismatch'; end if;
 definition:=replace(definition,old_check,'administration.permission(p_actor,(case when p_action in (''inspect'',''access'') then ''billing.read'' else ''billing.manage'' end))');
 definition:=replace(definition,'exists(select 1 from public.subscription_admin_permissions where subject_id=p_actor and active and permission=''billing.manage'')','administration.permission(p_actor,''billing.manage'')');
 definition:=replace(definition,'return snapshot||jsonb_build_object','return (case when (select enabled from administration.configuration where singleton) then snapshot - ''commands'' else snapshot end)||jsonb_build_object');
 -- Staff accounts are not ordinary customer support targets, even when inactive.
 definition:=replace(definition,'if p_doc ? ''operation_id'' then','if (select enabled from administration.configuration where singleton) and exists(select 1 from administration.memberships where subject=p_account) then return jsonb_build_object(''error'',''denied''); end if; if p_doc ? ''operation_id'' then');
 execute definition;
 select pg_get_functiondef('public.billing_admin_work(uuid,text)'::regprocedure) into definition;
 old_check:='exists(select 1 from public.subscription_admin_permissions where subject_id=cmd.actor and permission=''billing.manage'' and active)';
 if position(old_check in definition)=0 then raise exception 'billing worker compatibility source mismatch'; end if;
 execute replace(definition,old_check,'administration.permission(cmd.actor,''billing.manage'')');
end$$;
commit;
