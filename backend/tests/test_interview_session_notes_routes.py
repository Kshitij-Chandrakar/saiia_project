from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview_sessions as interview_sessions_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.interview_notes import CloudInterviewNotesRecord
from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionNotFoundError,
)
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def _notes(**overrides: object) -> CloudInterviewNotesRecord:
    payload = {
        "id": "50000000-0000-4000-8000-000000000001",
        "user_id": TEST_USER_ID,
        "session_id": SESSION_ID,
        "status": "ready",
        "notes_markdown": "# Interview Notes\n\n## Summary\n\nBased on this transcript...\n",
        "summary": "Based on this transcript...",
        "strengths": ["Clear explanations"],
        "improvement_areas": ["More metrics"],
        "technical_topics": ["FastAPI"],
        "key_questions": ["How is authentication implemented?"],
        "suggested_followups": ["Practice architecture tradeoffs"],
        "provider": "openai",
        "model": "gpt-test",
        "generation_ms": 210,
        "transcript_entry_count": 2,
        "generated_at": "2026-08-29T10:30:00Z",
        "created_at": "2026-08-29T10:30:00Z",
        "updated_at": "2026-08-29T10:30:00Z",
    }
    payload.update(overrides)
    return CloudInterviewNotesRecord(**payload)  # type: ignore[arg-type]


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
    interview_sessions_api._cached_cloud_interview_notes_service.cache_clear()


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


class FakeInterviewNotesService:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, object]] = []
        self.generate_calls: list[dict[str, object]] = []

    def get_notes(self, *, user_id: str, session_id: str):
        self.get_calls.append({"user_id": user_id, "session_id": session_id})
        return _notes(user_id=user_id, session_id=session_id)

    def generate_notes(self, *, user_id: str, session_id: str, force_regenerate: bool = False):
        self.generate_calls.append(
            {"user_id": user_id, "session_id": session_id, "force_regenerate": force_regenerate}
        )
        return _notes(user_id=user_id, session_id=session_id)


@pytest.fixture
def fake_service(client: TestClient) -> FakeInterviewNotesService:
    service = FakeInterviewNotesService()
    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_notes_service] = lambda: service
    return service


def test_notes_routes_require_jwt(client: TestClient) -> None:
    response = client.get(f"/api/interview-sessions/{SESSION_ID}/notes")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_get_notes_route_uses_verified_user(client: TestClient, fake_service: FakeInterviewNotesService) -> None:
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/notes",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == SESSION_ID
    assert response.json()["summary"] == "Based on this transcript..."
    assert fake_service.get_calls == [{"user_id": TEST_USER_ID, "session_id": SESSION_ID}]


def test_generate_notes_route_uses_verified_user_and_force_flag(client: TestClient, fake_service: FakeInterviewNotesService) -> None:
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/notes/generate",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"force_regenerate": True, "user_id": "wrong-user"},
    )

    assert response.status_code == 422
    assert fake_service.generate_calls == []

    valid = client.post(
        f"/api/interview-sessions/{SESSION_ID}/notes/generate",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"force_regenerate": True},
    )

    assert valid.status_code == 200
    assert valid.json()["provider"] == "openai"
    assert fake_service.generate_calls == [
        {"user_id": TEST_USER_ID, "session_id": SESSION_ID, "force_regenerate": True}
    ]


def test_generate_notes_triggers_dry_run_email_from_verified_identity(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_service: FakeInterviewNotesService,
) -> None:
    trigger_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        interview_sessions_api,
        "_trigger_feature_email",
        lambda **kwargs: trigger_calls.append(kwargs),
    )

    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/notes/generate",
        headers={"Authorization": f"Bearer {_token()}"},
        json={},
    )

    assert response.status_code == 200
    assert len(trigger_calls) == 1
    assert trigger_calls[0]["session_id"] == SESSION_ID
    assert trigger_calls[0]["current_user"].user_id == TEST_USER_ID  # type: ignore[union-attr]
    assert trigger_calls[0]["current_user"].email == "user@example.com"  # type: ignore[union-attr]
    assert trigger_calls[0]["sender"] is interview_sessions_api.send_ai_notes_ready_email_dry_run
    assert fake_service.generate_calls == [
        {"user_id": TEST_USER_ID, "session_id": SESSION_ID, "force_regenerate": False}
    ]


def test_cross_user_notes_access_is_blocked(client: TestClient) -> None:
    class RaisingNotesService(FakeInterviewNotesService):
        def get_notes(self, *, user_id: str, session_id: str):
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_notes_service] = (
        lambda: RaisingNotesService()
    )
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/notes",
        headers={"Authorization": f"Bearer {_token(subject='another-user')}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session was not found."}


def test_generate_notes_empty_transcript_maps_to_409(client: TestClient) -> None:
    class RaisingNotesService(FakeInterviewNotesService):
        def generate_notes(self, *, user_id: str, session_id: str, force_regenerate: bool = False):
            raise CloudInterviewSessionConflictError("This session does not have transcript entries yet.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_notes_service] = (
        lambda: RaisingNotesService()
    )
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/notes/generate",
        headers={"Authorization": f"Bearer {_token()}"},
        json={},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This session does not have transcript entries yet."}
