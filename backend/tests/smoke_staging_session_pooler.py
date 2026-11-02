"""Operator-run, private-prompt staging connection smoke; no business writes."""

import argparse
import getpass
import socket
import ssl
import struct
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never load the normal project's credentials while importing pool guard classes.
import dotenv

dotenv.load_dotenv = lambda *_a, **_kw: False

from app.commercial.catalog_database import CatalogDatabase
from app.commercial.executor_connection import (
    STAGING_PROJECT,
    STAGING_SESSION_HOST,
    SessionPooler,
    check_executor_identity,
    connection_parameters,
    restore_executor_timeouts,
)
from app.commercial.subscription_database import SubscriptionDatabase

# Previously recorded conservative deadline, not extended by rerunning this script.
DEADLINE = datetime(2026, 10, 26, 13, 8, 53, tzinfo=timezone.utc)


def require_window():
    if datetime.now(timezone.utc) >= DEADLINE - timedelta(minutes=2):
        raise RuntimeError("approved staging intake window closed")


def tls_preflight(ca):
    require_window()
    context = ssl.create_default_context(cafile=str(ca))
    with socket.create_connection((STAGING_SESSION_HOST, 5432), timeout=3) as raw:
        raw.sendall(struct.pack("!II", 8, 80877103))
        if raw.recv(1) != b"S":
            raise RuntimeError("staging endpoint did not offer TLS")
        with context.wrap_socket(raw, server_hostname=STAGING_SESSION_HOST):
            pass


def guard(conn, role):
    require_window()
    if role == "usage_executor":
        SubscriptionDatabase.check(conn)
    elif role in {"catalog_draft_executor", "catalog_public_reader"}:
        CatalogDatabase._check(
            conn,
            lifecycle=role == "catalog_draft_executor",
            public_only=role == "catalog_public_reader",
        )
    else:
        check_executor_identity(conn, role)
        required = (
            [
                "public.usage_binding_call(uuid,text,jsonb)",
                "public.usage_terms_read(uuid)",
            ]
            if role == "usage_binding_executor"
            else ["public.usage_call(uuid,text,jsonb)"]
        )
        for signature in required:
            if not conn.execute(
                "SELECT has_function_privilege(current_user,%s,'EXECUTE')", (signature,)
            ).fetchone()[0]:
                raise RuntimeError("executor ACL mismatch")
        for table in [
            "account_plan_bindings",
            "usage_events",
            "usage_periods",
            "usage_operations",
        ]:
            if conn.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",
                ("public." + table,),
            ).fetchone()[0]:
                raise RuntimeError("executor direct-table ACL mismatch")
        conn.commit()


def reset(conn, role):
    if role == "usage_executor":
        SubscriptionDatabase.reset(conn)
    elif role in {"catalog_draft_executor", "catalog_public_reader"}:
        CatalogDatabase._reset(
            conn,
            lifecycle=role == "catalog_draft_executor",
            public_only=role == "catalog_public_reader",
        )
    else:
        conn.rollback()
        conn.execute("RESET ALL")
        restore_executor_timeouts(conn)
        conn.commit()
        guard(conn, role)


class SessionCheckFailure(AssertionError):
    """Constant check names only: never include driver values or credentials."""


def verify_session(condition, check):
    if not condition:
        raise SessionCheckFailure(check)


def session_checks(conn, role):
    """Transaction-local isolation, session affinity, failed-tx reset and reuse."""
    from psycopg.errors import DivisionByZero

    require_window()
    pid, app = conn.execute(
        "SELECT pg_backend_pid(),current_setting('application_name')"
    ).fetchone()
    conn.commit()
    for action, finish in [("commit", conn.commit), ("rollback", conn.rollback)]:
        require_window()
        conn.execute("SET LOCAL application_name='c132.local.only'")
        verify_session(
            conn.execute("SELECT current_setting('application_name')").fetchone()[0]
            == "c132.local.only",
            "local_setting_" + action,
        )
        finish()
        observed_pid, observed_app = conn.execute(
            "SELECT pg_backend_pid(),current_setting('application_name')"
        ).fetchone()
        verify_session(observed_pid == pid, "session_affinity_" + action)
        verify_session(observed_app == app, "local_setting_restored_" + action)
        conn.commit()
    conn.execute("SET application_name='c132.session.dirty'")
    conn.execute("SET catalog.draft_actor='c132.dirty'")
    conn.commit()
    try:
        conn.execute("SELECT 1/0")
    except DivisionByZero:
        verify_session(conn.info.transaction_status == 3, "failed_transaction_state")
    else:
        raise SessionCheckFailure("division_error_expected")
    reset(conn, role)
    verify_session(conn.info.transaction_status == 0, "reset_idle")
    observed_pid, observed_app = conn.execute(
        "SELECT pg_backend_pid(),current_setting('application_name')"
    ).fetchone()
    verify_session(observed_pid == pid, "reset_session_affinity")
    verify_session(observed_app == app, "reset_application_name")
    verify_session(
        conn.execute(
            "SELECT coalesce(current_setting('catalog.draft_actor',true),'')"
        ).fetchone()[0]
        == "",
        "reset_private_actor",
    )
    # Actual timeout protections must remain after reset and before pool reuse.
    timeouts = conn.execute(
        "SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout'),current_setting('transaction_timeout')"
    ).fetchone()
    for name, actual, expected in zip(
        ("statement", "lock", "idle_transaction", "transaction"),
        timeouts,
        ("10s", "5s", "15s", "20s"),
    ):
        verify_session(actual == expected, "reset_timeout_" + name)
    conn.commit()
    guard(conn, role)


