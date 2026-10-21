# Answer quality and diagrams: Phase 7 local closeout

2026-10-21. **Local implementation verification; human quality, native Windows,
live-model and hosted acceptance remain pending. Not ready for activation.**

## Baseline and preservation

Parent `bff9827ab7ebbcfb560dcac5178a9391f530c5a9`, branch `dev/current-work`.
The entry index was empty. Sixty-three changed/untracked files already existed;
Phases 1-4 and 6 were uncommitted dependencies. The Phase 5 design is the reviewed
conversation contract, not an invented historical implementation record.
Entry bytes, SHA-256 inventory and index digest are retained outside Git in
`%TEMP%/saiia-phase7-_p4b880m/entry` and `baseline.json`. No stash/reset/clean,
staging, commit, push, environment edit or hosted operation was performed.

Unrelated exclusions: `docs/C6_DESKTOP_STARTUP_UI_SESSION_SETUP_PLAN.md`,
`docs/G9_REALTIME_ROUTING_FALLBACK.md`, `docs/SESSION_ANSWER_MODELS_CLOSEOUT.md`,
and the pre-existing two-line content-protection comment in Electron main.
That comment remains in the original working file, excluded from proposed B.
The shared `backend/app/api/generate.py` file has separate quality and trusted-save
hunks; patch A includes the former and patch B adds the latter.

Graphify read-only queries were used before/after code work. Its existing graph
returned older Screen lifecycle context, not current answer-quality coverage;
current source/tests are the evidence. No graph regeneration occurred.

## Verified implementation and Phase 7 corrections

- `answer_planner.build_answer_plan` and generator request-local policy preserve
  explicit constraints, authorized evidence and question-specific guidance before
  optional style. Approved ranges remain guidance, not mandatory minimums.
- `answer_generator._clean_answer` preserves complete prose/code, alternatives and
  caveats. Required correction uses current-attempt policy/evidence; optional
  refinement failure does not justify accepting required validation failure.
  Similarity alone no longer initiates factual/coding rewrites.
- Resume index/cloud selection rejects no-match substitution, preserves selected
  resume authority and bounded relevant excerpts. Follow-up compiler/resolver
  retain code/constraints as conversation, never verified personal achievements.
  See Phase 4's synthetic before/after failures; these are not human quality scores.
- Diagram API/cloud/service use owned canonical transcript identity, versioned
  server hash, trusted source/provenance, durable claims/checkpoint/finalization,
  private fences and safe projections. Client metadata cannot stamp provenance.
  Disabled or unapplied diagram schema does not block normal answer saves.
- Main-only Electron bridge and `MainAnswerDisplay`/`DiagramSection` restore saved
  history, fence navigation/auth/source/operation results and keep answer/audio
  state independent. Overlay has no diagram payload/control/status publication.
- Dagre worker has a bounded deadline; fixed React SVG shapes/colors represent
  client, service, database, storage, queue, cache and external kinds. No model
  markup, style, coordinate or resource execution; text alternative is retained.

A full-run shutdown timeout was investigated rather than retried away. Python
3.10 `asyncio.wait_for` can return an inner result when cancellation races its
completion. `grpc_server.answer_worker` then re-entered `questions.get()` and
`stop_answers` hung awaiting that worker. A gated real-localhost regression failed
before the fix with DEADLINE_EXCEEDED, without sleeps or audio starvation.
`answers_stopping` is now set before cancellation and checked before another queue
wait. This does not set Stop on a turn-level GenerationStopped/error, extend source
timeouts, suppress EOF assertions or keep unhealthy capture alive. Existing typed
error/next-turn/replacement and actual Stop/disconnect/source tests remain active.
The new test plus all six neighboring transport cases passed five repetitions.

Other Phase 7 changes are test/evaluation work only:
`answer_quality_review.py` builds reproducible blinded paired packs, rejects missing
or unmatched baselines/settings/context and discloses authored fixtures.
The baseline harness isolates an existing provider cooldown on its capture instance;
it does not change global/production cooldown. GPT-parser tests explicitly disable
an otherwise unmocked fallback key in that test process. Full-run fail-closed network
guards exposed these two fixture-isolation defects; no provider error was swallowed.
The diagram capacity test now interleaves a production answer display queue and a
synthetic STT/control packet while all four provider jobs are gated.
The rendered stream fixture now uses the actual main answer card, not overlay's
shared AnswerPanel. A 20,500-character test proves two incoming prefixes before
completion and canonical replacement in main and overlay.

