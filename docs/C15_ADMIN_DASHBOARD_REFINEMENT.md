# Admin dashboard refinement

5 November 2026. Local presentation changes only. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Existing local synthetic environment remains running at http://127.0.0.1:5400/auth/admin?view=overview.

## Reproduction and cause

The original shell expanded to document height. Its header was in normal document flow. The sidebar used sticky positioning inside a grid whose containing block also moved with document scrolling. At 1440×900, a wheel scroll moved the header from y=28 to -59 and the sidebar container from y=0 to -87. At 1366×768 these became -191 and -219. These measurements are in `evidence/c15-admin-refinement-20261105/before.json`.

No separate new recording attachment was accessible in this turn. Reproduction used the actual running application and measured browser geometry. A new recording demonstrates the resulting behavior.

Page-wide horizontal overflow was not reproduced at the requested widths: document scroll width equalled viewport width before and after. The wider elements were 760px-minimum accessible data tables inside their existing `.ac-table` horizontal scrolling regions, not an escaping page-width element. Those tables remain available without truncation. No body-level overflow hiding was added.

## Implemented

- Viewport-height grid shell, stationary sidebar and header, one flexible `main` content scrollport with explicit zero minimum sizes, stable scrollbar gutter and contained scroll chaining.
- Sidebar brand/profile remain outside its independently scrollable navigation. Navigation scrolls only if its contents exceed the available height.
- Warm palette, logo, typography and blue interactions retained. Supporting copy uses neutral gray; summary values retain tabular numerals and aligned label/value space.
- Unavailable KPI values use an accessible dash rather than large “Unavailable” text. Real zero, loading and failures retain their separate meanings and explanations.
- Existing native selects, modal verification/navigation dialogs, tooltips, tables, permission checks and metric contracts reused. No schema, backend, provider or role changes.

## Changed source and checks

1. `frontend/src/auth/admin-console.css`: shell sizing/scrolling and focused visual adjustments.
2. `frontend/src/auth/AdminOverview.jsx`: accessible unavailable KPI presentation.
3. `frontend/tests/c15-admin/refinement.run.mjs`: actual-login geometry, wheel/scrollbar, footer, role, navigation and verification checks plus recording.
4. `frontend/tests/c15-admin/overview-info.run.mjs`: optional evidence-directory override.
5. `frontend/tests/c15-admin/overview-states.run.mjs`: optional evidence-directory override.

All belong to the existing admin presentation review slice; this refinement does not create a new application feature or change earlier dependency ordering.

## Evidence and limitations

Fresh evidence directory: `docs/evidence/c15-admin-refinement-20261105/`.

- `before-*.png`, `before.json`: original actual local geometry/screenshots, both roles.
- `after-*.png`, `bottom-*.png`, `results.json`: final actual local checks at 1440×900, 1366×768, 768×1024, 390×844, 720×450 and 1280×450, both roles. The 720×450 viewport exercises the effective layout size of a 1440×900 window at 200% zoom.
- `stable-scrolling.webm`: actual Super admin session, wheel scrolling, native scrollbar dragging, verification dialog and stationary shell. Intermediate recordings retained separately.
- `state-results-reference.json`: 21 existing state/interaction checks passed, including labelled populated metric fixtures, loading, failure, unavailable, partial coverage, filters, actual local Auth TOTP, mobile keyboard navigation and forbidden Admin deep link. Only metric fixture responses are simulated; actual roles/Auth remain local-engine-backed.
- `results.json` from the tooltip runner uses its own six checks; see `tooltip-results.json` for the copied result to avoid confusing it with shell results.
- `build.json`: full Vite build passed, 2,191 transformed modules and 75 outputs, `envFile:false`, `write:false`. Scoped ESLint passed. No new dependency or output build directory.

Browser captures were visually inspected at desktop and mobile, including the reachable footer. This is Chromium desktop/touch emulation and effective zoom-size coverage, not physical mobile hardware or cross-browser certification. No backend regression suite was repeated for this presentation-only change.

Preservation exception: the first invocation of the pre-existing state/tooltip runners regenerated their default screenshot/result filenames before their new evidence-directory override was added. The earlier original before/final-accepted actual screenshots, reports, journals and protected leftovers were not removed. Subsequent runs use the fresh directory. This is a capture-history refresh, not an application-data mutation.

The same synthetic local services remain running. No fixtures were reset, no account grants were changed, no provider actions were executed and no protected cleanup was attempted.
