# Manual Chat latency audit — 2026-09-07

## A. Finding and evidence boundary

At the time of this audit, the selected-resume desktop Chat route buffered the complete answer. The user waited for classification/profile loading, optional desktop re-verification/bootstrap, backend session authorization, cloud resume reads, generation, local postprocessing, and transcript persistence before the answer returned to the renderer. React/IPC delivery and Chat painting followed. The displayed timers did not cover these stages consistently. A post-audit implementation now provides an opt-in incremental path for this branch; the baseline measurements below remain buffered-path evidence and are not retroactively changed.

**The reported 15,391 ms incident is not causally reconciled.** Its reported primary span is 7,829.31 ms; the remaining 7,561.69 ms is an unattributed outer-span remainder, conditional on those fields belonging to the same request. It is not evidence of a second model call. There is no captured request ID or incident trace to establish that relationship retrospectively.

Four real provider-backed, isolated generator samples were completed with unchanged model, reasoning, token cap, refinement and validation settings. Every sample had **one provider call, one HTTP attempt, no correction, no semantic validation, no refinement and no fallback**. These measure the generator, not the authenticated manual Chat pipeline. No listener was present on local ports 8000, 5173 or 9222; no authenticated desktop session was exercised. Existing backend-run logs contained neither the supplied timing values nor the question. No original screenshot artifact was available beyond the user's description.

Worked on `dev/current-work`. No AGENTS.md was found in the repository or the checked parent directories. At the baseline-audit point, the pre-existing two-line diff in `frontend/electron/main.cjs` was preserved and production source, provider configuration and UI were not edited. The post-audit implementation is documented in section G. No login, account mutation, migration, commit, push or deployment was performed.

## B. Executed path and measured timelines

### Post-audit correction to the selected-resume path

The baseline path described below was verified before implementation. It no longer describes the default selected-resume desktop path when the stream bridge and `ENABLE_TRUE_ANSWER_STREAMING` are available: the renderer uses a request-scoped `startAnswerStream` preload operation, the main process consumes authenticated NDJSON incrementally, and the existing Chat state receives answer-text deltas before terminal completion. The buffered `generateAnswer` path remains available as a compatibility/rollback fallback when streaming is unavailable. Authentication, selected-resume ownership, final validation and transcript persistence were not bypassed.

### Desktop selected-resume Chat path established from source

