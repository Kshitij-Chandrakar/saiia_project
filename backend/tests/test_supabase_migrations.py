from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
GRANTS_MIGRATION = MIGRATIONS_DIR / "20260801115446_grant_cloud_table_privileges.sql"


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
