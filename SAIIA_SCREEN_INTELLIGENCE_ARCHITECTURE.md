# SAIIA Screen Intelligence Architecture

**Product:** SAIIA - Smart AI Interview Assistant  
**Document type:** Screen Intelligence architecture source of truth  
**Version:** 1.1  
**Last updated:** 2026-07-24  
**Status:** Architecture locked for planned C0.9 implementation  
**Owner:** Project developer  
**Related source-of-truth documents:** `SAIIA_PRODUCTION_PRD_CORE.md`, `SAIIA_PRODUCTION_TECHSTACK.md`, `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`, `SAIIA_PRODUCTION_PHASES_TRACKER.md`  
**Implementation status:** C0.9.1 documentation complete; C0.9.2 OCR/Extension menu and one-click multi-question OCR complete; C0.9.3 contracts complete; C0.9.4 operation ownership and reliable active-window targeting complete; C0.9.5 browser extension prototype complete; C0.9.6 Generic Coding-Page DOM Extraction implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, sample/example metadata preservation, explanation pairing, `Prints`/`Returns` output aliases, Input/Output and STDIN/Function table normalization, editor-root and folded-code diagnostics, confidence calibration, false-negative/false-MCQ/false-visual detection fixes, controlled unsupported-content results, and Chrome/Edge real-page validation pending; C0.9.7 onward not started

---

## 1. Purpose

This document defines the final Screen Intelligence architecture before implementation begins. It locks the Analyze Screen user experience, the OCR and Extension source actions, extraction contracts, pairing rules, browser support policy, operation ownership, provider boundaries, and privacy requirements.

Final product rule:

```text
Analyze Screen opens a menu with exactly two actions: OCR and Extension.
OCR reads user-approved visible screen content.
Extension extracts coding problems from the active tab in the paired supported browser after one click.
Both paths return an Extraction Result Envelope containing one or more Normalized Questions.
```

C0.9.2 one-click OCR uses a backward-compatible direct screen-result extension instead of the full C0.9.3 Extraction Result Envelope: one screenshot, one screen-model request, one structured batch response, and one history entry at most.

## 2. Scope

In scope:

- Analyze Screen menu behavior
- OCR source action
- Extension source action
- one-time browser installation, permission, and pairing model
- Chrome/Edge initial support policy
- multiple-browser behavior
- connection and error states
- Extraction Result Envelope
- Normalized Question schema
- question types
- coding submission modes
- language resolution and conflict behavior
- operation timing, history, cancellation, and stale-result rejection
- provider ownership boundaries
- security and privacy requirements
- C0.9 phase placement

Out of scope for this documentation task:

- implementing the browser extension
- implementing the OCR/Extension menu
- implementing the bridge or Native Messaging
- changing backend, frontend, Electron, API, extension, provider, or test code
- installing dependencies
- marking any unimplemented feature complete

## 3. Final Analyze Screen User Experience

Visible menu:

```text
Analyze Screen

OCR
Read visible screen content using screen capture, vision, and OCR.

Extension
Read the coding problem automatically from the active tab in the paired browser.
```

There is no third selection step. The user must not be asked to select Browser Page after clicking Extension, choose the active tab manually, paste the page URL, click the extension icon in the browser every time, select Chrome or Edge on every operation, or grant the same permission again on every extraction.

`Browser Page` may be used only as an internal architectural description when necessary. It must not appear as an additional user action after clicking Extension.

## 4. Menu Side-Effect Rule

Clicking Analyze Screen only opens the menu.

Opening the menu must not:

- capture the screen
- take a screenshot
- contact the extension for extraction
- query the active tab
- inject a content script
- start OCR
- start answer generation
- clear the existing answer
- create an extraction operation
- create a history entry

The menu may display cached last-known status such as Extension connected, Extension disconnected, or Paired browser: Microsoft Edge. A status refresh may check connection health only. It must not query page content, inject the extractor, extract content, or start generation.

## 5. Top-Level Flow

```text
User has coding problem open in supported paired browser
        |
User clicks Analyze Screen in SAIIA Electron floating window
        |
Menu opens: OCR or Extension
   +----+----------------+
   |                     |
OCR                 Extension
   |                     |
Screen/window/     Check paired extension
region capture          |
   |                Extract active tab automatically
Vision/OCR              |
   |                Generic DOM extraction
   +----------+----------+
              |
OCR direct result or future Extraction Result Envelope
              |
One visible answer result
              |
Question classification
              |
Language and submission-mode resolution
              |
Existing answer pipeline
              |
Overlay and history
```

