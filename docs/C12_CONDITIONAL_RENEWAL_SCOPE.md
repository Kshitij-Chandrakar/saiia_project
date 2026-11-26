# Conditional Razorpay renewal acceptance - prepared, NOT authorized or executed

27 October 2026. Local requirement coverage is indexed in `C12_ACCEPTANCE_CHECKLIST.md`. This proposal covers only actual subsequent-charge interoperability; it does not repeat the four passed initial-payment tests. No provider request, new plan/subscription, charge or support message was made to prepare it.

## Mandatory preconditions - stop if any is absent

1. Owner reviews the six-object support packet and obtains ID-bound evidence resolving whether the selected existing Plus-monthly subscription **`sub_SYNTHETIC_ONLY`** is scheduled for cancellation and whether a test charge is safe. Do not charge an unresolved or scheduled-to-cancel mandate merely because it still says Active.
2. Retained card token remains eligible for the documented Test Mode subsequent debit, and the Dashboard offers **Charge this now**. Razorpay documents a three-day card-token limit. Initial-payment time is not itself proof of token creation time or eligibility. If the facility is unavailable/expired, mark this scope blocked; do not create a replacement subscription, update the mandate or change intervals.
3. A local restoration fixture must establish the existing operation's merchant, immutable offer/payable snapshot, account association and provider subscription ID from saved evidence with recorded hashes. The old disposable database is gone. Saved four-price results contain operation/provider/payable/account summaries, not a complete database backup. Do not invent missing columns, histories, signed events or import a ready operation by trusting client input. If the recorded snapshots cannot support a faithful test-only restore through existing validation, stop preparation with that exact missing evidence; no provider window begins.
4. All local duplicate/recovery invariants and installer tests are evaluated independently; pending support does not block those local tasks. Fresh owner approval is required for the exact external execution below. Previous clocks/counters remain closed.

## Proposed single external window

- **15 minutes**, with a new exclusively created journal and start/deadline recorded before external activity; no retries, counter reset or deadline extension.
- Existing Plus-monthly ID above, final recurring total **INR 470.82**, existing approved plan/count unchanged. **Zero new plans, subscriptions or customers.**
- **One manual Test Mode Charge this now action**, success path only, after all preconditions. This can create one provider renewal payment/invoice as a consequence; record returned IDs. No simulated failure/retry/halt/max-term exhaustion, mutation replay, refund, cancel or mandate update.
- **At most 20 Razorpay GET attempts total**, reserved durably before dispatch, including authentication/merchant/subscription/plan/invoice/payment checks and reconciliation; redirects off, bounded timeouts, no automatic retry. Stop if the existing adapter's required reads cannot fit the remaining budget.
- **One temporary Test Mode webhook**, limited to implemented subscription events needed for the selected existing object; **one callback-only HTTPS tunnel** to an isolated loopback gateway. At most **12 forwarded callback requests**, including provider retries. No public website/admin/database exposure.
- Masked process-only test API key ID/secret, expected merchant account ID and dedicated webhook signing secret; no frontend keys, dotenv changes or secret values in evidence.
- Fresh disposable native PostgreSQL, restricted billing executor, synthetic restored local account, existing validation/application services. No shared database or remote migration.
- Application email dispatch disabled; a renewal outbox event may be inspected but not sent. Razorpay may emit its own configured customer notification for the test charge; disclose this in the final execution approval rather than promising control over provider notices.

## Exact acceptance sequence

1. Reserve bounded reads to verify authentication, merchant and selected object's state/plan, eligibility and original immutable mapping. Stop on mismatch, cancellation uncertainty or missing restore evidence.
2. Record the existing application receipt/outbox baseline. Create the one temporary webhook/tunnel and verify the exact-route boundary without provider mutations.
3. Owner triggers the one documented subsequent charge. Do not repeat after timeout or unclear result.
4. Use existing read-only reconciliation to establish the new captured payment/invoice and paid-period end. If demonstrating missed delivery, hold application projection in the acceptance-only harness after durable signed ingress; do not acknowledge and discard an event. Reconcile first, then release the retained callback for normal processing. No production recovery bypass or fabricated provider event is permitted.
5. Verify one additional payment receipt and one additional paid-period application, one renewal business-notification identity, unchanged signup-based allowance boundaries and no email dispatch. A later duplicate callback/reconciliation must not extend access twice.
6. Permission-controlled admin reconciliation is explicitly included: step 4 must be initiated through one existing target/revision-bound admin review and confirmation, then executed once by its worker. It targets only the restored operation for the named subscription. Record actor, action, target, confirmation revision, queued outcome and worker outcome; verify actual receipt/period evidence independently of the command status. No commercial override or second admin execution.

## Cleanup, stop conditions and evidence

Stop new testing on uncertainty, missing precondition, deadline or budget. Do not cancel these resources as cleanup: all six historical cancellation outcomes require support resolution and separate mutation authorization. The selected object remains a retained Test Mode object; disclose its updated paid count/period if a renewal occurred.

