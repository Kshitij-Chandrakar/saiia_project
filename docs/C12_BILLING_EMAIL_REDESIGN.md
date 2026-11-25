# C12 initial-payment and renewal email redesign — locally verified

**Later approved publication/inbox execution, 27 October:** actual results (owner-held private record `C12_EMAIL_REDESIGN_01_EXECUTION.md`; excluded from this checkout) supersede the historical unpublished/prepared-only statements below. Three new versioned objects verified, two redesigned emails accepted by Resend, owner confirmed receipt/artwork/no CTA; all within original limits/deadline after bounded transfer recovery. Public website remains undeployed; CTA stays omitted. No production activation; C12 remains open.

26 October 2026. Presentation-only implementation, using the owner's supplied HTML as visual direction and supplied payment/renewal illustrations. No actual email, upload, provider call, migration, shared-service change, activation, commit, push or deployment occurred. Existing payment verification, outbox/event identities, retries, recipient policy, Resend adapter, subjects and cancellation uncertainty are preserved.

## Implemented presentation

Shared table-based layout in `backend/app/email/billing_templates.py`, called only for `billing_payment` and `billing_renewal` by the existing renderer. Pale blue **#eef4ff**, white max-600px container, optional rounded corners/shadow, blue illustration panel, existing mascot and live-text wordmark, navy heading and account button, aligned summary, muted automated footer, hidden preheader and Arial/Helvetica/sans-serif fallbacks. Inline layout styles, responsive rules and a fixed-width Outlook conditional wrapper; no JavaScript, forms, SVG/base64 images, fake invoice button or reset/recovery content. Cancellation/access-end layout and behavior are unchanged.

- Initial heading: **Payment received**; verifies payment and explains current plan/access.
- Renewal heading: **Your subscription is renewed**; confirms renewal and the new paid period.
- Immutable source snapshot currently supplies **plan, interval, INR total and paid-period end**, plus offer/price identity. It does **not** contain payment date/reference or period start. Missing fields are omitted; none are derived from dispatch time, invented or backfilled. No next-charge, invoice-number or cancellation confirmation is added.
- Existing exact integer-paise formatter remains authoritative. HTML escapes every dynamic text value. Configured image/account references accept HTTPS only and reject credentials, queries, fragments, control characters, markup, protocol-relative links and invalid paths. Payment details are independent of images.
- Both text variants match the heading, explanation, plan/interval/total/available end and non-GST-invoice/automated-message disclosures. C10's existing plain-text safety contract forbids arbitrary absolute URLs; it remains unchanged. When a site origin is configured, plain text uses the existing relative `/auth/dashboard` path rather than weakening that contract.

## Owner-confirmed destination and deployment configuration

Owner explicitly confirmed **no public website origin is deployed**. Keep production `EMAIL_WEBSITE_ORIGIN` **unset**. Real HTML and plain-text receipts therefore omit the account CTA until an approved HTTPS origin is configured. Local previews alone show the existing `/auth/dashboard` destination using `http://localhost:5173/auth/dashboard`; this is not a deployed public destination.

No shared backend email asset setting existed; the supplied Auth HTML contains direct image URLs. The existing C10 settings module now has two optional, server-owned presentation fields, both empty by default:

```text
EMAIL_ASSET_BASE_URL=<approved published HTTPS directory containing the three raster files>
EMAIL_WEBSITE_ORIGIN=<approved deployed HTTPS origin, without a path>
```

No dotenv or Auth configuration was edited. No existing public Auth URL is repointed to unpublished artwork. If asset base is unset, image tags/hero are omitted and the wordmark/live receipt remain complete. If website origin is unset, no button or plain-text account link is emitted. Invalid configured references fail closed. The existing account route is `/auth/dashboard`, as used by `BillingCheckout.jsx` and registered in `App.jsx`.

Before real image use, publish exactly these local files into the approved existing asset hosting workflow and verify their returned content types/dimensions, without modifying Auth assets:

| Local file under `frontend/public/email-assets/billing/` | Dimensions | Size | Alt text |
| --- | --- | --- | --- |
| `payment-success.jpg` | 1080 × 540 | 56,965 bytes | Intervucopilot mascot celebrating beside a receipt and checkmark |
| `renewal-success.jpg` | 1080 × 540 | 63,394 bytes | Intervucopilot mascot beside a calendar with renewal arrows and a checkmark |
| `mascot.png` | 120 × 80 | 11,659 bytes | Intervucopilot mascot |

All are local and **unpublished**. The supplied hero PNGs were resized/compressed as progressive JPEGs; the exact existing header mascot was proportionally downsampled to PNG. No character redraw or AI generation was necessary. `manifest.json` records source hashes and dimensions. Total raster payload **132,018 bytes**; heroes display at max 540 × 270, header at 48 × 32. No price/date/text/logo/button is baked into the heroes. Public uploads and URL configuration are not authorized by this task.

## Previews and screenshots

Generated under `tmp/c12-billing-email-redesign/previews/`:

