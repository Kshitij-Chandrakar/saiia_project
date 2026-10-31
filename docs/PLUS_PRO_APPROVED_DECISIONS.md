# Approved Plus/Pro and C11.4 local integration - 2026-10-23

Status: integrated local implementation; production activation and overall C11 acceptance are **not** claimed. This decision record supersedes earlier Plus/Pro-pending checkpoints and proposed unlimited Plus Clipboard/priority-support claims. The original pricing image is inspiration only. Executable reference terms live in the existing admin import architecture, not a second public pricing array.

## Confirmed terms

| Term | Free (unchanged v2) | Plus (v3) | Pro (v3) |
|---|---|---|---|
| Monthly / annual payment | Free, no currency or paid interval | INR 39,900 / 299,900 minor units | INR 89,900 / 649,900 minor units |
| Annual display | Free under either toggle | INR 2,999 total billed annually; approximately INR 250/month | INR 6,499 total billed annually; approximately INR 542/month |
| Annual comparison | Not applicable | INR 4,788 for 12 monthly payments; floor savings 37% | INR 10,788 for 12 monthly payments; floor savings 39% |
| Auto running allowance | 600 seconds / IST day | 18,000 seconds / original-signup month | Explicit unlimited |
| Starts / measurement | Any number until cumulative allowance is used; includes silence, excludes stopped time, combined audio once | Same measurement | Same measurement, no subscription time quota |
| Stored resumes | One | Five simultaneously | Explicit unlimited capacity |
| Successful replacements | One / original-signup month, initial upload distinct | Unlimited | Unlimited |
| Screen analyses / follow-ups | Five/month; follow-ups excluded | Unlimited analyses; follow-ups included without subscription quota | Same as Plus |
| NEW user-written Clipboard saves | Five/month | Ten/month (supersedes unlimited proposal) | Explicit unlimited |
| Sketch | Excluded, Introducing Sketch struck through | Included | Included |
| Support / early access | No support benefit configured | Standard email support; Coming soon until an operational workflow exists (supersedes priority support) | AI support with human escalation and early access when released; Coming soon |

All plans retain company-funded providers, dynamically configured supported/available models, unlimited manual capture/transcription/answers, history/exports/AI Notes/Ask AI, and operational safeguards. Clipboard reads consume no saves; resets retain answers; users cannot individually edit/delete them. Account-wide deletion remains separate.

Daily periods begin at midnight Asia/Kolkata. Monthly allowances use the original signup-day anchor at midnight IST, clamped in shorter months then restored. Annual payment never creates an annual allowance pool. No rollover or subscription-start anchor was added. The existing IST helper and Free JSON/reference, v1/v2 registries and previously prepared migrations were preserved byte-for-byte.

## Requirement completion

| Requirement | Local result / evidence | Production dependency |
|---|---|---|
| Approved imports, save, reopen, edit, preview | Completed via explicit Free/Plus/Pro actions and existing authenticated draft APIs; UUID price identities assigned per candidate; no import writes until Save | Real catalog configuration remains an explicit admin decision |
| Versioned terms, validation, CAS and durable retries | V3 adds storage capacity and bounded service-benefit metadata; existing C11.3 service, transaction authorization and idempotency stay authoritative; v1/v2 decoding/fingerprints unchanged | Reviewed migrations/roles on an authorized deployment |
| Review/publication/replace/retire | Existing immutable lifecycle reused; actual server policy resolver and native transactions exercised with synthetic grants/policies | Explicit approved policies, validity window, references and secured lifecycle configuration |
| Public catalog | GET /api/catalog, dedicated read-only role, one SQL snapshot for revision/time/visible publications, explicit safe DTO projection, no-store | Default-off public configuration and reviewed reader credentials |
| Landing pricing | Existing heading/section; three reference offers after synthetic publication, monthly/yearly, exact integer money/savings, responsive pastel cards, safe signup and disabled paid CTAs | Publish real approved offers only after policy/deployment readiness |
| Support readiness | Standard email, AI/human escalation and early-access metadata retained as Coming soon | Support operations/chatbot/escalation/release program are separate work |
| Sketch/Clipboard | Existing accessible controls reused; exact Free information copy retained; Plus/Pro save-count copy; excluded Sketch only struck through; preview eyes disabled | No preview assets/destinations were found or invented |
| Native browser acceptance | Browser imports/saves/reopens, changes policies/storage/support metadata, reviews/publishes all three, renders public prices, replaces/retires Pro | Synthetic Supabase session source; actual signed JWT verification and native SQL, not deployed Supabase acceptance |
| C12/C13/Electron | Intentionally unchanged | Payments, usage reservations/enforcement, current-plan/Upgrade desktop slice remain pending |

