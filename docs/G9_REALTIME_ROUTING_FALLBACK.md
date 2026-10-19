# G9 — microphone realtime routing and fallback hardening

## Runtime audit (2026-10-16)

The repository is Intervucopilot, retaining SAIIA/intervuAI internal names. The working tree and index were clean at the start of this task. No applicable AGENTS.md was found. Graphify's existing graph was queried with its own vocabulary (`grpc realtime auto pipeline startup server microphone transport health fallback electron auth`); its results primarily point to legacy P8 documentation and package launch scripts, so current source was inspected directly.

Before G9:

- `python -m uvicorn app.main:app ...` starts FastAPI. It did not start gRPC.
- `frontend/package.json`'s `electron:dev` starts Vite and Electron only. `electron:build` builds the renderer and packages Electron; it does not package or spawn Python.
- `python -m app.grpc_server` starts the separately operated loopback server. `GRPC_REALTIME_ENABLED` gates its CLI.
- All seven requested switches defaulted to false in code/template: backend realtime/STT/answer, Auto pipeline, cloud context pipeline, Electron realtime/audio. Actual values in a developer's private environment may override defaults; the private environment is not changed by G9.
- `App.startAutoMode` captures a microphone stream, checks eligibility in `grpc_auto_session.js`, and attempts `GrpcRealtimeClient.connectAuto` through preload/main. The backend validates cloud auth/context before opening AssemblyAI streaming STT. PCM is mono 16 kHz signed little-endian, framed by the existing microphone transport. Detected questions flow through the existing utterance buffer and answer adapter into the existing generation pipeline, then bounded main-process snapshots update the renderer, overlay and history.
- System-only takes `startAutoStreamingSystem`; microphone standard mode takes `startAutoStreamingMic` (`/ws/auto-stt`) and the existing recording/REST fallback. Both-source Auto is intentionally blocked. These source behaviors remain unchanged.
- Cloud authorization remains in Electron main. `GrpcCloudContext.authorize/load` verifies JWT, identity, active session ownership/status, resume and job context. `grpc_answer_pipeline` remains the sole gRPC answer-save caller, with existing idempotent request identity. No persistence contract changes.

## Ownership and defaults after G9

When explicitly enabled, FastAPI's lifespan starts the loopback gRPC server and stops it on shutdown. A bind/start failure emits a generic warning and leaves REST available. Run one owner: the normal FastAPI lifecycle **or** the standalone gRPC command, not both. Verify deployment worker/port configuration before enabling.

Electron main performs a nonblocking startup health probe, plus an explicit probe before microphone Auto routing. `CheckHealth` is a bounded, provider-free unary RPC: no interview stream, microphone, transcript, auth metadata, STT connection or model request. It reports configured capabilities, **not** measured provider availability or credential validity. An older server without this RPC safely falls back.

| Switch | G9 code/template default |
| --- | --- |
| GRPC_REALTIME_ENABLED | false (deployment kill switch) |
| GRPC_STT_ENABLED | false |
| GRPC_ANSWER_STREAM_ENABLED | false |
| USE_GRPC_AUTO_PIPELINE | true |
| USE_GRPC_CLOUD_CONTEXT_PIPELINE | true |
| ELECTRON_GRPC_REALTIME_ENABLED | false (desktop deployment kill switch) |
| ELECTRON_GRPC_AUDIO_ENABLED | false |

Auto/cloud preference is enabled behind the deployment/capability gates. Explicit `false` remains honored. Packaged desktop still does **not** launch Python; global production enablement is not warranted until a compatible loopback backend is provisioned and physical acceptance passes. No credentials or private `.env` values were changed.

## Routing and failure contract

`realtime_router.selectRealtimeRoute` is the final deterministic routing decision. Legacy eligibility is reused, not replaced with a second auth system.

