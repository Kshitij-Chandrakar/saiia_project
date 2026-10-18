# Proposed focused commit scope

## Feature-only commit verification (2026-10-18)

Final independent broad backend check (normal hook test selection): **1019 passed, 2 skipped, 86 deselected**, 5 existing SWIG warnings, 21.09 s. Broad-suite testing exposed a scoped-generator method-restoration bug that could bind a copied request generator to the shared receiver; fixed method restoration and added a regression test. Feature tests now give subprocesses an explicit backend cwd and isolate the readiness test from independent audio initialization. Initial hook attempts failed before these fixes; hooks were not bypassed.

The model-selection-only candidate has now been extracted and tested independently against HEAD in an isolated snapshot. Earlier mixed-tree commit warnings below describe the pre-isolation review, not the current candidate. No real environment or unrelated working file was replaced. Candidate main.py retains only the minimal project-validation lifespan; G9 gRPC server startup/stop and health/protobuf/audio/transport-routing changes remain outside this commit. Baseline gRPC defaults remain false.

Independent candidate checks: **196 backend tests passed** (5 existing SWIG warnings), **168 frontend tests passed**, **9 rendered tests passed** (Chromium plus isolated Electron at 421 x 484, mocked bridges), all **3 isolated PGlite SQL scripts passed**, and frontend build passed (2152 modules; existing chunk-size warning). Tests used existing installed dependencies and a blank snapshot dotenv, not production credentials. These do not add live provider/failure acceptance evidence.

The standalone gRPC entry point already exists in HEAD. Without the separate G9 lifecycle work, start it explicitly in another terminal when enabled for testing: from backend, `E:\deepfake_envs\SaIIA\python.exe -m app.grpc_server --host 127.0.0.1 --port 50051`. Never start it if another process owns 50051. This commit does not enable any flag or start/restart services.

Exact isolated backend command: `python -m pytest -q tests/test_answer_model_config.py tests/test_answer_model_foundation.py tests/test_session_model_contract.py tests/test_session_generation.py tests/test_model_admission.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_routes.py`.

Exact isolated frontend commands: `node --test src/desktop_auth_session.test.js src/generation_dispatch.test.js src/answer_stream_protocol.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/startup_login_screen.test.js`; `node --test tests/session_model_setup.browser.test.mjs`; `npm run build`. Run all three SQL scripts from the snapshot root with the existing PGlite dependency provisioned at their documented local path. No dependency tree, snapshot, screenshot or real dotenv belongs in the commit.


Prepared 2026-10-18 against the current uncommitted tree. **Nothing staged or committed.** Do not use `git add .` or stage mixed files wholesale. Scope is a review manifest, not a claim that an isolated staged patch has passed tests. Current-tree checks do not validate a selectively staged subset.

Proposed message: `feat: add configuration-driven session answer models`

## Whole-file feature changes

For existing tracked files below, all current diff hunks belong to this feature (do not replace the whole file with another snapshot):

- `backend/app/api/generate.py`
- `backend/app/api/interview_sessions.py`
- `backend/app/cloud/interview_sessions.py`
- `backend/app/grpc_answer_pipeline.py`
- `backend/app/grpc_cloud_context.py`
- `backend/app/nlp/answer_variation.py`
- `backend/tests/test_grpc_cloud_context.py`
- `backend/tests/test_interview_session_routes.py`
- `frontend/electron/desktop_auth_session.cjs`
- `frontend/src/answer_stream_protocol.test.js`
- `frontend/src/components/AnswerPanel.jsx`
- `frontend/src/components/StartupSessionSetupScreen.jsx`
- `frontend/src/components/startup-session-setup.css`
- `frontend/src/desktop_auth_session.test.js`
- `frontend/src/generation_dispatch.test.js`
- `frontend/src/startup_login_screen.test.js`

New feature source, tests, required migrations and legitimate bundled assets:

- `backend/app/answer_models.py`
- `backend/app/answer_generation.py`
- `backend/app/session_generation.py`
- `backend/tests/test_answer_model_config.py`
- `backend/tests/test_answer_model_foundation.py`
- `backend/tests/test_model_admission.py`
- `backend/tests/test_session_generation.py`
- `backend/tests/test_session_model_contract.py`
- `backend/tests/session_models.postgres.mjs`
- `backend/tests/session_generation.postgres.mjs`
- `backend/tests/session_model_bindings.postgres.mjs`
- `frontend/src/components/AnswerModelSelect.jsx`
- `frontend/tests/session_model_setup.browser.test.mjs`
- `frontend/tests/fixtures/session-model-electron.cjs`
- `frontend/tests/fixtures/session-model-setup.html`
- `frontend/tests/fixtures/session-model-setup.jsx`
- `supabase/migrations/20261018120000_add_session_model_selection.sql`
- `supabase/migrations/20261018150000_add_session_generation_turns.sql`
- `supabase/migrations/20261018180000_add_session_model_bindings.sql`
- `frontend/src/assets/provider-logos/googlegemini.svg`
- `frontend/src/assets/provider-logos/groq.svg`
- `frontend/src/assets/provider-logos/LOBE-ICONS-LICENSE.txt`
- `frontend/src/assets/provider-logos/openai.svg`
- `frontend/src/assets/provider-logos/README.md`
- `frontend/src/assets/provider-logos/SIMPLE-ICONS-LICENSE.txt`

Documentation (include only the new current-status annotation in the four older project docs; preserve all their historical text):

- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`
- `SAIIA_PRODUCTION_TECHSTACK.md`
- `docs/C6_DESKTOP_STARTUP_UI_SESSION_SETUP_PLAN.md`
- `docs/SESSION_ANSWER_MODELS_CLOSEOUT.md`
- `docs/SESSION_ANSWER_MODELS_COMMIT_SCOPE.md`
- `docs/SESSION_ANSWER_MODELS_CONFIGURATION.md`
- `docs/SESSION_ANSWER_MODELS_DEV_ACTIVATION.md`
- `docs/SESSION_ANSWER_MODELS_DEV_MIGRATION_VERIFICATION.md`
- `docs/SESSION_ANSWER_MODELS_DEV_ROLLOUT.md`
- `docs/SESSION_ANSWER_MODELS_PHASE1.md`
- `docs/SESSION_ANSWER_MODELS_PHASE2.md`
- `docs/SESSION_ANSWER_MODELS_PHASE3.md`
- `docs/SESSION_ANSWER_MODELS_PHASE4.md`

## Mixed files: exact semantic hunk selection

Coordinates refer to the closeout working tree and can shift. Use symbol/content anchors, splitting hunks when neighboring unrelated edits are combined.

| File | Include for model feature | Exclude / preserve unstaged |
|---|---|---|
| `.env.example` | Session flag/Gemini/deadline block; ANSWER_MODELS/default/fallback/overrides/disabled; project-guarded readiness block | G9 transport/lifespan/probe comments and USE_GRPC_AUTO_PIPELINE / CLOUD_CONTEXT default changes |
| `backend/app/config.py` | Five catalog settings at start; session-readiness/flag/Gemini/deadline block | Existing two gRPC default false-to-true changes |
| `backend/app/main.py` | Import/call validate_session_model_dev_activation at start of lifespan | G9 asynccontextmanager/lifespan gRPC start/stop changes; the feature validation must be placed in baseline startup lifecycle if G9 is not landed first |
| `backend/app/grpc_server.py` | uuid import; server-minted logical_turn_id/request_id; pipeline logical_turn_id argument; typed GenerationFailure/TurnStateError handling and auto_listening after failure | CheckHealth implementation |
| `frontend/electron/main.cjs` | safeAnswerStreamEvent attempt fields, terminal codes/message/retry_attempt; cloud:list-answer-models handler | Startup checkHealth probe |
| `frontend/electron/preload.cjs` | listAnswerModels in both narrow exposed APIs | checkGrpcRealtimeHealth and closeGrpcRealtime(run) transport changes |
| `frontend/electron/grpc_realtime_client.cjs` | answerRequestId/completedAnswerRequestId/answerFailureCode initialization/reset/status fields; request-id stale/completed fencing; Gemini provider acceptance; turn-start resets; full completed-text replacement; typed terminal clear while transport remains open | Health/probe state and methods, transport-route diagnostics, connection waiters/cleanup/run scoping, gRPC defaults, microphone/system admission changes and new health IPC |
| `frontend/src/App.jsx` | failedAnswerTurnRef and setup reset; streamAttempt fence; terminal error capture; UUID logical HTTP turn; retry clear when starting a fresh HTTP turn; gRPC onAnswer generating/error capture and Retry identity; generation-retry action; answerRetryAvailable reset on session close | realtime_router import, health/route diagnostics, transport fallback/status messages, audio cleanup/watchdogs/route lifecycle changes |
| `frontend/src/grpc_auto_session.js` | answerFailureCode block that clears failed turn, calls onAnswer with requestId/historyEntryId, resumes listening | G9 onFallback/onStartupFailure/onLifecycle, routing/cleanup/capture changes |
| `frontend/src/grpc_auto_session.test.js` | Test named `generation failure clears one turn without closing capture and next turn completes` | G9 routing/lifecycle fixture changes and transport fallback tests; split the combined added-test hunk |
| `frontend/src/grpc_realtime_client.test.js` | `turn failure clears provisional text, rejects stale events and keeps transport usable`; answerRequestId/answerFailureCode expectation additions only | Health tests/IPC expectations, defaults and other routing/cleanup changes; split shared getStatus expectation |

The existing gRPC contract carries logical identity in request_id; protobuf/health changes are not part of this model-selection commit. Existing legacy save idempotency now uses a unique logical turn rather than question-text hashing; its exact behavior change is intentional and covered in the Phase 3 record/test.

## Exclude entirely

- Every real `.env` variant and credentials, even if ignored.
- `tmp/**`, `graphify-out/**`, logs, screenshots, tooling/node_modules, local DB outputs, temporary test userData and evidence dumps.
- `backend/protos/interview_realtime.proto`, both generated Python protobuf files, `frontend/electron/protos/interview_realtime.proto` (G9 health contract).
- `docs/G9_REALTIME_ROUTING_FALLBACK.md`, `backend/tests/test_grpc_health.py`, `frontend/src/realtime_router.js`, its test, `frontend/src/realtime_lifecycle.test.js`, `frontend/src/components/MainDiagnosticsWindow.jsx`, `frontend/src/grpc_mic_test.js` and its test (existing realtime/audio work).

## Review findings and prerequisites to committing

No unrelated work was removed or staged. Fixed stale foundation-only comments in sanitized example configuration and config.py; updated stale status documentation through current annotations, retaining historical phases. Reviewed source retains ownership, immutable binding, request-scoped routing, replacement, terminal Retry and protected checkpoint/persistence boundaries. Missing post-fallback failure-code persistence remains a documented diagnostic limitation, not an inferred quota cause.

**Commit isolation remains a prerequisite:** the working tree mixes G9 and this feature, including a startup lifespan dependency. Either land/review G9 independently first, or construct the selective patch in an isolated checkout and adapt the validation call to its baseline startup hook, then run the focused suites on that exact patch. No isolated staged patch has been verified; current-tree green checks must not be presented as proof it applies/runs independently.

Test portability limits: SQL scripts import already-installed PGlite from ignored `tmp/transcript-delete-db/node_modules`; rendered fixture invokes the local absolute Python interpreter. They are legitimate test sources to include, but a clean CI checkout needs documented tooling provisioning/interpreter substitution before claiming reproducibility. Do not commit the temporary dependency tree. No new dependencies installed during closeout.

Live-model pending checks (Terra and Gemini Flash primary) are release verification limitations, not evidence of implementation success. Production target activation remains separately gated. Never use a feature commit to enable runtime settings or modify the deployed admission function.
