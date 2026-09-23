# C10.1 - Email System Planning and Safety Contract

## Status

**C10.1 completed/merged.** C10.1 is documentation-only and defines the email safety contract. No email provider has been called, no SMTP has been configured, and no real email has been sent by this repository. The C10.2A runbook is complete in `docs/C10_2A_SUPABASE_AUTH_RESEND_SMTP_RUNBOOK.md`; C10.2B live delivery remains blocked pending a verified Resend sender/domain. C10.3A, C10.3B, C10.3C, and C10.3D backend dry-run/event foundations are complete locally; PR #32 is merged, the `outbound_email_events` migration is applied to remote Supabase dev, and post-apply tests passed. C10.4A and C10.4B welcome-template and dry-run trigger work is complete locally; C10.5A feature templates/helpers and C10.5B available dry-run triggers are complete locally, while session-summary wiring and real delivery remain deferred. Full C10.3, real C10.4 delivery, and full C10.5 remain incomplete.

## 1. C10 Goal

C10 will build a safe email system for:

- auth verification emails
- password reset emails
- welcome emails
- session summary emails
- transcript export emails
- AI notes ready emails
- account and security notifications
- future promotional and discount emails

## 2. Email Categories

### A. Supabase Auth Emails Through Resend SMTP

This category includes signup verification, password reset, and future email-change confirmation or magic-link emails if needed.

- Supabase Auth generates secure verification and reset links.
- Supabase Auth owns auth-email resend, cooldown, and rate-limit behavior.
- intervuAI does not create custom verification or reset tokens.
- Resend only delivers the email through SMTP.
- Templates use Supabase-supported variables.
- Supabase Auth template variables such as `ConfirmationURL` and `RecoveryURL` are allowed when required by Supabase Auth; their full values must never be logged, tracked, telemetered, or stored.
- Redirect URLs must be fixed per environment. Local development may allow only `http://localhost:5173/auth/callback` and `http://localhost:5173/auth/reset-password`; staging and production must require HTTPS approved-domain URLs. User-supplied or unapproved destinations are rejected.
- `outbound_email_events` does not claim or deduplicate Supabase Auth verification, reset, email-change confirmation, or magic-link emails.
- C10.2 must document and manually test allowed and rejected Supabase Auth redirect URLs, resend behavior, cooldown/rate limits, and SMTP delivery.
- Resend SMTP must use authenticated SMTP with TLS/encryption and certificate validation; plaintext SMTP is prohibited. The C10.2 setup checklist must verify the SMTP host, port, authentication, TLS, and certificate settings before any real demo email. SMTP passwords and API keys must not appear in the repository, docs, or tests.

For custom transactional and marketing links created by intervuAI, secrets are prohibited in query strings. Full Supabase Auth URLs must not be placed in `outbound_email_events` metadata, analytics, or logs. No custom auth tokens are created.

### B. Backend Transactional Emails Through the Resend API

This category includes welcome emails after verified login/profile bootstrap, AI notes ready, session summary, transcript export, and account/security notifications.

