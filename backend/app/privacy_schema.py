"""Frozen field inventory: new columns/types need an explicit classification."""

import json
from pathlib import Path

from app.privacy_content import ContentBlocked, ContentEngine
from app.privacy_registry import (
    CONTENT,
    OPTIONAL_PRIVATE_SCHEMA,
    PRIVATE_LIFECYCLE,
    RETAINED,
    SAFE_METADATA,
)

MANIFEST = Path(__file__).with_name("privacy_fields.json")


def live_schema(cursor):
    columns = ContentEngine.columns(cursor)
    relevant = {
        t
        for t, c in columns.items()
        if {"__account_linked__", "account_id", "user_id"} & c
        or t in CONTENT
        or t in SAFE_METADATA
        or t in RETAINED
        or t in PRIVATE_LIFECYCLE
    }
    cursor.execute(
        "select table_name,column_name,data_type,udt_name from information_schema.columns where table_schema='public' order by table_name,ordinal_position"
    )
    result: dict[str, dict[str, str]] = {}
    for table, column, kind, udt in cursor.fetchall():
        if table in relevant:
            result.setdefault(table, {})[column] = kind + ":" + udt
    return result


def validate_schema(cursor, require_full=False):
    try:
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["tables"]
    except (OSError, ValueError):
        raise ContentBlocked("field_classification_unavailable") from None
    required = set(expected)
    expected.update(
        {
            table: {"fields": {name: {"type": kind} for name, kind in fields.items()}}
            for table, fields in OPTIONAL_PRIVATE_SCHEMA.items()
        }
    )
    actual = live_schema(cursor)
    for table, columns in actual.items():
        if table not in expected:
            raise ContentBlocked("unclassified_table:" + table)
        fields = expected[table]["fields"]
        if any(
            name not in fields or fields[name]["type"] != kind
            for name, kind in columns.items()
        ):
            raise ContentBlocked("unclassified_field:" + table)
    if require_full and any(
        t not in actual or set(actual[t]) != set(info["fields"])
        for t, info in expected.items()
        if t in required
    ):
        raise ContentBlocked("schema_coverage_incomplete")
    return {"classification_version": "c15.fields.v1", "tables": len(actual)}


def candidate_manifest(cursor):
    """Explicit test/bootstrap operation only, never called by request handling."""
    tables = {}
    for table, columns in live_schema(cursor).items():
        export = set((CONTENT | SAFE_METADATA).get(table, ("", None, ""))[2].split())
        fields = {}
        for name, kind in columns.items():
            disposition = "export_owned" if name in export else "exclude_export"
            if table in CONTENT:
                treatment = "account_cleanup; scoped cleanup only through registered owner/session joins"
            elif table in RETAINED or table in SAFE_METADATA:
                treatment = "retained envelope; legacy minimization/retirement blocked unless an explicit narrow worker handles this field"
            else:
                treatment = "private lifecycle/control evidence; explicit secret expiry or separate restore/suppression horizon"
            fields[name] = {"type": kind, "export": disposition, "deletion": treatment}
        tables[table] = {"fields": fields}
    return {"version": "c15.fields.v1", "tables": tables}
