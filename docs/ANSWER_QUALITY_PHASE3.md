# Answer quality Phase 3: cleanup, correction and repetition consistency

2026-10-20. Phase 3 only. No live-provider evaluation or human quality claim.

## Baseline and preservation

Entry revision: `d20f672f74d369f56e785a93834431d2a58086ec`, on
`dev/current-work`. This includes `d20f672` Screen admission/capture restoration,
following `cec0cf9`. Phase 1/2 answer-quality work was already uncommitted; the
baseline therefore describes HEAD plus that working tree, not HEAD alone.

Read the Phase 1/2 records, synthetic specification, harness, planner/generator,
endpoint, selected/unbound coordination and streaming records. No applicable
ancestor or repository AGENTS.md was found. Ponytail favors the existing frozen
AnswerPlan, existing prepared prompt and existing validation/cancellation paths.
No dependency, parallel policy framework or new provider call was added.

Entry contained Phase 1/2 production/test changes and untracked records/harness,
three staged documents and unrelated `frontend/electron/main.cjs` comments.
`%TEMP%/saiia-quality-phase3-before.json` records revision, status, index hash,
changed-file hashes and three synthetic cleanup samples. Unrelated files and
original staging remain byte-identical. This phase intentionally overlaps the
generator, endpoint, baseline/Phase 2 tests, noncoding and OpenAI pipeline tests;
their Phase 1/2 policy changes are retained. Historical records and synthetic
case specification are unchanged. All new work remains unstaged, uncommitted.

