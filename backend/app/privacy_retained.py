"""Primary-payload verification is separate from retained-metadata retirement.

Only fixed, source-reviewed envelopes qualify. Unknown JSON, live credentials,
financial/support payloads and incomplete ownership remain blockers. This never
claims that pseudonymous identifiers are anonymous or already past retention.
"""

SCALAR_ENVELOPES = {
    "account_plan_bindings": "usage_recovery",
    "subscription_scheduled_changes": "billing_exception",
    "subscription_resume_history": "usage_recovery",
    "subscription_deletion_jobs": "restore_evidence",
    "subscription_handoff_limits": "usage_recovery",
}
BINDING_FIELDS = [
    "account_id",
    "binding_id",
    "offer_version_id",
    "price_id",
    "signup_at",
    "valid_from",
    "valid_until",
    "source_ref",
    "policy_version",
    "revision",
    "active",
]
REPLY_FIELDS = [
    "run_id",
    "sequence",
    "fence",
    "active",
    "authorized_until",
    "server_time",
    "heartbeat_seconds",
]


def primary_safe(c, table, account):
    if table in SCALAR_ENVELOPES:
        # Column schemas are frozen/classified before cleanup. These tables
        # contain no content/credential/JSON column under that frozen contract.
        return SCALAR_ENVELOPES[table]
    if table == "subscription_auto_runs":
        c.execute(
            "select exists(select 1 from subscription_auto_runs where account_id=%s and (active or owner_token is not null or owner_verifier is not null))",
            (account,),
        )
        return None if c.fetchone()[0] else "usage_recovery"
    if table == "subscription_binding_history":
        c.execute(
            "select exists(select 1 from subscription_binding_history where account_id=%s and (jsonb_typeof(document)<>'object' or document-%s::text[]<>'{}' or exists(select 1 from jsonb_each(document) x where jsonb_typeof(x.value) not in ('string','number','boolean','null')) or document->>'account_id'<>account_id::text))",
            (account, BINDING_FIELDS),
        )
        return None if c.fetchone()[0] else "usage_recovery_or_financial"
    if table == "subscription_auto_replies":
        c.execute(
            "select exists(select 1 from subscription_auto_replies a join subscription_auto_runs r using(run_id) where r.account_id=%s and not(a.document='{}'::jsonb||jsonb_build_object('format_version',2) or (jsonb_typeof(a.document)='object' and a.document-%s::text[]='{}' and a.document->>'run_id'=a.run_id::text and not exists(select 1 from jsonb_each(a.document) x where jsonb_typeof(x.value) not in ('string','number','boolean','null')))))",
            (account, REPLY_FIELDS),
        )
        return None if c.fetchone()[0] else "usage_recovery"
    if table == "subscription_payment_receipts":
        # Accepted financial replay/binding facts contain no candidate payload.
        # Unknown/nested fields remain blocked; no accepted receipt is rewritten.
        c.execute(
            "select exists(select 1 from subscription_payment_receipts where account_id=%s and (jsonb_typeof(result)<>'object' or result-array['account_id','binding_id','offer_version_id','price_id','signup_at','valid_from','valid_until','source_ref','policy_version','revision','active','event_id','kind','effective_at','binding_revision','target_offer_id']<>'{}' or exists(select 1 from jsonb_each(result) v where jsonb_typeof(v.value) not in ('string','number','boolean','null')) or (result ? 'account_id' and result->>'account_id'<>account_id::text)))",
            (account,),
        )
        return None if c.fetchone()[0] else "financial_exception"
    if table == "usage_events":
        c.execute(
            "select exists(select 1 from usage_events where account_id=%s and (actor_principal not in ('usage_executor','usage_binding_executor','usage_reconciler') or event !~ '^(binding[.](assign|bootstrap|status|expire_to_free|verified_payment|scheduled_change|period_end_change)|privacy[.]prepare|auto[.](reserve|settle)|result[.](settle|release)|aggregate[.]rebuild|reserve|dispatch|checkpoint|settle|release|reconcile)$'))",
            (account,),
        )
        return None if c.fetchone()[0] else "usage_recovery_or_financial"
    return None
