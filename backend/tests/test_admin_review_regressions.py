"""Review regressions with synthetic state; native SQL/engine coverage lives in the rehearsal."""

import asyncio
import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.admin_dispatch import CancellationDispatcher
from app.admin_restore import AdministrationRestore
from app.admin_telemetry import Attempt, context, measured_async_call, measured_call
from app.privacy_checkpoint import LocalCheckpointStore
from app.privacy_content import ContentBlocked
from app.privacy_restore import RestoreJournal


@pytest.mark.parametrize("nested", ["text", [], 7, None])
def test_usage_accepts_nonobject_nested_provider_response(nested):
    rows = []
    token = context.set(("subject", "request", rows.append))
    try:
        response = {"response": nested, "x_groq": nested}
        assert measured_call(lambda: response, telemetry_provider="ollama") is response
    finally:
        context.reset(token)
    assert rows[0]["outcome"] == "completed"


def test_async_telemetry_sink_does_not_block_loop():
    async def scenario():
        loop_thread = threading.get_ident()
        started, release = threading.Event(), threading.Event()
        threads = []

        def record(document):
            threads.append(threading.get_ident())
            started.set()
            assert release.wait(3)

        async def provider():
            return {"response": "answer"}

        token = context.set(("subject", "request", record))
        try:
            task = asyncio.create_task(
                measured_async_call(provider, telemetry_provider="ollama")
            )
            assert await asyncio.to_thread(started.wait, 2)
            assert not task.done()
            release.set()
            assert await task == {"response": "answer"}
            assert threads == [threads[0]] and threads[0] != loop_thread
        finally:
            release.set()
            context.reset(token)

    asyncio.run(scenario())


def test_async_attempt_failure_preserves_original_exception():
    async def scenario():
        rows = []
        token = context.set(("subject", "request", rows.append))
        try:
            with pytest.raises(ValueError, match="provider failed"):
                async with Attempt("synthetic", "model"):
                    raise ValueError("provider failed")
        finally:
            context.reset(token)
        assert rows[0]["outcome"] == "failed"

    asyncio.run(scenario())


def test_async_telemetry_does_not_wait_for_default_executor():
    async def scenario():
        started, release = threading.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        old = loop._default_executor
        pool = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(pool)
        try:
            blocked = loop.run_in_executor(
                pool, lambda: (started.set(), release.wait(5))
            )
            assert started.wait(2)
            rows = []
            token = context.set(("subject", "request", rows.append))
            try:
                await asyncio.wait_for(
                    measured_async_call(
                        lambda: asyncio.sleep(0), telemetry_provider="ollama"
                    ),
                    2,
                )
            finally:
                context.reset(token)
            assert len(rows) == 1
        finally:
            release.set()
            await blocked
            loop.set_default_executor(old or ThreadPoolExecutor(max_workers=1))
            pool.shutdown()

    asyncio.run(scenario())


def test_async_attempt_without_owner_skips_executor(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            loop, "run_in_executor", lambda *_: pytest.fail("unowned telemetry queued")
        )
        await measured_async_call(lambda: asyncio.sleep(0), telemetry_provider="ollama")

    asyncio.run(scenario())


@pytest.mark.parametrize("dispatch", [None, {}, {"allowed": False}])
def test_disabled_cancellation_dispatch_never_calls_provider(dispatch):
    worker = CancellationDispatcher(None, SimpleNamespace(enabled=True))
    calls = []

    def call(action, document):
        calls.append(action)
        return {"id": "command", "lease": "lease"} if action == "claim" else dispatch

    worker.call = call
    assert worker.run_one()
    assert calls == ["claim", "dispatch"]


def test_cancellation_recovery_reestablishes_durable_intent():
    calls = []
    billing = SimpleNamespace(
        enabled=True,
        _cancel_account=lambda account, operation: calls.append((account, operation))
        or {"provider_state": "cancelled"},
    )
    worker = CancellationDispatcher(None, billing)

    def call(action, document):
        if action == "claim":
            return {
                "id": "command",
                "lease": "lease",
                "account_id": "subject",
                "billing_id": "billing",
                "reconcile_only": True,
            }
        if action == "dispatch":
            return {"allowed": True}
        assert document["outcome"] == "confirmed"

    worker.call = call
    assert worker.run_one()
    assert calls == [("subject", "billing")]


