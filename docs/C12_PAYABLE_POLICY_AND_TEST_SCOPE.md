# C12 payable policy decision and bounded test-mode scope

Secure setup follow-up: [hidden local input, webhook-only HTTPS gateway and one consolidated execution scope](C12_SECURE_TEST_SETUP.md). Preparation is complete; external execution remains unapproved. The proposed scope covers one session-generated trycloudflare.com hostname recorded before registration; acceptance by Razorpay is not assumed.

25 October 2026. **Prepared for review; not authorization to execute.** No provider API calls, webhook registration, tunnel creation, remote migrations, deployment or live payment is authorized or performed by this document. Razorpay documentation was read, not its authenticated payment API. Refunds, coupons/discount application and paid-plan upgrade/proration charges remain unavailable.

Local implementation evidence updated 26 October 2026: changes and verification (owner-held private record `C12_GST_IMPLEMENTATION_EVIDENCE.md`; excluded from this checkout).

## Approved current GST-added policy (25 October 2026)

The user approved base prices plus **18% GST**. This supersedes the earlier unapproved inclusive-total proposal; that proposal is historical only and was never activated. Base catalog amounts remain unchanged. The payable calculation is separately versioned as `billing.inr.gst18.v1`.

| Plan / interval | Base | GST | Final recurring charge | Total paise |
|---|---:|---:|---:|---:|
| Plus monthly | INR 399.00 | INR 71.82 | INR 470.82 | 47082 |
| Plus yearly | INR 2,999.00 | INR 539.82 | INR 3,538.82 | 353882 |
| Pro monthly | INR 899.00 | INR 161.82 | INR 1,060.82 | 106082 |
| Pro yearly | INR 6,499.00 | INR 1,169.82 | INR 7,668.82 | 766882 |

Website paid cards show the prominent base price, then `per month + 18% GST` (or `per year + 18% GST`), then `Total: <final amount>`. They show no separate GST amount, included-tax breakdown, coupon, crossed-out price or savings badge. Free shows INR 0 without GST wording. Checkout review and internal invoice preparation retain base, rate, tax and total.

The backend computes integer paise using `base * 1800 / 10000`, requiring an exact result. These four calculations are exact. No general fractional-paise rounding rule was previously approved: future inexact prices fail closed until that separate policy is decided. No floats, FX or extra rounding affect these totals.

Public catalog prices include backend-generated payable projections. New checkouts persist an immutable payable document binding currency, base, rate, GST, total, offer ID/version/fingerprint and price ID. A quote ID also binds the operation, provider plan and cycle count. Consent must submit that exact quote ID. Old financial snapshots/consent are not backfilled or repriced. An unconsented legacy review must be replaced and reviewed afresh; a dispatched/uncertain historical mandate is reconciled at its original amount.

