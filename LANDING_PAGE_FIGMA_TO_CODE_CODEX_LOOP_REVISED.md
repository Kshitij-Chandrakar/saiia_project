# Codex Loop: Implement the Figma Landing Page Exactly in the Existing Frontend

Use this prompt loop in Codex with the `saiia_project` repository open. It is designed to be run in repeated passes until the public website landing page matches the referenced Figma design and the in-scope checks pass.

This loop is strict because the landing page must match Figma closely. Codex must not redesign, simplify, rewrite, or “improve” the page unless the user explicitly approves it.

---

## Fixed design reference

- Figma file: `AjlJbD9X8xHbGUtRcUdXrf`
- Target node: `173:2428` (`Desktop - 1`)
- Reference URL: https://www.figma.com/design/AjlJbD9X8xHbGUtRcUdXrf/SAIIA--Smart-AI-Interview-Assistant?node-id=173-2428&m=dev
- The target is a long desktop landing page. Inspect the full page and every child section; do not implement only the first viewport.
- The Figma design is the visual source of truth for layout, images, icons, vectors, typography, spacing, colors, section order, pricing, privacy/security copy, and interactions.
- Do not invent copy, sections, destinations, product claims, pricing behavior, animation behavior, or responsive behavior where the design/repository does not define them.

---

## Locked user decisions

These decisions are already approved by the user and must not be reopened unless the Figma file itself contradicts them in a specific element.

1. Public website brand text should follow Figma and use `Intervucopilot` where that is what the Figma shows.
2. Do not normalize all visible text to `Intervu AI`.
3. Keep internal repository/docs names such as `SAIIA` unchanged. Do not rename internal files or docs.
4. Copy Figma pricing section from Figma. Do not replace it with “Coming soon” or “Early access.”
5. Copy Figma security/privacy section from Figma. Do not rewrite those claims in this implementation pass.
6. Treat `(attach video here)` as a design placeholder. Do not show that text on the live website.
7. This implementation is for the public website landing route only.
8. `/` must show the Figma landing page.
9. `/desktop` must show the Electron desktop app/main window.
10. `/auth/*` routes must continue working.
11. Electron main window must load `/desktop`, not `/`.

---

## Hard boundaries

Allowed to change only when needed:

- `frontend/src/landing/LandingPage.jsx`
- `frontend/src/landing/LandingPage.css`
- `frontend/src/assets/landing/*`
- `frontend/src/App.jsx` only for route wiring
- `frontend/electron/main.cjs` only to preserve Electron loading `/desktop`
- `frontend/src/startup_login_screen.test.js` only to preserve route-regression expectations

Do not change:

- backend code
- Supabase migrations
- Resend/email logic
- marketing email logic
- auth logic, except preserving existing auth routes in `App.jsx`
- dashboard logic
- provider/model logic
- Electron desktop runtime UI
- overlay UI
- unrelated docs

If any change outside the allowed list seems required, stop and ask the user first.

---

## Important current-state rule

Before editing, Codex must check the working tree.

If there are unrelated modified or untracked files, Codex must preserve them and must not run broad cleanup commands.

Required first commands:

```powershell
git status --short
git diff --check
```

Do not run unrestricted commands like:

```powershell
git clean -fd
```

Only remove files by explicit path after showing the user exactly what will be removed.

---

## Prompt 1 — Inspect, recover route safety, and plan only

