# Saiia-dev session answer models: development activation

Activated with explicit authorization on **Saiia-dev**, project **rbmxfazjbldmkomdpyzl**. This records actual development activation, superseding earlier records' pre-activation state. Shipped `.env.example` defaults remain disabled.

## Target and database

Before activation, live CLI project metadata matched Saiia-dev / `rbmxfazjbldmkomdpyzl` / `ACTIVE_HEALTHY`. Ledger contained 29 matching local/remote versions and no pending migrations. All three feature migration hashes still matched the reviewed rollout record.

Database admission was opened with the reviewed `session_model_routing_ready()` replacement, explicitly targeting this linked project. The same transaction checked all three migration versions, model key/binding columns, protected claims storage and required RPC signatures before changing the helper. No additional migrations were applied.

Actual result: admission helper returns true; anon/authenticated EXECUTE remain false, service_role EXECUTE remains true. No grants were broadened.

## Local settings changed

Only these eight settings were changed/added in the repository root `.env`:

```dotenv
ENABLE_SESSION_ANSWER_MODELS=true
SESSION_ANSWER_MODELS_DEV_READY=true
SESSION_ANSWER_MODELS_DEV_PROJECT_REF=rbmxfazjbldmkomdpyzl
GRPC_REALTIME_ENABLED=true
GRPC_STT_ENABLED=true
GRPC_ANSWER_STREAM_ENABLED=true
ELECTRON_GRPC_REALTIME_ENABLED=true
ELECTRON_GRPC_AUDIO_ENABLED=true
```

All pre-existing non-target parsed values, including credentials, were compared before/after and preserved. Appending settings required a trailing line break; no credential values changed. No real credential was printed or copied into this record. Gemini's key remains absent.

Preserved: existing STT providers/model settings, manual batch `openai_whisper`, manual live/Auto `assemblyai_streaming`, microphone/system configuration, ports, backend URL and all provider credentials. `USE_GRPC_AUTO_PIPELINE` and `USE_GRPC_CLOUD_CONTEXT_PIPELINE` were already true and did not need changes. Experimental `USE_GRPC_MANUAL_PIPELINE` remains false. No recording or audio selection was started/changed.

## Process and service verification

An existing project Uvicorn `--reload` watcher was identified on port 8000. Its ordinary reload was requested through the relevant config module's mtime; config source content was checked unchanged. Watcher PID 39756 remained; worker PID changed from 13744 to 2588. No forced termination or unrelated process termination was used.

Actual service checks:

| Check | Result |
|---|---|
| HTTP `GET http://127.0.0.1:8000/api/interview-sessions/answer-models` | HTTP 200 |
| Catalog admission | `enabled` |
| Backend default | `gemini-3.5-flash-lite` |
| Ordered choices | `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-oss-120b`, `gemini-3.5-flash-lite`, `gemini-3.6-flash` |
| Gemini options | Selectable |
| gRPC channel | Reachable at `127.0.0.1:50051` |
| gRPC `CheckHealth(Empty)` | STT, answer-stream, Auto, cloud-context capabilities all true |

The gRPC health method is configuration-only and does not connect to STT or LLM providers. No `StreamInterview` call, recording, test session creation or generation request was made. No claim of successful live provider generation or account access is made.

No Electron app or Vite server was running, so neither was terminated or automatically opened. To start the desktop UI for manual testing:

```powershell
Set-Location E:\saiia_project\saiia_project\frontend
npm run electron:dev
```

The backend is already running. If it is later stopped, its normal command is:

