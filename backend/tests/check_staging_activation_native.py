"""Local disposable role lifecycle verification; never accepts a remote DSN."""

import argparse
from pathlib import Path

from app.commercial.catalog_store import RpcFailure
from test_catalog_store_native import Native

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "C11_C13_STAGING_cfmvqbjmnwklxqlpelxe"
ROLES = (
    "catalog_draft_executor",
    "catalog_public_reader",
    "usage_executor",
    "usage_binding_executor",
    "usage_reconciler",
)


def check(pg_bin):
    db = Native(pg_bin)
    try:
        for name in ROLES:
            db.run(f"CREATE ROLE {name} NOLOGIN NOINHERIT")
        enable = (
            ROOT / "docs/sql" / f"{PREFIX}_LOGIN_PENDING_APPROVAL.sql"
        ).read_text()
        revoke = (ROOT / "docs/sql" / f"{PREFIX}_REVOKE_LOGIN.sql").read_text()

        def role_state():
            return db.rows(
                "SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,"
                "rolcreaterole,rolcreatedb,rolreplication FROM pg_roles "
                "WHERE rolname IN ("
                + ",".join("'" + n + "'" for n in ROLES)
                + ") ORDER BY rolname"
            )

        baseline = role_state()
        try:
            db.run(enable)
        except RpcFailure as error:
            assert error.sqlstate == "P0001"
        else:
            raise AssertionError("Missing SCRAM must deny LOGIN activation")
        assert role_state() == baseline
        for name in ROLES:
            # Synthetic value used only inside this new loopback cluster.
            db.run(
                "SET password_encryption='scram-sha-256';"
                f"ALTER ROLE {name} PASSWORD 'local-only-not-a-staging-credential'"
            )
        db.run(enable)
        assert all(row["rolcanlogin"] is True for row in role_state())
        assert [{**row, "rolcanlogin": False} for row in role_state()] == baseline
        assert db.rows(
            "SELECT count(*) FROM pg_roles WHERE rolname IN ("
            + ",".join("'" + n + "'" for n in ROLES)
            + ") AND rolvaliduntil > clock_timestamp()+interval '23 hours' "
            "AND rolvaliduntil <= clock_timestamp()+interval '24 hours'"
        ) == [{"count": 5}]
        db.run(revoke)
        db.run(revoke)  # Idempotent credential cleanup.
        assert role_state() == baseline
        assert db.rows(
            "SELECT count(*) FROM pg_authid WHERE rolname IN ("
            + ",".join("'" + n + "'" for n in ROLES)
            + ") AND rolpassword IS NULL AND rolvaliduntil < clock_timestamp()"
        ) == [{"count": 5}]
        print(
            "PASS: missing-secret denial, five bounded LOGINs, unchanged flags, idempotent revocation"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    check(parser.parse_args().pg_bin)
