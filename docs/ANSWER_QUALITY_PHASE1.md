# Answer quality Phase 1: synthetic baseline and policy specification

2026-10-20. Phase 1 only. No production behavior or diagram feature is implemented.

## Baseline and preservation

Revision: `cec0cf9e7fd712769a702c7a90235e560757eafa`, `dev/current-work`.
The preceding read-only answer-quality audit was supplied in the conversation,
not a repository document. Its findings were rechecked against current source.
PR #49 microphone, PR #50 Computer/combined (`5368914`) and PR #52 answer
streaming (`e87d39c`) are merged ancestors; local HEAD additionally includes
`6015770` legacy-routing test isolation and the contextual Screen workflow.

No applicable ancestor/repository AGENTS.md was found. Ponytail favors the
existing endpoint, planner and provider helpers; no dependencies were added.

Pre-existing staged files:

- `docs/C6_DESKTOP_STARTUP_UI_SESSION_SETUP_PLAN.md`
- `docs/G9_REALTIME_ROUTING_FALLBACK.md`
- `docs/SESSION_ANSWER_MODELS_CLOSEOUT.md`

Pre-existing unstaged file: `frontend/electron/main.cjs` (two comment lines).
An external `%TEMP%/saiia-quality-phase1-baseline.json` records revision, status,
index-diff hash and these four file hashes. No environment file was read for
that baseline. Those bytes and staging are preserved; all Phase 1 files are new
and unstaged. No source, runtime settings, hosted data or migration was changed.

Graphify read-only queries ran before and after work. Existing graph vocabulary
includes answer/generator/planner/followup; broad matches mainly reached historical
records. Current source is authoritative. No artifacts were regenerated or query
results saved; no provider token usage occurred.

## Deliverables and boundaries

- `backend/tests/answer_quality_spec.py`: 24 authored synthetic cases and the
  executable `approved_policy()` specification, not a production classifier.
- `backend/scripts/answer_quality_baseline.py`: offline capture/export and guarded
  pytest entry point. There is deliberately no live-provider mode.
- `backend/tests/test_answer_quality_baseline.py`: current-behavior characterization,
  desired-spec integrity, context isolation, adapter and safety regressions.
- This phase record and review rubric.

`capture()` runs the real buffered `generate_answer()` endpoint, real follow-up
resolution, planner, context-permission filtering, selected-resume profile building,
prompt construction and ordinary postprocessing. Retrieval returns synthetic data
only when production requests it. The primary provider boundary supplies an
authored double; semantic judgment is mocked, not evaluated. Actual legacy
`_generate_with_openai()`/`_generate_with_groq()` helpers capture requested budgets
at mocked provider boundaries. `_request()` also captures effective output caps
for the synthetic process catalog, omitting headers/credentials. Captures include full synthetic system/user
instructions, full planner inputs/fields, requested budgets, context-load decisions,
approved policy and final double. They exclude application timing values.

Ambiguous follow-ups may return a deterministic clarification with no provider
prompt. That outcome is captured explicitly. A primary/fallback facade regression
exercises `AttemptRun.primary()` with shared prepared input and verifies raw text
preservation. It does not simulate a failed primary or prove end-to-end fallback
quality, streaming, transport, persistence or authorization. Adapter tests cover
every supported API profile, without enumerating current model identities.

Mocks are installed before application/pytest startup by the documented runner:
dotenv loading is disabled, inherited configuration is replaced with a minimal
synthetic environment, credentials are synthetic, STT/session-model execution is
disabled in that test process, and HTTP/DNS/external socket access fails closed.
Windows asyncio's loopback wakeup socket is permitted; HTTP is blocked even on
loopback. Provider methods, cloud retrieval/storage and refinement fail unless
explicitly doubled. Local resume-index/JD loaders return empty synthetic defaults;
they never read developer documents. Coding-contract LLM extraction returns no
LLM contract. No FastAPI server, STT adapter or capture device is started.

Scoped patches also protect collection in a process where config is already
imported: credentials are synthetic, session-model execution/refinement/variation
rewrite are disabled and restored on exit. Capture history is fresh per case.
These controlled baselines are not the developer's deployed configuration and do
not characterize repeated-history variation calls or semantic-model judgments.

## Case inventory and approved precedence

Each expanded case contains question, profile/snippets/JD/history, expected intent,
explicit constraints, permitted personal facts, prohibited inferences, essential
content, useful/unnecessary examples, critical failures and human review criteria.
Depth is resolved by `approved_policy()` from the explicit evaluation intent,
independently of the production plan, so disagreements remain visible.

| Cases | Coverage |
| --- | --- |
| introduction, motivation | Supported introduction, role fit without company invention |
| behavioral_verified, behavioral_missing | One evidenced incident versus missing history/hypothetical |
| concept_cache, simple_fact | Mechanism/detail versus a direct short factual answer |
| comparison_auth, comparison_storage | Correct distinctions and contextual tradeoffs |
| coding_dedupe, coding_repeat, debugging | Complete code, preserved semantics, concrete bug |
| design_notifications, fallback_long | Broad design, long explanation, fallback review requirements |
| project_contribution, project_walkthrough | Ownership boundaries and sparse broad-project evidence |
| followup_narrow, followup_ambiguous | Bounded continuation versus unresolved reference |
| personal_missing, selected_conflict | No invented incident; selected-resume authority over stale profile |
| jd_only, retrieval_irrelevant | JD is not experience; irrelevant snippets must not steer answer |
| fact_repeat, explicit_short, explicit_detailed | Stable correctness and explicit depth/format overrides |

