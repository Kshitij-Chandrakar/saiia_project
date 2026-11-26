"""Single hidden prompt; staging-only provision/smoke/revoke, no migrations."""

import argparse
import getpass
import json
import os
import secrets
import sys
import time
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import smoke_staging_session_pooler as smoke
from app.commercial.executor_connection import (
    EXECUTORS,
    STAGING_PROJECT,
    STAGING_SESSION_HOST,
)
from psycopg import Connection, Error, OperationalError, sql

ROOT = Path(__file__).resolve().parents[2]
# This historical acceptance scope must not expand when product roles are added.
ROLES = (
    "catalog_draft_executor",
    "catalog_public_reader",
    "usage_binding_executor",
    "usage_executor",
    "usage_reconciler",
)
assert set(ROLES) <= EXECUTORS
FAILURES = (
    Error,
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    AssertionError,
    KeyboardInterrupt,
    ImportError,
    LookupError,
    AttributeError,
)


def stage(name):
    print("STAGE: " + name, flush=True)


def error_code(error):
    # Error messages, SQL text and driver tracebacks may contain secret material.
    code = getattr(error, "sqlstate", None)
    return type(error).__name__ + (
        ":" + code
        if isinstance(code, str) and len(code) == 5 and code.isalnum()
        else ""
    )


def safe_cause(error):
    """Classify locally; never return any substring of a driver message."""
    if isinstance(error, MaintenanceConnectionFailure):
        return str(error)
    message = str(error).lower()
    for pattern, category in (
        ("password authentication failed", "authentication_rejected"),
        ("tenant or user not found", "pooler_route_rejected"),
        ("certificate verify failed", "tls_certificate_rejected"),
        ("does not match host name", "tls_hostname_rejected"),
        ("connection refused", "connection_refused"),
        ("could not translate host name", "dns_failed"),
        ("timeout expired", "connection_timeout"),
        ("connection timeout", "connection_timeout"),
        ("too many clients", "connection_capacity"),
        ("max client connections", "connection_capacity"),
        ("maintenance identity mismatch", "identity_mismatch"),
    ):
        if pattern in message:
            return category
    return "unclassified_" + type(error).__name__


class MaintenanceConnectionFailure(OperationalError):
    """Contains only a fixed safe category, never an original driver message."""


def require_intake():
    if datetime.now(timezone.utc) >= smoke.DEADLINE - timedelta(minutes=5):
        raise RuntimeError("intake closed; reserve time for cleanup")


def require_cleanup_window():
    if datetime.now(timezone.utc) >= smoke.DEADLINE:
        raise RuntimeError("approval expired; remote work stopped")


@contextmanager
def single_workflow():
    # A non-secret, OS-held lock is released even if the operator closes the app.
    (ROOT / "tmp").mkdir(exist_ok=True)
    lock = (ROOT / "tmp/c132-staging-session.lock").open("a+b")
    try:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)
    finally:
        lock.close()


class OwnerConnection(Connection):
    def __repr__(self):
        return "<staging maintenance connection>"

    def execute(self, *args, **kwargs):
        guard = getattr(self, "_workflow_guard", None)
        if guard is not None:
            guard()
        return super().execute(*args, **kwargs)

    def close(self):
        timer = getattr(self, "_deadline_timer", None)
        if timer is not None:
            timer.cancel()
        super().close()


def connect_owner(password, ca):
    import threading

    require_cleanup_window()
    conn = None
    try:
        conn = OwnerConnection.connect(
            host=STAGING_SESSION_HOST,
            port=5432,
            dbname="postgres",
            user="postgres." + STAGING_PROJECT,
            password=password,
            sslmode="verify-full",
            sslrootcert=str(ca.resolve()),
            connect_timeout=3,
            autocommit=True,
            prepare_threshold=None,
            application_name="c132.staging.controller",
            options="-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=20000 -c transaction_timeout=30000",
        )
        remaining = max(
            0, (smoke.DEADLINE - datetime.now(timezone.utc)).total_seconds()
        )
        conn._deadline_timer = threading.Timer(remaining, conn.close)
        conn._deadline_timer.daemon = True
        conn._deadline_timer.start()
        if conn.execute(
            "SELECT session_user,current_user,current_setting('role')"
        ).fetchone() != ("postgres", "postgres", "none"):
            conn.close()
            raise RuntimeError("maintenance identity mismatch")
        return conn
    except (Error, ValueError, OSError, RuntimeError) as error:
        if conn is not None:
            conn.close()
        raise MaintenanceConnectionFailure(safe_cause(error)) from None


def read_state(conn):
    require_cleanup_window()
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            "SELECT rolname,rolcanlogin,rolpassword IS NULL,"
            "coalesce(rolvaliduntil<clock_timestamp(),false),"
            "rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit,"
            "EXISTS(SELECT FROM pg_auth_members WHERE member=r.oid) "
            "FROM pg_authid r WHERE rolname=ANY(%s) ORDER BY rolname",
            (list(ROLES),),
        ).fetchall()
        sessions = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",
            (list(ROLES),),
        ).fetchone()[0]
    if tuple(row[0] for row in rows) != ROLES:
        raise RuntimeError("expected executor set missing")
    return {
        "roles": [
            {
                "name": r[0],
                "login": r[1],
                "password_cleared": r[2],
                "expired": r[3],
                "elevated": r[4],
                "member": r[5],
            }
            for r in rows
        ],
        "executor_sessions": sessions,
    }


