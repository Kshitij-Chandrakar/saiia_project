-- C11.3A: caller-only, read-only membership probe. No mutation grants/subjects.
begin;
create function public.subscription_admin_self_probe() returns jsonb
language plpgsql stable security definer set search_path=pg_catalog as $$
declare subject uuid; r bigint;
begin
  if session_user <> 'authenticator' or current_setting('role',true) <> 'authenticated' then
    raise exception 'identity gateway denied' using errcode='42501';
  end if;
  subject:=auth.uid();
  if subject is null then raise exception 'identity required' using errcode='42501'; end if;
  select revision into r from public.subscription_admin_permissions
    where subject_id=subject and permission='subscriptions.manage' and active;
  return jsonb_build_object('contract_version','admin.access.v1','subject_id',subject,
    'permissions',case when r is null then '[]'::jsonb else '["subscriptions.manage"]'::jsonb end,
    'permission_revision',r::text);
end;
$$;
revoke all on function public.subscription_admin_self_probe() from public,anon,authenticated,service_role;
-- Deliberate narrow access: only caller's safe permission facts, no actor input.
grant execute on function public.subscription_admin_self_probe() to authenticated;
commit;
