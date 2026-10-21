# Answer intent and presentation correction

2026-10-21. Local source/test correction after Phase 7; no live quality acceptance,
runtime activation, hosted record change, migration, staging or commit.

## Baseline and independent findings

Parent remains `bff9827ab7ebbcfb560dcac5178a9391f530c5a9`, `dev/current-work`.
Entry staging was empty. Phase 7's prepared A/B patches and verification record
remain historical and unchanged; all feature work remains uncommitted. New entry
hashes/index are retained in `%TEMP%/saiia-intent-presentation-_bq5ubsv/baseline.json`.
No AGENTS.md was found. Ponytail and read-only Graphify queries were used. Graph
coverage is contextual, not proof of current implementation; source/tests govern.

**Intent confirmed:** `answer_planner._base_answer_plan` matched topic substrings
(system design, architecture, URL shortener, notification service, chat system)
as architecture tasks. Before-change fixtures assigned all eight reported matrix
questions to system_design with tradeoffs/assumptions/flow/scaling coverage. Even
"Explain the system design of my project" forbade profile evidence. This establishes
a source-level bias toward the wrong task, not proof of which model produced the
reported millions-of-requests/storage/consistency claims. No recorded provider
output or screenshot artifact was supplied in this turn. The Groq footer cannot
distinguish selected, legacy or fallback routing.

**Presentation confirmed:** `MainAnswerDisplay` and `DesktopAnswerHistory` inserted
raw strings. `AnswerPanel` also displayed raw strings during reveal; its general
completed path used `answer_format.parseConceptualAnswer`, which groups simple
bullets but does not interpret emphasis or numbered lists. Its separate Screen
solution formatting/code controls are outside the changed path. A provider footer
exists in AnswerPanel, but that alone does not identify the screenshot's exact view.
Tests cover actual main, overlay and owned-history consumers rather than assuming.

**Compressed steps:** `AnswerGenerator._clean_answer` preserved the supplied
`**Main considerations**`, paragraph breaks and two numbered lines byte-for-byte.
Both main raw text and overlay parsing lacked semantic ordered lists; the main's
existing pre-wrap style would preserve actual supplied newlines. Thus newline
loss in the specific reported answer is unresolved: it may already have been in
provider output or another loaded version. No regex now manufactures breaks around
every number. Request policy tells providers to place list items on separate lines;
a one-line "1. ... 2. ..." remains one paragraph in the renderer.

**Running revision is not proven:** the observed Uvicorn/reload process started at
13:39 on 2026-10-21, after the planner's 00:49 source timestamp; the local main card
source was 01:07 and pre-task dist was 01:24. This makes current quality work possible,
not verified as loaded: module-only commands did not establish the running cwd or
screenshot provenance. No Electron/Vite process was identified in that snapshot.
No processes were restarted or real configuration inspected. The later build verifies
the current candidate compiles, not what the earlier manual run executed.

## Before/after task matrix

| Question | Before | Now |
| --- | --- | --- |
| Explain system design | system_design | technical_concept |
| What is system design? | system_design | technical_concept |
| How do you approach system design interviews? | system_design | technical_process |
| Explain the design of a URL shortener | system_design | system_design |
| Design a URL shortener | system_design | system_design |
| Explain caching in system design | system_design | technical_concept |
| Design a cache for a product catalog | system_design | system_design |
| Explain the system design of my project | system_design, profile forbidden | system_design, profile required |

Before/after synthetic policy inputs are retained in `before.json`/`after.json` in
the external evidence directory. They are not generated answer samples.

## Trace and minimal changes

HTTP manual/typed routes resolve follow-ups and build the plan in
`api/generate.py:generate_answer` / `generate_answer_stream`. gRPC Auto's
`grpc_answer_pipeline.stream_question_answer` delegates to the same generation
endpoint/coordinator for all audio sources. `session_generation.AttemptRun` caches
the prepared prompt across primary/fallback; it does not get a second intent policy.
`AnswerGenerator._build_interview_prompt`, `_answer_messages`, refinement and
`_semantic_correction_with_openai` consume the same request-local plan/evidence.
Canonical finalization, identity fences and one final-save owner are unchanged.

