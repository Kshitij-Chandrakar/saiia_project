# C15 local Auth-engine rehearsal: executed setup, blocked engine

30 October 2026, Asia/Calcutta. **Actual Auth acceptance did not run.** The authorized setup/download/build attempt was executed, not replaced with another synthetic issuer. The pinned current Supabase Auth engine cannot build unchanged for this Windows host. No compatible container/Linux runtime is available without system installation. C15 remains incomplete and normal account deletion disabled. C15.5 and Razorpay remain paused.

## Baseline and preservation

Verified `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, origin `https://github.com/Kshitij-Chandrakar/saiia_project.git`, HEAD `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Entry: **87 uncommitted files**, final **93**. No switch, stash, commit, push, history rewrite or PR mutation by this task. Writes stayed in this isolated worktree and its owned temporary setup directory. Applicable instruction inventory found no AGENTS.md in the worktree/ancestors.

Read Stage 1/1B/1C/1D reports, approved decisions and actual setup/test foundations. Used Ponytail to attempt the existing native PostgreSQL/portable-tool approach rather than install system components. Graphify queried the existing graph **before and after setup work** (`auth privacy deletion session storage`, BFS, 63 nodes); no rebuild, unrelated corpus update or graph feedback write. Historical graph locations were navigation only. No application code or executable migration was changed in this attempt.

All earlier reports, evidence and screenshots are preserved: **47 historical file hashes match entry**. This turn's evidence is exclusively in `docs/evidence/c15-local-auth-rehearsal/`. Screenshot capture was disabled. Read-only entry/final comparison found the original worktree's roadmap/tracker diff changed during the interval; its observed final HEAD is `e613577c6c6db088b9cd70ef50c28156c0fac148`. This task did not write that worktree or alter those changes. The C15 worktree HEAD remains unchanged. This is an observation, not an attribution to another actor or a claim that original refs stayed fixed.

## Actual runtime setup attempt

| Component | Exact identity and result |
| --- | --- |
| Host | Windows amd64. Docker, Podman, Supabase CLI and Go absent from PATH. Standard Docker/Go installation locations also absent. `wsl --list --quiet` explicitly reports WSL is not installed. No system software/security policy was changed. |
| Preferred local workflow | No usable Supabase CLI/container runtime; no local `supabase/config.toml` in this checkout. Did not silently connect to a hosted project. |
| Auth source | Official **v2.197.0**, tag resolved through GitHub API to **`4eee58f296d9698a1c2c0ae14d7a0b379c7622d3`**. Downloaded the commit-pinned archive from official `codeload.github.com/supabase/auth`. SHA-256 **`b35bab74f6a45e0593e7a113e30f85c12c83bbb540940c3e82eeb0a9af76a297`**. No source patch. |
| Portable Go | Official **go1.27.3 windows/amd64**, checksum matched official Go download metadata before extraction/execution. ZIP SHA-256 **`f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff`**. `go version` executed successfully. Extracted go.exe SHA-256 `83b7ba66215e696414fa49462d0db2da4f4cf15c7bebd42f0b189fa04866999d`. No system-wide install or persistent PATH change. |
| Build | `CGO_ENABLED=0`, Windows amd64, `GOTOOLCHAIN=local`, `GOWORK=off`, `GOTELEMETRY=off`; task-owned Go caches. `go build -mod=readonly -buildvcs=false -trimpath -ldflags="-X github.com/supabase/auth/internal/utilities.Version=v2.197.0" -o ../auth.exe .` **failed**. No Auth executable produced. |
| Native PostgreSQL | Existing portable binary inspected: **17.11**. No rehearsal cluster/database/volume was created because the engine failed before service preflight. Existing PostgreSQL installations/clusters were not modified. |
| Browser runtime | Node **v24.16.0**; existing installed Playwright/Chromium and Vite fixture. Only independent component regression ran, on `127.0.0.1:5396`. |
| Container image digest | Not applicable: no container engine or image was run. Source/archive hashes above identify the attempted native build; they are not image digests. |

