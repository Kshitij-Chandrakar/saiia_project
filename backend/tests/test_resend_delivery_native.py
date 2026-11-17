"""Signed fixtures only; restricted native PostgreSQL, no external transport."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
import test_billing_notifications_native as f
from app.config import settings
from app.email.delivery import DeliveryConflict
from svix.webhooks import Webhook
from test_draft_api_native import actor

# Reuse the actual isolated billing/email fixture chain.
database = f.database
case = f.case
f1_install = f.f1_install
f2_install = f.f2_install
install = f.install
pricing = f.pricing
upgraded = f.upgraded
usage = f.usage
integration = f.integration
billing = f.billing
mail = f.mail
SECRET = "whsec_" + base64.b64encode(b"synthetic callback signing key 32").decode()


def signed(message, kind="email.delivered", identity=None, timestamp=None):
    timestamp = timestamp or datetime.now(timezone.utc)
    raw = json.dumps(
        {
            "type": kind,
            "created_at": "2026-10-27T00:00:00Z",
            "data": {"email_id": message, "to": ["ignored@example.invalid"]},
        }
    ).encode()
    identity = identity or "msg_" + uuid4().hex
    return raw, {
        "svix-id": identity,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": Webhook(SECRET).sign(identity, timestamp, raw.decode()),
    }


def sent(u):
    f.paid(u)
    u["mail"].run()
    return str(uuid5(NAMESPACE_URL, "billing:" + f.sources(u)[0]["id"]))


def deliver(u, message, kind="email.delivered", identity=None):
    raw, h = signed(message, kind, identity)
    return u["mail"].delivery(raw, h, SECRET)


def test_valid_concurrent_duplicate_conflict_history_admin(mail):
    u = mail
    message = sent(u)
    raw, h = signed(message)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(lambda _: u["mail"].delivery(raw, h, SECRET), range(3)))
    assert f.sources(u)[0]["delivery_state"] == "delivered"
    assert u["db"].rows("select count(*) as n from billing_email_delivery_events") == [
        {"n": 1}
    ]
    raw2, h2 = signed(message, "email.bounced", h["svix-id"])
    with pytest.raises(DeliveryConflict):
        u["mail"].delivery(raw2, h2, SECRET)
    for kind in (
        "email.complained",
        "email.sent",
        "email.delivered",
        "email.delivery_delayed",
        "email.bounced",
        "email.failed",
    ):
        deliver(u, message, kind)
    assert f.sources(u)[0]["delivery_state"] == "failed"
    f.grant(u)
    snapshot = u["admin"].call(actor(f.MANAGER), "inspect", u["account"])
    events = snapshot["notifications"][0]["delivery_events"]
    assert len(events) == 7 and all(x["processed_at"] for x in events)
    assert any(x["failure_category"] == "complained" for x in events)
    assert "ignored@example.invalid" not in json.dumps(snapshot)
    assert u["admin"].call(actor(u["account"]), "inspect", u["account"]) == {
        "error": "denied"
    }


@pytest.mark.parametrize(
    "change",
    [
        "signature",
        "missing",
        "stale",
        "future",
        "invalid_time",
        "raw",
        "malformed",
        "oversized",
        "unsupported",
    ],
)
def test_verifier_rejects(mail, change):
    before = mail["db"].rows("select count(*) as n from billing_email_delivery_events")
    raw, h = signed(str(uuid4()))
    if change == "signature":
        h["svix-signature"] = "v1,bm90dmFsaWQ="
    if change == "missing":
        h.pop("svix-id")
    if change == "stale":
        raw, h = signed(
            str(uuid4()), timestamp=datetime.now(timezone.utc) - timedelta(minutes=6)
        )
    if change == "future":
        raw, h = signed(
            str(uuid4()), timestamp=datetime.now(timezone.utc) + timedelta(minutes=6)
        )
    if change == "invalid_time":
        h["svix-timestamp"] = "nan"
    if change == "raw":
        raw += b" "
    if change in ("malformed", "oversized"):
        raw = b"{" if change == "malformed" else b"x" * 131073
        h["svix-signature"] = Webhook(SECRET).sign(
            h["svix-id"],
            datetime.fromtimestamp(int(h["svix-timestamp"]), timezone.utc),
            raw.decode(),
        )
    if change == "unsupported":
        raw, h = signed(str(uuid4()), "email.opened")
    with pytest.raises((ValueError, KeyError)):
        mail["mail"].delivery(raw, h, SECRET)
    assert (
        mail["db"].rows("select count(*) as n from billing_email_delivery_events")
        == before
    )


def test_early_callback_crash_restart_scope_and_expiry(mail, monkeypatch):
    u = mail
    f.paid(u)
    identifier = f.sources(u)[0]["id"]
    message = str(uuid5(NAMESPACE_URL, "billing:" + identifier))
    original = u["mail"].delivery_call

    def crash(action, document=None):
        if action == "process":
            raise RuntimeError("synthetic crash")
        return original(action, document)

    monkeypatch.setattr(u["mail"], "delivery_call", crash)
    raw, h = signed(message)
    with pytest.raises(RuntimeError):
        u["mail"].delivery(raw, h, SECRET)
    monkeypatch.setattr(u["mail"], "delivery_call", original)
    u["mail"].run()  # no binding yet at initial processing; dispatch then binds it
    u["db"].run(
        "update billing_email_delivery_events set next_attempt_at=clock_timestamp()"
    )
    u["mail"].delivery_call("process")
    assert f.sources(u)[0]["delivery_state"] == "delivered"
    monkeypatch.setattr(settings, "RESEND_BILLING_WEBHOOK_SCOPE", "other-environment")
    deliver(u, message, "email.bounced")
    deliver(u, str(uuid4()), "email.failed")
    assert f.sources(u)[0]["delivery_state"] == "delivered"
    u["db"].run(
        "update billing_email_delivery_events set attempts=23,next_attempt_at=clock_timestamp() where processing_state='pending'"
    )
    u["mail"].delivery_call("process")
    assert u["db"].rows(
        "select count(*) as n from billing_email_delivery_events where processing_state='expired'"
    ) == [{"n": 2}]


def test_route_configuration_rotation_and_database_failure(mail, monkeypatch):
    u = mail
    message = sent(u)
    raw, h = signed(message)
    route = "/api/billing/email/events"
    assert u["client"].post(route, content=raw, headers=h).status_code == 503
    monkeypatch.setattr(settings, "RESEND_BILLING_WEBHOOK_SECRET", SECRET)
    assert u["client"].post(route, content=raw, headers=h).status_code == 415
    h["content-type"] = "application/json"
    assert u["client"].post(route, content=raw, headers=h).status_code == 200
    monkeypatch.setattr(
        settings,
        "RESEND_BILLING_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(b"new synthetic key").decode(),
    )
    monkeypatch.setattr(settings, "RESEND_BILLING_WEBHOOK_PREVIOUS_SECRET", SECRET)
    monkeypatch.setattr(
        settings,
        "RESEND_BILLING_WEBHOOK_PREVIOUS_UNTIL",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    assert u["client"].post(route, content=raw, headers=h).status_code == 200
    monkeypatch.setattr(
        settings,
        "RESEND_BILLING_WEBHOOK_PREVIOUS_UNTIL",
        (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )
    assert u["client"].post(route, content=raw, headers=h).status_code == 400
    monkeypatch.setattr(settings, "RESEND_BILLING_WEBHOOK_SECRET", SECRET)

    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable synthetic")

    monkeypatch.setattr(u["mail"], "delivery_call", fail)
    response = u["client"].post(route, content=raw, headers=h)
    assert response.status_code == 503 and "database" not in response.text


def test_database_receipt_failure_rolls_back_and_route_bounds(mail, monkeypatch):
    u = mail
    monkeypatch.setattr(settings, "RESEND_BILLING_WEBHOOK_SECRET", SECRET)
    raw, h = signed(str(uuid4()))
    h["content-type"] = "application/json"
    u["db"].run(
        "create function public.synthetic_receipt_failure() returns trigger language plpgsql as $$begin raise exception 'synthetic storage unavailable'; end$$; create trigger synthetic_receipt_failure before insert on billing_email_delivery_events for each row execute function public.synthetic_receipt_failure()"
    )
    try:
        response = u["client"].post("/api/billing/email/events", content=raw, headers=h)
        assert response.status_code == 503 and "storage" not in response.text
        assert u["db"].rows(
            "select count(*) as n from billing_email_delivery_events where delivery_id='"
            + h["svix-id"]
            + "'"
        ) == [{"n": 0}]
    finally:
        u["db"].run(
            "drop trigger synthetic_receipt_failure on billing_email_delivery_events; drop function public.synthetic_receipt_failure()"
        )
    assert (
        u["client"]
        .post("/api/billing/email/events", content=b"x" * 131073, headers=h)
        .status_code
        == 413
    )
    assert (
        u["client"]
        .post("/api/billing/email/events?extra=1", content=raw, headers=h)
        .status_code
        == 404
    )
    assert (
        u["client"]
        .post(
            "/api/billing/email/events",
            content=raw,
            headers=list(h.items()) + [("svix-id", "duplicate")],
        )
        .status_code
        == 400
    )