Before and after prompt exports:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --output "$env:TEMP/saiia-answer-quality-before-phase3.json"
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --output "$env:TEMP/saiia-answer-quality-after-phase3.json"
```

Each captures 24 synthetic cases: 20 effective provider-double prompts and four
early clarifications. No live calls or quality scores. The separate cleanup
capture shows ordinary 230-word prose cut at the old cap, an `Alternatively:`
section discarded, and blank lines collapsed inside a fenced code sample.
Those are source/helper observations, not observed application answer quality.

Graphify queries ran before and after source changes using the existing graph:

```text
graphify query "answer generator variation refinement" --dfs --budget 350
graphify query "answer generator refinement variation validation" --dfs --budget 350
```

The final query uses existing graph vocabulary: answer, generator, refinement,
variation, validation. Results primarily reach historical tracker/memory nodes,
not the uncommitted implementation. Current source/tests are authoritative. No
graph artifacts were regenerated, query memories saved or provider tokens used.

## Changed-file inventory for this phase

Production:

- `backend/app/nlp/answer_generator.py`: content-preserving sanitation, policy and
  evidence in correction/refinement, optional refinement checks, protected coding
  output, required semantic/personal rejection and repetition diagnostics.
- `backend/app/nlp/answer_variation.py`: correctness-first repetition instruction,
  no similarity-driven model rewrite, evidence-safe metadata dimensions.
- `backend/app/api/generate.py`: personal repair eligibility follows the resolved
  AnswerPlan rather than earlier category/subtype hints.

Verification:

- `backend/tests/test_answer_quality_phase3.py`: new desired-policy helper,
  coordinator, real localhost gRPC, cancellation and fake-clock regressions.
- `backend/tests/test_answer_quality_baseline.py`: explicitly superseded cleanup
  and alternative-deletion expectations, labeled Phase 3.
- `backend/tests/test_answer_quality_phase2.py`: explicitly superseded generic
  hypothetical-fallback assertion; original first-generation policy tests remain.
- `backend/tests/test_non_coding_answer_quality.py`: refinement follows the plan
  instead of a mandatory conceptual layout.
- `backend/tests/test_answer_variation_problem2.py`: stable correct answers replace
  expectations for automatic similarity rewrites; scoping/TTL/size tests remain.
- `backend/tests/test_openai_answer_pipeline.py`: rejected required validation or
  unsuccessful required correction now fails; successful correction remains tested.
- `backend/tests/test_coding_implementation_intent.py`: compiled coding follow-up
  must retain actual code, not merely structured metadata.
- This record.

No frontend, protobuf, generated binding, provider catalog, retrieval, database,
audio/STT, configuration or runtime setting was changed.

## Before/after cleanup and finalization

`AnswerGenerator._clean_answer()` now sanitizes internal markers and leading
wrapper text without applying the old global soft word cap, cutting sentences,
inventing terminating punctuation, stripping ordinary Markdown/list markers or
deleting alternatives/conclusions. Fenced code retains its internal whitespace.
Existing recognized conceptual bullet/example spacing remains compatible; a
plain subtraction expression is not reclassified as an inline bullet list.
The unused `_truncate_words()` helper is removed.

Explicit depth/format is enforced through the existing request-local prompt
policy, not by cutting a completed answer to an approximate word range. The
technical completeness helper receives the plan and skips broad concept-depth
keyword requirements for brief, one-sentence and narrow-follow-up requests.
Factual distinction checks and other existing validation remain. Arbitrary exact
word counts and naturalness are not proven by deterministic checks.

Interview coding finalization retains the generated explanation, alternatives
and code instead of rebuilding only four recognized sections. Explicit code-only
requests retain only the requested fenced code. The separate Screen structured
presentation remains unchanged. Coding correction receives the plan and complete
interview implementation, instead of a 1,600-character excerpt; Screen's existing
compact correction context remains. Existing compact question/sample/stub
selection, correction count and output budgets are unchanged.

`_format_coding_answer_with_explanation_model()` rejects changed protected code;
its existing failure branch retains the original code. Optional general
refinement also rejects changed fenced code, empty output and existing
deterministic correctness/plan violations. These checks are not proof of semantic
equivalence or exhaustive factual grounding.

Hard limits remain: selected-attempt accumulation is bounded at 262,144
characters, and final transcript admission rejects answers above the existing
24,000-character limit before checkpoint/save. No final is silently shortened
to fit storage. Existing size-rejection and save-only recovery tests pass.

## Correction/refinement policy and evidence flow

`generate_answer()` passes its already assembled, permission-filtered prompt to
`_semantic_validate_with_openai()`, `_semantic_correction_with_openai()` and
`refine_answer_with_groq()` / `_build_refinement_prompt()`. This carries the same
resolved plan, explicit constraints, applicable preference, selected-resume
authority and selected evidence without another classification/retrieval pass.
Context is identified as data, and the current answer is not candidate evidence.
Semantic helpers receive the complete answer rather than a 5,000-character prefix.
Direct helper callers without an assembled prompt receive the plan instructions.

Refinement removes its conflicting mandatory example heading, bullet/paragraph
counts and 100-160-word instruction. It preserves hypothetical framing and
supported facts; JD requirements and previous generated answers are not personal
experience. It cannot add unsupported metrics, responsibilities or outcomes.
The old numeric refinement value remains solely in its unchanged provider budget
calculation; this phase does not raise token limits to match longer guidance.

Required semantic rejection cannot return a rejected original after correction
failure, malformed required validation, disabled correction or failed corrected
deterministic validation. It raises content-free `ProviderError` with
`invalid_response`, handled by the existing endpoint/coordinator policy. No helper
chooses an independent model fallback. Existing selected adapters keep corrections
on the active attempt and common budget. Corrections remain buffered.

Optional stylistic refinement failure keeps the original, which still proceeds
through normal final validation. No universal semantic call was added: existing
provider/eligibility conditions and selected-resume skip remain. Deterministic
advisory warnings are not silently reclassified into universal mandatory model
validation. Corrected output is rechecked deterministically; no extra semantic
verification call is introduced, and claim-level correctness is not guaranteed.

Personal repair no longer substitutes a generic hypothetical paragraph. It
removes wrappers only if the remaining text passes the existing personal checks;
otherwise it raises `invalid_response` through existing recovery/fallback handling.
The endpoint now invokes this rapport-specific helper only for a resolved
`personal_story` plan. A real regression exposed an earlier category hint sending
a compiled coding follow-up into personal repair: the old fallback could replace
code while leaving coding metadata intact. The plan guard and strengthened
endpoint regression prevent that mismatch. Selected-resume strict-mode handling
is retained. The personal checks remain pattern checks, not claim verification.

## Repetition, calls and streaming

`build_variation_plan()` keeps history namespacing, context fingerprints, TTL,
size bounds and repetition detection. `variation_instruction()` no longer demands
a different opening/example or inserts prior generated excerpts into the prompt.
It permits stable correct facts/code and follows explicit requests for another
example, approach or more detail under the same policy. No topic-specific novelty
exceptions or new memory system were added.

The optional `_variation_rewrite_with_openai()` call/path is removed. Similarity
is diagnostic only: high similarity yields `stable_repetition`, not another model
call. `rewrite_allowed` is false even if the existing rewrite setting is enabled;
no real flag/configuration was edited. A retained secondary variation rewrite
would require evidence of benefit and validation of protected facts/code; lexical
distance cannot establish meaning preservation.

Provider-call effects: no unconditional calls added; one fewer possible
similarity-only rewrite, and no explanation call for explicit interview code-only
requests. Brief/narrow concept completeness heuristics no longer manufacture an
unnecessary semantic correction solely for broad depth. Required failures can
reach the existing single outer fallback; retry/save-only policy is unchanged.
Longer validation/correction inputs may increase latency/cost, unmeasured here.

Selected primary/fallback and coordinated unbound sessions retain their existing
adapters, route selection, shared prepared primary input and deadlines. Legacy
HTTP/provider routes use the same cleaner/policy helpers with their existing
provider-specific conditional processing. No stream/protocol changes: genuine
provisional deltas, empty discard resets, attempt/revision fencing, buffered
correction and atomic canonical replacement remain. Returned/displayed canonical
text and the single coordinator-owned final save agree in the gated test. Save-only
recovery still performs zero provider regeneration. There is no variation work
left to cancel; actual correction cancellation/deadline behavior is exercised.

## Verification

All commands run from repository root through the existing guarded offline runner.
Before application import it disables dotenv loading, substitutes synthetic
credentials, blocks external HTTP/DNS/TCP, and permits localhost transport only.
Retrieval/storage/STT are mocked. The existing Node loopback-only preload guards
Electron test children. No recording, playback or paid/provider request occurs.

Final full command (stdout redirected outside the repository to
`%TEMP%/saiia-phase3-final2.txt`):

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase3.py backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_baseline.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_answer_planner_problem1.py backend/tests/test_generate_selected_resume.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py backend/tests/test_openai_answer_pipeline.py backend/tests/test_answer_generator_reliability.py backend/tests/test_coding_quality_gate.py backend/tests/test_coding_implementation_intent.py backend/tests/test_session_generation.py backend/tests/test_answer_stream_phase2.py backend/tests/test_answer_stream_phase3.py backend/tests/test_answer_stream_characterization.py backend/tests/test_answer_streaming.py backend/tests/test_grpc_answers.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_combined.py backend/tests/test_grpc_cloud_context.py backend/tests/test_grpc_manual.py backend/tests/test_grpc_realtime.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_screen_intelligence_contract.py -q --tb=short
```

