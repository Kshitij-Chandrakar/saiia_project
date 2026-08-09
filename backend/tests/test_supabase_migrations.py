from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
GRANTS_MIGRATION = MIGRATIONS_DIR / "20260801115446_grant_cloud_table_privileges.sql"
C3_2_MIGRATION = MIGRATIONS_DIR / "20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql"
C3_4_MIGRATION = MIGRATIONS_DIR / "20260804134140_add_cloud_resume_chunk_activation.sql"
C3_4_PARSING_FIX_MIGRATION = MIGRATIONS_DIR / "20260804151715_fix_cloud_resume_activation_profile_parsing.sql"
C3_4_PROFILE_PRESERVE_MIGRATION = MIGRATIONS_DIR / "20260804162315_preserve_profile_fields_on_cloud_resume_activation.sql"
C4_2_MIGRATION = MIGRATIONS_DIR / "20260809120000_add_cloud_job_context_lifecycle.sql"


def _normalized_sql() -> str:
    return " ".join(GRANTS_MIGRATION.read_text(encoding="utf-8").lower().split())


def test_c2_3_privilege_migration_grants_required_roles_and_tables() -> None:
    sql = _normalized_sql()

    assert "grant usage on schema public to authenticated, service_role" in sql
    assert "grant select, insert, update, delete on table" in sql
    assert "to authenticated, service_role" in sql

    for table in (
        "public.profiles",
        "public.user_settings",
        "public.resumes",
        "public.resume_chunks",
        "public.job_contexts",
    ):
        assert table in sql


def test_c2_3_privilege_migration_does_not_grant_anon_or_change_rls() -> None:
    sql = _normalized_sql()

    assert " to anon" not in sql
    assert "anon," not in sql
    assert "disable row level security" not in sql
    assert "drop policy" not in sql
    assert "create policy" not in sql


def test_c3_2_resume_lifecycle_migration_adds_required_state_contract() -> None:
    sql = " ".join(C3_2_MIGRATION.read_text(encoding="utf-8").lower().split())

    for column in (
        "status",
        "is_active",
        "confirmed_at",
        "extraction_attempt",
        "confirmed_profile",
        "active_chunk_generation",
        "failure_code",
        "failure_message",
        "failed_at",
        "last_error_at",
    ):
        assert f"add column if not exists {column}" in sql

    assert "resumes_status_check" in sql
    assert "resumes_active_ready_check" in sql
    assert "check (is_active = false or status = 'ready')" in sql
    assert "create unique index resumes_one_active_per_user_idx on public.resumes (user_id) where is_active = true" in sql

    for status in (
        "uploaded",
        "extracting",
        "needs_review",
        "indexing",
        "ready",
        "failed",
        "timeout",
        "cancelled",
        "deleted",
    ):
        assert f"'{status}'" in sql


