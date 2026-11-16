"""Checkpoint acceptance: real disposable PostgreSQL, fake Auth/Storage only."""

# ruff: noqa: F401,F811 -- pytest fixtures imported explicitly
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from app.privacy_checkpoint import (
    LocalCheckpointStore,
    RestoreCoordinator,
    RestoreReadinessMiddleware,
)
from app.privacy_content import ContentBlocked, ContentEngine
from app.privacy_restore import RestoreGate, RestoreJournal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_privacy_remaining_native import (
    Storage,
    accept,
    case,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    privacy,
    remaining,
    seed,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True

# Each restore case owns its entire cluster: accepted decisions from another
# test must never be discarded merely to make a fresh journal appear complete.
_original_database = database.__wrapped__
_original_f1 = f1_install.__wrapped__
_original_f2 = f2_install.__wrapped__
_original_install = install.__wrapped__


@pytest.fixture
def database(request):
    generator = _original_database(request)
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()
        # The offline fixture forbids socket.connect globally. Inspect OS
        # listeners instead; no network boundary or guard bypass is needed.
        if os.name == "nt":
            count = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"@(Get-NetTCPConnection -State Listen -LocalPort {int(db.port)} -ErrorAction SilentlyContinue).Count",
                ],
                text=True,
            ).strip()
            closed = count == "0"
        elif Path("/proc/net/tcp").exists():
            closed = not any(
                int(line.split()[1].rsplit(":", 1)[1], 16) == db.port
                and line.split()[3] == "0A"
                for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6"))
                if table.exists()
                for line in table.read_text().splitlines()[1:]
            )
        else:
            tool = shutil.which("lsof")
            assert tool, "lsof required for POSIX listener verification"
            result = subprocess.run(
                [tool, "-nP", f"-iTCP:{int(db.port)}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                check=False,
            )
            closed = result.returncode == 1 and not result.stdout.strip()
        assert closed and not db.directory.exists()
        path = (
            Path(__file__).parents[2]
            / request.config.getoption("--c15-evidence-dir")
            / "owned-cluster-cleanup.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(
                json.dumps(
                    {
                        "case": request.node.name,
                        "directory": str(db.directory),
                        "port": db.port,
                        "removed": True,
                        "closed": True,
                    }
                )
                + "\n"
            )


@pytest.fixture(autouse=True)
def ephemeral_checkpoint_files(tmp_path):
    owned = tmp_path.resolve()
    assert owned.is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert owned.name.startswith("test_")
    yield
    # Only this fixture's freshly assigned pytest directory, never prior build
    # leftovers, journals, screenshots or another test's files.
    shutil.rmtree(owned)


@pytest.fixture
def f1_install(database):
    return _original_f1(database)


@pytest.fixture
def f2_install(database, f1_install):
    return _original_f2(database, f1_install)


@pytest.fixture
def install(database, f1_install, f2_install):
    return _original_install(database, f1_install, f2_install)


def setup(remaining, path):
    _u, e, *_ = remaining
    journal = RestoreJournal(path / "journal", {"v1": secrets.token_bytes(32)}, "v1")
    store = LocalCheckpointStore(
        path / "checkpoint.sqlite",
        path / "witness.sqlite",
        secrets.token_bytes(32),
        str(uuid4()),
        str(uuid4()),
    )
    store.initialize(journal.initialize())
    baseline = RestoreCoordinator(e, journal, store, str(uuid4()), str(uuid4()))
    baseline.seal_source()
    baseline.reconcile()
    return RestoreCoordinator(e, journal, store, baseline.generation, baseline.snapshot)


def test_empty_replay_restart_gate_and_unaffected_account(remaining, tmp_path):
    _u, e, *_ = remaining
    co = setup(remaining, tmp_path)
    assert not co.ready()
    co.reconcile()
    assert co.ready()
    restarted = RestoreCoordinator(e, co.journal, co.store, co.generation, co.snapshot)
    assert not restarted.ready()  # A restored DB flag is insufficient.
    restarted.reconcile()
    assert restarted.ready()
    app = FastAPI()
    app.add_middleware(RestoreReadinessMiddleware, required=True, coordinator=restarted)

    @app.get("/private")
    def private():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/private").status_code == 200
        with e.transaction() as c:
            c.execute("update privacy_restore_state set ready=false")
        assert client.get("/private").status_code == 503


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "tampered",
        "truncated",
        "wrong_environment",
        "wrong_dataset",
        "wrong_generation",
        "wrong_snapshot",
    ],
)
def test_invalid_evidence_never_releases_ready(remaining, tmp_path, damage):
    co = setup(remaining, tmp_path)
    if damage == "missing":
        co.journal.path.rename(tmp_path / "unavailable-journal")
    elif damage == "tampered":
        co.journal.path.write_bytes(b"tampered\n")
    elif damage == "truncated":
        co.journal.path.write_bytes(co.journal.path.read_bytes()[:-1])
    elif damage in ("wrong_environment", "wrong_dataset"):
        co.store = LocalCheckpointStore(
            co.store.path,
            co.store.witness,
            co.store.key,
            str(uuid4()) if damage == "wrong_environment" else co.store.environment,
            str(uuid4()) if damage == "wrong_dataset" else co.store.dataset,
        )
    else:
        if damage == "wrong_generation":
            co.generation = str(uuid4())
        else:
            co.snapshot = str(uuid4())
    with pytest.raises(ContentBlocked):
        co.reconcile()
    assert not co.ready()
    with co.engine.transaction() as c:
        assert not c.execute("select ready from privacy_restore_state").fetchone()[0]


