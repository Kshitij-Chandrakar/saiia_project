"""Native retention and isolated synthetic restore; no real Auth/provider."""
# ruff: noqa: F401,F811 -- imported native fixtures are required by pytest

import json
import re
import secrets
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from app.privacy_content import ContentBlocked, ContentEngine
from app.privacy_notifications import PrivacyNotifier
from app.privacy_remaining import Minimizer, RetentionWorker
from app.privacy_restore import RestoreGate, RestoreJournal
from app.privacy_schema import MANIFEST, candidate_manifest, validate_schema
from app.privacy_settings import public_settings
from test_privacy_content_native import (
    Storage,
    case,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    privacy,
    seed,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True
ROOT = Path(__file__).parents[2]


@pytest.fixture
def remaining(content, request):
    u, engine, *_ = content
    db = u["db"]
    if not db.rows(
        "select 1 from pg_tables where tablename='privacy_minimized_records'"
    ):
        db.run(
            "create table if not exists storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[])"
        )
        db.run(
            (
                ROOT / "supabase/migrations/20260731123545_enable_rls_and_storage.sql"
            ).read_text(encoding="utf-8")
        )
        # Supabase supplies these managed-Storage privileges/RLS in the real
        # stack; the native metadata fixture explicitly reproduces them.
        db.run(
            "alter table storage.objects enable row level security;grant usage on schema storage to authenticated;grant select on storage.objects,profiles to authenticated"
        )
        # Complete the public account-data schema omitted by the earlier focused
        # commercial fixture, without modifying any managed Auth implementation.
        for column, table, name in (
            (
                "location",
                "job_contexts",
                "20260809120000_add_cloud_job_context_lifecycle.sql",
            ),
            (
                "terms_accepted",
                "profiles",
                "20260904170000_add_signup_consent_preferences.sql",
            ),
            (
                "onboarding_current_step",
                "user_settings",
                "20261016120000_add_dashboard_onboarding_state.sql",
            ),
        ):
            if not db.rows(
                f"select 1 from information_schema.columns where table_name='{table}' and column_name='{column}'"
            ):
                db.run(
                    (ROOT / "supabase/migrations" / name).read_text(encoding="utf-8")
                )
        if not db.rows(
            "select 1 from pg_tables where tablename='marketing_unsubscribe_tokens'"
        ):
            db.run(
                (
                    ROOT
                    / "supabase/migrations/20260905103000_add_marketing_unsubscribe_tokens.sql"
                ).read_text(encoding="utf-8")
            )
        for column, name in (
            ("selected_model_key", "20261018120000_add_session_model_selection.sql"),
            ("selected_model_binding", "20261018180000_add_session_model_bindings.sql"),
        ):
            if not db.rows(
                f"select 1 from information_schema.columns where table_name='interview_sessions' and column_name='{column}'"
            ):
                db.run(
                    (ROOT / "supabase/migrations" / name).read_text(encoding="utf-8")
                )
        db.run(
            (
                ROOT
                / "supabase/migrations/20261018210000_harden_session_generation_recovery.sql"
            ).read_text(encoding="utf-8")
        )
        db.run(
            (
                ROOT
                / "supabase/migrations/20261030140000_privacy_retention_restore.sql"
            ).read_text(encoding="utf-8")
        )
    if request.config.getoption("--c15-prepare-fields", default=False):
        with engine.transaction() as c:
            manifest = candidate_manifest(c)
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return content


def accept(remaining, days=0):
    u, e, _storage, service, actor, document = remaining
    service.call(actor, "challenge", document)
    service.call(actor, "confirm", {**document, "confirmation_text": "delete"})
    if days:
        # Synthetic fixture clock, never a production retirement override.
        with e.transaction() as c:
            c.execute(
                "update privacy_deletion_requests set accepted_at=clock_timestamp()-%s::interval where account_id=%s",
                (f"{days} days", u["account"]),
            )


def security_email(remaining, kind="account_security"):
    u, e, *_ = remaining
    event = str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into outbound_email_events(id,user_id,email_type,recipient_email,idempotency_key,status,metadata_json) values(%s,%s,%s,%s,%s,'sent','{\"legacy_private\":\"SYNTHETIC_PRIVATE_PAYLOAD\"}')",
            (
                event,
                u["account"],
                kind,
                u["account"] + "@example.invalid",
                str(uuid4()),
            ),
        )
    return event


