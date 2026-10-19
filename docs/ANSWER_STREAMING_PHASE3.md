# Answer streaming: Phase 3 Electron, React and overlay

Historical phase record. See [streaming closeout](ANSWER_STREAMING_CLOSEOUT.md)
for final verified status and separately attributed user acceptance.

2026-10-20. Implements the Phase 2 negotiated consumer; Phase 4 acceptance and
commit preparation are not started. All changes remain unstaged/uncommitted.

## Baseline and scope

Entry HEAD: `b8b6dc703a0e773ccc5ca9e757a821ab8f8ef2e3`, branch
`dev/current-work`. History includes the PR #50 empty-native-read review fix,
`317489b` audio closeout and PR #49 merge `1c676ad`. Remote PR status was not
queried. There were 56 modified/untracked files at entry; the index was empty.
No applicable ancestor or repository AGENTS.md was found. Read Phase 1/2,
G12 audio closeout and session-model closeout records; verified against source.
Ponytail guidance favors the existing client/Auto/React/overlay state owners.

`%TEMP%/saiia-answer-phase3-baseline.json` records entry HEAD, SHA-256 for all
56 existing changed/untracked files and the staged-diff hash. Only five of those
files changed in this phase: Electron main, App, the Phase 1 Python transport
fixture, its Node driver and JSX rendered fixture. All other entry hashes and
staging remain unchanged. Main/App already contained Screen/UI changes; targeted
additions preserve those hunks. Preload, AnswerPanel, OverlayWindow, auth,
Screen services, audio/STT/mixer code, model work and Phase 2 production files
are unchanged from entry. The mixed working tree is the verification baseline.

Execution plan: inspect the wire and state owners; negotiate and fence in the
existing Electron client; preserve identity through Auto and overlay snapshots;
exercise deterministic unit/rendered/localhost boundaries; run regressions and
record remaining acceptance work. Graphify queries ran before and after:

```text
graphify query "grpc_realtime_client grpc_auto_session OverlayWindow" --budget 350
graphify query "grpc_auto_session OverlayWindow answer_stream" --budget 200
```

The existing graph is navigation context, not an index of new code. No Graphify
artifacts were regenerated or saved.

## Changed files

| File | Change |
| --- | --- |
| `frontend/electron/answer_stream_state.cjs` | Negotiated identity/sequence fence and main-side overlay answer fence; contains no answer accumulator |
| `frontend/electron/grpc_realtime_client.cjs` | Version advertisement/acknowledgement, replacements, bounded delta publication, safe snapshot metadata and cancellation |
| `frontend/electron/main.cjs` | Fence stale answer fields when merging overlay updates; stamp overlay publications |
| `frontend/src/grpc_auto_session.js` | Reject duplicate/stale snapshots; propagate identity; authoritative completion and stable negotiated history identity |
| `frontend/src/App.jsx` | Carry gRPC display identity in existing overlay state; release it for Stop/HTTP Retry; order overlay reception; retain captured Retry context |
| `frontend/src/overlay_snapshot.js` | Receiver-side publication and run/turn/revision/terminal fences, including initial-load races and invalidation |
| `frontend/src/grpc_realtime_client.test.js` | Extend explicit safe status-field expectation |
| `frontend/src/answer_stream_phase3.test.js` | 15 negotiated state/publication/lifecycle/receiver tests |
| `frontend/tests/fixtures/answer_stream_driver.mjs` | Optional negotiated synthetic transport, explicit identity and sequence injection; legacy mode retained |
| `frontend/tests/fixtures/answer-stream.jsx` | Render production AnswerPanel and OverlayWindow with production snapshot merging |
| `frontend/tests/answer_stream_phase3.browser.test.mjs` | Main and overlay DOM prefixes/reset/canonical checks for three sources |
| `frontend/tests/fixtures/answer_stream_localhost.mjs` | Real Electron transport, registered IPC, executed preload and production Auto consumer in Node |
| `backend/tests/test_answer_stream_characterization.py` | Optional external-client branch reuses production Python localhost fixture |
| `backend/tests/test_answer_stream_phase3.py` | Three gated Python-to-Node integration cases with mock auth/STT/capture/providers/storage |
| This record | Contract, verification and Phase 4 handoff |

