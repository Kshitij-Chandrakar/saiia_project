# Saiia-dev session-model rollout preparation

Target verified through the live CLI project list: **Saiia-dev**, `rbmxfazjbldmkomdpyzl`, region `ap-southeast-2`, status `ACTIVE_HEALTHY`. The linked reference and backend/frontend Supabase hosts match. This record supersedes the Phase 4 in-memory monkey-patch activation proposal.

## CLI and reviewed ledger

Installed Supabase CLI **2.121.0** as an isolated local npm development dependency, using Node 24.16.0. This follows Supabase's supported npm method (not unsupported npm global installation). No frontend/backend dependency manifest was changed.

Reproduce installation if the ignored tooling directory is absent:

```powershell
Set-Location E:\saiia_project\saiia_project
npm.cmd install --prefix tmp/supabase-cli --save-dev --save-exact supabase@2.121.0
```

Commands actually completed, exit code 0:

```powershell
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd --version
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd projects list
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd migration list --linked
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd db push --linked --dry-run
```

The CLI used its available authentication and initialized its login role. No application migration or readiness update was applied. Credentials were not supplied on the command line or printed. Only target project metadata was reported from the project listing.

Ledger: **26 matching local/remote versions**, **3 local-only versions**, no remote-only versions or version-history discrepancies. Historical migration contents/checksums were not compared against remote source; this is a version-ledger verification, not a historical SQL equivalence claim.

Exact dry-run set, in order:

| Migration | SHA256 of reviewed local file |
|---|---|
| `20261018120000_add_session_model_selection.sql` | `b2d81acfe2196b8a1f1d7fc12a7071f496f28c8a9b9096f577254fbbf9e466dc` |
| `20261018150000_add_session_generation_turns.sql` | `3d2cd07961ef4bccf4873a2a9719806b3f827917bd8c1a08665d2028d3af44ca` |
| `20261018180000_add_session_model_bindings.sql` | `023b07210a271370b0f13f456dc75a7996b5a96274e2959480e8147b9b91689b` |

No unexpected migrations, seeds or roles in the dry-run. The CLI explicitly skipped `supabase/migrations/README.md` because it is not a migration; that is not a ledger discrepancy. No repair or `--include-all` was used.

Sanitized outputs: `tmp/session-model-rollout/migration-list.txt` and `tmp/session-model-rollout/dry-run.txt`. Do not publish credentials or unfiltered CLI debug logs. Rerun the target/ledger/dry-run checks immediately before a separately approved application; stop if the set or hashes changed.

## Maintainable development activation

New documented settings:

```dotenv
ENABLE_SESSION_ANSWER_MODELS=false
SESSION_ANSWER_MODELS_DEV_READY=false
SESSION_ANSWER_MODELS_DEV_PROJECT_REF=
```

These are the shipped defaults and remain the effective current values. The real .env was not edited.

The backend development readiness helper requires readiness=true, the configured expected project reference equal to the explicit approved Saiia-dev reference, configured cloud credentials, and an exact HTTPS Supabase URL for that reference. A mismatched target with readiness=true fails backend startup with a secret-free configuration error. This is intentionally a Saiia-dev-only activation mechanism, not a production bypass or a project-name heuristic. Adding another approved environment requires explicit review of the allowed target.

Execution of model-bound requests additionally requires the existing execution flag. Restored bound records retain their bindings and fail closed when execution/development readiness is off. Catalog admission and the service's session-create path now share the same database readiness probe; direct API callers cannot bypass it by omitting the Electron admission header. The insert RPC/trigger remains the final transactional admission gate.

Database admission is separate from ongoing execution: closing the database gate pauses new model-bound sessions while already-bound sessions can continue with their stored model if backend execution/development readiness remains on. Turning off backend execution or development readiness stops bound execution; it never relabels sessions as legacy. Ownership, cancellation, fallback, immutable snapshots and claims protections remain.

## Activation steps for review only — not executed

1. Recheck link and dry-run. Expected reference must be `rbmxfazjbldmkomdpyzl`, project name Saiia-dev, and pending set exactly the three files above.
2. After explicit migration approval only, run:

```powershell
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd db push --linked
& .\tmp\supabase-cli\node_modules\.bin\supabase.cmd migration list --linked
```

The push command is not file-specific; do not run if unrelated pending migrations appear. Confirm all three versions are now remote and required columns/RPCs are exposed before activation.

3. After separate readiness approval, in the **Saiia-dev** SQL editor run:

```sql
create or replace function public.session_model_routing_ready()
returns boolean language sql stable set search_path=pg_catalog
as $$ select true $$;
```

Recreating this existing function retains its service-only privileges. Do not broaden grants. Closing it later uses the same definition with `select false`.

4. In a dedicated backend terminal, after stopping the old backend instance, set only these common development rollout values (process environment; no Python patch):