## 6. OCR Action

When the user clicks OCR:

- create one `operation_id`
- create one `request_id`
- start the existing user-approved screen/window/region capture
- capture exactly one screenshot in the C0.9.2 one-click path
- send exactly one normal-path screen-model request in the C0.9.2 one-click path
- detect every fully visible independent quiz, MCQ, aptitude, or general question
- solve every complete independent question in top-to-bottom order in the same response
- ignore incomplete or partially visible question blocks
- for coding pages, solve the single dominant complete coding problem
- preserve the previous valid answer until the new answer succeeds

OCR can process diagrams, charts, graphs, PDFs, images, MCQs, aptitude questions, technical questions, debugging screenshots, output-prediction questions, system-design prompts, architecture diagrams, coding questions, multiple questions visible at once, meeting screen shares, remote desktops, native desktop applications, and browser pages inaccessible to the extension.

OCR is allowed as a coding fallback.

## 7. Extension Action

When the user clicks Extension:

- create one `operation_id`
- create one `request_id`
- identify the paired supported browser
- check extension connection
- send an `extract_active_tab` command
- let the extension service worker query the active tab
- validate the URL and page eligibility
- run the generic coding-page DOM extractor
- return controlled `unsupported_page` for MCQs, code-based MCQs, output-prediction, technical/general, visual/chart/diagram, tutorial/article, and editor-only pages
- return an Extraction Result Envelope
- validate the schema and operation ownership
- continue through the common normalized-question pipeline
- generate the answer
- display the result in Analyze Screen

Required flow:

```text
Analyze Screen
        |
Extension
        |
Check paired extension
        |
Extract active tab automatically
        |
Generic coding-page DOM extraction
        |
Extraction Result Envelope
        |
Normalized question
        |
Answer generation
```

This all begins from one click on Extension. There is no later Browser Page button.

## 8. Browser Installation and Pairing

The extension is installed and paired once with SAIIA.

During setup or pairing:

- the user installs the SAIIA extension
- the user grants browser permission required for active-page extraction
- the extension pairs with the SAIIA desktop app
- the user may select a preferred browser
- SAIIA stores only safe pairing and browser identity metadata
- no page extraction starts during pairing unless explicitly initiated by the user as a connection test

After successful setup, normal Extension operations must not require another browser-side click.

This architecture does not rely only on temporary `activeTab` permission granted by clicking the browser extension icon. Automatic extraction initiated from Electron requires previously granted page access.

Likely implementation direction:

- Manifest V3
- scripting permission
- tabs access only where required
- browser host access granted by the user during setup or pairing
- connected extension service worker
- Electron-to-extension `extract_active_tab` command

Do not finalize exact Manifest permission patterns during this documentation pass. Record exact permission patterns as an implementation decision to verify during C0.9.5.

## 9. Supported Browsers

Initial officially supported browsers:

- Google Chrome
- Microsoft Edge

Architecture target:

- one Chromium Manifest V3 extension codebase where practical

Potential future browsers after explicit compatibility testing:

- Brave
- Opera
- Vivaldi
- other Chromium-based desktop browsers

Do not claim universal browser support. Do not claim Firefox or Safari support initially.

Each supported browser must be installed, paired, permission-approved, and tested separately before SAIIA lists it as officially supported. Each browser-store build may use a different extension ID. Production Native Messaging configuration must allow the exact approved extension IDs for each supported browser/store build.

## 10. Multiple Browser Behavior

The user must not select a browser on every extraction.

During setup or settings, SAIIA may store a preferred paired browser. Normal behavior uses the preferred paired browser and extracts the active tab from that browser.

If the preferred browser is unavailable:

- do not silently inspect another browser
- show a clear reconnect or browser-settings action
- preserve the previous valid answer

If several browsers are paired and no preferred browser is resolved:

- report `browser_ambiguous`
- require setup/settings resolution
- do not ask the user to select a browser during every normal extraction

The exact setup UI remains an implementation decision.

## 11. No Silent Fallback

If Extension extraction fails, SAIIA must not automatically run OCR.

Show:

```text
The coding problem could not be extracted from the active browser tab.
```

Actions:

- Use OCR
- Cancel

OCR begins only after the user clicks Use OCR. Similarly, OCR must not silently switch to Extension. The user always owns the source choice.

## 12. Extension Connection States

Document these states consistently:

- `extension_not_installed`
- `extension_installed_not_paired`
- `extension_connected`
- `extension_disconnected`
- `browser_not_running`
- `browser_ambiguous`
- `permission_not_granted`
- `permission_revoked`
- `requesting_active_tab`
- `restricted_url`
- `unsupported_page`
- `extraction_started`
- `extraction_complete`
- `extraction_incomplete`
- `no_coding_problem_found`
- `connection_lost`
- `operation_cancelled`
- `stale_result_rejected`

Required behavior:

- `extension_not_installed`: show installation guidance.
- `extension_installed_not_paired`: show pairing guidance.
- `permission_not_granted` or `permission_revoked`: show permission setup action.
- `browser_not_running`: ask the user to open the paired browser.
- `browser_ambiguous`: ask the user to resolve the preferred browser in setup/settings.
- `restricted_url`: explain that browser-internal, extension, store, and other restricted pages cannot be read.
- `extraction_incomplete`: offer Use OCR or Cancel.
- `no_coding_problem_found`: preserve the previous answer and show a clear message.

No error may silently start OCR.

## 13. Extraction Result Envelope

Both OCR and Extension return the same Extraction Result Envelope.

```json
{
  "schema_version": "1.0",
  "request_id": "...",
  "operation_id": "...",
  "mode": "screen",
  "source_type": "browser_extension | screen_capture",
  "browser": {
    "name": null,
    "extension_id": null,
    "tab_id": null,
    "window_id": null,
    "url_origin": null,
    "page_title": null
  },
  "status": "ready | selection_required | incomplete | failed | cancelled",
  "questions": [
    {
      "question_id": "question_1",
      "question": {},
      "region": {
        "x": null,
        "y": null,
        "width": null,
        "height": null
      }
    }
  ],
  "selected_question_id": null,
  "extraction": {
    "complete": false,
    "confidence": 0.0,
    "missing_sections": [],
    "warnings": [],
    "method": "generic_dom | screen_vision | local_ocr | combined"
  }
}
```

Rules:

- Extension normally returns one question.
- Future OCR envelope flows may return one or multiple questions.
- One valid future-envelope question may be selected automatically.
- Future selection workflows may use `status=selection_required`.
- C0.9.2 one-click OCR quiz/batch screenshots are the exception: they return one structured batch answer without `selected_question_id`.
- Future-envelope answer generation must not begin until `selected_question_id` is resolved.
- Region coordinates are optional and mainly used by OCR.
- Full raw HTML must not be included.
- Screenshots or crops must not be persisted by default.
- Browser metadata must not include cookies, tokens, storage contents, or unrelated browsing information.

## 14. Normalized Question

Each `questions[].question` must follow a common schema equivalent to:

```json
{
  "question_type": "coding",
  "title": "",
  "statement": "",
  "function_description": "",
  "input_format": "",
  "output_format": "",
  "constraints": [],
  "examples": [
    {
      "input": "",
      "output": "",
      "explanation": ""
    }
  ],
  "options": [],
  "visual_context": {
    "diagram_present": false,
    "chart_present": false,
    "image_context_required": false,
    "visual_description": null
  },
  "code_context": {
    "selected_language": null,
    "language_source": null,
    "starter_code": null,
    "function_signature": null,
    "class_name": null,
    "editor_type": null,
    "platform_mode": null,
    "submission_mode": null
  }
}
```

Do not describe OCR and Extension as two separate extraction systems. The Envelope manages operation-level and multi-question state. The Normalized Question represents one independently solvable question.

## 15. Question Types

Supported normalized question types should include:

- `coding`
- `debugging`
- `output_prediction`
- `mcq`
- `diagram`
- `chart`
- `architecture`
- `system_design`
- `technical`
- `aptitude`
- `general`
- `unknown`

During implementation, Codex must audit the real enums and preserve backward compatibility. Do not break existing category or Answer Plan names. Where existing names differ, document a compatibility mapping rather than silently renaming production values.

## 16. Coding Submission Modes

Language alone is not enough. Planned submission modes:

- `standalone_program`: return a complete runnable program.
- `stdin_full_solution`: return a complete program that follows visible input/output requirements.
- `function_stub`: return only the required function and preserve the exact signature.
- `class_stub`: return the required class/method structure.
- `editor_template`: fill the visible starter template while preserving required scaffolding.
- `explanation_only`: explain the approach without unnecessary replacement code.
- `debug_fix`: correct the visible code in the original language and intended contract.
- `output_prediction`: return and explain the output instead of writing an unrelated program.

