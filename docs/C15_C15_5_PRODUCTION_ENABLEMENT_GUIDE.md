# Enable C15 privacy and C15.5 administration

**Operator guide — 24 November 2026, Asia/Calcutta. No activation is performed or authorized by this document.**

This guide explains what is installed, what still needs work, and the order for safely enabling it. A developer completes the code and connection work; an operator handles credentials and deployment; the Product Owner approves policy, grants and release. One person may hold several responsibilities, but the checks still apply.

## 1. What are we enabling?

| Area | What the user gets | What it does not mean |
| --- | --- | --- |
| C15 | Export their own data; erase a session/history; request irreversible account deletion after verification and confirmation | Logout alone is not deletion. A request being accepted is not proof that every copy is erased. |
| C15.5 | Admin/Super admin panel for approved metrics, operational metadata and support actions | Neither role may read private resumes/transcripts, initiate customer deletion, see secrets or bypass privacy safeguards. |

Think of the rollout as **install → connect → test → enable**. Installing database migrations completed the first part; it did not connect the workers or grant anyone panel access.

The first intended environment is the **local website/backend connected to hosted Saiia-dev, using synthetic accounts**. Public production deployment is a later, separate release. Saiia-dev contains existing accounts: it is not a disposable database merely because its name includes “dev”. A localhost application can still change hosted data.

## 2. Current position: database installed, features off

These facts come from the owner's hosted SQL reports on 24 November, not a claim that this guide independently queried the hosted project.

| Check | Reported result | Meaning |
| --- | --- | --- |
| Project | Saiia-dev, `rbmxfazjbldmkomdpyzl`; CLI labels it production | Verify this identity before any future remote operation. |
| Database | PostgreSQL 17.6; all 36 expected migrations applied; none missing | Do not replay, reset or repair the applied migration history. |
| Function security | Expected private owners; no ordinary-role EXECUTE grants; no active SET/INHERIT owner memberships; no private tables reported without RLS | The checked database definitions match the postflight expectations. This is not end-to-end acceptance. |
| Auth bridge | Four postgres-owned fixed functions; `search_path=pg_catalog`; ordinary roles lack schema access | The bridge is installed. Actual Auth behavior still needs configured tests. |
| Runtime roles | All 12 checked roles exist; NOLOGIN, no superuser/CREATEROLE/BYPASSRLS/inheritance | Application/worker connection credentials have not been provisioned through these roles. |
| Suppression key | Zero active keys | Permanent email suppression cannot operate until its key is securely configured. |
| Privacy/admin configuration | Both disabled; one configuration row each; admin bootstrap unused | No first Super admin has been established by this rollout. |
| Restore state | `required=false`, `ready=false` | The hosted mandatory restore gate is not commissioned. Do not change ready to true as a shortcut. |
| Storage | Private resumes/exports buckets; ZIP allowed for exports; restrictive export-access policy installed | Actual read/sign/upload/delete/expiry behavior still needs testing. |
| Export bucket limit | 10 MiB | The bucket limit may reject an archive before the application's larger configurable engineering bound. Reconcile and test both limits; never silently truncate. |

