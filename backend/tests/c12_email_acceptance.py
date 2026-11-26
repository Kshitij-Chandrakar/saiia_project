"""Bounded C12 email acceptance. Default transport is deterministic, never Resend."""

import argparse
import hashlib
import json
import os
import re
import socket
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from app.email.billing import BillingNotifications, ResendBillingProvider
from app.email.config import EmailSettings
from razorpay_local_runtime import local_runtime
from test_billing_email_provider import Session
from test_billing_notifications_native import paid, sources
from app.email.provider import validate_recipient_email


def approved_recipient(value):
    recipient = validate_recipient_email(value)
    domain = recipient.rsplit("@", 1)[1].lower()
    if "." not in domain or domain.endswith((".invalid", ".test", ".example", ".localhost")):
        raise ValueError("Explicit approved deliverable recipient required")
    return recipient


@contextmanager
def journal_ownership(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "execution.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class BoundedSession:
    """Single-use journal: restarting cannot resume, reset or repeat sends."""

    def __init__(self, directory, sender, recipient, transport):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "execution.json"
        self.transport = transport
        self.sender = sender
        self.recipient = recipient
        self.state = {
            "attempts": 0,
            "maximum_attempts": 2,
            "maximum_minutes": 15,
            "started_utc": None,
            "deadline_utc": None,
            "mode": "substitute" if isinstance(transport, Session) else "actual_email",
            "recipient_sha256": hashlib.sha256(recipient.encode()).hexdigest(),
            "observations": [],
            "cleanup": "pending",
        }
        # Refuse an existing journal, including one left by a crashed process.
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.state, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def save(self):
        temporary = self.path.with_suffix(".pending")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.state, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def start_window(self):
        now = datetime.now(timezone.utc)
        if self.state["started_utc"] is None:
            self.state["started_utc"] = now.isoformat()
            self.state["deadline_utc"] = (now + timedelta(minutes=15)).isoformat()
            ist = timezone(timedelta(hours=5, minutes=30))
            self.state["started_ist"] = now.astimezone(ist).isoformat()
            self.state["deadline_ist"] = (
                (now + timedelta(minutes=15)).astimezone(ist).isoformat()
            )
        if now >= datetime.fromisoformat(self.state["deadline_utc"]):
            raise ValueError("Execution deadline limit reached")

    def post(self, url, **kwargs):
        payload = kwargs["json"]
        if (
            url != "https://api.resend.com/emails"
            or payload["to"] != [self.recipient]
            or payload["from"] != self.sender
            or not payload["subject"].startswith("[SYNTHETIC C12 TEST]")
            or kwargs.get("allow_redirects") is not False
            or kwargs.get("timeout") != (3, 10)
        ):
            raise ValueError("Transport/allowlist boundary rejected")
        self.start_window()
        if json.loads(self.path.read_text(encoding="utf-8"))["attempts"] != self.state["attempts"]:
            raise ValueError("Journal reservation changed; stop without dispatch")
        if self.state["attempts"] >= 2:
            raise ValueError("Execution limit reached; do not retry")
        self.state["attempts"] += 1
        observation = {
            "outcome": "dispatch_reserved",
            "idempotency_key": kwargs["headers"]["Idempotency-Key"],
        }
        self.state["observations"].append(observation)
        self.save()  # Reserve before dispatch, even when acceptance is uncertain.
        try:
            response = self.transport.post(url, **kwargs)
        except Exception:
            observation["outcome"] = "unknown_transport_result"
            self.save()
            raise
        observation.update(
            outcome="response_received", http_status=response.status_code
        )
        self.save()
        return response


class LabelledProvider:
    def __init__(self, provider):
        self.provider = provider

    def send_email(self, request):
        if request.email_type not in ("billing_payment", "billing_renewal"):
            raise ValueError("Acceptance permits only payment and renewal fixtures")
        return self.provider.send_email(
            replace(
                request,
                subject="[SYNTHETIC C12 TEST] " + request.subject,
                text_body="SYNTHETIC LOCAL BILLING FIXTURE. No new Razorpay payment.\n\n"
                + request.text_body,
                html_body="<p><strong>SYNTHETIC LOCAL BILLING FIXTURE. No new Razorpay payment.</strong></p>"
                + request.html_body,
            )
        )


@contextmanager
def save_notifications(journal, runtime):
    """Save recoverable dispatch state before disposing even a failed runtime."""
    try:
        yield
    finally:
        journal.state["notifications"] = runtime["db"].rows(
            "select id,kind,payload,delivery_state,attempts from billing_notification_sources order by created_at"
        )
        journal.state["messages"] = runtime["db"].rows(
            "select id,provider_message_id from outbound_email_events where email_type in ('billing_payment','billing_renewal')"
        )
        journal.save()


def execute(args, *, journal=None):
    # Remove the credential before PostgreSQL/test subprocess environment capture.
    credential = os.environ.pop("RESEND_API_KEY", "")
    if args.execute and (not credential or not args.sender_domain_verified):
        raise ValueError("RESEND_API_KEY and verified sender confirmation required")
    sender = args.sender if args.execute else "billing@synthetic.invalid"
    recipient = args.recipient if args.execute else "acceptance@synthetic.invalid"
    if not all(
        re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", value or "")
        for value in (sender, recipient)
    ):
        raise ValueError("Explicit sender and recipient required")
    transport = (
        journal.transport
        if journal
        else (requests.Session() if args.execute else Session())
    )
    transport.trust_env = False
    journal = journal or BoundedSession(
        Path(args.evidence), sender, recipient, transport
    )
    settings = EmailSettings(
        enabled=True,
        dry_run=False,
        resend_api_key=credential if args.execute else "synthetic",
        from_email=sender,
    )
    provider = ResendBillingProvider(settings, journal)
    directory = None
    port = None
    try:
        with (
            local_runtime(args.pg_bin, billing_email=True) as u,
            save_notifications(journal, u),
        ):
            directory, port = u["db"].directory, u["db"].port
            journal.state["database"] = {
                "host": "127.0.0.1",
                "port": port,
                "name": "postgres",
                "directory": str(directory),
                "synthetic_account": u["account"],
            }
            journal.save()
            # Parameter binding; never accept checkout/webhook recipient inputs.
            with (
                u["connect"]("catalog_test_owner") as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "update auth.users set email=%s,email_confirmed_at=clock_timestamp() where id=%s",
                    (recipient, u["account"]),
                )
            worker = BillingNotifications(
                lambda: u["connect"]("usage_binding_executor"),
                LabelledProvider(provider),
            )
            assert sources(u) == [], "Refuse pre-existing notification queue"
            op, raw, signature = paid(u)
            u["billing"].webhook(raw, signature)
            assert len(sources(u)) == 1
            worker.run()
            assert sources(u)[0]["delivery_state"] == "accepted", (
                "Send not accepted; stop without retry"
            )
            paid(u, offset=1, op=op)
            assert [row["kind"] for row in sources(u)] == [
                "billing_payment",
                "billing_renewal",
            ]
            worker.run()
            assert all(row["delivery_state"] == "accepted" for row in sources(u))
            # A repeated worker pass must not produce a third POST.
            repeated = worker.run()
            assert repeated["checked"] == 0 and journal.state["attempts"] == 2
            journal.state["result"] = "provider_accepted_not_inbox_confirmed"
            journal.save()
    finally:
        credential = ""
        provider.settings = EmailSettings()
        settings = EmailSettings()
        if hasattr(transport, "close"):
            transport.close()
        stopped = True
        if port:
            with socket.socket() as probe:
                probe.settimeout(1)
                stopped = probe.connect_ex(("127.0.0.1", port)) != 0
        journal.state["cleanup"] = {
            "database_removed": bool(directory and not directory.exists()),
            "database_port_closed": stopped,
            "credential_references_cleared": True,
        }
        journal.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--sender")
    parser.add_argument("--recipient")
    parser.add_argument("--sender-domain-verified", action="store_true")
    options = parser.parse_args()
    try:
        execute(options)
    except (ValueError, RuntimeError, OSError, AssertionError) as error:
        # Do not emit exception bodies, credentials, addresses or HTTP headers.
        print("Acceptance stopped:", type(error).__name__, "(see redacted journal)")
        raise SystemExit(1) from None
    print("Acceptance finished; inspect redacted journal. Inbox delivery is separate.")
