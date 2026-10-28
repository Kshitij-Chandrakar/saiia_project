"""Actual JWT/account API/native pool acceptance. Explicit synthetic policy only."""

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.subscription_database import SubscriptionDatabase
from app.commercial.subscription_service import (
    SubscriptionService,
    VerifiedPaymentService,
)
from test_catalog_store_native import ROOT
from test_draft_api_native import create, headers
from test_draft_service_native import wait_blocked
from test_pricing_native import definition, publish
from test_usage_store_native import (
    actor,
    case,  # noqa: F401 -- pytest fixture
    database,  # noqa: F401 -- pytest fixture
    f1_install,  # noqa: F401 -- pytest fixture
    f2_install,  # noqa: F401 -- pytest fixture
    install,  # noqa: F401 -- pytest fixture
    pricing,  # noqa: F401 -- pytest fixture
    reserve,
    step,
    upgraded,  # noqa: F401 -- pytest fixture
    usage,  # noqa: F401 -- pytest fixture
)  # noqa: F401


@pytest.fixture
def integration(usage):  # noqa: F811 -- imported pytest fixture
    u = usage
    db = u["db"]
    if not db.rows(
        "select 1 from pg_tables where tablename='subscription_configuration'"
    ):
        db.run(
            "alter table auth.users add column email_confirmed_at timestamptz default clock_timestamp()"
        )
        db.run(
            (
                ROOT
                / "supabase/migrations/20261024010000_subscription_account_integration.sql"
            ).read_text()
        )
        db.run(
            (
                ROOT / "supabase/migrations/20261024020000_subscription_auto_leases.sql"
            ).read_text()
        )
        # Existing resume/profile storage schema and activation functions.
        db.run(
            "create schema if not exists extensions;create schema storage;create table storage.objects(bucket_id text,name text);create function storage.foldername(text) returns text[] language sql as $$select string_to_array($1,'/')$$;create policy saiia_storage_select_own on storage.objects for select using(true)"
        )
        for name in (
            "20260731121714_create_base_cloud_schema.sql",
            "20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql",
            "20260804134140_add_cloud_resume_chunk_activation.sql",
            "20260804151715_fix_cloud_resume_activation_profile_parsing.sql",
            "20260804162315_preserve_profile_fields_on_cloud_resume_activation.sql",
        ):
            db.run((ROOT / "supabase/migrations" / name).read_text())
        db.run(
            (
                ROOT
                / "supabase/migrations/20260828120000_add_interview_session_lifecycle.sql"
            ).read_text()
        )
        db.run(
            (
                ROOT
                / "supabase/migrations/20260915120000_add_interview_session_my_answers.sql"
            ).read_text()
        )
        db.run(
            (
                ROOT
                / "supabase/migrations/20261024030000_subscription_clipboard_settlement.sql"
            ).read_text()
        )
        for name in (
            "20260829103000_add_interview_session_transcript_storage.sql",
            "20261011120000_add_permanent_transcript_deletion.sql",
            "20261018150000_add_session_generation_turns.sql",
            "20261021120000_add_answer_sources.sql",
            "20261021130000_add_answer_diagrams.sql",
            "20261024040000_subscription_sketch_execution.sql",
            "20261024050000_subscription_manual_execution.sql",
            "20261024060000_subscription_scheduled_changes.sql",
            "20261024070000_subscription_auto_transport.sql",
            "20261024080000_subscription_screen_results.sql",
            "20261024090000_subscription_resume_settlement.sql",
            "20260829223000_add_interview_session_ai_notes.sql",
            "20260901103000_add_interview_session_ask_ai_messages.sql",
            "20260901123000_add_ask_ai_request_idempotency_keys.sql",
            "20260901170000_add_ask_ai_request_key_updated_at_trigger.sql",
            "20260902120000_add_ask_ai_atomic_turn_persistence.sql",
            "20261024100000_subscription_auxiliary_execution.sql",
            "20261024110000_subscription_relay_privacy.sql",
            "20261025010000_subscription_relay_connections.sql",
        ):
            db.run((ROOT / "supabase/migrations" / name).read_text())
    db.run("delete from subscription_configuration")
    offer = u["document"]["offer_version_id"]
    db.run(
        f"insert into subscription_configuration select true,offer_version_id,fingerprint,clock_timestamp()-interval '1 day','subscriptions.approved.2026-10-24' from catalog_offer_versions where offer_version_id='{offer}'"
    )
    u["subscription"] = SubscriptionService(u["connect"])
    # Exercise the actual reviewed pool for HTTP/browser composition too.
    runtime = SubscriptionDatabase(
        "true",
        f"host=127.0.0.1 port={db.port} dbname=postgres user=usage_executor sslmode=disable",
    )
    runtime.start()
    assert runtime._pool is not None
    previous = u["client"].app.state.subscriptions
    u["client"].app.state.subscriptions = runtime
    try:
        yield u
    finally:
        u["client"].app.state.subscriptions = previous
        runtime.close()


def test_current_api_bootstrap_and_cross_account_denial(integration):
    u = integration
    account = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{account}')")
    r = u["client"].get("/api/account/subscription", headers=headers(account))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert (
        r.json()["plan"]["name"] == "Free" and r.json()["plan"]["valid_until"] is None
    )
    before = u["db"].rows("select count(*) as n from subscription_binding_history")[0]
    assert (
        u["client"]
        .get("/api/account/subscription", headers=headers(account))
        .json()["plan"]
        == r.json()["plan"]
    )
    assert (
        u["db"].rows("select count(*) as n from subscription_binding_history")[0]
        == before
    )
    assert u["client"].get("/api/account/subscription").status_code == 401
    ordinary = str(uuid4())
    u["db"].run(
        f"insert into auth.users(id,email_confirmed_at) values ('{ordinary}',null)"
    )
    assert (
        u["client"]
        .get("/api/account/subscription", headers=headers(ordinary))
        .status_code
        == 403
    )
    assert (
        "PRIVATE" not in r.text
        and "policy_version" not in r.text
        and "source_ref" not in r.text
    )


def test_no_backfill_missing_config_and_restricted_pool(integration):
    u = integration
    account = str(uuid4())
    u["db"].run(
        f"insert into auth.users(id,email_confirmed_at) values ('{account}',clock_timestamp()-interval '2 days')"
    )
    assert (
        u["client"]
        .get("/api/account/subscription", headers=headers(account))
        .status_code
        == 503
    )
    u["db"].run("delete from subscription_configuration")
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    assert (
        u["client"].get("/api/account/subscription", headers=headers(other)).status_code
        == 503
    )
    runtime = SubscriptionDatabase(
        "true",
        f"host=127.0.0.1 port={u['db'].port} dbname=postgres user=usage_executor sslmode=disable",
    )
    try:
        runtime.start()
        assert runtime._pool is not None
        assert runtime.service().current(u["actor"])["plan"]["name"] == "Free"
    finally:
        runtime.close()


def test_verified_payment_preserved_bootstrap_and_expiry(integration):
    u = integration
    raw = definition("plus")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=raw["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )

    def verifier(evidence):
        if evidence == "synthetic.equivalent":
            return {
                **event,
                "account_id": event["account_id"].upper(),
                "paid_until": datetime.fromisoformat(event["paid_until"])
                .astimezone(timezone(timedelta(hours=5, minutes=30)))
                .isoformat(),
            }
        if evidence != "synthetic.verified":
            raise ValueError()
        return event

    payments = VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=verifier
    )
    with pytest.raises(CatalogStoreError):
        payments.apply("forged")
    assigned = payments.apply("synthetic.verified")
    assert payments.apply("synthetic.verified") == assigned
    assert payments.apply("synthetic.equivalent") == assigned
    assert (
        u["subscription"].current(u["actor"], bootstrap=True)["plan"]["name"] == "Plus"
    )
    u["db"].run(
        f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 second',revision=revision+1 where account_id='{u['account']}'"
    )
    assert u["subscription"].current(u["actor"])["plan"]["name"] == "Free"
    assert (
        u["db"].rows(
            f"select count(*) as n from subscription_binding_history where account_id='{u['account']}'"
        )[0]["n"]
        >= 3
    )


def test_auto_duplicate_stop_fencing_and_account_isolation(integration):
    u = integration
    s = u["subscription"]
    doc = dict(run_id=str(uuid4()), request_id=str(uuid4()))
    r = s.auto(u["actor"], "start", doc)
    assert r["active"] and r["heartbeat_seconds"] == 5
    assert s.auto(u["actor"], "start", doc) == r
    with pytest.raises(CatalogStoreError) as error:
        s.auto(u["actor"], "start", dict(run_id=str(uuid4()), request_id=str(uuid4())))
    assert error.value.code == ErrorCode.CONFLICT
    update = dict(
        run_id=r["run_id"], owner_token=r["owner_token"], fence=r["fence"], sequence=1
    )
    stopped = s.auto(u["actor"], "stop", update)
    assert not stopped["active"] and s.auto(u["actor"], "stop", update) == stopped
    state = s.auto(u["actor"], "status", {"run_id": r["run_id"]})
    assert not state["active"] and "owner_token" not in state
    rows = u["db"].rows(
        f"select charged,requested,state from usage_operations where resource_id='{r['run_id']}'"
    )
    assert (
        len(rows) == 1
        and rows[0]["state"] == "settled"
        and 0 <= rows[0]["charged"] <= rows[0]["requested"]
    )
    with pytest.raises(CatalogStoreError):
        s.auto(u["actor"], "renew", {**update, "sequence": 2})
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    s.current(actor(other), bootstrap=True)
    with pytest.raises(CatalogStoreError):
        s.auto(actor(other), "stop", update)


