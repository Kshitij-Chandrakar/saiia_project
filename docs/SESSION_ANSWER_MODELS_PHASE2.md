# Phase 2: immutable session model storage

> Historical phase record. Current implementation, Saiia-dev activation, live evidence and remaining limits are consolidated in [SESSION_ANSWER_MODELS_CLOSEOUT.md](SESSION_ANSWER_MODELS_CLOSEOUT.md). Statements below about disabled gates, missing credentials or future integration describe the phase at the time; they are not the current development activation status.


Date: 2026-10-18, Asia/Calcutta. Phase 2 only; no runtime routing or UI activation.

## Contract and rollout

- Session create accepts only `selected_model_key` from the existing five-model
  catalog; provider/API identifiers, URLs and other arbitrary fields are rejected.
- Future enabled-and-routing-ready creation defaults omitted/null selection to
  Gemini 3.5 Flash-Lite. Credentials are never consulted during session creation.
- `ENABLE_SESSION_ANSWER_MODELS=false` preserves legacy creation, old RPC arguments
  and exact normalized payload hashes. Explicit model selection returns conflict.
- With that flag true but routing not implemented, ALL creation is rejected before
  storage. `SESSION_MODEL_ROUTING_READY=False` is code readiness, not another env
  switch. Tests simulate future readiness separately; production readiness stays false.
- The migration independently gates bound inserts through a literal-false readiness
  function. Future routing work must intentionally replace it in a later migration.
- Session responses return `selected_model_key` and derived `model_selection_kind`
  (`legacy` or `model_bound`). No client can submit the derived kind.
- Read-only authenticated detail recovery returns the authoritative stored key.
  Existing execution callers of the shared session loader fail closed for any bound
  record while routing is unimplemented, even with the admission flag disabled.
  This is covered through the real HTTP authorization and gRPC context loaders;
  neither generation implementation was edited.
- If the flag is disabled after bound sessions exist, do not clear their keys or
  interpret them as legacy. This release refuses execution of bound records; detail
  reads and lifecycle updates remain available. The routing phase must retain explicit
  failure or implement continued bound-model execution independently of new-session
  admission. It must never use global-default routing for such records.

## Storage and permissions

Prepared migration: `20261018120000_add_session_model_selection.sql`.

One nullable `selected_model_key` column, with a five-key CHECK constraint. NULL
means no known selection; no historical backfill, transcript writes or invented model.
The field and session owner are immutable, including service-role updates. Existing
end/abandon and other legitimate non-selection updates still work.

Inspected existing migration privileges: authenticated SELECT/INSERT/UPDATE on
sessions, forced owner RLS; existing create RPC executable by service_role only.
No table grants or RLS policies are broadened or revoked. The trigger rejects bound
direct authenticated inserts, selection changes and owner changes. New RPC/helper
execution is backend-only. Existing privileges on the old RPC are explicitly retained.

The model-aware RPC preserves the existing user lock, ownership checks, one-active
session rule and creation idempotency store. Model selection participates in both
hash conflicts and the two-minute equivalent-session replay shortcut. The old
nine-argument RPC remains callable with its original arguments, delegating to the
new implementation with NULL selection. No generation claims were added.

## Historical truth and unresolved policy

Verified current source default and allowlisted local `.env` values (no secrets):
`ANSWER_PROVIDER=openai`, `OPENAI_MODEL=gpt-5.4-mini-2026-03-17`, and local
`GROQ_MODEL=openai/gpt-oss-120b`. This agrees with the earlier proposed legacy primary
for this workstation, but is not evidence of the model used by every historical turn
or deployment. No legacy identifier was hard-coded into storage or compatibility code.

Legacy sessions continue existing runtime configuration behavior in this phase.
Choosing a frozen/versioned legacy routing policy remains unresolved for the routing
phase; it must be approved before claiming deterministic legacy generation. Historical
selections stay NULL and existing transcript provider/model metadata stays unchanged.

## Verification

Baseline command from `backend`: **92 passed**, before Phase 2 edits:

```powershell
python -m pytest -q tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_supabase_migrations.py tests/test_answer_model_foundation.py
```

Final backend command from `backend`: **230 passed**, five existing SWIG deprecation
warnings, no failures. Includes **27 new Phase 2 cases**. Python storage transports
are mocked; these alone are not database validation.

```powershell
python -m pytest -q tests/test_session_model_contract.py tests/test_answer_model_foundation.py tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_supabase_migrations.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py
```

Frontend regression command from repository root: **113 passed**:

```powershell
node --test frontend/src/answer_stream.test.js frontend/src/answer_stream_protocol.test.js frontend/src/generation_auth.test.js frontend/src/generation_dispatch.test.js frontend/src/request_state.test.js frontend/src/grpc_auto_session.test.js frontend/src/grpc_realtime_client.test.js frontend/src/realtime_lifecycle.test.js
```

Database command from root: **PASS**:

```powershell
node backend/tests/session_models.postgres.mjs
```

This actually executes the original session migrations and new migration in an
isolated in-memory PGlite PostgreSQL-in-WASM database using the already-installed
package under `tmp/transcript-delete-db`. No packages installed, credentials used or
shared/deployed database contacted. Exercises schema/RPC execution, all five keys,
invalid values, replay and conflicts even with the same supplied hash, service-role
and authenticated tampering, cross-owner RLS, old RPC compatibility, lifecycle updates,
closed admission and unchanged historical transcript metadata. Future readiness is
enabled only inside the disposable test database, then restored to the shipped false.

Limit: this does not validate hosted Supabase/PostgREST schema-cache behavior, deployed
privileges or migration application. Those remain pending; no shared migration applied.

`git diff --check`: passed. Existing uncommitted work preserved. No real `.env`,
Electron, generation, audio/STT, protobuf, watchdog or request-claim changes.

Graphify before edits:
`graphify query "CloudInterviewSessionService normalize_session_payload" --budget 900`.
After edits: fresh structural extraction of session API/service and new Python tests,
**146 nodes / 529 edges**, under `tmp/session-model-phase2-graphify/graphify-out`;
queried there with `graphify query "CloudInterviewSessionService selected_model_key" --budget 700`.
Repository-wide graph left intact; no semantic/provider calls.

Next: review this storage phase. UI and generation integration remain unimplemented.
