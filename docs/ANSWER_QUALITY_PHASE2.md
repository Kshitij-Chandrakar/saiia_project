# Answer quality Phase 2: first-generation policy and personal grounding

2026-10-20. Phase 2 only. Human answer quality and provider/application latency
remain unmeasured. Mocked outputs establish policy/plumbing, not naturalness.

## Baseline and scope

Entry revision: `cec0cf9e7fd712769a702c7a90235e560757eafa`, `dev/current-work`.
Read the conversational audit, Phase 1 record/specification/harness/tests, planner,
generator, HTTP endpoints, session coordinator and relevant streaming records.
No applicable ancestor/project AGENTS.md was found. Ponytail favors extending the
existing immutable AnswerPlan rather than adding orchestration or a model call.

Entry already contained Phase 1's four untracked files, three staged model/startup
documentation changes, an Electron comment hunk, and unstaged Screen API/service
changes. Additional Screen architecture/tests/docs and Electron edits appeared
outside this task during execution. None of those files was edited or reverted by
this phase. Staging remains untouched. External entry hashes/status/index are in
`%TEMP%/saiia-quality-phase2-baseline.json`; do not interpret concurrently changed
unrelated file hashes as changes made by this phase.

Before policy edits, the existing guarded harness captured all 24 cases to
`%TEMP%/saiia-answer-quality-before-phase2.json`: 20 provider-double prompts and
four early clarification responses. The final after capture is
`%TEMP%/saiia-answer-quality-after-phase2.json`. These contain synthetic inputs,
prompts/budgets and authored doubles, not measured model answers or credentials.
The four early responses remain motivation, debugging, JD-fit and the deliberately
ambiguous follow-up. No resolver bypass or assumption that all cases must generate.

Graphify existing-graph queries ran before and after changes:

```text
graphify query "answer generator planner followup" --dfs --budget 300
graphify query "answer generator planner followup" --dfs --budget 450
```

The graph mainly returned historical navigation context; source is authoritative.
No graph artifacts were regenerated/saved, and no provider tokens were used.

## Changed-file inventory

Production:

- `backend/app/nlp/answer_planner.py`: consumed, request-local first-generation
  policy, intent/depth/format guidance and budget-classification compatibility.
- `backend/app/nlp/answer_generator.py`: interview prompt assembly, system/personal
  grounding, safe personal repair, optional-example compatibility and legacy budget
  recognition. Existing structured Screen prompt branch remains separate.
- `backend/app/api/generate.py`: pass original request and resolved follow-up flag
  into the existing planner in buffered and streaming endpoints.

Offline verification:

- `backend/scripts/answer_quality_baseline.py`: distinguish strict capture doubles
  from regression code-under-test; permit only HTTPX MockTransport in-memory sends,
  retain real-network rejection, and guard Node children before startup.
- `backend/tests/test_answer_quality_phase2.py`: approved desired-policy tests,
  explicit constraints, context concurrency, safe repair and selected-attempt parity.
- `backend/tests/test_answer_quality_baseline.py`: update only three superseded
  limitations to explicitly labeled Phase 2 expectations; preserve remaining
  characterization of cleanup limits, alternative trimming, adapters and safety.
- `backend/tests/test_non_coding_answer_quality.py`: replace superseded mandatory
  layout/creative-story assertions with desired policy/evidence properties.
- `backend/tests/test_generate_selected_resume.py`: preserve authority, identity,
  snippet and JD checks while removing universal walkthrough/literal-template demands.
- `backend/tests/test_openai_answer_pipeline.py`: use an actual factual error rather
  than absence of an optional example to trigger validation/correction regressions.
- `backend/tests/test_answer_generator_reliability.py`: grounded personal expectations
  and explicit synthetic explanation-provider doubles in three code-gate tests.
- This record.

Phase 1's approved case specification and historical record are unchanged. Its
before capture is preserved separately; tests superseded by approved production
behavior are labeled Phase 2 rather than retaining unexplained failures.

## Effective ownership and precedence

`build_answer_plan()` refines the existing frozen AnswerPlan. No policy is stored
on the shared AnswerGenerator. The endpoint provides resolved task intent plus
the original request and follow-up status. `AnswerPlan.prompt_instructions()`
consumes preferred structure, coverage, example policy, voice, context permissions
and suggested word range. `_build_interview_prompt()` supplies only context allowed
by that plan, using the existing profile/snippet selection helpers.

