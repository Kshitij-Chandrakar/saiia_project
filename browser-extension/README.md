# SAIIA Browser Extension Prototype

This is the C0.9.5-C0.9.6 development prototype for the SAIIA Chrome/Edge extension.

It proves an installable Manifest V3 extension can request page access, run a service worker, inject a content script on an explicit development test action, extract controlled coding-page DOM content, and return a structured Extraction Result Envelope.

## Scope

Implemented in C0.9.5:

- Manifest V3 extension shell
- service worker
- popup/options development UI
- explicit optional host permission setup
- one development-only active-tab extraction test
- generic DOM extraction on controlled fixtures
- Normalized Question and Extraction Result Envelope compatible payloads
- Chrome/Edge sideload instructions
- static and unit tests

Implemented in C0.9.6:

- platform-agnostic active-tab coding-problem discovery
- semantic section extraction beyond plain heading tags
- optional input/output/constraints/examples handling
- coding-task completeness evaluation
- unsupported-content rejection for MCQs, code-based MCQs, output-prediction, technical/general, visual/chart/diagram, article/tutorial, and editor-only pages
- generic visible code and editor-line extraction
- editor presence tracked independently from readable starter-code availability
- generic starter-code extraction from accessible Monaco, Ace, CodeMirror, native textarea, and contenteditable editor DOM
- honest `editor_code_unavailable` warning when an editor is detected but readable code is unavailable
- generic split coding workspace handling that combines complementary problem and editor panes
- false-negative coding-scope protection for valid coding pages that expose equivalent statement, starter-code, signature, class, or editor fields
- false-MCQ protection so raw list, label, navigation, language, and control candidates cannot reject valid coding pages
- false-visual protection so decorative SVGs, logos, images, and canvas-backed editors cannot force coding pages to OCR
- nested/duplicate candidate collapse before ambiguity decisions
- generic problem-title ranking with numbered-title support
- contextual example parsing so example input/output stays inside examples
- normalized `examples` array preserves official Sample/Example/Test Case kind, original label, and numeric index
- official sample/example input-output pairs stay ordered while custom input, run output, console output, and test-result panels are excluded
- semantic example/sample parsing normalizes ordered blocks before grouping, so child `Input`/`Output`/`Explanation` labels attach to the correct parent sample/example
- official Input/Output and STDIN/Function tables normalize into `question.examples` without creating orphan `unknown` entries
- final extraction-quality pass: standalone explanations attach to their sample/example, duplicate unknown example fallbacks are removed, `Prints`/`Returns` are output-contract aliases, STDIN/Function sample tables normalize to STDIN, canonical editor roots are counted once, folded editor DOM reports `editor_code_may_be_partial`, and confidence is capped below perfect when warnings exist
- validated option groups used only to reject non-coding content
- bounded DOM-readiness wait
- safe extraction diagnostics in the popup preview

Not implemented in C0.9.5:

- Electron connection
- localhost, WebSocket, HTTP, or Native Messaging bridge
- extension pairing
- production active-tab extraction from SAIIA
- answer generation
- OpenAI/Groq/provider calls
- platform-specific HackerRank/LeetCode adapters

## Install In Chrome

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select this `browser-extension` directory.
5. Open a controlled fixture or safe test page.
6. Open the extension popup.

## Install In Edge

1. Open `edge://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select this `browser-extension` directory.
5. Repeat the same popup and fixture checks used in Chrome.

## Permission Model

Required permissions:

- `scripting`: inject the content script only when the development test action is clicked.
- `storage`: store safe setup/status metadata only.

Optional host permissions:

- `http://*/*`
- `https://*/*`

The user grants host access through the popup button. Installation alone does not start extraction. Opening the popup does not request permission or extract content. Granting permission does not extract content.

The prototype intentionally does not request cookies, history, bookmarks, downloads, webRequest, debugger, management, clipboard, browsingData, topSites, or tabs.

## Development-Only Test Flow

1. Open a test page or fixture.
2. Open the extension popup.
3. Click Grant Page Access.
4. Click Check Permission.
5. Click Test Active Tab Extraction.

The browser icon test action is temporary for C0.9.5. The final production flow will be started from SAIIA after later pairing/bridge phases.

Supported pages return a coding envelope only. Non-coding pages return a controlled unsupported result and instruct the user to use Analyze Screen OCR. The extension never silently starts OCR.

## Privacy Rules

The extension must not:

- store complete extracted questions
- store answers
- return raw HTML
- read cookies, history, localStorage, or sessionStorage
- execute page code
- submit forms or click page buttons
- call SAIIA backend
- call model providers
- include URL paths, queries, or fragments in envelope metadata

The envelope includes origin-only URL metadata and bounded structured strings.

## Directory Structure

- `manifest.json`: MV3 manifest
- `service-worker.js`: extension lifecycle, permission checks, active-tab test action
- `content-script.js`: isolated-world DOM extraction
- `popup/`: development setup and test UI
- `options/`: development status page
- `core/`: message, permission, ID, state, and limit helpers
- `extractors/`: generic fixture extractor used by tests
- `schemas/`: JavaScript envelope/question compatibility helpers
- `fixtures/`: original controlled local test pages
- `tests/`: Node test suite

## Commands

From this directory:

```powershell
npm run validate
```

This runs syntax checks and focused tests. No dependencies are required beyond Node.

## Known Limitations

- Chrome and Edge sideload validation passed manually during C0.9.5 closure.
- Generic coding extraction is still heuristic and platform-agnostic; split coding layout, title ranking, semantic sample/example block grouping, sample/example metadata preservation, explanation pairing, table normalization, runtime-panel exclusion, example/format separation, `Prints`/`Returns` output aliases, canonical editor-root counting, folded-code diagnostics, confidence calibration, coding-only scope checks, accessible editor-code extraction, false-negative coding detection, false-MCQ rejection protection, false-visual rejection protection, option-group rejection, and candidate-diagnostic tests pass. Chrome/Edge real-page validation remains pending for C0.9.6.
- Closed shadow-root editors, cross-origin iframe editors, and platform-specific extraction adapters are later work.
- Desktop connection remains `not_implemented`.

## Final Production Flow

The future production flow remains:

```text
Analyze Screen -> Extension -> paired browser extension extracts a coding problem from the active tab -> SAIIA receives envelope -> SAIIA generates/displays the code answer
```

That flow is not connected in C0.9.5.

Unsupported flow:

```text
Analyze Screen -> Extension -> no coding problem detected -> user explicitly chooses OCR for other question types
```
