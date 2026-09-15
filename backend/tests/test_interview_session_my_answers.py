from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview_sessions as api
from app.auth.supabase_auth import get_auth_verification_config
from app.cloud.interview_session_my_answers import (
    CloudInterviewMyAnswerRecord,
    CloudInterviewMyAnswersService,
    CloudInterviewSessionValidationError,
    CloudInterviewSessionError,
    MIGRATION_FAILURE_MESSAGE,
    SupabaseInterviewSessionMyAnswersClient,
)
from app.cloud.interview_sessions import CloudInterviewSessionNotFoundError, CloudInterviewSessionRecord
from app.cloud.supabase_config import CLOUD_MODE_ENV, SUPABASE_REQUIRED_ENV_VARS, get_supabase_settings

TEST_SECRET = "my-answers-unit-test-secret"
USER_ID = "00000000-0000-4000-8000-000000000001"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000002"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def token(subject: str = USER_ID) -> str:
    return jwt.encode(
        {
            "iss": "https://project-ref.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
            "sub": subject,
            "role": "authenticated",
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def session_record(user_id: str = USER_ID, status: str = "active") -> CloudInterviewSessionRecord:
    return CloudInterviewSessionRecord(
        id=SESSION_ID,
        user_id=user_id,
        selected_resume_id=None,
        job_context_id=None,
        title="Interview",
        target_role="Engineer",
        company_name="Acme",
        job_description_preview=None,
        status=status,
        started_at="2026-09-15T00:00:00Z",
        ended_at=None,
        created_at="2026-09-15T00:00:00Z",
        updated_at="2026-09-15T00:00:00Z",
    )


class FakeSessionService:
    def __init__(self, owner: str = USER_ID, status: str = "active") -> None:
        self.owner = owner
        self.status = status

    def get_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        if user_id != self.owner or session_id != SESSION_ID:
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")
        return session_record(user_id=self.owner, status=self.status)


class FakeMyAnswersService:
    def __init__(self) -> None:
        self.items: list[CloudInterviewMyAnswerRecord] = []

    def list_answers(self, *, user_id: str, session_id: str):
        return list(self.items)

    def create_answer(self, *, user_id: str, session_id: str, body: str):
        if not body.strip():
            raise CloudInterviewSessionValidationError("Answer body is required.")
        answer = CloudInterviewMyAnswerRecord(
            id=f"answer-{len(self.items) + 1}",
            user_id=user_id,
            session_id=session_id,
            body=body.strip(),
            position=len(self.items) + 1,
            created_at="2026-09-15T00:00:00Z",
        )
        self.items.append(answer)
        return answer


@pytest.fixture(autouse=True)
def clear_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", TEST_SECRET)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    api._cached_cloud_interview_session_service.cache_clear()
    api._cached_cloud_interview_my_answers_service.cache_clear()
    yield
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    api._cached_cloud_interview_session_service.cache_clear()
    api._cached_cloud_interview_my_answers_service.cache_clear()


@pytest.fixture
def setup_client():
    app = FastAPI()
    app.include_router(api.router, prefix="/api/interview-sessions")
    sessions = FakeSessionService()
    answers = FakeMyAnswersService()
    app.dependency_overrides[api.get_cloud_interview_session_service] = lambda: sessions
    app.dependency_overrides[api.get_cloud_interview_my_answers_service] = lambda: answers
    with TestClient(app) as client:
        yield client, sessions, answers
    app.dependency_overrides.clear()


def test_my_answers_require_auth_and_are_session_scoped(setup_client) -> None:
    client, _sessions, answers = setup_client
    path = f"/api/interview-sessions/{SESSION_ID}/my-answers"

    assert client.get(path).status_code == 401
    saved = client.post(path, headers={"Authorization": f"Bearer {token()}"}, json={"body": " My answer "})
    assert saved.status_code == 201
    assert saved.json()["body"] == "My answer"
    listed = client.get(path, headers={"Authorization": f"Bearer {token()}"})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["position"] == 1
    assert len(answers.items) == 1


def test_my_answers_reject_empty_closed_and_cross_user_access(setup_client) -> None:
    client, sessions, _answers = setup_client
    path = f"/api/interview-sessions/{SESSION_ID}/my-answers"
    headers = {"Authorization": f"Bearer {token()}"}

    assert client.post(path, headers=headers, json={"body": "  \n"}).status_code == 400
    sessions.status = "ended"
    assert client.get(path, headers=headers).status_code == 409
    sessions.status = "active"
    sessions.owner = OTHER_USER_ID
    assert client.get(path, headers=headers).status_code == 404


def test_my_answers_have_no_update_endpoint(setup_client) -> None:
    client, _sessions, _answers = setup_client
    path = f"/api/interview-sessions/{SESSION_ID}/my-answers"
    response = client.put(path, headers={"Authorization": f"Bearer {token()}"}, json={"body": "changed"})
    assert response.status_code == 405


def test_service_normalizes_empty_body_and_uses_client_without_edit_method() -> None:
    class Client:
        def create_answer(self, **kwargs):
            return kwargs

    service = CloudInterviewMyAnswersService(client=Client())
    with pytest.raises(CloudInterviewSessionValidationError):
        service.create_answer(user_id=USER_ID, session_id=SESSION_ID, body=" ")


def test_supabase_schema_failure_exposes_migration_error_without_provider_details() -> None:
    class Response:
        status_code = 404

        @staticmethod
        def json():
            return {"code": "PGRST205", "message": "Could not find the table in the schema cache."}

    client = object.__new__(SupabaseInterviewSessionMyAnswersClient)
    with pytest.raises(CloudInterviewSessionError, match=MIGRATION_FAILURE_MESSAGE):
        client._raise("list", Response())


def test_migration_enforces_session_scope_and_backend_only_writes() -> None:
    migration = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260915120000_add_interview_session_my_answers.sql"
    sql = " ".join(migration.read_text(encoding="utf-8").lower().split())
    assert "create table if not exists public.interview_session_my_answers" in sql
    assert "alter table public.interview_session_my_answers force row level security" in sql
    assert "where s.id = session_id and s.user_id = auth.uid()" in sql
    assert "revoke insert, update, delete on table public.interview_session_my_answers from authenticated" in sql
    assert "create or replace function public.create_interview_session_my_answer" in sql
    assert "grant execute on function public.create_interview_session_my_answer(uuid, uuid, text) to authenticated" not in sql
