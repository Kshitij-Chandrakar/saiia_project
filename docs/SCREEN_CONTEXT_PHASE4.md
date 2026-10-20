# Analyze Screen Phase 4 — lifecycle and concurrency hardening

2026-10-19. Phase 4 implementation is complete locally. Native Windows and live-provider acceptance remain pending. Phase 5 is not started. No migration, permanent screenshot storage, provider change or saved-history deletion.

## Confirmed defects and changes

- Queued renderer commands previously had no expected lifecycle fence. Execute, Retry, clarification and Screen-only Stop now carry runtime generation, thread, revision and current request identity. Main validates synchronously before mutation. Bounded command IDs make repeated OCR delivery idempotent; Retry still mints a new attempt for the same frozen logical turn.
- A successful main commit could lose its notification, leaving the renderer without the result. A bounded main-memory delivery queue now commits atomically with an answered turn, inside the existing retained-byte/turn limits. Status can replay current-thread deliveries; React acknowledges after its history state commits. History/request identity and operation identity suppress duplicates. A notification exception cannot turn a valid commit into failure. A later Stop preserves a completed commit; New/reference/session invalidation removes pending delivery for obsolete context.
- Old capture cleanup could restore overlay visibility after explicit hiding or lifecycle disposal. Capture remains serialized through restoration, checks ownership before native work, and restores only the same live window/lifecycle. An overlay visibility-intent generation prevents obsolete restoration.
- Uncooperative transport/auth promises could retain the active local pipeline after cancellation. Abort-aware waits detach local processing and cancel a late response body. Native capture stays serialized until cleanup; ownership rejects its delayed image.
- Queued startup could reopen admission during asynchronous logout/session finalization. Main closes admission synchronously using ending/logout latches before finalization. Old catch/finally blocks affect only their own attempt/timer.

## Existing protections verified and preserved

The controller already owned immutable retry snapshots, exact clarification linkage, append-only evidence revision, one active logical turn, session/account generation, memory limits and stale commit rejection. Backend output/authentication/semantic contracts remain unchanged. Clarification never commits. Failed New/Passage stays fresh and empty; Continue failure preserves accepted context. Three-choice selection remains passive. Existing cloud-session-ended React handling checks the current cloud session and uses current Auto/manual cleanup before clearing ownership; a delayed Session A event cannot clear B. Existing local end/logout/account replacement/owner-window close/shutdown invalidate before asynchronous finalization. No changes to unrelated audio/gRPC behavior were required.

## Ownership map

| Resource | Authoritative owner and guard |
| --- | --- |
| Runtime/account/cloud identity | Main/controller adopted session and generation; invalidate before finalization |
| Thread/revision and accepted evidence/answers | Controller; exact token/base revision, append-only commit |
| Logical turn/operation/request attempt | Controller token; Retry preserves turn/operation, changes request |
| Native capture | Executor serialized queue; current-attempt check plus window restoration lifecycle |
| Upload/transport | Executor attempt AbortController and deadline; abort-aware waits |
| Retry and clarification | Controller frozen snapshot; executor exact clarification request linkage |
| Delivery | Controller memory queue; exact identity acknowledgement, cleared at context boundary |
| Renderer/history | Fresh main status sequence and lifecycle, operation/request dedupe, existing history append |
| Backend resources | Existing endpoint slot/deadline/disconnect task; shielded worker/upload cleanup |

## Transitions

| Trigger | Synchronous action | Late completion / retained state |
| --- | --- | --- |
| Open/select/dismiss chooser | No context mutation | Existing work continues |
| Execute New/Passage | Validate fence; supersede attempt; replace thread | Old result rejected; failed fresh context remains empty |
| Execute Continue | Admit one turn on accepted snapshot | Failure keeps accepted context |
| Retry/clarification | Validate current fence and exact pending linkage | Reuse image; one attempt admitted; no duplicate commit |
| Stop | Invalidate pending turn before abort | No later context/UI/history mutation; prior valid commit retained |
| Valid answered result | Validate ownership, atomically commit evidence/answer/delivery | Renderer replay, then history acknowledgement |
| More content/reference accepted | Commit genuine evidence only | No answer/history delivery |
| Session/account/owner disposal | Close admission; invalidate; clear buffers and pending delivery | Old IPC/result rejected; async finalization cannot reopen old lifecycle |
| Renderer remount within live owner | Subscribe once and request fresh status | Replay only unacknowledged current-thread delivery |