Result: **585 passed in 39.03 s**. Coverage includes all three synthetic audio
entry routes, selected fallback, unbound configured routing, HTTP/legacy behavior,
actual localhost gRPC handler/adapter, existing actual Electron/preload integration,
pending/uncertain/save-only recovery and shared-generator Screen/coding regressions.
No frontend source was changed; a standalone frontend build/render suite was not
rerun. These transport/consumer assertions are not live Windows acceptance or paint
timings. No human naturalness, factual guarantee or latency improvement is claimed.

Final focused command:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase3.py -q --tb=short
```

Result: **32 passed in 1.29 s**. The ten changed Python files compile in memory;
their whitespace/newline checks and this record's Markdown fence checks pass.
`git diff --check` passes. Entry revision, original staged-diff SHA-256 and all
unrelated entry-file SHA-256 comparisons pass. Final Graphify query also succeeds.

New Phase 3 tests cover detailed prose, alternatives, Markdown/code/sentence
preservation, explicit brief/format requests, narrow follow-ups, authorized evidence
and hypothetical correction, concurrent isolation, optional refinement failure,
stable factual/coding/personal repetition, explicit alternate requests, protected
code, canonical replacement/save parity, fallback after failed correction, real
gRPC Stop/disconnect during actual correction and fake-clock budget expiry. Gates
and bounded waits detect deadlock; there are no sleeps to simulate quality/streaming.

Development evidence is not hidden: the first focused run had 117 passes and 11
superseded historical assertions; later focused coverage passed 149 tests. An
intermediate expanded run passed 574. After stronger personal validation the full
run had 583 passes and one real coding-follow-up failure, fixed by resolved-plan
repair eligibility rather than weakening the test. Initial new fixture mistakes
used a nonexistent coordinator API/field, then were corrected to consume the actual
endpoint NDJSON and `PreparedAnswer.text`. A code-only test exposed the one-token
code/structured-metadata condition; final code-only handling no longer depends on
that metadata being present. Final 585-test run includes these regressions.

Syntax compilation in memory, changed-file trailing whitespace/newline checks,
Markdown fence checks, `git diff --check`, original index-hash comparison and
unrelated-file hash comparisons complete the verification. No bytecode generation,
new dependency, staging or commit is required.

## Remaining limitations and Phase 4 handoff

Grounding relies on authorized supplied evidence, prompt boundaries and existing
pattern/conditional validation. It is not exhaustive claim verification. Provider
budgets, finish behavior, correction latency and human-rated quality still need
the separately approved synthetic provider comparison from Phase 1; this phase
does not activate it or raise output limits/deadlines. Storage rejection remains
possible for oversized complete answers, with existing recovery semantics.

Phase 4 should first reproduce evidence-selection/follow-up gaps rather than
change retrieval broadly. The synthetic baseline still yields early clarification
for motivation, debugging, JD-fit and the intentionally ambiguous follow-up. The
first three are resolver/reference-guard candidates, not proven retrieval failures.
The irrelevant-retrieval, sparse evidence, selected-resume/profile conflict and
JD-only cases supply the targeted matrix for checking what authorized evidence
actually reaches prompts. Mocked outputs do not demonstrate a ranking failure or
justify inventing personal details; no retrieval change is made here.

Keep selected-resume authority, untrusted-context handling, request-local policy,
stream identity, shared budgets and one final-save owner in any Phase 4 change.
Measure missing versus irrelevant evidence separately from poor generation.
Diagrams, UI redesign, migration/admission and the paused recovery migration remain
outside this phase. No migration or database dependency was activated. Stop after
Phase 3; Phase 4 is not implemented.
