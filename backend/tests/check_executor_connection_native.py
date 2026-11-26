"""Fresh loopback-only PostgreSQL: direct pools, ACLs, identity and session reset."""

import argparse
import os
import re
import time
from pathlib import Path

from app.commercial.catalog_database import CatalogDatabase
from app.commercial.executor_connection import EXECUTORS, connect_executor
from app.commercial.subscription_database import SubscriptionDatabase
from test_catalog_store_native import Native
from run_staging_session_workflow import ROLES

ROOT = Path(__file__).resolve().parents[2]
assert set(ROLES) <= EXECUTORS


def prove_scram_rejection(db, dsn, role):
    import psycopg
    from psycopg.conninfo import make_conninfo
    log = db.directory / "server.log"
    offset = log.stat().st_size
    try:
        wrong = psycopg.connect(make_conninfo(dsn, password="incorrect-synthetic-password"))
    except psycopg.Error as error:
        if error.sqlstate == "28P01":
            return
        # libpq may omit startup SQLSTATE; require the server's own 28P01 log.
        until = time.monotonic() + 2
        while time.monotonic() < until:
            with log.open("rb") as stream:
                stream.seek(offset)
                text = stream.read().decode("utf-8", errors="replace")
            if re.search(r'28P01:.*password authentication failed for user "' + re.escape(role) + '"', text):
                return
            time.sleep(.05)
        raise AssertionError("SCRAM invalid-password SQLSTATE not established") from None
    else:
        wrong.close()
        raise AssertionError("Incorrect password accepted; HBA reload not established")


