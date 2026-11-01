# Subscription-admin user guide

**C13.2 implementation update (24 October 2026):** See [canonical approved policies](SUBSCRIPTION_APPROVED_POLICIES.md) and [actual implementation and acceptance](C13_2_IMPLEMENTATION_EVIDENCE.md). Catalog administration does not assign subscriptions or activate enforcement. Earlier unresolved assignment/Auto/result/resume/Clipboard policy notes are superseded for these approved matters; publication validity/tax/trial/refund requirements remain separate.

Intervucopilot | Source-checked 23 October 2026

This guide describes `/auth/admin/subscriptions` as currently implemented. Practice in an isolated environment first. It does not authorize shared migrations, permission changes or real publication. Never include tokens, passwords, connection strings or private account details in screenshots or support messages.

## Available now versus remaining prerequisites

| Available implementation | Separate prerequisite or limitation |
| --- | --- |
| Draft import, save, reopen, edit and preview | Compatible restricted database connection, reviewed schema and current admin permission |
| Review, publish, replace, retire and outcome recovery controls | Enabled lifecycle composition and explicit authoritative policy approval; fail closed when absent |
| Public catalog and landing-page pricing | Separate public-reader composition and currently visible published offers |
| Versioned permissions, allowances, prices and presentation | Catalog representation alone does not implement C13 runtime enforcement |
| Support/early-access presentation | Current service benefits remain Coming soon; labels do not implement services |

Payments, subscriber migration and Electron subscription enforcement are not operational through this workspace. Publishing does not charge customers or grant paid access. Overall C11 remains partial. The lifecycle panel still contains historical wording saying public pricing is unavailable; actual public display depends on the separate public-catalog configuration. Checkout remains unavailable.

## 1. Start and access the workspace

### Normal local development

Have a developer prepare the existing Python environment and frontend dependencies using the repository's environment instructions and lockfiles. Use two PowerShell terminals. These commands start existing applications; they do not install migrations or grant access.

Backend, with the prepared Python interpreter active:

```powershell
Set-Location E:/saiia_project/saiia_project/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
Set-Location E:/saiia_project/saiia_project/frontend
npm.cmd run dev
```

Open **http://localhost:5173/auth/login** and sign in through the existing website flow. Then open **http://localhost:5173/auth/admin/subscriptions** in the normal setup. The admin route itself shows the existing 404 page for signed-out or known non-admin accounts. Use website development, not `electron:dev`.

Vite binds port 5173 strictly. If occupied, identify its owner rather than killing an unrelated service. Stop a server you launched with Ctrl+C. Do not replace the Python environment or install system packages merely to work around an admin error.

### Configuration names: environment-administrator checklist

Keep values in the existing secure configuration mechanism. This table is not an instruction to enable every switch. `VITE_` values are browser-visible: never put a database password, DSN or service-role key there.

| Location | Variables | Purpose |
| --- | --- | --- |
| Frontend | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Existing browser authentication; intended Supabase project |
| Frontend | `VITE_BACKEND_URL` | Admin backend origin; defaults to `http://localhost:8000` |
| Backend cloud configuration | `SAIIA_CLOUD_MODE`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG`, `SUPABASE_RESUME_BUCKET`, `SUPABASE_EXPORT_BUCKET` | Existing cloud/auth configuration requirements; bucket settings are not billing settings. Service-role credentials stay backend-only |
| Backend drafts | `CATALOG_DRAFTS_ENABLED`, `CATALOG_DRAFTS_DSN` | Opt-in direct PostgreSQL draft composition; default off/empty |
| Backend lifecycle | `CATALOG_LIFECYCLE_ENABLED` | Separate opt-in lifecycle composition; default off, still requires schema, grants and policy |
| Backend public catalog | `CATALOG_PUBLIC_ENABLED`, `CATALOG_PUBLIC_DSN` | Separate restricted public reader; default off/empty |
| Vite public proxy | `CATALOG_DEV_PROXY_TARGET` | Optional process-scoped target for exact `/api/catalog` proxy; defaults to `http://127.0.0.1:8000` |

