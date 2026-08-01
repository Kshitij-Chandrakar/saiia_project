import pytest

from app.cloud.supabase_config import (
    CLOUD_MODE_ENV,
    SUPABASE_REQUIRED_ENV_VARS,
    SupabaseConfigurationError,
    get_supabase_config_state,
    get_supabase_settings,
)


@pytest.fixture(autouse=True)
def clear_supabase_env(monkeypatch):
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    yield
    get_supabase_settings.cache_clear()


def test_local_mode_allows_missing_supabase_credentials():
    settings = get_supabase_settings()

    assert settings.mode == "local"
    assert settings.cloud_enabled is False
    assert settings.configured is False
    assert settings.missing_required == ()


def test_cloud_mode_reports_missing_required_names(monkeypatch):
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    get_supabase_settings.cache_clear()

    state = get_supabase_config_state()

    assert state["mode"] == "cloud"
    assert state["configured"] is False
    assert state["missing_required"] == list(SUPABASE_REQUIRED_ENV_VARS)


def test_partial_supabase_env_switches_to_clear_cloud_state(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    get_supabase_settings.cache_clear()

    settings = get_supabase_settings()

    assert settings.cloud_enabled is True
    assert settings.configured is False
    assert "SUPABASE_URL" not in settings.missing_required
    assert "SUPABASE_SERVICE_ROLE_KEY" in settings.missing_required


def test_configured_cloud_state_redacts_secret_values(monkeypatch):
    anon_value = "anon-" + "unit-test-value"
    service_role_value = "service-role-" + "unit-test-value"
    jwt_value = "jwt-" + "unit-test-value"
    values = {
        "SUPABASE_URL": "https://project-ref.supabase.co",
        "SUPABASE_ANON_KEY": anon_value,
        "SUPABASE_SERVICE_ROLE_KEY": service_role_value,
        "SUPABASE_JWT_SECRET_OR_JWKS_CONFIG": jwt_value,
        "SUPABASE_RESUME_BUCKET": "resume-bucket",
        "SUPABASE_EXPORT_BUCKET": "export-bucket",
    }
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_supabase_settings.cache_clear()

    settings = get_supabase_settings()
    state = settings.redacted_state()

    assert settings.configured is True
    assert state["configured"] is True
    assert service_role_value not in repr(settings)
    assert service_role_value not in str(state)
    assert anon_value not in str(state)
    assert jwt_value not in str(state)


def test_require_configured_raises_clear_error_without_secret_values(monkeypatch):
    service_role_value = "service-role-" + "unit-test-value"
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", service_role_value)
    get_supabase_settings.cache_clear()

    with pytest.raises(SupabaseConfigurationError) as exc_info:
        get_supabase_settings().require_configured()

    message = str(exc_info.value)
    assert "SUPABASE_URL" in message
    assert service_role_value not in message
