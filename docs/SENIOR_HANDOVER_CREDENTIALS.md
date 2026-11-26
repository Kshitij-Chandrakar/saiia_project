# Intervucopilot: credentials and configuration handoff

This guide is for a senior developer reviewing or running the project on their own machine. It contains configuration names only, never working credentials. The README is unchanged.

## 1. Choose what to test first

| Goal | Credentials needed |
| --- | --- |
| Read code, build the frontend, run offline unit tests | No real provider credentials. Install the documented development/test dependencies. Native/browser tests have additional local runtime requirements. |
| Test the website with login and saved cloud data | An isolated Supabase environment, its browser-safe URL/key, and backend authentication configuration. |
| Generate answers or parse resumes with a hosted model | A key for each provider actually selected by configuration; not every provider listed below. |
| Transcribe microphone/system audio | Keys for the selected transcription paths, or a configured supported local fallback. |
| Test privacy/admin end to end | The isolated Auth/database/Storage/mail setup, restricted runtime principals, workers and restore/checkpoint services. API keys alone are insufficient. |
| Test billing or delivery | Fake payment boundaries and local mail capture first. Real test-provider activity requires separate authorization. |

Use synthetic accounts and files. Do not connect to the existing hosted/shared project merely because its configuration is available. Agree with the project owner whether to use a new isolated environment or approved access to an existing test environment.

## 2. Where configuration belongs

- **Backend:** start with the repository-root [.env.example](../.env.example), creating a private local `.env`. Start the backend from the repository root so dotenv discovery is predictable. Review the template before filling it; it is not a production activation profile.
- **Website:** place browser-safe `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `frontend/.env.local`. Restart Vite after configuration changes. See [the browser client](../frontend/src/auth/supabaseClient.js).
- **Desktop:** use the existing Electron environment handling and documented setup. Do not expose server credentials through Electron renderer configuration.
- **Deployment:** use the approved secret manager/runtime configuration. Do not upload secrets to GitHub, commit them, paste them into issues/chat, or include them in screenshots.

Never put a service-role key, database password, provider API key, signing secret or encryption key in a `VITE_*` variable. Vite variables are visible in the browser bundle. A Supabase anon key is browser-safe only with the intended database/Storage authorization in place.

## 3. Credentials for selected features

The senior should obtain credentials from their own authorized provider accounts or receive scoped access through the owner's secure handoff process. They should not reuse personal developer credentials copied from a laptop.

| Feature | Configuration | What to provide and where |
| --- | --- | --- |
| Supabase identity/cloud data | `SUPABASE_URL`, `SUPABASE_ANON_KEY`; matching frontend `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | URL and browser-safe anon key for the intended isolated project. Frontend/backend must target the same environment. |
| Backend JWT verification | `SUPABASE_JWT_SECRET_OR_JWKS_CONFIG` | The supported verifier configuration for that Auth environment. A signing secret, if used, stays server-side. Follow the existing Auth contract; do not substitute an unrelated API key. |
| Privileged Supabase operations | `SUPABASE_SERVICE_ROLE_KEY` | Only where the reviewed server adapter requires it. Server-side only; not a general substitute for restricted SQL identities or an automatic requirement for code review. |
| OpenAI answers, selected parsing/STT paths | `OPENAI_API_KEY` | An authorized OpenAI project API key, only if an OpenAI path is selected. A ChatGPT login/password is not this credential. |
| Groq answers, manual STT or vision | `GROQ_API_KEY` | An authorized Groq API key for selected Groq paths. |
| Gemini generation | `GEMINI_API_KEY` | Required only when a Gemini model/path is selected. |
| OpenRouter vision | `OPENROUTER_API_KEY` | Required only when the OpenRouter path is selected. |
| AssemblyAI transcription | `ASSEMBLYAI_API_KEY` | Required for selected AssemblyAI batch/streaming paths. |
| Optional Affinda resume parser | `AFFINDA_API_KEY`, `AFFINDA_WORKSPACE`, `AFFINDA_DOCUMENT_TYPE` | Parser credentials and workspace/document-type identifiers. `AFFINDA_COLLECTION` is the existing compatibility setting. Affinda is not required for every parsing configuration. |
| Optional local models | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, local Whisper/ffmpeg settings | Local software/model configuration, not hosted API credentials. Local fallback must be explicitly configured and available. |
| Application email | `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO` | No real key needed for dry-run/fake delivery. Real sending requires authorized credentials and a verified sender; adding a key does not authorize sending. See [email configuration](../backend/app/email/config.py). |
| Google sign-in | Google OAuth client ID and client secret | Configure through the intended Supabase Auth provider setup, with matching redirect URLs. These are not application passwords or browser environment secrets. Synthetic Google metadata does not verify real Google OAuth. |