`HOSTED_COMMERCIAL_MODE` is not an admin-access switch. Keep payments, AI commercial admission and unrelated capabilities disabled. The legacy `SUBSCRIPTION_ADMIN_SUBJECTS` restart list is not sufficient authority for catalog operations.

The reviewed direct connection requires PostgreSQL 17 or later and the exact restricted login `catalog_draft_executor` for admin operations, or `catalog_public_reader` for public reads. Remote access requires `verify-full` TLS. A Supabase pooler username with a project suffix is not automatically compatible with current exact-username checks. An environment administrator must supply a reviewed compatible endpoint; do not substitute a superuser or privileged service credential. PostgREST exposing the permission probe does not automatically expose private SQL functions as RPCs.

### Confirm the environment before writing

1. Ask the environment administrator for the intended environment label, project reference and connection roles. Compare privately with frontend auth and backend configuration. A localhost address identifies a server, not its database.
2. In browser developer tools, inspect `GET /api/commercial/admin/me` on the configured backend. Confirm JSON, not the Vite HTML fallback. Never copy its Authorization header.
3. An authorized response includes `subscriptions.manage`; an authenticated ordinary account receives an empty permissions result and the website displays 404. An unavailable permission store is a separate failure.
4. Have the database administrator compare `supabase_migrations.schema_migrations` **and actual objects/functions/grants** with repository migrations using the [access preparation runbook](SUBSCRIPTION_ADMIN_ACCESS_PREPARATION.md). Do not blindly execute pending batches. Migration records alone do not prove usable schema or permissions.
5. Confirm the backend's direct draft connection targets that same intended environment. A successful auth probe does not prove draft storage works. Only then test a clearly labelled disposable draft.

A website 404 means the workspace is concealed for that identity; it need not be an HTTP 404 document response. Unavailable/503 can mean missing configuration, schema, grants, policy or connectivity. It does not prove lack of human permission. There is no in-app database-target inspector or grant editor.

### Granting access: authorized database-operator task

The current permission is **`subscriptions.manage`** for draft and lifecycle operations. There is no separate implemented publish-permission checkbox. Policy approval and lifecycle composition remain additional gates.

An authorized operator must confirm the target database, the intended account's exact existing Supabase Auth UUID and the approving operator's Auth UUID. Email may verify identity, but authorization uses UUID, never email matching or editable user metadata. Ordinary users cannot promote themselves.

Use the existing maintenance procedure in the [access preparation runbook](SUBSCRIPTION_ADMIN_ACCESS_PREPARATION.md), replacing its target-specific identities only after verification. It upserts `public.subscription_admin_permissions`: insert revision 1 if absent; reactivate an inactive grant with revision +1; do nothing when already active. The existing trigger atomically records `permission.change` in `catalog_admin_actions` with approver, reason and revision. Revocation sets an active row to `active=false` with revision +1 and verified approver/reason. Never delete grants or disable triggers. Do not reuse the runbook's named account for another team member.

Subsequent operations consult authoritative storage across workers; restart is unnecessary for permission removal. An in-flight transaction holding the permission lock may finish before a waiting revocation commits. Operations ordered after committed revocation are denied, including protected replay. A prior probe is not write authorization. Database login/function privileges are separate from the human grant.

### Isolated synthetic setup is different

The existing runner creates disposable native PostgreSQL, synthetic identities, explicit test policy and synthetic published offers. It does not authorize your normal signed-in account in that cluster. Its public demo is **http://127.0.0.1:5173/#pricing**. Normal Vite has used IPv6 `::1:5173` while this demo uses IPv4 `127.0.0.1:5173`; `localhost` and `127.0.0.1` can show different applications.

