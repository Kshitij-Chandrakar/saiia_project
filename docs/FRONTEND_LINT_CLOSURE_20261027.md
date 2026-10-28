# Frontend lint gate closure ? 27 October 2026

**Lint gate passes: 60 errors / 29 warnings ? 0 errors / 12 warnings.** This is not warning-free or full-CI acceptance. C11/C12/C13 remain open for their separately recorded gates. No provider/installed-app test, external action, migration, credential/configuration change, commit or push occurred.

## Baseline and gate

Inspected Git status, existing uncommitted work, frontend package scripts, ESLint configuration, `.github/workflows/ci.yml` and `docs/C13_2_LINT_ATTRIBUTION.json`. No applicable AGENTS.md was found. Current baseline was measured, not copied from the historical count. Historical attribution and acceptance journals remain unchanged.

`npm run lint` executes `eslint .` with no `--max-warnings` threshold. Rule errors fail; the configured exhaustive-deps warnings do not. CI currently runs frontend build and Node tests but has no separate ESLint job; no CI/configuration/rule/exclusion was changed to obtain this result. Existing uncommitted configuration changes were preserved.

Machine-readable by-file/rule diagnostics: `tmp/frontend-lint-closure/baseline.json` and `final.json`. Before-edit source snapshots for initially diagnosed files and the initial Git status were retained locally. Counts and command results: `summary.json`, `commands.json` in that directory.

## Corrections

- Removed unreferenced legacy capture/analysis/system-streaming helpers after checking references; active Electron source-capture and current Screen-context execution remain. Unused state values use omitted destructuring while keeping setters/render behavior. Removed unused SVG imports and observational timing locals, not side-effecting operations.
- Made component-only helpers private, moved shared startup-login policy into existing `desktop_auth_ui.js`, and separated the shared Screen-context hook into `components/useScreenContextStatus.js`. Test fixture components export themselves for Fast Refresh. No suppression or rule weakening.
- Stabilized startup auth response handlers while using the latest committed parent callback; pending requests remain fenced. New browser regression verifies prop rerender does not repeat the request and completion invokes the current parent callback.
- Stabilized setup model/quota/resume loaders and admin permission checks with actual dependencies, without render-driven request loops. Resume loader reacts to account changes and ignores the previous account's late response; new browser regression verifies this. Existing permission, revocation, retry and navigation browser checks passed.
- Stabilized verified-account resume-token/loading helpers and onboarding resource loader. Added backend-origin dependency to email verification while retaining its single pending operation; no new token verification per render.
- Screen-event subscription uses the latest committed answer handler without resubscribing/refetching on every answer update. Toolbar effect only registers/removes the event listener each commit, has no network/state mutation at setup, and therefore uses current render handlers without a request/render loop. Existing manual/toolbar/screen regressions passed.
- Corrected resize minimum-height dependency and captured the actual dialog/focus target for cleanup. Password-reset lease semantics remain unchanged.
- Corrected JSX icon binding, equivalent regex syntax and redundant boolean conversion. Precision literals retain the same JavaScript numeric values (equality checked); no visual coordinate or billing calculation changed.
- Updated source-based assertions to the actual shared auth helper/current capture handler and replaced the removed dead-handler boundary in the live-mic VM test. Relevant active-path assertions remain; no test was disabled.

## Commands and results

