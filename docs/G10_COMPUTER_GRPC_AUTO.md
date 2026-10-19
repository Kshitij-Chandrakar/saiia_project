# Phase 2: Computer-only gRPC Auto

> Phase 4 update: Final verification and focused audio integration are recorded in [G12 closeout](G12_GRPC_AUDIO_CLOSEOUT.md). The user reports that Windows checks for both sources, overlap, Stop/restart, permission denial, device loss, logout and session end passed. Earlier staging and manual-test statements below are historical phase evidence. Answer-token streaming remains deferred; the model-recovery migration remains paused.

Computer-only uses local-backend WASAPI loopback capture. gRPC owns session control and transcript/answer events; system PCM goes directly from backend capture to the existing STT socket. No microphone MediaStream, renderer PCM capture or microphone IPC frames are used. Microphone Auto keeps its existing behavior and fallback policy. Combined mode remains rejected.

## Capability and compatibility

`RealtimeHealth.system_audio_available` is an additive bool at field 5. It reports configured STT/answer/Auto readiness, Windows/PyAudioWPatch availability and capture ownership/cleanup readiness. The probe opens no device, starts no interview/STT and invokes no model. Actual default-device access is checked only on explicit Start. Missing/false capability, including older servers, blocks Computer startup with restart/configuration guidance; it never switches to HTTP or WebSocket capture.

Both protobuf copies match. Python protobuf bindings are regenerated; the unchanged service binding remains compatible. No audio-format, model-selection, Retry, persistence or database contract changes are introduced.

## Capture and lifecycle

- Resolve Windows default output through PyAudioWPatch's `get_default_wasapi_loopback`, not enumeration order. Unavailable default output is an error, never a substitution with the first device.
- Keep the existing 16 kHz mono linear16 conversion and 3,200-byte framing, three-frame bounded capture queue, single STT socket and shared intake/answer worker. Backend and Electron both reject client PCM for Computer sessions.
- Reserve a backend capture lease before opening STT/capture. Native open/read is shielded from cancellation; cleanup retains the lease until the native operations settle and close succeeds. A second session waits for ownership without opening a second STT or device. Electron bounds startup, and cancellation safely removes a waiting RPC without orphaning the lease.
- Stop cancels/discards pending speech and generation, as before. It does not drain/replay speech through another transport. Server capture startup is conservatively treated as possibly processed audio before Electron receives readiness.
- Electron invalidates the run immediately and requests end-session with matching transport session/request IDs. It reports clean only after matching backend `ended`; pending cleanup, disconnect or timeout reports failure. Backend cleanup waits up to three seconds before reporting `system_cleanup_pending`, while retaining ownership until native cleanup actually finishes. An uncertain native close requires a local backend restart.
- Fresh health after explicit restart can establish that delayed cleanup finished. There is no automatic transport retry, capture rebinding or speech replay. Main-process epochs, renderer runs, transport session IDs and run-scoped close fence late events and cleanup.
- Default-output changes are checked on native reads at most once per second, and read errors/stalls stop capture. Silent PCM does not cause capture failure. A changed/lost device requires explicit restart; the capture never silently follows a new output.
- Existing logout/session-end/finalization cleanup uses the same close path. Session ownership, authoritative model binding, generation failure handling, answer fallback, explicit Retry and one final persistence owner remain unchanged.

## Verification

The feature was developed and checked in a detached checkout of `dd22af7`, with no real environment file, ignored project tooling or uncommitted screen/model changes copied in. Dependencies use the existing frontend lockfile. Per the latest user instruction, this phase is not staged or committed.

Commands (PowerShell):

```powershell
# From the repository root:
python -m pytest backend/tests -q -k "not openai and not openrouter"
$grpcTests = @(Get-ChildItem backend/tests -Filter 'test_grpc*.py' | ForEach-Object { $_.FullName })
python -m pytest $grpcTests backend/tests/test_session_generation.py -q -p no:cacheprovider

# From frontend:
$tests = @(Get-ChildItem src -Recurse -Filter '*.test.js' | ForEach-Object { $_.FullName })
node --test --test-reporter=tap $tests

# From the repository root, invokes the existing normal hook without a commit:
git hook run pre-commit
```

Coverage includes actual renderer Computer Start with forbidden microphone/legacy capture APIs; capability and combined-mode rejection; PCM input exclusion; late startup/events; owned cleanup and rapid restart; synthetic localhost gRPC with fake loopback/STT; silence, open/read/close failure and cleanup timeout; non-first Windows default selection; output-change rejection; microphone regression; and Computer-selected model generation failure followed by another turn with one final save. Observed isolated results: 539 frontend tests passed; 140 gRPC/session-generation tests passed; the broad backend selection passed 1,053 tests with 2 skipped and 86 deselected. The directly invoked normal hook passed production build, Electron syntax, compile/whitespace and all 124 browser-extension checks. No staging or commit was performed.

Credential-pattern scanning, whitespace checks, matching protobuf/regenerated bindings, Electron syntax and production build are included. Browser-extension fixtures in the disposable checkout use their committed LF bytes to avoid the known Windows autocrlf test artifact; no extension change is included. Existing dependency deprecation and large-bundle advisories are outside this feature.

## Windows manual acceptance (not performed)

1. Restart the local backend and Electron to load matching code/protobufs. Use one loopback backend owner/process, through FastAPI lifespan or standalone, not both. Electron packaging still does not bundle Python.
2. Confirm the deployment already permits `GRPC_REALTIME_ENABLED`, `GRPC_STT_ENABLED`, `GRPC_ANSWER_STREAM_ENABLED`, `USE_GRPC_AUTO_PIPELINE`, `ELECTRON_GRPC_REALTIME_ENABLED` and `ELECTRON_GRPC_AUDIO_ENABLED`. Cloud sessions also need the existing cloud-context/session-model readiness. No real environment values or runtime switches were changed by this phase.
3. Choose the Windows default playback output before Start. Select Computer only and deny/disable microphone access. With user-controlled playback, confirm gRPC is selected, source is system, an answer streams, and exactly one final session entry is saved using the selected answer model.
4. Verify silence stays listening; unavailable gRPC/loopback shows actionable error and starts no alternate transport. Both-source remains blocked. Repeat microphone-only acceptance to check its existing behavior.
5. Stop during startup/listening/generation, press Stop twice, then restart rapidly. Confirm old events cannot update the new run and the device is not reopened before cleanup. Repeat logout and matching session end.
6. Change/remove the output device or disconnect the backend. Expect stopped/error state and explicit restart. Wait for cleanup; restart the local backend if native cleanup remains failed. Do not infer successful cleanup from a stopped renderer alone.

No physical recording, playback, live provider request, hosted migration or runtime activation was performed during automated verification. Real driver/device behavior and live latency/accuracy remain manual acceptance work. The existing per-block resampling and driver-specific loopback mapping limitations are unchanged. No source attribution/diarization or combined mixing is claimed. The model-recovery migration remains paused pending CodeRabbit review.
