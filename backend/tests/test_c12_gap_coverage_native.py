"""Missing cross-path renewal/outbox assertion; providers remain deterministic."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest

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


def review_database(request):
    from test_catalog_store_native import Native
    binary = request.config.getoption("--catalog-pg-bin", default=None)
    if not binary:
        pytest.skip("explicit disposable native PostgreSQL required")
    return Native(binary)


def test_review_project_ownership_is_global_across_connections(request, monkeypatch):
    import psycopg
    import run_staging_session_workflow as workflow
    db = review_database(request)
    monkeypatch.setattr(workflow, "require_cleanup_window", lambda: None)
    def connect():
        return workflow.OwnerConnection.connect(host="127.0.0.1", hostaddr="127.0.0.1", port=db.port,
                               dbname="postgres", user="catalog_test_owner", autocommit=True)
    try:
        with workflow.project_ownership(connect) as check:
            maintenance = connect()
            maintenance._workflow_guard = check
            # Maintenance reconnects cannot release the independently held lock.
            connect().close()
            connect().close()
            with pytest.raises(RuntimeError, match="already owned"):
                with workflow.project_ownership(connect):
                    pytest.fail("second checkout admitted")
            check()
        try:
            with pytest.raises(psycopg.Error):
                maintenance.execute("CREATE TABLE forbidden_after_lease_loss(id integer)")
            assert db.rows("SELECT to_regclass('public.forbidden_after_lease_loss') IS NULL AS absent") == [{"absent": True}]
        finally:
            maintenance.close()
        with workflow.project_ownership(connect) as check:
            check()
    finally:
        db.close()


def test_review_auth_fixture_connections_ignore_inherited_hostaddr(request, monkeypatch):
    import jwt
    from io import BytesIO
    from check_staging_application_native import NativeAuth
    db = review_database(request)
    auth = None
    try:
        db.run("CREATE ROLE authenticated; CREATE ROLE authenticator LOGIN NOINHERIT; GRANT authenticated TO authenticator; CREATE FUNCTION public.subscription_admin_self_probe() RETURNS jsonb LANGUAGE sql AS $$SELECT '{\"ok\":true}'::jsonb$$")
        auth = NativeAuth(db)
        monkeypatch.setenv("PGHOSTADDR", "203.0.113.8")
        with auth.connect() as conn:
            assert conn.execute("SELECT host(inet_server_addr())").fetchone()[0] == "127.0.0.1"
        token = jwt.encode({"sub": str(uuid4()), "aud": "authenticated"}, auth.key, algorithm="HS256")
        # Invoke the synthetic probe handler directly; native DB connections
        # remain real, and pytest's prohibition on HTTP stays unchanged.
        handler = object.__new__(auth.server.RequestHandlerClass)
        handler.path = "/rest/v1/rpc/subscription_admin_self_probe"
        handler.headers = {"Authorization": "Bearer " + token}
        handler.wfile = BytesIO()
        statuses = []
        handler.send_response = lambda code: statuses.append(code)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        handler.do_POST()
        assert statuses == [200] and json.loads(handler.wfile.getvalue()) == {"ok": True}
    finally:
        if auth:
            auth.close()
        db.close()


def test_review_scram_requires_actual_invalid_password_rejection(request):
    import psycopg
    from psycopg.conninfo import make_conninfo
    from check_executor_connection_native import prove_scram_rejection
    db = review_database(request)
    try:
        db.run("CREATE ROLE usage_executor LOGIN PASSWORD 'synthetic-local-only'; ALTER SYSTEM SET log_error_verbosity='verbose'")
        dsn = make_conninfo(host="127.0.0.1", hostaddr="127.0.0.1", port=db.port, dbname="postgres", user="usage_executor", password="synthetic-local-only")
        with pytest.raises(AssertionError, match="Incorrect password accepted"):
            prove_scram_rejection(db, dsn, "usage_executor")
        hba = db.directory / "data/pg_hba.conf"
        hba.write_text("host postgres usage_executor 127.0.0.1/32 scram-sha-256\n" + hba.read_text())
        db.command("pg_ctl", ["-D", str(db.directory / "data"), "-l", str(db.directory / "server.log"), "restart", "-m", "fast", "-w"])
        prove_scram_rejection(db, dsn, "usage_executor")
        with psycopg.connect(dsn) as conn:
            assert conn.execute("SELECT session_user").fetchone()[0] == "usage_executor"
    finally:
        db.close()


def test_review_optional_reader_guard_rejects_authority_before_grants(request):
    import re
    from app.commercial.catalog_store import RpcFailure
    db = review_database(request)
    text = (Path(__file__).resolve().parents[2] / "docs/sql/SUBSCRIPTION_ADMIN_OPTIONAL_POLICY_PUBLIC_PENDING_APPROVAL.sql").read_text()
    guard = re.search(r"do \$\$ begin.*?end \$\$;", text, re.S).group()
    try:
        db.run(guard)
        for enabled, disabled in [("LOGIN", "NOLOGIN"), ("INHERIT", "NOINHERIT"), ("SUPERUSER", "NOSUPERUSER"), ("BYPASSRLS", "NOBYPASSRLS"), ("CREATEDB", "NOCREATEDB"), ("CREATEROLE", "NOCREATEROLE"), ("REPLICATION", "NOREPLICATION")]:
            db.run("ALTER ROLE catalog_public_reader " + enabled)
            with pytest.raises(RpcFailure):
                db.run(guard)
            db.run("ALTER ROLE catalog_public_reader " + disabled)
        db.run("CREATE ROLE synthetic_member; GRANT catalog_public_reader TO synthetic_member")
        with pytest.raises(RpcFailure):
            db.run(guard)
        db.run("REVOKE catalog_public_reader FROM synthetic_member; GRANT synthetic_member TO catalog_public_reader")
        with pytest.raises(RpcFailure):
            db.run(guard)
        db.run("REVOKE synthetic_member FROM catalog_public_reader")
        db.run(guard)
    finally:
        db.close()


def test_review_prepared_retirement_requires_explicit_stage(pricing):
    import psycopg
    from test_pricing_native import definition, publish
    from test_draft_api_native import create
    from test_catalog_store_native import ROOT, MANAGER
    db, client, app, _ = pricing
    raw = definition("plus")
    assert create(client, raw).status_code == 200
    offer = publish(client, raw)
    text = (ROOT / "docs/sql/SUBSCRIPTION_ADMIN_CORE_PENDING_APPROVAL.sql").read_text()
    sql = text[text.rfind("create or replace function public.catalog_lifecycle_service_call"):]
    sql = sql[:sql.index("$$;", sql.index("as $$") + 5) + 3]
    db.run(sql)
    operation = {"operation": "offer.retire", "request_id": str(uuid4()), "offer_version_id": offer["receipt"]["offer_version_id"], "expected_revision": offer["current"]["revision"], "reason": "synthetic null-stage rejection"}
    target = "SELECT state FROM catalog_visibility WHERE offer_version_id='" + operation["offer_version_id"] + "'"
    assert db.rows(target) == [{"state": "visible"}]
    with app.state.catalog_drafts.connect() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("SELECT public.catalog_lifecycle_service_call(%s,NULL,%s::jsonb,NULL)", (MANAGER, json.dumps(operation)))
        conn.rollback()
    assert db.rows(target) == [{"state": "visible"}]


def test_missed_renewal_reconciliation_and_duplicate_delivery_share_one_email(mail):
    u = mail
    op, _, _ = f.paid(u)
    first = u["subscription"].current(actor(u["account"]))
    renewal = u["provider"].pay(op["provider_id"], offset=2592000)
    raw, sig = f.fixtures.signed(u, renewal)
    # No renewal webhook initially: reconciliation discovers the paid invoice.
    u["billing"].reconcile(u["account"], op["operation_id"])
    after = u["subscription"].current(actor(u["account"]))
    expected = datetime.fromtimestamp(u["provider"].bills[op["provider_id"]][-1]["billing_end"], timezone.utc)
    assert datetime.fromisoformat(after["plan"]["valid_until"].replace("Z", "+00:00")) == expected
    assert expected > datetime.fromisoformat(first["plan"]["valid_until"].replace("Z", "+00:00"))
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
