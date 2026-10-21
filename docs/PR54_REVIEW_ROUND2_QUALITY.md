# PR 54 second review: answer quality

Parent: `69cd862af2e305caea22edad3b254103a9ab92dc`. The actual publication remains one dependent series on `dev/current-work` to `main` (PR 54); A/B describe ownership of commits. Work is isolated; original files/index/environment bytes remain preserved.

## Verified findings and fixes

1. Streaming `needs_clarification` retrieved selected-resume evidence and could emit 409 before a non-generating clarification. Removed that branch's retrieval/enforcement. Existing pre-branch authentication/session authorization and managed dispatch/lifecycle checks remain. Production buffered/streaming parity tests assert local clarification, zero evidence/provider calls, and 401/404/409 rejection by existing auth/session checks.
2. `validate_personal_answer` classified mid-answer "in conclusion" as required meta output. Only this style phrase now has advisory `style_phrase` diagnostics; text is preserved. Empty output and genuine meta output remain required failures, leading wrappers still sanitize, and grounding/correctness checks remain unchanged. Actual helpers are tested through normal, ResumeIndexError and JobContextError paths. Success testing uncovered duplicate project-metadata keywords in the ResumeIndexError response constructor: removed four duplicates already supplied by `_session_context_metadata`, restoring successful recovery without changing their values.
3. Project-aware retrieval accepted experience/work_experience/internship, but chunking did not stamp stable identity there. Both now import one shared section policy from the existing index service, including existing project aliases. Long experience paragraphs retain their origin across continuation chunks; partial matching and genuine multi-entry ambiguity are tested. Existing JSON metadata storage needs no migration. Old rows without identity still use conservative title fallback; arbitrary old continuations are not guessed or rewritten. No hosted reindex/backfill occurred.
6. Prior general-question fix is already present: all three answer-generating `_require_selected_resume_context` calls receive the request-local plan. Added real buffered, HTTP streaming and job-context recovery tests for selected-resume deadlock/no-match generation, plus missing-project buffered/streaming 409 tests with zero provider calls. No irrelevant fallback chunks were restored. Managed routes continue to use this common endpoint.

## Evidence

New regressions on the pre-fix head: 10 failed, 10 passed. Current round-two module independently: 25 passed. Focused quality/resume/grounding regressions: 226 passed. Round-two plus diagram modules on Python 3.11.9: 90 passed. Complete suite and actual normal-hook results are recorded in the PR after execution; no historical counts are substituted.

Changed files: `backend/app/api/generate.py`, `backend/app/cloud/cloud_resume.py`, `backend/app/nlp/answer_generator.py`, `backend/app/services/resume_index_service.py`, `backend/tests/test_answer_review_round2.py`, `backend/tests/test_answer_streaming.py`, this record.

All providers, storage/retrieval boundaries and credentials are synthetic/offline. No runtime environment edits, providers/STT, hosted queries, activation or migrations. Recovery hardening remains paused.

The full-suite pass initially found an old test deliberately expecting clarification to fail on evidence retrieval (and using an incomplete follow-up stub). Its negative protocol case now uses an actual answer-generating question and still requires start/error/done with 503, no delta/metadata, and the existing incomplete=false semantics for an answer that never began; the separate real clarification parity tests assert zero evidence/provider calls. The initial full run failed this one obsolete expectation (1 failed, 1686 passed); it is not recorded as a pass.
