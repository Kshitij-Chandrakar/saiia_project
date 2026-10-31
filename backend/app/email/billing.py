"""Billing adapter for the existing C10 outbound lifecycle. Default-off sending."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from uuid import UUID

import requests

from app.commercial.draft_service import DraftService
from app.config import settings
from app.email.billing_templates import receipt_content
from app.email.config import load_email_settings
from app.email.delivery import DeliveryConflict, verified_event
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.provider import EmailSendRequest, EmailValidationError

SUBJECTS = {
    "billing_payment": "Your payment is confirmed",
    "billing_renewal": "Your renewal payment is confirmed",
    "billing_cancellation": "Your renewal cancellation is confirmed",
    "billing_access_end": "Your paid access has ended",
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BillingTemplate:
    subject: str
    text: str
    html: str


def render_billing_email(kind, payload, *, brand=None):
    subject = SUBJECTS[kind]
    amount = str(payload["amount_minor"])
    if not amount.isascii() or not amount.isdigit() or payload["currency"] != "INR":
        raise EmailValidationError("Invalid billing money")
    paise = int(amount)
    formatted = f"INR {paise // 100:,}.{paise % 100:02d}"
    plan = str(payload["plan"])
    if len(plan) > 120 or any(ord(c) < 32 for c in plan):
        raise EmailValidationError("Invalid plan label")
    period = payload.get("period_end")
    when = "Not available"
    if period:
        parsed = datetime.fromisoformat(period.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise EmailValidationError("Billing date requires a timezone")
        when = parsed.strftime("%d %b %Y at %H:%M UTC%z")
    interval = payload["interval"]
    if interval not in ("month", "year"):
        raise EmailValidationError("Invalid billing interval")
    if kind in ("billing_payment", "billing_renewal"):
        text, html = receipt_content(
            kind, plan, formatted, interval, when if period else None, brand
        )
        return BillingTemplate(subject, text, html)
    details = [subject + ".", f"Plan: {plan}", f"Billing interval: {interval}"]
    if kind == "billing_cancellation":
        details += [
            "Future renewal has been stopped by the payment provider.",
            f"Paid access remains tied to its verified end: {when}",
        ]
    else:
        details += [
            f"Verified paid-period end: {when}",
            "At that end your account returned to Free. Check your account for its current plan. Fresh consent is required for a new paid subscription.",
        ]
    text = "Intervucopilot\n\n" + "\n".join(details)
    html = '<html><body style="background:#f5f7fb;color:#152a45;font-family:Arial,sans-serif;padding:24px"><main style="max-width:560px;margin:auto;background:white;border:1px solid #dde5ef;border-radius:16px;padding:28px"><h1 style="color:#235ac9;font-size:24px">Intervucopilot</h1>'
    html += (
        "".join("<p>" + escape(line) + "</p>" for line in details)
        + "</main></body></html>"
    )
    return BillingTemplate(subject, text, html)


class SendNotAccepted(Exception):
    """A definite provider rejection, eligible for bounded retries."""


class ResendBillingProvider:
    """Same configured C10 provider. Never retry an uncertain send automatically."""

    def __init__(self, settings=None, session=None):
        self.settings = settings or load_email_settings()
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.dry_run = DryRunEmailProvider()

    def send_email(self, request):
        settings = self.settings
        if not settings.live_delivery_requested:
            result = self.dry_run.send_email(request)
            return {
                "state": "dry_run",
                "provider": result.provider,
                "message_id": result.message_id,
            }
        if (
            settings.provider != "resend"
            or not settings.from_email
            or not settings.resend_api_key
            or not request.idempotency_key
        ):
            raise EmailValidationError("Billing email provider unavailable")
        payload = {
            "from": settings.from_email,
            "to": [request.recipient_email],
            "subject": request.subject,
            "text": request.text_body,
            "html": request.html_body,
        }
        if settings.reply_to:
            payload["reply_to"] = settings.reply_to
        # Resend supports this key for 24h. Timeout/crash remains unknown; do not
        # redispatch after that window or claim guaranteed exactly-once delivery.
        response = self.session.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": "Bearer " + settings.resend_api_key,
                "Idempotency-Key": request.idempotency_key,
            },
            json=payload,
            timeout=(3, 10),
            allow_redirects=False,
        )
        if response.status_code in (400, 401, 403, 422, 429):
            raise SendNotAccepted()
        if response.status_code != 200:
            raise RuntimeError("Uncertain provider result")
        return {
            "state": "accepted",
            "provider": "resend",
            "message_id": str(UUID(response.json()["id"])),
        }


class BillingNotifications:
    def __init__(self, connect, provider=None):
        self.channel = DraftService(connect)
        self.provider = provider or ResendBillingProvider()

    def call(self, action, identifier=None, document=None):
        return self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_notification_call(%s,%s,%s::jsonb)",
                (
                    action,
                    identifier,
                    json.dumps(
                        {
                            **(document or {}),
                            "scope": settings.RESEND_BILLING_WEBHOOK_SCOPE,
                        }
                    ),
                ),
            ),
        )

    def delivery_call(self, action, document=None):
        return self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_delivery_call(%s,%s::jsonb)",
                (action, json.dumps(document or {})),
            ),
        )

    def run(self):
        self.delivery_call("process")
        result = {"checked": 0, "accepted": 0, "unknown": 0}
        deadline = time.monotonic() + 20
        for identifier in self.call("list"):
            if time.monotonic() >= deadline:
                break
            job = self.call("claim", identifier)
            if not job:
                continue
            result["checked"] += 1
            try:
                template = render_billing_email(job["kind"], job["payload"])
                request = EmailSendRequest(
                    recipient_email=job["recipient"],
                    email_type=job["kind"],
                    subject=template.subject,
                    text_body=template.text,
                    html_body=template.html,
                    idempotency_key=job["idempotency_key"],
                )
                outcome = self.provider.send_email(request)
            except SendNotAccepted:
                outcome = {"state": "failed", "provider": "resend"}
            except Exception:
                # No exception text: it can contain recipients or credentials.
                logger.exception(
                    "Billing email result requires reconciliation", exc_info=False
                )
                outcome = {"state": "unknown", "provider": "resend"}
            self.call(
                "complete", identifier, {**outcome, "claim_token": job["claim_token"]}
            )
            if outcome["state"] in result:
                result[outcome["state"]] += 1
        return result

    def delivery(self, raw, headers, secret):
        event = verified_event(
            raw,
            headers,
            secret,
            settings.RESEND_BILLING_WEBHOOK_SCOPE,
            settings.RESEND_BILLING_WEBHOOK_PREVIOUS_SECRET,
            settings.RESEND_BILLING_WEBHOOK_PREVIOUS_UNTIL,
        )
        receipt = self.delivery_call("ingest", event)
        if receipt.get("error") == "conflict":
            raise DeliveryConflict("Conflicting callback identity")
        # Separate committed receipt: a crash here is recovered by the worker.
        self.delivery_call("process")
        return {"received": True}
