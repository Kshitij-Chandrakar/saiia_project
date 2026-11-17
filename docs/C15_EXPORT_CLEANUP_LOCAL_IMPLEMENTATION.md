# C15 export and cleanup: local implementation

30 October 2026. **Local implementation and synthetic verification only. C15 is incomplete; production export/deletion remain disabled. C15.5 and Razorpay execution remain paused.**

## Owner-facing result

Own-account export now has an authenticated, default-closed local API, purpose-bound confirmation, durable snapshots, ZIP construction, original-file inclusion, status, private download authorization and expiry cleanup. The local worker implements separate session, history and accepted-account cleanup contracts, dependency-ordered deletion, object manifests, progress checkpoints, leases, fencing and retry recovery.

This is not deployable account erasure. Account jobs explicitly remain blocked on retained-record minimization/retirement. Nonempty unclassified settings objects block export rather than silently losing settings. Actual Auth, Storage, processor and recovery-copy acceptance remain outstanding. Destructive customer controls remain unavailable.

## Authority and isolation

- Worktree `E:/saiia_project/c15-stage1`; branch `work/c15-stage1`; baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`; origin `https://github.com/Kshitij-Chandrakar/saiia_project.git`.
- Entry inventory: 93 changed/untracked files. No checkout, stash, commit, push, merge, PR mutation or edits to another worktree. Existing review groups are preserved in their original evidence file.
- No applicable AGENTS.md was found in the worktree inventory or the checked parent locations. Used Ponytail, Graphify, Playwright Expert and the product register of Impeccable. Queried the existing graph before and after code work; its older roadmap locations are navigation, not acceptance evidence. No graph refresh or installation.
- Source requirements: [audit](C15_PRIVACY_DELETION_AUDIT_AND_PLAN.md), [decision package](C15_DECISION_PACKAGE_AND_IMPLEMENTATION_SCOPE.md), [approved policies](C15_APPROVED_POLICIES.md), Stage 1–1D reports, [Auth rehearsal](C15_LOCAL_AUTH_REHEARSAL.md), current C15 roadmap, ordered migrations and current code. Historical proposals and acceptance journals were preserved.
- The current owner instruction permits independent local export/cleanup work despite the historical Auth-rehearsal sequencing blocker. It does not waive actual Auth acceptance or authorize activation.
- All native database connections used disposable, loopback PostgreSQL. The existing offline pytest boundary disables operational environment/provider use. Object storage and mailbox delivery are in-memory synthetic adapters; no real email or provider request is composed. No Auth build was repeated.

## Requirement and status trace

| Requirement | Local implementation/evidence | Status and remaining boundary |
| --- | --- | --- |
| Own-data export, approved content/exclusions | `privacy_registry.py`, `ContentEngine.snapshot/build`, content API and native archive tests | Implemented locally; nonempty unclassified settings fail closed |
| Original owned resumes, all generations and profile copies | Resume/chunk/profile projections; version-bound object inventory; populated archive and soft-deleted-account tests | Controlled primary stores covered; device/external copies unverified |
| Explicit account confirmation, restriction and 24h target | Reuses Stage 1 accepted request and `subscription_deletion_jobs`; account intake requires that exact accepted request | Existing authority preserved; target is not proof of completed cleanup |
| Separate full-session/history/account erasure | `ContentEngine.request/cleanup`, session manifests, operation-bound notes-version cleanup | Local service contracts; new destructive browser routes are not exposed |
| Transcript-only guard and saved-answer policy | Existing transcript API/migration unchanged; privacy worker deletes scoped saved answers separately | Ordinary editing/deletion remains unchanged |
| Durable recovery and truthful status | Jobs, object manifests, leases, retries, checkpoints, scoped status extension | Primary verification is distinct from retained obligations; no full-erasure state |
| Finite metadata retention without weakening immutability | Retained registry entries and explicit blockers | Retirement/minimization architecture remains blocked; no trigger bypass |
| Late writes/recreation | Existing account fences plus session manifests and keyed creation-key tombstones | Native DB tests; actual Auth/Storage and disconnected-device acceptance outstanding |
| Customer controls | Settings export panel, disabled history controls, synthetic confirmation/status/download UI | Normal feature remains off; screenshots are synthetic previews |

