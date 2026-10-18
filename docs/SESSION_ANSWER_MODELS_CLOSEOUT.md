# Intervucopilot session answer models: closeout

## Feature-only commit verification (2026-10-18)

Final independent broad backend check (normal hook test selection): **1019 passed, 2 skipped, 86 deselected**, 5 existing SWIG warnings, 21.09 s. Broad-suite testing exposed a scoped-generator method-restoration bug that could bind a copied request generator to the shared receiver; fixed method restoration and added a regression test. Feature tests now give subprocesses an explicit backend cwd and isolate the readiness test from independent audio initialization. Initial hook attempts failed before these fixes; hooks were not bypassed.

The model-selection-only candidate has now been extracted and tested independently against HEAD in an isolated snapshot. Earlier mixed-tree commit warnings below describe the pre-isolation review, not the current candidate. No real environment or unrelated working file was replaced. Candidate main.py retains only the minimal project-validation lifespan; G9 gRPC server startup/stop and health/protobuf/audio/transport-routing changes remain outside this commit. Baseline gRPC defaults remain false.

Independent candidate checks: **196 backend tests passed** (5 existing SWIG warnings), **168 frontend tests passed**, **9 rendered tests passed** (Chromium plus isolated Electron at 421 x 484, mocked bridges), all **3 isolated PGlite SQL scripts passed**, and frontend build passed (2152 modules; existing chunk-size warning). Tests used existing installed dependencies and a blank snapshot dotenv, not production credentials. These do not add live provider/failure acceptance evidence.

The standalone gRPC entry point already exists in HEAD. Without the separate G9 lifecycle work, start it explicitly in another terminal when enabled for testing: from backend, `E:\deepfake_envs\SaIIA\python.exe -m app.grpc_server --host 127.0.0.1 --port 50051`. Never start it if another process owns 50051. This commit does not enable any flag or start/restart services.

Exact isolated backend command: `python -m pytest -q tests/test_answer_model_config.py tests/test_answer_model_foundation.py tests/test_session_model_contract.py tests/test_session_generation.py tests/test_model_admission.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_routes.py`.

Exact isolated frontend commands: `node --test src/desktop_auth_session.test.js src/generation_dispatch.test.js src/answer_stream_protocol.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/startup_login_screen.test.js`; `node --test tests/session_model_setup.browser.test.mjs`; `npm run build`. Run all three SQL scripts from the snapshot root with the existing PGlite dependency provisioned at their documented local path. No dependency tree, snapshot, screenshot or real dotenv belongs in the commit.


Date: 2026-10-18. Implementation complete for development testing; production release is separate. This is the current status, superseding phase-time statements without rewriting their historical results.

## Implemented scope and ownership

Backend-owned startup catalog drives `GET /api/interview-sessions/answer-models` and the existing Electron Create Session AI Model control through authenticated narrow IPC. Names/order/descriptions/default come from the backend. Bundled provider SVGs include provenance/licenses; unknown logo keys use a neutral local icon. Portal positioning, internal scroll, keyboard navigation, selected/disabled descriptions and focus restoration preserve the existing 421 x 484 setup/footer. No active-session selector or last-selection memory.

New sessions default to Gemini 3.5 Flash-Lite. Creation validates stable keys, includes immutable execution snapshots in idempotency, enforces ownership, and returns authoritative selection. API/RPC/database guards prevent selection/owner/binding mutation while preserving lifecycle updates. Historical unbound rows stay legacy; no invented historical model or transcript backfill. Existing snapshot bindings survive catalog removal/profile edits. Old five-key pre-snapshot bindings use frozen compatibility profiles. Unsupported snapshots fail closed.

Owned active sessions route HTTP manual answers, typed Chat, standard Auto/live follow-ups and cloud gRPC Auto through request-scoped providers. Existing prompts, resume/JD retrieval, formatting and validation remain. Corrections use the current attempt provider. STT/classification, direct OCR/vision answers, dashboard Ask AI and AI Notes remain on independent routing; this feature does not claim those surfaces use the session answer model.