| Stage | Files/functions | Execution conditions and scope |
|---|---|---|
| Enter | `frontend/src/components/AnswerPanel.jsx:606`, `handleChatKeyDown` → `handleManualSubmit` | Nonempty input, Enter without Shift; generating guard. Sends `submit-manual-question` through preload. |
| Toolbar IPC | `frontend/electron/preload.cjs:14`; `main.cjs:1013,1881` | `toolbar:trigger` checks startup completion and broadcasts to renderer windows. Broadcast is not a provider call. |
| Logical submission | `frontend/src/App.jsx:5314`, `handleManualQuestionSubmit`; action handler near 5772 | Guards busy modes, clears answer metadata, sets manual-generating. Calls `classifyAndGenerate` with `mode/source=chat`. Timer starts at 5349, after Enter/initial IPC and local reset work. |
| Classification | `App.jsx:2851`; `backend/app/api/classify.py:32`, `classify_text` | Awaited `/classify/` fetch + JSON parse. Reported classification prefers backend classifier-only duration, excluding transport. |
| Profile | `App.jsx:2382,2886`, `loadProfileForLiveAnswer` | Cached or awaited `/api/profile`; can force a second load if invalid. Occurs even though selected resume later replaces submitted profile. Profile can also be prefetched on app mount. |
| Generation selection | `App.jsx:1457,1493`, `streamGenerateAnswer` | The audited baseline invoked `window.saiia.generateAnswer` and buffered JSON. The post-audit selected-resume desktop path invokes the dedicated `startAnswerStream` bridge and consumes `/generate/stream`; it keeps the buffered `generateAnswer` path as a rollback/compatibility fallback when streaming is unavailable. |
| Desktop authentication/HTTP | `desktop_auth_session.cjs`, `openAnswerStream`; `_backendJson` | The stream bridge performs the same authenticated verification/bootstrap and owner-scoped backend request checks before handing the response stream to the main process. It uses a request-scoped abort signal and never returns credentials to the renderer. |
| Optional bootstrap work | `backend/app/api/auth.py:225`; `app/cloud/profile_bootstrap.py` | Profile bootstrap and synchronous best-effort welcome-email dry-run event handling exist on this conditional route. Not measured or invoked by this audit. Never assume every question executes them. |
| Backend entry | `backend/app/main.py`; `app/api/generate.py:1578` | FastAPI validation, CORS middleware; synchronous `_authorize_generation_session` executes before endpoint's `started` timer. JWT verification and owner-scoped session read. |
| Plan/context | `generate.py:1587,1738,1781` | Follow-up resolution/compiler, rule routing, immutable answer plan; job context omitted for this forbidden-policy concept; selected resume still fetched despite legacy profile context being disabled. |
| Resume reads | `cloud/cloud_resume.py:1226`, `retrieve_resume_chunks` | Owner-scoped resume readiness read, active chunk read, then local ranking. Returned RAG duration covers ranking, not the preceding cloud reads. |
| Generator | `nlp/answer_generator.py:1238`, `generate_answer` | Prompt → synchronous OpenAI Responses API → category extraction/cleanup → formatting and deterministic validation. Selected-resume-authoritative mode skips semantic validation and disables controlled variation. Coding-only corrections are not relevant to these concepts. |
| Persistence | `generate.py:979`, `_store_transcript_for_response`; `cloud/interview_transcripts.py:246` | With session ID: authentication plus synchronous transcript RPC before return. Ordinary generation history write, outside generator timing. No separate awaited usage-accounting call found. |
| Response/Chat display | `desktop_auth_session.cjs`, `main.cjs`, `preload.cjs`, `answer_stream_protocol.cjs`, `App.jsx`, `AnswerPanel.jsx` | The post-audit stream is parsed incrementally in the trusted main process, forwarded through a request-scoped preload event channel, and applied to the existing Chat state as deltas. The terminal event is emitted only after backend transcript persistence. React state receipt is measured separately from actual paint; paint remains unmeasured. |

The alternate no-selected-resume/non-desktop branch already used NDJSON `/generate/stream`; a non-OK stream response triggers `/generate/` fallback. The post-audit desktop bridge now uses the same backend stream contract only after retaining the selected-resume authorization/context path. Microphone/STT, audio watchdog/cooldown and screen capture were not executed in the isolated samples and are not awaited by typed Chat submission. No intentional debounce or queue delay was found on the traced selected-resume branch. A rapid submission race is not ruled out by React state guards, but there is no trace showing duplicate execution.

### Supplied incident

| Measurement | Supplied value | What can be established |
|---|---:|---|
| Pipeline / answer received | 15,391 / 15,391 ms | Renderer outer span; not Enter-to-paint |
| Primary generation | 7,829.31 ms | SDK call plus initial cleanup, if current code/request matches |
| Classification / profile load | 15.25 / 8.4 ms | Different scopes; classification excludes its HTTP overhead |
| RAG / prompt build | 1.15 / 3.12 ms | Local ranking / prompt assembly; not whole context acquisition |
| Provider calls / HTTP attempts | Unknown / unknown | Cannot infer from durations |
| First visible / final Chat paint | Unknown / unknown | `n/a` and zero UI spans do not establish these |

### Controlled provider-backed sample

Artifact: `tmp/manual-chat-generator-baseline.json`. Each record has an audit request UUID, nested call ID and HTTP attempt index. All durations use `time.perf_counter()` in one process. The same generator/client and synthetic two-chunk selected-resume profile were reused. No cloud context, private resume, follow-up history, session or UI was used. Category was determined normally. This is a changed environment, not a reproduction of the incident.

