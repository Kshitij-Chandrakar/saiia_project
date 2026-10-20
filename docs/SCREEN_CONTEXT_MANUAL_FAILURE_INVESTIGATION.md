# Analyze Screen first-attempt / Continue investigation

Status: the provider-schema/semantic-contract gap described below is fixed and verified with mocked boundary tests. Exact values from earlier failing model outputs were not retained; live model acceptance remains pending. Phase 4 has not started. No live provider call, native screenshot capture, migration, dependency installation, or commit was performed for this investigation.

## Output-contract correction (2026-10-19)

The latest supplied evidence establishes successful capture registration and Continue arriving with two images, one evidence turn and revision 1, followed by provider completion without refusal/truncation. These attempts are output-contract failures, independent of the earlier native capture failures.

Exact rejecting predicates in `ScreenContextOutput.combinations()`:

- `screen_output_evidence_complete`: evidence has already passed strict typing/presence validation, but `evidenceDelta.complete != (outcome == 'answered')`. This can mean answered/false or reference_accepted or needs_more_content/true. The code alone does not identify which combination occurred.
- `screen_output_evidence_presence`: `(evidenceDelta is not None)` differs from whether the outcome is answered/reference_accepted/needs_more_content. This can mean null evidence on a committable outcome or an evidence object on clarification/failure. It is not proof of a missing JSON key or wrong type; those fail field validation first.
- `response_contract invalid_output / outcome`: `reference_accepted` with action other than reference, or answered/needs_more_content with action reference. On a correlated Continue request this necessarily means reference_accepted was returned. The guard uses action, not contextKind. Existing backend and Electron code already permit answered/needs_more_content for Continue over reference context.

Root contract gap: strict provider structured output was configured, but the broad exported schema allowed all five outcomes for every action, independently nullable evidence, and either boolean complete value. Python after-validators enforced combinations not represented in that schema. Thus schema-valid completed output could fail semantic or action validation. Prompt wording also mixed reference storage and reference-context answering without expressing the outcome matrix in the provider schema.

Fix:

- `ScreenContextProviderOutput.schema_for_action()` derives nested outcome branches from canonical model definitions. Reference allows reference_accepted/needs_clarification/failed; New and Continue allow answered/needs_more_content/needs_clarification/failed. Each committable branch requires a genuine evidence object, with complete=true only for answered. Other branches require evidenceDelta=null. Items, missing details, conflicts and clarification are constrained by outcome.
- The provider-only JSON envelope is `{ "result": <outcome object> }`, enabling nested anyOf while retaining the required object root. `text.format` still uses strict JSON schema in the same Responses SDK/model call. The parser validates the envelope then applies the existing semantic checks; response adaptation still checks hashes, replacements, targeting and action. No flat-output fallback was added. External backend/Electron contracts remain version 1 and unchanged.
- Trusted instructions now state that action selects the current task, contextKind only describes retained material, and Continue over reference may answer. They explicitly distinguish combined-question completeness from a fully captured passage and list the same outcome/evidence matrix as the schema.
- The backend response model revalidates outcome semantics and controller-payload agreement. Controller evidence is never synthesized for non-committable outcomes; evidence-only commits omit answer as before.
- Failure diagnostics now report an allowlisted outcome plus field presence/type only; action/outcome rejection has reason `action_outcome_mismatch`. They never log evidence, prompts, answers, images, credentials or full responses.

Verification includes 107 contextual tests (actual multipart → mocked provider JSON → parser/semantic checks → backend serialization → real Electron validation/controller commit), schema assertions for each action, every observed mismatch direction, valid incomplete continuation, and frozen retry after invalid evidence. Initial and retry model calls are asserted identical in logical input, instructions, schema and budget. Forty controller/execution Node tests pass. Live model adherence and actual native capture require manual acceptance.

Official support reference: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) documents object roots, nested anyOf and strict JSON schemas. Installed SDK 1.97.1 accepts strict text.format schemas. No SDK/provider change was required.

Manual retest: restart/reload the backend (Electron contract is unchanged), start a fresh screen context, save a readable Passage / Data capture, then Continue with a related question. Expected revisions/counts: reference 1/1 without history answer, answered continuation 2/2 with one answer. Check New → answered separately, and a split question → More content needed → Continue. On failure retry the retained screenshot once without recapture; count/revision must advance at most once. Copy only the tagged `screen_context validation` line plus matching request/provider/backend lines if it still fails. It now includes outcome and field presence/type, so a failure can be interpreted without guessing its direction. No automatic retry, evidence fabrication, boolean coercion, budget/timeout increase, or validation bypass was introduced.

