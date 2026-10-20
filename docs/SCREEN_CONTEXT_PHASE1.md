# Analyze Screen Context Foundation — Phase 1

Date: 2026-10-18. Implemented locally; no live Electron/provider verification.

Phase 3 integration amendment: this foundation is now connected to runtime OCR.
The focused revision adds explicit fresh `reference` execution and controller-owned
`contextKind` (question/reference), preserved through continuation/retry and cleared
at boundaries. The existing evidence-only commit accepts validated reference evidence;
no minimal commit-payload relaxation or image persistence is introduced.
Stable batch item/replacement sidecars and bounded clarification-candidate resolution
were added narrowly to this controller. See [Phase 3](SCREEN_CONTEXT_PHASE3.md)
for current APIs, lifecycle integration and verification; the original foundation
scope below records the state at Phase 1 completion.

## Scope and ownership

`frontend/electron/screen_context_controller.cjs` is an internal, memory-only
main-process store. Existing OCR capture/request/commit, UI and history do not use
it yet. No new IPC, provider request, backend contract, storage, migration or
audio/gRPC change is introduced.

The controller separates accepted screenshot evidence, successful AI answers,
one pending contribution and an optional retry snapshot. Images are immutable
base64 strings owned by main, never broadcast overlay state. `prepareRequest()`
returns a frozen private-process snapshot; `metadata()` returns only safe IDs,
generation, revision, status, counts, limits and error codes. No credentials,
image contents, source text or answers appear in metadata.

## State and execution

- `adoptSession` captures a main-minted runtime ID, lifecycle generation, account
  generation and optional cloud ID. Same identity is a no-op; replacement disposes
  old context.
- `begin({action:'new'|'continue', operationId?, requestId?})` is execution only.
  No UI-option selection method exists. Future integration should pass existing
  operation/request IDs. New execution supersedes pending work and starts empty;
  failure does not restore a retired thread. Continue requires accepted evidence.
- A synchronous admission guard, full identity matching and base revision fence
  prevent competing continuations and duplicate/stale commitment.
- `registerImage` validates size/decoded pixels through an injected decoder and
  deduplicates bytes, not logical turns. `prepareRequest` freezes current input.
- `commitEvidence` accepts internally validated nonempty source text and a boolean
  completeness flag. `commitAnswer` atomically adds that evidence and a separately
  validated successful answer. Either advances revision once. Richer evidence
  parsing and backend response validation belong to later integration.
- `fail(token, {retryable:true})` may retain captured input within the same budget.
  `retryTurn` retains the logical turn, operation and frozen input, but changes
  request-attempt ID. Cancellation, New and session disposal invalidate retries.
  `cancelRetry` releases a retained failed candidate.
- `invalidate`/`dispose` fence callbacks before releasing controller references.
  Repeated cleanup is harmless. JavaScript cannot promise physical memory erasure.

This guarantees at-most-once local commitment, not exactly-once upstream execution.
No provider runs in this phase. History is neither supplied to nor deleted by
the controller; no older-thread resumption is available.

## Limits

Factory options configure limits; no unused environment variables are added.

| Limit | Starting value | Basis |
| --- | --- | --- |
| Distinct retained images | 6 | Confirmed starting requirement; pending/retry images count. |
| Compressed bytes per image | 10 MiB | Existing backend screen-upload ceiling. |
| Decoded pixels per image | 2,200 × 2,200 | Existing Electron capture maximum dimension. |
| Retained payload | 64 MiB | Provisional conservative UTF-16 base64/text accounting; about 24 MiB compressed images before evidence/answers. |

The payload budget counts unique image strings plus evidence/answer records.
Pending/retry snapshots share frozen records. It is not an exact V8/native heap
measurement: transient decoding/serialization allocations and object overhead
are outside the bound. Overflow rejects the candidate or whole commit without
evicting accepted evidence. Compressed-byte checks precede native decoding;
externally supplied images will need live decoder validation during integration.

## Lifecycle

Main adopts at startup completion. Cloud-session replacement invalidates working
context; a new runtime is adopted at its next startup completion. It is never
automatically resurrected by a delayed session-creation response.
An internal auth-manager callback invalidates before remote logout, active-session
ending, exchanged-account adoption and local auth clearing, and on verified
account/cloud-session replacement. Main invalidates before asynchronous finalization
and shutdown, and disposes when the owning main window closes. Remote failure
cannot prevent cleanup. No lifecycle hook here deletes answer history.

## Validation and deferred work

Behavioral Node tests exercise transitions, identity fences, retry immutability,
limits, private metadata, auth-manager lifecycle callbacks with fake adapters,
and failed main-process finalization. Existing frontend regressions exercise
OCR/menu/history, auth/startup and audio/gRPC paths.

Chooser UI, current OCR integration, backend response handling, contextual provider
requests, model/token budgets and live Electron/provider acceptance remain deferred.
Phase 1 does not make the overall multi-screenshot feature available to users.

Validation: all 431 frontend tests passed (including 15 new focused tests).
The repository audit with `-SkipBackendTests` passed: whitespace/staged-file
checks, backend compilation, frontend build, Electron syntax and 124 Extension
tests. The full audit reported repeated backend failures and was stopped after
stalling. A fail-fast rerun reproduced the first failure after 90 passes:
`test_generate_stream_primary_success_with_session_id_stores_transcript` reaches
`session_generation.py:234` with a dict instead of an object having `.status`.
Those backend files are unchanged by Phase 1; backend-wide validation is not green.
## Contract audit amendment — 2026-10-19

Working source records now retain validated supporting-image/replacement links and explicit reference kind; successful clarification remains separately labelled in bounded working memory. Commit authority enforces outcome completeness atomically. Storage remains append-only: each accepted turn adds exactly one evidence record and revision. Stable item origins were verified through repeated targeted/batch follow-ups and needed no redesign. See [audit and acceptance report](SCREEN_CONTEXT_CONTRACT_AUDIT.md). Saved history and cleanup boundaries are unchanged.