## Source and files

- Domain: `backend/app/commercial/catalog_contract.py:341` V3 readiness registry, `:362` OfferTermsV3, `:888` public V3 projection. V3 alone recognizes existing saved-answer diagrams and screen Continue as implemented source paths; this does not certify hosted operation or provider results. V2 stays conservative and unchanged.
- Capability evidence: `backend/app/api/answer_diagrams.py`, `backend/app/services/answer_diagram_service.py`, `frontend/src/components/DiagramSection.jsx`; `backend/app/api/screen_context.py`, `backend/app/services/screen_context_service.py`, `backend/app/models/screen_context.py`. Existing New/Continue/Passage mapping still needs C13 operation/charging decisions; no new charge rule was invented.
- Support audit: no account support chatbot/ticket/human-escalation API or UI was found in backend API/frontend auth source. Existing transactional email is not an operational customer-support service. Ask AI remains a session feature, not a support substitute. The requested Pro chatbot is newly requested future work, not implemented here. No support address, SLA or response-time claim was added.
- Trusted policy: `backend/app/commercial/publication_policy.py:9`; anonymous public projection: `backend/app/commercial/public_catalog.py:10`; existing pool: `backend/app/commercial/catalog_database.py:37`. Main lifecycle, config and exact hosted ingress composition extended; no provider execution path changed.
- API/readers: draft/lifecycle DTOs, review contract/service, boundary and pool version handling were extended. Existing store/draft/lifecycle transaction implementations and original migration history are reused.
- Reference/import/editor: `frontend/src/auth/approvedPlusTerms.json`, `approvedProTerms.json`, `catalogRegistryV3.json`, `catalogV2.js:62`, `SubscriptionAdmin.jsx:457`, `CatalogDraftFields.jsx`, `CatalogPolicyFields.jsx`, `CatalogPolicyPreview.jsx`, `CatalogLifecycle.jsx`, `catalogApi.js`, `catalogDraft.js`, `catalogLifecycle.js`. Free imports remain v2. Storage/benefit labels remain editable; coming-soon metadata cannot activate a service.
- Customer renderer: `frontend/src/landing/CatalogPricing.jsx`, `catalog-pricing.css`, `pricingMoney.js`, existing `LandingPage.jsx:2751`. No separate pricing page, Electron screen or hardcoded public offers. Existing fixed-height pricing wrapper is overridden only for this section to prevent FAQ overlap.
- Tests: `backend/tests/test_catalog_v3.py`, `test_pricing_native.py`, `test_pricing_browser_native.py`; `frontend/src/auth/catalogV2.test.js`, `frontend/src/landing/pricingMoney.test.js`, `frontend/tests/catalog/pricing.spec.js`, `pricing.integration.spec.js`. Existing presentation fixture now supplies a valid empty public response instead of expecting the removed pre-C11.4 placeholder; its accessibility/layout assertions are retained.

### Additive SQL and authority

Prepared and applied **only to task-owned native disposable PostgreSQL**:

1. `supabase/migrations/20261023140000_catalog_v3_terms.sql`: adds version-pair/triple acceptance, updates accepted immutable-offer/lifecycle guards for V3; no historical record rewrite, role expansion, prices or catalog seed.
2. `supabase/migrations/20261023150000_catalog_policy_public_read.sql`: deployment-owned policy table with RLS and no application/client writes; revision guard; current-permission-checked policy resolver with FOR SHARE locking; dedicated NOLOGIN catalog_public_reader and exact read-function EXECUTE. No real LOGIN/admin/policy/offer is provisioned.

