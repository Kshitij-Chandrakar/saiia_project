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
- Idempotency keys prevent duplicate sends.
- Logs and any event records contain safe metadata only.

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
- `status`
- `error_code` nullable
- `metadata_json` containing safe metadata only
- `created_at`
- `updated_at`

Backend-only insert/update is preferred. A future user-owned safe-metadata select may be added if needed. Frontend direct writes are not allowed. No event log may contain raw transcript, resume text/chunks, prompts, tokens, headers, or secrets.

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
