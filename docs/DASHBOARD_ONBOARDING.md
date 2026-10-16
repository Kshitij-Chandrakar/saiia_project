# Dashboard onboarding (local implementation)

Five steps: Welcome, Resume, Preparation context, Interview Session, Desktop Experience.

The approved migration remains local and unapplied. Deploy it before enabling the
new dashboard gate. Pause account creation and drain in-flight signup transactions
for the reviewed existing-account eligibility cutoff. Do not rerun its backfill.
Existing rows are preserved; missing settings rows are seeded from auth.users.
RLS is unchanged. Bootstrap inserts only user_id and retains step 1 / NULL defaults.

Authenticated API (identity comes only from verified bearer auth):
- GET /api/onboarding
- PATCH /api/onboarding/step with current_step (integer 1 through 5)
- POST /api/onboarding/complete

The backend uses the established private service-role REST architecture with an
explicit verified-user filter. Only onboarding fields are mutated. Completion is
conditional on NULL, so retries preserve the first completion timestamp. Completed
accounts cannot be reset by step updates. Missing schema/settings fail with a safe
503; they are never treated as completed or silently created by this read API.

Website /auth/dashboard and /auth/sessions are gated; /auth/onboarding is protected
by the existing RequireAuth boundary. Completed users continue to the dashboard.
Next/Back persist before updating the view. Skip exits the entire flow and Continue
to App completes it. Failed writes leave the current step available for retry.
Electron bypasses this website gate. Login/signup/callback security is unchanged.

Existing cloud resumes, jobs and sessions are loaded, never fabricated. Resume
upload uses the existing upload API and confirmation remains in Resumes. The API
limit is 5MB, despite the Figma's 10MB copy. Job document extraction requires
explicit provider-processing consent and preserves the extraction receipt for
server validation. Context/session creation occurs only on user action and uses
stable idempotency keys. Existing contexts/sessions are shown without overwriting.

Known product integration limits:
- No official published desktop download destination was found. The download
  action shows an unavailable notice; Continue to App remains functional.
- Job/session empty states replace Figma demo records to avoid invented user data.
- Live-call mock content on step 5 is an illustration, not real session data.

Verification uses synthetic auth/network mocks, not real accounts or remote SQL:
  cd frontend
  npx playwright test --config playwright.onboarding.config.js
  node --test --test-reporter=spec --test-reporter-destination=stdout src/*.test.js src/auth/*.test.js
  npm run build
  cd ..
  python -m pytest backend/tests/test_onboarding.py backend/tests/test_profile_bootstrap.py backend/tests/test_auth_routes.py -q

Screenshots: tmp/onboarding-five-screenshots (all five steps at all six requested widths).
Figma comparison: tmp/onboarding-five-figma-comparison.png. These are local QA artifacts,
not application assets. No remote migration or live-email authentication was tested.
