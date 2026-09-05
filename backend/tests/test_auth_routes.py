from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import (
    DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS,
    DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER,
    _desktop_handoff_create_timestamps,
    _desktop_handoffs,
    _hash_handoff_code,
    _trigger_welcome_email,
    router as auth_router,
)
from app.auth.supabase_auth import (
    AUTH_ERROR_DETAIL,
    get_auth_verification_config,
)
from app.cloud.profile_bootstrap import ProfileBootstrapResult, ProfileConsent
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
    _desktop_handoff_create_timestamps.clear()
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    yield
    _desktop_handoffs.clear()
    _desktop_handoff_create_timestamps.clear()
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
    monkeypatch.setattr("app.api.auth._trigger_welcome_email", lambda current_user: None)

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


def _create_handoff(client: TestClient, *, token: str | None = None, state: str = "desktop-state-123456"):
    return client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {token or _token()}"},
        json={"state": state, "refresh_token": "refresh-token"},
    )


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


def test_profile_bootstrap_triggers_welcome_from_verified_identity_not_body(
    monkeypatch,
    client: TestClient,
):
    trigger_calls: list[tuple[str, str | None]] = []

    def fake_trigger(current_user) -> None:
        trigger_calls.append((current_user.user_id, current_user.email))

    def fake_bootstrap(user_id: str) -> ProfileBootstrapResult:
        return ProfileBootstrapResult(
            user_id=user_id,
            profile_exists=True,
            profile_created=True,
            settings_exists=True,
            settings_created=True,
            next_step="profile_setup",
        )

    monkeypatch.setattr("app.api.auth._trigger_welcome_email", fake_trigger)
    monkeypatch.setattr("app.api.auth.bootstrap_authenticated_profile", fake_bootstrap)

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "email": "attacker@example.com",
        },
    )

    assert response.status_code == 200
    assert trigger_calls == [(TEST_USER_ID, "user@example.com")]


def test_profile_bootstrap_persists_consent_for_jwt_user_not_body_identity(monkeypatch, client: TestClient):
    calls: list[tuple[str, ProfileConsent | None]] = []

    def fake_bootstrap(user_id: str, consent: ProfileConsent | None = None) -> ProfileBootstrapResult:
        calls.append((user_id, consent))
        return ProfileBootstrapResult(
            user_id=user_id,
            profile_exists=True,
            profile_created=False,
            settings_exists=True,
            settings_created=False,
            next_step="profile_setup",
        )

    monkeypatch.setattr("app.api.auth.bootstrap_authenticated_profile", fake_bootstrap)

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "email": "attacker@example.com",
            "terms_accepted": True,
            "privacy_accepted": True,
            "marketing_email_opt_in": False,
            "consent_source": "signup",
            "consent_version": "c10.6a-v1",
        },
    )

    assert response.status_code == 200
    assert calls == [
        (
            TEST_USER_ID,
            ProfileConsent(True, True, False, "signup", "c10.6a-v1"),
        )
    ]


def test_profile_bootstrap_rejects_incomplete_consent(monkeypatch, client: TestClient):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.api.auth.bootstrap_authenticated_profile",
        lambda user_id: calls.append(user_id),
    )

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"terms_accepted": True, "privacy_accepted": False},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Terms and Privacy acceptance are required."}
    assert calls == []