## Budgets and local measurements

**No token, timeout, queue, storage or concurrency budget changed.** Mocked prompt
exports at the parent and candidate each contain 24 cases, 20 effective prompts
and four early clarifications. They capture production prompts, not model outputs.

| Boundary | Existing requested bound / observation |
| --- | --- |
| OpenAI initial | standard/personal 2500, coding 6000, system-design 5000 output tokens |
| Selected catalog | prepared policy budget clamped through each adapter/catalog output limit; no fixed-model policy |
| Legacy Groq | ordinary 420 (demo 280), conceptual 520, personal 560; coding default 1600, cap 2000 |
| Coordinated attempt | first text 6s, idle 4s, overall 25s, fallback reserve 8s |
| Corrections | OpenAI validation 900/15s; correction prepared budget/20s, bounded by shared selected-attempt deadline |
| Optional Groq refinement | 160-320 tokens / 2.5s, conditional, no new unconditional call |
| Answer transport/storage | queue 32; selected accumulation 262144 chars; transcript question 4000 / answer 24000 chars; oversized final rejected, not silently truncated |
| Diagram | 25s, 4096 output tokens, 128 KiB response, 32 KiB graph; 20 nodes/32 edges, 80-char labels/240-char evidence quotes; four local active jobs, lease 90s |
| Layout | 2s worker deadline; local fixed rendering, bounded scroll |

The synthetic long-answer run produced three pre-completion snapshots, maximum
22,900 serialized bytes. Node serialization took 0.105ms locally; browser
state-to-DOM intervals were 28.4/28.2/7.6/3.8ms in that run. These are same-process
local intervals, not cross-clock subtraction, painted frames, provider latency or
production SLOs. Tests assert ordering and bounded termination, not those values.
The queue-one 23,000-character fixture confirms backpressure and cancellation.
Existing shared-deadline/correction/fallback tests use mocked pacing.

Legacy coding output and optional short refinement may need live calibration for
complex approved tasks. Synthetic tests do not demonstrate provider truncation or
justify raising every limit. The full application scheduler/STT under sustained
native load and arbitrary maximum graphs remain acceptance work; four gated jobs
plus an interleaved packet is not a throughput benchmark.

## Commands, isolation and results

All Python tests start through the fail-closed `offline()` harness before imports:
synthetic credentials, dotenv disabled, HTTP only mock/ASGI transports, loopback
only, no real retrieval/storage. Node inherits the existing loopback-only guard.
Normal audit scripts are unchanged, invoked without skip switches. A temporary
`python.cmd` launcher wraps their pytest/compileall commands in the same offline
guard, with explicit pytest_asyncio/anyio plugins, plugin autoload/cache disabled.
No real .env/runtime flag was changed. Raw output stays outside the repository.

Commands (PowerShell; `$art` denotes the external evidence directory above):

```powershell
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --output $art/candidate-prompts.json
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_closeout.py backend/tests/test_session_generation.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_combined.py backend/tests/test_grpc_realtime.py -q --tb=short
# Repeat the new shutdown regression plus the six parameterized real-gRPC cases five times.
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests -q -k 'openai or openrouter' --tb=short
# In isolated A and applied A+B, PATH prepends $art/hook-python, NODE_OPTIONS is loopback guard:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/pre_commit_audit.ps1
$testFiles = @(rg --files frontend | Where-Object {$_ -match '\.test\.(cjs|js|mjs)$' -and $_ -notmatch '\.browser\.test\.' -and $_ -notmatch 'node_modules'})
node --test @testFiles
node --test frontend/tests/answer_diagrams.browser.test.mjs frontend/tests/answer_stream.browser.test.mjs frontend/tests/answer_stream_phase3.browser.test.mjs
node backend/tests/answer_diagrams.postgres.mjs
node backend/tests/transcript_deletion.postgres.mjs
node backend/tests/session_generation.postgres.mjs
git diff --check
```

