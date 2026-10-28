"""Actual HTTP/JWT/service/adapter/pool with restricted native SQL login.

Disposable owner installs fixtures; application connections are NEVER owner or
superuser. Local initdb trust authentication does not prove deployed passwords/TLS.
"""

import argparse
import copy
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import supabase_auth as auth
from app.commercial.boundary import CommercialBoundaryMiddleware
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_api import router
from app.commercial.draft_service import DraftService
from app.config import settings
from test_catalog_contract import document
from test_catalog_store_native import MANAGER, ORDINARY, literal
from test_draft_service_native import KEY, actor, counts
from test_draft_service_native import database as database


def headers(subject=MANAGER, **claims):
    return {"Authorization": "Bearer " + actor(subject, **claims)._bearer}


def path(raw):
    return "/api/admin/catalog/drafts/" + raw["draft_id"]


def private(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "authorization" in response.headers["vary"].lower()
    assert "catalog_test_owner" not in response.text
    assert KEY not in response.text


def create(client, raw, key=None, **kwargs):
    return client.post(
        "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts",
        json={"document": raw, "reason": "synthetic create"},
        headers={**headers(), "Idempotency-Key": key or str(uuid4()), **kwargs},
    )


@pytest.fixture
def case(database, monkeypatch):
    db = database
    # Only disposable infrastructure: expose the already accepted restricted
    # principal as a synthetic LOGIN, no admin/member/table/function broadening.
    db.run("alter role catalog_draft_executor login;")
    db.run(
        f"update subscription_admin_permissions set active=true,revision=revision+1,reason='synthetic reset' where subject_id={literal(MANAGER)};"
    )
    monkeypatch.setattr(
        auth,
        "get_auth_verification_config",
        lambda: auth.AuthVerificationConfig(
            "legacy_secret", KEY, "https://synthetic.invalid/auth/v1", "authenticated"
        ),
    )
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    monkeypatch.setattr(settings, "SESSION_ANSWER_MODELS_DEV_READY", False)
    monkeypatch.setattr(settings, "GRPC_REALTIME_ENABLED", False)
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_ENABLED", "false")
    monkeypatch.setattr(settings, "SUBSCRIPTIONS_DSN", "")
    monkeypatch.setattr(settings, "CATALOG_PUBLIC_ENABLED", "false")
    monkeypatch.setattr(settings, "CATALOG_PUBLIC_DSN", "")
    monkeypatch.setattr(settings, "CATALOG_DRAFTS_ENABLED", "true")
    monkeypatch.setattr(
        settings,
        "CATALOG_DRAFTS_DSN",
        f"host=127.0.0.1 port={db.port} dbname=postgres user=catalog_draft_executor sslmode=disable",
    )
    monkeypatch.setattr("whisper.load_model", lambda *a, **k: NS())
    from app.main import app

    raw = document()
    raw.update(draft_id=str(uuid4()), state="draft")
    raw["plan"] = dict(plan_id=str(uuid4()), code="synthetic-" + uuid4().hex)
    raw["terms"]["prices"][0]["price_id"] = str(uuid4())
    with TestClient(app) as client:
        assert isinstance(app.state.catalog_drafts.service(), DraftService)
        yield db, client, raw, app
    assert app.state.catalog_drafts._pool is None


@pytest.mark.parametrize(
    "credentials", [{}, {"Authorization": "Bearer invalid"}, headers(exp=0)]
)
def test_authentication_before_parsing(case, credentials):
    db, client, raw, app = case
    before = counts(db)
    response = client.post(
        "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts",
        content="invalid JSON",
        headers=credentials,
    )
    assert response.status_code == 401
    private(response)
    assert counts(db) == before


def test_authorized_roundtrip_and_preview_no_writes(case):
    db, client, raw, app = case
    raw["terms"] = {}  # valid incomplete draft
    response = create(client, raw)
    assert response.status_code == 200, response.text
    private(response)
    assert response.headers["etag"] == '"1"'
    assert set(response.json()) == {
        "draft_id",
        "plan",
        "revision",
        "state",
        "contract_version",
        "registry_version",
        "terms",
        "internal_notes",
    }
    before = counts(db)
    read = client.get(path(raw), headers=headers())
    assert read.status_code == 200
    preview = client.post(
        path(raw) + "/preview",
        json={"expected_revision": "1", "contract_version": "catalog.v1"},
        headers=headers(),
    )
    assert (
        preview.status_code == 200
        and not preview.json()["publishable"]
        and preview.json()["pending"]
    )
    assert preview.json()["validation_scope"] == "structural_only"
    assert preview.json()["publication_enabled"] is False
    assert counts(db) == before
    stale = client.post(
        path(raw) + "/preview",
        json={"expected_revision": "2", "contract_version": "catalog.v1"},
        headers=headers(),
    )
    assert (
        stale.status_code == 409
        and stale.json()["detail"]["code"] == ErrorCode.CONFLICT
    )
    edited = dict(raw, revision=2, internal_notes="synthetic edit")
    edit = client.patch(
        path(raw),
        json={"document": edited, "reason": "edit"},
        headers={**headers(), "Idempotency-Key": str(uuid4()), "If-Match": '"1"'},
    )
    assert edit.status_code == 200 and edit.headers["etag"] == '"2"'
    for response in [read, preview, stale, edit]:
        private(response)
    missing = client.get("/api/admin/catalog/drafts/" + str(uuid4()), headers=headers())
    assert (
        missing.status_code == 404
        and missing.json()["detail"]["code"] == ErrorCode.NOT_FOUND
    )


def test_ordinary_and_forged_authority(case):
    db, client, raw, app = case
    before = counts(db)
    response = create(
        client,
        raw,
        **headers(
            ORDINARY, app_metadata={"role": "admin"}, email="admin@synthetic.invalid"
        ),
        **{"X-Actor-Id": MANAGER, "X-Permissions": "subscriptions.manage"},
    )
    assert response.status_code == 403, response.text
    private(response)
    for overrides in [
        {"actor_subject": MANAGER},
        {"permissions": ["subscriptions.manage"]},
        {"role": "admin"},
    ]:
        response = client.post(
            "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts",
            json={"document": raw, "reason": "test", **overrides},
            headers={**headers(), "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": {"code": ErrorCode.INVALID}}
        private(response)
    assert counts(db) == before


@pytest.mark.parametrize(
    "kind",
    [
        "missing-key",
        "bad-key",
        "bad-json",
        "oversize",
        "deep",
        "duplicate-json",
        "unknown-feature",
        "actor-in-document",
        "query-actor",
        "plan-mismatch",
        "too-many-nodes",
    ],
)
def test_invalid_input_no_writes(case, kind):
    db, client, raw, app = case
    url = "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts"
    body = {"document": raw, "reason": "test"}
    hdr = {
        **headers(),
        "Idempotency-Key": str(uuid4()),
        "Content-Type": "application/json",
    }
    if kind == "missing-key":
        hdr.pop("Idempotency-Key")
    elif kind == "bad-key":
        hdr["Idempotency-Key"] = "not-a-uuid"
    elif kind == "unknown-feature":
        raw["terms"]["entitlements"][0]["feature"] = "missing.feature"
    elif kind == "actor-in-document":
        raw["actor_subject"] = MANAGER
    elif kind == "query-actor":
        url += "?actor_id=" + MANAGER
    elif kind == "plan-mismatch":
        body["document"]["plan"]["plan_id"] = str(uuid4())
    elif kind == "too-many-nodes":
        body["extra"] = [0] * 4097
    data = json.dumps(body)
    if kind == "bad-json":
        data = "{"
    elif kind == "oversize":
        data = "x" * 131073
    elif kind == "deep":
        data = '["' + "x" * 5 + '",' * 0 + "[" * 40 + "0" + "]" * 40 + "]"
    elif kind == "duplicate-json":
        data = '{"actor":1,"actor":2}'
    before = counts(db)
    response = client.post(url, content=data, headers=hdr)
    assert response.status_code == 400, response.text
    private(response)
    assert counts(db) == before


def test_retry_conflict_and_lost_response(case):
    db, client, raw, app = case
    runtime = app.state.catalog_drafts
    real = runtime.service()
    key = str(uuid4())

    class LostResponse:
        def __init__(self):
            self.conn = runtime.connect()

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            self.conn.commit()
            raise TimeoutError("synthetic lost reply")

    runtime._service = DraftService(LostResponse, model_keys=real._models)
    first = create(client, raw, key)
    assert (
        first.status_code == 503
        and first.json()["detail"]["code"] == ErrorCode.UNCERTAIN
    )
    before = counts(db)
    runtime._service = real
    replay = create(client, raw, key)
    assert replay.status_code == 200
    equivalent = copy.deepcopy(raw)
    equivalent["terms"]["entitlements"].append(
        {"feature": "notes.generate", "allowed": False}
    )
    assert create(client, equivalent, key).json() == replay.json()
    conflict = create(client, dict(raw, internal_notes="different"), key)
    assert (
        conflict.status_code == 409
        and conflict.json()["detail"]["code"] == ErrorCode.IDENTITY_CONFLICT
    )
    assert counts(db) == before
    for response in [first, replay, conflict]:
        private(response)


def test_revocation_separate_app_and_reused_identity(case):
    db, client, raw, app = case
    runtime = app.state.catalog_drafts
    runtime._pool.resize(1, 1)
    key = str(uuid4())
    assert create(client, raw, key).status_code == 200

    def inspect():
        conn = runtime.connect()
        try:
            row = conn.execute(
                "select pg_backend_pid(),session_user,current_setting('role'),coalesce(current_setting('catalog.draft_actor',true),'')"
            ).fetchone()
            assert conn.execute(
                "select current_setting('statement_timeout'),current_setting('lock_timeout'),"
                "current_setting('idle_in_transaction_session_timeout'),current_setting('transaction_timeout')"
            ).fetchone() == ("10s", "5s", "15s", "20s")
            conn.commit()
            return row
        finally:
            conn.close()

    first = inspect()
    assert first[1:] == ("catalog_draft_executor", "none", "")
    ordinary = client.get(path(raw), headers=headers(ORDINARY))
    assert ordinary.status_code == 403
    second = inspect()
    assert first == second  # same physical connection, no actor carry-over
    from app.main import lifespan

    other_app = FastAPI(lifespan=lifespan)
    other_app.include_router(router, prefix="/api/admin/catalog")
    other_app.add_middleware(CommercialBoundaryMiddleware)
    with TestClient(other_app) as other:
        assert other.get(path(raw), headers=headers()).status_code == 200
        db.run(
            f"update subscription_admin_permissions set active=false,revision=revision+1,reason='revoke' where subject_id={literal(MANAGER)};"
        )
        before = counts(db)
        for response in [
            client.get(path(raw), headers=headers()),
            other.get(path(raw), headers=headers()),
            create(client, raw, key),
        ]:
            assert response.status_code == 403
            private(response)
        assert counts(db) == before


@pytest.mark.parametrize("mode", ["cas", "duplicate", "conflicting-key"])
def test_concurrent_http_mutations(case, mode):
    db, client, raw, app = case
    assert create(client, raw).status_code == 200
    hold = db.barrier(
        f"select 1 from catalog_drafts where draft_id={literal(raw['draft_id'])} for update;"
    )
    key = str(uuid4())
    before = counts(db)

    def edit(i):
        return client.patch(
            path(raw),
            json={
                "document": dict(
                    raw,
                    revision=2,
                    internal_notes="same" if mode == "duplicate" else str(i),
                ),
                "reason": "concurrent",
            },
            headers={
                **headers(),
                "If-Match": '"1"',
                "Idempotency-Key": str(uuid4()) if mode == "cas" else key,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(edit, i) for i in range(2)]
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if (
                    db.rows(
                        "select count(*)::int as n from pg_stat_activity where application_name='catalog-drafts' and cardinality(pg_blocking_pids(pid))>0"
                    )[0]["n"]
                    >= 2
                ):
                    break
            else:
                pytest.fail("HTTP requests did not reach independent SQL lock barriers")
        finally:
            db.release(hold)
        responses = [j.result(timeout=15) for j in jobs]
    assert sorted(r.status_code for r in responses) == (
        [200, 200] if mode == "duplicate" else [200, 409]
    )
    if mode != "duplicate":
        code = ErrorCode.CONFLICT if mode == "cas" else ErrorCode.IDENTITY_CONFLICT
        assert (
            next(r for r in responses if r.status_code == 409).json()["detail"]["code"]
            == code
        )
    else:
        assert responses[0].json() == responses[1].json()
    after = counts(db)
    assert (
        after["audits"] == before["audits"] + 1
        and after["requests"] == before["requests"] + 1
    )
    for r in responses:
        private(r)


def test_missing_config_schema_and_exhaustion(case):
    db, client, raw, app = case
    assert create(client, raw).status_code == 200
    runtime = app.state.catalog_drafts
    leases = [runtime.connect() for _ in range(4)]
    try:
        response = client.get(path(raw), headers=headers())
        assert (
            response.status_code == 503
            and response.json()["detail"]["code"] == ErrorCode.UNAVAILABLE
        )
        private(response)
    finally:
        for lease in leases:
            lease.close()
    db.run(
        "alter function public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text) rename to catalog_draft_service_missing;"
    )
    try:
        response = client.get(path(raw), headers=headers())
        assert response.status_code == 503
        private(response)
    finally:
        db.run(
            "alter function public.catalog_draft_service_missing(uuid,text,uuid,uuid,bigint,jsonb,text) rename to catalog_draft_service_call;"
        )
    app.state.catalog_drafts = CatalogDatabase()
    try:
        response = client.get(path(raw), headers=headers())
        assert response.status_code == 503
        private(response)
    finally:
        app.state.catalog_drafts = runtime


@pytest.mark.parametrize(
    "match", [None, "*", 'W/"1"', "1", '"01"', '"99999999999999999"']
)
def test_edit_preconditions_reject_without_writes(case, match):
    db, client, raw, app = case
    assert create(client, raw).status_code == 200
    before = counts(db)
    hdr = {**headers(), "Idempotency-Key": str(uuid4())}
    if match is not None:
        hdr["If-Match"] = match
    response = client.patch(
        path(raw),
        json={"document": dict(raw, revision=2), "reason": "test"},
        headers=hdr,
    )
    assert response.status_code == 400
    private(response)
    assert counts(db) == before


def test_duplicate_identity_headers_rejected(case):
    db, client, raw, app = case
    before = counts(db)
    response = client.post(
        "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts",
        json={"document": raw, "reason": "test"},
        headers=[
            *headers().items(),
            ("Idempotency-Key", str(uuid4())),
            ("Idempotency-Key", str(uuid4())),
        ],
    )
    assert response.status_code == 400
    private(response)
    assert counts(db) == before


def test_excess_table_privileges_fail_composition_check(case):
    db, client, raw, app = case
    assert create(client, raw).status_code == 200
    # Negative fixture only; no shipped ACL is broadened to perform a mutation.
    db.run("grant select on public.catalog_drafts to catalog_draft_executor;")
    before = counts(db)
    try:
        response = client.get(path(raw), headers=headers())
        assert response.status_code == 503
        private(response)
    finally:
        db.run("revoke select on public.catalog_drafts from catalog_draft_executor;")
    assert counts(db) == before


def test_known_database_termination_rolls_back_and_allows_explicit_retry(
    case, monkeypatch
):
    db, client, raw, app = case
    from app.commercial import draft_service as service_module

    original = service_module.RpcFailure
    states = []

    def observe(code=None, **kwargs):
        states.append(code)
        return original(code, **kwargs)

    monkeypatch.setattr(service_module, "RpcFailure", observe)
    assert create(client, raw).status_code == 200
    before = counts(db)
    hold = db.barrier(
        f"select 1 from catalog_drafts where draft_id={literal(raw['draft_id'])} for update;"
    )
    key = str(uuid4())

    def edit():
        return client.patch(
            path(raw),
            json={"document": dict(raw, revision=2), "reason": "connection loss"},
            headers={**headers(), "If-Match": '"1"', "Idempotency-Key": key},
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(edit)
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                rows = db.rows(
                    "select pid from pg_stat_activity where application_name='catalog-drafts' and cardinality(pg_blocking_pids(pid))>0"
                )
                if rows:
                    break
            else:
                pytest.fail("mutation did not reach native lock barrier")
            assert db.rows(
                f"select pg_terminate_backend({int(rows[0]['pid'])}) as stopped"
            )[0]["stopped"]
            response = job.result(timeout=15)
        finally:
            db.release(hold)
    assert (
        response.status_code == 503
        and response.json()["detail"]["code"] == ErrorCode.UNAVAILABLE
    )
    private(response)
    assert "57P01" in states  # Definite server abort, unlike a lost commit reply.
    assert counts(db) == before
    replay = edit()
    assert replay.status_code == 200
    assert counts(db)["audits"] == before["audits"] + 1


@pytest.mark.parametrize(
    "enabled,dsn",
    [
        ("false", ""),
        ("invalid", ""),
        ("true", ""),
        (
            "true",
            "host=127.0.0.1 dbname=postgres user=catalog_test_owner sslmode=disable",
        ),
        (
            "true",
            "host=synthetic.invalid dbname=postgres user=catalog_draft_executor password=synthetic sslmode=disable",
        ),
        (
            "true",
            "host=127.0.0.1 dbname=postgres user=catalog_draft_executor sslmode=disable options=untrusted",
        ),
    ],
)
def test_configuration_rejection_before_connection(enabled, dsn, monkeypatch):
    import psycopg_pool

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("unexpected pool construction")

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", forbidden)
    runtime = CatalogDatabase(enabled, dsn)
    runtime.start()
    with pytest.raises(CatalogStoreError) as error:
        runtime.service()
    assert error.value.code == ErrorCode.UNAVAILABLE
    assert runtime._pool is None
    assert not calls


def test_import_construction_no_connections():
    import subprocess

    script = """
import socket,sys
class NoNetwork(socket.socket):
    def connect(*args,**kwargs): raise AssertionError('network')
    connect_ex=connect
socket.socket=NoNetwork
from app.commercial.catalog_database import CatalogDatabase
CatalogDatabase();CatalogDatabase('true','unparsed secret')
assert 'psycopg_pool' not in sys.modules and 'psycopg' not in sys.modules
assert 'app.main' not in sys.modules
"""
    from test_catalog_store_native import ROOT

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "backend",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_health_failure_sanitizes_rollback_failure():
    class Broken:
        info = NS(server_version=170011)

        def execute(self, *args):
            raise RuntimeError("private SQL failure")

        def rollback(self):
            raise RuntimeError("private DSN failure")

    with pytest.raises(RuntimeError) as error:
        CatalogDatabase._check(Broken())
    assert str(error.value) == "catalog database unavailable"


def test_unknown_routes_methods_aliases_closed(case, monkeypatch):
    db, client, raw, app = case
    before = counts(db)
    for hosted in [True, False]:
        monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", hosted)
        for method, url in [
            ("DELETE", path(raw)),
            ("PUT", path(raw)),
            ("GET", path(raw) + "/"),
            ("GET", path(raw).replace("/drafts/", "/%64rafts/")),
            ("POST", path(raw) + "/publish"),
            ("POST", path(raw) + "/archive"),
            ("GET", "/api/admin/catalog/drafts"),
            ("POST", "/api/admin/catalog/plans"),
            ("POST", "/api/admin/catalog/grants"),
            ("GET", path(raw).upper()),
            ("GET", "/api/admin/catalog/unknown"),
        ]:
            response = client.request(
                method, url, headers=headers(), follow_redirects=False
            )
            assert response.status_code in ({503} if hosted else {404, 405}), (
                url,
                response.status_code,
            )
            private(response)
    assert counts(db) == before


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    arguments = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=arguments.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )
