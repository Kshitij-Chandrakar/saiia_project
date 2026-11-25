"""Single-use C12 callback acceptance. Real transport requires --execute."""

import argparse
import base64
import getpass
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import dotenv

# Isolated fixture runtime must never load the workspace's operational dotenv.
dotenv.load_dotenv = lambda *args, **kwargs: False

import requests
import uvicorn
from app.config import settings
from app.email.billing import BillingNotifications, ResendBillingProvider
from app.email.config import EmailSettings
from c12_email_acceptance import BoundedSession, LabelledProvider, approved_recipient
from razorpay_local_runtime import local_runtime
from svix.webhooks import Webhook
from test_billing_email_provider import Session
from test_billing_notifications_native import paid, sources
from test_catalog_store_native import MANAGER
from test_draft_api_native import headers

from scripts import c12_resend_gateway as gateway

logger = logging.getLogger(__name__)

SENDER = "billing@intervucopilot.in"
RECIPIENT = "acceptance-recipient@example.invalid"
SCOPE = "c12-resend-callback-01"
ASSETS = (
    "https://rbmxfazjbldmkomdpyzl.supabase.co/storage/v1/object/public/email-assets"
)


class OneSend(BoundedSession):
    def __init__(self, directory, transport, recipient=RECIPIENT, *, live=False):
        super().__init__(directory, SENDER, recipient, transport)
        self.live = live
        self.lock = threading.RLock()
        self.state.update(
            maximum_attempts=1,
            maximum_forwarded_callbacks=12,
            forwarded_callbacks=[],
            stage="local_preflight",
            replay_verified=False,
            provider_webhook_disable="not_yet_confirmed",
            real_provider_calls=0,
        )
        self.save()

    def save(self):
        if hasattr(self, "lock"):
            with self.lock:
                super().save()
        else:
            super().save()

    def post(self, url, **kwargs):
        payload = kwargs["json"]
        if (
            self.state["attempts"] >= 1
            or "reply_to" in payload
            or "/auth/dashboard" in payload["html"]
            or "/auth/dashboard" in payload["text"]
        ):
            raise ValueError("Single-send/CTA boundary rejected")
        try:
            return super().post(url, **kwargs)
        finally:
            self.state["real_send_attempt_reservations"] = self.state["attempts"] if self.live else 0
            self.state["real_provider_calls"] = sum(row["outcome"] == "response_received" for row in self.state["observations"]) if self.live else 0
            self.save()

    def active(self):
        return self.state["deadline_utc"] and datetime.now(
            timezone.utc
        ) < datetime.fromisoformat(self.state["deadline_utc"])

    def stage(self, stage, **facts):
        with self.lock:
            self.state.update(stage=stage, **facts)
            self.save()


def listener(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def await_provider_disable(journal, directory):
    marker = directory / "webhook-disabled.confirmed"
    while not marker.exists() and journal.active():
        time.sleep(1)
    confirmed = marker.exists()
    journal.state["provider_webhook_disable"] = "owner_confirmed_disabled" if confirmed else "unconfirmed_cleanup_required"
    if not confirmed:
        settings.RESEND_BILLING_WEBHOOK_SECRET = ""
    journal.save()
    return confirmed


def stop_tunnel(tunnel):
    if tunnel.poll() is None:
        tunnel.terminate()
    try:
        tunnel.wait(timeout=15)
    except subprocess.TimeoutExpired:
        tunnel.kill()
        tunnel.wait(timeout=5)


def forwarding_exhausted(rows):
    return len(rows) >= 12 and not any(row["status"] == "reserved" for row in rows)


def completion_stage(state):
    complete = (state.get("result") and not state.get("error_type")
                and not state.get("cleanup_error_type") and not state.get("cleanup_snapshot_error_type") and all(state["cleanup"].values())
                and state["provider_webhook_disable"] in {"owner_confirmed_disabled", "substitute_no_endpoint"})
    return "finished" if complete else "stopped"


def server(app, port, stack):
    if listener(port):
        raise ValueError("Acceptance port already in use")
    instance = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_level="critical",
            log_config=None,
            lifespan="off",  # The existing fixture already owns application lifespan.
        )
    )
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()

    def close():
        instance.should_exit = True
        thread.join(timeout=8)

    stack.callback(close)
    end = time.monotonic() + 10
    while not instance.started:
        if not thread.is_alive() or time.monotonic() >= end:
            raise RuntimeError("Local service startup failed")
        time.sleep(0.1)