## Live evidence update: provider-output cross-field rejection

The later reference screenshot showed a valid `needs_clarification` response asking what to do with the passage. That is an unnecessary task question: reference intent already specifies saving source evidence. The prompt had a generic "uncertain intent clarifies" instruction and placed the actual selected action only in the untrusted source JSON. The service now states the validated action/context kind in trusted instructions and adds an active reference-only task explicitly forbidding requests to choose summarization, question generation, etc. Source ambiguity may still clarify and never commits. Continue does not receive the active save-only task. Mocked provider-boundary tests verify this instruction routing; real model adherence still needs a live retest. This prompt correction does not establish or resolve the separate `invalid_output` predicate.

The supplied backend logs correlate with the Electron attempts and establish that New attempts and the clarified reference retry completed at the provider with no refusal/incomplete reason, then failed `ScreenContextOutput` validation at `<root>` with `value_error`. This is before backend response adaptation or Electron/controller validation. The first reference attempt validly returned `needs_clarification`; it did not save evidence. No Continue attempt appears in this sequence. The separate early capture failures remain distinct.

The root diagnostic was ambiguous because three checks in `combinations()` used plain `ValueError`: outcome-field compatibility/blank content, consecutive item numbering, and coding code/language requirements. These now emit static `screen_output_*` error types with safe mapped field paths. No rejected content or exception messages are logged. The accepted/rejected outcome combinations remain identical; a 240-combination check and individual HTTP/provider diagnostic tests protect that behavior. The exact live predicate still requires one reproduction after the backend reloads this refinement. Copy the `screen_context validation` line; it will now name the specific rule, for example `screen_output_coding_language_missing` at `items.[].language`. Do not infer that example was the observed cause.

## Findings

- Later supplied attempts `487c4e9f...` and `8dd31eb1...` stop at capture: no usable recent target, fallback `active_window_ambiguous`, no registered image, no upload and no captured retry. `createActiveWindowNotIdentifiedError()` already supplied a safe code, but contextual execution discarded it into `unclassified_error` / generic `request_failed`. Execution now preserves `active_window_not_identified`, logs only an allowlisted capture reason, and the renderer advises focusing the passage/question window before explicit OCR. No target-selection guard, freshness limit, or automatic capture behavior changed. 562 Node tests, eight mocked Playwright tests (including capture-failure recovery), and the frontend build passed. Native foreground detection still needs a Windows retest: focus the external target for a few seconds, open the chooser with Ctrl+Shift+Enter, select the intent, and explicitly click OCR promptly. The existing target freshness ceiling is 30 seconds.

- Reported symptoms: New fails then retry answers; Passage / Data fails then retry accepts reference; Continue after reference fails on both attempts. These observations do not establish a shared cause, truncation, or a serialization defect.
- `screen_context_execution.cjs` `run()` captures and registers the candidate only when `needsCapture` is true. `retry()` calls `retryTurn()` and launches with false. Both paths use `prepareRequest()` → `multipart()` → authorization → the same endpoint → `validateResponse()` → the same commit branches.
- The controller freezes image/evidence/answer input before transport. Ordinary retry preserves the turn, operation, thread, generation, revision, action, context kind, selections, clarification and input, changing only request ID. Multipart boundaries also change. Clarification resolution intentionally changes its bound clarification/selection sidecars.
- Reference acceptance stores `{text, complete:false, imageHash, turnId}`. The next request's `SourceEvidence` accepts exactly those fields. The current candidate is distinct from accepted context until commit. Manifest roles are derived from accepted evidence/current hash; matching captures legitimately use one `prior_current` image rather than duplicate bytes.
- A persistent-controller integration test now verifies the actual multipart bytes through FastAPI parsing, mocked SDK output, backend response serialization, Electron validation and controller commit. First New, first reference, reference → Continue → Continue, and a failed attempt → frozen retry all pass. Continue includes the retained reference image/evidence, one distinct current image, chronological answers, matching revision, and valid item bindings.
- Provider non-completion/refusal, strict output parsing, response adaptation, Electron envelope/identity validation, controller commit and renderer display remain separate failure boundaries. HTTP 200 may contain a non-committable failed outcome.
- The visible generic error comes from `ScreenContextStatus` when `phase === 'failed'` and its error code has no specific UI message. A backend `failed/invalid_output` is propagated by execution's non-committable `backend_outcome` branch through `controller.fail({retryable:true})`. That is a known route to the message, not proof that all three current failures take that route.

