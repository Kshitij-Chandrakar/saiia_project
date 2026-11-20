# Admin Overview and shell: approved reference implementation

5 November 2026, Asia/Calcutta. Implemented in `E:/saiia_project/c15-stage1`, `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. The explicitly authorized synthetic local environment remains running. No migrations, grants, provider operations, emails, commits or pushes were performed for this design task.

Open http://127.0.0.1:5400/auth/admin?view=overview using an existing local staff login. Edit `frontend/src/auth/`; Vite hot reload remains enabled. Login, stop and reset commands remain in [local development instructions](C15_LOCAL_DEVELOPMENT.md).

## Scope and implementation

| Requirement | Implemented behavior | Evidence |
| --- | --- | --- |
| Reference palette and hierarchy | Ivory canvas `#F5F1E9`, beige sidebar `#F0EADF`, warm-white `#FFFEFC` cards, navy text, existing blue accent, delicate borders,12px cards, local Dashboard Inter and tabular numerals | Before/after and fixture screenshots |
| Shared admin shell |248px desktop sidebar, actual own account display name or email prefix/initials and backend role; current role controls management navigation; all previous destinations retained | Actual role views and safety checks |
| Compact header | One page heading, original7/30/90-day and Asia/Calcutta/UTC behavior, compact controls, refresh pending state, exact source freshness | Filter/refresh/browser cases |
| KPI grid | Verified current/new users, active7-day users and estimated cost; existing growth,30-day and approximate5-minute activity retained | Actual sparse view and isolated populated fixtures |
| Charts | Native responsive SVG, measured with ResizeObserver, labelled axes, explicit observations, focus/hover details, ranked model bars and comparable attempt counts; no chart dependency | Point focus, date-gap and data-table checks |
| Data alternatives and coverage | Exact user/model tables in the keyboard-accessible Metric definitions / Data coverage disclosure; source dates, exclusions and definitions remain available | Disclosure and chart checks |
| Honest states | Unavailable is distinct from verified zero; single observation remains one point; missing dates split lines; incomplete cost coverage, separate currencies, older snapshot, loading and failed reads are explicit | State fixtures and real sparse data |
| Verification | Existing Auth TOTP enforcement unchanged; compact dialog surfaces on sensitive-operation403, traps focus and supports Escape; badge requires current session AAL2, TOTP issuance method and existing5-minute freshness | Actual Auth verification and denied review cases |
| Route title | Fixed route-title vocabulary includes authorized admin routes; actual customer/Admin forbidden screens still show Page not found | Metadata unit tests and actual role-switch/deep-link checks |
| Responsive behavior |1440x900,1366x768,768x1024 and390x844; two-column tablet cards, mobile drawer, explicit focus management, scoped table scrolling, zoom/long-name/large-value checks and reduced-motion support | Both-role responsive and interaction cases |

Authentication status is a presentation hint only. Every permission, proof, confirmation and mutation remains subject to the existing backend checks. Private customer content, audit permissions, commercial permissions and deletion behavior were not broadened. Existing commercial form blockers and workflows were not edited. Console navigation retains existing query parameters; late metric responses cannot restore an old section. Privacy request inspection remains within Customers.

The lower activity chart groups the existing executed attempts by model, not invented weeks. Cost detail uses actual per-currency aggregates and measured coverage; no provider-level monetary split or currency conversion is invented. Growth percentages describe the backend's selected window, not a manufactured previous-period comparison. Negative growth uses a downward indicator. Unknown prior history and unsupported provider charges remain unavailable. The actual view has no sample-data banner. Labelled populated fixtures replace only metrics responses in isolated browser contexts and never write fixture metrics into the runtime database.

## Changed files