def is_clean(state):
    return (
        state["executor_sessions"] == 0
        and len(state["roles"]) == 5
        and all(
            not r["login"]
            and r["password_cleared"]
            and r["expired"]
            and not r["elevated"]
            and not r["member"]
            for r in state["roles"]
        )
    )


@contextmanager
def project_ownership(owner_factory):
    guard = owner_factory()
    try:
        require_cleanup_window()
        acquired = guard.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0))",
            ("intervucopilot:c132:" + STAGING_PROJECT,),
        ).fetchone()[0]
        if not acquired:
            raise RuntimeError("staging project already owned; no state inspected or changed")

        def check():
            require_cleanup_window()
            guard.execute("SELECT 1").fetchone()

        yield check
    finally:
        guard.close()


def cleanup(conn):
    require_cleanup_window()
    conn.rollback()
    with conn.transaction():
        for role in ROLES:
            require_cleanup_window()
            conn.execute(
                sql.SQL(
                    "ALTER ROLE {} NOLOGIN PASSWORD NULL VALID UNTIL '1970-01-01T00:00:00Z'"
                ).format(sql.Identifier(role))
            )
    # Wait for termination instead of assuming a delivered signal means gone.
    require_cleanup_window()
    conn.execute(
        "SELECT pg_terminate_backend(pid,1000) FROM pg_stat_activity WHERE usename=ANY(%s) AND pid<>pg_backend_pid()",
        (list(ROLES),),
    ).fetchall()
    state = read_state(conn)
    if not is_clean(state):
        raise RuntimeError("credential/session cleanup not verified")
    return state


def provision(conn, passwords):
    require_intake()
    if not is_clean(read_state(conn)):
        raise RuntimeError("refusing provisioning over unclean state")
    with conn.transaction():
        for role in ROLES:
            require_intake()
            # Same libpq client-side SCRAM encryption used by psql \password.
            # Plaintext never enters SQL, parameters, arguments or diagnostics.
            verifier = conn.pgconn.encrypt_password(
                passwords[role].encode(), role.encode(), b"scram-sha-256"
            ).decode()
            conn.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} VALID UNTIL {}").format(
                    sql.Identifier(role),
                    sql.Literal(verifier),
                    sql.Literal(smoke.DEADLINE.isoformat()),
                )
            )
            del verifier


