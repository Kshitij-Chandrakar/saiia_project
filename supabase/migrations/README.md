# Supabase Migrations

Future cloud schema changes must be committed here as SQL migrations using:

```text
YYYYMMDDHHMMSS_descriptive_name.sql
```

C1.1 intentionally adds no schema migration because it only establishes
configuration, documentation, and migration conventions. Do not create tables
through the Supabase dashboard without adding an equivalent migration.
