# C15.5 PR 73 UI review fixes

17 November 2026, Asia/Calcutta. Baseline `70705e5`, incorporating backend review fixes `97b5768`. No activation, grants, real delivery/payment operations, remote migration or production configuration change.

## Corrected behavior

- Same-account `SIGNED_IN`/`TOKEN_REFRESHED` events now use a separate authority probe. They do not abort mutations, reset operation IDs or unmount campaign drafts. Unverified work remains mounted but hidden/inert; dialogs close while suspended and reopen with their review identity after verified recovery. Account replacement, sign-out and loss of required role still clear private work. Backend checks remain authoritative.
- Coupon replacement controls and editing are disabled during a save, so its earlier result cannot discard a different editor.
- The customer resume empty state imports its existing FileText icon again. Successor sign-in carries the fixed acceptance route as its allowed `next` destination.
- Commercial-shell checks use shared template/resume helpers and current headings/recovery disclosures. Customer rows are selected through exact email descendants; the stale-inspection probe waits for all four older JSON bodies and a rendering barrier before checking the selected account.
- Dialog scrolling compares geometry before the first edge wheel and retains the original background baseline. This stricter check reproduced a one-pixel native-wheel clamp in a fractional-height commercial modal; scoped integer header line heights eliminate that movement without loosening the assertions. The metrics stale-response test changes sections through actual router navigation. Refinement evidence has a checkout-relative/configurable destination and wheel assertions wait for scroll state instead of fixed delays.

## Verification

Focused Playwright fixtures cover unsaved campaign retention, temporary authority suspension/recovery, account replacement, exact confirmation retry after token refresh, coupon-save locking, stale-role denial and successor redirect. An intentional first-edge movement probe verifies that the stronger scrolling helper rejects movement instead of accepting its shifted baseline. These tests run actual routed components against explicit synthetic Auth/API responses; they do not count as real Supabase acceptance.

Final results: all 71 existing commercial/admin browser scenarios and all 6 new review regressions passed. The three affected scroll scenarios also passed three repeats each (9 checks), without relaxing the first-wheel or original-background assertions. All 747 frontend Node tests passed, scoped ESLint reported no errors/warnings, and the dotenv-disabled frontend build passed. Frontend Node tests, scoped ESLint, JavaScript syntax, dotenv-disabled build and normal pre-commit audit are checked; final totals are recorded in the PR update. No lint/assertion/authorization rule is disabled.

Standalone runners requiring the separately running local demo and synthetic fixture credentials are updated and syntax-checked; that credential-dependent demo is not started or reset by this fix. Prior actual-engine/browser evidence remains historical. Fresh review artifacts remain outside committed source slices. Backend PR 72 stays first and the UI slice remains below 100 files. Original authoring source, staging and historical evidence are preserved.
