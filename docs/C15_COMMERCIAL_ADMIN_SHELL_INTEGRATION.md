# Commercial configuration: shared admin shell

5 November 2026. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. UI integration only. Existing changes, local services, historical evidence and protected leftovers preserved.

## Cause and implementation

`App.jsx` already routes `/auth/admin/subscriptions` to `SubscriptionAdmin`. That component explicitly rendered `DashboardLayout`, which supplies the customer workspace navigation, white canvas and customer profile/header. The editor itself is its separate, keyed `DraftWorkspace` with existing authority, cancellation, replay and navigation-guard logic.

The existing admin presentation was extracted into `AdminShell`, used by both `AdminConsole` and `SubscriptionAdmin`. It owns the common logo/sidebar/profile, mobile navigation dialog, compact header and workspace structure. Consumers retain their own authoritative admission and operations. The common dialog focus helper was moved verbatim into `adminFocus.js`.

Commercial navigation stays active using `aria-current` on its existing link. The main heading is Commercial configuration; Subscription drafts remains an internal section. Draft controls/editor and publication sections use scoped warm-white cards, neutral secondary text, responsive wrapping and the existing blue controls. There is one `#admin-content` scrollport, no customer shell and no duplicated header/sidebar.

`DraftWorkspace` remains in place with the same account key, hooks, blocker, request epochs, aborts, save identities, review/confirmation bindings, revision checks and lifecycle operations. The backend-authorized `subscriptions.manage` result is the existing admission condition; C15.5 maps that capability to Super admin. It is not granted by the sidebar or a client-editable role label. Actual ordinary Admin/customer direct-route denial remains verified.

No extra “Verified” badge or assurance claim was introduced on the commercial route. Its original permission probe, focus/interval rechecks and operation-level authorization remain unchanged. Existing AdminConsole verification controls and dialogs remain intact inside the shared shell.

Customer-shell profile/logout controls are replaced by the existing administration profile presentation. External sign-out and account-switch events still clear the private commercial workspace and pending dialogs. The customer DashboardLayout itself is unchanged.

## Changed files

| Files | Change |
| --- | --- |
| `frontend/src/auth/AdminShell.jsx`, `adminFocus.js` | Shared existing shell and unchanged dialog-focus helper. |
| `frontend/src/auth/AdminConsole.jsx` | Uses extracted shell; existing controls, dialogs and handlers retained. |
| `frontend/src/auth/AdminSidebar.jsx`, `admin-console.css` | Commercial active-link state, using the same sidebar highlight as buttons. |
| `frontend/src/auth/SubscriptionAdmin.jsx`, `subscription-admin.css` | Replaces customer wrapper, preserves workspace and groups existing content; scoped presentation only. |
| `frontend/tests/catalog/workspace.spec.js`, `lifecycle.spec.js` | Navigation checks now leave through Customers, including the mobile drawer, rather than the removed customer Resumes destination. Logout-while-blocked simulates the same external sign-out event as the other auth-event tests rather than clicking the removed customer-shell button. All retention/replay/write-count assertions remain. |
| `frontend/tests/c15-admin/commercial-shell.run.mjs`, `commercial-regression.config.mjs` | Actual local app checks and reproducible existing deterministic commercial suite against the running Vite server. |

Eleven source/test files plus this report and fresh evidence, within the existing admin presentation review group. No backend/API/schema/migration, customer layout, Electron, pricing calculation, commercial terms or activation-flag edits. No dependencies, commits, pushes or PR changes.

## Verification

Fresh evidence: `docs/evidence/c15-commercial-shell-20261105/`.

- **52 existing workspace/lifecycle browser tests passed**: create/open/edit/save/preview, approved imports, decimal precision, review/confirm/publish/replace/retire fixtures, revision conflicts, uncertain writes/replay, duplicate submissions, unavailable states, saved-version semantics, Stay/Discard, browser history, beforeunload, account switching/revocation/logout, expiry, modal focus/scroll bounds, close/reopen and published-offer refresh. API and Auth responses in this suite are isolated browser fixtures. These are not real publication/provider acceptance.
- Actual local Auth + normal application checks at **1440×900, 1366×768 and 390×844** verify sidebar entry, one shell/heading, correct active destination, direct refresh, mobile drawer/Escape, stable header during content scrolling and no page-wide overflow. Actual Back/Forward, draft creation/editing and Stay/Discard remain functional. Admin and customer direct routes show the established 404.
- **5 actual authorization/verification shell checks passed**, including missing-proof denial and account-switch cleanup.
- **21 existing dashboard state/interaction checks passed** after shell extraction, including actual local TOTP, responsive role navigation, filters, keyboard drawer/verification, sparse/fixture/error/partial states and denied deep links. Metric response fixtures are separate from actual Auth/role checks.
- **15 catalog/metadata unit tests passed**. Scoped ESLint: zero errors, three pre-existing ref-cleanup warnings in unchanged `SubscriptionAdmin` effects. No lint rules disabled. Scoped whitespace check passed. Full Vite build passed with `envFile:false` and `write:false`, 2,196 modules, 75 outputs. No TypeScript files changed; no unrelated formatter/typechecker dependency added.
- Desktop/mobile screenshots were visually inspected. Browser coverage is Chromium/emulated mobile, not physical-device or cross-browser certification.

Reproduce from `frontend`:

```powershell
node tests/c15-admin/commercial-shell.run.mjs
node node_modules/@playwright/test/cli.js test -c tests/c15-admin/commercial-regression.config.mjs
node --test src/auth/catalogDraft.test.js src/auth/catalogLifecycle.test.js src/auth/catalogV2.test.js src/websiteMetadata.test.js
```

## Existing local-backend limitation, kept explicit

The current local launcher does not set `CATALOG_DRAFTS_ENABLED`, `CATALOG_PUBLIC_ENABLED`, their DSNs or `CATALOG_LIFECYCLE_ENABLED`. Defaults in `backend/app/config.py:40` keep those paths disabled; `CatalogDatabase` does not start its pool without opt-in. An actual synthetic save returns HTTP 503 `catalog_database_unavailable`. The UI retains the edits and same-save retry identity and does not claim success. Public offer refresh likewise reports unavailable.

This task explicitly prohibits changing commercial activation flags or backend composition. Those were not changed. Actual persistence/preview/publication success is therefore **not claimed** for this running profile. The complete UI workflows pass at the permitted isolated test boundary, while the actual app's unavailable path is recorded separately in `actual-results.json`. No accepted historical commercial test was relabelled as current actual-backend acceptance. No test publishes to a real catalog/provider.

The initial actual test also needed to await closure of the native Stay/Discard dialog before filling an input; that synchronization was fixed in the test, without changing draft state handling.

The existing “Before real offers” and private-catalog warnings were preserved. They are historical commercial-policy/activation copy, not a new statement of approved tax/trial/discount policy or of global application readiness. Any policy-status wording review should be separate from this shell integration.

## Cleanup and access

Only test-owned browser contexts were closed. No fixture reset, service teardown, historical-file deletion, provider call, permission grant or remote operation occurred. Local development remains running with hot reload:

http://127.0.0.1:5400/auth/admin/subscriptions
