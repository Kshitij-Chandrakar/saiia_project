# Intervucopilot: production readiness and deployment handoff

Prepared 26 November 2026. This is a release checklist and handoff, not a declaration of production readiness or an executable deployment. No infrastructure, credentials, permissions, migrations, activation flags or provider operations are changed by this document.

## What “deployed” means

There are three different deliverables:

1. **Website:** built React/Vite assets served over HTTPS, with working direct links, Auth redirects and API routing.
2. **Backend and supporting services:** authenticated FastAPI, approved workers, SQL/Storage access, readiness/witness services, and explicitly reviewed realtime boundaries.
3. **Desktop app:** a packaged, tested and appropriately signed Electron installer, pointing to approved services. A web deployment does not install a working desktop backend on a customer's computer.

Code review, a green CI run, a local demo, a successful build and production activation are separate milestones.

## Current facts and blockers

- Reviewed C15/C15.5 code exists in `main`; use exact release commit IDs and current CI results, not this guide as a permanent claim that the latest branch passes.
- The last approved hosting record says frontend/backend remain local; no production application host or region is selected. Supabase hosting does not choose the application's hosting topology. Obtain an explicit current decision before provisioning.
- [C15/C15.5 production enablement](C15_C15_5_PRODUCTION_ENABLEMENT_GUIDE.md) remains authoritative for privacy/admin activation. Migration presence alone does not establish runtime readiness.
- The inspected FastAPI CORS list in [main.py](../backend/app/main.py) contains `http://localhost:5173`; production-origin policy/routing requires implementation and verification, not a claim that an environment variable already fixes it.
- [Vite development proxies](../frontend/vite.config.js) are development behavior, not production reverse-proxy rules. Review every browser API base URL and packaged Electron endpoint for localhost leakage.
- The current gRPC module describes a loopback-only experimental transport. Do not expose port 50051 publicly by changing its bind address. A hosted transport requires its reviewed authentication, TLS/proxy, restriction/readiness and streaming acceptance.
- The package scripts include `electron:build`, but an installer command is not proof of a complete signed distribution/update pipeline. Review actual builder configuration, included files and backend ownership before release.
- A known native billing-notification regression was reported during PR #80 acceptance: ambiguous `e.id` in `billing_notification_call` in [20261026010000_billing_notifications_admin.sql](../supabase/migrations/20261026010000_billing_notifications_admin.sql), SQLSTATE `42702`. Reproduce and resolve through a reviewed compatible fix before enabling that path; do not hide it behind a mock or edit applied history casually.
- Razorpay cancellation acceptance, processor retention, actual backup/log lifecycle and production witness/principal setup remain separate gates. No new provider outcome is asserted here.

These are engineering/deployment gaps to close, not permission to reopen approved policies or run production mutations.

## 1. Agree on the release boundary

**Owner: Product Owner + senior/release engineer.** Record the target commit, release owner, supported desktop OS/architecture, intended domains, approved data region, budget, operating/on-call owner, and which features are enabled or remain unavailable. Choose development, staging and production environments that cannot be confused.

| Decision | Required answer before provisioning |
| --- | --- |
| Website host | Where built static assets are served, TLS/domain owner, routing and release/rollback controls. |
| Backend host | Long-running API/stream/worker support, resource limits, outbound access, private networking, restart and observability ownership. |
| Desktop topology | Which services run on the user's machine and which run hosted; how local services are installed, started, updated and secured. |
| Data environment | Supabase project/region, allowed processors, connection mode and authorized operator identities. |
| Independent restore authority | Journal/head witness and fencing outside the product restore failure domain; independent freshness and key recovery owner. |
| Release scope | Website-only review, desktop pilot, or customer release; unavailable features must remain honestly unavailable. |

No hosting provider, region, purchased tier or recovery guarantee is selected by this document. Exact vendor CLI/DNS/certificate commands follow only after those choices and authorization.

## 2. Prepare a clean, reproducible release

**Owner: Developer/reviewer.** Check out the reviewed commit into a clean release workspace. Do not deploy the dirty development folder. Review [CI](../.github/workflows/ci.yml), lockfiles and runtime support; CI currently tests Python 3.11 and Node 20, which are evidence of compatibility, not a permanent security-support policy. Validate supported runtime versions before selecting production images; upgrades need their own compatibility checks.

