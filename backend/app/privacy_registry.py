"""Versioned C15 projections. Omitted columns are never exported implicitly.

This registry describes primary stores, not processor or backup acceptance.
Unknown owned tables remain coverage blockers. No SELECT * is used.
"""

VERSION = "c15.content.v1"
PRIVATE_LIFECYCLE = frozenset(
    [
        "privacy_configuration",
        "privacy_matching_keys",
        "privacy_email_suppression",
        "privacy_deletion_requests",
        "privacy_followup_tasks",
        "privacy_lifecycle_audit",
        "privacy_reauth_intents",
        "privacy_revocation_credentials",
        "privacy_email_otp",
        "privacy_email_otp_limits",
        "privacy_content_jobs",
        "privacy_erased_sessions",
        "privacy_erased_session_keys",
        "privacy_export_rows",
        "privacy_content_objects",
        "privacy_export_proofs",
        "privacy_export_otp_sends",
        "privacy_minimized_records",
        "privacy_retention_attestations",
        "privacy_restore_state",
        "privacy_restore_outbox",
        "privacy_restored_subjects",
        "privacy_restored_sessions",
        "privacy_restored_replays",
        "privacy_auto_reply_payloads",
        "privacy_retirement_configuration",
        "privacy_retirement_units",
        "privacy_retirement_members",
        "privacy_retirement_holds",
        "privacy_retirement_preparation_events",
    ]
)

# table: (owner column, session column, explicit exported columns)
CONTENT = {
    "marketing_unsubscribe_tokens": ("user_id", None, ""),
    "subscription_auth_handoffs": ("account_id", None, ""),
    "profiles": (
        "user_id",
        None,
        "id full_name headline summary skills technical_skills soft_skills education experience projects achievements certifications tools_frameworks profile_completion created_at updated_at terms_accepted terms_accepted_at privacy_accepted privacy_accepted_at marketing_email_opt_in marketing_email_opt_in_at marketing_email_opt_out_at consent_source consent_version",
    ),
    "resumes": (
        "user_id",
        None,
        "id original_filename mime_type file_size status confirmed_at parser_status extraction_status index_status confirmed_profile is_active deleted_at created_at updated_at",
    ),
    "resume_chunks": (
        "user_id",
        None,
        "id resume_id section chunk_text generation_id created_at",
    ),
    "job_contexts": (
        "user_id",
        None,
        "id company position location employment_type source_file_metadata job_description required_skills responsibilities seniority domain_keywords is_active created_at updated_at",
    ),
    "user_settings": (
        "user_id",
        None,
        "id preferred_answer_length preferred_answer_style default_audio_source marketing_consent overlay_settings notification_preferences onboarding_current_step onboarding_completed_at created_at updated_at",
    ),
    "interview_sessions": (
        "user_id",
        "id",
        "id selected_resume_id job_context_id title target_role company_name job_description_preview status started_at ended_at selected_model_key created_at updated_at",
    ),
    "interview_session_transcript_entries": (
        "user_id",
        "session_id",
        "id session_id turn_index source question_text answer_text category provider model created_at",
    ),
    "interview_session_ai_notes": (
        "user_id",
        "session_id",
        "id session_id status notes_markdown summary strengths improvement_areas technical_topics key_questions suggested_followups generated_at created_at updated_at",
    ),
    "interview_session_ask_ai_messages": (
        "user_id",
        "session_id",
        "id session_id role message_text turn_index created_at",
    ),
    "interview_session_my_answers": (
        "user_id",
        "session_id",
        "id session_id body position created_at",
    ),
    "interview_answer_sources": (
        "user_id",
        "session_id",
        "transcript_id session_id answer_type source_revision",
    ),
    "interview_answer_diagrams": (
        "user_id",
        "session_id",
        "transcript_id session_id state graph created_at updated_at",
    ),
    "session_generation_turns": (
        "user_id",
        "session_id",
        "session_id state transcript_id",
    ),
    "interview_session_ask_ai_request_keys": ("user_id", "session_id", ""),
    "interview_session_idempotency_keys": ("user_id", "interview_session_id", ""),
    "job_context_idempotency_keys": ("user_id", None, ""),
    "subscription_screen_threads": ("account_id", "session_id", ""),
    "subscription_screen_results": (
        "account_id",
        "session_id",
        "result_id session_id kind state response created_at",
    ),
    "subscription_notes_versions": ("account_id", None, "operation_id result"),
    "subscription_resume_jobs": ("account_id", None, ""),
    "subscription_resume_active_sets": ("account_id", None, ""),
}

