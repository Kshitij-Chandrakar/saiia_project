# Answer streaming: Phase 2 backend and negotiated gRPC

Historical phase record. See [streaming closeout](ANSWER_STREAMING_CLOSEOUT.md)
for final verified status and separately attributed user acceptance.

2026-10-19. Backend/protocol support only; the shipped Electron client does not
advertise version 1 and remains on legacy delivery. User-visible fallback
streaming is not complete. No Phase 3 consumer implementation is included.

## Baseline and scope

HEAD at entry: `b8b6dc703a0e773ccc5ca9e757a821ab8f8ef2e3`, `dev/current-work`.
This includes PR #50's empty-native-read review fix, following `317489b` and
microphone merge `1c676ad` / PR #49. At entry there were 21 modified tracked
files and 25 untracked files, including Phase 1 and unrelated Screen/UI/model
work. No applicable AGENTS.md was found. Phase 1, G12 audio closeout and the
model-routing/recovery source and records were reviewed. Ponytail guidance
favored a request-local bridge rather than a second endpoint/preparation path.

An outside-repository inventory at `%TEMP%/saiia-answer-phase2-baseline.json`
records HEAD, original status, SHA-256 for every existing changed/untracked file,
and staged-diff hash. All those files remain byte-identical except the explicitly
extended Phase 1 fixture. Existing staging is unchanged. No `.env`, SQL, audio,
STT, mixer, model catalog, prompt policy, frontend consumer or unrelated code was
edited. Changes remain unstaged/uncommitted; no push, hosted query or migration.

Existing Graphify queries ran before and after changes:
`graphify query "stream_question_answer" --budget 250` (200 for the final check). They navigate the old
graph; no graph artifacts were regenerated or saved, so new code is not indexed.
Current source and executable tests are the authority.

## Changed files

| File | Purpose |
| --- | --- |
| `backend/app/answer_streaming.py` | Request-local policy, bounded display identity/publication, configured legacy streaming bridge |
| `backend/app/session_generation.py` | Opt-in primary/fallback deltas and revisions, unbound bridge in the existing single worker |
| `backend/app/grpc_answer_pipeline.py` | Preserve identity/replacements; fence stale/duplicate/post-terminal NDJSON |
| `backend/app/grpc_server.py` | Negotiate before STT can publish; emit replacements and identity; mint turn IDs for all routes |
| `backend/protos/interview_realtime.proto` | Additive version, acknowledgement, identity and replacement fields |
| `backend/app/grpc_generated/interview_realtime_pb2.py` | Regenerated message binding |
| `frontend/electron/protos/interview_realtime.proto` | Required shipped schema copy; no frontend advertisement |
| `backend/tests/test_answer_stream_phase2.py` | Negotiated streaming, legacy adapters, lifecycle, recovery and compatibility coverage |
| `backend/tests/test_answer_stream_characterization.py` | Optional version/old-codec/turn-queue fixture inputs; old-client assertions retained |
| `backend/tests/test_grpc_realtime.py` | Additive schema expectation and explicit foundation-only flags |
| This record | Contract, evidence and Phase 3 handoff |

`interview_realtime_pb2_grpc.py` was regenerated with repository tooling but its
content is unchanged because RPC signatures are unchanged. No frontend JS/JSX
or preload/main-process implementation changed.

## Contract and ordering

All prior protobuf field numbers and meanings remain intact. Added fields:

- `StartSession.answer_stream_version = 7`: exactly `1` requests this contract.
  Zero/absence and unknown versions decline to legacy behavior.
- `InterviewServerEvent.answer_stream_capabilities = 22`: new oneof event with
  `AnswerStreamCapabilities.version = 1`. Version 1 acknowledgement is emitted
  before opening STT, preventing a startup question from racing negotiation.
- `InterviewServerEvent.answer_replaced = 23`: new oneof `TextEvent`, whose text
  atomically replaces the display; empty text explicitly clears it.