def snapshot_fixture(tmp_path):
    key = secrets.token_bytes(32)
    store = LocalCheckpointStore(
        tmp_path / "checkpoint", tmp_path / "witness", key, str(uuid4()), str(uuid4())
    )
    journal = RestoreJournal(tmp_path / "journal", {"v1": key}, "v1")
    store.initialize(journal.initialize())
    with store.locked() as local:
        record = store.read(local)
        assert record["journal_id"] is None
        assert record["state_hash"] is None
        assert record["database_revision"] == 0
        assert record["source_sealed"] is False
    restore = AdministrationRestore(None, journal, store, str(uuid4()), str(uuid4()))
    return store, restore


def test_large_snapshots_rotate_without_event_or_lifetime_exhaustion(tmp_path):
    store, restore = snapshot_fixture(tmp_path)
    # 100,000 restrictions exceed both the per-event limit and the old lifetime cap.
    state = {
        "revision": 1,
        "restrictions": [
            {
                "subject": str(uuid4()),
                "restricted": True,
                "revision": 1,
                "changed_at": "2026-11-17T00:00:00+00:00",
            }
            for _ in range(100000)
        ],
        "memberships": [],
        "spent_campaigns": [],
    }
    assert len(json.dumps(state).encode()) > 1024 * 1024
    for revision in range(1, 4):
        state["revision"] = revision
        with store.locked() as local:
            record = store.read(local)
            restore._publish(local, record, state, ready=True)
            assert restore._state(record) == state
        restore.prune_acknowledged()
        assert len(list(tmp_path.glob("journal.*.snapshot"))) <= 2


def test_snapshot_ack_loss_restart_and_tamper_fail_closed(tmp_path):
    store, restore = snapshot_fixture(tmp_path)
    state = {"revision": 1, "restrictions": []}
    with store.locked() as local:
        restore._publish(local, store.read(local), state, ready=True)
    with pytest.raises(ContentBlocked):
        with store.locked() as local:
            restore._publish(
                local, store.read(local), dict(state, revision=2), ready=True
            )
            raise RuntimeError("crash before witness commit")
    with store.locked() as local:
        record = store.read(local)
        assert restore._state(record) == state
        restore._publish(local, record, dict(state, revision=2), ready=True)
    with store.locked() as local:
        record = store.read(local)
        path = restore._journal(record).path
        path.write_bytes(path.read_bytes()[:-1])
        with pytest.raises(ContentBlocked):
            restore._state(record)


def test_acknowledged_snapshot_pruning_recovers_after_interrupted_housekeeping(
    tmp_path,
):
    store, restore = snapshot_fixture(tmp_path)
    for revision in range(1, 4):
        with store.locked() as local:
            restore._publish(
                local,
                store.read(local),
                {"revision": revision, "restrictions": []},
                ready=True,
            )
    assert len(list(tmp_path.glob("journal.*.snapshot"))) == 3
    restore.prune_acknowledged()
    assert len(list(tmp_path.glob("journal.*.snapshot"))) == 1
    with store.locked() as local:
        assert restore._state(store.read(local))["revision"] == 3


def test_billing_authorization_uses_worker_thread(monkeypatch):
    from app.commercial import billing_admin

    main = threading.get_ident()
    threads = []

    def verify(request):
        threads.append(threading.get_ident())
        return "actor"

    monkeypatch.setattr(billing_admin, "verified_actor", verify)
    request = SimpleNamespace(
        method="GET",
        app=SimpleNamespace(
            state=SimpleNamespace(billing_admin=SimpleNamespace(call=lambda *args: {}))
        ),
    )
    asyncio.run(billing_admin.billing_admin(request, "access"))
    assert threads and threads[0] != main


def test_assembly_returned_error_is_failed_attempt(monkeypatch):
    from app.services.assemblyai_stt_service import AssemblyAISTTService
    from app.services.stt_provider import STTServiceError

    service = AssemblyAISTTService()
    sdk = SimpleNamespace(
        TranscriptionConfig=lambda **kwargs: None,
        SpeechModel=SimpleNamespace(best="best"),
        Transcriber=lambda: SimpleNamespace(
            transcribe=lambda *args, **kwargs: SimpleNamespace(
                status="error", error="synthetic failure"
            )
        ),
        TranscriptStatus=SimpleNamespace(error="error"),
    )
    monkeypatch.setattr(service, "_get_sdk", lambda: sdk)
    rows = []
    token = context.set(("subject", "request", rows.append))
    try:
        with pytest.raises(STTServiceError):
            service.transcribe(audio_path="synthetic-only")
    finally:
        context.reset(token)
    assert rows[0]["outcome"] == "failed"
