# G12: gRPC Auto audio closeout (Phase 4)

## Status and acceptance

Computer-only and Microphone + Computer Auto are complete for focused local integration. Microphone-only remains supported. This closes the audio verification/documentation phase; answer-token streaming is a separate deferred task.

On 2026-10-19 the **user reported** that physical Windows checks passed for both sources, overlap, Stop/restart, permission denial, device loss, logout and session end. Earlier Computer-only success was also user-reported. The agent did not observe or perform those physical tests and does not infer long-duration audio quality, every driver/device scenario or production readiness from that report.

The model-recovery migration remains paused. No environment, credential, runtime activation, database, migration, deployment, push or merge operation is part of this closeout.

## Baseline and execution plan

Verified history: `dd22af7` microphone routing and `34430fc` lifecycle/router fixes are ancestors of the intended parent, merge commit `1c676ad` from PR #49. At the start, `dev/current-work` contained unstaged Phase 2/3 work alongside unrelated screen-context/model-review changes; the index was empty. No applicable AGENTS.md was found. Ponytail and Electron boundary guidance were applied. Graphify was queried/updated before and after review; current source was the implementation authority.

Plan executed: inspect the working tree and source contracts; fix confirmed audio defects; select only complete audio dependencies/hunks; verify the exact patch in a detached checkout of the intended parent without real environment files; run normal hooks and create a focused local commit; attach that verified commit without rewriting working files or absorbing unrelated staging.

Baseline status, tracked diff, file hashes (including real environment files, without contents), exact scope and verification logs are retained outside the repository in `../grpc-phase4-artifacts/`. The disposable checkout is `../grpc-phase4-verify/`.

## Final architecture

| Auto source | Capture and STT route | Failure policy |
| --- | --- | --- |
| Microphone | Existing renderer microphone PCM through Electron/gRPC; existing supported standard route remains available under its established rules | Existing pre-processing fallback guards remain; uncertain/processed audio is not replayed |
| Computer | Backend default-output WASAPI loopback directly into the existing STT connection; gRPC owns control and answer/transcript events | No microphone acquisition/PCM; no alternate transport or source; explicit restart |
| Microphone + Computer | Renderer microphone PCM and backend WASAPI feed one bounded backend mono mixer, then one STT receiver/question intake/answer pipeline | Either source failing stops the required resources; no one-source substitution or transport fallback; explicit restart |

Wire audio remains bounded mono 16 kHz signed little-endian PCM. Output frames are 3,200 bytes / 100 ms. Computer rejects client PCM. Combined validates the same microphone PCM contract, sequences and optional timestamps. Additive health fields `system_audio_available = 5` and `combined_audio_available = 6` distinguish capabilities from older servers; health opens no device, provider or interview. RPC signatures and audio messages are unchanged, and matching Python message bindings are regenerated.

Default output uses PyAudioWPatch's default-WASAPI loopback resolver, never first-enumerated-device selection. Reads monitor output changes; no automatic device rebinding. Manual combined recording remains unsupported. The selected Auto path cannot also start the legacy system HTTP/WebSocket flow.

The mixer has 500 ms / 8,000 samples per source, fixed 0.5 gains and wide accumulation/clamping. Fractional sample-area conversion is stateful across chunks. Output waits for both sources, then uses the backend monotonic cadence and a 200 ms initial jitter allowance. Underflow zero-fills; overflow discards bounded backlog and reanchors. New renderer frames older than 300 ms are discarded before IPC; elapsed sender timestamp durations are anchored to backend arrival rather than comparing unrelated clocks. Legacy absent metadata remains supported with arrival ordering. Delivery absence over two seconds, five-second initial source timeout or excessive mixer scheduling delay ends the run; PCM silence alone does not.

Run/session/request/main-epoch fencing rejects late permission, PCM, native-read, STT and answer events. Stop discards pending speech and cancels applicable generation. Exclusive native ownership survives canceled open/read until actual release. Restart waits for matching cleanup acknowledgement; uncertain or failed release is reported honestly and may require backend restart. Capture startup is conservatively treated as potentially processed audio, including lost acknowledgement.

