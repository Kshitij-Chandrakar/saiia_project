# Analyze Screen Backend Continuity — Phase 2

Date: 2026-10-18. Backend implementation only. The Electron contextual flow is
not activated; no chooser, shortcut, IPC, migration or provider-routing change.

Status: Phase 2 implemented and automated checks passed locally. Live acceptance
and end-to-end functionality remain pending Phase 3.

Phase 3 amendment: the Electron contextual flow is now connected locally. The
user approved an optional bounded `clarificationResponse` field, tied to the
retained thread/turn and previous clarification request; it is supplied separately
from screenshot evidence. Clarification still never commits. See
[Phase 3](SCREEN_CONTEXT_PHASE3.md) for the current runtime and validation;
the remainder records Phase 2's original completion state.

Focused three-intent revision: additive v1 request action `reference`, optional
`contextKind` defaulting to `question`, and strict `reference_accepted` evidence-only
outcome now support Passage / Data. Original images remain supplied; previous AI
answers remain separate. Reference continuation may answer a new question without
implicitly selecting the sole older answer. Legacy endpoints/callers are unchanged.
Current contracts, source limits, regression results and manual steps are in Phase 3.

## Endpoint and ownership

`POST /api/screen/analyze-context` is additive to the unchanged legacy
`/api/screen/analyze-active-window-answer` route. FastAPI's OpenAPI describes its
multipart body and typed response. The complete strict metadata models live in
`backend/app/models/screen_context.py`.

Electron main remains the temporary context owner. The backend has no conversation
store, screenshot cache, cross-request cancellation registry or history writes.
It validates structure and cloud authorization; it cannot independently establish
that client-supplied prior evidence really was committed to the claimed thread.
Phase 3 must serialize the controller's frozen snapshot, not renderer-authored
history, and use the controller's full currentness/revision checks before commit.

## Request contract, version 1

Multipart contains exactly one UTF-8 `context` JSON field and `image_0` through
`image_N`, in manifest order. Filenames are ignored, never opened as paths.
No client image URLs, provider file IDs, base64 fields or arbitrary metadata are
accepted. Extra fields are rejected. Example metadata shape:

```json
{
  "contractVersion": "1",
  "sourceType": "screen_capture",
  "identity": {
    "runtimeSessionId": "runtime-id",
    "generation": 1,
    "accountGeneration": null,
    "cloudSessionId": null,
    "threadId": "thread-id",
    "turnId": "turn-id",
    "operationId": "operation-id",
    "requestId": "attempt-id",
    "baseRevision": 0
  },
  "action": "new",
  "input": {
    "currentImageHash": "<sha256 of uploaded bytes>",
    "images": [{"imageHash": "<same sha256>", "role": "current", "part": "image_0"}],
    "evidence": [],
    "answers": []
  },
  "targetQuestionId": null,
  "priorItems": [],
  "replacesTurnIds": []
}
```

Identity names match Phase 1 exactly. IDs are bounded safe strings; generation and
revision are nonnegative safe integers. A cloud ID must be a UUID and have a
captured account generation. Identity metadata never grants authorization.

`input.evidence` retains Phase 1's `{text,complete,imageHash,turnId}` records;
`input.answers` retains `{text,turnId}` records. Code/whitespace inside text is
preserved. Arrays follow accepted-turn chronology. Each turn contributes one
evidence record, so baseRevision equals the evidence count in this uncompacted v1.

Manifest hashes/parts are unique. The order is first accepted use, followed by a
distinct new image. Exactly one hash is current. `prior_current` explicitly reuses
accepted identical bytes for a new logical turn without uploading duplicate bytes.
Every prior image must have accepted evidence, every answer must reference an
accepted turn, and upload bytes must match the declared SHA-256.

New requests have revision zero and no prior evidence, answers, items, replacement
references or continuation target. Continue requires accepted evidence. Optional
`priorItems` contains `{questionId,turnId,index}` bindings from successful answers;
IDs are application-generated as `turnId:index`. Unknown targets are rejected.
Several prior items without a target return a non-committable clarification,
without invoking the model. Without item bindings the model must clarify any
ambiguous batch reference rather than infer it from flattened answers.

`replacesTurnIds` is explicit caller-authorized replacement of supplied prior
source turns. It is not inferred from chronology or generated AI answers. Model
output must echo these references exactly; unapproved replacement is rejected.

## Response and controller compatibility