| Verification | Actual result |
| --- | --- |
| A-only normal repository audit | 1442 backend passed, 2 skipped, 87 deselected; build, Electron syntax, whitespace and 124 extension tests passed |
| Applied A+B normal repository audit | 1484 backend passed, 2 skipped, 87 deselected (68.97s); production build 3.90s; Electron syntax and 124 extension tests passed; audit exit 0 |
| Hook-excluded OpenAI/OpenRouter tests, guarded separately | 87 passed, 1486 deselected (4.29s) |
| Focused closeout + session/gRPC suites | 101 passed (17.84s) |
| Shutdown race + six real-gRPC contract cases | five separate repetitions, 7 passed each; 35 total case executions |
| Frontend/Electron/layout unit regressions | 680 passed |
| Rendered Playwright suites | 16 passed in original checkout and final isolated series (10.58s); cold-cache failure diagnosed and corrected as described below |
| Isolated SQL | diagram/source, transcript deletion and generation scripts all passed |
| Static/preservation | Python AST, Markdown fences, scoped secret patterns (68 files, no findings), tracked proto mirror parity, whitespace and original index/unrelated hashes checked |

The audit's 87 deselections are an existing hook filter, not unrun tests: they
passed separately. The two normal skipped tests remain skips, not claimed passes.
Build retains its existing >500 kB chunk warning. No production latency promise
or provider quality score is inferred.

The first isolated browser replay had 15 passes/one failure: Vite discovered the
worker's Dagre dependency on first use, reoptimized and reloaded the page. A fresh
cache reproduction recorded two navigations, dependency-reload=true and no ready
result with exactly one fake call. Predeclaring Dagre in the browser fixture's
optimizeDeps produced one initial navigation, no dependency reload and a ready
result. The test now asserts zero further main-frame navigations during generation.
A parallel isolated replay also exposed interference from sharing optimized caches
between differently configured Vite fixture servers through dependency junctions.
The diagram suite now uses its own temporary cache as well as predeclaring Dagre;
all 16 concurrent browser tests then passed. The new assertion checks no navigation
after the initial load. These are test-server changes, not production timeout/retry
policy. The temporary cache is outside Git. Final replay results are recorded in
the external verification ledger. Earlier failed audit runs
are retained: two offline fixture-boundary leaks, Windows checkout CRLF assumptions
in extension fixture exact-text tests, and the real gRPC cancellation race above.
Disposable worktrees restore extension fixture bytes from exact HEAD blobs, without
editing extension production/tests or changing original files. No failure was
hidden through broad retry or weaker production limits.

## Blinded quality evaluation: prepared, not run

`answer_quality_review.py --baseline before.json --candidate after.json --seed
20261021 --output review-pack` produces separate reviewer/key files. The input
schema is executable in `test_answer_quality_closeout.py`: revision, sample_origin,
case_id, answer, model, profile, settings, input_sha256, attempt_role, sample_index.
Compute the input digest with `input_hash(case)` from the full synthetic case.
Use provider_generated only for actual captured outputs. Baseline revision is the
parent above; identify the candidate by the reviewed A/B patch hashes until commits
exist. Do not label a prompt export or reconstructed authored answer a historical
measured baseline. Run the parent and candidate with the same synthetic evidence,
model/profile, settings and initial conditions. Pair primary and explicitly gated
fallback samples separately; preserve refusals/errors in a separate outcome ledger rather than selecting only
successful answers or manufacturing text for missing-output review pairs.

Use Phase 1's anchored 1-5 rubric for correctness, relevance, clarity, useful depth,
specificity, naturalness, structure, grounding and repetition. Two independent
reviewers score blinded randomized A/B, read aloud where useful, then reconcile
critical failures and report by question type. Fabricated positive/negative personal
history and materially wrong code/facts block acceptance. Automated code checks and
prompt/evidence tests supplement, never replace, review. Preference thresholds are
provisional: require zero critical failures and propose a majority preference with
no type-specific regression; obtain approval before using a numeric release gate.
Latency needs an actual provider baseline and separate first-text/final measurements.

A later approval can authorize a bounded pilot: six representative synthetic
questions on two versions (12 logical answer turns), at most 36 actual answer
provider calls including conditional validation/correction/fallback, plus four
candidate diagram calls (40 total upstream-call ceiling). Stop on the call ceiling,
a critical failure or the separately approved monetary cap; do not run until a
model/profile, dollar ceiling and account authorization are approved. Expand to all
24 cases only after pilot review. No live samples, ratings or paid calls exist from
this phase. An LLM judge alone cannot accept naturalness or grounding.

Diagram review must check canonical-answer hash/association, every component and
relationship/direction, labels/data flow, unsupported extra infrastructure, omitted
critical dependencies, understandable cycles, readable symbols/labels, and correct
insufficient_detail behavior. Substring evidence validation does not establish
semantic faithfulness.