From the repository root, if the retained runtime files exist and IPv4 port 5173 is free:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
New-Item -ItemType File -Force tmp/catalog-manual.request | Out-Null
& E:/deepfake_envs/SaIIA/python.exe "$env:TEMP/c113c-test-launch.py" backend/tests/test_pricing_browser_native.py --pg-bin C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin
```

Stop only that runner from a second terminal at the repository root:

```powershell
Set-Content tmp/catalog-manual.stop (Get-Date).ToString('O')
```

See [local manual setup](CATALOG_LOCAL_MANUAL.md) for diagnostics, resource ownership and the one-hour lifetime. These retained paths are machine-specific, not a portable production installation. If absent, ask a developer to prepare the existing native harness. Never point it at shared Supabase. This public demo is not a general manual admin-login bootstrap. The existing `backend/tests/test_free_browser_native.py` verifies the admin browser with synthetic session setup, signed JWTs and native PostgreSQL; synthetic session setup is not real Supabase sign-in evidence.

## 2. Understand the workspace

| Term/control | Current behavior |
| --- | --- |
| Draft | Editable candidate; local changes are not stored until confirmed save |
| Saved revision | Exact stored revision; edits check it to prevent silently overwriting another administrator |
| `New draft` / `Create a blank draft` | Starts a blank `catalog.v1` candidate; use approved imports for current Free/Plus/Pro structures |
| `Import approved Free draft`, `Import approved Plus draft`, `Import approved Pro draft` | Load unsaved candidates, never publish; all disabled while an editor is open |
| `Open a draft by ID` / `Open draft` | Reopens saved unpublished work; no draft list/search exists |
| **Published offers** | Lists currently visible published offers from the same backend. **Open offer** loads protected terms; **Create draft version** makes an unsaved editable successor without copying an ID. **Refresh offers** reads the current catalog |
| `Draft ID & plan identity` | Expands identifiers; retain the saved draft ID privately |
| `Save draft` / `Save changes` | Creates/revises a stored draft with audit reason; no publication |
| `Preview saved draft` | Opens the centered Subscription review popup for the customer-facing structural preview; no publication or review-receipt write |
| Review receipt | Evidence of exact reviewed revision/terms/policy, not independent permission or payment confirmation |
| Published offer | Immutable versioned terms with separate availability state; public composition and visibility dates still apply |
| Replacement | New versioned terms replace a predecessor for new offers; history is preserved |
| Retirement | Removes availability for new offers without deleting history or cancelling subscribers/payments |

Tabs are **Identity**, **Prices**, **Features & limits**, **Discounts**, and, for current imports, **Usage & presentation**. `Internal notes` are private, not public pricing content.

### Review popup, Close and navigation

**Preview saved draft** opens the customer-facing preview in a centered **Subscription review** popup instead of a side panel. Close it with its top-right **Close subscription review** x or Escape to return to the editor. Requirement buttons close the popup and focus the relevant editor field. Closing preserves draft/revision and does not cancel requests, discard edits or publish. **Review for publication** remains a separate action: it opens publication validation/loading/errors and exact terms in the same popup style, then **Confirm review** records a receipt. **Publish reviewed offer** or **Replace reviewed offer** still requires its own explicit confirmation. **Open subscription review** reopens retained publication-review/recovery state without automatically repeating a mutation. A pending write keeps its original Operation ID and retry actions even when the popup is closed.

Long content scrolls inside the popup; its heading/x stay visible. Focus is contained, background scrolling is locked, and focus returns to the trigger on closing. Logout/account changes/revocation clear private popup state.


The x immediately right of the `Draft` badge is implemented, with accessible name **Close draft** and a discard explanation tooltip. It closes without another confirmation. Never-saved contents are discarded without a database write; saved records remain unchanged and only subsequent unsaved edits are discarded. Preview/transient editor state clears, import buttons become available again and focus returns to the import area. Record the saved ID before closing.

Close is disabled during active requests or uncertain save/lifecycle outcomes. Resolve those first: closing cannot erase recovery identity. Stale responses cannot reopen a closed editor. Logout, account switching and permission loss clear private state regardless of edit warnings.

Other navigation retains **Stay** / **Discard and leave**, or **Keep editing** / **Discard edits and continue** for local draft switching. Browser/tab exit uses the browser's native warning. Discard never deletes a saved record.

## 3. First-time walkthrough: approved template to saved preview

Use a disposable environment and synthetic identity, not real offer configuration.

1. Sign in and open `/auth/admin/subscriptions`.
2. Click the relevant **Import approved Free draft**, **Import approved Plus draft** or **Import approved Pro draft**. This is an unsaved candidate, not an automatic write.
3. Under **Identity**, check **Plan code**, **Display name** and **Description**; fill missing identity fields. For training, use a unique code such as `training-pro-example` and clearly labelled test name before first save. Do not casually rename real approved plans or try to move a saved draft to a different plan.
4. Compare the imported terms with the [Free decisions](FREE_PLAN_APPROVED_DECISIONS.md) and [Plus/Pro decisions](PLUS_PRO_APPROVED_DECISIONS.md):

   | Plan | Price | Auto | Resumes | Screen / follow-ups | NEW Clipboard saves |
   | --- | --- | --- | --- | --- | --- |
   | Free | Free; no invented paid currency/frequency | 600 seconds/IST day | 1 stored; 1 successful replacement/month | 5 analyses/month; follow-ups excluded | 5/month |
   | Plus | INR 399/month or 2,999/year | 18,000 seconds/month | 5 stored; unlimited replacements | Unlimited analyses/follow-ups | 10/month |
   | Pro | INR 899/month or 6,499/year | Unlimited | Unlimited storage/replacements | Unlimited analyses/follow-ups | Unlimited |

5. In **Prices**, enter currency amounts, not paise as rupees: INR 399.00 means 39,900 paise. Precision is validated without rounding. **Billing frequency** is independent of allowance resets: annual payment does not create an annual allowance pool.
6. In **Usage & presentation**, unlimited is explicit. Missing/unconfigured and zero do not mean unlimited. Read units: Auto amounts here are integer seconds, so 600 is 10 minutes and 18,000 is 5 hours.
7. Check reset cadence: daily at midnight IST; monthly on original signup day at midnight IST, clamped in shorter months then restored. No rollover. Auto includes silence, excludes stopped time and counts Both once. Initial resume upload differs from replacement. Clipboard counts NEW user-written saves, not reads or all stored answers; reset does not erase old answers.
8. Supply **Change reason**, then **Save draft**. Incomplete but structurally valid drafts may be saved. Wait for confirmed success/revision; a timeout or field error is not success.
9. Record **Saved draft ID**, click **Close draft**, then use **Open a draft by ID** and **Open draft**. Confirm stored values survived.
10. Make an intentional test edit, enter **Change reason**, click **Save changes**, then **Preview saved draft**. Resolve errors and pending requirements. Further changes require another save/preview.

All plans represent available configured models and unlimited manual audio/transcription/answers, history/exports, AI Notes and Ask AI. Operational safeguards and retention remain separate. Sketch is excluded from Free and included in Plus/Pro. Support and early access remain Coming soon where unavailable. Clipboard answers are user-written and not individually editable/deletable; account-wide privacy deletion is separate.

**Duplicate plan code:** importing again creates a separate candidate, not an update. Close the duplicate and reopen the original draft ID. If lost, an authorized operator must locate it; there is no UI list. For an existing published plan, use **Create a new draft version**, not a new template import with the same stable code.

## 4. Configure an existing registered feature: isolated Sketch example

Use a disposable **Pro v3** candidate with unique test identity. Its approved template already includes Sketch; to practice enabling a previously excluded feature, change Excluded then Included locally without saving the intermediate state. Do not change the approved real Free allocation for training.

1. In **Features & limits**, find **Introducing Sketch**, stable key `sketch.generate`. Select **Included**. **Excluded** records denial; **Not set** omits the entitlement and is not permission.
2. Sketch has no registered usage meter here: do not invent a quota. For a metered feature, use **Add a usage allowance** under **Usage & presentation** and select a compatible included-feature meter. Example: the approved Plus `auto.authorized_running` allowance is `limited`, amount `18000` seconds, **Reset auto.authorized_running** = `month`. This illustrates controls, not a change to Pro's unlimited terms.
3. Storage and concurrency differ from quotas. **Add a registered limit** exposes compatible limits. V3 also has **Resume storage capacity** / **Maximum stored resumes**. Never substitute total saved-answer storage for monthly NEW saves.
4. Edit **Label sketch.generate** and **Information sketch.generate** in its existing **Usage & presentation** row. Keep approved wording unless deliberately changing it with approval. Templates also include Clipboard presentation. There is no general arbitrary presentation-row creation control. Wording does not grant access. Preview-eye destinations are unavailable; pricing uses information icons only.
5. Save with a reason, close/reopen, then preview. Free v2 has conservative readiness restrictions; enabling Sketch there can remain publication-blocked. Do not change a contract version manually to bypass readiness; request developer-reviewed compatibility.
6. Follow section 7 to review and publish/replace only in the isolated environment. When public composition is configured, verify `/api/catalog` and landing-page `#pricing`: Sketch inclusion/strikethrough must match. Other registry features may appear in JSON without automatically gaining a compact card row; renderer support is developer work.

