# Sketch: enablement, testing and troubleshooting

Prepared 26 November 2026. Documentation only: this guide does not enable features, install software, apply migrations or make provider calls. Its examples are for an explicitly authorized isolated development environment, not a production activation script.

## What Sketch does

Sketch turns an existing completed system-design answer into an architecture diagram. It uses the saved answer as its source rather than generating a replacement answer. It is not a freehand drawing canvas or a general image generator.

The provider returns a bounded structured graph. Nodes and relationships require supporting text from the answer; labels and graph structure are validated before rendering. The interface includes a textual alternative. An answer without enough connected architecture may legitimately produce `insufficient_detail`.

## Why it is currently disabled

The local configuration audit found no explicit `DIAGRAM_GENERATION_ENABLED` setting in the repository-root `.env`. [Backend settings](../backend/app/config.py) default it to `false`. No checked local application listener was running during that audit, so this was a source/configuration finding, not live acceptance.

Other independent gates still apply after enabling the flag:

| Gate | Expected condition |
| --- | --- |
| Identity | An authenticated owner of the session and answer. Admin membership does not override customer ownership. |
| Source | A completed, saved, trusted `system_design` answer from an accepted answer/Auto/chat source, with the matching source revision. |
| Provider | Backend OpenAI credential and the currently supported diagram model family. Groq/Gemini answer credentials do not replace the diagram provider credential. |
| Persistence | Compatible diagram schema/RPCs and the correct database permissions. |
| Subscription mode | Working subscription runtime, authoritative feature permission and available allowance. Approved Free excludes Sketch; approved Plus/Pro include it. Published entitlement snapshots, not local JSON templates, determine a real account's rights. |
| Client | The actual supported diagram bridge and source descriptor, not merely a visible plan label. |
| Restrictions | Account deletion/restriction and other product-access checks must permit the operation. |

## Where the feature is implemented

| Component | Source |
| --- | --- |
| Main-window placement | [MainAnswerDisplay.jsx](../frontend/src/components/MainAnswerDisplay.jsx), [App.jsx](../frontend/src/App.jsx) |
| Desktop history | [DesktopAnswerHistory.jsx](../frontend/src/components/DesktopAnswerHistory.jsx) |
| UI, status and source checks | [DiagramSection.jsx](../frontend/src/components/DiagramSection.jsx) |
| Electron transport | [answer_diagrams.cjs](../frontend/electron/answer_diagrams.cjs) |
| HTTP API | [answer_diagrams.py](../backend/app/api/answer_diagrams.py) |
| Generation/provider lifecycle | [answer_diagram_service.py](../backend/app/services/answer_diagram_service.py) |
| Original storage adapter | [cloud/answer_diagrams.py](../backend/app/cloud/answer_diagrams.py) |
| Subscription-aware adapter | [subscription_sketch.py](../backend/app/commercial/subscription_sketch.py) |

**Desktop versus website:** `DiagramSection` defaults to `window.electronAPI`; the current main-window integration is in Electron, separate from the answer overlay. Do not expect an ordinary browser tab to acquire that bridge. A browser fixture that injects a fake API verifies presentation, not customer-website integration or a real provider. Audit any proposed website placement/adapter separately before promising website availability.

## Before enabling it

1. Use a reviewed commit and a disposable/local or separately approved isolated test environment. Record the commit, project, database and intended synthetic account.
2. Read the [credentials handoff](SENIOR_HANDOVER_CREDENTIALS.md). Supply secrets securely on the backend only. Do not use real customer content for the rehearsal.
3. Confirm Auth, database and Storage target the same isolated environment. Check the intended user's subscription and remaining allowance if subscription mode is enabled.
4. Check migration history, functions and permissions. The original diagram migration is [20261021130000_add_answer_diagrams.sql](../supabase/migrations/20261021130000_add_answer_diagrams.sql); the subscription integration is [20261024040000_subscription_sketch_execution.sql](../supabase/migrations/20261024040000_subscription_sketch_execution.sql). These have earlier/later dependencies: do not run the two files alone, reapply applied migrations, or repair history blindly. Use the reviewed ordered migration process, only on the authorized target.
5. Start with deterministic tests before a separately authorized provider-backed generation. Keep payment/email actions disabled or fake. Do not turn off subscription or ownership enforcement to force a pass.