## Executable treatment registry and allowlist

The executable source is `backend/app/privacy_registry.py`, version `c15.content.v1`. [Machine-readable treatment/source register](evidence/c15-export-cleanup/treatment-registry.json) records exact columns, ownership predicates, session references, cleanup order and migration sources. No `SELECT *`, arbitrary client-selected table, or bucket-prefix walk is used.

- Auth export: only `id`, `email`, `email_confirmed_at` from the verified subject's Auth row.
- Personal projections: profile and persisted consent fields; resume metadata and allowlisted confirmed-profile fields; chunk text/generation IDs; saved job context; session metadata; transcript questions/answers; sources and diagrams; AI Notes; Ask AI; saved answers; projected Screen results and Notes versions; registered settings fields.
- Safe metadata: explicit usage-operation/period quantities, billing status/amount/currency/consent/cancellation-request fields, payment-receipt dates and email-type/status dates. Verified billing authority is unchanged.
- `confirmed_profile` has a separate explicit field list. Screen/Notes JSON is recursively projected; Screen items retain question/answer/code/language and visible extracted text, not image hashes, prompts or claim tokens.
- Excluded: credential/session/suppression material, internal prompts/security/retry/lease fields, other accounts, raw support-note bodies, numeric embeddings and external/unmanaged copies.
- The current schema permits arbitrary `overlay_settings` and `notification_preferences` objects without a verified public nested-field contract. Nonempty values block export with `user_settings:unregistered_nested_settings_fields`; they are not silently omitted from a successful archive. Their public projection is a technical follow-up.
- Reachability inspection follows indirect foreign-key children from Auth, not just direct Auth foreign keys. New unclassified linked tables block export. Retained envelopes have explicit dispositions, not inferred cleanup approval.

## Export lifecycle and download safety

`POST /api/privacy/content/{begin,otp_start,otp_verify,confirm,status,download_begin,authorize,download}` is an exact ingress allowlist. Bodies reject extra fields and query strings; the server derives the account from a verified bearer. The route returns unavailable unless an isolated fixture explicitly injects `app.state.privacy_content_local`. Main application composition never assigns it, and no production worker/Storage adapter is provided.

1. Begin binds an expiring proof to account, request and session. Password/TOTP uses existing signed-presence checks and requires proof after the request began. Password can establish a fresh same-subject session; refresh alone does not qualify.
2. The owner additionally approved fresh export-bound mailbox OTP in this conversation. It is mailbox control, not Google reauthentication/MFA. Export purpose is separate from deletion; codes have five-minute validity, single-use verification, five guesses, 60-second resend spacing, three sends/hour and ten/day. Delivery is only an injected fake. Codes/digests/keys are absent from reports and archives.
3. Verification does not create an export. Final typed `export` confirmation consumes proof and snapshots content in the same account-locked transaction. Repeated confirmation recovers the existing job. A ready archive can receive fresh download proof without creating a second archive.
4. All projected database categories use one SQL statement/snapshot through a server-side cursor. Files are captured as explicit owned references with versions; changes/missing files prevent publication. Safe generated archive paths are mapped back to original resume IDs/names in the manifest. User filenames never become filesystem paths.
5. ZIP construction uses an owned temporary file, bounded row batches and streamed object reads. `Limits` provides configurable initial engineering defaults: 1 GiB total uncompressed content, 10,000 members and a 1 MiB per-row transfer ceiling. These are not permanent product policy. Exceeding any bound rejects the archive; no truncation or partial publication occurs.
6. Publication rechecks the live lease and account restriction. Ready time establishes the 24-hour expiry. Expiry denies access even if object deletion fails.
7. Authorization creates a 256-bit capability, stored only as a digest, valid for at most 60 seconds and consumed once. It is sent in a POST body, never a URL, email or log. Ownership, restriction and expiry are checked again at consumption and between delivery chunks. HTTP responses are `no-store`.
8. Stopping authorization/further delivery cannot recall bytes already delivered. Browser object URLs represent already-downloaded bytes, not reusable server credentials. Expiry reconciliation revisits invalid artifacts because an uncertain old put could finish after an earlier absence check.