This verifies catalog representation/presentation, not C13 runtime enforcement.

## 5. Add a genuinely new product feature

An administrator cannot create working application behavior by adding a label. Developer prerequisites are:

1. Implement the capability and ownership/security checks.
2. Register its stable feature key and any compatible meter/unit/operation mapping in backend and supported client contracts.
3. Extend validation/storage/explicit versions only if necessary; preserve historical snapshots/fingerprints and bind reviews to all new contractual terms.
4. Add authoritative entitlement/enforcement and compatible UI. Current C13 integration is deferred; registry presence is not an active paid gate.
5. Test compatibility and abuse paths; release compatible backend/client code.
6. Expose supported editor configuration, then let the admin save, preview, review and publish it.

New Electron screens, capture behavior, IPC or unsupported contract handling need a compatible Electron release. An existing supported field can be reconfigured without a release only where released code already consumes it. Current source does not establish Electron subscription enforcement or entitlement refresh. Its later scope is current plan plus Upgrade in Buy Credits; full comparison stays on the website. Restarting Electron is not authoritative enforcement.

## 6. Change prices or allowances

1. Find the plan under **Published offers** and click **Open offer** to verify its version. You can also use **Create draft version** directly in that row. Manual **Open an offer by ID** remains available for a known historical/scheduled/retired version.
2. From the opened offer, choose **Create a new draft version** (or use its list-row **Create draft version**). This copies terms for the same stable plan into a candidate with new draft/price identifiers; it does not edit the snapshot.
3. Edit **Prices** or **Usage & presentation**, enter **Change reason**, save, reopen and preview.
4. Choose **Replace current offer** under **Publication action**, review the exact new saved revision and confirm the correct predecessor before replacement.