Policy document schema v1 requires explicit version, reviewer_rule_ref, model_registry_version, absolute valid_from/valid_until and allowed_refs. There is no default validity duration or approval. Only explicitly configured current_subscription_admin review is supported; other rules fail closed, rather than pretending a second-reviewer workflow exists. References for subscription/migration must match the row, and all limit/reset/tax/rounding/discount policy references must be explicitly approved. The canonical document fingerprint, monotonically advanced approval revision and live backend model-key fingerprint bind receipts. The SQL permission lock precedes policy locking, and the policy lock stays through the review/publication transaction. Revocation committed first denies subsequent operations; an operation holding the share lock may commit before a waiting revocation. Missing/inactive/corrupt policy is unavailable. Policy management is deployment-owned; no policy editor/bootstrap route was added.

`CATALOG_DRAFTS_ENABLED`, `CATALOG_LIFECYCLE_ENABLED` stay default false. New `CATALOG_PUBLIC_ENABLED` defaults false and `CATALOG_PUBLIC_DSN` defaults empty. No .env/.env.example was changed. The same reviewed pool implementation supports a dedicated public-only role mode: required catalog_public_reader, no memberships/bypass/table privileges, fixed safe SQL function/search path, bounded connections/waits/statements/transactions, reset on return, no identity persistence. The admin role gets only the exact policy resolver EXECUTE. Public credentials cannot execute admin policy functions or mutate tables. Service-role RLS bypass is not authority; service_role has no new EXECUTE/table grants. Superuser/schema-owner maintenance remains outside ordinary application guarantees.

The public SQL query joins actual publication provenance and visibility, filters active time windows, and binds revision/time/offers in one statement snapshot. Unsupported future versions are omitted; corrupt supported snapshots fail safely unavailable. Python recomputes canonical fingerprints and projects explicit fields; private notes, source drafts, policy refs, receipts, audit, credentials and future payment mappings are excluded. No-store avoids stale persistent/shared caches. The website reloads on focus/visibility and every 30 seconds while visible; each response atomically replaces its rendered set. An already open tab may remain stale until that bounded refresh; it never grants access or checkout. Empty is 200/offers[]; missing composition/database is 503/catalog_unavailable. Wrong methods/aliases remain blocked; only exact GET /api/catalog was added to hosted ingress. Paid CTAs stay disabled, with exact offer/version/price identifiers retained as data for future checkout; no guessed payment URL or redirect authority.

### Migration rollout and rollback

No shared/remote database was inspected or altered. Deploy only with separate authorization: verify all prior migration histories; apply additive files; provision restricted LOGIN secrets/TLS outside clients; configure approved absolute policy windows/references/reviewer rule/model registry; verify ownership, RLS, ACLs, pool credentials/JWT project alignment and exact proxy routes. Do not use test policies/grants as production configuration. Import/review real offers explicitly; publication does not imply C12 readiness or C13 enforcement.

Rollback disables public/lifecycle composition, then reverts compatible client display if necessary; preserve all V1/V2/V3 terms, consumed receipts, audit, operation results and subscriber references. Do not delete historical snapshots, downgrade stored V3 records or run older V1/V2-only readers against them. Roll forward schema corrections; never edit remotely applied history. No actual deployment was performed here.

## Verification evidence

| Check | Actual result |
|---|---|
| Backend catalog/v1-v3/storage/IST/admission/registry | 213 passed |
| Authoritative admin access, separate process | 41 passed |
| Node website/auth/catalog plus money | 119 passed |
| New native policy/public projection suite | 3 passed, PostgreSQL 17.11; actual restricted pool roles/JWT, policy locks across independent connections, mutation denial, policy revision guard, safe/unavailable API, synthetic replace/retire/replay/history |
| Existing v2 native API/storage/review | 4 passed; historical bytes preserved, corruption denied, Free no-currency publication |
| Existing lifecycle native API | 22 passed; races/retry/revocation/rollback/pool isolation and safe errors |
| Existing draft native API | 40 passed |
| Playwright workspace/lifecycle/presentation/pricing | 42 passed; mocked auth/API fixtures are identified separately from native integration |
| Real native browser pricing integration | 1 passed (15.0s browser, 29.32s runner); actual HS256 signature/issuer/audience/expiry verification, server actor, services, restricted native pools and database policy; all three imports to public landing, Plus storage/support editing, exact prices, periods, savings, mobile/desktop/tooltip bounds, replacement/retirement |
| Production frontend build | Passed, existing large-chunk advisory remains |
| Graphify | Before query completed; after-code structural refresh: 31 changed code files, 6,994 nodes/16,000 edges; post-query finds resolver/import/public API/cards. No semantic-provider calls. CLI warns skill 0.9.1/package 0.9.29; no installation changed |
| Whitespace/source integrity | git diff --check plus changed-file whitespace/syntax validation; unrelated baseline hashes preserved |

