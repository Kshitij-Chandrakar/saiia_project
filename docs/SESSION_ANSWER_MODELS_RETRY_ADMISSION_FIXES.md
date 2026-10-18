# Checkpoint Retry and admission transitions

2026-10-18. Both supplied CodeRabbit findings confirmed against source and fixed without schema or runtime configuration changes.

- Track acknowledged and recovered checkpoints separately from a persistence error. Known checkpoint/completed recovery stays save-only; completion failure never calls the provider again.
- Unknown checkpoint outcomes require bounded durable claim reconciliation. A processing row is failed using only the original owned token, then read again: only an observed failed state permits generation_failed and an incremented-attempt Retry. SQL fail is processing-only, so a late checkpoint survives a no-op fail and remains save-only. RPC acknowledgement alone is not proof of failed state.
- stale_attempt never triggers fail/cancel of newer work. Reconciliation/fail RPC failure yields generation_uncertain with no regeneration Retry, preserving durable state. Existing 120-second processing leases eventually fence abandoned work into uncertain state. This does not guarantee exactly one upstream execution after crashes.
- HTTP bridge/renderer preserve the typed uncertain result, clear provisional text, and withhold Retry rather than presenting pending save as known success or known failed generation.
- Catalog refresh clears staleSelection when admission becomes legacy or closed. Enabled admission still requires explicit reselection. Closed admission blocks creation and exposes Refresh models so reopened admission can be checked without restarting setup.

Regression coverage includes rejected checkpoint, response loss before/after commit, late checkpoint racing fail, completion failure/lost response, failed fail-RPC, unavailable reconciliation, stale fences, save-only Retry and single final persistence. Providers/storage are mocked in handler tests. The local PGlite script executes real SQL proving processing-only fail, stale-token isolation and single saved transcript; network loss is simulated, not hosted transport validation. Browser/isolated Electron tests cover admission transitions and genuine stale-model reselection through the actual setup component.

No migration is added or edited. Hosted application of the earlier additive `20261018210000_harden_session_generation_recovery.sql` remains paused pending completion of CodeRabbit review. The original applied migrations remain unchanged. No provider calls, recording, hosted migration, runtime setting change, push or unrelated work is included.

Independent feature-only snapshot results: **1036 backend tests passed**, 2 skipped, 86 deselected, 5 existing SWIG warnings (38.00 s); **29 focused frontend tests passed**; **12 rendered tests passed**; **all three isolated SQL scripts passed**. Normal hooks remain enabled. No hosted migration was applied.