SAFE_METADATA = {
    "usage_operations": (
        "account_id",
        None,
        "operation_id operation requested charged state",
    ),
    "usage_periods": (
        "account_id",
        None,
        "period_id meter starts_at ends_at mode allowance used reserved",
    ),
    "outbound_email_events": (
        "user_id",
        "session_id",
        "id email_type status created_at updated_at",
    ),
    "billing_operations": (
        "account_id",
        None,
        "operation_id consent_at cancel_requested provider_state amount currency interval_unit state created_at",
    ),
    "subscription_payment_receipts": ("account_id", None, "event_id recorded_at"),
}

# Dependency order; parent rows are last. Each operation is its own savepoint.
CLEANUP_ORDER = [
    "marketing_unsubscribe_tokens",
    "subscription_auth_handoffs",
    "interview_answer_diagrams",
    "interview_answer_sources",
    "session_generation_turns",
    "interview_session_ask_ai_request_keys",
    "interview_session_ask_ai_messages",
    "interview_session_my_answers",
    "interview_session_ai_notes",
    "subscription_notes_versions",
    "subscription_screen_results",
    "subscription_screen_threads",
    "interview_session_transcript_entries",
    "interview_session_idempotency_keys",
    "interview_sessions",
    "subscription_resume_active_sets",
    "subscription_resume_jobs",
    "resume_chunks",
    "resumes",
    "job_context_idempotency_keys",
    "job_contexts",
    "profiles",
    "user_settings",
]

EXCLUSIONS = [
    "credentials, tokens and suppression identifiers",
    "internal prompts and security metadata",
    "internal retry/lease payloads",
    "raw internal support notes",
    "numeric embeddings",
    "processor copies, backups and unmanaged device downloads",
]

# Classified retention envelopes; no blanket promise that every current field
# is minimized or eligible for the approved clocks. Cleanup stays blocked until
# field-level retirement/scrubbing is reviewed for these records.
RETAINED = frozenset(
    [
        "account_plan_bindings",
        "usage_events",
        "subscription_binding_history",
        "subscription_payment_receipts",
        "subscription_auto_runs",
        "subscription_auto_replies",
        "subscription_scheduled_changes",
        "subscription_resume_history",
        "subscription_relay_frames",
        "subscription_deletion_jobs",
        "subscription_handoff_limits",
        "subscription_relay_connections",
        "billing_operations",
        "billing_email_delivery_events",
        "billing_evidence",
        "billing_payable_quotes",
        "catalog_draft_requests",
        "catalog_lifecycle_requests",
        "catalog_publication_reviews",
        "catalog_publications",
        "subscription_admin_permissions",
        "billing_notification_sources",
        "billing_admin_commands",
        "billing_admin_reviews",
    ]
)

# Nested result objects require projection too, never pass provider JSON through.
RESULT_FIELDS = frozenset(
    [
        "answer",
        "items",
        "index",
        "display_number",
        "question_type",
        "language",
        "code",
        "evidenceDelta",
        "complete",
        "missingDetails",
        "conflicts",
        "clarification",
        "response",
        "text",
        "outcome",
        "question",
        "notes_markdown",
        "summary",
        "strengths",
        "improvement_areas",
        "technical_topics",
        "key_questions",
        "suggested_followups",
        "created_at",
        "session_id",
    ]
)