Published snapshots and prices remain immutable. Recorded terms are preserved; there is no implemented subscriber migration, proration, refund or payment-update workflow. Do not promise publication changes existing subscribers. Preserved history supports that future system; it does not prove the system is operational.

**Discounts** supports authoring percentage/fixed definitions, compatible currencies, eligibility/redemption/application references, validity, redemption limits and duration. **Discount stacking** supports **Do not stack**; Not decided is unresolved. This does not implement checkout redemption or guarantee pricing-page discount display. Tax, trial, discount, review-validity and subscriber policies need explicit approval. Never fabricate reference strings to clear warnings.

## 7. Review, publish, replace and retire

### Prerequisites

You need current `subscriptions.manage`, a confirmed clean saved draft, preview with no errors/pending requirements, lifecycle schema/function grants, enabled composition and authoritative approved policy. `20261023150000_catalog_policy_public_read.sql` supplies policy/public primitives separately from the ten core migrations; an environment administrator must inspect actual application status. Editor users should not apply it themselves.

The resolver requires versioned approved policy, references, model-registry version, validity window and supported reviewer rule. It invents no default expiry. `current_subscription_admin` permits the supported reviewer behavior only when explicitly approved for that environment. The workspace cannot create policy approvals; permission alone is insufficient.

### First publication or replacement

