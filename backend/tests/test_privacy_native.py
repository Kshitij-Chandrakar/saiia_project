"""C15 disposable native PostgreSQL + actual ASGI/JWT; no external boundaries."""

import json
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.auth.supabase_auth import CurrentUser
from app.commercial.catalog_store import CatalogStoreError, RpcFailure
from app.privacy import POLICY, PrivacyService, digest, recent_presence
from test_catalog_store_native import literal
from test_draft_service_native import actor
from test_subscription_integration_native import (  # noqa: F401
    case,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    upgraded,
    usage,
)


@pytest.fixture
def privacy(integration, monkeypatch, request):  # noqa: F811 -- imported pytest fixture
    from app.config import settings

    u = integration
    db = u["db"]
    if not db.rows("select 1 from pg_tables where tablename='privacy_configuration'"):
        db.run(
            "create role supabase_auth_admin;alter table auth.users add column email text;alter table auth.users add column raw_user_meta_data jsonb;create table auth.identities(id uuid primary key,user_id uuid references auth.users,identity_data jsonb);create table auth.sessions(id uuid primary key,user_id uuid references auth.users)"
        )
        for filename in (
            "20261025020000_razorpay_checkout.sql",
            "20261025030000_billing_gst_payable.sql",
            "20260904143000_add_outbound_email_events.sql",
            "20260922120000_add_marketing_email_event_type.sql",
            "20260924120000_fix_outbound_email_event_claim_ambiguous_user_id.sql",
            "20261026010000_billing_notifications_admin.sql",
            "20261027010000_resend_delivery_callbacks.sql",
        ):
            db.run(
                (
                    Path(__file__).parents[2] / "supabase/migrations" / filename
                ).read_text()
            )
        db.run(
            (
                Path(__file__).parents[2]
                / (
                    "docs/sql/C15_SUPPORTED_AUTH_PACKAGE_PENDING.sql"
                    if getattr(request.module, "SUPPORTED_AUTH_PACKAGE", False)
                    else "supabase/migrations/20261029010000_privacy_confirmation_foundation.sql"
                )
            ).read_text()
        )
        # Synthetic, disposable key only; never read environment/real credentials.
        db.run(
            "update auth.users set email=id::text||'@example.invalid' where email is null;insert into privacy_matching_keys values(1,decode(repeat('12',32),'hex'),true);update privacy_configuration set enabled=true"
        )
    db.run(
        f"update auth.users set email='{u['account']}@example.invalid' where id='{u['account']}'"
    )
    if not db.rows("select 1 from pg_tables where tablename='privacy_reauth_intents'"):
        db.run(
            (
                Path(__file__).parents[2]
                / "supabase/migrations/20261029020000_privacy_auth_recovery.sql"
            ).read_text()
        )
    monkeypatch.setattr(settings, "C15_ENABLED", "true")
    monkeypatch.setattr(settings, "C15_RESTRICTIONS_REQUIRED", "true")
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    if not db.rows(
        "select 1 from pg_tables where tablename='privacy_revocation_credentials'"
    ):
        db.run(
            (
                Path(__file__).parents[2]
                / "supabase/migrations/20261030010000_privacy_auth_integration.sql"
            ).read_text()
        )
    monkeypatch.setenv("C15_REVOCATION_KEYS", '{"test":"' + "EhIS" * 10 + 'EhI="}')
    monkeypatch.setenv("C15_REVOCATION_CURRENT_KEY", "test")
    service = PrivacyService(u["connect"])
    from app.privacy import router

    if not any(
        route.path == "/api/privacy/deletion/{action}"
        for route in u["client"].app.routes
    ):
        u["client"].app.include_router(router)
    session = str(uuid4())
    stamp = int(time.time())
    auth = actor(
        u["account"],
        email=u["account"] + "@example.invalid",
        session_id=session,
        amr=[{"method": "password", "timestamp": stamp}],
        c15_auth_method="password",
    )
    doc = dict(  # noqa: C408 -- compact fixture document
        verified_email=u["account"] + "@example.invalid",
        request_id=str(uuid4()),
        session_id=session,
        reauthenticated_at=datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
        policy_version=POLICY,
        scope="whole_account",
        confirmation_hash=digest(secrets.token_urlsafe(32)),
        status_hash=digest(secrets.token_urlsafe(32)),
        proof_method="password",
    )
    service.call(auth, "begin", doc)
    db.run(
        f"update privacy_reauth_intents set started_at=clock_timestamp()-interval '2 seconds' where account_id='{u['account']}'"
    )
    return u, service, auth, doc


