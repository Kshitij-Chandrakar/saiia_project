from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
from typing import Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.supabase_auth import (
    AUTH_CONFIG_ERROR_DETAIL,
    AUTH_ERROR_DETAIL,
    CurrentUser,
    get_auth_verification_config,
    get_current_user,
    verify_supabase_token,
)
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings


TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


@pytest.fixture(autouse=True)
def clear_supabase_auth_env(monkeypatch):
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    yield
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()


@pytest.fixture
def auth_client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: CurrentUser = Depends(get_current_user)):
        return {
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "claims": user.claims,
        }

    return TestClient(app)


def _configure_legacy_secret(monkeypatch, *, secret: str = TEST_SECRET) -> None:
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-" + "unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-" + "unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", secret)
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()


def _token(
    *,
    secret: str = TEST_SECRET,
    subject: str | None = TEST_USER_ID,
    expires_delta: timedelta = timedelta(minutes=5),
    extra_claims: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "email": "user@example.com",
        "role": "authenticated",
    }
    if subject is not None:
        payload["sub"] = subject
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_missing_authorization_header_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_non_bearer_authorization_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get("/protected", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401


def test_malformed_token_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get("/protected", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_expired_token_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get(
        "/protected",
        headers={"Authorization": f"Bearer {_token(expires_delta=timedelta(minutes=-1))}"},
    )

    assert response.status_code == 401


def test_invalid_signature_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get(
        "/protected",
        headers={"Authorization": f"Bearer {_token(secret='wrong-secret')}"},
    )

    assert response.status_code == 401


def test_valid_token_accepted(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get("/protected", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == TEST_USER_ID
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "authenticated"
    assert "exp" in payload["claims"]


def test_jwks_url_config_is_preferred_when_configured(monkeypatch):
    _configure_legacy_secret(monkeypatch, secret="https://project-ref.supabase.co/auth/v1/.well-known/jwks.json")

    config = get_auth_verification_config()

    assert config.mode == "jwks_url"
    assert config.key.endswith("/.well-known/jwks.json")


def test_jwks_json_config_is_supported(monkeypatch):
    _configure_legacy_secret(monkeypatch, secret='{"keys": []}')

    config = get_auth_verification_config()

    assert config.mode == "jwks_json"


def test_missing_subject_rejected(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)

    response = auth_client.get(
        "/protected",
        headers={"Authorization": f"Bearer {_token(subject=None)}"},
    )

    assert response.status_code == 401


def test_missing_auth_config_is_clear_when_dependency_called(auth_client: TestClient):
    response = auth_client.get("/protected", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 503
    assert response.json() == {"detail": AUTH_CONFIG_ERROR_DETAIL}


def test_local_backend_import_still_works_without_auth_config():
    env = dict(os.environ)
    env["PYTHONPATH"] = "backend"
    for name in SUPABASE_REQUIRED_ENV_VARS:
        env.pop(name, None)
    env[CLOUD_MODE_ENV] = "local"

    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app; print(app.title)"],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "SAIIA Backend" in result.stdout


def test_raw_token_not_returned_in_error_response(auth_client: TestClient, monkeypatch):
    _configure_legacy_secret(monkeypatch)
    raw_token = _token(secret="wrong-secret")

    response = auth_client.get("/protected", headers={"Authorization": f"Bearer {raw_token}"})

    assert response.status_code == 401
    assert raw_token not in response.text


def test_service_role_key_is_not_used_for_jwt_verification(monkeypatch):
    service_role_value = "service-role-" + "unit-test-value"
    _configure_legacy_secret(monkeypatch, secret="")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", service_role_value)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()

    with pytest.raises(Exception) as exc_info:
        verify_supabase_token(_token(secret=service_role_value))

    assert service_role_value not in str(exc_info.value)