1. In **Review and publication**, choose **Publish a first offer** or **Replace current offer** under **Publication action**. For replacement, open the intended predecessor and create/save its new draft version first.
2. Set **Offer starts at (IST)** and optionally **Offer ends at (IST, optional)**; enter **Lifecycle reason**. Enter India Standard Time (Asia/Kolkata), regardless of your computer timezone. The UI converts to UTC for the API and shows IST in confirmations and offer details. Leave the optional end blank unless the offer should expire. Availability dates are separate from allowance resets.
3. Click **Review for publication**. In **Confirm reviewed terms**, inspect saved revision, features, prices, allowances, availability and predecessor if replacing. Choose **Confirm review** or **Cancel**.
4. A current receipt enables **Publish reviewed offer** or **Replace reviewed offer**. Click it, inspect **Publish this offer?** or **Replace this offer?**, then choose **Confirm publication** or **Confirm replacement**.
5. Wait for committed server confirmation. Record offer/version and **Operation ID**. The source becomes read-only. Publication atomically records immutable terms, availability, receipt consumption, audit and catalog version; it does not charge/grant customer access.

Content edits, another administrator's action, changed preconditions or expired/changed policy can invalidate review. Save, preview and obtain fresh review. A receipt for old terms is not reusable approval for new ones. Server checks remain authoritative even when a button was enabled.

### Retirement

1. **Open offer** with its exact ID and verify the version/terms.
2. Enter **Lifecycle reason**, then **Retire this offer**.
3. In **Retire this offer?**, confirm the exact target with **Confirm retirement**.
4. Verify the confirmed **Retired offer** view. History remains; this does not cancel subscriptions/payments or revoke existing entitlements. A concurrent precondition change requires fresh reading/review.

### Conflict and uncertainty recovery

| Outcome | Safe next action |
| --- | --- |
| Revision conflict | **Review latest revision** preserves local edits. Inspect differences, then deliberately choose **Replace local edits with latest** or **Keep local edits**. Neither is automatic merging |
| Unknown save outcome | Keep the tab open and use **Retry same save**, preserving identity and payload. Do not refresh/import a replacement mutation to guess the result. Close stays disabled |
| Unknown lifecycle outcome | Keep **Operation ID**; **Check pending operation** reads without repeating a write. **Retry same action** preserves identity/semantics when needed |
| After lifecycle reload | Paste the recorded ID into **Check an operation by ID**, then **Check operation**. This never automatically repeats the mutation |
| Conflicting request identity | Stop and investigate; do not generate new keys until something succeeds |
| Revoked permission | Recovery also checks current permission. Contact the authorized operator; old success/receipt is not access |
| Policy/storage unavailable | Completion is unconfirmed; restore service and recover the existing operation before deciding on a new write |

Leaving an uncertain save loses its in-memory retry details, not necessarily the server mutation. Unlike lifecycle operation lookup, no equivalent save-recovery-by-ID UI is provided. Have a developer/operator establish saved revision/audit outcome before a new write if recovery information was lost. A timeout never proves failure or success.

Private terms/receipts are not stored in browser persistence for recovery. Retain necessary IDs only in an approved internal work record. Logout/account changes clear protected state. Durable replay avoids duplicate supported mutations/audit; never blindly resubmit a new consequential operation after a timeout.

## 8. Reusable verification checklist

