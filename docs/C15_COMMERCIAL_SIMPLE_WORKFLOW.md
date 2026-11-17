# Commercial configuration: simplified workflow

6 November 2026. Local frontend implementation; commercial activation unchanged. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Existing work and historical evidence preserved.

## Implemented behavior

1. **Choose a plan:** one New plan chooser starts Free, Plus, Pro or scratch using existing imports/create behavior. Resume a draft reveals the existing ID path. Published plans remain independently accessible.
2. **Edit and save:** plan name/description lead; pricing/features retain existing tabs and validation. Lower-frequency policies live in Advanced settings; validation opens hidden fields and focuses them. Save draft is private. Failed saves preserve edits and retry identity. Only successful saves advance the indicator.
3. **Review and publish:** saved preview, readable blockers, review and separate exact-version confirmation retain existing contracts. Dirty drafts invalidate review eligibility. Navigation, preview and saving never publish. Published-plan actions use View plan, Create updated version and Stop offering this version. Retirement confirmation explains new-customer availability and preservation of existing subscriber terms.

Troubleshooting retains draft/operation IDs and recovery. Uncertain results open recovery immediately without repeating a write. Shared shell, access rules, activation flags, revisions, request cancellation, account-switch cleanup and unsaved-navigation guards remain in place. No new dependencies, backend APIs or migrations.

## Files

Application: `frontend/src/auth/SubscriptionAdmin.jsx`, `CatalogDraftFields.jsx`, `CatalogLifecycle.jsx`, `PublishedOffers.jsx`, `catalogDraft.js`, `catalogDraft.test.js`, `subscription-admin.css`.

Browser coverage: `frontend/tests/catalog/fixtures/workspace.js`, `workspace.spec.js`, `lifecycle.spec.js`, `workflow.spec.js`; `frontend/tests/c15-admin/commercial-regression.config.mjs`, `commercial-flow-actual.run.mjs`.

This report and fresh `docs/evidence/c15-commercial-workflow-20261106/` artifacts accompany the scoped frontend review. Preserve the existing dependency-ordered C15 review slices; no commits or PR changes made.

## Validation

- Actual routed website / local Auth: seven scenario groups passed, recorded in `actual-results.json`. Real synthetic Super-admin login, sidebar/deep-link/reload and Back/Forward navigation, Stay/Discard, stable shared header, mobile drawer and no page overflow at 1440x900, 1366x768 and 390x844. Ordinary Admin and customer remain denied. Real failed save preserves inputs.
- Isolated API/Auth fixtures: workspace/lifecycle/workflow browser suite covers template/blank starts, ID reopen, save/retry/uncertainty, keyboard/modal behavior, stale responses, account switching, separate review/final publication, versioning/retirement and invalidation after edits. Fixture screenshots explicitly identify synthetic data.
- Unit checks: 16 passed (`catalogDraft`, `catalogLifecycle`, `catalogV2`, `websiteMetadata`).
- Scoped ESLint: zero errors; six existing hook/ref dependency warnings retained, no rules disabled.
- Vite 7.0.6 production build passed, 2,195 modules / 74 outputs; `envFile:false`, `write:false`, so no operational dotenv loading or generated build overwrite.
- Scoped `git diff --check` passed. Graphify queried before and after; historical graph verified against current source, no refresh/provider calls.

Browser testing caught and fixed focus restoration when closing a draft during the catalog refresh, and the absence of a visible lifecycle reason when stopping a published version without opening a draft. Regression coverage includes both. Hidden/visible reason inputs are targeted semantically by role.

## Evidence and limits

Screenshots: `stage-1-choose-{1440,1366,390}.png`, `stage-2-edit-{1440,1366,390}.png`, `stage-3-review-{1440,1366,390}.png`. Real routed screens: `commercial-{1440,1366,390}.png`, `commercial-editor.png`, `save-check.png`.

**Actual catalog storage remains disabled:** real save returns HTTP 503 `catalog_database_unavailable`; public catalog listing is unavailable. Successful persistence/reopen/preview/review/publication/versioning/retirement were verified with isolated browser fixtures only, not real catalog storage. These remain actual-backend acceptance dependencies. No activation flags or permissions were changed to obtain a pass. Mobile checks use browser viewport emulation, not physical-device acceptance.

## Preservation and access

Working URL: http://127.0.0.1:5400/auth/admin/subscriptions

The previously authorized local environment remains running (website5400/backend8400/local Auth19940/Storage15040/PostgreSQL15440/Mailpit8040). No new service/database resources were created by this refinement. Historical screenshots, rejected cleanup leftovers and existing changes remain untouched. No real emails, publication, provider operations, remote changes, grants, commits or pushes.

Final browser regression result: **58/58 passed** (1.7 minutes), including all three viewport workflows and published-version retirement without an open draft. Final artifacts: erified-regressions/.
