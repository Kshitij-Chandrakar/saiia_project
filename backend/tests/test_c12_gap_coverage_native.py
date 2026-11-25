"""Missing cross-path renewal/outbox assertion; providers remain deterministic."""

from concurrent.futures import ThreadPoolExecutor

import test_billing_notifications_native as f
from test_draft_api_native import actor

# Reuse the accepted restricted PostgreSQL fixture chain, not shared databases.
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


def test_missed_renewal_reconciliation_and_duplicate_delivery_share_one_email(mail):
    u = mail
    op, _, _ = f.paid(u)
    first = u["subscription"].current(actor(u["account"]))
    renewal = u["provider"].pay(op["provider_id"], offset=2592000)
    raw, sig = f.fixtures.signed(u, renewal)
    # No renewal webhook initially: reconciliation discovers the paid invoice.
    u["billing"].reconcile(u["account"], op["operation_id"])
    after = u["subscription"].current(actor(u["account"]))
    assert after["plan"]["valid_until"] != first["plan"]["valid_until"]
    with ThreadPoolExecutor(3) as pool:
        jobs = [
            pool.submit(u["billing"].webhook, raw, sig),
            pool.submit(u["billing"].reconcile, u["account"], op["operation_id"]),
            pool.submit(u["billing"].sweep),
        ]
        for job in jobs:
            job.result()
    assert u["subscription"].current(actor(u["account"]))["plan"] == after["plan"]
    assert [x["kind"] for x in f.sources(u)] == ["billing_payment", "billing_renewal"]
    assert u["db"].rows(
        f"select count(*) as n from subscription_payment_receipts where account_id='{u['account']}'"
    ) == [{"n": 2}]
    u["mail"].run()
    u["mail"].run()
    assert len(u["mail_provider"].requests) == 2
    assert len({x.idempotency_key for x in u["mail_provider"].requests}) == 2
    assert all(x["delivery_state"] == "accepted" for x in f.sources(u))