Existing authorization, session ownership, immutable session-selected model routing, provider answer fallback, explicit Retry and final-save ownership remain unchanged. There is no second STT/question/answer/save pipeline. UI transcript/answer events remain available intentionally; diagnostic payloads contain counters/status/numeric audio measurements instead of transcript excerpts, raw PCM or credentials.

## Confirmed review fixes

1. On transport disconnect, native release previously preceded generation cancellation. A blocked native read could delay canceling work capable of persistence. Cleanup now cancels the answer worker before awaiting native release. A real localhost synthetic test failed by cancellation timeout before the fix and passed after it.
2. Combined capture skipped native rate/RMS/peak updates and reported an unused system queue as its buffer depth. Native measurements now update for both source modes; combined depth/drop counters describe the bounded mixer. Synthetic localhost assertions cover these diagnostics.
3. Existing question-intake diagnostics exposed ignored-transcript and utterance-buffer excerpts. Backend diagnostic construction now omits those fields, Electron also strips them from older-server diagnostics, and diagnostic rows no longer display them. Internal detection/buffering and explicit transcript/answer UI events are preserved. Regressions verify redaction and retained counters.

## Verification evidence

Providers, native capture and storage use deterministic fakes/synthetic audio. Localhost gRPC transport is real. No physical recording/playback or live provider request was initiated. Verification uses the exact audio-only patch on `1c676ad`, with no real `.env` copied and dependencies installed from the existing lockfile. Unrelated screen/model changes are absent from that checkout.

Commands (PowerShell):

```powershell
# Disposable checkout root:
$grpcTests = @(Get-ChildItem backend/tests -Filter 'test_grpc*.py' | ForEach-Object { $_.FullName })
python -m pytest $grpcTests backend/tests/test_session_generation.py -q -p no:cacheprovider
$tests = @(Get-ChildItem frontend/src -Recurse -Filter '*.test.js' | ForEach-Object { $_.FullName })
node --test --test-reporter=tap $tests
git hook run pre-commit
# Normal commit runs the same hook again, without bypass flags.
git diff --check
git diff --cached --check
python -m compileall -q backend/app
node --check frontend/electron/grpc_realtime_client.cjs
```

The normal repository hook also runs `python -m pytest backend/tests -q -k "not openai and not openrouter"`, frontend `npm run build`, Electron main/preload syntax and browser-extension validation. In the disposable checkout only, unchanged extension fixtures use their committed LF bytes to avoid the known Windows autocrlf artifact; no extension file is included in the patch.

Protobuf verification compares both shipped proto files byte-for-byte and regenerates Python messages with `python -m grpc_tools.protoc -I backend/protos --python_out=<temporary-directory> backend/protos/interview_realtime.proto`, then compares generated bytes. A scoped pattern scan checks private-key/provider/GitHub token patterns without printing potential secrets. These checks are pattern-based, not a guarantee against every secret format.

Final exact-patch results: **561 frontend tests passed**; **156 gRPC/session-generation tests passed**; the normal hook backend selection passed **1,069 tests, 2 skipped, 86 deselected**. Backend compile, Electron syntax, frontend production build, matching proto/regenerated messages, whitespace and the scoped credential-pattern scan passed. Current mixed-working-tree frontend regressions separately passed **615 tests**; their higher count includes unrelated Screen tests excluded from this commit.

The first hook run passed backend/build/syntax but failed six extension fixture assertions on CRLF-versus-LF text. Restoring the 108 disposable fixtures to their exact committed bytes addresses the checkout artifact without changing tests or the original tree. The normal hook is rerun without bypass flags; the resulting extension validation covers **124 checks**. Existing Swig deprecation warnings, dependency deprecation messages and the large-bundle build advisory remain outside this audio patch.

The focused local commit message is `feat: add computer and combined audio to gRPC Auto`. The commit runs normal hooks again and includes only the reviewed 30-file audio scope below.