| Input | Route | Reason |
| --- | --- | --- |
| Healthy, enabled microphone; local context or valid cloud session | grpc_realtime | microphone_eligible |
| System-only | existing_default | system_audio_selected |
| Both selected | existing_default decision; existing UI blocks starting | system_audio_selected |
| Missing transport/disabled audio or capabilities | existing_default | grpc_unavailable |
| Failed/timed-out health | existing_default | grpc_health_failed / grpc_connection_timeout / grpc_unavailable |
| Explicit Auto kill switch | existing_default | config_disabled |
| Cloud context preference disabled | existing authenticated standard path | cloud_session_active |
| Confirmed auth/session/context block | blocked | auth_unavailable / cloud_session_invalid / cloud_session_ended / other whitelisted auth reason |
| Health passed but stream handshake failed | existing_default, before capture | grpc_start_failed / grpc_connection_timeout |

No fallback strips cloud IDs or silently turns a cloud session into local generation. Standard fallback retains the existing authenticated generation flow.

A stream failure may switch to standard mode only after gRPC cleanup succeeds and no question/answer commit, transcript, or sent audio could represent an unseen backend commit. Buffered speech is discarded, never replayed. Once any audio may have reached the server, lost delivery cannot prove no generation occurred: stop safely, retain the displayed answer, and require an explicit restart for the next question. This deliberately favors duplicate prevention over transparent recovery. There is no automatic retry/regeneration of a committed or uncertain question, no automatic save retry, and no hidden token reconnect.

Main retains a conservative commit latch and lifecycle stage through failures. Existing `manualRun`/question-number history identity and existing backend save identity are reused. Run-scoped close prevents late cleanup from closing a newer stream. Explicit Stop cancels connection/auth waits, request deadlines, capture queues/pacing, polling, cooldown/deadline timers, subscriptions, transcript buffers and pending utterances, aborts current standard generation, releases tracks and closes streams. Cleanup is idempotent; late callbacks are fenced by existing run/epoch guards. Fresh runs reset cloud/save/transport diagnostics.

Diagnostics include routing/default/reason, health and health timestamps, connection/failure/fallback state, source, cloud auth/session/context/save state, Auto run, question/answer transport, commit/stage and cleanup status. System mode reports cloud auth `not_applicable`, never a stale cloud-auth failure. Failed-run diagnostics remain visible until a new run or deliberate source change; live content is not replayed.

## Physical acceptance — not performed by automated tests

Use a test account/session; each actual speech/generation run may incur normal provider usage. Do not use real sensitive interview content. Start backend from `backend` with `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; enable backend realtime/STT/answer gates and the two Auto/cloud preference flags in that process. Do **not** also start the standalone gRPC command. Start Electron with its realtime/audio gates and Auto/cloud flags enabled, pointing to loopback port 50051; from `frontend` run `npm run electron:dev`. Keep secrets only in their existing server/main locations. Unset flags/restore their previous values after testing.

Backend terminal, from the repository root (provider configuration already installed separately):

```powershell
$env:GRPC_REALTIME_ENABLED = 'true'
$env:GRPC_STT_ENABLED = 'true'
$env:GRPC_ANSWER_STREAM_ENABLED = 'true'
$env:USE_GRPC_AUTO_PIPELINE = 'true'
$env:USE_GRPC_CLOUD_CONTEXT_PIPELINE = 'true'
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Separate Electron terminal, from the repository root:

```powershell
$env:ELECTRON_GRPC_REALTIME_ENABLED = 'true'
$env:ELECTRON_GRPC_AUDIO_ENABLED = 'true'
$env:USE_GRPC_AUTO_PIPELINE = 'true'
$env:USE_GRPC_CLOUD_CONTEXT_PIPELINE = 'true'
$env:ELECTRON_GRPC_REALTIME_HOST = '127.0.0.1'
$env:ELECTRON_GRPC_REALTIME_PORT = '50051'
Set-Location frontend
npm run electron:dev
```

