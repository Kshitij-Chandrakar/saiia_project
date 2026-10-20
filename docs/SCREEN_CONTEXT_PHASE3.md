# Analyze Screen runtime integration — Phase 3

Date: 2026-10-18. Implemented locally. Real Windows capture, native shortcut,
authenticated cloud deployment and paid-provider acceptance remain pending.
No dependencies, migrations, screenshot persistence, commits or deployment added.
Phase 4 has not started.

## Current focused revision: three capture intents

The chooser now offers **New question**, **Passage / Data**, and **Continue previous
question**, followed by the unchanged OCR / Extension source controls. Opening,
selecting and dismissing are passive. New remains the default only with no accepted
context; accepted context requires a fresh explicit choice. OCR execution alone
applies resets. New or Passage / Data may supersede running Screen work. Existing
displayed/saved history is separate and retains earlier-context attribution.

| Choice | Execution and successful result |
| --- | --- |
| New question (`action=new`) | Clear all working sources/answers/candidates, start `contextKind=question`, capture/solve independently. A readable incomplete question may commit `needs_more_content`, without completed history. |
| Passage / Data (`action=reference`) | Clear all working context, start `contextKind=reference`, capture readable reference source only. Commit `reference_accepted` evidence plus original image, never an answer/history entry. Show “Reference saved. Capture your question using Continue previous question.” Repeating replaces the old reference and its working questions/answers. |
| Continue (`action=continue`) | Retain active kind and accepted sources/images/successful answers; capture once. Disabled without accepted evidence. Reference mode supports successive independent questions using the saved passage, plus relevant follow-ups. |

Compatible additive v1 changes: request action gains `reference`; optional
`contextKind` defaults to `question` for existing callers. Main derives kind from
its controller; renderer cannot submit it. Response/provider output gains
`reference_accepted`: nonblank grounded evidence, `complete=false`, current/known
image hashes, exact replacement references, empty items/answer/missing/conflicts,
null clarification and no error. Its minimal controller payload omits the answer
key entirely. The backend and Electron reject answered/missing-question workaround
results for reference intent and reject reference acceptance for question intent.
Unreadable/irrelevant captures remain failures; ambiguity remains non-committable
clarification. Existing endpoints/callers and legacy normalized adapters are unchanged.

Controller `contextKind` survives frozen retries and continuations and resets on
replacement/lifecycle cleanup. The first accepted turn in reference context is
explicitly identified in provider input as `referenceTurnIds`; original source images
remain present alongside structured source text. Previous answers retain their
separate fallible-generated-content input section. Reference continuations do not
automatically inherit the sole prior question ID or trigger question-mode batch
target preflight: a new question may receive a new stable ID. Explicit targets still
bind to known items; ambiguous follow-ups must clarify. History never chooses a target.

The six-image/byte/pixel/text and aggregate upload limits remain unchanged; overflow
rejects without evicting the saved passage. Failed replacement remains a fresh empty
context. Retry never recaptures; late old responses cannot commit. Auth, loopback,
capture/hide/restore, privacy, session cleanup and Extension controlled behavior remain.

Revision files: controller/executor (intent, kind, evidence-only commit and target
validation), `ScreenContextControls.jsx` (third passive choice and acknowledgement),
backend `models/screen_context.py` and `services/screen_context_service.py` (additive
schema, strict intent/outcome validation, reference instructions), their behavioral
tests and the Playwright real-view test. No migrations, new provider/dependencies,
permanent screenshots, audio/gRPC changes or hidden feature activation.

Verification: 561 frontend tests, 132 focused backend regressions (65 contextual),
seven Playwright real main/overlay-view scenarios, and the repository audit excluding
backend tests passed. The audit includes build, compile, syntax, whitespace and 124
Extension checks. Tests use synthetic captures/mocked transport/provider; they prove
contracts, no solving/history on reference acceptance, isolation, source/image order,
two successive question IDs, retry, cleanup and ceilings—not live model accuracy.
The known broader backend session-generation baseline remains separate as described
below; Phase 4 remains unstarted. Graphify updates/queries ran before and after changes.

