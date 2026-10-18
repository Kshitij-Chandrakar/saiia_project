# Session answer models: Phase 0/1 record

> Historical phase record. Current implementation, Saiia-dev activation, live evidence and remaining limits are consolidated in [SESSION_ANSWER_MODELS_CLOSEOUT.md](SESSION_ANSWER_MODELS_CLOSEOUT.md). Statements below about disabled gates, missing credentials or future integration describe the phase at the time; they are not the current development activation status.


Date: 2026-10-18 (Asia/Calcutta). Scope: baseline and inactive backend foundation only.

## Changes and boundaries

- `backend/app/answer_models.py`: immutable five-option catalog, stable product keys,
  display/provider/API identifiers, effort profiles and output limits. Its safe
  projection keeps every option selectable, including Gemini without credentials.
  Credential presence is separate from live access (`not_verified`). No catalog API
  route or UI was added in this phase.
- `backend/app/answer_generation.py`: request-scoped async Responses, Groq Chat
  Completions and Gemini GenerateContent SSE adapters; normalized answer-only output
  and reported model/version; attempt coordinator, deadlines and cancellation.
- Existing synchronous OpenAI/Groq adapters have mutable model/retry state and do not
  provide the shared async cancellation contract. The foundation reuses their fixed
  API protocols and the already-installed `httpx` dependency rather than modifying
  those runtime adapters or introducing another SDK. No dependencies were added.
- `backend/app/config.py` and `.env.example`: disabled-by-default foundation flag,
  optional Gemini credential (also accepts backend `GOOGLE_API_KEY`) and provisional
  deadlines. The real `.env` was not edited.
- `backend/tests/test_answer_model_foundation.py`: 41 provider-free cases using
  MockTransport, controllable clocks and cancellable fake streams.

No session schema, migration, request-claim storage, variation memory, HTTP/gRPC route,
watchdog, protobuf, Electron, STT, classification, OCR, Ask AI or AI Notes change.
Existing runtime generation modules do not import either foundation module. Even
enabling the flag does not activate a route: integration remains a future phase.

## Provider evidence

Checked official documentation before encoding the profiles:

