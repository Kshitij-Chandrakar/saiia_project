# C12 authoritative acceptance checklist

Current as of 27 October 2026. **C12 remains open.** This is the current requirement/evidence index; earlier execution records remain historical evidence, not current status summaries. No old journal, counter or accepted external test is reset or recreated.

## Interpretation and approved sources

- **R**: roadmap C12.1/C12.2/C12.3, C12 tests and six exit criteria in `SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md`. Its "Possible routes" and recommended structures are not additional approved release gates.
- **P**: `SUBSCRIPTION_APPROVED_POLICIES.md`: automatic renewal, explicit consent, 12 monthly / 5 yearly maxima, verified-period access preservation and fresh consent after completion; approved GST-added calculations.
- **T**: `C12_PAYABLE_POLICY_AND_TEST_SCOPE.md`, especially actual-provider scope steps 5-6. Actual future lifecycle cases are conditional on documented test facilities; fixtures must not be relabelled actual observations.
- **L**: `C12_RAZORPAY_LOCAL_ACCEPTANCE.md`, `C12_GST_IMPLEMENTATION_EVIDENCE.md` and their retained native/Node/browser results.
- **S03**: `C12_RZP_TEST_03_EXECUTION.md`; **READ**: `C12_RZP_READ_01_RESULTS.md`; **SUPPORT**: `C12_RAZORPAY_CANCELLATION_SUPPORT_DRAFT.md`.
- **MAIL**: `C12_BILLING_EMAIL_ADMIN_LOCAL_ACCEPTANCE.md`, `C12_EMAIL_ADMIN_01_EXECUTION.md`, `C12_EMAIL_REDESIGN_01_EXECUTION.md`, `C12_RESEND_CALLBACK_01_EXECUTION.md`.

**Passed** means the cited approved criterion has sufficient evidence, which may be deterministic. **Local-only** means implementation/substitutes are verified but an explicitly identified actual integration is not. **Blocked** identifies an external finding/input. **Untested** claims no acceptance. **Explicitly deferred** requires an existing approval/boundary. Evidence type is always recorded independently of status. Actual-provider execution is not required merely because it is imaginable.

## C12 functional requirements

