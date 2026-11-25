-- READ ONLY. Run only after confirming an isolated STAGING project, never a customer target.
-- No account data, tokens, DSNs or secrets returned.
BEGIN READ ONLY;
select current_database() as database_name, current_user as inspector, version() as postgres_version;
select to_regclass('supabase_migrations.schema_migrations') as migration_history;
-- Stop here if history is absent; have the database administrator inspect history format.
WITH required(version,filename) AS (VALUES
('20260731121714','20260731121714_create_base_cloud_schema.sql'),
('20260731123545','20260731123545_enable_rls_and_storage.sql'),
('20260801115446','20260801115446_grant_cloud_table_privileges.sql'),
('20260803143000','20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql'),
('20260804134140','20260804134140_add_cloud_resume_chunk_activation.sql'),
('20260804151715','20260804151715_fix_cloud_resume_activation_profile_parsing.sql'),
('20260804162315','20260804162315_preserve_profile_fields_on_cloud_resume_activation.sql'),
('20260809120000','20260809120000_add_cloud_job_context_lifecycle.sql'),
('20260828120000','20260828120000_add_interview_session_lifecycle.sql'),
('20260828153000','20260828153000_fix_interview_session_idempotency_rpc.sql'),
('20260829103000','20260829103000_add_interview_session_transcript_storage.sql'),
('20260829170000','20260829170000_lock_down_transcript_entry_inserts.sql'),
('20260829223000','20260829223000_add_interview_session_ai_notes.sql'),
('20260901103000','20260901103000_add_interview_session_ask_ai_messages.sql'),
('20260901123000','20260901123000_add_ask_ai_request_idempotency_keys.sql'),
('20260901170000','20260901170000_add_ask_ai_request_key_updated_at_trigger.sql'),
('20260902120000','20260902120000_add_ask_ai_atomic_turn_persistence.sql'),
('20260902130000','20260902130000_drop_redundant_ask_ai_message_index.sql'),
('20260915120000','20260915120000_add_interview_session_my_answers.sql'),
('20261011120000','20261011120000_add_permanent_transcript_deletion.sql'),
('20261018120000','20261018120000_add_session_model_selection.sql'),
('20261018150000','20261018150000_add_session_generation_turns.sql'),
('20261018180000','20261018180000_add_session_model_bindings.sql'),
('20261018210000','20261018210000_harden_session_generation_recovery.sql'),
('20261021120000','20261021120000_add_answer_sources.sql'),
('20261021130000','20261021130000_add_answer_diagrams.sql'),
('20261022120000','20261022120000_catalog_storage_foundation.sql'),
('20261022150000','20261022150000_catalog_adapter_primitives.sql'),
('20261022180000','20261022180000_subscription_admin_self_probe.sql'),
('20261022200000','20261022200000_catalog_draft_service.sql'),
('20261022210000','20261022210000_catalog_publication_reviews.sql'),
('20261022220000','20261022220000_catalog_lifecycle_transactions.sql'),
('20261023010000','20261023010000_catalog_lifecycle_transport.sql'),
('20261023120000','20261023120000_catalog_v2_drafts.sql'),
('20261023130000','20261023130000_catalog_v2_review_binding.sql'),
('20261023140000','20261023140000_catalog_v3_terms.sql'),
('20261023150000','20261023150000_catalog_policy_public_read.sql'),
('20261023160000','20261023160000_account_usage_foundation.sql'),
('20261024010000','20261024010000_subscription_account_integration.sql'),
('20261024020000','20261024020000_subscription_auto_leases.sql'),
('20261024030000','20261024030000_subscription_clipboard_settlement.sql'),
('20261024040000','20261024040000_subscription_sketch_execution.sql'),
('20261024050000','20261024050000_subscription_manual_execution.sql'),
('20261024060000','20261024060000_subscription_scheduled_changes.sql'),
('20261024070000','20261024070000_subscription_auto_transport.sql'),
('20261024080000','20261024080000_subscription_screen_results.sql'),
('20261024090000','20261024090000_subscription_resume_settlement.sql'),
('20261024100000','20261024100000_subscription_auxiliary_execution.sql'),
('20261024110000','20261024110000_subscription_relay_privacy.sql'),
('20261025010000','20261025010000_subscription_relay_connections.sql')
)
select r.version,r.filename,case when h.version is null then 'MISSING_HISTORY_REVIEW_SCHEMA' else 'RECORDED_REVIEW_SCHEMA' end as status
from required r left join supabase_migrations.schema_migrations h on h.version=r.version order by r.version;
select name,to_regclass('public.'||name) as object from unnest(array[
'catalog_plans','catalog_drafts','catalog_offer_versions','catalog_price_versions','catalog_publication_reviews',
'catalog_publications','catalog_public_state','catalog_publication_policies','account_plan_bindings','usage_periods',
'usage_operations','usage_events','subscription_configuration','subscription_auto_runs','subscription_screen_results',
'subscription_resume_history','subscription_resume_jobs','subscription_resume_active_sets','subscription_notes_versions',
'subscription_relay_frames','subscription_relay_connections','subscription_auth_handoffs','subscription_handoff_limits','subscription_deletion_jobs'
]) name;
select rolname,rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication,rolinherit
from pg_roles where rolname in ('catalog_draft_executor','catalog_public_reader','usage_executor','usage_binding_executor','usage_reconciler');
select parent.rolname as inherited_role,member.rolname as member from pg_auth_members m join pg_roles parent on parent.oid=m.roleid join pg_roles member on member.oid=m.member
where member.rolname in ('catalog_draft_executor','catalog_public_reader','usage_executor','usage_binding_executor','usage_reconciler');
select n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) as arguments,p.prosecdef,p.proconfig,p.proacl::text
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and (p.proname like 'subscription_%' or p.proname like 'usage_%' or p.proname like 'catalog_%')
order by p.proname,arguments;
select c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text
from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public'
and (c.relname like 'usage_%' or c.relname like 'subscription_%' or c.relname like 'catalog_%') order by c.relname;
-- Include restrictive privacy policies and retained Auth references, not data.
select schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
from pg_policies where schemaname in ('public','storage')
and (policyname like '%subscription%' or tablename in ('objects','interview_sessions','resumes'))
order by schemaname,tablename,policyname;
select conrelid::regclass as referencing_table,conname,pg_get_constraintdef(oid) as definition
from pg_constraint where contype='f' and confrelid=to_regclass('auth.users')
order by conrelid::regclass::text,conname;
ROLLBACK;
