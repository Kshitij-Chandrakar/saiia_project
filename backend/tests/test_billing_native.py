"""Synthetic Razorpay protocol + real JWT, C13 authority and native PostgreSQL."""

import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import test_subscription_integration_native as fixtures
from app.commercial.billing_service import BillingService
from app.commercial.catalog_store import CatalogStoreError
from app.commercial.razorpay import PaymentUnavailable, signature
from test_catalog_store_native import ROOT
from test_draft_api_native import create, headers
from test_pricing_native import definition, publish
from test_usage_store_native import actor

case = fixtures.case
database = fixtures.database
f1_install = fixtures.f1_install
f2_install = fixtures.f2_install
install = fixtures.install
pricing = fixtures.pricing
upgraded = fixtures.upgraded
usage = fixtures.usage
integration = fixtures.integration
SECRET = "synthetic-webhook-secret"


class Provider:
    key = "rzp_test_synthetic"

    def __init__(self):
        self.orders = {}
        self.charges = {}
        self.bills = {}
        self.calls = 0
        self.timeout = ""
        self.plans = {}

    def plan(self, key):
        return self.plans[key]

    def create(self, op):
        self.calls += 1
        if self.timeout == "before":
            raise TimeoutError()
        sub = {
            "id": "sub_" + uuid4().hex,
            "entity": "subscription",
            "plan_id": op["provider_plan"],
            "quantity": 1,
            "total_count": op["total_count"],
            "notes": {"operation_id": op["operation_id"]},
            "status": "created",
            "offer_id": None,
        }
        self.orders[sub["id"]] = sub
        if self.timeout == "after":
            raise TimeoutError()
        return sub

    def subscription(self, key):
        return self.orders[key]

    def find(self, op):
        return [
            o
            for o in self.orders.values()
            if o["notes"]["operation_id"] == op["operation_id"]
        ]

    def invoices(self, key):
        return self.bills.get(key, [])

    def payment(self, key):
        return self.charges[key]

    def callback(self, sub, payment, supplied):
        return signature(SECRET, (payment + "|" + sub).encode(), supplied)

    def cancel(self, key):
        self.orders[key]["status"] = "cancelled"
        return self.orders[key]

    def pay(self, key, status="captured", offset=0):
        sub = self.orders[key]
        plan = self.plans[sub["plan_id"]]
        amount = plan["item"]["amount"]
        inv = "inv_" + uuid4().hex
        order = "order_" + uuid4().hex
        p = {
            "id": "pay_" + uuid4().hex,
            "entity": "payment",
            "order_id": order,
            "status": status,
            "captured": status == "captured",
            "amount": amount,
            "currency": "INR",
            "amount_refunded": 0,
            "invoice_id": inv,
            "created_at": int(time.time()),
        }
        self.charges[p["id"]] = p
        if status == "captured":
            sub["status"] = "active"
            self.bills.setdefault(key, []).append(
                {
                    "id": inv,
                    "entity": "invoice",
                    "subscription_id": key,
                    "order_id": order,
                    "payment_id": p["id"],
                    "status": "paid",
                    "amount": amount,
                    "amount_paid": amount,
                    "amount_due": 0,
                    "currency": "INR",
                    "partial_payment": False,
                    "line_items": [
                        {
                            "type": "plan",
                            "quantity": 1,
                            "amount": amount,
                            "currency": "INR",
                        }
                    ],
                    "billing_start": int(time.time()) + offset,
                    "billing_end": int(time.time()) + 2592000 + offset,
                }
            )
        return p


