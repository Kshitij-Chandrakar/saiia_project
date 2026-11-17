# C15 production restore journal, witness and fencing proposal

31 October 2026, Asia/Calcutta. **Proposal only. No infrastructure provisioned, provider/region selected, remote settings changed or production activation authorized.** Owner confirmed in this stage: frontend/backend remain local; **no production host or data region is approved**. Continue independent local work. This supersedes any inference from illustrative hosting choices in architecture documents.

## Known facts and missing inputs

Canonical policy is `C15_APPROVED_POLICIES.md`: irreversible accepted confirmation, immediate restriction, 24-hour primary cleanup target, category-specific 90/180-day clocks, permanent exact-email suppression, restricted unresolved billing exception and Product Owner review at least every seven days. Financial, processor, backup and restoration-marker lifetimes remain separate. Do not reuse the old deletion proposal's superseded “all periods provisional” sentence as current policy.

Last owner-confirmed platform facts in `SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md` (25 October) describe staging Free, no included scheduled project backups and PITR not enabled. They are dated owner evidence, not a new Dashboard inspection. Current owner confirmation says application hosts remain local. External dumps, log drains/TTL, object versions, caches, processor retention and future production recovery topology remain unknown. No real customer data or operational credentials are needed to resolve these deployment facts.

The local checkpoint implementation has authenticated journal/head comparison, source sealing and readiness tests; **local SQLite files do not establish independent production durability**. See `C15_RESTORE_CHECKPOINT_LOCAL_IMPLEMENTATION.md` for exact limits, including the accepted-decision/publication window and direct-service boundaries.

## Recommended topology and alternatives

Prefer a small **managed independent acceptance/journal authority**, outside the product Supabase project, product host and their restore/administrative failure domain. It needs transactional append + conditional current-head advancement, encrypted journal records and durable idempotency receipts. Use an independently protected **current-head anti-rollback anchor** controlled by the deployment/recovery plane, excluded from every product and journal restoration set. Exact provider and region remain unselected.

The authority may use a supported transactional database behind a narrow service: one fixed append/lookup/CAS protocol, rather than a collection of unrelated queues and object stores requiring invented distributed transactions. The anchor must supply authenticated monotonic observations/conditional updates that survive an authority restore. The normal product application must not be able to rewind either store or provision a new empty authority for an existing dataset.

| Placement option | Practical consequence | Decision before selection |
| --- | --- | --- |
| Independently managed authority and protected deployment-plane anchor — recommended | Less operational storage/replication burden; still requires separate access, restore controls and tested durability. A second project under the same bulk-restore credentials is insufficient. | Approved application host/region, independent operator ownership and acceptable managed-service recovery guarantees. |
| Independently operated durable service on a separate control host/failure domain | Feasible where deployment/region constraints require it, but the operator owns replication, backups, monitoring, recovery and independent freshness protection. A lone local disk on the product machine is insufficient. | Named operator/on-call responsibility, separate storage/backup domain and demonstrated recovery capability. |
| Product DB, product VM disk, current staging project or files restored with the application | **Reject as authoritative witness.** Restoring the dataset can erase newer decisions and the supposed proof of freshness together. | No configuration can turn a co-restored file into independent evidence. |

No cost, service tier, region or provider capability is assumed. Vendor evaluation should test this protocol and failure model, not choose components by name first. Do not deploy the local file adapter as the production authority.

## Record and identity contract

Each accepted decision has an opaque idempotency/request ID, verified subject reference, scope/policy version, authoritative accepted timestamp, subject restriction generation, minimized keyed email-suppression material and source classifier/version. No password, session credential, OTP, private result, filename or raw email belongs in the independent journal. Retained UUIDs/keyed identifiers are pseudonymous personal data, not anonymous. Billing linkage stays separately restricted; the witness needs no payment credentials.