Coverage includes all three modes, no microphone/legacy transport in Computer mode, no transport fallback in Computer/combined, permission rejection and late permission, partial startup, native ownership/acknowledged cleanup, Stop/restart, logout/session end, old events, output selection/change/loss, disconnect, quiet PCM, overlapping signals/headroom, irregular 16/44.1/48 kHz conversion, jitter/drift/late/overflow/underflow bounds, selected-model generation failure/next-turn/Retry/persistence and diagnostic privacy.

## Reviewed commit scope

- Backend implementation: `backend/app/grpc_server.py`, `backend/app/pcm_mixer.py`, `backend/app/services/system_audio_capture.py`, `backend/app/grpc_generated/interview_realtime_pb2.py`, `backend/protos/interview_realtime.proto`.
- Backend regressions: `backend/tests/test_grpc_health.py`, `test_grpc_system_audio.py`, `test_grpc_computer_devices.py`, `test_grpc_computer_lifecycle.py`, `test_grpc_combined.py`, `test_session_generation.py`.
- Desktop contract: `frontend/electron/grpc_realtime_client.cjs`, `frontend/electron/protos/interview_realtime.proto`.
- Renderer implementation: audio-only hunks in `frontend/src/App.jsx` and diagnostic-row hunks in `frontend/src/components/MainDiagnosticsWindow.jsx`; `grpc_auto_session.js`, `grpc_mic_test.js`, `live_mic_transport.js`, `realtime_router.js`.
- Frontend regressions: `frontend/src/grpc_auto_session.test.js`, `grpc_realtime_client.test.js`, `realtime_router.test.js`, `grpc_computer_auto.test.js`, `grpc_combined.test.js`, and audio-only `realtime_lifecycle.test.js` hunks.
- Records: `docs/G10_COMPUTER_GRPC_AUTO.md`, `docs/G11_COMBINED_GRPC_AUTO.md`, this record; only current-audio status blocks in `docs/G9_REALTIME_ROUTING_FALLBACK.md` and `SAIIA_PRODUCTION_PHASES_TRACKER.md`.

Main/preload/auth screen-context changes, Screen UI/code/tests/docs, model-review changes, unrelated roadmap content, real environments, logs, recordings and temporary tooling are excluded. No new dependency is needed; existing NumPy/SciPy, PyAudioWPatch, gRPC and frontend dependencies suffice. The generated service binding is unchanged because the RPC signature did not change.

The original index was empty. Explicit paths/selective hunks are staged only from the reviewed checkout. The commit must have the intended parent and exactly the tested tree. Its audio blobs can then be attached to the original branch/index with compare-and-swap parent/tree checks, leaving original working files physically unchanged. Any concurrent staging change blocks attachment rather than being absorbed. Final before/after hashes verify preservation.

## Remaining limitations and restart guidance

- Use headphones: combined mono mixing provides neither echo cancellation nor reliable speaker/source attribution. Overlapping speakers may reduce STT accuracy.
- Timing uses bounded drop/zero-fill correction, not adaptive hardware-clock synchronization. Corrections can cause discontinuities. Callback timestamps do not establish sample-perfect physical alignment. Simple averaging conversion is not a high-rejection studio resampler; clipping already present at input cannot be repaired.
- Output change/loss and either required-source failure require explicit restart. Silence remains listening. After uncertain native cleanup, wait for a fresh successful capability check or restart the local backend.
- Use one local gRPC backend owner; capture exclusion is scoped to that service process, not an OS-wide multi-process lock. Electron still does not bundle/provision Python; packaged deployment remains a separate concern.
- Restart matching backend and Electron code after integration to load capabilities/bindings. This task does not activate flags or change existing deployment settings.
- User-reported Windows acceptance is attributed above; extended real-device quality/performance and other driver/platform coverage remain limitations. Microphone-only behavior and manual-mode policies are unchanged.

Stop after this Phase 4 closeout. Answer-token streaming is deferred as a separate future task. The model-recovery database migration remains paused.
