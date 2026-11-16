"""Account-owned settings JSON, not an untyped credential bag."""

import json
import math
import re

from app.privacy_content import ContentBlocked

SENSITIVE = re.compile(
    r"token|secret|password|credential|authorization|cookie|private.?key|suppression",
    re.IGNORECASE,
)
JOB_METADATA_FIELDS = frozenset({"filename", "mime_type", "byte_size", "source"})


def job_metadata(value):
    if (
        not isinstance(value, dict)
        or set(value) - JOB_METADATA_FIELDS
        or any(not isinstance(v, str) for v in value.values())
    ):
        raise ContentBlocked("job_metadata_unclassified")
    return value


def public_settings(value):
    """Preserve ordinary user-defined settings losslessly; reject unsafe legacy
    objects rather than silently dropping keys. Schema columns remain explicit.
    """

    def visit(item, depth=0):
        if depth > 8:
            raise ContentBlocked("settings_shape_unverified")
        if isinstance(item, dict):
            for key, child in item.items():
                if (
                    not isinstance(key, str)
                    or not 1 <= len(key) <= 64
                    or SENSITIVE.search(key)
                ):
                    raise ContentBlocked("settings_sensitive_field")
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 4000 or re.search(
                r"Bearer\s|-----BEGIN", item, re.IGNORECASE
            ):
                raise ContentBlocked("settings_sensitive_value")
        elif (
            item is not None
            and type(item) not in (bool, int, float)
            or type(item) is float
            and not math.isfinite(item)
        ):
            raise ContentBlocked("settings_shape_unverified")

    if not isinstance(value, dict):
        raise ContentBlocked("settings_shape_unverified")
    visit(value)
    if len(json.dumps(value).encode()) > 65536:
        raise ContentBlocked("settings_size_exceeded")
    return value