- Sends are initiated only by the backend.
- User-action routes are authenticated and use `CurrentUserDep`.
- Session ownership is verified server-side.
- `user_id` is never trusted from a request body.
- The idempotency, claim-lease, retry, and reconciliation rules below apply only to backend transactional emails, not Supabase Auth emails.
- Idempotency is scoped by `user_id`, `email_type`, `recipient_email`, nullable `session_id`, and `idempotency_key`.
- The planned unique index/constraint uses PostgreSQL `NULLS NOT DISTINCT` across `user_id`, `email_type`, `recipient_email`, `session_id`, and `idempotency_key`, so sessionless events are also unique. If that syntax is unavailable, equivalent partial unique indexes must separately cover `session_id IS NULL` and `session_id IS NOT NULL`.
- Before calling the provider, the backend atomically creates or claims an `outbound_email_events` row. This NULL-safe uniqueness rule prevents concurrent duplicate claims.
- `pending` is a pre-send reservation. Every pending reservation must have a present `pending_expires_at` or equivalent pending lease. The backend may reclaim it only when no active sending attempt exists, that present lease is expired, and the same idempotency scope still matches. Reclamation uses an atomic compare-and-claim matching the scope, previous status `pending`, and `pending_expires_at < now()`; only a successful claim moves it to `sending` with a new `claim_token` or `attempt_id`, `sending_started_at`, and `lease_expires_at`.
- Event status is one of `pending`, `sending`, `sent`, `failed`, `canceled`, `needs_reconciliation`, or `retry_blocked` as needed; only one active send attempt exists for a given idempotency scope.
- Reusing an idempotency key reuses the existing event state. A `sent` event returns its prior `provider_message_id` and status; a fresh `sending` claim returns a safe already-processing response; an unexpired `pending` reservation returns a safe already-processing response; an expired `pending` reservation may be reclaimed because provider send has not started.
- A pending row without a pending lease is invalid or corrupt. It must move to `needs_reconciliation` or `retry_blocked`, not be blindly reclaimed. Expired pending rows are safely reclaimable only through the atomic compare-and-claim, without changing the unique idempotency scope or violating the single-active-attempt rule.
- Only transient or explicitly retryable failures can receive a new claim/retry. Permanent failures remain `failed` and require user correction or a new valid request after the cause is fixed. Confirmed not-sent is not automatically retryable unless the failure is transient or explicitly retryable.
- Provider success followed by a database update failure requires reconciliation rather than an automatic resend. A provider timeout or unknown result must not blindly resend. Provider idempotency support is used where available in addition to database uniqueness.
- Logs and any event records contain safe metadata only.

Canonical backend transactional `email_type` values are:

- `welcome`
- `account_security`
- `ai_notes_ready`
- `session_summary`
- `transcript_export`

The human-readable descriptions above are aliases only. These values, and only these values, use `outbound_email_events` idempotency.

### Abandoned sending claims

- Each send attempt has a `claim_token` or `attempt_id`, plus `sending_started_at` and `lease_expires_at`. Only the holder of the active claim token may update that attempt.
- An expired `sending` lease is never reset blindly to `pending`. First reconcile provider state using the provider idempotency key, provider lookup, or delivery webhook when available.
- If the provider confirms sent, mark the event `sent`. If it confirms failed or not sent, claim a retry with a new token only when the failure is transient or explicitly retryable; otherwise keep it `failed` and require correction or a new valid request. If provider state is unknown, mark the event `needs_reconciliation` or `retry_blocked` and defer to documented support/manual handling rather than risking a duplicate.
- A same-key request with an expired sending claim enters reconciliation. A retry may send only after the provider proves the message was not sent or provider idempotency guarantees deduplication.
- A same-key request with an expired pending claim may be reclaimed safely because the provider call has not started; it still requires a present expired pending lease, an atomic compare-and-claim, a new claim token, and the preserved unique scope.

### Reconciliation authority

- Moving an event into `needs_reconciliation` assigns a `reconciliation_token` or increments a `row_version`. Only the holder of the current reconciliation token, or an update matching the current row version, may record the outcome.
- Late results carrying an old `claim_token` or `attempt_id` are rejected and cannot overwrite reconciled state. Reconciliation updates are conditional compare-and-set operations.
- `needs_reconciliation` may move to `sent` only when the provider confirms sent; to `failed` only when the provider confirms permanent failure; or to `sending`/retry only when the provider confirms not sent and the failure is transient or explicitly retryable. Unknown provider state remains `needs_reconciliation` or `retry_blocked`.
- No reconciliation path may perform a blind resend.

C10.3B migration/service tests prove duplicate prevention for both `session_id IS NULL` and a populated `session_id`, abandoned pending recovery, a pending row with a missing lease is not blindly reclaimed, expired sending claims are not retried blindly, only transient/explicitly retryable failures receive a new claim, `claim_token` prevents stale attempt updates, and `reconciliation_token` or `row_version` prevents stale worker overwrites.

### C. Marketing and Promotional Emails