Journal records are versioned, authenticated/encrypted, sequenced and linked to prior head. Bind every record/receipt/head to environment and dataset identity. A cutover receipt also binds **new restore generation** and an independently verified **manifest of actual DB and object snapshots**: immutable snapshot identifiers, source generations, cutoffs, object version/checksum manifests and complete recovery-source inventory. An operator-entered UUID alone does not attest which bytes were mounted.

Current-head reads must come from the protected current authority/anchor, with sufficient consistency for compare-and-swap. A valid signature over an old head is not freshness. Compare journal head, independent anchor and acknowledged decision coverage; truncation, unknown tail, rollback, mismatched identities or unavailable current evidence keeps service quarantined. If *every* trust root is rolled back together, cryptography alone cannot detect it; the operational separation and independent anchor are mandatory, not a promise from a hash chain.

Keep publisher, application-readiness reader and recovery coordinator credentials separate. Publishers may append a validated decision for the correct environment and use conditional head advancement; no arbitrary overwrite/delete. Readers may inspect safe coverage/restriction evidence, not export raw journal contents. Recovery credentials may create a new cutover generation and run the fixed replay contract; no customer/admin HTTP shortcut. Key recovery requires independently protected versioned key material, audited access and restoration testing; losing keys must quarantine rather than silently initialize an empty journal.

## Close the acceptance/publication window

Do not merely schedule a best-effort outbox after the existing DB-accepted response. If that DB is lost before publication, a later restore cannot reconstruct a decision that never reached independent storage.

Recommended protocol to implement in a **later separately reviewed stage**:

1. After verified identity, fresh proof and final typed confirmation, the product transaction records a **provisional restriction and pending independent acceptance**, with a stable request/revision and outbox. It must not yet claim irreversible acceptance or cleanup completion. Existing direct DB/Storage access must already respect that provisional restriction.
2. The authority validates the bound request and durably commits the authoritative accepted decision and journal head using its clock/idempotency contract. This is the proposed authoritative acceptance point. It preserves the same policy: no undo after acceptance, and the 24/90/180 clocks derive from that accepted timestamp, never a replay timestamp.
3. Advance/confirm the independent anchor and retain an idempotent authenticated receipt. Only a covered, independently durable accepted outcome may be reported as accepted; uncertain transport returns pending/unknown and resolves the **same** request. An authority/anchor disagreement quarantines recovery; it is not an excuse to invent a new request or discard a committed decision.
4. Materialize the accepted receipt into the product DB restriction/outbox/tasks, using the authoritative timestamp/revision. If the DB commit/response is uncertain, restriction remains; replay recovers the same accepted request. Late writes/jobs/callbacks consult the authoritative restriction/generation and the existing account locks/commit fences.

There is no claim of an atomic transaction across product DB, journal service and anchor. Each uncertain boundary has a durable identity and fail-closed reconciliation. The ordering and all ingress barriers must be proven before changing the existing acceptance API. An outage must not produce a false “accepted”, “fully erased”, cancellation or refund result. Repeated typed confirmation must not create another irreversible request or authorization interval.

## Restore cutover and mandatory readiness

1. The deployment plane issues a new generation and fences **all old source** HTTP, direct Auth/REST/Storage, gRPC, queues, scheduled workers, export publication/download and provider callbacks. Cancel or finish active work under existing leases/fences. Record the cutoff and old-generation writer acknowledgements; a UI checkbox is insufficient.
2. Freeze confirmation/history-deletion acceptance while draining the live source outbox to the authority and checking complete coverage. Compare all accepted decisions, not just rows already bearing a checkpoint. Commit source quarantine before acknowledging a seal. Calls arriving after the cutoff are denied or durably quarantined; no writer may acknowledge a decision solely into a source that will be discarded.
3. Mount the selected DB/object snapshots in an isolated maintenance dataset. Independently verify the actual manifest and environment/dataset/generation. Obtain the current witnessed head from outside the restored inputs; never trust their old ready flags or co-restored journal.
4. Replay restrictions, permanent suppression, resource/session/account erasure decisions, retired-key markers and export invalidation before serving. Cleanup uses the existing job leases/fences, scope/ownership checks and verified absence. Preserve unresolved billing linkage and review responsibilities without restoring entitlements or ordinary mail.
5. Verify required cleanup, artifact invalidation, all decision coverage and no old-generation writer before durable acknowledgement. Protected legacy payloads keep affected recovery blocked until an approved safe treatment exists; do not disable immutable guards. Start all serving components only from the trusted mandatory boot profile after a fresh readiness verification.
6. Keep readiness conditional on current head/coverage/generation. Missing evidence, newer unacknowledged decisions, rollback or control-plane outage closes access again. Restart starts closed. Diagnostics expose safe IDs/categories and aggregate coverage only; no content, secrets, object paths or suppression digests.