def retention(remaining):
    _u, e, *_ = remaining

    def connect():
        c = e.connect()
        c.execute("set session authorization privacy_retention_executor")
        c.commit()
        return c

    return RetentionWorker(connect)


def test_complete_field_inventory_and_drift(remaining):
    _u, e, *_ = remaining
    with e.transaction() as c:
        # This full-coverage assertion follows the current ordered forward
        # schema; the older focused fixture intentionally omits these tables.
        c.execute("savepoint full_schema")
        for migration in (
            "20261031100000_privacy_retirement_preparation.sql",
            "20261031120000_privacy_auto_credentials.sql",
        ):
            script = (ROOT / "supabase/migrations" / migration).read_text(
                encoding="utf8"
            )
            # Keep this isolated schema assertion inside its savepoint rather
            # than allowing the migration's outer transaction to commit it.
            c.execute(re.sub(r"(?m)^(begin|commit);\s*$", "", script))
        assert validate_schema(c, require_full=True)["tables"] > 30
        c.execute("alter table profiles add column synthetic_new_private_field text")
        with pytest.raises(ContentBlocked, match="unclassified_field"):
            validate_schema(c)
        c.execute("alter table profiles drop column synthetic_new_private_field")
        c.execute("rollback to savepoint full_schema")


def test_settings_lossless_and_sensitive_legacy_blocked():
    value = {"theme": "dark", "position": {"x": 12, "y": 9}, "muted": True}
    assert public_settings(value) == value
    for value in (
        {"access_token": "secret"},
        {"password": "secret"},
        {"safe": "Bearer private"},
    ):
        with pytest.raises(ContentBlocked):
            public_settings(value)


def test_email_private_payload_minimized_without_financial_mutation(remaining):
    u, e, *_ = remaining
    event = security_email(remaining)
    accept(remaining)
    result = Minimizer(e).run(u["account"])
    assert result["minimized"]["email"] == 1
    assert Minimizer(e).run(u["account"])["minimized"]["email"] == 0
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from outbound_email_events where id=%s", (event,)
            ).fetchone()[0]
            == 0
        )
        row = c.execute(
            "select source_kind,category,event_kind,outcome from privacy_minimized_records where account_id=%s",
            (u["account"],),
        ).fetchone()
        assert row == ("security_email", "security_audit", "account_security", "sent")
        assert (
            c.execute(
                "select count(*) from account_plan_bindings where account_id=%s",
                (u["account"],),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("age,eligible", [(179, False), (181, True)])
def test_security_retention_clock_and_integrity(remaining, age, eligible):
    u, e, *_ = remaining
    security_email(remaining)
    accept(remaining, age)
    Minimizer(e).run(u["account"])
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "update privacy_minimized_records set outcome='rewritten' where account_id=%s",
            (u["account"],),
        )
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "delete from privacy_minimized_records where account_id=%s", (u["account"],)
        )
    assert retention(remaining).run_one() is eligible


def test_retention_concurrent_claim_and_restart(remaining):
    u, e, *_ = remaining
    security_email(remaining)
    accept(remaining, 181)
    Minimizer(e).run(u["account"])
    worker = retention(remaining)
    with ThreadPoolExecutor(2) as pool:
        leases = [str(uuid4()), str(uuid4())]
        claims = list(pool.map(lambda lease: worker.call("claim", lease), leases))
    assert sum(bool(x) for x in claims) == 1
    winner = leases[0] if claims[0] else leases[1]
    assert worker.call("finish", winner)["removed"]
    with pytest.raises(psycopg.Error):
        worker.call("finish", winner)