The provider selectors, models and limits are configuration, not credentials. Check [backend settings](../backend/app/config.py) and `.env.example` together; the template is not the complete privacy/admin runtime configuration.

## 4. Extra requirements for privacy and administration

Follow the [C15/C15.5 production enablement guide](C15_C15_5_PRODUCTION_ENABLEMENT_GUIDE.md), which separates local testing from shared-project/production activation.

The handoff must cover:

- Restricted database connection strings and verified TLS configuration for each required responsibility. Examples include `C15_RUNTIME_DSNS` and the separate `ADMIN_CONSOLE_DSN`, `ADMIN_RETENTION_DSN`, `ADMIN_DISPATCH_DSN` and `ADMIN_RESTORE_DSN` settings. These contain secrets and stay server-side.
- The reviewed Auth-hook authentication, permanent-suppression key material, revocation encryption/key references, and desktop handoff encryption configuration where used. Obtain exact formats from the current implementation and enablement guide, not invented placeholder keys.
- Independent journal/witness access and restore/checkpoint configuration, including key recovery. Do not regenerate established suppression or encryption keys casually: doing so can break existing suppression or recovery.
- Synthetic customer, Admin and Super-admin identities with verified immutable account IDs. Membership is database-backed; account email/profile metadata alone grants no role.
- An authenticator app for a staff account's enrolled TOTP factor where recent verification is required. The app generates the current code; there is no shared permanent admin code to hand over. Never commit enrollment seeds or recovery codes.
- Mail capture and fake payment endpoints, plus the existing application and worker startup wiring.

Production activation remains gated. Do not enable privacy/admin flags simply to make a page load, run migrations against an existing project as routine setup, or use owner/service-role SQL connections to bypass runtime permission failures. Emergency administrator recovery remains unavailable until its designated people and procedure are configured and tested.

## 5. Billing is not part of a basic review setup

Keep billing/provider execution disabled for ordinary review. If a separately authorized Razorpay Test Mode rehearsal is required, the existing runner uses `RAZORPAY_TEST_KEY_ID`, `RAZORPAY_TEST_KEY_SECRET`, `RAZORPAY_TEST_ACCOUNT_ID` and `RAZORPAY_TEST_WEBHOOK_SECRET`. Enter these through its documented secure process, not frontend configuration. Do not supply live payment credentials or repeat historical sessions/budgets.

Real delivery callbacks have their own webhook credentials and acceptance scope. Supabase Auth SMTP is configured separately from application email; a Resend API key in the backend does not configure Auth SMTP automatically. Use local capture during isolated acceptance.

## 6. What to hand over

- The GitHub repository's reviewed `main` branch and this guide.
- The [README](../README.md), [tracker](../SAIIA_PRODUCTION_PHASES_TRACKER.md), and linked implementation/enablement reports.
- A non-secret environment inventory: intended project, service URLs/ports, enabled test features and remaining acceptance gates.
- Securely provisioned access only when needed, with least privilege and a clear owner. Prefer individual access over shared passwords.

Do **not** send the entire working folder, `.env` files, provider keys, database passwords, Auth sessions, private backups, private execution records or Windows caches. The 64 excluded local files are not a credential bundle and should not be pushed for handoff. Share any specifically needed private record separately after reviewing and redacting it.

## First-run checklist

- [ ] Confirm the intended isolated environment before entering any credential.
- [ ] Start with code review/build/offline tests; leave unnecessary integrations disabled.
- [ ] Configure only the providers needed for the chosen test.
- [ ] Verify frontend/backend/Auth/Storage all point to the intended environment.
- [ ] Capture email locally and use fake payments for local acceptance.
- [ ] Use synthetic data and the reviewed restricted principals/workers for full privacy/admin testing.
- [ ] Record remaining gates honestly; a successful login or green CI is not production activation approval.