def test_auto_expiry_and_recovery_never_charge_beyond_authorization(integration):
    u = integration
    s = u["subscription"]
    r = s.auto(u["actor"], "start", dict(run_id=str(uuid4()), request_id=str(uuid4())))
    # Owner-only deterministic clock fault, no wall-clock sleeps.
    u["db"].run(
        f"update usage_operations set authorized_at=clock_timestamp()-interval '2 seconds',lease_until=clock_timestamp()-interval '1 second' where resource_id='{r['run_id']}'"
    )
    conn = u["connect"]("usage_reconciler")
    try:
        assert conn.execute(
            "select public.subscription_auto_reap(%s)", (u["account"],)
        ).fetchone()[0]
        conn.commit()
        assert not conn.execute(
            "select public.subscription_auto_reap(%s)", (u["account"],)
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    row = u["db"].rows(
        f"select charged,extract(epoch from(lease_until-authorized_at))*1000000 as duration from usage_operations where resource_id='{r['run_id']}'"
    )[0]
    assert row["charged"] == int(row["duration"])
    newer = s.auto(
        u["actor"], "start", dict(run_id=str(uuid4()), request_id=str(uuid4()))
    )
    assert newer["run_id"] != r["run_id"]


def test_upgrade_keeps_consumed_monthly_allowance(integration):
    u = integration
    o = reserve(u, units=3)
    step(u, o, "dispatch")
    step(u, o, "checkpoint", result_ref=str(uuid4()))
    step(u, o, "settle", charged=3, policy_version="synthetic.usage.v1")
    raw = definition("plus")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=raw["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )
    VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
    ).apply("synthetic")
    current = u["subscription"].current(u["actor"])
    clipboard = next(x for x in current["usage"] if x["meter"] == "clipboard.new_saves")
    assert clipboard["allowance"] == "10" and clipboard["used"] == "3"
    assert reserve(u, units=7)["requested"] == 7
    with pytest.raises(CatalogStoreError) as error:
        reserve(u, units=1)
    assert error.value.code == ErrorCode.EXHAUSTED


def test_actual_clipboard_store_atomic_replay_exhaustion_and_ownership(integration):
    u = integration
    s = u["subscription"]
    session = str(uuid4())
    key = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    result = s.save_clipboard(u["actor"], session, key, "My own answer")
    assert result["body"] == "My own answer"
    assert s.save_clipboard(u["actor"], session, key, "My own answer") == result
    with pytest.raises(CatalogStoreError) as error:
        s.save_clipboard(u["actor"], session, key, "Different answer")
    assert error.value.code == ErrorCode.IDENTITY_CONFLICT
    for n in range(4):
        s.save_clipboard(u["actor"], session, str(uuid4()), f"Personal answer {n}")
    with pytest.raises(CatalogStoreError) as error:
        s.save_clipboard(u["actor"], session, str(uuid4()), "Sixth answer")
    assert error.value.code == ErrorCode.EXHAUSTED
    balance = next(
        x for x in s.current(u["actor"])["usage"] if x["meter"] == "clipboard.new_saves"
    )
    assert balance["used"] == "5" and balance["reserved"] == "0"
    assert (
        u["db"].rows(
            f"select count(*) n from interview_session_my_answers where user_id='{u['account']}'"
        )[0]["n"]
        == 5
    )
    assert not u["db"].rows(
        f"select 1 from usage_operations where account_id='{u['account']}' and state<>'settled'"
    )
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    s.current(actor(other), bootstrap=True)
    with pytest.raises(CatalogStoreError) as error:
        s.save_clipboard(actor(other), session, key, "My own answer")
    assert error.value.code == ErrorCode.NOT_FOUND


def test_clipboard_insert_failure_rolls_back_usage_and_retry(integration):
    u = integration
    s = u["subscription"]
    session = str(uuid4())
    key = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}');create function synthetic_clipboard_fail() returns trigger language plpgsql as $$begin raise exception 'synthetic rollback';end$$;create trigger synthetic_failure before insert on interview_session_my_answers for each row execute function synthetic_clipboard_fail();"
    )
    try:
        with pytest.raises(CatalogStoreError):
            s.save_clipboard(u["actor"], session, key, "Retry after rollback")
        assert not u["db"].rows(
            f"select 1 from usage_operations where account_id='{u['account']}'"
        )
    finally:
        u["db"].run(
            "drop trigger synthetic_failure on interview_session_my_answers;drop function synthetic_clipboard_fail()"
        )
    saved = s.save_clipboard(u["actor"], session, key, "Retry after rollback")
    assert s.save_clipboard(u["actor"], session, key, "Retry after rollback") == saved


def test_independent_workers_auto_start_and_last_clipboard_unit(integration):
    u = integration
    s = u["subscription"]
    gate = threading.Barrier(2)

    def start(_):
        gate.wait(timeout=5)
        try:
            return s.auto(
                u["actor"], "start", dict(run_id=str(uuid4()), request_id=str(uuid4()))
            )
        except CatalogStoreError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(start, range(2)))
    assert (
        sum(isinstance(x, dict) for x in results) == 1 and ErrorCode.CONFLICT in results
    )
    session = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    for n in range(4):
        s.save_clipboard(u["actor"], session, str(uuid4()), f"Existing {n}")
    gate = threading.Barrier(2)

    def save(n):
        gate.wait(timeout=5)
        try:
            return s.save_clipboard(u["actor"], session, str(uuid4()), f"Final {n}")
        except CatalogStoreError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, range(2)))
    assert (
        sum(isinstance(x, dict) for x in results) == 1
        and ErrorCode.EXHAUSTED in results
    )


def test_account_api_aliases_and_corrupt_authority_fail_closed(integration):
    u = integration
    c = u["client"]
    for method, path in [
        ("GET", "/api/account/subscription/"),
        ("POST", "/api/account/subscription"),
        ("GET", "/api/account/%73ubscription"),
    ]:
        r = c.request(
            method, path, headers=headers(u["account"]), follow_redirects=False
        )
        assert r.status_code == 404 and r.headers["cache-control"] == "no-store"
    # An existing binding cannot be revived merely because it has expired.
    u["db"].run(
        f"update account_plan_bindings set active=false,revision=revision+1 where account_id='{u['account']}'"
    )
    assert (
        c.get("/api/account/subscription", headers=headers(u["account"])).status_code
        == 403
    )


def test_clipboard_actual_http_jwt_mutation_and_retained_reads(
    integration, monkeypatch
):
    from app.api import interview_sessions as api
    from app.config import settings

    u = integration
    c = u["client"]
    session = str(uuid4())
    key = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)

    def forbidden_cloud_call():
        raise AssertionError(
            "Direct SQL Clipboard must not construct PostgREST clients"
        )

    monkeypatch.setattr(
        api, "get_cloud_interview_session_service", forbidden_cloud_call
    )
    monkeypatch.setattr(
        api, "get_cloud_interview_my_answers_service", forbidden_cloud_call
    )
    url = f"/api/interview-sessions/{session}/my-answers"
    h = {**headers(u["account"]), "Idempotency-Key": key}
    assert c.post(url, json={"body": "Owned personal answer"}).status_code == 401
    duplicate = [
        ("Authorization", h["Authorization"]),
        ("Idempotency-Key", key),
        ("Idempotency-Key", str(uuid4())),
    ]
    assert (
        c.post(url, headers=duplicate, json={"body": "Ambiguous key"}).status_code
        == 422
    )
    result = c.post(url, headers=h, json={"body": "Owned personal answer"})
    assert result.status_code == 201, result.text
    assert result.headers["cache-control"] == "no-store"
    assert (
        c.post(url, headers=h, json={"body": "Owned personal answer"}).json()
        == result.json()
    )
    assert (
        c.post(
            url, headers=h, json={"body": "Forged", "actor": u["account"]}
        ).status_code
        == 422
    )
    assert c.post(url, headers=h, json={"body": "Conflicting"}).status_code == 409
    u["db"].run(
        f"update interview_sessions set status='ended',ended_at=clock_timestamp() where id='{session}';update account_plan_bindings set active=false,revision=revision+1 where account_id='{u['account']}'"
    )
    read = c.get(url, headers=h)
    assert (
        read.status_code == 200 and read.json()["items"][0]["id"] == result.json()["id"]
    )
    assert (
        c.post(
            url,
            headers={**h, "Idempotency-Key": str(uuid4())},
            json={"body": "Not authorized"},
        ).status_code
        == 403
    )
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    assert c.get(url, headers=headers(other)).status_code == 404


def test_verified_profile_bootstrap_installs_free_in_hosted_opt_in(
    integration, monkeypatch
):
    from app.api import auth as api
    from app.cloud.profile_bootstrap import ProfileBootstrapResult
    from app.config import settings

    u = integration
    account = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{account}')")
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    monkeypatch.setattr(
        api,
        "bootstrap_authenticated_profile",
        lambda user_id: ProfileBootstrapResult(
            user_id, True, False, True, False, "ready"
        ),
    )
    monkeypatch.setattr(api, "_trigger_welcome_email", lambda *_: None)
    response = u["client"].post("/api/auth/profile/bootstrap", headers=headers(account))
    assert response.status_code == 200, response.text
    rows = u["db"].rows(
        f"select valid_until,revision from account_plan_bindings where account_id='{account}'"
    )
    assert rows == [{"valid_until": None, "revision": 1}]
    assert response.headers["cache-control"] == "no-store"


