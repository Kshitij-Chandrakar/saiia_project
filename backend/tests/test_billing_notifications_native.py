"""Explicit disposable native C12 tests. All provider delivery is substituted."""

import base64
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
import test_billing_native as fixtures
from app.commercial.billing_admin import BillingAdmin, router
from app.config import settings
from app.email.billing import (
    BillingNotifications,
    SendNotAccepted,
    render_billing_email,
)
from test_catalog_store_native import MANAGER, ROOT
from test_draft_api_native import actor

database = fixtures.database
case = fixtures.case
f1_install = fixtures.f1_install
f2_install = fixtures.f2_install
install = fixtures.install
pricing = fixtures.pricing
upgraded = fixtures.upgraded
usage = fixtures.usage
integration = fixtures.integration
billing = fixtures.billing


class MailProvider:
    def __init__(self, failure=None):
        self.requests = []
        self.failure = failure

    def send_email(self, request):
        self.requests.append(request)
        if self.failure:
            raise self.failure()
        return {
            "state": "accepted",
            "provider": "resend",
            "message_id": str(uuid5(NAMESPACE_URL, request.idempotency_key)),
        }


@pytest.fixture
def mail(billing, monkeypatch):
    u = billing
    db = u["db"]
    monkeypatch.setattr(
        settings, "RESEND_BILLING_WEBHOOK_SCOPE", "synthetic-c12-resend"
    )
    monkeypatch.setattr(settings, "BILLING_ADMIN_ENABLED", "true")
    monkeypatch.setattr(settings, "BILLING_NOTIFICATIONS_ENABLED", "true")
    db.run("alter table auth.users add column if not exists email text")
    if not db.rows(
        "select 1 from pg_tables where tablename='billing_notification_sources'"
    ):
        db.run("create extension if not exists pgcrypto with schema extensions")
        for filename in (
            "20260904143000_add_outbound_email_events.sql",
            "20260922120000_add_marketing_email_event_type.sql",
            "20260924120000_fix_outbound_email_event_claim_ambiguous_user_id.sql",
            "20261026010000_billing_notifications_admin.sql",
            "20261027010000_resend_delivery_callbacks.sql",
        ):
            db.run((ROOT / "supabase/migrations" / filename).read_text())
        u["client"].app.include_router(router)
    db.run(
        f"update auth.users set email='billing@example.invalid',email_confirmed_at=clock_timestamp() where id='{u['account']}'"
    )
    provider = MailProvider()
    notifications = BillingNotifications(
        lambda: u["connect"]("usage_binding_executor"), provider
    )
    admin = BillingAdmin(
        lambda: u["connect"]("usage_binding_executor"), u["billing"], notifications
    )
    u["client"].app.state.billing_admin = admin
    u["client"].app.state.billing_notifications = notifications
    u.update(mail=notifications, mail_provider=provider, admin=admin)
    return u


def paid(u, offset=0, op=None):
    op = op or fixtures.ready(u)
    payment = u["provider"].pay(op["provider_id"], offset=offset)
    raw, sig = fixtures.signed(u, payment)
    u["billing"].webhook(raw, sig)
    return op, raw, sig


def sources(u):
    return u["db"].rows(
        f"select id,kind,delivery_state,attempts from billing_notification_sources where account_id='{u['account']}' order by created_at"
    )


def grant(u):
    u["db"].run(
        f"insert into subscription_admin_permissions(subject_id,permission,active,approved_by,reason) values('{MANAGER}','billing.read',true,'{MANAGER}','synthetic test'),('{MANAGER}','billing.manage',true,'{MANAGER}','synthetic test') on conflict(subject_id,permission) do update set active=true,revision=subscription_admin_permissions.revision+1"
    )


def review(u, action, target):
    return u["admin"].call(
        actor(MANAGER),
        "review",
        u["account"],
        {"action": action, "target": target, "operation_id": str(uuid4())},
    )


def test_payment_renewal_duplicate_recovery(mail):
    u = mail
    op, raw, sig = paid(u)
    u["billing"].webhook(raw, sig)
    u["billing"].status(actor(u["account"]), op["operation_id"])
    assert [r["kind"] for r in sources(u)] == ["billing_payment"]
    # A new worker instance recovers an outbox not dispatched by the old process.
    restarted = BillingNotifications(
        lambda: u["connect"]("usage_binding_executor"), u["mail_provider"]
    )
    assert restarted.run()["accepted"] == 1
    assert sources(u)[0]["delivery_state"] == "accepted"
    assert u["mail_provider"].requests[0].recipient_email == "billing@example.invalid"
    assert "INR 470.82" in u["mail_provider"].requests[0].text_body
    paid(u, offset=1, op=op)
    assert [r["kind"] for r in sources(u)] == ["billing_payment", "billing_renewal"]
    restarted.run()
    assert len({r.idempotency_key for r in u["mail_provider"].requests}) == 2