def test_rollback_checkpoint_even_with_old_dataset_flag_is_rejected(
    remaining, tmp_path
):
    co = setup(remaining, tmp_path)
    old = co.store.path.read_bytes()
    gen, snapshot = str(uuid4()), str(uuid4())
    co.store.authorize_restore(1, gen, snapshot)
    co = RestoreCoordinator(co.engine, co.journal, co.store, gen, snapshot)
    co.reconcile()
    assert co.ready()
    # Deliberate fixture rollback: witness remains outside the restored inputs.
    co.store.path.write_bytes(old)
    assert not co.ready()
    with pytest.raises(ContentBlocked, match="checkpoint_rollback"):
        co.reconcile()


def test_generation_rotation_is_compare_and_swap(remaining, tmp_path):
    co = setup(remaining, tmp_path)
    co.reconcile()
    gen, snapshot = str(uuid4()), str(uuid4())
    co.store.authorize_restore(1, gen, snapshot)
    with pytest.raises(ContentBlocked):
        co.store.authorize_restore(1, str(uuid4()), str(uuid4()))
    assert not co.ready()
    replacement = RestoreCoordinator(co.engine, co.journal, co.store, gen, snapshot)
    replacement.reconcile()
    assert replacement.ready()


def test_concurrent_publication_and_new_decision_invalidate_ready(remaining, tmp_path):
    co = setup(remaining, tmp_path)
    co.reconcile()
    accept(remaining)
    assert not co.ready()
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(pool.map(lambda _: co.publish(), range(2)))
    assert versions == [2, 2]
    assert (
        len(co.journal.read(hashlib.sha256(co.journal.path.read_bytes()).hexdigest()))
        == 2
    )
    assert not co.ready()


def test_crash_after_journal_append_recovers_same_outbox(
    remaining, tmp_path, monkeypatch
):
    co = setup(remaining, tmp_path)
    accept(remaining)
    real = co.store.write

    def crash(*_):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(co.store, "write", crash)
    with pytest.raises(ContentBlocked):
        co.publish()
    assert not co.ready()
    monkeypatch.setattr(co.store, "write", real)
    assert co.publish() == 2
    assert co.publish() == 2


def test_missing_current_outbox_is_not_accepted_as_crash_tail(remaining, tmp_path):
    co = setup(remaining, tmp_path)
    with co.store.locked() as c:
        head = co.store.read(c)["head"]
    co.journal.append({"kind": "unknown", "event_id": str(uuid4())}, head)
    with pytest.raises(ContentBlocked, match="checkpoint_coverage"):
        co.publish()


def test_readiness_is_default_closed_without_operator_composition():
    app = FastAPI()
    app.add_middleware(RestoreReadinessMiddleware, required=True)

    @app.get("/health")
    def health():
        return {"ready": True}

    with TestClient(app) as client:
        assert client.get("/health?ready=true").json() == {
            "status": "restore_quarantined"
        }
        assert (
            client.post(
                "/api/privacy/restore/approve", json={"ready": True}
            ).status_code
            == 503
        )


