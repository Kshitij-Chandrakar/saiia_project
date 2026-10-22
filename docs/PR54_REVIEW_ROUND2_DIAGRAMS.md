# PR 54 second review: diagram history and schema disposition

This follows the quality fix on the existing `dev/current-work` to `main` PR. Diagram generation remains disabled and migrations remain unapplied.

## History isolation

Confirmed: one invalid row threw out the entire history page. The bridge now validates that the response is an array; malformed response envelopes still fail safely. Each of the first 50 rows is independently checked for non-null, non-array object shape, string UUID, nonblank string question/answer and authoritative 4000/24000 Unicode-code-point bounds. Invalid rows are skipped; valid canonical strings are returned unchanged, never truncated or hashed after truncation. An entirely invalid array yields an empty usable result, without malformed content. A raw-page `has_more` hint preserves navigation when filtering removes entries; the history consumer retains its existing fallback for older snapshots without this hint.

Tests cover null/non-object rows, invalid ID types/values, non-string text, oversized/non-BMP text, mixed valid/invalid entries, entirely invalid results, malformed arrays and maximum valid canonical text. A rendered test confirms a full filtered page can navigate to valid saved answers on the next page without generating a diagram.

## Repeated strict-schema finding

Previously evaluated, rechecked against current official documentation on 2026-10-21:

- https://developers.openai.com/api/docs/models/gpt-4.1-mini confirms this exact model supports Responses and Structured Outputs.
- https://developers.openai.com/api/docs/guides/structured-outputs documents the supported subset and expressly lists additional string-keyword restrictions for fine-tuned models. The configured service accepts only the base `gpt-4.1-mini` alias or dated base snapshots, not fine-tuned IDs.

No blanket removal of minLength/maxLength was made. Those pages do not provide an explicit GPT-4.1-mini per-keyword acceptance matrix, so the review's rejection claim is unconfirmed rather than falsely resolved. Mock request-contract tests now run both the actual base alias and configured dated snapshot, verify strict Responses text.format, exact emitted schema/length/pattern/array bounds, store=false and no tools, and retain full local rejection tests. Mock acceptance does not prove live upstream schema acceptance. The review thread is left open with this limitation; no provider call is authorized or made.

## Verification and inventory

Independent diagram module: 65 passed; Python 3.11 round-two plus diagram modules: 90 passed. Frontend non-browser suite: 687 passed. Rendered diagram/presentation/streaming tests: 19 passed. Registered `npm --prefix backend/tests test`: all four isolated SQL scripts passed; no SQL or migration files changed. Final build/hooks/remote CI are reported after execution.

Changed files: `frontend/electron/answer_diagrams.cjs`, `frontend/src/components/DesktopAnswerHistory.jsx`, `frontend/tests/answer_diagrams.test.cjs`, `frontend/tests/answer_diagrams.browser.test.mjs`, `backend/tests/test_answer_diagrams.py`, this record.

No real environment changes, hosted queries, live providers/STT, activation, migrations or recovery-hardening changes. Native Windows/live semantic acceptance remains separate.
