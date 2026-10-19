# Answer streaming: Phase 1 characterization

Historical phase record. See [streaming closeout](ANSWER_STREAMING_CLOSEOUT.md)
for final verified status and separately attributed user acceptance.

2026-10-19. Phase 1 only. No production behavior, protobuf, generated binding,
catalog, prompt, fallback/persistence policy, database, environment file or audio
implementation changed. All additions remain unstaged and uncommitted.

## Baseline and execution

Verified revision: `b8b6dc703a0e773ccc5ca9e757a821ab8f8ef2e3` on
`dev/current-work`. PR #49 is merged through ancestor `1c676ad`; PR #50 remains
open with head `b8b6dc7`. Its additional committed review fix tolerates empty
native reads in combined capture (`grpc_server.py` and `test_grpc_combined.py`).
That fix is included in verification; no pending unstaged audio fix was present.
No applicable project/ancestor AGENTS.md was found. Ponytail guidance was used.

Existing work at entry: 21 modified tracked files and 18 untracked files. Screen
context work overlaps Electron main/preload/auth, App, AnswerPanel, OverlayWindow
and diagnostics. Model closeout differences correct quoted text; roadmap/audio
records also have unrelated edits. The coordinator, answer adapter, gRPC client,
Auto consumer and protobufs match HEAD. Verification uses the mixed working tree,
including those existing UI differences, rather than an isolated committed tree.

Before editing, a SHA-256 inventory of every existing modified/untracked file,
the tracked binary diff and staged diff was saved outside the repository at
`%TEMP%/saiia-answer-phase1-baseline.json`. After verification every original
file hash, tracked diff and staged diff matched. Relevant UI baseline hashes:

| File | SHA-256 |
| --- | --- |
| `frontend/electron/main.cjs` | `cd666f5f90b024456c1a15e1e360c28fc168749f9530071c16650297a659cd9d` |
| `frontend/electron/preload.cjs` | `8a9d5227bc143c58cc86c39411b6935f4092ce7c41d29d036d7b1c8719dbec77` |
| `frontend/electron/desktop_auth_session.cjs` | `4100f7fd4bba737fd1c32acefaf2524b1c552db190b5c8a8b075784d7af810d6` |
| `frontend/src/App.jsx` | `edd62ab43a831bcaab3634211b89cc589d0103227772d75044d33a8c9da15662` |
| `frontend/src/components/AnswerPanel.jsx` | `6b9f1bbe94c69496caddfc109a6f2c1b3f53c48bc5691c3fa8e23d7aa8919f82` |
| `frontend/src/components/OverlayWindow.jsx` | `da624044477922ec3415110f29bdef4700ec002ff33e9cc9dede3e2b33e03b5a` |

Read G12 audio closeout, session-model Phase 3/closeout and Retry/admission
records. Source remains authoritative. Existing Graphify was queried before
and after additions with `graphify query "stream_question_answer" --budget 500`
(350 and 200 after); no graph generation, reflection or save-result was run. Existing
graph navigation points to the coordinator/adapter but does not describe the
new tests until a separately authorized refresh.

Execution plan: reuse isolated auth/storage fixtures; gate provider chunks,
completion, postprocessing return and save independently; observe real
coordinator/adapter/localhost gRPC; connect production Electron/Auto consumers;
render the actual AnswerPanel; run focused regressions and record limits.

## Confirmed behavior

The following results apply to microphone, Computer (`system`) and combined
(`both`) accepted-question routes. Native capture and STT I/O are mocked; shared
production question queuing, coordinator, adapter and gRPC handler execute.

| Case | Coordinator / adapter | gRPC / display |
| --- | --- | --- |
| Selected primary | A and B arrive independently before provider completion; coordinator attempt `0` exists | Both deltas cross localhost gRPC before completion; Electron and Auto consumer show distinct prefixes |
| Partial primary then fallback | Empty `replace` becomes adapter `replacement`; fallback A/B are withheld | No reset event reaches the wire; primary provisional text remains until authoritative fallback completion |
| No stored binding | Production configured legacy provider selection executes; no selected-model bridge is installed | No deltas at coordinator, adapter or wire; full answer arrives at completion |
| Canonical formatting change | Production planner/validator runs; injected formatter result is held at its return boundary | Provisional primary remains until validation-return and durable completion; final text replaces rather than concatenates |
| Both attempts fail | Failed-attempt discard/reset occurs internally | Typed `generation_failed`; Electron/Auto consumer clears partial text and retains request identity for existing Retry handling |
| Stop / disconnect | Blocked primary generator closes; no second provider call and no final save | Real gRPC cancel event and channel cancellation are both exercised |