The planner now distinguishes task grammar (design/architect/redesign requests,
conditional design questions, explanation of a particular system's design) from
mere topic mentions. "Explain system design" receives technical_concept, direct
meaning/purpose/considerations and an optional illustrative example, with approved
100-200 word guidance. It no longer receives mandatory architecture coverage.
"Design a URL shortener" retains system_design, 220-400 guidance and labeled
assumptions rather than asserted scale/storage requirements. These are guidance,
not hard bounds or minimums. Personal project architecture requires evidence.
The old budget classification is deliberately retained: no token/deadline increases.
Screen-specific prompt contracts remain unchanged.

`followup_resolver` resolves "Now design one" against a concrete completed topic;
a method-only topic or missing reference stays a clarification. "Explain that
component" after a broad architecture also stays ambiguous; a specific component
anchor resolves to a narrow explanation. A newly requested full design is not
forced into narrow follow-up length guidance. Endpoint tests additionally exposed
standalone conditional design and grammatical "it" definition questions incorrectly
requesting clarification; the minimal grammar corrections preserve referential
"it/that" ambiguity. No model/retrieval call or new runtime clarification mechanism.

`AnswerText` is one small, local React Markdown subset: emphasis, paragraphs,
headings, ordered/unordered lists, inline code, fenced/indented code. Unmatched inline
markers remain text until complete; an unfinished fence renders safe code. Model
text never selects elements, styles or attributes. HTML/resources/links remain
inert visible text; no raw HTML, external fetch or new dependency. It replaces only
interview answer text in main/history and AnswerPanel's general/reveal paths.
Screen coding rendering, toolbar controls, cursor behavior, overlay background and
diagram exclusion remain unchanged. Authoritative text and storage are not rewritten.
Canonical completion replaces provisional content through existing state ownership.

Future trusted answer_type now keeps conceptual answers diagram-ineligible, while
actual saved architecture tasks remain eligible under existing ownership/provenance
checks (`DiagramStore.source`). No keyword backfill or reclassification of previously
saved trusted history was attempted. A historical answer misclassified by old code
may retain that old metadata; this patch does not silently alter hosted history.
Diagram generation remains disabled and migrations unapplied.

## Changed files and patch ownership

A (answer policy/presentation):
- `backend/app/nlp/answer_planner.py`
- `backend/app/nlp/followup_resolver.py`
- `backend/tests/test_answer_intent_presentation.py`
- `frontend/src/components/AnswerText.jsx`
- `frontend/src/components/AnswerText.css`
- `frontend/src/components/AnswerPanel.jsx`

B (existing main/history diagram integration and combined verification):
- `backend/tests/test_answer_diagrams.py`
- `frontend/src/components/MainAnswerDisplay.jsx`
- `frontend/src/components/DesktopAnswerHistory.jsx`
- `frontend/tests/answer_presentation.browser.test.mjs`
- `frontend/tests/fixtures/answer-presentation.html`
- `frontend/tests/fixtures/answer-presentation.jsx`
- `docs/ANSWER_INTENT_PRESENTATION_FIX.md`

The original Phase 7 patches do not contain this correction. Updated proposals
are retained separately in the new evidence directory: A then B, expected inventories
34 and 43 (76 unique files, one API overlap). Main/history depend on A's shared
AnswerText; combined browser fixtures depend on B's main/history components.
Do not cherry-pick only one renderer hunk. No historical 30/39-file claim was edited.
Stage-free replay and final results are recorded in the external verification ledger.
Updated patches are based on the same parent; both pass `git apply --check
--whitespace=error` and source comparison without staging. Temporary dependency
junctions reuse installed modules and extension fixtures use exact HEAD bytes,
matching Phase 7's Windows checkout normalization; no dependency was installed.

| Isolated scope/check | Actual result |
| --- | --- |
| A normal audit, no skip switches | 1473 backend passed, 2 skipped, 87 hook-filter deselections; build 3.82s, Electron syntax and 124 extension tests passed; exit 0 |
| A+B normal audit, no skip switches | 1517 backend passed, 2 skipped, 87 hook-filter deselections (77.28s); build 4.43s, Electron syntax and 124 extension tests passed; exit 0 |
| A final strengthened endpoint matrix | 31 passed (1.46s), including authoritative response answer_type |
| A+B frontend/Electron | 680 passed |
| A+B rendered integration | 25 passed; updated production-CSS/math/marker assertions also passed in the final two-test presentation run |
| A+B isolated diagram/source SQL | passed; paused migration excluded |

The full original-checkout run below includes all 87 tests excluded by the normal
hook filter. The normal audit's unchanged Python commands were wrapped in Phase 7's
temporary offline launcher before pytest imports, with explicit async plugins and
plugin autoload/cache disabled. It was run directly, not via an actual commit hook.
After the audits, only test assertions/fixture CSS and this record were finalized;
focused tests cover those changes. No production source changed after these audits.

## Verification

All application/provider tests run through `answer_quality_baseline.offline()`
before imports: synthetic credentials, dotenv disabled, fail-closed outbound HTTP,
mock storage/retrieval/provider boundaries. Browser network is loopback only.
No live-generated samples or human-quality ratings were created.

Commands from repository root (logs outside Git in the evidence directory):

```powershell
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_intent_presentation.py backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_phase3.py backend/tests/test_answer_quality_phase4.py backend/tests/test_answer_diagrams.py backend/tests/test_answer_planner_problem1.py backend/tests/test_live_followup_resolver.py backend/tests/test_followup_intent_compiler.py backend/tests/test_session_generation.py backend/tests/test_answer_quality_closeout.py -q --tb=short
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests -q --tb=short
$env:NODE_OPTIONS='--require "E:/saiia_project/saiia_project/frontend/tests/fixtures/loopback_only.cjs"'
$testFiles=@(rg --files frontend | Where-Object {$_ -match '\.test\.(cjs|js|mjs)$' -and $_ -notmatch '\.browser\.test\.' -and $_ -notmatch 'node_modules'})
node --test @testFiles
node --test frontend/tests/answer_presentation.browser.test.mjs frontend/tests/answer_stream_phase3.browser.test.mjs frontend/tests/answer_diagrams.browser.test.mjs frontend/tests/screen_context.browser.test.mjs
# From frontend:
npm run build
# From root:
node --check frontend/electron/main.cjs
node --check frontend/electron/preload.cjs
git diff --check
```

Initial focused set: 250 passed. Endpoint matrix expansion then had two confirmed
resolver failures/29 passes; both were fixed, not removed or skipped. Full guarded
backend: **1604 passed, 2 existing skipped (67.14s)**. Frontend unit/Electron: **680
passed**. Browser integration: **25 passed**, including real main/overlay/history
DOM formatting at 420/620 widths, partial emphasis/fences, canonical replacement,
malicious HTML/link inertness, actual streaming driver across Mic/Computer/Both,
diagram/lifecycle and Screen regressions. Build passed (3.93s), with existing large
chunk warning. The final two-test presentation rerun (5.87s) includes the real glass stylesheet,
inline-number/math/list assertions and valid-emphasis marker checks. Browser fixtures
abort external font/resource requests before network delivery; no hosted resource
is necessary for the checks. Isolated patch replays are recorded in the final ledger. DOM checks do not establish painted frames,
native Electron acceptance or better model prose. SQL migrations are unchanged.

## Manual retest still required

1. Confirm the backend and desktop frontend are launched from this reviewed checkout
   using the normal development/build workflow. Reopen the answer window so the
   loaded build is known; source timestamps alone are insufficient. Do not change
   credentials, flags or diagram activation for this retest.
2. Ask "Explain system design." Expect a direct definition/purpose/considerations,
   an explicitly illustrative example if helpful, and no assumed web-scale task.
   Check bold text, separate list items/paragraphs and readability in main/overlay.
3. Ask "Design a URL shortener." Expect requested architecture, labeled assumptions,
   flow/components/tradeoffs and useful depth. Do not infer fallback route from the
   footer alone. Capture safe route/turn metadata if later debugging requires it.
4. Try a concrete "Now design one" follow-up and an ambiguous "Explain that component";
   check narrow/contextual behavior and existing clarification. Reopen saved history
   and compare its canonical answer. Diagram controls remain unavailable for a generic
   conceptual answer and generation remains disabled.

These scenarios are pending user/native/live acceptance, not passes inferred from
mocked outputs. No claim is made that prompt instructions guarantee intent adherence
or prevent all factual invention.