@pytest.fixture
def billing(integration):
    u = integration
    db = u["db"]
    if not db.rows("select 1 from pg_tables where tablename='billing_operations'"):
        import subprocess

        applied = subprocess.run(
            [*db.args, "-v", "VERBOSITY=default"],
            input=(
                ROOT / "supabase/migrations/20261025020000_razorpay_checkout.sql"
            ).read_text(),
            encoding="utf-8",
            check=False,
            capture_output=True,
            env=db.env,
            timeout=25,
        )
        assert applied.returncode == 0, applied.stderr
    if not db.rows("select 1 from pg_tables where tablename='billing_payable_quotes'"):
        db.run(
            (
                ROOT / "supabase/migrations/20261025030000_billing_gst_payable.sql"
            ).read_text()
        )
    raw = definition("plus")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    provider = Provider()
    service = BillingService(
        lambda: u["connect"]("usage_binding_executor"),
        provider,
        merchant="acc_synthetic",
        webhook_secrets=(SECRET,),
        renewal="automatic",
        enabled=True,
        total_policy_ref="billing.inr.gst18.v1",
        plan_mappings={
            raw["terms"]["prices"][0]["price_id"]: {
                "provider_plan": "plan_synthetic",
                "total_count": 12,
            }
        },
    )
    provider.plans["plan_synthetic"] = {
        "id": "plan_synthetic",
        "entity": "plan",
        "period": "monthly",
        "interval": 1,
        "item": {"amount": 47082, "currency": "INR"},
    }
    u["client"].app.state.billing = service
    u.update(
        billing=service,
        provider=provider,
        checkout={
            "operation_id": str(uuid4()),
            "offer_version_id": offer,
            "price_id": raw["terms"]["prices"][0]["price_id"],
        },
    )
    yield u
    u["client"].app.state.billing = None


def ready(u):
    s, a = u["billing"], actor(u["account"])
    op = s.prepare(a, u["checkout"])
    return s.start(a, op["operation_id"], True, op["quote_id"])


def signed(u, payment):
    event = {
        "entity": "event",
        "account_id": "acc_synthetic",
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": next(
                    sub
                    for sub in u["provider"].orders.values()
                    if any(
                        i["payment_id"] == payment["id"]
                        for i in u["provider"].bills.get(sub["id"], [])
                    )
                )
            },
            "payment": {"entity": payment},
        },
    }
    raw = json.dumps(event, separators=(",", ":")).encode()
    return raw, hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def test_checkout_verified_entitlement_and_duplicate_webhook(billing):
    u = billing
    op = ready(u)
    assert op["state"] == "ready" and op["amount_minor"] == "47082"
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"
    payment = u["provider"].pay(op["provider_id"])
    raw, sig = signed(u, payment)
    for _ in range(2):
        response = u["client"].post(
            "/api/billing/webhook", content=raw, headers={"x-razorpay-signature": sig}
        )
        assert response.status_code == 200, response.text
    result = u["client"].get("/api/account/subscription", headers=headers(u["account"]))
    assert result.status_code == 200 and result.json()["plan"]["name"] == "Plus"
    assert u["db"].rows(
        f"select count(*) n from subscription_payment_receipts where account_id='{u['account']}'"
    ) == [{"n": 1}]


@pytest.mark.parametrize(
    "key,value",
    [
        ("amount_minor", "1"),
        ("base_amount_minor", "1"),
        ("tax_rate_basis_points", "0"),
        ("tax_amount_minor", "0"),
        ("total_amount_minor", "1"),
        ("currency", "USD"),
        ("account_id", str(uuid4())),
        ("plan_id", str(uuid4())),
    ],
)
def test_forged_inputs(billing, key, value):
    u = billing
    response = u["client"].post(
        "/api/billing/checkout",
        headers=headers(u["account"]),
        json={**u["checkout"], key: value},
    )
    assert response.status_code == 400
    assert u["provider"].calls == 0


def test_two_tabs_and_concurrent_dispatch(billing):
    u = billing
    a = actor(u["account"])
    s = u["billing"]
    with ThreadPoolExecutor(4) as pool:
        ops = list(
            pool.map(
                lambda _: s.prepare(a, {**u["checkout"], "operation_id": str(uuid4())}),
                range(4),
            )
        )
    assert len({o["operation_id"] for o in ops}) == 1
    with ThreadPoolExecutor(4) as pool:
        list(
            pool.map(
                lambda _: s.start(a, ops[0]["operation_id"], True, ops[0]["quote_id"]),
                range(4),
            )
        )
    assert u["provider"].calls == 1


