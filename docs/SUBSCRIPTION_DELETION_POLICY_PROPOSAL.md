# Account deletion policy — proposal awaiting approval

25 October 2026. **Not an approved policy and not enabled.** No real account,
file, Auth identity or immutable record has been deleted. No account-level
preparation/access barrier implementation is included in this documentation
branch's runtime tree. The separate runtime proposal below contains a
`policy_pending` preparation barrier; it is not an irreversible purge workflow.
This proposal does not change approved plan terms or subscription lifecycle rules.

## Implementation evidence boundary - 30 October 2026

This document is reviewed on the documentation-only PR #58. Its runtime tree at
`8c4c5b44b5890b6c076f7550250763698d0a7685` does not contain the account-level
preparation barrier or its tests. The separate [subscription runtime PR #60](https://github.com/Kshitij-Chandrakar/saiia_project/pull/60)
at `d9789a5e4f54f995ff06c5906203c15e8b1e8b36` contains
[`subscription_deletion_prepare` and access restrictions](https://github.com/Kshitij-Chandrakar/saiia_project/blob/d9789a5e4f54f995ff06c5906203c15e8b1e8b36/supabase/migrations/20261024110000_subscription_relay_privacy.sql),
the [internal preparation caller](https://github.com/Kshitij-Chandrakar/saiia_project/blob/d9789a5e4f54f995ff06c5906203c15e8b1e8b36/backend/app/commercial/hosted_coordination.py)
and [native preparation/access-barrier tests](https://github.com/Kshitij-Chandrakar/saiia_project/blob/d9789a5e4f54f995ff06c5906203c15e8b1e8b36/backend/tests/test_hosted_subscription_native.py).
References below to existing preparation, access denial, handoff removal and
preparation tests describe that separate local runtime slice, not code added by
this PR or functionality verified on main. Test definitions and historical
local results do not establish merged, deployed or irreversible-deletion
acceptance. No account purge, retention policy or activation is authorized here.

## Minimum decisions

| Decision requiring owner approval | Concrete proposal | Rationale / dependency |
| --- | --- | --- |
| Personal-content erasure and recovery | Revoke access immediately on confirmed deletion; remove primary personal DB content and active storage objects within **24 hours**. No post-confirmation undo/grace period. Retry failed jobs, never restore access to make progress. | A short, explicit deletion objective; job recovery means completing deletion, not restoring personal data. Needs reliable worker/storage inventory before activation. |
| Minimal ledger/security retention and identity linkage | Retain minimized usage/binding/retry/relay metadata for **90 days** after confirmation; security/admin audit metadata for **180 days**. Explicitly allow retention of the legacy account UUID as a **pseudonymous identifier**, not claim anonymity. Remove email/profile/token linkage when Auth is removed after personal purge. | Bounded investigation/reconciliation window. These periods are proposed product choices, not asserted legal requirements. Retention exceptions and an integrity-preserving expiry mechanism must be reviewed before implementation. |
| Backups and completion wording | Inaccessible backup copies age out within a proposed maximum **30 days**, subject to a verified staging/hosting backup lifecycle. Report “personal content deleted; retained accounting metadata expires on …” before final retention expiry; do not claim all records erased early. | Backup TTL is currently unknown. Owner/environment administrator must confirm achievable expiry and restoration controls; a restore must replay deletion barriers/jobs before access is reopened. |

Approval may accept or change these three choices. It does not authorize a real
deletion run or shared migration. None is silently inferred from inactivity.

## Exact record treatment

| Record category | Proposed action | Current implementation |
| --- | --- | --- |
| Auth access/refresh sessions, encrypted desktop handoffs | Revoke active sessions, remove outstanding handoffs; never log their values | Handoffs removed and application access barrier tested. Full remote Auth-session revocation is not implemented by this internal preparatory slice. |
| Resumes, extracted text/chunks, reviewed profiles, embeddings/indexes, storage files | Delete account-owned personal payloads through a checkpointed manifest/outbox; preserve access denial during partial failure | No purge/outbox or irreversible storage deletion enabled |
| Interview sessions, transcript entries, screen results, notes, Ask AI messages, saved personal answers, diagrams and private result checkpoints | Delete personal payloads and private storage after recording their deletion tasks; keep no captured content in deletion/audit metadata | Preparation denies new private access; current records are retained |
| Account profile, preferences and identity email linkage | Delete personal profile and unlink Auth after private-content tasks are verified complete | Auth rows remain protected by existing RESTRICT references |
| `account_plan_bindings`, `usage_operations`, `usage_periods`, `usage_events`, Auto runs/replies, relay connections/frame claims and durable retry identity | Retain minimized accounting/recovery facts under the proposed 90-day rule; no audio, prompts, answers, credentials or profile content may be copied into retained metadata | Existing immutable rows/triggers/FKs remain unchanged. No retention purge primitive exists. |
| Catalog review/publication/admin audit referencing the deleting actor | Retain minimized security/admin event facts under proposed 180-day rule; remove personal display/email linkage | Existing audit immutability and Auth references retained |
| Non-personal immutable catalog terms/prices/version/fingerprint history | Preserve as product history independently of deleting an account | Existing immutable catalog behavior unchanged |
| Backup snapshots | Deny customer/application access; expire per approved verified backup TTL; enforce deletion replay on restore | Environment/backup inventory not supplied or verified |
| Previously downloaded exports, user-managed recordings and external copies | State explicitly that server account deletion cannot erase copies outside controlled storage | No unsupported remote-wipe promise |

Some retained UUIDs/timestamps may remain linkable through outside records.
“Pseudonymous” must not be presented as anonymous or fully erased.

## Immutable history and Auth removal: proposed technical design

Do not delete ledgers to satisfy Auth FK constraints or disable immutable triggers.
Prepare a separately reviewed internal, non-authenticating account-subject record
and nullable Auth mapping. Repoint reviewed foreign-key *definitions* to the
internal subject without rewriting the accepted UUID values or ledger event
bytes. Legacy internal IDs may equal the former Auth UUID; that is why explicit
pseudonymous retention approval is required. Prevent the subject record from
being used as a sign-in/admin/entitlement grant. Each subject may map to at most one Auth identity. Once set, the mapped identity cannot be replaced; unlinking is permanent and must prevent relinking to either the former or a different identity. A durable tombstone or equivalent non-authenticating marker must block reuse after unlink. Future schema/transaction enforcement and tests must cover replacement attempts, concurrent linking, unlink/relink attempts and tombstone persistence before this design can be enabled.

After private purge and inventory verification, remove Auth linkage/sessions and
the actual Auth identity using approved privileged orchestration. At retention
expiry, use a separately reviewed integrity-preserving retention mechanism;
current append-only tables cannot simply be DELETEd. No such mechanism or FK
migration is implemented or approved by this proposal. Catalog terms remain
immutable; aggregate reconciliation and audit evidence must remain consistent.

## Access, retry and completion

1. Verify the requesting account server-side, require recent server-validated
   authentication and obtain explicit deletion confirmation; an ordinary account
   can never target another UUID. Before irreversible deletion is enabled, the
   endpoint contract must define the freshness window and step-up verification,
   and tests must reject stale, missing, replayed or client-asserted assurance.
   This is a release gate, not a claim that the existing preparation barrier
   implements recent authentication.
2. Commit the existing idempotent preparation barrier; stop/fence active Auto,
   settle only valid authorized intervals, remove handoffs, block private reads
   and further execution. Same-key recovery resolves uncertain commits.
3. Future orchestration inventories exact owned resources and writes bounded
   per-resource deletion tasks. No captured content or credentials enter the job.
4. Retry only unfinished tasks. A storage failure keeps the barrier and progress
   checkpoints. Do not call logout “account deleted.”
5. Verify primary content/storage absence, existing signed-URL expiry/revocation
   and Auth unlink before reporting personal-content completion. RLS alone does
   not revoke already issued signed URLs or downloaded copies.
6. Report retained categories/expiry accurately. Final all-in-scope completion
   requires the approved retention/backup obligations to be satisfied. There is
   no current user-facing deletion-status API or undo control to advertise.

The separate runtime slice's disposable-user tests cover preparation, active-run stop,
private API/RLS/storage denial, rollback, same-key replay, conflicting requests,
concurrent requests and uncertain commits. They do **not** prove irreversible
erasure, remote Auth revocation, backup expiry or the proposed time objectives.


## Hosting feasibility review: 25 October 2026 (not policy approval)

The owner-supplied read-only staging preflight reports PostgreSQL 17.11, read-only
transaction, no migration-history relation, no public application columns/indexes/
constraints, no catalog/usage executor roles and no required application tables.
`pgcrypto` and `uuid-ossp` are installed; `vector` is available but not installed.
These facts concern the confirmed disposable staging project only. They do not
prove normal/shared deployment state, backup settings, storage inventory or log TTL.
No remote connection or migration was performed by the agent.

| Proposed period | Actual support established | Safe current statement |
| --- | --- | --- |
| Immediate access denial | Existing isolated preparation barrier stops/fences runs and denies private application access | Local implementation evidence, not hosted activation, Auth-token global revocation or signed-URL revocation |
| Personal DB/storage purge within 24h | PostgreSQL supports controlled deletion; Supabase Storage supports permanent API deletion, but no purge worker/outbox/SLA or full resource inventory exists | 24h is an unapproved objective, not a supported deadline |
| Ledger metadata 90d | Current immutable usage-event triggers block UPDATE/DELETE/TRUNCATE and RESTRICT links protect dependencies; no retention API/partitions/job exists | Automatic 90d expiry is NOT supported by current implementation |
| Security/admin metadata 180d | Application audit retention mechanism and actual platform/log-drain TTL are unverified | 180d is neither implemented nor confirmed by hosting |
| Backups maximum 30d | Plan/PITR/backups/off-site exports not supplied; SQL catalog results cannot establish them | No 30d promise; verify every recovery copy and restore behavior first |

Official platform capabilities (reviewed 25 October; not proof of this project's
settings): [Supabase backups](https://supabase.com/docs/guides/platform/backups)
are plan-dependent and exclude Storage file contents; those need separate inventory.
[Storage deletion](https://supabase.com/docs/guides/storage/management/delete-objects)
must use Storage API, not SQL metadata deletion, which leaves orphaned objects.
[Signed URLs](https://supabase.com/docs/guides/storage/serving/downloads) have separate
expiry semantics; logout/RLS barriers alone must not be represented as URL revocation.
[Platform logs](https://supabase.com/docs/guides/observability/logs) include Auth,
Storage, gateway and database sources, and may identify users; application ledger
retention does not govern platform logs or external drains. Do not infer physical
media erasure, cache invalidation or all-backup destruction from a successful row/API delete.

### The 90-day/immutability conflict: exact current limitation

Existing plaintext account UUIDs in usage events and referenced records cannot
expire merely by deleting an Auth mapping. They remain pseudonymous, potentially
linkable records. A tombstone or retained hash does not erase the original row.
Key destruction cannot erase existing plaintext UUIDs. An expiry job that disables
triggers, bypasses RESTRICT or temporarily grants arbitrary DELETE would weaken
current guarantees and is expressly rejected. There is no honest claim that this
schema already provides both permanent append-only retention and 90-day erasure.

A possible future design REQUIRES separate approval to define immutability as
unchangeable *during an explicitly bounded retention lifetime*, then controlled
whole-subject retirement after that lifetime. Preserve old bytes while retained;
use a narrowly privileged, non-application retention orchestrator that verifies
confirmed deletion, frozen account, completed work, elapsed deadline and every
reference before retiring an isolated retention unit. No general ledger-row edit
permission, no in-place event rewriting, no trigger disabling. Supporting storage
units/partitions, dependent tables, safe inter-unit references and an append-only
non-identifying destruction attestation require a reviewed schema design and
native adversarial tests. Current tables are not already arranged this way.

If permanent nondeletable ledger rows must remain an absolute requirement, the
90-day erasure proposal must instead be rejected/revised; those requirements cannot
both hold for the same retained plaintext bytes. Future per-account encryption can
be evaluated as an alternative, but only after removing linkable plaintext keys,
proving key-backup destruction and explicitly agreeing what erasure means. It is
not a shortcut for historical records or an implemented capability.

### Records needing separate rules

- Active bindings/usage and unresolved reservations/results: retain for actual
  operation/reconciliation; the proposed clock is from confirmed deletion, not
  account creation or last write. Do not silently extend 90d for unresolved work:
  define an approved exception/escalation rule before promising a deadline.
- Relay replay claims, durable operation keys and Auto fences: expiry must not
  allow replay or rebootstrap of a deleted identity. A minimal deletion/replay
  suppression marker needs its own retention and pseudonym treatment decision.
- Security/admin audits referencing the same identity: proposed 180d conflicts
  with removing all linkage at 90d; separate subjects/references and treatment of
  remaining identifiers must be approved. A longer retained audit still means
  identity-associated data remains.
- Product catalog terms/fingerprints: preserve non-personal commercial history;
  separate the actor identity from that history. No plan snapshot rewrite.
- Deletion job manifest/attestations: keep through task completion, retry and
  backup replay needs; approve a minimal evidence retention period separately.
- Auth/platform/proxy/application logs, crash reports and log drains: independent
  hosts/TTLs, possibly IP addresses/identifiers; inventory and redact at source.
- Backups/PITR/off-site exports/object versions/CDN caches: own lifecycle from
  snapshot/copy creation; a backup made near day 90 may retain ledger data beyond
  day 90. Specify live-store expiry vs last recoverable-copy expiry separately.
- Future payment/tax/dispute records: C12 not implemented; no invented legal
  duration or generic 90/180d rule. Define before accepting real payments.
- User downloads/external copies: outside server deletion control.

Required evidence: actual plan tier and backup/PITR horizon, external dumps/log
drains, backend/frontend host, log TTLs, Storage bucket/cache/signed-URL settings,
object-copy lifecycle, and restore rehearsal that reapplies deletion barriers before
access. Ask for settings only, never secrets. Until provided, all proposed numeric
deletion deadlines remain unapproved and unverified. Accepted capture trials stand.


## Owner-confirmed hosting settings - 25 October 2026

Target: `cfmvqbjmnwklxqlpelxe`. The owner observed **Free Plan** on the
Supabase Backups page, which states **project backups are not included**.
This is operator-reported Dashboard evidence, not an agent inspection.
The bracketed alternatives in the owner's template are placeholders, not settings.

| Setting | Current evidence/status |
| --- | --- |
| Supabase tier | Free, owner-confirmed |
| Included project backups | Not included, owner-confirmed Backups-page message |
| PITR | Not checked; do not infer enabled or disabled |
| Platform log retention | Unknown |
| Log drains | Unknown; do not infer none |
| External backups/dumps/exports | Unknown; do not infer none |
| Backend/frontend hosting | Not supplied; do not infer not deployed |
| Storage copies/cache/signed-URL lifecycle | Unverified |

Unavailable included backups do not prove absence of provider recovery copies,
manual exports, external replicas, logs or storage copies. They neither validate
a 30-day backup expiry nor establish any personal-data erasure deadline.
24-hour purge, 90-day ledger expiry, 180-day audit retention and 30-day backup
maximum remain unapproved/provisional. No irreversible deletion is implemented.

Independent preparation remains safe: retain the read-only schema findings and
reviewed migration hashes; inventory recovery and logging systems; define explicit
live-store versus last-recoverable-copy completion; design/verify resumable jobs
only against disposable data once policy is approved. A future staging migration
requires a separately approved recovery plan: Free-plan lack of included backups
must not be described as an available rollback snapshot. Prepare an explicitly
approved encrypted external pre-change export plus restore procedure, or an
explicitly approved rebuild of this empty disposable target. Neither was executed.
A rebuild authorization is not a general license to delete projects or data.

Next evidence to collect, without secrets: PITR screen state; log TTL and drain
settings; external backup destinations/TTLs and restore owners; deployed host names;
Storage bucket/cache/signed-URL settings. Keep every unchecked field unknown.
Accepted local/hosted capture results are unchanged and are not repeated.


Current owner-confirmed hosting update - 25 October 2026: staging Free; scheduled
project backups not included; PITR not enabled (Dashboard upgrade offer).
Frontend/backend run locally and are not deployed. This supersedes earlier unknown
PITR/hosting status only. Log TTL/drains and external backups remain unknown;
unavailable scheduled backups/PITR do not prove absence of retained copies. All
numeric deletion/retention objectives remain provisional and unapproved. No expiry,
Auth unlink, retention bypass or irreversible deletion is enabled.
