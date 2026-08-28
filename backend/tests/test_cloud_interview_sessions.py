import pytest
import requests

from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionService,
    CloudInterviewSessionValidationError,
    InterviewSessionListPage,
    MAX_JOB_DESCRIPTION_PREVIEW_CHARS,
    SupabaseInterviewSessionClient,
    normalize_session_payload,
    normalized_payload_hash,
    validate_idempotency_key,
)


class FakeClient:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.resume_owned = True
        self.job_context_owned = True

    def resume_owned_by_user(self, *, user_id: str, resume_id: str) -> bool:
        return self.resume_owned

    def job_context_owned_by_user(self, *, user_id: str, job_context_id: str) -> bool:
        return self.job_context_owned

    def create_session(self, **kwargs):
        self.create_calls.append(kwargs)

        class Result:
            replayed = False
            record = type(
                "Record",
                (),
                {
                    "id": "30000000-0000-4000-8000-000000000001",
                    "user_id": kwargs["user_id"],
                    "selected_resume_id": kwargs["payload"]["selected_resume_id"],
                    "job_context_id": kwargs["payload"]["job_context_id"],
                    "title": kwargs["payload"]["title"],
                    "target_role": kwargs["payload"]["target_role"],
                    "company_name": kwargs["payload"]["company_name"],
                    "job_description_preview": kwargs["payload"]["job_description_preview"],
                    "status": "active",
                    "started_at": "2026-08-28T00:00:00Z",
                    "ended_at": None,
                    "created_at": "2026-08-28T00:00:00Z",
                    "updated_at": "2026-08-28T00:00:00Z",
                },
            )()

        return Result()

    def list_sessions(self, *, user_id: str, limit: int, page: int):
        return []

    def get_session(self, *, user_id: str, session_id: str):
        return self.create_session(user_id=user_id, payload={"selected_resume_id": None, "job_context_id": None, "title": None, "target_role": None, "company_name": None, "job_description_preview": None}, idempotency_key="", request_hash="").record

    def end_session(self, *, user_id: str, session_id: str):
        record = self.get_session(user_id=user_id, session_id=session_id)
        record.status = "ended"
        record.ended_at = "2026-08-28T00:05:00Z"
        return record

    def abandon_active_sessions(self, *, user_id: str):
        return []


def test_idempotency_key_validation_rejects_invalid_values() -> None:
    assert validate_idempotency_key("start:abc-123_OK") == "start:abc-123_OK"

    for key in ("", "x" * 81, "bad key", "snowman-\u2603"):
        with pytest.raises(CloudInterviewSessionValidationError):
            validate_idempotency_key(key)


def test_payload_normalization_trims_text_and_stores_preview_only() -> None:
    payload = normalize_session_payload(
        {
            "title": " Design Interview ",
            "target_role": " Senior Frontend Engineer ",
            "company_name": " Acme ",
            "job_description": "x" * 500,
        }
    )

    assert payload["title"] == "Design Interview"
    assert payload["target_role"] == "Senior Frontend Engineer"
    assert payload["company_name"] == "Acme"
    assert len(payload["job_description_preview"] or "") == MAX_JOB_DESCRIPTION_PREVIEW_CHARS

    with pytest.raises(CloudInterviewSessionValidationError):
        normalize_session_payload({"user_id": "evil"})


def test_payload_hash_changes_when_preview_changes() -> None:
    first = normalized_payload_hash(normalize_session_payload({"title": "A", "job_description": "one"}))
    second = normalized_payload_hash(normalize_session_payload({"title": "A", "job_description": "two"}))

    assert first != second
    assert len(first) == 64


def test_service_validates_owned_resume_and_job_context_before_create() -> None:
    client = FakeClient()
    service = CloudInterviewSessionService(client=client)

    service.create_session(
        user_id="user-1",
        payload={
            "title": "Design round",
            "selected_resume_id": "30000000-0000-4000-8000-000000000002",
            "job_context_id": "30000000-0000-4000-8000-000000000003",
            "job_description": "Frontend system design",
        },
        idempotency_key="start:1",
    )

    assert client.create_calls[0]["user_id"] == "user-1"
    assert client.create_calls[0]["idempotency_key"] == "start:1"
    assert client.create_calls[0]["payload"]["job_description_preview"] == "Frontend system design"
    assert len(client.create_calls[0]["request_hash"]) == 64

    client.resume_owned = False
    with pytest.raises(CloudInterviewSessionNotFoundError, match="Selected resume"):
        service.create_session(
            user_id="user-1",
            payload={
                "title": "Design round",
                "selected_resume_id": "30000000-0000-4000-8000-000000000002",
                "job_description": "Frontend system design",
            },
            idempotency_key="start:2",
        )

    client.resume_owned = True
    client.job_context_owned = False
    with pytest.raises(CloudInterviewSessionNotFoundError, match="Job context"):
        service.create_session(
            user_id="user-1",
            payload={
                "title": "Design round",
                "job_context_id": "30000000-0000-4000-8000-000000000003",
                "job_description": "Frontend system design",
            },
            idempotency_key="start:3",
        )