Responses echo validated `identity`, including null local identity fields, and
contain `outcome`, `committable`, `evidenceDelta`, `controllerResult`, formatted
`answer`, ordered `items`, `missingDetails`, `conflicts`, `clarification`, safe
`errorCode` and metrics. The model never generates operation/session/item identity.

| Outcome | Evidence eligible | Answer | Controller action in Phase 3 |
| --- | --- | --- | --- |
| answered | Yes; sufficient combined evidence | Required ordered items | `commitAnswer(identity, controllerResult)` |
| needs_more_content | Yes; readable incomplete source and specific missing details | None | `commitEvidence(identity, controllerResult)` |
| needs_clarification | No; evidenceDelta/controllerResult are null | None | Preserve accepted context; resolve ambiguity first |
| failed | No; safe failure code where applicable | None | Fail candidate; never commit |

Clarification never commits, as confirmed by the user for this phase.
`controllerResult` has only Phase 1's accepted keys: `validated:true`,
`evidence:{text,complete}` and, for answered outcomes, `answer`. Evidence-only
results omit the answer key entirely. Backend eligibility is only a proposal:
main must still check current session, thread, turn, attempt and base revision.

EvidenceDelta also contains supporting image hashes and replacement references.
Phase 3 must retain item/replacement sidecars with accepted turns if it uses them;
Phase 1 deliberately has no fields for these yet. No Phase 1 controller change or
runtime serialization was implemented here. It must never commit clarification
sidecars or put images/private evidence into broadcast UI metadata.

## Provider behavior

The existing ScreenVisionService exposes an async contextual method using the
same configured OpenAI Screen provider/model, image preparation and answer
formatter. No final-answer-model, audio, gRPC or Extension routing changes.
Application instructions are separate from untrusted screenshot/source content;
previous successful AI answers have their own fallible-generated-content section.
All retained diagram images are supplied. Independent questions remain separate,
ordered batch items; unrelated incomplete blocks are ignored. Relevant incomplete
fragments may accumulate. Uncertain conflicting code requires clarification;
only explicit replacement references authorize superseding prior source.

There is one normal-path logical SDK invocation, no extraction/answer loop and
no automatic fallback. This route alone uses `max_retries=0`, disallows HTTP
redirects, and counts HTTP attempts through its HTTPX request hook. Counters mean
local dispatch, not guaranteed server receipt or exactly-once provider execution.
Response status/refusal/size are checked before strict JSON/result validation.
Truncated, malformed, refused or inconsistent output cannot commit.