PR [#78](https://github.com/Kshitij-Chandrakar/saiia_project/pull/78) merged the ownership-transfer fix into main. Its local checks passed; they do not establish hosted runtime acceptance. The original development worktree can still have uncommitted copies and unrelated changes. Use a clean, reviewed release checkout; do not reset or clean the dirty worktree to obtain one.

### Backup position

A private manual backup was made outside Git. Its schema/data restore matched 99 table row counts, including 29 Auth users and 60 then-existing migration-history rows. Eighteen Storage files matched expected presence and size. The backup was taken sequentially, **not as one consistent point-in-time snapshot**; serving restored files through Storage API was not verified by that check. Keep its location and credentials private. Take and validate an appropriate fresh recovery set before the next authorized deployment change. Free-tier status does not prove there are no other retained copies.

## 3. The route to enablement

Work through these eight steps in order. Stop at a failed check; do not compensate by giving a worker more privileges or forcing a success flag.

### Step 1 — Fix the release target and finish hosted runtime support

**Developer + Product Owner.** Confirm whether the release is the synthetic localhost/hosted rehearsal or a public deployment. For public deployment, select the application host, data region, operator and recovery owner first. These have not been selected in the recorded hosting decision.

There is real code work before hosted activation:

- `backend/app/privacy_runtime.py::configure` explicitly raises `production_activation_disabled` unless the local-rehearsal profile is selected. Its current composition uses local mail capture and rehearsal adapter settings. Implement/review the intended hosted profile; **do not set the local-rehearsal flag merely to bypass this guard**.
- `backend/app/commercial/executor_connection.py::SessionPooler` is pinned to a different staging project and host. Saiia-dev session-pooler routing is not supported simply by pasting its connection string. Add a reviewed explicit target binding and pass it through all required connection factories. Preserve verified TLS, correct session_user and the rejection of transaction pooling/SET ROLE shortcuts.
- Keep the existing fixed-operation adapter and separate worker principals. Do not replace them with database-owner/service-role execution for ordinary SQL.
- Enforce a verified synthetic-subject allowlist for the hosted rehearsal at API, job-claim and worker boundaries, or use a genuinely isolated equivalent dataset. A local email restriction alone does not limit database cleanup. Existing customers must remain unaffected.

**Done when:** a reviewed profile starts the normal application and workers against the intended target, rejects other targets/subjects, and passes restricted-principal and restart tests. No externally exposed feature is enabled yet.

### Step 2 — Provision connections and secrets securely

**Operator + developer.** Obtain only non-secret connection facts through ordinary discussion: project reference, connection host/port, database name, direct versus session-pooler mode and CA certificate location. Enter passwords and service keys through an approved local secret prompt/store or deployment secret manager—not chat, Git, screenshots, PRs or frontend bundles.

| Connection responsibility | Intended SQL identity |
| --- | --- |
| Owner-derived privacy/usage RPCs | `usage_executor` |
| Export and personal-content tasks | `privacy_content_executor` |
| Credential/private-sidecar cleanup | `privacy_cleanup_executor` |
| Auth-identity task coordination | `privacy_identity_executor` |
| Authoritative session-revocation observation | `privacy_revocation_observer` |
| Approved minimized-record retention | `privacy_retention_executor` |
| Restore replay only | `privacy_restore_executor` |
| Ordinary administration operations | `admin_executor` |
| First Super-admin bootstrap, one-time operator use | `admin_bootstrap_executor` |
| Admin retention, command dispatch and restore | Separate `admin_retention_executor`, `admin_dispatch_executor`, `admin_restore_executor` |

Prepare the exact reviewed provisioning/revocation procedure before changing NOLOGIN status or installing credentials. Existing entry points check the exact session_user and prohibit role switching; a convenient generic login that SET ROLEs to these identities will fail and is not an approved substitute. Bootstrap credentials must not remain in the normal web process. Private function-owner roles stay NOLOGIN and unavailable to runtime callers.

Configure the suppression matching key and preserve every version needed to enforce permanent suppression. Configure the supported credential/proof, journal and witness keys, with recovery and rotation procedures. Do not publish their values or invent expiry for suppression/restore evidence. Do not generate a new unrelated key after a restore and declare earlier decisions covered.

**Done when:** each process can connect as exactly its intended restricted identity over verified TLS; negative SQL tests deny private direct access, role switching and unrelated capabilities. Keys survive the documented recovery process. Password/key failure produces a safe unavailable state.

### Step 3 — Commission independent restore protection

**Recovery owner + developer.** A restore witness is the independent record that proves which deletion decisions are newer than the backup being restored.

Use [the witness proposal](C15_PRODUCTION_RESTORE_WITNESS_PROPOSAL.md) and [checkpoint implementation](C15_RESTORE_CHECKPOINT_LOCAL_IMPLEMENTATION.md). Choose independently protected journal/current-head storage outside the product's restore and administrator failure domain. A file on the same machine or a second co-restored file is not production-independent durability.

Record environment, dataset, actual snapshot identity and restore generation. Complete the proposed acceptance-to-independent-publication protocol and source fencing in code; the proposal is not an installed production service. No accepted deletion may be lost because the product database failed before a best-effort publisher ran. An uncertain acknowledgement remains pending/unknown and recovers the same request.

Fence website/backend, gRPC, workers, queues and callbacks during restore. Also address direct Supabase Auth, REST, Storage and previously issued capabilities; backend middleware alone does not fence those services. Replay restrictions, suppression, cleanup decisions and artifact invalidation before releasing readiness. Test missing/stale/tampered evidence and rollback of both product data and the witness.

**Done when:** an isolated restore of older DB/object data cannot reactivate a deleted subject; unaffected accounts resume only after verified reconciliation. Outage or missing current evidence fails closed. Never unlock readiness by editing a database boolean.

### Step 4 — Connect Auth, Storage and notifications

**Developer + platform/email operators.** Configure the supported Auth hooks and application-controlled provisioning checks from the reviewed Auth integration. Confirm the actual deployed hook signatures, authentication, invocation and failure behavior before setting Dashboard URLs. Test ordinary signup, suppressed signup, Google-only handling, email changes/linking, privileged provisioning and existing-account product denial separately. Do not assume a creation hook covers every path or blocks unrestricted project administrators.

Keep proof semantics unchanged: supported password/TOTP proof or the approved operation-bound mailbox proof; separate export/deletion proof; explicit final confirmation afterward. Mailbox proof is **not Google reauthentication or MFA**. Real Google OAuth needs its own acceptance; synthetic Google metadata is not that test.

Use supported Auth revocation/identity cleanup, durable tasks and independent confirmation. A later 401 or successful logout does not prove global revocation or identity cleanup. Do not add unmanaged triggers to Supabase-owned Auth tables.

For Storage, keep both buckets private and the restrictive export policy. Agree the effective upload/archive size with the configured platform limit. The 1 GiB/10,000-entry application bounds are initial configurable engineering defaults, not a permanent promise or an instruction to set every bucket to 1 GiB. Over-limit exports fail clearly without partial/truncated success. Downloads recheck restriction/expiry server-side and keep reusable capabilities out of URLs/logs. Measure historical signed-URL behavior; neither policy changes nor logout recall bytes already delivered.

For the hosted rehearsal, keep all messages in local capture and payments fake, with strict synthetic recipients. Production SMTP/sender/unsubscribe/webhook configuration and authorized real-delivery acceptance are separate. No customer archive or reusable download credential goes into email. Do not enable marketing/cancellation dispatch merely to test panel navigation.

**Done when:** configured Auth/Storage paths pass two-account isolation, replay/expiry and negative-access tests; required notices report truthful progress and capture locally during rehearsal.

### Step 5 — Verify cleanup, retention and legacy treatment

**Developer + security reviewer + Product Owner.** Verify the treatment registry against the deployed schema. Cover soft-deleted resumes, original files, extraction/profile copies, every chunk generation, session descendants and retry/checkpoint copies. Unknown fields and immutable blockers prevent a full-cleanup claim.

Preserve the approved rules:

- Account deletion is irreversible after accepted confirmation; restrict access immediately; target controlled primary cleanup within 24 hours.
- Approved minimized usage/recovery records use 90 days and security/audit records 180 days from accepted deletion. Do not assign these periods to every financial, suppression, backup or restore record.
- Ordinary terminal nonfinancial delivery metadata is removed during primary cleanup. Necessary unresolved billing linkage remains separate, owned by Product Owner and reviewed at least every seven days.
- Full-session/history erasure preserves reusable account resources; whole-account cleanup includes them. Clear Transcript remains transcript-only with its existing guard. Standalone AI Notes/Ask AI/settings reset controls are deferred.
- Private exports expire 24 hours after ready even if physical deletion retries.
- Account deletion does not initiate a refund. The no-refund policy applies except where a refund is required by applicable law.

The 36 deployed migrations **do not authorize or prove production execution of the legacy-retirement/redaction candidates**. Files such as `docs/sql/C15_USAGE_RETIREMENT_CANDIDATE.sql` are disposable-test candidates, not commands to paste into the hosted SQL Editor. Promote any required mechanism through its separate exact migration/security review and existing-data authorization. Preserve immutable protections and accounting facts. Legacy credential/private-content copies must be resolved or explicitly block the affected release promise; removing one owner token is not full erasure.

For C15.5 normal-operation retention, preserve the approved clocks in the [decision table](C15_5_ADMIN_AUDIT_AND_PLAN.md): activity/model attempts 90 days from completion; campaign drafts 90 days from edit; audience references seven days from review; terminal delivery metadata 90 days from terminal outcome; admin audit/action outcomes 180 days from action. Proof secrets disappear on consume/expiry. Expiry invalidates dependent reviews and safely stops affected dispatch without enabling duplicate sends. Earlier account-deletion removal takes precedence where applicable.

**Done when:** crash/retry/stale-lease tests prove verified absence for each approved scope, retained exceptions are explicit, and no applicable private payload remains hidden behind an accounting/retention label.

### Step 6 — Prepare the first Super admin safely

**Verified-identity operator + Product Owner.** Test synthetic bootstrap only in a fresh disposable acceptance database/project, never in shared Saiia-dev. Execute the exact reviewed `public.administration_bootstrap` migration/function through `admin_bootstrap_executor` with synthetic Auth identity and verified TOTP, as in `scripts/c15_admin_acceptance.py`. Check a correctly bound subject without a verified TOTP factor is denied without consuming bootstrap; also check wrong subject/email, missing correlation, successful bootstrap, replay denial and audit. Use a new disposable database/project for another successful-bootstrap run; discard only that owned environment afterward. Local-engine results prove the SQL/identity contract, not hosted configuration. A hosted-specific bootstrap check requires a separately authorized synthetic-only hosted acceptance project.

**What counts as proof:** `administration.authenticator_ready(subject)` checks that the subject has a verified TOTP factor. The `p_confirmation` UUID is only an operator/audit correlation ID; it is not an OTP, session-bound proof or cryptographic receipt, and the SQL function does not verify a fresh TOTP challenge from it. Preserve this distinction: the separately authorized operator procedure must verify the person's identity and fresh authenticator interaction before granting the one-time bootstrap authority. Do not claim an arbitrary UUID proves authentication or that factor enrollment alone proves current user presence.

On shared Saiia-dev, preserve `bootstrap_consumed=false`, the reserved bootstrap subject and the empty initial membership state until the separately approved real bootstrap in Step 8. Do not call bootstrap with a synthetic subject, clear memberships or reset the marker for a rehearsal. If it is consumed accidentally, stop the rollout, preserve the audit and obtain a separately reviewed operator recovery/correction; do not set it back to false as test cleanup. Successor transfer cannot replace or reset bootstrap.

For the real bootstrap package, verify the existing account for the designated email `chandrakarkshitij2208@gmail.com` and its immutable Auth UUID using the approved operator process. An email/profile field alone is not role authority. Do not create a signup privilege rule.

Prepare the reviewed one-time `public.administration_bootstrap` call with its restricted identity, exact subject/confirmation checks and durable audit. This guide does not grant the real account a role. Verify TOTP readiness and recent-proof behavior. Remove/disable one-time bootstrap access after its authorized execution, not by clearing the consumed marker.

**Proposed fixed subject-binding transaction for operator review, executed only under Step 8 authorization:** use a trusted deployment/operator connection, not an application or browser identity. Bind `$1` as the independently verified immutable UUID and `$2` as the designated verified email using driver parameters; these are not SQL Editor substitutions. First lock the singleton configuration row with `SELECT singleton FROM administration.configuration WHERE singleton FOR UPDATE`. Then execute only this fixed update in the same transaction:

```sql
UPDATE administration.configuration AS c
SET bootstrap_subject = $1::uuid
WHERE c.singleton AND NOT c.bootstrap_consumed AND NOT c.enabled
  AND (c.bootstrap_subject IS NULL OR c.bootstrap_subject = $1::uuid)
  AND NOT EXISTS (SELECT 1 FROM administration.memberships)
  AND administration.eligible($1::uuid)
  AND administration.authenticator_ready($1::uuid)
  AND EXISTS (SELECT 1 FROM auth.users AS u
              WHERE u.id = $1::uuid AND u.email = $2
                AND u.email_confirmed_at IS NOT NULL)
RETURNING true AS bootstrap_subject_bound, c.bootstrap_consumed;
```

Require exactly one returned row with `bootstrap_consumed=false` before committing; otherwise roll back and investigate. Refuse a different existing binding, consumed bootstrap, existing membership, enabled panel or ineligible identity. This operation changes **only** `bootstrap_subject`; it never resets `bootstrap_consumed`, grants a membership or provides a public binding endpoint. Record the operator's identity-verification approval separately. The readiness query now exposes `admin_bootstrap_subject_bound` as a boolean without returning the UUID. Before the real call, verify that boolean plus the approved subject match privately; `true` alone does not identify whose account is bound. Keep the bound UUID and the bootstrap call's UUID identical. Successor transfer is not a substitute.

| Power | Admin | Super admin |
| --- | --- | --- |
| Approved metrics, ordinary-customer metadata and subscription inspection | Yes | Yes |
| Request renewal cancellation; separately revoke ordinary-customer product access | Yes | Yes |
| Campaign workspace; existing user-authorized C15 status/eligible retry | Yes | Yes |
| Membership changes, commercial configuration, access restoration, audit-history reads | No | Yes |
| Private customer content, secrets, staff-initiated deletion or audit editing | No | No |

Admin directory queries exclude staff; own-account/role display remains available. Customer actions must not indirectly manage administrators. Protect the last active Super admin under concurrent staff actions, while preserving voluntary C15 self-deletion. Successor transfer is advisory. Emergency recovery remains unavailable until named independent attestors and the operator procedure are configured and tested; do not invent approvers or a third product role.

Coupons remain configuration-only. Cancellation preserves authoritative paid access until expiry unless separately revoked; revocation does not cancel billing. Restoration cannot undo a C15 restriction or revive expired entitlements. Razorpay remains paused until separately authorized and accepted.

**Done when:** the disposable bootstrap contract passes, the shared marker remains untouched, and the real identity/confirmation package is ready for Step 8 authorization. Customer, Admin, two-Super-admin and last-Super-admin journeys are checked in the enabled acceptance deployment in Step 7. A role label or visible sidebar is not sufficient proof.

### Step 7 — Run the release acceptance checklist

**Developer + independent reviewer.** Use at least two synthetic customers, Admin and Super admin, plus a separately disposable deletion subject. On a shared hosted project, explicitly bind the permitted fixture UUIDs and objects before testing; never run a broad fixture reset or cleanup sweep. Do not delete the only usable administrator to demonstrate deletion.

**Acceptance order and gate state:**

1. With shared Saiia-dev privacy/admin gates still **off**, run only read-only configuration/permission checks and expected-denial checks there. Those denials are not successful export/deletion/Admin journey acceptance.
2. Obtain separate authorization for a bounded **synthetic-only acceptance deployment** before mutation tests. For hosted-service acceptance, use a separately authorized disposable hosted project containing no existing customers and its own bootstrap marker; provision nothing under this document alone. Apply the reviewed migrations/profile and synthetic bootstrap there. Do not repurpose shared Saiia-dev's first-admin marker. If this hosted target is unavailable, keep hosted journeys blocked and report local-engine evidence separately.
3. After Step 1's hosted profile and Steps 2–6 safeguards pass, enable the acceptance deployment's `C15_RUNTIME_ENABLED=true`, `C15_ENABLED=true`, `C15_RESTRICTIONS_REQUIRED=true`, `ADMIN_CONSOLE_ENABLED=true` and both database `enabled` gates. Commission the required restore gate and obtain ready state through authenticated reconciliation first. Use that target's restricted credentials, independently bound checkpoint environment/dataset and fixture scopes; keep mail captured and payments fake. The current local-only profile is not sufficient: `C15_RUNTIME_LOCAL_REHEARSAL` does not open hosted routes or substitute for the missing hosted profile.
4. Run the journeys below through normal application/worker wiring **with those acceptance gates on**. Record the enabled state and target with the results. Afterward stop new acceptance requests and dispose only the separately owned test resources under their cleanup authorization; retain evidence and any required suppression/deletion records. Shared Saiia-dev remains off. Its real bootstrap and first enabled smoke checks occur only under Step 8 release authorization.

| Journey | Required evidence |
| --- | --- |
| Website and authorization | Normal app/worker startup, login, customer dashboard → role-only Admin panel, direct-URL denial, stale-role/session denial, desktop/mobile and keyboard use |
| Proof and export | Wrong/expired/replayed/superseded proof rejected; separate export confirmation; valid isolated ZIP; 24-hour expiry; over-limit failure; deletion racing build/download |
| Deletion | Final typed confirmation; immediate restriction; durable request; worker restart/retry; verified primary/identity cleanup; unaffected account preserved; retained obligations shown separately |
| Auth/Storage | Actual configured services, direct REST/Storage boundaries, revoked refresh sessions, already-issued JWT/signed-capability limits, no late resurrection |
| Admin | Both role boundaries, exact-version confirmations, concurrent last-SA protection, disposable-target synthetic bootstrap/transfer, safe metadata and protected audit; shared bootstrap marker unchanged |
| Campaign/billing boundaries | Captured messages, suppression/unsubscribe recheck, deduplication and uncertain-outcome recovery; fake payment dispatch; real providers explicitly unverified |
| Restore and retention | Independent-head/fencing tests, old snapshot replay, stopped stale workers, class-specific clocks, permitted legacy treatment and accounting integrity |
| Privacy/logging | No OTPs, credentials, private content, object paths or suppression identifiers in diagnostics; safe IDs/categories and truthful unavailable/blocked states |

Record source/configuration versions and evidence paths. Run affected native, engine/browser, lint/type/format/build checks. Reuse unchanged passed evidence, but rerun anything whose deployed wiring changed. Mock boundaries do not count as actual hosted/provider acceptance. Keep an explicit unresolved list for real Google, processor retention/deletion, financial retention, logs/drains, backups/object copies/CDN behavior and real email/payment acceptance.

**Done when:** the required journeys pass in the enabled, explicitly identified acceptance deployment, the shared project's gates/marker are unchanged, and every production dependency has verified disposition. Read-only/off-state checks or local-only rehearsals do not satisfy hosted journey requirements. Do not sign off while required hosted tests are unavailable or move unfinished code into a “production checklist”.

### Step 8 — Approve and enable only the verified release

**Product Owner + release operator.** After Step 7's enabled acceptance results pass, obtain a separate shared-project release authorization covering the exact commit, project, identities, real-bootstrap package, secret references, worker schedule, recovery set, proof/hook configuration, completed tests and remaining disclosed limitations. Step 7's bounded test authorization is not this release authorization. The flags below are a map, **not a ready-to-run activation file**.

| Control | Purpose / release rule |
| --- | --- |
| `C15_RUNTIME_ENABLED`, `C15_RUNTIME_DSNS`, `C15_RUNTIME_ENDPOINTS`, `C15_RUNTIME_CHECKPOINT` | Start the reviewed runtime with restricted connections and accepted endpoint/witness configuration. Current composition still needs the hosted work in Step 1. |
| `C15_RUNTIME_LOCAL_REHEARSAL` | Isolated local profile only. Not a hosted/production guard bypass. |
| `C15_REVOCATION_KEYS`, `C15_REVOCATION_CURRENT_KEY`, `C15_REVOCATION_ENABLED` | Secure revocation authority and its accepted lifecycle; validate the exact current consumers before provisioning. Never print values. |
| `C15_RESTORE_BOOT_REQUIRED` and database restore state | Require independent startup/readiness evidence. Reconciliation, not a manual ready flag, releases quarantine. |
| `C15_RESTRICTIONS_REQUIRED` | Preserve accepted-account restrictions, including while new requests are disabled. |
| `C15_ENABLED` + `public.privacy_configuration.enabled` | Public privacy actions. Both application and database state must match the reviewed rollout; neither alone completes activation. |
| `ADMIN_CONSOLE_ENABLED`, the separate `ADMIN_*_DSN` settings and `ADMIN_RESTORE_CHECKPOINT` + `administration.configuration.enabled` | Administration startup/authority. Keep bootstrap, retention, dispatch and restore responsibilities separate. |
| Provider, campaign dispatch and commercial publication controls | Separate approvals. Admin-panel access does not authorize real email/payment actions, coupon redemption or offer publication. |

On the shared release target, start and verify infrastructure, restricted workers, publication and readiness before accepting irreversible customer requests. Execute Step 6's separately authorized subject-binding transaction, verify its readiness boolean and privately matched UUID, then execute the real first-Super-admin bootstrap once and verify its consumed marker/audit; never reuse a synthetic acceptance marker. Then enable the approved database/application gates through the reviewed release procedure and run the authorized first enabled smoke checks at `/auth/settings`, `/auth/admin` and Super-admin-only `/auth/admin/subscriptions`. Keep general access fenced until those target-specific checks pass. Record the first accepted request and publication coverage. Monitor worker age/retries, expired artifacts, blocked obligations and witness health without collecting payloads.

**Done when:** the signed release record and post-activation checks show the intended users can use the approved features, unaffected users remain safe, and operators can detect/recover failures. Only then mark the corresponding production gates passed.

## 4. If something goes wrong

| Situation | Safe action |
| --- | --- |
| Migration error | Stop. Inspect actual committed history. Do not mark versions applied, reset the project or replay already-applied files to skip the problem. |
| Missing key, broken TLS, wrong SQL identity or unknown schema | Keep the affected path unavailable. Repair the exact dependency; do not use postgres/service-role SQL as an emergency runtime workaround. |
| Witness unavailable or inconsistent | Quarantine the affected environment. Reconcile authenticated current evidence before release. |
| New export/deletion feature fails | Stop new requests/publication through the reviewed controls. Preserve accepted restrictions, durable tasks, suppression and evidence. Keep healthy cleanup/recovery running only where readiness and authority remain valid. |
| Cleanup/revocation/identity result uncertain | Retain restriction, retry the same durable task under a new valid lease, and report pending/blocked. Never infer erasure or cancellation from timeout, 404/401 or logout alone. |
| Admin/campaign failure | Stop the affected dispatch/action; retain minimal safe receipts/deduplication. Do not blindly repeat an uncertain send or cancellation. |
| Restore required | Fence old writers and direct services first; restore in quarantine; replay decisions; verify before serving. |

Disabling future execution does not undo accepted deletion, restore erased content, recall a download or unsend email. A code rollback is not a data-restoring rollback. Restoring an old backup must never resurrect deleted accounts/content or remove later suppression decisions.

## 5. Commands and documents to use

Use a clean reviewed checkout and the known-working, verified Supabase CLI version. The cached CLI failed to launch during the recent assistant-side check; repair/verify the CLI normally if that persists. Do not bypass machine security policy. Do not install or upgrade tooling as part of a remote migration without review.

```powershell
# Read-only migration comparison. Verify the target project first.
# It should now report that the remote database is up to date.
npx supabase db push --dry-run --remote
```

This command does not validate workers, hooks, credentials or feature readiness. An actual `db push` is a separate write operation, not part of routine postflight. No new migration push is currently required by the reported 36/36 history.

Run these checked-in queries in the intended project's SQL Editor when needed. They open read-only transactions and do not return customer rows or secret values:

- [Migration/security postflight](sql/C15_HOSTED_READ_ONLY_POSTFLIGHT.sql): 36 expected versions, owners/grants, private buckets, export policy and disabled-state snapshot.
- [Runtime readiness](sql/C15_HOSTED_RUNTIME_READINESS.sql): intended role attributes/memberships, active suppression-key count and database readiness/activation snapshot.

A successful query is evidence of its reported metadata only. It cannot prove the frontend build, running process environment, mail routing or independent recovery durability.

When preparing this guide for review, include both linked SQL helpers if they are not already tracked. Keep private backups, credentials, screenshots and generated Graphify artifacts outside that source-review slice.

## 6. Handoff: what is needed next?

Do **not** turn everything on after reading this document. Complete the first unmet step with its named owner.

| Input/work | Owner | Current status |
| --- | --- | --- |
| Hosted runtime profile, explicit Saiia-dev routing and synthetic-scope safeguards | Developer | Required; code changes not performed by this documentation task |
| Non-secret direct/session-pooler connection facts and CA setup | Platform operator | Awaiting verified target details; credentials stay out of discussion |
| Restricted principal provisioning and secret recovery | Platform/security operator | Roles installed; logins/key material not commissioned |
| Production host/region and independently protected witness ownership | Product Owner + recovery operator | Not selected in recorded decision |
| Acceptance/publication protocol, deployed witness and all-boundary fencing | Developer + recovery operator | Local implementation/proposal exist; production composition/acceptance outstanding |
| Legacy redaction/retirement release procedure for existing data | Security reviewer + Product Owner | Disposable candidate evidence is not existing-data execution authorization |
| Real Super-admin identity/MFA/bootstrap and emergency-recovery people | Product Owner + identity operator | Bootstrap unused; recovery stays unavailable until configured/tested |
| Hosted/provider/processor/backup/log/financial evidence and final release | Responsible service owners + Product Owner | Separate gates remain; no blanket retention/erasure promise |

Keep one release record with **requirement → implementation → exact test evidence → owner → approved/unapproved**. Treat historical reports as source evidence, not proof that the current deployed configuration has passed.

## Source map

- [Approved C15 policies](C15_APPROVED_POLICIES.md), [C15 local closure](C15_FINAL_LOCAL_CLOSURE.md), [actual-engine rehearsal](C15_ACTUAL_AUTH_STORAGE_REHEARSAL.md).
- [C15.5 approved plan/decision table](C15_5_ADMIN_AUDIT_AND_PLAN.md), [C15.5 implementation and final acceptance](C15_5_ADMIN_IMPLEMENTATION.md).
- [Production witness/fencing proposal](C15_PRODUCTION_RESTORE_WITNESS_PROPOSAL.md), [durable checkpoint implementation](C15_RESTORE_CHECKPOINT_LOCAL_IMPLEMENTATION.md), [legacy retirement proposal](C15_LEGACY_RETIREMENT_PROPOSAL.md).
- [Hosted ownership correction](C15_HOSTED_OWNERSHIP_FIX.md); owner's 24 November hosted postflight/runtime-readiness reports are the source of the current-state table above.
- Runtime gates/configuration: `backend/app/privacy_runtime.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/administration.py`.
- Restricted connections and boundaries: `backend/app/commercial/executor_connection.py`, `backend/app/privacy_storage.py`, `backend/app/privacy_credentials.py`, `backend/app/privacy_witness.py`, `backend/app/privacy_checkpoint.py`.
- Database sources: `supabase/migrations/20261029010000_privacy_confirmation_foundation.sql`, `20261030140000_privacy_retention_restore.sql`, `20261102020000_privacy_runtime_operations.sql`, `20261102050000_admin_authority.sql` and the subsequent ordered administration migrations.

**This deliverable changes documentation and local Graphify navigation only. It does not provision infrastructure, install keys, grant roles, change hosted settings, run cleanup/retirement, enable providers, commit or push.**