def test_timeout_is_unknown_not_automatic_retry(mail):
    u = mail
    paid(u)
    u["mail_provider"].failure = TimeoutError
    u["mail"].run()
    u["mail"].run()
    assert sources(u)[0]["delivery_state"] == "unknown"
    assert len(u["mail_provider"].requests) == 1
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"


def test_definite_failure_retry_exhaustion(mail):
    u = mail
    paid(u)
    u["mail_provider"].failure = SendNotAccepted
    for _ in range(4):
        u["mail"].run()
        u["db"].run(
            "update billing_notification_sources set next_attempt_at=clock_timestamp()-interval '1 second'"
        )
    assert sources(u)[0]["attempts"] == 3
    assert sources(u)[0]["delivery_state"] == "failed"
    assert len(u["mail_provider"].requests) == 3


def test_crash_after_acceptance_requires_reconciliation(mail, monkeypatch):
    u = mail
    paid(u)
    original = u["mail"].call

    def crash(action, *args):
        if action == "complete":
            raise RuntimeError("synthetic crash")
        return original(action, *args)

    monkeypatch.setattr(u["mail"], "call", crash)
    with pytest.raises(RuntimeError):
        u["mail"].run()
    monkeypatch.setattr(u["mail"], "call", original)
    u["db"].run(
        "update outbound_email_events set lease_expires_at=clock_timestamp()-interval '1 second' where status='sending'"
    )
    u["mail"].run()
    assert sources(u)[0]["delivery_state"] == "unknown"
    assert len(u["mail_provider"].requests) == 1


def test_unverified_recipient_defers(mail):
    u = mail
    paid(u)
    u["db"].run(
        f"update auth.users set email_confirmed_at=null where id='{u['account']}'"
    )
    u["mail"].run()
    assert not u["mail_provider"].requests
    assert sources(u)[0]["delivery_state"] == "queued"


def test_pending_cancel_never_confirms_email(mail):
    u = mail
    op, _, _ = paid(u)
    u["db"].run(
        f"update billing_operations set cancel_requested=true,provider_state='active' where operation_id='{op['operation_id']}'"
    )
    assert not any(r["kind"] == "billing_cancellation" for r in sources(u))
    u["provider"].orders[op["provider_id"]]["status"] = "cancelled"
    u["billing"].reconcile(u["account"], op["operation_id"])
    assert any(r["kind"] == "billing_cancellation" for r in sources(u))
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"


def test_authoritative_expiry_enqueues_access_end(mail):
    u = mail
    paid(u)
    u["db"].run(
        f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 second',revision=revision+1 where account_id='{u['account']}'"
    )
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"
    assert any(r["kind"] == "billing_access_end" for r in sources(u))


def test_admin_denial_is_durable_and_inspection_is_local(mail):
    u = mail
    paid(u)
    assert u["admin"].call(actor(MANAGER), "inspect", u["account"]) == {
        "error": "denied"
    }
    assert u["db"].rows(
        "select outcome from billing_admin_audit order by id desc limit 1"
    ) == [{"outcome": "denied"}]
    grant(u)
    before = u["provider"].calls
    snapshot = u["admin"].call(actor(MANAGER), "inspect", u["account"])
    assert snapshot["operations"] and u["provider"].calls == before
    assert "billing@example.invalid" not in json.dumps(snapshot)
    response = u["client"].get("/api/admin/billing/" + u["account"])
    assert response.status_code == 401