@pytest.mark.parametrize(
    "kind",
    [
        "welcome",
        "ai_notes_ready",
        "session_summary",
        "transcript_export",
        "marketing_product_update",
    ],
)
def test_ordinary_email_metadata_removed_during_primary_cleanup(remaining, kind):
    u, e, *_ = remaining
    event = security_email(remaining, kind)
    accept(remaining, 181)
    Minimizer(e).run(u["account"])
    assert not retention(remaining).run_one()
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from outbound_email_events where id=%s", (event,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from privacy_minimized_records where account_id=%s",
                (u["account"],),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("age,eligible", [(89, False), (91, True)])
def test_usage_recovery_90_day_clock(remaining, age, eligible):
    u, e, *_ = remaining
    _resume, session, _key = seed(remaining)
    run = str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into subscription_auto_runs(run_id,account_id,request_id,semantic_hash,active) values(%s,%s,%s,%s,false)",
            (run, u["account"], str(uuid4()), "a" * 64),
        )
        c.execute(
            "insert into subscription_relay_frames(run_id,account_id,session_id,source,last_hash,bytes_received) values(%s,%s,%s,'microphone',%s,1024)",
            (run, u["account"], session, "b" * 64),
        )
    accept(remaining, age)
    assert Minimizer(e).run(u["account"])["minimized"]["relay"] == 1
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from subscription_relay_frames where account_id=%s",
                (u["account"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from subscription_auto_runs where account_id=%s",
                (u["account"],),
            ).fetchone()[0]
            == 1
        )
    assert retention(remaining).run_one() is eligible


def test_retention_expired_lease_recovers_and_stale_worker_is_denied(remaining):
    u, e, *_ = remaining
    security_email(remaining)
    accept(remaining, 181)
    Minimizer(e).run(u["account"])
    worker = retention(remaining)
    old = str(uuid4())
    new = str(uuid4())
    assert worker.call("claim", old)
    with e.transaction() as c:
        c.execute(
            "update privacy_minimized_records set lease_until=clock_timestamp()-interval '1 second' where account_id=%s",
            (u["account"],),
        )
    assert worker.call("claim", new)
    with pytest.raises(psycopg.Error):
        worker.call("finish", old)
    assert worker.call("finish", new)["removed"]


def test_privacy_notifications_reuse_durable_contract_and_never_claim_full_erasure(
    remaining, caplog
):
    from app.email.dry_run_provider import DryRunEmailProvider
    from app.email.event_store import OutboundEmailEventService
    from app.email.service import EmailService
    from test_email_event_store import FakeEventClient

    u, e, *_ = remaining
    accept(remaining)
    provider = DryRunEmailProvider()
    events = FakeEventClient()
    service = EmailService(
        provider, event_store=OutboundEmailEventService(client=events)
    )
    notifier = PrivacyNotifier(e, service)
    with caplog.at_level("INFO"):
        notifier.notify(u["account"], "accepted")
        notifier.notify(u["account"], "accepted")
    assert len(provider.records) == 1
    assert len(events.claim_calls) == 2
    assert u["account"] + "@example.invalid" not in caplog.text
    assert "recipient=" not in caplog.text
    with pytest.raises(ContentBlocked):
        notifier.notify(u["account"], "primary_verified")
    with pytest.raises(ContentBlocked):
        notifier.notify(u["account"], "fully_deleted")


def test_notification_sql_guard_rejects_forged_target_and_unverified_completion(
    remaining,
):
    u, e, *_ = remaining
    accept(remaining)
    document = remaining[-1]
    for kind, email in [
        ("privacy_primary_verified", u["account"] + "@example.invalid"),
        ("privacy_request_accepted", "different@example.invalid"),
    ]:
        with pytest.raises(psycopg.Error), e.transaction() as c:
            c.execute(
                "insert into outbound_email_events(user_id,email_type,recipient_email,idempotency_key,status,pending_expires_at,metadata_json) values(%s,%s,%s,%s,'pending',clock_timestamp()+interval '5 minutes',%s::jsonb)",
                (
                    u["account"],
                    kind,
                    email,
                    str(uuid4()),
                    json.dumps({"privacy_request": document["request_id"]}),
                ),
            )
    with e.transaction() as c:
        result = c.execute(
            "select * from claim_outbound_email_event(%s,null,'privacy_request_accepted',%s,%s,%s::jsonb,clock_timestamp()+interval '5 minutes')",
            (
                u["account"],
                u["account"] + "@example.invalid",
                str(uuid4()),
                json.dumps({"privacy_request": document["request_id"]}),
            ),
        ).fetchone()
        assert result