Selected model runs first; eligible failure tries Groq GPT-OSS 120B once, silently. Missing Gemini credentials do not block creation and immediately take fallback. No self-fallback; every subsequent question starts at the selected model. Authorization/lifecycle/cancellation/supersession stops do not trigger fallback. Shared first-token/idle/overall deadlines and fallback reserve bound the whole turn. HTTP replace events clear failed partial text; gRPC full answer_completed replaces provisional text. Typed terminal failure clears text and exposes ?Unable to generate an answer? with Retry. Retry reuses the captured failed turn without audio recapture or a second history entry.

One backend claim/checkpoint/complete boundary owns final validated persistence. Restricted selected/actual provider/API identifiers and fallback_used preserve historical truth. Claims/checkpoints have service-only access, forced RLS, ownership checks and transcript-equivalent deletion/session-close cleanup. Completed replay and checkpoint save-only recovery do not regenerate. Processing leases expire after 120 seconds into uncertain recovery; crash-before-checkpoint uncertainty does not regenerate automatically. Fencing/database deduplication does not guarantee exactly one upstream execution after crashes. Existing gRPC request_id carries server-minted turn identity; Retry recovers it over existing HTTP, not a new protobuf retry contract. Auto source metadata alone does not identify the transport used.

## Development activation and configuration

Activated only on Saiia-dev (`rbmxfazjbldmkomdpyzl`). All three reviewed migrations applied in order and ledger/schema/RPC/access restrictions verified; see [migration verification](SESSION_ANSWER_MODELS_DEV_MIGRATION_VERIFICATION.md). Project-guarded development readiness, backend execution and database admission are enabled locally. Shipped defaults remain disabled. See [activation record](SESSION_ANSWER_MODELS_DEV_ACTIVATION.md) and [reviewed rollout](SESSION_ANSWER_MODELS_DEV_ROLLOUT.md). This closeout changes no runtime settings or database state.

Backend dotenv: repository root `.env`. Never commit it. Gemini reads GEMINI_API_KEY, with GOOGLE_API_KEY fallback. Credential detection is verified; values are never recorded. Process environment overrides dotenv.

To add a protocol-compatible model, append `provider:api-id` to ANSWER_MODELS in the backend dotenv; ordering controls new choices. Supported providers: openai, groq, gemini. Optional ANSWER_MODEL_OVERRIDES supplies bounded labels/descriptions/profile/effort/output_limit. Keep ANSWER_DEFAULT_MODEL and ANSWER_FALLBACK_MODEL valid catalog entries. Default is `gemini:gemini-3.5-flash-lite`; fallback is `groq:openai/gpt-oss-120b`. Adding a provider or incompatible API requires adapter work; configuration does not prove account access. See [configuration reference](SESSION_ANSWER_MODELS_CONFIGURATION.md).

To remove a new choice, remove its entry and corresponding overrides; adjust default/fallback first if needed. Restart all backend workers using their existing interpreter/environment. Do not start a duplicate server. Normal local command, after gracefully stopping the existing instance:

```powershell
Set-Location E:\saiia_project\saiia_project\backend
E:\deepfake_envs\SaIIA\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Refresh setup/catalog after restart. A stale open setup refreshes choices and requires explicit valid selection; it never substitutes another model. Existing bindings retain their snapshot and continue execution after removal. ANSWER_DISABLED_MODELS explicitly disables an identity even for existing sessions and follows eligible fallback; it does not rewrite stored selection.

Pause new admission by changing only the development DB `session_model_routing_ready()` helper to false using the reviewed activation instructions. Leave execution/readiness on for existing bound sessions. Do not clear binding snapshots, reclassify sessions or delete claims. Disabling execution/readiness instead fails bound execution closed. Production requires its own reviewed readiness/target mechanism, migrations/access checks, deployment configuration and acceptance; the current hard-coded development guard deliberately does not admit another project.

## Evidence, with limits

User confirmation ?everything is working? is recorded as **user-reported manual success** only. It does not establish unreported model/transport/failure tests.

Read-only restricted metadata review on Saiia-dev (100 most recent saved transcript metadata rows, no question/answer text or identities printed):

| Selection | Primary successes observed | Fallback successes observed | Status |
|---|---:|---:|---|
| GPT-5.6 Luna | 2 | 0 | Selected and actual OpenAI / gpt-5.6-luna match; fallback_used=false |
| GPT-5.6 Terra | 0 | 0 | No evidence in reviewed records; pending |
| GPT-OSS 120B | 3 | 0 | Selected and actual Groq / openai/gpt-oss-120b match; fallback_used=false |
| Gemini 3.5 Flash-Lite | 3 | 0 | Selected and actual Gemini / gemini-3.5-flash-lite match; fallback_used=false |
| Gemini 3.6 Flash | 0 | 1 | Selection retained; actual Groq / openai/gpt-oss-120b; fallback_used=true; Gemini primary pending |

Observed entries have source=auto. These records verify persisted routing outcomes, not independent capture of HTTP versus gRPC transport, wire responses or all failure scenarios. Flash failure cause remains unknown: sanitized failure codes are currently transient and not persisted after successful fallback; no relevant backend log was available. Free-tier quota is a user hypothesis, not a verified diagnosis. No new generation or audio was initiated for closeout.

Earlier phase records report: Phase 3 backend 307 / frontend 137 passing; configuration backend 334 / frontend 137; Phase 4 backend 340 / frontend 232, 9 rendered checks including isolated Electron at actual bounds, build passing with existing chunk warning; development-gate targeted 108 passing. These are historical runs, not all rerun today. Provider/storage tests use mocks; SQL scripts execute isolated PGlite; hosted migration verification used actual read-only schema/role/REST checks. Rendered checks use mocked bridges, not full authenticated live Electron acceptance.

Closeout rerun: backend catalog/foundation/session contract/generation/admission: **135 passed**, 5 existing SWIG warnings, 11.47 s. Frontend desktop auth/dispatch/stream protocol/gRPC consumers/startup: **183 passed**, 0 failed. Exact commands:

```powershell
# backend
E:\deepfake_envs\SaIIA\python.exe -m pytest -q tests/test_answer_model_config.py tests/test_answer_model_foundation.py tests/test_session_model_contract.py tests/test_session_generation.py tests/test_model_admission.py
# frontend
node --test src/desktop_auth_session.test.js src/generation_dispatch.test.js src/answer_stream_protocol.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/startup_login_screen.test.js
```

Pending: Terra and Gemini Flash primary success; independently attributed HTTP/gRPC live coverage; full live Stop/logout/session-end/Retry/both-failure/partial-stream acceptance; assistive technology; real multi-worker crash/concurrency behavior. No exactly-once upstream guarantee. Synthetic coverage does not establish hosted end-to-end behavior.

Closeout isolated SQL rerun: all three scripts PASS (`session_models.postgres.mjs`, `session_generation.postgres.mjs`, `session_model_bindings.postgres.mjs`), covering gates/ownership/immutability, claims/fences/recovery/deletion and snapshots/removal compatibility. These execute PGlite locally, not hosted migrations. `git diff --check` passed (only existing line-ending notices). Exact-current-credential/private-key scanning of candidate additions found no matches; this is a targeted check, not a guarantee that every possible sensitive string is absent.

## Final review and commit preparation

See [focused commit scope](SESSION_ANSWER_MODELS_COMMIT_SCOPE.md). No commit, staging, push, deployment, runtime configuration change, admission change or hosted migration was made in closeout. Historical records now carry explicit current-status links; roadmap/tracker/tech-stack/C6 annotations distinguish implemented scope from their earlier planning text. No runtime logic changed in this closeout.