Discounts, product updates, launch offers, and plan-upgrade offers are not implemented in C10.1.

- Require explicit marketing opt-in.
- Require unsubscribe support.
- Remain separate from transactional email.
- Unsubscribing from marketing must not block auth or security emails.

Deferred marketing `email_type` values are `marketing_promotion_future` and `marketing_product_update_future`; they require opt-in and unsubscribe support before any implementation.

Supabase-owned auth `email_type` labels, which are not stored in `outbound_email_events`, are `auth_signup_verification`, `auth_password_reset`, `auth_email_change_confirmation_future`, and `auth_magic_link_future`.

## 3. Real Email Demo Strategy

### Local Automated Tests

```env
EMAIL_ENABLED=false
EMAIL_DRY_RUN=true
```

No real email is sent. Tests use a fake or dry-run provider.

### Manual Mentor Demo

```env
EMAIL_ENABLED=true
EMAIL_DRY_RUN=false
```

Real Resend email delivery is allowed only for the demo, using our own verified email addresses. Promotional email remains disabled.

### Production Later

Production will use real Resend delivery, stronger rate limits, a verified domain, marketing unsubscribe support, and monitoring/logging with safe metadata.

## 4. Config/Environment Contract

The planned environment contract is:

```env
EMAIL_ENABLED=false
EMAIL_DRY_RUN=true
EMAIL_PROVIDER=resend
RESEND_API_KEY=
EMAIL_FROM=
EMAIL_REPLY_TO=
APP_PUBLIC_URL=
RESEND_WEBHOOK_SECRET=
```

Secrets are never hardcoded or committed. Real keys belong only in local environment configuration or the eventual secret manager. Automated tests use a fake/dry-run provider.

## 5. Database Event Log Plan

The C10.3B backend-owned table is implemented through `supabase/migrations/20260904143000_add_outbound_email_events.sql` and is applied to remote Supabase dev after PR #32 merged; post-apply tests passed. C10.3C connects this event store to the offline/dry-run email service without adding delivery:

- `id`
- `user_id`
- `session_id` nullable
- `email_type`
- `recipient_email`
- `provider`
- `provider_message_id` nullable
- `idempotency_key`
- `claim_token` or `attempt_id`
- `reconciliation_token` or `row_version`
- `sending_started_at` nullable
- `lease_expires_at` nullable
- `pending_expires_at` nullable
- `status`
- `error_code` nullable
- `metadata_json` containing safe metadata only
- `created_at`
- `updated_at`

Outbound email event inserts and updates are backend-only. Frontend/client direct insert, update, and delete are prohibited. A future user-facing API may return only safe projected status for the authenticated owner; there are no frontend direct table writes. No event log may contain raw transcript, resume text/chunks, prompts, tokens, headers, or secrets.

### Access, projection, and retention

- Backend/service-role processes may read full event metadata for delivery and reconciliation.
- Users may read only their own safe event status if a user-facing email history is added later; the initial implementation has no frontend direct table reads or writes.
- A user-facing response may expose `email_type`, `status`, `created_at`, `provider`, and a safe message. `recipient_email` should be masked in UI and log output when possible. `provider_message_id` remains internal unless support needs it.
- Keep event logs for a limited support/debug window, 90 days by default. Longer retention requires a later compliance, billing, or security decision.
- Account deletion should delete or anonymize that user's email events. Privacy deletion removes or anonymizes `recipient_email`.
- Never retain raw email bodies, transcript/resume content, prompts, tokens, headers, or secrets.

No migration is created in C10.1.

## 6. Email Preference Plan

The C10.6A local foundation extends `user_settings` with server-recorded consent and preference fields:

- `terms_accepted` and `terms_accepted_at`
- `privacy_accepted` and `privacy_accepted_at`
- `marketing_email_opt_in` and `marketing_email_opt_in_at`
- `marketing_email_opt_out_at` for later opt-out handling
- `consent_source`
- `consent_version`