1. **A — cloud microphone:** sign in, create/select a fresh active cloud interview with authorized resume/job context, select microphone only and Auto. Expect `selected_realtime_pipeline=grpc_realtime`, `grpc_health=healthy`, `cloud_grpc_auth_status=verified`, session/context true. Ask a sanitized question, see streamed answer, then `cloud_answer_save_status=saved`. Reopen website history and verify exactly one saved entry. Repeat with another question. No token must appear in renderer diagnostics.
2. **B — local microphone:** in development, choose the existing Local test session control (suspends cloud selections in memory), microphone only, Auto. Expect gRPC, continuous multiple questions and no cloud save (`n/a`). Restore cloud context afterward.
3. **C — system-only:** select system audio only and Auto. Expect `existing_default`, REST/WebSocket, `system_audio_selected`, cloud auth `not_applicable`, fallback-used false. Verify the stable loopback path still works. Both-source remains blocked as before.
4. **D — unavailable backend:** stop the gRPC-owning backend; restart FastAPI with realtime disabled so REST remains up, leaving Electron gates enabled. Start microphone Auto. Expect health unavailable and standard fallback before generation, exact health failure reason, fallback-used true, no crash. Separately interrupt gRPC after a question/delta: the answer must stay, no REST regeneration or duplicate cloud save may occur, and the user must explicitly restart for the next question.
5. **E — Stop/restart:** during listening, partial speech, generation and cooldown, press Stop twice. Confirm tracks/capture indicator stop, streams close, cleanup becomes clean, timers/pending buffers no longer update UI. Restart and expect a fresh Auto run and main run, no old transcript/question/save state, and one answer per new question. Also stop while health/authorization is pending, restart quickly, and ensure old cleanup cannot close the new stream.

Also validate expired/refreshed/switched-account auth, permission denial, sleep/wake, microphone removal, packaged backend provisioning/shutdown, and real provider startup failures before production promotion. A refreshed token intentionally invalidates the old stream and requires the existing explicit restart mechanism. No physical capture, live OAuth/cloud writes or paid generation was performed during implementation.

## Rollback

Set `USE_GRPC_AUTO_PIPELINE=false` in Electron and backend to retain standard Auto; backend realtime and Electron realtime/audio switches can also remain false. No schema/data rollback is needed. Ship matching backend/frontend proto bindings together; older backends without health support select standard fallback. The unrelated website, C10, migrations, transcript deletion and startup presentation are outside this change.

## Exact G9-only staging scope

Nothing is staged, committed or pushed by this task. Review and stage only these paths:

```text
.env.example
backend/app/config.py
backend/app/grpc_generated/interview_realtime_pb2.py
backend/app/grpc_generated/interview_realtime_pb2_grpc.py
backend/app/grpc_server.py
backend/app/main.py
backend/protos/interview_realtime.proto
backend/tests/test_grpc_health.py
docs/G9_REALTIME_ROUTING_FALLBACK.md
frontend/electron/grpc_realtime_client.cjs
frontend/electron/main.cjs
frontend/electron/preload.cjs
frontend/electron/protos/interview_realtime.proto
frontend/src/App.jsx
frontend/src/components/MainDiagnosticsWindow.jsx
frontend/src/grpc_auto_session.js
frontend/src/grpc_auto_session.test.js
frontend/src/grpc_mic_test.js
frontend/src/grpc_mic_test.test.js
frontend/src/grpc_realtime_client.test.js
frontend/src/realtime_lifecycle.test.js
frontend/src/realtime_router.js
frontend/src/realtime_router.test.js
```

Graphify reflection/query memory is local ignored tooling output, not a G9 commit artifact. No migration, dependency or model-selection change is required.

## Earlier G9 verification results (historical)

- Frontend Node suite: **488 passed**, 0 failed, 0 skipped (`node --test` over all `frontend/src/**/*.test.js`). Includes routing, health timeout/safety, before-commit fallback, post-question/start/delta/uncertain-audio no replay, capture-start failure after PCM, run-scoped close, silent token/user invalidation, queued PCM cancellation, actual renderer Stop, double Stop, fresh restart and stale standard-generation completion guards.
- Backend gRPC suite: **84 passed** across the gRPC test files. Includes real loopback health RPC with synthetic settings, existing Auto utterance buffering/topic prompts, ownership/session/context rejection, cloud save-once/idempotency, manual/answer streaming and legacy system implementation regression coverage. The legacy server-side system tests do not enable any Electron system route.
- `scripts/pre_commit_audit.ps1`: **passed**. Backend **882 passed, 2 skipped, 77 deselected** under its existing `not openai and not openrouter` selection; Python compile, production build, Electron syntax and browser-extension validation (**124 passed**) passed. The first broad run exposed a test-order dependency from eagerly importing unrelated Whisper/scipy adapters; the new lifecycle test now isolates and executes the actual lifespan function without those unrelated imports. No dependency was changed.
- After the final stale-standard-generation guard, the complete frontend suite and production build passed again. Build still reports the existing >500 kB bundle advisory.
- `git diff --check` passed; backend/shipped proto SHA-256 hashes match. No excluded files or index entries changed.
- These are automated state-machine/mock-provider checks and a local transport RPC check. No physical microphone/system audio, live OAuth, real cloud-save/delete, paid provider request, packaged-runtime provisioning, latency or accuracy measurement was performed. Physical acceptance above remains required before production promotion.


