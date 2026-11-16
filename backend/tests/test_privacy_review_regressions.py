"""CodeRabbit privacy regressions: safe API boundaries and real native SQL scopes."""

# ruff: noqa: F401,F811 -- imported native fixtures
import threading
import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.auth.supabase_auth import CurrentUser, SupabaseAuthError
from app.commercial.boundary import CommercialBoundaryMiddleware
from app.config import settings
from app.privacy_checkpoint import RestoreReadinessMiddleware
from app.privacy_content import ContentBlocked
from app.privacy_restore import RestoreJournal


SUPPORTED_AUTH_PACKAGE = True


def test_hosted_boundary_allows_privacy_sessions(monkeypatch):
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    app = FastAPI()
    app.add_middleware(CommercialBoundaryMiddleware)

    @app.post("/api/privacy/content/sessions")
    def sessions():
        return {"sessions": []}

    response = TestClient(app).post("/api/privacy/content/sessions", json={})
    assert response.status_code == 200
    assert response.json() == {"sessions": []}


@pytest.mark.parametrize("runtime_enabled,expected_calls", [("true", 0), ("false", 1)])
def test_revocation_consumer_composition(monkeypatch, runtime_enabled, expected_calls):
    from app.commercial.subscription_database import SubscriptionDatabase
    from app import privacy_revocation

    calls = []
    monkeypatch.setattr(settings, "C15_RUNTIME_ENABLED", runtime_enabled)
    monkeypatch.setattr(
        privacy_revocation, "configured_worker", lambda *a, **k: calls.append(k)
    )
    db = SubscriptionDatabase()
    db._stop.set()
    db._sweep()
    assert len(calls) == expected_calls


@pytest.mark.parametrize(
    "failure,status", [("auth", 401), ("presence", 403), ("outage", 503)]
)
def test_content_auth_and_presence_are_not_outages(monkeypatch, failure, status):
    from app import privacy_content_api as api

    app = FastAPI()
    app.include_router(api.router)
    user = CurrentUser(
        user_id=str(uuid4()),
        email="synthetic@example.invalid",
        role="authenticated",
        claims={},
    )

    def verify(_token):
        if failure == "auth":
            raise SupabaseAuthError("invalid")
        return user

    def proof(*args, **kwargs):
        if failure == "presence":
            raise HTTPException(403, detail={"code": "reauthentication_required"})
        raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")

    monkeypatch.setattr(api, "verify_supabase_token", verify)
    app.state.privacy_content = SimpleNamespace(proof=proof)
    response = TestClient(app).post(
        "/api/privacy/content/begin",
        json={"request_id": str(uuid4())},
        headers={"Authorization": "Bearer synthetic"},
    )
    assert response.status_code == status
    assert "SYNTHETIC_PRIVATE_ERROR" not in response.text


def test_readiness_io_is_off_event_loop_and_fails_closed():
    observed = []
    sent = []
    loop_thread = threading.get_ident()

    def ready():
        observed.append(threading.get_ident())
        raise OSError("synthetic unavailable evidence")

    async def unused(*args):
        raise AssertionError("quarantined application must not be served")

    async def send(message):
        sent.append(message)

    gate = RestoreReadinessMiddleware(
        unused, required=True, coordinator=SimpleNamespace(ready=ready)
    )
    asyncio.run(gate({"type": "http", "path": "/", "headers": []}, unused, send))
    assert sent[0]["status"] == 503
    assert observed and all(t != loop_thread for t in observed)


def test_journal_size_rejection_preserves_previous_evidence(tmp_path):
    journal = RestoreJournal(
        tmp_path / "journal", {"synthetic": b"x" * 32}, "synthetic"
    )
    head = journal.initialize()
    before = journal.path.read_bytes()
    journal.MAX_BYTES = len(before) + 8
    with pytest.raises(ContentBlocked, match="restore_evidence_size"):
        journal.append(
            {"event_id": "too-large", "kind": "synthetic", "payload": "x" * 100}, head
        )
    assert journal.path.read_bytes() == before
    assert journal.read(head)[0]["kind"] == "genesis"