No protobuf or generated-binding correction was needed. Existing preload methods
already carry the whitelisted `getStatus()` snapshot; no new IPC channel or
second answer store was introduced. Neither answer display component needed a
presentation change.

## Negotiation and event-to-state mapping

`GrpcRealtimeClient.startSession` advertises `answer_stream_version: 1` for Auto
only. The client activates it only after `answer_stream_capabilities.version ===
1` on the current transport session, before any accepted answer. Health does not
negotiate it. Close/connection replacement resets acknowledgement and fences.
Manual, declined/unmanaged and old-server routes retain legacy behavior.

`AnswerStreamState` stores identity/terminal state only; the existing client's
`currentAnswer` remains the sole Electron answer accumulator.

| Event | State operation |
| --- | --- |
| `question_detected` | Accept only a strictly newer `accepted_turn` and fresh request; clear provisional text |
| `answer_started` | Mark generating once for the accepted turn |
| `answer_delta` | Append only on exact current retry/provider/revision identity |
| `answer_replaced` | Open a strictly newer revision, without decreasing provider attempt; assign text including empty string |
| `answer_completed` | Assign authoritative full text; mark terminal; increment completion once |
| `answer_error` | Clear provisional text; mark terminal; retain safe recovery code and request identity; keep healthy transport listening |

Failure invalidation and fallback start may produce consecutive empty resets on
the same or next provider attempt. Both are accepted when revisions increase.
Canonical replacement may advance revision without changing attempt. Completion
uses that canonical revision and replaces, never appends. Fallback stays silent.
Unknown negotiated turn-error codes become `generation_uncertain`, never raw
provider messages or automatic regeneration.

`uint` accepts bounded unsigned values and rejects unsafe numeric input. Wire
uint64 values remain decimal strings across IPC and use BigInt comparison;
uint32 attempts are normalized likewise. Connection-wide sequence gaps are
allowed because STT/status events share the sequence. Duplicate/older sequences,
old session/epoch events, incompatible attempts, old starts, stale revisions and
post-terminal mutations are rejected. Non-answer events also advance the
negotiated sequence fence; turn-specific listening/save status cannot mutate an
unrelated active turn. Cloud authorization remains main-owned and separate from
the random transport session ID.

`createGrpcAutoSession.apply` rejects older/duplicate snapshot versions, while
still checking connection/auth failure at an unchanged version. It accepts skipped
versions, uses the current turn's terminal status rather than a previous turn's
completion counter, and fences logical ordering/revision/terminal state again.
A connected startup snapshot can recover events published before subscription.
Negotiated history IDs use run + server request ID; legacy IDs retain the old
run + question-counter behavior. Existing history helpers replace by ID, so
canonical completion does not add a duplicate entry.

## Batching, React, overlay and lifecycle

Negotiated deltas update Electron's bounded existing accumulator immediately and
publish through at most one 16 ms timer. Subsequent chunks coalesce into its
latest snapshot. This is an application batching interval, not a latency promise.
The timer captures epoch and answer identity and rechecks them before publication.
Reset, new question, completion and turn error cancel it and publish immediately.
Close invalidates epoch and cancels it before existing transport cleanup. Existing
audio backpressure and backend queue bounds are unchanged.

The Auto consumer writes real incoming text through the existing App onAnswer
callback; it does not animate a completed answer or add a render-frame queue.
Existing generating/reveal state and terminal identity distinguish provisional
and canonical text. Existing safe text/Markdown rendering is reused.

App carries only safe display identity as `grpcAnswerIdentity`. Main filters
stale answer fields against the live client identity and previous snapshot
version while retaining unrelated control/Screen fields. Main stamps every
broadcast with `overlayPublicationVersion`. The overlay receiver subscribes
before loading initial state, ignores duplicate/older initial/event snapshots,
and separately checks run/epoch/session/turn/retry/provider/revision/terminal
identity. It retains an identity watermark when gRPC display ownership is released,
so late provisional snapshots cannot restore discarded text. A newer question or
connection can establish ownership again. No cloud authorization or database fence
token enters that metadata.

