# Phase 3: Microphone + Computer gRPC Auto

> Phase 4 update: Final verification and focused audio integration are recorded in [G12 closeout](G12_GRPC_AUDIO_CLOSEOUT.md). The user reports that Windows checks for both sources, overlap, Stop/restart, permission denial, device loss, logout and session end passed. Earlier staging and manual-test statements below are historical phase evidence. Answer-token streaming remains deferred; the model-recovery migration remains paused.

## Baseline and audit

Phase 1 microphone routing (`dd22af7`) and lifecycle/router corrections (`34430fc`) were merged by PR #49. The current branch is `dev/current-work`. Phase 2 and unrelated screen-context/model-review work were already present as unstaged changes; no index entries were present. They remain unstaged. Computer-only working on Windows is **user-reported success**, not evidence that all Phase 2 scenarios passed.

No applicable AGENTS.md was found. Ponytail was applied: reuse capture, transport, ownership, authorization, STT, question intake and answer persistence. Graphify was queried and updated before/after; its broad vocabulary query included unrelated screen-capture results, so current source was the implementation authority. Baseline status, tracked binary diff and source hashes were saved outside the repository in `../grpc-phase3-artifacts/`.

Audit integration points:

| Boundary | Evidence and change |
| --- | --- |
| Selection/start/Stop | `App.jsx`: `startAutoMode`, `stopAutoMode`; remove only the Auto combined guard, acquire microphone once, retain late-permission token fencing, extend pending-RPC cleanup to `both`. Manual combined recording remains unsupported. |
| Routing/readiness | `realtime_router.selectRealtimeRoute`, `getGrpcAutoBlockReason`, Electron `connectAuto` and `CheckHealth`: combined requires explicit capability, configured gRPC and authorized session. No HTTP/WS fallback. |
| Microphone | `grpc_mic_test.createGrpcMicTest`, `live_mic_transport.createPcmMicCapture`: existing mono PCM/IPC path, optional stateful conversion and stale-queue discard for combined only. |
| Native source | `SystemAudioCaptureService`: existing default-WASAPI resolution, device-change/read failure handling and native-close result; optional continuous conversion for combined only. |
| STT and ownership | `InterviewRealtimeService.StreamInterview`: existing exclusive system lease and shielded native operations, one existing STT connection/receiver, one new mixer sender instead of forwarding microphone separately. |
| Answers | Existing utterance buffer, question queue, answer worker, cloud-context/session-selected model, Retry and single final-save owner are reused. No new generation, persistence or token-streaming feature. |

Execution order was backend mixer/conversion, lifecycle/transport integration, combined eligibility, then synthetic regressions and build/hook checks. Unrelated files were not edited to make checks pass.

## Architecture and contract

Renderer microphone → stateful mono PCM16 conversion → existing 3,200-byte/100 ms framing and bounded IPC pacing → gRPC `AudioChunk` → backend microphone buffer.

Windows default playback loopback → existing native capture → stateful channel mean/rate conversion → backend system buffer.

Both buffers → one paced 16 kHz mono signed little-endian PCM timeline → one existing STT socket → existing transcription/question/session-model/answer/save flow. Computer-only still rejects client PCM. Microphone-only keeps its capture and fallback behavior. Old system HTTP/WebSocket capture is not started for combined Auto.

`source="both"` already exists as a string value; `sequence_number` and `timestamp_ms` already exist on client events. Audio messages are unchanged. Additive `RealtimeHealth.combined_audio_available = 6` distinguishes this implementation from Phase 2 servers, which otherwise advertise system support but reject combined capture. Older servers decode it as false; combined startup blocks safely. Both proto copies and generated Python message bindings match. The RPC service signature is unchanged.

Health is capability/configuration/lease readiness only: it opens no native device, interview, STT socket, auth context or model connection. Running is not reported until the renderer has acquired microphone permission, backend native startup has succeeded and microphone Web Audio setup has completed. Actual sample delivery is supervised separately.

## Timing, buffers and failure policies