def check(pg_bin):
    if any(key.upper().startswith("PG") for key in os.environ):
        raise RuntimeError("Inherited libpq configuration rejected; use a clean local rehearsal process")
    import smoke_staging_session_pooler as smoke

    # Local session-semantics reuse does not depend on remote activation dates.
    smoke.require_window = lambda: None
    db = Native(pg_bin)
    runtimes = []
    try:
        # Local fixture only: mirror the managed maintenance role name so the
        # exact staging script's identity guard is exercised, never relaxed.
        db.run("CREATE ROLE postgres LOGIN SUPERUSER")
        db.args[db.args.index("-U") + 1] = "postgres"
        # Same minimal managed interfaces as check_staging_packet_native; no Auth
        # calls, remote DSNs, inherited credentials or normal database connection.
        db.run("""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;
        create schema auth;create schema storage;create schema extensions;
        create table auth.users(id uuid primary key,created_at timestamptz default now(),email_confirmed_at timestamptz);
        create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        create function auth.role() returns text language sql stable as $$select current_setting('request.jwt.claim.role',true)$$;
        create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
        create table storage.objects(id uuid primary key,bucket_id text,name text);
        alter table storage.objects enable row level security;
        create function storage.foldername(text) returns text[] language sql as $$select string_to_array($1,'/')$$;
        grant usage on schema auth,storage,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        """)
        db.run(
            (
                ROOT
                / "docs/sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_APPLICATION_PENDING_APPROVAL.sql"
            ).read_text()
        )
        prefix = "C11_C13_STAGING_cfmvqbjmnwklxqlpelxe"
        for role in ROLES:
            db.run(
                "SET password_encryption='scram-sha-256';ALTER ROLE "
                + role
                + " PASSWORD 'synthetic-local-only'"
            )
        provision = (
            ROOT / "docs/sql" / (prefix + "_SESSION_PROVISION.psql")
        ).read_text()
        # psql password prompts are replaced ONLY by local synthetic passwords;
        # execute the exact remaining server-side guards and deadline-capped DDL.
        db.run(
            "\n".join(
                line for line in provision.splitlines() if not line.startswith("\\")
            )
        )
        db.run((ROOT / "docs/sql" / (prefix + "_REVOKE_LOGIN.sql")).read_text())
        db.run(
            (ROOT / "docs/sql" / (prefix + "_SESSION_CLEANUP_VERIFY.sql")).read_text()
        )
        print(
            "PASS: native deadline-capped provisioning and read-only credential/session cleanup verification"
        )
        for role in ROLES:
            db.run("ALTER ROLE " + role + " LOGIN")
            dsn = f"host=127.0.0.1 port={db.port} dbname=postgres user={role} sslmode=disable"
            conn = connect_executor(dsn, role)
            try:
                smoke.guard(conn, role)
                smoke.session_checks(conn, role)
                if role in {
                    "usage_executor",
                    "catalog_draft_executor",
                    "catalog_public_reader",
                }:
                    table = (
                        "usage_events" if role == "usage_executor" else "catalog_drafts"
                    )
                    signature = (
                        "public.subscription_current(uuid,boolean)"
                        if role == "usage_executor"
                        else (
                            "public.catalog_public_read()"
                            if role == "catalog_public_reader"
                            else "public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text)"
                        )
                    )
                    # Disposable DB only: prove batching retains both ACL denials.
                    db.run(f"GRANT SELECT ON public.{table} TO {role}")
                    try:
                        try:
                            smoke.guard(conn, role)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError("direct-table privilege was accepted")
                    finally:
                        db.run(f"REVOKE SELECT ON public.{table} FROM {role}")
                    db.run(f"REVOKE EXECUTE ON FUNCTION {signature} FROM {role}")
                    try:
                        try:
                            smoke.guard(conn, role)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError(
                                "missing function privilege was accepted"
                            )
                    finally:
                        db.run(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")
                    smoke.guard(conn, role)
            finally:
                conn.close()
            if role in {
                "catalog_draft_executor",
                "catalog_public_reader",
                "usage_executor",
            }:
                runtime = (
                    SubscriptionDatabase("true", dsn)
                    if role == "usage_executor"
                    else CatalogDatabase(
                        "true",
                        dsn,
                        public_only=role == "catalog_public_reader",
                        lifecycle_enabled=(
                            "true" if role == "catalog_draft_executor" else "false"
                        ),
                    )
                )
                runtimes.append(runtime)
                runtime.start()
                assert runtime._pool is not None, role
                with runtime.connect() as conn:
                    smoke.session_checks(conn, role)
                runtime.close()
            print(
                "PASS: direct "
                + role
                + " actual identity/ACLs, commit/rollback, failed-transaction reset, timeout restoration"
            )
        import psycopg
        import run_staging_session_workflow as workflow
        from psycopg.conninfo import make_conninfo

        # Require real password authentication for the five local executors.
        db.run("ALTER SYSTEM SET log_error_verbosity='verbose'")
        hba = db.directory / "data/pg_hba.conf"
        original_hba = hba.read_text()
        hba.write_text(
            "host postgres "
            + ",".join(ROLES)
            + " 127.0.0.1/32 scram-sha-256\n"
            + original_hba
        )
        db.command("pg_ctl", ["-D", str(db.directory / "data"), "reload"])
        workflow.require_intake = lambda: None
        workflow.require_cleanup_window = lambda: None

        def owner_factory():
            return psycopg.connect(
                host="127.0.0.1",
                hostaddr="127.0.0.1",
                port=db.port,
                dbname="postgres",
                user="postgres",
                autocommit=True,
            )

        def password_smoke(role, password):
            private_dsn = make_conninfo(
                host="127.0.0.1",
                port=db.port,
                dbname="postgres",
                user=role,
                password=password,
                sslmode="disable",
            )
            prove_scram_rejection(db, private_dsn, role)
            conn = connect_executor(private_dsn, role)
            try:
                smoke.session_checks(conn, role)
            finally:
                conn.close()

        result = workflow.execute_workflow(owner_factory, password_smoke)
        assert result["error"] is None and result["cleanup_verified"], result
        assert result["smoke_passed"] == list(workflow.ROLES)

        def fail_after_real_auth(role, password):
            password_smoke(role, password)
            raise RuntimeError("synthetic failure after real SCRAM authentication")

        failed = workflow.execute_workflow(owner_factory, fail_after_real_auth)
        assert failed["error"] == "RuntimeError" and failed["cleanup_verified"], failed
        assert failed["smoke_passed"] == []
        print(
            "PASS: five generated SCRAM passwords authenticated; success and injected-failure workflows verified NOLOGIN/NULL passwords/zero sessions"
        )
    finally:
        for runtime in runtimes:
            runtime.close()
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    check(parser.parse_args().pg_bin)