## Rollout and rollback gates

Prepared migrations, in order:
1. `20261021120000_add_answer_sources.sql`.
2. `20261021130000_add_answer_diagrams.sql`.

Existing transcript lifecycle/storage/deletion and generation-turn/model-binding
baselines are prerequisites, as exercised by the isolated SQL script. The new
source/diagram SQL test does not load the separately paused
`20261018210000_harden_session_generation_recovery.sql`. The older generation SQL
regression uses its own in-memory migration setup; that is not hosted application
or a new diagram dependency. PGlite executes SQL/roles/fences/cascade and serialized
interleavings; it does not prove real multi-connection PostgreSQL lock contention.

Deploy reviewed backend/desktop with generation disabled; additive schema rollout
needs separate approval. Missing new schema leaves diagram unavailable and normal
answer saves usable; source-only and source+diagram combinations are covered by SQL.
Saved diagram reads remain available when generation is disabled. Unknown legacy
provenance remains ineligible, with no keyword backfill. Managed verified history
can resolve; unmanaged stamps use the trusted server-save path. No client answer
text/user/model substitution is accepted.

Navigation/session end may allow bounded work on its original source. Logout/window
close requests cancellation and invalidates UI. Source deletion plus locks/FK/fences
prevents a late worker from resurrecting it. Cancellation over process/network loss
is best effort; expired unknown execution becomes uncertain, never auto-regenerated.
No exactly-once upstream execution is promised. One explicit retry follows confirmed
failure; saved replay and checkpoint recovery use zero new generation calls.

Rollback disables new generation while retaining saved reads, canonical provenance,
source/diagram rows and answer model bindings. Do not drop additive schema or apply
the paused recovery replacement as rollback. Account/model availability, PostgREST
schema cache, actual PostgreSQL locks/privileges and hosted deletion must be checked
under separately authorized rollout.

Manual acceptance remains **pending**: representative HR/behavioral/technical/code/
project/follow-up answers and personal vs hypothetical claims; main+overlay streaming
in Mic/Computer/Both; eligible durable completion before diagram button; semantic
agreement; saved-history replay without generation; failures/Retry/uncertain recovery;
navigation/logout/deletion; diagrams disabled/failing while answers stay usable;
packaged Windows worker/CSP/layout/cursor/scroll at actual dimensions. Browser DOM
checks are not native Electron or paint evidence. Prior streaming/audio acceptance
does not accept these quality/diagram changes.

Next separate approvals: review focused patches; approve hosted migration only after
real PostgreSQL checks; approve bounded synthetic live evaluation/cost cap; accept
human/native results; then approve generation activation. None is implied here.

## Proposed focused patch inventory

Order A then B. The shared API file is intentionally split by hunk; no source file
is omitted to reduce scope. B's integrated verification uses A's offline tools and
policy/context tests. This is a dependency of the reviewed patch series, not a claim
that diagram layout intrinsically requires different answer prose. No new unrelated
work, environment, logs, screenshots or tooling artifacts belong in either patch.

Suggested A: `feat: unify grounded interview answer policy and context` (includes
verified gRPC Stop reliability correction and offline evaluation tooling).
Suggested B: `feat: add opt-in saved-answer architecture diagrams` (includes additive
migrations, main-only visuals/history and this integration record).

A: 30 files.

- `backend/app/api/generate.py`
- `backend/app/cloud/cloud_resume.py`
- `backend/app/grpc_answer_pipeline.py`
- `backend/app/grpc_server.py`
- `backend/app/nlp/answer_generator.py`
- `backend/app/nlp/answer_planner.py`
- `backend/app/nlp/answer_variation.py`
- `backend/app/nlp/followup_intent_compiler.py`
- `backend/app/nlp/followup_resolver.py`
- `backend/app/services/resume_index_service.py`
- `backend/app/session_generation.py`
- `backend/scripts/answer_quality_baseline.py`
- `backend/scripts/answer_quality_review.py`
- `backend/tests/answer_quality_spec.py`
- `backend/tests/test_answer_generator_reliability.py`
- `backend/tests/test_answer_quality_baseline.py`
- `backend/tests/test_answer_quality_closeout.py`
- `backend/tests/test_answer_quality_phase2.py`
- `backend/tests/test_answer_quality_phase3.py`
- `backend/tests/test_answer_quality_phase4.py`
- `backend/tests/test_answer_variation_problem2.py`
- `backend/tests/test_coding_implementation_intent.py`
- `backend/tests/test_generate_selected_resume.py`
- `backend/tests/test_non_coding_answer_quality.py`
- `backend/tests/test_openai_answer_pipeline.py`
- `backend/tests/test_resume_gpt_parser_service.py`
- `docs/ANSWER_QUALITY_PHASE1.md`
- `docs/ANSWER_QUALITY_PHASE2.md`
- `docs/ANSWER_QUALITY_PHASE3.md`
- `docs/ANSWER_QUALITY_PHASE4.md`