| ID / requirement and source | Implementation and exact retained evidence | Status / evidence type | Remaining action / dependency / ownership |
| --- | --- | --- | --- |
| C12-01 payment creates/updates subscription (R) | Existing billing service/C13 paid receipt; S03 four initial captured Plus/Pro monthly/yearly flows | **Passed**, actual Razorpay Test Mode plus local SQL | Preserve; do not repeat initial payments; C12 |
| C12-02 approved amount/currency/interval, maximum count and explicit immutable consent (P,R) | Versioned payable quotes, mappings and consent; L 35 focused native cases; S03 totals INR 470.82/3,538.82/1,060.82/7,668.82 | **Passed**, deterministic + actual initial amounts | No repricing or new commercial behavior; C12 |
| C12-03 authenticated ownership and idempotent creation/two tabs (R) | `test_two_tabs_and_concurrent_dispatch`, forged-input/cross-account tests and L recorded results | **Passed**, deterministic JWT/API/native PostgreSQL | No additional provider two-tab gate is invented; C12 |
| C12-04 signed, merchant-bound authoritative webhook; no redirect-only grant (R) | S03 actual signed events; native signature/merchant/authorized-only callback tests | **Passed**, actual + deterministic | Preserve exact authority boundary; C12 |
| C12-05 duplicate/out-of-order events are safe (R) | `test_checkout_verified_entitlement_and_duplicate_webhook`, `test_renewal_out_of_order_and_cancel_retains_paid_access`; L results | **Passed**, deterministic; S03 concurrent reconciliation supplements it | No external replay required solely to duplicate proven local ordering; C12 |
| C12-06 missed/delayed webhook reconciliation (R,T) | Existing recovery/sweep and authorization-only server recovery; new `test_missed_renewal_reconciliation_and_duplicate_delivery_share_one_email` discovers renewal without webhook, then races webhook/reconcile/sweep | **Passed**, deterministic native; new focused test 1 passed | Actual missed-event renewal path remains separately named below, not relabelled; C12 |
| C12-07 uncertain create outcome never redispatches (R) | `test_create_uncertainty_never_redispatches` covers before/after create ambiguity; L accepted suite | **Passed**, deterministic | Deliberately creating provider uncertainty is not a new release requirement; C12 |
| C12-08 crash after verified payment before entitlement apply (R) | `test_concurrent_verify_webhook_recovery_and_crash`, `test_recorded_payment_crash_recovers_one_outbox`; retained native evidence | **Passed**, deterministic native | No actual provider crash repetition needed for this criterion; C12 |
| C12-09 renewal extends once and emits one business email identity (R,P) | Existing renewal/ordering and distinct-email tests; new missed-renewal/concurrent test asserts two distinct payment receipts, one renewal source and no resend on worker repetition | **Passed**, deterministic native | Actual Razorpay subsequent-charge interoperability is local-only, separately scoped below; C12 |
| C12-10 approved expiry returns Free without deleting retained data (P,R) | Native verified-payment/bootstrap/expiry, maximum-term completion, over-cap data retention and access-end notification cases; L/C13 evidence | **Passed**, deterministic native | Do not wait a real month/year; production clock/integration evidence belongs to separately specified rollout; C12/C13 |
| C12-11 cancellation preserves verified paid access (P,R) | Native renewal/cancel test and pending-cancel email test; S03 product retained paid access after requests | **Passed**, deterministic preservation; actual request/access observation | This does not confirm provider cancellation; separate blocked row below; C12 |
| C12-12 fresh consent after 12/5 maximum, no automatic replacement (P) | `test_explicit_recurring_consent_and_mandate_limit`, `test_yearly_five_cycles_and_fresh_consent_after_completion`; L native results | **Passed**, deterministic | Actual terminal mandate event not observed; supplemental provider coverage remains untested, no multi-year wait/new gate; C12 |
| C12-13 paid periods do not reset signup-based usage (P) | Existing C13 allowance/usage/recovery suite (207 accepted regressions), immutable paid-period projection | **Passed**, deterministic; C13 staging retained | Do not repeat C13 staging; C13 dependency |
| C12-14 failed/dismissed checkout stays Free; pending states honest (R) | S03 unsuccessful checkout records; React/native checkout cases | **Passed**, actual Test Mode + deterministic UI | Preserve; C12 |
| C12-15 authoritative website/account refresh (R) | S03 paid refresh and local React/main-process manager results | **Passed**, actual backend/account observation + deterministic shared Electron code | Installed product integration is separate below; C12/C13 |
| C12-16 initial and renewal receipts through C10 durable lifecycle (R) | MAIL original two synthetic billing-transition emails, provider acceptance, delivered screenshots and Gmail confirmations | **Passed**, actual email transport; billing fixtures synthetic | Not actual Razorpay renewal evidence; C12.2/C10 |
| C12-17 ambiguous cancellation never sends confirmation; access-end follows authority (P,R) | Native pending cancellation/no-confirmation, verified terminal state and authoritative expiry notification tests | **Passed**, deterministic | Real cancellation notification cannot be exercised while all six provider outcomes remain unresolved; no resend; C12.2 |
| C12-18 recipient identity, exact money, escaping, business dedupe, bounded retries/unknown (R) | Existing template/provider/native tests; MAIL verified-account recipient policy and durable outbox/retry/crash records | **Passed**, deterministic; actual sends use same dispatcher | Preserve templates, retries, recipients and identities; C12.2 |
| C12-19 signed Resend tracking, stored correlation and replay dedupe (approved callback scope) | `C12_RESEND_CALLBACK_01_EXECUTION.md`: one send, three HTTP-200 forwards, two stored events, one manual delivered replay; billing.read/denial/audit | **Passed**, actual signed callbacks/native persistence | Mail-server delivery is distinct from inbox placement; provider disable is owner-confirmed; C12.2 |
| C12-20 redesigned presentation and versioned artwork (approved redesign scope) | MAIL three verified published assets; two redesigned emails owner-confirmed in Gmail, no CTA | **Passed**, machine asset verification + owner receipt/rendering | Prior redesign dashboard Delivered status is unverified and not a duplicate acceptance gate; Outlook/dark mode not invented as requirements; C12.2 |
| C12-21 explicit billing permissions, target/state confirmation and durable audit (R scoped C12.3) | MAIL native admin matrix + browser fixture; actual email acceptance's local admin checks and callback read/denial | **Passed**, deterministic/local admin integration | No generic C15.5 console or commercial overrides; C12.3 |
| C12-22 eligible retry and queued reconciliation use existing services (approved admin scope) | Native eligible retry, exhausted/unknown refusal, stale/tampered/replayed confirmation and worker audit tests | **Passed**, deterministic service integration | Queued is not successful provider execution. Actual admin-triggered Razorpay renewal reconciliation remains untested, not silently passed; C12.3 |
| C12-23 backend-only keys/default-off/live-key rejection (R) | Native default-off/restricted pool/live-prefix tests; redacted journals; package scan below | **Passed**, deterministic + execution hygiene | No keys in renderer/installer; C12/C16 boundary |
| C12-24 billing states visible; no unsupported paid overrides (R) | Checkout/account/admin UI records + pending/unknown cancellation wording; refund/discount/upgrade actions unavailable | **Passed**, supported approved scope | Invoice history/issuance is not implemented; see separate boundary below |