Manual acceptance after restarting backend/Electron (no feature flag):

1. Start a session. Put Passage A in an external window. Open Analyze Screen,
   choose Passage / Data, dismiss, and verify no capture/reset. Reopen and select
   Passage / Data → OCR. Expect the reference acknowledgement, count 1/6, no answer
   or completed history. A passage/table/chart/diagram/code is valid reference material.
2. Display Question 1. Continue previous question → OCR. Expect an answer grounded
   in Passage A. Display Question 2 and repeat Continue → OCR. Passage A must remain
   supplied; Question 2 must not be silently treated as a revision of Question 1.
3. Display Passage B. Select Passage / Data without executing: A stays intact.
   Execute OCR: B replaces all of A's working sources/questions/AI answers. Count
   returns to 1/6; previous displayed answer/history remains attributed to old context.
4. Display Question X. New question → OCR. Expect no A/B sources or earlier answers
   in working input. Continue a follow-up. Also test an incomplete New capture,
   More content needed (no completed history), then Continue the remaining portion.
5. Fail/cancel a fresh reference replacement: old working context must not return.
   Retry a retained failed capture without recapture. Resolve clarification without
   accepting its evidence. End/switch session during a request and reject late results.
6. Check diagram/code fidelity, actual provider outcomes and budget behavior live.
   If the old failure remains, copy only the safe tagged terminal validation/status
   lines described below; no screenshots, prompts, answers or credentials are needed.

## Manual failure investigation — open

The reported OpenAI 200 + contextual endpoint 200 does not establish an answered
outcome. The exact visible generic message is the fallback in `ScreenContextStatus`
when main reports `phase=failed` and its error code is absent from the UI message
map. It is shared by backend semantic failures and unclassified main exceptions.
Zero accepted screenshots is consistent with a rejected first turn; a retained
retry candidate deliberately does not count as accepted evidence.

The later supplied status establishes backend `outcome=failed`, `errorCode=invalid_output`,
matching identity, revision/count zero and a retained retry candidate. This rules out
HTTP transport success as semantic success and points to backend parsing/validation/
adaptation paths; the exact provider field or predicate was not supplied. There is no
evidence of a Phase 1 minimal-payload mismatch. Its full FastAPI→Electron→controller
round trips pass for answered, incomplete evidence and reference acceptance. The
previous workflow's missing explicit reference intent/outcome is corrected above;
the exact old invalid-output branch remains unresolved, rather than guessed to be
caused solely by absence of a question. Safe validation paths were requested. The
development terminal projection needs no DevTools. Phase 4 remains on hold.

The existing Python→Node contract test now passes the entire real FastAPI JSON
response through Electron's `validateResponse` before committing, rather than
testing only `controllerResult`. Both answered and evidence-only payloads pass
strict validation and advance accepted count/revision to one. The test uses
deterministic synthetic IDs across its two Node subprocesses; production identity
checks are unchanged. Retry tests verify one capture, frozen input, new attempt ID,
one accepted screenshot and no answer/history result for incomplete evidence.

Temporary diagnostics:

- Backend (opt in using `SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS=1` in the development terminal only) `screen_context provider`: opaque request ID, bounded status/refusal
  boolean and incomplete reason. `screen_context backend`: outcome/committable/error
  code. Validation diagnostics contain error types and sanitized schema paths only;
  unknown model keys are redacted and Pydantic input/msg/ctx are excluded.
- Unpackaged Electron development builds only: `[screen-context-status]` prints exactly `phase`, `errorCode`, `revision`, `acceptedImageCount`, `retryAvailable`; `[screen-context]`: same request ID, processing stage, validated outcome,
  identity/ownership-match booleans, rejection code and revision-advance boolean.
  Capture data, prompt/source/answer text, auth and raw exception messages are absent.
  Logging is observational; existing outcome/identity/commit checks remain intact.