The local-only migration is `supabase/migrations/20260904170000_add_signup_consent_preferences.sql`; it has not been applied to remote Supabase. The no-consent legacy profile bootstrap remains compatible with the pre-migration schema, but consent-bearing bootstrap is intentionally migration-dependent. Rollout order for a target environment is: (1) merge and review the implementation, (2) apply `20260904170000_add_signup_consent_preferences.sql`, (3) apply `20260905103000_add_marketing_unsubscribe_tokens.sql`, (4) set `VITE_CONSENT_FEATURE_ENABLED=true`, and (5) deploy/enable the consent and unsubscribe flows. The frontend consent flow is disabled by default until that sequence is complete. If the new columns are absent, the backend schema gate must fail before profile/settings mutation rather than drop consent fields or report persistence success. The authenticated profile-bootstrap path writes these fields using the verified JWT user identity. Signup requires Terms and Privacy acceptance, while marketing opt-in is explicit and defaults to no preference update until the checkbox is touched. The signup links currently use safe `/terms` and `/privacy` placeholders; real legal pages must be supplied before release.

C10.6B adds a local-only, backend-owned unsubscribe foundation. The migration `supabase/migrations/20260905103000_add_marketing_unsubscribe_tokens.sql` must run after the C10.6A consent migration and is not applied to remote Supabase in this phase.

- Secure opaque tokens are generated with the standard cryptographic random source; only a SHA-256 hash is stored.
- Each token is scoped to its server-provided `user_id`, `recipient_email`, and the fixed `marketing` category, with `created_at`, `expires_at`, `used_at`, and `revoked_at` state.
- Creation is service-role-only. The consume operation looks up the hash, rejects expired/used/revoked/invalid tokens without exposing account data, sets `marketing_email_opt_in` false, records `marketing_email_opt_out_at`, and marks the token used atomically.
- The marketing guard reads only the authenticated user's preference. Opting out never blocks auth, account-security, welcome, or other transactional email.
- Raw tokens are returned only from token creation for future link construction; they are never stored or logged. Full unsubscribe URLs, tokens, prompts, transcript/resume content, headers, and secrets are excluded from logs and metadata.
- Frontend/client direct token-table writes are prohibited. C10.6C now adds the public unauthenticated `POST /api/email/unsubscribe` endpoint and the frontend `/unsubscribe` confirmation page locally. The endpoint accepts only a token, consumes it through the existing hash-only service/RPC, and returns a generic response for valid, invalid, reused, or expired tokens without account disclosure. The page removes the token query parameter from the visible URL, never displays or persists the token, and explains that transactional email is unaffected. The local migrations remain unapplied remotely; promotional campaign sending is not implemented.

Marketing email is allowed only when `marketing_email_opt_in` is true. C10.6B token/opt-out behavior and C10.6C public link integration are complete locally, while promotional delivery remains deferred.

## 7. Future Backend Architecture

The planned implementation consists of:

- email provider interface
- dry-run provider
- Resend provider
- email service
- safe, versioned template layer
- idempotency helper
- safe event logging
- provider error handling
- bounded retry strategy
- rate limiting

Supabase Auth remains responsible for verification/reset link generation. Resend remains the delivery provider, not a token or identity system.

## 8. Future API Routes

These routes are planned only and are not implemented in C10.1:

- `POST /api/interview-sessions/{session_id}/email-summary`
- `POST /api/interview-sessions/{session_id}/email-transcript`
- `POST /api/interview-sessions/{session_id}/email-notes`

Each future route must be authenticated, verify session ownership, require an idempotency key, and initially send only to the verified email of the logged-in user.

## 9. C10 Phase Breakdown

