# Admin popup scroll containment

6 November 2026. Worktree `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Existing changes/evidence preserved.

## Diagnosis

The admin application uses native dialog elements in several components, rather than one common React dialog component. Shared presentation is in `admin-console.css`. The commercial preview/review wrapper additionally has its own scrollable body in `subscription-admin.css`.

Before changes, the live Change admin access popup computed to `overflow-y:auto`, `overscroll-behavior-y:contain`. Its background `#admin-content` remained `overflow-y:auto`; the document used default overscroll behavior. `contain` prevents chaining but permits the browser's local overscroll affordance. Other native admin dialogs had no common overscroll policy. The commercial body separately used `contain`. Native modal inertness is not an explicit lock on the application's nested scroll container.

`before.json` records the actual 390x560 popup: 502px inner height, 855px content, 353px range, background scroll position 384. Automated baseline wheel input did not produce measurable DOM-frame movement; compositor/native rubber-band animation must not be represented as an observed DOM offset. The original user recording was not available as an attached video file in this continuation; testing used the same actual Change admin access route and a new local recording.

## Fix

- Shared `dialog:modal` rules use `overscroll-behavior:none`, disable document overflow and lock the actual background main/desktop-navigation scrollports while any admin modal remains open.
- Ordinary dialog scrollports keep `overflow-y:auto`, bounded available viewport height and stable scrollbar gutter. Content is not clipped or made non-scrollable.
- Nested verification continues to lock the background until the last modal closes; no counter or wheel-cancelling JavaScript is needed.
- The commercial wrapper's separate scroll body changes from contain to none. Its existing header, focus trap and standalone body-lock/restore behavior remain intact.
- The mobile drawer's own navigation scrolls with overscroll none. It is excluded from the ordinary form height rules.
- Floating metadata-help surfaces also use overscroll none; these nonmodal disclosures intentionally do not lock the page.

Production changes: `frontend/src/auth/admin-console.css`, `frontend/src/auth/subscription-admin.css`. No API, authorization, commercial, confirmation or focus-handler changes.

## Actual routed browser checks

Command from frontend: `node tests/c15-admin/dialog-scroll.run.mjs`.

| Implementation | Evidence |
| --- | --- |
| Change admin access, 390x560 | Real local Auth/API; 353px range; first/last controls reachable; role/status/reason focus and role selection work; repeated excess wheel input at both boundaries leaves frame, heading, scroll offset and background unchanged. |
| Change admin access, 1366x600 | 228px range; same boundary assertions. |
| Nested verification over membership | Actual review returns 403 without fresh proof; verification opens; closing it keeps background locked under parent; closing parent restores main overflow. No grant executed. |
| Standalone access verification | Stable at both edges, code field focus and Escape preserved; no OTP submitted. |
| Customer access confirmation | Real local metadata and actual popup; 26px range; boundary and Cancel checks; no restriction confirmed. Renewal cancellation and eligible cleanup retries use this same native support-dialog implementation. |
| Mobile navigation drawer | Independent nav scrollport, 18px range; boundaries/background stable; Escape works. |
| Campaign confirmation | Actual route, local Auth, isolated campaign API fixtures; both ends stable; Cancel works; no send or provider request. |
| Metadata help popover | Actual local metadata; computed overscroll none, repeated wheel input stable, Escape dismisses. |
| Legacy billing review | Actual `/auth/admin/billing` component with isolated billing API fixtures; confirmed it is an inline static SECTION with role=dialog, not a floating/modal popup or separate overlay scrollport. No write executed; no unrelated conversion to a modal. |

`actual-results.json` records nine groups. The video starts after login; credentials/OTP entry is not captured. Current successful recording: `video/page@4809c0f3a1e49a5974c76f6a82e55ea6.webm`.

## Commercial regression coverage

Two new browser tests exercise the actual routed components with isolated Auth/catalog fixtures:
- Saved-plan preview and unsaved-navigation Stay dialog, 390x560.
- Publication review and separate final publication confirmation, 390x560, including a genuinely scrollable long body, final-button reachability and cancellation without publication.

Common test helper checks real wheel scrolling, then six additional wheel events beyond each natural edge, comparing dialog/frame/heading/background coordinates and scroll offset after animation frames. It also checks backdrop wheel input and restored background scrolling. A natural wheel boundary is established before sampling to avoid mistaking fractional programmatic scroll clamping for an ongoing edge oscillation.

Final commercial suite: **60/60 passed**, 1.8 minutes. It retains exact-version review, separate final confirmation, replacement/retirement, focus restoration, keyboard trapping, dirty navigation, stale responses, account switching and retry identities. Six malformed separator literals in test labels were corrected to an explicit Unicode escape; exact rendered-heading assertions were retained, not relaxed.

The existing membership workflow browser runner also passed actual lookup/denial/focus and isolated review/confirmation-retry checks after the CSS fix. No actual role mutation occurred.

Scoped ESLint passed with no errors/warnings. Vite 7.0.6 build passed: 2,196 transformed modules; `envFile:false`, `write:false` preserves operational dotenv and generated-build leftovers. `git diff --check` passed. Graphify queried read-only; its historical graph does not contain all current admin components, so current source and rendered browser evidence are authoritative.

## Artifacts and preservation

New evidence only: `docs/evidence/c15-admin-dialog-scroll-20261106/` contains before measurements, screenshots, recordings, actual results and final `verified-regressions/` artifacts. Earlier failed-run evidence is retained alongside final results. Screenshots include `before.png`, `membership-bottom.png`, `membership-desktop.png`, `recording-frame.png` and commercial popup screenshots in test artifacts.

Test changes: `frontend/tests/c15-admin/dialogScroll.js`, `dialog-scroll.run.mjs`, `dialog-scroll-before.run.mjs`, and focused additions in `frontend/tests/catalog/workspace.spec.js` / `lifecycle.spec.js`.

No new services or databases created. All browser contexts/processes closed; existing website5400/backend8400/Auth19940/Storage15040/PostgreSQL15440/Mailpit8040 remain running for review. No real data, grants, email sends, provider operations, activation, commits or pushes. Historical/protected leftovers were not removed.

Local URL: http://127.0.0.1:5400/auth/admin?view=memberships

Limit: tested local Chromium with desktop/mobile viewport emulation and actual wheel input. Physical touchpad/touch-device overscroll and the unavailable original recording were not independently replayed. Commercial/campaign/billing mutation paths use explicitly isolated fixtures; no actual backend mutation acceptance is claimed from them.
