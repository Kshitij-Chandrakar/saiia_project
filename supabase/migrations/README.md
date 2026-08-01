# Supabase Migrations

Future cloud schema changes must be committed here as SQL migrations using:

```text
YYYYMMDDHHMMSS_descriptive_name.sql
```

C1.1 intentionally adds no schema migration because it only establishes
configuration, documentation, and migration conventions. Do not create tables
through the Supabase dashboard without adding an equivalent migration.

Current C1/C2.3 migrations:

- `20260731121714_create_base_cloud_schema.sql`
- `20260731123545_enable_rls_and_storage.sql`
- `20260801115446_grant_cloud_table_privileges.sql`

The C2.3 privilege migration fixed the live Supabase PostgREST table-privilege
blocker for authenticated profile bootstrap. C2.4 remains pending and not
started.
