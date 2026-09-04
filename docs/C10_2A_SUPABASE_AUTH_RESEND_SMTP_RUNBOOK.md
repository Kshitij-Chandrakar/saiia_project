# C10.2A - Supabase Auth Emails Through Resend SMTP Runbook

## Status and boundary

**Completed/merged: runbook and controlled validation preparation.** This document does not configure Supabase, call Resend, send email, add secrets, or implement custom authentication logic. C10.2B live verification/reset delivery remains blocked until a verified Resend sender/domain and approved credentials are available.

This phase covers only:

- Supabase signup verification email through Resend SMTP
- Supabase password reset email through Resend SMTP
- fixed Supabase Auth redirect allowlists
- safe manual smoke testing and rollback

Supabase Auth generates secure links and owns resend, cooldown, and rate-limit behavior. Resend SMTP only delivers those messages. `outbound_email_events` is not used for Supabase Auth emails. C10.2 backend transactional email work is not part of this phase.

## 1. Resend setup checklist

Use an approved Resend account and a verified sender. Do not paste credentials into this file.

- [ ] Verify the sender or sending domain in Resend.
- [ ] Confirm the sender address is `<verified_sender_email>`.
- [ ] Configure SMTP host as `smtp.resend.com`.
- [ ] Configure SMTP port as `587` with authenticated STARTTLS/TLS.
- [ ] Configure SMTP username as `resend`.
- [ ] Configure SMTP password as `<RESEND_API_KEY - never commit>` using the secret input only.
- [ ] Confirm certificate validation is enabled and plaintext SMTP is unavailable.
- [ ] Test only with addresses owned by the team or mentor for the approved demo.
- [ ] Keep promotional email disabled for this phase.

Before any real demo email, verify the SMTP host, port, authentication, TLS mode, and certificate validation. Never put the SMTP password or API key in the repository, docs, tests, screenshots, tickets, or chat.

## 2. Supabase Auth SMTP setup checklist

Perform this only in the intended Supabase project and record configuration changes in an approved secure operations system, not in this repository.

- [ ] Open the Supabase Auth email/SMTP settings for the intended environment.
- [ ] Set the SMTP host to `smtp.resend.com`.
- [ ] Set the SMTP port to `587` and require authenticated STARTTLS/TLS.
- [ ] Set the SMTP username to `resend`.
- [ ] Enter the Resend credential through the dashboard secret field; do not copy it into notes or logs.
- [ ] Set the sender email to `<verified_sender_email>`.
- [ ] Confirm the sender name/reply-to values are approved and contain no secrets.
- [ ] Confirm Supabase Auth remains responsible for signup verification and password reset link generation.
- [ ] Use only Supabase-supported template variables such as `ConfirmationURL` and `RecoveryURL`; do not create custom token variables.
- [ ] Confirm auth email resend, cooldown, and rate-limit settings remain Supabase-owned.
- [ ] Confirm no `outbound_email_events` row is created for an Auth verification or reset email.

### Secure SMTP requirements

- Authenticated SMTP is mandatory.
- TLS/encryption and certificate validation are mandatory.
- Plaintext SMTP is prohibited.
- SMTP passwords and API keys must not appear in the repo, docs, tests, logs, or screenshots.

## 3. Redirect allowlist checklist

Redirect destinations are fixed per environment. User-supplied redirect destinations, wildcard destinations, and unapproved domains are rejected.

### Local development only

- [ ] Allow `http://localhost:5173/auth/callback`.
- [ ] Allow `http://localhost:5173/auth/reset-password`.
- [ ] Reject non-localhost HTTP destinations.
- [ ] Reject arbitrary ports, paths, query overrides, and user-provided redirect values.

### Staging and production later

- [ ] Use only fixed HTTPS routes under the approved environment domain.
- [ ] Production callback: `https://<approved-domain>/auth/callback`.
- [ ] Production reset: `https://<approved-domain>/auth/reset-password`.
- [ ] Reject HTTP, localhost, unapproved domains, wildcard patterns, and user-supplied destinations.
- [ ] Do not select or invent a production domain in this runbook.

The allowlist contains base application routes only. Generated Auth URLs may contain Supabase-required token query parameters and must be treated as sensitive. Never log, store, track, or share a full generated Auth URL.

