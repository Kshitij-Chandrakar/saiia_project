"""Closed Python service/adapter against disposable native PostgreSQL only.

Requires explicit --pg-bin and psycopg in the test interpreter, not a project
runtime dependency. No remote DSN/config is accepted by this runner.
"""

import argparse
import copy
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import supabase_auth as auth
from app.commercial import catalog_contract as c
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, RpcFailure
from app.commercial.draft_service import DraftService
from test_catalog_contract import document
from test_catalog_store_native import MANAGER, ORDINARY, ROOT, Native, literal

KEY = "synthetic-only-draft-service-jwt-key-long-enough"
SIGNATURE = "public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text)"


def actor(subject=MANAGER, **claims):
    payload = dict(
        sub=subject,
        exp=int(time.time()) + 600,
        aud="authenticated",
        iss="https://synthetic.invalid/auth/v1",
        role="authenticated",
    )
    payload.update(claims)
    token = jwt.encode(
        payload,
        KEY,
        algorithm="HS256",
    )
    return VerifiedActor(subject, token)


def failure(code, call):
    with pytest.raises(CatalogStoreError) as error:
        call()
    assert error.value.code == code
    assert str(error.value) == code.value


@pytest.fixture(scope="module")
def database(request):
    binary = request.config.getoption("--catalog-pg-bin", default=None)
    if not binary:
        pytest.skip("explicit disposable native PostgreSQL required")
    psycopg = pytest.importorskip("psycopg")
    db = Native(binary)
    try:
        db.run(f"""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;
        grant anon,authenticated,service_role to authenticator;
        create schema auth;create table auth.users(id uuid primary key);
        create function auth.uid() returns uuid language sql stable as
          $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        grant usage on schema auth,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        insert into auth.users values ({literal(MANAGER)}),({literal(ORDINARY)});
        """)
        for name in [
            "20261022120000_catalog_storage_foundation.sql",
            "20261022150000_catalog_adapter_primitives.sql",
            "20261022180000_subscription_admin_self_probe.sql",
            "20261022200000_catalog_draft_service.sql",
        ]:
            db.run((ROOT / "supabase/migrations" / name).read_text(encoding="utf-8"))
        db.run(
            f"insert into public.subscription_admin_permissions values ({literal(MANAGER)},'subscriptions.manage',1,true,{literal(MANAGER)},'synthetic');"
        )

        def connect(app="c113b-service"):
            conn = psycopg.connect(
                host="127.0.0.1",
                port=db.port,
                dbname="postgres",
                user="catalog_test_owner",
                connect_timeout=5,
                application_name=app,
            )
            # Fixture-only impersonation by disposable owner. Shipped principal
            # has NOLOGIN and no members; no deployment/provisioning is claimed.
            conn.execute("SET SESSION AUTHORIZATION catalog_draft_executor")
            conn.commit()
            return conn

        db.connect = connect
        print("native draft service:", db.rows("select version() as version"))
        yield db
    finally:
        db.close()


@pytest.fixture
def case(database, monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_auth_verification_config",
        lambda: auth.AuthVerificationConfig(
            "legacy_secret", KEY, "https://synthetic.invalid/auth/v1", "authenticated"
        ),
    )
    db = database
    db.run(
        f"update public.subscription_admin_permissions set active=true,revision=revision+1,reason='synthetic reset' where subject_id={literal(MANAGER)};"
    )
    raw = document()
    raw.update(draft_id=str(uuid4()), state="draft")
    raw["plan"] = dict(plan_id=str(uuid4()), code="synthetic-" + uuid4().hex)
    raw["terms"]["prices"][0]["price_id"] = str(uuid4())
    return db, DraftService(db.connect), raw


def counts(db):
    return db.rows(
        "select (select count(*) from catalog_plans) as plans,"
        "(select count(*) from catalog_drafts) as drafts,"
        "(select count(*) from catalog_draft_revisions) as revisions,"
        "(select count(*) from catalog_admin_actions) as audits,"
        "(select count(*) from catalog_draft_requests) as requests"
    )[0]


def test_roundtrip_incomplete_and_preview(case):
    db, service, raw = case
    raw["terms"] = {}
    key = str(uuid4())
    saved = service.create(actor(), raw, request_id=key, reason="create")
    assert saved.revision == 1
    before_reads = counts(db)
    assert service.retrieve(actor(), saved.draft_id) == saved
    report = service.preview(actor(), saved.draft_id)
    assert report.valid and not report.publishable and report.pending
    assert counts(db) == before_reads
    raw.update(revision=2, internal_notes="editable incomplete")
    assert (
        service.edit(
            actor(), raw, expected_revision=1, request_id=str(uuid4()), reason="edit"
        ).revision
        == 2
    )
    failure(ErrorCode.NOT_FOUND, lambda: service.retrieve(actor(), str(uuid4())))
    assert (
        db.rows(
            f"select actor_subject::text as actor from catalog_admin_actions where resource_id={literal(raw['draft_id'])}"
        )
        == [{"actor": MANAGER}] * 2
    )


