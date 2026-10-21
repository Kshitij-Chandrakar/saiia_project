# Answer quality Phase 4: targeted evidence and follow-up context

2026-10-21. Phase 4 only. Synthetic evidence selection is measured; human-rated
answer quality and live latency are not. No diagram functionality is implemented.

## Baseline, execution and preservation

Entry revision: `d20f672f74d369f56e785a93834431d2a58086ec`, `dev/current-work`.
Phases 1-3 remain uncommitted in the entry working tree. Read their records,
synthetic specification/harness/tests and current retrieval, generator, endpoint,
follow-up, gRPC adapter and coordinator source. No ancestor/repository AGENTS.md
was found. Ponytail favors existing lexical retrieval, bounded context structures
and request-local preparation; no service, dependency or model call was added.

Plan executed: preserve entry state; reproduce misses with synthetic documents;
fix only demonstrated selection/context gaps; verify route and lifecycle contracts;
record before/after evidence. Existing staged documents and unrelated Electron,
Screen, audio and model work remain untouched. All Phase 4 work is unstaged.

`%TEMP%/saiia-quality-phase4-before.json` records revision/status, staged-diff
SHA-256 and hashes of every existing changed/untracked file except environment
files. No real environment file or personal document was inspected. Original
staging and every non-overlapping entry file hash match after work. Generator,
endpoint and the offline harness overlap earlier phases; their policy, cleanup,
validation and streaming work is preserved. Earlier phase records/spec/tests
remain byte-identical.

Graphify existing-graph queries ran before and after changes:

```text
graphify query "resume context retrieval" --dfs --budget 350
graphify query "resume context retrieval followup" --dfs --budget 350
```

These terms occur in the graph vocabulary. Results primarily navigate historical
context/tracker nodes; new uncommitted code is not indexed. Source and executable
tests establish implementation behavior. No graph regeneration, saved query
memory, token-consuming extraction or artifact update occurred.

## Demonstrated failures and before/after evidence

All examples below are authored synthetic inputs, not user resumes or model
outputs. Comparisons are outside the repository in
`%TEMP%/saiia-quality-phase4-reproductions.json`,
`saiia-quality-phase4-after-reproductions.json` and
`saiia-quality-phase4-additional-comparison.json`.

| Fixture and expected context | Before | After / responsible production function |
| --- | --- | --- |
| Quantum cryptography question; documents describe weather forecasts and calendar maintenance; expect no matching evidence | Category weights select two unrelated chunks despite zero query overlap | Zero chunks. `ResumeIndexService._score_chunk()` requires overlap before section boosts, except intentional broad candidate-context intents |
| Five supplied snippets: four weather projects followed by semaphore experience; expect semaphore fact | Section-only second-stage ordering drops the fifth, relevant snippet | Relevant experience retained. `AnswerGenerator._select_retrieved_snippets()` reuses lexical ranking and deduplication |
| Selected resume contains only biology/poetry; cryptography question; expect honest absence and no profile substitution | `CloudResumeService.retrieve_resume_chunks()` falls back to first chunks after no match | Empty retrieval; existing strict endpoint guard returns 409, never uses conflicting profile or calls a provider |
| Atlas Scheduler, Atlas Analytics, and similar Atlas Scheduler Analytics; ask for a specific named project | Exact and partial matches can be returned together; original two-project fixture returns two chunks | One matching project in the fixture; `_project_focus_chunks()` prioritizes exact normalized title, excludes weaker identities and rejects ambiguous unmatched titles |
| Profile first line is weather work; later line is Atlas Scheduler contribution; expect supplied Atlas facts | `_profile_context_lines()` uses only first project line | Bounded relevant excerpt retains the later project/contribution; no invented metric |
| Long generic JD prefix followed by “Role requires sharding expertise”; expect requirement within existing 700-character budget | Prefix loses requirement | `relevant_excerpt()` selects the matching sentence/window; `_build_interview_prompt()` retains requirement as JD context, not experience |
| Completed distinct-values implementation, insertion-order/hashability constraint and `unique(xs)`; “Now write it in Java” / explain empty input | Compiler emits a generic task and flags previous code available, but supplies neither code nor exact edge-case request to generation | Exact request survives compilation; `FollowUpIntentPlan.reference_context` carries one bounded code/excerpt/signature/platform anchor beside the task |
| Two gRPC completed turns stored chronological order; follow-up should reference newest | Adapter supplies oldest-first list to a newest-first resolver | `stream_question_answer()` reverses the existing five-entry window when constructing the request |
| Explicit failed/provisional/discarded history record; expect exclusion | Resolver/lookup can use it as anchor | `completed_context_entry()` filters explicit nonfinal records; completed producers remain final-only |
| Coordinated unbound HTTP turn canceled while retrieval is gated; expect zero subsequent generation | Returning lookup starts one legacy provider double after cancellation; selected-model case already prevented a network call | `cached_context()` checks request control before lookup/cache reuse and after lookup; late values are discarded before generation; both cases make zero provider calls and save nothing |

