"""Real disposable PostgreSQL checks for C15 review findings."""

# ruff: noqa: F401,F811 -- imported native fixtures
import threading
from uuid import uuid4
import psycopg
import pytest
from app.privacy_content import ContentBlocked
from app.privacy_provisioning import ProvisioningGate
from test_privacy_runtime_native import (
    ROOT,
    accept,
    case,
    complete,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    owned_temporary_journals,
    prepared,
    pricing,
    privacy,
    remaining,
    restricted,
    runtime,
    seed,
    start,
    stop,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True


def test_history_waits_for_prior_session_erasure(content):
    u, e, *_ = content
    _, session, _ = seed(content)
    first, history = str(uuid4()), str(uuid4())
    e.request(u["account"], first, "session", session)
    with pytest.raises(ContentBlocked, match="previous_session_cleanup_pending"):
        e.request(u["account"], history, "history")
    with e.connect() as c:
        assert (
            c.execute(
                "select count(*) from privacy_content_jobs where id=%s", (history,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select state from privacy_content_jobs where id=%s", (first,)
            ).fetchone()[0]
            == "pending"
        )


def test_inactive_key_dependency_and_enabled_failure(complete):
    u, e, *_ = complete
    with e.connect() as c, c.transaction(force_rollback=True):
        c.execute("update privacy_configuration set enabled=false")
        c.execute("delete from privacy_matching_keys")
        assert (
            c.execute(
                "select public.privacy_email_denied('synthetic@example.invalid')"
            ).fetchone()[0]
            is False
        )
        c.execute("update privacy_configuration set enabled=true")
        with pytest.raises(psycopg.Error) as error, c.transaction():
            c.execute("select public.privacy_email_denied('synthetic@example.invalid')")
        assert error.value.sqlstate == "P0005"


def test_provisioning_does_not_hold_auth_commit_lock(complete):
    _, e, *_ = complete
    with e.connect() as c:
        c.execute(
            (
                ROOT
                / "supabase/migrations/20261101020000_privacy_provisioning_gate.sql"
            ).read_text(encoding="utf-8")
        )
        c.execute("alter role privacy_provisioning_executor login")
    email = "provisioned@example.invalid"

    def create(operation, address, password):
        with e.connect() as c:
            assert c.execute(
                "select pg_try_advisory_xact_lock(hashtextextended(%s,15715))",
                (address,),
            ).fetchone()[0]
        return {"id": operation}

    gate = ProvisioningGate(
        lambda: restricted(complete, "privacy_provisioning_executor"), create
    )
    operation = str(uuid4())
    assert gate.provision(operation, email, "synthetic-local-password") == {
        "id": operation
    }


def test_runtime_email_delete_is_account_and_category_bound(runtime, complete):
    u, e, *_ = runtime
    other, ordinary, billing = str(uuid4()), str(uuid4()), str(uuid4())
    with complete[1].connect() as c:
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, "other@example.invalid"),
        )
        for event, owner, kind in [
            (ordinary, other, "welcome"),
            (billing, u["account"], "billing_payment"),
        ]:
            c.execute(
                "insert into outbound_email_events(id,user_id,email_type,recipient_email,status,idempotency_key) values(%s,%s,%s,'synthetic@example.invalid','sent',%s)",
                (event, owner, kind, str(uuid4())),
            )
    accept(complete)
    assert e.queue_accepted()
    job = e.claim()
    with e.transaction() as c:
        c.scope(job)
        for event, owner in [(ordinary, other), (billing, u["account"])]:
            c.execute(
                "delete from outbound_email_events where id=%s and user_id=%s",
                (event, owner),
            )
            assert c.rowcount == 0
    with complete[1].connect() as c:
        assert (
            c.execute(
                "select count(*) from outbound_email_events where id=any(%s)",
                ([ordinary, billing],),
            ).fetchone()[0]
            == 2
        )


def test_export_lease_heartbeat_covers_storage_put(runtime, complete, monkeypatch):
    u, e, storage, *_ = runtime
    seed(complete)
    job_id = str(uuid4())
    e.request(u["account"], job_id)
    job = e.claim()
    assert job and str(job["id"]) == job_id
    renewed, upload = threading.Event(), threading.Event()
    original = e.renew

    def renew(job):
        original(job)
        if upload.is_set():
            renewed.set()

    put = storage.put

    def slow_put(*args):
        upload.set()
        assert renewed.wait(
            10
        ), "heartbeat did not run while Storage upload was pending"
        return put(*args)

    monkeypatch.setattr(e, "renew", renew)
    monkeypatch.setattr(e, "LEASE_RENEW_INTERVAL", 0.02)
    monkeypatch.setattr(storage, "put", slow_put)
    e.build(job)
    assert e.status(u["account"], job_id)["state"] == "ready"


def test_retirement_rejects_unclassified_inbound_dependency(complete):
    u, e, *_ = complete
    with e.connect() as c, c.transaction(force_rollback=True):
        for candidate in [
            "C15_LEGACY_REPLY_RETIREMENT_CANDIDATE.sql",
            "C15_USAGE_RETIREMENT_CANDIDATE.sql",
        ]:
            c.execute((ROOT / "docs/sql" / candidate).read_text(encoding="utf-8"))
        assert c.execute("select public.privacy_usage_schema_current()").fetchone()[0]
        c.execute(
            "create table c15_unclassified_child(id uuid references public.usage_operations(operation_id) on delete cascade)"
        )
        assert (
            c.execute("select public.privacy_usage_schema_current()").fetchone()[0]
            is False
        )


