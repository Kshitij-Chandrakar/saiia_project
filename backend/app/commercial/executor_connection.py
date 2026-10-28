"""Explicit staging session routing; SQL authority remains the unsuffixed role."""

from dataclasses import dataclass
from pathlib import Path

STAGING_PROJECT = "cfmvqbjmnwklxqlpelxe"
STAGING_SESSION_HOST = "aws-0-ap-south-1.pooler.supabase.com"
EXECUTORS = frozenset(
    {
        "usage_executor",
        "catalog_draft_executor",
        "catalog_public_reader",
        "usage_binding_executor",
        "usage_reconciler",
    }
)
_KEYS = {"host", "port", "dbname", "user", "password", "sslmode", "sslrootcert"}


@dataclass(frozen=True)
class SessionPooler:
    # Trusted operator configuration from Dashboard Connect, never request data.
    host: str
    project: str = STAGING_PROJECT

    def __post_init__(self):
        if self.project != STAGING_PROJECT or self.host != STAGING_SESSION_HOST:
            raise ValueError("executor connection unavailable")


def connection_parameters(dsn, role, *, session_pooler=None):
    """No role normalization/SET ROLE: keep routing user intact for the driver."""
    from psycopg import Error
    from psycopg.conninfo import conninfo_to_dict

    try:
        if role not in EXECUTORS:
            raise ValueError
        args = {k: str(v) for k, v in conninfo_to_dict(dsn).items() if v is not None}
        host = args.get("host", "")
        local = host in {"127.0.0.1", "::1", "localhost"}
        port = int(args.get("port", "5432"))
        if (
            set(args) - _KEYS
            or not host
            or "," in host
            or not args.get("dbname")
            or not 1 <= port <= 65535
            or args.get("sslmode")
            not in ({"disable", "verify-full"} if local else {"verify-full"})
            or (not local and not args.get("password"))
        ):
            raise ValueError
        if session_pooler is not None:
            if not isinstance(session_pooler, SessionPooler):
                raise ValueError
            if (
                host != session_pooler.host
                or port != 5432
                or args.get("dbname") != "postgres"
                or args.get("user") != role + "." + session_pooler.project
                or not args.get("sslrootcert")
                or not Path(args["sslrootcert"]).is_file()
            ):
                raise ValueError
        elif (
            args.get("user") != role
            or host.lower().rstrip(".").endswith(".pooler.supabase.com")
            or (host.lower().rstrip(".").endswith(".supabase.co") and port == 6543)
        ):
            # Pooler routing must be explicit, pinned, TLS-verified and session-only.
            raise ValueError
        return args
    except (Error, ValueError, TypeError, OSError):
        # A driver parse exception can contain the original secret-bearing DSN.
        raise ValueError("executor connection unavailable") from None


def check_executor_identity(conn, role):
    """Used by trusted fixture connections without a runtime pool of their own."""
    from psycopg import Error

    try:
        if role not in EXECUTORS:
            raise ValueError
        row = conn.execute(
            "SELECT session_user,current_user,current_setting('role'),"
            "rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication OR rolinherit "
            "FROM pg_roles WHERE rolname=session_user"
        ).fetchone()
        if row != (role, role, "none", False):
            raise ValueError
        if conn.execute(
            "SELECT EXISTS(SELECT FROM pg_auth_members WHERE member="
            "(SELECT oid FROM pg_roles WHERE rolname=session_user))"
        ).fetchone()[0]:
            raise ValueError
        conn.commit()
    except (Error, ValueError, TypeError):
        try:
            conn.rollback()
        except Error:
            raise RuntimeError("executor connection unavailable") from None
        raise RuntimeError("executor connection unavailable") from None


def restore_executor_timeouts(conn):
    """RESET ALL may restore server defaults rather than pooler startup options."""
    conn.execute("SET lock_timeout=5000")
    conn.execute("SET statement_timeout=10000")
    conn.execute("SET idle_in_transaction_session_timeout=15000")
    conn.execute("SET transaction_timeout=20000")


def connect_executor(dsn, role, *, session_pooler=None):
    """Bounded one-shot binding/reconciler fixture connection; no provider work."""
    from psycopg import Error, connect

    conn = None
    try:
        args = connection_parameters(dsn, role, session_pooler=session_pooler)
        conn = connect(
            **args,
            connect_timeout=3,
            prepare_threshold=None,
            options="-c lock_timeout=5000 -c statement_timeout=10000 "
            "-c idle_in_transaction_session_timeout=15000 -c transaction_timeout=20000",
        )
        check_executor_identity(conn, role)
        return conn
    except (Error, ValueError, RuntimeError, OSError, TypeError):
        if conn is not None:
            conn.close()
        raise RuntimeError("executor connection unavailable") from None
