"""Business workflow acceptance: actual SQL/Auth, explicitly fake payment provider."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from psycopg import Error as DatabaseError
from psycopg import sql


def seed_billing(r, account):
    from app.commercial import catalog_contract as c
    from app.commercial.billing_service import BillingService

    terms = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "frontend/src/auth/approvedPlusTerms.json"
        ).read_text()
    )
    terms.update(
        subscription_policy_ref="synthetic.lifecycle",
        migration_policy_ref="synthetic.migration",
    )
    for price in terms["prices"]:
        price.update(
            price_id=str(uuid4()),
            tax_policy_ref="synthetic.tax",
            rounding_policy_ref="synthetic.rounding",
        )
    for limit in terms["limits"]:
        limit["policy_ref"] = "synthetic.storage"
    raw = {
        "draft_id": str(uuid4()),
        "plan": {"plan_id": str(uuid4()), "code": "synthetic-" + uuid4().hex},
        "revision": "1",
        "state": "draft",
        "contract_version": "catalog.v3",
        "registry_version": "catalog.features.v3",
        "terms": terms,
    }
    draft = c.CatalogDraft.model_validate(raw)
    data = draft.model_dump(mode="python")
    data["terms"] = c._normalized(draft.terms).model_dump(mode="python")
    data["state"] = "previewed"
    snap = c.create_snapshot(data, offer_version_id=str(uuid4()), version=1)
    free_terms = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "frontend/src/auth/approvedFreeTerms.json"
        ).read_text()
    )
    free_terms.update(
        subscription_policy_ref="synthetic.lifecycle",
        migration_policy_ref="synthetic.migration",
    )
    for limit in free_terms["limits"]:
        limit["policy_ref"] = "synthetic.storage"
    free = c.CatalogDraft.model_validate(
        {
            **raw,
            "draft_id": str(uuid4()),
            "plan": {"plan_id": str(uuid4()), "code": "synthetic-free-" + uuid4().hex},
            "contract_version": "catalog.v2",
            "registry_version": "catalog.features.v2",
            "terms": free_terms,
        }
    )
    free_data = free.model_dump(mode="python")
    free_data["state"] = "previewed"
    free_data["terms"] = c._normalized(free.terms).model_dump(mode="python")
    free_snapshot = c.create_snapshot(
        free_data, offer_version_id=str(uuid4()), version=1
    )
    with r.connect() as db:
        db.execute(
            "insert into catalog_plans values(%s,%s)",
            (draft.plan.plan_id, draft.plan.code),
        )
        db.execute(
            "insert into catalog_drafts values(%s,%s,1,%s::jsonb)",
            (draft.draft_id, draft.plan.plan_id, draft.model_dump_json()),
        )
        db.execute(
            "insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json) values(%s,%s,1,%s,1,%s)",
            (
                snap.offer_version_id,
                snap.plan.plan_id,
                draft.draft_id,
                snap.canonical_json(),
            ),
        )
        db.execute(
            "insert into catalog_plans values(%s,%s)",
            (free.plan.plan_id, free.plan.code),
        )
        db.execute(
            "insert into catalog_drafts values(%s,%s,1,%s::jsonb)",
            (free.draft_id, free.plan.plan_id, free.model_dump_json()),
        )
        db.execute(
            "insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json) values(%s,%s,1,%s,1,%s)",
            (
                free_snapshot.offer_version_id,
                free.plan.plan_id,
                free.draft_id,
                free_snapshot.canonical_json(),
            ),
        )
        db.execute(
            "insert into subscription_configuration(singleton,free_offer_id,free_fingerprint,verification_since,policy_version) values(true,%s,%s,clock_timestamp()-interval '1 day','subscriptions.approved.2026-10-24') on conflict(singleton) do nothing",
            (free_snapshot.offer_version_id, free_snapshot.fingerprint),
        )
        price = raw["terms"]["prices"][0]
        until = datetime.now(timezone.utc) + timedelta(days=30)
        db.execute(
            "insert into account_plan_bindings(account_id,binding_id,offer_version_id,price_id,signup_at,valid_from,valid_until,source_ref,policy_version) values(%s,%s,%s,%s,clock_timestamp()-interval '1 day',clock_timestamp(),%s,'synthetic.acceptance','synthetic.lifecycle')",
            (account, uuid4(), snap.offer_version_id, price["price_id"], until),
        )
        operation, provider_id, plan = (
            str(uuid4()),
            "sub_" + uuid4().hex,
            "plan_" + uuid4().hex,
        )
        db.execute(
            "insert into billing_operations(operation_id,account_id,offer_version_id,price_id,mode,merchant,provider_plan,total_count,consent_at,snapshot,fingerprint,amount,currency,interval_unit,state,provider_id,provider_state) values(%s,%s,%s,%s,'test','acc_synthetic',%s,12,clock_timestamp(),%s,%s,%s,'INR','month','confirmed',%s,'active')",
            (
                operation,
                account,
                snap.offer_version_id,
                price["price_id"],
                plan,
                snap.canonical_json(),
                snap.fingerprint,
                int(price["amount_minor"]),
                provider_id,
            ),
        )
        db.execute(
            sql.SQL("alter role usage_binding_executor login password {}").format(
                sql.Literal(r.password)
            )
        )

    class Provider:
        key = "rzp_test_synthetic"

        def __init__(self):
            self.plans = {}
            self.orders = {}

        def plan(self, key):
            return self.plans[key]

        def subscription(self, key):
            return self.orders[key]

        def invoices(self, key):
            return []

        def cancel(self, key):
            self.orders[key]["status"] = "cancelled"

    provider = Provider()
    provider.plans[plan] = {
        "id": plan,
        "entity": "plan",
        "period": "monthly",
        "interval": 1,
        "item": {"amount": int(price["amount_minor"]), "currency": "INR"},
    }
    provider.orders[provider_id] = {
        "id": provider_id,
        "entity": "subscription",
        "plan_id": plan,
        "quantity": 1,
        "total_count": 12,
        "notes": {"operation_id": operation},
        "status": "active",
        "offer_id": None,
    }
    billing = BillingService(
        lambda: r.connect("usage_binding_executor"),
        provider,
        merchant="acc_synthetic",
        webhook_secrets=("synthetic",),
        renewal="automatic",
        enabled=True,
    )
    return billing, operation, until


def verify_cancellation(r, super_admin, results):
    from app.admin_dispatch import CancellationDispatcher

    customer = r.user()["id"]
    billing, operation, until = seed_billing(r, customer)
    # All provider methods here are the existing in-memory fake; no HTTP boundary.
    original = billing.provider.cancel
    calls = []

    def lost_ack(key):
        calls.append(key)
        original(key)
        raise TimeoutError("synthetic uncertain response")

    billing.provider.cancel = lost_ack
    sid = uuid4()
    presence = datetime.now(timezone.utc)

    def call(action, doc):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_cancel(%s,%s,%s,%s,%s::jsonb)",
                (super_admin, sid, presence, action, json.dumps(doc)),
            ).fetchone()[0]

    reviewed = call(
        "review",
        {
            "target": customer,
            "billing_id": operation,
            "operation_id": str(uuid4()),
            "reason": "support",
        },
    )
    assert "review_id" in reviewed, reviewed
    doc = {"review_id": reviewed["review_id"], "confirm": True}
    accepted = call("confirm", doc)
    assert accepted["state"] == "queued", accepted
    assert call("confirm", doc) == accepted
    with r.connect() as fixture:
        # Crash window: command dispatch committed before billing cancel_claim.
        fixture.execute(
            "update administration.commands set dispatched=true where id=%s",
            (accepted["operation_id"],),
        )
        assert (
            fixture.execute(
                "select cancel_requested from billing_operations where operation_id=%s",
                (operation,),
            ).fetchone()[0]
            is False
        )
    worker = CancellationDispatcher(
        lambda: r.connect("admin_dispatch_executor"), billing
    )
    assert worker.run_one()
    assert len(calls) == 1
    with r.connect() as c:
        state = c.execute(
            "select state from administration.commands where id=%s",
            (accepted["operation_id"],),
        ).fetchone()[0]
        if state != "confirmed":
            try:
                c.execute(
                    "update administration.commands set lease_until=clock_timestamp()-interval '1 second' where id=%s",
                    (accepted["operation_id"],),
                )
                c.commit()
                assert worker.run_one()
                state = c.execute(
                    "select state from administration.commands where id=%s",
                    (accepted["operation_id"],),
                ).fetchone()[0]
            except (
                DatabaseError,
                RuntimeError,
                OSError,
                ValueError,
                KeyError,
            ) as error:
                r.save(
                    "cancellation-diagnostic.json",
                    {
                        "type": type(error).__name__,
                        "sqlstate": getattr(error, "sqlstate", None),
                        "sql_errors": r.sql_errors[-8:],
                    },
                )
                raise AssertionError(
                    "cancellation_reconcile:" + type(error).__name__
                ) from None
        assert state == "confirmed", state
        assert c.execute(
            "select valid_until,active from account_plan_bindings where account_id=%s",
            (customer,),
        ).fetchone() == (until, True)
        assert not c.execute(
            "select exists(select 1 from administration.customer_access where subject=%s and restricted)",
            (customer,),
        ).fetchone()[0]
    assert not worker.run_one()
    assert len(calls) == 1
    # An expired lease after dispatch is reconciled, not blindly sent again.
    with r.connect() as c:
        c.execute(
            "update administration.commands set state='unknown',lease_until=clock_timestamp()-interval '1 second' where id=%s",
            (accepted["operation_id"],),
        )
    assert worker.run_one()
    assert len(calls) == 1
    results.append(
        {
            "scenario": "renewal_cancel_existing_billing_adapter_fake_provider_lost_ack_replay_paid_expiry_preserved",
            "passed": True,
        }
    )


def verify_campaign(r, actor, results):
    import base64
    import secrets
    import time

    from app.admin_campaigns import CampaignDispatcher
    from app.email.config import MarketingEmailSettings
    from app.privacy_runtime import LocalCatcher
    from svix.webhooks import Webhook

    first, second = r.user(), r.user()
    with r.connect() as c:
        for u in (first, second):
            c.execute(
                "insert into user_settings(user_id,marketing_email_opt_in) values(%s,true)",
                (u["id"],),
            )
    sid = uuid4()
    now = datetime.now(timezone.utc)

    def call(action, doc):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_campaign(%s,%s,%s,%s,%s::jsonb)",
                (actor, sid, now, action, json.dumps(doc)),
            ).fetchone()[0]

    campaign = str(uuid4())
    saved = call(
        "save",
        {
            "campaign_id": campaign,
            "revision": "0",
            "name": "Synthetic campaign",
            "subject": "Synthetic C15.5 local capture",
            "body": "Synthetic approved campaign content.",
        },
    )
    assert saved["revision"] == "1", saved
    assert call("audience", {"campaign_id": campaign, "revision": "1"})["error"] == "conflict"
    assert (
        call("preview", {"campaign_id": campaign})["template_version"]
        == "admin_campaign.v1"
    )
    test_document = {
        "campaign_id": campaign,
        "revision": "1",
        "target": first["id"],
        "operation_id": str(uuid4()),
    }
    requested_test = call("test", test_document)
    assert requested_test.get("state") == "queued", requested_test
    assert call("test", test_document)["state"] == "already_requested"
    with r.connect() as observed:
        assert (
            observed.execute(
                "select count(*) from administration.campaign_deliveries where campaign_id=%s and account_id=%s and test_revision=1",
                (campaign, first["id"]),
            ).fetchone()[0]
            == 1
        )
    assert "error" in call(
        "test", {"campaign_id": campaign, "revision": "1", "target": actor, "operation_id": str(uuid4())}
    )
    worker = CampaignDispatcher(
        lambda: r.connect("admin_dispatch_executor"),
        settings=MarketingEmailSettings(
            enabled=True,
            provider_mode="live",
            resend_api_key="synthetic-unused-local-capture",
        ),
        provider=LocalCatcher("mail", 1025),
    )
    assert worker.run_one()
    with r.connect() as observed:
        assert (
            observed.execute(
                "select state from administration.campaign_deliveries where campaign_id=%s and test_revision=1",
                (campaign,),
            ).fetchone()[0]
            == "accepted"
        )
    assert call("audience", {"campaign_id": campaign, "revision": "0"})["error"] == "conflict"
    audience = call("audience", {"campaign_id": campaign, "revision": "1"})
    assert audience["recipient_count"] == 2, audience
    with r.connect() as c:
        c.execute(
            "update user_settings set marketing_email_opt_in=false where user_id=%s",
            (second["id"],),
        )
    doc = {
        "review_id": audience["review_id"],
        "confirm": True,
        "operation_id": str(uuid4()),
    }
    confirmed = call("confirm", doc)
    assert confirmed["state"] == "queued", confirmed
    assert call("confirm", doc) == confirmed
    for _ in range(3):
        worker.run_one()
    status = call("read", {"campaign_id": campaign})
    assert status["results"].get("accepted") == 1, status
    assert status["results"].get("skipped") == 1, status
    assert not worker.run_one()
    messages = r.http.get(r.url("mail") + "/api/v1/messages", timeout=5).json()
    assert (
        sum(
            m["Subject"] == "Synthetic C15.5 local capture"
            for m in messages["messages"]
        )
        == 2
    )
    with r.connect() as c:
        message_id = str(
            c.execute(
                "select message_id from administration.campaign_deliveries where campaign_id=%s and state='accepted' and test_revision=0",
                (campaign,),
            ).fetchone()[0]
        )
    secret = "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()
    raw = json.dumps(
        {
            "type": "email.delivered",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {"email_id": message_id},
        }
    )
    event_id = "synthetic-" + uuid4().hex
    timestamp = int(time.time())
    signature = Webhook(secret).sign(
        event_id, datetime.fromtimestamp(timestamp, timezone.utc), raw
    )
    headers = {
        "svix-id": event_id,
        "svix-timestamp": str(timestamp),
        "svix-signature": signature,
    }
    assert worker.delivery(raw.encode(), headers, secret, "admin_campaigns")
    assert worker.delivery(raw.encode(), headers, secret, "admin_campaigns")
    assert call("read", {"campaign_id": campaign})["results"].get("delivered") == 1
    import re

    from app.admin_campaigns import CampaignUnsubscribe
    from app.email.unsubscribe import MarketingUnsubscribeService

    message = next(
        item
        for item in messages["messages"]
        if item["Subject"] == "Synthetic C15.5 local capture"
    )
    captured = r.http.get(
        r.url("mail") + "/api/v1/message/" + message["ID"], timeout=5
    ).json()
    match = re.search(r"token=([A-Za-z0-9_-]{20,256})", captured.get("Text", ""))
    assert match is not None, "local unsubscribe token missing"
    optout = MarketingUnsubscribeService(
        client=CampaignUnsubscribe(lambda: r.connect("admin_dispatch_executor"))
    )
    assert optout.unsubscribe(raw_token=match[1]).unsubscribed
    with r.connect() as c:
        assert (
            c.execute(
                "select marketing_email_opt_in from user_settings where user_id=%s",
                (first["id"],),
            ).fetchone()[0]
            is False
        )
    assert "error" in call(
        "test",
        {"campaign_id": campaign, "revision": "1", "target": first["id"], "operation_id": str(uuid4())},
    )
    changed = call(
        "save",
        {
            "campaign_id": campaign,
            "revision": "1",
            "name": "Forbidden resend",
            "subject": "No",
            "body": "No",
        },
    )
    assert changed["error"] == "conflict"
    results.append(
        {
            "scenario": "campaign_draft_preview_audience_confirm_local_mailpit_optout_recheck_dispatch_dedup_signed_callbacks",
            "passed": True,
        }
    )


def verify_successor(r, actor, results):
    from c15_admin_acceptance import verify_totp

    recipient, other = r.user(), r.user()
    verify_totp(r, recipient)
    sid = uuid4()
    now = datetime.now(timezone.utc)

    def call(subject, action, doc, presence=now):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_successor(%s,%s,%s,%s,%s::jsonb)",
                (subject, sid, presence, action, json.dumps(doc)),
            ).fetchone()[0]

    offer = call(actor, "offer", {"target": recipient["id"], "confirm": True})
    assert offer["state"] == "offered", offer
    doc = {"transfer_id": offer["transfer_id"], "confirm": True}
    assert call(other["id"], "accept", doc)["error"] == "reauthentication_required"
    assert (
        call(recipient["id"], "accept", doc, now.replace(year=2020))["error"]
        == "reauthentication_required"
    )
    assert call(recipient["id"], "accept", doc)["state"] == "accepted"
    assert call(recipient["id"], "accept", doc)["state"] == "accepted"
    with r.connect("admin_executor") as c:
        admitted = c.execute(
            "select public.administration_call(%s,null,null,'me','{}')",
            (recipient["id"],),
        ).fetchone()[0]
    assert admitted["role"] == "super_admin", admitted
    assert call(actor, "status", {"transfer_id": offer["transfer_id"]})[
        "successor_access_verified"
    ]
    with r.connect() as c:
        assert c.execute(
            "select role,status from administration.memberships where subject=%s",
            (actor,),
        ).fetchone() == ("super_admin", "active")
    assert (
        call(other["id"], "status", {"transfer_id": offer["transfer_id"]})["error"]
        == "not_found"
    )
    results.append(
        {
            "scenario": "successor_actual_auth_mfa_independent_acceptance_access_verification_replay_subject_isolation_no_self_deletion_block",
            "passed": True,
        }
    )


def verify_metrics(r, actor, results):
    with r.connect() as schema_connection:
        schema = schema_connection.execute(
            "select public.administration_schema()"
        ).fetchone()[0]
        r.save("admin-schema.json", schema)
    from datetime import timedelta

    from app.admin_telemetry import Attempt, context

    customer = r.user()
    now = datetime.now(timezone.utc)

    def record(document):
        with r.connect("admin_executor") as c:
            c.execute(
                "select public.administration_attempt(%s::jsonb)",
                (json.dumps(document),),
            )

    token = context.set((customer["id"], str(uuid4()), record))
    try:
        with Attempt("openai", "synthetic-model") as attempt:
            attempt.usage(
                {
                    "model": "synthetic-model-v1",
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                    "private": "SENTINEL_MUST_NOT_RECORD",
                }
            )
            attempt.outcome = "completed"
        record(
            {
                "attempt_id": attempt.id,
                "request_id": str(uuid4()),
                "account_id": customer["id"],
                "provider": "openai",
                "model": "synthetic-model",
                "reported_model": None,
                "outcome": "failed",
                "input_tokens": None,
                "output_tokens": None,
                "duration_ms": 0,
            }
        )
        try:
            with Attempt("groq", "synthetic-failed"):
                raise RuntimeError("SENTINEL_MUST_NOT_RECORD")
        except RuntimeError:
            pass
        with Attempt("openai", "synthetic-aborted"):
            pass
    finally:
        context.reset(token)
    with r.connect() as c:
        c.execute(
            "insert into administration.model_rates values('openai','synthetic-model','synthetic-v1','USD',1,2,%s,%s)",
            (now - timedelta(days=1), now + timedelta(days=1)),
        )
        assert (
            c.execute(
                "select count(*) from administration.provider_attempts where id=%s",
                (attempt.id,),
            ).fetchone()[0]
            == 1
        )
        assert "SENTINEL" not in str(
            c.execute(
                "select to_jsonb(a) from administration.provider_attempts a"
            ).fetchall()
        )

    def metrics(
        subject,
        start=now - timedelta(days=1),
        end=now + timedelta(seconds=10),
        zone="Asia/Calcutta",
    ):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_metrics(%s,%s,%s,%s)",
                (subject, start, end, zone),
            ).fetchone()[0]

    got = metrics(actor)
    if "models" not in got:
        with r.connect() as diagnostic:
            flags = diagnostic.execute(
                "select %s::timestamptz is null,%s::timestamptz<=%s::timestamptz,%s::timestamptz-%s::timestamptz>interval '90 days',%s::timestamptz>clock_timestamp()+interval '1 minute',exists(select 1 from pg_timezone_names where name='Asia/Calcutta')",
                (
                    now - timedelta(days=1),
                    now + timedelta(seconds=10),
                    now - timedelta(days=1),
                    now + timedelta(seconds=10),
                    now - timedelta(days=1),
                    now + timedelta(seconds=10),
                ),
            ).fetchone()
        raise AssertionError({"metrics_error": got, "validation_flags": flags})
    assert sum(m["attempts"] for m in got["models"]) == 3, got
    assert got["cost_unknown_attempts"] == 2, got
    assert got["costs"][0]["estimated_amount"] == 0.00014, got
    assert got["provider_confirmed_charges"] is None
    assert metrics(customer["id"])["error"] == "not_found"
    assert metrics(actor, zone="invalid/zone")["error"] == "invalid"
    assert metrics(actor, start=now - timedelta(days=91))["error"] == "invalid"
    with r.connect("admin_executor") as c:
        detail = c.execute(
            "select public.administration_read(%s,'user',%s,null,null)",
            (actor, customer["id"]),
        ).fetchone()[0]
    assert detail["resources"]["resume_count"] == 0, detail
    assert detail["consent"] is None
    assert "auth_provider_labels" in detail
    assert "filename" not in json.dumps(detail)
    results.append(
        {
            "scenario": "metrics_actual_restricted_role_content_free_attempts_completed_failed_aborted_replay_cost_coverage_timezone_metadata_allowlist",
            "passed": True,
        }
    )


def verify_lifecycle(r, actor, results):
    from app.admin_registry import validate_admin_schema
    from app.privacy_content import ContentBlocked

    with r.connect("admin_executor") as c:
        current = c.execute("select public.administration_schema()").fetchone()[0]
    validate_admin_schema(current)
    drift = {**current, "unclassified": {"secret": "text:text"}}
    try:
        validate_admin_schema(drift)
    except ContentBlocked:
        pass
    else:
        raise AssertionError("schema drift admitted")
    with r.connect() as c:
        c.execute(
            "update administration.provider_attempts set completed_at=clock_timestamp()-interval '90 days'-interval '1 second' where model='synthetic-aborted'"
        )
        c.execute(
            "update administration.provider_attempts set completed_at=clock_timestamp()-interval '90 days'+interval '1 hour' where model='synthetic-failed'"
        )
        stale = uuid4()
        review = uuid4()
        recipient = r.user()["id"]
        c.execute(
            "insert into administration.campaigns(id,name,subject,body,author,state) values(%s,'Synthetic expired','Synthetic','Synthetic',%s,'queued')",
            (stale, actor),
        )
        c.execute(
            "insert into administration.audience_reviews(id,campaign_id,revision,actor,actor_revision,session_id,recipient_count,references_until) values(%s,%s,1,%s,1,%s,1,clock_timestamp()-interval '1 second')",
            (review, stale, actor, uuid4()),
        )
        c.execute(
            "insert into administration.audience_members values(%s,%s)",
            (review, recipient),
        )
        c.execute(
            "insert into administration.campaign_deliveries(campaign_id,review_id,account_id) values(%s,%s,%s)",
            (stale, review, recipient),
        )
    with r.connect("admin_retention_executor") as c:
        outcome = c.execute("select public.administration_lifecycle(100)").fetchone()[0]
    assert outcome["records_removed"] >= 2, outcome
    with r.connect() as c:
        assert (
            c.execute(
                "select count(*) from administration.provider_attempts where model='synthetic-aborted'"
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from administration.provider_attempts where model='synthetic-failed'"
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from administration.audience_members where review_id=%s",
                (review,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select state from administration.campaign_deliveries where campaign_id=%s",
                (stale,),
            ).fetchone()[0]
            == "skipped"
        )
        assert (
            c.execute(
                "select state from administration.campaign_fences where id=%s", (stale,)
            ).fetchone()[0]
            == "expired"
        )
    with r.connect() as c:
        import psycopg

        for role in ("service_role", "authenticated"):
            c.execute(
                psycopg.sql.SQL("alter role {} login password {}").format(
                    psycopg.sql.Identifier(role), psycopg.sql.Literal(r.password)
                )
            )
    for role in (
        "admin_executor",
        "admin_dispatch_executor",
        "service_role",
        "authenticated",
    ):
        try:
            with r.connect(role) as c:
                c.execute("select public.administration_lifecycle(100)")
        except DatabaseError as error:
            assert getattr(error, "sqlstate", None) == "42501", type(error).__name__
        else:
            raise AssertionError("retention capability leaked")
    with r.connect("admin_retention_executor") as c:
        c.execute("select public.administration_lifecycle(100)")
    results.append(
        {
            "scenario": "administration_retention_schema_drift_90day_boundaries_7day_audience_expiry_stops_dispatch_spent_fences_repeat_and_negative_permissions",
            "passed": True,
        }
    )


def verify_export_registry(r, results):
    import io
    import zipfile

    import psycopg
    from app.privacy_content import ContentEngine
    from app.privacy_runtime_db import RuntimeConnection
    from c15_actual_engines import ActualStorage

    account = r.user()["id"]
    other = r.user()["id"]
    job = str(uuid4())
    with r.connect() as c:
        for role in ("privacy_content_executor", "privacy_cleanup_executor"):
            c.execute(
                psycopg.sql.SQL("alter role {} login password {}").format(
                    psycopg.sql.Identifier(role), psycopg.sql.Literal(r.password)
                )
            )
    storage = ActualStorage(r)
    engine = ContentEngine(
        lambda: RuntimeConnection(
            r.connect("privacy_content_executor"), "privacy_content_executor"
        ),
        storage,
        local_rehearsal=True,
        credential_connect=lambda: r.connect("privacy_cleanup_executor"),
    )
    with r.connect() as fixture:
        fixture.execute(
            "insert into administration.provider_attempts(id,request_id,subject,provider,model,outcome,duration_ms) select gen_random_uuid(),gen_random_uuid(),%s,'ollama','synthetic-model','completed',1 from generate_series(1,6000)",
            (account,),
        )
    engine.request(account, job)
    with r.connect() as c:
        record = c.execute(
            "select document from privacy_export_rows where job_id=%s and category='administration_personal'",
            (job,),
        ).fetchone()[0]
        assert record["executed_attempts"] == []
        documents = c.execute(
            "select document from privacy_export_rows where job_id=%s and category='administration_personal'",
            (job,),
        ).fetchall()
        assert (
            sum(len(row[0].get("executed_attempts", [])) for row in documents) == 6000
        )
        assert all(len(json.dumps(row[0]).encode()) < 1024 * 1024 for row in documents)
        assert "protected audit history" in record["exclusions"]
        assert other not in json.dumps(record)
    assert engine.run_one()
    assert engine.status(account, job)["state"] == "ready"
    with r.connect() as c:
        key = c.execute(
            "select artifact_key from privacy_content_jobs where id=%s", (job,)
        ).fetchone()[0]
    version = storage.stat("exports", key)
    with zipfile.ZipFile(
        io.BytesIO(b"".join(storage.read("exports", key, version)))
    ) as archive:
        assert any(
            name.startswith("data/administration_personal/")
            for name in archive.namelist()
        )
    results.append(
        {
            "scenario": "admin_personal_projection_normal_restricted_content_runtime_actual_private_storage_zip_no_audience_or_audit_leak",
            "passed": True,
        }
    )


def verify_admin_restore(r, actor, results):
    import secrets
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from app.admin_restore import AdministrationRestore
    from app.privacy_checkpoint import LocalCheckpointStore
    from app.privacy_content import ContentBlocked
    from app.privacy_restore import RestoreJournal

    target, unaffected = r.user()["id"], r.user()["id"]
    campaign = uuid4()
    with r.connect("admin_restore_executor") as c:
        original = c.execute(
            "select public.administration_restore('capture','{}')"
        ).fetchone()[0]
    for malformed in (
        None,
        {},
        {
            "version": 1,
            "revision": "0",
            "memberships": [],
            "restrictions": [],
            "spent_campaigns": [],
            "arbitrary": "forbidden",
        },
    ):
        try:
            with r.connect("admin_restore_executor") as c:
                c.execute(
                    "select public.administration_restore('replay',%s::jsonb)",
                    (json.dumps(malformed),),
                )
        except DatabaseError as error:
            assert error.sqlstate == "22023"
        else:
            raise AssertionError("malformed restore evidence accepted")
    with r.connect("admin_restore_executor") as c:
        assert (
            c.execute(
                "select public.administration_restore('capture','{}')"
            ).fetchone()[0]
            == original
        )
    with tempfile.TemporaryDirectory(prefix="owned-admin-restore-") as directory:
        root = Path(directory)
        key = secrets.token_bytes(32)
        store = LocalCheckpointStore(
            root / "checkpoint",
            root / "independent-witness",
            key,
            str(uuid4()),
            str(uuid4()),
        )
        journal = RestoreJournal(root / "journal", {"v1": key}, "v1")
        source = AdministrationRestore(
            lambda: r.connect("admin_restore_executor"),
            journal,
            store,
            str(uuid4()),
            str(uuid4()),
        )
        source.initialize_source()
        # Crash after durable journal append but before checkpoint acknowledgement.
        with r.connect() as fixture:
            fixture.execute(
                "insert into administration.campaign_fences values(%s,1,'expired')",
                (uuid4(),),
            )
        original_write = store.write

        def lost_checkpoint(*_):
            raise ContentBlocked("synthetic_checkpoint_ack_lost")

        store.write = lost_checkpoint
        try:
            try:
                source.publish()
            except ContentBlocked:
                pass
            else:
                raise AssertionError("publication fault not injected")
        finally:
            store.write = original_write
        assert not source.ready()
        source.publish()
        assert source.ready()
        source.start()
        assert source.ready()
        import threading

        from app.privacy_witness import HTTPCheckpointStore, local_authority

        reader, writer, operator = (secrets.token_urlsafe(32) for _ in range(3))
        server = local_authority(store, reader, writer, operator_token=operator)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:" + str(server.server_address[1])
        remote_store = HTTPCheckpointStore(
            url, writer, key, store.environment, store.dataset, local_rehearsal=True
        )
        operator_store = HTTPCheckpointStore(
            url, operator, key, store.environment, store.dataset, local_rehearsal=True
        )
        with store.locked() as local:
            prior = store.read(local)
            assert prior["journal_id"] is not None
            prior.pop("source_sealed")
            store.write(local, prior)
        try:
            remote_store.upgrade_snapshot_schema()
        except ContentBlocked:
            pass
        else:
            raise AssertionError("ordinary witness writer upgraded the schema")
        operator_store.upgrade_snapshot_schema()
        with remote_store.locked() as checkpoint:
            assert remote_store.read(checkpoint)["source_sealed"] is False
        source.store = remote_store
        try:
            source.start()
            second_store = HTTPCheckpointStore(
                url, writer, key, store.environment, store.dataset, local_rehearsal=True
            )
            second_source = AdministrationRestore(
                lambda: r.connect("admin_restore_executor"),
                journal,
                second_store,
                source.generation,
                source.snapshot,
            )
            second_source.start()
            with r.connect() as c:
                c.execute(
                    "insert into administration.campaign_fences values(%s,1,'expired')",
                    (uuid4(),),
                )
            try:
                with ThreadPoolExecutor(2) as pool:
                    list(
                        pool.map(
                            lambda coordinator: coordinator.publish(),
                            (source, second_source),
                        )
                    )
                assert source.ready() and second_source.ready()
                with remote_store.locked() as checkpoint:
                    selected = source._journal(remote_store.read(checkpoint)).path
                assert selected.is_file()
            finally:
                second_store.http.close()
            with r.connect("admin_restore_executor") as c:
                old = source.capture(c)
            with r.connect("admin_executor") as c:
                session = uuid4()
                now = datetime.now(timezone.utc)
                review = c.execute(
                    "select public.administration_access(%s,%s,%s,'review',%s::jsonb)",
                    (
                        actor,
                        session,
                        now,
                        json.dumps(
                            {
                                "target": target,
                                "restricted": True,
                                "reason": "support",
                                "operation_id": str(uuid4()),
                            }
                        ),
                    ),
                ).fetchone()[0]
                assert "review_id" in review, review
                accepted = c.execute(
                    "select public.administration_access(%s,%s,%s,'confirm',%s::jsonb)",
                    (
                        actor,
                        session,
                        now,
                        json.dumps({"review_id": review["review_id"], "confirm": True}),
                    ),
                ).fetchone()[0]
                assert accepted["restricted"]
            with r.connect() as c:
                c.execute(
                    "insert into administration.campaign_fences values(%s,1,'sent')",
                    (campaign,),
                )
            source.publish()
            source.seal_source()
            with store.locked() as local:
                sequence = store.read(local)["sequence"]
            # Controlled synthetic old-snapshot restoration. No historical/shared database is touched.
            with r.connect() as c:
                c.execute(
                    "delete from administration.customer_access where subject=%s",
                    (target,),
                )
                c.execute(
                    "delete from administration.campaign_fences where id=%s",
                    (campaign,),
                )
                c.execute(
                    "update administration.restore_revision set revision=%s",
                    (int(old["revision"]),),
                )
            assert not source.ready()
            generation, snapshot = str(uuid4()), str(uuid4())
            operator_store.authorize_restore(sequence, generation, snapshot)
            restored = AdministrationRestore(
                lambda: r.connect("admin_restore_executor"),
                journal,
                remote_store,
                generation,
                snapshot,
            )

            def reconcile():
                try:
                    restored.reconcile()
                    return "ready"
                except ContentBlocked:
                    return "quarantined"

            with ThreadPoolExecutor(2) as pool:
                outcomes = list(pool.map(lambda _: reconcile(), range(2)))
            assert outcomes.count("ready") == 1, outcomes
            # The losing coordinator cannot grant readiness; explicitly verify the acknowledged generation.
            restored.start()
            assert restored.ready()
            with r.connect("admin_executor") as c:
                assert (
                    c.execute(
                        "select public.administration_product_access(%s)", (target,)
                    ).fetchone()[0]
                    is False
                )
                assert (
                    c.execute(
                        "select public.administration_product_access(%s)", (unaffected,)
                    ).fetchone()[0]
                    is True
                )
            with r.connect() as c:
                assert (
                    c.execute(
                        "select state from administration.campaign_fences where id=%s",
                        (campaign,),
                    ).fetchone()[0]
                    == "restored_blocked"
                )
            # Lost responses both before and after the independent CAS acknowledgement.
            for acknowledged in (False, True):
                restored.seal_source()
                with store.locked() as local:
                    sequence = store.read(local)["sequence"]
                generation, snapshot = str(uuid4()), str(uuid4())
                operator_store.authorize_restore(sequence, generation, snapshot)
                recovering = AdministrationRestore(
                    lambda: r.connect("admin_restore_executor"),
                    journal,
                    remote_store,
                    generation,
                    snapshot,
                )
                write = remote_store.write

                def uncertain(slot, record, acknowledge=acknowledged, publish=write):
                    if acknowledge:
                        publish(slot, record)
                    raise ContentBlocked("synthetic_witness_response_lost")

                remote_store.write = uncertain
                try:
                    try:
                        recovering.reconcile()
                    except ContentBlocked:
                        pass
                    else:
                        raise AssertionError("witness fault not injected")
                finally:
                    remote_store.write = write
                with r.connect("admin_restore_executor") as c:
                    revision = recovering.capture(c)["revision"]
                if acknowledged:
                    recovering.start()
                else:
                    recovering.reconcile()
                assert recovering.ready()
                with r.connect("admin_restore_executor") as c:
                    assert recovering.capture(c)["revision"] == revision
                restored = recovering
            with remote_store.locked() as checkpoint:
                selected = restored._journal(remote_store.read(checkpoint)).path
            selected.write_bytes(selected.read_bytes()[:-1])
            assert not restored.ready()
        finally:
            remote_store.http.close()
            operator_store.http.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive()
    results.append(
        {
            "scenario": "admin_restore_actual_http_witness_independent_authenticated_checkpoint_old_database_replay_restriction_spent_campaign_concurrent_coordinators_generation_tamper_quarantine",
            "passed": True,
        }
    )


def verify_admin_account_cleanup(r, results):
    import psycopg

    account, other = r.user()["id"], r.user()["id"]
    job, lease = str(uuid4()), str(uuid4())
    campaign, review = uuid4(), uuid4()
    with r.connect() as c:
        c.execute(
            "insert into privacy_deletion_requests(account_id,request_id,session_id,reauthenticated_at,policy_version,scope,confirmation_hash,status_hash,email_key_version,email_digest,state,expires_at,accepted_at) values(%s,%s,%s,clock_timestamp(),'synthetic.cleanup','whole_account','synthetic','synthetic',1,decode(repeat('ab',32),'hex'),'accepted_restricted',clock_timestamp(),clock_timestamp())",
            (account, job, uuid4()),
        )
        c.execute(
            "insert into privacy_content_jobs(id,account_id,kind,registry_version,state,lease_id,lease_until) values(%s,%s,'account','c15.content.v1','running',%s,clock_timestamp()+interval '30 seconds')",
            (job, account, lease),
        )
        for subject in (account, other):
            c.execute(
                "insert into administration.activity(subject,event_id,kind) values(%s,%s,'session_started')",
                (subject, uuid4()),
            )
        c.execute(
            "insert into administration.campaigns(id,name,subject,body,author) values(%s,'Synthetic account-owned','Synthetic','Synthetic',%s)",
            (campaign, account),
        )
        c.execute(
            "insert into administration.audience_reviews(id,campaign_id,revision,actor,actor_revision,session_id,recipient_count) values(%s,%s,1,%s,1,%s,1)",
            (review, campaign, account, uuid4()),
        )
        c.execute(
            "insert into administration.audience_members values(%s,%s)", (review, other)
        )
        c.execute(
            "insert into administration.campaign_deliveries(campaign_id,review_id,account_id) values(%s,%s,%s)",
            (campaign, review, account),
        )
        before = c.execute(
            "select (select count(*) from billing_evidence),(select count(*) from privacy_email_suppression)"
        ).fetchone()
    with r.connect("usage_executor") as c:
        c.execute("select public.subscription_deletion_prepare(%s,%s)", (account, job))
    try:
        with r.connect("privacy_cleanup_executor") as c:
            c.execute(
                "select public.administration_subject_cleanup(%s,%s)",
                (job, str(uuid4())),
            )
    except psycopg.errors.InsufficientPrivilege:
        pass
    else:
        raise AssertionError("stale cleanup fence accepted")
    for _ in range(2):
        with r.connect("privacy_cleanup_executor") as c:
            c.execute(
                "select public.administration_subject_cleanup(%s,%s)", (job, lease)
            )
    with r.connect() as c:
        assert (
            c.execute(
                "select count(*) from administration.activity where subject=%s",
                (account,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from administration.activity where subject=%s",
                (other,),
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from administration.campaigns where author=%s",
                (account,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from administration.audience_members where review_id=%s",
                (review,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select state from administration.campaign_fences where id=%s",
                (campaign,),
            ).fetchone()[0]
            == "expired"
        )
        assert (
            c.execute(
                "select (select count(*) from billing_evidence),(select count(*) from privacy_email_suppression)"
            ).fetchone()
            == before
        )
    with r.connect("admin_executor") as c:
        c.execute(
            "select public.administration_attempt(%s::jsonb)",
            (
                json.dumps(
                    {
                        "attempt_id": str(uuid4()),
                        "request_id": str(uuid4()),
                        "account_id": account,
                        "provider": "openai",
                        "model": "synthetic-late",
                        "reported_model": None,
                        "outcome": "completed",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "duration_ms": 1,
                    }
                ),
            ),
        )
    with r.connect() as c:
        assert (
            c.execute(
                "select count(*) from administration.provider_attempts where subject=%s",
                (account,),
            ).fetchone()[0]
            == 0
        )
    results.append(
        {
            "scenario": "admin_scope_lease_bound_account_cleanup_stale_worker_retry_other_account_billing_suppression_preserved_late_attempt_denied",
            "passed": True,
        }
    )


def verify_population(r, actor, results):
    def metrics(start, end):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_metrics(%s,%s,%s,%s)",
                (actor, start, end, "UTC"),
            ).fetchone()[0]

    now = datetime.now(timezone.utc)
    first = metrics(now - timedelta(days=30), now + timedelta(seconds=1))
    assert first["new_users"] is None and first["growth_percent"] is None, first
    with r.connect() as c:
        cutoff = c.execute(
            "select population_started_at from administration.telemetry_coverage"
        ).fetchone()[0]
    baseline = metrics(cutoff, datetime.now(timezone.utc) + timedelta(seconds=1))
    recently_verified = r.user()["id"]
    with r.connect() as c:
        c.execute(
            "update auth.users set created_at=clock_timestamp()-interval '120 days' where id=%s",
            (recently_verified,),
        )
    recent = metrics(cutoff, datetime.now(timezone.utc) + timedelta(seconds=1))
    assert recent["new_users"] == baseline["new_users"] + 1, recent
    with r.connect() as c:
        joined, historical = c.execute(
            "select joined_at,baseline from administration.population where subject=%s",
            (recently_verified,),
        ).fetchone()
        assert joined >= cutoff and historical is False
    baseline = recent
    new = r.user()["id"]
    observed = metrics(cutoff, datetime.now(timezone.utc) + timedelta(seconds=1))
    assert observed["new_users"] == baseline["new_users"] + 1, observed
    with r.connect() as c:
        before = c.execute(
            "select joined_at from administration.population where subject=%s", (new,)
        ).fetchone()[0]
        c.execute(
            "update auth.users set email_confirmed_at=clock_timestamp() where id=%s",
            (new,),
        )
    again = metrics(cutoff, datetime.now(timezone.utc) + timedelta(seconds=1))
    assert again["new_users"] == observed["new_users"], again
    with r.connect() as c:
        assert (
            c.execute(
                "select joined_at from administration.population where subject=%s",
                (new,),
            ).fetchone()[0]
            == before
        )
    with r.connect("usage_executor") as c:
        c.execute(
            "select public.subscription_deletion_prepare(%s,%s)", (new, str(uuid4()))
        )
    removed = metrics(cutoff, datetime.now(timezone.utc) + timedelta(seconds=1))
    assert removed["total_users"] == observed["total_users"] - 1, (observed, removed)
    with r.connect() as c:
        assert c.execute(
            "select removed_at is not null from administration.population where subject=%s",
            (new,),
        ).fetchone()[0]
    historic = metrics(cutoff - timedelta(days=2), cutoff - timedelta(days=1))
    assert (
        historic["total_users"] is None and historic["daily_registrations"] == []
    ), historic
    results.append(
        {
            "scenario": "population_baseline_no_fabricated_history_verified_uuid_registration_email_reverification_dedup_deletion_removal_and_unknown_coverage",
            "passed": True,
        }
    )
