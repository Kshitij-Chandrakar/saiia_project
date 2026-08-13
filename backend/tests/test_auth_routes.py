from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import _desktop_handoffs, router as auth_router
from app.auth.supabase_auth import (
    AUTH_ERROR_DETAIL,
    get_auth_verification_config,
)
from app.cloud.profile_bootstrap import ProfileBootstrapResult
from app.cloud.supabase_config import (
    CLOUD_MODE_ENV,
    SUPABASE_REQUIRED_ENV_VARS,
    SupabaseConfigurationError,
    get_supabase_settings,
)


TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


@pytest.fixture(autouse=True)
def clear_supabase_auth_env(monkeypatch):
    _desktop_handoffs.clear()
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    yield
    _desktop_handoffs.clear()
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", TEST_SECRET)
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    return TestClient(app)


def _token(
    *,
    secret: str = TEST_SECRET,
    expires_delta: timedelta = timedelta(minutes=5),
    extra_claims: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "sub": TEST_USER_ID,
        "email": "user@example.com",
        "role": "authenticated",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_auth_me_rejects_missing_token(client: TestClient):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_auth_me_rejects_invalid_token(client: TestClient):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_auth_me_accepts_valid_token(client: TestClient):
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": TEST_USER_ID,
        "email": "user@example.com",
        "role": "authenticated",
    }


def test_auth_me_does_not_return_raw_token_or_claims(client: TestClient):
    token = _token(extra_claims={"app_metadata": {"provider": "email"}})

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert token not in response.text
    assert "claims" not in body
    assert "app_metadata" not in body


def test_profile_bootstrap_rejects_missing_token(client: TestClient):
    response = client.post("/api/auth/profile/bootstrap")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_profile_bootstrap_rejects_invalid_token(client: TestClient):
    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_profile_bootstrap_uses_verified_user_id(monkeypatch, client: TestClient):
    calls: list[str] = []

    def fake_bootstrap(user_id: str) -> ProfileBootstrapResult:
        calls.append(user_id)
        return ProfileBootstrapResult(
            user_id=user_id,
            profile_exists=True,
            profile_created=True,
            settings_exists=True,
            settings_created=True,
            next_step="profile_setup",
        )

    monkeypatch.setattr("app.api.auth.bootstrap_authenticated_profile", fake_bootstrap)

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"user_id": "11111111-1111-4111-8111-111111111111"},
    )

    assert response.status_code == 200
    assert calls == [TEST_USER_ID]
    assert response.json() == {
        "user_id": TEST_USER_ID,
        "profile_exists": True,
        "profile_created": True,
        "settings_exists": True,
        "settings_created": True,
        "next_step": "profile_setup",
    }


def test_profile_bootstrap_response_excludes_token_service_role_and_claims(monkeypatch, client: TestClient):
    service_role_value = "service-role-unit-test-value"

    def fake_bootstrap(user_id: str) -> ProfileBootstrapResult:
        return ProfileBootstrapResult(
            user_id=user_id,
            profile_exists=True,
            profile_created=False,
            settings_exists=True,
            settings_created=False,
            next_step="profile_setup",
        )

    monkeypatch.setattr("app.api.auth.bootstrap_authenticated_profile", fake_bootstrap)
    token = _token(extra_claims={"service_role_key": service_role_value})

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert token not in response.text
    assert service_role_value not in response.text
    assert "claims" not in response.json()


def test_profile_bootstrap_config_error_response_is_generic(monkeypatch, client: TestClient):
    def fake_bootstrap(user_id: str) -> ProfileBootstrapResult:
        raise SupabaseConfigurationError("SUPABASE_SERVICE_ROLE_KEY matches SUPABASE_ANON_KEY")

    monkeypatch.setattr("app.api.auth.bootstrap_authenticated_profile", fake_bootstrap)

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Supabase cloud configuration is not ready."}
    assert "SUPABASE_SERVICE_ROLE_KEY" not in response.text


def test_create_desktop_handoff_requires_valid_authenticated_user(client: TestClient):
    response = client.post(
        "/api/auth/desktop-handoff",
        json={"state": "desktop-state-123456", "refresh_token": "refresh-token"},
    )

    assert response.status_code == 401
    assert "refresh-token" not in response.text


def test_desktop_handoff_exchange_works_once_and_excludes_tokens_from_create_response(client: TestClient):
    token = _token()
    create = client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {token}"},
        json={"state": "desktop-state-123456", "refresh_token": "refresh-token"},
    )

    assert create.status_code == 200
    handoff_code = create.json()["handoff_code"]
    assert handoff_code
    assert token not in create.text
    assert "refresh-token" not in create.text
    assert handoff_code not in _desktop_handoffs

    exchange = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "desktop-state-123456", "handoff_code": handoff_code},
    )

    assert exchange.status_code == 200
    assert exchange.json() == {
        "access_token": token,
        "refresh_token": "refresh-token",
    }

    replay = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "desktop-state-123456", "handoff_code": handoff_code},
    )
    assert replay.status_code == 404
    assert replay.json() == {"detail": "Invalid or expired desktop handoff."}
    assert handoff_code not in replay.text
    assert token not in replay.text
    assert "refresh-token" not in replay.text


def test_desktop_handoff_rejects_mismatched_and_expired_state(monkeypatch, client: TestClient):
    now = 1000.0
    monkeypatch.setattr("app.api.auth.time.time", lambda: now)
    create = client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"state": "desktop-state-123456", "refresh_token": "refresh-token"},
    )
    handoff_code = create.json()["handoff_code"]

    mismatch = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "wrong-desktop-state", "handoff_code": handoff_code},
    )
    assert mismatch.status_code == 404
    assert "refresh-token" not in mismatch.text

    create = client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"state": "desktop-state-abcdef", "refresh_token": "refresh-token"},
    )
    handoff_code = create.json()["handoff_code"]
    now += 301

    expired = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "desktop-state-abcdef", "handoff_code": handoff_code},
    )
    assert expired.status_code == 404
    assert "refresh-token" not in expired.text
