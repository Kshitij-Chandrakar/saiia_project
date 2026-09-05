import logging

import pytest

from app.cloud.profile_bootstrap import (
    ProfileConsent,
    SupabaseProfileBootstrapError,
    SupabaseRestClient,
    bootstrap_authenticated_profile,
)
from app.cloud.supabase_config import (
    CLOUD_MODE_ENV,
    SUPABASE_REQUIRED_ENV_VARS,
    SupabaseConfigurationError,
    get_supabase_settings,
)


TEST_USER_ID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def clear_supabase_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    yield
    get_supabase_settings.cache_clear()


class FakeBootstrapClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.rows = set(existing or set())
        self.inserts: list[tuple[str, str]] = []
        self.consent_updates: list[tuple[str, ProfileConsent]] = []
        self.consent_schema_checks = 0

    def ensure_consent_schema(self) -> None:
        self.consent_schema_checks += 1

    def row_exists(self, table: str, user_id: str) -> bool:
        return (table, user_id) in self.rows

    def insert_user_row(self, table: str, user_id: str) -> bool:
        self.inserts.append((table, user_id))
        if (table, user_id) in self.rows:
            return False
        self.rows.add((table, user_id))
        return True

    def update_user_settings_consent(self, user_id: str, consent: ProfileConsent) -> None:
        self.consent_updates.append((user_id, consent))


class ConflictThenVisibleClient:
    def __init__(self) -> None:
        self.exists_checks: dict[str, int] = {}
        self.inserts: list[tuple[str, str]] = []

    def row_exists(self, table: str, user_id: str) -> bool:
        self.exists_checks[table] = self.exists_checks.get(table, 0) + 1
        return self.exists_checks[table] > 1

    def insert_user_row(self, table: str, user_id: str) -> bool:
        self.inserts.append((table, user_id))
        return False


class ConflictStillMissingClient(ConflictThenVisibleClient):
    def row_exists(self, table: str, user_id: str) -> bool:
        self.exists_checks[table] = self.exists_checks.get(table, 0) + 1
        return False


class FakeResponse:
    def __init__(self, status_code: int, data: object, text: str = "") -> None:
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self) -> object:
        return self._data


class FakeRestSession:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []
        self.patch_calls: list[dict[str, object]] = []
        self.get_response = FakeResponse(200, [])
        self.post_response = FakeResponse(201, [{"id": "profile-id"}])
        self.patch_response = FakeResponse(204, [])

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return self.get_response

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self.post_response

    def patch(self, url: str, **kwargs: object) -> FakeResponse:
        self.patch_calls.append({"url": url, **kwargs})
        return self.patch_response


def _rest_client(session: FakeRestSession, service_role_key: str = "service-role-unit-test-value") -> SupabaseRestClient:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://project-ref.supabase.co/rest/v1"
    client._service_role_key = service_role_key
    client._session = session
    client._headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return client


def test_bootstrap_creates_profile_and_settings_when_missing() -> None:
    client = FakeBootstrapClient()

    result = bootstrap_authenticated_profile(TEST_USER_ID, client=client)

    assert result.user_id == TEST_USER_ID
    assert result.profile_exists is True
    assert result.profile_created is True
    assert result.settings_exists is True
    assert result.settings_created is True
    assert result.next_step == "profile_setup"
    assert client.inserts == [
        ("profiles", TEST_USER_ID),
        ("user_settings", TEST_USER_ID),
    ]


def test_bootstrap_is_idempotent_for_repeated_calls() -> None:
    client = FakeBootstrapClient()

    first = bootstrap_authenticated_profile(TEST_USER_ID, client=client)
    second = bootstrap_authenticated_profile(TEST_USER_ID, client=client)

    assert first.profile_created is True
    assert first.settings_created is True
    assert second.profile_created is False
    assert second.settings_created is False
    assert client.inserts == [
        ("profiles", TEST_USER_ID),
        ("user_settings", TEST_USER_ID),
    ]


def test_bootstrap_reuses_existing_profile_and_settings() -> None:
    client = FakeBootstrapClient(
        {
            ("profiles", TEST_USER_ID),
            ("user_settings", TEST_USER_ID),
        }
    )

    result = bootstrap_authenticated_profile(TEST_USER_ID, client=client)

    assert result.profile_exists is True
    assert result.profile_created is False
    assert result.settings_exists is True
    assert result.settings_created is False
    assert client.inserts == []


def test_bootstrap_persists_consent_for_verified_user_only() -> None:
    client = FakeBootstrapClient()
    consent = ProfileConsent(
        terms_accepted=True,
        privacy_accepted=True,
        marketing_email_opt_in=True,
        consent_source="signup",
        consent_version="c10.6a-v1",
    )

    bootstrap_authenticated_profile(TEST_USER_ID, client=client, consent=consent)

    assert client.consent_updates == [(TEST_USER_ID, consent)]
    assert client.consent_schema_checks == 1


def test_consent_bootstrap_fails_before_partial_mutation_when_schema_is_missing() -> None:
    class MissingConsentSchemaClient(FakeBootstrapClient):
        def ensure_consent_schema(self) -> None:
            raise SupabaseProfileBootstrapError("consent columns are missing")

    client = MissingConsentSchemaClient()

    with pytest.raises(SupabaseProfileBootstrapError):
        bootstrap_authenticated_profile(
            TEST_USER_ID,
            client=client,
            consent=ProfileConsent(True, True, None),
        )

    assert client.inserts == []
    assert client.consent_updates == []


