from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview_sessions as interview_sessions_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.interview_sessions import (
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionValidationError,
)
from app.cloud.interview_transcripts import (
    CloudInterviewTranscriptEntryRecord,
    CreateInterviewTranscriptEntryResult,
    InterviewTranscriptEntryListPage,
)
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def _entry(**overrides: object) -> CloudInterviewTranscriptEntryRecord:
    payload = {
        "id": "40000000-0000-4000-8000-000000000001",
        "user_id": TEST_USER_ID,
        "session_id": SESSION_ID,
        "turn_index": 1,
        "source": "chat",
        "question_text": "What is FastAPI authentication?",
        "answer_text": "It uses dependency-based auth checks.",
        "category": "technical",
        "provider": "openai",
        "model": "gpt-test",
        "generation_ms": 123,
        "created_at": "2026-08-29T10:30:00Z",
    }
    payload.update(overrides)
    return CloudInterviewTranscriptEntryRecord(**payload)  # type: ignore[arg-type]


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
    interview_sessions_api._cached_cloud_interview_transcript_service.cache_clear()


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
    app.dependency_overrides[interview_sessions_api.get_cloud_interview_session_service] = (
        lambda: FakeInterviewSessionService()
    )
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


class FakeTranscriptService:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.export_calls: list[dict[str, object]] = []

    def create_transcript_entry(self, *, user_id: str, session_id: str, payload: dict):
        self.create_calls.append({"user_id": user_id, "session_id": session_id, "payload": payload})
        return CreateInterviewTranscriptEntryResult(record=_entry(session_id=session_id, user_id=user_id), replayed=False)

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int):
        self.list_calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "page": page})
        return InterviewTranscriptEntryListPage(
            items=[_entry(session_id=session_id, user_id=user_id)],
            limit=limit,
            page=page,
        )

    def export_transcript(self, *, user_id: str, session_id: str, format: str):
        self.export_calls.append({"user_id": user_id, "session_id": session_id, "format": format})
        if format not in {"txt", "md"}:
            raise CloudInterviewSessionValidationError("format must be txt or md.")
        return "Interview Transcript\n"


class FakeInterviewSessionService:
    def get_session(self, *, user_id: str, session_id: str):
        return object()


@pytest.fixture
def fake_service(client: TestClient) -> FakeTranscriptService:
    service = FakeTranscriptService()
    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_transcript_service] = lambda: service
    return service


def test_transcript_routes_require_jwt(client: TestClient) -> None:
    response = client.get(f"/api/interview-sessions/{SESSION_ID}/transcript-entries")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_create_transcript_route_uses_verified_user(client: TestClient, fake_service: FakeTranscriptService) -> None:
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/transcript-entries",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "request_id": "turn-1",
            "question_text": "What is FastAPI authentication?",
            "answer_text": "It uses dependency-based auth checks.",
            "source": "chat",
            "category": "technical",
            "user_id": "wrong-user",
        },
    )

    assert response.status_code == 422
    assert fake_service.create_calls == []

    valid = client.post(
        f"/api/interview-sessions/{SESSION_ID}/transcript-entries",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "request_id": "turn-1",
            "question_text": "What is FastAPI authentication?",
            "answer_text": "It uses dependency-based auth checks.",
            "source": "chat",
            "category": "technical",
        },
    )

    assert valid.status_code == 201
    assert fake_service.create_calls == [
        {
            "user_id": TEST_USER_ID,
            "session_id": SESSION_ID,
            "payload": {
                "request_id": "turn-1",
                "source": "chat",
                "question_text": "What is FastAPI authentication?",
                "answer_text": "It uses dependency-based auth checks.",
                "category": "technical",
                "provider": "",
                "model": "",
                "metadata": {},
            },
        }
    ]


def test_list_and_download_transcript_routes_are_user_owned(client: TestClient, fake_service: FakeTranscriptService) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    listing = client.get(f"/api/interview-sessions/{SESSION_ID}/transcript-entries?limit=10&page=2", headers=headers)
    markdown = client.get(f"/api/interview-sessions/{SESSION_ID}/transcript/download?format=md", headers=headers)
    text = client.get(f"/api/interview-sessions/{SESSION_ID}/transcript/download?format=txt", headers=headers)

    assert listing.status_code == 200
    assert listing.json()["items"][0]["session_id"] == SESSION_ID
    assert listing.json()["items"][0]["question_text"] == "What is FastAPI authentication?"
    assert fake_service.list_calls == [{"user_id": TEST_USER_ID, "session_id": SESSION_ID, "limit": 10, "page": 2}]
    assert markdown.status_code == 200
    assert markdown.headers["content-disposition"] == 'attachment; filename="interview-session-transcript.md"'
    assert text.status_code == 200
    assert text.headers["content-disposition"] == 'attachment; filename="interview-session-transcript.txt"'
    assert fake_service.export_calls == [
        {"user_id": TEST_USER_ID, "session_id": SESSION_ID, "format": "md"},
        {"user_id": TEST_USER_ID, "session_id": SESSION_ID, "format": "txt"},
    ]


def test_transcript_export_triggers_dry_run_email_after_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_service: FakeTranscriptService,
) -> None:
    trigger_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        interview_sessions_api,
        "_trigger_feature_email",
        lambda **kwargs: trigger_calls.append(kwargs),
    )

    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/transcript/download?format=md",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 200
    assert len(trigger_calls) == 1
    assert trigger_calls[0]["session_id"] == SESSION_ID
    assert trigger_calls[0]["current_user"].user_id == TEST_USER_ID  # type: ignore[union-attr]
    assert trigger_calls[0]["current_user"].email == "user@example.com"  # type: ignore[union-attr]
    assert trigger_calls[0]["sender"] is interview_sessions_api.send_transcript_export_email_dry_run


def test_cross_user_transcript_export_does_not_trigger_email(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    trigger_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        interview_sessions_api,
        "_trigger_feature_email",
        lambda **kwargs: trigger_calls.append(kwargs),
    )

    class RaisingSessionService:
        def get_session(self, *, user_id: str, session_id: str):
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_session_service] = (
        lambda: RaisingSessionService()
    )

    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/transcript/download?format=txt",
        headers={"Authorization": f"Bearer {_token(subject='another-user')}"},
    )

    assert response.status_code == 404
    assert trigger_calls == []


def test_cross_user_transcript_access_is_blocked(client: TestClient) -> None:
    class RaisingTranscriptService(FakeTranscriptService):
        def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int):
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_transcript_service] = (
        lambda: RaisingTranscriptService()
    )
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/transcript-entries",
        headers={"Authorization": f"Bearer {_token(subject='another-user')}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session was not found."}


def test_invalid_transcript_download_format_is_rejected(client: TestClient, fake_service: FakeTranscriptService) -> None:
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/transcript/download?format=pdf",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "format must be txt or md."}
    assert fake_service.export_calls == [{"user_id": TEST_USER_ID, "session_id": SESSION_ID, "format": "pdf"}]
