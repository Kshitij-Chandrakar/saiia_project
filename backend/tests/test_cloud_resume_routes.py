from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import resumes as resumes_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeError,
    CloudResumeNotFoundError,
    CloudResumeRecord,
    CloudResumeValidationError,
)
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
RESUME_ID = "10000000-0000-4000-8000-000000000001"


def _record(**overrides: object) -> CloudResumeRecord:
    payload = {
        "id": RESUME_ID,
        "user_id": TEST_USER_ID,
        "storage_path": f"{TEST_USER_ID}/{RESUME_ID}/resume.txt",
        "original_filename": "resume.txt",
        "mime_type": "text/plain",
        "file_size": 12,
        "status": "uploaded",
        "is_active": False,
        "extraction_attempt": 0,
    }
    payload.update(overrides)
    return CloudResumeRecord(**payload)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def clear_supabase_auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    yield
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    resumes_api._cached_cloud_resume_service.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
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
    app.include_router(resumes_api.router, prefix="/api/resumes")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _token(*, subject: str = TEST_USER_ID, secret: str = TEST_SECRET) -> str:
    return jwt.encode(
        {
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
            "sub": subject,
            "email": "user@example.com",
            "role": "authenticated",
        },
        secret,
        algorithm="HS256",
    )


class FakeRouteService:
    def __init__(self) -> None:
        self.user_ids: list[str] = []
        self.confirm_payloads: list[dict[str, Any]] = []

    def upload_resume(self, *, user_id: str, filename: str, content: bytes, content_type: str | None):
        self.user_ids.append(user_id)

        class Result:
            resume = _record(user_id=user_id, original_filename=filename, file_size=len(content))

        return Result()

    def get_current_resume(self, user_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, status="ready", is_active=True)

    def get_review_candidate(self, user_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, status="needs_review")

    def get_status(self, *, user_id: str, resume_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=resume_id)

    def extract_resume(self, *, user_id: str, resume_id: str):
        self.user_ids.append(user_id)

        class Result:
            status = "needs_review"
            extraction_attempt = 1
            parser_provider = "local"
            fallback_used = False
            missing_fields: list[str] = []
            review_required = False
            profile = {"full_name": "Test User"}
            extracted_text_length = 12

        result = Result()
        result.resume_id = resume_id
        return result

    def confirm_resume(self, *, user_id: str, resume_id: str, extraction_attempt: int, confirmed_profile: dict[str, Any]):
        self.user_ids.append(user_id)
        self.confirm_payloads.append(confirmed_profile)

        class Result:
            status = "ready"
            confirmed_profile_saved = True
            next_step = "resume_ready"
            chunks_indexed = True
            chunk_count = 1
            ready = True
            active = True

        result = Result()
        result.resume_id = resume_id
        result.extraction_attempt = extraction_attempt
        return result


@pytest.fixture
def fake_service(client: TestClient) -> FakeRouteService:
    service = FakeRouteService()
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: service
    return service