The formatting test injects a deterministic final formatter result after the
real generator finishes; it does not claim to test a semantic correction model
or every coding formatter branch. Existing correction-facade regression tests
run separately. No claim is made about which route caused the user's original
completion-only turn; there is no runtime evidence for that attribution.

Material production references:

- `backend/app/session_generation.py`: `dispatch_session_generation`, nested
  `produce/events`, `AttemptRun.call/primary`, `AttemptProvider.generate`.
  `display and index == 0` allows primary deltas; corrections use `display=False`;
  unbound sessions use `run=None`; final publication follows checkpoint/complete.
- `backend/app/answer_generation.py`: `provider_stream`, `_request`, `_normalize`.
  Real streaming adapters exist; new tests mock this network boundary, while
  existing adapter/catalog tests cover mocked provider response normalization.
- `backend/app/grpc_answer_pipeline.py`: `stream_question_answer`. It maps NDJSON
  delta/replace to adapter events and drops provider-attempt identity.
- `backend/app/grpc_server.py`: `StreamInterview`, `queue_final`,
  `answer_worker.generate`. Deltas are emitted; nonempty replacements/results
  update its private accumulator; empty replacement is ignored. Completion sends
  the full final answer. The wire has no replacement or provider-attempt field.
- `frontend/electron/grpc_realtime_client.cjs`: `connect` data handler,
  `getStatus`, `onAutoEvent`. Appends deltas, publishes snapshots immediately,
  replaces final text and clears recognized terminal failures.
- `frontend/src/grpc_auto_session.js`: `createGrpcAutoSession/apply`. Production
  renderer consumer accepts progressive snapshots and one terminal completion.
- `frontend/src/App.jsx`: Auto `onAnswer`, `useElectronOverlaySync`.
  `AnswerPanel.jsx`: `getPanelCopy`, component rendering. Source supports current
  answer display before completion; the rendered harness uses the real panel.

## Fixtures and safe diagnostics

`backend/tests/test_answer_stream_characterization.py` reuses the existing
session test's isolated authorization/store fixture. Async events gate first
chunk, subsequent chunk and completion separately for primary and fallback.
A thread event holds the production generator return boundary; another async
event holds durable completion. Assertions use synchronization and bounded
10-second deadlock waits, not latency thresholds. Fake native reads use the
existing 100 ms capture cadence solely to pace synthetic silence; correctness
does not depend on this wait. No mixer behavior is asserted.

`Probe` holds at most 256 test events. Assertion payloads are synthetic and stay
inside the test. `safe_summary()` emits only `stage` and Python-local `local_ms`;
it excludes payloads, identifiers, prompts, answers, credentials and context.
Stages include provider first/next text/end/close, coordinator events, adapter
events, gRPC emission, gRPC receipt, validation-return and durable completion.
The summary is attached to optional pytest/JUnit properties, including failures.

The reusable Node driver mocks the gRPC transport boundary while executing the
real Electron parser/publication. At most 128 Node-local stages record client
receipt and Electron publication. Renderer fixtures record consumption, React
state requests and MutationObserver DOM changes (128 maximum). Browser reporting
emits only route categories, stage counts and local state-request-to-DOM durations.
No production instrumentation, flags, endpoint, telemetry or database was added;
the diagnostics are inactive outside explicitly invoked tests.

Python, Node and browser clocks are separate. Only local durations are compared;
causality across processes comes from gates/event delivery, never timestamp
subtraction. DOM mutation is not proof of a painted frame. Provider latency is
synthetic and controlled; test wall time includes initialization and gates.

To enable locally later, run the commands below. Optional JUnit goes to TEMP;
no real `.env` edits or app runtime activation are needed. Existing gRPC
`manualTimings` remains available but this phase adds no cross-protocol timing
metadata. Live provider-to-Electron correlation remains a protocol/diagnostic
gap deferred to Phase 2.

## Verification on this tree

PowerShell, backend working directory:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:ENABLE_SESSION_ANSWER_MODELS='false'
E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_answer_stream_characterization.py tests/test_session_generation.py tests/test_grpc_answers.py tests/test_grpc_auto.py tests/test_grpc_cloud_context.py tests/test_grpc_combined.py tests/test_answer_streaming.py tests/test_answer_model_foundation.py -p no:cacheprovider -o junit_family=legacy --junitxml="$env:TEMP/saiia-answer-phase1-tests.xml"
# Final regression run: 198 passed, 5 existing SWIG warnings, 26.94 s.

