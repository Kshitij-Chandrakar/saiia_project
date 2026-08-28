from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview_sessions as interview_sessions_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionRecord,
    CloudInterviewSessionValidationError,
    CreateInterviewSessionResult,
    InterviewSessionListPage,
)
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def _record(**overrides: object) -> CloudInterviewSessionRecord:
    payload = {
        "id": SESSION_ID,
        "user_id": TEST_USER_ID,
        "selected_resume_id": "20000000-0000-4000-8000-000000000001",
        "job_context_id": "20000000-0000-4000-8000-000000000002",
        "title": "Design interview",
        "target_role": "Frontend Engineer",
        "company_name": "Acme",
        "job_description_preview": "Safe preview only",
        "status": "active",
        "started_at": "2026-08-28T00:00:00Z",
        "ended_at": None,
        "created_at": "2026-08-28T00:00:00Z",
        "updated_at": "2026-08-28T00:00:00Z",
    }
    payload.update(overrides)
    return CloudInterviewSessionRecord(**payload)  # type: ignore[arg-type]


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
    interview_sessions_api._cached_cloud_interview_session_service.cache_clear()


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
    app.include_router(interview_sessions_api.router, prefix="/api/interview-sessions")
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


class FakeInterviewSessionService:
    def __init__(self) -> None:
        self.user_ids: list[str] = []
        self.idempotency_keys: list[str | None] = []
        self.last_create_payload: dict | None = None

    def list_sessions(self, *, user_id: str, limit: int, page: int):
        self.user_ids.append(user_id)
        return InterviewSessionListPage(items=[_record(user_id=user_id)], limit=limit, page=page)

    def create_session(self, *, user_id: str, payload: dict, idempotency_key: str | None):
        self.user_ids.append(user_id)
        self.idempotency_keys.append(idempotency_key)
        self.last_create_payload = payload
        return CreateInterviewSessionResult(record=_record(user_id=user_id), replayed=False)

    def get_session(self, *, user_id: str, session_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=session_id)

    def end_session(self, *, user_id: str, session_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=session_id, status="ended", ended_at="2026-08-28T00:15:00Z")


@pytest.fixture
def fake_service(client: TestClient) -> FakeInterviewSessionService:
    service = FakeInterviewSessionService()
    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_session_service] = lambda: service
    return service


def test_interview_session_routes_require_jwt(client: TestClient) -> None:
    response = client.get("/api/interview-sessions")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_create_requires_idempotency_key_and_uses_verified_user(client: TestClient, fake_service: FakeInterviewSessionService) -> None:
    payload = {
        "title": "Design interview",
        "target_role": "Frontend Engineer",
        "company_name": "Acme",
        "job_description": "long job description that should not be returned",
    }

    missing = client.post("/api/interview-sessions", headers={"Authorization": f"Bearer {_token()}"}, json=payload)
    response = client.post(
        "/api/interview-sessions",
        headers={"Authorization": f"Bearer {_token()}", "Idempotency-Key": "session:1"},
        json={**payload, "user_id": "11111111-1111-4111-8111-111111111111"},
    )

    assert missing.status_code == 400
    assert response.status_code == 422
    assert fake_service.user_ids == []

    valid = client.post(
        "/api/interview-sessions",
        headers={"Authorization": f"Bearer {_token()}", "Idempotency-Key": "session:2"},
        json=payload,
    )
    assert valid.status_code == 201
    assert fake_service.user_ids == [TEST_USER_ID]
    assert fake_service.idempotency_keys == ["session:2"]
    assert fake_service.last_create_payload == payload
    assert "job_description" not in valid.json()["session"]


def test_list_detail_and_end_are_user_owned(client: TestClient, fake_service: FakeInterviewSessionService) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    listing = client.get("/api/interview-sessions?limit=10&page=2", headers=headers)
    detail = client.get(f"/api/interview-sessions/{SESSION_ID}", headers=headers)
    ended = client.post(f"/api/interview-sessions/{SESSION_ID}/end", headers=headers)

    assert listing.status_code == 200
    assert listing.json()["limit"] == 10
    assert listing.json()["page"] == 2
    assert listing.json()["items"][0]["company_name"] == "Acme"
    assert detail.status_code == 200
    assert detail.json()["id"] == SESSION_ID
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert ended.json()["ended_at"] == "2026-08-28T00:15:00Z"
    assert fake_service.user_ids == [TEST_USER_ID, TEST_USER_ID, TEST_USER_ID]


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_detail"),
    [
        (CloudInterviewSessionValidationError("bad request"), 400, "bad request"),
        (CloudInterviewSessionNotFoundError("Interview session was not found."), 404, "Interview session was not found."),
        (CloudInterviewSessionConflictError("stale"), 409, "stale"),
        (TypeError("boom"), 502, "Supabase cloud interview session operation failed."),
    ],
)
def test_interview_session_error_mapping(
    client: TestClient,
    exc: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    class RaisingService(FakeInterviewSessionService):
        def list_sessions(self, *, user_id: str, limit: int, page: int):
            raise exc

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_session_service] = lambda: RaisingService()

    response = client.get("/api/interview-sessions", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
