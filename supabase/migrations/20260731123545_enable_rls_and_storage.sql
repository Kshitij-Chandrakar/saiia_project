-- C1.3 RLS policies and private storage buckets for SAIIA cloud data.
-- FastAPI token verification, auth UI, and upload flows are intentionally deferred.

alter table public.profiles enable row level security;
alter table public.resumes enable row level security;
alter table public.resume_chunks enable row level security;
alter table public.job_contexts enable row level security;
alter table public.user_settings enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
on public.profiles
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own
on public.profiles
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own
on public.profiles
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists profiles_delete_own on public.profiles;
create policy profiles_delete_own
on public.profiles
for delete
to authenticated
using (user_id = auth.uid());

drop policy if exists resumes_select_own on public.resumes;
create policy resumes_select_own
on public.resumes
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists resumes_insert_own on public.resumes;
create policy resumes_insert_own
on public.resumes
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists resumes_update_own on public.resumes;
create policy resumes_update_own
on public.resumes
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists resumes_delete_own on public.resumes;
create policy resumes_delete_own
on public.resumes
for delete
to authenticated
using (user_id = auth.uid());

drop policy if exists resume_chunks_select_own on public.resume_chunks;
create policy resume_chunks_select_own
on public.resume_chunks
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists resume_chunks_insert_own on public.resume_chunks;
create policy resume_chunks_insert_own
on public.resume_chunks
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists resume_chunks_update_own on public.resume_chunks;
create policy resume_chunks_update_own
on public.resume_chunks
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists resume_chunks_delete_own on public.resume_chunks;
create policy resume_chunks_delete_own
on public.resume_chunks
for delete
to authenticated
using (user_id = auth.uid());

drop policy if exists job_contexts_select_own on public.job_contexts;
create policy job_contexts_select_own
on public.job_contexts
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists job_contexts_insert_own on public.job_contexts;
create policy job_contexts_insert_own
on public.job_contexts
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists job_contexts_update_own on public.job_contexts;
create policy job_contexts_update_own
on public.job_contexts
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists job_contexts_delete_own on public.job_contexts;
create policy job_contexts_delete_own
on public.job_contexts
for delete
to authenticated
using (user_id = auth.uid());

drop policy if exists user_settings_select_own on public.user_settings;
create policy user_settings_select_own
on public.user_settings
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists user_settings_insert_own on public.user_settings;
create policy user_settings_insert_own
on public.user_settings
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists user_settings_update_own on public.user_settings;
create policy user_settings_update_own
on public.user_settings
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists user_settings_delete_own on public.user_settings;
create policy user_settings_delete_own
on public.user_settings
for delete
to authenticated
using (user_id = auth.uid());

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  (
    'resumes',
    'resumes',
    false,
    10485760,
    array[
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain'
    ]
  ),
  (
    'exports',
    'exports',
    false,
    10485760,
    array[
      'application/json',
      'application/pdf',
      'text/csv',
      'text/markdown',
      'text/plain'
    ]
  )
on conflict (id) do update
set
  name = excluded.name,
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists saiia_storage_select_own on storage.objects;
create policy saiia_storage_select_own
on storage.objects
for select
to authenticated
using (
  bucket_id in ('resumes', 'exports')
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists saiia_storage_insert_own on storage.objects;
create policy saiia_storage_insert_own
on storage.objects
for insert
to authenticated
with check (
  bucket_id in ('resumes', 'exports')
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists saiia_storage_update_own on storage.objects;
create policy saiia_storage_update_own
on storage.objects
for update
to authenticated
using (
  bucket_id in ('resumes', 'exports')
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id in ('resumes', 'exports')
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists saiia_storage_delete_own on storage.objects;
create policy saiia_storage_delete_own
on storage.objects
for delete
to authenticated
using (
  bucket_id in ('resumes', 'exports')
  and (storage.foldername(name))[1] = auth.uid()::text
);

comment on policy saiia_storage_select_own on storage.objects is
  'C1.3: authenticated users can read only resumes/exports objects under their own top-level auth.uid() folder.';