## Isolated local configuration

For an approved isolated test only, set these server-side values in the private runtime configuration:

```dotenv
DIAGRAM_GENERATION_ENABLED=true
DIAGRAM_MODEL=gpt-4.1-mini
# Supply OPENAI_API_KEY securely; never commit the value.
```

The implementation accepts `gpt-4.1-mini` and its supported dated form. It currently calls OpenAI's Responses endpoint, with a 25-second configured timeout and a 4,096-token output cap defined in code. It does not automatically use the main answer provider's model. Do not assume arbitrary model names work, or that setting nonexistent timeout environment variables changes these code constants.

Restart the backend after changing settings. If Electron's endpoint configuration changed, restart Electron too. Preserve the configured subscription mode and runtime; do not use an unmanaged path as evidence for hosted subscription admission.

Local startup examples, from the repository root and a prepared environment:

```powershell
# Terminal 1: backend; required environment must already be configured.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# Terminal 2: Windows Electron development.
cd frontend
npm run electron:dev
```

These commands do not provision Auth, SQL principals, a subscription, workers, or database schema. Use the existing isolated launcher when those services are required. They are development commands, not production service definitions.

## Actual user journey

1. Log in to the intended synthetic customer account in Electron. In subscription mode, use an entitled synthetic Plus/Pro account through the approved fixture/grant process; do not change a real account.
2. Start an authenticated interview session and obtain a completed system-design answer. Example question: “Explain a service with a client, API, queue, worker and database.” The saved answer must actually describe connected components; the question alone is insufficient.
3. Wait until the answer is durably saved. Look below it in the main window for **Architecture diagram**, not inside the overlay.
4. Select **Generate diagram** if available. Record the status, not private request bodies or authorization headers.
5. Verify the saved diagram is readable, its labels correspond to the answer, and the text alternative works. Reopen it in supported desktop session history.
6. Verify another synthetic account cannot read or mutate it. Sign out/switch accounts and ensure late results do not appear in the other account.

Saving the answer does not automatically generate a diagram. Reads and recovery of an already saved result are distinct from permission to start a new generation.

## How to diagnose an unavailable control

The source resolver is `GET /api/interview-sessions/{session_id}/answer-sources`, with exactly one of `transcript_id` or `request_id`. Electron sends it from the **main process**, so the renderer's Network tab does not show that HTTP request.

