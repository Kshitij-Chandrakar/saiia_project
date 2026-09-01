from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
GRANTS_MIGRATION = MIGRATIONS_DIR / "20260801115446_grant_cloud_table_privileges.sql"
C3_2_MIGRATION = MIGRATIONS_DIR / "20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql"
C3_4_MIGRATION = MIGRATIONS_DIR / "20260804134140_add_cloud_resume_chunk_activation.sql"
C3_4_PARSING_FIX_MIGRATION = MIGRATIONS_DIR / "20260804151715_fix_cloud_resume_activation_profile_parsing.sql"
C3_4_PROFILE_PRESERVE_MIGRATION = MIGRATIONS_DIR / "20260804162315_preserve_profile_fields_on_cloud_resume_activation.sql"
C4_2_MIGRATION = MIGRATIONS_DIR / "20260809120000_add_cloud_job_context_lifecycle.sql"
C6_3_MIGRATION = MIGRATIONS_DIR / "20260828120000_add_interview_session_lifecycle.sql"
C6_3_RPC_FIX_MIGRATION = MIGRATIONS_DIR / "20260828153000_fix_interview_session_idempotency_rpc.sql"
C7_MIGRATION = MIGRATIONS_DIR / "20260829103000_add_interview_session_transcript_storage.sql"
C7_LOCKDOWN_MIGRATION = MIGRATIONS_DIR / "20260829170000_lock_down_transcript_entry_inserts.sql"
C8_MIGRATION = MIGRATIONS_DIR / "20260829223000_add_interview_session_ai_notes.sql"


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
    assert "drop index" not in sql
    assert "job_contexts_user_updated_id_idx" in sql


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
    signature = (
        "public.create_job_context_with_idempotency( "
        "uuid, text, text, text, text, text, jsonb, jsonb, text, jsonb, text, text, jsonb, boolean "
        ")"
    )

    assert "create table if not exists public.job_context_idempotency_keys" in sql
    assert "job_context_idempotency_user_key_idx" in sql
    assert "job_context_idempotency_expires_at_idx" in sql
    assert "alter table public.job_context_idempotency_keys enable row level security" in sql
    assert "alter table public.job_context_idempotency_keys force row level security" in sql
    assert "create or replace function public.create_job_context_with_idempotency" in sql
    assert "insert into public.job_context_idempotency_keys" in sql
    assert "insert into public.job_contexts" in sql
    assert "update public.job_context_idempotency_keys set status = 'completed'" in sql
    assert "if reservation.status = 'completed' and reservation.job_context_id is null then" in sql
    assert "status := 'gone'" in sql
    assert "request_hash" in sql
    assert "job_context_id uuid references public.job_contexts(id) on delete set null" in sql
    assert "job_description" not in table_sql
    assert "completed_response" not in table_sql
    assert f"revoke all on function {signature} from public" in sql
    assert f"revoke all on function {signature} from anon" in sql
    assert f"revoke all on function {signature} from authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c6_3_interview_session_migration_adds_table_rls_and_active_uniqueness() -> None:
    sql = " ".join(C6_3_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.interview_sessions" in sql
    assert "selected_resume_id uuid null references public.resumes(id) on delete set null" in sql
    assert "job_context_id uuid null references public.job_contexts(id) on delete set null" in sql
    assert "job_description_preview text null" in sql
    assert "constraint interview_sessions_status_check check (status in ('active', 'ended', 'abandoned'))" in sql
    assert "constraint interview_sessions_active_end_check check" in sql
    assert "create unique index if not exists interview_sessions_one_active_per_user_idx" in sql
    assert "where status = 'active' and ended_at is null" in sql
    assert "alter table public.interview_sessions enable row level security" in sql
    assert "create policy interview_sessions_select_own" in sql
    assert "create policy interview_sessions_insert_own" in sql
    assert "create policy interview_sessions_update_own" in sql
    assert "auth.uid() = user_id" in sql


def test_c6_3_interview_session_migration_keeps_idempotency_backend_only_and_preview_only() -> None:
    sql = " ".join(C6_3_MIGRATION.read_text(encoding="utf-8").lower().split())
    table_sql = sql.split("); create unique index if not exists interview_session_idempotency_user_key_idx", 1)[0]
    signature = "public.create_interview_session_with_idempotency( uuid, text, text, uuid, uuid, text, text, text, text )"

    assert "create table if not exists public.interview_session_idempotency_keys" in sql
    assert "interview_session_idempotency_user_key_idx" in sql
    assert "interview_session_idempotency_expires_at_idx" in sql
    assert "alter table public.interview_session_idempotency_keys enable row level security" in sql
    assert "create or replace function public.create_interview_session_with_idempotency" in sql
    assert "pg_advisory_xact_lock(lock_key)" in sql
    assert "selected resume was not found" in sql
    assert "job context was not found" in sql
    assert "set status = 'abandoned'" in sql
    assert "interval '2 minutes'" in sql
    assert "job_description_preview" in sql
    assert "job_description text" not in table_sql
    assert f"revoke all on function {signature} from public" in sql
    assert f"revoke all on function {signature} from anon" in sql
    assert f"revoke all on function {signature} from authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c6_3_followup_migration_fixes_ambiguous_status_reference_with_aliases() -> None:
    sql = " ".join(C6_3_RPC_FIX_MIGRATION.read_text(encoding="utf-8").lower().split())
    signature = "public.create_interview_session_with_idempotency( uuid, text, text, uuid, uuid, text, text, text, text )"

    assert "create or replace function public.create_interview_session_with_idempotency" in sql
    assert "from public.interview_session_idempotency_keys as k" in sql
    assert "where k.user_id = p_user_id and k.idempotency_key = p_idempotency_key" in sql
    assert "from public.interview_sessions as s where s.user_id = p_user_id and s.status = 'active' and s.ended_at is null" in sql
    assert "update public.interview_sessions as s set status = 'abandoned'" in sql
    assert "return query select reservation.interview_session_id, true, 'completed'::text" in sql
    assert "return query select existing_session.id, true, 'completed'::text" in sql
    assert "return query select created_session.id, false, 'completed'::text" in sql
    assert "raise exception 'interview session idempotency key conflict'" in sql
    assert "status := 'completed'" not in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c7_transcript_migration_adds_table_constraints_and_rls() -> None:
    sql = " ".join(C7_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.interview_session_transcript_entries" in sql
    assert "session_id uuid not null references public.interview_sessions(id) on delete cascade" in sql
    assert "request_id text null" in sql
    assert "turn_index integer not null" in sql
    assert "question_text text not null" in sql
    assert "answer_text text not null" in sql
    assert "metadata jsonb not null default '{}'::jsonb" in sql
    assert "constraint interview_session_transcript_turn_index_positive check (turn_index > 0)" in sql
    assert "constraint interview_session_transcript_metadata_object check (jsonb_typeof(metadata) = 'object')" in sql
    assert "create unique index if not exists interview_session_transcript_session_turn_idx" in sql
    assert "create unique index if not exists interview_session_transcript_session_request_idx" in sql
    assert "alter table public.interview_session_transcript_entries enable row level security" in sql
    assert "alter table public.interview_session_transcript_entries force row level security" in sql
    assert "create policy interview_session_transcript_select_own" in sql
    assert "create policy interview_session_transcript_insert_own" in sql


def test_c7_transcript_migration_keeps_rpc_backend_only_and_user_scoped() -> None:
    sql = " ".join(C7_MIGRATION.read_text(encoding="utf-8").lower().split())
    signature = (
        "public.create_interview_session_transcript_entry( "
        "uuid, uuid, text, text, text, text, text, text, text, integer, jsonb )"
    )

    assert "create or replace function public.create_interview_session_transcript_entry" in sql
    assert "where s.id = p_session_id and s.user_id = p_user_id" in sql
    assert "interval '5 minutes'" in sql
    assert "select max(e.turn_index)" in sql
    assert "where e.session_id = p_session_id" in sql
    assert "where e.session_id = p_session_id and e.request_id = p_request_id" in sql
    assert "raise exception 'interview session was not found'" in sql
    assert "raise exception 'interview session is closed'" in sql
    assert f"revoke all on function {signature} from public" in sql
    assert f"revoke all on function {signature} from anon" in sql
    assert f"revoke all on function {signature} from authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c7_transcript_lockdown_migration_removes_authenticated_direct_insert_path() -> None:
    sql = " ".join(C7_LOCKDOWN_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "revoke insert on table public.interview_session_transcript_entries from authenticated" in sql
    assert "drop policy if exists interview_session_transcript_insert_own on public.interview_session_transcript_entries" in sql
    assert "grant insert on table public.interview_session_transcript_entries to authenticated" not in sql
    assert "create policy interview_session_transcript_insert_own" not in sql


def test_c8_ai_notes_migration_adds_table_constraints_and_rls() -> None:
    sql = " ".join(C8_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.interview_session_ai_notes" in sql
    assert "session_id uuid not null references public.interview_sessions(id) on delete cascade" in sql
    assert "notes_markdown text not null" in sql
    assert "strengths jsonb not null default '[]'::jsonb" in sql
    assert "improvement_areas jsonb not null default '[]'::jsonb" in sql
    assert "technical_topics jsonb not null default '[]'::jsonb" in sql
    assert "key_questions jsonb not null default '[]'::jsonb" in sql
    assert "suggested_followups jsonb not null default '[]'::jsonb" in sql
    assert "transcript_entry_count integer not null default 0" in sql
    assert "constraint interview_session_ai_notes_status_check check (status in ('ready', 'failed'))" in sql
    assert "constraint interview_session_ai_notes_markdown_length check (char_length(notes_markdown) between 1 and 24000)" in sql
    assert "create unique index if not exists interview_session_ai_notes_session_idx" in sql
    assert "alter table public.interview_session_ai_notes enable row level security" in sql
    assert "alter table public.interview_session_ai_notes force row level security" in sql
    assert "create policy interview_session_ai_notes_select_own" in sql


def test_c8_ai_notes_migration_keeps_authenticated_writes_backend_only() -> None:
    sql = " ".join(C8_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "grant select on table public.interview_session_ai_notes to authenticated" in sql
    assert "grant select, insert, update, delete on table public.interview_session_ai_notes to service_role" in sql
    assert "grant insert on table public.interview_session_ai_notes to authenticated" not in sql
    assert "grant update on table public.interview_session_ai_notes to authenticated" not in sql
    assert "create policy interview_session_ai_notes_insert_own" not in sql
    assert "create policy interview_session_ai_notes_update_own" not in sql