The historical second-stage snippet helper was executed in memory from its HEAD
AST body, verified unchanged by Phases 1-3; semaphore selection was false before
and true after. No checkout or source replacement was performed. JD comparison
uses the source-confirmed old `[:700]` evidence prefix versus the new helper, not
a historical model response. The initial diagnostic searched the whole prompt for
“sharding” and was inconclusive because the question itself contained that word;
the corrected check compares the actual JD evidence excerpt/complete requirement.

A semaphore first-stage ranking case already selected experience correctly before
the changes and still does. Conflicting selected-resume/profile authority, JD
versus experience separation, missing evidence versus negative personal history
and existing ambiguity guards did not demonstrate new defects requiring policy
changes. Tests retain these boundaries rather than inventing new claims or routes.

## Changed-file inventory

Eight production files:

- `backend/app/services/resume_index_service.py`: query-match eligibility before
  boosts, exact-text deduplication, text-derived tokens and bounded excerpt helper.
- `backend/app/cloud/cloud_resume.py`: remove arbitrary no-match fallback; keep
  specific project identities separate.
- `backend/app/nlp/answer_generator.py`: reuse ranking for supplied snippets;
  relevant bounded profile/JD excerpts; retain source/section labels; append
  conversation data separately from question classification.
- `backend/app/nlp/followup_resolver.py`: explicit nonfinal-history exclusion.
- `backend/app/nlp/followup_intent_compiler.py`: bounded reference-context field,
  exact follow-up wording, completed-anchor lookup.
- `backend/app/api/generate.py`: thread reference context beside AnswerPlan into
  all existing buffered/streaming generator calls.
- `backend/app/grpc_answer_pipeline.py`: newest-first request history and final
  code/language retention in the existing per-connection completed history.
- `backend/app/session_generation.py`: cancellation fence around request-local
  prepared context; late retrieval cannot start unbound generation.

Offline evidence:

- `backend/tests/test_answer_quality_phase4.py`: 31 deterministic helper,
  endpoint, coordinator/cache, gRPC consumer and lifecycle tests.
- `backend/scripts/answer_quality_baseline.py`: allow only known in-process
  Starlette TestClient / HTTPX ASGI transports alongside MockTransport; real
  HTTP, DNS and socket restrictions remain active.
- This record. Eleven files in Phase 4; no frontend file, protobuf/binding,
  model catalog, provider budget/deadline, runtime configuration or schema change.

## Source authority and bounded selection

Local/manual profile routes retain their existing profile/index permissions.
Selected-resume routes still authenticate ownership and active chunk generation
through `CloudResumeService`; no other resume/default profile is merged. A real
no-match response carries no supporting chunks and reaches the existing strict
409 guard. Missing context does not establish that the candidate has never done
something. This phase does not generate or judge personal claims.

Broad introduction/role-fit/motivation plans intentionally allow general authorized
candidate context without lexical overlap with “yourself” or “hire”; that is not a
specific factual retrieval match. Named-project selection prefers exact title
identity. Missing/ambiguous projects use existing insufficient-context behavior,
not another project's achievements. Substring/lexical matching is not a semantic
retriever and remains imperfect.

