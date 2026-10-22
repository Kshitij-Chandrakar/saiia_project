# Answer-quality and optional-diagram review handoff

This record supersedes the historical patch inventories in Phase 7, without changing their historical results. Parent: `bff9827ab7ebbcfb560dcac5178a9391f530c5a9` (merged audio, streaming and Screen fixes retained).

Publication: one PR from `dev/current-work` to `main`, with two dependency-ordered commits. A contains 38 files; B contains 47 files; the series has 84 unique files. The shared `backend/app/api/generate.py` contributes quality changes in A and trusted server-save provenance stamping in B. B depends on A's answer policy and safe AnswerText renderer.

Subsequent fixes included: conceptual explanation versus architecture intent; safe Markdown presentation; imperative design/build/implement Auto acceptance; and source-lookup pending/schema-unavailable handling, confirmed-save gating and duplicate-request coalescing. The actual hosted cause of the reported 503 remains unverified without runtime evidence.

The unrelated C6 startup plan, G9 routing record, model closeout record and existing content-protection comment are excluded. Original working files, environment files and staging are preserved; commits are prepared in isolation.

## Verification

Current isolated verification results are recorded below before publication. Offline synthetic fixtures and application-local ordering establish implementation behavior, not human-rated answer quality or live-provider latency. DOM assertions do not measure painted frames. PGlite SQL coverage does not establish multi-connection PostgreSQL concurrency.

## Activation remains separate

Diagram generation remains disabled. Prepared migrations, in order: `20261021120000_add_answer_sources.sql`, then `20261021130000_add_answer_diagrams.sql`; neither is applied. The recovery-hardening migration remains separate and paused. No provider calls, hosted queries, environment edits or activation are part of this review.

Before activation, obtain separate approval for hosted migration application, configuration activation and bounded live-model evaluation. Human blinded quality review, diagram semantic faithfulness, real PostgreSQL concurrency and packaged Windows/native Electron acceptance remain pending. Disabling diagram generation preserves saved reads, trusted provenance and session answer-model bindings.

## Current isolated results (2026-10-21)

- A: `python -B backend/scripts/answer_quality_baseline.py --tests backend/tests -q --tb=short`: 1,588 passed, 2 skipped (74.98s).
- A: `node --test` over all non-browser frontend test files: 670 passed. `node --test frontend/tests/answer_stream.browser.test.mjs`: 3 passed.
- A actual normal commit hook: 1,501 passed, 2 skipped, 87 deselected under its standard `not openai and not openrouter` expression; production build, compile, Electron syntax and extension validation passed. Commit `a6c9d32`.
- Combined: same offline backend command: 1,642 passed, 2 skipped (80.32s); all non-browser frontend tests: 683 passed.
- Combined browser command: `node --test frontend/tests/answer_diagrams.browser.test.mjs frontend/tests/answer_stream_phase3.browser.test.mjs frontend/tests/answer_presentation.browser.test.mjs frontend/tests/screen_context.browser.test.mjs frontend/tests/answer_stream.browser.test.mjs`: 31 passed.
- `node backend/tests/answer_diagrams.postgres.mjs`, `node backend/tests/session_generation.postgres.mjs`, `node backend/tests/transcript_deletion.postgres.mjs`: all passed against isolated PostgreSQL-in-WASM. Diagram migrations exclude the paused recovery migration; the pre-existing generation fixture's separate isolated setup is not a new deployment dependency.
- Protobuf source/copy byte parity, diagram Electron syntax, Dagre dependency resolution and `git diff --check`: passed. Scoped secret-pattern scan reports counts only; no credential values are logged.

Tests run through the existing offline harness with synthetic credentials, isolated storage and unexpected external calls blocked. The unchanged normal hook uses a process-local Python launcher wrapping pytest/compileall in that same offline context, with explicit pytest-asyncio/anyio plugins. Node uses the existing loopback-only fixture through process-local `NODE_OPTIONS`. Existing installed Node modules are junctioned into disposable worktrees; no dependency installation occurred. These overrides do not edit runtime flags or real environment files.

B's normal hook and final publication result are reported in the PR/final report after execution. No skipped hook is represented as a passed check. Original local `dev/current-work` and index remain at the parent while the remote branch receives the isolated commits; this intentionally preserves the original working-tree interpretation.
