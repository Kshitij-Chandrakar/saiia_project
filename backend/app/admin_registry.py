"""Frozen administration field classification; no implicit table/JSON treatment."""

import json
from pathlib import Path

from app.privacy_content import ContentBlocked

FIELDS = json.loads(
    Path(__file__).with_name("admin_fields.json").read_text(encoding="utf8")
)


def validate_admin_schema(actual):
    expected = {
        table: {name: field["type"] for name, field in entry["fields"].items()}
        for table, entry in FIELDS["tables"].items()
    }
    if actual != expected:
        raise ContentBlocked("administration_field_classification_incomplete")
    return FIELDS["version"]