@pytest.mark.parametrize("when", ["before", "after"])
def test_create_uncertainty_never_redispatches(billing, when):
    u = billing
    u["provider"].timeout = when
    op = ready(u)
    for _ in range(2):
        op = u["billing"].start(
            actor(u["account"]), op["operation_id"], True, op["quote_id"]
        )
    assert u["provider"].calls == 1
    assert op["state"] == ("uncertain" if when == "before" else "ready")


def test_signatures_state_binding_and_cross_account(billing):
    u = billing
    op = ready(u)
    u["provider"].pay(op["provider_id"], status="authorized")
    raw, sig = b"{}", "0" * 64
    for data, proof in [(raw + b" ", sig), (raw, "0" * 64), (b"{}", "")]:
        assert (
            u["client"]
            .post(
                "/api/billing/webhook",
                content=data,
                headers={"x-razorpay-signature": proof},
            )
            .status_code
            == 503
        )
    assert (
        u["billing"].status(actor(u["account"]), op["operation_id"])["state"] == "ready"
    )
    assert (
        u["client"]
        .get(
            "/api/billing/status",
            params={"operation_id": op["operation_id"]},
            headers=headers(str(uuid4())),
        )
        .status_code
        == 403
    )
    assert (
        u["client"].post("/api/billing/webhook", content=b"x" * 131073).status_code
        == 413
    )


def test_concurrent_verify_webhook_recovery_and_crash(billing, monkeypatch):
    u = billing
    op = ready(u)
    p = u["provider"].pay(op["provider_id"])
    service = u["billing"]
    original = service._call

    def crash(account, action, *args):
        if action == "apply":
            raise RuntimeError("synthetic crash")
        return original(account, action, *args)

    monkeypatch.setattr(service, "_call", crash)
    with pytest.raises(RuntimeError):
        service.status(actor(u["account"]), op["operation_id"])
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"
    monkeypatch.setattr(service, "_call", original)
    raw, sig = signed(u, p)
    callback = {
        "razorpay_subscription_id": op["provider_id"],
        "razorpay_payment_id": p["id"],
        "razorpay_signature": hmac.new(
            SECRET.encode(),
            (p["id"] + "|" + op["provider_id"]).encode(),
            hashlib.sha256,
        ).hexdigest(),
    }
    with ThreadPoolExecutor(3) as pool:
        jobs = [
            pool.submit(service.webhook, raw, sig),
            pool.submit(
                service.callback, actor(u["account"]), op["operation_id"], callback
            ),
            pool.submit(service.sweep),
        ]
        for job in jobs:
            job.result()
    assert (
        service.status(actor(u["account"]), op["operation_id"])["state"] == "confirmed"
    )
    assert u["db"].rows(
        f"select count(*) n from subscription_payment_receipts where account_id='{u['account']}'"
    ) == [{"n": 1}]


def test_default_off_and_live_key(billing):
    from app.commercial.razorpay import RazorpaySubscriptions

    with pytest.raises(PaymentUnavailable):
        RazorpaySubscriptions("rzp_live_forbidden", "secret")
    u = billing
    u["billing"].enabled = False
    assert (
        u["client"]
        .post(
            "/api/billing/checkout", json=u["checkout"], headers=headers(u["account"])
        )
        .status_code
        == 503
    )


def test_renewal_out_of_order_and_cancel_retains_paid_access(billing):
    u = billing
    op = ready(u)
    first = u["provider"].pay(op["provider_id"])
    u["billing"].status(actor(u["account"]), op["operation_id"])
    second = u["provider"].pay(op["provider_id"], offset=2592000)
    raw, sig = signed(u, second)
    u["billing"].webhook(raw, sig)
    before = u["subscription"].current(actor(u["account"]))["plan"]
    raw, sig = signed(u, first)
    u["billing"].webhook(raw, sig)
    assert u["subscription"].current(actor(u["account"]))["plan"] == before
    result = u["billing"].cancel(actor(u["account"]), op["operation_id"])
    assert result["cancel_requested"] and result["provider_state"] == "cancelled"
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"
    assert u["db"].rows(
        f"select count(*) n from subscription_scheduled_changes where account_id='{u['account']}'"
    ) == [{"n": 1}]


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 1),
        ("currency", "USD"),
        ("invoice_id", "inv_forged"),
        ("order_id", "order_forged"),
    ],
)
def test_provider_binding_mismatch_never_grants(billing, field, value):
    u = billing
    op = ready(u)
    p = u["provider"].pay(op["provider_id"])
    p[field] = value
    with pytest.raises(PaymentUnavailable):
        u["billing"].status(actor(u["account"]), op["operation_id"])
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"