Precedence is accuracy/grounding/task constraints, explicit question format/depth,
applicable existing user length preference, type guidance, then wording variation.
Question constraints recognize brief/one-sentence/deep requests, word counts,
bullets/headings/tables and code-only requests. This is bounded deterministic
interpretation, not a complete natural-language constraint parser.

An available `preferred_answer_style` of brief/concise/detailed is honored below an
explicit request. Arbitrary style strings are not promoted to instructions. No new
length UI/request field is introduced; unavailable or context-suppressed preferences
are not fetched through a new channel.

Approved prose guidance is 90-160 HR, 100-170 introductions, 150-230 behavioral,
100-200 concepts, 20-70 simple facts, 140-230 comparisons, 100-220 coding/debugging
explanation with complete code separately, 220-400 design, 140-240 projects,
200-320 broad walkthroughs, and 30-110 narrow follow-ups unless the task needs more.
Ranges are not minimums or hard ceilings. Simple facts retain the technical-concept
metadata type with a direct-fact structure, avoiding a new variation category.

The planner distinguishes technical failure modes from personal failure stories,
and supported contribution questions from broad walkthroughs. Those decisions
control context permissions before generation. The model is no longer invited to
reclassify an interview task in conflict with its evidence permissions. Intake and
follow-up resolution themselves remain unchanged.

## Before/after prompt contracts

| Before | Phase 2 interview contract |
| --- | --- |
| Planner detail/structure/length fields mostly descriptive | Fields drive effective prompt instructions |
| Model may silently reinterpret category | Resolved plan owns intent and context permissions |
| Optional example plus mandatory example heading | Relevant examples conditional; no required heading |
| 100-160 conceptual target and several competing category limits | Approved guidance from one plan; explicit request wins |
| Broad selected-project workflow on narrow contribution questions | Exact question/contribution first; broad workflow only when asked |
| Fixed paragraphs/bullets conflicting with other rules | Task-appropriate layout, with existing special code contracts retained |
| Creative low-risk memories/preferences and canned first-person repair | Evidence or explicit hypothetical; no invented positive/negative history |

Non-Screen structured coding prompts consume policy too, while preserving signatures,
stdin/stdout rules, complete fenced code and required extraction contracts. Code-only
requests remove forced explanation sections in first-generation prompts. Final
structured formatting is still a later-stage limitation, not claimed fixed here.

## Grounding and compatibility

System/user policy treats resume/profile/retrieval/JD/previous AI answers as data,
not overriding instructions. Selected-resume authority remains exclusive. JD facts
tailor relevance, never establish achievements. General examples cannot become
personal experience. Unsupported metrics, ownership and stories are prohibited;
missing evidence does not establish a negative history either.

`_build_personal_prompt()` uses the same plan. Creative generation metadata is
false, and personal target-range metadata follows the effective plan. The canned
childhood/failure/friendship narratives are removed from `_fallback_personal_answer()`.
Its terminal replacement explicitly describes a hypothetical approach and states
that it is not a past-life event. It may be generic: this is a safe fallback, not
proof of a satisfying answer to every personal question.

Minimum validator compatibility changes:

1. `_validate_technical_real_life_example()` accepts absence of the optional section.
   An explicitly labeled empty or inappropriate example still triggers its checks.
2. `validate_personal_answer()` no longer requires minimum words, multiple sentences,
   first-person wording or memory/emotion keywords. It retains empty/meta/repeated/
   sensitive/professional-content checks as applicable. Short answers are not replaced
   merely to pad them into a story.

Deterministic and conditional semantic validation/correction still run through the
existing pipeline. These prompts and pattern checks do not prove claim-level
entailment or prevent every hallucination/injection. Existing validation-failure
policies are unchanged, including returning an original answer if correction fails.

Primary/fallback reuse the same prepared prompt in AttemptRun. Model catalog,
binding snapshots, adapters, provider choice, shared deadlines/reserve, cancellation,
Retry/save-only recovery and final-save ownership are unchanged. New quality intent
must not implicitly activate larger budgets: `provider_budget_type` preserves the
prior classification for output/reasoning selection, and a bounded internal budget
class preserves legacy Groq ceilings without retaining the old forced-layout marker.
All 20 before/after captured requested budget dictionaries match, including catalog
profile caps; this is synthetic configuration evidence, not deployed limit discovery.

## Verification

All external boundaries use synthetic credentials, fake providers/storage and
guarded HTTP/DNS/socket access before startup. Tests may exercise actual provider
methods against HTTPX MockTransport; real HTTP remains forbidden. Windows asyncio
loopback wakeup sockets and localhost gRPC are permitted. Node child processes use
the existing loopback-only preload. No dotenv values, live calls, recording or
playback are involved.