def test_list_limit_and_page_are_bounded() -> None:
    service = CloudInterviewSessionService(client=FakeClient())

    assert service.list_sessions(user_id="user-1", limit=20, page=1) == InterviewSessionListPage(items=[], limit=20, page=1)
    with pytest.raises(CloudInterviewSessionValidationError):
        service.list_sessions(user_id="user-1", limit=0, page=1)
    with pytest.raises(CloudInterviewSessionValidationError):
        service.list_sessions(user_id="user-1", limit=20, page=0)


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeRestSession:
    def __init__(self) -> None:
        self.post_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.post_response = FakeResponse(
            200,
            [{"interview_session_id": "30000000-0000-4000-8000-000000000001", "replayed": True, "status": "completed"}],
        )
        self.get_response = FakeResponse(
            200,
            [
                {
                    "id": "30000000-0000-4000-8000-000000000001",
                    "user_id": "user-1",
                    "selected_resume_id": None,
                    "job_context_id": None,
                    "title": "Design round",
                    "target_role": "Frontend Engineer",
                    "company_name": "Acme",
                    "job_description_preview": "Preview only",
                    "status": "active",
                    "started_at": "2026-08-28T00:00:00Z",
                    "ended_at": None,
                    "created_at": "2026-08-28T00:00:00Z",
                    "updated_at": "2026-08-28T00:00:00Z",
                }
            ],
        )

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int):
        self.post_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.post_response

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, str], timeout: int):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return self.get_response


def _supabase_client_with_session(session: FakeRestSession) -> SupabaseInterviewSessionClient:
    client = object.__new__(SupabaseInterviewSessionClient)
    client._rest_url = "https://project-ref.supabase.co/rest/v1"
    client._session = session
    client._headers = {
        "apikey": "service-role-unit-test-value",
        "Authorization": "Bearer service-role-unit-test-value",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return client


def test_supabase_create_session_posts_prefixed_rpc_args_and_accepts_replayed_result() -> None:
    session = FakeRestSession()
    client = _supabase_client_with_session(session)

    result = client.create_session(
        user_id="user-1",
        payload={
            "selected_resume_id": None,
            "job_context_id": None,
            "title": "Design round",
            "target_role": "Frontend Engineer",
            "company_name": "Acme",
            "job_description_preview": "Preview only",
        },
        idempotency_key="start:replay",
        request_hash="abc123",
    )

    assert result.replayed is True
    assert result.record.id == "30000000-0000-4000-8000-000000000001"
    assert session.post_calls[0]["json"] == {
        "p_user_id": "user-1",
        "p_idempotency_key": "start:replay",
        "p_request_hash": "abc123",
        "p_selected_resume_id": None,
        "p_job_context_id": None,
        "p_title": "Design round",
        "p_target_role": "Frontend Engineer",
        "p_company_name": "Acme",
        "p_job_description_preview": "Preview only",
    }


def test_supabase_create_session_logs_safe_error_fields_for_ambiguous_sql(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeRestSession()
    session.post_response = FakeResponse(
        400,
        {
            "code": "42702",
            "message": 'column reference "status" is ambiguous',
            "details": "It could refer to either a PL/pgSQL variable or a table column.",
            "hint": "Use a table alias.",
        },
    )
    client = _supabase_client_with_session(session)

    with caplog.at_level("ERROR", logger="cloud_interview_sessions"), pytest.raises(CloudInterviewSessionError):
        client.create_session(
            user_id="user-1",
            payload={
                "selected_resume_id": None,
                "job_context_id": None,
                "title": "Design round",
                "target_role": None,
                "company_name": None,
                "job_description_preview": None,
            },
            idempotency_key="start:42702",
            request_hash="abc123",
        )

    assert "error_code=42702" in caplog.text
    assert 'message=column reference "status" is ambiguous' in caplog.text
    assert "details=It could refer to either a PL/pgSQL variable or a table column." in caplog.text
    assert "hint=Use a table alias." in caplog.text
    assert "service-role-unit-test-value" not in caplog.text


def test_supabase_create_session_maps_p0001_to_conflict() -> None:
    session = FakeRestSession()
    session.post_response = FakeResponse(
        409,
        {"code": "P0001", "message": "interview session idempotency key conflict"},
    )
    client = _supabase_client_with_session(session)

    with pytest.raises(CloudInterviewSessionConflictError):
        client.create_session(
            user_id="user-1",
            payload={
                "selected_resume_id": None,
                "job_context_id": None,
                "title": "Design round",
                "target_role": None,
                "company_name": None,
                "job_description_preview": None,
            },
            idempotency_key="start:conflict",
            request_hash="different-hash",
        )
