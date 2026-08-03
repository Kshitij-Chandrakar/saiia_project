-- C3.2 resume lifecycle markers and direct-write hardening.
--
-- Browser clients must not mutate resume lifecycle state, chunks, profile
-- fields, or resume storage objects directly. C3 backend routes use verified
-- Supabase JWT identity plus backend-only service-role operations.

alter table public.resumes
  add column if not exists status text,
  add column if not exists is_active boolean,
  add column if not exists confirmed_at timestamptz,
  add column if not exists extraction_attempt integer,
  add column if not exists confirmed_profile jsonb,
  add column if not exists active_chunk_generation uuid,
  add column if not exists failure_code text,
  add column if not exists failure_message text,
  add column if not exists failed_at timestamptz,
  add column if not exists last_error_at timestamptz;

update public.resumes
set
  status = coalesce(status, 'uploaded'),
  is_active = coalesce(is_active, false),
  extraction_attempt = coalesce(extraction_attempt, 0),
  confirmed_profile = coalesce(confirmed_profile, '{}'::jsonb);

alter table public.resumes
  alter column status set default 'uploaded',
  alter column status set not null,
  alter column is_active set default false,
  alter column is_active set not null,
  alter column extraction_attempt set default 0,
  alter column extraction_attempt set not null,
  alter column confirmed_profile set default '{}'::jsonb,
  alter column confirmed_profile set not null;

alter table public.resumes
  drop constraint if exists resumes_status_check;

alter table public.resumes
  add constraint resumes_status_check
  check (
    status in (
      'uploaded',
      'extracting',
      'needs_review',
      'indexing',
      'ready',
      'failed',
      'timeout',
      'cancelled',
      'deleted'
    )
  );

alter table public.resumes
  drop constraint if exists resumes_active_ready_check;

alter table public.resumes
  add constraint resumes_active_ready_check
  check (is_active = false or status = 'ready');

drop index if exists public.resumes_one_active_per_user_idx;
create unique index resumes_one_active_per_user_idx
  on public.resumes (user_id)
  where is_active = true;

comment on column public.resumes.status is
  'C3.2 top-level cloud resume lifecycle status. Parser/extraction/index diagnostic statuses remain separate.';

comment on column public.resumes.confirmed_profile is
  'C3.2 server-owned reviewed profile snapshot. POST /confirm writes here only; profiles updates happen later during indexed activation.';

comment on column public.resumes.active_chunk_generation is
  'C3 placeholder for later atomic chunk generation activation. C3.2 does not build cloud RAG indexes.';

revoke insert, update, delete on table
  public.profiles,
  public.resumes,
  public.resume_chunks
from authenticated;

grant select on table
  public.profiles,
  public.resumes,
  public.resume_chunks
to authenticated;

grant select, insert, update, delete on table
  public.profiles,
  public.resumes,
  public.resume_chunks
to service_role;

drop policy if exists profiles_insert_own on public.profiles;
drop policy if exists profiles_update_own on public.profiles;
drop policy if exists profiles_delete_own on public.profiles;

drop policy if exists resumes_insert_own on public.resumes;
drop policy if exists resumes_update_own on public.resumes;
drop policy if exists resumes_delete_own on public.resumes;

drop policy if exists resume_chunks_insert_own on public.resume_chunks;
drop policy if exists resume_chunks_update_own on public.resume_chunks;
drop policy if exists resume_chunks_delete_own on public.resume_chunks;

drop policy if exists saiia_storage_insert_own on storage.objects;
drop policy if exists saiia_storage_update_own on storage.objects;
drop policy if exists saiia_storage_delete_own on storage.objects;

drop policy if exists saiia_exports_storage_insert_own on storage.objects;
drop policy if exists saiia_exports_storage_update_own on storage.objects;
drop policy if exists saiia_exports_storage_delete_own on storage.objects;

create policy saiia_exports_storage_insert_own
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'exports'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy saiia_exports_storage_update_own
on storage.objects
for update
to authenticated
using (
  bucket_id = 'exports'
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id = 'exports'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy saiia_exports_storage_delete_own
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'exports'
  and (storage.foldername(name))[1] = auth.uid()::text
);

comment on policy saiia_storage_select_own on storage.objects is
  'C3.2: authenticated users can read only resumes/exports objects under their own top-level auth.uid() folder; direct resume bucket mutation is backend-only.';

comment on policy saiia_exports_storage_insert_own on storage.objects is
  'C3.2: direct authenticated storage mutation remains available only for private exports, not resume uploads.';
