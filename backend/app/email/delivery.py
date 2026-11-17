"""Verify Resend's raw payload with the supported Svix verifier; retain no PII."""

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID

from svix.webhooks import Webhook, WebhookVerificationError

EVENTS = frozenset(
    "email." + kind
    for kind in (
        "sent",
        "delivered",
        "delivery_delayed",
        "bounced",
        "complained",
        "failed",
    )
)


class DeliveryConflict(ValueError):
    pass


def configuration(secret, scope):
    if not secret.startswith("whsec_") or not re.fullmatch(
        r"[a-z][a-z0-9._-]{0,63}", scope
    ):
        raise RuntimeError("Delivery verification is not configured")
    try:
        if len(base64.b64decode(secret[6:], validate=True)) < 16:
            raise ValueError()
    except (ValueError, binascii.Error):
        raise RuntimeError("Delivery verification is not configured") from None


def verified_event(raw, headers, secret, scope, previous="", previous_until=""):
    configuration(secret, scope)
    required = ("svix-id", "svix-timestamp", "svix-signature")
    if len(raw) > 131072 or any(
        not headers.get(k) or len(headers[k]) > 1024 for k in required
    ):
        raise ValueError("Invalid callback")
    if len(headers["svix-id"]) > 120:
        raise ValueError("Invalid callback")
    keys = [secret]
    if previous and previous_until:
        until = datetime.fromisoformat(previous_until.replace("Z", "+00:00"))
        if until.tzinfo and datetime.now(timezone.utc) < until:
            keys.append(previous)
    verified = False
    for key in keys:
        try:
            Webhook(key).verify(raw, dict(headers))
            verified = True
            break
        except (WebhookVerificationError, ValueError, UnicodeError):
            verified = False
    if not verified:
        raise ValueError("Invalid callback")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result

    event = json.loads(raw, object_pairs_hook=unique_pairs)
    if (
        not isinstance(event, dict)
        or not isinstance(event.get("data"), dict)
        or not isinstance(event.get("created_at"), str)
        or not isinstance(event.get("type"), str)
    ):
        raise TypeError("Invalid callback shape")
    if event["type"] not in EVENTS:
        raise ValueError("Unsupported callback")
    occurred = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
    if not occurred.tzinfo:
        raise ValueError("Invalid callback time")
    detail = "unspecified"
    if event["type"] == "email.bounced":
        bounce = event["data"].get("bounce", {})
        if isinstance(bounce, dict) and bounce.get("type") in (
            "Permanent",
            "Temporary",
        ):
            detail = bounce["type"]
    elif event["type"] == "email.failed":
        failed = event["data"].get("failed", {})
        if isinstance(failed, dict) and failed.get("reason") == "reached_daily_quota":
            detail = "reached_daily_quota"
    return {
        "failure_detail": detail,
        "scope": scope,
        "delivery_id": headers["svix-id"],
        "raw_hash": hashlib.sha256(raw).hexdigest(),
        "message_id": str(UUID(event["data"]["email_id"])),
        "event_type": event["type"],
        "event_at": occurred.isoformat(),
    }
