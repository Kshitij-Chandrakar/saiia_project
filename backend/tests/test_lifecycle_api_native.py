"""F3 HTTP/JWT -> existing bounded pool -> actual services/native PostgreSQL.

Synthetic policy injection and disposable local LOGIN only; no remote acceptance.
"""

import argparse
import copy
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import supabase_auth as auth
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.catalog_store import ErrorCode
from app.commercial.review_contract import ReviewAuthority
from app.config import settings
from test_catalog_store_native import ROOT, MANAGER, ORDINARY, literal
from test_draft_service_native import database, KEY
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install, counts
from test_draft_api_native import headers, path, create, private
from test_catalog_contract import document


@pytest.fixture(scope="module", autouse=True)
def install(database, f1_install, f2_install):
    database.run(
        (
            ROOT / "supabase/migrations/20261023010000_catalog_lifecycle_transport.sql"
        ).read_text()
    )


@pytest.fixture
def case(database, install, monkeypatch):
    db = database
    db.run(
        f"update subscription_admin_permissions set active=true,revision=revision+1 where subject_id={literal(MANAGER)}"
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
    monkeypatch.setattr(settings, "CATALOG_LIFECYCLE_ENABLED", "true")
    monkeypatch.setattr(
        settings,
        "CATALOG_DRAFTS_DSN",
        f"host=127.0.0.1 port={db.port} dbname=postgres user=catalog_draft_executor sslmode=disable",
    )
    monkeypatch.setattr("whisper.load_model", lambda *a, **k: NS())

    def forbidden(*args, **kwargs):
        raise AssertionError("No provider/payment HTTP calls")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    from app import main

    now = datetime.now(timezone.utc)
    state = dict(
        authority=ReviewAuthority(
            policy_id=str(uuid4()),
            policy_version=1,
            policy_fingerprint="a" * 64,
            approval_revision=1,
            reviewer_rule_ref="synthetic.rule",
            model_registry_version="synthetic.models",
            model_keys=(),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
    )

    def resolver(query, subject, draft):
        if state.get("on_resolve"):
            state["on_resolve"]()
        if state["authority"] is None:
            raise RuntimeError("synthetic missing policy")
        return state["authority"]

    # Explicit TEST-ONLY constructor injection. Production main supplies no resolver.
    monkeypatch.setattr(
        main,
        "CatalogDatabase",
        lambda *a, **kw: CatalogDatabase(*a, **kw, resolver=resolver),
    )
    raw = document()
    raw.update(draft_id=str(uuid4()), state="draft")
    raw["plan"] = dict(plan_id=str(uuid4()), code="synthetic-" + uuid4().hex)
    raw["terms"]["prices"][0]["price_id"] = str(uuid4())
    with TestClient(main.app) as client:
        runtime = main.app.state.catalog_drafts
        runtime.lifecycle_service()  # requires actual pool ACL/schema checks
        yield db, client, raw, main.app, state
    assert runtime._pool is None


def write_headers(key=None, revision="1", subject=MANAGER):
    return {
        **headers(subject),
        "Idempotency-Key": key or str(uuid4()),
        "If-Match": '"' + revision + '"',
    }


def basis(client, raw, action="publish"):
    response = client.post(
        path(raw) + "/preview",
        json=dict(
            scope="publication_review",
            expected_revision="1",
            contract_version="catalog.v1",
            intent=dict(action=action, valid_from="2026-01-01T00:00:00Z"),
        ),
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    private(response)
    return response.json()["basis"]


def review(client, raw, action="publish", key=None):
    b = basis(client, raw, action)
    response = client.post(
        path(raw) + "/publication-reviews",
        json=dict(basis=b, confirmed=True, reason="synthetic review"),
        headers=write_headers(key),
    )
    assert response.status_code == 200, response.text
    private(response)
    return response.json()


def publish(client, raw, reviewed, key=None, action="publish", **overrides):
    b = reviewed["receipt"]["basis"]
    body = dict(
        review_id=reviewed["receipt"]["review_id"],
        reason="synthetic publish",
        expected_archive_revision=(
            b["archived_offer"]["visibility_revision"] if b["archived_offer"] else None
        ),
    )
    if action == "replace":
        body["predecessor"] = b["current_offer"]
    body.update(overrides)
    return client.post(path(raw) + "/" + action, json=body, headers=write_headers(key))


def test_review_publish_retire_recovery_and_terminal_dto(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    before = counts(db)
    rk = str(uuid4())
    r = review(client, raw, key=rk)
    rid = r["receipt"]["review_id"]
    assert (
        client.get(
            "/api/admin/catalog/publication-reviews/" + rid, headers=headers()
        ).json()
        == r
    )
    assert (
        client.get("/api/admin/catalog/operations/" + rk, headers=headers()).json() == r
    )
    key = str(uuid4())
    response = publish(client, raw, r, key)
    assert response.status_code == 200, response.text
    private(response)
    result = response.json()
    assert result["current"]["state"] == "visible" and not result["publication_enabled"]
    assert publish(client, raw, r, key).json() == result
    op = client.get("/api/admin/catalog/operations/" + key, headers=headers())
    assert op.json() == result
    offer_id = result["receipt"]["offer_version_id"]
    offer_path = "/api/admin/catalog/offers/" + offer_id
    offered = client.get(offer_path, headers=headers())
    assert offered.status_code == 200, offered.text
    private(offered)
    assert set(offered.json()) == {
        "snapshot",
        "current",
        "publication",
        "source",
        "catalog_revision",
        "publication_enabled",
        "purchasable",
    }
    assert offered.json()["source"]["state"] == "published"
    assert offered.json()["source"]["revision"] == "2"
    immutable = offered.json()["snapshot"]
    retired = client.post(
        offer_path + "/retire",
        json={"reason": "synthetic"},
        headers=write_headers(revision="2"),
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["current"]["state"] == "retired"
    replay = publish(client, raw, r, key)
    assert replay.status_code == 200 and replay.json()["current"]["state"] == "retired"
    assert replay.json()["receipt"] == result["receipt"]
    assert client.get(offer_path, headers=headers()).json()["snapshot"] == immutable
    assert counts(db)["epoch"] == before["epoch"] + 2


def test_replacement(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    first = publish(client, raw, review(client, raw)).json()
    nxt = copy.deepcopy(raw)
    nxt["draft_id"] = str(uuid4())
    nxt["terms"]["prices"][0]["price_id"] = str(uuid4())
    assert create(client, nxt).status_code == 200
    reviewed = review(client, nxt, "replace")
    before = counts(db)
    wrong = dict(reviewed["receipt"]["basis"]["current_offer"], fingerprint="b" * 64)
    rejected = publish(client, nxt, reviewed, action="replace", predecessor=wrong)
    assert (
        rejected.status_code == 409
        and rejected.json()["detail"]["code"] == ErrorCode.REVIEW_STALE
    )
    assert counts(db) == before
    response = publish(client, nxt, reviewed, action="replace")
    assert response.status_code == 200, response.text
    assert (
        client.get(
            "/api/admin/catalog/offers/" + first["receipt"]["offer_version_id"],
            headers=headers(),
        ).json()["current"]["state"]
        == "retired"
    )


@pytest.mark.parametrize(
    "credentials", [{}, {"Authorization": "Bearer invalid"}, headers(exp=0)]
)
def test_auth_before_body(case, credentials):
    db, client, raw, app, state = case
    before = counts(db)
    response = client.post(
        path(raw) + "/publish", content="not JSON", headers=credentials
    )
    assert response.status_code == 401
    private(response)
    assert counts(db) == before


def test_ordinary_forged_and_revoked_identity(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    rid = r["receipt"]["review_id"]
    before = counts(db)
    ordinary = client.post(
        path(raw) + "/publish",
        json=dict(review_id=rid, reason="bad"),
        headers={
            **write_headers(subject=ORDINARY),
            **headers(
                ORDINARY,
                app_metadata={"role": "admin"},
                email="admin@synthetic.invalid",
            ),
            "X-Actor-Id": MANAGER,
            "X-Permissions": "subscriptions.manage",
        },
    )
    assert ordinary.status_code == 403
    private(ordinary)
    for extra in [
        {"actor_subject": MANAGER},
        {"permissions": ["subscriptions.manage"]},
        {"role": "admin"},
        {"state": "published"},
    ]:
        bad = publish(client, raw, r, **extra)
        assert bad.status_code == 400
        private(bad)
    assert counts(db) == before
    key = str(uuid4())
    result = publish(client, raw, r, key).json()
    # A second application/pool sees the same authoritative grant removal.
    from fastapi import FastAPI
    from app.commercial.lifecycle_api import router
    from app.commercial.boundary import CommercialBoundaryMiddleware

    second = CatalogDatabase(
        "true", settings.CATALOG_DRAFTS_DSN, lifecycle_enabled="true"
    )
    second.start()
    other_app = FastAPI()
    other_app.state.catalog_drafts = second
    other_app.add_middleware(CommercialBoundaryMiddleware)
    other_app.include_router(router, prefix="/api/admin/catalog")
    db.run(
        f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)}"
    )
    try:
        with TestClient(other_app) as other:
            denied = other.get(
                "/api/admin/catalog/operations/" + key, headers=headers()
            )
            assert denied.status_code == 403
            private(denied)
        for response in [
            publish(client, raw, r, key),
            publish(client, raw, r),
            client.get(
                "/api/admin/catalog/publication-reviews/" + rid, headers=headers()
            ),
            client.post(
                "/api/admin/catalog/offers/"
                + result["receipt"]["offer_version_id"]
                + "/retire",
                json={"reason": "bad"},
                headers=write_headers(revision="2"),
            ),
        ]:
            assert response.status_code == 403
            private(response)
    finally:
        second.close()


def test_incomplete_stale_and_mismatched_review(case):
    db, client, raw, app, state = case
    raw["terms"] = {}
    assert create(client, raw).status_code == 200
    response = client.post(
        path(raw) + "/preview",
        json=dict(
            scope="publication_review",
            expected_revision=1,
            contract_version="catalog.v1",
            intent=dict(action="publish", valid_from="2026-01-01T00:00:00Z"),
        ),
        headers=headers(),
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == ErrorCode.NOT_PUBLISHABLE
    )
    # Restore a complete draft as revision 2; review basis must reflect exact r2.
    raw["terms"] = document()["terms"]
    raw["terms"]["prices"][0]["price_id"] = str(uuid4())
    raw["revision"] = 2
    assert (
        client.patch(
            path(raw),
            json={"document": raw, "reason": "complete"},
            headers=write_headers(),
        ).status_code
        == 200
    )
    b_response = client.post(
        path(raw) + "/preview",
        json=dict(
            scope="publication_review",
            expected_revision=2,
            contract_version="catalog.v1",
            intent=dict(action="publish", valid_from="2026-01-01T00:00:00Z"),
        ),
        headers=headers(),
    )
    b = b_response.json()["basis"]
    before = counts(db)
    bad = dict(b, terms_fingerprint="b" * 64)
    wrong = client.post(
        path(raw) + "/publication-reviews",
        json=dict(basis=bad, confirmed=True, reason="bad"),
        headers=write_headers(revision="2"),
    )
    assert (
        wrong.status_code == 409
        and wrong.json()["detail"]["code"] == ErrorCode.REVIEW_STALE
    )
    for confirmed in [False, 1, "true"]:
        wrong = client.post(
            path(raw) + "/publication-reviews",
            json=dict(basis=b, confirmed=confirmed, reason="bad"),
            headers=write_headers(revision="2"),
        )
        assert wrong.status_code == 400
    assert counts(db) == before
    reviewed = client.post(
        path(raw) + "/publication-reviews",
        json=dict(basis=b, confirmed=True, reason="synthetic"),
        headers=write_headers(revision="2"),
    ).json()
    rid = reviewed["receipt"]["review_id"]
    wrong_path = client.post(
        "/api/admin/catalog/drafts/" + str(uuid4()) + "/publish",
        json=dict(review_id=rid, reason="synthetic publish"),
        headers=write_headers(revision="2"),
    )
    assert wrong_path.status_code == 400
    wrong_revision = publish(client, raw, reviewed)
    assert (
        wrong_revision.status_code == 409
        and wrong_revision.json()["detail"]["code"] == ErrorCode.CONFLICT
    )
    raw["revision"] = 3
    assert (
        client.patch(
            path(raw),
            json={"document": raw, "reason": "changed"},
            headers=write_headers(revision="2"),
        ).status_code
        == 200
    )
    stale = client.post(
        path(raw) + "/publish",
        json=dict(review_id=rid, reason="synthetic publish"),
        headers=write_headers(revision="2"),
    )
    assert (
        stale.status_code == 409
        and stale.json()["detail"]["code"] == ErrorCode.REVIEW_STALE
    )
    assert (
        client.get(
            "/api/admin/catalog/publication-reviews/" + rid, headers=headers()
        ).json()["state"]
        == "draft_changed"
    )


@pytest.mark.parametrize("mode", ["duplicate", "conflict", "competing"])
def test_concurrent_http_requests(case, mode):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    reviewed = review(client, raw)
    key = str(uuid4())
    before = counts(db)
    hold = db.barrier(
        f"select 1 from catalog_plans where plan_id={literal(raw['plan']['plan_id'])} for no key update;"
    )

    def call(i):
        return publish(
            client,
            raw,
            reviewed,
            str(uuid4()) if mode == "competing" else key,
            reason=str(i) if mode == "conflict" else "synthetic publish",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(call, i) for i in range(2)]
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if (
                    db.rows(
                        "select count(*) as n from pg_stat_activity where application_name='catalog-drafts' and cardinality(pg_blocking_pids(pid))>0"
                    )[0]["n"]
                    >= 2
                ):
                    break
            else:
                pytest.fail("HTTP requests did not reach two native lock waits")
        finally:
            db.release(hold)
        responses = [j.result(timeout=15) for j in jobs]
    assert sorted(r.status_code for r in responses) == (
        [200, 200] if mode == "duplicate" else [200, 409]
    )
    if mode == "duplicate":
        assert responses[0].json() == responses[1].json()
    else:
        assert next(r for r in responses if r.status_code == 409).json()["detail"][
            "code"
        ] == (
            ErrorCode.IDENTITY_CONFLICT
            if mode == "conflict"
            else ErrorCode.REVIEW_STALE
        )
    assert counts(db)["consumed"] == before["consumed"] + 1
    assert counts(db)["epoch"] == before["epoch"] + 1


@pytest.mark.parametrize("committed", [True, False])
def test_http_uncertain_commit_recovery(case, committed):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    s = app.state.catalog_drafts.lifecycle_service()
    connect = s._drafts._connect

    class Lost:
        def __init__(self):
            self.connection = connect()

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            self.connection.commit() if committed else self.connection.rollback()
            raise OSError("synthetic lost commit response")

    before = counts(db)
    key = str(uuid4())
    s._drafts._connect = Lost
    try:
        uncertain = publish(client, raw, r, key)
        assert (
            uncertain.status_code == 503
            and uncertain.json()["detail"]["code"] == ErrorCode.UNCERTAIN
        )
        private(uncertain)
    finally:
        s._drafts._connect = connect
    result = publish(client, raw, r, key)
    assert result.status_code == 200
    assert publish(client, raw, r, key).json() == result.json()
    assert counts(db)["epoch"] == before["epoch"] + 1
    assert counts(db)["consumed"] == before["consumed"] + 1


def test_rollback_at_late_audit_failure(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    before = counts(db)
    key = str(uuid4())
    db.run(
        """create function f3_fail() returns trigger language plpgsql as $$begin
    if new.operation='offer.publish' then raise exception 'synthetic'; end if; return new; end;$$;
    create trigger f3_failure before insert on catalog_admin_actions for each row execute function f3_fail();"""
    )
    try:
        failed = publish(client, raw, r, key)
        assert failed.status_code == 503
        private(failed)
        assert counts(db) == before
    finally:
        db.run(
            "drop trigger f3_failure on catalog_admin_actions;drop function f3_fail();"
        )
    assert publish(client, raw, r, key).status_code == 200


def test_missing_config_policy_schema_grants_and_pool_exhaustion(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    runtime = app.state.catalog_drafts
    before = counts(db)
    runtime._lifecycle._resolver = None  # actual production default
    unavailable = publish(client, raw, r)
    assert (
        unavailable.status_code == 503
        and unavailable.json()["detail"]["code"] == ErrorCode.UNAVAILABLE
    )
    private(unavailable)
    assert counts(db) == before
    # Retirement and historical reads do not invent dependency approvals.
    app.state.catalog_drafts = CatalogDatabase()
    try:
        response = client.get(
            "/api/admin/catalog/publication-reviews/" + r["receipt"]["review_id"],
            headers=headers(),
        )
        assert response.status_code == 503
        private(response)
    finally:
        app.state.catalog_drafts = runtime
    leases = [runtime.connect() for _ in range(4)]
    try:
        response = client.get(
            "/api/admin/catalog/publication-reviews/" + r["receipt"]["review_id"],
            headers=headers(),
        )
        assert response.status_code == 503
        private(response)
    finally:
        for lease in leases:
            lease.close()
    signature = "public.catalog_lifecycle_read_call(uuid,text,uuid)"
    db.run(f"revoke execute on function {signature} from catalog_draft_executor")
    try:
        response = client.get(
            "/api/admin/catalog/operations/" + str(uuid4()), headers=headers()
        )
        assert response.status_code == 503
        private(response)
    finally:
        db.run(f"grant execute on function {signature} to catalog_draft_executor")
    db.run("alter table catalog_public_state rename to f3_missing_epoch")
    try:
        response = client.get(
            "/api/admin/catalog/operations/" + str(uuid4()), headers=headers()
        )
        assert response.status_code == 503
        private(response)
    finally:
        db.run("alter table f3_missing_epoch rename to catalog_public_state")
    assert counts(db) == before


def test_pool_identity_reuse_and_extra_privilege_denial(case):
    db, client, raw, app, state = case
    runtime = app.state.catalog_drafts
    # Hold all but one connection, forcing actual reuse for different subjects.
    held = [runtime.connect() for _ in range(3)]
    try:
        assert create(client, raw).status_code == 200
        r = review(client, raw)
        target = "/api/admin/catalog/publication-reviews/" + r["receipt"]["review_id"]
        for subject in [ORDINARY, MANAGER, ORDINARY, MANAGER]:
            response = client.get(target, headers=headers(subject))
            assert response.status_code == (200 if subject == MANAGER else 403)
            private(response)
        with runtime.connect() as connection:
            assert connection.execute(
                "select coalesce(current_setting('catalog.draft_actor',true),''),session_user,current_user"
            ).fetchone() == ("", "catalog_draft_executor", "catalog_draft_executor")
            assert connection.execute(
                "select rolsuper,rolbypassrls from pg_roles where rolname=current_user"
            ).fetchone() == (False, False)
            connection.commit()
    finally:
        for conn in held:
            conn.close()
    # Negative ACL fixture: an unreviewed helper grant must poison checkout.
    db.run(
        "grant execute on function public.catalog_lifecycle_result(uuid,uuid) to catalog_draft_executor"
    )
    try:
        response = client.get(target, headers=headers())
        assert response.status_code == 503
        private(response)
    finally:
        db.run(
            "revoke execute on function public.catalog_lifecycle_result(uuid,uuid) from catalog_draft_executor"
        )


def test_exact_ingress_sizes_methods_and_preconditions(case, monkeypatch):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    before = counts(db)
    for hosted in [True, False]:
        monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", hosted)
        for method, url in [
            ("GET", path(raw) + "/publish"),
            ("PUT", path(raw) + "/publish"),
            ("POST", path(raw) + "/publish/"),
            ("POST", path(raw) + "/archive"),
            ("POST", path(raw).replace("/drafts/", "/%64rafts/") + "/publish"),
            ("POST", path(raw).upper() + "/publish"),
            ("GET", "/api/admin/catalog/offers"),
            ("POST", "/api/admin/catalog/grants"),
            ("POST", "/api/admin/catalog/operations/" + str(uuid4())),
        ]:
            response = client.request(
                method, url, headers=headers(), follow_redirects=False
            )
            assert response.status_code in ({503} if hosted else {404, 405})
            private(response)
    for value in [None, "*", 'W/"1"', '"01"', "1"]:
        hdr = write_headers()
        if value is None:
            hdr.pop("If-Match")
        else:
            hdr["If-Match"] = value
        response = client.post(
            path(raw) + "/publish",
            json=dict(review_id=r["receipt"]["review_id"], reason="test"),
            headers=hdr,
        )
        assert response.status_code == 400
        private(response)
    for value in [dict(actor=MANAGER), {"reason": "x" * 131073}]:
        response = client.post(
            path(raw) + "/publish", json=value, headers=write_headers()
        )
        assert response.status_code == 400
        private(response)
    deep = {}
    for _ in range(40):
        deep = {"x": deep}
    response = client.post(path(raw) + "/publish", json=deep, headers=write_headers())
    assert response.status_code == 400
    assert counts(db) == before
    monkeypatch.setattr(settings, "CATALOG_LIFECYCLE_ENABLED", "false")
    response = publish(client, raw, r)
    assert response.status_code == 404
    assert counts(db) == before


def test_other_admin_cannot_read_caller_operation(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    key = str(uuid4())
    review(client, raw, key=key)
    # Synthetic second manager, scoped to this disposable transaction fixture.
    db.run(
        f"insert into subscription_admin_permissions values({literal(ORDINARY)},'subscriptions.manage',1,true,{literal(MANAGER)},'synthetic') on conflict(subject_id,permission) do update set active=true,revision=subscription_admin_permissions.revision+1"
    )
    try:
        response = client.get(
            "/api/admin/catalog/operations/" + key, headers=headers(ORDINARY)
        )
        assert response.status_code == 404
        private(response)
    finally:
        db.run(
            f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(ORDINARY)}"
        )


@pytest.mark.parametrize("edit_first", [True, False])
def test_http_edit_publish_order(case, edit_first, monkeypatch):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    r = review(client, raw)
    entered, go = threading.Event(), threading.Event()

    def pause():
        entered.set()
        assert go.wait(10)

    if edit_first:
        state["on_resolve"] = pause
    else:
        service = app.state.catalog_drafts.lifecycle_service()
        original = service._basis

        def locked(*a, **kw):
            result = original(*a, **kw)
            pause()
            return result

        monkeypatch.setattr(service, "_basis", locked)

    def edit():
        return client.patch(
            path(raw),
            json={"document": dict(raw, revision=2), "reason": "race"},
            headers=write_headers(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        pub = executor.submit(publish, client, raw, r)
        assert entered.wait(10)
        if edit_first:
            try:
                assert edit().status_code == 200
            finally:
                go.set()
            response = pub.result(timeout=15)
            assert (
                response.status_code == 409
                and response.json()["detail"]["code"] == ErrorCode.REVIEW_STALE
            )
        else:
            editing = executor.submit(edit)
            try:
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    if (
                        db.rows(
                            "select count(*) as n from pg_stat_activity where application_name='catalog-drafts' and cardinality(pg_blocking_pids(pid))>0"
                        )[0]["n"]
                        >= 1
                    ):
                        break
                else:
                    pytest.fail("edit did not reach native row-lock barrier")
            finally:
                go.set()
            assert pub.result(timeout=15).status_code == 200
            assert editing.result(timeout=15).status_code == 409


def test_request_key_semantics_and_review_retry(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    b = basis(client, raw)
    key = str(uuid4())
    body = dict(basis=b, confirmed=True, reason="synthetic")
    first = client.post(
        path(raw) + "/publication-reviews", json=body, headers=write_headers(key)
    )
    assert first.status_code == 200
    before = counts(db)
    assert (
        client.post(
            path(raw) + "/publication-reviews", json=body, headers=write_headers(key)
        ).json()
        == first.json()
    )
    conflicting = client.post(
        path(raw) + "/publication-reviews",
        json=dict(body, reason="different"),
        headers=write_headers(key),
    )
    assert (
        conflicting.status_code == 409
        and conflicting.json()["detail"]["code"] == ErrorCode.IDENTITY_CONFLICT
    )
    assert counts(db) == before
    pk = str(uuid4())
    assert publish(client, raw, first.json(), pk).status_code == 200
    body = dict(
        review_id=first.json()["receipt"]["review_id"], reason="synthetic publish"
    )
    changed = client.post(
        path(raw) + "/publish", json=body, headers=write_headers(pk, revision="2")
    )
    assert (
        changed.status_code == 409
        and changed.json()["detail"]["code"] == ErrorCode.IDENTITY_CONFLICT
    )


def test_safe_corrupt_offer_and_read_only_paths(case):
    db, client, raw, app, state = case
    assert create(client, raw).status_code == 200
    rk = str(uuid4())
    r = review(client, raw, key=rk)
    pk = str(uuid4())
    result = publish(client, raw, r, pk).json()
    oid = result["receipt"]["offer_version_id"]
    before = counts(db)
    for url in [
        "/api/admin/catalog/publication-reviews/" + r["receipt"]["review_id"],
        "/api/admin/catalog/offers/" + oid,
        "/api/admin/catalog/operations/" + rk,
        "/api/admin/catalog/operations/" + pk,
    ]:
        response = client.get(url, headers=headers())
        assert response.status_code == 200
        private(response)
    assert counts(db) == before
    original = db.rows(
        f"select canonical_json from catalog_offer_versions where offer_version_id={literal(oid)}"
    )[0]["canonical_json"]
    db.run(
        f"alter table catalog_offer_versions disable trigger immutable_rows;update catalog_offer_versions set canonical_json='{{}}' where offer_version_id={literal(oid)};alter table catalog_offer_versions enable trigger immutable_rows;"
    )
    try:
        response = client.get("/api/admin/catalog/offers/" + oid, headers=headers())
        assert (
            response.status_code == 503
            and response.json()["detail"]["code"] == ErrorCode.STORED_INVALID
        )
        private(response)
    finally:
        db.run(
            f"alter table catalog_offer_versions disable trigger immutable_rows;update catalog_offer_versions set canonical_json={literal(original)} where offer_version_id={literal(oid)};alter table catalog_offer_versions enable trigger immutable_rows;"
        )
    assert counts(db) == before


def test_role_and_function_boundary(case):
    db, client, raw, app, state = case
    from app.commercial.catalog_database import LIFECYCLE_SIGNATURES
    from app.commercial.catalog_store import RpcFailure

    for signature in LIFECYCLE_SIGNATURES:
        assert db.rows(
            f"select prosecdef,proconfig from pg_proc where oid={literal(signature)}::regprocedure"
        ) == [{"prosecdef": True, "proconfig": ["search_path=pg_catalog"]}]

    for role in ["anon", "authenticated", "service_role"]:
        for signature in LIFECYCLE_SIGNATURES:
            assert db.rows(
                f"select has_function_privilege('{role}','{signature}','EXECUTE') as allowed"
            ) == [{"allowed": False}]
        for table in [
            "catalog_publications",
            "catalog_publication_reviews",
            "catalog_lifecycle_requests",
            "catalog_public_state",
            "subscription_admin_permissions",
        ]:
            assert db.rows(
                f"select has_table_privilege('{role}','{table}','SELECT,INSERT,UPDATE,DELETE,TRUNCATE') as allowed"
            ) == [{"allowed": False}]
        with pytest.raises(RpcFailure) as error:
            db.run(
                f"set role {role};select public.catalog_lifecycle_read_call({literal(MANAGER)},'operation',{literal(str(uuid4()))})"
            )
        assert error.value.sqlstate == "42501"
    assert db.rows(
        "select has_function_privilege('catalog_draft_executor','public.catalog_lifecycle_result(uuid,uuid)','EXECUTE') as allowed"
    ) == [{"allowed": False}]
    # Wrong role/session cannot assert an actor even if a maintenance fixture
    # supplies the manager's UUID and transaction-local GUC.
    with pytest.raises(RpcFailure) as error:
        db.run(
            f"set catalog.draft_actor={literal(MANAGER)};select public.catalog_lifecycle_read_call({literal(MANAGER)},'operation',{literal(str(uuid4()))})"
        )
    assert error.value.sqlstate == "42501"


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