```powershell
$env:ENABLE_SESSION_ANSWER_MODELS='true'
$env:SESSION_ANSWER_MODELS_DEV_READY='true'
$env:SESSION_ANSWER_MODELS_DEV_PROJECT_REF='rbmxfazjbldmkomdpyzl'
Set-Location E:\saiia_project\saiia_project\backend
E:\deepfake_envs\SaIIA\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Normal Uvicorn startup, including reload in later development, reads documented configuration; no in-memory monkey patch is needed. Existing Supabase credentials remain in their current secure configuration. Do not copy them into scripts or reports.

5. Start Electron in its own terminal:

```powershell
Set-Location E:\saiia_project\saiia_project\frontend
npm run electron:dev
```

Catalog admission must be `enabled` only when backend flag/readiness and database admission are open. Otherwise it is closed (or legacy when execution is false). Run actual session creation with a signed-in test account; confirm immutable selected key/snapshot and one final transcript per logical turn.

## HTTP and gRPC: minimum required changes

The following were inspected from the current effective configuration and actual dependency checks, not assumed:

| Path | Required additional changes after common activation | Already correct / preserve |
|---|---|---|
| HTTP manual answers | None | `ENABLE_TRUE_ANSWER_STREAMING=true`; manual live STT `assemblyai_streaming`; manual batch STT `openai_whisper`; existing provider selection/audio setup |
| Microphone cloud gRPC Auto, backend | `GRPC_REALTIME_ENABLED=true`, `GRPC_STT_ENABLED=true`, `GRPC_ANSWER_STREAM_ENABLED=true` | `USE_GRPC_AUTO_PIPELINE=true`, `USE_GRPC_CLOUD_CONTEXT_PIPELINE=true`; loopback `127.0.0.1:50051`; AssemblyAI key present |
| Microphone cloud gRPC Auto, Electron | `ELECTRON_GRPC_REALTIME_ENABLED=true`, `ELECTRON_GRPC_AUDIO_ENABLED=true` | Auto/cloud-context flags already true; endpoint defaults match backend; backend URL `http://localhost:8000` |

For a separately approved gRPC test, set the three backend booleans in terminal 4 **before** Uvicorn starts, and the two Electron booleans in terminal 5 **before** Electron starts. Do not enable `USE_GRPC_MANUAL_PIPELINE` (currently false), system-capture flags, or change STT provider/model, microphone/system selection, protobuf or watchdogs. gRPC Auto requires microphone source; system/both deliberately retain the existing route. The backend health probe requires STT + AssemblyAI key before advertising answers/Auto, and Electron also requires its transport/audio flags, matching health capabilities and valid cloud authorization. Key presence does not prove account/STT service access; those live checks remain pending.

## Manual acceptance checklist

- Fresh setup: backend-configured order, local logos, Gemini Flash-Lite Default; create with all five choices; authoritative selection/snapshot matches owned session. No active-window selector or selection updates.
- HTTP manual answer and microphone gRPC Auto: distinguish primary success from fallback success using restricted transcript metadata (`selected_model_key`, selected/actual provider/API IDs, `reported_model`, `fallback_used`, `retry_attempt`). No interview text or credentials in diagnostic logs.
- Gemini key is currently absent: keep Gemini primary-live checks pending; verify selectable creation and silent Groq fallback. Groq actual + fallback_used=true is fallback success, not Gemini verification. OpenAI/Groq key presence likewise does not prove primary account/model access.
- Both attempts failing: use isolated test-process credential overrides; exact “Unable to generate an answer”, Retry reuses captured logical turn/history without audio recapture, one final save. Restore only that test process afterward.
- Stop/logout/session end during generation: no late output, no fallback caused by cancellation, no duplicate save. HTTP replacement/gRPC final text must not mix models.
- Add/remove a compatible configured model in a development-only process and restart: new choices update; stale selection requires an explicit valid choice; existing immutable bindings still resolve after removal.

No live generation or audio/STT service connection was made during preparation. No application migrations, database admission activation, real .env edits, deployments, commits or pushes were performed.

## Changes and verification in this preparation

- `backend/app/config.py`, `.env.example`: disabled-by-default development readiness and expected-project settings.
- `backend/app/cloud/interview_sessions.py`: explicit project guard, startup validation helper, shared catalog/create DB admission check and bound execution guard.
- `backend/app/main.py`: validate development target before starting services.
- `backend/app/session_generation.py`: enforce development target readiness for bound attempts and lifecycle monitoring.
- `backend/tests/test_model_admission.py`, `test_session_model_contract.py`, `test_session_generation.py`: target/startup/DB-gate and affected routing/creation checks.
- `docs/SESSION_ANSWER_MODELS_PHASE4.md`: withdraw obsolete monkey-patch runbook and link this procedure.
- `docs/SESSION_ANSWER_MODELS_DEV_ROLLOUT.md`: this record.
- CLI package/lock/binaries are isolated under ignored `tmp/supabase-cli`; app dependencies unchanged.

Focused command from backend: **108 passed**, five existing SWIG warnings:

```powershell
E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_model_admission.py tests/test_session_model_contract.py tests/test_session_generation.py tests/test_interview_session_routes.py tests/test_cloud_interview_sessions.py tests/test_grpc_cloud_context.py
```

No unrelated frontend/build/audio tests were repeated. `git diff --check`: passed. The feature migrations were not changed. Disabling rollout must preserve binding columns, transcripts and durable claims; never downgrade existing sessions to unbound routing or drop their stored model facts.

Graphify before: existing-graph query for `model_admission_status SESSION_MODEL_ROUTING_READY`. After: fresh scoped graph of five affected files, **103 nodes / 224 edges**, queried for `session_model_backend_ready model_admission_status` under `tmp/session-model-dev-gate-graphify`. Main graph preserved.

## Subsequent approved migration application

The three reviewed migrations were subsequently applied to Saiia-dev and verified, with admission and execution still disabled. See [SESSION_ANSWER_MODELS_DEV_MIGRATION_VERIFICATION.md](SESSION_ANSWER_MODELS_DEV_MIGRATION_VERIFICATION.md) for actual hosted results. The preparation/dry-run statements above describe the pre-application state. Runtime activation remains pending.

## Subsequent authorized development activation

Saiia-dev database admission and the reviewed local settings were subsequently activated under explicit authorization. See [SESSION_ANSWER_MODELS_DEV_ACTIVATION.md](SESSION_ANSWER_MODELS_DEV_ACTIVATION.md) for actual settings and service checks. Earlier disabled-state statements describe preparation, not the current development runtime. Shipped defaults remain disabled; no live generation was tested.