`store:false` is explicit. No provider conversation/previous-response reference is
used. This does not guarantee zero provider retention. Official references:
[image inputs](https://developers.openai.com/api/docs/guides/images-vision) and
[data controls](https://developers.openai.com/api/docs/guides/your-data).

## Authentication and resource limits

As confirmed by the user, requests without a cloud ID require a loopback peer.
Any supplied Authorization header is verified with the existing JWT utility;
invalid credentials never downgrade to local. Cloud requests require JWT identity
and the existing owner-scoped session loader, with an active, non-ended session.
No client user_id or resume/JD/transcript/Ask AI content is fetched into prompts.
Direct Screen routing remains independent of session answer-model bindings.
Proxy deployment must preserve trustworthy peer-IP handling; do not expose this
local branch through an untrusted loopback proxy.

Limits are deliberately separate from Phase 1's retained-payload budget:

| Resource | Bound |
| --- | --- |
| Images/files | 6 unique uploaded images; only explicit current reuse |
| Compressed image | 10 MiB each, 24 MiB aggregate |
| Entire multipart stream | 25 MiB including JSON/headers/overhead |
| Metadata | 256 KiB UTF-8; no arbitrary nested metadata |
| Prior evidence / answers / items | 32 / 32 / 20 records |
| Evidence, answer or code field | 24,000 characters; reject rather than truncate |
| Missing/conflict details | 20 each, 1,000 characters each |
| Decoded image | At most 2,200 per dimension and 2,200² pixels, one frame |
| Prepared base64 image content | 32 MiB aggregate |
| Model output | Configured Screen output tokens capped at 4,096; 64 KiB JSON text |
| Duration | 45 seconds overall; configured provider timeout capped at 30 seconds |
| Concurrent requests | 2 per worker, including parsing; excess returns 429 |

The 10 MiB ceiling is reused. The aggregate, collection, output, concurrency and
deadline bounds are provisional operational limits requiring live measurement.
The installed Starlette multipart parser is subclassed to bound stream/parts and
raise its in-memory spool threshold above the entire allowed body. It never rolls
screenshots to disk. All parsed files close on success, validation failure,
disconnect, timeout and cancellation. This relies on parser callbacks/internal
cleanup tracking and has a focused regression test for dependency upgrades.

Peak heap is larger than compressed bytes: parsing temporarily overlaps spool
and byte copies, prepared base64, SDK serialization and one decoded RGB image.
Two slots bound admission, not an exact RSS guarantee; profile worker memory before
raising limits or worker count. Pixel headers are checked before full decoding.
Cancellation checkpoints occur between image decodes; a single bounded PIL decode
is synchronous. Disconnect cancels async provider work and closes transport, but
cannot guarantee provider cancellation or prevent billing after submission.

## Baseline backend failure

Before Phase 2 edits this exact command failed:

```text
python -m pytest backend/tests/test_answer_streaming.py::test_generate_stream_primary_success_with_session_id_stores_transcript -q --tb=short
```

Error: `AttributeError: 'dict' object has no attribute 'status'` at
`backend/app/session_generation.py:234`, reached from `generate_answer_stream`.
The legacy test's `_session_record()` returns a dict; enabled session-model
dispatch expects a record object. A second subprocess running the same command
with only `ENABLE_SESSION_ANSWER_MODELS=false` passed. The actual dotenv and working
tree were not modified for either reproduction. This is a demonstrated pre-Phase-2,
configuration-sensitive baseline failure, not a conclusion based on untouched tests.
It has no demonstrated dependency on Screen continuity and was not repaired here.

## Deferred verification

Validation performed:

- 112 backend tests passed: 45 contextual tests plus legacy Screen provider,
  envelope/orchestrator and JWT utility regressions (5 existing SWIG warnings).
- 48 frontend/controller tests passed. Separate backend test cases perform both
  real-controller round trips for answered and evidence-only response payloads
  using Node, not a live Electron app.
- `scripts/pre_commit_audit.ps1 -SkipBackendTests` passed: whitespace/staged-file
  checks, backend compilation, frontend build, Electron syntax and 124 Extension
  tests. The full backend suite is not claimed green because of the baseline above.
- Graphify code updates and graph queries ran before and after implementation.

Exact focused backend command:

```text
python -m pytest backend/tests/test_screen_context.py backend/tests/test_screen_vision_openai.py backend/tests/test_screen_vision_openrouter.py backend/tests/test_screen_intelligence_contract.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_supabase_auth.py -q --tb=short
```

Exact frontend command:

```text
node --test frontend/src/screen_context_controller.test.js frontend/src/screen_operation_state.test.js frontend/src/analyze_screen_menu.test.js frontend/src/screen_intelligence_contract.test.js
```

Tests use synthetic images, real parsing/validation and mocked provider calls;
they prove contracts, construction, cleanup and isolation, not model reasoning.
Live provider availability, small-code/diagram fidelity after existing resizing,
latency/memory/cost, authenticated deployment and end-to-end Electron acceptance
remain unverified. Phase 3 owns UI/execution serialization, sidecar retention,
controller commits and lifecycle integration of the actual contextual request.
# Provider output-contract correction (2026-10-19)

The provider-only structured output now wraps the canonical outcome in a required `result` object, with action-specific nested `anyOf` branches that enforce evidence presence/completeness and empty/required fields per outcome. Reference storage permits `reference_accepted`; New/Continue permit `answered` and `needs_more_content`, including Continue with `contextKind=reference`. Semantic validation, source-reference checks and action guards remain. Backend request/response version 1 and the Electron/controller commit contracts are unchanged. See [the investigation](SCREEN_CONTEXT_MANUAL_FAILURE_INVESTIGATION.md) for predicates, diagnostics and retest steps.

## Contract audit amendment — 2026-10-19

The existing nested provider schema was verified, not presumed broken. Shared `OUTCOME_RULES` drive outcome validation/schema generation; additive v1 source provenance and accepted clarification fields preserve relationships on later requests. Decode work now runs off-loop with owned cancellation cleanup under the existing two-slot/45-second endpoint boundary. Safe provider timeout/rate/configuration classifications and schema fingerprints were added; limits/providers/auth are unchanged. See [audit and acceptance report](SCREEN_CONTEXT_CONTRACT_AUDIT.md) for tests and compatibility.
