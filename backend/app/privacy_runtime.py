"""Default-disabled normal C15 composition; fixed principals, existing lifecycles."""

import base64
import json
import logging
import smtplib
import threading
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

import requests

from app.commercial.executor_connection import connect_executor
from app.email.event_store import (
    OutboundEmailEventService,
    SupabaseOutboundEmailEventClient,
)
from app.email.provider import EmailSendResult, utc_timestamp
from app.email.service import EmailService
from app.privacy_content import ContentBlocked, ContentEngine
from app.privacy_credentials import CredentialBox, GlobalLogout, PrivateAuthAdmin
from app.privacy_identity import IdentityCleanupWorker
from app.privacy_notifications import PrivacyNotifier
from app.privacy_remaining import RetentionWorker
from app.privacy_revocation import RevocationWorker, SessionRevocationObserver
from app.privacy_runtime_db import RuntimeConnection
from app.privacy_storage import PrivateStorage


class PrivateEvents(SupabaseOutboundEmailEventClient):
    def __init__(self, connect):
        self.connect = connect

    def _rpc(self, name, payload):
        with self.connect() as c:
            return c.execute(
                "select public.privacy_notice_event(%s,%s::jsonb)",
                (name, json.dumps(payload)),
            ).fetchone()[0]


class LocalCatcher:
    """Only an explicit synthetic rehearsal can use SMTP; no external relay."""

    def __init__(self, host, port):
        if host not in {"127.0.0.1", "localhost", "mail"} or not 0 < int(port) < 65536:
            raise ContentBlocked("catcher_configuration_invalid")
        self.host, self.port = host, int(port)

    def deliver(self, email, subject, body):
        if not email.endswith("@example.invalid") or any(c in email for c in "\r\n"):
            raise ContentBlocked("synthetic_recipient_required")
        message = EmailMessage()
        message["From"] = "privacy@example.invalid"
        message["To"] = email
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=5) as smtp:
            smtp.send_message(message)

    def send_email(self, message):
        self.deliver(message.recipient_email, message.subject, message.text_body)
        return EmailSendResult(
            "sent",
            "local_mailpit",
            str(uuid4()),
            False,
            "***",
            message.email_type,
            utc_timestamp(),
        )

    def code(self, email, code):
        self.deliver(
            email, "Your privacy confirmation code", "Confirmation code: " + code
        )