def accept(service, auth, doc):
    service.call(auth, "challenge", doc)
    return service.call(auth, "confirm", {**doc, "confirmation_text": "delete"})


def test_atomic_acceptance_replay_status_and_pending_tasks(privacy):
    u, s, a, d = privacy
    result = accept(s, a, d)
    assert result["state"] == "accepted_restricted" and result["revision"] == 2
    assert (
        result["content_erased"] is False and result["session_revocation"] == "pending"
    )
    assert s.call(a, "confirm", {**d, "confirmation_text": "delete"}) == result
    assert (
        s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
        == result
    )
    assert u["db"].rows(
        f"select count(*) n from privacy_followup_tasks where request_id='{d['request_id']}'"
    ) == [{"n": 3}]
    assert u["db"].rows(
        f"select count(*) n from privacy_lifecycle_audit where request_id='{d['request_id']}' and action='deletion.accepted_restricted'"
    ) == [{"n": 1}]
    assert u["db"].rows(
        f"select primary_cleanup_target_at-accepted_at=interval '24 hours' and usage_retention_until-accepted_at=interval '90 days' and security_retention_until-accepted_at=interval '180 days' ok from privacy_deletion_requests where request_id='{d['request_id']}'"
    ) == [{"ok": True}]
    with pytest.raises(CatalogStoreError):
        s.status({"request_id": d["request_id"], "status_hash": "wrong"})


def test_concurrent_confirmations_recover_same_request(privacy):
    _, s, a, d = privacy
    s.call(a, "challenge", d)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: s.call(a, "confirm", {**d, "confirmation_text": "delete"}),
                range(2),
            )
        )
    assert results[0] == results[1] and results[0]["revision"] == 2


def test_wrong_text_subject_session_and_expired_confirmation(privacy):
    u, s, a, d = privacy
    s.call(a, "challenge", d)
    for change in (
        {"confirmation_text": "DELETE"},
        {"session_id": str(uuid4())},
        {"policy_version": "other"},
        {"confirmation_hash": "wrong"},
    ):
        with pytest.raises(CatalogStoreError):
            s.call(a, "confirm", {**d, "confirmation_text": "delete", **change})
    other = actor(str(uuid4()))
    with pytest.raises(CatalogStoreError):
        s.call(other, "confirm", {**d, "confirmation_text": "delete"})
    u["db"].run(
        f"update privacy_deletion_requests set expires_at=clock_timestamp()-interval '1 second' where account_id='{u['account']}'"
    )
    with pytest.raises(CatalogStoreError):
        s.call(a, "confirm", {**d, "confirmation_text": "delete"})


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"session_id": str(uuid4()), "iat": int(time.time())},
        {
            "session_id": str(uuid4()),
            "c15_auth_method": "token_refresh",
            "amr": [{"method": "password", "timestamp": int(time.time())}],
        },
        {
            "session_id": str(uuid4()),
            "c15_auth_method": "oauth",
            "amr": [{"method": "oauth", "timestamp": int(time.time())}],
        },
        {
            "session_id": str(uuid4()),
            "c15_auth_method": "password",
            "amr": [{"method": "password", "timestamp": int(time.time()) - 600}],
        },
    ],
)
def test_missing_stale_refresh_or_silent_oauth_is_not_presence(claims):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        recent_presence(CurrentUser(str(uuid4()), claims=claims))