def run_role_smoke(role, password, ca):
    from time import monotonic

    require_window()
    from psycopg import Connection, Error, OperationalError
    from psycopg.conninfo import make_conninfo
    from psycopg_pool import ConnectionPool

    class SafeConnection(Connection):
        def __repr__(self):
            return "<staging smoke connection>"

        @classmethod
        def connect(cls, *a, **kw):
            try:
                require_window()
                conn = super().connect(*a, **kw)
                remaining = max(
                    0, (DEADLINE - datetime.now(timezone.utc)).total_seconds()
                )
                conn._staging_timer = threading.Timer(remaining, conn.close)
                conn._staging_timer.daemon = True
                conn._staging_timer.start()
                return conn
            except (Error, ValueError, OSError, RuntimeError):
                raise OperationalError("staging connection unavailable") from None

        def close(self):
            timer = getattr(self, "_staging_timer", None)
            if timer is not None:
                timer.cancel()
            super().close()

    target = SessionPooler(STAGING_SESSION_HOST)
    params = connection_parameters(
        make_conninfo(
            host=target.host,
            port=5432,
            dbname="postgres",
            user=role + "." + STAGING_PROJECT,
            password=password,
            sslmode="verify-full",
            sslrootcert=str(ca.resolve()),
        ),
        role,
        session_pooler=target,
    )
    del password
    pool = ConnectionPool(
        "",
        kwargs={
            **params,
            "connect_timeout": 3,
            "prepare_threshold": None,
            "application_name": "c132.staging.smoke",
            "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000 -c transaction_timeout=20000",
        },
        connection_class=SafeConnection,
        open=False,
        min_size=1,
        max_size=1,
        timeout=2,
        max_waiting=1,
        reconnect_timeout=3,
        num_workers=1,
        configure=lambda c, r=role: guard(c, r),
        check=lambda c, r=role: guard(c, r),
        reset=lambda c, r=role: reset(c, r),
        name="staging-smoke",
    )
    try:
        require_window()
        started = monotonic()
        pool.open(wait=True, timeout=5)
        print("CHECK: " + role + " pool_open", flush=True)
        with pool.connection() as conn:
            session_checks(conn, role)
        print("CHECK: " + role + " session_checks", flush=True)
        with pool.connection() as conn:
            guard(conn, role)
        print(
            "PASS: "
            + role
            + " identity/ACLs, transactions, session reset and checked reuse ("
            + str(round(monotonic() - started, 2))
            + "s)"
        )
    finally:
        # A reset runs the real ACL guard; allow its bounded transaction to end.
        pool.close(timeout=20)
        params.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ca",
        required=True,
        type=Path,
        help="CA downloaded from staging Dashboard; not a secret",
    )
    parser.add_argument("--include-maintenance", action="store_true")
    args = parser.parse_args()
    require_window()
    if not sys.stdin.isatty():
        raise RuntimeError(
            "use a dedicated interactive local console for hidden credential input"
        )
    tls_preflight(args.ca)
    print("PASS: Dashboard-pinned session endpoint TLS chain and hostname verified")
    roles = ["usage_executor", "catalog_draft_executor", "catalog_public_reader"]
    if args.include_maintenance:
        roles += ["usage_binding_executor", "usage_reconciler"]
    for role in roles:
        require_window()
        password = getpass.getpass(f"Staging {role} password (hidden): ")
        run_role_smoke(role, password, args.ca)
        del password
    print("Smoke complete; owned connections closed. No data/role/fixture writes made.")


if __name__ == "__main__":
    from psycopg import Error

    try:
        main()
    except (
        Error,
        RuntimeError,
        ValueError,
        OSError,
        AssertionError,
        EOFError,
    ) as error:
        # No raw driver exception, traceback or DSN may escape the private console.
        code = getattr(error, "sqlstate", None)
        print(
            "FAIL: staging smoke stopped; safe error type="
            + type(error).__name__
            + (" SQLSTATE=" + code if code else "")
        )
        raise SystemExit(1) from None
