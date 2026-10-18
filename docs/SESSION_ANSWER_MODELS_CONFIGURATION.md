# Configurable session answer models

> Historical phase record. Current implementation, Saiia-dev activation, live evidence and remaining limits are consolidated in [SESSION_ANSWER_MODELS_CLOSEOUT.md](SESSION_ANSWER_MODELS_CLOSEOUT.md). Statements below about disabled gates, missing credentials or future integration describe the phase at the time; they are not the current development activation status.


Implemented after Phase 3; no activation. `ENABLE_SESSION_ANSWER_MODELS` still defaults false. Python and SQL model-bound creation gates remain closed. The Electron dropdown and frontend lists were not changed. Existing uncommitted work was preserved; real environment files, credentials, hosted databases and historical transcripts were not modified.

## Configuration

The existing dotenv loader reads the backend's environment on process start. Environment variables already supplied to the process take precedence over dotenv. The catalog is parsed once, at import/startup, not on requests. Restart every backend worker after editing the loaded `.env`; development reload alone does not reliably watch dotenv files.

Add a same-provider model (example: Groq Llama 3.3; account access not verified):

```dotenv
ANSWER_MODELS=openai:gpt-5.6-luna,openai:gpt-5.6-terra,groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash-lite,gemini:gemini-3.6-flash,groq:llama-3.3-70b-versatile
ANSWER_DEFAULT_MODEL=gemini:gemini-3.5-flash-lite
ANSWER_FALLBACK_MODEL=groq:openai/gpt-oss-120b
ANSWER_MODEL_OVERRIDES={}
ANSWER_DISABLED_MODELS=
ENABLE_SESSION_ANSWER_MODELS=false
```

Remove that new choice:

```dotenv
ANSWER_MODELS=openai:gpt-5.6-luna,openai:gpt-5.6-terra,groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash-lite,gemini:gemini-3.6-flash
ANSWER_DEFAULT_MODEL=gemini:gemini-3.5-flash-lite
ANSWER_FALLBACK_MODEL=groq:openai/gpt-oss-120b
ANSWER_MODEL_OVERRIDES={}
ANSWER_DISABLED_MODELS=
ENABLE_SESSION_ANSWER_MODELS=false
```

