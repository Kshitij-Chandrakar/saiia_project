"""Native supported-hook candidate + encrypted capability + fake HTTP. No Auth engine.

The same fixture applies the generated package instead of the historical managed
Auth guards. It deliberately demonstrates the remaining identity-creation gap.
"""
# ruff: noqa: F811 -- imported pytest fixtures injected by name

import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.privacy_credentials import CredentialBox, CredentialUnavailable, GlobalLogout
from app.privacy_revocation import RevocationWorker, configured_worker
from test_privacy_native import (  # noqa: F401 -- native fixture dependencies
    CatalogStoreError,
    RpcFailure,
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
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True


@pytest.fixture(autouse=True)
def isolated_queue(privacy):
    u, _, _, d = privacy
    u["db"].run(
        f"update privacy_followup_tasks set state='blocked',lease_id=null,lease_until=null where kind='revoke_sessions' and request_id<>'{d['request_id']}'"
    )


def hook(db, name, event, caller="supabase_auth_admin"):
    # Only fixed test roles; never use caller input in production composition.
    assert caller in (
        "supabase_auth_admin",
        "usage_executor",
        "authenticated",
        "anon",
        "service_role",
    )
    raw = db.run(
        f"set session authorization {caller};select public.{name}({literal(event)})::text"
    )
    return json.loads(raw.strip().splitlines()[-1])


def event(d, method="password"):
    now = int(time.time())
    return {
        "user_id": d["account"],
        "authentication_method": method,
        "claims": {
            "sub": d["account"],
            "iss": "https://synthetic.invalid/auth/v1",
            "aud": "authenticated",
            "exp": now + 600,
            "iat": now,
            "role": "authenticated",
            "aal": "aal1",
            "session_id": d["session_id"],
            "email": d["verified_email"],
            "phone": "",
            "is_anonymous": False,
        },
    }


def test_supported_package_has_no_auth_table_ddl_and_remains_closed(privacy):
    u, _, _, _ = privacy
    assert u["db"].rows(
        "select count(*) n from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname='auth' and tgname like 'privacy_%'"
    ) == [{"n": 0}]
    sql = (
        Path(__file__).parents[2] / "docs/sql/C15_SUPPORTED_AUTH_PACKAGE_PENDING.sql"
    ).read_text()
    assert "privacy_auth_email_guard" not in sql and "privacy_identity_guard" not in sql
    assert "create role" not in sql.lower()
    assert "default false" in sql
    from app.config import settings

    assert settings.C15_REVOCATION_ENABLED == "false"
    assert configured_worker(u["connect"]) is None


def test_hook_contract_authority_normal_auth_and_all_issuance_methods(privacy):
    u, s, a, d = privacy
    d = {**d, "account": u["account"]}
    before = {"user": {"id": str(uuid4()), "email": d["verified_email"]}}
    assert hook(u["db"], "privacy_auth_before_create", before) == {}
    for caller in ("usage_executor", "authenticated", "anon", "service_role"):
        with pytest.raises(RpcFailure):
            hook(u["db"], "privacy_auth_before_create", before, caller)
    for bad in (
        [],
        {},
        {"user": {}},
        {"user": {"id": "bad", "email": "synthetic@example.invalid"}},
    ):
        with pytest.raises(RpcFailure):
            hook(u["db"], "privacy_auth_before_create", bad)
    with pytest.raises(RpcFailure):
        hook(u["db"], "privacy_auth_token", {"user_id": u["account"], "claims": {}})
    assert (
        hook(u["db"], "privacy_auth_token", event(d))["claims"]["c15_auth_method"]
        == "password"
    )
    accept(s, a, d)
    assert (
        hook(u["db"], "privacy_auth_before_create", before)["error"]["http_code"] == 403
    )
    for method in ("password", "oauth", "token_refresh", "email_change"):
        assert (
            hook(u["db"], "privacy_auth_token", event(d, method))["error"]["http_code"]
            == 403
        )


def test_hooks_outage_and_no_identity_commit_guarantee(privacy):
    u, s, a, d = privacy
    before = {"user": {"id": str(uuid4()), "email": d["verified_email"]}}
    assert hook(u["db"], "privacy_auth_before_create", before) == {}
    accept(s, a, d)
    # A hook already returned. Simulate a later Auth INSERT in another TX:
    # supported hooks alone do not prevent the identity row, but product writes
    # and token issuance must still deny it. This is NOT remote acceptance.
    restored = str(uuid4())
    u["db"].run(
        f"insert into auth.users(id,email) values('{restored}','{d['verified_email']}')"
    )
    with pytest.raises(RpcFailure):
        u["db"].run(f"insert into profiles(user_id) values('{restored}')")
    assert (
        hook(u["db"], "privacy_auth_token", event({**d, "account": restored}))["error"][
            "http_code"
        ]
        == 403
    )
    u["db"].run("update privacy_matching_keys set current_key=false")
    assert (
        hook(
            u["db"],
            "privacy_auth_before_create",
            {"user": {"id": str(uuid4()), "email": "normal@example.invalid"}},
        )["error"]["http_code"]
        == 503
    )
    u["db"].run("update privacy_matching_keys set current_key=true where version=1")


def test_atomic_encrypted_capture_restart_logout_and_clean_completion(privacy):
    u, s, a, d = privacy
    result = accept(s, a, d)
    rows = u["db"].rows(
        f"select key_version,ciphertext from privacy_revocation_credentials where request_id='{d['request_id']}'"
    )
    assert len(rows) == 1 and a._bearer not in json.dumps(rows)
    assert u["db"].rows(
        "select has_table_privilege('usage_executor','privacy_revocation_credentials','SELECT') allowed"
    ) == [{"allowed": False}]
    assert a._bearer not in json.dumps(
        u["db"].rows(
            f"select * from privacy_followup_tasks where request_id='{d['request_id']}'"
        )
    )
    calls = []

    def post(url, **kw):
        assert url == "https://synthetic.invalid/auth/v1/logout?scope=global"
        assert kw["timeout"] == (3, 10) and kw["allow_redirects"] is False
        assert kw["stream"] is True
        assert kw["headers"]["Authorization"] == "Bearer " + a._bearer
        calls.append(1)
        return SimpleNamespace(status_code=204)

    # New box/worker has no initiating browser state; only DB + server keys.
    worker = RevocationWorker(
        u["connect"],
        logout=GlobalLogout(
            CredentialBox.configured(),
            "https://synthetic.invalid",
            "synthetic-public-key",
            post,
        ),
    )
    assert worker.run_one() and calls == [1]
    assert not u["db"].rows(
        f"select 1 from privacy_revocation_credentials where request_id='{d['request_id']}'"
    )
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert (
        status["session_revocation"] == "succeeded"
        and status["content_erased"] is False
    )
    assert result["state"] == "accepted_restricted"


def test_crypto_aad_expiry_missing_key_and_cross_account(privacy):
    _, _, a, d = privacy
    box = CredentialBox.configured()
    sealed = box.seal(a._bearer, a.subject_id, d["request_id"], int(time.time()) + 600)
    assert box.open(sealed, a.subject_id, d["request_id"]) == a._bearer
    for subject, request in (
        (str(uuid4()), d["request_id"]),
        (a.subject_id, str(uuid4())),
    ):
        with pytest.raises(CredentialUnavailable):
            box.open(sealed, subject, request)
    with pytest.raises(CredentialUnavailable):
        CredentialBox({"other": b"9" * 32}, "other").open(
            sealed, a.subject_id, d["request_id"]
        )
    with pytest.raises(CredentialUnavailable):
        box.open(
            {**sealed, "expires_at": int(time.time()) - 1},
            a.subject_id,
            d["request_id"],
        )


def test_missing_key_prevents_acceptance_but_recovers_accepted_status(
    privacy, monkeypatch
):
    u, s, a, d = privacy
    s.call(a, "challenge", d)
    monkeypatch.delenv("C15_REVOCATION_KEYS")
    with pytest.raises(CatalogStoreError):
        s.call(a, "confirm", {**d, "confirmation_text": "delete"})
    assert not u["db"].rows(
        f"select 1 from subscription_deletion_jobs where account_id='{u['account']}'"
    )
    monkeypatch.setenv("C15_REVOCATION_KEYS", '{"test":"' + "EhIS" * 10 + 'EhI="}')
    accepted = s.call(a, "confirm", {**d, "confirmation_text": "delete"})
    monkeypatch.delenv("C15_REVOCATION_KEYS")
    assert s.call(a, "confirm", {**d, "confirmation_text": "delete"}) == accepted


@pytest.mark.parametrize("outcome", [401, 403, 302, 500, "timeout"])
def test_fake_http_failure_never_false_success(privacy, outcome):
    import requests

    u, s, a, d = privacy
    accept(s, a, d)

    def post(*_, **__):
        if outcome == "timeout":
            raise requests.Timeout("must never persist this text")
        return SimpleNamespace(status_code=outcome)

    worker = RevocationWorker(
        u["connect"],
        logout=GlobalLogout(
            CredentialBox.configured(), "https://synthetic.invalid", "synthetic", post
        ),
    )
    assert worker.run_one()
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert (
        status["session_revocation"] in ("pending", "blocked")
        and not status["content_erased"]
    )


def test_expiry_cleanup_and_cross_account_lease_denial(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    worker = RevocationWorker(u["connect"])
    task = worker.call("claim", {"lease_id": str(uuid4())})
    assert "ciphertext" not in task
    with pytest.raises(CatalogStoreError):
        worker.call("credential", {**task, "account_id": str(uuid4())})
    u["db"].run(
        f"update privacy_revocation_credentials set expires_at=clock_timestamp()-interval '1 second' where request_id='{d['request_id']}'"
    )
    worker.call("expire", {})
    assert worker.call("credential", task) == {}
    assert u["db"].rows(
        f"select state from privacy_followup_tasks where request_id='{d['request_id']}' and kind='personal_cleanup'"
    ) == [{"state": "pending"}]


def test_cross_uuid_bootstrap_commit_serializes_with_deletion(privacy):
    from concurrent.futures import ThreadPoolExecutor

    import psycopg
    from test_draft_service_native import wait_blocked

    u, s, a, d = privacy
    s.call(a, "challenge", d)
    restored = str(uuid4())
    u["db"].run(
        f"insert into auth.users(id,email) values('{restored}','{d['verified_email']}')"
    )
    writer = psycopg.connect(
        host="127.0.0.1",
        port=u["db"].port,
        user="catalog_test_owner",
        dbname="postgres",
    )
    try:
        writer.execute("insert into profiles(user_id) values(%s)", (restored,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                s.call, a, "confirm", {**d, "confirmation_text": "delete"}
            )
            wait_blocked(u["db"], {"c131-worker"})
            writer.commit()
            assert future.result()["state"] == "accepted_restricted"
        with pytest.raises(psycopg.Error):
            writer.execute(
                "update profiles set summary=%s where user_id=%s",
                ("late payload", restored),
            )
    finally:
        writer.rollback()
        writer.close()


def test_missing_worker_key_clears_credential_without_calling_auth(privacy):
    u, s, a, d = privacy
    accept(s, a, d)

    def forbidden(*_, **__):
        pytest.fail("cross-key credential must never reach HTTP")

    worker = RevocationWorker(
        u["connect"],
        logout=GlobalLogout(
            CredentialBox({"other": b"9" * 32}, "other"),
            "https://synthetic.invalid",
            "synthetic",
            forbidden,
        ),
    )
    assert worker.run_one()
    assert (
        s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})[
            "session_revocation"
        ]
        == "blocked"
    )
    assert not u["db"].rows(
        f"select 1 from privacy_revocation_credentials where request_id='{d['request_id']}'"
    )


def test_lost_ack_after_remote_logout_cannot_infer_success_from_unauthorized(privacy):
    u, s, a, d = privacy
    accept(s, a, d)
    replies = iter([204, 401])
    logout = GlobalLogout(
        CredentialBox.configured(),
        "https://synthetic.invalid",
        "synthetic",
        lambda *_, **__: SimpleNamespace(status_code=next(replies)),
    )
    first = RevocationWorker(u["connect"], logout=logout)
    task = first.call("claim", {"lease_id": str(uuid4())})
    assert logout(task, first.call("credential", task)) == "succeeded"
    # Simulate death before acknowledging, then a server that rejects the old
    # session credential. An auth failure is not a global-scope completion proof.
    u["db"].run(
        f"update privacy_followup_tasks set lease_until=clock_timestamp()-interval '1 second' where request_id='{d['request_id']}' and kind='revoke_sessions'"
    )
    with pytest.raises(CatalogStoreError):
        first.call("credential", task)
    assert RevocationWorker(u["connect"], logout=logout).run_one()
    status = s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})
    assert status["session_revocation"] == "blocked" and not status["content_erased"]


def test_opt_in_factory_uses_fake_http_with_persistent_database_only(
    privacy, monkeypatch
):
    import requests
    from app.cloud import supabase_config
    from app.config import settings

    u, s, a, d = privacy
    accept(s, a, d)
    calls = []

    def post(*_, **__):
        calls.append(1)
        return SimpleNamespace(status_code=204)

    session = SimpleNamespace(post=post, trust_env=True)
    config = SimpleNamespace(
        supabase_url="https://synthetic.invalid", anon_key="synthetic"
    )
    config.require_configured = lambda: config
    monkeypatch.setattr(requests, "Session", lambda: session)
    monkeypatch.setattr(supabase_config, "get_supabase_settings", lambda: config)
    monkeypatch.setattr(settings, "C15_REVOCATION_ENABLED", "true")
    worker = configured_worker(u["connect"])
    assert worker is not None and session.trust_env is False
    assert worker.run_one() and calls == [1]
    assert (
        s.status({"request_id": d["request_id"], "status_hash": d["status_hash"]})[
            "session_revocation"
        ]
        == "succeeded"
    )
