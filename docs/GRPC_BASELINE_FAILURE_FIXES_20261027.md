# gRPC baseline failure fixes ? 27 October 2026

**Both reported failures are resolved.** This is separate from the completed lint cleanup and historical isolated baseline comparison. Only two test files changed; production App/session code is byte-identical to the start of this work. Existing uncommitted gRPC production changes were preserved. No applicable AGENTS.md was found in the inspected project/parent/frontend paths.

## Root causes and intended contracts

### Capture-start failure: outdated fixture state

`createGrpcAutoSession` subscribes to backend events, then awaits `mic.start()`. If capture start rejects, it reads current commit status, invokes `fail()`/`close()` and returns a failed session. Audio-track `ended` listeners are registered only after capture starts successfully. The old test declared `ended` without an initializer and assumed cleanup would always call its `removeEventListener` mock, setting it to null. On partial startup no listener was ever attached, so removal correctly does not occur and the mock variable stayed undefined.

The mock now initializes its empty listener slot to null. The final null assertion remains. Additional assertions require zero registrations on capture-start failure and one on track/backend failures, matching removals, identical removed listener identity, one mic close, one backend unsubscribe, one stream stop and one backend close. Repeated `close()`/`stop()` must return the same cleanup promise before and after completion. Late backend/ended callbacks cannot publish answers or trigger fallback/extra cleanup.

This corrects the fixture's representation of an absent listener; production does not promise to call removeEventListener on a never-registered listener. Production `createGrpcMicTest.stopCapture` fences its generation, clears pacing/queued work, closes/nulls capture and drops its stream reference; `ownsStream:false` leaves stream stopping to the combined-session owner. The outer App does not retain a failed session and preserves source-specific no-fallback behavior.

Changed: `frontend/src/grpc_combined.test.js` only.

### Permission wait: incorrectly synchronized fixture

App's Auto startup awaits `getGrpcRealtimeStatus()` to determine hosted capture before requesting microphone permission. The test invoked Start and immediately called the resolver that is assigned only when getUserMedia runs. Because startup had yielded at the status await, that resolver did not yet exist. This was not evidence of a production permission/cancellation failure.

The test now awaits a promise signaled by the fake getUserMedia implementation after its response resolver is assigned. It then invalidates the start token, resolves the late synthetic stream and awaits startup completion. No sleeps, microtask-count assumptions or polling loops. A one-second test timeout bounds a broken handshake. Existing assertions still require exactly one late-track stop and zero gRPC connects; added assertions require no stream/session reference retained. Production already checks the start token immediately after permission resolution and stops stale tracks before storing them.

Changed: `frontend/src/grpc_computer_auto.test.js` only.

## Verification

All commands ran locally. Exact argument vectors, cwd and exit codes are in `tmp/grpc-baseline-fixes/commands.json`; before-input snapshots/hashes and logs are retained beside it.

| Check | Result |
| --- | --- |
| Affected cases before editing, current code only (not a baseline rerun) | 2 failed, exit 1 |
| `node --require ./tmp/frontend-lint-baseline-comparison/current/no-network.cjs --test --test-name-pattern "combined capture-start failure|Stop during combined permission wait" frontend/src/grpc_combined.test.js frontend/src/grpc_computer_auto.test.js` after editing | 2 passed, exit 0 |
| Twelve gRPC/hosted-audio/router test files, `node --require <loopback-only.cjs> --test <files>` | **164 passed, 0 failed, exit 0** |
| `npm run lint -- --format json --output-file ../tmp/grpc-baseline-fixes/lint.json` from frontend | **0 errors / 12 existing warnings, exit 0** |
| `node --check` on each changed test | Both passed, exit 0 |
| `git diff --check -- frontend/src/grpc_combined.test.js frontend/src/grpc_computer_auto.test.js` | Passed, exit 0 |

The first expanded suite attempt used a deny-all guard: 163 passed and one real **localhost** socket test was blocked. That was a harness restriction, not a source failure. The corrected guard permits only loopback TCP/fetch/WebSocket destinations; external/provider destinations remain blocked. The entire 164-case lifecycle suite then passed. A console-encoding exception occurred while printing the successful run's Unicode tail; the subprocess log/recorded exit code remained 0 and were read back to confirm 164/164. This reporting exception did not change the test outcome.

No build was repeated for these test-only changes. No full CI command set was executed, so no full-CI pass is claimed. The 12 pre-existing lint warnings remain documented. No tests were skipped, assertions weakened, errors suppressed or lint settings changed.

## Preservation and review status

Historical isolated comparison inputs still match their saved hashes; its comparison was not repeated or overwritten. Five payment/email/callback provider execution journals match their historical hashes. No accepted payment, callback, installed-app, physical or staging acceptance was repeated. No providers, real emails, tunnel, migrations, credentials, deployment, commit or push.

Graphify's existing graph query traced `createGrpcAutoSession`, `startAutoMode`, permission and close relationships (63 related nodes, budget-limited view); direct source inspection established the current contracts. No model-based extraction or root-graph overwrite occurred. Graph navigation is historical, not runtime verification.

**These two failure fixes and the lint changes are ready for review.** The previously reported two Node blockers are resolved by the focused lifecycle suite, while full-CI status remains unverified. C11/C12/C13 are not closed. Razorpay support findings remain pending and provider execution paused.