[Groq's model list](https://console.groq.com/docs/models) currently lists that identifier as Enterprise; its [text-generation guide](https://console.groq.com/docs/text-chat) demonstrates the compatible Chat Completions API. This example proves neither account entitlement nor successful live execution. Unavailable models follow normal fallback. Do not interpret a parsed entry as capability verification.

Remove overrides for a removed choice too. Default/fallback references must remain in the selectable catalog configuration. Whitespace surrounding comma-separated entries is accepted; malformed IDs, duplicate entries/JSON keys, unsupported providers, unknown override fields and invalid references abort startup with secret-free errors.

Optional override example (use with the corresponding entry in `ANSWER_MODELS`):

```dotenv
ANSWER_MODEL_OVERRIDES='{"groq:llama-3.3-70b-versatile":{"display_name":"Llama 3.3 70B","description":"Text generation via Groq","output_limit":32768}}'
```

The override object accepts only `display_name`, `description`, `profile`, `effort`, `output_limit`. Profile names are backend-owned protocol implementations; arbitrary URLs, headers, tools and request parameters are rejected. Display strings are bounded and reject control characters. No speed ranking or recommendation is generated.

| Provider | Default for unfamiliar IDs | Optional supported profile |
|---|---|---|
| OpenAI | `openai-responses`: text Responses SSE, token limit, store=false | `openai-reasoning`: adds allowed reasoning effort |
| Groq | `groq-chat`: text Chat Completions SSE and token limit | `groq-oss`: adds reasoning effort and disables reasoning output |
| Gemini | `gemini-content`: text streamGenerateContent SSE, token limit | `gemini-thinking`: adds allowed thinking level |

Known five models retain their prior polished names, descriptions, keys and parameter profiles. Unfamiliar IDs use a readable derived name, neutral provider description and logo key `openai`, `groq` or `gemini`; no remote image URL is returned. Provider comes solely from the explicit prefix. Profile overrides must match the provider and supported effort values. The output limit caps request tokens; it is not proof of the provider's actual capacity.

Compatible additions use configuration alone. Models requiring another API (for example OpenAI Chat Completions-only instead of Responses), different stream framing, tools, multimodal inputs, custom thinking budgets or additional mandatory parameters need adapter/profile implementation. Same provider does not imply compatibility. No live model-list or generation call is made at startup.

## Removal, execution and immutable storage

`GET /api/interview-sessions/answer-models` is the future dropdown contract. Its ordered items contain only safe presentation/availability fields: key, display name, provider, logo key, description, default/selectable flags, credentials-configured boolean and `live_access=not_verified`. It exposes no API credentials, execution profiles or provider URLs. Missing Gemini credentials keep it selectable; execution triggers the existing immediate fallback. The dropdown remains unchanged in this task and must consume this endpoint in its later phase.

Removing a model from `ANSWER_MODELS` hides it from new choices and rejects new selection. It does **not** disable execution for existing sessions. To explicitly disable an identity even for existing sessions:

```dotenv
ANSWER_DISABLED_MODELS=groq:llama-3.3-70b-versatile
```

This independent list may include removed identities. Execution produces an eligible `model_disabled` attempt failure, then the established fallback once; it never changes the stored selection. Disabled choices still in the catalog are marked unselectable and rejected for creation. Disabling the fallback itself produces a terminal failure if reached; it cannot loop. Missing credentials remain runtime conditions, separate from explicit disabling.

New model-enabled payloads snapshot version, explicit provider, exact API ID, parameter profile, effort and output limit alongside the existing selected key. Session creation hashes include the snapshot, and the new RPC compares it for idempotency even if a supplied hash is identical. No client can submit a snapshot/provider override. Session responses retain authoritative keys; internal records/recovery include snapshots.

Execution resolves that persisted snapshot, independently of the current selectable catalog. Removing an entry, changing profiles for future sessions, or restarting cannot remap an existing binding. For the original five Phase 2/3 keys without snapshots, a frozen copy of the actual prior implementation profiles provides compatibility. Their keys are not renamed, rows are not backfilled and historical transcript metadata stays unchanged. Unknown pre-snapshot keys fail closed rather than guessing their provider/profile.

The additive `20261018180000_add_session_model_bindings.sql` migration adds nullable snapshot JSON, drops the five-key SQL CHECK, validates supported protocol/profile structure, and extends immutable-owner/selection enforcement to snapshots. The new service-only `create_interview_session_with_binding` RPC retains ownership checks, locking and lifecycle semantics. Authenticated direct bound inserts and immutable updates remain blocked; legitimate lifecycle updates still succeed. Existing unbound RPC callers remain compatible; old bound creation calls without snapshots fail closed. Neither SQL nor frontend needs a per-model list edit. A database catalog synchronization mechanism is unnecessary because admission is validated by the backend-owned startup catalog and bound creation is backend-only. The pure schema-validation helper grants no access to stored data. Table grants/RLS are not broadened.

HTTP/gRPC planner, prompts, follow-ups, streaming replacement, shared deadline, Retry, durable claims, checkpoint deletion, cancellation and selected/actual metadata remain in place. Fallback order is shared and self-fallback compares explicit provider/API identity. Disabled mode retains legacy behavior and bound-session fail-closed protection. No protobuf, audio/STT, OCR, dashboard Ask AI or AI Notes files were changed.

## Restart / rollout

Stop the backend's existing terminal/service, edit its loaded `.env`, then start it with the same environment/interpreter and working directory. For the local checkout:

```powershell
Set-Location E:\saiia_project\saiia_project\backend
E:\deepfake_envs\SaIIA\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Do not start an extra process on top of an existing one. Restart all workers; do not rely on mixed old/new catalog processes. Inspect the catalog endpoint for ordering/labels. No Python model array edit or per-model migration is required after the one-time binding migration. The migration must be separately reviewed/applied before future model-bound admission is enabled; no shared database was touched here. Keep the feature false and both readiness gates closed. No dropdown activation occurred.

## Changed files in this task

- `.env.example`: documented ordered catalog, default/fallback, overrides and explicit execution disable.
- `backend/app/config.py`: dotenv settings with confirmed defaults.
- `backend/app/answer_models.py`: immutable startup catalog, parser, known profiles, safe presentation, persisted-binding validation and frozen old-key compatibility.
- `backend/app/answer_generation.py`: optional profile-specific parameters, output caps, explicit disable and identity-based self-fallback prevention.
- `backend/app/session_generation.py`: resolve selected execution from stored binding instead of current catalog membership.
- `backend/app/cloud/interview_sessions.py`: validate new choices, snapshot/hash bindings, read recovery snapshots and call the new RPC.
- `backend/app/api/interview_sessions.py`: presentation endpoint before dynamic session routes.
- `supabase/migrations/20261018180000_add_session_model_bindings.sql`: additive binding storage, immutable checks and backend-only RPC.
- `backend/tests/test_answer_model_config.py` (new): parser, profile, presentation, subprocess restart/removal and execution-disable tests.
- `backend/tests/test_session_generation.py`: actual handler routes a removed custom model from its persisted snapshot.
- `backend/tests/test_session_model_contract.py`: new RPC and transmitted snapshot assertion.
- `backend/tests/session_model_bindings.postgres.mjs` (new): isolated actual SQL tests.
- `docs/SESSION_ANSWER_MODELS_CONFIGURATION.md` (new): this record.

## Verification and limits

Backend: **334 passed**, five existing SWIG deprecation warnings. Run from `backend`:

```powershell
E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_answer_model_config.py tests/test_session_generation.py tests/test_session_model_contract.py tests/test_answer_model_foundation.py tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_supabase_migrations.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py tests/test_answer_variation_problem2.py tests/test_live_followup_resolver.py tests/test_followup_intent_compiler.py tests/test_grpc_realtime.py tests/test_grpc_manual.py tests/test_grpc_health.py
```

Frontend existing Phase 3 suite: **137 passed**, no failures. No frontend file changed in this task.

```powershell
# From frontend
node --test src/answer_stream.test.js src/answer_stream_protocol.test.js src/generation_auth.test.js src/generation_dispatch.test.js src/request_state.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/realtime_lifecycle.test.js src/grpc_manual_session.test.js src/manual_chat_streaming.test.js src/realtime_router.test.js
```

From root, all three isolated database scripts **PASS**:

```powershell
node backend/tests/session_models.postgres.mjs
node backend/tests/session_generation.postgres.mjs
node backend/tests/session_model_bindings.postgres.mjs
```

The new script executes the additive migration and arbitrary previously unlisted binding, profile-sensitive replay/conflicts, owner isolation, direct-write/RPC privilege denial, immutable snapshots, legitimate lifecycle updates, closed readiness and unchanged historical rows/transcripts. Existing Phase 2/3 scripts also pass. This is real isolated PostgreSQL-in-WASM via existing PGlite, not hosted Supabase or multi-process database validation. Python providers/storage are mocked; the regression suite retains the real localhost gRPC transport check. Subprocess tests actually reload the startup catalog across removal. Live generation/account access, hosted role/schema-cache behavior and actual Electron acceptance remain pending. No exactly-once upstream execution guarantee is made.

Graphify before: `graphify query "AnswerModel MODEL_CATALOG normalize_session_payload" --budget 500`. After: scoped structural graph of seven relevant files, **220 nodes / 713 edges**, in `tmp/session-model-config-graphify/graphify-out`; queried with `graphify query "parse_catalog resolve_binding model_binding" --budget 500`. Main graph preserved. `git diff --check`: passed.

No installs, real environment edits, hosted migrations, deployment, commits or pushes. Stopped before dropdown integration and runtime activation.