Focused command (222 passed before the final additional code-only assertion):

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_baseline.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_answer_planner_problem1.py backend/tests/test_generate_selected_resume.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py backend/tests/test_openai_answer_pipeline.py -q --tb=short
```

Expanded regression command:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_baseline.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_answer_planner_problem1.py backend/tests/test_generate_selected_resume.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py backend/tests/test_openai_answer_pipeline.py backend/tests/test_answer_generator_reliability.py backend/tests/test_coding_quality_gate.py backend/tests/test_coding_implementation_intent.py backend/tests/test_session_generation.py backend/tests/test_answer_stream_phase2.py backend/tests/test_answer_stream_phase3.py backend/tests/test_answer_stream_characterization.py backend/tests/test_answer_streaming.py backend/tests/test_grpc_answers.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_combined.py backend/tests/test_grpc_cloud_context.py backend/tests/test_grpc_manual.py backend/tests/test_grpc_realtime.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_screen_intelligence_contract.py -q --tb=short
```

Final result: **553 passed in 46.17 s** on the final production code. The new
Phase 2 module separately passed **39 tests in 1.60 s**. Ten scoped Python files
compile in memory without bytecode and pass trailing-whitespace checks. Markdown
fences and `git diff --check` pass. Original index/staged-document hashes and Phase
1's specification/record hashes match entry; concurrently edited unrelated files
were left untouched. All 20 before/after requested budget dictionaries match.

Scope includes real localhost Python
coordinator/gRPC to actual Electron client/IPC/preload/Auto consumers with gated
synthetic chunks across microphone, system and both, plus reset/fallback/completion,
Stop/disconnect, claims/recovery and one-save regressions. It does not establish
rendered paint timing or human quality. No standalone frontend build is needed for
this phase's backend-only production changes; unrelated frontend edits are excluded.

An initial expanded run had 541 passes / eight failures: three tests omitted a
coding explanation double, two personal tests demanded creative story repair,
and three in-memory HTTPX tests were rejected by the overly broad harness send
guard. Explicit doubles, approved personal assertions and MockTransport-only
permission resolved these without enabling real network access. The next expanded
run passed 549; code-only and general budget-compatibility assertions brought the
final set to 553. No cases were disabled.

Syntax verification (repository root, no bytecode):

```powershell
E:/deepfake_envs/SaIIA/python.exe -B -c "from pathlib import Path; files=['backend/app/api/generate.py','backend/app/nlp/answer_generator.py','backend/app/nlp/answer_planner.py','backend/scripts/answer_quality_baseline.py','backend/tests/test_answer_quality_phase2.py','backend/tests/test_answer_quality_baseline.py','backend/tests/test_non_coding_answer_quality.py','backend/tests/test_generate_selected_resume.py','backend/tests/test_openai_answer_pipeline.py','backend/tests/test_answer_generator_reliability.py']; [compile(Path(p).read_text(encoding='utf-8'),p,'exec') for p in files]; print('10 syntax checks passed')"
```

Before/after export command (run once before edits with `before`, after with `after`):

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --output "$env:TEMP/saiia-answer-quality-after-phase2.json"
git diff --check
```

## Phase 3 handoff and remaining limits

Phase 1's anchored rubric and blinded A/B procedure remain the review protocol.
The paired synthetic captures are comparison inputs only: do not score their
authored doubles as model outputs. A later separately approved provider matrix,
call/cost ceiling and two-reviewer evaluation are needed. Preference thresholds
remain provisional; latency thresholds remain unset until measured.

Phase 3 owns general cleanup, correction/refinement and variation consistency.
Ordinary legacy prose can still be cut by ANSWER_MAX_WORDS (source default 160),
and alternative-section trimming remains punctuation-sensitive. Refinement can
still impose its old 100-160 conceptual format, and final code formatting can
restore headers after a code-only first-generation request. Review these before
claiming final answers fully honor depth/format. Do not simply raise every budget.

Retrieval ranking/truncation and unmatched-context behavior are unchanged. The four
early clarification cases require separate resolver review. Keep Screen/vision,
dashboard Ask AI and AI Notes policies separate; no direct vision policy is changed.
No diagram, UI, schema, migration, hosted query or runtime activation is included.
The recovery migration remains paused. Stop after Phase 2; no commit/staging/push.