Official sources: [Supabase Auth commit](https://github.com/supabase/auth/tree/4eee58f296d9698a1c2c0ae14d7a0b379c7622d3), [Go distribution metadata](https://go.dev/dl/?mode=json). Artifact URLs, sizes and hashes are retained in [artifacts.json](evidence/c15-local-auth-rehearsal/artifacts.json).

### Exact engine blocker

The unchanged pinned source reaches Unix-specific socket calls in `cmd/serve_cmd.go:190` that cannot compile for Windows:

```text
undefined: unix.SetsockoptInt
undefined: unix.SOL_SOCKET
undefined: unix.SO_REUSEPORT
```

[Raw build failure](evidence/c15-local-auth-rehearsal/engine-build.txt); [pinned source](https://github.com/supabase/auth/blob/4eee58f296d9698a1c2c0ae14d7a0b379c7622d3/cmd/serve_cmd.go#L190).

Official tagged source compatibility was also inspected: v2.170.0/v2.180.0/v2.190.0 have the same Unix socket dependency. The v2.160.0–v2.169.0 configurations checked do not expose `BeforeUserCreated`; those tags were not substituted to claim the current integration passed. This is a bounded compatibility inspection, not a claim to have proved that every historical release cannot run.

No Auth source alteration, synthetic replacement, hook bypass, broader database grant or weakened assertion was used to obtain a pass. Installing Docker/WSL/system virtualization is outside this task's no-system-install boundary. A compatible existing Linux/container runtime is the missing prerequisite.

### Setup traffic, separate from application activity

Only public setup/documentation traffic occurred: official GitHub release/tag/source metadata and archives; Go distribution metadata/archive; Go modules through its public proxy with pinned source `go.sum` and read-only module mode. Go archive: **79,010,309 bytes**; Auth source archive: **1,069,852 bytes**. Module download volume was not metered. Build caches stayed under the explicitly owned temporary root. No application/customer data, Auth token, project key or mailbox code was sent in setup traffic.

No operational dotenv was loaded by an Auth/application service: neither service was started. The browser fixture sets `envFile:false`, explicitly clears hosted Supabase Vite variables and intercepts external requests. No real SMTP, Resend, Google, Razorpay or hosted Auth call occurred.

## Preflight status

| Gate | Result |
| --- | --- |
| Loopback Auth/database/catcher endpoints | **Not reached**: no Auth binary, no service configuration generated, no DB/catcher started. Do not interpret this as verified runtime isolation. |
| Catch-all local email delivery | **Not reached**: no email catcher was started and no test emails were generated. No external SMTP was configured. |
| Disposable migrations | **Not applied** in this attempt. Prior native/synthetic results remain historical only. |
| Temporary rehearsal-only activation | **Not enabled**. Normal C15 flags/config remain unchanged/off; no purge worker started. |
| Existing development services | Listener baseline captured before the independent UI run; all **37** baseline listener address/port/PID tuples remain present afterward. No normal service was stopped. |

## Scenario-by-scenario outcome

**Actual Auth scenarios passed: zero.** All engine-dependent cases below are blocked by the failed build before endpoint preflight. Earlier synthetic issuer tests are not relabeled as actual Auth acceptance.

| Requested scenario | Actual Auth result | Identity / session / product distinction |
| --- | --- | --- |
| Application mailbox OTP: correct/wrong/expired/replayed/superseded codes; subject/request/session binding; limits/concurrency | **Blocked** at engine setup. No code was generated or retrieved from a catcher in this run. | The implementation issues an **application-owned deletion OTP**, not Auth-issued login OTP. No claim about actual engine session/identity behavior. |
| OTP → subsequent typed confirmation; cancellation/navigation/interrupted verification | Engine-backed UI **blocked**. Independent component checks below passed with intercepted boundaries. | Component behavior does not establish Auth identity creation, session issuance or backend acceptance. |
| Password/TOTP, stale/refresh/wrong-subject/replay, unaffected users | **Blocked**. No real Auth password/TOTP endpoints were exercised. | No new MFA requirement or assurance-policy change. |
| Direct password signup / applicable new identity creation | **Blocked/unverified**. Supported before-create hook not loaded into an engine. | Identity creation prevention is not proved. |
| Existing restricted-account login / session issuance | **Blocked/unverified**. Token hook not invoked by an actual engine. | Session denial and product denial remain separate unaccepted runtime gates. |
| Linking / email changes / admin/import boundaries | **Blocked/unverified**. No external provider fixture was used to mask this gap. | Creation hooks do not automatically cover these mutations. |
| Bootstrap and concurrent signup/bootstrap versus acceptance | **Blocked** for actual Auth. No database migrations/transactions were run here. | Earlier native commit-fence evidence remains useful but does not prove engine transaction ordering. |
| Suppression dependency outage / hook caller credentials / malformed input / timeout | **Blocked** against actual Auth. | No claim that mocked hooks establish protected-operation behavior in the engine. |
| Browser closes; durable credential/global revocation; another account unaffected | **Blocked**. No synthetic acceptance or Auth logout call executed here. | No refresh-session, JWT or Storage-capability invalidation claim. |
| Worker restart/retry/expiry/missing key/uncertain response/stale lease; credential cleanup | **Blocked** for actual Auth. | Earlier fake-provider tests were not repeated or promoted as engine evidence. |
| Google OAuth / hosted Auth / actual Storage | **Not performed** and remain outside this local result. | No provider fixture or local result proves real Google behavior or signed Storage URL expiry. |

### Independent UI checks actually executed

Existing real `WebsiteSettings` component was exercised with synthetic client/API interception: **16 passed, 11.3s**. This covers the profile-menu/Settings path, disabled entry, exact typed confirmation, mailbox-code then newly typed confirmation, existing authenticator branch, duplicate clicks, uncertain outcomes/recovery, wrong account/password, expiry, account switching, unmount/late response, desktop/mobile layout and keyboard focus behavior.

[Browser component log](evidence/c15-local-auth-rehearsal/browser-component.txt). **This is not full website + actual Auth-engine acceptance.** External requests were aborted; no provider UI or real user data was involved. No historical screenshot was overwritten. Playwright stopped its owned Vite server; port 5396 is closed.

## Defects and code checks

Demonstrated defect/blocker: upstream pinned source has an unsupported Windows build dependency. No application integration defect was demonstrated because the engine never started. Consequently no speculative application fix, new migration, mock replacement or privilege change was made. Application lint/typing/build were not rerun without application changes; earlier results remain in their original reports. `git diff --check` passed for the documentation/evidence work.

The execution result is blocked actual acceptance after a real verified setup/build attempt, not an implementation-completed or planning-approved state.

## Review slices

The complete cumulative changed-file inventory is partitioned in [review-slices.json](evidence/c15-local-auth-rehearsal/review-slices.json), including all source helpers, generated SQL, tests, assets and evidence. Each slice is below 100 files with substantial room for fixes; no CodeRabbit filters or hidden omissions. Dependency order:

1. Approved requirements/policies and traceability documents: **11 files**.
2. Backend, SQL/package/configuration foundations and their native tests, depending on policy: **20 files**.
3. Website/UI/browser tests and required existing preview assets, depending on APIs: **23 files**.
4. Evidence/rehearsal report and review manifest, depending on the implementation slices: **39 files**.

These are proposed review groupings, not actual branches/commits/PR mutations. The 87-file entry scope was preserved; this attempt adds only the report and new evidence files. The manifest records exact cumulative and per-slice counts.

## Cleanup verification and exact leftovers

[cleanup.json](evidence/c15-local-auth-rehearsal/cleanup.json) records the result:

- No Auth process/executable, rehearsal PostgreSQL cluster/volume, email catcher, captured synthetic email or ephemeral runtime credential was created. There was therefore no database/email/credential cleanup to execute.
- Portable build processes have exited; no process executable under the owned root is running.
- The independent UI server is stopped and port 5396 is closed. All 37 baseline listener tuples remain present.
- **Artifact cleanup is incomplete.** Automatic approval review rejected the recursive `Remove-Item` request with **“blocked by policy.”** No alternate deletion tool, command reformulation or security-policy change was attempted.

Exact remaining directory: `C:/Users/chand/AppData/Local/Temp/c15-auth-engine-mtu1mjkl`, containing the ownership marker, official Go/source archives and extraction, Go dependency/build caches, public provenance and failed-build log. No operational credential or synthetic mailbox data is stored there. The directory remains on disk and requires cleanup through an allowed mechanism outside this rejected action; this report does not claim it was removed.

## Next bounded C15 stage and activation blockers

Repeat **this actual Auth-engine rehearsal** in an available authorized Linux/container runtime using the pinned engine and verified artifacts, disposable PostgreSQL and a strictly local email catcher, then execute the requested scenarios and fix demonstrated defects. Do not advance to export/purge or mark the Auth gate satisfied based on this attempt.

No additional fallback-policy decision is needed: mailbox OTP approval remains settled. Actual Auth hooks/metadata/mutation transaction semantics, real refresh-session recovery, local engine-backed UI acceptance and the prior cleanup/Storage/retention/restore/processor gates remain open. Normal deletion stays disabled; C15 is not complete. Cleanup artifact removal also remains unresolved due to the automatic rejection.