## Cleanup contracts and state machine

`ContentEngine.request(account, request_id, kind, resource)` is an internal trusted local service, not a client-targeted API. Kinds are `session`, `history`, `account`; export is separate. Account intake reuses the existing `personal_cleanup` outbox and requires the exact accepted deletion request. No new account-access authority or admin workflow was introduced.

Jobs move `pending → running → ready` for exports, or `pending → running → primary_verified/blocked` for cleanup. Transient failure returns unfinished work to `pending` with exponential backoff; exhausted work becomes `failed`. Leases last 30 seconds and are fenced by random lease IDs; at most five claims are permitted. A local explicit retry can requeue eligible blocked cleanup without restoring product access. `expired` never restores download access.

- Each table is cleaned in dependency order within its own guarded transaction/savepoint, then absence is checked and progress recorded. Retrying revisits scopes idempotently. Constraint/immutability failures remain blockers, not bypasses.
- Full-session/history requests capture concrete owned session IDs under the existing account lock. Timestamp-only membership was rejected after a native test exposed equal clock ticks. New unrelated sessions remain usable; old session IDs stay fenced after row deletion.
- Existing session-creation keys are replaced by purpose-separated keyed replay tombstones before cleanup. An old key cannot bootstrap a replacement session after its original row is removed. Marker/key retirement remains an unresolved suppression-evidence dependency; no 90-day expiry is inferred.
- Notes versions join their retained usage operation's owner, `notes.generate` operation and session resource. Ambiguous operations block that scope. Visible session data, saved answers, checkpoints, Notes and Ask AI are removed without deleting reusable resumes, chunks, profiles or job contexts.
- Account cleanup includes soft-deleted resumes, all chunk generations, confirmed-profile copies, profile/settings, saved contexts and private session children. Marketing tokens and encrypted handoffs are excluded from exports and deleted as private credential data; their late writes receive the existing account fence.
- Resume removal checks active processing leases. Object manifests originate from owned rows, not guessed prefixes. Namespace/path validation and remaining-reference checks precede removal. Forbidden Storage access is blocked, authorized absence is distinct, and unavailable/uncertain operations retry. Object absence is checked again after removal.
- Accepted restriction, primary-content removal and outstanding billing/retention/processor/backup obligations are separate. The existing scoped deletion receipt now exposes safe progress after validating its capability. `content_erased` remains false; no `fully_deleted` outcome is introduced.

## Precisely blocked work

Account completion remains blocked on the retained entries listed in the treatment register. In particular:

- `subscription_binding_history` and `subscription_payment_receipts` retain immutable JSON/account linkage (`20261024010000_subscription_account_integration.sql`, `immutable_rows`/`immutable_truncate`). `billing_payable_quotes` retains immutable financial/contact/consent snapshots (`20261025030000_billing_gst_payable.sql`, `billing_quote_immutable`). No existing bytes or protections were changed.
- Usage/Auto/recovery/relay history, resume-upload history, billing evidence/operations/notification records and operator/catalog history need field-level minimization and approved controlled retirement. Listing a category as retained is not approval to keep every existing field indefinitely. The worker reports `<table>:retained_payload_minimization_not_verified` and continues independent cleanup.
- Actual configured Auth, Storage, processor, backup/log-copy and restore-suppression behavior is unverified. Native schema/data tests do not establish those capabilities. No backup erasure deadline or legally required period is asserted.
- Legacy browser/Electron caches and offline queues need account ownership tagging and reconnect acceptance; unowned legacy files/downloads are not wiped by guessing paths. Actual provider callback and remote Storage acceptance remain separate from the existing/native write-fence tests.
- Failed-upload/crash-temp retention remains undecided. No clock or system-temp/bucket sweeper was enabled. Export expiry is the separately approved clock.