- **C10.1 - Email plan and safety contract:** completed/merged; no sending implementation.
- **C10.2A - Supabase Auth emails through Resend SMTP:** runbook/setup documentation completed/merged; live C10.2B delivery is blocked pending a verified Resend sender/domain.
- **C10.2 - Supabase Auth email delivery:** not complete until live verification/reset emails are tested.
- **C10.3A - Backend email foundation with dry-run provider:** completed locally; backend config, provider contract, safe dry-run provider, and tests are present, with no real sending.
- **C10.3B - Outbound email event persistence and idempotency foundation:** completed locally and applied to remote Supabase dev; backend-only event storage, NULL-safe claims, lease/state transitions, reconciliation fencing, and tests are present, with no delivery.
- **C10.3C - Dry-run event-store integration:** completed locally; the service claims events before the dry-run provider, updates outcomes with the active claim token, replays sent events safely, and covers lease/retry behavior without network delivery.
- **C10.3D - Remote migration apply and post-apply validation:** completed; PR #32 is merged, `20260904143000_add_outbound_email_events.sql` is applied to remote Supabase dev, and post-apply tests passed. No real email delivery was enabled.
- **C10.3 - Backend transactional email delivery:** not complete; live provider integration and transactional triggers remain deferred.
- **C10.4A - Welcome email template + dry-run trigger:** completed locally; the safe plain-text `welcome` template uses the existing backend event-store idempotency path and dry-run provider. Signup/profile bootstrap wiring and real delivery are not included.
- **C10.4B - Wire welcome email trigger in dry-run mode:** completed locally; the authenticated profile bootstrap route triggers the welcome event from verified JWT identity/email, remains non-blocking on email failure, and preserves the existing response contract. No real delivery or Auth email routing is included.
- **C10.4 - Welcome email delivery:** dry-run path complete locally; real delivery remains blocked pending a verified Resend sender/domain and intentional live-provider enablement.
- **C10.5A - Feature email templates in dry-run mode:** completed locally; safe plain-text `ai_notes_ready`, `session_summary`, and `transcript_export` templates/helpers use session-scoped event-store idempotency and the dry-run provider. No automatic triggers, attachments, raw transcript/notes content, or real delivery are included.
- **C10.5B - Feature email trigger wiring:** completed locally for `ai_notes_ready` after successful notes generation and `transcript_export` after successful export preparation. No existing session-summary preparation flow was found, so that trigger remains deferred; all delivery remains dry-run-only.
- **C10.5 - Session summary, transcript, and AI notes emails:** incomplete; C10.5A template/helper groundwork and the available C10.5B dry-run triggers are complete locally, while session-summary wiring, remaining authenticated actions, and production delivery remain deferred.
- **C10.6A - Signup consent and marketing preference foundation:** completed locally; signup requires Terms and Privacy acceptance, marketing opt-in is unchecked by default, consent is persisted through authenticated profile bootstrap, and no marketing sends are implemented.
- **C10.6B - Marketing unsubscribe token/opt-out foundation:** completed locally; hash-only opaque token generation, expiry/use/revocation checks, service-role-only atomic opt-out, and a marketing preference guard are implemented and tested. The local migration `20260905103000_add_marketing_unsubscribe_tokens.sql` is not applied remotely. No public unsubscribe endpoint, campaign sending, or real email delivery is included.
- **C10.6C - Public unsubscribe link endpoint and promotional integration:** completed locally for the public `POST /api/email/unsubscribe` endpoint, safe `/unsubscribe` confirmation page, token-removal behavior, and tests. Apply `20260904170000_add_signup_consent_preferences.sql` before `20260905103000_add_marketing_unsubscribe_tokens.sql`, then enable/deploy consent and unsubscribe features. The local migrations remain unapplied remotely; promotional campaign sending and real delivery are not started.
- **C10.6 - Marketing preferences and promotional emails:** incomplete; C10.6A consent, C10.6B token/opt-out, and C10.6C public unsubscribe integration are complete locally, while promotional delivery and remote migration rollout remain deferred.

## 10. Manual Demo Checklist

The later demo should show:

- signup verification email received
- password reset email received
- welcome email received
- dry-run mode disabled only for the demo
- no secrets committed
- logs showing safe email event metadata only

## Safety Boundary

