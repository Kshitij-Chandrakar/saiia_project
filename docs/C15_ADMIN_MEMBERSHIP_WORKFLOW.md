# Administrators: simpler access workflow

6 November 2026. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Focused frontend change; existing dirty work preserved.

## User workflow

- The administrator list comes first, with readable roles/status, row-level Change access and revision under Record details.
- Add administrator opens one guided dialog: find an existing user by exact email or Account ID, select the returned account, choose access/status/reason, review, then separately confirm. No manual UUID copying is necessary for this path.
- The chosen account is displayed throughout review. Unknown accounts cannot advance. Deletion-restricted lookup results cannot be selected for a grant. Backend checks remain authoritative.
- Admin and Super admin capabilities are explained beside the list and inside the dialog. Suspended/revoked access is explained separately from account deletion and billing.
- Successor transfer is a separate expandable section with short instructions. Recovery remains unavailable and is explained under Recovery and safeguards. No transfer, grant or recovery is executed by opening these sections.
- Lookup failures, uncertain reviews and confirmations preserve safe retry identities and selected inputs. Cancel/Escape restore focus. Existing MFA, exact review/confirmation and last-active-Super-admin enforcement remain unchanged.

## Files

- `frontend/src/auth/AdminConsole.jsx`: connects existing lookup and review/confirm operations, retains account/generation guards, revises the dialog and successor presentation.
- `frontend/src/auth/AdminMemberships.jsx`: scoped list, role guidance and account picker.
- `frontend/src/auth/admin-console.css`: scoped warm-white cards, spacing, dialog and responsive treatment.
- `frontend/tests/c15-admin/membership-workflow.run.mjs`: actual local lookup/access checks and isolated mutation fixtures.
- `frontend/tests/c15-admin/actual.run.mjs`: existing journey selectors follow new labels and disclosure; underlying scenarios retained.

## Verification and limits

Command: `node tests/c15-admin/membership-workflow.run.mjs` from frontend.

Passed actual local application/Auth/API checks: Super-admin admission; existing customer email lookup and matching immutable ID; no advancement without selection; prefilled existing staff row changes; Cancel/Escape focus restoration; successor/recovery disclosure; no page-wide overflow at 390px; ordinary Admin direct-route denial; actual membership review without fresh verification returns 403 and exposes the existing authenticator dialog. **No role grant or successor operation executed.**

Passed isolated UI fixtures: review failure retains account/role and operation identity; retry uses the same operation; review success alone does not confirm; confirmation failure retains receipt; retry uses the same review; final confirmed result closes dialog. These are frontend sequencing checks, not new database concurrency/permission acceptance. Existing backend contracts, grants, last-Super-admin concurrency logic and database tests were not changed or rerun.

Scoped ESLint: zero errors/warnings. Vite production bundle checked with `envFile:false`, `write:false`; no generated build outputs overwritten. Screenshots visually inspected: desktop list and mobile review. Evidence in `docs/evidence/c15-membership-workflow-20261106/`: `desktop.png`, `mobile.png`, `choose-access.png`, `review-desktop-fixture.png`, `review-mobile-fixture.png`, `results.json`. Review screenshots use synthetic identities and simulated mutation responses; no backend permissions were changed.

The existing memberships response supplies account IDs rather than emails; the list does not invent staff emails. Customer lookup shows the authorized email returned by the existing endpoint. Unknown/deleted identities remain server-controlled.

Local URL: http://127.0.0.1:5400/auth/admin?view=memberships

Local environment remains running. Browser contexts were closed. No new databases/services, backend/schema/activation changes, real emails, remote/provider operations, grants, commits or pushes. Historical evidence and protected leftovers remain untouched. Physical mobile devices were not tested.
