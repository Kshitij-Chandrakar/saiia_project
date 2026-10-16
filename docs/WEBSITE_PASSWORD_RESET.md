# Website password-reset dialogs

The website keeps the login page behind native modal dialogs. Forgot Password and `/auth/forgot-password` open the request stage. The accepted request opens a non-enumerating confirmation with a masked email. A fresh `/auth/confirm?token_hash=…&type=recovery` link is verified through Supabase `verifyOtp` before the new-password form is enabled. Successful `updateUser` and local recovery-session sign-out precede the success stage.

## Recovery boundary

The isolated Supabase client does not persist sessions, auto-refresh, or consume URL fragments. Verification is single-flight, requires a fresh recovery token hash and a server-verified user, and strips URL parameters before the network operation. Updating rechecks that authenticated identity; no client-supplied account ID or email targets the update. Ordinary sessions and client-controlled URL flags cannot enable recovery. Signup confirmation and Electron retain their existing flow.

No recovery tokens, passwords, emails, or user IDs are written to application storage. The normal Supabase client skips URL session adoption on website recovery entries. Refreshing after URL cleanup requires a fresh link rather than persisting the token. Cancelling a verified recovery signs out only the isolated recovery session (`scope: local`); it does not revoke unrelated sessions. An in-flight update cannot be dismissed as cancelled. Fetches have a 15-second deadline and uncertain updates do not display success.

## Email template and deployment checks

The project owner confirmed that both active Reset Password template links use the token-hash `/auth/confirm` format. Keep both CTA and fallback expressions as:

```
{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery
```

Verify **Authentication → URL Configuration → Site URL** points to the intended website origin and that the website reset redirect is allowed. The repository cannot establish the remote Site URL. The owner confirmed the allowlist includes `http://localhost:5173/auth/callback`, `http://localhost:5173/auth/reset-password`, and `saiia://auth/callback`; these entries do not establish Site URL. Site URL confirmation remains an outstanding live-email compatibility check. Mocked Playwright uses 127.0.0.1 and does not send email. Requests construct `/auth/reset-password` on the current website origin; no localhost URL is hard-coded in the website flow. Legacy implicit session fragments deliberately do not enable the password form. Do not alter signup templates, OAuth/PKCE, or remote settings as part of this change.

## Rate limits and password policy

Supabase Auth `/recover` is the only upstream send/resend boundary, so its provider-side rate limits apply to both actions. A shared pending guard and 60-second deadline are additional UX controls, not production rate-limit enforcement. The 60-second UX default follows Supabase's documented per-user recovery-email default. Provider 429 and Retry-After extend this deadline (up to 24 hours); no automatic email retries occur. Browser storage contains only the numeric deadline, which survives closing and reopening the modal.

Actual remote limits, custom SMTP configuration, password policy, and link expiry were not available through read-only tools. Before deployment, inspect Authentication → Rate Limits and Password Security. Confirm email-send protections remain enabled and appropriate for the deployment; test provider enforcement in an isolated environment without sending real user emails. No remote settings were changed. The helper retains the project's six-character frontend minimum and states that the account policy also applies; Supabase remains authoritative and weak-password errors are actionable. No unverified 15-minute expiry or encryption claim is displayed.

Automated tests mock provider verification, requests, password updates, and cleanup. A real Supabase SDK test uses a mocked `/recover` 429 response and proves Retry-After suppresses another application upstream send. This checks SDK/UX wiring, **not live Supabase server enforcement**. No custom server limiter or unprotected alternative send endpoint is added.

## Local verification

From `frontend`:

```
node --test --test-reporter=spec --test-reporter-destination=stdout src/*.test.js src/auth/*.test.js
node node_modules/@playwright/test/cli.js test --config playwright.password-reset.config.js
node node_modules/@playwright/test/cli.js test --config playwright.signup.config.js
npm run build
npm run lint
```

Password-reset screenshots are under `tmp/password-reset/`: request, sent, new password, success, loading, and unavailable-link error at 1440×900, 1366×768, 1280×720, 390×844, and 360×800. Closed-login checks compare actual before/after screenshots at desktop and mobile widths. Tests never send real emails or update real passwords; trace/video recording is disabled for recovery tests.