def test_account_browser_real_jwt_native_database(integration, monkeypatch):
    u = integration
    manual, provider_calls = manual_case(u, monkeypatch)
    physical = os.environ.get("C132_PHYSICAL_ACCEPTANCE") == "true"
    # Browser projection expects an untouched allowance. Physical Electron work
    # must use its own verified synthetic account so parallel tests cannot debit it.
    electron_account = str(uuid4())
    electron_manual = {**manual, "session_id": str(uuid4())}
    u["db"].run(f"insert into auth.users(id) values ('{electron_account}')")
    bootstrap = u["client"].get(
        "/api/account/subscription", headers=headers(electron_account)
    )
    assert (
        bootstrap.status_code == 200 and bootstrap.json()["plan"]["valid_until"] is None
    )
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{electron_manual['session_id']}','{electron_account}')"
    )

    def browser_headers(subject=None):
        # A bounded synthetic manual session outlives the usual 10-minute test
        # token. Keep actual JWT exp aligned with desktop session metadata.
        return headers(
            subject or u["account"],
            **(
                {"exp": int(datetime.now(timezone.utc).timestamp()) + 3600}
                if physical
                else {}
            ),
        )

    from app.api import auth as auth_api
    from app.cloud.profile_bootstrap import ProfileBootstrapResult

    monkeypatch.setattr(
        auth_api,
        "bootstrap_authenticated_profile",
        lambda user_id: ProfileBootstrapResult(
            user_id, True, False, True, False, "ready"
        ),
    )
    monkeypatch.setattr(auth_api, "_trigger_welcome_email", lambda *_: None)

    from types import SimpleNamespace

    from app.api import transcribe

    monkeypatch.setattr(
        transcribe.stt_provider,
        "transcribe_upload",
        lambda **_: SimpleNamespace(
            text="Synthetic desktop transcription",
            transcription_provider="synthetic",
            transcription_model="synthetic",
            transcription_ms=0,
            fallback_used=False,
            fallback_reason=None,
            no_speech=False,
            reason=None,
        ),
    )

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            response = u["client"].get(
                self.path,
                headers={"Authorization": self.headers.get("Authorization", "")},
            )
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response.content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response.content)

        def do_POST(self):
            if self.path in (
                "/auth/v1/token?grant_type=refresh_token",
                "/auth/v1/logout",
            ):
                body = json.dumps(
                    dict(
                        access_token=browser_headers(electron_account)["Authorization"][
                            7:
                        ],
                        refresh_token="synthetic-only",
                        expires_at=int(datetime.now(timezone.utc).timestamp()) + 3600,
                    )
                    if "token?" in self.path
                    else {}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/auth/profile/bootstrap":
                size = int(self.headers.get("Content-Length", "0"))
                if size:
                    self.rfile.read(size)
                response = u["client"].post(
                    self.path,
                    headers={"Authorization": self.headers.get("Authorization", "")},
                )
                self.send_response(response.status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)
                return
            if self.path == "/transcribe/":
                size = int(self.headers.get("Content-Length", "0"))
                assert 0 < size < 16384
                response = u["client"].post(
                    self.path,
                    headers={
                        "Authorization": self.headers.get("Authorization", ""),
                        "Content-Type": self.headers["Content-Type"],
                    },
                    content=self.rfile.read(size),
                )
                self.send_response(response.status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)
                return
            assert self.path == "/generate/"
            size = int(self.headers.get("Content-Length", "0"))
            assert 0 < size < 16384
            response = u["client"].post(
                self.path,
                headers={"Authorization": self.headers.get("Authorization", "")},
                json=json.loads(self.rfile.read(size)),
            )
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response.content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response.content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from contextlib import ExitStack

    resources = ExitStack()
    grpc_port = None
    hosted = None
    try:
        if os.environ.get("C132_HOSTED_ACCEPTANCE") == "true":
            from subscription_acceptance_devices import hosted_workers

            hosted = resources.enter_context(hosted_workers(u, answers=not physical))
        if physical and not hosted:
            from subscription_acceptance_devices import physical_workers

            grpc_port = resources.enter_context(physical_workers(u, monkeypatch))
        result = subprocess.run(
            [
                "cmd",
                "/c",
                "npx",
                "playwright",
                "test",
                "--config",
                "playwright.catalog.config.js",
                "subscription-account.integration.spec.js",
                "subscription-electron.integration.spec.js",
            ],
            cwd=ROOT / "frontend",
            env={
                **os.environ,
                "CATALOG_BROWSER_NATIVE": json.dumps(
                    dict(
                        url=f"http://127.0.0.1:{server.server_port}",
                        token=browser_headers()["Authorization"][7:],
                        manual=manual,
                        grpcPort=grpc_port,
                        hosted=hosted,
                        electron=dict(
                            token=browser_headers(electron_account)["Authorization"][
                                7:
                            ],
                            manual=electron_manual,
                        ),
                    )
                ),
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=3700 if physical else 180,
        )
        print(result.stdout[-3000:])
        assert result.returncode == 0, result.stderr[-1500:]
        assert len(provider_calls) == 1
        if hosted and not physical:
            assert u["db"].rows(
                f"select count(*) n from interview_session_transcript_entries where session_id='{electron_manual['session_id']}'"
            ) == [{"n": 5}]
            assert u["db"].rows(
                f"select coalesce(sum(reserved),0) n from usage_periods where account_id='{electron_account}'"
            ) == [{"n": 0}]
        assert (
            u["db"].rows(
                f"select count(*) n from interview_session_transcript_entries where session_id='{manual['session_id']}'"
            )[0]["n"]
            == 1
        )
    finally:
        resources.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_clipboard_commit_ack_loss_recovers_the_same_saved_answer(integration):
    u = integration
    session = str(uuid4())
    key = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )

    class LostAcknowledgement:
        def __init__(self):
            self.connection = u["connect"]()

        def cursor(self):
            return self.connection.cursor()

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            self.connection.commit()
            raise ConnectionError("synthetic lost acknowledgement")

        def rollback(self):
            self.connection.rollback()

        def close(self):
            self.connection.close()

    uncertain = SubscriptionService(LostAcknowledgement)
    with pytest.raises(CatalogStoreError) as error:
        uncertain.save_clipboard(u["actor"], session, key, "Durable personal answer")
    assert error.value.code == ErrorCode.UNCERTAIN
    replay = u["subscription"].save_clipboard(
        u["actor"], session, key, "Durable personal answer"
    )
    assert replay["body"] == "Durable personal answer"
    assert (
        u["db"].rows(
            f"select count(*) n from interview_session_my_answers where session_id='{session}'"
        )[0]["n"]
        == 1
    )
    balance = next(
        x
        for x in u["subscription"].current(u["actor"])["usage"]
        if x["meter"] == "clipboard.new_saves"
    )
    assert balance["used"] == "1" and balance["reserved"] == "0"


def test_missing_grant_pool_fails_closed_with_safe_diagnostics(integration, caplog):
    u = integration
    u["db"].run(
        "revoke execute on function public.subscription_current(uuid,boolean) from usage_executor"
    )
    runtime = SubscriptionDatabase(
        "true",
        f"host=127.0.0.1 port={u['db'].port} dbname=postgres user=usage_executor sslmode=disable",
    )
    try:
        runtime.start()
        with pytest.raises(CatalogStoreError) as error:
            runtime.service()
        assert error.value.code == ErrorCode.UNAVAILABLE
        assert (
            "host=127.0.0.1" not in caplog.text
            and "SELECT" not in caplog.text
            and "permission denied for function" not in caplog.text
        )
    finally:
        runtime.close()
        u["db"].run(
            "grant execute on function public.subscription_current(uuid,boolean) to usage_executor"
        )


def test_current_auth_lock_does_not_deadlock_existing_reconciliation(integration):
    u = integration
    s = u["subscription"]
    r = s.auto(u["actor"], "start", dict(run_id=str(uuid4()), request_id=str(uuid4())))
    u["db"].run(
        f"update usage_operations set authorized_at=clock_timestamp()-interval '2 seconds',lease_until=clock_timestamp()-interval '1 second' where resource_id='{r['run_id']}'"
    )
    blocker = u["db"].barrier(
        f"select 1 from account_plan_bindings where account_id='{u['account']}' for update;"
    )
    reader = SubscriptionService(
        lambda: u["connect"]("usage_executor", "c132-current-fk-wait")
    )
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(reader.current, u["actor"])
        try:
            wait_blocked(u["db"], ["c132-current-fk-wait"])
        finally:
            # Fixture acquired only the ordering lock as owner. The actual
            # reconciliation runs under the restricted existing principal.
            blocker.stdin.write(
                f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp(),revision=revision+1 where account_id='{u['account']}';set session authorization usage_reconciler;select public.subscription_auto_reap('{u['account']}');commit;\n"
            )
            blocker.stdin.close()
            assert blocker.wait(timeout=10) == 0
        plan = pending.result(timeout=15)["plan"]
        assert plan["name"] == "Free" and plan["valid_until"] is None
    assert u["db"].rows(
        f"select state from usage_operations where resource_id='{r['run_id']}'"
    ) == [{"state": "settled"}]


def test_paid_expiry_preserves_over_cap_data_and_cross_scope_audit(integration):
    u = integration
    s = u["subscription"]
    raw = definition("pro")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=raw["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )
    VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
    ).apply("synthetic")
    session = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    for n in range(7):
        s.save_clipboard(u["actor"], session, str(uuid4()), f"Preserved answer {n}")
    u["db"].run(
        f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 second',revision=revision+1 where account_id='{u['account']}'"
    )
    current = s.current(u["actor"])
    balance = next(x for x in current["usage"] if x["meter"] == "clipboard.new_saves")
    assert (
        current["plan"]["name"] == "Free"
        and balance["allowance"] == "5"
        and balance["used"] == "7"
    )
    assert len(s.read_clipboard(u["actor"], session)) == 7
    with pytest.raises(CatalogStoreError) as error:
        s.save_clipboard(u["actor"], session, str(uuid4()), "Over capacity")
    assert error.value.code == ErrorCode.EXHAUSTED
    period = u["db"].rows(
        f"select period_id from usage_periods where account_id='{u['account']}' and meter='clipboard.new_saves' and allowance=5"
    )[0]["period_id"]
    assert u["reconciler"].audit(u["account"], period)["used"] == 7


def test_pooled_context_reset_exhaustion_and_pro_unlimited(integration):
    u = integration
    runtime = SubscriptionDatabase(
        "true",
        f"host=127.0.0.1 port={u['db'].port} dbname=postgres user=usage_executor sslmode=disable",
    )
    try:
        runtime.start()
        connection = runtime.connect()
        connection.execute(
            "select set_config('request.jwt.claim.sub','synthetic-prior-account',true)"
        )
        connection.commit()
        connection.close()
        other = runtime.connect()
        assert other.execute(
            "select current_setting('request.jwt.claim.sub',true)"
        ).fetchone()[0] in ("", None)
        other.commit()
        other.close()
        held = [runtime.connect() for _ in range(4)]
        try:
            with pytest.raises(CatalogStoreError) as error:
                runtime.connect()
            assert error.value.code == ErrorCode.UNAVAILABLE
        finally:
            for connection in held:
                connection.close()
    finally:
        runtime.close()
    raw = definition("pro")
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=raw["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=366)).isoformat(),
    )
    VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
    ).apply("synthetic")
    result = u["subscription"].current(u["actor"])
    assert result["plan"]["name"] == "Pro"
    auto = next(x for x in result["usage"] if x["meter"] == "auto.authorized_running")
    assert auto["mode"] == "unlimited" and auto["allowance"] is None