The generic extractor should infer submission mode from visible instructions, input/output sections, starter code, function signatures, class signatures, and editor structure. It must not rely only on the platform hostname.

## 17. Coding Language Resolution

Priority:

1. Language explicitly requested in the current question.
2. Explicit manual language override selected in SAIIA.
3. Language selected on the active coding website.
4. Language required by starter code/function/class signature.
5. Previous relevant coding continuation.
6. Preferred coding language saved in setup/settings.
7. Configured fallback language.

Normalize aliases consistently:

```text
Python, Python 3, PyPy3 -> python
Java 8, Java 15, Java 17 -> java
C++14, C++17, GNU C++20 -> cpp
JavaScript, Node.js -> javascript
TypeScript -> typescript
C Language, GCC -> c
C#, C Sharp -> csharp
Go, Golang -> go
```

Do not confuse Java and JavaScript, C and C++, or C# and C++. Do not randomly default to Python.

Conflict behavior:

- explicit language and platform contract agree: proceed
- manual override and platform contract agree: proceed
- explicit language or override conflicts with visible starter code/platform contract: set `conflict=true`, list conflict sources, do not combine languages, do not silently rewrite the platform stub, require user confirmation or explicit force override, and preserve the previous valid answer
- language unresolved: use the saved preferred language only when no stronger source exists

## 18. Generic DOM Extraction

The Extension extractor must be generic. It must not be limited to HackerRank, LeetCode, CodeChef, Codeforces, GeeksforGeeks, InterviewBit, or any other named platform.

Generic extraction should use visible semantic content, headings, labels, candidate container scoring, accessible names, code editor contents where accessible, starter code, function/class signatures, section labels, examples, and math recovery where practical. Optional platform adapters may be added later only as accuracy improvements. Deleting all optional adapters must not make the generic extractor unusable.

The extension must not execute page code or upload complete raw HTML.

## 19. Math and Code Recovery

Extension extraction should recover accessible MathJax, KaTeX, MathML, and LaTeX source where practical. It should detect Monaco, CodeMirror, and Ace where accessible, selected language, visible starter code, function/class signatures, class name, editor type, platform mode, and submission mode.

Extracted code is displayed and normalized. It must never be executed by SAIIA.

## 20. One-Click OCR Multi-Question Behavior

When C0.9.2 one-click OCR detects multiple fully visible independent questions, SAIIA must not merge them into one large question and must not ask the user to select one.

Required flow:

```text
OCR selected
-> capture one approved screenshot
-> send one screen-model request
-> detect complete independent question blocks
-> solve all complete blocks in screen order
-> ignore incomplete blocks
-> return one structured batch response
-> display all answers together
```

This is not parallel Solve All. It creates one operation, one request, one model response, one formatted answer batch, and at most one successful Analyze Screen history entry.

For coding pages, OCR solves the single dominant complete coding problem. It must not treat examples, sample cases, editor content, navigation, discussions, or partially visible secondary problems as separate questions.

## 21. History and Operation Timing

Lifecycle:

Analyze Screen menu opened:

- no operation
- no extraction
- no history entry

OCR or Extension clicked:

- create `operation_id`
- create `request_id`
- create temporary operation state
- no completed answer-history entry

Extraction running:

- previous valid answer remains visible

Multiple questions detected:

- temporary selection state only
- no answer-history entry

Question selected:

- continue the same operation
- do not create another operation
- do not create duplicate history

Answer successfully completed:

- create exactly one Analyze Screen history entry

Operation failed, stopped, or cancelled:

- preserve previous valid answer
- do not create a successful history entry
- reject any late result
- safe operation diagnostics may be recorded separately

## 22. Request Ownership and Cancellation

Every OCR or Extension action must own:

- one `operation_id`
- one `request_id`
- one `source_type`
- one cancellation controller
- one result destination
- at most one successful Analyze Screen history entry

Late results must not replace a newer answer, update another mode, create duplicate history, appear after cancellation, or overwrite a result created by another source.

Cancellation must be idempotent. Starting a newer Analyze Screen operation must make older operation results ineligible to update visible state.

## 23. Common Answer Pipeline Integration

After a question is selected or auto-selected, OCR and Extension use the existing generation pipeline:

```text
Extraction Result Envelope
-> selected Normalized Question
-> classification
-> resume/JD context
-> language and submission-mode resolution for coding
-> answer contract selection
-> configured primary answer provider
-> configured fallback when enabled
-> overlay
-> history
```