- [OpenAI Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and
  [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra):
  `gpt-5.6-luna`, `gpt-5.6-terra`, Responses streaming. Profile uses low effort,
  `max_output_tokens`, no optional sampling parameters, and `store=false`.
- [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses):
  consume output-text deltas; require completed response; reject incomplete/failed.
- [Groq parameters](https://console.groq.com/docs/api-reference) and
  [reasoning](https://console.groq.com/docs/reasoning): `openai/gpt-oss-120b`,
  `max_completion_tokens`, low/medium/high efforts. GPT-OSS does not support
  `reasoning_format`; send `include_reasoning=false`, consume content only.
- [Gemini 3.5/3.6](https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.6)
  and [GenerateContent](https://ai.google.dev/api/generate-content):
  `gemini-3.5-flash-lite`, `gemini-3.6-flash`, streaming GenerateContent;
  no deprecated sampling parameters, candidate count or prefilled model turn.
  Use minimal/medium thinking respectively; ignore thought parts.

No credential validity, account model access or provider latency is claimed. No
billable generation calls were made. Gemini live verification is pending its key.

## Deadline and attempt contract

| Seconds | Standard | Coding |
| --- | ---: | ---: |
| First answer token | 6 | 10 |
| Idle answer stream | 4 | 6 |
| Overall | 25 | 40 |
| Fallback reserve | 8 | 12 |

All are configurable provisional defaults, not benchmarks. Reserve must cover the
first-token allowance and be less than overall. Primary ends no later than overall
minus reserve (17/28 seconds); first-token and idle limits may end it earlier.
Fallback uses the remaining original overall budget, including unused primary time.
Direct GPT-OSS has no fallback and no reserve cutoff. Heartbeats, reasoning and
whitespace-only deltas never extend answer-token deadlines.

The monotonic `GenerationBudget` is created once per logical generation. Future
answer-producing correction calls must reuse it and its `wait` method; passing an
existing budget never resets its start. No correction pipeline was wired this phase.

Missing credentials fail before opening a provider connection. Provider failures
allow one explicit fallback; SDK retries are absent and HTTP transport retries are
zero. Unknown keys, disabled feature and lifecycle stops cannot initiate fallback.
The future HTTP/gRPC caller must signal `GenerationControl.cancel()` on logout,
supersession, authorization rejection or termination and close the iterator on
disconnect; these lifecycle integrations are intentionally not active yet.

Every provisional delta/discard identifies its attempt. Fallback text is buffered,
then emits a full replacement and one normalized final result. Consumers must never
append fallback text to primary text, or persist provisional events. Both attempts
failing raises typed `GenerationFailure` with the exact safe terminal message.
Selection, actual requested model and provider-reported version remain separate.
No UI toast/banner or persistence is performed by this foundation.

Rollout requirement for the next phase: disabling admission for new model-bound
sessions must not reroute existing bound sessions to global defaults. Session phase
must define immutable stored contracts and safe continued execution or explicit
failure before exposing this feature.

## Baseline and verification commands

Existing work at entry: 18 tracked modified files plus untracked G9 realtime tests,
router/lifecycle files and documentation. Relevant overlap: config/template, FastAPI
lifespan, gRPC server/generated contracts, Electron bridge/client, App and Auto tests.
Only additive config/template edits overlap this phase; existing edits were preserved.
No reset, stash, commit, installation or deployment was performed.

From repository root, inspected with:

```powershell
git status --short
git diff --stat
git diff -- backend/app/config.py backend/app/main.py backend/app/grpc_server.py
git diff -- .env.example
rg --files -g AGENTS.md --hidden -g '!node_modules' -g '!.git'
```

No repository AGENTS.md found; previously discovered Codex-level file is empty.

Initial root invocation of the backend command below, using `backend/tests/` paths,
failed collection with two `ModuleNotFoundError: app` errors. This was an invocation
path issue before edits; corrected by running from `backend`, without environment
changes. The corrected baseline passed **132 tests**, with five existing SWIG
deprecation warnings:

```powershell
# Working directory: backend
python -m pytest -q tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py
```

Frontend baseline and post-change command both passed **113 tests**:

```powershell
# Working directory: repository root
node --test frontend/src/answer_stream.test.js frontend/src/answer_stream_protocol.test.js frontend/src/generation_auth.test.js frontend/src/generation_dispatch.test.js frontend/src/request_state.test.js frontend/src/grpc_auto_session.test.js frontend/src/grpc_realtime_client.test.js frontend/src/realtime_lifecycle.test.js
```

Final backend run passed **173 tests** (132 existing + 41 foundation), same five
SWIG warnings, no failures:

```powershell
# Working directory: backend
python -m pytest -q tests/test_answer_model_foundation.py tests/test_cloud_interview_sessions.py tests/test_interview_session_routes.py tests/test_provider_routing.py tests/test_openai_answer_pipeline.py tests/test_answer_streaming.py tests/test_grpc_answers.py tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_cloud_interview_transcripts.py tests/test_interview_session_transcript_routes.py
```

`git diff --check` passed. Source inspection plus an automated import-boundary test
confirms production generation and gRPC remain disconnected from the foundation;
existing routing/streaming/Auto/cancellation/auth/persistence regression tests pass.
This is code/test evidence, not live Electron/provider verification.

Graphify before edits:

```powershell
graphify query "GenerateRequest stream_openai_primary_answer" --budget 1000
```

After edits, ran provider-free Graphify structural extraction on the two new modules
and their test file. Fresh scoped output: **71 nodes, 166 edges**, under
`tmp/answer-model-foundation-graphify/graphify-out/graph.json`. Queried it with:

```powershell
# Working directory: tmp/answer-model-foundation-graphify
graphify query "GenerationBudget stream_answer" --budget 900
```

The existing repository-wide graph was not rebuilt; scoped extraction avoids
re-indexing unrelated uncommitted work. No semantic extraction/model call was used.

## Next phase, not authorized by this phase

Immutable session selection and deterministic legacy compatibility: storage/API/RPC
contracts, database write protection, authoritative restoration, and rollout policy.
Do not enable UI options or activate HTTP/gRPC routing before those contracts exist.
