# C10.1 - Email System Planning and Safety Contract

## Status

**In progress: planning document created.** C10.1 is documentation-only. No email provider has been called, no SMTP has been configured, and no real email has been sent. C10.2 implementation has not started.

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
- intervuAI does not create custom verification or reset tokens.
- Resend only delivers the email through SMTP.
- Templates use Supabase-supported variables.
- Redirect URLs must be tested carefully in each environment.

### B. Backend Transactional Emails Through the Resend API

This category includes welcome emails after verified login/profile bootstrap, AI notes ready, session summary, transcript export, and account/security notifications.

- Sends are initiated only by the backend.
- User-action routes are authenticated and use `CurrentUserDep`.
- Session ownership is verified server-side.
- `user_id` is never trusted from a request body.
- Idempotency is scoped by `user_id`, `email_type`, `recipient_email`, nullable `session_id`, and `idempotency_key`.
- The planned unique index/constraint uses PostgreSQL `NULLS NOT DISTINCT` across `user_id`, `email_type`, `recipient_email`, `session_id`, and `idempotency_key`, so sessionless events are also unique. If that syntax is unavailable, equivalent partial unique indexes must separately cover `session_id IS NULL` and `session_id IS NOT NULL`.
- Before calling the provider, the backend atomically creates or claims an `outbound_email_events` row. This NULL-safe uniqueness rule prevents concurrent duplicate claims.
- Event status is one of `pending`, `sending`, `sent`, `failed`, `canceled`, `needs_reconciliation`, or `retry_blocked` as needed; only one active send attempt exists for a given idempotency scope.
- Reusing an idempotency key reuses the existing event state. A `sent` event returns its prior `provider_message_id` and status; a fresh `sending` claim returns a safe already-processing response; `pending` returns a safe retry/conflict response; `failed` may be retried only for an explicitly retryable failure or may require a new key.
- Provider success followed by a database update failure requires reconciliation rather than an automatic resend. A provider timeout or unknown result must not blindly resend. Provider idempotency support is used where available in addition to database uniqueness.
- Logs and any event records contain safe metadata only.

### Abandoned sending claims

- Each send attempt has a `claim_token` or `attempt_id`, plus `sending_started_at` and `lease_expires_at`. Only the holder of the active claim token may update that attempt.
- An expired `sending` lease is never reset blindly to `pending`. First reconcile provider state using the provider idempotency key, provider lookup, or delivery webhook when available.
- If the provider confirms sent, mark the event `sent`. If it confirms failed or not sent, claim a retry with a new token and retry safely. If provider state is unknown, mark the event `needs_reconciliation` or `retry_blocked` and defer to documented support/manual handling rather than risking a duplicate.
- A same-key request with an expired sending claim enters reconciliation. A retry may send only after the provider proves the message was not sent or provider idempotency guarantees deduplication.

The future C10.3 migration tests must prove duplicate prevention for both `session_id IS NULL` and a populated `session_id`, prove an expired sending claim is not retried blindly, and prove `claim_token` prevents stale attempt updates.

### C. Marketing and Promotional Emails

Discounts, product updates, launch offers, and plan-upgrade offers are not implemented in C10.1.

- Require explicit marketing opt-in.
- Require unsubscribe support.
- Remain separate from transactional email.
- Unsubscribing from marketing must not block auth or security emails.

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

The planned backend-owned table is `outbound_email_events`:

- `id`
- `user_id`
- `session_id` nullable
- `email_type`
- `recipient_email`
- `provider`
- `provider_message_id` nullable
- `idempotency_key`
- `claim_token` or `attempt_id`
- `sending_started_at` nullable
- `lease_expires_at` nullable
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

Future work may add `email_preferences` or `marketing_subscriptions` with:

- `user_id`
- `marketing_opt_in`
- `unsubscribed_at`
- `created_at`
- `updated_at`

Marketing opt-in is required before promotional sends. It is not required for auth or security emails.

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

- **C10.1 - Email plan and safety contract:** this document; no sending implementation.
- **C10.2 - Supabase Auth emails through Resend SMTP:** configure and test Auth delivery; not started.
- **C10.3 - Backend email config and dry-run provider:** add backend provider boundary and safe local default; not started.
- **C10.4 - Welcome email:** add the verified-login welcome flow; not started.
- **C10.5 - Session summary, transcript, and AI notes emails:** add explicit authenticated user actions; not started.
- **C10.6 - Marketing preferences and promotional emails later:** add consent and unsubscribe controls; not started.

## 10. Manual Demo Checklist

The later demo should show:

- signup verification email received
- password reset email received
- welcome email received
- dry-run mode disabled only for the demo
- no secrets committed
- logs showing safe email event metadata only

## Safety Boundary

C10.1 does not call Resend, configure Supabase SMTP, add real API keys, send emails, create custom verification/reset tokens, modify applied migrations, or implement promotional messaging. C9 remains merged/closed. C10.2 is not started.