C10.1, C10.3A, C10.3B, C10.3C, C10.3D, C10.4A, C10.4B, C10.5A/B, C10.6A, C10.6B, and C10.6C do not call Resend, configure Supabase SMTP, add real API keys, send emails, create custom verification/reset tokens, modify applied migrations, or implement promotional campaign messaging. C9 remains merged/closed. C10.2A runbook/setup documentation is completed/merged, but C10.2B live verification/reset delivery is blocked pending a verified Resend sender/domain, so C10.2 delivery is not complete. C10.3A is completed locally with disabled/offline dry-run defaults. C10.3B adds the backend-owned `outbound_email_events` migration and event-store boundary, and C10.3D records its successful remote dev apply and post-apply validation. C10.3C connects the event store to the dry-run provider only. C10.4A adds the service-level welcome template and C10.4B wires it after authenticated profile bootstrap; C10.5A adds feature templates/helpers and C10.5B wires available notes-generation and transcript-export success points only. C10.6A adds signup consent/preference capture, C10.6B adds hash-only unsubscribe tokens and atomic opt-out, and C10.6C adds the public generic unsubscribe endpoint and safe confirmation page. The C10.6A/C10.6B migrations remain local and unapplied remotely. These paths remain dry-run-only and non-blocking, with no session-summary trigger because no preparation flow exists. Full C10.3/C10.5/C10.6 and real C10.4/C10.5 delivery remain incomplete because real delivery is not enabled.

## C10.2C.1 — one-time auth email action handler (local implementation)

The frontend now handles `/auth/confirm` with Supabase `verifyOtp({ token_hash, type })` using `email` for signup verification and `recovery` for password recovery. Missing, duplicate, unknown, or unsafe parameters are rejected before verification. Optional `next` accepts only `/auth/dashboard` or `/auth/status`, matching the existing auth route allowlist.

A valid verification displays **Email verified** and **Your Intervu AI account is ready.** Continue enters the existing authenticated account/profile-bootstrap flow when a session was returned; otherwise it opens login. Recovery success displays the existing password form on the scrubbed confirmation route. The form is hidden after a successful password update. A replayed/expired link shows a safe expired-or-already-used message and a login/reset-request action, even when another session already exists. A reload of the scrubbed confirmation URL requires a new email link. Supabase enforces token consumption; no browser token cache is used. StrictMode effect replay shares the pending verification rather than submitting the token twice.

The query and fragment are removed from the address bar before verification. Token hashes are never sent to the application backend, written to localStorage, displayed, or included in application errors/logs. Supabase retains its existing session persistence behavior. Hosting/CDN access logs must redact query strings for this route: frontend URL cleanup cannot remove a URL already received by the host. No real email/Supabase smoke test or deployment has been performed as part of this local implementation.

### Template cutover — only after the route is deployed

Keep current Supabase templates until the deployed frontend serves `/auth/confirm` directly (SPA fallback included). Then manually change **both the CTA and fallback link** in each template:

- Confirm signup: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email`
- Reset password: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery`

In HTML attributes escape the query separator as `&amp;`. Replace `{{ .ConfirmationURL }}` in both locations; use the deployed app origin as the existing Site URL. Smoke-test fresh, second-click, expired, and invalid links plus password reset completion before rollout. Do not change SMTP, Resend, DNS, or secrets for this frontend cutover. Existing legacy callback/reset routes remain available during transition. C10.2C.2 custom auth domain / Google OAuth branding remains pending.