Debug verification: 55 backend contextual tests and 40 focused frontend tests
passed. Node syntax/whitespace checks passed. Live failing-request diagnostics are
still needed; remove these temporary logs after the demonstrated cause is resolved.

Retest without DevTools:

1. Restart is necessary for Electron main-process changes. It clears temporary
   context/retry candidates, so reproduce a new failing attempt after restarting.
   Stop the current development Electron command with Ctrl+C in its terminal.
2. In the existing activated backend environment/terminal, stop its current server,
   then run from the repository root (no dotenv edits or dependency installation):

   ```powershell
   $env:SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS = "1"
   cd E:\saiia_project\saiia_project\backend
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

3. In the frontend development terminal:

   ```powershell
   cd E:\saiia_project\saiia_project\frontend
   npm run electron:dev
   ```

4. Complete existing startup/session setup. Put a test question in an external
   window. Analyze Screen ? New question ? OCR. Wait for the failure or result.
5. In the terminal running `npm run electron:dev`, copy the final
   `[screen-context-status]` line and the `[screen-context]` response/outcome/rejected
   lines for that attempt. In the backend terminal, copy only matching
   `screen_context provider`, `screen_context validation`, `screen_context backend`
   lines. The opaque request ID links the stage lines; the status line has just
   the five requested fields. Do not copy the full terminal log.
6. Click Retry captured screenshot once without closing/restarting. It must reuse
   the captured image; copy those same tagged lines for the retry. A validated
   answer or More content needed must advance `acceptedImageCount` and `revision`
   to 1; failure must leave both at 0. Incomplete evidence creates no answer history.

No screenshot, source, answer, prompt, credentials or full API body is needed.
Backend diagnostics default off; never set this opt-in in deployment. Electron
packaged builds suppress both diagnostic tags. Once investigation finishes, stop
backend, remove the temporary terminal opt-in with
`Remove-Item Env:\SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS`, and restart normally.

## Runtime and files

| File | Phase 3 responsibility |
| --- | --- |
| `frontend/electron/screen_context_execution.cjs` | Main-only capture admission, serialized native hide/restore, bounded multipart, trusted destination, authentication adapter, abort/deadline, strict echoed-response validation, commits, safe events and narrow sender-validated IPC registration. |
| `frontend/electron/screen_context_controller.cjs` | Existing sole working-context owner; now retains stable batch item bindings and explicit replacement references. Clarification resolution retains the candidate and frozen evidence/images, changes attempt ID and explicit resolution sidecars only. |
| `frontend/electron/main.cjs` | Connects the existing active-window capture, verified auth, lifecycle invalidation and main/overlay events. Stop cancels Screen before its existing audio/Chat broadcast. |
| `frontend/electron/desktop_auth_session.cjs` | Screen-named wrapper reuses existing verified authorization; gRPC implementation and routing remain unchanged. |
| `frontend/electron/preload.cjs` | Five narrow Screen commands plus removable status/result subscription. No arbitrary fetch, ownership claims, images or commit API. |
| `frontend/src/components/ScreenContextControls.jsx` | Passive context choices, batch target, safe status/counts, incomplete/clarification/error, explicit replacement, frozen retry and Screen-only cancel. |
| `frontend/src/components/OverlayWindow.jsx` | Toolbar and shortcut action open the same chooser. OCR alone executes. Reopening mounts a fresh choice; existing context requires explicit selection. |
| `frontend/src/components/AnswerPanel.jsx`, `MainDiagnosticsWindow.jsx` | Existing entry points open the chooser; New remains accessible while an older Screen request runs. Existing audio guards and controlled Extension behavior remain. |
| `frontend/src/screen_context_events.js`, `App.jsx` | Recheck fresh main status and sequence/ownership before display/history. Reuse the existing batch formatter and sole history append path; attribute each displayed/history result to its thread. History navigation never changes main context. |
| `backend/app/models/screen_context.py`, `services/screen_context_service.py` | User-approved bounded clarification-response compatibility addition, supplied separately from observed evidence and previous generated answers. |
| Focused Node, backend and Playwright tests | Controller/executor/IPC/lifecycle/transport validation and real React main + overlay interaction with mocked native capture/provider transport. |

Flow: passive chooser → explicit OCR → controller `begin` → one existing
active-window capture → `registerImage` / `prepareRequest` → multipart
`/api/screen/analyze-context` → bounded response parsing + full identity/outcome
validation → controller commit → safe event → renderer checks fresh main status →
existing `commitDirectScreenAnswer` display/history path.

Main mints all operation identities. `accountGeneration` remains the lifecycle
snapshot adopted at startup; it is not compared with the auth manager's current
`sessionGeneration`, which also advances during same-account verification.
Account/session replacement callbacks invalidate before async work can commit.
Cloud requests require the current main-owned cloud session and existing verified
credentials. Invalid/unavailable credentials never trigger a local or legacy retry.
Local requests contain no credentials and require the configured loopback backend.
Redirects are rejected; renderer supplies no URL, token, image, evidence or answer.

## UI and outcome rules

Opening, selecting, closing, Escape and reopening perform no capture, generation,
context mutation or history append. First capture defaults to New; Continue is
disabled until accepted evidence exists. With accepted context, OCR is disabled
until a fresh explicit Continue/New choice. Selection is scoped synchronously to
the current thread/context availability, including delayed status reads.

New execution releases the old working thread and pending/retry candidate before
capture. A failed or cancelled New remains empty; older displayed answers and
history stay available and are labelled as belonging to an earlier question.
Continue uses accepted evidence, images and successful answers only. An optional
batch-item selection uses main-retained IDs, never the currently displayed answer.
Older threads remain history entries; there is no old-thread resumption control.

| Outcome/action | Working context | Display/history |
| --- | --- | --- |
| Capturing/processing | Candidate separate; previous accepted context remains for Continue | Prior valid answer stays visible. |
| `answered` | Atomic evidence + answer + validated item/replacement sidecars; revision advances once | One existing completed history entry per logical operation. Duplicate event delivery is ignored. |
| `needs_more_content` | Evidence only; revision advances once | Missing details; Continue enabled; no completed history entry. |
| `needs_clarification` | Nothing commits; candidate retained within existing budgets | Specific ambiguity/conflicts, explicit target/replacement and/or bounded text; no history entry. |
| Failure | No candidate commits; captured retry remains eligible if available | Safe error and explicit retry, previous valid answer remains. |
| Retry | Same frozen capture/context, turn and operation; new request ID | No recapture; at most one completed entry. |
| Cancel / Stop | Abort + invalidate commit eligibility, clear retry/clarification; accepted context preserved | No late result or new history; existing Stop audio/Chat behavior retained. |
| Executed New / lifecycle change | Prior attempts cannot commit; New isolates, lifecycle invalidation releases all working context | Late renderer events fail fresh main-status checks. Saved history is not supplied as model context or deleted by this mechanism. |

Extension remains controlled/unavailable. Executing Extension cancels an active
Screen attempt while preserving accepted context, then uses its existing unavailable
path. There is no Extension capture, bridge, continuity or automatic fallback.

## Clarification compatibility addition

Approved by the user during Phase 3. Optional v1 field (old requests remain valid):

```json
{
  "clarificationResponse": {
    "requestId": "the-last-clarification-attempt",
    "threadId": "the-pending-thread",
    "turnId": "the-retained-turn",
    "text": "Use this corrected implementation."
  }
}
```

Text is nonblank and at most 2,000 characters; IDs use existing safe-ID limits.
Main accepts resolution only for its current pending clarification request. It
validates target/replacement membership before minting a new attempt, retains the
same logical turn and image, and includes the old clarification request binding.
Backend checks thread/turn equality and that the referenced request differs from
the current attempt. As in Phase 2, this stateless backend cannot independently
prove historical commitment; main is authoritative. Text goes in a separate
untrusted-user-clarification model-input section, never in source evidence or AI
answer collections. It cannot override application rules or fill unreadable facts.
Only a later validated answer/incomplete-source outcome can commit. Cancellation,
executed New, session/account changes and disposal clear the candidate and binding.

Batch resolution requires an explicit known question target. Replacement choices
identify source turns, not arbitrary generated code or displayed history. Accepted
replacement references survive subsequent requests; originals remain as attributed
source evidence/images, with explicit supersession instructions. No silent eviction.

## Limits and lifecycle

Existing limits remain: six distinct images including candidate/retry, 10 MiB per
image, 2,200² decoded pixels, 64 MiB retained payload. Main also enforces Phase 2's
24 MiB aggregate compressed images, 256 KiB JSON and exact 25 MiB multipart body
before sending. Overflow rejects the whole request without dropping evidence.
Accepted source turns are bounded at 32 and batch bindings at 20. Clarification
text and retained sidecars count toward retention. Main response parsing is bounded
at 1 MiB, transport/capture execution at 50 seconds; backend retains its 45-second
overall and 30-second maximum provider deadline. These are ceilings, not guarantees
of latency or precise RSS usage. Native capture cannot be forcibly interrupted;
new captures queue behind prior hide/restore completion, and retired results are
discarded. Aborting HTTP cannot guarantee upstream cancellation or avoid billing.

Session end/finalization, logout, account replacement, session switching, owning
window disposal and shutdown reuse Phase 1 invalidation hooks. They abort active
transport and clear candidates before asynchronous lifecycle operations. A fresh
runtime is adopted at startup completion, not by a delayed cloud response. Restart
has no working context to restore. Display/history stay separate; this feature
does not delete stored cloud session/answer records or read them into prompts.

No C9 Ask AI, microphone, transcript, resume or job-description context is added.
Provider/model routing, one normal-path screen-model call, independent batch
questions and exact active-window selection remain unchanged. A partial capture
may become sufficient through combined accepted sources; missing facts still
produce More content needed. This narrowly amends the older architecture's rule
that each screenshot must contain a complete question by itself.

## Automated validation

- 554 frontend Node tests passed, including 17 new executor/IPC behavioral cases
  and existing controller, history, auth/startup, audio/gRPC and Extension contracts.
- 120 focused backend tests passed (53 contextual cases including eight new
  clarification validation/input-separation cases, plus legacy Screen/JWT regressions).
- Six Playwright Chromium tests passed using the actual `App.jsx` main renderer
  and actual overlay/AnswerPanel views, linked by a mocked narrow bridge to the
  real main controller/executor. Capture, credentials and provider transport are
  synthetic. They exercise passive chooser/shortcut-action delivery, keyboard,
  rapid clicks, three captures/diagram/answers, New isolation/supersession, batch
  targeting, result entry point, incomplete evidence, clarification replacement,
  retry/history, duplicate events and session late-result rejection. Native OS
  shortcut activation is not claimed from injected toolbar-action delivery.
- Repository audit with backend tests skipped passed its build, compilation,
  whitespace/staged-file, Electron syntax and 124 Extension tests. Separate syntax
  checks cover the new main modules. Vite reports its existing large-chunk warning.
- Graphify code update and `graphify query` used before and after implementation.

Commands:

```powershell
$screenFrontendTests = @(rg --files frontend/src -g '*.test.js')
node --test --test-concurrency=4 $screenFrontendTests
node --test frontend/tests/screen_context.browser.test.mjs
python -m pytest backend/tests/test_screen_context.py backend/tests/test_screen_vision_openai.py backend/tests/test_screen_vision_openrouter.py backend/tests/test_screen_intelligence_contract.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_supabase_auth.py -q --tb=short
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/pre_commit_audit.ps1 -SkipBackendTests
```

Synthetic screenshots/traces are under ignored `tmp/screen-context-phase3/`.
No captured user screen content was used. Known broader backend baseline remains
separate: `test_generate_stream_primary_success_with_session_id_stores_transcript`
expects a dict where enabled session-model generation reads `.status`; see Phase 2
for its pre-change reproduction and configuration comparison. The full backend
suite is not claimed green.

## Enable and manual acceptance (pending live verification)

No feature flag or dependency installation. Restart the existing backend and
Electron app using their normal development commands. Keep the existing Screen
provider/model configured; local mode requires a loopback backend. For cloud mode,
sign in and start an owned active session through the existing startup UI.

1. Put a test problem in an external window. Click Analyze Screen or press the
   actual Ctrl+Shift+Enter. Verify chooser only, no capture/request or answer loss.
   Continue is disabled initially; New is selected. Escape returns toolbar focus.
2. Click OCR. Verify one capture, one contextual request, answer/code/batch rendering
   and one history entry. Open again: neither context option is preselected now.
3. Split a question over three external-window views. Execute New OCR for the first,
   then explicitly Continue + OCR twice. Confirm missing constraints are requested
   through More content needed and incomplete turns create no completed history.
4. Include a diagram in the first view and a dependent question later. Confirm
   image fidelity and answer grounding. Ask a later correction dependent on a prior
   AI answer; confirm it can correct a mistaken answer against source evidence.
5. Show changed code. When clarification appears, select the exact earlier source
   turn to replace, enter intent, and Resolve. Confirm no recapture and subsequent
   continuations preserve replacement references. Test batch question selection.
6. Browse history, open chooser, explicitly Continue a target. Confirm history
   navigation did not change that target or import an older thread's evidence.
7. With a valid answer, execute New. Confirm the older answer remains attributed,
   and the request has no previous images/evidence/answers. Fail/cancel this New:
   Continue stays disabled and the old context is not restored.
8. Interrupt a Continue with Stop; test retry after a controlled failed request.
   Confirm frozen retry/no recapture/no duplicate history. While an old request runs,
   select New (no mutation), then OCR (supersedes); release delayed old response.
9. End the session during capture/request, then test logout/account/session switch,
   window recreation and restart. Confirm working bytes/counts are released and
   delayed results cannot repopulate UI/history. Verify existing saved records remain.
10. Exercise existing single-screenshot coding/MCQ/batch, history, audio/Chat/gRPC
    Stop and Extension unavailable paths. Measure live latency, cost and memory,
    small-font/diagram quality after existing resizing and authenticated deployment.

## Rollback

No data migration or hidden flag to reverse. Ship the previously reviewed frontend
and Electron bundle together to restore its legacy Screen flow; the additive backend
endpoint/optional clarification field can remain unused. Reverting source must be
limited to Phase 3 hunks/new files and preserve pre-existing audio/gRPC and Phases
1–2 work. Do not reset this working tree wholesale. Restart Electron to release
ephemeral context. No saved history/session deletion is required.
## Contract audit amendment — 2026-10-19

Confirmed commit-to-next-request provenance/clarification losses are corrected; stable IDs, exact main-owned clarification binding and append-only revision semantics were verified. Main now retains per-source image/replacement links and kind, and successful user clarification separately from source facts/answers. 588 frontend tests, 126 contextual backend tests, 67 legacy Screen/auth checks, eight mocked Playwright tests and repository audit excluding the full backend suite passed. Build/compile and 124 Extension checks are included. No live fidelity/native capture claim, migration, history deletion or Phase 4 work. See [audit report](SCREEN_CONTEXT_CONTRACT_AUDIT.md).
