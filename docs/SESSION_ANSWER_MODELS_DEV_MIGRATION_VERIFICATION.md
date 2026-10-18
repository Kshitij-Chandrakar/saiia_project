# Saiia-dev feature migration application and verification

Applied only to **Saiia-dev**, project **rbmxfazjbldmkomdpyzl**, following explicit migration approval. No runtime/readiness activation was authorized or performed.

## Preflight

- Live CLI project metadata: Saiia-dev, `rbmxfazjbldmkomdpyzl`, `ACTIVE_HEALTHY`.
- Linked project reference matched; all three local SHA256 hashes exactly matched `SESSION_ANSWER_MODELS_DEV_ROLLOUT.md`.
- Ledger before application: 26 matching local/remote versions and exactly three approved local-only versions.
- Fresh `db push --linked --dry-run`: exactly the three files below, no seeds, roles or unrelated migrations.
- Rechecked linked reference, hashes, local migration set and real environment-file hashes immediately before application.

## Applied migrations

Supabase CLI 2.121.0, `db push --linked --yes`, exit code 0:

1. `20261018120000_add_session_model_selection.sql`
2. `20261018150000_add_session_generation_turns.sql`
3. `20261018180000_add_session_model_bindings.sql`

Post-application ledger: **29 matching versions, zero pending or remote-only versions**. No migration repair was used. The CLI's normal login-role initialization was part of authentication; no extra application migration or readiness SQL was executed.

## Actual hosted verification

Metadata verification used read-only SQL transactions through the CLI with both `--linked` and explicit `--project-ref rbmxfazjbldmkomdpyzl`. REST probes selected zero rows; no interview content was fetched.

| Check | Actual result |
|---|---|
| `interview_sessions.selected_model_key` | Present; exposed REST query HTTP 200 |
| `interview_sessions.selected_model_binding` | Present; exposed REST query HTTP 200 |
| `session_generation_turns` | Present; backend REST query HTTP 200 |
| Claims primary key | `(session_id, request_id)` |
| Claims foreign keys | Session/user deletion cascades; transcript reference deletion sets null |
| Claims RLS | Enabled and forced |
| Claims CRUD privileges | No anon/authenticated access; service_role CRUD allowed |
| Required RPCs | Correct signatures for `create_interview_session_with_model`, `create_interview_session_with_binding`, `session_generation_turn`, `session_model_routing_ready` |
| Restricted RPC execution | anon/authenticated denied; service_role allowed |
| Legacy creation RPC | Still service-only |
| Binding validator | Present; authenticated/service execution allowed as required for legitimate constrained lifecycle updates; anon denied |
| Session owner policies | INSERT/SELECT/UPDATE remain scoped by `auth.uid() = user_id`; session RLS enabled and forced |
| Immutable fields | Deployed trigger includes guards for selected key, binding and owner; backend-only bound insert guard present |
| Model constraint | Snapshot validation CHECK present; old five-model key CHECK removed |
| Deletion protections | Enabled session-close and transcript-delete content purge triggers |
| Database admission | `session_model_routing_ready()` returns **false**, SQL and service REST verified |

Additional direct read-only negative probes under `SET LOCAL ROLE authenticated` produced the expected permission-denied errors for claims SELECT and readiness RPC execution. Anonymous REST claims/readiness probes returned HTTP 401. No user sessions, claims or transcripts were created to test writes, so live behavioral tampering/deletion/replay tests remain separate acceptance work. This verification establishes deployed schema, effective privileges, policies and guard definitions; it does not claim end-to-end application generation or exactly-once upstream execution.

## Configuration retained

Verified effective values remain false:

- `ENABLE_SESSION_ANSWER_MODELS`
- `SESSION_ANSWER_MODELS_DEV_READY`
- `GRPC_REALTIME_ENABLED`
- `GRPC_STT_ENABLED`
- `GRPC_ANSWER_STREAM_ENABLED`

Real `.env` file contents were checked against preflight SHA256 hashes and are unchanged. No audio/STT configuration, gRPC transport, provider credentials or generation calls were changed/started. No provider calls, deployments, commits or pushes occurred.

Sanitized evidence and read-only verification SQL are under `tmp/session-model-migration-apply/`:
`apply-result.txt`, `post-ledger.txt`, `schema-access-verification.txt`, `verify-extra.txt`, `deny-authenticated-claims.txt`, `deny-authenticated-rpc.txt`, `rest-and-config.json`.

No migration-verification blockers remain. Application activation and live manual testing are still pending separate authorization; Gemini primary verification remains pending its key. Stopped after migration verification.