- `InterviewServerEvent.answer_identity = 6`: envelope `AnswerIdentity` on
  question/start/delta/replacement/completion/turn-error events, after negotiation.
  Its fields are `retry_attempt = 1`, `provider_attempt = 2`,
  `display_revision = 3`, `accepted_turn = 4`.

Identity scopes:

1. Existing envelope `session_id` is the transport connection session, not cloud
   authorization. Verified cloud context still supplies owned session/model data.
2. Envelope `request_id` is a new server-minted UUID per worker turn on every
   route, including unmanaged routes; it never inherits an audio packet ID.
3. `accepted_turn` increases within the connection. Rejected candidates may leave
   ordinal gaps. Serial/latest-pending question handling is unchanged.
4. `retry_attempt` identifies durable logical-turn Retry. Current gRPC intake
   starts at zero; existing captured-turn Retry still uses HTTP. No gRPC Retry
   command was added.
5. `provider_attempt` identifies the outer selected-model attempt (0 primary,
   1 fallback). Unbound sessions number existing primary/fallback provider calls
   in order. It is not a model identifier. Replay is final-only; its fresh display
   scope starts at zero and does not imply a new provider call.
6. `display_revision` increases on reset and authoritative canonical replacement.
   Deltas append only to the current attempt/revision. A nested primary call or
   eligible legacy rate-limit retry advances revision even if provider attempt
   remains unchanged. Corrections do not publish a new provisional revision.

Failure invalidation and starting the next provider call are separate boundaries;
they can produce two successive empty replacements. Consumers must accept both
and must not require an attempt increase for every revision increase. Final
canonical replacement and `answer_completed.text` use the same final revision.
Completion is authoritative full text, never an append operation.

The existing `sequence_number` remains strictly connection-scoped across ALL
server events, including transcript/status events. Answer-only sequences can have
gaps. Internally, coordinator NDJSON sequence starts at zero per response; the
adapter rejects gaps/malformed sequence, ignores duplicates, and fences stale
identity before accumulation. Only replacement may open another display revision.
The handler also rejects stale deltas/duplicate replacements and ignores events
after completion. Database fence tokens remain backend-only.

## Negotiation and compatibility

| Client / server | Behavior verified |
| --- | --- |
| Old / new | Real localhost handler with pre-v1 dynamic protobuf codec: primary deltas and complete final text; no new events or identity; fallback stays buffered |
| New / old | Real localhost generic gRPC service with pre-v1 decoder ignores advertised field; no acknowledgement; new codec receives legacy deltas/full completion |
| New / new, version 1 | Empty resets, primary/fallback deltas, attempt/revision identity and canonical replacement/completion |
| Absent/unsupported version / new | Legacy events; no acknowledgement or new identity |
| Unmanaged/local route / new | Capability declined even if requested; legacy delivery retained, with unique turn request IDs |

Version 1 is supported only when the authorized cloud session enters the
coordinator with `ENABLE_SESSION_ANSWER_MODELS` enabled. Both bound and unbound
sessions qualify. Unmanaged/local execution is intentionally not advertised as
version 1: its separate legacy HTTP route cannot guarantee incremental fallback.
This is a capability limitation, not a substitution of its model or policy.

These are executable codec/transport tests, not a claim that a historical deployed
Electron binary or every historical server version was launched. Field parity is
also checked. Future clients must wait for acknowledgement and treat its absence
as legacy; health's old `answer_stream_available` does not imply version 1.

## Generation, cancellation and persistence

`incremental_answers` is a ContextVar captured at dispatch and reset by the gRPC
adapter after response creation. It is not a mutable global switch or a client
request-body property. HTTP defaults, old gRPC clients and durable request hashes
are unchanged. No independent fallback was added.

For selected bindings, `AttemptRun.call` forwards real primary AND fallback chunks
under that policy. Failed and newly started display attempts reset; queued deltas
from invalidated revisions are suppressed. Existing marker sanitation is reused.
Full raw output still enters the existing validation/correction/formatting path;
those secondary calls remain buffered. Shared first-token/idle/overall deadlines,
primary fallback reserve, configured selection and no-self-fallback remain.

