-- C2.3 support: grant PostgREST table privileges for SAIIA cloud tables.
--
-- RLS remains enabled by the C1.3 migration. The authenticated role receives
-- table privileges only because own-row RLS policies restrict rows by
-- auth.uid(). The service_role grant is for backend-only trusted operations;
-- backend code must still derive user_id from a verified Supabase JWT.

grant usage on schema public to authenticated, service_role;

grant select, insert, update, delete
on table
  public.profiles,
  public.user_settings,
  public.resumes,
  public.resume_chunks,
  public.job_contexts
to authenticated, service_role;
