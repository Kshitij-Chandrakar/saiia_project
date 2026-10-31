# Default-off hosted audio and deletion preparation

25 October 2026. Local implementation/review packet, not deployment approval.
See the [current status](C11_C13_ACCEPTANCE_RUNBOOK.md#current-status--25-october-2026),
[approved policies](SUBSCRIPTION_APPROVED_POLICIES.md) and
[fixed C11 scope](C11_CLOSURE_CHECKLIST.md). Accepted physical timing/JBL trials
are retained; this packet does not request repeating them.

## Implemented relay contract

`backend/app/commercial/hosted_audio.py` exposes only
`WS /api/account/audio/stream`, default-off. It reuses `InterviewRealtimeService`
internally, existing verified JWT/session ownership, `AccountAutoLease`, SQL fences,
and durable generation turns. It never opens a server microphone or WASAPI device.
Legacy hosted gRPC/WS paths remain closed. The native tests use actual WebSocket
connections, including two independent loopback Uvicorn processes sharing one
task-owned PostgreSQL cluster; providers are deterministic substitutes.

1. Require an exact allowed Origin, no query string, and exactly one bearer.
   Supply Authorization or a first-frame `bearer` field, never both. No tokens in
   URLs, cookies, screenshots, ledger metadata or request logs. Deployment requires
   WSS/TLS; the disposable harness alone uses loopback WS.
2. Within five seconds send one JSON **object** with `stream_id`, `session_id`,
   `source` (`microphone`, `system`, `both`), and optional first-frame bearer.
   IDs are UUIDs; extra actor/permission/allowance fields are rejected. Maximum
   start payload: 16384 UTF-8 bytes. Wait for authorized `ready` before forwarding.
3. Send binary frames: eight-byte unsigned big-endian sequence followed by even
   PCM bytes, 16000Hz mono signed PCM16. Audio length 2–6400 bytes. Sequence starts
   at 1 and advances by one; maximum 2^53−1. The client mixes Both once, never
   opens two account runs. Exact last-frame retries are suppressed in PostgreSQL;
   conflicting or out-of-order sequences fail closed.
4. Send exact text `ping` every five seconds; the existing authorization is at
   most fifteen seconds and is clamped to quota, period and binding validity.
   Pings are liveness, not client-supplied elapsed time. Idle authorization is
   rechecked at most every 500ms, without renewal. Stop uses exact text `stop`.
   Disconnect, expiry, revocation and worker failure settle through the existing
   bounded lease path. A dead worker cannot extend a lease.
5. Limits are operational: 20 audio packets/second, server-clock byte pacing
   (6400-byte initial burst plus 32000 bytes/second), two-second output send wait,
   twenty-second inbound wait, 128-character control bound. Configure the ASGI
   server's receive queue/message limits as in the test worker: eight messages,
   16384 bytes maximum. Preserve existing bounded engine/provider queues.
6. Responses use the existing protobuf JSON field names and owned answer-stream
   identity, including durable completion; owner tokens/fences are not exposed.
   Retrieve saved results through existing owned session APIs. A retry must not
   start a new generation merely because a response was lost.

The relay deliberately does **not** promise exactly-once PCM delivery to an
external provider: a worker may fail between a committed frame claim and network
forwarding. It prevents automatic replay of that uncertain frame/run. Durable
answer-turn checkpoints distinguish saved replay and uncertain execution; a new
stream ID is a deliberate new run after prior ownership expires/is stopped.
No automatic reconnect/resubmit loop is implemented. Native tests prove a replayed
frame does not regenerate or create a second durable result.

The default-off desktop hosted transport is now implemented in
`frontend/electron/hosted_audio_transport.cjs`, selected through the existing main
client and unchanged preload channels. The compiled renderer acquires mic/system/Both
only after server ready; Both is mixed once with the existing Web Audio PCM encoder.
Main alone holds Authorization. A bounded `ws` parser is pinned as a direct dependency
(8.22.0): 4 MiB incoming limit, no compression/redirects, five-second handshake;
capability HTTP reads are capped at 4096 bytes and reject redirects. Outgoing audio
is acknowledged one frame at a time with a 12800-byte socket buffer ceiling. Existing
continuous-capture stale-frame limits now also apply to hosted mic/system streams.

Production targets require HTTPS/WSS, valid certificate checking, no URL credentials,
query, hash or arbitrary path. Main obtains the destination only from trusted process
configuration, never IPC. Insecure loopback is injectable only by the test entry's
private main-process construction; NODE_ENV or renderer flags cannot grant it.
Server readiness requires matching protocol/deployment designation, current verified
account authority, required schema/EXECUTE and configured operational flags. There
is no unmetered hosted fallback or automatic socket reconnect.

Windows system capture is granted only to the current main frame during its
server-authorized system/Both run, once per run. The primary display supplies loopback
audio; video is never sent to the relay. Stop/error/account cleanup aborts pending
acquisition too, releases late tracks and stops all acquired tracks/AudioContexts.
Physical hosted system permission/loopback acceptance is prepared separately; simulated
media tests do not prove actual OS capture or deployed HTTPS/TLS behavior.

## Shared auth and worker coordination

Hosted desktop handoff create/exchange reuse the existing exact HTTP routes and
verified identity. PostgreSQL stores only code/state hashes plus separately
Fernet-encrypted access/refresh payloads for a five-minute single-use handoff;
not usage/audit records. Workers need the same secret key. Three outstanding
handoffs and five-second create spacing are enforced per account. Exchange is
atomic; lost/uncertain exchange cannot issue replacement credentials. Create a
fresh user-initiated sign-in if necessary. Local development's existing isolated
memory handoff behavior remains separate.

Configuration names (never values): `HOSTED_AUDIO_ENABLED=false`,
`HOSTED_AUDIO_ORIGINS`, `HOSTED_AUDIO_DEPLOYMENT_ID`, `DESKTOP_HANDOFF_ENCRYPTION_KEY`,
`SUBSCRIPTIONS_ENABLED=false`, `SUBSCRIPTIONS_DSN`; existing verified Auth/project,
Auto/STT/answer/model readiness configuration remains mandatory. Missing key,
schema, permissions or authority fails closed. Provider readiness is not quota.
No `.env` changes or production flags were made.

## Additive SQL and least privilege

Prepared migration:
`supabase/migrations/20261024110000_subscription_relay_privacy.sql`.
SHA256: `0ab2802ca886767c8d68fb525903460eaabd04c417305fad20e4cad162525166`.
It follows `20261024100000_subscription_auxiliary_execution.sql`.

- Four private RLS-forced tables: relay frame claims, encrypted temporary
  handoffs, handoff rate limits and deletion-preparation jobs.
- Restricted SECURITY DEFINER functions with fixed `pg_catalog` search path;
  application calls use the existing exact `usage_executor` pool. No LOGIN,
  role membership, direct-table grant, real account permission or live assignment.
- Current/usage-read functions gain a deletion guard using CREATE OR REPLACE,
  retaining function identity rather than leaving an old unguarded alias.
- A self-only `authenticated` RLS helper intersects existing public Auth-FK
  tables and `storage.objects` policies with a restrictive deletion barrier.
  It grants no private-table access. Service-role RLS bypass still exists;
  application JWT checks therefore enforce the same barrier. Future tables,
  SECURITY DEFINER APIs and storage signed URLs require deployment review.

The [ordered manifest](sql/C11_C13_STAGING_MANIFEST.json) has **50 candidates**;
the previous 49 hashes were checked, not presumed unapplied. No target was
identified/contacted. The [read-only preflight](sql/C11_C13_STAGING_PREFLIGHT.sql)
checks history **and** actual objects, roles, function ACL/search paths, RLS,
privacy policies and Auth references. An absent history row does not establish
that its objects are absent; resolve drift before preparing a target patch.

Before any staging write, the owner must identify the exact disposable project,
confirm it has no customer accounts/data, provide redacted preflight results and
approve the resulting ordered file/hash/role/configuration change set. Do not
use Saiia-dev by assumption. No execution-ready target-specific unapplied batch
can honestly be produced until those facts are supplied.

Rollback: close intake/flags, drain or expire authorized leases, reconcile saved
results, preserve usage/history and deletion barriers, then restore compatible
code/config. Do not roll back to code that bypasses an existing deletion marker.
Do not drop ledgers, reset allowances or remove RESTRICT protections. For this
isolated target only, approved snapshot restoration/destruction is the schema
rollback path. Stop pools/revoke approved temporary LOGIN/admin grants before
destroying synthetic staging; preserve redacted acceptance evidence.

## Deletion: implemented preparation versus pending irreversible policy

`HostedCoordination.prepare_deletion(verified_actor, request_id)` is internal and
unwired. It derives the account from verified server context. One transaction
locks authority, records an idempotent request/audit, revokes/settles active runs,
removes pending handoffs and advances to `policy_pending` with
`irreversible_enabled=false`. Same-key replay is safe; conflicting keys reject.
Private application reads and authenticated RLS/storage access are denied after
the barrier. Rollback leaves no partial barrier/audit; uncertain commit is resolved
with the same key. No cancellation/reopening shortcut is exposed.

Nothing here deletes Auth users, stored files, resumes, answers, transcripts,
bindings or immutable ledgers. Auth foreign-key RESTRICT and immutable-event
triggers remain. Logout is not deletion. Existing emitted storage URLs/cached
copies are not revoked merely by a new RLS policy; staged storage TTL/revocation
must be audited before advertising immediate complete erasure.

Concrete proposal for **review**, not implemented business policy:

| Records / stage | Proposed technical handling | Decision required |
| --- | --- | --- |
| Auth/session credentials and in-flight work | Prepare barrier first, stop runs, revoke sessions/handoffs; retry idempotently | No new retention policy needed for the implemented barrier |
| Resume files/indexes, session content, saved answers, diagrams and other personal results | Inventory an account-owned deletion manifest; resumable outbox removes storage and DB payloads with durable per-item checkpoints | Approved erasure deadline, exceptions and recoverability window |
| Usage events/operations, accepted plan bindings, catalog/admin audit Auth references | Retain immutable integrity; review an internal non-authenticating account tombstone/mapping so Auth can eventually be unlinked without rewriting ledger entries | Exact retention duration and fields; whether stable/pseudonymous Auth UUID linkage may remain |
| Final unlink/erasure | Verify no live/private resources remain and all retention exceptions are accounted for before irreversible Auth removal | Approval of retention and identity-unlink semantics, including backups/signed URLs |

The missing decisions concern these records/retention/linkage, not a new
commercial subscription policy. Full purge/outbox/Auth-unlink implementation and
deployed erasure acceptance remain open. The tested preparatory barrier is useful
independently, but is not advertised as complete account deletion.

## Repeatable local automated checks

From the repository root in PowerShell, using the retained local runtime:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
$pgBin='C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin'
& E:/deepfake_envs/SaIIA/python.exe backend/tests/run_subscription_acceptance.py --pg-bin $pgBin --backend
```

`--backend` creates disposable native clusters and synthetic identities, runs
relay/privacy/usage/IST acceptance, and does not require or open Electron. It
accepts no remote database connection string. It does not execute the accepted
physical timing or Bluetooth tests. The runner rejects combining this mode with
physical or full packaged acceptance.

To check the non-physical packaged JWT/current-plan/browser/IPC flow separately:

```powershell
node frontend/scripts/prepare-subscription-acceptance.cjs
& E:/deepfake_envs/SaIIA/python.exe backend/tests/run_subscription_acceptance.py --pg-bin $pgBin
```

Backend tests use deterministic provider substitutes and TXT fixture data; the
runner explicitly rejects PDF use rather than emulating the unavailable retained
PDF binding. Existing UI fixture regressions can be run from `frontend` with:

```powershell
npx playwright test --config playwright.catalog.config.js workspace.spec.js lifecycle.spec.js presentation.spec.js pricing.spec.js subscription-resume-access.spec.js
npm run build
```

Do not launch physical acceptance again unless an affecting change warrants it.

## External acceptance dependencies (remaining)

Signed/installed acceptance needs an approved signing credential/build artifact
and isolated Windows VM/test user. Existing unsigned `win-unpacked` physical
evidence does not prove installer signature/SmartScreen, protocol registration,
real external-browser Auth return, installed update/uninstall or OS integration.
Use the existing runbook's installed checklist; no signing credentials or staging
target are guessed and no real account is used.


## Desktop rollout and additional connection-fencing migration

Additional prepared SQL: `supabase/migrations/20261025010000_subscription_relay_connections.sql`.
SHA256 `14d30cb9b0bc46755f6ce2ef3b23108176b558774ffc8df1ab9660f1795509da`.
It follows the unchanged relay/privacy migration. A private RLS-forced connection
claim table and one usage_executor-only SECURITY DEFINER function prevent the same
logical stream opening another transport/pipeline. The claim precedes lease creation;
a losing replay cannot stop the first connection. Claim/lease/result uncertain states
remain fail-closed; a deliberate new operation requires a fresh ID after resolving
current ownership/results. No existing migration, immutable term or ledger row was rewritten.

Process configuration names, all activation unchanged/default-off:
`ELECTRON_HOSTED_AUDIO_ENABLED=false`, `ELECTRON_HOSTED_AUDIO_URL` (optional exact
trusted relay origin, otherwise configured backend origin),
`ELECTRON_HOSTED_AUDIO_DEPLOYMENT_ID` matching backend `HOSTED_AUDIO_DEPLOYMENT_ID`;
existing authenticated account, Auto and model readiness flags remain required.
Only exact GET `/api/account/audio/capabilities` and WS `/api/account/audio/stream`
are added/reused. Capabilities are authenticated/no-store and create no Auto run.
Missing/mismatched designation, invalid TLS/configuration or permission/schema failure
must prevent capture; a flag cannot grant plan access or a lease.

Run the new non-physical packaged path after building:
`python backend/tests/run_subscription_acceptance.py --pg-bin <local-pg-bin> --hosted`.
It uses real main/preload/compiled renderer and two real local workers/native SQL,
with deterministic media/providers. The separate `--hosted --physical` mode uses
real devices and the same isolated services; it does not rerun accepted local timing/JBL
checks automatically. Stop with the existing physical marker command. Normal local
gRPC/manual flows remain available when hosted mode is off.

Staging owner explicitly reports no designated isolated project. Required next
inputs are the future project reference ID and confirmation it is disposable with
no customer data. Do not connect to Saiia-dev. Before a target change set exists:
confirm owner, PostgreSQL/timeout compatibility, Auth issuer/JWKS or approved synthetic
verification, backup/rollback snapshot, exact roles/no memberships, separate test
credentials, pinned immutable Free/test policies, HTTPS/WSS certificate/origin/proxy
rules, WS queue/size/timeouts, blocked live provider/payment egress, deployment IDs
and secret-store locations. Never put secret values into the packet or .env files.
Then execute only the read-only history/object/ACL preflight and derive an exact
ordered diff for approval. Fifty candidates are not fifty unapplied migrations.

The concrete deletion decisions are now presented in
[the proposal](SUBSCRIPTION_DELETION_POLICY_PROPOSAL.md): personal purge within 24h,
minimal usage metadata 90d/security audit 180d, backup expiry maximum 30d, and explicit
pseudonymous UUID/Auth-unlink treatment. These are proposals only. No irreversible
purge, retention exception, Auth-FK change or real deletion is approved/enabled.


### Staging target designated ? 25 October 2026

Owner confirms **intervucopilot-staging / cfmvqbjmnwklxqlpelxe** is newly created,
disposable and contains no real customer accounts/data; authorizes **read-only
preflight only**. This supersedes prior no-target statements, not migration or
activation approval. No authorized connector/browser session was available; owner
will run the target-specific SQL Editor preflight. Exact unapplied migrations and
compatibility remain unknown pending results. See the [target review packet](C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_REVIEW.md).
All 50 candidate hashes were verified locally; none is presumed unapplied.
Accepted local/hosted capture evidence is preserved. Signed installation and
irreversible deletion-policy approval remain open; no remote changes occurred.