def test_bootstrap_re_reads_after_conflict_and_accepts_visible_row() -> None:
    client = ConflictThenVisibleClient()

    result = bootstrap_authenticated_profile(TEST_USER_ID, client=client)

    assert result.profile_exists is True
    assert result.profile_created is False
    assert result.settings_exists is True
    assert result.settings_created is False
    assert client.inserts == [
        ("profiles", TEST_USER_ID),
        ("user_settings", TEST_USER_ID),
    ]
    assert client.exists_checks == {"profiles": 2, "user_settings": 2}


def test_bootstrap_raises_when_conflict_row_is_still_missing() -> None:
    client = ConflictStillMissingClient()

    with pytest.raises(SupabaseProfileBootstrapError):
        bootstrap_authenticated_profile(TEST_USER_ID, client=client)
    assert client.exists_checks["profiles"] == 2


def test_supabase_rest_insert_headers_and_payload_match_schema() -> None:
    session = FakeRestSession()
    client = _rest_client(session)

    created = client.insert_user_row("profiles", TEST_USER_ID)

    assert created is True
    call = session.post_calls[0]
    assert call["json"] == {"user_id": TEST_USER_ID}
    assert call["params"] == {"on_conflict": "user_id"}
    assert call["timeout"] == 10
    headers = call["headers"]
    assert headers["apikey"] == "service-role-unit-test-value"
    assert headers["Authorization"] == "Bearer service-role-unit-test-value"
    assert headers["Content-Type"] == "application/json"
    assert headers["Prefer"] == "resolution=ignore-duplicates,return=representation"


def test_supabase_rest_consent_update_uses_verified_user_id_and_safe_fields() -> None:
    session = FakeRestSession()
    client = _rest_client(session)
    consent = ProfileConsent(True, True, True, "signup", "c10.6a-v1")

    client.update_user_settings_consent(TEST_USER_ID, consent)

    call = session.patch_calls[0]
    assert call["params"] == {"user_id": f"eq.{TEST_USER_ID}"}
    assert call["json"]["terms_accepted"] is True
    assert call["json"]["privacy_accepted"] is True
    assert call["json"]["marketing_email_opt_in"] is True
    assert call["json"]["marketing_email_opt_in_at"]
    assert call["json"]["marketing_email_opt_out_at"] is None
    assert call["json"]["consent_source"] == "signup"
    assert call["json"]["consent_version"] == "c10.6a-v1"
    assert "user_id" not in call["json"]
    assert "email" not in call["json"]


def test_supabase_rest_consent_update_records_opt_out_and_clears_opt_in_timestamp() -> None:
    session = FakeRestSession()
    client = _rest_client(session)

    client.update_user_settings_consent(TEST_USER_ID, ProfileConsent(True, True, False))

    payload = session.patch_calls[0]["json"]
    assert payload["marketing_email_opt_in"] is False
    assert payload["marketing_email_opt_in_at"] is None
    assert payload["marketing_email_opt_out_at"]


def test_supabase_rest_consent_update_omits_marketing_fields_when_not_supplied() -> None:
    session = FakeRestSession()
    client = _rest_client(session)

    client.update_user_settings_consent(TEST_USER_ID, ProfileConsent(True, True, None))

    payload = session.patch_calls[0]["json"]
    assert "marketing_email_opt_in" not in payload
    assert "marketing_email_opt_in_at" not in payload
    assert "marketing_email_opt_out_at" not in payload


def test_consent_schema_check_precedes_profile_and_settings_mutations() -> None:
    session = FakeRestSession()
    session.get_response = FakeResponse(400, {"message": "missing consent column"})
    client = _rest_client(session)

    with pytest.raises(SupabaseProfileBootstrapError):
        bootstrap_authenticated_profile(
            TEST_USER_ID,
            client=client,
            consent=ProfileConsent(True, True, False),
        )

    assert session.post_calls == []
    assert session.patch_calls == []
    assert session.get_calls[0]["params"]["limit"] == "0"


def test_supabase_rest_client_rejects_anon_key_reused_as_service_role(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reused_key = "anon-unit-test-value"
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", reused_key)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", reused_key)
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", "unit-test-jwt-secret")
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()

    with caplog.at_level(logging.ERROR, logger="supabase_profile_bootstrap"):
        with pytest.raises(SupabaseConfigurationError):
            SupabaseRestClient()

    assert "SUPABASE_SERVICE_ROLE_KEY matches SUPABASE_ANON_KEY" in caplog.text
    assert reused_key not in caplog.text


def test_supabase_rest_select_failure_logs_sanitized_context(caplog: pytest.LogCaptureFixture) -> None:
    service_role_key = "service-role-unit-test-value"
    session = FakeRestSession()
    session.get_response = FakeResponse(
        401,
        {"message": "invalid key"},
        f'{{"message":"invalid key {service_role_key}"}}',
    )
    client = _rest_client(session, service_role_key=service_role_key)

    with caplog.at_level(logging.ERROR, logger="supabase_profile_bootstrap"):
        with pytest.raises(SupabaseProfileBootstrapError):
            client.row_exists("profiles", TEST_USER_ID)

    log_text = caplog.text
    assert "table=profiles" in log_text
    assert "operation=select" in log_text
    assert "status=401" in log_text
    assert "invalid key [redacted]" in log_text
    assert service_role_key not in log_text


def test_supabase_rest_upsert_failure_logs_sanitized_context(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeRestSession()
    session.post_response = FakeResponse(400, {"message": "bad payload"}, '{"message":"bad payload"}')
    client = _rest_client(session)

    with caplog.at_level(logging.ERROR, logger="supabase_profile_bootstrap"):
        with pytest.raises(SupabaseProfileBootstrapError):
            client.insert_user_row("user_settings", TEST_USER_ID)

    assert "table=user_settings" in caplog.text
    assert "operation=upsert" in caplog.text
    assert "status=400" in caplog.text
    assert "bad payload" in caplog.text