## Cancellation and provider cleanup - not a local implementation failure by inference

| Requirement/source | Current evidence | Status | Exact next dependency |
| --- | --- | --- | --- |
| Paid cancellation scheduled/effective date for four S03 subscriptions (P,T) | S03 saved HTTP outcomes; READ six actual GETs; four Active, no positive schedule evidence | **Blocked**, actual outcome unknown | ID-bound Dashboard audit or Razorpay Support findings; no repeat GET/cancellation authorized |
| Close two unauthorised Created subscriptions (T) | Prior cycle-end requests 400/BAD_REQUEST_ERROR; READ still Created, `expire_by:null` | **Blocked**, rejected requests; terminal cleanup unknown | Support-approved closure method and separate authorization before mutations |
| Temporary test infrastructure cleanup (T,MAIL) | Retained execution cleanup checks; callback 01 owner-confirmed webhook Disabled before machine-verified teardown | **Passed**, mixed owner confirmation and local machine checks | Preserve distinction; prior stopped preparation directory exception remains historical |

All six IDs and exact request times remain in SUPPORT. No support response has been supplied in repository evidence; the owner reports the ticket submitted; findings are pending. Current official cancellation documentation declares a boolean parameter but explicitly also accepts `1`/`0`; the saved integer is **not an established defect**. Current docs describe rejecting cycle-end cancellation without an active cycle, but missing original response bodies prevent assigning that explanation to these two historical errors. No cancellation response or request ID is reconstructed.

## Installed Electron and cross-phase boundaries

| Requirement | Evidence / status | Ownership and next action |
| --- | --- | --- |
| Separate unsigned installer, identity/profile/install path and no protocol takeover | Built `0.0.0-c12.1`, app ID `in.intervucopilot.c12acceptance`; installer signature NotSigned; explicit file allowlist; 3,133 text files credential-scanned | Current local acceptance artifact; no production signing claim |
| Free display/backend enforcement; Upgrade; trusted plan/allowance refresh; restart; logout/account switch; expiry; unavailable state | **Passed**, installed executable: one Playwright test / nine observed checks; synthetic auth and native disposable PostgreSQL; `C12_INSTALLED_ACCEPTANCE.md` | C12/C13 installed integration; record observed results separately from unpacked build |
| Production code signing, updater publication, production auth/deployment | **Untested / outside this local scope** | C16/C16.1; must not be newly attributed to C12 payment logic |
| Normal application/profile/protocol preservation | Protocol/auth snapshot unchanged after installation, runtime and uninstall attempt | **Passed**, owner removal followed by read-only verification: both acceptance directories absent, no owned process/listeners/database; normal protocol/auth snapshot unchanged. See installed report |

## Named remaining actual-provider coverage

These are observations still missing, not a mandate to recreate deterministic coverage:

1. **Actual subsequent Razorpay Test Mode charge** correlated to the existing mandate and one additional verified paid period. No such charge was recorded in S03; original synthetic renewal emails do not establish it.
2. **Actual renewal discovered by reconciliation without relying on delivery**; application recovery is deterministic-tested, provider subsequent-invoice interoperability is unobserved. A future single renewal scope can cover both, including one supported admin reconciliation command if prepared/authorized.
3. **Actual cycle-end cancellation schedule/effective cancellation** for four paid subscriptions, plus safe closure of two Created records: blocked by missing ID-bound provider findings.
4. **Actual provider terminal completion/failed renewal/halted lifecycle**: unobserved. Local expiry/fresh-consent/failure behavior is covered; no need to wait years or deliberately exhaust mandates under this authorization. Any real lifecycle exercise is separately reviewed, not silently added to the one-charge scope.
5. **Actual provider-create timeout/crash/ordering fault injection**: not performed, but approved application invariants have deterministic coverage. Do not introduce new mandatory external fault tests without a requirement source.

Razorpay documents Test Mode **Charge this now** and subsequent-debit eligibility within three days of card-token creation. That is a provider facility, not evidence that any retained subscription remains eligible. Current retained resource/cancellation uncertainty must be resolved first. Sources: https://razorpay.com/docs/payments/subscriptions/test/ and https://razorpay.com/docs/api/payments/subscriptions/cancel-subscription/ (checked 27 October 2026).

## Invoice work, business inputs and live readiness

Provider invoice retrieval/validation exists for captured-payment authority; payment receipt HTML/plain text exists. No seller tax-invoice generation, numbered invoice ledger, secure invoice-PDF storage/download or invoice-history API/UI is implemented. A roadmap "Possible route" is not proof of implementation or a new unconditional gate. Invoice implementation is **explicitly deferred from this task**, separate requested future work; never rename a receipt a GST tax invoice.

Concrete required inputs before that work: seller legal name/address and country/state; registration/GST status and GSTIN only if applicable; required buyer billing fields and B2B/B2C handling; invoice numbering/financial-year/sequence policy; authoritative tax treatment/place-of-supply allocation and rounding; chosen secure invoice delivery/storage/history method. Do not invent these or install Invoify. Business confirmation and review belong to live-readiness/invoice work, not repeating sandbox payments. Refunds, discounts, proration and upgrade charges remain unapproved/unavailable.

The conditional renewal proposal is recorded separately in `C12_CONDITIONAL_RENEWAL_SCOPE.md`. Nothing there is authorization to execute.


## Support and renewal preparation follow-up ? 27 October 2026

Six IDs reconciled against Session 03 resources, four paid/two unsuccessful checkout records and READ results; seven cancellation attempts/timestamps/outcomes reconciled. Final support message and two minimal redacted attachments are indexed in `C12_RAZORPAY_CANCELLATION_SUPPORT_DRAFT.md`. No source journal or counter changed. All six cancellation outcomes remain unresolved.

Actual renewal and actual reconciliation recovery remain **open/blocked**, not passed. The corrected conditional scope explicitly includes one permission-controlled admin reconciliation before releasing a retained charged callback; the same charge then verifies duplicate-safe webhook processing. It cannot additionally prove independent webhook-first renewal. Existing caps are unchanged; 4 preflight + 5 admin recovery + 5 webhook reconciliation + 6 contingency GETs require local gating and verified invoice-count assumptions. Support safe-reuse findings, current token/Dashboard eligibility and faithful restoration/gating remain prerequisites. No provider activity, migration, credential loading or accepted test repetition occurred. Installed, email, callback, admin, deterministic coverage and cleanup acceptance remain passed; invoice issuance and production readiness remain separate.


## Support ticket submitted ? owner report, 27 October 2026

Owner confirms submission. Ticket reference/submission timestamp are not recorded; findings remain pending. This supersedes prior UNSENT/prepared-only labels for submission status, not the facts or uncertainty. All four paid cancellation schedules/effective dates/renewal risks and two Created-subscription rejection/closure outcomes remain unresolved. Provider execution is paused; no reads, charges or cancellation retries are authorized by submission. All passed acceptance, original journals/counters and verified cleanup are preserved.