| Run | Question | Primary ms | Generator wall ms | Calls / attempts | Input / output / reasoning tokens | First visible / Chat complete |
|---|---|---:|---:|---:|---|---|
| 1, first provider request | what is clustering | 4,376.02 | 4,381.07 | 1 / 1 | 1681 / 188 / 16 | Unmeasured |
| 2, warm | what is clustering | 2,812.30 | 2,813.25 | 1 / 1 | 1681 / 175 / 15 | Unmeasured |
| 3, warm | what is clustering | 2,686.10 | 2,686.78 | 1 / 1 | 1681 / 188 / 15 | Unmeasured |
| 4, warm | what is normalization | 2,278.07 | 2,278.77 | 1 / 1 | 1763 / 197 / 23 | Unmeasured |

Reasoning tokens are a subset of output tokens, not additive.

The following sequential observer intervals explain each isolated generator wall time approximately; timestamp rounding and observer overhead account for small differences. They must not be added again to primary-generation timing.

| Run | Generation start → provider call | SDK before HTTP dispatch | HTTP dispatch → response headers | Headers → parsed SDK response | Provider return → generator complete |
|---|---:|---:|---:|---:|---:|
| 1 | 1.68 | 56.89 | 4168.85 | 142.16 | 11.48 |
| 2 | 0.49 | 2.06 | 2777.94 | 31.74 | 1.01 |
| 3 | 0.39 | 1.66 | 2632.86 | 51.23 | 0.63 |
| 4 | 0.42 | 1.74 | 2240.83 | 35.01 | 0.76 |

Units: ms. Headers-to-parsed combines remaining body receipt and SDK parsing; full-body receipt is not separately observable here. No provider text chunks exist on this nonstreaming call. HTTP time includes transport, remote waiting and generation: it is **not model-compute time**. First-run AnswerGenerator/client construction took 426.87 ms outside these intervals. The script's first fixture inspection also consumed approximately 1.07 s before generation (including lazy setup); it warmed prompt construction. Therefore run 1 is first-provider-request evidence, not a pristine cold application startup measurement. The smaller warm values do not establish a causal cache benefit.

## C. Timing reconciliation

`App.jsx:3023–3063` measures answer-received from its pipeline start, then defines total as **answer-received + frontend-update**. They are related, not independent end-to-end measurements. The latter measures synchronous work around an optional transcript setter/audio reset, rounded to two decimals; it does not wait for React commit, state IPC, formatting or a frame. `overlay_commit_ms` is likewise a misleading name for the tiny local block. Equal totals with a rounded zero are expected.

The normal success path assigns primary generation from the returned payload and total from the awaiting renderer request, guarded by latest request ID. That supports same-request association during ordinary execution. However diagnostics are not an immutable correlated trace: history selection can restore old metadata (`App.jsx:1422`), and screen/audio states are independent. The incident association remains unverified.

`resetAnswerMeta` clears pipeline timings; defaults are null. Classification bypass explicitly assigns zero, cached profile display assigns zero, some RAG paths explicitly return zero, and UI code rounds tiny spans to zero. Zero is not a universal measured-zero convention. In Chat the pipeline starts after the user's initial Enter/IPC, not while typing. Cached profile timing can originate from earlier prefetch, but the displayed profile-load entry uses zero for cache hits.

Primary generation at `answer_generator.py:2387–2401` includes the SDK call, all internal retries/backoff of that call, extraction and cleanup. It excludes prompt construction and later validation/correction/variation, cloud operations and persistence. `generation_ms` is assigned at line 1691 **before** later deterministic/semantic validation and variation; even that broader field is not complete generator wall time. Backend `total_pipeline_ms` is normally a sum of supplied and selected stage numbers, not endpoint wall time; it also omits cloud and persistence spans.

Thus **7,561.69 ms remains unallocated for the incident**. It may contain pre-generation and post-generation cloud/desktop/transport work, plus unmeasured overhead. Do not subtract nested classification/RAG/provider spans as if every displayed value were a disjoint interval. No per-stage portion of that remainder has been measured.

## D. Confirmed findings versus hypotheses