@pytest.mark.parametrize("after_replay", [False, True])
def test_replay_crash_restart_is_not_ready(
    remaining, tmp_path, monkeypatch, after_replay
):
    co = setup(remaining, tmp_path)
    real = RestoreGate.apply

    def crash(self, *args):
        if after_replay:
            real(self, *args)
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(RestoreGate, "apply", crash)
    with pytest.raises(ContentBlocked, match="restore_reconciliation_failed"):
        co.reconcile()
    assert not co.ready()
    monkeypatch.setattr(RestoreGate, "apply", real)
    co.reconcile()
    assert co.ready()


def test_new_confirmation_during_replay_keeps_coverage_closed(
    remaining, tmp_path, monkeypatch
):
    co = setup(remaining, tmp_path)

    def late_decision():
        accept(remaining)
        return False

    monkeypatch.setattr(co.engine, "expire_one", late_decision)
    with pytest.raises(ContentBlocked, match="checkpoint_coverage"):
        co.reconcile()
    assert not co.ready()


def test_duplicate_coordinators_have_one_durable_binding(remaining, tmp_path):
    co = setup(remaining, tmp_path)

    def attempt(_):
        worker = RestoreCoordinator(
            co.engine, co.journal, co.store, co.generation, co.snapshot
        )
        try:
            worker.reconcile()
            return True
        except ContentBlocked:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, range(2)))
    # Conservative contention can quarantine; a clean retry must recover.
    co.reconcile()
    assert co.ready()
    with co.store.locked() as c:
        assert co.store.read(c)["generation"] == co.generation


def test_cold_snapshot_objects_exports_and_billing_barrier(remaining, tmp_path):
    u, e, storage, *_ = remaining
    _resume, _session, key = seed(remaining)
    export = e.request(u["account"], str(uuid4()))
    e.run_one()
    archived = dict(storage.items)
    co = setup(remaining, tmp_path)
    old_checkpoint = co.store.path.read_bytes()
    db = u["db"]
    clone = db.directory / "checkpoint-restore"
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
    accept(remaining)
    co.publish()
    co = RestoreCoordinator(e, co.journal, co.store, str(uuid4()), str(uuid4()))
    co.seal_source()
    current_checkpoint = co.store.path.read_bytes()
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
                str(db.directory / "checkpoint-restore.log"),
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

        restored_storage = Storage()
        restored_storage.items = archived
        restored = ContentEngine(connect, restored_storage, local_rehearsal=True)
        runner = RestoreCoordinator(
            restored, co.journal, co.store, co.generation, co.snapshot
        )
        co.store.path.write_bytes(old_checkpoint)
        with pytest.raises(ContentBlocked, match="checkpoint_rollback"):
            runner.reconcile()
        assert not runner.ready()
        co.store.path.write_bytes(current_checkpoint)
        # Existing cleanup conservatively blocks protected legacy payloads.
        # Never bypass that blocker just to release unaffected users early.
        try:
            runner.reconcile()
        except ContentBlocked as error:
            assert str(error) == "restore_cleanup_pending"
        with pytest.raises(ContentBlocked):
            restored.request(u["account"], str(uuid4()))
        with pytest.raises(ContentBlocked):
            restored.authorize(u["account"], export)
        assert ("resumes", key) not in restored_storage.items
        assert not any(bucket == "exports" for bucket, _ in restored_storage.items)
        with restored.transaction() as c:
            assert (
                c.execute("select count(*) from privacy_email_suppression").fetchone()[
                    0
                ]
                >= 1
            )
            assert (
                c.execute(
                    "select count(*) from privacy_followup_tasks where kind='billing_review'"
                ).fetchone()[0]
                >= 1
            )
            with pytest.raises(psycopg.Error):
                c.execute(
                    "insert into profiles(user_id,full_name) values(%s,'late')",
                    (u["account"],),
                )
    finally:
        if started:
            db.command("pg_ctl", ["-D", str(clone), "-m", "fast", "-w", "stop"])
