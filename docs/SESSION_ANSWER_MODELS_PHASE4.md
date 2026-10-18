# Phase 4: configuration-driven Electron session model control

> Historical phase record. Current implementation, Saiia-dev activation, live evidence and remaining limits are consolidated in [SESSION_ANSWER_MODELS_CLOSEOUT.md](SESSION_ANSWER_MODELS_CLOSEOUT.md). Statements below about disabled gates, missing credentials or future integration describe the phase at the time; they are not the current development activation status.


Implemented behind the existing disabled rollout. Real environment files were not edited. At Phase 4 completion Python and SQL readiness were closed. The subsequent [development rollout record](SESSION_ANSWER_MODELS_DEV_ROLLOUT.md) replaces the Python constant/monkey-patch proposal with a project-pinned, disabled-by-default configuration gate; SQL readiness remains closed. No hosted migration, activation, deployment, commit or push. Existing uncommitted work was preserved.

## Behavior

- The existing AI Model field alone was replaced. No selector was added to the active interview. Native setup bounds remain **421 x 484**, with the existing layout and footer.
- Renderer calls `saiia.listAnswerModels`; narrow preload/main IPC validates its sender and uses the main-owned authenticated request manager to GET `/api/interview-sessions/answer-models`. No renderer credentials, generic fetch, provider calls or model array. The manager returns only bounded safe presentation fields and admission status, with account/request generation guards.
- Ordering, names, descriptions, selectable state and the fresh-setup default all come from the backend. Previous session selection is ignored. Gemini credential availability is never a renderer eligibility check. A configured unfamiliar model works without a UI edit; unknown logo keys use local Lucide Cpu.
- OpenAI, Groq and Gemini marks are local SVG assets, with upstream sources/licenses in `frontend/src/assets/provider-logos/README.md`. No generated brand marks or remote image requests.
- The listbox is portaled to document.body, fixed within viewport bounds, placed above/below its trigger and internally scrollable. Arrow/Home/End navigation, Enter/Space selection, Escape/Tab closure, focus restoration, selected/disabled semantics and descriptions are present. Outside click closes without stealing focus. Existing scrolling form cannot clip the popup.
- Catalog loads fail closed, show a catalog-specific Retry and reject stale async responses after unmount/account/setup reset. Initial default is backend-owned. A removed/disabled selection returns typed `model_selection_stale`; setup refreshes, clears the selection and requires an explicit valid choice. It does not substitute the new default. If admission changed to legacy/closed, restart setup; an already reviewed model choice is not silently discarded.
- Admission is `legacy`, `closed`, or `enabled`. Disabled flag returns legacy: disabled Automatic control, no key submitted, original legacy creation. Enabled flag with either backend development readiness or database readiness closed blocks all creation. Future readiness requires the database helper to return true; probe/configuration failures fail closed.
- Creation includes the stable key only in enabled mode. The authenticated bridge preserves the server-returned selection/kind. Setup takes those authoritative response values, locks during/after creation, and preserves company/resume validation and the in-flight guard. Missing binding on a supposedly bound response is rejected and that session is ended.
- An optional `X-Session-Model-Admission` request header protects Electron against rollout changing between catalog load and creation. Existing clients without the header retain their contract. A legacy setup cannot accidentally default into a model-bound session, nor can enabled setup silently become unbound.
- HTTP/gRPC generation and Retry were not changed here. Existing tests execute partial replacement, attempt/stale guards, the main-process safe failure filter, exact `Unable to generate an answer`, captured logical-turn Retry, existing history reuse and double-click protection. gRPC terminal failure keeps capture/transport alive; its full completion replaces provisional output. No fallback notification was introduced.

## Files changed in this phase