| Finding | Evidence | Measured contribution | Confidence / limits |
|---|---|---|---|
| Selected-resume Chat buffers complete answer | `App.jsx:1493`, desktop `_backendJson`, nonstreaming provider | All samples nonstreaming; first-visible benefit cannot be quantified | High for code branch; no incident UI trace |
| Cloud context reads excluded from RAG timer | `cloud_resume.py:1235–1302`; indexer starts timer later | Unknown cloud duration | High timer-scope evidence; not proof of a 7.56 s cloud delay |
| Session authorization and transcript RPC outside primary span | `generate.py:1583,979` | Unknown | High code evidence, conditional on session ID |
| Expired desktop verification adds sequential requests | `desktop_auth_session.cjs:983,631,667` | Unknown | Conditional; 30 s freshness default, incident cache state unknown |
| Provider wait dominates isolated generator | Trace headers and call spans above | 2.24–4.17 s dispatch-to-headers | High for samples only; no network/queue/inference split |
| No duplicate calls/retries in samples | One phase/call, one HTTP hook event each | Zero retry or extra-call time in samples | High for samples; original count unknown |
| Local postprocessing is small in samples | Return-to-complete and deterministic timers | 0.63–11.48 ms after provider return | High for these short answers; no renderer profiling |
| Synchronous async-endpoint work can block event loop | Direct synchronous generator/cloud calls inside `async def generate_answer` | No concurrent-request delay measured | Structural risk, not incident cause established |
| Two loading indicators are duplicate presentation | `AnswerPanel.jsx:302–310` fallback body plus `960–963` explicit status | No measured execution cost | High source evidence; no screenshot/paint capture |

OpenAI client is constructed once per AnswerGenerator and reused. Endpoint module has a persistent generator. Cloud helper factories construct new service/client sessions for authorization, resume retrieval and transcript writes; cross-request connection reuse is not supplied by those short-lived instances. TLS/connect/cold-start costs are plausible but unmeasured. Long renderer tasks, full-body transport time, bootstrap state and concurrency blocking remain hypotheses. Do not attribute this typed flow to audio or screen activity without new evidence.

### Effective provider configuration

Local measured provider/model: OpenAI / `gpt-5.4-mini-2026-03-17`, also confirmed in every returned response. Installed Python SDK: **1.97.1**. API method: synchronous `client.responses.create`; no `stream=True`; primary timeout 25 s, output cap 2500, reasoning effort `low`. Client max retries is 2. Refinement and parallel refinement are false; semantic validation and conditional correction are configured true but did not execute because authoritative selected-resume mode suppresses semantic validation. No provider configuration was changed.

