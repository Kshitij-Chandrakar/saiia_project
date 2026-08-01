# Supabase Migrations

Cloud schema changes must be committed here as SQL migrations using:

```text
YYYYMMDDHHMMSS_descriptive_name.sql
```

Current migrations:

- `20260731121714_create_base_cloud_schema.sql`: creates the C1.2 user-owned
  cloud tables for profiles, resumes, resume chunks, job contexts, and user
  settings.
- `20260731123545_enable_rls_and_storage.sql`: enables RLS, adds own-row
  policies, creates private `resumes` and `exports` buckets, and adds storage
  ownership policies.
- `20260801115446_grant_cloud_table_privileges.sql`: grants the required
  `authenticated` and backend-only `service_role` table privileges for
  PostgREST while leaving RLS enabled; this fixed the C2.3 live profile
  bootstrap privilege blocker.

Do not create tables through the Supabase dashboard without adding an
equivalent migration. These committed migrations are the source of truth. C2.4
remains pending and not started.