- Output: 1,600 samples every 100 ms, on the backend monotonic clock. Wait for first valid samples from both sources (maximum five seconds after native startup), then use a 200 ms initial jitter allowance. No first-source-only STT audio is sent while waiting.
- Each source has an 8,000-sample/500 ms ring (16 KB, 32 KB total). Native reads and microphone messages remain independently bounded. Microphone PCM format validation and existing acknowledged IPC backpressure remain intact.
- Slow/underflowing sources contribute zeros at that tick and resume at the current output cursor. Normal zero-valued PCM refreshes liveness and is not a failure. Source delivery absent for over two seconds stops the run; this is delivery loss, not an RMS/silence detector.
- Overflow discards buffered source backlog, keeps at most the newest 500 ms and reanchors it at the current cursor. Clock drift is bounded by this drop/zero-fill policy; there is no adaptive sample-clock synchronization. These corrections can create audible discontinuities and need physical acceptance.
- New microphone frames carry their renderer enqueue wall timestamp. Queued frames older than 300 ms are discarded before IPC. Electron validates optional timing and fills the existing timestamp/sequence fields; legacy clients may omit timing or use send time.
- Backend anchors the first sender timestamp to local arrival and compares **elapsed durations**, never client wall time directly with backend monotonic time. Duplicate/regressing nonzero sequence/timestamps and frames over 300 ms late relative to that anchor are rejected. A legacy zero sequence/timestamp remains accepted, with arrival ordering and bounded buffers. Callback timestamps approximate frame availability, not sample-perfect physical capture time.
- Native stereo is averaged before stateful sample-area rate conversion. The renderer carries fractional sample areas when AudioContext does not supply requested 16 kHz. Fractional input state persists across irregular callback boundaries. This simple averaging converter is not a high-rejection studio resampler; alias suppression and live audio quality remain physical-test limitations.
- Sum sources with fixed 0.5 gain each, accumulate wider than PCM16 and clamp to PCM16 bounds. Combined native conversion uses unity gain rather than the legacy per-block automatic gain. This prevents mixer clipping but cannot repair clipping already present at a device.
- A mixer scheduling stall over 300 ms stops instead of sending an unbounded catch-up burst. STT send/native read waits retain the existing two-second limits.
- Either required source failing stops both; microphone track ending is also handled immediately. Device change/loss requires explicit restart. There is no source substitution, automatic transport retry, speech replay, separate STT stream or extra question/answer owner.

Stop/session end/logout/disconnect invalidate the existing renderer run and main epoch immediately. Tracks/processors, subscriptions and pending capture queues stop; backend sender/reader tasks and mixer buffers are disposed, STT closes and applicable answer work is canceled/discarded. Native open/read is allowed to settle before close. The existing lease remains held until native close succeeds. Restart waits for matching owned cleanup acknowledgement; timeout/unknown close reports failure, not success, and may require backend restart. Capture-start is conservatively latched as potentially processed audio before acknowledgement. A canceled startup/lease waiter cannot open a second owner. Manual-operation cleanup remains mode-aware.

## Changed-file inventory (Phase 3 only)

- New: `backend/app/pcm_mixer.py`, `backend/tests/test_grpc_combined.py`, `frontend/src/grpc_combined.test.js`, this record.
- Backend: `app/grpc_server.py`, `app/services/system_audio_capture.py`, `protos/interview_realtime.proto`, `app/grpc_generated/interview_realtime_pb2.py`.
- Backend regressions: `tests/test_grpc_computer_lifecycle.py`, `tests/test_grpc_health.py`, `tests/test_session_generation.py`.
- Desktop/renderer: `frontend/electron/grpc_realtime_client.cjs`, shipped `protos/interview_realtime.proto`, `frontend/src/App.jsx`, `grpc_auto_session.js`, `grpc_mic_test.js`, `live_mic_transport.js`, `realtime_router.js`.
- Frontend regressions: `grpc_auto_session.test.js`, `grpc_realtime_client.test.js`, `grpc_computer_auto.test.js`, `realtime_lifecycle.test.js`.

Some of these files already contain Phase 2 or unrelated hunks. Do not stage whole mixed files without reviewing the separate phase scopes. No files are staged or committed by this task.

## Verification

Automated input is synthetic; native capture, STT and model/storage are mocked. Localhost gRPC itself is real. No physical recording/playback, live provider request, runtime activation, real environment edits or hosted migrations were initiated.

Commands from repository root unless noted:

```powershell
python -m pytest backend/tests/test_grpc_combined.py backend/tests/test_grpc_computer_lifecycle.py -q -p no:cacheprovider
# From backend:
python -m pytest tests/test_session_generation.py -q -p no:cacheprovider
# From root:
$tests = @(Get-ChildItem frontend/src -Recurse -Filter '*.test.js' | ForEach-Object { $_.FullName })
node --test --test-reporter=tap $tests
python -m compileall -q backend/app
node --check frontend/electron/grpc_realtime_client.cjs
git diff --check
git diff --cached --name-only
# In the disposable checkout without any real .env:
python -m pytest backend/tests -q -k "not openai and not openrouter"
git hook run pre-commit
```

Observed results: **614 frontend tests passed**; **21 combined/native lifecycle tests passed**; **45 session-generation tests passed**. The disposable-checkout broad backend suite and normal pre-commit hook passed **1,192 tests, 2 skipped, 86 deselected**, production build, backend compile, Electron main/preload syntax, whitespace and **124 extension checks**. One additional synthetic native-start failure test was added afterward and passed in the focused 21-test run; it is not included in that broad count. Final renderer lifecycle checks passed **22 tests** after the microphone indicator correction. Existing Swig deprecation warnings and the bundle-size advisory remain. Matching protobuf copies, regeneration parity, scoped credential-pattern scan, final syntax/compile/whitespace and empty-index checks passed. Files outside the 22-file Phase 3 scope retain their captured baseline hashes.

Logs live in `../grpc-phase3-artifacts/`. The first broad current-tree run was stopped after failures exposed real-environment-sensitive test assumptions (for example selected-session model dispatch enabled where older test mocks return dictionaries). Verification was repeated in `../grpc-phase3-verify`, with current source copied, dependencies installed from the existing lockfile and no real environment file. Only disposable extension fixtures were restored to committed LF bytes for the known Windows autocrlf issue. No original fixture was changed.

Coverage includes known mixed amplitudes/headroom, native stereo conversion, split/whole 16/44.1/48 kHz continuity, a 10,000-tick synthetic drift/jitter run, overflow/underflow/late/duplicate frames, source loss, real localhost single STT, permission denial/late permission, renderer startup Stop, native lease cleanup on canceled open/read and waiter cancellation, rapid restart and old-event fencing. Existing logout/session-end tests and manual cleanup regressions remain. Session-selected generation failure/next-turn/save-once tests now run for microphone, system and combined.

## Windows manual acceptance — user to perform

1. Restart matching backend and Electron code; use exactly one local gRPC backend owner. Existing activation/settings must already permit the G9/G10 capabilities; this phase changes none. No migration is required. Configure Windows default output **before** Start.
2. Use headphones. Select Microphone + Computer and Auto. Grant microphone permission. Confirm pending startup becomes listening only after both captures initialize; verify one gRPC session and no legacy system capture. Play sanitized audio yourself, then speak yourself, then overlap both. Confirm transcription/questions/answers and selected-session model behavior; verify one final saved answer per logical turn.
3. Test quiet playback, microphone silence and both silent. Listening should continue. Mono mixing provides no reliable source attribution/diarization and no echo cancellation; do not use speakers for the initial test.
4. Stop during permission, capture startup, listening and generation. Restart rapidly, stop twice and deny permission. Verify indicators/tracks end, no delayed permission result restarts work, old events are ignored and native capture does not reopen before owned cleanup.
5. Remove microphone or change/remove default output. Both sources must stop with restart guidance. Do not expect automatic rebinding or one-source fallback. Restore the device, wait for cleanup, then explicitly restart. Restart backend if cleanup remains uncertain/failed.
6. Repeat transport disconnect, logout and matching cloud-session end during startup/listening/generation; unrelated session-end events must be ignored. No old audio, transcript or answer may restore ended work.
7. Recheck microphone-only and Computer-only, including Computer-only with microphone permission denied. Manual mode is unchanged. Run a longer combined session to assess drift correction, CPU/memory, latency, quiet-source gain and actual driver behavior.

No live audio quality, full physical acceptance or production readiness is claimed. Answer-token streaming/Phase 4 and the model-recovery migration remain deferred/paused.
