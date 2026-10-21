# Answer quality Phase 6: saved-answer architecture diagrams

2026-10-21. Local implementation only. Generation remains disabled by default.
No hosted migration, activation, provider evaluation, recording or playback occurred.

## Baseline and preservation

Entry revision: `bff9827ab7ebbcfb560dcac5178a9391f530c5a9` (PR #53 merged).
Phases 1-4 are existing uncommitted dependencies, not changes introduced here.
The reviewed Phase 5 design is in the conversation; no Phase 5 repository record
exists. Current source and the approved Phase 6 contract governed implementation.
No applicable repository/ancestor AGENTS.md was found. Ponytail and read-only
Graphify were used; no graph regeneration occurred.

Entry staging was empty. The 30 pre-existing changed/untracked file hashes and
index-diff hash are recorded outside the repository in
`%TEMP%/saiia-diagram-phase6-before.json`. All 28 non-overlapping files retain their
entry bytes. The two intentional overlaps are `backend/app/api/generate.py`
(trusted unmanaged save stamping) and `frontend/electron/main.cjs` (main-only
bridge/lifecycle hooks); prior quality changes and the existing comment hunk
remain. Staging is unchanged. No environment file was inspected or edited.

Plan executed in order: 6A trusted identity; 6B durable storage; 6C provider/API;
6D Electron bridge; 6E main rendering/history; 6F integrated checks/record.
Each substep received focused verification before proceeding; later integration
checks also re-exercised earlier substeps.

## 6A - Trusted source identity

`interview_answer_sources` is server-owned, separate from arbitrary transcript
metadata. Its primary key references the persisted transcript; owner/session are
derived, with versioned canonical question/answer SHA-256, answer intent and
managed/server provenance. Generic transcript creation cannot stamp this table.

The additive `capture_managed_answer_source` trigger verifies completed durable
turn identity, same owner/session, exact stored canonical text and supported source
before using the existing trusted `result.answer_type`. The migration also admits
verifiable completed managed history using these same comparisons, without
keyword inference or trusting historical client metadata. Unknown history remains
ineligible. Canonical text/ownership changes invalidate the source and its diagram.

`_store_transcript_for_response()` stamps new unmanaged server saves through
`CloudInterviewTranscriptService.stamp_generated_answer()` and the existing
transcript client's authenticated connection. Replays are not newly stamped;
internal coordinated saves keep their existing owner. The RPC checks expected
canonical text and ownership. HTTP transport line endings/outer whitespace are
normalized exactly as in the existing transcript save. Missing migration/network
failure leaves the successful answer save successful and the source unavailable;
there is no second transcript save or dependency on diagram activation.

The descriptor resolver uses authenticated owner/session plus transcript ID or
generation request ID. It returns a narrow identity/eligibility projection, never
question/answer text, arbitrary metadata or a database fence. The UI independently
checks the displayed question/answer against the server revision (exact managed
text or the existing unmanaged transport normalization). This prevents an old
request-ID replay from attaching a canonical diagram to different local text.
Hash parity is executable in SQL/Node, including Unicode, escaping and newlines.

Eligible intent is exactly trusted `system_design`, with interview sources
`answer`, `auto` or `chat`. Screen is excluded. Dashboard Ask AI and AI Notes use
other storage/generation paths and do not acquire this provenance.

6A verification initially passed isolated SQL contracts and 71 Python tests.
Final focused verification includes the actual server-save helper, replay/internal
exclusion, unavailable-migration behavior and the existing transcript routes.

## 6B - Storage, coordination and deletion

`interview_answer_diagrams` is separate bounded storage, uniquely linked to the
source transcript. It stores derived owner/session, source revision, graph/prompt
schema 1, configured/actual model, state, attempt (1-2), operation UUID, private
token/90-second lease, validated checkpoint/final graph, safe failure code and
timestamps. No graph goes into transcript metadata.

`answer_diagram_operation` is service-role-only. Direct authenticated diagram
table access is denied; backend reads return a safe projection. Every operation
rechecks ownership, eligibility and source revision. Lock order matches Clear
Transcript: session advisory lock (existing seed 0), session row, transcript,
source, diagram. Locks are released before provider work.

State transitions:

- absent -> claimed processing -> validated checkpoint -> ready/insufficient_detail.
- Confirmed processing failure -> failed; one explicit retry may claim attempt 2.
- Ready replays without generation; checkpoint reads finalize persistence only.
- Lost write acknowledgements reconcile through durable reads.
- Expired processing without checkpoint -> fenced uncertain; no regeneration.
- Cancel before claim creates a tombstone, preventing an overtaken delayed claim.
- Cancel processing/checkpoint clears checkpoint and rotates the private token.
  Cancel after finalization preserves the saved result.
- Source deletion/revision invalidation cascades diagram/checkpoint removal.
  Returning workers cannot recreate missing parents or pass old fences.

There is no claim of exactly-once upstream execution across crashes. An ambiguous
claim/checkpoint can conservatively become uncertain instead of issuing another
provider request. Cancelled and insufficient-detail results are terminal; no
regeneration control was added for them.

Executable PGlite tests cover source/hash/ownership/RLS permissions, duplicate
claims, bounded retry, replay, stale workers, expired leases, checkpoint recovery,
cancel-before-claim/after-checkpoint/after-finalization, source changes, both ordered
deletion/finalization outcomes, actual Clear Transcript RPC and nonempty session/
account cascades. They load the existing baseline migrations and these two new
migrations, deliberately excluding the paused recovery-hardening replacement.

PGlite serializes this test database: these are deterministic transaction
interleavings and executable SQL permissions/FK checks, not simultaneous
multi-connection PostgreSQL contention or hosted Supabase acceptance.

## 6C - Provider, validation and API

Separate settings in `config.py`:

| Setting/bound | Value |
| --- | --- |
| DIAGRAM_GENERATION_ENABLED | false by default |
| DIAGRAM_MODEL | gpt-4.1-mini by default; matching dated snapshot configurable |
| Credential | Existing backend OPENAI_API_KEY only |
| Provider total deadline | 25 seconds |
| Output budget | 4096 tokens |
| Decoded response body | 128 KiB |
| Provider concurrency | Four operations per backend process |
| Source input | Existing stored question/answer bounds; no silent truncation |
| Graph | 20 nodes, 32 edges, 80-character labels, 240-character evidence quotes, 32 KiB |
| Layout | Separate local worker, 2-second startup/layout timeout, bounded geometry |

`generate_graph()` makes one HTTPX Responses request with strict JSON schema,
`store=false`, no tools/retrieval, no reasoning-specific options, no redirects,
SDK retries, fallback or repair. Refusal, incomplete response, timeout, malformed
JSON, oversized body and provider failure become content-free error codes.
Credentials, prompts, answers and provider messages are never logged by this
feature. Tests assert authorization values and interview content are absent from
captured diagnostics. No live request was made.

Official references checked:
[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini) and
[Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Account/model access and live structured-output acceptance remain unverified.
Mocked request-contract tests establish neither upstream acceptance nor rejection.
A later, separately authorized synthetic check on 2026-10-21 accepted the exact
schema for `gpt-4.1-mini-2025-04-14`, completed generation and passed local validation.
See the fingerprinted one-request record in `ANSWER_QUALITY_PHASE7.md`; this is
narrow compatibility evidence, not general live-feature acceptance or activation.

Graph v1 is flat JSON:
```json
{
  "status": "ready",
  "nodes": [{"id": "api", "label": "API", "kind": "service", "evidence_quote": "API"}],
  "edges": [{"source": "api", "target": "queue", "label": "tasks", "evidence_quote": "API sends tasks to Queue."}]
}
```
This illustrates fields, not a valid complete graph: ready requires at least two
unique nodes and one valid edge. Kinds: client/service/database/queue/cache/storage/
external. Insufficient detail uses status `insufficient_detail` and empty arrays.
Unknown fields, unsafe IDs, duplicate/dangling edges, unsupported kinds, markup/
resource labels and byte/string/array overflow are rejected. Cycles are allowed.
Every evidence quote must be an exact substring of the canonical answer. Quotes
remain server-side in storage and are omitted from the Electron graph projection.
Schema validity and substring evidence do not prove semantic faithfulness.

Authenticated API under `/api/interview-sessions`:

| Method/path | Input |
| --- | --- |
| GET /{session}/answer-sources | Exactly one transcript_id or request_id |
| GET /{session}/transcript-entries/{transcript}/diagram | source_revision |
| POST /{session}/transcript-entries/{transcript}/diagram | source_revision, operation_id |
| POST same path /retry | Same narrow body; existing confirmed failure required |
| POST same path /cancel | Same narrow body; no model or user fields |

Generation requests reject answer text, user identity, model overrides and extra
fields. Ready reads and checkpoint persistence recovery work with generation
disabled. `DiagramService` tracks/awaits workers, consumes exceptions, bounds
capacity and provides application-shutdown cancellation. HTTP detachment does
not cancel bounded original-answer work; explicit cancel fences durable work and
cancels a matching worker in this process. Cross-process cancellation fences
persistence even when the remote provider call must finish under its deadline.

## 6D - Electron boundary

`AnswerDiagrams` reuses `DesktopAuthSessionManager`, its fresh authorization,
captured auth-generation context and authenticated backend method. New IPC uses
`validateAuthIpc` (main window only), not the main-plus-overlay validator.
Input/result allowlists omit credentials, private tokens, raw errors and evidence
quotes. Source revision/session are checked again on receipt. Pending-operation
tracking is bounded; delayed old results cannot clear a newer retry's cancellation
record. No answer-streaming lock or audio state is acquired.

Logout, account/auth replacement and main-window closure invalidate delivery first
and request cancellation using the original token while available. Main-only
invalidation events clear pending UI work. Cancellation is best effort if the
network/process has already disappeared; backend deadlines/fences remain necessary.
Navigation/session end do not cancel original-source bounded work. There is no
diagram publication in overlay snapshots, AnswerPanel or OverlayWindow, and no
protobuf/generated-binding change.

The diagram-specific backend HTTP wait is 45 seconds; all other backend requests
retain their prior timeout. A lost client response does not authorize regeneration.

## 6E - Main rendering and history

`MainAnswerDisplay` is the production main-window answer card used by
`MainDiagnosticsWindow`. Its `DiagramSection` is separate from the overlay's
shared AnswerPanel. Completed HTTP/Auto/manual gRPC and answer Retry retain only
saved session/request references in existing local history. No graph is persisted
locally or saved as another transcript.

`DiagramSection` verifies the canonical descriptor before showing Generate.
It supports disabled/unavailable, generating/saving, ready, failed with backend-
approved Retry, uncertain/cancelled and insufficient-detail states. Polling is
read-only except backend checkpoint finalization, one pending timer, bounded to
100 polls; a lost response cannot trigger another provider call. Sources, UI
revision, async callbacks, polling and worker replies are fenced; cleanup
invalidates pending work. The written answer remains intact throughout.

The existing Electron past-sessions list gains View answers, with bounded,
paginated owned transcript retrieval and selection. A selected canonical answer
restores its saved diagram through the same descriptor/read path. No automatic
generation occurs on history opening. Unknown legacy provenance is unavailable.
Remote deletion has no new push subscription: reopening/reloading history or
another API operation rechecks storage. Durable deletion and late-worker fencing
do not depend on renderer notification.

Only `@dagrejs/dagre@3.1.1` and transitive `@dagrejs/graphlib@4.0.5` were added.
Dagre runs in a terminated-on-completion worker. Fixed React SVG rect/path/text/
tspan elements control styling, arrows and coordinates; no innerHTML, arbitrary
SVG, foreignObject, image, link or external resource is accepted. Top-to-bottom
layout uses readable fixed font size, bounded scrolling, accessible description
and component/relationship text alternative. No export/edit/zoom/fullscreen UI.

Playwright exercises this real main card, DiagramSection, DesktopAnswerHistory
and real worker in Chromium at 420px/620px widths, plus stalled-worker cleanup.
Screenshots `%TEMP%/saiia-diagram-420.png` and `saiia-diagram-620.png` were inspected.
These are synthetic component fixtures, not a full native Electron session,
packaged CSP test or a measured paint-latency result.

## 6F - Verification

All Python tests use the existing guarded offline runner: dotenv disabled before
startup, synthetic credentials, mocked providers/storage and outbound HTTP/DNS/TCP
blocked (localhost transport permitted). Node/browser tests use the loopback-only
preload and browser request allowlists. No microphone/STT/provider is started by
the diagram fixtures. Existing streaming suites cover all three synthetic audio
sources and actual localhost gRPC/Electron consumer boundaries.

Final broad backend command, from repository root:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_diagrams.py backend/tests/test_answer_quality_phase4.py backend/tests/test_answer_quality_phase3.py backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_baseline.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_answer_planner_problem1.py backend/tests/test_generate_selected_resume.py backend/tests/test_cloud_resume.py backend/tests/test_cloud_resume_routes.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py backend/tests/test_openai_answer_pipeline.py backend/tests/test_answer_generator_reliability.py backend/tests/test_coding_quality_gate.py backend/tests/test_coding_implementation_intent.py backend/tests/test_session_generation.py backend/tests/test_answer_stream_phase2.py backend/tests/test_answer_stream_phase3.py backend/tests/test_answer_stream_characterization.py backend/tests/test_answer_streaming.py backend/tests/test_grpc_answers.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_combined.py backend/tests/test_grpc_cloud_context.py backend/tests/test_grpc_manual.py backend/tests/test_grpc_realtime.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_screen_intelligence_contract.py backend/tests/test_interview_session_transcript_routes.py -q --tb=short
```

Result: **752 passed in 45.82 s**. After the final unmanaged line-ending stamping
compatibility adjustment, focused source/diagram/selected-resume/transcript tests
were rerun: **119 passed in 1.78 s**. Final diagram-specific suite: **42 tests**.

Other exact commands/results:

```powershell
# Repository root: executable isolated SQL, including new migrations
node backend/tests/answer_diagrams.postgres.mjs

# Repository root: final focused backend checks
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_diagrams.py backend/tests/test_generate_selected_resume.py backend/tests/test_interview_session_transcript_routes.py -q --tb=short

# frontend directory: unit/bridge/auth/Screen/manual/Auto/history regressions
node --require ./tests/fixtures/loopback_only.cjs --test src/*.test.js src/auth/*.test.js tests/answer_diagrams.test.cjs

# Repository root: Playwright/Chromium diagram and existing streaming DOM tests
node --require ./frontend/tests/fixtures/loopback_only.cjs --test --test-timeout=45000 frontend/tests/answer_diagrams.browser.test.mjs frontend/tests/answer_stream.browser.test.mjs frontend/tests/answer_stream_phase3.browser.test.mjs

# frontend directory
npm run build
npm ls @dagrejs/dagre @dagrejs/graphlib

# Repository root
node --check frontend/electron/main.cjs
node --check frontend/electron/preload.cjs
node --check frontend/electron/desktop_auth_session.cjs
node --check frontend/electron/answer_diagrams.cjs
git diff --check
git diff --cached --check
```

- SQL checks passed; permissions, hash parity, cascades and ordered races included.
- Frontend unit/bridge suite: **680 passed**, zero failures (2.56 s).
- Playwright/streaming suite: **13 passed**, zero failures (6.47 s).
  Seven diagram cases cover click-only generation, both widths, late/new-source
  and logout delivery, saved replay, mismatch exclusion and worker timeout.
- Build passed (3.81 s), with the existing large-main-chunk warning; no blanket
  bundle refactor was introduced.
- Dependency tree passed; protobuf files remain byte-identical.
- Eight changed/new Python files compile in memory, with no bytecode needed.
- Whitespace, Markdown fences, inventory/index and preservation checks passed.
- No human-rated quality, provider latency, native audio or hosted acceptance claim.

Development failures were investigated, not hidden: Python 3.10 required
`asyncio.wait_for` instead of `asyncio.timeout`; rendered tests initially had an
ANSI-corrupted arrow expectation, an incorrect select locator and an empty status
locator conflict. Cold development-worker startup informed the bounded 2-second
worker timeout. Broader checks exposed a configuration-cache interaction from
independent provenance-client initialization; stamping now reuses the existing
transcript client, with test caches isolated. Existing Screen cleanup order was
preserved after its regression caught hook placement. Initial SQL/fixture syntax
and a missing required request category were corrected. Final checks pass.

Read-only Graphify commands before/after changes:

```text
graphify query "session_generation transcript completion ownership deletion" --dfs --budget 1800
graphify query "interview_sessions transcript deletion main preload" --dfs --budget 450
```

Existing graph vocabulary includes the queried source nodes. The graph predates
this uncommitted feature and mostly navigates historical implementation; source
and executable checks establish current behavior. No artifact regeneration,
saved query memory or model-token extraction was performed.

## Changed-file inventory (35 files)

Backend:
- `backend/app/api/answer_diagrams.py`
- `backend/app/api/generate.py` (overlap preserved)
- `backend/app/cloud/answer_diagrams.py`
- `backend/app/cloud/interview_transcripts.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/services/answer_diagram_service.py`
- `backend/tests/answer_diagrams.postgres.mjs`
- `backend/tests/test_answer_diagrams.py`

Electron/frontend:
- `frontend/electron/answer_diagrams.cjs`
- `frontend/electron/desktop_auth_session.cjs`
- `frontend/electron/main.cjs` (overlap preserved)
- `frontend/electron/preload.cjs`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/App.jsx`
- `frontend/src/components/DesktopAnswerHistory.jsx`
- `frontend/src/components/DiagramSection.jsx`
- `frontend/src/components/DiagramSection.css`
- `frontend/src/components/MainAnswerDisplay.jsx`
- `frontend/src/components/MainDiagnosticsWindow.jsx`
- `frontend/src/components/StartupSessionChoiceScreen.jsx`
- `frontend/src/diagram_labels.js`
- `frontend/src/diagram_layout.js`
- `frontend/src/diagram_layout.worker.js`
- `frontend/src/diagram_layout.test.js`
- `frontend/src/diagram_source_revision.js`
- `frontend/src/grpc_manual_session.js`
- `frontend/tests/answer_diagrams.test.cjs`
- `frontend/tests/answer_diagrams.browser.test.mjs`
- `frontend/tests/fixtures/answer-diagrams.html`
- `frontend/tests/fixtures/answer-diagrams.jsx`

Storage/record:
- `supabase/migrations/20261021120000_add_answer_sources.sql`
- `supabase/migrations/20261021130000_add_answer_diagrams.sql`
- `docs/ANSWER_QUALITY_PHASE6.md`

## Rollout prerequisites and Phase 7 handoff

No migration is applied or feature activated by this phase. Before any later
approved rollout:

1. Review/verify existing transcript and generation-turn baseline migrations are
   deployed. Apply source migration `20261021120000` before diagram migration
   `20261021130000`, using the separately approved hosted process. Do not apply,
   copy or replace the paused `20261018210000` recovery-hardening RPC.
2. Verify service-role grants, owner reads, actual PostgreSQL multi-connection
   lock contention/deletion races and hosted PostgREST schema cache. These were
   not exercised against hosted infrastructure.
3. Deploy backend/desktop with generation still disabled. New backend against
   old schema keeps normal answer saves working but diagrams unavailable;
   old backend with additive migrations keeps existing answer behavior. Verify
   owned descriptor/history reads and verifiable managed-history coverage.
4. Separately approve GPT-4.1 mini account/model availability, synthetic live
   call/cost budget and semantic human review. Backend-only existing credentials
   must be configured without exposing values. Do not silently substitute models.
5. Only after approval, enable DIAGRAM_GENERATION_ENABLED in the backend process
   environment; DIAGRAM_MODEL remains independently configured. No real .env
   edit or process activation was performed here.
6. Run packaged/native Windows Electron acceptance (actual main dimensions,
   worker/CSP loading, cursor/scroll, auth/logout/window lifecycle), all three
   working audio modes alongside bounded diagrams, and saved-history/deletion
   checks. Browser fixtures are not native Electron acceptance.

Rollback is disabling generation while retaining saved reads/checkpoint
persistence recovery. Do not drop storage/provenance or alter answer-model
routing as a rollback. Existing answer-quality work remains uncommitted and must
be included/reviewed as a dependency before a focused future commit.

Phase 7 owns separately approved quality, budget, semantic-fidelity and live/native
acceptance. Substring evidence cannot establish component/relationship semantics;
a small mocked graph cannot prove readable layout for every permitted architecture.
Cancellation across process/network loss is best effort, uncertain work is not
regenerated, and no exactly-once upstream claim is made. No Phase 7 work started.

## Approved visual follow-up: colors and component symbols

The subsequent user-approved visual changes add fixed local colors and symbols:
blue person for client/user; teal rounded service box; purple cylinders for database
and storage; amber stacked messages for queue; amber chip for cache; blue cloud
for external system. A compact color legend supplements the existing text alternative.
SVG circle/ellipse/path/rect primitives remain locally controlled; the model supplies
only the existing validated kind. No schema, provider, persistence or overlay change.
Kind-specific bounded node padding reserves room for symbols and labels.

Verification: the guarded diagram Playwright suite plus layout/hash unit tests
passed **11 tests** (nine browser, two unit), including all seven kinds at both
420px and 620px widths. Symbol screenshots were visually inspected. The frontend
build passed in 4.01 seconds with the existing bundle-size warning; Graphify
read-only query and whitespace checks passed. Text contrast for all four node
fills exceeds 10:1. Changes remain unstaged/uncommitted; generation stays disabled.