Owning native-window disposal retains the existing policy: working context is disposed. This queue does not restore sessions after app restart, retain acknowledged renderer history across full reload, or change saved/cloud history retention.

## Resource/security audit

The backend already bounds two contextual requests per worker, upload/image sizes, provider duration and endpoint duration. Multipart objects close in shielded cleanup; disconnect handling cancels and joins request/watcher tasks; image-worker cancellation signals and awaits owned work before releasing admission. Tests cover cleanup and decoding limits. No global conversation/cancellation store is added. Aborting transport cannot guarantee provider cancellation or avoid billing. Electron native capture already in progress cannot be forcibly stopped; its queue remains occupied until cleanup. Development diagnostics remain safe codes, identities/generations, counts and ownership outcomes, without source/answer/image/credential content.

## Verification

- `node --test` over all frontend `*.test.js`: **602 passed**, including 14 deterministic Phase 4 regressions. Covers before/during capture, transport, post-validation cancellation, New/Passage supersession, stale commands, notification failure, exact acknowledgement, session boundaries, obsolete visibility and startup admission. Existing suites cover frozen double Retry, stale clarification, account/session replacement, matching cloud-end Auto/manual cleanup, passive selection and normal/batch flows.
- Backend contextual/OpenAI/OpenRouter/auth selected suites: **184 passed**. Full broader backend suite was not run; earlier phase records' baseline failures are historical, not newly reproduced here.
- Repository `pre_commit_audit.ps1 -SkipBackendTests`: passed, including Vite build, syntax/compile/whitespace checks and **124 Extension tests**.
- Playwright real React views with mocked capture/provider: **10 passed**, covering normal continuity plus missed-notification/acknowledgement recovery. Final run: `tmp/phase4-browser-final.log`. These tests do not establish native Windows capture or live model behavior.
- Graphify incremental update/query run before and after the change; generated graph is navigation evidence, actual source/tests establish behavior.

## Manual acceptance still required

1. Start Electron normally. Execute New, Passage then Continue; verify count, reference/diagram continuity and prior-answer follow-up. Saved history stays available.
2. Stop during window hiding/capture and during generation. Wait for a late completion: no count/answer/history change and Retry stays unavailable. Explicitly hide overlay during capture; it must not reopen unexpectedly.
3. Double-click OCR/Retry: one active attempt, Retry reuses image, one history entry. Select New/Passage while processing (passive), then execute it: old response cannot overwrite the replacement.
4. End local/cloud session during capture and generation, including failed cloud finalization; context clears immediately. Switch A to B then deliver A's ended event; B stays active. Repeat logout/account replacement.
5. Exercise Auto/manual session end, Chat/audio Stop isolation, native owner-window disposal/recreation and app shutdown. Check no stale result/subscription or restored obsolete window. Measure native resource/latency behavior separately.

## Rollback

Review/revert only Phase 4 hunks and its new tests/record, keeping existing Phases 1–3 and unrelated uncommitted changes. Main/preload/renderer changes must ship together. Restart releases temporary memory. No database rollback or history deletion is needed.


## Commit preparation verification (2026-10-20)

On the synchronized `dev/current-work` base, the complete frontend Node suite
passed **659 tests**; contextual plus legacy OpenAI/OpenRouter backend suites
passed **163 tests**, and mocked real-view browser acceptance passed **10 tests**.
No physical capture or live-provider acceptance was performed.

The first normal commit hook exposed existing legacy tests inheriting the local
session-model setting and a Windows CRLF-sensitive generated-code comparison.
Separate test-only commit `6015770` pins legacy routing inside those test modules
and compares generated Python text with normalized newline handling. Runtime
configuration, model routing and generated protobuf files are unchanged.
After that correction the normal audit passed **1,280 backend tests**, with
2 skipped, 88 deselected and 5 existing Swig warnings, plus production build,
Electron syntax, compile/whitespace checks and **124 Extension tests**. Earlier
phase counts above remain historical evidence. Native Windows/live-provider
acceptance and Phase 5 remain pending.