SDK automatic retries are inside the measured primary call. The application hardcodes `primary_retry_used=False` for OpenAI, so that flag cannot establish SDK attempt count. Version-matched official SDK documentation confirms default retries for connection errors and selected HTTP statuses: [openai-python v1.97.1](https://github.com/openai/openai-python/tree/v1.97.1#retries). Installed `_base_client.py` also places retry sleep within the call. Observed attempts, not the application flag, were used in this audit. Provider token usage is discarded by the ordinary text-returning wrapper; diagnostic observers captured it before disposal.

### Context and classification contradictions

* `profile_context_used=true` in the screen diagnostics reads **screenProfileContextUsed**, initialized true (`App.jsx:1237`; `MainDiagnosticsWindow.jsx:1243`). It is a different scope from Chat pipeline context, not evidence that Chat sent profile text.
* `Profile context used=false` is the endpoint's legacy `use_profile_context`, disabled by forbidden policy and selected-resume strict mode (`generate.py:1738`).
* `selected_resume_context_used_in_prompt=true` is calculated from strict mode and retrieved context availability (`generate.py:471`), **not final prompt inspection**.
* Selected resume retrieval still executes; `_generation_profile_context_enabled` returns true when selected context is active. But `_build_prompt` checks `_needs_candidate_context`; neutral clustering does not qualify, so candidate profile and snippets are excluded.
* Isolated synthetic fixtures showed neither of two resume text sentinels in the prompt for clustering or normalization. The strict selected-resume **instruction** remained. A separate synthetic comparison measured 314 extra characters due to that instruction, with no resume text. No token/time attribution to this instruction was measured. Real incident context/token impact is unknown; retrieval count alone proves neither inclusion nor influence.
* Deterministic validation is passed `profile_context_enabled and (profile or snippets)`, rather than observed prompt inclusion (`answer_generator.py:1809`). Samples returned one validation warning despite absent resume text. This is a real metadata/validation-input mismatch. The prompt also contains both forbidden-context guidance and selected-resume-only instructions; that tension is real, but its quality/latency effect is unmeasured.
* `generationStarted` is an auto/audio state, not Chat's `isManualGenerating`; Chat does not set it true. `answerPipelineState` is updated under `trackAudioPipeline`, false for Chat. Idle/false does not contradict a completed Chat generation.
* Clustering misses the technical keyword/definition whitelist and returns `general` (`classifier.py:193–227`). The planner separately recognizes “what is” and creates `technical_concept`, FORBIDDEN profile/job context, confidence 0.86 (`answer_planner.py:109`). Category affects prompt guidance/rule selection but did not select another provider or a general fallback plan. Normalization classified technical yet used the same conceptual plan and provider settings. No classifier changes are proposed from one example.

## E. Ranked proposals and implementation status

These are candidates ranked by the confirmed code/trace evidence, not claimed incident savings.

| Rank | Specific proposal | Target / benefit | Risk and required validation |
|---|---|---|---|
| 1 | Add authenticated incremental answer delivery to the selected-resume desktop bridge, preserving owner checks, formatting and final validation | **Implemented locally after the baseline audit.** First-visible benefit is expected, but no live TTFT or total-time estimate is available. | Focused synthetic stream/auth tests pass. Live authenticated, paint-level and packaged Electron validation remain required. |
| 2 | After cloud spans are measured, reuse cloud HTTP clients and eliminate demonstrably redundant context/session reads without weakening authorization | Both if cloud setup/read time is significant; no measured estimate | Request-scoped auth must remain isolated; test user changes, stale resume generations, revocation, pool concurrency and failures. |
| 3 | After measuring transcript RPC cost, consider durable decoupling from response completion | Both on this buffered path; potential ceiling is measured RPC time, currently unknown | Do not fire-and-forget history: preserve durability, idempotency, ownership, order and failure reporting. |
| 4 | Make context diagnostics reflect actual final prompt inclusion; reconcile selected-resume instruction with immutable policy and avoid context work only when policy safely permits | Diagnostics immediately; possible total improvement from skipped cloud reads remains unmeasured | Prompt-policy/quality change requires separate approval and conceptual, personal, project and follow-up regression coverage. No prompt optimization applied. |
| 5 | Move synchronous blocking work off the ASGI event loop or use equivalent async clients | **Implemented for the stream path with bounded thread offload.** It targets event-loop responsiveness; no demonstrated single-request reduction. | Preserve cancellation, thread safety, context correlation, auth and response behavior; bounded concurrency validation remains. |

Do not disable validation, remove examples, reduce token caps, change models, weaken authentication or extend verification freshness to chase this screenshot. Bootstrap optimization should only be considered after a trace proves that branch ran and quantifies it. Duplicate loading presentation is confirmed but is not a latency optimization.

## F. Diagnostic changes, checks and missing live evidence

The original audit added these diagnostic artifacts:

1. `scripts/audit_manual_chat_latency.py`: explicitly invoked standalone harness. Default performs synthetic prompt inspection only; `--live` performs a fixed maximum four samples, stopping on failure. Reuses configured provider/client, records safe monotonic events, call/attempt identities, sizes and token usage. Its temporary wrappers/hooks are restored after each sample. It suppresses existing application logs for this isolated run. No production import or response contract change.
2. `scripts/audit_manual_chat_backend.py`: explicitly invoked `--serve` localhost launcher. Wraps existing `/generate/` handler and selected synchronous stages; inherits the request body's existing request ID when valid, records backend entry, auth/session, cloud reads, prompt/provider/cleanup, persistence, response-ready and body-send events. Adds SDK HTTP attempt/header hooks. Normal app startup does not load it. It logs no credentials, headers, IDs of users/resumes/sessions, prompts or answers. It only traces `/generate/`, not bootstrap/classification or the alternate stream route. Standard application logging is unchanged. Observer overhead is not calibrated.
3. This report. Safe local artifacts: `tmp/manual-chat-generator-baseline.json`, `tmp/manual-chat-fixture.json`, `tmp/manual-chat-backend-smoke.jsonl` (tmp is ignored by Git).

The post-audit streaming implementation also added production timing fields in `frontend/src/App.jsx`, explicit diagnostics labels in `frontend/src/components/MainDiagnosticsWindow.jsx`, and the trusted stream protocol/bridge files `frontend/electron/answer_stream_protocol.cjs`, `frontend/electron/desktop_auth_session.cjs`, `frontend/electron/main.cjs`, and `frontend/electron/preload.cjs`. These changes emit only bounded event types, safe metadata, counts and durations. They do not log prompts, answers, resume content, credentials or auth headers. The existing public buffered endpoint contract remains available for rollback with `ENABLE_TRUE_ANSWER_STREAMING=false`.

Baseline checks: four successful live generator samples; two no-provider synthetic prompt fixtures; synthetic instruction-size comparison; backend ASGI smoke preserved invalid-question HTTP 400 and recorded zero provider calls; Python compilation; targeted selected-resume, planner and classifier tests **101 passed**. Initial pytest invocation needed `PYTHONPATH=backend`; full matrix then had 25 failures solely because Trio was missing, with 101 passing. Re-running `-k 'not trio'` yielded 101 passed / 25 deselected. Post-audit checks are recorded in section G. Graphify query ran before the streaming implementation changes; graph update for the final implementation is run separately during handoff. `git diff --check` passed before the post-audit edits.

### Exact remaining trace needed

An existing authenticated desktop runtime with the same selected resume/session/context and baseline settings is needed to connect the original class of wait to cloud and paint timings. This audit did not start login/bootstrap or create accounts/sessions to manufacture that environment. Four generator samples are the entire paid sample; no load test was run.

For a future bounded local UI reproduction, capture the real Chat Enter event, its toolbar IPC, App handler entry, classification/profile full round trips, desktop verification/bootstrap spans, stream dispatch/headers, first answer state update, Chat state receipt, and final Chat paint under the **same logical request ID**. Current backend audit instrumentation starts correlation at the existing generation request ID; it does not magically correlate earlier Enter/auth operations. The post-audit renderer/main fields now cover request dispatch, first delta/state update and backend stream duration, but browser paint evidence remains outstanding and is not claimed complete.

Use per-process `performance.now()`/`perf_counter()` durations, matching IDs and causal boundaries; never subtract clocks across processes. Capture browser Performance trace/filmstrip in the actual Chat renderer; use nonempty answer DOM evidence plus a frame showing the answer. A React setter, MutationObserver, IPC receipt or requestAnimationFrame callback alone is not proof of displayed pixels. A double-rAF marker is only an approximation and must be labeled. Record first visible answer and final rendered answer separately, including whether the panel was selected/visible. Filmstrips may contain private content and should remain local/redacted.

Specifically unresolved: Enter-to-App overhead; desktop freshness branch and duration; backend session/cloud fetch/persistence durations; original SDK attempts/token usage; backend-to-client headers/body interval; state-to-Chat-frame latency; long renderer tasks; duplicate submissions in the original incident; and live first-delta/completion comparison against the 15,391 ms baseline. No screenshot-derived claim can assign these times. The supplied 7,561.69 ms remainder stays unexplained until this evidence exists.

## G. Post-audit streaming implementation (2026-09-08)

### Architecture and event contract

The selected-resume desktop Chat path now uses `startAnswerStream` only when the narrow preload bridge is available and the existing selected-resume desktop branch is active. The main process calls the authenticated `openAnswerStream` manager method, which preserves verification/bootstrap, backend authorization, selected-resume ownership and the existing `/generate/stream` request. The main process parses NDJSON incrementally with `TextDecoder`, including split UTF-8 transport chunks and multiple events per chunk, then forwards only the originating request's events through `onAnswerStreamEvent`. The renderer appends answer-text `delta` events to the existing Chat state before completion. No generic fetch or unrestricted event subscription was added.

The safe event types are `start`, `delta`, `replace`, `metadata`, `error`, and `done`. `delta`/`replace` carry answer text only; control and metadata fields are bounded and sanitized. Provider reasoning, raw provider events, prompts, resume chunks, auth data and other private payloads are excluded. `done` is terminal only when the backend has completed its existing transcript persistence. Missing terminal events are treated as interrupted. Partial output is not stored or reported as a successfully completed answer, and no fallback is started after visible text has been emitted.

### Cancellation, ownership and fallback

The main process keeps one request-scoped stream entry with an abort controller and sender/request identity. Logout, user change, window destruction and terminal auth cleanup abort applicable streams; renderer request-generation guards reject stale deltas and late results. The backend uses bounded thread offload around its synchronous provider iterator and synchronous preparation/final processing so the ASGI event loop is not held by those operations. Thread cancellation is cooperative at the transport boundary; provider-specific cancellation remains a limitation of the synchronous SDK path.

Existing final answer normalization, deterministic validation, correction/variation rules, transcript persistence, model, reasoning settings and token caps are retained. The stream sends incremental primary text, then an accepted post-processing answer as `replace` before the terminal event. If the stream endpoint is unavailable before generation begins, the renderer uses the existing buffered path. If a stream fails after deltas, it reports an incomplete answer rather than silently issuing a second generation.

### Measurements and verification

The streaming path now records separate nullable values: backend `provider_first_delta_ms` is request start to the first item returned by the provider iterator; backend `time_to_first_visible_text_ms` is request start to the first nonempty sanitized answer delta; renderer `frontend_first_delta_ms` is Chat pipeline start to the first renderer answer-state update; `stream_dispatch_to_first_delta_ms` is stream dispatch to that update; and `backend_stream_duration_ms` covers the backend stream lifecycle. Diagnostics distinguish these values from final completion. A renderer state update is not presented as a painted-frame measurement; first visible pixels remain `n/a` until an actual renderer performance trace/filmstrip is captured. No two-second target is claimed.

Focused checks completed after implementation: backend streaming tests **17 passed** (with 5 existing SWIG deprecation warnings); the focused frontend/Electron Node tests **71 passed**; `npm run build` passed with only the existing large-chunk warning. The stream tests cover fragmented NDJSON/UTF-8 parsing, terminal-event enforcement, provider reasoning-event exclusion, missing provider completion, sync-provider event-loop responsiveness, authenticated stream request shape, stale/cancel-safe source behavior, and buffered fallback compatibility. `python -m compileall -q backend/app` and `git diff --check` passed. The full backend suite and `scripts/pre_commit_audit.ps1` are recorded separately during handoff.

The final hardening binds one stream to its validated sender and logical request ID, assigns strictly increasing backend event sequence numbers, rejects out-of-order/missing events in the main process, removes the subscription on completion/cancellation, aborts on sender destruction/logout/account change, and permits only a bounded allowlist of safe metadata through preload. `done` follows final persistence. If a session-bound transcript cannot be stored, the stream emits incomplete/error rather than a successful terminal answer. Coding/provider paths that require the buffered contract return to the existing authenticated JSON path before any answer delta. Renderer updates are frame-batched without typewriter delay. Opt-in browser Performance marks record submit, state and double-animation-frame opportunities; the latter are explicitly approximations, not proof of painted pixels.

Live authenticated desktop comparison for “what is clustering”, a second conceptual question, a resume-grounded question and a practical/coding question was not available in this environment. No local authenticated session/listener was used, and no real user or account data was created. Required follow-up evidence is: first-delta time, first painted Chat time, final persistence/completion time, provider-call count and any backend pre-generation/persistence spans under the same request ID, plus actual Electron cancellation/logout/user-switch checks.

### Rollout and rollback

The existing `ENABLE_TRUE_ANSWER_STREAMING` feature flag controls the stream route where the current application branch already reads it. Disable that flag to return to the buffered `/generate/` contract without changing authentication or persistence. The stream path is not considered fully production-validated until live authenticated ownership, cancellation, paint-level timing, and packaged Electron checks are completed.
