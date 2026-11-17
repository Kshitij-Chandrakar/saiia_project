# Admin page scroll bounce

6 November 2026. Focused follow-up to the popup fix; worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`.

The main admin content scrollport and sidebar navigation still used `overscroll-behavior:contain`. This blocks chaining but permits the browser's local edge affordance. The popup fix deliberately applied only while modals were open, so it did not change ordinary page scrolling.

Changed `frontend/src/auth/admin-console.css`: main content and sidebar use overscroll none; document/root overscroll is suppressed only while the shared admin application is present. Normal overflow remains auto. No wheel prevention handlers, positioning changes, data/API changes or hidden page content were introduced. Existing popup rules remain intact.

Verification command: `node tests/c15-admin/page-scroll.run.mjs` from frontend.

20 actual-route checks passed with synthetic local Auth accounts:
- Super admin: Overview, Customers, Campaigns, Administrators, Coupon drafts, Audit history, Commercial configuration.
- Admin: Overview, Customers, Campaigns only.
- Each checked at 1366x768 and 390x560.
- Long pages scroll through wheel input; fitting pages are explicitly distinguished.
- After reaching both natural boundaries, five repeated excess wheel events preserve content-text position, scroll offset, header/sidebar position and document offset.
- No page-level horizontal overflow. No endpoints were mocked for these checks; existing unavailable catalog/metrics states are not relabelled as successful data acceptance.

`docs/evidence/c15-admin-page-scroll-20261106/results.json` contains all results and observed scroll ranges; desktop/mobile screenshots cover Overview, Administrators and Audit history.

Scoped test ESLint and Vite production build passed (`envFile:false`, `write:false`). Existing local services remain running on website5400/backend8400. No new databases/services, permission grants, emails, provider calls, remote changes, commits or pushes. Historical evidence and protected leftovers preserved.

Browser wheel/viewport checks do not establish physical-device touchpad acceptance. The legacy standalone billing page is not part of the shared sidebar application and was not changed by this focused section fix.

URL: http://127.0.0.1:5400/auth/admin?view=audit
