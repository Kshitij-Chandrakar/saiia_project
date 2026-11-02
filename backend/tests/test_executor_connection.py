"""No-network coverage of pinned routing and unchanged SQL authority guards."""

from types import SimpleNamespace

import pytest
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.executor_connection import (
    EXECUTORS,
    STAGING_PROJECT,
    SessionPooler,
    check_executor_identity,
    connection_parameters,
)
from app.commercial.subscription_database import SubscriptionDatabase
from psycopg.conninfo import make_conninfo

# Operator-confirmed Dashboard host. Unit tests never resolve or connect to it.
HOST = "aws-0-ap-south-1.pooler.supabase.com"


@pytest.fixture
def routing(tmp_path):
    ca = tmp_path / "synthetic-ca.pem"
    ca.write_text("synthetic; not used for a TLS connection")
    return SessionPooler(HOST), {
        "host": HOST,
        "port": "5432",
        "dbname": "postgres",
        "password": "never-sent-secret",
        "sslmode": "verify-full",
        "sslrootcert": str(ca),
    }


@pytest.mark.parametrize("role", sorted(EXECUTORS))
def test_routing_preserves_wire_user_and_requires_trusted_target(routing, role):
    target, args = routing
    args["user"] = role + "." + STAGING_PROJECT
    dsn = make_conninfo(**args)
    result = connection_parameters(dsn, role, session_pooler=target)
    assert result == args
    with pytest.raises(ValueError, match="^executor connection unavailable$"):
        connection_parameters(dsn, role)


@pytest.mark.parametrize(
    "change",
    [
        {"user": "usage_executor.otherproject"},
        {"user": "usage_executor.cfmvqbjmnwklxqlpelxe.extra"},
        {"user": "usage_executor..cfmvqbjmnwklxqlpelxe"},
        {"user": "usage_executor"},
        {"user": "postgres.cfmvqbjmnwklxqlpelxe"},
        {"user": "catalog_draft_executor.cfmvqbjmnwklxqlpelxe"},
        {"host": "aws-1-synthetic.pooler.supabase.com"},
        {"host": "aws-0-synthetic.pooler.supabase.com.evil.invalid"},
        {"host": "127.0.0.1"},
        {"port": "6543"},
        {"port": "0"},
        {"port": "65536"},
        {"sslmode": "require"},
        {"sslrootcert": ""},
        {"sslrootcert": "missing-ca.pem"},
        {"dbname": "other"},
        {"password": ""},
        {"options": "reference=cfmvqbjmnwklxqlpelxe"},
        {"hostaddr": "127.0.0.1"},
    ],
)
def test_mismatched_or_unsafe_pooler_parameters_fail_closed(routing, change):
    target, args = routing
    args.update(user="usage_executor." + STAGING_PROJECT)
    args.update(change)
    with pytest.raises(ValueError, match="^executor connection unavailable$") as error:
        connection_parameters(
            make_conninfo(**args), "usage_executor", session_pooler=target
        )
    assert "never-sent-secret" not in str(error.value)


@pytest.mark.parametrize(
    "host,project",
    [
        (HOST, "otherproject"),
        ("localhost", STAGING_PROJECT),
        (HOST + ".evil.invalid", STAGING_PROJECT),
    ],
)
def test_target_cannot_select_another_project_or_arbitrary_endpoint(host, project):
    with pytest.raises(ValueError):
        SessionPooler(host, project)


@pytest.mark.parametrize("role", sorted(EXECUTORS))
def test_direct_compatibility(role):
    for host, port, ssl in [
        ("127.0.0.1", "15432", "disable"),
        ("db." + STAGING_PROJECT + ".supabase.co", "5432", "verify-full"),
    ]:
        args = {
            "host": host,
            "port": port,
            "sslmode": ssl,
            "user": role,
            "password": "synthetic",
            "dbname": "postgres",
        }
        assert connection_parameters(make_conninfo(**args), role) == args
    with pytest.raises(ValueError):
        connection_parameters(
            make_conninfo(
                host=HOST,
                port=6543,
                user=role,
                password="synthetic",
                dbname="postgres",
                sslmode="verify-full",
            ),
            role,
        )


