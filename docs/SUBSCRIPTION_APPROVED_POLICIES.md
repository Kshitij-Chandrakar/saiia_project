# Canonical approved subscription policies

Approved by the user on 24 October 2026. This record supersedes the earlier unresolved-policy rows in the milestone, plan and audit for the matters below. Approval of policy is not implementation, shared migration or production activation acceptance. Existing Free/Plus/Pro catalog decisions and immutable versions remain authoritative.

## Account lifecycle

Every newly verified account receives Free once, without expiry. Trusted configuration pins the exact approved immutable Free version/fingerprint; no arbitrary offer lookup. Bootstrap is idempotent, never replaces paid access and does not backfill existing verified accounts. A server-owned verification cutoff distinguishes new verification from backfill. Auth owns account identity, verification and original signup timestamp.

Paid activation requires a backend-verified successful payment. Upgrades take effect immediately after verification and preserve current-period usage. Downgrade/cancellation takes effect at paid-period end. Failed renewal returns the account to Free when paid access expires. Preserve all saved data; excess resumes remain readable and require selection of the permitted active set, with new uploads blocked while over cap. Billing periods are independent of allowance periods; annual payment retains monthly resets. C12 supplies real provider verification; no customer/admin paid-assignment shortcut is authorized.

## Auto

One active Auto run per account across devices, including Pro. A second cannot start until Stop or server authorization expiry. Pro has unlimited total time, not unlimited concurrent runs. Server-authorized running time counts silence; combined microphone/system counts once. Stop, exhaustion and lease expiry end authorization/charging; never charge after expiry. Use bounded leases/heartbeats, fenced ownership and server time. Client timers are display only. Technical implementation timings must be documented separately from commercial policy.

## Screen and Sketch

Charge only a valid result durably saved and retrievable by its authorized user. Failed/cancelled attempts without such a result release reservations; duplicate/saved replay is free. A deliberate new generation is a new operation. Each successfully answered new screen question counts one analysis. Passage/Data capture alone is free; the answered question resulting from it counts once. Clarification completing the original question stays in that operation. Free cannot submit follow-ups; Plus/Pro can. Classification is server-owned, not a trusted client label.

## Resume

Free initial successful upload is separate from replacement. A replacement counts only after its reviewed profile/index is ready and activation commits. Failure/duplicate retries do not charge; delete/reupload never restores initial-upload eligibility. Preserve the previous usable resume on replacement failure. Apply stored-resume capacity separately from monthly replacement usage and preserve excess data on downgrade.

## Clipboard

Count successfully committed NEW user-written saves only. Failed/duplicate saves do not charge extra. Saved answers remain immutable for every plan; reads remain available after downgrade. Resets do not remove entries; account-wide privacy/deletion is separate from individual edit/delete restrictions.

## Terms and periods

Free Auto: 600 cumulative seconds per IST day. Plus: 18,000 per signup-anniversary month. Pro: explicit unlimited total time. Existing prices/features/other allowances in [Free](FREE_PLAN_APPROVED_DECISIONS.md) and [Plus/Pro](PLUS_PRO_APPROVED_DECISIONS.md) are unchanged. Daily reset is midnight Asia/Kolkata. Monthly reset is the original Auth signup day at midnight IST, clamped in short months and restored afterward. No rollover. Unlimited is distinct from zero, absent or invalid configuration. Operational safeguards remain independent.

Refunds, proration, tax, trials, provider selection and support service promises are not approved by this record. Missing technical composition is unavailable, never fabricated Free/paid access. Production enablement, real backfill/assignments, shared migrations and deployment require separate authorization.

## C12 recurring billing decision, 25 October 2026

The user selected Razorpay Subscriptions with automatic renewal and explicit recurring consent. Approved configurable maximums: 12 monthly billing cycles and 5 yearly billing cycles, subject to provider validation. Disclose the recurring charge, interval and actual maximum term before consent. After the final verified paid period, require fresh consent for further renewal; otherwise return to Free. Never automatically create a replacement mandate. Cancellation preserves access through the verified paid-period end. These decisions supersede the provider-selection/renewal uncertainty only; tax, refunds, discount application and upgrade/proration charges remain unapproved and unavailable. Local implementation and actual-provider acceptance are distinguished in [C12 acceptance](C12_RAZORPAY_LOCAL_ACCEPTANCE.md).

## C12 GST-added payable and display approval, 25 October 2026

The user approved unchanged INR base prices plus 18% GST: Plus monthly 399.00 + 71.82 = 470.82; Plus yearly 2,999.00 + 539.82 = 3,538.82; Pro monthly 899.00 + 161.82 = 1,060.82; Pro yearly 6,499.00 + 1,169.82 = 7,668.82. This supersedes the earlier proposed inclusive-total policy and the prior undecided tax-added/inclusive status, for this calculation and display scope only.

Paid website cards keep the base prominent, put `per month + 18% GST` or `per year + 18% GST` below it, then show `Total: <final payable>`. No separate GST amount or included-tax breakdown appears on pricing cards. Free remains INR 0 with no GST wording. No coupon, crossed-out price or discount badge is added. Checkout/internal invoice preparation retain all components.

Use exact integer paise and versioned payable snapshots without changing immutable catalog bases or historical mandates/consent. New/changed payable reviews require exact quote-bound consent. The four calculations need no rounding. General fractional-paise rounding remains undecided for future prices and fails closed. Approved 12 monthly / 5 yearly cycle maxima, fresh consent after completion, usage periods, eligibility and cancellation timing are unchanged.

Seller identity, registration, location applicability and tax-invoice requirements remain separate live readiness inputs. No GSTIN, CGST/SGST/IGST allocation or compliance claim is approved here. Refunds, discounts and upgrade charges remain unavailable. See [current policy and acceptance scope](C12_PAYABLE_POLICY_AND_TEST_SCOPE.md).

## Implementation evidence

The [C13.2 evidence record](C13_2_IMPLEMENTATION_EVIDENCE.md) records current default-off execution, exact transaction/retry guarantees, technical lease/recovery timings, isolated tests and remaining deployment/installed acceptance. Technical timings are not new commercial policy. The approved decisions above are unchanged.