@pytest.mark.parametrize(
    "kind",
    [
        "ordinary",
        "forged_subject",
        "invalid_token",
        "service_role_token",
        "actor_field",
        "permission_field",
        "invalid_feature",
        "bad_revision",
        "oversize",
    ],
)
def test_denied_invalid_zero_writes(case, kind):
    db, service, raw = case
    identity = actor()
    code = ErrorCode.INVALID
    if kind == "ordinary":
        identity = actor(
            ORDINARY, app_metadata={"role": "admin"}, email="admin@synthetic.invalid"
        )
        code = ErrorCode.DENIED
    elif kind == "forged_subject":
        identity = VerifiedActor(MANAGER, actor(ORDINARY)._bearer)
        code = ErrorCode.DENIED
    elif kind == "invalid_token":
        identity = VerifiedActor(MANAGER, "invalid")
        code = ErrorCode.DENIED
    elif kind == "service_role_token":
        identity = actor(role="service_role")
        code = ErrorCode.DENIED
    elif kind == "actor_field":
        raw["actor_subject"] = MANAGER
    elif kind == "permission_field":
        raw["permissions"] = ["subscriptions.manage"]
    elif kind == "invalid_feature":
        raw["terms"]["entitlements"][0]["feature"] = "imaginary"
    elif kind == "bad_revision":
        raw["revision"] = 2
    elif kind == "oversize":
        raw["internal_notes"] = "x" * 131073
    before = counts(db)
    failure(
        code,
        lambda: service.create(identity, raw, request_id=str(uuid4()), reason="test"),
    )
    assert counts(db) == before


def test_durable_replay_semantics_and_conflicts(case):
    db, service, raw = case
    key = str(uuid4())
    first = service.create(actor(), raw, request_id=key, reason="create")
    baseline = counts(db)
    equivalent = copy.deepcopy(raw)
    equivalent["terms"]["entitlements"].append(
        dict(feature="notes.generate", allowed=False)
    )
    # Explicit denied keys and absent denied keys canonicalize identically.
    assert (
        DraftService(db.connect).create(
            actor(), equivalent, request_id=key, reason="create"
        )
        == first
    )
    assert counts(db) == baseline
    changed = dict(raw, internal_notes="different")
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: service.create(actor(), changed, request_id=key, reason="create"),
    )
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: service.create(
            actor(), dict(raw, draft_id=str(uuid4())), request_id=key, reason="create"
        ),
    )
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: service.edit(
            actor(),
            dict(raw, revision=2),
            expected_revision=1,
            request_id=key,
            reason="create",
        ),
    )
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: service.create(actor(), raw, request_id=key, reason="different"),
    )
    service.edit(
        actor(),
        dict(raw, revision=2),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="edit",
    )
    assert service.create(actor(), raw, request_id=key, reason="create") == first
    assert service.retrieve(actor(), raw["draft_id"]).revision == 2
    # Revision conflicts aren't stored as success/retry records.
    before = counts(db)
    failure(
        ErrorCode.CONFLICT,
        lambda: service.edit(
            actor(),
            dict(raw, revision=2),
            expected_revision=1,
            request_id=str(uuid4()),
            reason="stale",
        ),
    )
    assert counts(db) == before


def test_revocation_denies_replay_read_edit_preview(case):
    db, service, raw = case
    key = str(uuid4())
    service.create(actor(), raw, request_id=key, reason="create")
    db.run(
        f"update subscription_admin_permissions set active=false,revision=revision+1,reason='revoke' where subject_id={literal(MANAGER)};"
    )
    before = counts(db)
    for call in [
        lambda: DraftService(db.connect).create(
            actor(), raw, request_id=key, reason="create"
        ),
        lambda: service.retrieve(actor(), raw["draft_id"]),
        lambda: service.preview(actor(), raw["draft_id"]),
        lambda: service.edit(
            actor(),
            dict(raw, revision=2),
            expected_revision=1,
            request_id=str(uuid4()),
            reason="edit",
        ),
    ]:
        failure(ErrorCode.DENIED, call)
    assert counts(db) == before


