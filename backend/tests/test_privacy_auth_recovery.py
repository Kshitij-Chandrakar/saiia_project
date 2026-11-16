"""Stage 1B: native transactions, synthetic identities and fake Auth only."""
# ruff: noqa: F811 -- imported pytest fixtures are intentionally injected by name

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.commercial.catalog_store import RpcFailure
from app.privacy_revocation import RevocationWorker
from test_privacy_native import (  # noqa: F401 -- disposable fixture dependencies
    CatalogStoreError,
    CurrentUser,
    accept,
    case,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    literal,
    pricing,
    privacy,
    recent_presence,
    upgraded,
    usage,
)


@pytest.fixture(autouse=True)
def isolate_revocation_queue(privacy):
    # The native suite intentionally shares a cluster. Prior tests' accepted
    # accounts must not become this test's globally eligible fake-Auth work.
    u, _, _, d = privacy
    u["db"].run(
        f"update privacy_followup_tasks set state='blocked',lease_id=null,lease_until=null where kind='revoke_sessions' and request_id<>'{d['request_id']}'"
    )


def test_presence_must_follow_operation_and_replay_is_bound(privacy):
    u, s, a, d = privacy
    u["db"].run(
        f"update privacy_reauth_intents set started_at=clock_timestamp() where account_id='{u['account']}'"
    )
    with pytest.raises(CatalogStoreError):
        s.call(a, "challenge", d)
    u["db"].run(
        f"update privacy_reauth_intents set started_at=clock_timestamp()-interval '2 seconds' where account_id='{u['account']}'"
    )
    s.call(a, "challenge", d)
    with pytest.raises(CatalogStoreError):
        s.call(a, "challenge", {**d, "session_id": str(uuid4())})
    with pytest.raises(CatalogStoreError):
        s.call(a, "begin", {**d, "request_id": str(uuid4())})
    with pytest.raises(CatalogStoreError):
        s.call(
            a,
            "challenge",
            {
                **d,
                "reauthenticated_at": datetime.fromtimestamp(
                    time.time() - 10, timezone.utc
                ).isoformat(),
            },
        )


def test_totp_original_session_and_fresh_aal2(privacy):
    _, s, a, d = privacy
    signed = CurrentUser(
        user_id=a.subject_id,
        email=d["verified_email"],
        role="authenticated",
        claims={
            "session_id": d["session_id"],
            "c15_auth_method": "totp",
            "aal": "aal2",
            "amr": [{"method": "totp", "timestamp": int(time.time())}],
        },
    )
    assert recent_presence(signed)[0] == d["session_id"]
    with pytest.raises(CatalogStoreError):
        s.call(
            a, "challenge", {**d, "proof_method": "totp", "session_id": str(uuid4())}
        )
    s.call(a, "challenge", {**d, "proof_method": "totp"})


def test_revocation_success_keeps_cleanup_pending_and_identity(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    seen = []
    worker = RevocationWorker(
        u["connect"], lambda subject: seen.append(subject) or "succeeded"
    )
    assert worker.run_one() and not worker.run_one()
    assert seen == [u["account"]]
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert status["session_revocation"] == "succeeded" and not status["content_erased"]
    assert u["db"].rows(
        f"select count(*) n from auth.users where id='{u['account']}'"
    ) == [{"n": 1}]
    assert u["db"].rows(
        f"select state from privacy_followup_tasks where request_id='{d['request_id']}' and kind='personal_cleanup'"
    ) == [{"state": "pending"}]


def test_retry_timeout_restart_stale_lease_and_exhaustion(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    worker = RevocationWorker(u["connect"], lambda _: "transient")
    first = worker.call("claim", {"lease_id": str(uuid4())})
    assert not worker.call("claim", {"lease_id": str(uuid4())})
    u["db"].run(
        f"update privacy_followup_tasks set lease_until=clock_timestamp()-interval '1 second' where request_id='{d['request_id']}' and kind='revoke_sessions'"
    )
    second = worker.call("claim", {"lease_id": str(uuid4())})
    with pytest.raises(CatalogStoreError):
        worker.call("finish", {**first, "outcome": "succeeded"})
    assert worker.call("finish", {**second, "outcome": "timeout"}) == {
        "state": "pending"
    }
    for _ in range(3):
        u["db"].run(
            f"update privacy_followup_tasks set due_at=clock_timestamp()-interval '1 second' where request_id='{d['request_id']}' and kind='revoke_sessions'"
        )
        assert worker.run_one()
    assert not worker.run_one()
    assert u["db"].rows(
        f"select state,attempts from privacy_followup_tasks where request_id='{d['request_id']}' and kind='revoke_sessions'"
    ) == [{"state": "blocked", "attempts": 5}]


def test_native_concurrent_revocation_claim_and_safe_failure(privacy):
    u, s, a, d = privacy
    accept(s, a, d)

    def revoke(_):
        raise TimeoutError("synthetic provider text must not persist")

    worker = RevocationWorker(u["connect"], revoke)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: worker.run_one(), range(2))) == [False, True]
    assert u["db"].rows(
        f"select safe_error from privacy_followup_tasks where request_id='{d['request_id']}' and kind='revoke_sessions'"
    ) == [{"safe_error": "timeout"}]


