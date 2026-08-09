# C4.2 Live Supabase Smoke Validation

Artifact commit: this PR commit / PR #17.

## Scope

- Project: `saiia-dev` / `rbmxfazjbldmkomdpyzl`
- Date: 2026-08-09
- Shell used: PowerShell from the repository root
- Validation method: inline Python smoke using `.env`, Supabase REST/Auth/Admin APIs, and FastAPI `TestClient`
- Data handling: sanitized assertion results only

## Redaction Boundary

This artifact intentionally does not contain:

- Supabase service-role key
- JWTs or access tokens
- passwords
- raw resume text
- raw job-description text
- private user data

## Validation Outcomes

All listed checks passed against the linked `saiia-dev` project:

- Migration-visible `job_contexts` columns exist: `location`, `employment_type`, `source_file_metadata`
- `job_contexts.is_active` defaults to `false` when omitted
- `job_context_idempotency_keys` exists
- `job_context_idempotency_keys` RLS blocks anon reads
- `job_context_idempotency_keys` RLS blocks authenticated reads
- `activate_job_context` RPC blocks anon execution
- `activate_job_context` RPC blocks authenticated execution
- `activate_job_context` RPC is executable through the service-role backend path
- `create_job_context_with_idempotency` RPC blocks anon execution
- `create_job_context_with_idempotency` RPC blocks authenticated execution
- Service-role RPC/FastAPI create path works through authenticated backend create
- Direct authenticated `INSERT` on `job_contexts` is blocked
- Direct authenticated `UPDATE` on `job_contexts` is blocked
- Direct authenticated `DELETE` on `job_contexts` is blocked
- Authenticated FastAPI create/list/detail/patch/activate/delete lifecycle passed
- Deleting the active context leaves a valid no-context state
- List responses exclude full raw job-description text and return preview-only fields
- Detail responses return full raw job-description text only for the owning authenticated user
- Cross-user detail access is blocked
- Cross-user activation is blocked without mutating another user's context
- Extraction rejects missing provider-processing consent before provider work
- Extraction rejects requests that provide both file upload and `job_description_text`

## Commands Recorded

- `git status --short --branch`
- `rg -n "C4\\.2|live Supabase|live smoke|Current active phase|Current Next Action|job-context" SAIIA_CLOUD_PRODUCT_IMPLEMENTATION_ROADMAP.md SAIIA_PRODUCTION_PHASES_TRACKER.md docs/C4_CLOUD_JOB_CONTEXT_PLAN.md`
- PowerShell inline Python live smoke from repository root using `.env`, Supabase REST/Auth/Admin APIs, and FastAPI `TestClient`
- PowerShell inline Python `is_active` default check using a service-role insert with `is_active` omitted, readback, and cleanup

The inline Python scripts were intentionally not copied into this artifact because they necessarily referenced live environment variables and generated temporary credentials at runtime. The stored record is limited to sanitized validation method and assertion outcomes.