## 4. Signup verification smoke test

Use a new test account owned by the team or mentor. Do not use a real user's account for setup testing.

- [ ] Confirm the local or approved environment is using the intended fixed callback allowlist.
- [ ] Sign up through the existing application flow.
- [ ] Confirm one verification email arrives from the verified sender.
- [ ] Open the message without copying or recording the full link.
- [ ] Follow the link and confirm the application reaches the fixed callback route.
- [ ] Confirm the account becomes verified through the normal Supabase Auth state.
- [ ] Confirm resend behavior, cooldown, and rate limits are controlled by Supabase Auth.
- [ ] Confirm no raw Auth URL, token, header, or email body was written to logs or telemetry.

Expected result: the verification flow succeeds through Supabase Auth and Resend SMTP without any custom token handling or `outbound_email_events` entry.

## 5. Password reset smoke test

Use a test account owned by the team or mentor.

- [ ] Request password reset through the existing application flow.
- [ ] Confirm one reset email arrives from the verified sender.
- [ ] Follow the link without copying or recording the full generated Auth URL.
- [ ] Confirm the application reaches the fixed reset route.
- [ ] Set a new password through the normal Supabase Auth reset flow.
- [ ] Confirm the new password can sign in.
- [ ] Confirm the old password no longer signs in, according to the normal Auth behavior.
- [ ] Confirm reset resend/cooldown/rate limits remain Supabase-owned.
- [ ] Confirm no raw Auth URL, token, header, or email body was written to logs or telemetry.

Expected result: password reset succeeds through Supabase Auth and Resend SMTP without custom reset tokens or `outbound_email_events` usage.

## 6. Redirect rejection tests

C10.2A validation must include both accepted and rejected destinations.

- [ ] Accepted local callback route reaches the fixed local callback path.
- [ ] Accepted local reset route reaches the fixed local reset path.
- [ ] Rejected user-supplied redirect is refused before an Auth link is issued or followed.
- [ ] Rejected unapproved domain is refused.
- [ ] Rejected HTTP staging/production destination is refused.
- [ ] Rejected wildcard or arbitrary port is refused.
- [ ] Production placeholder routes are not enabled until an approved HTTPS domain exists.

Do not paste rejected or generated token-bearing URLs into this document or test artifacts.

## 7. Rollback plan

Rollback must be performed by an authorized project operator using the secure provider dashboards.

- Stop the smoke test and disable the new SMTP configuration if delivery or redirect behavior is unsafe.
- Restore the previously approved Supabase Auth email provider/settings from the secure change record, if one exists.
- Keep the fixed redirect allowlist; do not broaden it as a rollback shortcut.
- Revoke or rotate the Resend credential if it was exposed or entered incorrectly.
- Confirm no real user or promotional email was sent during rollback.
- Re-run only the safe configuration and redirect checks after rollback.
- Record only safe status, timestamps, provider name, and error category in the change record.

No rollback credential, API key, SMTP password, or full Auth URL belongs in the repository.

## 8. Secrets and evidence handling

### Safe to share

- checklist completion status
- environment label such as local, staging, or production
- provider name and non-secret SMTP host/port
- masked sender address
- delivery success/failure category and timestamp
- screenshots with credentials, tokens, full Auth URLs, personal data, and message bodies cropped or redacted
- email client screenshots showing subject/sender only, without links or recipient details

### Never share

- Resend API keys or SMTP passwords
- Supabase keys, service-role keys, auth tokens, cookies, or headers
- full Supabase Auth URLs, including `ConfirmationURL` or `RecoveryURL` output
- reset/verification links copied from email
- raw email bodies containing Auth links
- recipient lists or unrelated personal data
- telemetry containing URLs, tokens, or message contents

Logs and screenshots must not include full Auth URLs, token query parameters, raw email bodies, or credentials. C10.2A uses no custom verification/reset tokens.

## Completion criteria

C10.2A runbook/documentation work is complete. C10.2B may be marked complete only after authorized manual verification proves signup verification and password reset delivery, redirect allowlist acceptance/rejection, authenticated encrypted SMTP, and safe evidence handling. Until then, keep C10.2B blocked/incomplete and keep `EMAIL_ENABLED`/`EMAIL_DRY_RUN` defaults unchanged.