- [ ] Confirm intended environment/database and current permission before writing.
- [ ] Use a labelled test draft; record its saved ID/revision.
- [ ] Save, close and reopen: stored values survive; discarded local changes do not.
- [ ] Preview the saved revision; resolve errors and pending requirements.
- [ ] Review exact terms and confirm the correct predecessor/version.
- [ ] Record committed offer/operation IDs; resolve uncertainty before another mutation.
- [ ] With public composition configured, `GET /api/catalog` includes only supported, published, currently visible offers. Drafts/private notes/audit must not leak. HTTP 200 with `offers: []` is empty; 503 is unavailable.
- [ ] Check existing landing-page `#pricing`, Monthly/Yearly, annual totals, approximate monthly equivalents and accurate savings: Plus 37%, Pro 39% when rounded down.
- [ ] Check Sketch inclusion/strikethrough, per-plan Clipboard information, shared benefits and **Allowance details**. Support stays Coming soon where unavailable.
- [ ] Refresh after replacement/retirement. Responses use `no-store`; the website refreshes on focus/visibility and approximately every 30 seconds while visible. It is not push-based. Reload for a prompt check; consider offer start/end times.
- [ ] Verify a separate ordinary account gets the existing website 404 and backend mutations stay denied. Do not revoke the sole administrator just to test this.
- [ ] Paid CTAs remain **Checkout coming soon**. Free **Get started** follows existing signup. Pricing state and publication do not grant entitlements.
- [ ] Record Electron/C13 enforcement as unverified/deferred unless separately implemented and tested.

## 9. Troubleshooting

| Symptom | Meaning | Admin action | When a developer/operator is needed |
| --- | --- | --- | --- |
| Admin route shows 404 | Signed out, invalid session or known non-admin | Sign in to intended account | Verified UUID still denied; operator checks current grant |
| Admin access unavailable / 503 | Store/configuration failure, not ordinary denial | Stop writes; confirm backend | Schema, grants, JWT/project, endpoint or connectivity |
| Probe returns HTML 200 | Frontend fallback, not API JSON | Inspect actual origin safely | Correct API configuration/routing |
| Probe works, saving fails | Human permission and direct storage are separate | Preserve edits/retry identity | Restricted DSN/login, migrations, pool or TLS |
| Duplicate plan code | Existing stable plan; import is not update | Reopen saved ID/new version | Authorized operator locates lost ID |
| Preview pending requirements | Not publication-ready | Read field/policy messages | Missing capability readiness or approved policy; never invent references |
| Stale review/revision conflict | Terms or state changed | Read latest; deliberately save/preview/review | Unexplained conflict or unresolved prior outcome |
| Policy unavailable | Missing compatible approval/current window | Keep private | Policy owner/environment operator approves and configures |
| Close disabled | Active request or uncertain mutation | Wait/use existing recovery | Outcome cannot be established |
| Plans temporarily unavailable | Public composition failed/off | Use visible **Try again** after recovery | Reader/schema/grants/configuration |
| Empty catalog | Valid read, no currently visible offers | Check environment/publication/dates | Unexpected filtering |
| Retired offer still visible | Page may await refresh | Reload/focus; allow refresh interval | Persisting stale response/failed refresh |
| Pooler username rejected | Exact reviewed direct-role requirements | Do not use privileged workaround | Compatible endpoint/role needed |
| Checkout unavailable | Expected before C12 | No guessed payment URL | Payment implementation/release |
| Catalog quota does not restrict app | Representation is not C13 enforcement | Do not promise unverified enforcement | Authoritative metering/entitlement integration |

## 10. Responsibilities

| Role | Owns | Does not replace |
| --- | --- | --- |
| Subscription admin | Approved draft terms/text, reasons, IDs, preview/review, deliberate lifecycle actions and recovery | Implementation with labels; publication with preview; recovery with new retry keys |
| Application developer | Features/registry/contracts, validation/versioning, APIs/UI, tests, C13 and Electron integration | Server authority with client state; missing policy with defaults |
| Database/environment administrator | Target verification, reviewed migrations/roles/TLS/secrets, verified-UUID grants/revocation/audit, approved policy storage | Human authorization with service-role RLS bypass or superuser runtime credentials |

Before real configuration/publication, consult the decision records. Free/Plus/Pro allocations and INR prices are recorded; unresolved tax, trial, discount, review validity, subscriber migration, refund and payment policies must not be invented. Synthetic testing does not authorize shared deployment.