def test_cloud_resume_routes_require_jwt(client: TestClient) -> None:
    response = client.get("/api/resumes/current")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_upload_route_derives_user_id_from_token_only(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.post(
        "/api/resumes",
        headers={"Authorization": f"Bearer {_token()}"},
        files={"file": ("resume.txt", b"resume bytes", "text/plain")},
        data={"user_id": "11111111-1111-4111-8111-111111111111"},
    )

    assert response.status_code == 201
    assert fake_service.user_ids == [TEST_USER_ID]
    assert response.json()["is_active"] is False
    assert "service-role-unit-test-value" not in response.text


def test_current_route_returns_safe_ready_state(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/current", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["resume"]["status"] == "ready"


def test_current_route_returns_ready_false_before_activation(client: TestClient) -> None:
    class NoCurrentService(FakeRouteService):
        def get_current_resume(self, user_id: str):
            self.user_ids.append(user_id)
            return None

    service = NoCurrentService()
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: service

    response = client.get("/api/resumes/current", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json() == {"ready": False, "resume": None}
    assert service.user_ids == [TEST_USER_ID]


def test_review_candidate_route_returns_empty_state_when_no_candidate(client: TestClient) -> None:
    class NoCandidateService(FakeRouteService):
        def get_review_candidate(self, user_id: str):
            self.user_ids.append(user_id)
            return None

    service = NoCandidateService()
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: service

    response = client.get("/api/resumes/review-candidate", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json() == {"has_candidate": False, "resume": None}
    assert service.user_ids == [TEST_USER_ID]


def test_review_candidate_route_is_separate_from_current(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/review-candidate", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json()["has_candidate"] is True
    assert response.json()["resume"]["status"] == "needs_review"


def test_review_candidate_route_returns_empty_after_confirmed_state(client: TestClient) -> None:
    class ConfirmedCandidateService(FakeRouteService):
        def __init__(self) -> None:
            super().__init__()
            self.confirmed = False

        def get_review_candidate(self, user_id: str):
            self.user_ids.append(user_id)
            if not self.confirmed:
                return _record(user_id=user_id, status="needs_review")
            return None

        def confirm_resume(
            self,
            *,
            user_id: str,
            resume_id: str,
            extraction_attempt: int,
            confirmed_profile: dict[str, Any],
        ):
            self.confirmed = True
            return super().confirm_resume(
                user_id=user_id,
                resume_id=resume_id,
                extraction_attempt=extraction_attempt,
                confirmed_profile=confirmed_profile,
            )

    service = ConfirmedCandidateService()
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: service

    headers = {"Authorization": f"Bearer {_token()}"}
    before = client.get("/api/resumes/review-candidate", headers=headers)
    confirm = client.post(
        f"/api/resumes/{RESUME_ID}/confirm",
        headers=headers,
        json={"extraction_attempt": 1, "profile": {"full_name": "Confirmed"}},
    )
    response = client.get("/api/resumes/review-candidate", headers=headers)

    assert before.status_code == 200
    assert before.json()["has_candidate"] is True
    assert confirm.status_code == 200
    assert response.status_code == 200
    assert response.json() == {"has_candidate": False, "resume": None}


def test_status_extract_and_confirm_are_user_owned(client: TestClient, fake_service: FakeRouteService) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    status_response = client.get(f"/api/resumes/{RESUME_ID}/status", headers=headers)
    extract_response = client.post(f"/api/resumes/{RESUME_ID}/extract", headers=headers)
    confirm_response = client.post(
        f"/api/resumes/{RESUME_ID}/confirm",
        headers=headers,
        json={"extraction_attempt": 1, "profile": {"full_name": "Test User"}},
    )

    assert status_response.status_code == 200
    assert extract_response.status_code == 200
    assert confirm_response.status_code == 200
    assert fake_service.user_ids == [TEST_USER_ID, TEST_USER_ID, TEST_USER_ID]
    assert fake_service.confirm_payloads == [{"full_name": "Test User"}]
    assert confirm_response.json()["status"] == "ready"
    assert confirm_response.json()["ready"] is True
    assert confirm_response.json()["active"] is True
    assert confirm_response.json()["chunks_indexed"] is True
    assert confirm_response.json()["chunk_count"] == 1


def test_confirm_activation_conflict_returns_safe_409(client: TestClient) -> None:
    class ConfirmConflictService(FakeRouteService):
        def confirm_resume(
            self,
            *,
            user_id: str,
            resume_id: str,
            extraction_attempt: int,
            confirmed_profile: dict[str, Any],
        ):
            self.user_ids.append(user_id)
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")

    service = ConfirmConflictService()
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: service

    response = client.post(
        f"/api/resumes/{RESUME_ID}/confirm",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"extraction_attempt": 1, "profile": {"full_name": "Test User"}},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Resume state changed. Please refresh and try again."}
    assert "service-role-unit-test-value" not in response.text


def test_malformed_resume_id_returns_422_before_service_call(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/not-a-uuid/status", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 422
    assert fake_service.user_ids == []


def test_invalid_token_rejected_before_service_call(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/current", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert fake_service.user_ids == []


class RaisingRouteService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def get_status(self, *, user_id: str, resume_id: str):
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_detail"),
    [
        (CloudResumeValidationError("bad upload"), 400, "bad upload"),
        (CloudResumeNotFoundError("missing"), 404, "Resume was not found."),
        (CloudResumeConflictError("stale"), 409, "stale"),
        (SupabaseConfigurationError("missing config"), 503, "Supabase cloud configuration is not ready."),
        (TypeError("boom"), 502, "Supabase cloud resume operation failed."),
    ],
)
def test_cloud_resume_route_error_mapping(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    exc: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: RaisingRouteService(exc)

    with caplog.at_level("ERROR", logger="cloud_resume_api"):
        response = client.get(f"/api/resumes/{RESUME_ID}/status", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    if isinstance(exc, TypeError):
        assert "Unexpected cloud resume route failure" in caplog.text
    else:
        assert "Unexpected cloud resume route failure" not in caplog.text


def test_other_users_resume_maps_to_404(client: TestClient) -> None:
    client.app.dependency_overrides[resumes_api.get_cloud_resume_service] = lambda: RaisingRouteService(
        CloudResumeNotFoundError("not owned")
    )

    response = client.get(f"/api/resumes/{RESUME_ID}/status", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Resume was not found."}