## Phase 1 isolated microphone baseline verification (2026-10-19)

This phase includes only microphone/G9 baseline files and selected gRPC hunks from mixed files. Screen-context work, model-review documentation corrections, real environment files and database migrations are excluded. System-source guards and the combined-mode block remain unchanged. Existing session-model routing is reused from HEAD; no new STT, generation or persistence owner was introduced.

Narrow hardening in this phase:

- Toolbar Stop and End Session now invalidate an Auto start while microphone permission is pending, through the existing Stop path.
- A matching cloud-session-ended event stops renderer capture before clearing session ownership. Electron main closes the matching gRPC connection before the cloud end request; application finalization also closes local Auto streams.
- The health test resolves its backend import from its own location, so it runs from a clean checkout without implicit PYTHONPATH or ignored tooling.
- Added executable regressions for pending-start Stop, matching session end, logout ordering, application finalization, permission rejection and servers without CheckHealth.

Verification used a detached worktree based on the current HEAD, with only the proposed 23-file baseline applied. Dependencies were installed from the existing frontend lockfile with `npm ci --no-audit --no-fund`. No real environment file was copied into that worktree.

Commands and observed results:

- From `frontend`: `$tests = @(Get-ChildItem src -Recurse -Filter '*.test.js' | ForEach-Object { $_.FullName }); node --test --test-reporter=tap $tests` ? 531 passed, zero failed/skipped.
- From `backend`: `python -m pytest tests/test_grpc_health.py tests/test_grpc_realtime.py tests/test_grpc_auto.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_manual.py tests/test_grpc_system_audio.py tests/test_grpc_utterance_buffer.py tests/test_session_generation.py -q -p no:cacheprovider` ? 125 passed. These include actual ephemeral localhost gRPC connections with synthetic audio and mocked STT/model/storage, selected-model routing/save-once checks, and generation failure followed by another question on the same connection.
- From the repository root: `python -m pytest backend/tests/test_grpc_health.py -q -p no:cacheprovider` ? 2 passed independently.
- The standard `scripts/pre_commit_audit.ps1` backend selection passed 1,038 tests, with 2 skipped and 86 deselected; backend compile, frontend production build and Electron main/preload syntax checks passed.
- Browser-extension validation passed all 124 tests after restoring fixture bytes from Git in the disposable worktree. Its initial run failed on CRLF-converted fixture text under Windows `core.autocrlf=true`; no extension source/fixture changes are part of this commit.
- Both protobuf copies are byte-identical. Regenerating Python bindings into an OS temporary directory using the installed pinned grpcio-tools produced the same bindings (with the repository's relative-import adjustment).
- Scoped credential-pattern scanning of all 23 proposed files found no private keys, AWS/Google/provider/GitHub tokens or JWTs. This is a pattern scan, not a guarantee against every secret format.

The normal Git pre-commit hook remains enabled for the baseline commit. Original mixed working files are preserved; only verified baseline blobs enter the commit. Test/build output and local Graphify output remain uncommitted.

No physical microphone capture, playback, live provider call, cloud write or migration was performed. User-reported microphone success remains separate from automated evidence. The existing build bundle-size advisory and dependency deprecation warnings remain. This establishes a tested software prerequisite for Computer-only planning/implementation, not physical Windows or production readiness. The model-recovery migration remains paused pending CodeRabbit review.
