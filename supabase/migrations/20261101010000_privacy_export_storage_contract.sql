-- Local C15 candidate. ZIP archives remain private; no feature activation.
begin;
update storage.buckets set allowed_mime_types=array_append(allowed_mime_types,'application/zip')
where id='exports' and public=false and allowed_mime_types is not null
and not ('application/zip'=any(allowed_mime_types));

-- Customer downloads must pass the application capability/restriction/expiry
-- checks. Otherwise direct Storage reads/signing bypass the 24h deadline while
-- physical cleanup retries. Bind to durable job identity, not just an object
-- manifest that may already have been cleared before a late worker put.
create function public.privacy_export_object_accessible(p_bucket text,p_name text)
returns boolean language sql stable security definer set search_path=pg_catalog as $$
 select case when p_bucket<>'exports' then true
 when auth.uid() is null or split_part(p_name,'/',1)<>auth.uid()::text then false
 else not exists(select 1 from public.privacy_content_jobs j
   where j.kind='export' and j.account_id=auth.uid()
   and split_part(p_name,'/',2)=j.id::text) end
$$;
revoke all on function public.privacy_export_object_accessible(text,text)
from public,anon,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_export_object_accessible(text,text) to authenticated;
create policy privacy_export_application_download on storage.objects
as restrictive for all to authenticated
using(public.privacy_export_object_accessible(bucket_id,name))
with check(public.privacy_export_object_accessible(bucket_id,name));
commit;
