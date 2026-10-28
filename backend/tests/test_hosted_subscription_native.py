"""Isolated actual JWT/ASGI/relay/PostgreSQL; no live provider or device."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_subscription_integration_native as native_fixtures
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.hosted_coordination import HostedCoordination, SharedHandoff
from test_draft_api_native import headers
from test_subscription_integration_native import (  # noqa: F401
    case,
    database,
    f1_install,
    f2_install,
    install,
    manual_case,
    pricing,
    upgraded,
    usage,
)
from test_usage_store_native import actor

integration = native_fixtures.integration


@pytest.fixture(autouse=True)
def isolated_relay_deployment(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'HOSTED_AUDIO_DEPLOYMENT_ID', 'synthetic.relay.v1')


def test_desktop_capabilities_are_verified_private_and_default_closed(
    integration, monkeypatch
):
    from app.config import settings
    from test_grpc_computer_lifecycle import configure

    u = integration
    manual_case(u, monkeypatch)
    configure(monkeypatch, lambda: None)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ENABLED", True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_DEPLOYMENT_ID", "")
    route = "/api/account/audio/capabilities"
    h = headers(u["account"])
    response = u["client"].get(route, headers=h)
    assert response.status_code == 503
    monkeypatch.setattr(settings, "HOSTED_AUDIO_DEPLOYMENT_ID", "synthetic.relay.v1")
    denied = u["client"].get(route)
    assert denied.status_code == 401 and denied.headers["cache-control"] == "no-store"
    response = u["client"].get(route, headers=h)
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert response.json()["protocol_version"] == 1
    assert response.json()["deployment_id"] == "synthetic.relay.v1"
    assert response.json()["combined_audio_available"]
    assert not u["db"].rows(
        f"select 1 from subscription_auto_runs where account_id='{u['account']}'"
    )
    assert u["client"].post(route, headers=h).status_code != 200


def test_staging_preflight_read_only_and_manifest_matches_source(integration):
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "docs/sql/C11_C13_STAGING_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert len({item["version"] for item in manifest}) == len(manifest)
    assert [item["version"] for item in manifest] == sorted(
        item["version"] for item in manifest
    )
    for item in manifest:
        assert (
            hashlib.sha256(
                (root / "supabase/migrations" / item["file"]).read_bytes()
            ).hexdigest()
            == item["sha256"]
        )
    db = integration["db"]
    target_preflight = (
        root / "docs/sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_PREFLIGHT.sql"
    ).read_text(encoding="utf-8")
    before = db.rows("select count(*) n from usage_events")
    assert "subscription_relay_connections" in db.run(target_preflight)
    assert db.rows("select to_regclass('supabase_migrations.schema_migrations') h") == [
        {"h": None}
    ]
    assert db.rows("select count(*) n from usage_events") == before
    # Test-only history intentionally omits the latest applied object's version:
    # preflight must report the history gap AND the actual existing objects.
    db.run(
        "create schema supabase_migrations;"
        "create table supabase_migrations.schema_migrations(version text primary key);"
    )
    before = db.rows("select count(*) n from usage_events")
    output = db.run(
        (root / "docs/sql/C11_C13_STAGING_PREFLIGHT.sql").read_text(encoding="utf-8")
    )
    assert "MISSING_HISTORY_REVIEW_SCHEMA" in output
    assert "20261024110000" in output and "subscription_relay_frames" in output
    assert db.rows("select count(*) n from usage_events") == before
    assert db.rows("select count(*) n from supabase_migrations.schema_migrations") == [
        {"n": 0}
    ]
    assert "subscription_relay_connections" in db.run(target_preflight)


def test_hosted_answer_is_durable_and_frame_replay_cannot_regenerate(
    integration, monkeypatch
):
    from app import grpc_answer_pipeline
    from app.config import settings
    from test_grpc_computer_lifecycle import configure

    u = integration
    body, calls = manual_case(u, monkeypatch)

    class NoDevice:
        def __init__(self):
            raise AssertionError("Hosted relay cannot capture on server")

    sockets = configure(monkeypatch, NoDevice)
    for flag in (
        "HOSTED_AUDIO_ENABLED",
        "ENABLE_SESSION_ANSWER_MODELS",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ORIGINS", "https://synthetic.invalid")

    async def detect(*_args, **_kwargs):
        return "What is dependency injection?", ""

    monkeypatch.setattr(grpc_answer_pipeline, "detect_intake_question", detect)
    h = {**headers(u["account"]), "origin": "https://synthetic.invalid"}
    document = {
        "stream_id": str(uuid4()),
        "session_id": body["session_id"],
        "source": "microphone",
    }
    with u["client"].websocket_connect("/api/account/audio/stream", headers=h) as ws:
        ws.send_json(document)
        for _ in range(20):
            event = ws.receive_json()
            assert "error" not in event, event
            if "ready" in event:
                break
        else:
            raise AssertionError("No authorized ready event")
        original = sockets[0].send

        async def send(data):
            await original(data)
            if isinstance(data, bytes):
                await sockets[0].events.put(
                    json.dumps(
                        {
                            "type": "Turn",
                            "transcript": "Explain dependency injection",
                            "turn_order": 0,
                            "end_of_turn": True,
                        }
                    )
                )

        sockets[0].send = send
        frame = (1).to_bytes(8, "big") + bytes(3200)
        ws.send_bytes(frame)
        for _ in range(60):
            event = ws.receive_json()
            assert "error" not in event and "answer_error" not in event, event
            if "answer_completed" in event:
                break
        else:
            raise AssertionError("No durable answer completion")
        assert len(calls) == 1
        assert u["db"].rows(
            f"select count(*) n from interview_session_transcript_entries where session_id='{body['session_id']}'"
        ) == [{"n": 1}]
        ws.send_bytes(frame)
        ws.send_text("ping")
        for _ in range(20):
            if "pong" in ws.receive_json():
                break
        else:
            raise AssertionError("No replay boundary acknowledgement")
        assert len(calls) == 1
        ws.send_text("stop")
        for _ in range(20):
            if ws.receive_json().get("status", {}).get("code") in (
                "ended",
                "system_cleanup_pending",
            ):
                break
    response = u["client"].get(
        f"/api/interview-sessions/{body['session_id']}/transcript-entries",
        headers=headers(u["account"]),
    )
    assert response.status_code == 200 and len(calls) == 1
    assert u["db"].rows(
        f"select count(*) n from interview_session_transcript_entries where session_id='{body['session_id']}'"
    ) == [{"n": 1}]


def test_deletion_barrier_resume_and_immutable_history(integration, monkeypatch):
    u = integration
    body, _ = manual_case(u, monkeypatch)
    coordination = HostedCoordination(u["subscription"])
    start = u["subscription"].auto(
        u["actor"], "start", {"run_id": str(uuid4()), "request_id": str(uuid4())}
    )
    key = str(uuid4())
    result = coordination.prepare_deletion(u["actor"], key)
    assert result["phase"] == "policy_pending" and not result["irreversible_enabled"]
    assert coordination.prepare_deletion(u["actor"], key) == result
    with pytest.raises(CatalogStoreError) as caught:
        coordination.prepare_deletion(u["actor"], str(uuid4()))
    assert caught.value.code == ErrorCode.IDENTITY_CONFLICT
    for operation in [
        lambda: u["subscription"].current(u["actor"]),
        lambda: u["subscription"].resolve(u["actor"]),
        lambda: coordination.available(u["actor"]),
    ]:
        with pytest.raises(CatalogStoreError) as denied:
            operation()
        assert denied.value.code == ErrorCode.DENIED
    assert u["db"].rows(
        f"select active from subscription_auto_runs where run_id='{start['run_id']}'"
    ) == [{"active": False}]
    assert u["db"].rows(
        f"select count(*) n from usage_events where account_id='{u['account']}' and event='privacy.prepare'"
    ) == [{"n": 1}]
    assert u["db"].rows(f"select id from auth.users where id='{u['account']}'")
    assert (
        u["client"]
        .get("/api/account/subscription", headers=headers(u["account"]))
        .status_code
        == 403
    )
    assert (
        u["client"]
        .get(
            f"/api/interview-sessions/{body['session_id']}/my-answers",
            headers=headers(u["account"]),
        )
        .status_code
        == 403
    )
    # Forged subject cannot act for the retained bearer, even after the barrier.
    with pytest.raises(CatalogStoreError):
        coordination.prepare_deletion(
            type(u["actor"])(str(uuid4()), u["actor"]._bearer), str(uuid4())
        )


def test_deletion_transaction_failure_rolls_back(integration):
    u = integration
    u["db"].run(
        "create function public.fail_privacy_test() returns trigger language plpgsql as $$begin raise exception 'synthetic rollback';end$$;create trigger fail_privacy_test before insert on subscription_deletion_jobs for each row execute function public.fail_privacy_test()"
    )
    key = str(uuid4())
    try:
        with pytest.raises(CatalogStoreError):
            HostedCoordination(u["subscription"]).prepare_deletion(u["actor"], key)
        assert not u["db"].rows(
            f"select 1 from subscription_deletion_jobs where account_id='{u['account']}'"
        )
        assert u["subscription"].current(u["actor"])["plan"]["name"] == "Free"
    finally:
        u["db"].run(
            "drop trigger fail_privacy_test on subscription_deletion_jobs;drop function public.fail_privacy_test()"
        )
    assert (
        HostedCoordination(u["subscription"]).prepare_deletion(u["actor"], key)["phase"]
        == "policy_pending"
    )


def test_deletion_direct_rls_and_storage_are_blocked(integration, monkeypatch):
    u = integration
    body, _ = manual_case(u, monkeypatch)
    u["db"].run(
        "grant authenticated to authenticator;grant usage on schema storage to authenticated;alter table storage.objects enable row level security;grant select on storage.objects to authenticated;insert into storage.objects values('synthetic','synthetic-object')"
    )

    def visible():
        conn = u["connect"]("authenticator")
        try:
            conn.execute("set role authenticated")
            conn.execute(
                "select set_config('request.jwt.claim.sub',%s,true)", (u["account"],)
            )
            return (
                conn.execute(
                    "select id from interview_sessions where id=%s",
                    (body["session_id"],),
                ).fetchall(),
                conn.execute(
                    "select name from storage.objects where name='synthetic-object'"
                ).fetchall(),
            )
        finally:
            conn.rollback()
            conn.close()

    assert all(visible())
    HostedCoordination(u["subscription"]).prepare_deletion(u["actor"], str(uuid4()))
    assert visible() == ([], [])
    # Physical Auth deletion and immutable history remain restricted, not weakened.
    import psycopg

    conn = u["connect"]("catalog_test_owner")
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("delete from auth.users where id=%s", (u["account"],))
    finally:
        conn.rollback()
        conn.close()


def test_shared_handoff_workers_replay_conflict_and_deletion(integration):
    from cryptography.fernet import Fernet

    u = integration
    key = Fernet.generate_key().decode()
    first, second = SharedHandoff(u["subscription"], key), SharedHandoff(
        u["subscription"], key
    )
    state = "synthetic-state-123456789"
    code = first.create(u["actor"], state, "synthetic-refresh")
    stored = u["db"].rows("select ciphertext from subscription_auth_handoffs")
    assert all(
        "synthetic-refresh" not in row["ciphertext"]
        and u["actor"]._bearer not in row["ciphertext"]
        for row in stored
    )
    barrier = threading.Barrier(2)

    def exchange(worker):
        barrier.wait()
        try:
            return worker.exchange(code, state)
        except CatalogStoreError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(exchange, [first, second]))
    assert sum(row is not None for row in results) == 1
    assert next(row for row in results if row)["access_token"] == u["actor"]._bearer
    with pytest.raises(CatalogStoreError):
        first.exchange(code, state)
    # Revocation/deletion removes outstanding handoffs; retained credentials never replay.
    with pytest.raises(CatalogStoreError) as limited:
        first.create(u["actor"], state, "synthetic-refresh")
    assert limited.value.code == ErrorCode.CONFLICT
    u["db"].run(
        f"update subscription_handoff_limits set last_created_at=clock_timestamp()-interval '6 seconds' where account_id='{u['account']}'"
    )
    code = first.create(u["actor"], state, "synthetic-refresh")
    HostedCoordination(u["subscription"]).prepare_deletion(u["actor"], str(uuid4()))
    with pytest.raises(CatalogStoreError):
        second.exchange(code, state)


def test_relay_frame_two_workers_fencing_and_payloads(integration, monkeypatch):
    u = integration
    body, _ = manual_case(u, monkeypatch)
    row = u["subscription"].auto(
        u["actor"], "start", {"run_id": str(uuid4()), "request_id": str(uuid4())}
    )
    lease = SimpleNamespace(actor=u["actor"], row=row, source="both")
    first, second = HostedCoordination(u["subscription"]), HostedCoordination(
        u["subscription"]
    )
    barrier = threading.Barrier(2)

    def frame(worker):
        barrier.wait()
        return worker.frame(lease, body["session_id"], 1, bytes(3200))

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(frame, [first, second]))
    assert sorted(results) == [False, True]
    with pytest.raises(CatalogStoreError) as conflict:
        second.frame(lease, body["session_id"], 1, bytes([1]) * 3200)
    assert conflict.value.code == ErrorCode.IDENTITY_CONFLICT
    with pytest.raises(CatalogStoreError):
        second.frame(lease, body["session_id"], 3, bytes(3200))
    with pytest.raises(CatalogStoreError):
        second.frame(lease, body["session_id"], 2, bytes(6402))
    alien = SimpleNamespace(actor=actor(str(uuid4())), row=row, source="both")
    with pytest.raises(CatalogStoreError):
        second.frame(alien, body["session_id"], 2, bytes(3200))
    u["subscription"].auto(
        u["actor"],
        "stop",
        {k: row[k] for k in ("run_id", "owner_token", "fence")} | {"sequence": 1},
    )
    with pytest.raises(CatalogStoreError):
        second.frame(lease, body["session_id"], 2, bytes(3200))


@pytest.mark.parametrize("source", ["microphone", "system", "both"])
def test_actual_hosted_websocket_pcm_stop_and_default_closed(
    integration, monkeypatch, source
):
    from app.config import settings
    from test_grpc_computer_lifecycle import configure

    u = integration
    body, calls = manual_case(u, monkeypatch)

    class NoServerDevice:
        def __init__(self):
            raise AssertionError("Hosted relay must never open a server audio device")

    sockets = configure(monkeypatch, NoServerDevice)
    for flag in (
        "HOSTED_AUDIO_ENABLED",
        "HOSTED_COMMERCIAL_MODE",
        "ENABLE_SESSION_ANSWER_MODELS",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ORIGINS", "https://synthetic.invalid")
    start = {
        "stream_id": str(uuid4()),
        "session_id": body["session_id"],
        "source": source,
    }
    with u["client"].websocket_connect(
        "/api/account/audio/stream",
        headers={**headers(u["account"]), "origin": "https://synthetic.invalid"},
    ) as ws:
        ws.send_json(start)
        while "ready" not in ws.receive_json():
            pass
        assert len(sockets) == 1
        ws.send_bytes((1).to_bytes(8, "big") + bytes(3200))
        while True:
            event = ws.receive_json()
            if event.get("status", {}).get("code") == "audio_chunk_received":
                break
        assert sockets[0].sent == [bytes(3200)]
        ws.send_bytes((1).to_bytes(8, "big") + bytes(3200))
        ws.send_text("ping")
        while "pong" not in ws.receive_json():
            pass
        assert sockets[0].sent == [bytes(3200)]
        ws.send_text("stop")
        while True:
            event = ws.receive_json()
            if event.get("status", {}).get("code") in (
                "ended",
                "system_cleanup_pending",
            ):
                break
    assert not calls
    assert u["db"].rows(
        f"select active from subscription_auto_runs where run_id='{start['stream_id']}'"
    ) == [{"active": False}]
    assert u["subscription"].current(u["actor"])["usage"]


def test_hosted_two_workers_revocation_and_reconnect(integration, monkeypatch):
    from app.commercial.boundary import CommercialBoundaryMiddleware
    from app.commercial.hosted_audio import router
    from app.commercial.subscription_database import SubscriptionDatabase
    from app.config import settings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_grpc_computer_lifecycle import configure

    u = integration
    body, calls = manual_case(u, monkeypatch)

    class NoDevice:
        def __init__(self):
            raise AssertionError("No hosted native capture")

    sockets = configure(monkeypatch, NoDevice)
    for flag in (
        "HOSTED_AUDIO_ENABLED",
        "ENABLE_SESSION_ANSWER_MODELS",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ORIGINS", "https://synthetic.invalid")
    runtime = SubscriptionDatabase(
        "true",
        f"host=127.0.0.1 port={u['db'].port} dbname=postgres user=usage_executor sslmode=disable",
    )
    runtime.start()
    assert runtime._pool is not None
    app = FastAPI()
    app.state.subscriptions = runtime
    app.add_middleware(CommercialBoundaryMiddleware)
    app.include_router(router)
    second = TestClient(app)
    h = {**headers(u["account"]), "origin": "https://synthetic.invalid"}
    document = {
        "stream_id": str(uuid4()),
        "session_id": body["session_id"],
        "source": "both",
    }

    def until(ws, field):
        for _ in range(30):
            event = ws.receive_json()
            if field in event:
                return event
            assert "error" not in event, event
        raise AssertionError("Required event absent")

    try:
        with u["client"].websocket_connect(
            "/api/account/audio/stream", headers=h
        ) as ws:
            ws.send_json(document)
            until(ws, "ready")
            with second.websocket_connect(
                "/api/account/audio/stream", headers=h
            ) as other:
                other.send_json({**document, "stream_id": str(uuid4())})
                error = until(other, "error")
                assert error["error"]["code"] == "subscription_auto_busy"
            assert len(sockets) == 1
            # Worker2 prepares deletion while worker1 is live. Next PCM is denied.
            HostedCoordination(runtime.service()).prepare_deletion(
                u["actor"], str(uuid4())
            )
            ws.send_bytes((1).to_bytes(8, "big") + bytes(3200))
            error = until(ws, "error")
            assert error["error"]["code"] == "subscription_denied"
            assert not sockets[0].sent and not calls
        with second.websocket_connect("/api/account/audio/stream", headers=h) as other:
            other.send_json(document)
            error = until(other, "error")
            assert error["error"]["code"] in (
                "subscription_relay_unavailable",
                "subscription_denied",
            )
        assert u["db"].rows(
            f"select count(*) n from subscription_auto_runs where account_id='{u['account']}'"
        ) == [{"n": 1}]
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "case_name",
    [
        "off",
        "origin",
        "forged",
        "foreign",
        "oversize",
        "sequence",
        "query",
        "alias",
        "non_object",
    ],
)
def test_hosted_untrusted_ingress_never_forwards(integration, monkeypatch, case_name):
    from app.config import settings
    from starlette.websockets import WebSocketDisconnect
    from test_grpc_computer_lifecycle import configure

    u = integration
    body, calls = manual_case(u, monkeypatch)

    class NoDevice:
        def __init__(self):
            raise AssertionError("No native hosted device")

    sockets = configure(monkeypatch, NoDevice)
    for flag in (
        "HOSTED_AUDIO_ENABLED",
        "ENABLE_SESSION_ANSWER_MODELS",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ORIGINS", "https://synthetic.invalid")
    h = {**headers(u["account"]), "origin": "https://synthetic.invalid"}
    path = "/api/account/audio/stream"
    doc = {
        "stream_id": str(uuid4()),
        "session_id": body["session_id"],
        "source": "microphone",
    }
    if case_name == "off":
        monkeypatch.setattr(settings, "HOSTED_AUDIO_ENABLED", False)
    if case_name == "origin":
        h["origin"] = "https://untrusted.invalid"
    if case_name == "forged":
        h["Authorization"] = "Bearer forged"
    if case_name == "foreign":
        doc["session_id"] = str(uuid4())
    if case_name == "query":
        path += "?bearer=forged"
    if case_name == "alias":
        path += "/"
    try:
        with u["client"].websocket_connect(path, headers=h) as ws:
            ws.send_json([] if case_name == "non_object" else doc)
            for _ in range(15):
                event = ws.receive_json()
                if "error" in event:
                    break
                if "ready" in event:
                    assert case_name in ("oversize", "sequence")
                    ws.send_bytes(
                        (2 if case_name == "sequence" else 1).to_bytes(8, "big")
                        + bytes(6402 if case_name == "oversize" else 3200)
                    )
            else:
                raise AssertionError("Missing terminal rejection")
    except WebSocketDisconnect:
        pass
    assert not calls and all(not socket.sent for socket in sockets)


def test_hosted_shared_handoff_http_contract(integration, monkeypatch):
    from app.config import settings
    from cryptography.fernet import Fernet

    u = integration
    manual_case(u, monkeypatch)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ENABLED", True)
    monkeypatch.setattr(
        settings, "DESKTOP_HANDOFF_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    payload = {
        "state": "synthetic-desktop-state-1234",
        "refresh_token": "synthetic-refresh",
    }
    response = u["client"].post(
        "/api/auth/desktop-handoff", headers=headers(u["account"]), json=payload
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    exchange = {
        "handoff_code": response.json()["handoff_code"],
        "state": payload["state"],
    }
    wrong = u["client"].post(
        "/api/auth/desktop-handoff/exchange",
        json={**exchange, "state": "another-state-1234567"},
    )
    assert wrong.status_code == 404
    response = u["client"].post("/api/auth/desktop-handoff/exchange", json=exchange)
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert set(response.json()) == {"access_token", "refresh_token"}
    assert (
        u["client"]
        .post("/api/auth/desktop-handoff/exchange", json=exchange)
        .status_code
        == 404
    )
    assert (
        u["client"]
        .post("/api/auth/desktop-handoff", headers=headers(u["account"]), json=payload)
        .status_code
        == 429
    )
    monkeypatch.setattr(settings, "DESKTOP_HANDOFF_ENCRYPTION_KEY", "")
    assert (
        u["client"]
        .post("/api/auth/desktop-handoff/exchange", json=exchange)
        .status_code
        == 503
    )


def test_deletion_lost_commit_and_concurrent_requests(integration):
    from app.commercial.subscription_service import SubscriptionService

    u = integration
    key = str(uuid4())

    class LostCommit:
        def __init__(self):
            self.conn = u["connect"]()

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            self.conn.commit()
            raise OSError("synthetic response loss")

    broken = HostedCoordination(SubscriptionService(LostCommit))
    with pytest.raises(CatalogStoreError) as uncertain:
        broken.prepare_deletion(u["actor"], key)
    assert uncertain.value.code == ErrorCode.UNCERTAIN
    gate = threading.Barrier(2)

    def retry(_):
        gate.wait()
        return HostedCoordination(u["subscription"]).prepare_deletion(u["actor"], key)

    with ThreadPoolExecutor(2) as pool:
        rows = list(pool.map(retry, range(2)))
    assert rows[0] == rows[1] and rows[0]["phase"] == "policy_pending"
    assert u["db"].rows(
        f"select count(*) n from usage_events where account_id='{u['account']}' and event='privacy.prepare'"
    ) == [{"n": 1}]


def test_actual_two_process_relay_worker_crash_and_recovery(integration, monkeypatch):
    import asyncio
    import os
    import socket
    import subprocess
    import sys
    from pathlib import Path

    import websockets
    from test_draft_service_native import KEY

    u = integration
    body, _ = manual_case(u, monkeypatch)
    workers = []

    def spawn():
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        # Synthetic-only process config; never load normal .env in child fixture.
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            in (
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "PYTHONPATH",
                "PYTHONUTF8",
            )
        }
        import tempfile

        env["PYTHONPATH"] = str(Path(tempfile.gettempdir()) / "c113c-db-driver")
        worker = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("hosted_subscription_worker.py")),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        workers.append(worker)
        worker.stdin.write(
            json.dumps(
                {
                    "host": "127.0.0.1",
                    "http_port": port,
                    "pg_port": u["db"].port,
                    "jwt_key": KEY,
                }
            )
            + "\n"
        )
        worker.stdin.flush()
        return worker, port

    async def ready(worker):
        line = await asyncio.wait_for(asyncio.to_thread(worker.stdout.readline), 30)
        if not line and worker.poll() is not None:
            diagnostic = worker.stderr.read()
            missing = [
                item
                for item in diagnostic.splitlines()
                if item.startswith("ModuleNotFoundError:")
            ]
            assert False, "Isolated worker startup: " + (
                ";".join(missing) or "failed; raw details suppressed"
            )
        assert (
            line.strip() == '{"ready": true}'
        ), "Isolated worker failed startup; inspect safe fixture configuration"

    async def exercise():
        a, port_a = spawn()
        b, port_b = spawn()
        await asyncio.gather(ready(a), ready(b))
        h = headers(u["account"])

        async def start(port, run):
            ws = await websockets.connect(
                f"ws://127.0.0.1:{port}/api/account/audio/stream",
                origin="https://synthetic.invalid",
                additional_headers=h,
                max_size=16384,
                max_queue=8,
            )
            await ws.send(
                json.dumps(
                    {
                        "stream_id": run,
                        "session_id": body["session_id"],
                        "source": "both",
                    }
                )
            )
            return ws

        async def until(ws, field):
            for _ in range(30):
                event = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if field in event:
                    return event
                assert "error" not in event, event
            raise AssertionError("Missing required relay event")

        run = str(uuid4())
        first = await start(port_a, run)
        try:
            await until(first, "ready")
            duplicate = await start(port_b, run)
            try:
                assert (await until(duplicate, "error"))["error"][
                    "code"
                ] == "subscription_relay_replay"
            finally:
                await duplicate.close()
            # Losing identical-start replay must not stop the original owner.
            await first.send((1).to_bytes(8, "big") + bytes(3200))
            while True:
                event = json.loads(await asyncio.wait_for(first.recv(), 5))
                if event.get("status", {}).get("code") == "audio_chunk_received":
                    break
            blocked = await start(port_b, str(uuid4()))
            try:
                assert (await until(blocked, "error"))["error"][
                    "code"
                ] == "subscription_auto_busy"
            finally:
                await blocked.close()
            a.kill()
            await asyncio.to_thread(a.wait, 5)

            # Real process death cannot release its capability; authorization is
            # still bounded by the existing SQL deadline, never a client timer.
            async def expired():
                while u["db"].rows(
                    f"select 1 from usage_operations where resource_id='{run}' and lease_until>clock_timestamp()"
                ):
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(expired(), 20)
            recovered = await start(port_b, str(uuid4()))
            try:
                await until(recovered, "ready")
                await recovered.send((1).to_bytes(8, "big") + bytes(3200))
                while True:
                    event = json.loads(await asyncio.wait_for(recovered.recv(), 5))
                    if event.get("status", {}).get("code") == "audio_chunk_received":
                        break
                await recovered.send("stop")
                while True:
                    event = json.loads(await asyncio.wait_for(recovered.recv(), 5))
                    if event.get("status", {}).get("code") in (
                        "ended",
                        "system_cleanup_pending",
                    ):
                        break
            finally:
                await recovered.close()
            old = await start(port_b, run)
            try:
                assert (await until(old, "error"))["error"][
                    "code"
                ] == "subscription_relay_replay"
            finally:
                await old.close()
        finally:
            await first.close()

    try:
        asyncio.run(exercise())
        assert not u["db"].rows(
            f"select 1 from subscription_auto_runs where account_id='{u['account']}' and active"
        )
        assert not u["db"].rows(
            f"select 1 from usage_operations where resource_id in(select run_id from subscription_auto_runs where account_id='{u['account']}') and authorized_at+charged*interval '1 microsecond'>lease_until"
        )
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
            worker.wait(timeout=5)


def test_hosted_near_exhaustion_tail_is_not_forfeited_or_charged_while_stopped(
    integration, monkeypatch
):
    import asyncio
    from datetime import datetime, timezone

    from app.commercial.subscription_auto import INSTANT
    from app.config import settings
    from test_grpc_computer_lifecycle import configure
    from test_usage_store_native import reserve, step

    u = integration
    body, calls = manual_case(u, monkeypatch)
    prior = reserve(u, units=599, meter="auto.authorized_running")
    step(u, prior, "dispatch")
    step(u, prior, "checkpoint", result_ref=str(uuid4()))
    step(u, prior, "settle", charged=599, policy_version="synthetic.usage.v1")

    class NoDevice:
        def __init__(self):
            raise AssertionError("No server capture")

    sockets = configure(monkeypatch, NoDevice)
    for flag in (
        "HOSTED_AUDIO_ENABLED",
        "ENABLE_SESSION_ANSWER_MODELS",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "HOSTED_AUDIO_ORIGINS", "https://synthetic.invalid")
    h = {**headers(u["account"]), "origin": "https://synthetic.invalid"}

    def start(ws):
        ws.send_json(
            {
                "stream_id": str(uuid4()),
                "session_id": body["session_id"],
                "source": "both",
            }
        )

    with u["client"].websocket_connect("/api/account/audio/stream", headers=h) as ws:
        start(ws)
        for _ in range(20):
            event = ws.receive_json()
            if "ready" in event:
                break
            assert "error" not in event, event
        ws.send_bytes((1).to_bytes(8, "big") + bytes(3200))
        for _ in range(20):
            event = ws.receive_json()
            if "error" in event:
                assert event["error"]["code"] == "subscription_auto_expired"
                break
        else:
            raise AssertionError("Bounded authorization must expire")

    def balance():
        return next(
            row
            for row in u["subscription"].current(u["actor"])["usage"]
            if row["meter"] == "auto.authorized_running"
        )

    before = balance()
    assert 599000000 <= int(before["used"]) <= 600000000 and before["reserved"] == "0"
    u["db"].rows("select pg_sleep(.1)")  # Stopped interval: no active authorization.
    assert balance()["used"] == before["used"]
    assert not calls

    async def finish_authorized_silence_only():
        # Explicit isolated silent authorization held ACTIVE until its SQL
        # deadline. No rounding, stopped-time charge or counter alteration.
        try:
            tail = u["subscription"].auto(
                u["actor"],
                "start",
                {"run_id": str(uuid4()), "request_id": str(uuid4())},
            )
        except CatalogStoreError as error:
            assert error.code == ErrorCode.EXHAUSTED
            return
        await asyncio.sleep(
            max(
                0,
                (
                    INSTANT.validate_python(tail["authorized_until"])
                    - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        )
        assert not u["subscription"].auto(
            u["actor"], "status", {"run_id": tail["run_id"]}
        )["active"]

    asyncio.run(finish_authorized_silence_only())
    providers_before = len(sockets)
    with u["client"].websocket_connect("/api/account/audio/stream", headers=h) as ws:
        start(ws)
        for _ in range(20):
            event = ws.receive_json()
            if "error" in event:
                assert event["error"]["code"] == "subscription_auto_exhausted"
                break
            assert "ready" not in event
        else:
            raise AssertionError("Exhaustion must deny, without retry loop")
    assert len(sockets) == providers_before and balance()["used"] == "600000000"