Exact duplicate text is removed after whitespace/case normalization; distinct
facts/metrics survive. There is no fuzzy-overlap deletion that could erase a
different outcome. Chunk IDs/source/section remain internal selection metadata;
prompts keep source and section beside evidence text. Profile, resume, JD and
conversation remain distinct. Document content is untrusted data under the
existing higher-priority request-local answer policy.

Existing retrieval/project caps are retained. Generator snippet caps remain two
for introductions, four for project questions, otherwise three. Profile summary
and project excerpts are bounded at 320 characters, experience at 360; JD text
remains 700 and short job fields 300. The previous first project line was unbounded;
it is now a bounded relevant window. Excerpt selection is deterministic lexical
work over already loaded text, without another retrieval/model/network call.
No chunk-count, context/token budget or timeout blanket increase occurs.

Existing corpus/upload and active-chunk bounds remain. Oversized individual
upstream chunks and lexical synonyms are not redesigned here. Authorized local
profile excerpts can still include another project when it fits the bounded
window; selected-resume named-project chunks are separately filtered. The answer
policy still forbids attributing unrelated facts to the requested project.

## Follow-up and pipeline integration

The resolver keeps its existing newest-first window, mode separation, TTL, limit
and ambiguity/clarification behavior. Explicit nonfinal states/flags are rejected;
legacy entries without a status remain supported. Renderer history already sends
only completed entries. gRPC history is populated only on successful completion;
terminal failure after partial output adds no history. Entries stay on the
authorized connection context, with no global history or new persistent store.

One referenced completed anchor supplies at most 4,000 code characters, 1,000
answer-excerpt characters, 300 signature and 100 platform characters, plus JSON
escaping/labels. Those are conversation excerpts, not guaranteed complete code
or verified candidate experience. Large-code analysis remains limited by this
existing producer/consumer budget. No complete conversation replay is added.

The original requested change is retained when an action template is compiled.
Code and prior generated prose travel separately in `reference_context`, then
`conversation_context`; they are appended to the prepared prompt only after the
question's AnswerPlan/evidence permissions and coding contract are constructed.
Thus a prior generated “I led 50 engineers” claim cannot change a technical
follow-up's profile permissions or become resume evidence. It remains untrusted
conversation text, not proof that the claim is true. No new factual-verification
guarantee or formal code-equivalence check is claimed.

HTTP manual/typed answers and the gRPC adapter use the same endpoint preparation.
Selected primary/fallback retain the same immutable session selection, shared
prepared primary prompt, request-local context cache, correction adapter and
deadlines. Coordinated unbound sessions retain configured provider choice; the
new cache fence prevents their late lookup results from initiating work after
cancellation. Phase 3 correction/refinement receives the same assembled prompt,
including authorized evidence and labeled conversation, without another lookup.

The cache is private to each logical generation and returns deep copies. Control
is internal to that cache, never sent through IPC or saved as context. Same-question
cross-user/session tests exercise independent cache scopes. Existing stream
identity/reset/replacement, session authorization, Retry, uncertain/pending and
save-only recovery contracts remain. Provisional chunks are not saved; one final
save owner remains. No audio/STT or transport semantics were changed.

## Verification

The guarded runner blocks outbound services before application imports, disables
dotenv loading, uses synthetic credentials, mocks retrieval/storage/provider/STT
boundaries and permits localhost transport/in-process ASGI only. No real resume,
interview transcript, hosted query, recording, playback or live provider call ran.