The extension does not own AI provider calls, answer generation, subscription checks, usage enforcement, cloud storage, user identity, or session history.

## 24. Provider Boundary

Current-state note:

- final answers currently use the configured backend answer provider
- current records show OpenAI Responses API through `OPENAI_MODEL` as the active final-answer path
- Groq is available as emergency/rollback fallback where enabled
- Analyze Screen uses the configured backend vision provider with local OCR support/fallback
- Auto Mode uses the configured STT/streaming provider
- C0.9 must reuse existing provider services
- C0.9 must not migrate or replace final-answer, STT, or vision models

Do not change environment variables, providers, model configuration, or provider ownership as part of C0.9 documentation or Extension foundation work.

## 25. SaaS and Cloud Integration

Ownership:

- Extension: active-page extraction, DOM normalization, source metadata.
- Electron: user interaction, operation control, local bridge, overlay updates, secure desktop session, preferred paired-browser selection.
- FastAPI backend: authentication, feature gates, source validation, question classification, language resolution, submission-mode resolution, answer generation, usage enforcement, cloud session persistence.
- Supabase/cloud: authenticated user data, settings, preferred coding language, session history, usage and entitlement data.

## 26. Privacy and Security

Extension extraction remains user-triggered and begins only after Analyze Screen -> Extension.

The extension must not:

- continuously inspect tabs
- extract on browser startup
- extract on tab change
- extract when the Analyze Screen menu opens
- read unrelated tabs
- read browser cookies
- read login tokens
- read unrelated local storage or session storage
- extract hidden test cases
- extract hidden solutions
- execute page code
- upload complete raw HTML
- log full private page content by default
- send API keys
- call the AI model directly

The extension may extract only the relevant visible or accessible coding-problem content needed to create the normalized contract.

## 27. Prototype Local Bridge

Prototype communication path:

```text
Electron Analyze Screen -> Extension
-> localhost-only authenticated bridge
-> paired extension
-> active-tab extraction
-> Extraction Result Envelope
-> normalized pipeline
```

The local bridge must be localhost-only, authenticated, schema-validated, and user-action bound. Exact implementation, port, and Electron/FastAPI ownership remain open decisions.

## 28. Production Native Messaging

Production communication path:

```text
Electron Analyze Screen -> Extension
-> Electron main process
-> Native Messaging host
-> extension service worker
-> active-tab extraction
-> authenticated FastAPI backend
-> answer pipeline
-> overlay
-> cloud session storage when enabled
```

Native Messaging is planned, not implemented. The production installer will later register the Native Messaging host. Production configuration must allow exact approved extension IDs for each supported browser/store build.

## 29. Phase Placement and Dependencies

Implementation belongs to C0.9 - Screen Intelligence Source Selection and Browser Extension Foundation in `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`.

C0.9 overall status:

```text
[~] In progress - C0.9.1, C0.9.2, C0.9.3, C0.9.4, and C0.9.5 complete; C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, controlled unsupported-content results, and Chrome/Edge real-page validation pending; C0.9.7 onward not started
```

Subphase status:

- [x] C0.9.1 - Documentation and architecture lock
- [x] C0.9.2 - Analyze Screen OCR/Extension menu, contextual result controls, and optimized one-click multi-question OCR
- [x] C0.9.3 - Extraction Result Envelope and Normalized Question schema
- [x] C0.9.4 - Screen Intelligence orchestrator, request ownership, and reliable active-window targeting
- [x] C0.9.5 - Generic Chrome/Edge extension prototype
- [~] C0.9.6 - Generic Coding-Page DOM Extraction implemented with coding-only scope, editor/starter-code extraction fixes, semantic sample/example grouping, sample/example metadata preservation, explanation pairing, output aliases, Input/Output and STDIN/Function table normalization, editor-root and folded-code diagnostics, confidence calibration, false-negative/false-MCQ/false-visual detection fixes, and controlled unsupported-content results; Chrome/Edge real-page validation pending
- [ ] C0.9.7 - Coding language and submission-mode resolution
- [ ] C0.9.8 - Electron-to-extension local bridge
- [ ] C0.9.9 - OCR multiple-question detection and selection
- [ ] C0.9.10 - Explicit fallback and error states
- [ ] C0.9.11 - Security and privacy hardening
- [ ] C0.9.12 - Regression and manual validation
- [ ] C0.9.13 - Production Native Messaging planning

Dependencies:

- existing C0 critical stability work remains protected
- mode isolation is stable
- Analyze Screen persistence exists
- request/stale-response ownership exists or is audited
- current OCR path is preserved
- current generation pipeline is preserved

## 30. Rollback Strategy

If C0.9 implementation becomes unstable, rollback must preserve the existing OCR baseline, current generation pipeline, Analyze Screen persisted-result behavior, mode isolation, and request ownership protections. Extension can be disabled behind feature gating without deleting OCR.

## 31. Known Limitations

- Extension implementation has not started.
- OCR/Extension menu implementation is complete for the current frontend flow.
- C0.9.4 operation ownership and reliable active-window targeting are complete.
- Local bridge implementation has not started.
- Native Messaging is not implemented.
- Chrome and Edge are the initial official browser targets only.
- Generic DOM extraction cannot guarantee every platform or page shape.
- OCR extraction accuracy depends on image quality and layout.
- OCR answers every fully visible independent question in one screenshot and one screen-model request; broader Extension extraction remains future work.

## 32. Future Enhancements

- optional platform adapters as accuracy improvements
- future sequential Solve All after cost, latency, and UI controls are designed
- Brave, Opera, Vivaldi, and other Chromium browser support after validation
- browser-store publication
- signed Native Messaging installer registration
- richer diagram/chart reasoning

## 33. Open Decisions Register

Open decisions that do not block documentation completion:

- exact extension store name
- exact Chrome extension ID
- exact Edge extension ID
- exact Manifest host-permission pattern
- whether host permission is broad at install or requested during pairing
- exact Native Messaging host executable
- exact local bridge implementation
- exact local bridge port
- whether the prototype bridge is owned by Electron or FastAPI
- pairing-token format
- preferred-browser setup UI
- behavior when several browsers are paired
- exact extension reconnect mechanism
- exact maximum detected-question count
- extraction confidence thresholds
- payload-size limits
- exact browser-extension publication phase
- future sequential Solve All support
- exact user-confirmation UI for language/starter-code conflicts

## 34. Acceptance Criteria

This architecture is accepted when:

- Analyze Screen shows only OCR and Extension
- clicking Extension immediately requests active-tab extraction from the paired browser
- no third Browser Page selection exists
- no tab picker is used in the normal flow
- extension permission and pairing occur during setup
- Chrome and Edge are initial official targets
- OCR remains available for coding fallback
- no silent fallback exists
- C0.9.2 one-click OCR multi-question screenshots use one structured batch response
- fully visible independent OCR questions are all answered in screen order
- C0.9.3 contracts are complete
- coding submission mode is represented
- language conflicts are handled safely
- previous valid results are preserved
- stale results cannot overwrite newer results
- provider documentation reflects the current architecture
- roadmap and tracker agree
- C0.9 is in progress because C0.9.1-C0.9.5 are complete, C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, and Chrome/Edge real-page validation pending, and C0.9.7 onward has not started
- C0.9.1 is complete
- C0.9.2 is complete
- C0.9.3 contracts are complete
- C0.9.4 operation ownership and active-window targeting are complete; C0.9.5 browser extension prototype is complete; C0.9.6 Generic Coding-Page DOM Extraction is implemented with coding-only scope, editor/starter-code extraction fixes, and controlled unsupported-content results; C0.9.7 onward remains unimplemented
- no source code changes are made for this documentation task
- no feature is falsely marked complete

## Decision Log

### 2026-07-23 - Adopt dual-source Screen Intelligence

**Decision:** Adopt a dual-source Screen Intelligence architecture.

**Reason:** OCR is unreliable for structured browser coding problems, DOM extraction preserves semantic structure, the extension cannot access meeting screen shares/images/PDFs/remote desktops/inaccessible visual content, OCR remains necessary, explicit user source selection avoids surprising behavior, and common contracts prevent two separate generation systems.

**Final decision:** explicit OCR or Extension choice, generic extension, OCR fallback, no silent fallback, Extraction Result Envelope, and Normalized Question.

### 2026-07-23 - Analyze Screen exposes OCR and Extension as the only two user actions

**Decision:** Analyze Screen exposes OCR and Extension as the only two user actions.

**Extension behavior:** One click on Extension automatically extracts the active tab from the paired supported browser. There is no third Browser Page selection.

**Reason:** The active coding tab is already open, repeated tab selection adds unnecessary friction, pairing and permission happen during setup, each extraction is still explicitly user-triggered from SAIIA, and the extension does not continuously monitor browser content.