def test_event_store_logging_does_not_include_provider_error_payload(caplog):
    import requests
    from app.email.event_store import SupabaseOutboundEmailEventClient

    response = requests.Response()
    response.status_code = 400
    response._content = b'{"message":"PRIVATE_FILENAME resume.pdf Bearer PRIVATE_TOKEN","code":"PRIVATE_CODE"}'
    client = object.__new__(SupabaseOutboundEmailEventClient)
    with caplog.at_level("ERROR"):
        client._log_failure("claim", response)
    assert "status=400" in caplog.text
    assert "PRIVATE" not in caplog.text and "resume.pdf" not in caplog.text


def test_journal_replay_and_old_checkpoint_fail_closed(remaining, tmp_path):
    u, e, *_ = remaining
    journal = RestoreJournal(
        tmp_path / "journal", {"v1": secrets.token_bytes(32)}, "v1"
    )
    first = journal.initialize()
    accept(remaining)
    latest = RestoreGate(e).publish(u["account"], journal, first)
    assert RestoreGate(e).publish(u["account"], journal, latest) == latest
    with pytest.raises(ContentBlocked):
        RestoreGate(e).apply(journal, first)
    with e.transaction() as c:
        assert not c.execute("select ready from privacy_restore_state").fetchone()[0]
        c.execute("update privacy_restore_state set required=false")


def test_quarantine_applies_to_native_authenticated_rls_reads(remaining, tmp_path):
    u, e, *_ = remaining
    seed(remaining)

    def visible():
        with e.transaction() as c:
            c.execute(
                "select set_config('request.jwt.claim.sub',%s,true)", (u["account"],)
            )
            c.execute("set local role authenticated")
            return c.execute(
                "select count(*) from profiles where user_id=%s", (u["account"],)
            ).fetchone()[0]

    assert visible() == 1
    journal = RestoreJournal(
        tmp_path / "evidence", {"v1": secrets.token_bytes(32)}, "v1"
    )
    head = journal.initialize()
    with pytest.raises(ContentBlocked):
        RestoreGate(e).apply(journal, "wrong-checkpoint")
    assert visible() == 0
    RestoreGate(e).apply(journal, head)
    assert visible() == 1


def test_retention_clock_category_cannot_be_relabelled(remaining):
    u, e, *_ = remaining
    accept(remaining, 181)
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "insert into privacy_minimized_records(account_id,source_kind,source_id,category,event_kind,outcome,confirmation_at,eligible_at) select account_id,'ordinary_email',%s,'security_audit','welcome','sent',accepted_at,accepted_at+interval '180 days' from privacy_deletion_requests where account_id=%s",
            (str(uuid4()), u["account"]),
        )


def test_restore_missing_or_tampered_evidence_stays_quarantined(remaining, tmp_path):
    _u, e, *_ = remaining
    journal = RestoreJournal(
        tmp_path / "outside-restored-dataset",
        {"synthetic": secrets.token_bytes(32)},
        "synthetic",
    )
    gate = RestoreGate(e)
    with pytest.raises(ContentBlocked):
        gate.apply(journal, "missing")
    with e.transaction() as c:
        assert c.execute(
            "select required,ready from privacy_restore_state"
        ).fetchone() == (True, False)
        c.execute("update privacy_restore_state set required=false")
    head = journal.initialize()
    journal.path.write_bytes(journal.path.read_bytes() + b"truncated")
    with pytest.raises(ContentBlocked):
        gate.apply(journal, head)
    with e.transaction() as c:
        assert not c.execute("select ready from privacy_restore_state").fetchone()[0]
        c.execute("update privacy_restore_state set required=false")