Focused final command:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase4.py -q --tb=short
```

Result: **31 passed in 0.87 s**, log `%TEMP%/saiia-phase4-targeted.txt`.

Final expanded command:

```powershell
E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_quality_phase4.py backend/tests/test_answer_quality_phase3.py backend/tests/test_answer_quality_phase2.py backend/tests/test_answer_quality_baseline.py backend/tests/test_non_coding_answer_quality.py backend/tests/test_answer_planner_problem1.py backend/tests/test_generate_selected_resume.py backend/tests/test_cloud_resume.py backend/tests/test_cloud_resume_routes.py backend/tests/test_followup_intent_compiler.py backend/tests/test_live_followup_resolver.py backend/tests/test_answer_variation_problem2.py backend/tests/test_openai_answer_pipeline.py backend/tests/test_answer_generator_reliability.py backend/tests/test_coding_quality_gate.py backend/tests/test_coding_implementation_intent.py backend/tests/test_session_generation.py backend/tests/test_answer_stream_phase2.py backend/tests/test_answer_stream_phase3.py backend/tests/test_answer_stream_characterization.py backend/tests/test_answer_streaming.py backend/tests/test_grpc_answers.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_combined.py backend/tests/test_grpc_cloud_context.py backend/tests/test_grpc_manual.py backend/tests/test_grpc_realtime.py backend/tests/test_screen_intelligence_orchestrator.py backend/tests/test_screen_intelligence_contract.py -q --tb=short
```

Result: **701 passed in 44.05 s**, log `%TEMP%/saiia-phase4-verified.txt`.
This includes localhost gRPC and actual Electron/preload boundary regressions,
all three synthetic audio routes, selected/unbound/legacy behavior, correction,
fallback, final-save parity, Retry/save-only recovery, resume ownership/auth routes
and Screen/shared-generator coding checks. No frontend source changed; standalone
frontend build/render tests and live Windows acceptance were not rerun or claimed.

Development results: focused existing regressions passed 295; initial new tests
passed 26, later expanded to 31. One early prompt assertion exposed broad role-fit
context being filtered; resolved broad candidate-context intent now preserves it,
without weakening the assertion. The first expanded run passed 675 and failed 22
ASGI route calls at the offline transport guard, before their assertions ran.
Allowing only known non-network transports fixed isolation; guard/route tests
then passed 88. An intermediate expanded run passed 698. The subsequently added
unbound late-retrieval test reproduced one unwanted provider-double call and
failed before the cache control fence; selected and unbound cases now pass.
An initial import cycle through `app.services` was resolved with local helper
imports, without initializing unrelated services. No failed case was removed.

Ten changed Python files compile in memory; newline/trailing-whitespace checks,
Markdown fence checks and `git diff --check` pass. Original index/revision and
all non-overlapping entry-file hashes match. Graphify queries succeeded; artifacts
remain unregenerated. No staging, commit, push or deployment was performed.

## Remaining limitations and Phase 5 handoff

Lexical selection does not prove semantic relevance, complete grounding or better
spoken answers. Project continuation chunks without reliable identity, synonyms,
large code excerpts and conditional validation limits remain. No embedding/ranking
service, new retrieval call or claim-verification system is justified by this
phase's evidence. The synthetic baseline's motivation/debugging/JD-fit early
clarifications remain resolver/reference-guard limitations, distinct from the
demonstrated retrieval misses; ambiguity policy was not broadened to force answers.

Client-supplied legacy history without status cannot be cryptographically proven
final/owned from its payload alone; it remains untrusted conversation rather than
authorized personal evidence. This phase does not fetch hosted transcripts to
establish history provenance. Coordinated cancellation is tested; no claim is made
that every unmanaged HTTP client's disconnect behavior has been redesigned.

Human quality, semantic recall, provider token cost and live latency remain
unmeasured. Longer useful input may cost more within unchanged output/deadline
budgets. Future evaluation needs separately authorized synthetic provider calls
and blinded review, not assertions about authored provider doubles.

Phase 5 is audit/design only: inspect completed system-design answer identity,
Generate diagram placement below the Electron answer, user-triggered generation,
separate configurable diagram model (still undecided), history ownership,
authorization/deletion, cancellation, request identity and safe rendering. Decide
diagram representation and persistence after that audit. No button, diagram
generation, model setting, storage field or migration is implemented here. Keep
the recovery migration paused; no database admission/runtime setting was changed.
Stop after Phase 4.