class PrivacyRuntime:
    def __init__(self, dsns, endpoints, coordinator_config):
        required = {
            "privacy_content_executor",
            "privacy_restore_executor",
            "privacy_cleanup_executor",
            "privacy_identity_executor",
            "privacy_revocation_observer",
            "privacy_retention_executor",
            "usage_executor",
        }
        if set(dsns) != required:
            raise ContentBlocked("runtime_principals_incomplete")
        self.dsns = dsns
        self.raw = lambda role: connect_executor(dsns[role], role)
        self.storage = PrivateStorage(
            endpoints["storage"], endpoints["service_key"], local_rehearsal=True
        )
        cleanup = lambda: self.raw("privacy_cleanup_executor")
        self.engine = ContentEngine(
            lambda: RuntimeConnection(
                self.raw("privacy_content_executor"), "privacy_content_executor"
            ),
            self.storage,
            local_rehearsal=True,
            credential_connect=cleanup,
        )
        self.restore_engine = ContentEngine(
            lambda: RuntimeConnection(
                self.raw("privacy_restore_executor"), "privacy_restore_executor"
            ),
            self.storage,
            local_rehearsal=True,
            credential_connect=cleanup,
        )
        self.box = CredentialBox.configured()
        self.mail = LocalCatcher(endpoints["smtp_host"], endpoints["smtp_port"])
        self.notifier = PrivacyNotifier(
            self.engine,
            EmailService(
                self.mail,
                event_store=OutboundEmailEventService(
                    client=PrivateEvents(lambda: self.raw("privacy_content_executor"))
                ),
            ),
        )
        self.admin = PrivateAuthAdmin(
            endpoints["auth"],
            endpoints["service_key"],
            local_rehearsal=True,
            standalone=endpoints.get("standalone_auth", False),
        )
        self.http = requests.Session()
        self.http.trust_env = False
        self.revocation = RevocationWorker(
            lambda: self.raw("usage_executor"),
            logout=GlobalLogout(
                self.box,
                endpoints["auth"],
                endpoints["anon_key"],
                self.http.post,
                local_rehearsal=True,
                standalone=endpoints.get("standalone_auth", False),
            ),
            verify=SessionRevocationObserver(
                lambda: self.raw("privacy_revocation_observer")
            ),
        )
        self.identity = IdentityCleanupWorker(
            lambda: self.raw("privacy_identity_executor"), self.admin
        )
        self.retention = RetentionWorker(lambda: self.raw("privacy_retention_executor"))
        from app.privacy_checkpoint import RestoreCoordinator
        from app.privacy_restore import RestoreJournal
        from app.privacy_witness import HTTPCheckpointStore

        c = coordinator_config
        keys = {
            k: base64.b64decode(v, validate=True) for k, v in c["journal_keys"].items()
        }
        journal = RestoreJournal(Path(c["journal"]), keys, c["journal_current"])
        store = HTTPCheckpointStore(
            c["witness_url"],
            c["witness_token"],
            base64.b64decode(c["witness_key"], validate=True),
            c["environment"],
            c["dataset"],
            local_rehearsal=True,
        )
        self.coordinator = RestoreCoordinator(
            self.restore_engine, journal, store, c["generation"], c["snapshot"]
        )
        self.stop = threading.Event()
        self.thread = None
        self.sweep_lock = threading.Lock()

    def prepare(self):
        for role in self.dsns:
            with self.raw(role):
                pass
        self.coordinator.reconcile()
        if not self.coordinator.ready():
            raise ContentBlocked("restore_quarantined")

    def sweep(self):
        if not self.sweep_lock.acquire(blocking=False):
            return
        try:
            # Recover an interrupted publication/reconciliation before touching
            # ordinary content workers, which correctly refuse quarantine.
            if not self.coordinator.ready():
                self.coordinator.seal_source()
                self.coordinator.reconcile()
            self.notices()
            self.revocation.run_one()
            self.engine.queue_accepted()
            self.engine.run_one()
            self.engine.expire_one()
            self.notices()
            self.identity.run_one()
            self.retention.run_one()
            # ponytail: reuse the verified source sealing/replay protocol, bounded by
            # the existing journal limit; incremental acknowledgement if profiling needs it.
            with self.coordinator.store.locked() as c:
                before = self.coordinator.store.read(c)["head"]
            self.coordinator.publish()
            with self.coordinator.store.locked() as c:
                after = self.coordinator.store.read(c)["head"]
            if before != after or not self.coordinator.ready():
                self.coordinator.seal_source()
                self.coordinator.reconcile()
        finally:
            self.sweep_lock.release()

    def notices(self):
        with self.raw("privacy_content_executor") as c:
            pending = c.execute("select public.privacy_pending_notices()").fetchone()[0]
        for item in pending:
            self.notifier.notify(item["account_id"], item["stage"])

    def start(self):
        def run():
            while not self.stop.wait(1):
                try:
                    self.sweep()
                except Exception as error:  # noqa: BLE001 -- durable retry without private driver/provider diagnostics
                    import traceback

                    logging.getLogger("privacy").warning(
                        "Privacy worker deferred: type=%s sqlstate=%s frames=%s",
                        type(error).__name__,
                        getattr(error, "sqlstate", None),
                        [
                            (f.name, f.lineno)
                            for f in traceback.extract_tb(error.__traceback__)
                        ],
                    )

        self.thread = threading.Thread(
            target=run, name="privacy-lifecycle", daemon=True
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=30)
        self.storage.http.close()
        self.admin.http.close()
        self.http.close()


def configure(app, settings):
    if getattr(settings, "C15_RUNTIME_ENABLED", "false") != "true":
        return None
    # Production stays disabled. This profile accepts only explicitly provisioned
    # isolated endpoints/keys; it never selects a production host/provider/region.
    if getattr(settings, "C15_RUNTIME_LOCAL_REHEARSAL", "false") != "true":
        raise ContentBlocked("production_activation_disabled")
    runtime = PrivacyRuntime(
        json.loads(settings.C15_RUNTIME_DSNS),
        json.loads(settings.C15_RUNTIME_ENDPOINTS),
        json.loads(settings.C15_RUNTIME_CHECKPOINT),
    )
    app.state.privacy_runtime = runtime
    app.state.privacy_content = runtime.engine
    app.state.privacy_export_box = runtime.box
    app.state.privacy_export_sender = runtime.mail.code
    app.state.privacy_otp_sender = runtime.mail.code
    app.state.restore_coordinator = runtime.coordinator
    return runtime