Auto close sets `closed` first, removes subscriptions/deadlines/cooldown/polling,
and follows existing capture cleanup. App's existing run/current-request guards
continue to fence Stop, logout, session end, supersession and delayed HTTP Retry
results. The existing HTTP frame callback still checks abort/current request and
cancels a pending frame on replacement; this phase adds no second frame loop.

Retry remains the existing captured-turn HTTP recovery path. It retains the
failed question, selected context, session, logical request ID, retry attempt and
history ID; no audio recapture is added. `generation_failed` advances Retry's
attempt; persistence/processing recovery retains it. Processing/persistence
recovery remains claim-controlled, uncertain/stopped results do not enable
regeneration. Terminal guidance is based on current request identity rather than
requiring the failed-turn reference to survive. Provisional chunks never enter
cloud persistence. The backend coordinator remains the only final-save owner.

## Verification

No provider/STT/device/cloud operation was used. Python tests run through the
existing outside-repository guarded runner, which blanks provider credentials and
disables local activation before imports, then rejects non-loopback Python
network connections. Fixtures explicitly enable synthetic routes. Node localhost
uses an explicit synthetic environment, fixed loopback address, synthetic bearer
and mocked capture; it does not load dotenv. Browser fixtures block non-loopback
requests. No real .env or running-process flag was changed.