def test_explicit_recurring_consent_and_mandate_limit(billing):
    u = billing
    prepared = u["billing"].prepare(actor(u["account"]), u["checkout"])
    response = u["client"].post(
        "/api/billing/start",
        headers=headers(u["account"]),
        json={"operation_id": prepared["operation_id"]},
    )
    assert response.status_code == 400 and u["provider"].calls == 0
    u["billing"].plan_mappings[u["checkout"]["price_id"]]["total_count"] = 13
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    u["subscription"].current(actor(other), bootstrap=True)
    with pytest.raises(CatalogStoreError):
        u["billing"].prepare(
            actor(other), {**u["checkout"], "operation_id": str(uuid4())}
        )
    assert u["provider"].calls == 0


def test_yearly_five_cycles_and_fresh_consent_after_completion(billing):
    u = billing
    yearly = definition("pro")
    assert create(u["client"], yearly).status_code == 200
    offer = publish(u["client"], yearly)["receipt"]["offer_version_id"]
    price = yearly["terms"]["prices"][1]
    u["billing"].plan_mappings[price["price_id"]] = {
        "provider_plan": "plan_year",
        "total_count": 5,
    }
    u["provider"].plans["plan_year"] = {
        "id": "plan_year",
        "entity": "plan",
        "period": "yearly",
        "interval": 1,
        "item": {"amount": 766882, "currency": "INR"},
    }
    request = {
        "operation_id": str(uuid4()),
        "offer_version_id": offer,
        "price_id": price["price_id"],
    }
    op = u["billing"].prepare(actor(u["account"]), request)
    assert op["total_count"] == 5 and op["interval"] == "year"
    op = u["billing"].start(
        actor(u["account"]), op["operation_id"], True, op["quote_id"]
    )
    u["provider"].pay(op["provider_id"])
    u["billing"].status(actor(u["account"]), op["operation_id"])
    u["provider"].orders[op["provider_id"]]["status"] = "completed"
    u["billing"].status(actor(u["account"]), op["operation_id"])
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Pro"
    assert u["provider"].calls == 1
    # Owner-only clock/fault fixture; never production API or commercial behavior.
    u["db"].run(
        f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 day',revision=revision+1 where account_id='{u['account']}'; update subscription_scheduled_changes set effective_at=clock_timestamp()-interval '1 day' where account_id='{u['account']}'"
    )
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"
    assert (
        u["billing"].status(actor(u["account"]), op["operation_id"])["state"]
        == "expired"
    )
    new = u["billing"].prepare(
        actor(u["account"]), {**request, "operation_id": str(uuid4())}
    )
    assert new["state"] == "prepared" and new["operation_id"] != op["operation_id"]
    assert u["provider"].calls == 1


def test_restricted_billing_pool_and_default_off(billing):
    from types import SimpleNamespace

    from app.commercial.billing_database import BillingDatabase

    u = billing
    config = SimpleNamespace(
        BILLING_DSN=f"host=127.0.0.1 port={u['db'].port} dbname=postgres user=usage_binding_executor sslmode=disable",
        BILLING_ENABLED="true",
        BILLING_RENEWAL="automatic",
        BILLING_TOTAL_POLICY_REF="billing.inr.gst18.v1",
        RAZORPAY_TEST_KEY_ID="rzp_test_synthetic",
        RAZORPAY_TEST_KEY_SECRET="synthetic",
        RAZORPAY_TEST_ACCOUNT_ID="acc_synthetic",
        RAZORPAY_TEST_WEBHOOK_SECRET=SECRET,
        RAZORPAY_TEST_PREVIOUS_WEBHOOK_SECRET="",
        RAZORPAY_TEST_PLAN_MAPPINGS="{}",
    )
    runtime = BillingDatabase(config)
    try:
        runtime.start()
        assert runtime._pool is not None and runtime.billing is not None
        conn = runtime.connect()
        assert (
            conn.execute("select current_user").fetchone()[0]
            == "usage_binding_executor"
        )
        conn.rollback()
        conn.close()
    finally:
        runtime.close()
    config.BILLING_ENABLED = "false"
    runtime = BillingDatabase(config)
    runtime.start()
    assert runtime._pool is None


