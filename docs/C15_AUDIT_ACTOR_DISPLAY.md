# Audit actor display

5 November 2026. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`. Existing work and historical audit rows preserved.

## Change

Audit history has six aligned columns: Time (UTC), Performed by, Action, Role at action, Outcome and Reason. Performed by shows the actor's current Auth email and the previously projected immutable account reference underneath. Role remains the role recorded when the action occurred. Missing email/actor references are explicitly unavailable; no identity is inferred from a role.

Email is resolved at read time, not copied into immutable audit history. It can change or become unavailable after identity cleanup. The screen states this limitation. Existing audit-reference retention and cleanup remain unchanged.

## Files

- `supabase/migrations/20261105090000_admin_audit_actor_email.sql`: fixed, bounded audit projection extension inside existing `public.administration_call`. Preserves its Super-admin-only authorization, owner, search path and grants. No new table, grant, audit mutation or lookup endpoint. Applied only to the running owned disposable PostgreSQL container `c15-actual-bbe61d2e94-db`; nothing remote.
- `frontend/src/auth/AdminAuditTable.jsx`: explicit actor cell, readable UTC dates and role labels.
- `frontend/src/auth/AdminConsole.jsx`: audit-only table wiring; other sections retain their existing tables.
- `frontend/src/auth/admin-console.css`: scoped widths, padding, wrapping and secondary ID styling. Narrow viewports scroll inside the labelled, keyboard-focusable table region.
- `frontend/tests/c15-admin/audit-actor.run.mjs`: actual local API/browser role checks and isolated missing-identity response fixture.

The migration extends the existing projection in `20261102050000_admin_authority.sql:120`, which already returns `actor_ref` from `administration.audit_references`. It does not store historical emails or rewrite accepted events. Standard local startup discovers ordered SQL files, so a future disposable reset includes it.

## Verification

Evidence: `docs/evidence/c15-audit-actor-20261105/`.

- Five browser scenario groups passed: actual Super admin identity projection at 1440×900, 1366×768 and 390×844; explicit missing-email/ID handling in a response-only fixture; actual Admin API 404 and no audit identity display.
- Native connection as `admin_executor`: Super admin fixed RPC returns actor email; Admin fixed RPC returns not_found. Direct SELECT on `auth.users`, `administration.audit` and `administration.audit_references` remains denied. These checks use the intended login principal, not database-owner execution as permission evidence.
- Scoped ESLint and full Vite build passed (`envFile:false`, `write:false`). Desktop screenshot visually inspected; no overlapping cells or page-wide horizontal overflow. Existing local services remain running.
- No provider calls, hosted migrations, permissions grants, commits or pushes. No unrelated acceptance repeated. Chromium checks are not physical-device or cross-browser certification.

URL: http://127.0.0.1:5400/auth/admin?view=audit