For unbound sessions, `LegacyRun` wraps request-local copies of the already
configured providers inside the original generator worker. It does not assign a
binding, consult historical model constants, call the public streaming handler
recursively, repeat preparation or create a second persistence owner. Existing
primary selection, fallback eligibility and fallback implementation stay in
`AnswerGenerator`. OpenAI reuses its existing SDK stream; Groq/Ollama use their
configured endpoint/model/request parameters with streaming enabled. The existing
eligible Groq 429 retry remains on the same provider attempt with a new revision.
Other legacy fallback/cooldown decisions remain in the generator. Buffered
correction output is consumed internally through cancellable adapters and is never
sent as provisional display text. Legacy preparation/availability operations keep
their existing synchronous limitations/timeouts; this phase does not redesign them.
For negotiated unbound execution, final `fallback_used` retains the legacy
generator's result rather than being overwritten by the coordinator's always-zero
unbound outer index. HTTP and old-client metadata behavior is unchanged.

Coordinator queue remains 8; gRPC output queue remains 32; question queue remains
4. New queue publication waits on the existing generation control/deadline. Stop,
disconnect, authorization/session failure and supersession cancel work without
fallback. Closing the bridge cancels pending futures and closes attached SDK
streams. Already queued pre-Stop transport events still require immediate client
run fencing in Phase 3; transport order alone is not a UI lifecycle guarantee.
Version-1 disconnect cleanup is shielded against repeated gRPC cancellation while
the response iterator is suspended at a yield. A deterministic unbound-validation
disconnect test exposed an orphan-worker window before this change. Shielding
retains the existing answer-fence/audio-close/STT-close order and audio ownership,
native cleanup timeouts and lease policies; legacy cleanup remains unchanged.

One claim/checkpoint/complete boundary still owns the final transcript. Nothing
persists provisional text. Final replacement/success follows required validation
and durable completion. Checkpoint/completed recovery opens no provider; pending
claims do not create parallel work; uncertain state does not regenerate. Existing
typed turn errors leave a healthy connection usable for a subsequent question.
The paused recovery migration is untouched; mock-store coverage does not establish
hosted SQL parity or exactly-once upstream execution.

## Verification

Repository tools used from the root:

```powershell
E:/deepfake_envs/SaIIA/python.exe backend/scripts/generate_grpc.py
node frontend/scripts/sync-grpc-proto.cjs
```

Tests regenerate messages/service bindings in a temporary directory and compare
against checked-in output, including the repository's relative-import adjustment.
Both shipped proto files match. Existing runtime imports exercise generated-code
compatibility with the installed pinned tools/runtime.

