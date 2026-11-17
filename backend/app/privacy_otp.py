"""Purpose-bound mailbox proof. Delivery is injected; no real sender is wired."""

import hashlib
import hmac
import secrets
from typing import Any

from app.privacy_credentials import CredentialBox


def matches(
    box: CredentialBox, subject: str, document: dict[str, Any], code: str = ""
) -> dict[str, Any]:
    def keyed(key: bytes, purpose: str, value: str) -> str:
        import json

        key = hmac.new(key, b"c15.email-otp.hmac-key.v1", hashlib.sha256).digest()

        context = json.dumps(
            [
                purpose + document.get("purpose", ""),
                subject,
                document["request_id"],
                document["session_id"],
                value,
            ]
        )
        return hmac.new(key, context.encode(), hashlib.sha256).hexdigest()

    email = str(document.get("verified_email") or "").strip().lower()
    return {
        "otp_hashes": {
            version: keyed(key, "c15.email-otp.code.v1", code)
            for version, key in box._keys.items()
        },
        "email_fingerprints": {
            version: keyed(key, "c15.email-otp.address.v1", email)
            for version, key in box._keys.items()
        },
    }


def reserve(
    box: CredentialBox, subject: str, document: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    code = f"{secrets.randbelow(100000000):08d}"
    hashed = matches(box, subject, document, code)
    version = box._current
    return code, {
        **document,
        "otp_key_version": version,
        "otp_hash": hashed["otp_hashes"][version],
        "email_fingerprint": hashed["email_fingerprints"][version],
    }