Use the root `requirements.txt`, the frontend lockfile and the approved test dependencies. Record exact Python/Node/PostgreSQL/Auth/Storage/package versions and image digests used for acceptance. Do not silently install latest dependencies during release.

Exclude `.env`, keys, test credentials, private journals/backups, screenshots/prototypes, generated caches and isolated fixture launchers from distributed runtime artifacts. Inspect the actual website bundle and desktop package contents, not only Git status. Preserve private evidence outside public artifacts.

## 3. Provision secrets and database authority

**Owner: Authorized operator + developer.** Use [the credentials handoff](SENIOR_HANDOVER_CREDENTIALS.md). Supply each selected provider credential securely; do not require every provider or share personal passwords. Browser `VITE_*` values are public at build time. Service-role, SQL, webhook, signing and encryption secrets must never enter browser bundles or an untrusted renderer.

Provision the exact restricted SQL principals from the reviewed C15/admin/catalog/billing procedures. Confirm session identity, TLS/CA settings, role membership and negative permissions. A database owner connection or generic SET ROLE login is not equivalent to the intended runtime principal. Bootstrap credentials must not remain in the ordinary web process.

Verify Auth URL/JWT verifier/Storage target consistency; redirect allowlists; Google OAuth setup if included; SMTP and sender configuration only for authorized delivery. Preserve permanent suppression and existing encryption-key recovery contracts. Keys cannot be replaced indiscriminately without affecting historical state.

## 4. Reconcile schema and recovery before migrations

**Owner: Database/release operator.** Read-only inspection first: compare local migration files and remote history, prepared compatibility changes, function ownership, grants/RLS, constraints and private bucket policies. A dry run is not a migration, backup, permission test or readiness proof.

Before an authorized schema write, create and verify the required recovery set: database, Storage bytes/metadata, necessary configuration, key recovery and independent deletion/suppression evidence. A database dump alone is not a complete Storage or Auth/platform recovery guarantee. Free-tier observations do not prove absence of copies or provide an automatic backup-erasure deadline.

Rehearse ordered migrations against disposable synthetic data, then the staging target under separate authorization. Keep applied history intact; ship reviewed additive fixes for existing deployments where required. Never use an indiscriminate `db push`, history repair, trigger bypass or blanket grant as a startup workaround.

Record counts/hashes and safe postflight results without customer payloads. If a migration fails partway, inspect the committed migration boundary before resuming. Stopping deployment does not undo already committed changes.

## 5. Compose backend, workers and readiness

**Owner: Backend/platform engineer.** Start the normal application composition, not a fixture server. [FastAPI lifespan](../backend/app/main.py) wires subscription/catalog/billing/admin/privacy components and conditionally gRPC. Inventory which workers belong to this process and which require a separate supervised service. Avoid launching duplicate dispatchers or scheduling a task in every web replica accidentally.

The host must provide TLS ingress, automatic startup/restart, graceful shutdown, bounded requests/streams/uploads, safe timeout handling, private database access and useful content-safe diagnostics. A process being alive is not readiness.

For C15, require independent current evidence before service readiness; missing/stale/conflicting witness/checkpoint state must quarantine affected ingress and workers. Reconcile DB and object snapshots, invalidate restored exports, reapply suppression/restrictions, and prevent callbacks/queues/old clients from resurrecting content. Follow the [restore witness proposal](C15_PRODUCTION_RESTORE_WITNESS_PROPOSAL.md); local files/SQLite are not independent production durability.

Readiness must cover relevant HTTP, gRPC, direct Supabase Auth/REST/Storage and CDN/signed-capability boundaries. An application middleware gate alone does not fence direct external access. Do not bypass quarantine to make a health check return success. Provide separately scoped safe liveness/operator diagnostics and record acceptance of the implemented readiness probe; no `/health` contract is assumed here.

A conceptual API process command, **not a complete production launch profile**, is:

```text
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

It assumes a same-host ingress/supervisor. Containers/other topologies need reviewed binding/networking. Do not use `--reload` in production. Do not add multiple workers until in-memory streams, capacity limits, cancellation, worker ownership and durable task coordination have passed multi-process tests. See [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/).

## 6. Build and publish the website

**Owner: Frontend/release engineer.** Configure the intended browser-safe Supabase URL/key and actual API origin before building. Audit all API clients, Auth callbacks, allowed origins, credentials behavior and deep links against the target domain. Implement and test the production CORS/origin policy; do not allow every origin to avoid a configuration error.

Build from the frontend directory:

```powershell
npm ci
npm run build
```

Publish the generated `frontend/dist` assets through the approved static host. The host must support direct loads/refreshes of `/auth/login`, `/auth/dashboard`, `/auth/settings`, `/auth/admin` and `/auth/admin/subscriptions`, with the correct SPA fallback where appropriate. API paths must route to the API, not return `index.html` with status 200.

Verify public assets, correct MIME types, cache rules and stale-chunk recovery. Keep authenticated/private responses and downloads out of shared caches; do not weaken CSP/security headers without compatibility review. Browser build flags do not grant backend permissions.

Do not run Vite's dev server or `vite preview` as the production web server. See [Vite static deployment](https://vite.dev/guide/static-deploy.html). Dev ports 5173/5400 and temporary pricing-preview services are not production infrastructure.

## 7. Package and distribute Electron

**Owner: Desktop/release engineer.** Inspect [package scripts](../frontend/package.json), [main process](../frontend/electron/main.cjs), preload/IPC boundaries and the effective electron-builder configuration. The existing entry command is:

```powershell
cd frontend
npm ci
npm run electron:build
```

This is a packaging entry point, not a guarantee that signing, backend bundling or delivery is configured. Verify output location and targets from the effective builder configuration; do not invent an installer filename.

Define and test:

- Product name/version, OS/architecture, application/protocol identifiers, icons and publisher identity.
- Correct packaged renderer paths and intended backend/Auth URLs; no dev-server dependency or privileged bundled secrets.
- Provisioning/lifecycle of required local Python/native/ffmpeg/audio components. If they are not bundled, the installer must not silently assume a developer virtual environment exists.
- Context isolation, restricted IPC/preload, navigation/window permissions, safeStorage/session cleanup and authenticated account switching.
- Microphone/system-audio/screen permissions, overlay/hotkeys and supported hardware/OS behavior, using synthetic data.
- Appropriate OS code signing and, where applicable, notarization; secure signing-key custody.
- Installer install/uninstall, clean-machine launch, offline/reconnect behavior and migration/config compatibility with the hosted backend.
- A supported update strategy. Do not claim auto-update exists because Electron supports it; ship and test manual signed upgrades if that is the approved initial strategy.

Test the actual packaged artifact on a clean supported Windows machine, not only `electron:dev`. Other OS support requires its own implementation/build/acceptance. See [Electron distribution](https://www.electronjs.org/docs/latest/tutorial/distribution-overview) and [packaging/signing guidance](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging).

## 8. Feature-specific release gates

| Area | Required acceptance; owner |
| --- | --- |
| Identity | Developer/operator: ordinary login, Google if included, recovery, session switching, suppression/provisioning hooks and restricted-account denial. Actual Auth-engine/hosted behavior is separate from synthetic identity fixtures. |
| Privacy | Privacy/release owner: operation-bound proof, confirmations, private export expiry/access, content cleanup/retries, identity cleanup, truthful retained exceptions, retention and restore replay. Use the existing C15 matrix/enablement guide. |
| Admin | Admin/release owner: backend/database role boundaries, verified-UUID bootstrap, last-Super-admin concurrency, stale-role denial, metadata-only access, audit protection, campaign deduplication/suppression and retention. No automatic email-based grant. |
| Commercial | Product/billing owner: authoritative published terms, consent, usage, cancellation semantics and provider acceptance. Razorpay stays paused until the unresolved cases and explicit authorization are addressed. Coupons remain configuration-only under their approved policy. |
| Email | Email/operator: local capture first; then separately authorized real delivery, sender/SMTP, unsubscribe/suppression, callbacks/replay, bounded dispatch and truthful outcomes. |
| Sketch | Developer/product owner: [Sketch guide](SKETCH_ENABLEMENT_AND_TESTING_GUIDE.md), correct Electron integration, provider/model/source gates, persisted results and accounting. No website promise without its actual adapter/journey. |
| Audio/AI/Screen | Desktop/backend owner: enabled processors, TLS/streaming, cancellation, quotas, provider failure/fallback and bounded temp data. Do not assume every configured provider is active or promises zero retention. |

No optional feature should bypass its release gate. If deliberately excluded from the launch scope, it must be visibly unavailable and excluded from commercial promises; exclusions cannot conceal a broken requirement in the approved release scope.

## 9. Test staging before opening production

**Owner: QA + developers.** Use at least two synthetic customers, Admin and Super-admin fixtures. Keep real email/payment actions separately controlled. Record the tested commit/configuration and classify each result as offline unit, native PostgreSQL, fake boundary, actual local engine, installed app or hosted/provider acceptance.

Required evidence for the enabled scope:

- Relevant CI checks, formatting/static checks, frontend build and secret scanning of source, bundles and installers.
- Negative HTTP/database/Storage authorization; direct links; cross-account isolation; recent proof expiry/replay.
- Concurrent workers, crash/restart, lost acknowledgements, stale leases, retries and duplicate submissions.
- Desktop/mobile website journeys, keyboard/focus, loading/error/unavailable states and actual packaged desktop flows.
- Backup/restore rehearsal with later deletion decisions replayed before readiness, including objects/exports and missing witness evidence.
- Measured response times, memory, connection use, streaming concurrency and bounded load representative of the planned release.
- Monitoring alerts, redacted errors, uptime/readiness behavior, queue age and cleanup failure detection.

CI's skipped native/manual suites are not automatically passed acceptance. The known billing SQL issue needs a passing regression on the corrected real database path before enabling billing notifications. Reuse valid evidence for unchanged inputs; do not repeat external/provider tests without a reason and authorization.

## 10. Release, observe and recover

**Owner: Product Owner authorizes; release operator executes.** Record the exact approved commit/artifact hashes, target environment, approved feature flags, principals, configuration references, migration boundary, recovery set, evidence and named rollback operator. Apply the reviewed staged deployment/activation plan; do not combine schema changes, role bootstrap, provider sends and public exposure into one opaque command.

Release initially to the approved bounded audience. Verify login, critical customer paths, role restrictions, worker progress and monitoring on the real deployment. Keep content-safe diagnostics and respond to errors before expanding access. Authorization for this guide is not release authorization.

Rollback has different meanings:

- **Website/backend code:** redeploy the last compatible artifact and stop new affected admission; retain accepted durable tasks/barriers.
- **Desktop:** offer the approved compatible signed version and preserve account-owned state safely.
- **Database:** use a separately reviewed compatible forward fix or recovery procedure. Do not assume restoring old code reverses a migration.
- **Deletion, sends and provider actions:** irreversible effects are not undone by rollback. Restores must replay current deletion/suppression evidence before traffic; billing obligations remain authoritative.

## Final go/no-go record

| Item | Owner | Evidence required |
| --- | --- | --- |
| Host, region, domains, desktop topology approved | Product/platform | Signed deployment inventory and responsibilities. |
| Reproducible reviewed artifacts, no secrets | Developer/release | Commit/build hashes and scan results. |
| Schema, principals, Auth/Storage boundaries | DB/Auth operator | Migration/postflight and negative-role tests on intended target. |
| Independent witness/fencing and recoverable keys | Recovery operator | Current-head publication/readback, quarantine and restore tests outside product restore domain. |
| Required local engineering defects closed | Developer | Passing regression evidence, including identified runtime/origin/packaging gaps. |
| Actual enabled-feature acceptance | QA/provider owners | Labelled local-engine, hosted/provider and installed-app evidence. |
| Backups, objects, logs, processors and retention facts | Operations/privacy owner | Verified inventory, recovery exercise and accurate disclosures; no guessed deadlines. |
| Monitoring, support and rollback operational | Operations | Tested alerts/runbook and named response owner. |
| Separate release/activation approval | Product Owner | Exact target, scope, artifacts, remaining exclusions and authorization. |

Stop at any unmet required gate. The senior can close independent engineering work before hosting selection, but cannot honestly mark the full deployment ready without the target-specific evidence above.

## Related documents

- [Credentials handoff](SENIOR_HANDOVER_CREDENTIALS.md)
- [C15/C15.5 enablement](C15_C15_5_PRODUCTION_ENABLEMENT_GUIDE.md)
- [C15 closure matrix](C15_CLOSURE_MATRIX.md)
- [C15.5 implementation](C15_5_ADMIN_IMPLEMENTATION.md)
- [Production tracker](../SAIIA_PRODUCTION_PHASES_TRACKER.md)

Official documentation links were consulted on 26 November 2026. Documented platform capabilities do not prove this repository's deployment is configured or accepted.