- `frontend/src/auth/AdminConsole.jsx`: shell, compact verification, existing handlers and filters.
- `frontend/src/auth/AdminSidebar.jsx`: role-filtered sidebar and real own-account presentation.
- `frontend/src/auth/AdminOverview.jsx`: KPI/chart grid, source coverage, states and accessible data alternatives.
- `frontend/src/auth/admin-console.css`: scoped shell/Overview styling; existing other-screen controls retained.
- `frontend/src/websiteMetadata.js`, `WebsiteNotFound.jsx`, `websiteMetadata.test.js`: fixed admin route metadata and forbidden-route regression.
- `frontend/tests/c15-admin/overview.run.mjs`, `overview-states.run.mjs`, `overview-safety.run.mjs`: actual-app responsive, isolated fixture and actual Auth/authorization checks.
- `frontend/tests/c15-admin/actual.run.mjs`: existing step-up helper opens the compact form when required; successor's existing visible form remains supported.
- This report. No backend, schema, package, lockfile, customer design, Electron or email-template changes.

## Verification

Evidence root: [c15-admin-overview-20261105](evidence/c15-admin-overview-20261105/verification.json).

- 8 before captures and8 final actual sparse-data views, both roles at the four requested sizes.
- 21 state/interaction checks: populated labelled fixtures, filter payloads, chart selection/focus/data alternatives, drawer containment/Escape/focus restoration, actual Auth TOTP, unavailable/partial/multiple-currency/older-snapshot/loading/error states, date gaps, large values, long labels,200% CSS zoom, late responses and Admin forbidden deep links.
- 5 actual local authorization/verification checks with no interception: absent fresh proof receives403 and surfaces verification before mutation, Super admin-to-Admin switching removes management navigation, and customer switching clears the staff shell and retains404/title behavior.
- 2 fixed-route metadata tests; scoped ESLint; complete App build with dotenv disabled and75 in-memory outputs. No build directories were generated. This JavaScript/JSX scope has no TypeScript compiler check; JSX is checked by ESLint and the full Vite transform/build.
- Actual Auth/API checks are distinct from browser-only metric fixtures. No provider/payment acceptance or unrelated existing C15/backend acceptance was repeated. Credential-bearing browser traces were not retained; screenshots and safe result categories provide diagnostics.

Before screenshots are `before-{role}-{width}.png`; final sparse screenshots are `after-final-accepted-{role}-{width}.png`; populated fixture screenshots are `fixture-{role}-{width}.png`. Earlier intermediate captures/results are retained and are not the final acceptance source. A preliminary unbounded browser capture stalled during hot reload; it was stopped, and the harness now has bounded waits, at most two parallel contexts, and an explicit ready-state assertion. Visual inspection also caught and fixed native-drawer reverse-tab escape and initial capture timing. Chart geometry was subsequently tightened to the approved reference without dropping data or scaling labels down.

## Design guidance and limits

Dashboard-designer/chart-builder source reused from the existing cached evidence at commit `bb47af79ad3befe01ae01940fcf5f16e30a1b6df` of NickCrew/Claude-Cortex. Applied headline KPI hierarchy, top filters, primary/secondary chart organization, consistent units, freshness and accessible details. Generic comparison recommendations were limited by actual source coverage.

Unslop guidance by Damir Sokolovsky (@heydamir), CC BY4.0, informed the spacing, restrained chrome, consistent icons and typography. Design-taste-frontend explicitly excludes dashboards; only its audit/brand-preservation and responsive/accessibility guidance was relevant. The approved image overrides generic font/palette preferences. Design settings: variance3, motion2, density6. Existing native CSS, React, Inter, Lucide and SVG were sufficient; no new system, chart package, illustration or external font was installed.

The design follows the reference's warm layout, proportions and chart hierarchy. It intentionally differs where unsupported data would otherwise be fabricated, where full commercial labels must stay readable, and where verification has not actually occurred. The user's identity is never hardcoded and no decorative verification badge is added.

Review order preserves every earlier slice; this bounded Overview/shell overlay has12 source/test/document paths, with evidence enumerated separately in groups of at most60 paths. No PR or Git history was changed. The local website, backend, workers, Auth, Storage, mail and checkpoint environment remain running for review; historical evidence and protected leftovers remain preserved.
