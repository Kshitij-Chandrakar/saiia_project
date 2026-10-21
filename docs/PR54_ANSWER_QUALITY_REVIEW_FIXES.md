# PR 54 answer-quality review fixes

Parent: `c21c69d66b2b3b836df4ba243867c39f230ad07a`. Publication remains one PR, `dev/current-work` to `main`; A/B denote dependent commit scopes, not separate PRs. Original working files, environment bytes and staging remain untouched in the original checkout.

## Confirmed findings

- CI jobs `119202917524` and `119202849986`: Python 3.11.17 importlib imports `backend/tests/test_answer_diagrams.py`; line 9 imports `app.api.answer_diagrams`; final exception is `ModuleNotFoundError: No module named 'app'`. Application code was never reached. The offline CLI previously inserted backend paths, masking collection order dependence. Reproduced independently on Python 3.10 and 3.11.9 from a clean worktree. Portable pytest conftest now installs the existing offline boundary and paths before application collection, without requiring another test to run first. Unexpected external calls fail closed; credentials are synthetic.
- A: selected-resume authorization/retrieval still executes, but general plans forbidding personal evidence no longer require irrelevant matching chunks. Personal, behavioral and project requirements remain strict. HTTP generation with a selected resume and no deadlock evidence is covered.
- B: project paragraphs now carry stable project-title metadata across continuation chunks, through cloud JSON metadata and matching. No schema migration/reindex is required for existing rows. Legacy rows lacking this optional identity retain conservative title matching; identity cannot safely be reconstructed for arbitrary old continuation prose, so those ambiguous old chunks can still require a normal future rebuild. Distinct ambiguous projects remain rejected.
- C: code-only rewrapping removes an existing trailing unverified warning before code extraction and appends one warning outside the final fence. Fenced and unfenced provider outputs are tested.
- D: empty/meta output remains required failure; broad keyword/style flags are diagnostic warnings, not claim-level grounding proof. A science-project childhood story is not rejected merely for a keyword. Required failures map to the same safe HTTP error in normal, resume-index-error and job-context-error paths. Existing semantic/grounding validation remains in place; this is no factual guarantee.
- H: shared offline startup makes affected modules independently runnable. Effective-prompt capture explicitly enters its own offline context before calling production capture.

## Verification

Pre-fix worktree with new quality regressions: 9 failed, 17 passed; current focused quality/reliability tests: 26 passed. Each affected module independently passed: intent/presentation 31, closeout 9, Phase 3 32, Phase 4 31, Auto acceptance 28. Python 3.10 full unfiltered suite: 1,655 passed, 2 skipped. CI command `python -m pytest backend/tests -q -k "not openai and not openrouter"`: 1,568 passed, 2 skipped, 87 deselected on Python 3.10.

The first local Python 3.11 full run collected correctly but exposed a pre-existing 200ms real-clock deadline fixture failure before either fake provider was called (1 failed, 1,567 passed). That fixture now uses the production budget with an explicit fake clock and a gated stalled primary, verifies 160ms remaining for fallback, and keeps production settings unchanged. The focused Python 3.11 deadline test passed. Final full Python 3.11 and normal-hook outcomes are recorded in the PR after execution.

Local Python 3.11.9 is not the Linux CI runner's 3.11.17. A disposable venv pins relevant API/test dependencies to repository versions, but is not a claim of an identical Linux dependency environment. Remote CI is the authoritative check for that runner. No broad retries, test skipping or production deadline increase was introduced. Earlier Python 3.11 streaming-fixture unraisable warnings remain outside these fixes and are reported rather than represented as passed lifecycle guarantees.

No live providers, audio, hosted queries, migrations, feature activation or real environment edits. Recovery hardening remains separately paused.
