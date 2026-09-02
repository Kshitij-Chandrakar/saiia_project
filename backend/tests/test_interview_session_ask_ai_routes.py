from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview_sessions as interview_sessions_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.interview_ask_ai import (
    ASK_AI_FAILURE_MESSAGE,
    AskAIContextUsed,
    AskAIResult,
    CloudInterviewAskAIMessageRecord,
    InterviewAskAIMessageListPage,
)
from app.cloud.interview_sessions import CloudInterviewSessionConflictError, CloudInterviewSessionError, CloudInterviewSessionNotFoundError
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def _message(index: int, role: str, text: str, **overrides: object) -> CloudInterviewAskAIMessageRecord:
    payload = {
        "id": f"60000000-0000-4000-8000-00000000000{index}",
        "user_id": TEST_USER_ID,
        "session_id": SESSION_ID,
        "role": role,
        "message_text": text,
        "turn_index": index,
        "provider": "openai" if role == "assistant" else None,
        "model": "gpt-test" if role == "assistant" else None,
        "generation_ms": 100 if role == "assistant" else None,
        "created_at": "2026-09-01T10:15:00Z",
    }
    payload.update(overrides)
    return CloudInterviewAskAIMessageRecord(**payload)  # type: ignore[arg-type]


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
    interview_sessions_api._cached_cloud_interview_ask_ai_service.cache_clear()


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


class FakeAskAIService:
    def __init__(self) -> None:
        self.ask_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []

    def list_messages(self, *, user_id: str, session_id: str, limit: int, page: int):
        self.list_calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "page": page})
        return InterviewAskAIMessageListPage(
            items=[_message(1, "user", "What should I improve?", user_id=user_id, session_id=session_id)],
            limit=limit,
            page=page,
            has_more=True,
            next_page=page + 1,
        )

    def ask_ai(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        request_id: str | None = None,
        include_notes: bool = True,
    ):
        self.ask_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "question": question,
                "request_id": request_id,
                "include_notes": include_notes,
            }
        )
        user_message = _message(1, "user", question, user_id=user_id, session_id=session_id)
        assistant_message = _message(
            2,
            "assistant",
            "Based on this transcript, improve specificity.",
            user_id=user_id,
            session_id=session_id,
        )
        return AskAIResult(
            user_message=user_message,
            assistant_message=assistant_message,
            answer_text=assistant_message.message_text,
            provider="openai",
            model="gpt-test",
            generation_ms=100,
            context_used=AskAIContextUsed(
                transcript_entry_count=2,
                notes_used=True,
                recent_message_count=0,
            ),
        )


@pytest.fixture
def fake_service(client: TestClient) -> FakeAskAIService:
    service = FakeAskAIService()
    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_ask_ai_service] = lambda: service
    return service


def test_ask_ai_routes_require_jwt(client: TestClient) -> None:
    response = client.get(f"/api/interview-sessions/{SESSION_ID}/ask-ai/messages")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_list_ask_ai_messages_uses_verified_user(client: TestClient, fake_service: FakeAskAIService) -> None:
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai/messages?limit=10&page=2",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["message_text"] == "What should I improve?"
    assert response.json()["has_more"] is True
    assert response.json()["next_page"] == 3
    assert fake_service.list_calls == [{"user_id": TEST_USER_ID, "session_id": SESSION_ID, "limit": 10, "page": 2}]


def test_ask_ai_post_uses_verified_user_and_rejects_body_user_id(
    client: TestClient,
    fake_service: FakeAskAIService,
) -> None:
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"question": "What should I improve?", "user_id": "wrong-user"},
    )

    assert response.status_code == 422
    assert fake_service.ask_calls == []

    valid = client.post(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"question": "What should I improve?", "request_id": "ask-1", "include_notes": False},
    )

    assert valid.status_code == 200
    assert valid.json()["answer_text"] == "Based on this transcript, improve specificity."
    assert valid.json()["context_used"] == {
        "transcript_entry_count": 2,
        "notes_used": True,
        "recent_message_count": 0,
    }
    assert fake_service.ask_calls == [
        {
            "user_id": TEST_USER_ID,
            "session_id": SESSION_ID,
            "question": "What should I improve?",
            "request_id": "ask-1",
            "include_notes": False,
        }
    ]


def test_cross_user_ask_ai_access_is_blocked(client: TestClient) -> None:
    class RaisingAskAIService(FakeAskAIService):
        def list_messages(self, *, user_id: str, session_id: str, limit: int, page: int):
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_ask_ai_service] = lambda: RaisingAskAIService()
    response = client.get(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai/messages",
        headers={"Authorization": f"Bearer {_token(subject='another-user')}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session was not found."}


def test_empty_context_ask_ai_maps_to_409(client: TestClient) -> None:
    class RaisingAskAIService(FakeAskAIService):
        def ask_ai(
            self,
            *,
            user_id: str,
            session_id: str,
            question: str,
            request_id: str | None = None,
            include_notes: bool = True,
        ):
            raise CloudInterviewSessionConflictError("This session does not have transcript or AI notes context yet.")

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_ask_ai_service] = lambda: RaisingAskAIService()
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"question": "What should I improve?"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This session does not have transcript or AI notes context yet."}


def test_provider_failure_ask_ai_maps_to_502(client: TestClient) -> None:
    class RaisingAskAIService(FakeAskAIService):
        def ask_ai(self, **kwargs):
            raise CloudInterviewSessionError(ASK_AI_FAILURE_MESSAGE)

    client.app.dependency_overrides[interview_sessions_api.get_cloud_interview_ask_ai_service] = lambda: RaisingAskAIService()
    response = client.post(
        f"/api/interview-sessions/{SESSION_ID}/ask-ai",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"question": "What should I improve?"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": ASK_AI_FAILURE_MESSAGE}


def test_ask_ai_capacity_guard_returns_retryable_503(client: TestClient, fake_service: FakeAskAIService) -> None:
    acquired = [interview_sessions_api._ASK_AI_CAPACITY.acquire(blocking=False) for _ in range(8)]
    try:
        response = client.post(
            f"/api/interview-sessions/{SESSION_ID}/ask-ai",
            headers={"Authorization": f"Bearer {_token()}"},
            json={"question": "What should I improve?"},
        )
    finally:
        for did_acquire in acquired:
            if did_acquire:
                interview_sessions_api._ASK_AI_CAPACITY.release()

    assert response.status_code == 503
    assert response.json() == {"detail": "Ask AI is busy. Please try again shortly."}
    assert fake_service.ask_calls == []
