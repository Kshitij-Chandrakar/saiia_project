import os

import pytest
import requests
from dotenv import load_dotenv


load_dotenv()


_ENABLED_VALUES = {"1", "true", "yes", "on"}

pytestmark = pytest.mark.skipif(
    os.getenv("SAIIA_ENABLE_LIVE_AUTH_SMOKE", "").strip().lower() not in _ENABLED_VALUES,
    reason="live Supabase auth smoke is disabled",
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} is not configured for live Supabase auth smoke")
    return value


def test_live_supabase_access_token_verifies_without_exposing_token():
    supabase_url = _required_env("SUPABASE_URL").rstrip("/")
    anon_key = _required_env("SUPABASE_ANON_KEY")
    email = _required_env("SAIIA_SMOKE_AUTH_EMAIL")
    password = _required_env("SAIIA_SMOKE_AUTH_PASSWORD")
    _required_env("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG")

    from app.auth.supabase_auth import (
        get_auth_verification_config,
        verify_supabase_token,
    )
    from app.cloud.supabase_config import get_supabase_settings

    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()

    response = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={
            "apikey": anon_key,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=15,
    )

    assert response.status_code == 200, (
        "Supabase live auth smoke sign-in failed with "
        f"status {response.status_code}"
    )
    access_token = response.json().get("access_token")
    assert isinstance(access_token, str)
    assert access_token

    user = verify_supabase_token(access_token)

    assert user.user_id
    assert access_token not in repr(user)