Provider configuration uses **the computed final total as `plan.item.amount`**, with no additional provider tax ID/rate/group or subscription add-on. This charges GST once. Plan, invoice and captured-payment totals must equal the accepted total; extra provider-side tax is rejected. The provider invoice is payment evidence, not a claim that a custom legally compliant tax invoice has been implemented. Internal GST components remain available for invoice preparation. Current official references: [plan fields](https://razorpay.com/docs/api/payments/subscriptions/create-plan), [invoice fields](https://razorpay.com/docs/api/payments/subscriptions/fetch-invoices/).

### Remaining live-billing inputs

Seller identity, registration status/identifiers, customer-location applicability, and required tax-invoice issuer/numbering/fields/delivery remain separate live readiness inputs. No GSTIN, CGST/SGST/IGST split, tax registration or compliance conclusion is invented. The approved 18% calculation is fully exercised with synthetic local fixtures without resolving or assuming these facts. Refunds, discounts/coupons and upgrade/proration charges remain unavailable.

## Where the renewal maximum approval is recorded

These values are **approved**, not proposed: the user explicitly approved them in this conversation, subject to Razorpay validation. The approval is already recorded in:

- [Canonical policy: C12 recurring billing decision, 25 October 2026](SUBSCRIPTION_APPROVED_POLICIES.md#c12-recurring-billing-decision-25-october-2026).
- C12 acceptance: Approved product choice (owner-held private record `C12_RAZORPAY_LOCAL_ACCEPTANCE.md`; excluded from this checkout).
- The C12 paragraphs of `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md` and `SAIIA_PRODUCTION_PHASES_TRACKER.md`.

The user's instruction was: “Approve configurable maximums of 12 billing cycles for monthly plans and 5 billing cycles for yearly plans, subject to Razorpay validation.” It also required disclosure, fresh consent after the final period, no replacement mandate without consent and paid-period-end preservation. Actual provider validation has not occurred. The monthly/yearly values cap configurable counts; they do not authorize live payments, provider API calls or remote changes.

## Exact ESLint comparison and fix

Baseline: `docs/C13_2_LINT_ATTRIBUTION.json`, 60 errors / 29 warnings. Compared current results as a **multiset of file + rule + message**, ignoring shifted line numbers.

| Measurement | Errors | Warnings | New error instances versus recorded baseline |
|---|---:|---:|---:|
| Before this fix | 61 | 29 | 1 |
| After this fix | 60 | 29 | 0 |

The sole added diagnostic was `no-unused-vars` at `frontend/tests/catalog/fixtures/physical-auto.js:4`: `'synthetic' is assigned a value but never used.` Removed only that unused destructured binding. The Electron acceptance caller's extra option remains harmless; the hosted synthetic stream is supplied by its existing `getUserMedia` substitute, not this unused binding. No capture controls or simulated/physical behavior changed. No ESLint rules or ignores changed.

Validation: targeted ESLint and `node --check` passed. Full ESLint still exits 1 for exactly the 60 recorded baseline errors, with no baseline errors removed or replaced. Attribution: C12_ESLINT_BASELINE_COMPARISON.json (owner-held private record `C12_ESLINT_BASELINE_COMPARISON.json`; excluded from this checkout); raw reports: `tmp/c12-policy-eslint-before.json` and `tmp/c12-policy-eslint-after.json`. The previous C12 description treating all 61 errors as baseline was insufficiently attributed and is corrected by this comparison.

Graphify was queried before the change; the post-change scoped graph and query include this fixture. Graph edges remain navigation aids; the diagnostic comparison and syntax/lint runs are the evidence for the fix. This unused-parameter fix does not require repeating microphone/device acceptance and does not claim it passed.

Post-change graph: `graphify-out/c12-policy-check/graph.json`, 329 nodes / 747 edges, structural extraction with zero model tokens. Diagnostics retain 90 dangling external endpoints and 15 collapsed directed edge pairs; the fixture is represented only by a file node, so the graph is incomplete. Query: `tmp/c12-policy-graph-after-query.txt`; full report: `graphify-out/c12-policy-check/GRAPH_REPORT.md`.

## One concrete acceptance scope: C12-RZP-TEST-01

**Status: prepared, not executed.** One owner-operated session, at most 60 minutes. Use one dedicated Razorpay **test-mode** merchant account and a new disposable **local** PostgreSQL 17 cluster. Do not use the `cfmvqbjmnwklxqlpelxe` staging database, accounts, storage or credentials. The currently open C11/C13 SQL files and previous staging authorization are outside this scope.

### Execution inputs that must be supplied first

1. Pin the approved GST-added payable version and existing immutable synthetic offer/price IDs with unchanged base prices; prepare provider plans at the final totals above. Seller/invoice readiness remains separate from this controlled synthetic acceptance.
2. Dedicated test API pair: `RAZORPAY_TEST_KEY_ID=rzp_test_...` and `RAZORPAY_TEST_KEY_SECRET`; exact `RAZORPAY_TEST_ACCOUNT_ID`; a new `RAZORPAY_TEST_WEBHOOK_SECRET`. Optional previous secret only if an actual test-secret rotation is being tested. Supply through backend secret configuration, never chat, source, renderer variables, screenshots or command history.
3. Owner-approved HTTPS public webhook hostname forwarding **only** `/api/billing/webhook` to the loopback backend on port 8000. The concrete hostname/tunnel owner must be named in the final authorization; it is not available from repository context. Website stays on loopback port 5173. No public admin, account, database or storage endpoint is exposed.
4. Eight disposable, verified synthetic account identities in the isolated local auth/data setup, with owner-controlled test inbox/contact data only. No customer account or real account plan changes. A local server runtime supporting the real adapter must be prepared separately from the offline substitute runner; putting keys into the mock runner does not turn it into provider acceptance.

### Provider and local mutation budget

- Create at most **4 test provider plans**, one per reviewed immutable price: Plus monthly/yearly, Pro monthly/yearly. Verify exact final INR plan amounts 47082 / 353882 / 106082 / 766882 paise, interval 1 and quantity 1; actual `total_count` 12 monthly / 5 yearly. Set no additional provider tax IDs/rates/groups; reject added GST or add-ons. No add-ons, offers, coupons, trial or upfront commercial charges.
- Create at most **8 test subscriptions**: one success and one unsuccessful/dismissed checkout per price, each on its own synthetic account. Duplicate clicks/tabs/retries must reuse the same operation; they do not increase the budget. No create retry after uncertain dispatch.
- At most **8 period-end subscription cancellation mutation attempts**, including cleanup. A timeout is reconciled by reads; no blind resend. Count a cancellation already requested by the app toward that limit. An unconfirmed cancellation prevents closing the packet as cleaned up.
- Register **one test webhook endpoint**, enable it only for the session, then disable/remove its registration during cleanup. No live Dashboard changes. Provider-hosted Checkout traffic is test mode only; never use a real card or real debit/mandate instrument.
- Bound backend reconciliation/provider reads to **500 GET requests** during the session; stop new work at that limit or the 60-minute deadline and perform the documented cleanup/reconciliation. The operator must collect redacted counts; this is an acceptance stop budget, not a claim of a new global rate limiter in the runtime.
- No refunds, capture mutation, subscription modification/upgrade, paid assignment shortcut, deployment, remote SQL or staging batch execution. Abort and report any provider setup that requires an additional commercial choice or an unlisted action.

### Local migration and configuration

Build the new cluster from the existing local native fixture prerequisites. Apply **once, locally only**:

`supabase/migrations/20261025020000_razorpay_checkout.sql`

The current `20261025020000_razorpay_checkout.sql` has canonical-LF SHA-256 `d53c967f0353177105339ddbc06f54f84f53cb39c972800ab91a33425a7a49c1`. This identifies the current file, not an earlier pre-edit revision. Then apply the additive `20261025030000_billing_gst_payable.sql` locally, once. It adds immutable payable storage and wraps the existing lifecycle RPC; it does not rewrite historical financial rows.

Prepare its own local application record and postflight evidence, including RLS/table denial and exact function grants. Do not edit or rerun the already-applied 50-file staging batch or change its manifest. A future remote migration requires a different scope, target and approval.

Use local restricted pools: existing `usage_executor` for account/usage and `usage_binding_executor` for billing; no privileged owner DSN in the app, no inherited memberships or direct table DML. Synthetic policy imports, Free bootstrap and account configuration belong only to this cluster. `BILLING_ENABLED` remains false until the named session starts. Pin `BILLING_RENEWAL=automatic`, `BILLING_TOTAL_POLICY_REF=billing.inr.gst18.v1` and server-only `RAZORPAY_TEST_PLAN_MAPPINGS` for those exact immutable price IDs. Do not publish/mutate real offers to make the test work.

### Webhook setup

Proposed URL: `https://<owner-approved-test-host>/api/billing/webhook` (replace with the exact approved host before execution).

Enable only these implemented test-mode subscription events: `subscription.authenticated`, `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`, `subscription.updated`.

Configure the dedicated test secret. Verify raw-byte HMAC before parsing, merchant binding, durable receipt/event recording, duplicate/out-of-order handling and backend invoice/payment reads. Localhost cannot directly receive provider webhook delivery; several tunnel domains are blocked in the [current Razorpay webhook documentation](https://razorpay.com/docs/webhooks/validate-test/). Approval must identify a usable public host rather than assume a tunnel works.

### Numbered session walkthrough and pass criteria

1. Verify test merchant/key provenance, local-only database/identity configuration, migration hash/postflight, no live keys, and default-off behavior. Record exact four immutable offer/price/provider-plan mappings and redacted resource IDs.
2. Start the scoped backend/public webhook session. Complete website pricing → review for all four intervals/prices. Verify the final payable amount and explicit recurring consent, maximum 12/5 cycles, and fresh-consent statement before any subscription creation.
3. Use only official test instruments. Require actual captured payment + paid subscription invoice with exact amount/currency/relationships and provider billing end. Record initial authentication/authorization transactions separately; do not invent an authorization fee or grant access from it. Browser-first and webhook-first processing must converge.
4. For the other four accounts, dismiss/fail checkout and confirm no paid access. Double-click/reload/two-tab recovery must keep one operation/provider object. Mutated price/account/signature/raw-body inputs must be rejected. Recovery after browser closure must use the accepted server operation.
5. Exercise duplicate/delayed webhook delivery and a missed-event reconciliation; simulate local network interruption/crash around durable evidence/application while keeping provider mutations within budget. Confirm website account projection and the existing Electron main-process account refresh update from the trusted API. Signed/installed physical Electron remains a separately identified acceptance gate.
6. Request cancellation at paid-period end; verify that paid access is not shortened. Check actual provider renewal/completion behavior **only if the provider offers a documented way to exercise the same configured plans within this session**. Do not change production-like intervals, forge a live-provider invoice, wait five years or claim completion from fixtures. Renewal failure/expiry/max-term behavior continues to have deterministic fixture evidence; any unexercised actual-provider lifecycle case remains explicitly pending.
7. Export redacted results: resource IDs, expected/actual amounts, invoice/period/state bindings, duplicate/recovery counts and failures. No keys, tokens, customer payloads or card details. Record separately: deterministic checks, actual provider test-mode checks, and untested/live readiness.
8. Perform cleanup below and return billing to off. C12 is not marked complete merely because the first test charge passed.

### Cleanup and closure

1. Stop new checkout creation. Reconcile uncertain test objects by stored operation notes/IDs; do not create replacements. Request period-end cancellation for every created test subscription within the existing mutation budget. Verify cancellation/scheduled cancellation by provider reads/Dashboard; preserve paid test periods and evidence. Do not issue refunds or immediate-cancel mutations to simplify cleanup.
2. Disable/remove the test webhook registration and close the public tunnel. Record any resource that cannot be cancelled/disabled; outstanding resources are an open cleanup gate. Provider invoices and plans may be retained as test records; do not invent a deletion API. Leave no active untracked test mandate.
3. Set `BILLING_ENABLED=false`, stop local workers, remove session-specific process credentials and revoke/rotate temporary test credentials as supported by the owner-controlled Dashboard. Do not touch live credentials or reuse webhook secrets across modes.
4. Retain only the redacted acceptance evidence. Once all provider resource IDs/cancellation outcomes and uncertainty evidence are captured, stop and remove **only the newly created disposable local cluster**, using its resolved task-owned path. Remove the eight local synthetic identities with that cluster; no remote account deletion or purge.
5. Record exact pass/fail/pending cases and cleanup verification. No staging or live readiness is inferred. Any additional provider call, remote migration or deployment outside this named scope requires a separately prepared authorization.

Next action: review the bounded GST-total test-mode packet and supply its remaining execution inputs. The scope remains unexecuted until its concrete credentials/host/local targets and external actions are authorized together.