def sketch_case(u, *, paid=True):
    from test_catalog_store_native import literal

    if paid:
        raw = definition("plus")
        assert create(u["client"], raw).status_code == 200
        offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
        event = dict(
            account_id=u["account"],
            event_id=str(uuid4()),
            offer_version_id=offer,
            price_id=raw["terms"]["prices"][0]["price_id"],
            paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        )
        VerifiedPaymentService(
            lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
        ).apply("synthetic")
    existing = u["db"].rows(
        f"select id from interview_sessions where user_id='{u['account']}' and status='active'"
    )
    session, transcript = (existing[0]["id"] if existing else str(uuid4())), str(
        uuid4()
    )
    question, answer = "Design a queue", "API sends tasks to Queue."
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}') on conflict(id) do nothing;"
        f"insert into interview_session_transcript_entries(id,user_id,session_id,request_id,turn_index,source,question_text,answer_text) select '{transcript}','{u['account']}','{session}','{transcript}',coalesce(max(turn_index),0)+1,'answer',{literal(question)},{literal(answer)} from interview_session_transcript_entries where session_id='{session}';"
        f"select stamp_answer_source('{u['account']}','{session}','{transcript}',{literal(question)},{literal(answer)},'system_design')"
    )
    revision = u["db"].rows(
        f"select source_revision from interview_answer_sources where transcript_id='{transcript}'"
    )[0]["source_revision"]
    return session, transcript, revision, answer


def sketch_graph():
    return dict(
        status="ready",
        nodes=[
            dict(id="api", label="API", kind="service", evidence_quote="API"),
            dict(id="queue", label="Queue", kind="queue", evidence_quote="Queue"),
        ],
        edges=[
            dict(
                source="api",
                target="queue",
                label="tasks",
                evidence_quote="API sends tasks to Queue.",
            )
        ],
    )


def test_sketch_http_actual_store_permission_replay_and_retained_read(
    integration, monkeypatch
):
    from app.api import answer_diagrams as api
    from app.config import settings
    from app.services.answer_diagram_service import DiagramService

    u = integration
    session, transcript, revision, _ = sketch_case(u)
    calls = []

    async def provider(*args):
        calls.append(args)
        return sketch_graph(), "gpt-4.1-mini"

    shared = DiagramService(provider=provider)
    monkeypatch.setattr(api, "diagram_service", lambda: shared)
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    monkeypatch.setattr(settings, "DIAGRAM_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "synthetic-never-sent")
    monkeypatch.setattr(settings, "DIAGRAM_MODEL", "gpt-4.1-mini")
    url = f"/api/interview-sessions/{session}/transcript-entries/{transcript}/diagram"
    payload = dict(source_revision=revision, operation_id=str(uuid4()))
    h = headers(u["account"])
    assert u["client"].post(url, json=payload).status_code == 401
    response = u["client"].post(url, headers=h, json=payload)
    assert response.status_code == 200, response.text
    assert (
        response.json()["state"] == "ready"
        and response.json()["graph"] == sketch_graph()
    )
    assert response.headers["cache-control"] == "no-store"
    assert not {"token", "lease_until", "user_id"} & response.json().keys()
    assert u["client"].post(url, headers=h, json=payload).json() == response.json()
    assert len(calls) == 1
    assert not u["db"].rows(
        f"select 1 from usage_operations where account_id='{u['account']}'"
    )
    assert (
        u["client"]
        .post(url, headers=h, json={**payload, "actor": u["account"]})
        .status_code
        == 422
    )
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    assert (
        u["client"]
        .get(url, headers=headers(other), params={"source_revision": revision})
        .status_code
        == 409
    )
    u["db"].run(
        f"update account_plan_bindings set active=false,revision=revision+1 where account_id='{u['account']}'"
    )
    assert u["client"].post(url, headers=h, json=payload).status_code == 403
    assert len(calls) == 1
    # Explicit historical owner reads preserve already saved diagrams.
    assert (
        u["client"]
        .get(url, headers=h, params={"source_revision": revision})
        .json()["graph"]
        == sketch_graph()
    )


def test_free_sketch_exclusion_before_provider_and_missing_composition(
    integration, monkeypatch
):
    from app.api import answer_diagrams as api
    from app.config import settings
    from app.services.answer_diagram_service import DiagramService

    u = integration
    session, transcript, revision, _ = sketch_case(u, paid=False)

    async def never(*_):
        raise AssertionError("Excluded Sketch must not dispatch")

    monkeypatch.setattr(api, "diagram_service", lambda: DiagramService(provider=never))
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "DIAGRAM_GENERATION_ENABLED", True)
    url = f"/api/interview-sessions/{session}/transcript-entries/{transcript}/diagram"
    h, payload = headers(u["account"]), dict(
        source_revision=revision, operation_id=str(uuid4())
    )
    source = u["client"].get(
        f"/api/interview-sessions/{session}/answer-sources",
        headers=h,
        params={"transcript_id": transcript},
    )
    assert source.status_code == 200 and source.json()["eligible"]
    assert (
        not source.json()["generation_enabled"]
        and source.json()["reason"] == "subscription_denied"
    )
    response = u["client"].post(url, headers=h, json=payload)
    assert (
        response.status_code == 403 and response.headers["cache-control"] == "no-store"
    )
    assert not u["db"].rows(
        f"select 1 from interview_answer_diagrams where transcript_id='{transcript}'"
    )
    old = u["client"].app.state.subscriptions
    u["client"].app.state.subscriptions = None
    try:
        assert u["client"].post(url, headers=h, json=payload).status_code == 503
    finally:
        u["client"].app.state.subscriptions = old


def test_sketch_checkpoint_recovery_and_revocation_during_dispatch(
    integration, monkeypatch
):
    import asyncio

    from app.cloud.answer_diagrams import DiagramError
    from app.commercial.subscription_sketch import SubscriptionSketchStore
    from app.config import settings
    from app.services.answer_diagram_service import DiagramService

    u = integration
    session, transcript, revision, _ = sketch_case(u)
    store = SubscriptionSketchStore(u["subscription"], u["actor"])
    identity = (u["account"], session, transcript, revision, str(uuid4()))
    row = store.operation("claim", *identity, model="gpt-4.1-mini")
    store.operation(
        "checkpoint",
        *identity,
        token=row["token"],
        graph=sketch_graph(),
        model="gpt-4.1-mini",
    )

    async def never(*_):
        raise AssertionError("Checkpoint recovery must not dispatch")

    service = DiagramService(store, never)
    assert asyncio.run(service.run(identity))["state"] == "ready"
    other_session, other_transcript, other_revision, _ = sketch_case(u, paid=False)
    other_identity = (
        u["account"],
        other_session,
        other_transcript,
        other_revision,
        str(uuid4()),
    )

    async def revoke(*_):
        # Deterministic: provider completion happens after the independent revoke commits.
        revision = int(u["subscription"].current(u["actor"])["plan"]["revision"])
        u["provision"].status(u["account"], revision, active=False)
        return sketch_graph(), "gpt-4.1-mini"

    monkeypatch.setattr(settings, "DIAGRAM_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "synthetic-never-sent")
    monkeypatch.setattr(settings, "DIAGRAM_MODEL", "gpt-4.1-mini")
    # Revocation prevents the post-provider checkpoint; cleanup records failure.
    with pytest.raises(DiagramError) as revoked:
        asyncio.run(DiagramService(store, revoke).run(other_identity))
    assert revoked.value.status == 403
    assert store.operation("read", *other_identity)["state"] == "failed"
    assert not u["db"].rows(
        f"select 1 from interview_answer_diagrams where transcript_id='{other_transcript}' and graph is not null"
    )
    with pytest.raises(DiagramError) as error:
        asyncio.run(service.run(identity))
    assert error.value.status == 403


def manual_case(u, monkeypatch):
    from app.api import generate as api
    from app.config import settings
    from app.nlp.answer_generator import ProviderResult

    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    monkeypatch.setattr(settings, "ENABLE_SESSION_ANSWER_MODELS", True)
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_VALIDATION", False)
    monkeypatch.setattr(settings, "ENABLE_CONTROLLED_ANSWER_VARIATION", False)
    monkeypatch.setattr(
        settings, "ENABLE_INCREMENTAL_ANSWER_STREAMING", False, raising=False
    )
    session = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    calls = []

    def provider(**kwargs):
        calls.append(kwargs["question"])
        return ProviderResult(
            answer="Dependency injection supplies dependencies externally, making classes easy to test.",
            provider="synthetic",
            model="synthetic",
            primary_provider="synthetic",
            primary_model="synthetic",
            fallback_used=False,
            generation_ms=0,
            error=None,
        )

    monkeypatch.setattr(
        api.generator._default, "_generate_with_primary_provider", provider
    )
    return (
        dict(
            question="What is dependency injection?",
            category="technical",
            source="chat",
            session_id=session,
            request_id=str(uuid4()),
        ),
        calls,
    )


def test_manual_http_native_turn_persistence_stream_replay_and_conflict(
    integration, monkeypatch
):
    u = integration
    body, calls = manual_case(u, monkeypatch)
    client, h = u["client"], headers(u["account"])
    assert client.post("/generate/", json=body).status_code == 401
    response = client.post("/generate/", headers=h, json=body)
    assert response.status_code == 200, response.text
    assert "Dependency injection" in response.json()["answer"]
    replay = client.post("/generate/", headers=h, json=body)
    assert (
        replay.status_code == 200
        and replay.json()["answer"] == response.json()["answer"]
    )
    stream = client.post("/generate/stream", headers=h, json=body)
    assert stream.status_code == 200 and '"type": "done"' in stream.text
    assert len(calls) == 1
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    assert (
        client.get("/api/account/subscription", headers=headers(other)).status_code
        == 200
    )
    assert (
        client.post("/generate/", headers=headers(other), json=body).status_code == 404
    )
    assert (
        client.post("/generate/", headers=h, json={**body, "actor": other}).status_code
        == 422
    )
    rows = u["db"].rows(
        f"select state,transcript_id from session_generation_turns where session_id='{body['session_id']}'"
    )
    assert (
        len(rows) == 1 and rows[0]["state"] == "completed" and rows[0]["transcript_id"]
    )
    assert (
        u["db"].rows(
            f"select count(*) n from interview_session_transcript_entries where session_id='{body['session_id']}'"
        )[0]["n"]
        == 1
    )
    assert (
        client.post(
            "/generate/", headers=h, json={**body, "question": "Conflicting content"}
        ).status_code
        == 409
    )
    for source in ("auto", "screen"):
        assert (
            client.post(
                "/generate/", headers=h, json={**body, "source": source}
            ).status_code
            == 503
        )
    u["provision"].status(
        u["account"],
        int(u["subscription"].current(u["actor"])["plan"]["revision"]),
        active=False,
    )
    assert client.post("/generate/", headers=h, json=body).status_code == 403
    assert len(calls) == 1


def test_manual_checkpoint_save_only_recovery_no_second_provider(
    integration, monkeypatch
):
    from app.commercial.subscription_execution import SubscriptionTurns
    from app.session_generation import TurnStateError

    u = integration
    body, calls = manual_case(u, monkeypatch)
    original = SubscriptionTurns.operation
    lost = []

    async def fault(self, action, *args, **kwargs):
        if action == "complete" and not lost:
            lost.append(True)
            raise TurnStateError("persistence_unavailable")
        return await original(self, action, *args, **kwargs)

    monkeypatch.setattr(SubscriptionTurns, "operation", fault)
    h = headers(u["account"])
    response = u["client"].post("/generate/", headers=h, json=body)
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "persistence_unavailable"
    assert (
        u["db"].rows(
            f"select state from session_generation_turns where session_id='{body['session_id']}'"
        )[0]["state"]
        == "checkpoint"
    )
    response = u["client"].post(
        "/generate/", headers=h, json={**body, "recover_turn": True}
    )
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert (
        u["db"].rows(
            f"select count(*) n from interview_session_transcript_entries where session_id='{body['session_id']}'"
        )[0]["n"]
        == 1
    )


def test_manual_concurrent_duplicate_does_not_generate_twice(integration, monkeypatch):
    from app.api import generate as api

    u = integration
    body, calls = manual_case(u, monkeypatch)
    provider = api.generator._default._generate_with_primary_provider
    entered, release = threading.Event(), threading.Event()

    def held(**kwargs):
        entered.set()
        assert release.wait(5)
        return provider(**kwargs)

    monkeypatch.setattr(api.generator._default, "_generate_with_primary_provider", held)
    h = headers(u["account"])
    with ThreadPoolExecutor(2) as workers:
        first = workers.submit(u["client"].post, "/generate/", headers=h, json=body)
        try:
            assert entered.wait(5)
            duplicate = u["client"].post("/generate/", headers=h, json=body)
            assert duplicate.status_code == 409, duplicate.text
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["cancel", "downgrade"])
def test_scheduled_paid_period_change_preserves_usage_and_retries(integration, kind):
    u = integration
    session = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )
    for n in range(3):
        u["subscription"].save_clipboard(
            u["actor"], session, str(uuid4()), f"Retained answer {n}"
        )
    pro, plus = definition("pro"), definition("plus")
    assert create(u["client"], pro).status_code == 200
    assert create(u["client"], plus).status_code == 200
    pro_offer = publish(u["client"], pro)["receipt"]["offer_version_id"]
    plus_offer = publish(u["client"], plus)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=pro_offer,
        price_id=pro["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(),
    )
    service = VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
    )
    binding = service.apply("synthetic.payment")
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        kind=kind,
        expected_revision=binding["revision"],
    )
    if kind == "downgrade":
        event.update(
            offer_version_id=plus_offer,
            price_id=plus["terms"]["prices"][0]["price_id"],
            paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        )
    scheduled = service.schedule("synthetic.lifecycle")
    assert service.schedule("synthetic.lifecycle") == scheduled
    assert u["subscription"].current(u["actor"])["plan"]["name"] == "Pro"
    # Wait for an observed server timestamp, not a guessed concurrent winner.
    u["db"].run(
        f"do $$begin while clock_timestamp()<(select valid_until from account_plan_bindings where account_id='{u['account']}') loop perform pg_sleep(.01); end loop; end$$"
    )
    result = u["subscription"].current(u["actor"])
    assert result["plan"]["name"] == ("Free" if kind == "cancel" else "Plus")
    assert service.schedule("synthetic.lifecycle") == scheduled
    balance = next(x for x in result["usage"] if x["meter"] == "clipboard.new_saves")
    assert balance["used"] == "3" and balance["reserved"] == "0"
    assert len(u["subscription"].read_clipboard(u["actor"], session)) == 3
    assert not u["db"].rows(
        f"select 1 from subscription_scheduled_changes where account_id='{u['account']}'"
    )
    assert (
        u["db"].rows(
            f"select count(*) n from usage_events where account_id='{u['account']}' and event='binding.period_end_change'"
        )[0]["n"]
        == 1
    )


