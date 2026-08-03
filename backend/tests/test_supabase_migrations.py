from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
GRANTS_MIGRATION = MIGRATIONS_DIR / "20260801115446_grant_cloud_table_privileges.sql"
C3_2_MIGRATION = MIGRATIONS_DIR / "20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql"


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
    assert "bucket_id = 'exports'" in sql
    assert " to anon" not in sql
    assert "disable row level security" not in sql