Disable and verify the temporary Razorpay webhook before tunnel closure; record whether this is owner-confirmed or machine-observed. Export only redacted identities, HTTP results, signed-event verification facts, immutable snapshot hashes, receipt/outbox/application counts and local audit outcomes. Clear process credentials, stop owned services and remove only the new disposable cluster; preserve all prior execution evidence.

No live mode, real application emails, support submission, new subscriptions, remote migration, asset/DNS/Auth changes, production activation, deployment, commits or pushes. This scope is intentionally **conditional and currently blocked by the support/eligibility/restoration prerequisites**, not a permission to execute.

Official facilities checked 27 October 2026: [Test subscriptions and subsequent charges](https://razorpay.com/docs/payments/subscriptions/test/); [cycle-end cancellation parameter and error semantics](https://razorpay.com/docs/api/payments/subscriptions/cancel-subscription/). Neither documentation nor deterministic tests resolve the six historical provider outcomes.


## Final preparation correction ? 27 October 2026

**Execution remains blocked.** Support must establish safe reuse for the selected ID; current ID-bound Dashboard/token eligibility must be verified in the later approved window before charging. Faithful local restoration remains unproven: saved summaries are not a complete database backup. The restoration validator and acceptance-only callback gate must be prepared and verified locally before requesting an external start. No credentials, migrations, provider calls or tests were run in this document review.

### One charge, two distinct observations

- **Renewal authority/recovery:** baseline the existing applied payment identity, paid-period end, account revision and signup-based allowance window/usage. Disable background sweep, status polling and other provider readers. Receive and verify signed callbacks into durable local ingress but withhold all application billing-handler dispatch. One admin review/confirm queues the only reconciliation job. The real adapter must discover a **distinct captured payment and paid invoice**, matching subscription, immutable INR 47082 snapshot, order and invoice linkage. Verify a valid new provider billing period extending the prior verified paid end, exactly one additional receipt and exactly one renewal outbox identity. If an accelerated charge does not establish an extending period, record that gap and stop; do not manufacture dates or charge again. Account stays Plus; allowance boundaries follow signup policy and usage is not reset merely by payment. Compare before/after entitlement, usage and window values.
- **Webhook processing after recovery:** only after recovery evidence is committed, release one retained relevant signed charged callback through the normal application handler. Its reconciliation must find the same invoice/payment, leaving receipt count, paid end and renewal identity unchanged. Other forwarded callbacks remain durably held until their processing can be completed within the budget; no automatic handler/sweep execution is allowed. Acknowledgment is allowed only after durable retention. Export held events and their processing state at stop; never describe pending events as processed.
- This establishes actual reconciliation-first renewal and actual duplicate-safe webhook handling for **the same charge**. It does **not** establish webhook-first renewal or a genuinely lost provider delivery; the webhook was deliberately withheld locally. Prior actual initial-payment webhook acceptance remains passed. A separate webhook-first renewal would require another charge and is excluded; no scope expansion is proposed here.

### Read accounting and feasibility

The current service reads subscription, validates plan, lists invoices (bounded pagination), then fetches each paid invoice's payment. With one invoice page and exactly two paid invoices, each full reconciliation costs **five GET attempts**. Source: `backend/app/commercial/billing_service.py::_reconcile`, `_validate_subscription`, `_validate_plan`; `backend/app/commercial/razorpay.py::invoices`. An old payment is retrieved again by the existing validator; do not count only the new payment.

Reserve the unchanged **20 total GET-attempt** ceiling as follows:

| Purpose | Maximum allocation |
| --- | --- |
| Authentication/merchant and selected subscription/plan preflight (including any baseline reads) | 4 |
| One admin worker renewal reconciliation, before webhook application | 5 |
| One released webhook's normal reconciliation after recovery | 5 |
| Contingency for extra required pages/payments or further held callback processing, not retries | 6 |

No provider reads occur for the local admin review/confirmation itself. Gateway counters count every forwarded request (maximum 12), separately from adapter GET reservations. The 12 callback limit does **not** authorize 12 full reconciliations: that could exceed 20 GETs. Reserve each actual GET durably before dispatch in every code path, redirects and automatic retries off. The local harness must gate callbacks/worker jobs and verify a full planned reconciliation fits remaining reads before starting it. If preflight needs more than four reads, paid invoices/pages exceed assumptions, independent merchant authentication cannot be established, callbacks cannot be safely retained, or all required processing/cleanup cannot fit 15 minutes, stop before charging and revise the concrete allocation for review **without increasing any cap**. Six contingency reads are not permission to retry an uncertain operation.

**Scope conclusion:** one 15-minute session, one existing Plus-monthly ID `sub_SYNTHETIC_ONLY`, one test renewal charge, 20 GET attempts, one temporary webhook/callback-only tunnel and 12 forwards can cover reconciliation-first authority plus subsequent webhook dedupe under the stated assumptions. Admin execution is included, not optional. No second charge, new plan/subscription, cancellation mutation, application email, automatic retry or retry after uncertain sending/charging is included. If webhook-first renewal is additionally required, that is a separate scope change before execution. No such execution is authorized by this preparation.