def test_schedule_revocation_identity_conflict_and_upgrade_supersession(integration):
    u = integration
    pro = definition("pro")
    assert create(u["client"], pro).status_code == 200
    offer = publish(u["client"], pro)["receipt"]["offer_version_id"]
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=pro["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )
    service = VerifiedPaymentService(
        lambda: u["connect"]("usage_binding_executor"), verify=lambda _: event
    )
    binding = service.apply("synthetic")
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        kind="cancel",
        expected_revision=binding["revision"],
    )
    result = service.schedule("synthetic")
    event["expected_revision"] += 1
    with pytest.raises(CatalogStoreError) as conflict:
        service.schedule("synthetic")
    assert conflict.value.code == ErrorCode.IDENTITY_CONFLICT
    event["expected_revision"] -= 1
    cancellation = event.copy()
    event = dict(
        account_id=u["account"],
        event_id=str(uuid4()),
        offer_version_id=offer,
        price_id=pro["terms"]["prices"][0]["price_id"],
        paid_until=(datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
    )
    renewed = service.apply("synthetic.renewal")
    current = u["subscription"].current(u["actor"])
    assert current["plan"]["name"] == "Pro" and current["plan"]["valid_until"]
    assert not u["db"].rows(
        f"select 1 from subscription_scheduled_changes where account_id='{u['account']}'"
    )
    event = cancellation
    assert service.schedule("synthetic.replay") == result
    u["provision"].status(u["account"], renewed["revision"], active=False)
    with pytest.raises(CatalogStoreError) as denied:
        service.schedule("synthetic.replay")
    assert denied.value.code == ErrorCode.DENIED


def test_unintegrated_transports_remain_closed_in_account_mode(
    integration, monkeypatch
):
    from app.config import settings
    from starlette.websockets import WebSocketDisconnect

    u = integration
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", False)
    for url in (
        "/api/screen/analyze-active-window-answer",
        "/api/resumes/upload",
        "/api/resume/upload",
        "/transcribe/alternate",
        "/api/audio/system/start",
    ):
        response = u["client"].post(url, headers=headers(u["account"]), json={})
        assert (
            response.status_code == 503
            and response.json()["detail"]["code"]
            == "subscription_execution_unavailable"
        )
    with pytest.raises(WebSocketDisconnect):
        with u["client"].websocket_connect("/ws/auto-stt"):
            pass


@pytest.mark.parametrize(
    "source,ending",
    [
        ("microphone", "stop"),
        ("system", "stop"),
        ("both", "stop"),
        ("microphone", "disconnect"),
        ("system", "expire"),
        ("system", "exhaust"),
    ],
)
def test_native_auto_grpc_capture_dispatch_ownership_heartbeat_and_stop(
    integration, monkeypatch, source, ending
):
    import asyncio
    from types import SimpleNamespace

    import grpc
    from app import grpc_answer_pipeline, grpc_server
    from app.config import settings
    from app.grpc_generated import (
        interview_realtime_pb2 as pb,
    )
    from app.grpc_generated import (
        interview_realtime_pb2_grpc as rpc,
    )
    from test_grpc_computer_lifecycle import chunk, configure, until

    u = integration
    body, calls = manual_case(u, monkeypatch)
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", False)
    monkeypatch.setattr(settings, "USE_GRPC_CLOUD_CONTEXT_PIPELINE", True)
    closed = []

    class Capture:
        def enable_continuous_resampling(self, session):
            pass

        def open_streaming_loopback_session(self, **kwargs):
            return SimpleNamespace(sample_rate=48000)

        def read_streaming_pcm_chunk(self, session):
            threading.Event().wait(
                0.01
            )  # Synthetic device pacing, never used to choose a race winner.
            return chunk(silent=True)

        def close_streaming_loopback_session(self, session):
            closed.append(True)
            return True

    if ending == "exhaust":
        prior = reserve(u, units=599, meter="auto.authorized_running")
        step(u, prior, "dispatch")
        step(u, prior, "checkpoint", result_ref=str(uuid4()))
        step(u, prior, "settle", charged=599, policy_version="synthetic.usage.v1")
    sockets = configure(monkeypatch, Capture)

    async def detect(text, allow_topics=False):
        return "What is dependency injection?", ""

    monkeypatch.setattr(grpc_answer_pipeline, "detect_intake_question", detect)

    async def exercise():
        runtime = u["client"].app.state.subscriptions
        server, port = await grpc_server.start_server(port=0, subscriptions=runtime)
        second, other_port = await grpc_server.start_server(
            port=0, subscriptions=runtime
        )
        metadata = (("authorization", headers(u["account"])["Authorization"]),)

        async def start(channel):
            call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(
                metadata=metadata, timeout=25 if ending == "expire" else 15
            )
            await call.write(
                pb.InterviewClientEvent(
                    session_id=str(uuid4()),
                    request_id="synthetic-start",
                    start_session=pb.StartSession(
                        mode="auto_pipeline",
                        source=source,
                        active_session_id=body["session_id"],
                        cloud_context_requested=True,
                    ),
                )
            )
            return call

        try:
            async with grpc.aio.insecure_channel(
                f"127.0.0.1:{port}"
            ) as channel, grpc.aio.insecure_channel(f"127.0.0.1:{other_port}") as other:
                call = await start(channel)
                ready = await until(
                    call, lambda e: e.HasField("ready") or e.HasField("error")
                )
                assert ready.HasField("ready"), ready.error.code
                assert len(sockets) == 1
                duplicate = await start(other)
                busy = await until(duplicate, lambda e: e.HasField("error"))
                assert busy.error.code == "subscription_auto_busy"
                assert len(sockets) == 1
                duplicate.cancel()
                if ending == "exhaust":
                    event = await asyncio.wait_for(
                        until(
                            call, lambda e: e.error.code == "subscription_auto_expired"
                        ),
                        3,
                    )
                    assert event.error.code == "subscription_auto_expired"
                    # The relay deliberately stops conservatively before its SQL
                    # deadline. Settle any tiny unused tail through an explicit
                    # synthetic silent lease, waiting for its returned deadline.
                    from app.commercial.subscription_auto import INSTANT

                    try:
                        tail = await asyncio.to_thread(
                            u["subscription"].auto,
                            u["actor"],
                            "start",
                            dict(run_id=str(uuid4()), request_id=str(uuid4())),
                        )
                    except CatalogStoreError as error:
                        assert error.code == ErrorCode.EXHAUSTED
                    else:
                        await asyncio.sleep(
                            max(
                                0,
                                (
                                    INSTANT.validate_python(tail["authorized_until"])
                                    - datetime.now(timezone.utc)
                                ).total_seconds(),
                            )
                        )
                        settled = await asyncio.to_thread(
                            u["subscription"].auto,
                            u["actor"],
                            "status",
                            dict(run_id=tail["run_id"]),
                        )
                        assert not settled["active"]
                    denied = await start(other)
                    exhausted = await until(
                        denied, lambda event: event.HasField("error")
                    )
                    assert exhausted.error.code == "subscription_auto_exhausted"
                    denied.cancel()
                    call.cancel()
                    assert not calls
                    return
                if source != "system":
                    await call.write(
                        pb.InterviewClientEvent(
                            session_id=ready.session_id,
                            audio_chunk=pb.AudioChunk(
                                audio=b"\0\0" * 1600,
                                sample_rate=16000,
                                channels=1,
                                encoding="linear16",
                            ),
                        )
                    )
                await sockets[0].events.put(
                    json.dumps(
                        dict(
                            type="Turn",
                            transcript="Explain dependency injection",
                            turn_order=0,
                            end_of_turn=True,
                        )
                    )
                )
                completed = await until(
                    call,
                    lambda e: e.HasField("answer_completed")
                    or e.HasField("error")
                    or e.HasField("answer_error"),
                )
                assert completed.HasField("answer_completed"), (
                    completed.error.code,
                    completed.answer_error.code,
                )
                assert len(calls) == 1
                sid = completed.session_id
                if source != "system":
                    await call.write(
                        pb.InterviewClientEvent(
                            session_id=sid,
                            audio_chunk=pb.AudioChunk(
                                audio=b"\0\0" * 1600,
                                sample_rate=16000,
                                channels=1,
                                encoding="linear16",
                            ),
                        )
                    )
                await call.write(
                    pb.InterviewClientEvent(
                        session_id=sid, request_id="heartbeat", ping=pb.Empty()
                    )
                )
                await until(call, lambda e: e.HasField("pong"))
                if ending == "expire":
                    event = await asyncio.wait_for(
                        until(
                            call, lambda e: e.error.code == "subscription_auto_expired"
                        ),
                        18,
                    )
                    assert event.error.code == "subscription_auto_expired"
                elif ending == "stop":
                    await call.write(
                        pb.InterviewClientEvent(
                            session_id=sid, request_id="stop", end_session=pb.Empty()
                        )
                    )
                    await until(
                        call,
                        lambda e: e.status.code in ("ended", "system_cleanup_pending"),
                    )

                call.cancel()
        finally:
            await server.stop(0)
            await second.stop(0)
            await grpc_server.shutdown_cleanup()

    asyncio.run(exercise())
    rows = u["db"].rows(
        f"select active from subscription_auto_runs where account_id='{u['account']}'"
    )
    assert (
        rows
        and all(not row["active"] for row in rows)
        and len(rows) <= (2 if ending == "exhaust" else 1)
    )
    balances = u["db"].rows(
        f"select sum(charged) used,sum(requested) reserved_count from usage_operations where account_id='{u['account']}' and operation='auto.running'"
    )
    assert 0 < balances[0]["used"] <= balances[0]["reserved_count"]
    assert balances[0]["used"] == 1000000 if ending == "exhaust" else True
    assert (
        balances[0]["used"] >= 15000000
        if ending == "expire"
        else balances[0]["used"] < 15000000
    )  # Silence counts; combined is one elapsed run, not two audio meters.
    assert u["db"].rows(
        f"select count(*) n from interview_session_transcript_entries where session_id='{body['session_id']}'"
    )[0]["n"] == (0 if ending == "exhaust" else 1)
    if source != "microphone":
        assert closed


def screen_case(u, monkeypatch, outcomes=None):
    from types import SimpleNamespace

    from app.api import screen_context as api
    from app.config import settings
    from app.models.screen_context import ScreenContextOutput
    from app.services.screen_context_service import response_for
    from test_screen_context import context, output

    original = api.get_screen_service()
    calls = []

    async def provider(request, files):
        calls.append(request)
        outcome = outcomes.pop(0) if outcomes else "answered"
        result = ScreenContextOutput.model_validate(
            output(request.model_dump(), outcome)
        )
        return response_for(request, result, original, logical_calls=1, http_attempts=1)

    monkeypatch.setattr(
        api, "get_screen_service", lambda: SimpleNamespace(answer_context=provider)
    )
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    session = str(uuid4())
    u["db"].run(
        f"insert into interview_sessions(id,user_id) values ('{session}','{u['account']}')"
    )

    def fresh(action="new"):
        body, files = context()
        body["identity"].update(
            cloudSessionId=session,
            accountGeneration=0,
            threadId=str(uuid4()),
            turnId=str(uuid4()),
            operationId=str(uuid4()),
            requestId=str(uuid4()),
        )
        body.update(
            action=action,
            contextKind="reference" if action == "reference" else "question",
        )
        return body, files

    def post(body, files, account=None):
        return u["client"].post(
            "/api/screen/analyze-context",
            headers=headers(account or u["account"]),
            data={"context": json.dumps(body)},
            files={
                key: ("synthetic.png", value, "image/png")
                for key, value in files.items()
            },
        )

    return fresh, post, calls


def test_native_screen_success_replay_exhaustion_and_forged_context(
    integration, monkeypatch
):
    u = integration
    fresh, post, calls = screen_case(u, monkeypatch)
    body, files = fresh()
    result = post(body, files)
    assert result.status_code == 200, result.text
    assert (
        result.json()["outcome"] == "answered"
        and result.headers["cache-control"] == "no-store"
    )
    assert post(body, files).json() == result.json() and len(calls) == 1
    for _ in range(4):
        b, f = fresh()
        assert post(b, f).status_code == 200
    b, f = fresh()
    exhausted = post(b, f)
    assert exhausted.status_code == 429, exhausted.text
    assert len(calls) == 5
    balance = next(
        x
        for x in u["subscription"].current(u["actor"])["usage"]
        if x["meter"] == "screen.analyses"
    )
    assert balance["used"] == "5" and balance["reserved"] == "0"
    # The result was persisted before being returned, and is owner-scoped.
    assert (
        u["db"].rows(
            f"select count(*) n from subscription_screen_results where account_id='{u['account']}' and response->>'outcome'='answered'"
        )[0]["n"]
        == 5
    )
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{other}')")
    u["subscription"].current(actor(other), bootstrap=True)
    assert post(body, files, other).status_code == 404


def test_native_screen_passage_clarification_and_server_followup_denial(
    integration, monkeypatch
):
    import copy

    u = integration
    fresh, post, calls = screen_case(u, monkeypatch, ["reference_accepted", "answered"])
    body, files = fresh("reference")
    reference = post(body, files)
    assert reference.status_code == 200, reference.text
    assert reference.json()["outcome"] == "reference_accepted"
    delta = reference.json()["evidenceDelta"]
    b = copy.deepcopy(body)
    b.update(action="continue")
    b["identity"].update(
        turnId=str(uuid4()),
        operationId=str(uuid4()),
        requestId=str(uuid4()),
        baseRevision=1,
    )
    b["input"]["evidence"] = [
        dict(
            text=delta["text"],
            complete=False,
            imageHash=b["input"]["currentImageHash"],
            turnId=body["identity"]["turnId"],
            kind="reference",
            imageHashes=delta["imageHashes"],
            replacesTurnIds=[],
        )
    ]
    b["input"]["images"][0]["role"] = "prior_current"
    answered = post(b, files)
    assert answered.status_code == 200, answered.text
    balance = next(
        x
        for x in u["subscription"].current(u["actor"])["usage"]
        if x["meter"] == "screen.analyses"
    )
    assert balance["used"] == "1"
    # Hiding the prior answer cannot change server-derived follow-up classification.
    forged = copy.deepcopy(b)
    forged["identity"].update(
        turnId=str(uuid4()),
        operationId=str(uuid4()),
        requestId=str(uuid4()),
        baseRevision=2,
    )
    # Duplicate source hash is kept as one manifest entry; both server evidence
    # turns refer to the same captured image, as supported by existing transport.
    d = answered.json()["evidenceDelta"]
    forged["input"]["evidence"].append(
        dict(
            text=d["text"],
            complete=True,
            imageHash=b["input"]["currentImageHash"],
            turnId=b["identity"]["turnId"],
            imageHashes=d["imageHashes"],
            replacesTurnIds=[],
        )
    )
    denied = post(forged, files)
    assert denied.status_code == 403, denied.text
    assert len(calls) == 2


def test_native_screen_failed_result_and_atomic_rollback_release_quota(
    integration, monkeypatch
):
    u = integration
    fresh, post, calls = screen_case(u, monkeypatch, ["failed", "answered"])
    b, f = fresh()
    failed = post(b, f)
    assert failed.status_code == 200 and failed.json()["outcome"] == "failed"
    u["db"].run(
        "create function synthetic_screen_failure() returns trigger language plpgsql as $$begin if new.event='result.settle' then raise exception 'synthetic rollback' using errcode='P0005';end if;return new;end$$;create trigger synthetic_screen_failure before insert on usage_events for each row execute function synthetic_screen_failure()"
    )
    try:
        b, f = fresh()
        result = post(b, f)
        assert result.status_code == 503, result.text
    finally:
        u["db"].run(
            "drop trigger synthetic_screen_failure on usage_events;drop function synthetic_screen_failure()"
        )
    balance = next(
        x
        for x in u["subscription"].current(u["actor"])["usage"]
        if x["meter"] == "screen.analyses"
    )
    assert balance["used"] == "0" and balance["reserved"] == "0"
    assert not u["db"].rows(
        f"select 1 from subscription_screen_results where account_id='{u['account']}' and response->>'outcome'='answered'"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )


def resume_case(u, monkeypatch):
    from app.api import resumes
    from app.cloud.cloud_resume import CloudResumeError, CloudResumeService
    from app.config import settings
    from app.services.resume_index_service import ResumeIndexService

    db = u["db"]
    objects = {}

    class Storage:
        def upload_resume_object(self, path, content, mime):
            if path in objects:
                raise CloudResumeError("exists")
            objects[path] = content

        def download_resume_object(self, path):
            return objects[path]

        def delete_resume_object(self, path):
            objects.pop(path, None)

        def insert_resume_chunks(self, chunks):
            for row in chunks:
                doc = json.dumps(row).replace("'", "''")
                db.run(
                    f"insert into resume_chunks(user_id,resume_id,section,chunk_text,generation_id,metadata) select x.user_id,x.resume_id,x.section,x.chunk_text,x.generation_id,x.metadata from jsonb_populate_record(null::resume_chunks,'{doc}') x"
                )

        def delete_resume_chunks(self, *, user_id, resume_id, generation_id=None):
            db.run(
                f"delete from resume_chunks where user_id='{user_id}' and resume_id='{resume_id}'"
                + (f" and generation_id='{generation_id}'" if generation_id else "")
            )

        def delete_inactive_resume_chunks(
            self, *, user_id, resume_id, active_generation_id
        ):
            db.run(
                f"delete from resume_chunks where user_id='{user_id}' and resume_id='{resume_id}' and generation_id<>'{active_generation_id}'"
            )

        def get_active_resume_chunk_counts(self, *, user_id, records):
            return {
                (r.id, str(r.active_chunk_generation)): db.rows(
                    f"select count(*) n from resume_chunks where user_id='{user_id}' and resume_id='{r.id}' and generation_id='{r.active_chunk_generation}'"
                )[0]["n"]
                for r in records
            }

    class Parser:
        def extract_profile(self, **kwargs):
            return dict(
                profile={
                    "full_name": "Synthetic candidate",
                    "professional_summary": "Builds synthetic software",
                },
                parser_provider="synthetic",
                extracted_text_length=25,
            )

    service = CloudResumeService(
        client=Storage(), parser=Parser(), indexer=ResumeIndexService()
    )
    monkeypatch.setattr(resumes, "_cached_cloud_resume_service", lambda: service)
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")

    def upload(key=None, body=b"Synthetic candidate software experience"):
        return u["client"].post(
            "/api/resumes",
            headers={**headers(u["account"]), "Idempotency-Key": key or str(uuid4())},
            files={"file": ("synthetic.txt", body, "text/plain")},
        )

    def ready(identifier):
        r = u["client"].post(
            f"/api/resumes/{identifier}/extract", headers=headers(u["account"])
        )
        assert r.status_code == 200, r.text
        r = u["client"].post(
            f"/api/resumes/{identifier}/confirm",
            headers=headers(u["account"]),
            json={
                "extraction_attempt": r.json()["extraction_attempt"],
                "profile": r.json()["profile"],
            },
        )
        return r

    return upload, ready, service


def test_native_resume_initial_replacement_delete_history_and_retries(
    integration, monkeypatch
):
    u = integration
    upload, ready, service = resume_case(u, monkeypatch)
    key = str(uuid4())
    first = upload(key)
    assert first.status_code == 201, first.text
    rid = first.json()["id"]
    assert upload(key).json()["id"] == rid
    assert upload(key, b"Other semantics").status_code == 409
    assert upload().status_code == 409
    result = ready(rid)
    assert result.status_code == 200, result.text
    assert (
        u["db"].rows(
            f"select count(*) n from usage_operations where account_id='{u['account']}' and period_id in (select period_id from usage_periods where meter='resume.replacements')"
        )[0]["n"]
        == 0
    )
    second = upload()
    assert second.status_code == 201, second.text
    rid2 = second.json()["id"]
    result = ready(rid2)
    assert result.status_code == 200, result.text
    assert (
        u["db"].rows(
            f"select sum(charged) n from usage_operations where account_id='{u['account']}' and period_id in (select period_id from usage_periods where meter='resume.replacements')"
        )[0]["n"]
        == 1
    )
    assert (
        u["client"]
        .delete(f"/api/resumes/{rid2}", headers=headers(u["account"]))
        .status_code
        == 200
    )
    assert upload().status_code == 429  # Deletion never restores the initial upload.
    assert (
        u["client"]
        .get(f"/api/resumes/{rid}/status", headers=headers(str(uuid4())))
        .status_code
        == 404
    )


def test_native_resume_failed_index_retains_previous_and_releases(
    integration, monkeypatch
):
    from app.services.resume_index_service import ResumeIndexError

    u = integration
    upload, ready, service = resume_case(u, monkeypatch)
    first = upload().json()["id"]
    assert ready(first).status_code == 200
    second = upload().json()["id"]
    monkeypatch.setattr(
        service._indexer,
        "build_chunks_from_documents",
        lambda *_: (_ for _ in ()).throw(ResumeIndexError("synthetic")),
    )
    assert ready(second).status_code == 502
    current = u["client"].get("/api/resumes/current", headers=headers(u["account"]))
    assert current.status_code == 200 and current.json()["resume"]["id"] == first
    assert u["db"].rows(
        f"select coalesce(sum(used),0) used,coalesce(sum(reserved),0) held from usage_periods where account_id='{u['account']}' and period_id in (select period_id from usage_periods where meter='resume.replacements')"
    )[0] == {"used": 0, "held": 0}
    assert upload().status_code == 201


def test_native_auxiliary_notes_ask_history_export_and_replay(integration, monkeypatch):
    from types import SimpleNamespace

    from app.api import interview_sessions as api

    u = integration
    body, calls = manual_case(u, monkeypatch)
    client = u["client"]
    h = headers(u["account"])
    sid = body["session_id"]
    assert client.post("/generate/", headers=h, json=body).status_code == 200
    notes_calls = []
    ask_calls = []

    class NotesGenerator:
        def generate(self, **kw):
            notes_calls.append(True)
            return dict(
                notes_markdown=f"Synthetic notes revision {len(notes_calls)}",
                provider="synthetic",
                model="synthetic",
            )

    class AskGenerator:
        def generate(self, **kw):
            ask_calls.append(True)
            return dict(
                answer_text="Synthetic coaching answer",
                provider="synthetic",
                model="synthetic",
            )

    monkeypatch.setattr(
        api,
        "_cached_cloud_interview_notes_service",
        lambda: SimpleNamespace(_generator=NotesGenerator()),
    )
    monkeypatch.setattr(
        api,
        "_cached_cloud_interview_ask_ai_service",
        lambda: SimpleNamespace(_generator=AskGenerator()),
    )
    monkeypatch.setattr(api, "_trigger_feature_email", lambda **_: None)
    notes_url = f"/api/interview-sessions/{sid}/notes/generate"
    key = str(uuid4())
    nh = {**h, "Idempotency-Key": key}
    first = client.post(notes_url, headers=nh, json={"force_regenerate": False})
    assert first.status_code == 200, first.text
    assert (
        client.post(notes_url, headers=nh, json={"force_regenerate": False}).json()
        == first.json()
    )
    second = client.post(
        notes_url,
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"force_regenerate": True},
    )
    assert second.status_code == 200, second.text
    assert (
        client.post(notes_url, headers=nh, json={"force_regenerate": False}).json()
        == first.json()
    )
    assert len(notes_calls) == 2
    url = f"/api/interview-sessions/{sid}/ask-ai"
    question = dict(
        question="How can I improve?", request_id=str(uuid4()), include_notes=True
    )
    answer = client.post(url, headers=h, json=question)
    assert answer.status_code == 200, answer.text
    assert (
        client.post(url, headers=h, json=question).json()["answer_text"]
        == answer.json()["answer_text"]
    )
    assert len(ask_calls) == 1
    assert (
        client.post(
            url, headers=h, json={**question, "question": "Conflicting question"}
        ).status_code
        == 409
    )
    r = client.get(f"/api/interview-sessions/{sid}/transcript-entries", headers=h)
    assert r.status_code == 200, r.text
    r = client.get("/api/interview-sessions", headers=h)
    assert r.status_code == 200, r.text
    # Hosted ingress intentionally only opens reviewed paths; exercise export in
    # local account composition without opening the rest of the hosted prefix.
    from app.config import settings

    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", False)
    exported = client.get(
        f"/api/interview-sessions/{sid}/transcript/download", headers=h
    )
    assert exported.status_code == 200 and "Dependency injection" in exported.text
    assert client.get(
        f"/api/interview-sessions/{sid}/notes", headers=headers(str(uuid4()))
    ).status_code in (403, 404, 503)


