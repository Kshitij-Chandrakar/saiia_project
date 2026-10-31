-- Additive draft version acceptance only. No permissions, publication or seeds.
begin;
do $$ declare item record; begin
 for item in select conname from pg_constraint
 where conrelid='public.catalog_drafts'::regclass and contype='c'
 and (pg_get_constraintdef(oid) like '%contract_version%' or pg_get_constraintdef(oid) like '%registry_version%') loop
 execute format('alter table public.catalog_drafts drop constraint %I',item.conname);
 end loop;
end $$;
alter table public.catalog_drafts add constraint catalog_document_version_pair check (
 (coalesce(document->>'contract_version',''),coalesce(document->>'registry_version',''))
 in (('catalog.v1','catalog.features.v1'),('catalog.v2','catalog.features.v2')));
commit;