def test_parse_errors_are_redacted():
    with pytest.raises(ValueError) as error:
        connection_parameters(
            "password=secret-diagnostic broken_syntax", "usage_executor"
        )
    assert str(error.value) == "executor connection unavailable"
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "kind,role",
    [
        ("usage", "usage_executor"),
        ("draft", "catalog_draft_executor"),
        ("public", "catalog_public_reader"),
    ],
)
def test_real_pools_keep_routing_username_and_callbacks(
    monkeypatch, routing, kind, role
):
    import psycopg_pool

    target, args = routing
    args["user"] = role + "." + STAGING_PROJECT
    captured = {}

    class NoNetworkPool:
        def __init__(self, *_, **kw):
            captured.update(kw)

        def open(self, **_):
            raise RuntimeError("synthetic stop before network")

        def close(self, **_):
            captured["closed"] = True

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", NoNetworkPool)
    dsn = make_conninfo(**args)
    runtime = (
        SubscriptionDatabase("true", dsn, session_pooler=target)
        if kind == "usage"
        else CatalogDatabase(
            "true", dsn, public_only=kind == "public", session_pooler=target
        )
    )
    runtime.start()
    assert captured["kwargs"]["user"] == args["user"]
    assert captured["kwargs"]["connect_timeout"] == 3
    assert captured["kwargs"]["prepare_threshold"] is None
    assert "statement_timeout" in captured["kwargs"]["options"]
    assert all(callable(captured[x]) for x in ["configure", "check", "reset"])
    assert captured["max_size"] == 4 and captured["timeout"] == 1
    assert captured["closed"] and runtime._pool is None


class IdentityConnection:
    def __init__(self, row, membership=False):
        self.row, self.membership = row, membership
        self.committed = self.rolled_back = False

    def execute(self, sql):
        return SimpleNamespace(
            fetchone=lambda: (
                (self.membership,) if "pg_auth_members" in sql else self.row
            )
        )

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


@pytest.mark.parametrize("role", sorted(EXECUTORS))
def test_exact_unsuffixed_identity_and_no_memberships(role):
    conn = IdentityConnection((role, role, "none", False))
    check_executor_identity(conn, role)
    assert conn.committed
    for row, membership in [
        ((role + "." + STAGING_PROJECT, role, "none", False), False),
        ((role, "postgres", "none", False), False),
        ((role, role, role, False), False),
        ((role, role, "none", True), False),
        ((role, role, "none", False), True),
    ]:
        conn = IdentityConnection(row, membership)
        with pytest.raises(RuntimeError, match="^executor connection unavailable$"):
            check_executor_identity(conn, role)
        assert conn.rolled_back and not conn.committed


def test_existing_runtime_sql_identity_checks_reject_mismatches():
    conn = IdentityConnection(
        ("usage_executor." + STAGING_PROJECT, "usage_executor", "none", False)
    )
    with pytest.raises(RuntimeError, match="subscription unavailable"):
        SubscriptionDatabase.check(conn)
    conn = IdentityConnection(
        (
            "catalog_draft_executor." + STAGING_PROJECT,
            "catalog_draft_executor",
            "none",
            "",
            False,
        )
    )
    conn.info = SimpleNamespace(server_version=170000)
    with pytest.raises(RuntimeError, match="catalog database unavailable"):
        CatalogDatabase._check(conn)


def test_credential_smoke_deadline_rejects_intake_before_connect(monkeypatch):
    from datetime import timedelta

    import smoke_staging_session_pooler as smoke

    class ExpiredClock:
        @staticmethod
        def now(_zone):
            return smoke.DEADLINE + timedelta(seconds=1)

    monkeypatch.setattr(smoke, "datetime", ExpiredClock)
    with pytest.raises(RuntimeError, match="approved staging intake window closed"):
        smoke.require_window()


def test_credential_smoke_refuses_nonprivate_input(monkeypatch, tmp_path):
    import sys

    import smoke_staging_session_pooler as smoke

    monkeypatch.setattr(smoke, "require_window", lambda: None)
    monkeypatch.setattr(sys, "argv", ["smoke", "--ca", str(tmp_path / "unused.crt")])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(RuntimeError, match="dedicated interactive local console"):
        smoke.main()


@pytest.mark.parametrize(
    "host", [HOST.upper(), HOST + ".", "DB." + STAGING_PROJECT + ".SUPABASE.CO."]
)
def test_direct_mode_does_not_allow_case_or_trailing_dot_pooler_bypass(host):
    with pytest.raises(ValueError):
        connection_parameters(
            make_conninfo(
                host=host,
                port=6543,
                dbname="postgres",
                user="usage_executor",
                password="synthetic",
                sslmode="verify-full",
            ),
            "usage_executor",
        )
