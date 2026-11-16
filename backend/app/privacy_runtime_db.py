"""Private fixed-operation PostgreSQL adapter; no arbitrary server SQL API."""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from app.commercial.executor_connection import check_executor_identity, connect_executor
from app.privacy_content import ContentBlocked

OPERATIONS = json.loads(
    Path(__file__)
    .with_name("privacy_runtime_operations.json")
    .read_text(encoding="utf8")
)


def encode(value):
    if isinstance(value, bytes):
        return "\\x" + value.hex()
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    raise TypeError("unsupported operation value")


def decode(value, oid):
    if value is None:
        return None
    if oid == 17:
        return bytes.fromhex(value[2:])
    if oid == 2950:
        return UUID(value)
    if oid in (1184, 1114):
        # PostgreSQL JSON uses variable fractional precision; Python 3.10 accepts
        # only three/six digits and has no Z support.
        wire = re.sub(
            r"\.(\d{1,6})(?=[+-]|$)",
            lambda m: "." + m[1].ljust(6, "0"),
            value.replace("Z", "+00:00"),
        )
        return datetime.fromisoformat(wire)
    if oid == 1082:
        return date.fromisoformat(value)
    return value


class RuntimeCursor:
    def __init__(self, connection, name=None):
        self.connection = connection
        self.name = name
        self.rows = []
        self.rowcount = -1
        self.spec = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.name and self.spec:
            self.rpc("close", "", [])

    def rpc(self, action, key, args):
        return self.connection.raw.execute(
            "select public.privacy_runtime_call(%s,%s,%s::jsonb)",
            (action, key, json.dumps(args, default=encode)),
        ).fetchone()[0]

    def scope(self, job):
        self.connection.raw.execute(
            "select public.privacy_runtime_scope(%s,%s)", (job["id"], job["lease"])
        )

    def execute(self, statement, params=None):
        text = (
            statement.as_string(self.connection.raw)
            if hasattr(statement, "as_string")
            else statement
        )
        if text in ("set local statement_timeout='15s'", "set local lock_timeout='5s'"):
            self.connection.raw.execute(text)
            return self
        key = hashlib.sha256(text.encode()).hexdigest()
        self.spec = OPERATIONS.get(key)
        if self.spec is None:
            import inspect
            import logging

            current = inspect.currentframe()
            frame = current.f_back if current else None
            logging.getLogger("privacy").warning(
                "Fixed operation unavailable at %s:%s",
                frame.f_code.co_name if frame else "unknown",
                frame.f_lineno if frame else 0,
            )
            raise ContentBlocked("unregistered_runtime_operation")
        value = self.rpc(
            "open" if self.spec["stream"] else "execute", key, list(params or [])
        )
        self.rows = value.get("rows", [])
        self.rowcount = value.get("count", 0)
        return self

    def fetchone(self):
        if not self.rows:
            return None
        assert self.spec is not None
        row = self.rows.pop(0)
        return tuple(decode(v, t) for v, t in zip(row, self.spec["types"]))

    def fetchall(self):
        assert self.spec is not None
        rows = self.rows
        self.rows = []
        return [
            tuple(decode(v, t) for v, t in zip(row, self.spec["types"])) for row in rows
        ]

    def fetchmany(self, size=16):
        assert self.spec is not None
        if self.spec["stream"]:
            self.rows = self.rpc("fetch", "", [])["rows"]
        rows = self.rows[:size]
        self.rows = self.rows[size:]
        return [
            tuple(decode(v, t) for v, t in zip(row, self.spec["types"])) for row in rows
        ]

    def __iter__(self):
        return iter(self.fetchall())


class RuntimeConnection:
    def __init__(self, raw, role):
        check_executor_identity(raw, role)
        self.raw = raw

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, *args):
        return self.raw.__exit__(*args)

    def cursor(self, name=None):
        return RuntimeCursor(self, name)

    def execute(self, *args, **kw):
        return self.cursor().execute(*args, **kw)

    def transaction(self):
        return self.raw.transaction()


def runtime_connect(dsn, role="privacy_content_executor"):
    return RuntimeConnection(connect_executor(dsn, role), role)
