from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import resumes as resumes_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.cloud_resume import CloudResumeRecord
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


def _record(**overrides: object) -> CloudResumeRecord:
    payload = {
        "id": "10000000-0000-4000-8000-000000000001",
        "user_id": TEST_USER_ID,
        "storage_path": f"{TEST_USER_ID}/10000000-0000-4000-8000-000000000001/resume.txt",
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
    return TestClient(app)


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
            status = "needs_review"
            confirmed_profile_saved = True
            next_step = "index_resume"

        result = Result()
        result.resume_id = resume_id
        result.extraction_attempt = extraction_attempt
        return result


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> FakeRouteService:
    service = FakeRouteService()
    monkeypatch.setattr(resumes_api, "get_cloud_resume_service", lambda: service)
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


def test_review_candidate_route_is_separate_from_current(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/review-candidate", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json()["has_candidate"] is True
    assert response.json()["resume"]["status"] == "needs_review"


def test_status_extract_and_confirm_are_user_owned(client: TestClient, fake_service: FakeRouteService) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    status_response = client.get("/api/resumes/resume-id/status", headers=headers)
    extract_response = client.post("/api/resumes/resume-id/extract", headers=headers)
    confirm_response = client.post(
        "/api/resumes/resume-id/confirm",
        headers=headers,
        json={"extraction_attempt": 1, "profile": {"full_name": "Test User"}},
    )

    assert status_response.status_code == 200
    assert extract_response.status_code == 200
    assert confirm_response.status_code == 200
    assert fake_service.user_ids == [TEST_USER_ID, TEST_USER_ID, TEST_USER_ID]
    assert fake_service.confirm_payloads == [{"full_name": "Test User"}]
    assert confirm_response.json()["status"] == "needs_review"


def test_invalid_token_rejected_before_service_call(client: TestClient, fake_service: FakeRouteService) -> None:
    response = client.get("/api/resumes/current", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert fake_service.user_ids == []