def test_auth_signup_email_change_and_hooks_are_not_frontend_checks(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    email = u["account"] + "@example.invalid"
    db = u["db"]
    event = json.dumps({"user": {"email": email.upper()}})
    assert db.rows(
        f"select privacy_before_user_created({literal(json.loads(event))})->'error'->>'http_code' code"
    ) == [{"code": "403"}]
    for email_value in (email, email.upper()):
        with pytest.raises(RpcFailure):
            db.run(
                f"insert into auth.users(id,email) values('{uuid4()}','{email_value}')"
            )
    other = str(uuid4())
    db.run(
        f"insert into auth.users(id,email) values('{other}','{other}@example.invalid')"
    )
    with pytest.raises(RpcFailure):
        db.run(f"update auth.users set email='{email}' where id='{other}'")
    token_event = {
        "user_id": u["account"],
        "claims": {"email": email},
        "authentication_method": "oauth",
    }
    assert db.rows(
        f"select privacy_access_token_hook({literal(token_event)})->'error'->>'http_code' code"
    ) == [{"code": "403"}]
    # Exact canonical email, not all aliases: plus addresses remain distinct.
    assert db.rows(
        f"select privacy_email_denied('{u['account']}+alias@example.invalid') denied"
    ) == [{"denied": False}]
    assert db.rows("select count(*) n from privacy_email_suppression")[0]["n"] >= 1
    with pytest.raises(RpcFailure):
        db.run(
            f"insert into auth.identities values('{uuid4()}','{other}',{literal({'email': email})})"
        )
    with pytest.raises(RpcFailure):
        db.run(f"insert into auth.sessions values('{uuid4()}','{u['account']}')")
    with pytest.raises(RpcFailure) as denied_metadata:
        db.run(
            f"update auth.users set raw_user_meta_data={literal({'private': 'late'})} where id='{u['account']}'"
        )
    assert denied_metadata.value.sqlstate == "42501"


def test_private_writes_and_confirmation_serialize_at_commit(privacy):
    import psycopg
    from test_draft_service_native import wait_blocked

    u, s, a, d = privacy
    s.call(a, "challenge", d)
    db = u["db"]
    writer = psycopg.connect(
        host="127.0.0.1", port=db.port, user="catalog_test_owner", dbname="postgres"
    )
    try:
        writer.execute("insert into profiles(user_id) values(%s)", (u["account"],))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                s.call, a, "confirm", {**d, "confirmation_text": "delete"}
            )
            wait_blocked(db, {"c131-worker"})
            writer.commit()
            assert future.result()["state"] == "accepted_restricted"
        with pytest.raises(psycopg.Error):
            writer.execute(
                "update profiles set summary=%s where user_id=%s",
                ("late private output", u["account"]),
            )
    finally:
        writer.rollback()
        writer.close()


def test_uncertain_commit_recovers_without_second_barrier(privacy):
    u, s, a, d = privacy
    s.call(a, "challenge", d)

    def connect():
        conn = u["connect"]()

        class LostAcknowledgement:
            def __getattr__(self, key):
                return getattr(conn, key)

            def commit(self):
                conn.commit()
                raise OSError("synthetic lost commit acknowledgement")

        return LostAcknowledgement()

    with pytest.raises(CatalogStoreError):
        PrivacyService(connect).call(a, "confirm", {**d, "confirmation_text": "delete"})
    recovered = s.call(a, "confirm", {**d, "confirmation_text": "delete"})
    assert recovered["revision"] == 2
    assert u["db"].rows(
        f"select count(*) n from subscription_deletion_jobs where account_id='{u['account']}'"
    ) == [{"n": 1}]


@pytest.mark.parametrize(
    "table,columns,values",
    [
        ("interview_session_ai_notes", "notes_markdown", "'synthetic notes'"),
        (
            "interview_session_ask_ai_messages",
            "role,message_text,turn_index",
            "'user','synthetic chat',1",
        ),
        (
            "session_generation_turns",
            "request_id,payload_hash,state",
            "'synthetic','a','processing'",
        ),
    ],
)
def test_late_notes_chat_generation_are_fenced_without_erasing_session(
    privacy, table, columns, values
):
    u, s, a, d = privacy
    sid = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values('{sid}','{u['account']}')"
    )
    accept(s, a, d)
    from app.commercial.catalog_store import RpcFailure

    with pytest.raises(RpcFailure) as failure:
        u["db"].run(
            f"insert into {table}(user_id,session_id,{columns}) values('{u['account']}','{sid}',{values})"
        )
    assert failure.value.sqlstate == "42501"
    assert u["db"].rows(
        f"select count(*) n from interview_sessions where id='{sid}'"
    ) == [{"n": 1}]