def test_native_screen_concurrent_duplicate_lost_ack_and_owner_read(
    integration, monkeypatch
):
    import asyncio

    from app.api import screen_context as api
    from app.commercial.subscription_screen import AccountScreen
    from fastapi import HTTPException

    u = integration
    fresh, post, calls = screen_case(u, monkeypatch)
    original_provider = api.get_screen_service().answer_context
    entered = threading.Event()
    release = threading.Event()

    async def delayed(context, files):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return await original_provider(context, files)

    from types import SimpleNamespace

    monkeypatch.setattr(
        api, "get_screen_service", lambda: SimpleNamespace(answer_context=delayed)
    )
    b, f = fresh()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(post, b, f)
        assert entered.wait(5)
        try:
            duplicate = pool.submit(post, b, f).result(5)
            assert duplicate.status_code == 409, duplicate.text
        finally:
            release.set()
        result = first.result(5)
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    original = AccountScreen.call
    lost = []

    def lose_ack(self, action, doc, **kw):
        result = original(self, action, doc, **kw)
        if action == "complete" and not lost:
            lost.append(True)
            raise HTTPException(503, detail={"code": "catalog_outcome_uncertain"})
        return result

    monkeypatch.setattr(AccountScreen, "call", lose_ack)
    b2, f2 = fresh()
    uncertain = post(b2, f2)
    assert uncertain.status_code == 503, uncertain.text
    replay = post(b2, f2)
    assert replay.status_code == 200, replay.text
    assert len(calls) == 2
    saved = u["client"].get(
        f"/api/screen/sessions/{b['identity']['cloudSessionId']}/results",
        headers=headers(u["account"]),
    )
    assert saved.status_code == 200 and len(saved.json()["items"]) == 2, saved.text
    assert all(
        "semantic_hash" not in x and "token" not in x for x in saved.json()["items"]
    )