| File | Purpose |
|---|---|
| `backend/app/cloud/interview_sessions.py` | Safe admission probe across Python/DB gates; typed stale-selection exception |
| `backend/app/api/interview_sessions.py` | Catalog admission field; typed stale response and optional admission-match creation guard |
| `frontend/electron/desktop_auth_session.cjs` | Authenticated safe catalog fetch, selected-key payload, authoritative safe response and stale code |
| `frontend/electron/main.cjs` | Sender-validated catalog IPC handler |
| `frontend/electron/preload.cjs` | Narrow catalog method on existing bridges |
| `frontend/src/components/StartupSessionSetupScreen.jsx` | Catalog lifecycle, default/reset/stale handling, gated control, creation selection/locking |
| `frontend/src/components/AnswerModelSelect.jsx` (new) | Accessible viewport-bounded portal listbox and local provider asset mapping |
| `frontend/src/components/startup-session-setup.css` | Scoped trigger/popup styles; existing dimensions/footer retained |
| `frontend/src/assets/provider-logos/*` (new) | Three SVG marks, sources and two upstream licenses |
| `backend/tests/test_model_admission.py` (new) | Gate/probe failure and admission-change guard tests |
| `backend/tests/test_session_model_contract.py` | Assert new typed stale-selection contract |
| `frontend/src/desktop_auth_session.test.js` | Catalog safety/auth/stale behavior, binding IPC and new preload allowlist |
| `frontend/src/startup_login_screen.test.js` | Correct old source assertion to the Phase 3 logical UUID implementation |
| `frontend/tests/session_model_setup.browser.test.mjs` (new) | Real rendered browser and isolated Electron checks |
| `frontend/tests/fixtures/session-model-setup.html`, `.jsx`, `session-model-electron.cjs` (new) | Isolated real-component fixture, mocked bridges and hidden isolated Electron shell |
| `docs/SESSION_ANSWER_MODELS_PHASE4.md` (new) | This record, runbook and rollback |

No protobuf, audio/STT, OCR, dashboard, generation-provider or unrelated UI file was changed by Phase 4. Other entries in git status predate this phase.

## Exact verification

- Backend focused/regression command below: **340 passed**, five existing SWIG warnings.
- Frontend Node suites below: **232 passed**, no failures.
- Rendered test command below: **9 passed**: eight Chromium scenarios and one actual isolated Electron renderer scenario. Uses the real setup component and real backend-derived catalog, with mocked catalog/session IPC and isolated process configuration. It does not validate production authenticated IPC end to end or hosted persistence.
- `npm run build`: **passed**, 2153 transformed modules; existing large-chunk warning.
- `node --check` on changed main/preload/auth-manager CJS files: **passed**.
- `git diff --check`: **passed** (Git emits existing LF/CRLF conversion notices).

From `backend`:

```powershell
E:/deepfake_envs/SaIIA/python.exe -m pytest -q tests/test_model_admission.py tests/test_answer_model_config.py tests/test_session_generation.py tests/test_session_model_contract.py tests/test_answer_model_foundation.py tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_supabase_migrations.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py tests/test_answer_variation_problem2.py tests/test_live_followup_resolver.py tests/test_followup_intent_compiler.py tests/test_grpc_realtime.py tests/test_grpc_manual.py tests/test_grpc_health.py
```

From `frontend`:

```powershell
node --test src/desktop_auth_session.test.js src/startup_login_screen.test.js src/startup_window_controller.test.js src/answer_stream.test.js src/answer_stream_protocol.test.js src/generation_auth.test.js src/generation_dispatch.test.js src/request_state.test.js src/grpc_auto_session.test.js src/grpc_realtime_client.test.js src/realtime_lifecycle.test.js src/grpc_manual_session.test.js src/manual_chat_streaming.test.js src/realtime_router.test.js
npm run build
```

From repository root:

```powershell
node --test frontend/tests/session_model_setup.browser.test.mjs
node --check frontend/electron/main.cjs
node --check frontend/electron/preload.cjs
node --check frontend/electron/desktop_auth_session.cjs
git diff --check
```

Rendered tests cover catalog loading/error/Retry, late responses, order/default, missing-credential independence, dynamic additions/removals, unknown logo, selected-key payload, authoritative response, locking, fresh reset, duplicate click, disabled/closed admission, keyboard/focus, portal bounds, large-catalog scrolling and company/resume validation. Backend/Node tests separately exercise actual auth-manager/preload contracts and readiness guards. No live billable generation was made.