## Demonstrated diagnostic defects fixed

1. Backend diagnostics previously required a separate environment opt-in; normal development Electron did not enable them. Development Electron now sends a fixed diagnostics header. Only a loopback peer can activate it automatically, scoped to the current request with a reset in `finally`. Packaged Electron sends no header. Explicit existing environment opt-in remains available for backend-only investigation.
2. Application INFO logging is not reliably visible with default Uvicorn logging. Enabled safe diagnostic lines now use at least WARNING severity.
3. Request-schema failures previously discarded the validation details. They now log sanitized error types and field paths, never Pydantic inputs/messages/context or unknown field names. Provider-output versus response-contract validation has a stage marker.
4. Electron validation previously collapsed all contract rejections to `invalid_response`. Static field paths now identify identity, metrics, evidence references and controller payload rejection. Commit failures include a safe commit rejection code. Prepared-request lines include intent, retry flag, revision and counts only.

No application failure was hidden by automatic retry, a larger budget/timeout, relaxed evidence validation, or legacy fallback. There is no evidence yet supporting such a change.

## Changed files in this investigation

- `frontend/electron/main.cjs`: enable diagnostics for development execution only.
- `frontend/electron/screen_context_execution.cjs`: fixed development header, prepared counts, safe validation paths and commit reason.
- `backend/app/api/screen_context.py`: loopback request-scoped diagnostics and sanitized request validation.
- `backend/app/services/screen_context_service.py`: visible diagnostic severity, extended safe path allowlist, stage/count/adapter diagnostics and missing semantic validation paths.
- `frontend/src/screen_context_execution.test.js`: development/packaged wiring, frozen whole logical request, safe field-path assertions.
- `backend/tests/test_screen_context.py`: persistent real-JS / actual FastAPI multipart roundtrip, automatic scoped logging, remote-header exclusion and truncation privacy checks.

## Verification

- 561 frontend Node tests passed, including retry, replacement, cleanup, stale ownership and history fencing.
- 72 contextual backend tests passed. The focused combined backend run also passed the existing 67 legacy Screen/auth checks (137 tests before adding the final two diagnostics checks).
- Seven Playwright Chromium tests passed using real React main/overlay views with mocked native capture/provider boundaries. These verify passive choices, reference continuity/replacement, cancellation/retry, history and cleanup. They are not live Electron/model acceptance.
- Frontend Vite build, Electron syntax checks and `git diff --check` passed. Existing Vite chunk-size and Python SWIG deprecation warnings remain.
- Graphify queried and updated before/after code changes. Direct source inspection was used for CommonJS boundaries.

## Manual retest / exact diagnostic request

Restart both backend and Electron to load these changes. Restart clears temporary screen context and retained retry candidates, so reproduce from a fresh session. Use the normal backend launch and `npm run electron:dev` in `frontend`. No DevTools or environment edits are needed when Electron reaches the backend over loopback.

1. Show a readable complete question in the external target window. Choose New question → OCR once. If it fails, click Retry captured screenshot once without restarting. Record whether the accepted count advances once.
2. Choose Passage / Data → OCR on readable reference material. If it fails, retry once. Successful acceptance shows Reference saved and count 1, without adding answer history.
3. Show a question about that reference. Choose Continue previous question → OCR. If it fails, retry once without recapturing. Success advances count to 2; failure must retain the valid reference/count 1 and previous displayed answer.
4. While a request runs, execute New or reference replacement, then end/switch session. Retired responses must not commit or restore context/history.

Copy only these tagged lines for each failed attempt and its retry:

- Backend terminal: `screen_context request`, `screen_context provider`, `screen_context validation`, `screen_context backend`.
- Electron terminal: `[screen-context]` and `[screen-context-status]`.

Include both attempts and the reference-save sequence preceding Continue. Lines contain application attempt identifiers, statuses, safe validation types/paths, booleans and counts only. Do not copy full terminal output, HTTP bodies, source content, answers, credentials or provider request IDs. `provider status=incomplete` with `incomplete_reason=max_output_tokens` would establish truncation; `validation stage=...` supplies the actual rejected boundary and path; `controller_commit` rejection identifies a commit failure. Until those failing live lines are available, a specific fix for the reported symptoms would be a guess.