def test_authorization_only_callback_and_server_recovery(billing):
    u = billing
    op = ready(u)
    p = u["provider"].pay(op["provider_id"], status="authorized")
    u["provider"].orders[op["provider_id"]]["status"] = "authenticated"
    proof = {
        "razorpay_subscription_id": op["provider_id"],
        "razorpay_payment_id": p["id"],
        "razorpay_signature": hmac.new(
            SECRET.encode(),
            (p["id"] + "|" + op["provider_id"]).encode(),
            hashlib.sha256,
        ).hexdigest(),
    }
    result = u["billing"].callback(actor(u["account"]), op["operation_id"], proof)
    assert result["state"] == "pending"
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"
    current = u["client"].get("/api/billing/current", headers=headers(u["account"]))
    assert (
        current.status_code == 200
        and current.json()["operation_id"] == op["operation_id"]
    )


def test_retired_offer_rejected_and_accepted_snapshot_preserved(billing):
    u = billing
    op = u["billing"].prepare(actor(u["account"]), u["checkout"])
    u["db"].run(
        f"update catalog_visibility set state='retired',retired_at=clock_timestamp(),revision=revision+1 where offer_version_id='{u['checkout']['offer_version_id']}'"
    )
    assert (
        u["billing"].start(
            actor(u["account"]), op["operation_id"], True, op["quote_id"]
        )["fingerprint"]
        == op["fingerprint"]
    )
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    u["subscription"].current(actor(other), bootstrap=True)
    response = u["client"].post(
        "/api/billing/checkout",
        headers=headers(other),
        json={**u["checkout"], "operation_id": str(uuid4())},
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "billing_terms_unavailable"
    )


def test_wrong_merchant_signed_event_never_trusted(billing):
    u = billing
    op = ready(u)
    payment = u["provider"].pay(op["provider_id"])
    raw, _ = signed(u, payment)
    data = json.loads(raw)
    data["account_id"] = "acc_wrong"
    raw = json.dumps(data).encode()
    proof = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    with pytest.raises(PaymentUnavailable):
        u["billing"].webhook(raw, proof)
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"


@pytest.mark.parametrize(
    "code,index,base,tax,total",
    [
        ("plus", 0, "39900", "7182", "47082"),
        ("plus", 1, "299900", "53982", "353882"),
        ("pro", 0, "89900", "16182", "106082"),
        ("pro", 1, "649900", "116982", "766882"),
    ],
)
def test_gst_exact_public_quote_consent_provider_and_payment(
    billing, code, index, base, tax, total
):
    u = billing
    raw = definition(code)
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    price = raw["terms"]["prices"][index]
    u["billing"].plan_mappings[price["price_id"]] = {
        "provider_plan": "plan_gst",
        "total_count": 12 if index == 0 else 5,
    }
    u["provider"].plans["plan_gst"] = {
        "id": "plan_gst",
        "entity": "plan",
        "period": "monthly" if index == 0 else "yearly",
        "interval": 1,
        "item": {"amount": int(total), "currency": "INR", "tax_rate": None},
    }
    op = u["billing"].prepare(
        actor(u["account"]),
        {
            "operation_id": str(uuid4()),
            "offer_version_id": offer,
            "price_id": price["price_id"],
        },
    )
    assert op["payable"]["base_amount_minor"] == base
    assert op["payable"]["tax_amount_minor"] == tax and op["amount_minor"] == total
    public = u["client"].get("/api/catalog").json()["payable_prices"][price["price_id"]]
    assert public == op["payable"] and public["tax_rate_basis_points"] == "1800"
    assert price["amount_minor"] == base
    before = u["db"].rows(
        f"select document,quote_id from billing_payable_quotes where operation_id='{op['operation_id']}'"
    )
    op = u["billing"].start(
        actor(u["account"]), op["operation_id"], True, op["quote_id"]
    )
    payment = u["provider"].pay(op["provider_id"])
    for _ in range(2):
        event, sig = signed(u, payment)
        u["billing"].webhook(event, sig)
    assert (
        u["subscription"].current(actor(u["account"]))["plan"]["name"] == code.title()
    )
    assert before == u["db"].rows(
        f"select document,quote_id from billing_payable_quotes where operation_id='{op['operation_id']}'"
    )
    assert u["db"].rows(
        f"select count(*) n from subscription_payment_receipts where account_id='{u['account']}'"
    ) == [{"n": 1}]


