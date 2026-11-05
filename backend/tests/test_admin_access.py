"""Actual ASGI/JWT verification; RPC/HTTP fault supplements, no live services."""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import jwt
import pytest
from app.auth import supabase_auth as auth
from app.commercial import admin
from app.commercial import admin_access as a
from app.commercial.catalog_store import (
    CatalogStore,
    CatalogStoreError,
    ErrorCode,
    RpcFailure,
)
from app.config import settings
from fastapi.testclient import TestClient
from test_catalog_contract import document

USER = "10000000-0000-4000-8000-000000000001"
OTHER = "10000000-0000-4000-8000-000000000002"
KEY = "synthetic-only-subscription-probe-signing-key"
PATH = "/api/commercial/admin/me"


def headers(subject=USER, **claims):
    return {
        "Authorization": "Bearer "
        + jwt.encode(
            dict(
                sub=subject,
                exp=int(time.time()) + 300,
                aud="authenticated",
                iss="https://synthetic.invalid/auth/v1",
                **claims
            ),
            KEY,
            algorithm="HS256",
        )
    }


def row(actor, allowed=False):
    return dict(
        contract_version="admin.access.v1",
        subject_id=actor.subject_id,
        permissions=[a.MANAGE] if allowed else [],
        permission_revision="1" if allowed else None,
    )


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", True)
    monkeypatch.setattr(
        auth,
        "get_auth_verification_config",
        lambda: auth.AuthVerificationConfig(
            "legacy_secret", KEY, "https://synthetic.invalid/auth/v1", "authenticated"
        ),
    )
    monkeypatch.setattr("whisper.load_model", lambda *x, **kw: NS())
    from app.main import app

    return app


def private(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "authorization" in response.headers["vary"].lower()


@pytest.mark.parametrize(
    "auth_headers,status",
    [
        ({}, 401),
        ({"Authorization": "Bearer invalid"}, 401),
        (headers("not-a-uuid"), 401),
        (headers(), 200),
        (headers(OTHER), 200),
    ],
)
def test_actual_api_auth_permission_and_safe_payload(
    application, monkeypatch, auth_headers, status
):
    calls = []

    def factory(actor):
        calls.append(actor.subject_id)
        return lambda *x: row(actor, actor.subject_id == USER)

    monkeypatch.setattr(admin, "probe_transport", factory)
    response = TestClient(application).get(PATH, headers=auth_headers)
    assert response.status_code == status
    private(response)
    if status == 401:
        assert not calls and response.headers["www-authenticate"] == "Bearer"
    else:
        assert response.json() == {"permissions": [a.MANAGE] if calls == [USER] else []}


def test_forged_inputs_and_static_lists_never_authorize(application, monkeypatch):
    monkeypatch.setattr(admin, "probe_transport", lambda actor: lambda *x: row(actor))
    monkeypatch.setattr(settings, "SUBSCRIPTION_ADMIN_SUBJECTS", OTHER)
    request_headers = headers(
        OTHER,
        role="admin",
        email="owner@synthetic.invalid",
        user_metadata={"role": "owner", "user_id": USER},
        app_metadata={"permissions": [a.MANAGE]},
    )
    request_headers["X-Actor-ID"] = USER
    response = TestClient(application).request(
        "GET",
        PATH + "?actor_id=" + USER,
        headers=request_headers,
        json={"actor_id": USER, "permissions": [a.MANAGE]},
    )
    assert response.status_code == 200 and response.json() == {"permissions": []}
    private(response)


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"permissions": ["subscriptions.manage"]},
        dict(
            contract_version="future",
            subject_id=USER,
            permissions=[a.MANAGE],
            permission_revision="1",
        ),
        dict(
            contract_version="admin.access.v1",
            subject_id=OTHER,
            permissions=[a.MANAGE],
            permission_revision="1",
        ),
    ],
)
def test_malformed_or_cross_subject_authority_fails_closed(
    application, monkeypatch, result
):
    monkeypatch.setattr(admin, "probe_transport", lambda actor: lambda *x: result)
    response = TestClient(application).get(PATH, headers=headers())
    assert response.status_code == 503 and response.json() == {
        "detail": {"code": ErrorCode.UNAVAILABLE.value}
    }
    private(response)


def test_missing_config_and_store_errors_safe(application, monkeypatch):
    for failure in [
        CatalogStoreError(ErrorCode.UNAVAILABLE),
        RuntimeError("PRIVATE SQL credential record"),
    ]:

        def factory(actor):
            raise failure

        monkeypatch.setattr(admin, "probe_transport", factory)
        response = TestClient(application).get(PATH, headers=headers())
        assert response.status_code == 503 and "PRIVATE" not in response.text
        private(response)
    monkeypatch.setattr(
        auth,
        "get_auth_verification_config",
        lambda: (_ for _ in ()).throw(auth.SupabaseAuthConfigurationError("PRIVATE")),
    )
    response = TestClient(application).get(PATH, headers=headers())
    assert response.status_code == 503 and "PRIVATE" not in response.text
    private(response)


@pytest.mark.parametrize("hosted", [True, False])
@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", PATH),
        ("DELETE", PATH),
        ("HEAD", PATH),
        ("GET", PATH + "/"),
        ("GET", "/api/commercial/admin/%6de"),
        ("GET", "/api/commercial/admin/drafts"),
        ("POST", "/api/commercial/admin/validate"),
    ],
)
def test_wrong_methods_aliases_and_unknown_routes(
    application, monkeypatch, hosted, method, path
):
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", hosted)

    def forbidden(*x):
        pytest.fail("unreviewed request reached authority")

    monkeypatch.setattr(admin, "probe_transport", forbidden)
    response = TestClient(application, follow_redirects=False).request(
        method, path, headers=headers()
    )
    assert response.status_code == (
        503 if hosted else (405 if method != "GET" and path == PATH else 404)
    )
    private(response)