## Verification and previews

| Check | Result |
| --- | --- |
| New native PostgreSQL content suite | 34 passed; [per-test results](evidence/c15-export-cleanup/tests.json) |
| Existing Stage 1, 1B, 1C and 1D native regressions | 52 passed |
| Existing deletion Playwright suite | 16 passed |
| New export Playwright suite | 5 passed |
| Scoped Ruff, Python 3.10 target; format check | Passed |
| Scoped mypy, `--check-untyped-defs --follow-imports=skip` | Passed for three new source modules; not a whole-project strict-typing claim |
| Scoped ESLint | Passed |
| Actual application Vite build, `envFile:false` | Passed; existing large-chunk warning remains |

Native coverage includes two populated accounts, nested-parent corruption, field/file isolation, path attacks, configurable limits without truncation, expiry, single-use capabilities, streaming restriction, file changes, stale leases/concurrent claims, account locking, soft-deleted rows/all generations, reusable-resource preservation, history membership, replay-key suppression, interrupted removal, 403/unavailability distinction, unknown direct/indirect categories, mailbox binding/replay/expiry and retained ledger/suppression integrity. Existing regressions cover prior confirmation/Auth integration protocols; they are not actual Auth-engine acceptance.

Demonstrated defects fixed: empty-archive limit bypass; stale test-queue contamination; timestamp-only history scope; replay through removed creation keys; post-expiry late artifact puts; password reauthentication establishing a new session; delayed-download mailbox re-verification; mobile dialog overflow. A Windows text-edit encoding mistake was corrected. An existing global status locator was scoped to the deletion dialog without weakening its assertion. A formatter's Python 3.11-only UTC conversion was reverted and checks target the actual Python 3.10 runtime.

[Desktop synthetic preview](evidence/c15-export-cleanup/previews/desktop-export.png) · [Mobile synthetic preview](evidence/c15-export-cleanup/previews/mobile-export.png). No OTP, password, customer content or provider interface is captured.

## Migration, review and cleanup

- Prepared additive migration: `20261030120000_privacy_content_jobs.sql`, applied only to disposable PostgreSQL after the supported Stage 1–1D package. Historical migrations/package inputs remain intact. No remote schema/Auth/configuration change.
- The migration provides no content-table privileges or worker login to application roles. The narrow progress RPC uses the existing backend role after receipt validation. A reviewed least-privilege production adapter remains required; the local engine uses the disposable fixture owner only.
- Rollback disables new requests/UI/worker composition; it must not remove accepted account barriers, suppression or session replay evidence. Physical erasure cannot be rolled back by restoring deleted content.
- [Review inventory](evidence/c15-export-cleanup/review-slices.json) preserves the prior 11/20/23/39-file groups and adds this stage as a dependency-ordered source group with review headroom. Shared files require sequential patches after those groups, not replaying their complete working copies.
- [Cleanup verification](evidence/c15-export-cleanup/cleanup.json) records disposable cluster/listener closure and exact leftovers. Only rehearsal-owned services were started/stopped. Synthetic mailbox/Storage data are in process memory; no temporary credential files were created.
- Automatic approval review rejected recursive removal of the owned generated `frontend/dist-c15-local` output as **“blocked by policy.”** It was not retried through another tool or shell. Every generated file is listed separately in the inventory, not hidden with filters or treated as required source. Previous Auth-rehearsal leftovers remain untouched.

Next bounded work: resolve the registered settings projection and retained-payload separation/controlled-retirement design, then implement least-privilege adapters and complete supported-runtime Auth/Storage acceptance before any activation. C15 remains incomplete.
