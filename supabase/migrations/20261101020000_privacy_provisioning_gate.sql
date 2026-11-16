-- Additive/default unavailable: no LOGIN, key or public provisioning route.
begin;
create role privacy_provisioning_executor nologin nosuperuser nocreatedb nocreaterole noinherit;
create function public.privacy_provisioning_check(p_email text) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare normalized text; begin
 if session_user<>'privacy_provisioning_executor' or current_setting('role',true)<>'none' then
  raise exception 'provisioning denied' using errcode='42501';
 end if;
 normalized:=public.privacy_normal_email(p_email);
 perform pg_advisory_xact_lock(hashtextextended(normalized,15715));
 return not public.privacy_email_denied(normalized);
end $$;
revoke all on function public.privacy_provisioning_check(text) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.privacy_provisioning_check(text) to privacy_provisioning_executor;
commit;
