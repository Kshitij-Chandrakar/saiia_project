# C15.5 PR 72 review fixes

17 November 2026, Asia/Calcutta. Review baseline `20404e0`; dependent UI baseline `46e2e60`. Local synthetic verification only. Production/admin activation defaults, coupons, emergency recovery and provider boundaries remain unchanged. No shared/hosted migration or real retirement was executed.

## Corrected behavior

- Disabled cancellation dispatch fails closed without terminating the worker. Recovery calls the existing idempotent billing cancellation entry point so a crash before durable cancellation intent cannot strand an operation. Exhausted leases become explicit failed/unknown outcomes, and already-authorized results survive later staff/configuration changes.
- Telemetry accepts string/list/nonobject nested provider fields, records asynchronous attempts off the event loop, and classifies returned AssemblyAI errors as failures. Billing authorization runs in the existing thread pool. gRPC distinguishes actual restrictions (403) from unavailable authority (503/other failures).
- Membership/access/privacy receipts bind actor, reviewed operation and action. Retained receipt identities cannot create replacement reviews after ephemeral review cleanup. The eligibility migration asserts its restriction patch. Session/history retry tasks are visible even without an account-deletion request.
- Coupon cleanup records its actual count. Terminal command retention starts from its maintained terminal-update timestamp. Expired obsolete audience reviews cannot expire newer campaign revisions.
- Campaign lease exhaustion terminates deliveries and completes otherwise stranded campaigns. Finish records provider facts under its existing lease, without reclassifying an accepted send as skipped after eligibility changes. Null acknowledgements preserve previously stored correlation IDs.
- Successor access verification requires both the transferred Super-admin role and its accepted membership revision. Population baselines count at coverage start; historical population results outside retained coverage are unavailable, not fabricated totals.
- Administration exports emit individual bounded records, preserving category arrays and the version/exclusion header. The existing row/archive size and entry limits still fail explicitly without truncation.

## Restore snapshot contract

The existing external checkpoint/witness interface selects an authenticated complete snapshot by encrypted-file hash and a UUID file identity. Each snapshot is versioned, environment/dataset-bound, and split into at most 512 KiB row batches under the existing 1 MiB encrypted-event bound. A complete-state digest and part count validate reconstruction. One snapshot has a bounded 128 MiB engineering limit; exceeding it quarantines rather than truncating evidence.

Publication writes a new immutable encrypted file before advancing the independent checkpoint. Database serialization precedes a fresh witness read. Only after successful witness acknowledgement may cleanup verify and remove the selected snapshot's authenticated predecessor; an unacknowledged concurrent candidate is never pruned by a filename sweep. A previous complete append without acknowledgement is recoverable on the verified live source without restarting, only with the expected predecessor head, source generation/snapshot and matching database state. Pending evidence blocks readiness; rollback, missing evidence and tampering fail closed. Legacy journal records remain readable. Restore merges cannot clear an existing customer restriction or reduce its revision. New local checkpoints include the fixed admin fields; older HTTP authorities require an explicit authenticated operator schema upgrade before admin publication.

These local files and the local HTTP witness rehearsal do not establish production-independent durability. Hosting, independent witness provisioning, key recovery and source fencing remain deployment acceptance requirements.

## Verification

- 40 focused Python tests passed, including real loopback gRPC permission/unavailability mapping; worker-thread recording, malformed nested provider output, cancellation recovery and AssemblyAI failure classification.
- The large-state test publishes three 100,000-restriction snapshots, verifies exact reconstruction beyond the old event/lifetime limits, and checks rotation, interrupted acknowledgement and tamper denial.
- Actual local-engine/native rehearsal: 24 scenario groups passed on `run-06`, using the pinned PostgreSQL 17.11, GoTrue 2.197.0, Storage 1.81.0, PostgREST 14.18 and Mailpit 1.27.11 images. Fixed-operation assertions use separate restricted LOGINs; owner writes are explicitly synthetic fixtures. Payment and delivery mutations remain fake/local only.
- Added native regressions cover receipt collisions, history retry projection without deletion, exhausted command/campaign leases, post-dispatch authority changes, ordinary coupon cleanup counts, terminal clocks, obsolete reviews, successor role/revision loss, old metric windows and monotone restore restrictions. Export acceptance includes all 6,000 synthetic attempt records and a valid archive, with each record below the configured row limit.
- Backend-only execution records browser/composed website acceptance as skipped when the dependent UI inputs are absent. This is intentional slice independence, not actual browser acceptance. Existing unchanged browser evidence remains distinct.
- Scoped Ruff and Black checks plus Python compilation passed for the new/rewritten modules. Normal repository commit audit is required; its final results are reported with the review update.

The subsequent five CodeRabbit follow-ups are covered by focused tests and a fresh local-engine run: witness CAS/pruning concurrency, fixed checkpoint schema and operator upgrade, live pending-publication recovery, dedicated telemetry executor under default-pool saturation, and old-created/recent-verified population. The exact run result is recorded in the new evidence directory; no production restore authority or deployed telemetry was exercised.

Evidence is preserved locally under `docs/evidence/c15-5-review-fixes-20261117/` and excluded from the PR. Earlier unsuccessful runs remain historical. Final cleanup records no owned containers, volumes, networks, published ports or temporary secret files. The reusable rehearsal runner image was built from the pinned existing base with `svix==2.9.1` from official PyPI; no operational credentials were loaded. Original authoring worktree/index and protected leftovers are untouched.

## Review order

PR 72 remains the backend prerequisite; this fix adds the billing-adapter caller correction, focused regression module, native scenario helper and this report. PR 73 keeps the same 66 UI/documentation paths after a normal merge of its updated backend parent. Both reviews remain below 100 files. No merge or production activation is authorized by this report.
