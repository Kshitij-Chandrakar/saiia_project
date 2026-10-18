# Session answer models: Phase 3 implementation record

> Historical phase record. Current implementation, Saiia-dev activation, live evidence and remaining limits are consolidated in [SESSION_ANSWER_MODELS_CLOSEOUT.md](SESSION_ANSWER_MODELS_CLOSEOUT.md). Statements below about disabled gates, missing credentials or future integration describe the phase at the time; they are not the current development activation status.


Status: implemented behind the existing disabled flag. Model-bound creation remains closed in both Python (`SESSION_MODEL_ROUTING_READY=False`) and the Phase 2 SQL RPC. No real environment values changed; no shared migration applied. Existing uncommitted Phase 1/2 and G9 work was preserved. Dropdown, protobuf, audio/STT and watchdog changes were not made by this phase.

## Runtime behavior

- Session generation uses the owned, active backend row, never client model/provider parameters. Unknown request fields are forbidden. The selected resume and job context remain session-owned.
- HTTP manual answers, typed Chat, standard Auto and their live follow-ups reuse the existing buffered planner, prepared prompt, grounding, formatting and validation in a cancellable worker. Request-local provider facades keep answer-producing corrections on the current attempt model. Cached retrieval and the primary prepared prompt are reused across fallback. Global provider configuration is never changed.
- Cloud gRPC Auto calls that same boundary when the feature flag is enabled. It keeps bounded same-session follow-up context in memory, using the resolver's existing answer-mode entries. STT, classification, extraction/vision, dashboard Ask AI and AI Notes provider routing is untouched. Direct OCR generation remains outside this integration; text generation explicitly submitted through the session answer endpoint follows its session binding.
- One shared attempt order: selected model, then Groq GPT-OSS 120B once. Direct GPT-OSS has no self-fallback. Missing Gemini credentials fail immediately at its adapter and silently fall back. Every new logical question starts with the stored selection. Selected and actual provider/API model plus reported version are separate restricted persistence metadata.
- Existing configurable standard deadlines: first answer token 6s, idle 4s, overall 25s, fallback reserve 8s. Coding: 10s/6s/40s/12s. The overall budget starts before the worker planner and is reused by corrections and fallback. Reserve bounds the primary attempt, rather than granting each provider a fresh deadline. Whitespace, heartbeat and reasoning traffic do not reset first-token time.
- HTTP sends ordered, sequenced NDJSON; failed provisional output is cleared with `replace`. Fallback deltas stay buffered until the final validated replacement. Attempt fences reject late primary events. The Electron IPC filter preserves safe attempt and typed-error fields.
- gRPC retains its existing protobuf: provisional deltas can remain visible until full `answer_completed.text` replaces them; fallback text is never appended to provisional text. Terminal failure clears it via typed `answer_error`. The connection remains usable for another question. Consumer guards ignore late and duplicate completion events.
- Both generation attempts failing produces `generation_failed`, the exact message "Unable to generate an answer", and Retry. Retry preserves the backend logical turn, advances its attempt, rebinds the existing UI history entry and prevents duplicate clicks. Storage recovery retries do not advance the attempt or regenerate.
- Cancellation, revoked authorization, session end, flag disable and supersession stop the current attempt. The monitor checks authorization, ownership/lifecycle and the durable fence; network reads close on cancellation/deadline. UI guards suppress stale output. An already committed database transaction cannot be undone by a later cancellation.

## Claims, persistence and crash recovery

The original transport-local request guards and transcript uniqueness cannot coordinate workers or prove whether a final answer was computed before a process died. The additive `session_generation_turns` migration supplies the minimal durable claim/fence/checkpoint needed for that gap; it does not replace session storage or introduce a new memory subsystem.

