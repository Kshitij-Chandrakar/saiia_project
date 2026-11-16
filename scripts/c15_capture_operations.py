"""Development-only fixed-operation compiler input; never composed by runtime."""

import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import psycopg

original = psycopg.Cursor.execute
server_original = psycopg.ServerCursor.execute
records = {}
failures = []
output = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[1]
if not output.is_relative_to(root / "docs/evidence") or output.exists():
    raise ValueError("fresh repository evidence path required")
sys.argv = sys.argv[2:]


def execute(self, query, params=None, *args, **kwargs):
    caller = inspect.currentframe().f_back
    path = caller.f_code.co_filename.replace("\\", "/")
    result = (server_original if isinstance(self, psycopg.ServerCursor) else original)(
        self, query, params, *args, **kwargs
    )
    if "/app/privacy_" not in path or path.endswith("privacy_runtime.py"):
        return result
    text = (
        query.as_string(self.connection) if hasattr(query, "as_string") else str(query)
    )
    if (
        text.lower()
        .lstrip()
        .startswith(("set ", "savepoint ", "rollback ", "release "))
    ):
        return result
    values = [] if params is None else list(params)
    types = [x.type_code for x in (self.description or [])]
    count = 0

    def replace(m):
        nonlocal count
        if m.group() == "%%":
            return "%"
        count += 1
        return "$" + str(count)

    prepared = re.sub(r"%%|%s", replace, text)
    name = "c15_capture_" + hashlib.sha256(prepared.encode()).hexdigest()[:24]
    if count != len(values):
        failures.append({"sql": text, "reason": "arity"})
        return result
    try:
        for attempt in range(count + 1):
            try:
                with self.connection.transaction(), self.connection.cursor() as c:
                    original(c, "prepare " + name + " as " + prepared)
                    original(
                        c,
                        "select parameter_types::text[] from pg_prepared_statements where name=%s",
                        (name,),
                    )
                    pt = c.fetchone()[0]
                    original(c, "deallocate " + name)
                break
            except psycopg.errors.IndeterminateDatatype as e:
                number = int(re.search(r"\$(\d+)", e.diag.message_primary).group(1))
                value = values[number - 1]
                kind = "bytea" if isinstance(value, bytes) else "text"
                prepared = re.sub(
                    r"\$" + str(number) + r"(?![0-9])",
                    lambda _, number=number, kind=kind: "$" + str(number) + "::" + kind,
                    prepared,
                )
        else:
            raise RuntimeError("inference")
        key = hashlib.sha256(text.encode()).hexdigest()
        spec = {
            "sql": text,
            "prepared": prepared,
            "parameters": pt,
            "results": types,
            "source": Path(path).name,
            "method": caller.f_code.co_name,
        }
        if key in records and records[key]["parameters"] != pt:
            raise RuntimeError("inconsistent_signature")
        records[key] = spec
    except (psycopg.Error, RuntimeError, TypeError, ValueError) as e:
        failures.append({"sql": text, "reason": type(e).__name__})
    return result


psycopg.Cursor.execute = execute
psycopg.ServerCursor.execute = execute
try:
    import runpy

    runpy.run_path("scripts/c15_content_local_tests.py", run_name="__main__")
finally:
    with output.open("x", encoding="utf8") as target:
        target.write(
            json.dumps({"operations": records, "failures": failures}, indent=2)
        )
    print("fixed operations captured", len(records), "failures", len(failures))
