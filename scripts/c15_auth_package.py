"""Build the fresh-install supported-hook candidate without rewriting history.

This is NOT migration execution. No remote connection/configuration is used.
"""

import argparse
import hashlib
from pathlib import Path


def supported_sql(root: Path) -> str:
    directory = root / "supabase/migrations"
    legacy = directory / "20261029010000_privacy_confirmation_foundation.sql"
    if (
        hashlib.sha256(legacy.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        != "1c44db79073424a334910d9ac460ef6a22d6711ae76c47e367c97af66e13ceff"
    ):
        raise ValueError("Historical migration changed; review packaging explicitly")
    before, marker, rest = legacy.read_text().partition("-- Auth-table commit guard")
    _, ending, after = rest.partition(
        "create function public.privacy_email_send_guard()"
    )
    if not marker or not ending:
        raise ValueError("Historical package boundaries missing")
    pieces = [before + ending + after]
    for name in (
        "20261029020000_privacy_auth_recovery.sql",
        "20261030010000_privacy_auth_integration.sql",
        "20261030020000_privacy_email_otp.sql",
    ):
        pieces.append((directory / name).read_text())
    content = "\n".join(
        line
        for piece in pieces
        for line in piece.splitlines()
        if line.strip().lower() not in {"begin;", "commit;"}
    )
    return (
        "-- PENDING: fresh C15 install candidate; default off, no keys. Not remote authorization.\n-- Do not combine with historical C15 migration execution. See Stage 1C report.\nbegin;\n"
        + content
        + "\ncommit;\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        supported_sql(Path(__file__).resolve().parents[1]), encoding="utf-8"
    )
