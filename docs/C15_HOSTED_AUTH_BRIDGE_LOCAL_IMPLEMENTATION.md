# Hosted Auth bridge compatibility

20 November 2026. Local changes only, based on main `204de23` in isolated
`fix/c15-hosted-auth-bridge`. Existing development edits remain in their original worktree.
No hosted SQL, migrations, grants, mail or provider requests executed.

## Change

Hosted postgres has underlying Auth SELECT/UPDATE privileges but no managed-table
ownership. Custom NOLOGIN function owners must not rely on grantable Auth schema
usage or install managed-table RLS policies.

Added `20261102025000_privacy_auth_bridge.sql`, before notification SQL compilation:
unexposed `c15_auth` schema, fixed postgres-owned SECURITY DEFINER functions with
`search_path=pg_catalog`. They expose only one subject's id/email/confirmation/deletion
fields, one subject row lock, a session-existence boolean or the users relation OID.
EXECUTE is granted only to the relevant existing private function owners. Ordinary
customers, service_role, admin_executor and content executors cannot call them directly.
No caller SQL, predicates, tables or column lists are accepted.

The narrow existing identity-absence boolean and contact-availability boolean retain
postgres ownership. Large runtime and identity executors retain their restricted owners.
Identity mutation remains the existing supported Auth API. Request, subject, lease,
expiry and task-state checks remain in the enclosing fixed operations.

Updated observer, identity, runtime and notification migrations to use the bridges.
The former Auth visibility migration now checks the bridge dependency rather than
creating Auth policies. The compiler preserves caller operation IDs and performs the
same fixed SQL lowering; immutable installed operation rows are not rewritten.

## Migration history restriction

This patch changes five previously pending migration bodies and adds one ordered
migration: the owner's reported pending set becomes 36 files. It is suitable only
for a target where these C15 versions remain unapplied, as reported by the dry run.
Never repair migration history or replay changed versions on an already migrated
database. Such environments require a separately reviewed forward upgrade strategy.
Do not copy only the new bridge SQL into a hosted project and push old sources.

## Local verification

- Actual local GoTrue/PostgreSQL/Storage/PostgREST/Mailpit authority rehearsal:
  25 scenario groups passed, including bridge ACLs and direct Auth schema denial.
- Normal main/gRPC/startup/worker rehearsal on actual engines passed. Personal cleanup,
  refresh revocation and identity cleanup succeeded; billing review remained pending.
  Worker restart/checkpoint wiring passed. No browser run was requested for SQL-only changes.
- Focused admin regressions: 17 passed. Python compile and whitespace checks passed.
- Initial normal-worker run exposed a remaining direct notification Auth join; fixed
  it and retained the failed evidence separately. Final normal run passed.
- Evidence: `docs/evidence/c15-hosted-auth-authority-final-20261120/` and
  `docs/evidence/c15-hosted-auth-main-final-20261120/`. These remain local/untracked.

## Remaining hosted gates

Local engines do not reproduce every hosted owner/RLS/platform restriction. Verify the
actual migration identity can assign postgres function ownership and that postgres reads
see the intended Auth rows under hosted RLS. Separately verify `FOR NO KEY UPDATE`
under the actual hosted function-owner identity and RLS using an explicitly authorized
synthetic Auth account, with a short lock timeout and transaction rollback. Require
exactly that account ID from `c15_auth.lock_user`; zero rows, timeout or permission
denial fails the gate. SELECT success alone is insufficient: the lock also requires
UPDATE privilege. Execute this gate only after separately authorized bridge installation;
this document does not authorize a remote lock, role change or migration execution.
Confirm c15_auth is not exposed by the Data
API, review default grants, migration history, backups/recovery and export size limits.
Supabase guidance: https://supabase.com/kb/troubleshooting/permission-errors-when-granting-custom-roles-access-to-the-auth-schema-9e32e7

Production flags remain disabled. No commit, push or remote migration is part of this work.