Black is not installed in the available backend/Graphify Python interpreters; formatting check is unavailable, not claimed passed. Known historical combined-process exception-class reload mismatch and Windows PDF subprocess block remain unresolved and are not relabelled passes. Older broader browser session-loss fixture failures remain outside this slice. The landing regression result is recorded in the implementation plan/audit after the final run. Initial iteration failures (ambiguous SQL join, incorrect screenshot currency/section height, stale browser fixture expectations and terminal-view test synchronization) were corrected and the affected checks rerun; no production assertion/timeout was weakened.

Screenshots of synthetic local published offers are run artifacts, not repository assets. After the native pricing browser runner completes, find monthly/yearly desktop/mobile PNGs in the run's pricing integration folder under `tmp/c113d-native-playwright/`. That ignored local directory is not included in a checkout; reproduce the run to create new artifacts. No screenshot links are published here.

## Exact isolated local reproduction

For browser commands and screenshots, use a checkout containing the dependent [catalog UI PR #59](https://github.com/Kshitij-Chandrakar/saiia_project/pull/59), which supplies `backend/tests/test_pricing_browser_native.py` and the browser fixtures. The API-only slice supports the native pricing command.

From repository root, using the already inspected retained runtime/isolated driver. These commands create only synthetic task-owned loopback clusters and clean them in finally blocks; they never consume a shared DSN or Supabase credentials. Retained runtime downloads are left untouched.

Replace `<python>` with the executable of your prepared backend environment (`python -c "import sys; print(sys.executable)"`), and `<pg-bin>` with the PostgreSQL binary directory (`pg_config --bindir`, or the directory containing `initdb`, `pg_ctl` and `psql` in your retained local runtime). The placeholders are local setup values, not shared credentials.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $env:TEMP 'c113c-db-driver'
$catalogPython = '<python>'
$catalogLauncher = Join-Path $env:TEMP 'c113c-test-launch.py'
$catalogPgBin = '<pg-bin>'
& $catalogPython $catalogLauncher backend/tests/test_pricing_native.py --pg-bin $catalogPgBin
& $catalogPython $catalogLauncher backend/tests/test_pricing_browser_native.py --pg-bin $catalogPgBin
```

The browser runner starts its own Vite on loopback 5186 and a loopback bridge to the actual API/lifespan. It creates synthetic test JWT/accounts, imports via the UI, saves incomplete drafts, reopens/edits explicit synthetic policy refs, previews/reviews/publishes, visits /#pricing, tests both toggles/tooltips at desktop/mobile, then replaces/retires and verifies SQL. Run one browser runner at a time on 5186. Browser Supabase session delivery/probe transport is a fixture; actual JWT verification and SQL permission/policy resolution are not mocked. The launcher retains the previously documented unused fitz stub solely to bypass the unrelated PDF-DLL import block; no PDF behavior is verified.

For interactive inspection, set `$env:PWDEBUG = '1'` in this temporary shell before the browser command and step through the Playwright Inspector (runner remains bounded to 240 seconds, test to 180 seconds). Do not copy tokens/policies into browser persistence or a real environment. Remove the temporary PWDEBUG variable afterward. This is an isolated inspection flow, not a persistent production login/bootstrap. Native results and screenshots are reproducible without manual database setup.

```powershell
Push-Location frontend
node --test src/auth/*.test.js src/landing/pricingMoney.test.js
npx.cmd playwright test --config playwright.catalog.config.js workspace.spec.js lifecycle.spec.js presentation.spec.js pricing.spec.js
npm.cmd run build
Pop-Location
```

## Remaining work and acceptance boundary

- Business policy: explicit tax treatment/rounding, trials/discounts if any, review/self-review validity windows, lifecycle/grace/refund/proration/subscriber migration rules remain pending. Approved prices/allocations are no longer pending; Plus 10 NEW saves and standard email supersede earlier proposals.
- Support: operational email support and the newly requested account-support AI chatbot/human escalation plus early-access release program remain unavailable/Coming soon. No full ticketing/chatbot was built.
- C12: provider selection, checkout/server mappings, verified webhooks, reconciliation, receipts/payment email remain unimplemented. Paid buttons disabled even for visible offers.
- C13: trusted cross-device signup-anchor provenance, durable reservations/settlement, Auto lease/time aggregation, resume initial/replacement/storage accounting, new-save accounting, screen action/follow-up definition and every expensive alternate route still need enforcement. This task proves representation and catalog persistence, not quota behavior.
- Deployment: review/apply migrations only with separate authorization; secure role secrets/TLS/proxy/auth ownership, approved policies/model readiness and staging acceptance before any real activation/publication. No real offers/admins or shared changes occurred.
- C11.4 website catalog/pricing has local acceptance. Customer subscription state and later Electron current-plan/Upgrade remain pending. C11.1/C11.2/C11.3 and overall C11 stay partial until actual exit criteria pass.

Next bounded slice: C13.1 usage-operation/reservation foundations using V2/V3 policy units and existing trusted actor/admission identity, with synthetic native tests and production gates closed. Do not begin it in this task.


Final broader landing regression (2026-10-23): **11 passed / 1 known unrelated failure**, `frontend/tests/e2e/landing.spec.js:239` expects the old accessible label `Intervu AI startup login`; unchanged desktop source uses `Intervucopilot startup login`. The test, startup component and Electron source hashes were preserved. This is not a pricing failure or a full-suite pass. The focused 42-test workspace/pricing suite and real native browser flow passed.


## Exact changed-file inventory for this integration

- `backend/app/commercial/boundary.py`
- `backend/app/commercial/catalog_contract.py`
- `backend/app/commercial/catalog_database.py`
- `backend/app/commercial/draft_api.py`
- `backend/app/commercial/lifecycle_api.py`
- `backend/app/commercial/public_catalog.py`
- `backend/app/commercial/publication_policy.py`
- `backend/app/commercial/review_contract.py`
- `backend/app/commercial/review_service.py`
- `backend/tests/test_catalog_v3.py`
- `backend/tests/test_pricing_browser_native.py`
- `backend/tests/test_pricing_native.py`
- `docs/C11_C13_SUBSCRIPTION_IMPLEMENTATION_PLAN.md`
- `docs/C11_SUBSCRIPTION_READINESS_AUDIT.md`
- `docs/FREE_PLAN_APPROVED_DECISIONS.md`
- `docs/PLUS_PRO_APPROVED_DECISIONS.md`
- `frontend/src/auth/CatalogDraftFields.jsx`
- `frontend/src/auth/CatalogLifecycle.jsx`
- `frontend/src/auth/CatalogPolicyFields.jsx`
- `frontend/src/auth/CatalogPolicyPreview.jsx`
- `frontend/src/auth/SubscriptionAdmin.jsx`
- `frontend/src/auth/approvedPlusTerms.json`
- `frontend/src/auth/approvedProTerms.json`
- `frontend/src/auth/catalogApi.js`
- `frontend/src/auth/catalogDraft.js`
- `frontend/src/auth/catalogLifecycle.js`
- `frontend/src/auth/catalogRegistryV3.json`
- `frontend/src/auth/catalogV2.js`
- `frontend/src/auth/catalogV2.test.js`
- `frontend/src/landing/CatalogPricing.jsx`
- `frontend/src/landing/catalog-pricing.css`
- `frontend/src/landing/pricingMoney.js`
- `frontend/src/landing/pricingMoney.test.js`
- `frontend/tests/catalog/presentation.spec.js`
- `frontend/tests/catalog/pricing.integration.spec.js`
- `frontend/tests/catalog/pricing.spec.js`
- `supabase/migrations/20261023140000_catalog_v3_terms.sql`
- `supabase/migrations/20261023150000_catalog_policy_public_read.sql`
- `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`
- `SAIIA_PRODUCTION_PHASES_TRACKER.md`
- `backend/app/config.py`
- `backend/app/main.py`
- `frontend/src/landing/LandingPage.jsx`