- Enabled session requests claim `(session_id, logical request_id)` before generation. Pending duplicates do not start a provider. Different question bodies conflict under the same turn ID; identical questions with different IDs remain independent.
- A token fences stale workers and failed-turn attempts. Supersession cancels the named previous processing/checkpoint claim. Authenticated users cannot read or write claim rows or execute the RPC. Service-only RPCs still verify the supplied owner and active session.
- Only the validated final result is checkpointed. The RPC atomically creates the transcript through the existing transcript RPC and marks the claim completed. HTTP and gRPC share this persistence owner in enabled mode; gRPC does not perform a second save.
- A checkpoint/completed replay returns the saved result without opening a provider. A failed transcript save leaves its checkpoint for save-only Retry. Persistence failures never invoke model fallback. A lost completion acknowledgement is resolved by checkpoint/completed replay.
- A processing lease is 120s, exceeding the maximum configured shipped generation budget. A later claim/check after expiry rotates its fence and marks it `uncertain`; it never starts another provider automatically. Such a turn is terminal and requires an explicit new question; it cannot be retried as a known failed generation. This prevents permanently pending requests while preserving uncertainty about work completed upstream before a crash.
- Checkpoint payloads contain answer/request content and are backend-only under forced RLS, with narrower privileges than transcript rows. Owner/session deletion cascades; transcript deletion purges replay content and retains only a content-free tombstone; ending/abandoning a session purges noncompleted checkpoints before transcript deletion. Historical transcript metadata is not rewritten.
- Database deduplication and fencing do **not** guarantee exactly one upstream provider execution after worker crashes. No such claim is made.

## Legacy compatibility and transport limits

With the flag false, unbound/legacy HTTP still uses its original persistence helper and cloud gRPC its original `cloud_context.save`. This was verified before and after introducing the opt-in shared owner. No claims migration is required by disabled legacy execution. Accepted gRPC answers now receive unique save IDs instead of question-text hashes, so separate identical questions do not collide. Existing intake deduplication remains unchanged.

With the flag true, legacy session requests can use claims while keeping the existing configured legacy generator, without inventing a historical selection. Historical nullable selections and transcript model metadata remain unchanged. Bound sessions fail closed if the flag is false; they are never routed through legacy configuration. Creation remains closed regardless of integration test success in this phase.

The actual gRPC wire contract carries the generated logical turn in the existing envelope `request_id`. It has no retry-attempt/request-body replay command. A real local gRPC test verifies two distinct IDs, failure then success on one connection, full final replacement and one persistence owner. Electron Retry crosses the existing authenticated HTTP bridge with that turn ID and `recover_turn`; the backend restores the canonical stored request. No protobuf change or assumed arbitrary transport metadata is involved. Reconnect does not resume an in-flight gRPC turn or restore its in-memory follow-up history; checkpoint/completed recovery is available by known turn ID through HTTP.

## Files changed in this phase

| File | Purpose |
|---|---|
| `backend/app/session_generation.py` (new) | Shared session execution, request-local planner/provider bridge, lifecycle monitor, claims, checkpoint/replay and event fencing |
| `backend/app/answer_generation.py` | Shared primary/fallback model ordering; update module description |
| `backend/app/api/generate.py` | Dispatch session requests, strict request/retry contract, authoritative model response fields, scoped generator/context and suppression of duplicate persistence |
| `backend/app/cloud/interview_sessions.py` | Allow bound execution only under the existing opt-in flag; preserve closed creation gates |
| `backend/app/grpc_answer_pipeline.py` | Propagate logical turn, consume replacement/typed failure, shared persistence and bounded follow-up context |
| `backend/app/grpc_server.py` | Unique turn envelope IDs; turn-level typed errors without terminating the stream |
| `backend/app/grpc_cloud_context.py` | Unique accepted-answer save IDs on legacy path |
| `backend/app/nlp/answer_variation.py` | User/session fingerprint isolation; retain existing history storage |
| `supabase/migrations/20261018150000_add_session_generation_turns.sql` (new) | Additive claims/checkpoint RPC, fencing, ownership/access controls and content deletion |
| `frontend/electron/main.cjs` | Preserve safe attempt, failure and retry fields through HTTP IPC |
| `frontend/electron/grpc_realtime_client.cjs` | Full-text completion replacement, terminal turn failure and stale/duplicate guards |
| `frontend/src/grpc_auto_session.js` | Clear failed turn and continue capture/listening |
| `frontend/src/App.jsx` | HTTP attempt guards, terminal output clearing, logical-turn Retry and history/request protection |
| `frontend/src/components/AnswerPanel.jsx` | Minimal terminal error and Retry control |
| `backend/tests/test_session_generation.py` (new) | Actual HTTP handler tests and real local gRPC transport, mocked providers/storage |
| `backend/tests/session_generation.postgres.mjs` (new) | Actual isolated SQL migration/RPC/access/deletion validation |
| `backend/tests/test_answer_model_foundation.py` | Replace Phase 1 no-runtime-import assertion with disabled-default assertion |
| `backend/tests/test_grpc_cloud_context.py` | Verify distinct accepted repeated-question save IDs |
| `frontend/src/answer_stream_protocol.test.js` | Actual main-process event filter contract |
| `frontend/src/generation_dispatch.test.js` | Partial replacement, queued paints, Retry identity/history and double-click guard |
| `frontend/src/grpc_realtime_client.test.js` | Event consumer stale/duplicate/failure/next-question checks; safe status fields |
| `frontend/src/grpc_auto_session.test.js` | Turn failure without capture shutdown; next question completes |
| `docs/SESSION_ANSWER_MODELS_PHASE3.md` (new) | This implementation and verification record |