```text
Inspect and plan the exact Figma landing page implementation. Do not edit files in this pass.

Figma URL:
https://www.figma.com/design/AjlJbD9X8xHbGUtRcUdXrf/SAIIA--Smart-AI-Interview-Assistant?node-id=173-2428&m=dev

Target:
- Figma file key: AjlJbD9X8xHbGUtRcUdXrf
- Node: 173:2428 / Desktop - 1

Goal:
Implement the public website landing page so it matches Figma as closely as possible.

Critical route behavior:
- `/` must show the landing page.
- `/desktop` must show the Electron desktop app/main window.
- `/auth/*` routes must keep working.
- Electron must load `/desktop`, not `/`.

Before editing:
1. Inspect git status and preserve unrelated user changes.
2. Inspect repository instructions such as AGENTS.md if present.
3. Inspect frontend routing and entry points.
4. Inspect current Electron route separation.
5. Inspect current landing implementation if present.
6. Inspect package scripts and installed UI/animation/icon dependencies.
7. Inspect existing brand and landing assets.
8. Use Figma MCP/design-to-code workflow to inspect node 173:2428.
9. Request a full-page screenshot for node 173:2428.
10. Retrieve high-fidelity context for each visible child section if the first result is sparse.
11. Inspect text, spacing, colors, typography, shadows, borders, radii, imagery, icons, vectors, components, and section order.
12. Read motion/prototype context for animated nodes. Do not invent motion specifications.

Locked user decisions:
- Use `Intervucopilot` where Figma shows it.
- Do not normalize all visible branding to Intervu AI.
- Copy Figma pricing from Figma.
- Copy Figma security/privacy copy from Figma.
- Do not show `(attach video here)` on the live site.
- Keep internal SAIIA docs/files unchanged.

Asset requirements:
1. Inventory every visible icon, logo, illustration, vector group, decorative shape, raster image, badge, footer graphic, and mockup.
2. Identify exact Figma layer/node when possible.
3. Identify export format: SVG for native vectors/icons, PNG/WebP only for raster artwork.
4. Do not replace Figma icons with generic icon-library icons.
5. Do not replace Figma artwork with screenshots of the whole page.
6. Do not use emoji replacements.
7. Do not use generated images.
8. Store final assets locally under `frontend/src/assets/landing/`.
9. Do not leave temporary Figma asset URLs in code.

Animation requirements:
1. List every Figma prototype interaction/motion found.
2. Include trigger, target, easing, duration, and loop behavior when available.
3. If MCP does not expose exact details, mark it as `needs manual Figma preview confirmation`.
4. Do not invent animations silently.

Return a short but complete plan:
- current route/entry point state
- whether `/` and `/desktop` are currently separated correctly
- exact Figma section list in order
- asset export checklist
- animation checklist
- files that will be changed
- validation commands
- blocking questions only

Do not edit files in this pass.
```

---

## Prompt 2 — Build static Figma parity first

Run this only after Prompt 1 is approved.

```text
Proceed with the approved plan for Figma node 173:2428.

Implement static visual parity first. Do not add complex animations yet unless the static layout requires a control structure such as tabs, accordions, or sliders.

Goal:
Match the Figma landing page closely at the intended desktop width.

Route requirements:
- `/` shows the public Figma landing page.
- `/desktop` shows the Electron desktop app/main window.
- `/auth/*` routes keep working.
- Electron main process continues loading `/desktop`.

Brand/copy requirements:
- Use visible Figma text exactly.
- Use `Intervucopilot` where the Figma says `Intervucopilot`.
- Copy pricing from Figma.
- Copy privacy/security copy from Figma.
- Do not show `(attach video here)`.
- Do not invent extra copy.
- Do not simplify or rewrite section text.

Asset requirements:
- Export every visible static icon/image/vector that lacks an exact local equivalent.
- Preserve original appearance, aspect ratio, crop, and placement.
- Use SVG for vector assets where possible.
- Use raster formats only for raster artwork.
- Store assets locally in `frontend/src/assets/landing/`.
- Use semantic filenames and accessible alt text.
- Use empty alt text for decorative images.
- Do not use temporary Figma URLs in code.
- Do not approximate Figma assets using CSS, emojis, generic icon libraries, or generated images.

Section requirements:
Rebuild sections in exact Figma order. Confirm these are present if shown in Figma:
- hero/navbar
- problem/video card area
- trusted by candidates/company logo marquee structure
- workflow/architecture diagram section
- feature tab/slider section
- product showcase/dashboard mockup
- preparation workflow slider section
- dedicated desktop app section
- privacy/security section
- pricing section
- FAQ collapsed rows
- CTA section
- footer

Implementation rules:
- Keep CSS scoped under landing-specific classes.
- Do not globally affect auth or Electron screens.
- Do not modify backend, email, migrations, provider, dashboard, or desktop runtime logic.
- Do not modify Electron UI; only route loading separation is allowed.
- Do not commit automatically.

Validation:
Run the repository’s relevant frontend checks, including:
- `git diff --check`
- frontend production build
- focused routing/startup tests if available

Manual verification to report:
- `/` shows the landing page.
- `/desktop` shows the Electron desktop app/main window.
- `/auth/login` still works.
- landing assets load from local project files.
- no temporary Figma URLs remain.
- no unrelated files were changed.

Report:
- files changed
- assets exported
- sections completed
- any static mismatch that remains
- validation commands and results
```

---

## Prompt 3 — Add Figma interactions and animations

Run this only after static visual parity is acceptable.

```text
Add Figma-defined interactions and animations to the landing page.

Do not change the static visual design except where required for interaction states.

Use only Figma prototype/motion metadata, user-approved behavior, or clearly visible Figma preview behavior.

Implement these only if they are defined or visible:
- company logo marquee
- workflow node state/smart-animate behavior
- feature tab/slider behavior
- preparation workflow slider and arrows
- FAQ collapsed row behavior
- hover/focus states
- any other Figma-defined interaction discovered through MCP

Rules:
- If exact timing/easing/keyframes are available, reproduce them.
- If only partial details are available, implement the closest equivalent and report exactly what was approximate.
- If behavior is unclear, ask the user instead of inventing.
- Respect `prefers-reduced-motion`.
- Ensure keyboard access and visible focus states.
- Do not add a heavy animation dependency if CSS or existing dependencies can handle the behavior.
- Do not modify backend, email, auth logic, dashboard logic, Electron UI, or provider logic.

Validation:
- exercise every visible control with mouse and keyboard
- check reduced-motion mode
- run frontend build/tests
- run `git diff --check`

Report:
- animations/interactions implemented
- approximated behaviors and why
- behaviors still needing manual Figma preview confirmation
- validation results
```

---

## Prompt 4 — Visual comparison and correction loop

Repeat this prompt after each correction pass.

```text
Audit the implemented landing page against Figma node 173:2428.

Start the app using the repository’s documented command and capture the page at the same viewport width as the Figma desktop frame, 1440 px wide. Also check any responsive viewport explicitly represented in Figma.

Compare section by section from header through footer:
- section order
- copy
- overall page height
- container widths
- alignment
- spacing
- type scale/weight/line-height
- colors
- gradients
- borders
- radii
- shadows
- image/icon identity
- image crop/size/position
- decorative vectors
- pricing cards
- privacy/security cards
- footer content
- responsive wrapping where defined
- interactions/animations where defined

Verify:
- every visible asset has a local file
- each asset is rendered in the correct slot
- no temporary Figma URL remains
- no console errors
- no broken asset requests
- `/desktop` still shows Electron app
- `/auth/login` still works

Fix concrete in-scope mismatches only.
Do not “improve” the design.
Do not rewrite copy.
Do not substitute assets.
If a mismatch depends on unclear Figma detail or undefined behavior, ask the user and continue with independent fixes.

Re-run relevant checks and capture a fresh screenshot after changes.

Summarize remaining differences with exact section/element and reason. Do not report a pass while known in-scope mismatches remain.
```

---

## Prompt 5 — Final acceptance pass

```text
Perform the final acceptance check for the Figma landing page at node 173:2428.

Confirm:
1. The complete page is present, not only the first viewport.
2. Header, all sections, CTA areas, and footer follow Figma order.
3. Visible brand/copy matches Figma and approved decisions.
4. `(attach video here)` is not visible on the live site.
5. Pricing section matches Figma.
6. Privacy/security section matches Figma.
7. All static assets are local, correct, and not distorted.
8. All defined links and controls work.
9. Keyboard focus is visible.
10. Reduced-motion behavior exists for moving/looping animations.
11. No console errors exist.
12. No broken asset requests exist.
13. No temporary Figma URLs remain.
14. `/` shows landing page.
15. `/desktop` shows Electron desktop app/main window.
16. `/auth/login` still works.
17. `git diff` is limited to landing page, landing assets, route separation, and necessary tests.
18. `git diff --check` passes.
19. Frontend build/checks pass.

If anything fails, fix it and repeat the failed checks.

Then provide a concise completion report:
- changed files
- assets added
- checks run
- validation results
- unresolved design questions
- remaining differences, if any

Do not commit or publish unless the user explicitly asks.
```

---

## Repeat loop

1. Run Prompt 1 and resolve only blocking questions.
2. Run Prompt 2 after the plan is approved.
3. Review the browser output before adding complex animation.
4. Run Prompt 3 for interactions and animation.
5. Run Prompt 4 repeatedly until no known in-scope visual/functional mismatch remains.
6. Run Prompt 5.
7. Stop only when acceptance checks pass or clearly identify what is blocked and why.