## Source verification and illustrated controls

Commands and labels were checked against current repository source. No services, shared migrations, grants or offers were changed for this documentation task. Prior native/browser acceptance is recorded in the plan/audit separately from deployed readiness.

- [Workspace and Close state](../frontend/src/auth/SubscriptionAdmin.jsx), [editor fields](../frontend/src/auth/CatalogDraftFields.jsx), [usage/presentation controls](../frontend/src/auth/CatalogPolicyFields.jsx), [lifecycle and recovery](../frontend/src/auth/CatalogLifecycle.jsx).
- [API client](../frontend/src/auth/catalogApi.js), [website routes](../frontend/src/App.jsx), [frontend commands](../frontend/package.json), [public proxy](../frontend/vite.config.js).
- [Backend configuration](../backend/app/config.py), [cloud configuration](../backend/app/cloud/supabase_config.py), [authoritative permission boundary](../backend/app/commercial/admin_access.py), [database composition](../backend/app/commercial/catalog_database.py), [publication policy](../backend/app/commercial/publication_policy.py).
- [Versioned contracts](../backend/app/commercial/catalog_contract.py), [public pricing renderer](../frontend/src/landing/CatalogPricing.jsx), [core storage/grant trigger](../supabase/migrations/20261022120000_catalog_storage_foundation.sql), [policy/public migration](../supabase/migrations/20261023150000_catalog_policy_public_read.sql).
- [Implementation plan](C11_C13_SUBSCRIPTION_IMPLEMENTATION_PLAN.md), [readiness audit](C11_SUBSCRIPTION_READINESS_AUDIT.md), [access preparation](SUBSCRIPTION_ADMIN_ACCESS_PREPARATION.md), [isolated setup](CATALOG_LOCAL_MANUAL.md).

Screenshots below are retained **synthetic-fixture** evidence from prior Close-control browser checks, not a real account or production database. The numbered explanations annotate the controls without modifying the captured interface.

![Synthetic desktop editor: Close beside Draft](assets/subscription-admin/close-draft-desktop.png)

1. The x beside **Draft** closes only local editing; its tooltip explains retained saved records.
2. Tabs separate identity, prices, permissions and usage/presentation. Keep the saved ID before closing.
3. The associated preview belongs to the editor session and disappears on Close.

![Synthetic mobile editor: Close beside the badge](assets/subscription-admin/close-draft-mobile.png)

On narrow screens the same control stays beside the badge. Disabled Close during uncertainty is intentional: resolve the operation rather than discarding its identity.


### Finding existing offers without copying IDs

Use **Published offers** inside **Review and publication**. Each row shows the plan name, version, Published status and selectable offer ID. **Open offer** uses the existing protected offer read. **Create draft version** reads the current immutable source and copies it locally; no database write occurs until Save draft. Existing unsaved edits require the same Keep editing / Discard edits and continue decision. After publication/replacement/retirement, the list refreshes; **Refresh offers** also updates it manually.

This discovery list uses the **same backend's** existing public catalog, not the localhost pricing-preview proxy or a hardcoded plan array. It requires configured public composition. A missing public catalog shows unavailable, while a successful empty response shows no currently visible offers. Scheduled, expired and retired versions are excluded by the existing public projection; use a known ID to open those. A full private history/search API is not implemented by this change. Account permission gates and protected reads remain mandatory; ordinary accounts still see 404.

## Account enforcement continuation (24 October 2026)

Catalog publication still does not assign subscriptions or enable checkout. The default-off [C13.2 integration](C13_2_IMPLEMENTATION_EVIDENCE.md) now connects native account authority to canonical execution and actual Electron Current plan/Upgrade. New verified Free enrollment requires trusted pinned configuration; real backfill/paid activation is not an admin draft action. Over-cap resumes are retained and their owner can choose the permitted active set on the website Resumes screen. No real activation/shared changes were made; see the evidence for isolated verification and remaining installed/hosted release checks.