Other pre-existing modified/untracked files belong to earlier work; their presence in `git status` does not imply changes by this phase.

## Verification

Baseline before Phase 3 edits: **230 passed**, five existing SWIG deprecation warnings, on the original session/provider/HTTP/gRPC/transcript suites listed in the Phase 2 record. No live providers were called.

Final backend from `backend`: **307 passed**, five existing SWIG deprecation warnings:

```powershell
E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_session_generation.py tests/test_session_model_contract.py tests/test_answer_model_foundation.py tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_supabase_migrations.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py tests/test_answer_variation_problem2.py tests/test_live_followup_resolver.py tests/test_followup_intent_compiler.py tests/test_grpc_realtime.py tests/test_grpc_manual.py tests/test_grpc_health.py
```

Final frontend from `frontend`: **137 passed**, no failures:

```powershell
node --test src/answer_stream.test.js src/answer_stream_protocol.test.js src/generation_auth.test.js src/generation_dispatch.test.js src/request_state.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/realtime_lifecycle.test.js src/grpc_manual_session.test.js src/manual_chat_streaming.test.js src/realtime_router.test.js
```

`npm run build`: passed (2149 modules); existing large-chunk warning. `git diff --check`: passed.

Actual isolated database validation from repository root, both **PASS**:

```powershell
node backend/tests/session_generation.postgres.mjs
node backend/tests/session_models.postgres.mjs
```

These execute SQL in the already installed PGlite PostgreSQL-in-WASM database, including existing transcript/session migrations. They exercise pending/conflicting/replayed turns, stale tokens, failed Retry, expired/uncertain claims, checkpoints, atomic single transcript save, cross-owner rejection, authenticated privilege denial, supersession, cancellation, session close and permanent transcript deletion. This is actual SQL execution, not mocked SQL assertions, but it is not hosted Supabase/PostgREST validation or a multi-process PostgreSQL concurrency test.

Python provider/storage calls are mocked, except the gRPC server/channel is real localhost transport. The tests cover all five choices, absent Gemini key, primary/fallback/both failures, direct GPT-OSS, shared prepared prompt, corrections, first-token cancellation, lifecycle stops during primary/fallback, pending duplicates, independent identical questions, save-only checkpoint recovery and variation isolation. SQL tests exercise persistence fencing/cancellation separately; they do not prove every combined cancellation timing against a hosted server. Frontend tests execute the existing consumer/renderer functions with mocked IPC, not an actual Electron window.

Graphify before edits: `graphify query "GenerateRequest CloudInterviewSessionService" --budget 600`. After edits: scoped structural extraction of ten relevant backend files, **257 nodes / 682 edges**, in `tmp/session-model-phase3-graphify/graphify-out`; queried with `graphify query "dispatch_session_generation AttemptRun TurnStore" --budget 600`. Repository-wide graph preserved; no semantic/provider calls.

## Rollout prerequisites / remaining limits

- Review and apply additive Phase 2/3 migrations separately before any future opt-in; hosted roles, PostgREST schema cache and real multi-worker crash/concurrency behavior remain unverified.
- Live model/account availability remains pending, including Gemini after its key is added. Missing Gemini is supported now through mocked fallback tests; no billable generation or credential mutation occurred.
- Actual Electron acceptance (Stop/logout, window rendering, history/Retry and continuous Auto across failure) remains pending. Native OS/audio acceptance is outside this phase.
- Keep `ENABLE_SESSION_ANSWER_MODELS=false` and both model-bound admission readiness gates closed. UI/dropdown work and a separate activation review follow; no activation was performed.
- An uncertain crash-before-checkpoint answer cannot be reconstructed safely. Explicit new-question submission can cause another upstream execution; automatic regeneration is deliberately refused.

Stopped after Phase 3. No commit, push, deployment, package installation, shared migration, dropdown integration or runtime activation.