def test_native_resume_concurrent_uploads_and_downgrade_active_set(
    integration, monkeypatch
):
    u = integration
    upload, ready, _ = resume_case(u, monkeypatch)
    barrier = threading.Barrier(2)

    def concurrent():
        barrier.wait(5)
        return upload()

    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(concurrent)
        two = pool.submit(concurrent)
        responses = [one.result(5), two.result(5)]
    assert sorted(r.status_code for r in responses) == [201, 409]
    first = next(r for r in responses if r.status_code == 201).json()["id"]
    assert ready(first).status_code == 200
    # Upgrade through the existing trusted synthetic-payment path, not a user
    # or admin assignment endpoint. Additional slots do not count replacements.
    sketch_case(u, paid=True)
    second = upload().json()["id"]
    assert ready(second).status_code == 200
    u["db"].run(
        f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 second',revision=revision+1 where account_id='{u['account']}'"
    )
    current = u["subscription"].current(u["actor"])
    assert current["plan"]["name"] == "Free"
    denied = upload()
    assert denied.status_code == 403, denied.text
    selected = u["client"].post(
        "/api/resumes/active-set",
        headers=headers(u["account"]),
        json={"resume_ids": [first]},
    )
    assert selected.status_code == 200, selected.text
    assert (
        len(
            u["client"]
            .get("/api/resumes", headers=headers(u["account"]))
            .json()["items"]
        )
        == 2
    )