Priority: correctness/grounding; explicit question constraints; existing user length
preference if available; type-specific guidance; stylistic variation. An explicit
request cannot authorize invented facts. Word ranges are not mandatory minimums
or enforced ceilings. Code is excluded from prose counts. Detailed requests can
exceed guidance; simple answers can be shorter. No length control is added to UI.

| Evaluation intent | Approved suggested prose words |
| --- | --- |
| HR/motivation; introduction | 90-160; 100-170 |
| Behavioral | 150-230 |
| Concept; simple fact | 100-200; 20-70 |
| Comparison | 140-230 |
| Coding/debugging | Complete code plus approximately 100-220 explanation words |
| Broad system design | 220-400 |
| Resume/project; broad walkthrough | 140-240; 200-320 |
| Narrow follow-up | 30-110 unless the requested task needs more |

Missing evidence permits an explicitly hypothetical approach, not an invented
positive or negative personal history. No new runtime clarification behavior is
activated. No STAR labels, headings, examples or paragraph count are universal.

## Confirmed current constraints (known limitations, not desired contracts)

- `AnswerGenerator._build_prompt()` around lines 3024-3033 makes examples both
  optional and mandatory; current conceptual target remains 100-160 words.
- Selected-resume project instructions around lines 2996-3012 request extensive
  coverage/paragraphs/bullets while later rules constrain structure and length.
- `AnswerPlan` declares `maximum_words`, `minimum_detail`, `preferred_structure`
  and `example_policy`, but changing them does not change the effective prompt.
  Their usage remains confined to planner construction; tests prove prompt parity.
- `_clean_answer()` / `_truncate_words()` truncate ordinary prose to the configured
  cap (source default 160), but preserve code and recognized conceptual layouts.
  `AttemptRun.primary()` returns raw text instead of that legacy cleaner.
- Alternative trimming at `_clean_answer()` lines 3447-3452 is punctuation-sensitive:
  a newline followed by `Alternatively:` or `Alternatively ` removes the remaining
  section. `Alternatively,` survives. The earlier audit's broad description is
  refined here; no global trimming behavior was changed.
- `_build_personal_prompt()` permits creative low-risk details. Endpoint personal
  validation can call `repair_personal_answer_if_needed()` and install a canned
  first-person story. Selected-resume strict mode skips this repair. The isolated
  regression directly demonstrates unsupported childhood-story substitution.
- The actual endpoint resolves four cases to clarification before generation:
  `motivation`, `debugging`, `jd_only`, and the intentionally ambiguous follow-up.
  The first three have expected standalone intents in the approved specification;
  this is an additional resolver gap, not a reason to manufacture a provider prompt
  or change production in Phase 1. Review `_has_clear_subject()` /
  `_looks_like_followup()` in `followup_resolver.py` in the later intent phase.

References: `backend/app/nlp/answer_generator.py` (`_build_prompt`, `_answer_messages`,
`_clean_answer`, `_build_personal_prompt`, `repair_personal_answer_if_needed`),
`backend/app/nlp/answer_planner.py`, `backend/app/api/generate.py`
(`generate_answer`, `_generation_profile`, `_apply_personal_validation`),
`backend/app/session_generation.py` (`AttemptRun.primary`), and
`backend/app/answer_generation.py` (`_request`). Production files are unchanged.

## Anchored human-review rubric

Score applicable dimensions separately; use N/A with a reason when inappropriate.
Do not average away a critical failure. Fabricated personal claims (including
unsupported denials) and materially wrong facts/code fail the case regardless of
fluency. Automated tests cannot reliably establish complete grounding or naturalness.

| Dimension | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| Correctness | Materially wrong | Significant omissions/errors | Core correct, caveats missing | Correct with minor omission | Correct, complete for task and appropriately qualified |
| Relevance | Wrong question | Mostly tangential | Answers core, some detours | Focused, minor excess | Exact request and constraints, no detours |
| Clarity | Incoherent | Hard to follow | Understandable with effort | Clear sequence | Precise explanation with effortless transitions |
| Useful depth | No explanation | Superficial assertions | Adequate essentials | Reasons/mechanisms well explained | All needed substance, no padding |
| Specificity | Empty slogans | Vague examples | Some concrete detail | Relevant concrete detail | Precise mechanisms/evidence/examples without unsupported detail |
| Naturalness | Unusable aloud | Canned/stilted | Speakable with edits | Natural with minor awkwardness | Direct, varied, comfortable spoken delivery without filler |
| Structure | Disorganized | Forced or confusing template | Reasonable organization | Well matched to task | Each part helps; no unnecessary labels/sections |
| Grounding | Invented history | Several unsupported implications | Evidence boundaries unclear | Supported with minor ambiguity | Every personal claim supported; general/hypothetical examples explicit |
| Repetition | Repeats most content | Substantial redundancy | Some repetition | Little redundancy | Each sentence adds value; stable facts on repeated questions |