Backend verification uses `%TEMP%/saiia-answer-phase2-tests.py`, invoked from
`backend` with:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B "$env:TEMP/saiia-answer-phase2-tests.py"
```

The outside-repository runner clears OpenAI/Groq/Gemini/AssemblyAI credentials
and sets `ENABLE_SESSION_ANSWER_MODELS`, `GRPC_STT_ENABLED` and
`GRPC_ANSWER_STREAM_ENABLED` to false in that test process only, before imports.
Fixtures explicitly enable mocked routes as needed. It wraps Python DNS/socket
connect and asyncio connection creation to reject non-loopback hosts. It invokes
the following exact pytest selection (after those guards):

```text
-q tests/test_answer_stream_phase2.py tests/test_answer_stream_characterization.py
tests/test_session_generation.py tests/test_answer_model_foundation.py
tests/test_answer_streaming.py tests/test_grpc_answers.py
tests/test_grpc_cloud_context.py tests/test_grpc_auto.py tests/test_grpc_manual.py
tests/test_grpc_combined.py tests/test_grpc_realtime.py tests/test_grpc_system_audio.py
tests/test_grpc_computer_lifecycle.py tests/test_grpc_health.py
-p no:cacheprovider --maxfail=3
```

Final guarded result: **286 passed**, 5 existing SWIG deprecation warnings,
42.70 seconds. This includes **57 Phase 2 cases**. An earlier guarded run passed
280 cases before the final lifecycle/policy-isolation cases were added. The new
disconnect test then caught the response-iterator cleanup window described above;
all cases pass after fixing it. A focused validation-interruption rerun also
passed all 4 bound/unbound Stop/disconnect cases.

New coverage includes independently gated multiple primary/fallback prefixes,
empty reset ordering, canonical formatting double, all three audio routes, old
codecs on real transport, configured OpenAI/Groq/Ollama unbound routes, adapter
network parsing with mocked responses, existing-generator unbound fallback,
nested 429 retry, stale queued chunks, duplicate/stale/post-terminal events,
direct fallback-model selection, terminal failure/next question, Stop during
primary/fallback/validation, disconnect during primary/fallback/validation, full
queue cancellation, concurrent HTTP/capable policy isolation, and
checkpoint/completed/pending/uncertain recovery. HTTP/catalog/correction and
legacy tests remain in the regression selection.

Frontend commands from `frontend`:

```powershell
node --test src/answer_stream_characterization.test.js src/grpc_realtime_client.test.js src/grpc_auto_session.test.js src/answer_stream.test.js src/answer_stream_protocol.test.js src/manual_chat_streaming.test.js src/grpc_manual_session.test.js src/grpc_computer_auto.test.js src/grpc_combined.test.js src/realtime_lifecycle.test.js
# 131 passed, 0 failed.
node --test tests/answer_stream.browser.test.mjs
# 3 passed, 0 failed. These exercise the unchanged legacy frontend, not version 1.
```

Python AST syntax, Node main/preload/client syntax, scoped whitespace checks and
`git diff --check` passed (existing LF/CRLF notices only). No install, frontend
production build, database/SQL execution or full repository suite was run.

One initial broader run had 3 failures / 240 passes: an outdated exact proto
assertion plus foundation tests inheriting local STT activation. The latter opened
an unintended AssemblyAI connection and debug output exposed an authorization
value. The failure occurred before audio submission; no audio was sent and no LLM
generation was initiated. The value is not reproduced here or saved in this
record. The foundation tests now explicitly disable STT/answer activation, and
subsequent verification uses blank credentials and network guards. The exposed
credential should be rotated separately; no credential/environment change was
performed. Later configured-provider tests also caught a test expectation using
`groq` instead of the existing provider label `Groq`; the test normalizes that
label without changing production routing.

## Phase 3 handoff and limitations

1. Add Electron version-1 advertisement only alongside acknowledgement handling,
   `answer_replaced`, identity validation and safe IPC snapshot fields. Preserve
   legacy mode when acknowledgement is absent; do not infer it from schema/health.
2. Fence connection epoch/transport session, authorized cloud session, request,
   accepted-turn ordinal, Retry attempt, provider attempt, revision and connection
   sequence. A replacement accepts a newer revision (including empty text);
   deltas only append within the current revision. Final text always replaces.
3. Cancel pending renderer frames/batches on reset, finalization, Stop, logout,
   session end and supersession. Check captured identity again inside queued React
   state updates. Carry equivalent fencing to the separate overlay window.
4. Retain one local history entry per logical turn, captured-turn HTTP Retry and
   existing save-only/uncertain recovery semantics. Do not save provisional text.
5. Bound/coalesce IPC and rendering without delaying reset/error/completion, then
   measure responsiveness with long answers. Audio/STT/mixer policies stay intact.
6. Add integrated capable Electron/React/overlay tests, followed by separately
   authorized Windows/live-provider acceptance. This phase tests Python gRPC and
   old/new codec consumers, not the complete new desktop flow or actual paint.

Real generation/provider services and hosted storage are mocked in successful
verification. Formatting coverage uses a fake canonical postprocessing result;
the production technical generator and final validation/storage normalization run,
but semantic provider validation is disabled in the shared fixture. These tests
do not establish every coding/semantic branch, multi-worker crash behavior,
instant cancellation of arbitrary synchronous preparation, Windows devices or
long-duration performance. No fixed production latency guarantee is made.