For an authorized local developer using synthetic data, stop active capture/generation and close the normal Electron instance. Run the backend and standalone Vite (`npm run dev`) in separate terminals. In a PowerShell terminal at `frontend/`, clear the process-local Node-only switch with `$env:ELECTRON_RUN_AS_NODE=$null`, then launch `.\node_modules\.bin\electron.cmd --inspect=127.0.0.1:9229 .`. Connect through `chrome://inspect` to the Electron main-process target. In `electron/answer_diagrams.cjs`, set a conditional breakpoint inside `perform()` immediately after `await manager._backendJson(...)`, with condition `action === 'resolve'`, so history requests continue normally. Inspect only `response.status`; on successful responses inspect the descriptor fields `response.payload.eligible`, `response.payload.generation_enabled` and `response.payload.reason`; on non-success responses inspect only `response.payload.detail.code` (for example, HTTP 503 with `subscription_unavailable`). Trigger the ordinary source lookup by opening an eligible saved answer; do not invoke generation merely to inspect it. Follow [Electron's main-process debugging guidance](https://www.electronjs.org/docs/latest/tutorial/debugging-main-process).

Keep the inspector loopback-only and close the debug instance afterward; never enable it on a production/public endpoint. Do not expand, log, screenshot or export the session, authorization context, full payload, tokens, answer content or account/source identifiers. The renderer's projected descriptor can omit unrecognized reason codes, so a null renderer reason does not establish that subscription authorization passed.

| Visible state/code | Meaning and next check |
| --- | --- |
| “Diagram generation is disabled” / `generation_disabled` | Check the effective backend flag and correct server/process first. The same UI text also appears when the flag is true but subscription authorization returns `generation_enabled=false`; inspect the safe resolver reason and verify entitlement/allowance, account restrictions and subscription-runtime availability before diagnosing it as a flag problem. Restart only after an actual configuration change. |
| Available only for verified saved system-design answers / `ineligible_source` | Verify the saved answer's trusted classification and source; do not change client labels to bypass it. |
| `source_pending` | The durable answer/source is not available yet; allow the normal persistence/resolve flow to finish. |
| `schema_unavailable` | Inspect migration/function/permission compatibility on the intended isolated DB. Missing schema is not a reason for a blind remote push. |
| `subscription_denied` | Inspect the authoritative entitlement, allowance and restriction state. |
| `subscription_unavailable` | The subscription runtime/database path is unavailable, not proof of an excluded plan. |
| `configuration_missing` | Verify backend credential presence and supported model; never log the credential value. |
| `busy` | The bounded generation capacity is occupied; preserve normal retry behavior. |
| `stale_source` / `operation_conflict` | The source revision or operation identity changed. Reload the authoritative source; do not reuse an old confirmation/operation blindly. |
| `insufficient_detail` | The answer lacks sufficient supported connected architecture; this is an honest outcome, not necessarily a service outage. |
| Provider failure / timeout / invalid graph | Inspect safe error categories and provider access. Do not retry uncertain work automatically or broaden graph validation. |
| `checkpoint` / `uncertain` | Saving/recovery is incomplete or the result cannot be confirmed. Use the existing recovery path; do not treat it as a new generation or promise it was uncharged. |

Generation/retry/cancel routes live under `/{session_id}/transcript-entries/{transcript_id}/diagram`. They bind operation IDs to source revisions. Never test them with another person's UUID or expose a reusable authenticated URL.

## Verification and evidence

Run focused existing tests after installing developer/test dependencies with `.\scripts\setup-dev.ps1 -WithTests` from the repository root. The setup script does not activate `.venv`, so use its interpreter explicitly:

```powershell
# Repository root: offline contracts; no live provider acceptance.
.\.venv\Scripts\python.exe -m pytest backend/tests/test_answer_diagrams.py -q

# Frontend directory: layout and Electron bridge contracts.
cd frontend
node --test src/diagram_layout.test.js tests/answer_diagrams.test.cjs
npm run build
```

Additional suites: [browser fixture tests](../frontend/tests/answer_diagrams.browser.test.mjs) and [PGlite persistence contract](../backend/tests/answer_diagrams.postgres.mjs). Read their prerequisites first. PGlite is not native PostgreSQL or hosted Supabase acceptance; browser fixtures are not real Electron/provider acceptance. Do not install a dependency into the application merely to make an optional test entry run.

Before local acceptance, record: disabled-flag behavior; eligible/ineligible sources; Free versus entitled accounts; source/operation replay and concurrency; cancellation/late results; account switching; missing key/schema; provider failure; graph validation; successful persistence/reopen; and usage accounting. Under the [approved policy](SUBSCRIPTION_APPROVED_POLICIES.md), charge only a valid durably saved retrievable result, release unsuccessful reservations as specified, and keep duplicate/saved replay free. Do not infer correct charging from a picture appearing.

Actual provider acceptance requires explicit authorization because it sends the authoritative answer/question to OpenAI and can incur cost. Record commit, environment, model, safe result/status and accounting outcome. Never claim that `store=False` in a request proves zero provider retention.

## Production enablement and disabling

Production additionally needs approved provider/data handling, restricted database principals, authenticated direct-API denial, deployed schema verification, C15 cleanup/export treatment, monitoring, rollback and installed-app acceptance. Follow the [production readiness guide](PRODUCTION_READINESS_AND_DEPLOYMENT_GUIDE.md) and C15 enablement gates. This document grants no production authorization.

To stop new generation, set the server flag to `false` and restart/redeploy through the approved release process. Existing reads/recovery remain separate. Disabling does not cancel every already running task, undo billing, remove saved diagrams, recall delivered bytes or authorize deleting history. Inspect active jobs and use the existing controlled cancellation/recovery lifecycle.

## Completion record

- [ ] Intended environment and synthetic identities verified.
- [ ] Flag/provider/model/schema/permissions verified.
- [ ] Entitled and denied accounts tested without bypasses.
- [ ] Actual Electron journey and saved-result recovery checked.
- [ ] Failure, concurrency, account-isolation and accounting checks passed.
- [ ] Fixture, native DB, actual-engine and provider evidence labelled separately.
- [ ] Production limitations and operator owner recorded.

This guide itself adds no new acceptance evidence and changes no configuration.