Objective checks: code/sample correctness where applicable, finish reasons,
complete code blocks, explicit format constraints, provider-call counts and
transport/persistence invariants. Word ranges are descriptive, not pass/fail
minimums. Human reviewers check claims against fixture evidence, not lexical
overlap alone. Existing mocked tests verify contracts, not improved quality.

## Later opt-in provider evaluation (not executed or enabled)

After separate approval of models, call count, cost ceiling and synthetic inputs:

1. Pin revision/policy version, fixture hash, adapter profile/model identity,
   parameters and context. Use a separate test environment, no real sessions/data.
2. Generate baseline and candidate answers on identical cases/settings. Start with
   two samples per case/model/version; budget the full matrix before running it.
   Evaluate primary/fallback explicitly; do not infer fallback parity from prompts.
3. Randomize anonymized A/B order with a recorded seed. Two reviewers independently
   score the rubric and prefer A/B/tie; disclose neither implementation nor model
   until ratings are locked. Resolve critical/disputed cases against evidence.
4. Report by type/route/model, not only aggregate. Report ties, failures and small
   sample uncertainty. An optional LLM judge may flag issues, never replace review.
5. Proposed 70% preference among non-ties is provisional, NOT approved. Critical
   correctness/grounding failures block acceptance. Latency thresholds remain unset
   until measured. No quality score is assigned to authored doubles or canned output.

Measure provider first usable text, application first visible text, provider end,
validation end and durable completion separately. Distinguish local durations and
cross-process ordering; never subtract unrelated monotonic clocks. DOM mutation
is not a measured painted frame. Track output sizes, finish reasons, correction
calls, fallback rate and complete versus truncated answers; no global limit raises.

## Verification

Commands run from repository root with Windows Python 3.10.20; no installation:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --output "$env:TEMP/saiia-answer-quality-baseline.json"
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_baseline.py backend/tests/test_answer_planner_problem1.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_generate_selected_resume.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py -q --tb=short
```

Capture: 24 cases, 20 with effective provider-double prompts and four deterministic
early clarifications, zero live calls, quality not measured. Synthetic export is
outside the repository and contains no credential values. Final checks:

- Combined new/focused regressions: **178 passed in 6.90 s** on the final code.
- Three new Python files compile in memory, without writing bytecode.
- Markdown fences and new-file trailing whitespace/newline checks pass.
- `git diff --check` passes; original index and all four pre-existing file hashes
  match the external baseline.
- Graphify query repeated after additions; graph remains unchanged/unregenerated.

Syntax command (no bytecode output):

```powershell
E:/deepfake_envs/SaIIA/python.exe -B -c "from pathlib import Path; files=['backend/scripts/answer_quality_baseline.py','backend/tests/answer_quality_spec.py','backend/tests/test_answer_quality_baseline.py']; [compile(Path(p).read_text(encoding='utf-8'), p, 'exec') for p in files]; print('3 syntax checks passed')"
git diff --check
graphify query "answer generator planner followup" --dfs --budget 450
```

During development, the initial alternative-trimming assertion incorrectly used
a comma; punctuation-specific assertions corrected that fixture assumption. The
first combined run had 12 failures / 165 passes because storage-focused existing
tests reached the deliberately blocked local retrieval loader. Explicit empty
synthetic local retrieval/JD doubles fixed harness isolation, not production code;
the next run passed 177 tests. Later additions include fresh-process credential
isolation. No failed test was excluded or production expectation weakened.

## Phase 2 handoff and deferred diagrams

Ready for review of Phase 2: make approved policy effective in first-generation
prompts, reconcile conflicting structure/length rules, and remove fabricated
personal completions/repairs. Keep evidence permissions, model bindings/fallback,
validation, real incremental deltas, reset/replacement, cancellation and Retry.
Do not add an unconditional humanizer call or another final-save owner. Update
known-limitation tests explicitly when the intended production behavior changes;
the approved specification remains separate from historical characterization.

Retrieval, budget tuning and UI changes require separate evidence/scope. Screen,
dashboard Ask AI and AI Notes policies remain excluded, with shared-code regressions
required before later changes. This phase exercises no actual gRPC channel,
Electron/overlay DOM, durable storage, live semantic validation, provider quality,
audio route or paint latency. Auth/session authorization is mocked in captures.
Existing streaming tests are not rerun or claimed as new evidence here.

Future diagram requirements are preserved only as a handoff: the user clicks
Generate diagram after a completed system-design answer; technical boxes, arrows
and labels appear below it in the Electron answer window; the diagram is saved
with session history; a separately configured model generates it, model undecided.
No diagram UI, generation, configuration, protocol, schema or storage exists as
part of Phase 1. Design authorization, persistence ownership and model choice in
its own later phase. Recovery migration remains paused; no migration/admission
change is needed to review this baseline. Stop after Phase 1.