def execute_workflow(
    owner_factory, role_smoke, *, cleanup_only=False, application=None
):
    result = {
        "target": STAGING_PROJECT,
        "provisioned": False,
        "smoke_passed": [],
        "cleanup_verified": False,
        "error": None,
        "cleanup_error": None,
        "migrations_rerun": False,
        "accounts_or_offers_created": False,
        "failed_stage": None,
        "cause": None,
        "cleanup_cause": None,
    }
    owner = None
    passwords = {}
    current_stage = "NOT_STARTED"
    ownership = ExitStack()
    check_ownership = None

    def mark(name):
        nonlocal current_stage
        current_stage = name
        if check_ownership is not None:
            check_ownership()
        stage(name)

    try:
        mark("ACQUIRE_PROJECT_OWNERSHIP")
        check_ownership = ownership.enter_context(project_ownership(owner_factory))
        mark("CONNECT_STAGING_MAINTENANCE")
        owner = owner_factory()
        owner._workflow_guard = check_ownership
        mark("READ_ONLY_CURRENT_STATE")
        state = read_state(owner)
        print(json.dumps(state), flush=True)  # Boolean status only; no verifier.
        if not is_clean(state):
            mark("RECOVER_PRIOR_CREDENTIALS")
            cleanup(owner)
        if not cleanup_only:
            if application is not None:
                mark("APPLICATION_AUTH_PREFLIGHT_READ_ONLY")
                application.auth_preflight()
            require_intake()
            passwords.update({role: secrets.token_urlsafe(48) for role in ROLES})
            if len(set(passwords.values())) != 5:
                raise RuntimeError("distinct credential generation failed")
            mark("PROVISION_TEMPORARY_EXECUTORS")
            provision(owner, passwords)
            result["provisioned"] = True
            if application is not None:
                mark("APPLICATION_ACCEPTANCE")
                result["application"] = application(owner, passwords)
            else:
                for role in ROLES:
                    require_intake()
                    mark("SMOKE_" + role)
                    role_smoke(role, passwords[role])
                    result["smoke_passed"].append(role)
    except FAILURES as error:
        result["error"] = error_code(error)
        result["failed_stage"] = current_stage
        result["cause"] = safe_cause(error)
        if isinstance(error, smoke.SessionCheckFailure):
            result["failure_check"] = str(error)
        if type(error).__module__ == "staging_application_acceptance":
            result["failure_check"] = error.safe_check
        print("STOP: " + result["error"], flush=True)
    finally:
        stage("FINAL_CLEANUP")
        try:
            if check_ownership is None:
                raise RuntimeError("ownership not acquired; cleanup not dispatched")
            check_ownership()
            require_cleanup_window()
            if owner is None or owner.closed:
                owner = (
                    owner_factory()
                )  # Cleanup-only recovery, never repeat provisioning.
                owner._workflow_guard = check_ownership
            try:
                result["final_state"] = cleanup(owner)
            except (Error, OSError):
                # A lost maintenance connection cannot erase the cleanup obligation.
                owner.close()
                check_ownership()
                owner = owner_factory()
                owner._workflow_guard = check_ownership
                check_ownership()
                result["final_state"] = cleanup(owner)
            result["cleanup_verified"] = True
            stage("CLEANUP_VERIFIED")
        except FAILURES as error:
            result["cleanup_error"] = error_code(error)
            result["cleanup_cause"] = safe_cause(error)
            print("CLEANUP FAILED: " + result["cleanup_error"], flush=True)
            print(
                "Secure recovery: rerun this script --cleanup-only in a private console within the approval window; after expiry report the unresolved state and stop remote work.",
                flush=True,
            )
        finally:
            passwords.clear()
            if owner is not None:
                try:
                    owner.close()
                except (Error, OSError, RuntimeError) as error:
                    result["cleanup_verified"] = False
                    result["cleanup_error"] = error_code(error)
                    print(
                        "CLEANUP FAILED: maintenance close " + result["cleanup_error"],
                        flush=True,
                    )
            ownership.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca", required=True, type=Path)
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--run-id", type=UUID, default=uuid4())
    parser.add_argument("--application", action="store_true")
    parser.add_argument("--launcher-gate", type=Path)
    args = parser.parse_args()
    if args.launcher_gate:
        expected = ROOT / "tmp" / ("c132-launch-" + str(args.run_id) + ".ready")
        if args.launcher_gate.resolve() != expected.resolve():
            raise RuntimeError("Invalid owned launcher gate")
        if os.name != "nt" and os.getpgrp() != os.getpid():
            os.setsid()
        gate_deadline = time.monotonic() + 20
        while not expected.is_file():
            require_cleanup_window()
            if time.monotonic() >= gate_deadline:
                raise RuntimeError("Owned launcher containment unavailable")
            time.sleep(.05)
        expected.unlink()
    if args.application and args.cleanup_only:
        parser.error("application and credential-only cleanup are separate")
    if not sys.stdin.isatty():
        raise RuntimeError("private interactive console required")
    # This affects only this private process, never the parent/normal services.
    for key in list(os.environ):
        if key.upper().startswith("PG"):
            del os.environ[key]
    if args.cleanup_only:
        require_cleanup_window()
    else:
        require_intake()
    with single_workflow():
        import ssl

        stage("VALIDATE_PINNED_TARGET_AND_CA")
        if not args.ca.is_file():
            raise RuntimeError("Dashboard CA file missing")
        ssl.create_default_context(cafile=str(args.ca))
        # Actual connect_owner enforces verify-full chain/hostname checking.
        # Avoid the smoke intake cutoff blocking cleanup-only in the final minutes.
        owner_credentials = [
            getpass.getpass(
                "Staging postgres maintenance password (hidden; asked once): "
            )
        ]
        application = None
        try:
            if args.application:
                from staging_application_acceptance import ApplicationAcceptance

                application = ApplicationAcceptance(
                    args.ca,
                    args.run_id,
                    getpass.getpass(
                        "Staging legacy anon key (hidden; public client key): "
                    ),
                    getpass.getpass(
                        "Staging legacy service_role key (hidden; Auth controller only): "
                    ),
                )
                require_intake()
            result = execute_workflow(
                lambda: connect_owner(owner_credentials[0], args.ca),
                lambda role, secret: smoke.run_role_smoke(role, secret, args.ca),
                cleanup_only=args.cleanup_only,
                application=application,
            )
            if application is not None:
                result["accounts_or_offers_created"] = bool(
                    application.state.get("accounts") or application.state.get("offers")
                )
                result["application_evidence"] = str(application.path.relative_to(ROOT))
                result["application_status"] = application.state.get(
                    "status", "not_started"
                )
                result["application_cleanup_errors"] = application.state[
                    "cleanup_errors"
                ]
                result["application_failure"] = application.state.get("failure")
        finally:
            owner_credentials.clear()
            if application is not None:
                application.clear_secrets()
        result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
        result["run_id"] = str(args.run_id)
        result["deadline_utc"] = smoke.DEADLINE.isoformat()
        print(json.dumps(result, indent=2), flush=True)
        # Only the sanitized result is persisted; credentials live in this process.
        payload = json.dumps(result, indent=2) + "\n"
        (ROOT / f"tmp/c132-session-{args.run_id}.json").write_text(
            payload, encoding="utf-8"
        )
        (ROOT / "tmp/c132-single-prompt-result.json").write_text(
            payload, encoding="utf-8"
        )
        return 0 if result["cleanup_verified"] and result["error"] is None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (*FAILURES, EOFError) as error:
        print("STOP: " + error_code(error), flush=True)
        raise SystemExit(1) from None