```powershell
Set-Location E:\saiia_project\saiia_project\backend
E:\deepfake_envs\SaIIA\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Do not start a second backend while port 8000 is occupied. The desktop's root dotenv loader will read the new transport/audio flags on launch; an externally supplied process environment still takes precedence over dotenv.

## Short manual checklist

1. Sign in to the Saiia-dev desktop flow. Open Create Session, confirm backend ordering and Gemini Flash-Lite Default; create using each choice and confirm the selected key/snapshot remains locked after creation.
2. Try HTTP manual answers and microphone gRPC Auto. Inspect restricted selected/actual provider/API model metadata and fallback_used; primary success and fallback success must be recorded separately.
3. With Gemini's key absent, Gemini selection should silently use Groq after primary credential failure. Keep Gemini primary-live verification pending until its key is added; this is not Gemini provider success.
4. In a separate controlled test configuration, both attempts failing must show exact “Unable to generate an answer” with Retry, reusing the captured turn/history without audio recapture or duplicates. Do not overwrite the preserved real keys merely to induce failure.
5. Stop/cancel during generation; verify no late mixed output, fallback caused by cancellation, or duplicate final transcript. Verify a removed choice disappears from new setup while existing immutable bindings remain intact.

## Pause only new-session admission

In the **Saiia-dev** SQL editor, replace only the admission helper:

```sql
create or replace function public.session_model_routing_ready()
returns boolean language sql stable set search_path=pg_catalog
as $$ select false $$;
```

This preserves the existing service-only grants and blocks new model-bound session creation. Keep backend execution/development readiness enabled if existing bound sessions should continue with their stored selections. Do not clear binding snapshots, change selected keys, rewrite transcripts or remove claim rows. Disabling backend execution/readiness instead stops bound execution; it never downgrades those sessions to legacy routing.

Evidence: `tmp/session-model-dev-activation/database-admission.json`, `settings-changed.json`, `live-http.json`, `live-grpc.json`, and the reviewed admission SQL. These contain safe settings/status data only. No deployment, commit or push occurred. Stopped after activation and readiness checks; live answer generation remains untested.

## Manual-test report and Gemini verification preparation

User reports earlier manual testing succeeded. This is user-reported success only: no particular model, transport, fallback, cancellation, persistence or Retry scenario is independently established by that report.

Gemini live verification remains pending. Source inspection confirms root `E:\saiia_project\saiia_project\.env`, primary variable `GEMINI_API_KEY` (with `GOOGLE_API_KEY` fallback), loaded by `backend/app/config.py`. The user will enter the key locally. No key value is requested or recorded. After the user confirms saving, restart the relevant backend and check credential presence only before manual generation.

For separate new Gemini Flash-Lite and Gemini Flash sessions, verify restricted persisted selected_model_key/selected_provider/selected_api_model and actual_provider/actual_api_model with fallback_used=false. Fallback success is not Gemini success. No automatic recording or generation is authorized by this preparation.

Gemini credential preparation completed after user confirmed saving: root dotenv contains a Gemini credential; backend settings detects it (boolean checks only). Graceful Uvicorn reload retained watcher 39448 and replaced worker 35328 with 34848; config content hash unchanged. Live HTTP catalog returned 200, admission enabled, both Gemini credentials_configured=true, default unchanged. gRPC CheckHealth returned STT/answer-stream/Auto/cloud-context available. No provider generation or recording occurred; Gemini live access remains not verified pending the user's separate new-session tests.

Read-only Saiia-dev metadata verification after user reported completion: latest session created 2026-10-18T08:17:03Z is bound to gemini-3.5-flash-lite. Its two saved Auto answers (08:17:27Z and 08:17:36Z) both have selected_provider=gemini, selected_api_model=gemini-3.5-flash-lite, actual_provider=gemini, actual_api_model=gemini-3.5-flash-lite, reported_model=gemini-3.5-flash-lite and fallback_used=false. This verifies persisted primary Gemini Flash-Lite success for those manual tests. Source=auto alone does not establish transport identity. No Gemini 3.6 Flash session appeared among the ten newest sessions; that separate check remains pending. Queries selected metadata only, not interview text; no automatic generation performed.

Gemini 3.6 Flash manual-test result: session created 2026-10-18T08:19:24Z retained selected_model_key=gemini-3.6-flash. Saved Auto answer at 08:19:58Z has selected_provider=gemini / selected_api_model=gemini-3.6-flash, but actual_provider=groq / actual_api_model=openai/gpt-oss-120b / fallback_used=true. This is fallback success, NOT Gemini Flash success. Primary failure reason is not in saved transcript metadata; source inspection shows session_generation collects sanitized failure codes in memory but does not persist them on fallback success. No relevant backend log file was available in tmp. Exact cause remains unverified; no automatic provider calls or configuration changes made.