def test_isolated_native_restore_replays_external_deletion(remaining, tmp_path):
    u, e, storage, *_ = remaining
    _resume, _session, key = seed(remaining)
    db = u["db"]
    clone = db.directory / "restore-data"
    # A clean, cold physical snapshot of this disposable PG17 cluster. No
    # hosted backup, installed service, Auth engine or customer data is involved.
    db.command("pg_ctl", ["-D", str(db.directory / "data"), "-m", "fast", "-w", "stop"])
    try:
        shutil.copytree(db.directory / "data", clone)
    finally:
        db.command(
            "pg_ctl",
            [
                "-D",
                str(db.directory / "data"),
                "-l",
                str(db.directory / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {db.port}",
                "-w",
                "start",
            ],
        )
    journal = RestoreJournal(
        tmp_path / "external-deletion-evidence",
        {"synthetic": secrets.token_bytes(32)},
        "synthetic",
    )
    head = journal.initialize()
    accept(remaining)
    head = RestoreGate(e).publish(u["account"], journal, head)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    started = False
    try:
        db.command(
            "pg_ctl",
            [
                "-D",
                str(clone),
                "-l",
                str(db.directory / "restore.log"),
                "-o",
                f"-h 127.0.0.1 -p {port}",
                "-w",
                "start",
            ],
        )
        started = True

        def connect():
            return psycopg.connect(
                host="127.0.0.1",
                port=port,
                user="catalog_test_owner",
                dbname="postgres",
            )

        restored = ContentEngine(connect, storage, local_rehearsal=True)
        result = RestoreGate(restored).apply(journal, head)
        assert result["state"] == "restrictions_replayed"
        with pytest.raises(ContentBlocked):
            restored.request(u["account"], str(uuid4()))
        with pytest.raises(psycopg.Error), restored.transaction() as c:
            c.execute(
                "insert into profiles(user_id,full_name) values(%s,'resurrected') on conflict(user_id) do update set full_name='resurrected'",
                (u["account"],),
            )
        assert restored.queue_accepted()
        restored.run_one()
        assert ("resumes", key) not in storage.items
        with restored.transaction() as c:
            assert (
                c.execute("select count(*) from privacy_email_suppression").fetchone()[
                    0
                ]
                >= 1
            )
    finally:
        if started:
            db.command("pg_ctl", ["-D", str(clone), "-m", "fast", "-w", "stop"])
    # The parent Native fixture removes BOTH owned cluster directories only
    # after stopping its source postmaster. Journal stays outside the snapshot.


def test_session_restore_replays_without_erasing_reusable_resources(
    remaining, tmp_path
):
    u, e, *_ = remaining
    resume, session, _key = seed(remaining)
    job = e.request(u["account"], str(uuid4()), "session", session)
    journal = RestoreJournal(
        tmp_path / "session-evidence", {"v1": secrets.token_bytes(32)}, "v1"
    )
    head = journal.initialize()
    head = RestoreGate(e).publish(u["account"], journal, head, job_id=job)
    RestoreGate(e).apply(journal, head)
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from interview_sessions where id=%s", (session,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute("select count(*) from resumes where id=%s", (resume,)).fetchone()[
                0
            ]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from profiles where user_id=%s", (u["account"],)
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from privacy_restored_sessions where session_id=%s",
                (session,),
            ).fetchone()[0]
            == 1
        )


def test_restore_wrong_matching_key_keeps_service_quarantined(remaining, tmp_path):
    u, e, *_ = remaining
    accept(remaining)
    journal = RestoreJournal(
        tmp_path / "key-evidence", {"v1": secrets.token_bytes(32)}, "v1"
    )
    head = RestoreGate(e).publish(u["account"], journal, journal.initialize())
    with e.transaction() as c:
        c.execute(
            "update privacy_matching_keys set secret=%s", (secrets.token_bytes(32),)
        )
    with pytest.raises(ContentBlocked, match="restore_matching_key_unavailable"):
        RestoreGate(e).apply(journal, head)
    with e.transaction() as c:
        assert c.execute(
            "select required,ready from privacy_restore_state"
        ).fetchone() == (True, False)