| Check | Result / exit |
| --- | --- |
| `npm run lint -- --format json --output-file ../tmp/frontend-lint-closure/baseline.json` (frontend cwd) | 60 errors / 29 warnings; exit 1 |
| Same frontend lint command to `final.json` | 0 errors / 12 warnings; exit 0 |
| `node --test` on AuthScreens, startup_login_screen, desktop_auth_ui, analyze_screen_menu, manual_capture, screen_context_execution and screen_intelligence_contract test files | 179 passed, 0 failed; exit 0 |
| CI-style `node --test frontend/src/*.test.js frontend/src/auth/*.test.js` | 715 passed, 2 pre-existing failures; exit 1 |
| `npx playwright test --config playwright.catalog.config.js lint-lifecycle.spec.js workspace.spec.js lifecycle.spec.js --reporter=list` | 52 existing workspace/lifecycle checks passed; 2 new fixture import failures, corrected below |
| Same Playwright config, `lint-lifecycle.spec.js` only, after correcting default ReactDOM fixture import | 2 passed; exit 0; no accepted tests rerun unnecessarily |
| `npm run build` | Passed, exit 0; existing >500 kB chunk-size advisory remains |
| `node --check` on 11 changed JS files | All passed; JSX parsed/compiled by build |
| `git diff --check` | Passed, exit 0 after scoped whitespace cleanup |

No frontend formatter/type-check script is configured and no TypeScript compiler was added. Whitespace/syntax/build checks are reported as such, not mislabeled static typing. No lint formatter/configuration was changed. Logs are retained under `tmp/frontend-lint-closure/`.

### Broader Node blockers, separate from lint

1. `grpc_combined.test.js`: capture-start failure cleanup expects `ended === null`, receives undefined. Its gRPC module/test were not modified by this task. The start-failure path does not register the ended listener. This assertion/fixture mismatch remains, not silently passed.
2. `grpc_computer_auto.test.js`: Stop during combined permission wait calls an unset resolver. The same failure reproduces using the saved pre-edit App source (`preexisting-repro.log`); it is not introduced by removing dead helpers or editing hook dependencies. This test needs its own asynchronous precondition/handshake investigation.

Neither was hidden, skipped or modified. CI-style Node verification remains blocked by these two failures despite the lint gate passing. No accepted provider or installed acceptance was rerun.

## Remaining diagnostics

All 12 are `react-hooks/exhaustive-deps` warnings, not errors:

| Location | Diagnostic |
| --- | --- |
| `frontend/src/App.jsx:1856` | The ref value 'autoStartTokenRef.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'autoStartTokenRef.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/CatalogLifecycle.jsx:73` | The ref value 'sequence.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'sequence.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/CatalogLifecycle.jsx:85` | React Hook useEffect has a missing dependency: 'pending'. Either include it or remove the dependency array. |
| `frontend/src/auth/PublishedOffers.jsx:10` | The ref value 'sequence.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'sequence.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/SubscriptionAdmin.jsx:125` | The ref value 'probe.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'probe.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/SubscriptionAdmin.jsx:233` | The ref value 'epoch.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'epoch.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/SubscriptionAdmin.jsx:234` | The ref value 'requests.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'requests.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/auth/WebsitePasswordReset.jsx:105` | The ref value 'lease.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'lease.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/components/DesktopAnswerHistory.jsx:17` | The ref value 'generation.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'generation.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/components/DiagramSection.jsx:153` | The ref value 'generation.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'generation.current' to a variable inside the effect, and use that variable in the cleanup function. |
| `frontend/src/components/DiagramSection.jsx:154` | React Hook useEffect has missing dependencies: 'apply' and 'source'. Either include them or remove the dependency array. |
| `frontend/src/components/StartupSessionSetupScreen.jsx:111` | The ref value 'modelRequestRef.current' will likely have changed by the time this effect cleanup function runs. If this ref points to a node rendered by React, copy 'modelRequestRef.current' to a variable inside the effect, and use that variable in the cleanup function. |

Ten warnings concern cleanup reading the latest generation/lease counter or request collection. These refs are mutable lifetime-fencing state, not interchangeable with a captured DOM node: copying their numeric mount-time values can invalidate newer work incorrectly or permit late writes. They remain explicit diagnostics; no suppression was added. The actual dialog element and focus-target warnings with clear capture semantics were fixed.