def test_required_restore_coordinator_is_wired_to_grpc(monkeypatch):
    from app import main, grpc_server
    from app.cloud import interview_sessions
    from app.services import answer_diagram_service

    ready = {"value": True}
    coordinator = SimpleNamespace(ready=lambda: ready["value"])
    captured = {}
    app = FastAPI()
    app.state.restore_coordinator = coordinator

    def database(*args, **kwargs):
        return SimpleNamespace(
            start=lambda: None,
            close=lambda: None,
            _service=None,
            billing=None,
            admin=None,
            notifications=None,
        )

    async def no_op(*args, **kwargs):
        pass

    async def start_server(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop=no_op), 0

    monkeypatch.setattr(settings, "C15_RUNTIME_ENABLED", "false")
    monkeypatch.setattr(settings, "C15_RESTORE_BOOT_REQUIRED", "true")
    monkeypatch.setattr(settings, "GRPC_REALTIME_ENABLED", True)
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "false")
    monkeypatch.setattr(main, "CatalogDatabase", database)
    monkeypatch.setattr(main, "SubscriptionDatabase", database)
    monkeypatch.setattr(main, "BillingDatabase", database)
    monkeypatch.setattr(
        interview_sessions, "validate_session_model_dev_activation", lambda: None
    )
    monkeypatch.setattr(grpc_server, "start_server", start_server)
    monkeypatch.setattr(grpc_server, "shutdown_cleanup", no_op)
    monkeypatch.setattr(answer_diagram_service, "shutdown_diagrams", no_op)

    async def exercise():
        async with main.lifespan(app):
            assert captured["readiness"] is coordinator.ready
            ready["value"] = False
            assert captured["readiness"]() is False

    asyncio.run(exercise())


def test_rehearsal_process_timeout_kills_and_reaps():
    import importlib.util
    import subprocess

    source = Path(__file__).parents[2] / "scripts/c15_actual_engines.py"
    spec = importlib.util.spec_from_file_location("c15_review_engines", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Process:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout):
            calls.append("wait")
            if "kill" not in calls:
                raise subprocess.TimeoutExpired("synthetic", timeout)

        def kill(self):
            calls.append("kill")

    module.stop_local_process(Process(), 1)
    assert calls == ["terminate", "wait", "kill", "wait"]


def test_rehearsal_cleanup_failure_is_not_success(monkeypatch):
    import importlib.util

    source = Path(__file__).parents[2] / "scripts/c15_actual_engines.py"
    spec = importlib.util.spec_from_file_location("c15_review_cleanup", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports = {}
    rehearsal = object.__new__(module.Rehearsal)
    rehearsal.name = "synthetic-owned-stack"
    rehearsal.created = ["synthetic-owned-container"]
    rehearsal.volumes = []
    rehearsal.http = SimpleNamespace(close=lambda: None)
    rehearsal.save = lambda name, document: reports.update({name: document})

    def docker(*args, **kwargs):
        if args[0] == "inspect":
            return SimpleNamespace(returncode=0, stdout=rehearsal.name)
        if args[0] == "rm":
            return SimpleNamespace(returncode=1, stdout="")
        if args[0] == "ps":
            return SimpleNamespace(returncode=0, stdout="synthetic-owned-container")
        return SimpleNamespace(
            returncode=1 if args[:2] == ("network", "inspect") else 0, stdout=""
        )

    monkeypatch.setattr(module, "docker", docker)
    with pytest.raises(RuntimeError, match="owned_rehearsal_cleanup_incomplete"):
        rehearsal.cleanup()
    assert reports["cleanup.json"]["failures"] == ["synthetic-owned-container"]
    assert reports["cleanup.json"]["remaining_containers"] == [
        "synthetic-owned-container"
    ]