def test_transport_wire_contract_read_only_and_lazy(monkeypatch):
    actor = a.VerifiedActor(USER, "synthetic-verified-bearer")
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *x):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs, self.trust_env))
            return self

        status_code = 200

        def iter_content(self, size):
            yield json.dumps(row(actor, True)).encode()

    monkeypatch.setattr(a.requests, "Session", Session)
    transport = a.ReadOnlyProbeRpc(
        "https://synthetic.invalid", "public-synthetic-key", actor
    )
    assert not calls and "synthetic-verified-bearer" not in repr(actor)
    assert a.AdminBoundary(actor, transport).access().permissions == (a.MANAGE,)
    url, kwargs, trust = calls[0]
    assert url == "https://synthetic.invalid/rest/v1/rpc/" + a.PROBE_RPC
    assert (
        kwargs["json"] == {} and kwargs["headers"]["apikey"] == "public-synthetic-key"
    )
    assert kwargs["headers"]["Authorization"] == "Bearer synthetic-verified-bearer"
    assert (
        kwargs["allow_redirects"] is False and kwargs["timeout"] == (3, 5) and not trust
    )
    for name, params in [
        ("catalog_adapter_archive_snapshot", {}),
        (a.PROBE_RPC, {"actor_id": OTHER}),
    ]:
        with pytest.raises(RpcFailure):
            transport(name, params)
    with pytest.raises(CatalogStoreError) as caught:
        CatalogStore(transport).load_draft(USER)
    assert caught.value.code == ErrorCode.DENIED and len(calls) == 1


@pytest.mark.parametrize(
    "url,key",
    [
        ("http://remote.invalid", "anon"),
        ("https://user:secret@synthetic.invalid", "anon"),
        ("https://synthetic.invalid?key=value", "anon"),
        ("https://synthetic.invalid:bad", "anon"),
        ("https://synthetic.invalid", "sb_secret_synthetic"),
    ],
)
def test_invalid_transport_configuration(url, key):
    with pytest.raises(CatalogStoreError):
        a.ReadOnlyProbeRpc(url, key, a.VerifiedActor(USER, "unused"))


def test_factory_never_uses_service_role_key(monkeypatch):
    actor = a.VerifiedActor(USER, "unused")
    monkeypatch.setattr(
        a,
        "get_supabase_settings",
        lambda: NS(
            cloud_enabled=True,
            supabase_url="https://synthetic.invalid",
            anon_key="public-synthetic",
            service_role_key="private-synthetic",
        ),
    )
    assert a.probe_transport(actor)._key == "public-synthetic"
    monkeypatch.setattr(a, "get_supabase_settings", lambda: NS(cloud_enabled=False))
    with pytest.raises(CatalogStoreError):
        a.probe_transport(actor)


@pytest.mark.parametrize(
    "status,body",
    [
        (302, b"{}"),
        (401, b"{}"),
        (403, b"{}"),
        (404, b"{}"),
        (500, b"PRIVATE"),
        (200, b"not-json"),
        (200, b"x" * 8193),
    ],
)
def test_http_transport_failures_and_bounded_body(status, body, monkeypatch):
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        status_code = status

        def post(self, *args, **kwargs):
            calls.append(True)
            return self

        def iter_content(self, size):
            yield body

    monkeypatch.setattr(a.requests, "Session", Session)
    actor = a.VerifiedActor(USER, "unused")
    boundary = a.AdminBoundary(
        actor, a.ReadOnlyProbeRpc("https://synthetic.invalid", "public", actor)
    )
    with pytest.raises(CatalogStoreError) as caught:
        boundary.access()
    assert caught.value.code == ErrorCode.UNAVAILABLE and len(calls) == 1


def test_internal_validation_rechecks_authority_and_never_persists():
    actor = a.VerifiedActor(USER, "unused")
    allowed = True
    calls = []

    def rpc(name, params):
        calls.append((name, params))
        return row(actor, allowed)

    boundary = a.AdminBoundary(actor, rpc)
    assert boundary.validate_draft(document()).publishable
    assert not boundary.validate_draft(dict(document(), actor_id=OTHER)).valid
    for payload in [{"value": ["x"] * 5000}, {"value": "x" * 131073}]:
        with pytest.raises(CatalogStoreError) as caught:
            boundary.validate_draft(payload)
        assert caught.value.code == ErrorCode.INVALID
    allowed = False
    with pytest.raises(CatalogStoreError) as caught:
        boundary.validate_draft(document())
    assert caught.value.code == ErrorCode.DENIED
    assert all(name == a.PROBE_RPC and params == {} for name, params in calls)


def test_module_import_and_construction_no_remote_calls():
    script = """
import sys, requests, socket, dotenv
sys.path.insert(0, 'backend')
def forbidden(*a, **k): raise AssertionError('import/construct performed I/O')
requests.Session = forbidden
socket.create_connection = forbidden
dotenv.load_dotenv = lambda *a, **k: False
from app.commercial.admin_access import ReadOnlyProbeRpc, VerifiedActor
ReadOnlyProbeRpc('https://synthetic.invalid','public',VerifiedActor('unused','unused'))
assert 'app.main' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("path", [PATH, "/api/admin/catalog/drafts", "/api/catalog"])
def test_cors_preflight_precedes_commercial_boundary(application, path):
    client = TestClient(application)
    response = client.options(path, headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.get("/api/not-reviewed", headers={"Origin": "http://localhost:5173"})
    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "commercial_path_unreviewed"
    assert denied.headers["access-control-allow-origin"] == "http://localhost:5173"