E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_answer_stream_characterization.py -p no:cacheprovider -o junit_family=legacy --junitxml="$env:TEMP/saiia-answer-phase1-characterization.xml"
# Final characterization-only rerun: 21 passed, 5 warnings, 4.96 s.
```

The process-only flag disables local activation for legacy fixtures; managed
fixtures explicitly enable it with monkeypatch. No running backend is activated
or reconfigured. Initial run without that override had 14 legacy-fixture failures
(179 passed): their mocked session/context shapes assume disabled session routing.
The override resolves that fixture/configuration mismatch. An initial root-CWD
invocation also failed collection (`app` not on import path); use backend CWD.
Early synthetic capture fixtures caused cleanup hangs; the final paced fixture
and acknowledged cleanup complete normally. Those interrupted runs are not passes.

Frontend working directory:

```powershell
node --test src/answer_stream_characterization.test.js src/grpc_realtime_client.test.js src/grpc_auto_session.test.js src/answer_stream.test.js src/answer_stream_protocol.test.js src/manual_chat_streaming.test.js src/grpc_manual_session.test.js src/grpc_computer_auto.test.js src/grpc_combined.test.js src/realtime_lifecycle.test.js
# 131 passed, 0 failed; includes 6 new Electron/Auto characterization cases.

node --test tests/answer_stream.browser.test.mjs
# 3 passed, 0 failed; Chromium + Vite, actual Auto consumer and AnswerPanel.
```

Rendered tests show `Prefix A`, then `Prefix A plus B`, with completed count
still zero, followed by canonical replacement without the prefix. Last run:
state-request-to-DOM samples were 1.7–2.8 ms. These are local synthetic samples,
not paint measurements, provider latency or a production latency guarantee.
Final Python-local samples (microphone/system/both): fake provider first usable
text to coordinator delta was 0.26/0.21/0.25 ms; gRPC emission to localhost
client receipt was 0.38/0.33/0.33 ms. Python uses `perf_counter`; these durations
exclude the explicitly held provider latency and cannot be combined with the
separate browser samples into an end-to-end latency claim.

Python AST parsing, Node `--check` on all new JS/MJS modules and whitespace
checks passed. Vite compiled/executed the JSX fixture during rendered tests.
`git diff --check` covers the existing tracked diff; additions were checked
separately since they are untracked. Existing Windows LF/CRLF notices are not
whitespace defects. No build, install or full repository test suite was run.

## Boundaries and Phase 2 handoff

- Python localhost transport and Node/browser consumers are complementary
  boundary tests, not one Python-to-Electron end-to-end process. Node transport
  and the preload/IPC bridge are mocked. Main `App.jsx` orchestration and the
  actual separate overlay window are source-reviewed, not mounted in this new
  harness. Native Windows devices, physical audio, live auth/providers/storage,
  paint and long-duration responsiveness are not tested here.
- No hosted queries or migration were run. The documented recovery migration
  `20261018210000_harden_session_generation_recovery.sql` remains a separately
  paused dependency. Mock storage does not establish deployed SQL parity.
- Existing model/correction/recovery/HTTP tests are regression evidence only;
  this phase does not add full crash/concurrency or all lifecycle-race coverage.
- Future acceptance: primary AND fallback real chunks must become visible before
  provider completion; discarded text must clear at the replacement boundary;
  validation/correction must atomically install canonical final text, with one
  final-save owner and no provisional persistence. Current-buffering assertions
  are explicitly known limitations and must change when that contract is approved.
- Phase 2 needs additive negotiated replacement/reset and attempt/revision
  identity, preserved through coordinator, adapter, gRPC, Electron and renderer.
  Never repurpose existing delta/completed fields. Forward empty replacements;
  expose fallback chunks only with attempt reset/fencing; retain atomic canonical
  completion. Plan proto-copy/generated-binding parity and old/new compatibility.
- Unbound sessions need a legacy-preserving primary bridge rather than assigning
  a model binding. Fence connection/session/turn/retry/provider attempts and queued
  UI work. Keep selected-model routing, validation, cancellation, single fallback,
  Retry/save-only recovery and persistence ownership unchanged. No Phase 2 work
  was started or implicitly approved by these characterization tests.
