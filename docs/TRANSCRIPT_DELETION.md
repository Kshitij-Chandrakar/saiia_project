# Permanent website transcript deletion

Clear Transcript permanently deletes only the selected session's saved transcript entries. Session metadata, AI Notes and saved Ask AI messages remain. Those retained records can contain information derived from the deleted transcript; this operation does not erase those copies. Clear Chat remains temporary display-only clearing.

## Deployment order

1. Review and apply `supabase/migrations/20261011120000_add_permanent_transcript_deletion.sql` through the normal migration process in an isolated/staging database first. This migration has not been applied to production by this change.
2. Deploy the backend with `DELETE /api/interview-sessions/{session_id}/transcript-entries`.
3. Deploy the website. No Electron change or provider configuration is required.

The API derives user identity from verified authentication, checks session ownership, and invokes the service-role-only deletion RPC. No browser-provided user ID is used. The database repeats the ownership check under the same per-session advisory lock and row lock as transcript creation. No additional transcript deletion grant is given to authenticated or anonymous clients; existing RLS remains enabled and forced.

Deletion is allowed only for ended or abandoned sessions with a recorded end time at least five minutes ago. Active and recently ended sessions return a safe 409 conflict. The website disables clearing in that window and explains the restriction; reopening the viewer refreshes eligibility. Repeated successful deletion returns zero deleted rows and remains safe.

The new before-insert trigger prevents insertion after the existing late-write deadline, including transactions whose `now()` timestamp predates the deadline. It uses `clock_timestamp()` and the shared lock. Deletion does not update the parent session, notes, or chat. Existing write retries cannot recreate cleared entries because clearing is unavailable until all permitted writes have expired. PostgreSQL lock/statement timeouts bound deletion work; existing authentication and request protections are unchanged.

After confirmed server success, the website clears the transcript cache and invalidates previously started reads/downloads. Failure keeps displayed entries and offers retry. Future downloads, notes generation and Ask AI transcript reads use the authoritative saved rows. Existing supported notes/chat context remains available. Files already downloaded cannot be recalled by deleting server records.

## Isolated verification

Run backend tests from `backend`:

```powershell
python -m pytest tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py tests/test_supabase_migrations.py -q
```

Run a PostgreSQL-compatible WASM fixture without connecting to any live database:

```powershell
npm install --prefix tmp/transcript-delete-db @electric-sql/pglite --no-save --package-lock=false
node backend/tests/transcript_deletion.postgres.mjs
```

This checks the actual C7 migrations and new migration, ownership, RPC grants, grace restrictions, idempotent deletion, the real-time stale-write fence and retained data. It does not replace live Supabase staging verification or a multi-connection contention test. No production data should be used for destructive tests.
