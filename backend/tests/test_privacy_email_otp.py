"""Disposable PostgreSQL + real ASGI/JWT boundary + isolated synthetic Auth issuer.

This rehearses the integration protocol, NOT the Supabase Auth engine.
"""
# ruff: noqa: F811 -- native pytest fixtures imported for injection

import secrets
import time
from uuid import uuid4

import pytest
from test_draft_service_native import actor
from test_privacy_native import (  # noqa: F401 -- fixture dependencies
    case,
    database,
    digest,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    privacy,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True


@pytest.fixture
def otp(privacy):
    u, _, _, d = privacy
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    issuer = FastAPI()

    @issuer.post("/token")
    def issue():
        identity = actor(
            u["account"],
            email=d["verified_email"],
            session_id=d["session_id"],
            c15_auth_method="oauth",
            amr=[{"method": "oauth", "timestamp": int(time.time()) - 600}],
            app_metadata={"providers": ["google"]},
        )
        return {"access_token": identity._bearer}

    mailbox = []

    def sender(email, code):
        assert email.endswith("@example.invalid")
        mailbox.append(code)

    u["client"].app.state.privacy_otp_sender = sender
    # A separate synthetic Auth application issues a signed identity. The real
    # backend verifier, deletion API and SQL enforce the rest of the rehearsal.
    with TestClient(issuer) as auth:
        token = auth.post("/token").json()["access_token"]
    document = {key: d[key] for key in ("request_id", "scope", "policy_version")}
    document.update(
        confirmation_token=secrets.token_urlsafe(32),
        status_token=secrets.token_urlsafe(32),
    )
    u["db"].run(f"delete from privacy_reauth_intents where account_id='{u['account']}'")
    headers = {"Authorization": "Bearer " + token}

    def call(action, **extra):
        return u["client"].post(
            "/api/privacy/deletion/" + action,
            headers=headers,
            json={**document, **extra},
        )

    assert call("begin").status_code == 200
    u["db"].run(
        f"update privacy_reauth_intents set started_at=clock_timestamp()-interval '2 seconds' where account_id='{u['account']}'"
    )
    return u, document, mailbox, call, headers


def test_isolated_auth_mailbox_proof_then_explicit_confirmation(otp):
    u, _d, mail, call, _ = otp
    assert call("confirm", confirmation_text="delete").status_code == 403
    assert call("otp_start").json()["state"] == "otp_sent"
    assert len(mail) == 1 and len(mail[0]) == 8
    assert not u["db"].rows(
        f"select 1 from subscription_deletion_jobs where account_id='{u['account']}'"
    )
    ready = call("otp_verify", code=mail[0])
    assert ready.status_code == 200 and ready.json()["state"] == "awaiting_confirmation"
    assert call("otp_verify", code=mail[0]).json()["state"] == "otp_rejected"
    assert call("otp_ready").json()["state"] == "awaiting_confirmation"
    assert u["db"].rows(
        f"select count(*) n from privacy_lifecycle_audit where request_id='{_d['request_id']}' and action='deletion.email_otp_verified'"
    ) == [{"n": 1}]
    assert not u["db"].rows(
        f"select 1 from subscription_deletion_jobs where account_id='{u['account']}'"
    )
    assert call("confirm", confirmation_text="DELETE").status_code == 422
    accepted = call("confirm", confirmation_text="delete")
    assert (
        accepted.status_code == 200
        and accepted.json()["state"] == "accepted_restricted"
    )
    assert not accepted.json()["content_erased"]
    assert call("confirm", confirmation_text="delete").json() == accepted.json()
    assert u["db"].rows(
        f"select code_hash is null and consumed_at is not null ok from privacy_email_otp where account_id='{u['account']}'"
    ) == [{"ok": True}]


def test_wrong_code_attempts_commit_and_sends_are_bounded(otp):
    u, _, mail, call, _ = otp
    assert call("otp_start").json()["state"] == "otp_sent"
    assert call("otp_start").json()["state"] == "otp_limited" and len(mail) == 1
    wrong = "00000000" if mail[0] != "00000000" else "11111111"
    for _ in range(5):
        assert call("otp_verify", code=wrong).json()["state"] == "otp_rejected"
    assert call("otp_verify", code=mail[0]).json()["state"] == "otp_rejected"
    assert u["db"].rows(
        f"select attempts from privacy_email_otp where account_id='{u['account']}'"
    ) == [{"attempts": 5}]
    for _ in range(2):
        u["db"].run(
            f"update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id='{u['account']}'"
        )
        assert call("otp_start").json()["state"] == "otp_sent"
    u["db"].run(
        f"update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id='{u['account']}'"
    )
    assert call("otp_start").json()["state"] == "otp_limited"


def test_expiry_resend_wrong_scope_session_and_no_code_leak(otp):
    u, d, mail, call, headers = otp
    sent = call("otp_start")
    assert mail[0] not in sent.text and "code_hash" not in sent.text
    assert (
        u["client"]
        .post(
            "/api/privacy/deletion/otp_verify",
            headers=headers,
            json={**d, "request_id": str(uuid4()), "code": mail[0]},
        )
        .status_code
        == 403
    )
    u["db"].run(
        f"update privacy_email_otp set expires_at=clock_timestamp()-interval '1 second' where account_id='{u['account']}'"
    )
    assert call("otp_verify", code=mail[0]).status_code == 403
    assert call("otp_ready").status_code == 403
    assert call("confirm", confirmation_text="delete").status_code == 403


def test_sender_unavailable_and_cross_account_are_closed(otp):
    u, d, _, call, _ = otp
    u["client"].app.state.privacy_otp_sender = None
    assert call("otp_start").status_code == 503
    assert not u["db"].rows(
        f"select 1 from privacy_email_otp where account_id='{u['account']}'"
    )
    other = actor(
        str(uuid4()),
        session_id=str(uuid4()),
        email="other@example.invalid",
        app_metadata={"providers": ["google"]},
    )
    assert (
        u["client"]
        .post(
            "/api/privacy/deletion/otp_ready",
            headers={"Authorization": "Bearer " + other._bearer},
            json=d,
        )
        .status_code
        == 403
    )


def test_concurrent_verify_and_resend_invalidates_old_code(otp):
    from concurrent.futures import ThreadPoolExecutor

    u, _, mail, call, _ = otp
    assert call("otp_start").json()["state"] == "otp_sent"
    old = mail[0]
    u["db"].run(
        f"update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id='{u['account']}'"
    )
    assert call("otp_start").json()["state"] == "otp_sent"
    if old != mail[-1]:
        assert call("otp_verify", code=old).json()["state"] == "otp_rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(
            pool.map(
                lambda _: call("otp_verify", code=mail[-1]).json()["state"], range(2)
            )
        )
    assert sorted(states) == ["awaiting_confirmation", "otp_rejected"]


def test_changed_session_daily_limit_and_expired_proof(otp):
    u, d, mail, call, _ = otp
    assert call("otp_start").json()["state"] == "otp_sent"
    wrong = actor(
        u["account"],
        email="unused@example.invalid",
        session_id=str(uuid4()),
        app_metadata={"providers": ["google"]},
    )
    assert (
        u["client"]
        .post(
            "/api/privacy/deletion/otp_verify",
            headers={"Authorization": "Bearer " + wrong._bearer},
            json={**d, "code": mail[0]},
        )
        .status_code
        == 403
    )
    u["db"].run(
        f"update privacy_email_otp_limits set day_count=10,hour_count=0 where account_id='{u['account']}';update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id='{u['account']}'"
    )
    assert call("otp_start").json()["state"] == "otp_limited"
    assert call("otp_verify", code=mail[0]).json()["state"] == "awaiting_confirmation"
    u["db"].run(
        f"update privacy_email_otp set expires_at=clock_timestamp()-interval '1 second' where account_id='{u['account']}'"
    )
    assert call("confirm", confirmation_text="delete").status_code == 403