def test_native_manual_transcription_eligibility_and_auto_bypass(
    integration, monkeypatch
):
    from types import SimpleNamespace

    from app.api import transcribe
    from app.config import settings

    u = integration
    calls = []
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)

    def provider(**kw):
        calls.append(True)
        return SimpleNamespace(
            text="Synthetic transcription",
            transcription_provider="synthetic",
            transcription_model="synthetic",
            transcription_ms=0,
            fallback_used=False,
            fallback_reason=None,
            no_speech=False,
            reason=None,
        )

    monkeypatch.setattr(transcribe.stt_provider, "transcribe_upload", provider)
    files = {"file": ("recording.wav", b"synthetic audio", "audio/wav")}
    response = u["client"].post("/transcribe/", files=files, data={"mode": "manual"})
    assert response.status_code == 401, response.text
    response = u["client"].post(
        "/transcribe/",
        headers=headers(u["account"]),
        files=files,
        data={"mode": "manual"},
    )
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    ), response.text
    response = u["client"].post(
        "/transcribe/",
        headers=headers(u["account"]),
        files=files,
        data={"mode": "auto"},
    )
    assert response.status_code == 403 and len(calls) == 1, response.text


def test_native_result_crash_reaper_fences_screen_and_notes(integration, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.api import screen_context as api

    u = integration
    fresh, post, calls = screen_case(u, monkeypatch)
    original = api.get_screen_service().answer_context
    entered = threading.Event()
    release = threading.Event()

    async def late(context, files):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return await original(context, files)

    monkeypatch.setattr(
        api, "get_screen_service", lambda: SimpleNamespace(answer_context=late)
    )
    body, files = fresh()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(post, body, files)
        assert entered.wait(5)
        try:
            u["db"].run(
                f"update subscription_screen_results set lease_until=clock_timestamp()-interval '1 second' where account_id='{u['account']}' and state='processing'"
            )
            u["subscription"]._channel._transaction(
                True, lambda q: q("select subscription_result_sweep(50)", ())
            )
        finally:
            release.set()
        result = pending.result(5)
    assert result.status_code == 409, result.text
    assert post(body, files).status_code == 409 and len(calls) == 1
    assert not u["db"].rows(
        f"select 1 from subscription_screen_results where account_id='{u['account']}' and response is not null"
    )
    assert u["db"].rows(
        f"select sum(used) used,sum(reserved) held from usage_periods where account_id='{u['account']}' and meter='screen.analyses'"
    )[0] == {"used": 0, "held": 0}
    # A separate native Notes operation proves sweep recovery is not Screen-only.
    session = body["identity"]["cloudSessionId"]
    key = str(uuid4())
    claim = u["subscription"]._channel._transaction(
        True,
        lambda q: q(
            "select subscription_aux_call(%s,%s,%s::jsonb)",
            (
                u["account"],
                "notes.claim",
                json.dumps(
                    dict(session_id=session, request_id=key, semantic_hash="e" * 64)
                ),
            ),
        ),
    )
    u["db"].run(
        f"update usage_operations set lease_until=clock_timestamp()-interval '1 second' where operation_id='{claim['operation_id']}'"
    )
    u["subscription"]._channel._transaction(
        True, lambda q: q("select subscription_result_sweep(50)", ())
    )
    row = u["db"].rows(
        f"select state,charged from usage_operations where operation_id='{claim['operation_id']}'"
    )[0]
    assert row == {"state": "released", "charged": None}
    replay = u["subscription"]._channel._transaction(
        True,
        lambda q: q(
            "select subscription_aux_call(%s,%s,%s::jsonb)",
            (
                u["account"],
                "notes.claim",
                json.dumps(
                    dict(session_id=session, request_id=key, semantic_hash="e" * 64)
                ),
            ),
        ),
    )
    assert replay["failed"] and not replay["claimed"]


def test_native_screen_clarification_same_operation_transport_retry_and_paid_followup(
    integration, monkeypatch
):
    import copy

    u = integration
    fresh, post, calls = screen_case(
        u, monkeypatch, ["needs_clarification", "answered", "answered"]
    )
    body, files = fresh()
    first = post(body, files)
    assert first.status_code == 200, first.text
    retry = copy.deepcopy(body)
    retry["identity"]["requestId"] = str(uuid4())
    again = post(retry, files)
    assert again.status_code == 200, again.text
    assert (
        again.json()["identity"]["requestId"] == retry["identity"]["requestId"]
        and len(calls) == 1
    )
    reply = copy.deepcopy(retry)
    reply["identity"]["requestId"] = str(uuid4())
    reply["clarificationResponse"] = dict(
        requestId=retry["identity"]["requestId"],
        threadId=body["identity"]["threadId"],
        turnId=body["identity"]["turnId"],
        text="Use the original implementation",
    )
    answered = post(reply, files)
    assert answered.status_code == 200, answered.text
    balance = next(
        x
        for x in u["subscription"].current(u["actor"])["usage"]
        if x["meter"] == "screen.analyses"
    )
    assert balance["used"] == "1" and balance["reserved"] == "0"
    sketch_case(u, paid=True)
    follow = copy.deepcopy(body)
    follow.update(action="continue")
    follow["identity"].update(
        turnId=str(uuid4()),
        operationId=str(uuid4()),
        requestId=str(uuid4()),
        baseRevision=1,
    )
    delta = answered.json()["evidenceDelta"]
    follow["input"]["evidence"] = [
        dict(
            text=delta["text"],
            complete=True,
            imageHash=follow["input"]["currentImageHash"],
            turnId=body["identity"]["turnId"],
            imageHashes=delta["imageHashes"],
            replacesTurnIds=[],
        )
    ]
    follow["input"]["images"][0]["role"] = "prior_current"
    result = post(follow, files)
    assert result.status_code == 200, result.text
    assert len(calls) == 3
    assert (
        u["db"].rows(
            f"select count(*) n from subscription_screen_results where account_id='{u['account']}' and kind='followup'"
        )[0]["n"]
        == 1
    )


def test_native_resume_lost_activation_response_replays_without_reindex_or_charge(
    integration, monkeypatch
):
    from app.commercial.subscription_resume import AccountResumeClient

    u = integration
    upload, ready, service = resume_case(u, monkeypatch)
    first = upload().json()["id"]
    assert ready(first).status_code == 200
    second = upload().json()["id"]
    original = AccountResumeClient.call
    lost = []

    def lose(self, action, **document):
        result = original(self, action, **document)
        if action == "activate" and not lost:
            lost.append(True)
            raise CatalogStoreError(ErrorCode.UNCERTAIN)
        return result

    monkeypatch.setattr(AccountResumeClient, "call", lose)
    uncertain = ready(second)
    assert uncertain.status_code == 503, uncertain.text
    # The original ready activation committed. Same reviewed identity recovers
    # the result and does not run parser/indexing or debit another replacement.
    record = (
        u["client"]
        .get(f"/api/resumes/{second}/status", headers=headers(u["account"]))
        .json()
    )
    result = u["client"].post(
        f"/api/resumes/{second}/confirm",
        headers=headers(u["account"]),
        json={
            "extraction_attempt": record["extraction_attempt"],
            "profile": {
                "full_name": "Synthetic candidate",
                "professional_summary": "Builds synthetic software",
            },
        },
    )
    assert result.status_code == 200 and result.json()["ready"], result.text
    assert (
        u["db"].rows(
            f"select sum(charged) n from usage_operations where account_id='{u['account']}' and operation='resume.replace'"
        )[0]["n"]
        == 1
    )
    wrong = u["client"].post(
        f"/api/resumes/{second}/confirm",
        headers=headers(u["account"]),
        json={
            "extraction_attempt": record["extraction_attempt"],
            "profile": {"full_name": "Conflicting review"},
        },
    )
    assert wrong.status_code == 409, wrong.text


def test_native_screen_cancellation_releases_without_saved_result(
    integration, monkeypatch
):
    import asyncio

    from app.commercial.subscription_screen import AccountScreen
    from app.models.screen_context import ScreenContextRequest
    from starlette.requests import Request

    u = integration
    fresh, _, _ = screen_case(u, monkeypatch)
    body, files = fresh()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/screen/analyze-context",
            "headers": [
                (b"authorization", headers(u["account"])["Authorization"].encode())
            ],
            "app": u["client"].app,
        }
    )

    async def exercise():
        entered = asyncio.Event()

        async def provider(*_):
            entered.set()
            await asyncio.Future()

        task = asyncio.create_task(
            AccountScreen(request).run(
                ScreenContextRequest.model_validate(body), files, provider
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert u["db"].rows(
        f"select state,response from subscription_screen_results where account_id='{u['account']}'"
    ) == [{"state": "failed", "response": None}]
    assert u["db"].rows(
        f"select used,reserved from usage_periods where account_id='{u['account']}' and meter='screen.analyses'"
    ) == [{"used": 0, "reserved": 0}]


def test_native_screen_revocation_before_result_releases_and_denies_replay(
    integration, monkeypatch
):
    from types import SimpleNamespace

    from app.api import screen_context as api

    u = integration
    fresh, post, calls = screen_case(u, monkeypatch)
    original = api.get_screen_service().answer_context

    async def revoke(context, files):
        u["provision"].status(u["account"], 1, active=False)
        return await original(context, files)

    monkeypatch.setattr(
        api, "get_screen_service", lambda: SimpleNamespace(answer_context=revoke)
    )
    body, files = fresh()
    result = post(body, files)
    assert result.status_code == 403, result.text
    assert post(body, files).status_code == 403 and len(calls) == 1
    assert not u["db"].rows(
        f"select 1 from subscription_screen_results where account_id='{u['account']}' and response is not null"
    )
    assert u["db"].rows(
        f"select used,reserved from usage_periods where account_id='{u['account']}' and meter='screen.analyses'"
    ) == [{"used": 0, "reserved": 0}]