def test_quote_identity_and_provider_double_tax_are_rejected(billing):
    u = billing
    op = u["billing"].prepare(actor(u["account"]), u["checkout"])
    with pytest.raises(CatalogStoreError):
        u["billing"].start(actor(u["account"]), op["operation_id"], True, "0" * 64)
    assert u["provider"].calls == 0
    u["provider"].plans["plan_synthetic"]["item"]["tax_rate"] = 18
    with pytest.raises(PaymentUnavailable):
        u["billing"].start(
            actor(u["account"]), op["operation_id"], True, op["quote_id"]
        )
    u["provider"].plans["plan_synthetic"]["item"]["tax_rate"] = None
    op = u["billing"].start(
        actor(u["account"]), op["operation_id"], True, op["quote_id"]
    )
    u["provider"].pay(op["provider_id"])
    u["provider"].bills[op["provider_id"]][0]["tax_amount"] = 7182
    with pytest.raises(PaymentUnavailable):
        u["billing"].status(actor(u["account"]), op["operation_id"])
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Free"


def test_legacy_unconsented_review_requires_fresh_gst_quote(billing):
    u = billing
    old = str(uuid4())
    # Owner-only persisted pre-GST fixture: never repriced or backfilled.
    u["db"].run(
        f"insert into billing_operations(operation_id,account_id,offer_version_id,price_id,mode,merchant,provider_plan,total_count,snapshot,fingerprint,amount,currency,interval_unit) select '{old}','{u['account']}',o.offer_version_id,p.price_id,'test','acc_synthetic','plan_synthetic',12,o.canonical_json,o.fingerprint,p.amount_minor,p.currency,p.billing_unit from catalog_offer_versions o join catalog_price_versions p using(offer_version_id) where p.price_id='{u['checkout']['price_id']}'"
    )
    legacy = u["billing"].current(actor(u["account"]))
    assert legacy["review_required"] and legacy["amount_minor"] == "39900"
    with pytest.raises(CatalogStoreError):
        u["billing"].start(actor(u["account"]), old, True, None)
    fresh = u["billing"].prepare(actor(u["account"]), u["checkout"])
    assert fresh["amount_minor"] == "47082" and fresh["quote_id"]
    original = u["db"].rows(
        f"select amount,consent_at,state from billing_operations where operation_id='{old}'"
    )[0]
    assert original == {"amount": 39900, "consent_at": None, "state": "expired"}
    with pytest.raises(CatalogStoreError):
        u["billing"].start(
            actor(u["account"]), fresh["operation_id"], True, "legacy.accepted"
        )
    assert u["provider"].calls == 0


