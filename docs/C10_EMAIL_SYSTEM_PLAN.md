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

The local-only migration is `supabase/migrations/20260904170000_add_signup_consent_preferences.sql`; it has not been applied to remote Supabase. The no-consent legacy profile bootstrap remains compatible with the pre-migration schema, but consent-bearing bootstrap is intentionally migration-dependent: apply this migration to the target database before running C10.6A signup/bootstrap code against any remote Supabase project. If the new columns are absent, the consent write must fail safely rather than drop consent fields or report persistence success. The authenticated profile-bootstrap path writes these fields using the verified JWT user identity. Signup requires Terms and Privacy acceptance, while marketing opt-in is explicit and defaults to false. The signup links currently use safe `/terms` and `/privacy` placeholders; real legal pages must be supplied before release.

C10.6B adds a local-only, backend-owned unsubscribe foundation. The migration `supabase/migrations/20260905103000_add_marketing_unsubscribe_tokens.sql` must run after the C10.6A consent migration and is not applied to remote Supabase in this phase.

- Secure opaque tokens are generated with the standard cryptographic random source; only a SHA-256 hash is stored.
- Each token is scoped to its server-provided `user_id`, `recipient_email`, and the fixed `marketing` category, with `created_at`, `expires_at`, `used_at`, and `revoked_at` state.
- Creation is service-role-only. The consume operation looks up the hash, rejects expired/used/revoked/invalid tokens without exposing account data, sets `marketing_email_opt_in` false, records `marketing_email_opt_out_at`, and marks the token used atomically.
- The marketing guard reads only the authenticated user's preference. Opting out never blocks auth, account-security, welcome, or other transactional email.
- Raw tokens are returned only from token creation for future link construction; they are never stored or logged. Full unsubscribe URLs, tokens, prompts, transcript/resume content, headers, and secrets are excluded from logs and metadata.
- Frontend/client direct token-table writes are prohibited. A public unauthenticated unsubscribe endpoint and link construction are deferred to a later C10.6C subphase; promotional sending is not implemented.

Marketing email is allowed only when `marketing_email_opt_in` is true. C10.6B token/opt-out behavior is complete locally, while public link integration and promotional delivery remain deferred.

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
- **C10.6C - Public unsubscribe link endpoint and promotional integration:** not started; public token-link handling and promotional delivery remain deferred.
- **C10.6 - Marketing preferences and promotional emails:** incomplete; C10.6A and the C10.6B opt-out foundation are complete locally, while public link integration, unsubscribe endpoint work, and promotional delivery remain deferred.

## 10. Manual Demo Checklist

The later demo should show:

- signup verification email received
- password reset email received
- welcome email received
- dry-run mode disabled only for the demo
- no secrets committed
- logs showing safe email event metadata only

## Safety Boundary

C10.1, C10.3A, C10.3B, C10.3C, C10.3D, C10.4A, C10.4B, C10.5A/B, and C10.6A do not call Resend, configure Supabase SMTP, add real API keys, send emails, create custom verification/reset tokens, modify applied migrations, or implement promotional messaging. C9 remains merged/closed. C10.2A runbook/setup documentation is completed/merged, but C10.2B live verification/reset delivery is blocked pending a verified Resend sender/domain, so C10.2 delivery is not complete. C10.3A is completed locally with disabled/offline dry-run defaults. C10.3B adds the backend-owned `outbound_email_events` migration and event-store boundary, and C10.3D records its successful remote dev apply and post-apply validation. C10.3C connects the event store to the dry-run provider only. C10.4A adds the service-level welcome template and C10.4B wires it after authenticated profile bootstrap; C10.5A adds feature templates/helpers and C10.5B wires available notes-generation and transcript-export success points only. C10.6A adds only signup consent/preference capture and local schema groundwork; C10.6B unsubscribe and promotional delivery are not started. These paths remain dry-run-only and non-blocking, with no session-summary trigger because no preparation flow exists. Full C10.3/C10.5/C10.6 and real C10.4/C10.5 delivery remain incomplete because real delivery is not enabled.
