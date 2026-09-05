from pathlib import Path
import re


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
C9_MIGRATION = MIGRATIONS_DIR / "20260901103000_add_interview_session_ask_ai_messages.sql"
C9_IDEMPOTENCY_MIGRATION = MIGRATIONS_DIR / "20260901123000_add_ask_ai_request_idempotency_keys.sql"
C9_IDEMPOTENCY_TRIGGER_MIGRATION = (
    MIGRATIONS_DIR / "20260901170000_add_ask_ai_request_key_updated_at_trigger.sql"
)
C9_ATOMIC_TURN_MIGRATION = MIGRATIONS_DIR / "20260902120000_add_ask_ai_atomic_turn_persistence.sql"
C9_INDEX_CLEANUP_MIGRATION = MIGRATIONS_DIR / "20260902130000_drop_redundant_ask_ai_message_index.sql"
C10_3B_MIGRATION = MIGRATIONS_DIR / "20260904143000_add_outbound_email_events.sql"
C10_6A_MIGRATION = MIGRATIONS_DIR / "20260904170000_add_signup_consent_preferences.sql"
C10_6B_MIGRATION = MIGRATIONS_DIR / "20260905103000_add_marketing_unsubscribe_tokens.sql"


def _normalized_sql() -> str:
    return " ".join(GRANTS_MIGRATION.read_text(encoding="utf-8").lower().split())