PROFILE_FIELDS = frozenset(
    [
        "full_name",
        "email",
        "phone",
        "location",
        "current_title",
        "target_role",
        "professional_summary",
        "education",
        "degree",
        "branch",
        "branch_specialization",
        "college",
        "college_university",
        "university",
        "graduation_year",
        "top_skills",
        "technical_skills",
        "soft_skills",
        "tools_frameworks",
        "projects",
        "experience",
        "work_experience",
        "leadership_activities",
        "achievements",
        "certifications",
        "live_profile_summary",
    ]
)


def project_result(value):
    if isinstance(value, dict):
        return {k: project_result(v) for k, v in value.items() if k in RESULT_FIELDS}
    if isinstance(value, list):
        return [project_result(v) for v in value]
    return value


# Only the explicitly reviewed disposable candidate installs these tables. Their
# fixed schemas are private replay/control evidence, excluded from customer
# archives and ordinary cleanup. No expiry is borrowed from usage/security data.
OPTIONAL_PRIVATE_SCHEMA = {
    "privacy_legacy_reply_retirements": {
        "run_id": "uuid:uuid",
        "account_id": "uuid:uuid",
        "request_id": "uuid:uuid",
        "accepted_at": "timestamp with time zone:timestamptz",
        "eligible_at": "timestamp with time zone:timestamptz",
        "expected_count": "integer:int4",
        "revision": "bigint:int8",
        "enabled": "boolean:bool",
        "completed": "boolean:bool",
    },
    "privacy_retirement_permits": {
        "transaction_id": "xid8:xid8",
        "run_id": "uuid:uuid",
        "expected_count": "integer:int4",
    },
    "privacy_legacy_retirement_attestations": {
        "id": "uuid:uuid",
        "category": "text:text",
        "classifier_version": "text:text",
        "count": "integer:int4",
        "retired_at": "timestamp with time zone:timestamptz",
    },
}
OPTIONAL_PRIVATE_SCHEMA.update(
    {
        "privacy_legacy_audit_retirements": {
            "request_id": "uuid:uuid",
            "account_id": "uuid:uuid",
            "accepted_at": "timestamp with time zone:timestamptz",
            "eligible_at": "timestamp with time zone:timestamptz",
            "expected_count": "integer:int4",
            "revision": "bigint:int8",
            "enabled": "boolean:bool",
            "completed": "boolean:bool",
        },
        "privacy_security_retirement_permits": {
            "transaction_id": "xid8:xid8",
            "request_id": "uuid:uuid",
        },
    }
)
OPTIONAL_PRIVATE_SCHEMA.update({
 "privacy_legacy_redaction_permits":{"transaction_id":"xid8:xid8","account_id":"uuid:uuid","job_id":"uuid:uuid","lease_id":"uuid:uuid"},
 "privacy_legacy_redaction_attestations":{"id":"uuid:uuid","classifier_version":"text:text","field_path":"text:text","rows":"integer:int4","redacted_at":"timestamp with time zone:timestamptz"},
})
PRIVATE_LIFECYCLE = PRIVATE_LIFECYCLE | OPTIONAL_PRIVATE_SCHEMA.keys()

# Fixed runtime SQL is non-customer configuration; retirement deny markers have
# the separate restoration/callback horizon, never an invented 90-day expiry.
OPTIONAL_PRIVATE_SCHEMA.update({
 "privacy_runtime_operations":{"operation_id":"text:text","body":"text:text","arity":"integer:int4","mode":"text:text","restore_only":"boolean:bool","requires_scope":"boolean:bool"},
 "privacy_usage_retirements":{"account_id":"uuid:uuid","request_id":"uuid:uuid","accepted_at":"timestamp with time zone:timestamptz","eligible_at":"timestamp with time zone:timestamptz","classifier_version":"text:text","revision":"bigint:int8","enabled":"boolean:bool","completed":"boolean:bool","expected_counts":"jsonb:jsonb"},
 "privacy_usage_retirement_permits":{"transaction_id":"xid8:xid8","account_id":"uuid:uuid"},
})
PRIVATE_LIFECYCLE = PRIVATE_LIFECYCLE | OPTIONAL_PRIVATE_SCHEMA.keys()