def test_key_outage_rotation_and_stale_restored_identity(privacy):
    u, s, a, d = privacy
    s.call(a, "challenge", d)
    u["db"].run("update privacy_matching_keys set current_key=false")
    with pytest.raises(CatalogStoreError):
        s.call(a, "confirm", {**d, "confirmation_text": "delete"})
    u["db"].run("update privacy_matching_keys set current_key=true where version=1")
    accept(s, a, d)
    db = u["db"]
    db.run(
        "update privacy_matching_keys set current_key=false;insert into privacy_matching_keys values(2,decode(repeat('34',32),'hex'),true)"
    )
    email = d["verified_email"]
    assert db.rows(f"select privacy_email_denied('{email.upper()}') denied") == [
        {"denied": True}
    ]
    assert db.rows(
        "select privacy_email_denied('unaffected@example.invalid') denied"
    ) == [{"denied": False}]
    # Hook remains authoritative for a stale identity even without its old UUID.
    event = {
        "user_id": str(uuid4()),
        "claims": {"email": email},
        "authentication_method": "oauth",
    }
    assert (
        "error"
        in db.rows(f"select privacy_access_token_hook({literal(event)}::jsonb) result")[
            0
        ]["result"]
    )
    db.run("update privacy_matching_keys set current_key=false")
    assert db.rows(
        "select privacy_before_user_created('{\"user\":{\"email\":\"unaffected@example.invalid\"}}')->'error'->>'http_code' code"
    ) == [{"code": "503"}]
    with pytest.raises(RpcFailure):
        db.run("select privacy_email_denied('unaffected@example.invalid')")
    db.run("update privacy_matching_keys set current_key=true where version=1")


def test_remote_success_then_worker_crash_repeats_without_false_cleanup(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    remote = []
    worker = RevocationWorker(
        u["connect"], lambda subject: remote.append(subject) or "succeeded"
    )
    task = worker.call("claim", {"lease_id": str(uuid4())})
    assert worker.revoke(task["account_id"]) == "succeeded"
    # Crash after Auth success, before durable acknowledgement. Replay is safe,
    # but external exactly-once is deliberately not asserted.
    u["db"].run(
        f"update privacy_followup_tasks set lease_until=clock_timestamp()-interval '1 second' where request_id='{d['request_id']}' and kind='revoke_sessions'"
    )
    assert RevocationWorker(u["connect"], worker.revoke).run_one()
    assert len(remote) == 2
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert (
        status["session_revocation"] == "succeeded"
        and status["cleanup_state"] == "pending"
    )


def test_supported_hooks_allow_normal_auth_and_deny_after_suppression(privacy):
    u, s, a, d = privacy
    event = {
        "user_id": u["account"],
        "claims": {"email": d["verified_email"]},
        "authentication_method": "password",
    }
    hook = lambda: u["db"].rows(
        f"select privacy_access_token_hook({literal(event)}) result"
    )[0]["result"]
    assert hook()["claims"]["c15_auth_method"] == "password"
    assert u["db"].rows(
        f"select privacy_before_user_created({literal({'user': {'email': d['verified_email']}})}) result"
    ) == [{"result": {}}]
    accept(s, a, d)
    for method in ("password", "oauth", "token_refresh", "email_change"):
        event["authentication_method"] = method
        assert hook()["error"]["http_code"] == 403


def test_unavailable_revocation_credential_blocks_only_task(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    worker = RevocationWorker(u["connect"], lambda _: "credential_unavailable")
    assert worker.run_one() and not worker.run_one()
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert status["session_revocation"] == "blocked" and not status["content_erased"]


def test_supported_hook_and_confirmation_share_email_lock(privacy):
    import json

    import psycopg
    from test_draft_service_native import wait_blocked

    u, s, a, d = privacy
    s.call(a, "challenge", d)
    event = json.dumps({"user": {"email": d["verified_email"]}})
    writer = psycopg.connect(
        host="127.0.0.1",
        port=u["db"].port,
        user="catalog_test_owner",
        dbname="postgres",
    )
    try:
        assert (
            writer.execute(
                "select privacy_before_user_created(%s::jsonb)", (event,)
            ).fetchone()[0]
            == {}
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                s.call, a, "confirm", {**d, "confirmation_text": "delete"}
            )
            wait_blocked(u["db"], {"c131-worker"})
            writer.commit()
            assert future.result()["state"] == "accepted_restricted"
        assert (
            writer.execute(
                "select privacy_before_user_created(%s::jsonb)", (event,)
            ).fetchone()[0]["error"]["http_code"]
            == 403
        )
        # This proves ordering of hook checks, NOT a managed Auth INSERT commit
        # fence after the hook transaction ends. That is an activation blocker.
    finally:
        writer.rollback()
        writer.close()