B: 39 files; API file overlaps A.

- `SAIIA_PRODUCTION_PHASES_TRACKER.md`
- `backend/app/api/answer_diagrams.py`
- `backend/app/api/generate.py`
- `backend/app/cloud/answer_diagrams.py`
- `backend/app/cloud/interview_transcripts.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/services/answer_diagram_service.py`
- `backend/tests/answer_diagrams.postgres.mjs`
- `backend/tests/test_answer_diagrams.py`
- `docs/ANSWER_QUALITY_PHASE6.md`
- `docs/ANSWER_QUALITY_PHASE7.md`
- `frontend/electron/answer_diagrams.cjs`
- `frontend/electron/desktop_auth_session.cjs`
- `frontend/electron/main.cjs`
- `frontend/electron/preload.cjs`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/App.jsx`
- `frontend/src/components/DesktopAnswerHistory.jsx`
- `frontend/src/components/DiagramSection.css`
- `frontend/src/components/DiagramSection.jsx`
- `frontend/src/components/MainAnswerDisplay.jsx`
- `frontend/src/components/MainDiagnosticsWindow.jsx`
- `frontend/src/components/StartupSessionChoiceScreen.jsx`
- `frontend/src/diagram_labels.js`
- `frontend/src/diagram_layout.js`
- `frontend/src/diagram_layout.test.js`
- `frontend/src/diagram_layout.worker.js`
- `frontend/src/diagram_source_revision.js`
- `frontend/src/grpc_manual_session.js`
- `frontend/tests/answer_diagrams.browser.test.mjs`
- `frontend/tests/answer_diagrams.test.cjs`
- `frontend/tests/answer_stream_phase3.browser.test.mjs`
- `frontend/tests/fixtures/answer-diagrams.html`
- `frontend/tests/fixtures/answer-diagrams.jsx`
- `frontend/tests/fixtures/answer-stream.jsx`
- `supabase/migrations/20261021120000_add_answer_sources.sql`
- `supabase/migrations/20261021130000_add_answer_diagrams.sql`

## Phase 7 edits and isolated series

Phase 7 specifically changes: gRPC Stop fence; offline cooldown isolation;
new review-pack script/closeout tests; resume-parser test boundary;
diagram-capacity interleaving; actual main-window streaming fixture/long-answer
test; cold-Dagre/private-cache browser setup/navigation assertion; Phase 6 trailing-blank-line
cleanup only; this record and one appended current tracker section. Historical
commands/results in Phases 1-6 were not rewritten.

Stage-free review artifacts live in `%TEMP%/saiia-phase7-_p4b880m`:
`A-answer-quality.patch`, `B-answer-diagrams.patch`, `manifest.json` and the final
`verification.json` SHA-256/results ledger. A contains 30 files, B contains 39,
with one API overlap: 68 unique files. A-only `quality` and applied-series
`patch-verified`/`final-series` worktrees are detached at the parent. Dependency
junctions reuse already-installed Node modules; no installation occurred.
The older transcript-deletion SQL fixture imports from its historical
`tmp/transcript-delete-db/node_modules` path; a matching disposable-worktree
junction was necessary and added before its successful final run. An initial
missing-module setup failure was not a SQL/migration defect.

Both patches are generated from HEAD to the scoped A tree and A to scoped B,
checked/applied with `git apply --check`/`git apply`, without staging. Every scoped
file is compared with the proposal. An accidental temporary directory from a failed
patch preparation is outside the repository and is not a reviewed patch/worktree.
The final ledger identifies the byte-exact patches; do not infer a commit hash from
a patch checksum. No commits were created and no actual commit hook was triggered;
the normal hook's unchanged repository audit was executed directly without skips.