def test_profile_bootstrap_welcome_failure_does_not_break_account_setup(monkeypatch, client: TestClient):
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

    def failing_event_store() -> None:
        raise RuntimeError("provider failure")

    monkeypatch.setattr(
        "app.api.auth._trigger_welcome_email",
        _trigger_welcome_email,
    )
    monkeypatch.setattr("app.api.auth.build_outbound_email_event_service", failing_event_store)

    response = client.post(
        "/api/auth/profile/bootstrap",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == TEST_USER_ID


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
    handoff_hash = _hash_handoff_code(handoff_code)
    assert handoff_hash in _desktop_handoffs

    exchange = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "desktop-state-123456", "handoff_code": handoff_code},
    )

    assert exchange.status_code == 200
    assert exchange.json() == {
        "access_token": token,
        "refresh_token": "refresh-token",
    }
    assert handoff_hash not in _desktop_handoffs

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
    monkeypatch.setattr("app.api.auth._now", lambda: now)
    create = client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"state": "desktop-state-123456", "refresh_token": "refresh-token"},
    )
    handoff_code = create.json()["handoff_code"]
    handoff_hash = _hash_handoff_code(handoff_code)
    assert handoff_hash in _desktop_handoffs

    mismatch = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "wrong-desktop-state", "handoff_code": handoff_code},
    )
    assert mismatch.status_code == 404
    assert "refresh-token" not in mismatch.text
    assert handoff_hash not in _desktop_handoffs

    now += DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS
    create = client.post(
        "/api/auth/desktop-handoff",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"state": "desktop-state-abcdef", "refresh_token": "refresh-token"},
    )
    handoff_code = create.json()["handoff_code"]
    handoff_hash = _hash_handoff_code(handoff_code)
    assert handoff_hash in _desktop_handoffs
    now += 301

    expired = client.post(
        "/api/auth/desktop-handoff/exchange",
        json={"state": "desktop-state-abcdef", "handoff_code": handoff_code},
    )
    assert expired.status_code == 404
    assert "refresh-token" not in expired.text
    assert handoff_hash not in _desktop_handoffs


def test_desktop_handoff_limits_active_records_per_user(monkeypatch, client: TestClient):
    now = 2000.0
    monkeypatch.setattr("app.api.auth._now", lambda: now)

    created_codes: list[str] = []
    for index in range(DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER):
        response = _create_handoff(client, state=f"desktop-state-limit-{index:02d}")
        assert response.status_code == 200
        created_codes.append(response.json()["handoff_code"])
        now += DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS

    too_many = _create_handoff(client, state="desktop-state-limit-over")
    assert too_many.status_code == 429
    assert too_many.json() == {"detail": "Too many desktop handoff requests."}
    assert all(code not in _desktop_handoffs for code in created_codes)
    assert all(_hash_handoff_code(code) in _desktop_handoffs for code in created_codes)


def test_desktop_handoff_expired_records_are_pruned_before_limit_check(monkeypatch, client: TestClient):
    now = 3000.0
    monkeypatch.setattr("app.api.auth._now", lambda: now)

    for index in range(DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER):
        response = _create_handoff(client, state=f"desktop-state-expired-{index:02d}")
        assert response.status_code == 200
        now += DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS

    now += 301
    response = _create_handoff(client, state="desktop-state-after-expired")
    assert response.status_code == 200
    assert len(_desktop_handoffs) == 1
    assert _hash_handoff_code(response.json()["handoff_code"]) in _desktop_handoffs


def test_desktop_handoff_limits_are_per_user(monkeypatch, client: TestClient):
    now = 4000.0
    monkeypatch.setattr("app.api.auth._now", lambda: now)
    first_user = _token()
    second_user = _token(
        extra_claims={
            "sub": "00000000-0000-4000-8000-000000000002",
            "email": "second@example.com",
        }
    )

    for index in range(DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER):
        response = _create_handoff(client, token=first_user, state=f"desktop-state-user1-{index:02d}")
        assert response.status_code == 200
        now += DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS

    first_blocked = _create_handoff(client, token=first_user, state="desktop-state-user1-over")
    assert first_blocked.status_code == 429

    second_allowed = _create_handoff(client, token=second_user, state="desktop-state-user2-00")
    assert second_allowed.status_code == 200


def test_desktop_handoff_creation_rate_limit_rejects_rapid_repeats(monkeypatch, client: TestClient):
    now = 5000.0
    monkeypatch.setattr("app.api.auth._now", lambda: now)

    first = _create_handoff(client, state="desktop-state-rate-00")
    assert first.status_code == 200

    rapid = _create_handoff(client, state="desktop-state-rate-01")
    assert rapid.status_code == 429
    assert rapid.json() == {"detail": "Too many desktop handoff requests."}
    assert "refresh-token" not in rapid.text

    now += DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS
    later = _create_handoff(client, state="desktop-state-rate-02")
    assert later.status_code == 200