Two warnings concern the draft-change-only reset's `pending` dependency and the diagram resolver's `apply/source` dependencies. Blind additions change behavior: clearing a just-completed lifecycle result or refetching/resetting diagrams on unstable object/function identities. Existing tests pass; a lifecycle/state-trigger refactor and focused diagram recovery verification would be needed to eliminate these safely. No missing product decision or credential blocks the current lint gate. The warnings remain follow-up technical work, not a claim that all effect code is warning-free.

## Changed source/test files

- `frontend/src/App.jsx`
- `frontend/src/analyze_screen_menu.test.js`
- `frontend/src/auth/AuthScreens.jsx`
- `frontend/src/auth/AuthScreens.test.js`
- `frontend/src/auth/DashboardOnboarding.jsx`
- `frontend/src/auth/SessionSuggestions.jsx`
- `frontend/src/auth/SignupMascot.jsx`
- `frontend/src/auth/SignupVerificationNotice.jsx`
- `frontend/src/auth/SubscriptionAdmin.jsx`
- `frontend/src/auth/WebsiteLogin.jsx`
- `frontend/src/auth/WebsitePasswordReset.jsx`
- `frontend/src/auth/WebsiteResumes.jsx`
- `frontend/src/auth/WebsiteSessionTable.jsx`
- `frontend/src/auth/WebsiteSessionViewer.jsx`
- `frontend/src/auth/authApi.js`
- `frontend/src/components/AnswerPanel.jsx`
- `frontend/src/components/MainDiagnosticsWindow.jsx`
- `frontend/src/components/OverlayWindow.jsx`
- `frontend/src/components/ScreenContextControls.jsx`
- `frontend/src/components/StartupLoginScreen.jsx`
- `frontend/src/components/StartupSessionSetupScreen.jsx`
- `frontend/src/components/useScreenContextStatus.js`
- `frontend/src/desktop_auth_ui.js`
- `frontend/src/desktop_auth_ui.test.js`
- `frontend/src/landing/LandingPage.jsx`
- `frontend/src/manual_capture.test.js`
- `frontend/src/screen_context_execution.test.js`
- `frontend/src/screen_intelligence_contract.js`
- `frontend/src/startup_login_screen.test.js`
- `frontend/tests/catalog/lint-lifecycle.spec.js`
- `frontend/tests/fixtures/answer-diagrams.jsx`
- `frontend/tests/fixtures/answer-presentation.jsx`
- `frontend/tests/fixtures/answer-stream.jsx`

## Evidence preservation and Graphify

Five historical provider execution journals retain their exact recorded hashes (`preserved-journals.json`). No old acceptance count or result was reset. Current support findings are pending and Razorpay execution remains paused. C12 cleanup remains verified; invoices and production readiness remain separate.

Graphify queried the existing root graph for App/startup/auth/Screen relationships: 47 related nodes, BFS depth 2 (`graph-query.txt`), no semantic extraction/model calls. The existing graph is historical navigation evidence, not proof that it reflects these edits; it was not overwritten or visualized. Direct source/reference inspection and runtime checks establish the changes above.


## Paired isolated gRPC follow-up ? 27 October 2026

Both reported failures now reproduce under identical commands and environment in separate pre-lint/current input copies: two tests, zero passes, two failures, exit 1 on each. Current working sources were byte-verified unchanged. [Baseline provenance, exact commands, hashes and limitations](FRONTEND_LINT_GRPC_BASELINE_COMPARISON.md). No regression from the lint edits was found in those two cases; lint changes are ready for review, while full-CI green remains blocked by the existing failures and the 12 warnings remain documented. Prior acceptance results were not rerun.


## Separate test-fixture fixes ? 27 October 2026

The two historical gRPC blockers above are now resolved by a subsequent test-only change: 164/164 relevant lifecycle cases pass. Production bytes unchanged; lint remains 0 errors / 12 warnings. [Separate root-cause/fix evidence](GRPC_BASELINE_FAILURE_FIXES_20261027.md). Earlier baseline logs/counts are retained unchanged; full CI was not rerun and is not claimed passed.