def test_revocation_commits_before_waiting_mutation(case):
    db, service, raw = case
    hold = db.barrier(
        f"update subscription_admin_permissions set active=false,revision=revision+1,reason='ordered revoke' where subject_id={literal(MANAGER)};"
    )
    before = counts(db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(
            lambda: failure(
                ErrorCode.DENIED,
                lambda: DraftService(lambda: db.connect("c113b-revoke-first")).create(
                    actor(), raw, request_id=str(uuid4()), reason="test"
                ),
            )
        )
        try:
            wait_blocked(db, ["c113b-revoke-first"])
        finally:
            db.release(hold)
        job.result(timeout=15)
    after = counts(db)
    assert after == dict(before, audits=before["audits"] + 1)


def test_mutation_lock_commits_before_waiting_revocation(case):
    db, _, raw = case
    ready, release = threading.Event(), threading.Event()

    class PausedCommit:
        def __init__(self):
            self.conn = db.connect("c113b-write-first")

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            ready.set()
            assert release.wait(8), "commit barrier timed out"
            self.conn.commit()

    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        write = pool.submit(
            lambda: DraftService(PausedCommit).create(
                actor(), raw, request_id=key, reason="create"
            )
        )
        assert ready.wait(5)
        revoke = pool.submit(
            lambda: db.run(
                f"update subscription_admin_permissions set active=false,revision=revision+1,reason='ordered revoke' where subject_id={literal(MANAGER)};",
                "c113b-revoke",
            )
        )
        try:
            wait_blocked(db, ["c113b-revoke"])
        finally:
            release.set()
        assert write.result(timeout=15).revision == 1
        revoke.result(timeout=15)
    failure(
        ErrorCode.DENIED,
        lambda: DraftService(db.connect).create(
            actor(), raw, request_id=key, reason="create"
        ),
    )


def test_unavailable_safe_no_retry(case):
    db, _, raw = case
    calls = []

    def unavailable():
        calls.append(1)
        raise OSError("private DSN and SQL must not appear")

    before = counts(db)
    failure(
        ErrorCode.UNAVAILABLE,
        lambda: DraftService(unavailable).create(
            actor(), raw, request_id=str(uuid4()), reason="test"
        ),
    )
    assert len(calls) == 1 and counts(db) == before
    failure(
        ErrorCode.UNAVAILABLE, lambda: DraftService().retrieve(actor(), raw["draft_id"])
    )


def wait_blocked(db, apps):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        rows = db.rows(
            "select application_name as app from pg_stat_activity where cardinality(pg_blocking_pids(pid))>0"
        )
        if set(apps) <= {r["app"] for r in rows}:
            return
    pytest.fail("independent sessions did not reach explicit database lock barrier")


@pytest.mark.parametrize("duplicate", [False, True, "conflicting-key"])
def test_concurrent_connections_cas_or_duplicate(case, duplicate):
    db, service, raw = case
    service.create(actor(), raw, request_id=str(uuid4()), reason="create")
    hold = db.barrier(
        f"select 1 from catalog_drafts where draft_id={literal(raw['draft_id'])} for update;"
    )
    key = str(uuid4())

    def edit(i):
        try:
            return DraftService(lambda: db.connect(f"c113b-edit-{i}")).edit(
                actor(),
                dict(
                    raw,
                    revision=2,
                    internal_notes="same" if duplicate is True else str(i),
                ),
                expected_revision=1,
                request_id=key if duplicate else str(uuid4()),
                reason="edit",
            )
        except CatalogStoreError as error:
            return error.code

    before = counts(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(edit, i) for i in range(2)]
        try:
            wait_blocked(db, ["c113b-edit-0", "c113b-edit-1"])
        finally:
            db.release(hold)
        results = [job.result(timeout=15) for job in jobs]
    if duplicate is True:
        assert results[0] == results[1] and isinstance(results[0], c.CatalogDraft)
    elif duplicate:
        assert sum(isinstance(r, c.CatalogDraft) for r in results) == 1
        assert ErrorCode.IDENTITY_CONFLICT in results
    else:
        assert (
            sum(isinstance(r, c.CatalogDraft) for r in results) == 1
            and ErrorCode.CONFLICT in results
        )
    after = counts(db)
    assert after["audits"] == before["audits"] + 1
    assert after["requests"] == before["requests"] + 1
    assert after["revisions"] == before["revisions"] + 1


@pytest.mark.parametrize("committed", [False, True])
def test_uncertain_commit_and_explicit_retry(case, committed):
    db, _, raw = case
    key = str(uuid4())

    class LostResponse:
        def __init__(self):
            self.conn = db.connect()

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            if committed:
                self.conn.commit()
                raise OSError("synthetic lost response after commit")
            raise TimeoutError("synthetic uncertain commit timeout")

    before = counts(db)
    failure(
        ErrorCode.UNCERTAIN,
        lambda: DraftService(LostResponse).create(
            actor(), raw, request_id=key, reason="create"
        ),
    )
    assert counts(db)["requests"] == before["requests"] + int(committed)
    DraftService(db.connect).create(actor(), raw, request_id=key, reason="create")
    assert counts(db)["requests"] == before["requests"] + 1
    assert counts(db)["audits"] == before["audits"] + 1


def test_rollback_and_snapshot_integrity(case):
    db, service, raw = case
    # Fault after audit insertion: constraint failure must undo plan/draft/history,
    # audit and retry state together, not leave a falsely successful retry record.
    db.run(
        "create function fail_retry() returns trigger language plpgsql as $$begin raise exception 'synthetic' using errcode='23514';end$$;create trigger fail_retry before insert on catalog_draft_requests for each row execute function fail_retry();"
    )
    before = counts(db)
    try:
        failure(
            ErrorCode.INVALID,
            lambda: service.create(
                actor(), raw, request_id=str(uuid4()), reason="rollback"
            ),
        )
        assert counts(db) == before
    finally:
        db.run(
            "drop trigger fail_retry on catalog_draft_requests;drop function fail_retry();"
        )
    saved = service.create(actor(), raw, request_id=str(uuid4()), reason="create")
    candidate = saved.model_dump(mode="python")
    candidate["state"] = "previewed"
    snapshot = c.create_snapshot(candidate, offer_version_id=str(uuid4()), version=1)
    db.run(
        f"insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json) values ({literal(snapshot.offer_version_id)},{literal(saved.plan.plan_id)},1,{literal(saved.draft_id)},1,{literal(snapshot.canonical_json())});"
    )

    def terms():
        return db.rows(
            "select canonical_json,fingerprint from catalog_offer_versions"
        ), db.rows("select document from catalog_price_versions")

    before_terms = terms()
    service.edit(
        actor(),
        dict(raw, revision=2),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="edit",
    )
    service.preview(actor(), saved.draft_id)
    assert terms() == before_terms
    with pytest.raises(RpcFailure) as error:
        db.run("update catalog_offer_versions set canonical_json='{}';")
    assert error.value.sqlstate == "55000"
    assert terms() == before_terms


def test_closed_privileges_and_request_storage(case):
    db, _, _ = case
    for role in ["anon", "authenticated", "service_role", "authenticator"]:
        assert not db.rows(
            f"select has_function_privilege('{role}','{SIGNATURE}','execute') as ok"
        )[0]["ok"]
        with pytest.raises(RpcFailure) as error:
            db.run(
                f"set session authorization authenticator;set role {role if role != 'authenticator' else 'none'};"
                f"select set_config('catalog.draft_actor',{literal(MANAGER)},false);"
                f"select public.catalog_draft_service_call({literal(MANAGER)},'draft.read',gen_random_uuid(),null,null,null,null);"
            )
        assert error.value.sqlstate == "42501"
        assert not db.rows(
            f"select pg_has_role('{role}','catalog_draft_executor','member') as ok"
        )[0]["ok"]
    flags = db.rows(
        "select rolcanlogin,rolsuper,rolcreaterole,rolbypassrls from pg_roles where rolname='catalog_draft_executor'"
    )[0]
    assert not any(flags.values())
    for table in [
        "catalog_drafts",
        "catalog_draft_requests",
        "subscription_admin_permissions",
        "catalog_offer_versions",
        "catalog_price_versions",
    ]:
        assert not db.rows(
            f"select has_table_privilege('catalog_draft_executor','public.{table}','select,insert,update,delete') as ok"
        )[0]["ok"]
    for sql in [
        "update subscription_admin_permissions set active=true",
        "select catalog_adapter_load_draft(gen_random_uuid())",
        "update catalog_offer_versions set canonical_json='{}'",
        "delete from catalog_draft_requests",
    ]:
        with pytest.raises(RpcFailure) as error:
            db.run("set session authorization catalog_draft_executor;" + sql)
        assert error.value.sqlstate == "42501"
    cols = db.rows(
        "select column_name as name from information_schema.columns where table_name='catalog_draft_requests'"
    )
    assert {r["name"] for r in cols} == {
        "actor_subject",
        "request_id",
        "operation",
        "draft_id",
        "expected_revision",
        "resulting_revision",
        "semantic_hash",
        "recorded_at",
    }


def test_import_construction_no_activation():
    script = """
import socket,sys
def deny(*args,**kwargs): raise AssertionError('network')
class NoNetwork(socket.socket):
    connect=deny
    connect_ex=deny
socket.socket=NoNetwork
socket.create_connection=deny
from app.commercial.draft_service import DraftService
DraftService(); DraftService(deny)
assert 'app.main' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


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
