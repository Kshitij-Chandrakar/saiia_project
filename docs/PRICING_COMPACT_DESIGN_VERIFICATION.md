# Compact pricing presentation - 2026-10-23

Completed website-only implementation of the supplied slim-card visual reference. Approved catalog terms remain authoritative. No backend, schema, real offers, .env, Electron, payment or production activation changes in this slice.

## Implementation

Existing #pricing section now uses the requested heading/subtitle, restrained pale blue/lavender background, centered segmented control, blue/teal/purple compact cards with natural content height, and a shared-benefits strip. No duplicated logo, sample prices, popularity badges or draft-description copy. Integer price formatting and floor annual savings are unchanged. Monthly and annual totals, approximate equivalents and offer/price/version identifiers still come from the public response. Free signup and disabled paid checkout remain unchanged.

Card differences derive from entitlements, allowance amounts/modes/periods and storage capacity, not plan-name entitlement branches. Auto seconds convert exactly to hours/minutes/seconds. Resume storage and replacements share one row; Clipboard has exactly one row with allowance-derived information. Sketch uses the published approved information text and strikes through only when excluded. Shared claims require every returned offer to qualify; a regression limits one offer's transcription and proves the shared unlimited claim disappears. Support labels/readiness remain published data, not an invented operational service.

All inert eye buttons/imports were removed from CatalogFeaturePresentation, a website-only presentation component. Its information controls retain hover/focus/tap-click/Escape, accessible names, visible focus and click isolation. Canonical catalog preview metadata is preserved to avoid changing historical terms. No unrelated application preview implementation was altered. The long paragraph is now concise copy plus native keyboard-accessible Allowance details, retaining silence/stopped/Both rules, midnight IST, original signup-day clamp/restore, no rollover and Clipboard retention/immutability.

## Files

- frontend/src/landing/CatalogPricing.jsx
- frontend/src/landing/catalog-pricing.css
- frontend/src/auth/CatalogFeaturePresentation.jsx
- frontend/tests/catalog/pricing.visual.spec.js (new, opt-in actual local catalog verification)
- frontend/tests/catalog/pricing.spec.js (updated labels and shared-benefit regression)
- frontend/tests/catalog/presentation.spec.js (approved heading/no-eye assertions)
- frontend/tests/catalog/pricing.integration.spec.js and free.integration.spec.js (approved visual/no-eye assertions retained alongside existing functional checks)

Existing price formatter, catalog reference JSON, backend and deployment configuration are unchanged by this slice. Earlier uncommitted work is preserved.

## Actual results

- 44 Playwright workspace/lifecycle/presentation/pricing tests passed, including one actual live IPv4 catalog visual test and synthetic mocked-state tests. No functional assertions or timeouts weakened; obsolete eye/heading/copy expectations updated only for the approved design.
- Final focused rerun after shared-model permission guard: 4 passed (17.0s); actual live visual test 9.4s.
- 119 Node website/auth/catalog/money tests passed.
- Production Vite build passed; existing large-chunk advisory remains.
- Actual URL http://127.0.0.1:5173/#pricing returned the existing isolated native catalog through its live proxy. No API interception in the visual test. Verified Monthly/Yearly at 1440x900, 1366x768, 820x1000 and 390x844; eight section screenshots. Three cards, prices/totals/savings, derived hours, one Clipboard row/card, Sketch exclusion, no eye controls, per-offer tooltips/focus/Escape/click, tooltip horizontal bounds, signup link, disabled paid CTAs and document overflow assertions passed.
- Mocked-state tests separately verify loading, empty, unavailable/retry, refresh after retirement and suppression of invalid universal unlimited claims. Existing 404/permission, uncertainty, revision/conflict, account cleanup, navigation and lifecycle UI tests passed. This presentation task does not re-establish deployed Supabase authorization acceptance.
- Before and after Graphify queries plus structural refresh completed (7,001 graph nodes). Package/skill version advisory remains nonblocking; no provider calls.

## Screenshots and manual inspection

Artifacts are under tmp/c113d-playwright/pricing.visual-compact-pri-c15e9-g-responsive-and-accessible/:

- pricing-1440-monthly.png / pricing-1440-yearly.png
- pricing-1366-monthly.png / pricing-1366-yearly.png
- pricing-820-monthly.png / pricing-820-yearly.png
- pricing-390-monthly.png / pricing-390-yearly.png

Desktop and mobile images were visually inspected against the supplied reference. Plan rows are compact and shared benefits are below the cards; smaller cards have natural shorter height rather than invented filler. No internal card scrollbars or fixed card heights.

Working isolated URL: **http://127.0.0.1:5173/#pricing**. Do not substitute localhost: it may select the separate normal IPv6 frontend. Existing runner lifetime is one hour; restart/stop instructions remain in CATALOG_LOCAL_MANUAL.md. Services not owned by this task were left running and untouched.

Reproduce the visual/browser suite from the repository root while that setup is running:

```powershell
$env:CATALOG_VISUAL_URL='http://127.0.0.1:5173/#pricing'
npx.cmd --prefix frontend playwright test --config frontend/playwright.catalog.config.js pricing.visual.spec.js pricing.spec.js presentation.spec.js workspace.spec.js lifecycle.spec.js
```

Remaining environment limitation: normal localhost/backend catalog readiness is still separate from the synthetic local setup, as documented in CATALOG_LOCAL_MANUAL.md and SUBSCRIPTION_ADMIN_ACCESS_PREPARATION.md. No normal/shared database grants, migrations or publication were performed to make these screenshots. Support/early access remain Coming soon; payments remain disabled. Prior unrelated broader landing startup-label mismatch and historical PDF/combined-process failures were not changed or relabelled passes.