def test_historical_dispatched_mandate_keeps_original_amount_and_consent(billing):
    u = billing
    old = str(uuid4())
    u["db"].run(
        f"insert into billing_operations(operation_id,account_id,offer_version_id,price_id,mode,merchant,provider_plan,total_count,snapshot,fingerprint,amount,currency,interval_unit,consent_at) select '{old}','{u['account']}',o.offer_version_id,p.price_id,'test','acc_synthetic','plan_synthetic',12,o.canonical_json,o.fingerprint,p.amount_minor,p.currency,p.billing_unit,'2026-01-01Z' from catalog_offer_versions o join catalog_price_versions p using(offer_version_id) where p.price_id='{u['checkout']['price_id']}'"
    )
    before = u["billing"]._operation(u["account"], old)
    subscription = u["provider"].create(before)
    u["db"].run(
        f"update billing_operations set state='ready',provider_id='{subscription['id']}' where operation_id='{old}'"
    )
    u["provider"].plans["plan_synthetic"]["item"]["amount"] = 39900
    u["provider"].pay(subscription["id"])
    for _ in range(2):
        result = u["billing"].status(actor(u["account"]), old)
        assert result["amount_minor"] == "39900" and result["payable"] is None
    after = u["billing"]._operation(u["account"], old)
    for field in ("snapshot", "fingerprint", "amount", "consent_at"):
        assert after[field] == before[field]
    assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"


def test_fractional_future_paise_requires_rounding_policy(billing):
    from app.commercial.payable import payable

    u = billing
    snapshot = u["billing"]._operation(
        u["account"],
        u["billing"].prepare(actor(u["account"]), u["checkout"])["operation_id"],
    )
    raw = json.loads(snapshot["snapshot"])
    next(
        p for p in raw["terms"]["prices"] if p["price_id"] == u["checkout"]["price_id"]
    )["amount_minor"] = "1"
    from app.commercial import catalog_contract as c

    raw["eligible_model_keys"] = ()
    changed = c.OfferSnapshot.model_validate(raw)
    with pytest.raises(ValueError, match="rounding"):
        payable(changed, u["checkout"]["price_id"])


def test_native_website_flow(billing):
    import os
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    u = billing
    pro = definition("pro")
    assert create(u["client"], pro).status_code == 200
    pro_id = publish(u["client"], pro)["receipt"]["offer_version_id"]
    visual_ids = [
        u["document"]["offer_version_id"],
        u["checkout"]["offer_version_id"],
        pro_id,
    ]

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            raw = self.rfile.read(int(self.headers.get("content-length", "0")))
            if self.path == "/__synthetic_pay":
                order = json.loads(raw)["order_id"]
                payment = u["provider"].pay(order)
                payload = json.dumps(
                    {
                        "razorpay_subscription_id": order,
                        "razorpay_payment_id": payment["id"],
                        "razorpay_signature": hmac.new(
                            SECRET.encode(),
                            (payment["id"] + "|" + order).encode(),
                            hashlib.sha256,
                        ).hexdigest(),
                    }
                ).encode()
                status = 200
            else:
                response = u["client"].request(
                    self.command,
                    self.path,
                    content=raw,
                    headers={
                        k: v
                        for k, v in self.headers.items()
                        if k.lower() not in ("host", "content-length", "connection")
                    },
                )
                payload, status = response.content, response.status_code
                if self.path == "/api/catalog" and status == 200:
                    data = response.json()
                    data["offers"] = sorted(
                        (
                            o
                            for o in data["offers"]
                            if o["offer_version_id"] in visual_ids
                        ),
                        key=lambda o: visual_ids.index(o["offer_version_id"]),
                    )
                    payload = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = dispatch
        do_POST = dispatch

    server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {
            **os.environ,
            "BILLING_BROWSER_NATIVE": json.dumps(
                {
                    "url": f"http://127.0.0.1:{server.server_port}",
                    "token": headers(u["account"])["Authorization"][7:],
                    "account": u["account"],
                    "offer": u["checkout"]["offer_version_id"],
                    "price": u["checkout"]["price_id"],
                }
            ),
        }
        result = subprocess.run(
            [
                "cmd",
                "/c",
                "npx",
                "playwright",
                "test",
                "--config",
                "playwright.catalog.config.js",
                "billing.integration.spec.js",
            ],
            cwd=ROOT / "frontend",
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=100,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        desktop = subprocess.run(
            ["node", "tests/catalog/billing-desktop.verify.cjs"],
            cwd=ROOT / "frontend",
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        assert desktop.returncode == 0, desktop.stdout + desktop.stderr
        assert u["subscription"].current(actor(u["account"]))["plan"]["name"] == "Plus"
        assert u["provider"].calls == 1
    finally:
        server.shutdown()
        server.server_close()