def test_valid_old_token_loses_product_access_but_scoped_status_needs_no_login(
    privacy, monkeypatch
):
    u, _, a, d = privacy
    raw = {
        key: value
        for key, value in d.items()
        if key in ("request_id", "scope", "policy_version")
    }
    raw.update(
        confirmation_token=secrets.token_urlsafe(32),
        status_token=secrets.token_urlsafe(32),
    )
    h = {"Authorization": "Bearer " + a._bearer}
    route = "/api/privacy/deletion/"
    u["db"].run(f"delete from privacy_reauth_intents where account_id='{u['account']}'")
    assert u["client"].post(route + "begin", headers=h, json=raw).status_code == 200
    u["db"].run(
        f"update privacy_reauth_intents set started_at=clock_timestamp()-interval '2 seconds' where account_id='{u['account']}'"
    )
    challenge = u["client"].post(route + "challenge", headers=h, json=raw)
    assert challenge.status_code == 200, challenge.text
    accepted = u["client"].post(
        route + "confirm", headers=h, json={**raw, "confirmation_text": "delete"}
    )
    assert accepted.status_code == 200, accepted.text
    from app.config import settings

    monkeypatch.setattr(settings, "C15_ENABLED", "false")
    assert u["client"].get("/api/account/subscription", headers=h).status_code == 403
    status = u["client"].post(
        route + "status", json={key: raw[key] for key in ("request_id", "status_token")}
    )
    assert status.status_code == 200 and status.json()["content_erased"] is False
    assert status.headers["cache-control"] == "no-store"
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "false")
    u["client"].app.state.subscriptions = None
    # Rolling back new feature/subscription composition cannot reopen old-token access.
    assert u["client"].get("/api/auth/me", headers=h).status_code == 503