From `backend`:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B "$env:TEMP/saiia-answer-phase2-tests.py" tests/test_answer_stream_phase3.py tests/test_answer_stream_phase2.py tests/test_answer_stream_characterization.py tests/test_session_generation.py tests/test_answer_model_foundation.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_grpc_manual.py tests/test_grpc_combined.py tests/test_grpc_realtime.py tests/test_grpc_system_audio.py tests/test_grpc_computer_lifecycle.py tests/test_grpc_health.py
# 289 passed; 5 existing SWIG deprecation warnings; 43.84 s.
E:/deepfake_envs/SaIIA/python.exe -B "$env:TEMP/saiia-answer-phase2-tests.py" tests/test_answer_stream_phase3.py
# Final actual-Electron boundary rerun: 3 passed; 5 warnings; 3.94 s.
```

The runner is described in Phase 2's verification record. It uses pytest `-q`,
`-p no:cacheprovider`, `--maxfail=3`. Phase 2's temporary-generation test verifies
both shipped proto copies and regenerated Python message/service bindings without
editing repository output. Selected-model/unbound/correction/recovery/legacy HTTP
coverage remains in that regression set.

From `frontend` (the spec output was piped through Select-String for concise
reporting; all pass/fail counts below are actual runner output):

```powershell
node --test --test-reporter=spec src/answer_stream_phase3.test.js src/answer_stream_characterization.test.js src/grpc_realtime_client.test.js src/grpc_auto_session.test.js src/answer_stream.test.js src/answer_stream_protocol.test.js src/manual_chat_streaming.test.js src/grpc_manual_session.test.js src/grpc_computer_auto.test.js src/grpc_combined.test.js src/realtime_lifecycle.test.js src/overlay_mode_state.test.js src/question_history.test.js src/toolbar_stop_button.test.js src/screen_context_phase4.test.js src/screen_context_execution.test.js src/screen_context_controller.test.js src/analyze_screen_menu.test.js src/desktop_auth_session.test.js src/desktop_auth_ui.test.js
# 329 passed, 0 failed.
node --test --test-reporter=spec src/generation_dispatch.test.js src/generation_auth.test.js src/request_state.test.js src/my_answers.test.js src/grpc_manual_latency.test.js src/manual_capture.test.js
# 125 passed, 0 failed. Separate files: 454 frontend regressions total.
node --test tests/answer_stream_phase3.browser.test.mjs tests/answer_stream.browser.test.mjs
# 6 passed, 0 failed: three negotiated main+overlay and three legacy cases.
node --test src/answer_stream_phase3.test.js tests/answer_stream_phase3.browser.test.mjs tests/answer_stream.browser.test.mjs
# Final receiver-fence rerun: 21 passed, 0 failed (15 state + 6 rendered).
npm run build
# Pass, 2156 modules transformed; existing >500 kB bundle-size warning.
```

Python AST checks passed for the two touched Python tests. `node --check` passed
for answer_stream_state, grpc_realtime_client, main, preload, grpc_auto_session,
overlay_snapshot, the new Node test, both Node drivers and the new browser test.
JSX compiled in Vite build and rendered tests. `git diff --check` and explicit
new-file trailing-whitespace checks passed; existing LF/CRLF notices remain.
Initial narrow regression had one expected status-allowlist failure before adding
the two safe fields. Two setup commands used the wrong CWD (fixture creation and
pytest file lookup); they executed no new cases. Corrected commands above pass.

### Evidence and limits

- Gated provider first/next/end, primary failure, fallback first/next/end and final
  persistence execute through the production coordinator, adapter and localhost
  Python handler. The actual @grpc/grpc-js Electron client receives them, registered
  IPC handlers dispatch them, actual preload executes in a VM with mocked Electron
  primitives, and the production Auto consumer receives them. All three source
  entry routes use the same assertions. Exactly one final mock-store save occurs.
- Node tests cover reset while a publication is pending, empty reset with no next
  chunk, stale primary data, canonical completion with queued text, duplicate and
  old starts/deltas/completions, unsafe uint64, delayed previous turn, typed errors,
  unchanged-version disconnect/auth loss, Stop/reconnect and receiver ordering.
- Rendered tests show two distinct primary prefixes and two fallback prefixes in
  both production display components while completion remains blocked. They verify
  empty reset and atomic canonical replacement, and reject an old overlay snapshot.
  This is DOM evidence, not paint evidence or real-provider latency.
- Authorization values are absent from synthetic captured Python diagnostics,
  Node stderr and published status snapshots; explicit regression assertions check
  this. This does not install a global live-provider debug-log redactor.
- The localhost/preload chain and rendered component tests are complementary;
  there is no single native Electron BrowserWindow-to-React end-to-end run. The full
  App tree, interactive Retry toolbar and native logout/session UI are not mounted
  in the new harness. Existing extracted production HTTP-dispatch tests and source
  regressions cover those orchestration paths; backend recovery tests use mock
  stores. No claim of hosted SQL parity or upstream exactly-once execution is made.
- No inference identifies the route of the user's original completion-only turn.
  No physical audio, live providers, live auth, hosted storage, packaged Electron,
  long-duration responsiveness or painted-frame timing was tested.

## Phase 4 acceptance handoff

1. Review the focused Phase 3 delta against the saved mixed-tree baseline; preserve
   all unrelated Screen/UI/audio/model work when preparing a future commit.
2. Verify the packaged Windows client acknowledges v1 against the intended backend;
   verify no-ack/unmanaged behavior against the supported older server.
3. For microphone, Computer and combined, observe progressive long primary answers
   in both windows, responsive STT/listening and unchanged capture/Stop behavior.
4. Use controlled synthetic failure/correction acceptance to verify silent fallback,
   empty discard, progressive fallback, authoritative canonical text and both-attempt
   failure followed by a new question on the same healthy connection.
5. Exercise Stop/restart, logout, session end, disconnect/reconnect, delayed overlay
   updates, actual Retry UI, pending/uncertain/save-only recovery and duplicate
   history prevention in native windows. Approve any live-provider runs separately.
6. Review logs for sensitive content, sustained IPC/update cadence and resource
   cleanup; do not interpret DOM test durations as production latency guarantees.
7. Keep `20261018210000_harden_session_generation_recovery.sql` and hosted admission
   separate. It remains paused, unapplied and unqueried; local recovery tests do
   not remove that deployment dependency.

No audio redesign, catalog/prompt/fallback-policy change, schema change, migration,
.env edit, live-provider request, staging, commit, push, merge or deployment was
performed in Phase 3.