def test_admin_confirmation_tamper_stale_and_duplicate(mail):
    u = mail
    op, _, _ = paid(u)
    grant(u)
    confirmation = review(u, "reconcile", op["operation_id"])
    document = {k: v for k, v in confirmation.items() if k != "action"} | {
        "confirm": True
    }
    assert u["admin"].call(
        actor(MANAGER), "retry_notification", u["account"], document
    ) == {"error": "conflict"}
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: u["admin"].call(
                    actor(MANAGER), "reconcile", u["account"], document
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert len(u["db"].rows("select id from billing_admin_commands")) == 1
    stale = review(u, "reconcile", op["operation_id"])
    u["db"].run(
        f"update billing_operations set cancel_requested=true where operation_id='{op['operation_id']}'"
    )
    assert u["admin"].call(
        actor(MANAGER),
        "reconcile",
        u["account"],
        {k: v for k, v in stale.items() if k != "action"} | {"confirm": True},
    ) == {"error": "conflict"}
    u["admin"].run()
    assert u["db"].rows("select state from billing_admin_commands") == [
        {"state": "confirmed"}
    ]


def test_signed_delivery_dedup_and_tamper(mail):
    u = mail
    paid(u)
    u["mail"].run()
    message_id = str(uuid5(NAMESPACE_URL, "billing:" + sources(u)[0]["id"]))
    raw = json.dumps(
        {
            "type": "email.delivered",
            "created_at": "2026-10-27T00:00:00Z",
            "data": {"email_id": message_id},
        }
    ).encode()
    key = b"synthetic delivery secret 32 bytes"
    secret = "whsec_" + base64.b64encode(key).decode()
    now = str(int(time.time()))
    sig = base64.b64encode(
        hmac.new(
            key, b"msg_synthetic." + now.encode() + b"." + raw, hashlib.sha256
        ).digest()
    ).decode()
    header = {
        "svix-id": "msg_synthetic",
        "svix-timestamp": now,
        "svix-signature": "v1," + sig,
    }
    for _ in range(2):
        u["mail"].delivery(raw, header, secret)
    assert sources(u)[0]["delivery_state"] == "delivered"
    assert (
        len(u["db"].rows("select event_hash from billing_email_delivery_events")) == 1
    )
    with pytest.raises(ValueError):
        u["mail"].delivery(raw + b" ", header, secret)


def test_template_escapes_and_formats_exact_money():
    template = render_billing_email(
        "billing_payment",
        {
            "plan": '<script>alert("x")</script>',
            "currency": "INR",
            "amount_minor": "766882",
            "interval": "year",
            "period_end": "2027-10-26T00:00:00+05:30",
        },
    )
    assert "INR 7,668.82" in template.text
    assert "<script>" not in template.html
    assert "&lt;script&gt;" in template.html
    assert "GST tax invoice" in template.text


def test_recorded_payment_crash_recovers_one_outbox(mail, monkeypatch):
    u = mail
    op = fixtures.ready(u)
    original = u["billing"]._call

    def crash(account, action, *args):
        if action == "apply":
            raise RuntimeError("synthetic crash before application")
        return original(account, action, *args)

    monkeypatch.setattr(u["billing"], "_call", crash)
    with pytest.raises(RuntimeError):
        paid(u, op=op)
    assert sources(u) == []
    monkeypatch.setattr(u["billing"], "_call", original)
    op = u["db"].rows(
        f"select operation_id from billing_operations where account_id='{u['account']}'"
    )[0]
    u["billing"].reconcile(u["account"], op["operation_id"])
    assert len(sources(u)) == 1
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"


def test_admin_worker_failure_and_revocation_audit(mail, monkeypatch):
    u = mail
    op, _, _ = paid(u)
    grant(u)
    confirmation = review(u, "reconcile", op["operation_id"])
    doc = {k: v for k, v in confirmation.items() if k != "action"} | {"confirm": True}
    u["admin"].call(actor(MANAGER), "reconcile", u["account"], doc)

    def fail(*args):
        raise TimeoutError()

    monkeypatch.setattr(u["billing"], "reconcile", fail)
    u["admin"].run()
    assert u["db"].rows(
        f"select outcome from billing_admin_audit where operation_id='{doc['operation_id']}' order by id desc limit 1"
    ) == [{"outcome": "unknown"}]
    u["db"].run(
        f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id='{MANAGER}' and permission='billing.manage'"
    )
    assert u["admin"].call(actor(MANAGER), "reconcile", u["account"], doc) == {
        "error": "denied"
    }


def test_admin_notification_retry_and_unknown_refusal(mail):
    u = mail
    paid(u)
    grant(u)
    u["mail_provider"].failure = SendNotAccepted
    u["mail"].run()
    target = sources(u)[0]["id"]
    confirmation = review(u, "retry_notification", target)
    doc = {k: v for k, v in confirmation.items() if k != "action"} | {"confirm": True}
    assert (
        u["admin"].call(actor(MANAGER), "retry_notification", u["account"], doc)[
            "state"
        ]
        == "requested"
    )
    u["mail_provider"].failure = None
    u["admin"].run()
    assert sources(u)[0]["delivery_state"] == "accepted"
    assert sources(u)[0]["attempts"] == 2


def test_cross_account_and_forged_admin_role_denied(mail):
    from test_draft_api_native import headers

    u = mail
    paid(u)
    response = u["client"].get(
        "/api/admin/billing/" + u["account"],
        headers=headers(u["account"], app_metadata={"role": "billing.manage"}),
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    op = u["db"].rows(
        f"select operation_id from billing_operations where account_id='{u['account']}'"
    )[0]
    response = u["client"].get(
        "/api/billing/status?operation_id=" + op["operation_id"],
        headers=headers(MANAGER),
    )
    assert response.status_code == 403


def test_unknown_notification_retry_refused_and_closed_tables(mail):
    u = mail
    paid(u)
    grant(u)
    u["mail_provider"].failure = TimeoutError
    u["mail"].run()
    confirmation = review(u, "retry_notification", sources(u)[0]["id"])
    doc = {k: v for k, v in confirmation.items() if k != "action"} | {"confirm": True}
    assert u["admin"].call(actor(MANAGER), "retry_notification", u["account"], doc) == {
        "error": "conflict"
    }
    for table in (
        "billing_notification_sources",
        "billing_admin_commands",
        "billing_admin_reviews",
        "billing_admin_audit",
        "outbound_email_events",
    ):
        assert u["db"].rows(
            f"select has_table_privilege('usage_binding_executor','public.{table}','SELECT,INSERT,UPDATE,DELETE') as direct"
        ) == [{"direct": False}]