def snapshot(journal, u):
    journal.state["notifications"] = u["db"].rows(
        "select id,kind,delivery_state,attempts,delivery_scope,resend_message_id from billing_notification_sources"
    )
    journal.state["messages"] = u["db"].rows(
        "select id,provider,provider_message_id,status from outbound_email_events where email_type='billing_payment'"
    )
    journal.state["receipts"] = u["db"].rows(
        "select scope,delivery_id,raw_hash,message_id,event_type,event_at,recorded_at,processing_state,attempts,processed_at from billing_email_delivery_events order by recorded_at"
    )
    journal.save()


def execute(args):
    directory = Path(args.evidence)
    recipient = approved_recipient(getattr(args, "recipient", None)) if args.execute else RECIPIENT
    # Refuse reuse before asking for any secret.
    if (directory / "execution.json").exists():
        raise ValueError("Existing journal: no resume/reset/send retry")
    key = (
        getpass.getpass("RESEND_API_KEY (masked, process only): ")
        if args.execute
        else "synthetic"
    )
    if not key:
        raise ValueError("Missing sending credential")
    transport = requests.Session() if args.execute else Session()
    transport.trust_env = False
    journal = OneSend(directory, transport, recipient, live=args.execute)
    provider = ResendBillingProvider(
        EmailSettings(
            enabled=True, dry_run=False, resend_api_key=key, from_email=SENDER
        ),
        journal,
    )
    key = ""
    tunnel = None
    db_directory = None
    db_port = None
    webhook_may_exist = False
    original_forward = gateway.forward
    logging.getLogger("httpx").setLevel(logging.WARNING)
    os.environ["EMAIL_ASSET_BASE_URL"] = ASSETS
    os.environ.pop("EMAIL_WEBSITE_ORIGIN", None)
    settings.RESEND_BILLING_WEBHOOK_SECRET = ""
    settings.RESEND_BILLING_WEBHOOK_PREVIOUS_SECRET = ""
    settings.RESEND_BILLING_WEBHOOK_PREVIOUS_UNTIL = ""
    try:
        with ExitStack() as stack:
            local_log = stack.enter_context(
                (directory / "local-runtime.log").open("w", encoding="utf-8")
            )
            with redirect_stdout(local_log), redirect_stderr(local_log):
                u = stack.enter_context(local_runtime(args.pg_bin, billing_email=True))
                # Only the deterministic fixture adapter can manufacture this transition.
                assert type(u["provider"]).__module__ == "test_billing_native"
                assert sources(u) == []
                paid(u)
                assert len(sources(u)) == 1
            db_directory, db_port = u["db"].directory, u["db"].port
            journal.state["database"] = {
                "directory": str(db_directory),
                "port": db_port,
                "host": "127.0.0.1",
                "name": "postgres",
            }
            settings.RESEND_BILLING_WEBHOOK_SCOPE = SCOPE
            with u["connect"]("catalog_test_owner") as connection:
                connection.execute(
                    "update auth.users set email=%s,email_confirmed_at=clock_timestamp() where id=%s",
                    (recipient, u["account"]),
                )
            worker = BillingNotifications(
                lambda: u["connect"]("usage_binding_executor"),
                LabelledProvider(provider),
            )
            u["client"].app.state.billing_notifications = worker
            gateway.UPSTREAM_PORT = 8122
            gateway.attempts = 0
            gateway.deadline = float("inf")  # No public ingress exists during setup.

            def forward(raw, hdrs):
                with journal.lock:
                    if (
                        not journal.active()
                        or len(journal.state["forwarded_callbacks"]) >= 12
                    ):
                        return 503
                    row = {
                        "delivery_id_sha256": hashlib.sha256(
                            hdrs["svix-id"].encode()
                        ).hexdigest(),
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "at": datetime.now(timezone.utc).isoformat(),
                        "status": "reserved",
                    }
                    journal.state["forwarded_callbacks"].append(row)
                    journal.save()
                status = original_forward(raw, hdrs)
                with journal.lock:
                    row["status"] = status
                    journal.save()
                return status

            gateway.forward = forward
            server(u["client"].app, 8122, stack)
            server(gateway.app, 8123, stack)
            journal.start_window()
            journal.save()
            gateway.deadline = time.monotonic() + max(
                0,
                (
                    datetime.fromisoformat(journal.state["deadline_utc"])
                    - datetime.now(timezone.utc)
                ).total_seconds(),
            )
            if args.execute:
                clean_env = {
                    k: v
                    for k, v in os.environ.items()
                    if k.upper()
                    in {
                        "PATH",
                        "SYSTEMROOT",
                        "WINDIR",
                        "TEMP",
                        "TMP",
                        "USERPROFILE",
                        "LOCALAPPDATA",
                        "APPDATA",
                    }
                }
                tunnel_log = stack.enter_context(
                    (directory / "tunnel.log").open("w", encoding="utf-8")
                )
                tunnel = subprocess.Popen(
                    [
                        args.cloudflared,
                        "tunnel",
                        "--url",
                        "http://127.0.0.1:8123",
                        "--no-autoupdate",
                    ],
                    stdout=tunnel_log,
                    stderr=subprocess.STDOUT,
                    env=clean_env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )

                def close_external():
                    nonlocal tunnel
                    provider.settings = EmailSettings()
                    if webhook_may_exist:
                        journal.stage("awaiting_provider_disable")
                        await_provider_disable(journal, directory)
                    try:
                        snapshot(journal, u)
                    except Exception as error:
                        logger.exception("Cleanup snapshot unavailable", exc_info=False)
                        journal.state["cleanup_snapshot_error_type"] = type(
                            error
                        ).__name__
                        journal.save()
                    if tunnel:
                        stop_tunnel(tunnel)
                        tunnel = None

                stack.callback(close_external)
                journal.state["tunnel_pid"] = tunnel.pid
                deadline = time.monotonic() + 60
                url = None
                while time.monotonic() < deadline and journal.active():
                    match = re.search(
                        r"https://[a-z0-9-]+\.trycloudflare\.com",
                        (directory / "tunnel.log").read_text(
                            encoding="utf-8", errors="replace"
                        ),
                    )
                    if match:
                        url = match.group() + gateway.PATH
                        break
                    if tunnel.poll() is not None:
                        raise RuntimeError("Tunnel did not start")
                    time.sleep(1)
                if not url:
                    raise RuntimeError("Tunnel URL unavailable")
                webhook_may_exist = True
                journal.stage("awaiting_webhook_secret", webhook_url=url)
                print("Create ONE temporary Resend webhook:", url, flush=True)
                print(
                    "Select only email.sent and email.delivered. Enter its whsec_ signing secret below.",
                    flush=True,
                )
                secret = getpass.getpass(
                    "RESEND_BILLING_WEBHOOK_SECRET (masked, process only): "
                )
            else:
                secret = (
                    "whsec_"
                    + base64.b64encode(b"synthetic acceptance signing secret").decode()
                )
            if not journal.active():
                raise RuntimeError("Deadline reached before send")
            from app.email.delivery import configuration

            configuration(secret, SCOPE)
            settings.RESEND_BILLING_WEBHOOK_SECRET = secret
            secret = ""
            try:
                worker.run()  # Exactly one isolated source; transport hard limit is one.
            finally:
                provider.settings = EmailSettings()
            snapshot(journal, u)
            if sources(u)[0]["delivery_state"] != "accepted":
                raise RuntimeError("Sending uncertain or rejected; never resend")
            journal.stage(
                "awaiting_signed_delivery",
                real_provider_responses=journal.state["real_provider_calls"],
            )
            if not args.execute:
                message = journal.state["messages"][0]["provider_message_id"]
                raw = json.dumps(
                    {
                        "type": "email.delivered",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "data": {"email_id": message},
                    }
                ).encode()
                now = datetime.now(timezone.utc)
                hdrs = {
                    "content-type": "application/json",
                    "svix-id": "msg_local_acceptance",
                    "svix-timestamp": str(int(now.timestamp())),
                    "svix-signature": Webhook(
                        settings.RESEND_BILLING_WEBHOOK_SECRET
                    ).sign("msg_local_acceptance", now, raw.decode()),
                }
                with requests.Session() as callback_client:
                    callback_client.trust_env = False
                    for _ in range(2):
                        response = callback_client.post(
                            "http://127.0.0.1:8123" + gateway.PATH,
                            data=raw, headers=hdrs, timeout=20, allow_redirects=False,
                        )
                        assert response.status_code == 200
            poll_at = 0
            while journal.active():
                if time.monotonic() >= poll_at:
                    worker.delivery_call("process")
                    snapshot(journal, u)
                    poll_at = time.monotonic() + 5
                receipts = journal.state.get("receipts", [])
                delivered = [
                    e
                    for e in receipts
                    if e["event_type"] == "email.delivered"
                    and e["processing_state"] == "applied"
                ]
                if delivered:
                    event = delivered[0]
                    digest = hashlib.sha256(event["delivery_id"].encode()).hexdigest()
                    matching = [
                        r
                        for r in journal.state["forwarded_callbacks"]
                        if r["delivery_id_sha256"] == digest
                        and r["raw_sha256"] == event["raw_hash"]
                        and r["status"] == 200
                    ]
                    if len(matching) >= 2:
                        assert (
                            sum(
                                e["delivery_id"] == event["delivery_id"]
                                for e in receipts
                            )
                            == 1
                        )
                        journal.stage("replay_verified", replay_verified=True)
                        break
                    journal.stage(
                        "awaiting_one_manual_replay",
                        delivery_message_id=event["message_id"],
                    )
                if forwarding_exhausted(journal.state["forwarded_callbacks"]):
                    raise RuntimeError("Callback forwarding budget reached")
                time.sleep(1)
            if not journal.state["replay_verified"]:
                raise RuntimeError("Deadline reached; incomplete callback acceptance")
            u["db"].run(
                f"insert into subscription_admin_permissions(subject_id,permission,active,approved_by,reason) values('{MANAGER}','billing.read',true,'{MANAGER}','synthetic callback inspection') on conflict(subject_id,permission) do update set active=true,revision=subscription_admin_permissions.revision+1"
            )
            response = u["client"].get(
                "/api/admin/billing/" + u["account"], headers=headers(MANAGER)
            )
            assert response.status_code == 200
            journal.state["admin_snapshot"] = response.json()
            denial = u["client"].get(
                "/api/admin/billing/" + u["account"], headers=headers(u["account"])
            )
            assert denial.status_code == 403
            journal.state["admin_denial_status"] = denial.status_code
            journal.state["admin_audit"] = u["db"].rows(
                "select actor,target,action,outcome,recorded_at from billing_admin_audit order by id"
            )
            journal.state["result"] = "signed_delivery_and_replay_verified"
            journal.save()
            # The provider must be disabled before ExitStack stops services/tunnel.
            if args.execute:
                journal.stage("awaiting_provider_disable")
                await_provider_disable(journal, directory)
            else:
                journal.state["provider_webhook_disable"] = "substitute_no_endpoint"
            if tunnel:
                stop_tunnel(tunnel)
                tunnel = None
            journal.stage("cleanup_in_progress")
    except Exception as error:
        journal.stage("stopped", error_type=type(error).__name__)
        raise
    finally:
        provider.settings = EmailSettings()
        settings.RESEND_BILLING_WEBHOOK_SECRET = ""
        settings.RESEND_BILLING_WEBHOOK_PREVIOUS_SECRET = ""
        settings.RESEND_BILLING_WEBHOOK_SCOPE = ""
        gateway.forward = original_forward
        transport.close() if hasattr(transport, "close") else None
        if tunnel:
            # Do not silently claim external cleanup on an abnormal exit.
            journal.state["provider_webhook_disable"] = (
                "unconfirmed_cleanup_required" if webhook_may_exist else "not_created"
            )
            try:
                stop_tunnel(tunnel)
            except Exception as error:
                journal.state["cleanup_error_type"] = type(error).__name__
        journal.state["cleanup"] = {
            "database_removed": bool(db_directory and not db_directory.exists()),
            "database_port_closed": not listener(db_port) if db_port else True,
            "backend_port_closed": not listener(8122),
            "gateway_port_closed": not listener(8123),
            "credential_references_cleared": True,
            "tunnel_stopped": tunnel is None or tunnel.poll() is not None,
        }
        journal.stage(completion_stage(journal.state))
    return journal.state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--cloudflared")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--recipient")
    args = parser.parse_args()
    try:
        execute(args)
    except Exception as error:
        logger.exception("Acceptance stopped", exc_info=False)
        print(
            "Acceptance stopped:",
            type(error).__name__,
            "See redacted execution.json; do not resend.",
            flush=True,
        )
        raise SystemExit(1) from None
    print(
        "Acceptance finished. Check redacted evidence; inbox confirmation is separate.",
        flush=True,
    )