Reference: [Supabase verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp) and [email templates](https://supabase.com/docs/guides/auth/auth-email-templates); local SDK `@supabase/supabase-js` 2.111.0.

## C10.7A — backend marketing foundation (local, no campaigns enabled)

The replacement email-type CHECK is a superset of the previous allowed values and is added `NOT VALID`, avoiding an immediate scan of existing rows. New and updated rows are still checked; the ALTER TABLE operations still acquire locks. Validation is deferred to a later maintenance migration after rollout. No validation migration is included in C10.7A.

`app.email.marketing.MarketingEmailService.send_marketing_email` is a backend-only, single-recipient service. It requires a user UUID, recipient email, campaign key, `template_key="product_update"`, and an idempotency key. Trusted backend callers must supply the recipient associated with that user; no public sending endpoint, frontend Resend integration, worker, scheduler, or campaign UI was added. Existing Supabase Auth SMTP and transactional/welcome/feature dry-run behavior are unchanged. Do not use Supabase Auth SMTP for marketing.

Configuration (backend only):

| Setting | Default / requirement |
| --- | --- |
| `EMAIL_PROVIDER_MODE` | `dry_run`; accepts only `dry_run` or `live` |
| `MARKETING_EMAILS_ENABLED` | `false`; explicit `true` required for live dispatch |
| `RESEND_API_KEY` | Secure backend environment only; required for `live` mode; never print it |
| `MARKETING_FROM_EMAIL` | `updates@intervucopilot.in`; exact sender domain enforced |
| `MARKETING_FROM_NAME` | `Intervu AI` |
| `MARKETING_REPLY_TO` | Omitted by default; if set, must be a safe address on `intervucopilot.in` |

Dry-run works without a Resend key and never contacts Resend. Persistence and token creation still require the existing database services; tests use offline fakes. Live dispatch requires **all** of `MARKETING_EMAILS_ENABLED=true`, `EMAIL_PROVIDER_MODE=live`, and a backend-only `RESEND_API_KEY`. Unknown/invalid configuration fails closed. No live flags were enabled or real messages sent during implementation.

The service reuses `user_settings.marketing_email_opt_in` and the existing unsubscribe token service. Only boolean `true` qualifies; missing, false, or malformed consent cancels the event. Unsubscribe consumes the existing hashed token and sets opt-in false. Consent is checked again after token creation immediately before dispatch. A remote opt-out racing an already dispatched provider request cannot retract that request; this is not an atomic transaction across Supabase and Resend. Token/consent errors block sending. No raw resume, transcript, interview data, claims, or discounts are accepted by the sample template.

`product_update` uses subject **What's new in Intervu AI** (typographic apostrophe in the message), generic product copy and a required unsubscribe URL. The body links to the existing `/unsubscribe?token=...` UI. `List-Unsubscribe` points to `https://intervucopilot.in/api/email/unsubscribe/one-click?token=...`; `List-Unsubscribe-Post` is `List-Unsubscribe=One-Click`. The new backend POST endpoint reuses token consumption without login. Uvicorn access records redact that endpoint's query, including rejected-method responses. Never enable URL/click tracking on unsubscribe links. Hosting/proxy/APM logs must also redact these queries; application redaction cannot control upstream logs.

`outbound_email_events` is reused with type `marketing_product_update`. Apply the forward migration `20260922120000_add_marketing_email_event_type.sql` through the normal approved migration process; it is **not applied remotely by this work**. It extends the type constraint and claim function allowlist while preserving RLS, service-role-only privileges and atomic unique claims. Metadata contains only `campaign_key`, `template_key`, and `dry_run`; provider message ID remains in its dedicated column. No body, HTML, raw token or unsubscribe URL is stored in event metadata. Recipient email remains in the existing restricted event column; logs use masked recipients.

Repeated keys return the terminal event or block an in-progress attempt. Dry-run and canceled events do not become live sends after flag changes; use an intentional new campaign/key for a new action. Resend receives the persisted event ID as its idempotency key. There are no automatic retries. A timeout, provider error, or failure to persist completion leaves the claim for existing reconciliation rather than risking a duplicate. Do not manually retry an uncertain message without provider reconciliation. Existing unsubscribe tokens retain their configured expiry.

Before any separately authorized real send: apply/verify the migration, verify consent and unsubscribe storage, verify the sender with Resend, deploy and route both public unsubscribe URLs (including `/api/email/...` to the backend), test one-click POST and replay/expired links, confirm query-log redaction and provider tracking settings, and make a reply-to decision. `support@intervucopilot.in` receiving is deferred because GoDaddy mailbox/forwarding needs paid setup. Omit reply-to until a receiving mailbox is confirmed; this phase does not depend on support receiving. No campaigns are enabled.

Provider reference: [Resend send-email API](https://resend.com/docs/api-reference/emails/send-email) and [idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys). The adapter uses existing `requests`, a bounded timeout, no redirect following, no automatic retries, and sanitized errors.

### Temporary C10.7A live smoke command (dev-only)

`app.email.marketing_smoke` is a temporary developer CLI kept in source with focused tests, not a public route or scheduled job. From `backend`, run:

```powershell
python -m app.email.marketing_smoke --user-id <test-user-uuid> --email <that-users-email> --idempotency-key c10-7a-smoke-<unique-attempt-id>
```

The operator must use the email belonging to the specified opted-in test account. Configure secrets only in the secure backend environment. The command does not enable flags: it refuses dispatch unless `EMAIL_PROVIDER_MODE=live`, `MARKETING_EMAILS_ENABLED=true`, a valid backend Resend configuration, and explicit consent are present. It sends one `product_update` request through the existing marketing service; existing consent rechecks, token creation, provider, event claims and reconciliation remain authoritative. Deployment/migration/unsubscribe readiness prerequisites above still apply.

Use one unique idempotency key for one intended smoke send and reuse that same key when checking/retrying it. Do not generate a new key after an uncertain failure; inspect/reconcile the stored event first. A `sent` result may be a replay of that event and confirms provider acceptance, not inbox delivery. Output is restricted to status, validated event/provider UUIDs and mode. Failures print a generic status only, never exceptions, recipient addresses, credentials, headers or unsubscribe values. Exit codes: 0 for sent/replayed-sent, 2 for blocked/canceled/incomplete, 1 for failure or invalid arguments. No live test was run during implementation. Remove this temporary tool after smoke verification; no ongoing campaign tooling is implied.

### Signup consent persistence fix

Email/password signup now checks that pending consent was saved before creating the auth user. After `/auth/confirm` verifies an `email` action and receives a session, it runs the existing authenticated profile bootstrap with consent from `intervuai.pendingSignupConsent` only when the feature flag is enabled and the stored email matches the verified session email (trimmed/lowercased). It clears matching pending consent only after bootstrap succeeds; a newer signup record is preserved. Bootstrap failure leaves consent pending and shows a safe account-setup retry message linking to Account, rather than claiming the email link expired.

Login does not manufacture consent. Marketing remains explicit `true`, unchecked `false`, or untouched `null`; no default opt-in is introduced. Google signup retains its existing store-before-redirect and matching-email rules. Verification in a different browser/origin, blocked storage, or a mismatched email does not transfer pending consent; this change does not trust Auth user metadata as a fallback. If verification returns no session, consent stays pending for the existing authenticated profile-setup flow. These paths were validated with local mocked tests, not a live signup/database mutation.

### Forward RPC ambiguity fix (2026-09-24)

The applied claim function already has `p_`-prefixed inputs and qualified SELECT/WHERE references. PostgreSQL also creates variables for `RETURNS TABLE` output names. Those output variables collide with bare index-column names in `ON CONFLICT (user_id, email_type, recipient_email, session_id, idempotency_key)`, producing SQLSTATE 42702.

New migration: `20260924120000_fix_outbound_email_event_claim_ambiguous_user_id.sql`. It replaces only the RPC, adds function-local `#variable_conflict use_column` for the conflict target, and uses an explicit INSERT alias in RETURNING. It preserves the exact RPC argument/result contract, six-type allowlist, unique-index inference, atomic INSERT/duplicate row lock behavior, grants, and existing status/lease logic. Old migrations are unchanged. No table changes or CHECK validation are added; deferred validation remains maintenance work.

The migration is local and must be applied separately through the approved rollout process; this fix does not claim a successful remote claim or send. Local regression tests compare the complete function to the previous version (apart from the intended fix) and exercise event-service claims with fakes. PostgreSQL execution remains a rollout check because no local PostgreSQL runtime is available. Do not retry a live smoke send until the forward migration is applied and the prior event state is checked; retain the intended idempotency key. No email was sent during this fix.

Reference: [PostgreSQL PL/pgSQL variable substitution](https://www.postgresql.org/docs/current/plpgsql-implementation.html#PLPGSQL-VAR-SUBST).