## Boundaries that cannot be skipped

| Boundary | Required enforcement / acceptance |
| --- | --- |
| Backend HTTP and WebSocket | Mandatory boot identity/readiness composition and per-request eligibility; ordinary auth remains required after readiness. Current local middleware is a starting contract, not a deployment gateway. |
| gRPC and active streams | Start only after readiness; close/invalidate old-generation streams and reject commits after restrictions. A healthy HTTP process does not prove gRPC was fenced. |
| Direct Supabase Auth/session/token hooks | Confirm actual supported hooks/transaction order for password, Google, linking/email change and bootstrap. Product denial, identity creation denial and session issuance denial are separate. Actual Auth-engine acceptance is still outstanding. |
| Direct REST/Postgres/RLS | Gate the separately served data boundary as well as the backend. RLS restriction replay and old-token behavior must be verified on the configured project. A restored internal ready flag alone cannot authorize exposure. |
| Storage/CDN/signed capabilities | Quarantine actual object service/caches and verify owned object versions/deletion/expiry. Prevent new publication/download authorization. Already delivered bytes cannot be recalled; issued capabilities may have limits that must be measured, not assumed. |
| Queue/worker/export processors | Bound jobs to environment/generation/account revision, reject stale commits, cancel/quarantine late outputs and verify durable retries. No sensitive payload in witness records. |
| Payment/email callbacks | Preserve signature verification and deduplication; append minimum allowed financial/delivery facts without rebootstrap, paid/Free activation, private content or ordinary marketing. Razorpay execution stays paused. |

The deployment plan must choose either a topology where every independently served boundary can be fenced, or an explicitly reviewed proxy-only data-access topology. Do not assume backend middleware alone controls hosted Supabase or CDN traffic. No remote Auth/RLS/Storage change is authorized here.

## Failure, recovery and required evidence

Require controlled tests of authority/anchor outage, conditional-update conflict, source loss before/after each durable step, clock/receipt consistency, key rotation/recovery, rollback of DB/object/journal/checkpoint/authority backups, wrong manifests/generations, concurrent coordinators, new confirmations during cutover, stale workers, late callbacks and missing evidence. Use synthetic identities; inspect archives/objects for cross-account leakage and prove no private content or credentials enter journal/logs. Compare nonmembers, billing integrity, suppression and global catalog/flags.

Accept **separately**: configured Auth hooks/revocation, actual Storage/CDN semantics, processor retention/deletion capability, backup/log/manual-copy inventory, externally durable current-head recovery and operator restore drills. Local native PostgreSQL/fake-provider results do not close those gates. Journal, suppression and restore/retirement markers require a justified horizon covering every restorable source/callback; no expiry period is approved here.

Before vendor selection, only two deployment facts are needed: the approved production application host/region (currently explicitly **not selected**), and who will own the independently protected recovery authority/anchor and its restore permissions. Once those exist, compare managed versus independently operated placement against the same protocol; present operational duties and recovery evidence rather than asking the owner to choose unexplained products. No additional decision blocks the authorized local preparation/separation work.