Screenshots (421 x 484):

- `tmp/session-model-phase4/dropdown.png`: Chromium.
- `tmp/session-model-phase4/electron-dropdown.png`: actual Electron in a hidden isolated shell, DPI scale 1, isolated userData under tmp.
- `tmp/session-model-phase4/admission-closed.png`: Chromium, closed rollout.

The full shipped application with real login/preload/backend/database together, deployed roles/schema cache, live model availability and assistive-technology acceptance remain unverified. The browser and isolated Electron checks are not full live desktop acceptance. Existing Phase 3 crash/uncertain-completion limitations remain; no exactly-once upstream execution guarantee is made.

Graphify before: `graphify query "CreateSession StartupSession" --budget 450`. After: structural extraction of seven relevant files, **238 nodes / 657 edges**, in `tmp/session-model-phase4-graphify/graphify-out`, queried with `graphify query "AnswerModelSelect model_admission_status listAnswerModels" --budget 500`. Main graph preserved.

## Manual testing runbook

### Safe repeatable rendered checks (no environment or database changes)

1. From repository root run the rendered test command above. It starts/stops its own Vite server, runs Chromium and a hidden Electron shell with mocked session creation, then writes screenshots under tmp. It derives choices from the actual Python catalog. Python path is the existing `E:/deepfake_envs/SaIIA/python.exe`.
2. Inspect all three screenshots. Confirm full option labels/descriptions/logos, Default, visible footer and no clipping. Repeat with a large configured catalog in the fixture; End must reach the last item while the list scrolls internally.
3. Run the Node/backend suites above. HTTP replacement must clear primary text; gRPC final text must replace it. Both-failure Retry must preserve logical turn/history, advance only a known failed generation attempt, and make no audio recapture. Persistence Retry must replay/save the checkpoint without another provider.

### Ordinary disabled-mode app smoke

Use the existing backend and Electron startup commands, without editing .env or readiness code:

```powershell
# Terminal 1
Set-Location E:\saiia_project\saiia_project\backend
E:\deepfake_envs\SaIIA\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Terminal 2
Set-Location E:\saiia_project\saiia_project\frontend
npm run electron:dev
```

Stop existing instances first instead of starting duplicate servers. Sign in, open Create Session, verify Automatic is disabled with an honest rollout explanation, enter company/select a ready resume, and create a legacy session. No selected_model_key is submitted. Close/back/reopen must reset setup. Catalog failure must offer Retry and block ambiguous creation. This requires the user's existing authenticated backend/storage and was not performed against hosted services in this phase.

### Enabled-mode integration (superseded runbook)

The original local/in-memory monkey-patch proposal is withdrawn. Use [SESSION_ANSWER_MODELS_DEV_ROLLOUT.md](SESSION_ANSWER_MODELS_DEV_ROLLOUT.md): it records the verified Saiia-dev target and reviewed CLI migration set, and provides the normal-startup, disabled-by-default, project-pinned activation procedure. No code patch or Python monkey patch is needed to activate that approved development target. Fully isolated component checks remain available through the rendered/mock test command above.

## Rollback preserving bindings

- Keep `ENABLE_SESSION_ANSWER_MODELS=false`, development readiness false and the SQL admission helper false. This blocks bound execution rather than silently switching its model; legacy/unbound flow remains available.
- Revert only reviewed Phase 4 UI/bridge/API-status hunks if needed. Do not reset the working tree: it contains earlier uncommitted work. Keep the Phase 1-3/configuration binding resolver, shared claims/fences, cancellation and checkpoint protections.
- Do not drop migration columns/tables, replace stored keys, clear snapshot JSON, remap removed models or rewrite transcripts. Keep all three additive model migrations and existing binding/claim data.
- An older renderer can use legacy creation while disabled; do not pair active bound sessions with a backend that lacks snapshot-aware routing. A later rollback that disables routing must fail closed for those sessions; restore a compatible backend or end them explicitly, never relabel them as legacy.

Stopped after Phase 4. No hosted migrations applied and no real runtime activation.