def test_c3_2_resume_lifecycle_migration_hardens_direct_authenticated_writes() -> None:
    sql = " ".join(C3_2_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "revoke insert, update, delete on table public.profiles, public.resumes, public.resume_chunks from authenticated" in sql
    assert "grant select, insert, update, delete on table public.profiles, public.resumes, public.resume_chunks to service_role" in sql
    assert "drop policy if exists resumes_insert_own" in sql
    assert "drop policy if exists resume_chunks_insert_own" in sql
    assert "drop policy if exists profiles_update_own" in sql
    assert "drop policy if exists saiia_storage_insert_own on storage.objects" in sql
    assert "drop policy if exists saiia_exports_storage_insert_own on storage.objects" in sql
    assert "drop policy if exists saiia_exports_storage_update_own on storage.objects" in sql
    assert "drop policy if exists saiia_exports_storage_delete_own on storage.objects" in sql
    assert "bucket_id = 'exports'" in sql
    assert " to anon" not in sql
    assert "disable row level security" not in sql


def test_c3_4_migration_adds_chunk_generation_and_activation_rpc() -> None:
    sql = " ".join(C3_4_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "add column if not exists generation_id uuid" in sql
    assert "alter column generation_id set not null" in sql
    assert "create index if not exists resume_chunks_user_resume_generation_idx" in sql
    assert "create index if not exists resumes_active_generation_idx" in sql
    assert "create or replace function public.activate_cloud_resume" in sql
    assert "status = 'indexing'" in sql
    assert "status = 'ready'" in sql
    assert "is_active = true" in sql
    assert "active_chunk_generation = p_generation_id" in sql
    assert "on conflict (user_id) do update" in sql
    assert "revoke all on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) from authenticated" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to service_role" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to anon" not in sql


def test_c3_4_followup_migration_preserves_prose_commas_and_skill_lists() -> None:
    sql = " ".join(C3_4_PARSING_FIX_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.saiia_text_to_jsonb_lines(value text)" in sql
    assert "regexp_split_to_array(coalesce(value, ''), e'\\\\n')" in sql
    assert "regexp_split_to_array(coalesce(value, ''), e'\\\\n|,')" not in sql

    for field in ("top_skills", "technical_skills", "tools_frameworks"):
        assert f"public.saiia_text_to_jsonb_array(coalesce(p_profile->>'{field}'" in sql
    assert "public.saiia_text_to_jsonb_array(coalesce(p_profile->>'top_skills', p_profile->>'skills', ''))" in sql

    for field in ("soft_skills", "education", "projects", "achievements", "certifications"):
        assert f"public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'{field}'" in sql
    assert "public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'experience', p_profile->>'work_experience', ''))" in sql


def test_c3_4_followup_migration_keeps_activation_rpc_backend_only() -> None:
    sql = " ".join(C3_4_PARSING_FIX_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.activate_cloud_resume" in sql
    assert "status = 'indexing'" in sql
    assert "status = 'ready'" in sql
    assert "is_active = true" in sql
    assert "active_chunk_generation = p_generation_id" in sql
    assert "on conflict (user_id) do update" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to service_role" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to anon" not in sql


def test_c3_4_profile_preserve_migration_keeps_omitted_profile_columns() -> None:
    sql = " ".join(C3_4_PROFILE_PRESERVE_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.activate_cloud_resume" in sql
    for column in (
        "full_name",
        "headline",
        "summary",
        "skills",
        "technical_skills",
        "soft_skills",
        "education",
        "experience",
        "projects",
        "achievements",
        "certifications",
        "tools_frameworks",
    ):
        assert f"else profiles.{column}" in sql

    assert "when p_profile ? 'full_name' then excluded.full_name" in sql
    assert "when p_profile ? 'professional_summary' then excluded.summary" in sql
    assert "when p_profile ? 'current_title' or p_profile ? 'target_role' then excluded.headline" in sql
    assert "when p_profile ? 'top_skills' or p_profile ? 'skills' then excluded.skills" in sql
    assert "when p_profile ? 'education' or p_profile ? 'degree' then excluded.education" in sql
    assert "when p_profile ? 'experience' or p_profile ? 'work_experience' then excluded.experience" in sql


def test_c3_4_profile_preserve_migration_parses_soft_skills_as_skill_list() -> None:
    sql = " ".join(C3_4_PROFILE_PRESERVE_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "public.saiia_text_to_jsonb_array(coalesce(p_profile->>'soft_skills', ''))" in sql
    for field in ("top_skills", "technical_skills", "tools_frameworks"):
        assert f"public.saiia_text_to_jsonb_array(coalesce(p_profile->>'{field}'" in sql
    for field in ("education", "projects", "achievements", "certifications"):
        assert f"public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'{field}'" in sql
    assert "public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'experience', p_profile->>'work_experience', ''))" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to service_role" in sql
    assert "grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to anon" not in sql


def test_c4_2_job_context_migration_adds_required_fields_and_defaults() -> None:
    sql = " ".join(C4_2_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "add column if not exists location text not null default ''" in sql
    assert "add column if not exists employment_type text not null default ''" in sql
    assert "add column if not exists source_file_metadata jsonb not null default '{}'::jsonb" in sql
    assert "alter column is_active set default false" in sql
    assert "job_contexts_source_file_metadata_object" in sql
    assert "check (jsonb_typeof(source_file_metadata) = 'object')" in sql
    assert "job_contexts_one_active_per_user_idx" not in sql or "drop index" not in sql


def test_c4_2_job_context_migration_hardens_authenticated_writes() -> None:
    sql = " ".join(C4_2_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "revoke insert, update, delete on table public.job_contexts from authenticated" in sql
    assert "grant select on table public.job_contexts to authenticated" in sql
    assert "grant select, insert, update, delete on table public.job_contexts to service_role" in sql
    assert "disable row level security" not in sql
    assert " to anon" not in sql


def test_c4_2_activation_rpc_is_service_role_only_and_owned() -> None:
    sql = " ".join(C4_2_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.activate_job_context" in sql
    assert "set local lock_timeout = '2s'" in sql
    assert "set local statement_timeout = '5s'" in sql
    assert "hashtextextended(p_user_id::text, 0)" in sql
    assert "pg_advisory_xact_lock(lock_key)" in sql
    assert "where id = p_job_context_id and user_id = p_user_id" in sql
    assert "where user_id = p_user_id and is_active = true and id <> p_job_context_id" in sql
    assert "revoke all on function public.activate_job_context(uuid, uuid) from public" in sql
    assert "revoke all on function public.activate_job_context(uuid, uuid) from anon" in sql
    assert "revoke all on function public.activate_job_context(uuid, uuid) from authenticated" in sql
    assert "grant execute on function public.activate_job_context(uuid, uuid) to service_role" in sql
    assert "grant execute on function public.activate_job_context(uuid, uuid) to anon" not in sql


def test_c4_2_idempotent_create_rpc_is_atomic_and_safe() -> None:
    sql = " ".join(C4_2_MIGRATION.read_text(encoding="utf-8").lower().split())
    table_sql = sql.split("); create unique index if not exists job_context_idempotency_user_key_idx", 1)[0]

    assert "create table if not exists public.job_context_idempotency_keys" in sql
    assert "job_context_idempotency_user_key_idx" in sql
    assert "create or replace function public.create_job_context_with_idempotency" in sql
    assert "insert into public.job_context_idempotency_keys" in sql
    assert "insert into public.job_contexts" in sql
    assert "update public.job_context_idempotency_keys set status = 'completed'" in sql
    assert "request_hash" in sql
    assert "job_context_id uuid references public.job_contexts(id) on delete set null" in sql
    assert "job_description" not in table_sql
    assert "completed_response" not in table_sql
    assert "revoke all on function public.create_job_context_with_idempotency" in sql
    assert "from authenticated" in sql
    assert "to service_role" in sql