- `billing_payment.html`, `.txt`, `billing_payment-images-blocked.html`
- `billing_renewal.html`, `.txt`, `billing_renewal-images-blocked.html`
- `assets/` contains the three local raster files; previews work from the filesystem without network access.

All acceptance previews retain a visible **SYNTHETIC C12 TEST** label and no-new-Razorpay-payment disclaimer. Preview-only asset references are rewritten to local files; synthetic `preview.invalid` scaffolding is never a deployment URL. The production renderer's empty settings omit unconfigured images/CTA as described above. The unchanged acceptance harness still adds its own explicit test subject/body labels.

Screenshots in `tmp/c12-billing-email-redesign/screenshots/` use `{billing_payment|billing_renewal}-{800|600|390}{-images-blocked}.png`: **12** full-page captures. Inspected both variants at desktop/mobile widths and both blocked-image mobile views. No horizontal overflow, container <=600px, complete images at proportional scale, readable wrapping/dates/summary/CTA/footer. Blocked-image alt placeholders are intentionally visible; the wordmark and all financial content remain live text.

Reproduce without provider configuration:

```powershell
$env:PYTHONPATH = 'E:\saiia_project\saiia_project\backend'
& 'E:\deepfake_envs\SaIIA\python.exe' backend/tests/render_billing_email_previews.py --output tmp/c12-billing-email-redesign/previews
```

From `frontend`: `npx playwright test --config tests/catalog/billing-receipts.playwright.config.js`. Two workers, no retries, local files/assets, HTTP(S) requests blocked, no server, no credentials; failure traces/screenshots stay local. The small page object tests headings, required text, local CTA, max width, overflow and loaded/blocked images. Existing admin fixture email-heading expectations were updated to match the intentional new headings; no admin behavior/UI changed.

## Verification

- Focused email/template/provider/C10/marketing/acceptance-boundary regressions: **90 passed, 1 skipped in 1.12 seconds**. Skip is `test_email_claim_integration.py`: explicit local Supabase integration opt-in required. No opt-in/shared database was used.
- Playwright: **12 passed, 4.9 seconds** final visual run, including 800/600/390px and loaded/blocked images for each variant. Screenshots were visually inspected.
- Python Ruff checks and formatting: **passed**, five touched files. Config import/layout formatting corrected without altering marketing behavior.
- Mypy: **passed**, three touched backend modules.
- Scoped ESLint: **passed**, receipt spec/config and updated shared email-preview assertion.
- Tests verify required variables, yearly/exact money, no fabricated absent fields, escaping, server-configured account/asset references, unsafe URL rejection, plain-text parity and safety contract, images/tables, preheader and absence of password/reset/invoice/support claims.
- No application UI or billing-transition logic changed; no production build or payment/provider acceptance was repeated for this presentation change. No disposable database or public runtime was needed.
- Graphify was queried before editing and rebuilt/queried after: `graphify-out/c12-email-redesign/` contains report/JSON/HTML for 43 scoped code files, zero semantic-model tokens. Extraction diagnostics include **257 dangling-endpoint edges and 28 collapsed directed endpoint pairs**. This incomplete navigation graph is not correctness evidence.

Earlier real email/session journal remains SHA-256 **F8655D9A1AB9BD134452FEB07E03B990605979360330F33C9D6FD2229C63C761** and Razorpay Session 03 remains **D3132F3648B8627679D6A195E50C25225DE0B5A72F2953A37D1099EF20273A35**. Those accepted observations apply to the previous HTML. They do **not** establish inbox compatibility of this redesign. Six cancellations remain unresolved; C12 remains open.

## Later two-email inbox check — prepared only, not authorized

After artwork is separately approved/published and its asset base configured, request one fresh bounded check: maximum **two real sends total**, no automatic retries, one initial and one renewal **synthetic** receipt, through the existing masked local harness and disposable PostgreSQL. Reuse the confirmed send-only `billing@intervucopilot.in`, Reply-To unset and sole recipient `acceptance-recipient@example.invalid`. A new maximum 15-minute window and durable journal would be required; do not reuse/reset the exhausted email-admin-01 journal or previous credentials. No Razorpay events are manufactured through API calls.

Keep the CTA absent while the public website is undeployed. Collect provider HTTP acceptance, provider-reported delivery and actual inbox receipt/rendering separately. Inspect both messages at Gmail desktop/mobile, with images enabled/blocked, and plain-text view. Actual Outlook acceptance requires an owner-authorized Outlook test inbox; do not assume the Gmail recipient proves Outlook. Browser previews cannot establish Gmail/Outlook sanitization, Word-engine rendering, dark-mode behavior or provider image caching. Round corners/shadows may degrade gracefully; no compatibility guarantee is made.

## Changed files

`backend/app/email/billing_templates.py`, `billing.py`, `config.py`; `backend/tests/test_billing_receipt_templates.py`, `render_billing_email_previews.py`; `frontend/tests/catalog/billing-receipts.spec.js`, its Playwright config and the existing shared `billing-admin.spec.js` preview heading assertion; three raster files, manifest and README under `frontend/public/email-assets/billing/`; this evidence and tracker/acceptance cross-references. No migration, recipient/identity change, provider activation or upload.
