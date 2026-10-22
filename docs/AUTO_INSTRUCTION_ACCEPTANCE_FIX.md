# Auto instruction acceptance correction

2026-10-21. Local synthetic diagnosis and minimal fix; no live provider, microphone,
recording, hosted query, migration, runtime flag, staging or commit.

## Baseline and exact rejecting stage

Parent `bff9827ab7ebbcfb560dcac5178a9391f530c5a9`, dev/current-work; staging was empty.
Existing answer-quality, diagram, source-lookup and presentation work was present
and preserved. Entry hashes/index and synthetic before/after evidence are outside
Git in `%TEMP%/saiia-auto-instructions-vb03li6p`. Applicable instructions and Ponytail
were read; no AGENTS.md found. Existing Graphify queries supplied detection-path
references; current source and tests are authoritative. No graph regeneration.

Before editing, actual `question_detect.detect_question` and
`grpc_answer_pipeline.detect_intake_question` were run with synthetic inputs:

| Transcript | HTTP detection before | gRPC before |
| --- | --- | --- |
| Explain system design | accepted | accepted |
| What is gRPC? | accepted | accepted |
| Design a URL shortener. | rejected | not_question |
| Design a parking lot system. | rejected | not_question |
| Build a rate limiter. | rejected | not_question |
| Implement an LRU cache. | accepted already | accepted already |
| Explain how you would design a chat application. | accepted already | accepted already |
| Yesterday we discussed a URL shortener. | rejected | not_question |
| That design looks good. | rejected | not_question |

For the supplied full transcript, disappearance is at **question detection**, not
intent planning. This is a deterministic source-level reproduction, not a claim
that physical STT transcribed the original manual utterance exactly; no live audio
trace was supplied or captured.

1. `grpc_server.receive_transcripts`: STT Turn with end_of_turn forwards the final
   transcript and calls queue_final. The new real-localhost test observes this event.
2. `queue_final`: utterance assembly calls `detect_intake_question`, which uses the
   shared HTTP extractor/polisher and `QuestionClassifier.should_process_as_question`.
   The old phrase rules omitted design/build instructions. Extraction likewise had
   no explicit instruction candidate for them. A four-word URL design prompt was
   rejected as "does not look like an interview question", mapped to not_question.
3. Because it is short, existing intake holds it for the one-second endpoint wait;
   the endpoint check rejects it again. Deduplication/cooldown and questions.put
   are below this rejection and are never reached for this rejected transcript.
4. Therefore answer_worker, its second detection pass, resolved AnswerPlan and
   provider dispatch cannot run. The recent concept-versus-design planner fix cannot
   repair an utterance discarded before planning.
5. Existing "Explain..." and coding-context "Implement an LRU cache" rules already
   pass; they are controls, not newly fixed failures.

## Minimal implementation

`classifier.looks_like_interview_instruction` recognizes an anchored design/build/
implement command with a/an/the and an object, optionally beginning "please". Empty
objects and dangling conjunction/preposition endings stay rejected. This is task
syntax, not a URL-shortener keyword exception or acceptance of any design mention.
The shared classifier applies it after existing filler/incomplete/coding checks.

`question_detect.extract_question_candidate` uses that same predicate only for a
sentence beginning with the instruction, or the tail of an existing explicit
question-context phrase. It does not search for a design/build verb anywhere in
conversation; "Yesterday we discussed how to design a URL shortener" remains false.
The normal polish/normalization and question-mark handling are unchanged.

No gRPC production change is needed: both its queue admission and generation adapter
already consult the shared classifier. In particular, stable-partial heuristics,
endpoint timing, utterance bounds, duplicate fingerprints/turn IDs, cooldown and
latest-pending dispatch are unchanged. New design commands wait for final speech;
an incomplete partial does not gain a new stable-partial shortcut. Explicit
low-confidence rejection remains authoritative.

Audio/STT capture, model catalog/routing, provider budgets, cancellation, diagram
activation, source/provenance storage and all migrations/environment settings remain
unchanged. Instruction acceptance does not change the planner's intent policy;
actual URL design still receives system_design rather than conceptual explanation.

Changed files (four):
- `backend/app/nlp/classifier.py`
- `backend/app/api/question_detect.py`
- `backend/tests/test_auto_instruction_acceptance.py`
- `docs/AUTO_INSTRUCTION_ACCEPTANCE_FIX.md`

The two production files add a small shared predicate and extraction branches.
Prior A/B patch artifacts are preserved; this acceptance correction belongs with
answer-quality patch A and needs inclusion before any later commit preparation.

## Verification and boundaries

All tests entered `answer_quality_baseline.offline()` before app imports: fake
credentials, dotenv disabled, mocked providers/retrieval/storage, forbidden unexpected
outbound HTTP and permitted localhost gRPC only. No physical capture or live STT.

```powershell
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_auto_instruction_acceptance.py -q --tb=short
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_auto_instruction_acceptance.py backend/tests/test_definition_question_detection.py backend/tests/test_grpc_auto.py backend/tests/test_grpc_utterance_buffer.py backend/tests/test_grpc_answers.py backend/tests/test_grpc_combined.py backend/tests/test_answer_intent_presentation.py -q --tb=short
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests -q --tb=short
git diff --check
```

- Initial new tests: **27 passed (1.45s)**; bounded split-final/expiry regression
  subsequently added, giving 28 new tests in the complete run.
- Focused acceptance/detection/Auto/utterance/combined/planner regressions:
  **140 passed (12.68s)**.
- Final full backend: **1642 passed, 2 existing skipped (76.96s)**.
- Python AST syntax, Markdown fences, scoped secret patterns, whitespace, original
  staging and unrelated entry hashes checked separately. No frontend source changed;
  frontend build/browser tests were not required or claimed for this backend fix.

The real localhost gRPC test keeps production handler, detector, adapter, endpoint,
planner, coordinator and final-save orchestration intact. Only STT socket/auth/
storage/provider boundaries are mocked. It releases a final transcript after an
incomplete partial, observes final_transcript -> question_detected -> answer_delta
-> answer_completed, verifies system_design in the effective provider prompt,
blocks completion with an explicit event, rejects a duplicate during generation,
and commits exactly one final answer. Stop closes the fake socket and awaits server
cleanup. It does not replace detection/generation with a pre-accepted question.

HTTP tests use the real FastAPI detection route for every positive prompt with no
punctuation and with a full stop. Negative tests retain conversational mentions,
filler and incomplete instructions. The existing bounded utterance buffer test uses
a fake clock for adjacent final assembly and expiry; no longer sleeps/timeouts or
weakened production limits. Existing cooldown/latest-pending and all three audio
source regression suites remain active in the complete run.

Remaining manual evidence: confirm the loaded checkout, observe a real final
transcript for "Design a URL shortener", and check its acceptance/answer in Auto.
That native/live scenario is not marked passed by mocked tests. Rule-based command
recognition is deliberately narrow; this does not claim perfect conversational
intent classification for every possible quoted or indirect instruction.