def test_late_private_writes_bootstrap_and_paid_apply_cannot_restore(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    db = u["db"]
    for table, columns, values in [
        ("profiles", "user_id", f"'{u['account']}'"),
        ("storage.objects", "bucket_id,name", f"'resumes','{u['account']}/late.txt'"),
    ]:
        with pytest.raises(RpcFailure):
            db.run(f"insert into {table}({columns}) values({values})")
    with pytest.raises(CatalogStoreError):
        u["subscription"].current(a, bootstrap=True)
    # The verified payment executor cannot restore a deleted binding.
    connection = u["connect"]("usage_binding_executor")
    try:
        result = [
            {
                "r": connection.execute(
                    "select public.subscription_payment_apply(%s,%s,%s,%s,clock_timestamp()+interval '30 days','synthetic')",
                    (u["account"], uuid4(), uuid4(), uuid4()),
                ).fetchone()[0]
            }
        ]
        connection.commit()
    finally:
        connection.close()
    assert result == [{"r": {"account_restricted": True, "access_granted": False}}]


def test_default_off_api_and_strict_own_subject_contract(privacy, monkeypatch):
    u, _, a, _ = privacy
    from app.config import settings

    route = "/api/privacy/deletion/challenge"
    headers = {"Authorization": "Bearer " + a._bearer}
    monkeypatch.setattr(settings, "C15_ENABLED", "false")
    assert u["client"].post(route, headers=headers, json={}).status_code == 404
    monkeypatch.setattr(settings, "C15_ENABLED", "true")
    assert (
        u["client"]
        .post(route, headers=headers, json={"account_id": str(uuid4())})
        .status_code
        == 422
    )


def test_late_financial_receipt_preserved_without_access_or_notification(privacy):
    from app.commercial.billing_service import BillingService
    from test_billing_native import SECRET, Provider, ready, signed
    from test_draft_api_native import create
    from test_pricing_native import definition, publish

    u, s, a, d = privacy
    raw = definition("plus")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    provider = Provider()
    provider.plans["plan_synthetic"] = {
        "id": "plan_synthetic",
        "entity": "plan",
        "period": "monthly",
        "interval": 1,
        "item": {"amount": 47082, "currency": "INR"},
    }
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
    u.update(
        billing=service,
        provider=provider,
        checkout={
            "operation_id": str(uuid4()),
            "offer_version_id": offer,
            "price_id": raw["terms"]["prices"][0]["price_id"],
        },
    )
    op = ready(u)
    # Fake cancellation/refund calls would fail this check immediately.
    provider.cancel = lambda *_: pytest.fail("No cancellation authorized")
    initial_payment = provider.pay(op["provider_id"])
    initial_event, initial_signature = signed(u, initial_payment)
    service.webhook(initial_event, initial_signature)
    assert u["subscription"].current(a)["plan"]["name"] == "Plus"
    before = u["db"].rows(
        f"select offer_version_id,revision from account_plan_bindings where account_id='{u['account']}'"
    )
    accept(s, a, d)
    payment = provider.pay(op["provider_id"], offset=2)
    raw_event, signature = signed(u, payment)
    service.webhook(raw_event, signature)
    service.webhook(raw_event, signature)
    assert (
        u["db"].rows(
            f"select offer_version_id,revision from account_plan_bindings where account_id='{u['account']}'"
        )
        == before
    )
    assert u["db"].rows(
        f"select count(*) n from billing_evidence where operation_id='{op['operation_id']}'"
    ) == [{"n": 2}]
    assert u["db"].rows(
        f"select count(*) n from billing_notification_sources where account_id='{u['account']}'"
    ) == [{"n": 1}]  # Only the pre-deletion event, no renewal notification.
    from app.email.billing import BillingNotifications

    class NoMail:
        def send_email(self, _request):
            pytest.fail("No email authorized")

    with pytest.raises(CatalogStoreError):
        BillingNotifications(
            lambda: u["connect"]("usage_binding_executor"), NoMail()
        ).run()


def test_signup_hook_check_cannot_race_suppression_commit(privacy):
    import psycopg
    from test_draft_service_native import wait_blocked

    u, s, a, d = privacy
    s.call(a, "challenge", d)
    db = u["db"]
    signup = psycopg.connect(
        host="127.0.0.1", port=db.port, user="catalog_test_owner", dbname="postgres"
    )
    email = u["account"] + "@example.invalid"
    try:
        assert (
            signup.execute(
                "select privacy_before_user_created(%s::jsonb)",
                (json.dumps({"user": {"email": email}}),),
            ).fetchone()[0]
            == {}
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            confirmation = pool.submit(
                s.call, a, "confirm", {**d, "confirmation_text": "delete"}
            )
            wait_blocked(db, {"c131-worker"})
            signup.commit()
            assert confirmation.result()["state"] == "accepted_restricted"
        # Even a hook which completed before acceptance cannot authorize a late insert.
        with pytest.raises(psycopg.Error) as denied:
            signup.execute(
                "insert into auth.users(id,email) values(%s,%s)", (uuid4(), email)
            )
        assert denied.value.sqlstate == "42501"
    finally:
        signup.rollback()
        signup.close()


def test_email_changed_after_challenge_requires_new_confirmation(privacy):
    u, s, a, d = privacy
    s.call(a, "challenge", d)
    u["db"].run(
        f"update auth.users set email='changed-{u['account']}@example.invalid' where id='{u['account']}'"
    )
    with pytest.raises(CatalogStoreError):
        s.call(a, "confirm", {**d, "confirmation_text": "delete"})
    assert u["db"].rows(
        f"select count(*) n from subscription_deletion_jobs where account_id='{u['account']}'"
    ) == [{"n": 0}]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--select", default="")
    parser.add_argument("--suite", default=__file__)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [
                args.suite,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "-k",
                args.select,
            ],
            plugins=[Options()],
        )
    )