def _check_constraint_definition(sql: str, name: str) -> str:
    match = re.search(
        rf"constraint\s+{re.escape(name)}\s+check\s*\((.*?)\)\s*,",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"missing CHECK constraint: {name}"
    return re.sub(r"\s+", "", match.group(1)).lower()


def _migration_function_sql(sql: str, name: str) -> str:
    start = sql.lower().index(f"create or replace function public.{name.lower()}")
    end = sql.lower().index("language plpgsql", start)
    return sql[start:end]


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


def test_c10_6a_signup_consent_preferences_are_local_and_default_safe() -> None:
    sql = " ".join(C10_6A_MIGRATION.read_text(encoding="utf-8").lower().split())

    for column in (
        "terms_accepted boolean not null default false",
        "terms_accepted_at timestamptz null",
        "privacy_accepted boolean not null default false",
        "privacy_accepted_at timestamptz null",
        "marketing_email_opt_in boolean not null default false",
        "marketing_email_opt_in_at timestamptz null",
        "marketing_email_opt_out_at timestamptz null",
        "consent_source text not null default 'profile_bootstrap'",
        "consent_version text null",
    ):
        assert f"add column if not exists {column}" in sql

    assert "constraint user_settings_consent_source_check" in sql
    assert "check (consent_source in ('signup', 'profile_bootstrap'))" in sql
    assert "c10.6a local-only" in sql


def test_c10_6b_marketing_unsubscribe_tokens_are_hash_only_and_backend_owned() -> None:
    sql = " ".join(C10_6B_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.marketing_unsubscribe_tokens" in sql
    for column in (
        "user_id uuid not null references auth.users(id) on delete cascade",
        "recipient_email text not null",
        "token_hash text not null",
        "email_category text not null default 'marketing'",
        "created_at timestamptz not null",
        "expires_at timestamptz not null",
        "used_at timestamptz null",
        "revoked_at timestamptz null",
    ):
        assert column in sql
    assert "token_hash ~ '^[a-f0-9]{64}$'" in sql
    assert "email_category = 'marketing'" in sql
    assert "alter table public.marketing_unsubscribe_tokens enable row level security" in sql
    assert "alter table public.marketing_unsubscribe_tokens force row level security" in sql
    assert "revoke all on table public.marketing_unsubscribe_tokens from authenticated" in sql
    assert "grant select, insert, update, delete on table public.marketing_unsubscribe_tokens to service_role" in sql
    assert "create or replace function public.consume_marketing_unsubscribe_token" in sql
    assert "p_token_hash text" in sql
    assert "t.token_hash = p_token_hash" in sql
    assert "marketing_email_opt_in = false" in sql
    assert "marketing_email_opt_out_at = timezone('utc', now())" in sql
    assert "grant execute on function public.consume_marketing_unsubscribe_token(text) to service_role" in sql
    assert "grant execute on function public.consume_marketing_unsubscribe_token(text) to authenticated" not in sql
    assert "c10.6b local-only" in sql


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


def test_c9_ask_ai_migration_adds_messages_table_constraints_and_rls() -> None:
    sql = " ".join(C9_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.interview_session_ask_ai_messages" in sql
    assert "session_id uuid not null references public.interview_sessions(id) on delete cascade" in sql
    assert "role text not null" in sql
    assert "message_text text not null" in sql
    assert "turn_index integer not null" in sql
    assert "metadata jsonb not null default '{}'::jsonb" in sql
    assert "constraint interview_session_ask_ai_role_check check (role in ('user', 'assistant'))" in sql
    assert "constraint interview_session_ask_ai_message_length check (char_length(message_text) between 1 and 12000)" in sql
    assert "constraint interview_session_ask_ai_metadata_size check (octet_length(metadata::text) <= 4000)" in sql
    assert "create unique index if not exists interview_session_ask_ai_session_turn_idx" in sql
    assert "alter table public.interview_session_ask_ai_messages enable row level security" in sql
    assert "alter table public.interview_session_ask_ai_messages force row level security" in sql
    assert "create policy interview_session_ask_ai_select_own" in sql
    assert "auth.uid() = user_id and exists" in sql
    assert "where s.id = session_id and s.user_id = auth.uid()" in sql


def test_c9_ask_ai_migration_keeps_authenticated_writes_backend_only() -> None:
    sql = " ".join(C9_MIGRATION.read_text(encoding="utf-8").lower().split())
    signature = "public.create_interview_session_ask_ai_message( uuid, uuid, text, text, text, text, integer, jsonb )"

    assert "create or replace function public.create_interview_session_ask_ai_message" in sql
    assert "where s.id = p_session_id and s.user_id = p_user_id" in sql
    assert "select max(m.turn_index)" in sql
    assert "where m.session_id = p_session_id" in sql
    assert "grant select on table public.interview_session_ask_ai_messages to authenticated" in sql
    assert "grant select, insert, update, delete on table public.interview_session_ask_ai_messages to service_role" in sql
    assert "grant insert on table public.interview_session_ask_ai_messages to authenticated" not in sql
    assert "grant update on table public.interview_session_ask_ai_messages to authenticated" not in sql
    assert "grant delete on table public.interview_session_ask_ai_messages to authenticated" not in sql
    assert "create policy interview_session_ask_ai_insert_own" not in sql
    assert "create policy interview_session_ask_ai_update_own" not in sql
    assert "create policy interview_session_ask_ai_delete_own" not in sql
    assert f"revoke all on function {signature} from public" in sql
    assert f"revoke all on function {signature} from anon" in sql
    assert f"revoke all on function {signature} from authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c9_ask_ai_idempotency_migration_adds_request_keys_table() -> None:
    sql = " ".join(C9_IDEMPOTENCY_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create table if not exists public.interview_session_ask_ai_request_keys" in sql
    assert "session_id uuid not null references public.interview_sessions(id) on delete cascade" in sql
    assert "request_id text not null" in sql
    assert "status text not null default 'processing'" in sql
    assert "user_message_id uuid null references public.interview_session_ask_ai_messages(id) on delete set null" in sql
    assert "assistant_message_id uuid null references public.interview_session_ask_ai_messages(id) on delete set null" in sql
    assert "constraint interview_session_ask_ai_request_key_status_check check (status in ('processing', 'completed', 'failed'))" in sql
    assert "constraint interview_session_ask_ai_request_key_unique unique (user_id, session_id, request_id)" in sql
    assert "alter table public.interview_session_ask_ai_request_keys enable row level security" in sql
    assert "alter table public.interview_session_ask_ai_request_keys force row level security" in sql
    assert "create policy interview_session_ask_ai_request_key_select_own" in sql
    assert "auth.uid() = user_id and exists" in sql
    assert "where s.id = session_id and s.user_id = auth.uid()" in sql
    assert "grant select on table public.interview_session_ask_ai_request_keys to authenticated" in sql
    assert "grant select, insert, update, delete on table public.interview_session_ask_ai_request_keys to service_role" in sql
    assert "grant insert on table public.interview_session_ask_ai_request_keys to authenticated" not in sql
    assert "grant update on table public.interview_session_ask_ai_request_keys to authenticated" not in sql
    assert "grant delete on table public.interview_session_ask_ai_request_keys to authenticated" not in sql
    assert "create policy interview_session_ask_ai_request_key_insert" not in sql
    assert "create policy interview_session_ask_ai_request_key_update" not in sql
    assert "create policy interview_session_ask_ai_request_key_delete" not in sql


def test_c9_ask_ai_idempotency_followup_migration_adds_updated_at_trigger() -> None:
    sql = " ".join(C9_IDEMPOTENCY_TRIGGER_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.set_interview_session_ask_ai_request_key_updated_at()" in sql
    assert "new.updated_at := timezone('utc', now())" in sql
    assert "create trigger interview_session_ask_ai_request_key_updated_at" in sql
    assert "before update on public.interview_session_ask_ai_request_keys" in sql
    assert "execute function public.set_interview_session_ask_ai_request_key_updated_at()" in sql


def test_c9_ask_ai_atomic_turn_migration_adds_fenced_completion_rpc() -> None:
    sql = " ".join(C9_ATOMIC_TURN_MIGRATION.read_text(encoding="utf-8").lower().split())
    signature = "public.complete_interview_session_ask_ai_turn( uuid, uuid, text, uuid, text, text, text, text, integer, jsonb )"

    assert "add column if not exists claim_token uuid" in sql
    assert "alter column claim_token set not null" in sql
    assert "create or replace function public.complete_interview_session_ask_ai_turn" in sql
    assert "p_claim_token uuid" in sql
    assert "where k.id = v_request_key.id" in sql
    assert "and k.claim_token = p_claim_token" in sql
    assert "insert into public.interview_session_ask_ai_messages" in sql
    assert f"revoke all on function {signature} from public" in sql
    assert f"revoke all on function {signature} from anon" in sql
    assert f"revoke all on function {signature} from authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql


def test_c9_ask_ai_index_cleanup_migration_drops_redundant_index() -> None:
    sql = " ".join(C9_INDEX_CLEANUP_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "drop index if exists public.interview_session_ask_ai_session_created_idx" in sql


def test_c10_3b_outbound_email_events_migration_adds_backend_idempotency_contract() -> None:
    raw_sql = C10_3B_MIGRATION.read_text(encoding="utf-8")
    sql = " ".join(raw_sql.lower().split())

    assert "create table if not exists public.outbound_email_events" in sql
    for column in (
        "user_id uuid not null references auth.users(id) on delete cascade",
        "session_id uuid null references public.interview_sessions(id) on delete set null",
        "email_type text not null",
        "recipient_email text not null",
        "provider text null",
        "provider_message_id text null",
        "idempotency_key text not null",
        "claim_token uuid null",
        "reconciliation_token uuid null",
        "row_version bigint not null default 1",
        "sending_started_at timestamptz null",
        "lease_expires_at timestamptz null",
        "pending_expires_at timestamptz null",
        "metadata_json jsonb not null default '{}'::jsonb",
    ):
        assert column in sql
    type_definition = _check_constraint_definition(
        C10_3B_MIGRATION.read_text(encoding="utf-8"),
        "outbound_email_events_type_check",
    )
    assert type_definition == (
        "email_typein('welcome','account_security','ai_notes_ready',"
        "'session_summary','transcript_export')"
    )
    status_definition = _check_constraint_definition(
        C10_3B_MIGRATION.read_text(encoding="utf-8"),
        "outbound_email_events_status_check",
    )
    assert status_definition == (
        "statusin('pending','sending','sent','failed','canceled',"
        "'needs_reconciliation','retry_blocked')"
    )

    assert ") nulls not distinct" in sql
    assert "outbound_email_events_pending_lease_check" in sql
    assert "status <> 'pending' or pending_expires_at is not null" in sql
    assert "outbound_email_events_sending_lease_check" in sql
    assert "claim_token is not null" in sql
    assert "sending_started_at is not null" in sql
    assert "lease_expires_at is not null" in sql
    assert "alter table public.outbound_email_events enable row level security" in sql
    assert "alter table public.outbound_email_events force row level security" in sql
    assert "revoke all on table public.outbound_email_events from authenticated" in sql
    assert "grant select, insert, update, delete on table public.outbound_email_events to service_role" in sql
    assert "grant insert on table public.outbound_email_events to authenticated" not in sql
    assert "grant update on table public.outbound_email_events to authenticated" not in sql
    assert "grant delete on table public.outbound_email_events to authenticated" not in sql
    assert "create policy" not in sql
    assert "create or replace function public.claim_outbound_email_event" in sql
    assert "on conflict (user_id, email_type, recipient_email, session_id, idempotency_key) do nothing" in sql
    assert "e.session_id is not distinct from p_session_id" in sql
    assert "create or replace function public.begin_outbound_email_event_send" in sql
    assert "create or replace function public.reclaim_outbound_email_event_pending" in sql
    assert "e.pending_expires_at is not null" in sql
    assert "e.pending_expires_at < timezone('utc', now())" in sql
    assert "create or replace function public.complete_outbound_email_event" in sql
    assert "and e.claim_token = p_claim_token" in sql
    assert "create or replace function public.reconcile_outbound_email_event" in sql
    assert "reconciliation_token = extensions.gen_random_uuid()" in sql
    assert "create or replace function public.resolve_outbound_email_event_reconciliation" in sql
    assert "and e.reconciliation_token = p_reconciliation_token" in sql
    assert "row_version = e.row_version + 1" in sql
    assert "grant execute on function public.claim_outbound_email_event" in sql
    assert "grant execute on function public.resolve_outbound_email_event_reconciliation" in sql

    rpc_row_columns = (
        ("id", "uuid"),
        ("user_id", "uuid"),
        ("session_id", "uuid"),
        ("email_type", "text"),
        ("recipient_email", "text"),
        ("provider", "text"),
        ("provider_message_id", "text"),
        ("idempotency_key", "text"),
        ("claim_token", "uuid"),
        ("reconciliation_token", "uuid"),
        ("row_version", "bigint"),
        ("sending_started_at", "timestamptz"),
        ("lease_expires_at", "timestamptz"),
        ("pending_expires_at", "timestamptz"),
        ("status", "text"),
        ("error_code", "text"),
        ("metadata_json", "jsonb"),
        ("created_at", "timestamptz"),
        ("updated_at", "timestamptz"),
    )
    for function_name in (
        "claim_outbound_email_event",
        "begin_outbound_email_event_send",
        "reclaim_outbound_email_event_pending",
        "complete_outbound_email_event",
        "retry_outbound_email_event",
        "reconcile_outbound_email_event",
        "resolve_outbound_email_event_reconciliation",
    ):
        function_sql = _migration_function_sql(raw_sql, function_name)
        assert "returns table" in function_sql.lower()
        for column, data_type in rpc_row_columns:
            assert re.search(
                rf"^\s+{column}\s+{data_type}(?:,|\s*$)",
                function_sql,
                flags=re.IGNORECASE | re.MULTILINE,
            ), f"{function_name} does not return {column}"

    claim_sql = _migration_function_sql(raw_sql, "claim_outbound_email_event")
    assert re.search(r"^\s+replayed\s+boolean(?:,|\s*$)", claim_sql, re.IGNORECASE | re.MULTILINE)
    assert re.search(r"^\s+conflict_reason\s+text(?:,|\s*$)", claim_sql, re.IGNORECASE | re.MULTILINE)