def test_replacement_challenge_renews_status_receipt(content):
    u, e, _, service, actor, document = content
    service.call(actor, "challenge", document)
    with e.connect() as c:
        c.execute(
            "update privacy_deletion_requests set expires_at=clock_timestamp()-interval '1 day',status_expires_at=clock_timestamp()-interval '1 day' where account_id=%s",
            (u["account"],),
        )
    with e.connect() as c:
        c.execute(
            "update privacy_reauth_intents set expires_at=clock_timestamp()-interval '1 day' where account_id=%s",
            (u["account"],),
        )
    replacement = {**document, "request_id": str(uuid4())}
    service.call(actor, "begin", replacement)
    with e.connect() as c:
        c.execute(
            "update privacy_reauth_intents set started_at=clock_timestamp()-interval '2 seconds' where account_id=%s",
            (u["account"],),
        )
    service.call(actor, "challenge", replacement)
    service.call(actor, "confirm", {**replacement, "confirmation_text": "delete"})
    assert (
        service.status(
            {
                "request_id": replacement["request_id"],
                "status_hash": replacement["status_hash"],
            }
        )["state"]
        == "accepted_restricted"
    )
    with e.connect() as c:
        assert c.execute(
            "select status_expires_at>clock_timestamp()+interval '6 days' from privacy_deletion_requests where account_id=%s",
            (u["account"],),
        ).fetchone()[0]


def test_sent_notice_history_cannot_starve_new_request(runtime, complete):
    import json

    u, e, *_ = complete
    accept(complete)
    with e.connect() as c:
        c.execute(
            (
                ROOT
                / "supabase/migrations/20261102030000_privacy_runtime_notifications.sql"
            ).read_text(encoding="utf-8")
        )
        for _ in range(17):
            account, request = str(uuid4()), str(uuid4())
            c.execute(
                "insert into auth.users(id,email) values(%s,%s)",
                (account, account + "@example.invalid"),
            )
            c.execute(
                "insert into privacy_deletion_requests select (jsonb_populate_record(null::privacy_deletion_requests,to_jsonb(r)||%s::jsonb)).* from privacy_deletion_requests r where r.account_id=%s",
                (
                    json.dumps(
                        {
                            "account_id": account,
                            "request_id": request,
                            "accepted_at": "2020-01-01T00:00:00Z",
                        }
                    ),
                    u["account"],
                ),
            )
            c.execute(
                "insert into privacy_minimized_records(account_id,source_kind,source_id,category,event_kind,outcome,confirmation_at,eligible_at) values(%s,'security_email',gen_random_uuid(),'security_audit','privacy_request_accepted','sent','2020-01-01T00:00:00Z'::timestamptz,'2020-01-01T00:00:00Z'::timestamptz+interval '180 days')",
                (account,),
            )
    with restricted(complete, "privacy_content_executor") as c:
        result = c.execute("select privacy_pending_notices()").fetchone()[0]
    assert {"account_id": u["account"], "stage": "accepted"} in result
    assert not any(row["account_id"] == account for row in result)


def test_unmanifested_resume_object_blocks_primary_completion(runtime, complete):
    u, e, *_ = runtime
    key = u["account"] + "/" + str(uuid4()) + "/orphan.pdf"
    with complete[1].connect() as c:
        c.execute(
            "insert into storage.objects(bucket_id,name) values('resumes',%s)", (key,)
        )
    accept(complete)
    assert e.queue_accepted()
    job = e.claim()
    with pytest.raises(ContentBlocked, match="resume_object_absence_not_verified"):
        e.cleanup(job)
    assert e.status(u["account"], job["id"])["state"] != "primary_verified"
    with pytest.raises(psycopg.Error) as error, complete[1].connect() as c:
        c.execute(
            "insert into storage.objects(bucket_id,name) values('resumes',%s)",
            (key + ".late",),
        )
    assert error.value.sqlstate == "42501"


def test_restore_runtime_can_fence_runs_and_preserve_replay_keys(runtime, complete):
    from app.privacy_runtime_db import RuntimeConnection

    u, e, *_ = complete
    _, row = start(complete)
    with e.connect() as c:
        c.execute("update privacy_restore_state set required=true,ready=false")
        c.execute(
            "insert into privacy_restored_subjects(account_id,request_id) values(%s,%s)",
            (u["account"], str(uuid4())),
        )
    with RuntimeConnection(
        restricted(complete, "privacy_restore_executor"), "privacy_restore_executor"
    ) as c:
        c.execute(
            "update subscription_auto_runs set active=false,fence=fence+1 where run_id=%s",
            (row["run_id"],),
        )
        c.execute(
            "insert into privacy_restored_replays values(%s,%s,decode(%s,'hex')) on conflict do nothing",
            (u["account"], 1, "ab" * 32),
        )
    with e.connect() as c:
        assert (
            c.execute(
                "select active from subscription_auto_runs where run_id=%s",
                (row["run_id"],),
            ).fetchone()[0]
            is False
        )
        assert (
            c.execute(
                "select count(*) from privacy_restored_replays where account_id=%s",
                (u["account"],),
            ).fetchone()[0]
            == 1
        )

        c.execute("update privacy_restore_state set required=false,ready=true")
