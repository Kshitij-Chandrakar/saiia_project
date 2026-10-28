"""Actual ASGI + real JWT verification + native caller-scoped database probe.

The fixture emulates PostgREST's verified gateway; no actual PostgREST/Supabase
HTTP deployment is claimed. Production HTTP transport has separate wire tests.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import supabase_auth as auth
from app.commercial import admin
from app.commercial import admin_access as a
from app.commercial.boundary import CommercialBoundaryMiddleware
from app.commercial.catalog_store import ErrorCode, RpcFailure
from test_admin_access import OTHER, PATH, USER, headers
from test_admin_access import application as application
from test_catalog_store_native import FUNCTIONS, ROOT, Native, literal


@pytest.fixture(scope="module")
def database(request):
    binary = request.config.getoption("--catalog-pg-bin", default=None)
    if not binary:
        pytest.skip("explicit disposable native PostgreSQL required")
    db = Native(binary)
    try:
        db.run(f"""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;create role direct_login login noinherit;
        grant anon,authenticated,service_role to authenticator;grant authenticated to direct_login;
        create schema auth;create table auth.users(id uuid primary key);
        create function auth.uid() returns uuid language sql stable as
          $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        grant usage on schema auth,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        insert into auth.users values ({literal(USER)}),({literal(OTHER)});
        """)
        for name in [
            "20261022120000_catalog_storage_foundation.sql",
            "20261022150000_catalog_adapter_primitives.sql",
            "20261022180000_subscription_admin_self_probe.sql",
            "20261022200000_catalog_draft_service.sql",
        ]:
            db.run((ROOT / "supabase/migrations" / name).read_text(encoding="utf-8"))
        db.run(
            f"insert into public.subscription_admin_permissions values ({literal(USER)},'subscriptions.manage',1,true,{literal(USER)},'synthetic admin test');"
        )
        print("native admin probe:", db.rows("select version() as version"))
        yield db
    finally:
        db.close()


def digest(db):
    state = {}
    for table in [
        "subscription_admin_permissions",
        "catalog_plans",
        "catalog_drafts",
        "catalog_draft_revisions",
        "catalog_offer_versions",
        "catalog_price_versions",
        "catalog_visibility",
        "catalog_admin_actions",
        "catalog_draft_requests",
    ]:
        state[table] = db.rows(
            f"select coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text),'[]') as data from public.{table} t"
        )[0]["data"]
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def composed(application, database, monkeypatch):
    db = database
    db.run(
        f"update public.subscription_admin_permissions set active=true,revision=revision+1,reason='synthetic reset' where subject_id={literal(USER)};"
    )
    pids = []

    def factory(actor):
        def rpc(name, params):
            assert name == a.PROBE_RPC and params == {}
            # Independently verify the original bearer at the synthetic gateway.
            user = auth.verify_supabase_token(actor._bearer)
            assert user.user_id == actor.subject_id
            role = user.role or "authenticated"
            if role not in {"authenticated", "anon", "service_role"}:
                raise RpcFailure("42501")
            output = db.run(
                f"begin read only;set session authorization authenticator;set role {role};"
                f"select set_config('request.jwt.claim.sub',{literal(user.user_id)},false);"
                f"select jsonb_build_object('result',public.{a.PROBE_RPC}(),'pid',pg_backend_pid());commit;"
            )
            result = json.loads(output.strip().splitlines()[-1])
            pids.append(result["pid"])
            return result["result"]

        return rpc

    monkeypatch.setattr(admin, "probe_transport", factory)
    return application, db, pids


@pytest.mark.parametrize(
    "case,status,permissions",
    [
        ("anonymous", 401, None),
        ("invalid", 401, None),
        ("ordinary", 200, []),
        ("admin", 200, [a.MANAGE]),
        ("forged", 200, []),
        ("role", 503, None),
    ],
)
def test_native_actual_api_zero_writes(composed, case, status, permissions):
    app, db, pids = composed
    before = digest(db)
    h = (
        {}
        if case == "anonymous"
        else (
            {"Authorization": "Bearer invalid"}
            if case == "invalid"
            else headers(
                OTHER if case in {"ordinary", "forged", "role"} else USER,
                **(
                    {"role": "service_role"}
                    if case == "role"
                    else (
                        {
                            "email": "owner@synthetic.invalid",
                            "user_metadata": {"role": "owner", "sub": USER},
                            "app_metadata": {"permissions": [a.MANAGE]},
                        }
                        if case == "forged"
                        else {}
                    )
                ),
            )
        )
    )
    response = TestClient(app).request(
        "GET",
        PATH + "?actor_id=" + USER,
        headers=h,
        json={"actor_id": USER, "permissions": [a.MANAGE]},
    )
    assert response.status_code == status
    if permissions is not None:
        assert response.json() == {"permissions": permissions}
    assert (
        response.headers["cache-control"] == "no-store"
        and "authorization" in response.headers["vary"].lower()
    )
    assert digest(db) == before
    assert len(pids) == (1 if permissions is not None else 0)


def test_native_revocation_new_connection_and_application(composed):
    app, db, pids = composed
    assert TestClient(app).get(PATH, headers=headers()).json() == {
        "permissions": [a.MANAGE]
    }
    db.run(
        f"update public.subscription_admin_permissions set active=false,revision=revision+1,reason='revoke' where subject_id={literal(USER)};"
    )
    before = digest(db)
    # Separate worker composition uses the same real route/middleware modules.
    worker = FastAPI()
    worker.add_middleware(CommercialBoundaryMiddleware)
    worker.include_router(admin.router, prefix="/api/commercial")
    response = TestClient(worker).get(PATH, headers=headers())
    assert response.status_code == 200 and response.json() == {"permissions": []}
    assert len(pids) == 2 and pids[0] != pids[1]
    assert digest(db) == before


def test_native_missing_store_returns_unavailable_without_writes(composed):
    app, db, pids = composed
    before = digest(db)
    db.run(
        "alter table public.subscription_admin_permissions rename to c113a_store_outage;"
    )
    try:
        response = TestClient(app).get(PATH, headers=headers())
        assert response.status_code == 503 and response.json() == {
            "detail": {"code": ErrorCode.UNAVAILABLE.value}
        }
        assert response.headers["cache-control"] == "no-store"
    finally:
        db.run(
            "alter table public.c113a_store_outage rename to subscription_admin_permissions;"
        )
    assert digest(db) == before and not pids


def test_native_function_permissions_no_mutation_access(database):
    db = database
    metadata = db.rows(
        "select provolatile,prosecdef,proconfig,pg_get_userbyid(proowner) as owner from pg_proc where oid='public.subscription_admin_self_probe()'::regprocedure"
    )[0]
    assert metadata == dict(
        provolatile="s",
        prosecdef=True,
        proconfig=["search_path=pg_catalog"],
        owner="catalog_test_owner",
    )
    for role, allowed in [
        ("authenticated", True),
        ("anon", False),
        ("service_role", False),
    ]:
        assert (
            db.rows(
                f"select has_function_privilege('{role}','public.subscription_admin_self_probe()','EXECUTE') as allowed"
            )[0]["allowed"]
            == allowed
        )
        for name, signature in {
            **FUNCTIONS,
            "catalog_save_draft": "uuid,uuid,bigint,jsonb,text",
            "catalog_retire_offer": "uuid,bigint,text",
        }.items():
            assert not db.rows(
                f"select has_function_privilege('{role}','public.{name}({signature})','EXECUTE') as allowed"
            )[0]["allowed"]
    for sql in [
        "set role authenticated;select * from public.subscription_admin_permissions;",
        "set role authenticated;update public.subscription_admin_permissions set active=true;",
        "set session authorization direct_login;set role authenticated;select public.subscription_admin_self_probe();",
    ]:
        with pytest.raises(RpcFailure) as caught:
            db.run(sql)
        assert caught.value.sqlstate == "42501"


def test_native_missing_migration_function_is_unavailable(composed):
    app, db, pids = composed
    before = digest(db)
    db.run(
        "alter function public.subscription_admin_self_probe() rename to c113a_missing_probe;"
    )
    try:
        response = TestClient(app).get(PATH, headers=headers())
        assert response.status_code == 503 and response.json() == {
            "detail": {"code": ErrorCode.UNAVAILABLE.value}
        }
        assert response.headers["cache-control"] == "no-store"
    finally:
        db.run(
            "alter function public.c113a_missing_probe() rename to subscription_admin_self_probe;"
        )
    assert digest(db) == before and not pids


def test_native_internal_validation_readonly(composed):
    app, db, pids = composed
    from starlette.requests import Request
    from test_catalog_contract import document

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", headers()["Authorization"].encode())],
        }
    )
    actor = a.verified_actor(request)
    boundary = a.AdminBoundary(actor, admin.probe_transport(actor))
    before = digest(db)
    assert boundary.validate_draft(document()).publishable
    assert not boundary.validate_draft(dict(document(), actor_id=OTHER)).valid
    assert digest(db) == before


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
