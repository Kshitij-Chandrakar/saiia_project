import logging

import httpx
from openai import BadRequestError
import pytest

from app.cloud.interview_notes import CloudInterviewNotesRecord, CloudInterviewNotesService, OpenAIInterviewNotesGenerator
from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionRecord,
    CloudInterviewSessionValidationError,
)
from app.cloud.interview_transcripts import CloudInterviewTranscriptEntryRecord, InterviewTranscriptEntryListPage
from app.nlp.answer_generator import ProviderError


SESSION_ID = "30000000-0000-4000-8000-000000000001"
USER_ID = "00000000-0000-4000-8000-000000000001"


def _session(**overrides: object) -> CloudInterviewSessionRecord:
    payload = {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "selected_resume_id": None,
        "job_context_id": None,
        "title": "Design round",
        "target_role": "Backend Engineer",
        "company_name": "Acme",
        "job_description_preview": "AI engineer",
        "status": "ended",
        "started_at": "2026-08-29T10:00:00Z",
        "ended_at": "2026-08-29T10:10:00Z",
        "created_at": "2026-08-29T10:00:00Z",
        "updated_at": "2026-08-29T10:10:00Z",
    }
    payload.update(overrides)
    return CloudInterviewSessionRecord(**payload)  # type: ignore[arg-type]


def _entry(index: int = 1, **overrides: object) -> CloudInterviewTranscriptEntryRecord:
    payload = {
        "id": f"40000000-0000-4000-8000-00000000000{index}",
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "turn_index": index,
        "source": "chat",
        "question_text": f"Question {index}",
        "answer_text": f"Answer {index}",
        "category": "technical",
        "provider": "openai",
        "model": "gpt-test",
        "generation_ms": 123,
        "created_at": "2026-08-29T10:05:00Z",
    }
    payload.update(overrides)
    return CloudInterviewTranscriptEntryRecord(**payload)  # type: ignore[arg-type]


def _notes(**overrides: object) -> CloudInterviewNotesRecord:
    payload = {
        "id": "50000000-0000-4000-8000-000000000001",
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "status": "ready",
        "notes_markdown": "# Interview Notes\n",
        "summary": "Based on this transcript, the candidate was solid.",
        "strengths": ["Clear examples"],
        "improvement_areas": ["More metrics"],
        "technical_topics": ["FastAPI"],
        "key_questions": ["How do you secure auth?"],
        "suggested_followups": ["Practice system design"],
        "provider": "openai",
        "model": "gpt-test",
        "generation_ms": 321,
        "transcript_entry_count": 2,
        "generated_at": "2026-08-29T10:12:00Z",
        "created_at": "2026-08-29T10:12:00Z",
        "updated_at": "2026-08-29T10:12:00Z",
    }
    payload.update(overrides)
    return CloudInterviewNotesRecord(**payload)  # type: ignore[arg-type]


class FakeNotesClient:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, str]] = []
        self.upsert_calls: list[dict[str, object]] = []
        self.stored: CloudInterviewNotesRecord | None = None

    def get_notes(self, *, user_id: str, session_id: str) -> CloudInterviewNotesRecord:
        self.get_calls.append({"user_id": user_id, "session_id": session_id})
        if self.stored is None:
            raise CloudInterviewSessionNotFoundError("Interview session notes were not found.")
        return self.stored

    def upsert_notes(self, *, user_id: str, session_id: str, payload: dict[str, object]) -> CloudInterviewNotesRecord:
        self.upsert_calls.append({"user_id": user_id, "session_id": session_id, "payload": payload})
        self.stored = _notes(
            user_id=user_id,
            session_id=session_id,
            notes_markdown=str(payload["notes_markdown"]),
            summary=payload["summary"],
            strengths=list(payload["strengths"]),
            improvement_areas=list(payload["improvement_areas"]),
            technical_topics=list(payload["technical_topics"]),
            key_questions=list(payload["key_questions"]),
            suggested_followups=list(payload["suggested_followups"]),
            provider=payload["provider"],
            model=payload["model"],
            generation_ms=payload["generation_ms"],
            transcript_entry_count=payload["transcript_entry_count"],
        )
        return self.stored


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def get_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        self.calls.append({"user_id": user_id, "session_id": session_id})
        return _session(user_id=user_id, id=session_id)


class FakeTranscriptService:
    def __init__(self, items: list[CloudInterviewTranscriptEntryRecord] | None = None) -> None:
        self.items = items if items is not None else [_entry(1), _entry(2)]
        self.calls: list[dict[str, object]] = []

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int) -> InterviewTranscriptEntryListPage:
        self.calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "page": page})
        return InterviewTranscriptEntryListPage(items=self.items, limit=limit, page=page)


class FakeGenerator:
    def __init__(self, *, result: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or {
            "status": "ready",
            "notes_markdown": "# Interview Notes\n\n## Summary\n\nBased on this transcript, the answers were solid.\n",
            "summary": "Based on this transcript, the answers were solid.",
            "strengths": ["Clear explanations"],
            "improvement_areas": ["More examples"],
            "technical_topics": ["Authentication"],
            "key_questions": ["How is auth implemented?"],
            "suggested_followups": ["Practice tradeoff answers"],
            "provider": "openai",
            "model": "gpt-test",
            "generation_ms": 222,
        }
        self.error = error

    def generate(self, *, session: CloudInterviewSessionRecord, transcript_entries: list[CloudInterviewTranscriptEntryRecord]) -> dict[str, object]:
        self.calls.append({"session": session, "transcript_entries": transcript_entries})
        if self.error is not None:
            raise self.error
        return dict(self.result)


def test_get_notes_requires_valid_session_id() -> None:
    service = CloudInterviewNotesService(
        client=FakeNotesClient(),
        session_service=FakeSessionService(),
        transcript_service=FakeTranscriptService(),
        generator=FakeGenerator(),
    )

    with pytest.raises(CloudInterviewSessionValidationError):
        service.get_notes(user_id=USER_ID, session_id="bad-id")


def test_generate_notes_returns_existing_notes_without_regenerating() -> None:
    client = FakeNotesClient()
    client.stored = _notes()
    generator = FakeGenerator()
    service = CloudInterviewNotesService(
        client=client,
        session_service=FakeSessionService(),
        transcript_service=FakeTranscriptService(),
        generator=generator,
    )

    result = service.generate_notes(user_id=USER_ID, session_id=SESSION_ID, force_regenerate=False)

    assert result.id == client.stored.id
    assert generator.calls == []
    assert client.upsert_calls == []


def test_generate_notes_creates_and_stores_notes_for_owned_session() -> None:
    client = FakeNotesClient()
    transcript_service = FakeTranscriptService()
    generator = FakeGenerator()
    service = CloudInterviewNotesService(
        client=client,
        session_service=FakeSessionService(),
        transcript_service=transcript_service,
        generator=generator,
    )

    result = service.generate_notes(user_id=USER_ID, session_id=SESSION_ID, force_regenerate=True)

    assert result.session_id == SESSION_ID
    assert transcript_service.calls == [{"user_id": USER_ID, "session_id": SESSION_ID, "limit": 200, "page": 1}]
    assert len(generator.calls[0]["transcript_entries"]) == 2
    assert client.upsert_calls[0]["user_id"] == USER_ID
    assert client.upsert_calls[0]["payload"]["transcript_entry_count"] == 2


def test_generate_notes_rejects_empty_transcript() -> None:
    service = CloudInterviewNotesService(
        client=FakeNotesClient(),
        session_service=FakeSessionService(),
        transcript_service=FakeTranscriptService(items=[]),
        generator=FakeGenerator(),
    )

    with pytest.raises(CloudInterviewSessionConflictError, match="does not have transcript entries yet"):
        service.generate_notes(user_id=USER_ID, session_id=SESSION_ID, force_regenerate=True)


def test_generate_notes_maps_provider_failure_to_safe_error() -> None:
    service = CloudInterviewNotesService(
        client=FakeNotesClient(),
        session_service=FakeSessionService(),
        transcript_service=FakeTranscriptService(),
        generator=FakeGenerator(
            error=ProviderError(
                "provider failed",
                provider="openai",
                model="gpt-test",
                phase="interview_notes_generate",
                error_type="timeout",
            )
        ),
    )

    with pytest.raises(CloudInterviewSessionError, match="AI notes generation is temporarily unavailable."):
        service.generate_notes(user_id=USER_ID, session_id=SESSION_ID, force_regenerate=True)


def test_generate_notes_force_regenerate_replaces_existing_notes() -> None:
    client = FakeNotesClient()
    client.stored = _notes(summary="Old summary")
    generator = FakeGenerator(result={
        "status": "ready",
        "notes_markdown": "# Interview Notes\n\nUpdated\n",
        "summary": "Updated summary",
        "strengths": ["Updated strength"],
        "improvement_areas": ["Updated gap"],
        "technical_topics": ["Vector search"],
        "key_questions": ["How did you build it?"],
        "suggested_followups": ["Practice scaling"],
        "provider": "openai",
        "model": "gpt-new",
        "generation_ms": 111,
    })
    service = CloudInterviewNotesService(
        client=client,
        session_service=FakeSessionService(),
        transcript_service=FakeTranscriptService(),
        generator=generator,
    )

    result = service.generate_notes(user_id=USER_ID, session_id=SESSION_ID, force_regenerate=True)

    assert result.summary == "Updated summary"
    assert client.upsert_calls


class FakeOpenAIResponsesClient:
    def __init__(self, *, response: object | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._response = response
        self._error = error
        self.responses = self

    def create(self, **kwargs: object):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def test_openai_notes_generator_uses_supported_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cloud.interview_notes.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_notes.settings.AI_NOTES_MODEL", "gpt-5.4-mini-2026-03-17")
    monkeypatch.setattr("app.cloud.interview_notes.settings.AI_NOTES_REASONING_EFFORT", "minimal")
    client = FakeOpenAIResponsesClient(
        response=type("Response", (), {"output_text": '{"summary":"ok","technical_topics":[],"key_questions":[],"strengths":[],"improvement_areas":[],"suggested_followups":[],"overall_feedback":"fine"}'})()
    )
    generator = OpenAIInterviewNotesGenerator(openai_client=client)

    result = generator.generate(session=_session(), transcript_entries=[_entry(1)])

    assert result["summary"] == "ok"
    assert client.calls[0]["reasoning"] == {"effort": "low"}
    assert client.calls[0]["input"]
    assert client.calls[0]["text"]["format"]["type"] == "json_schema"


def test_openai_bad_request_logs_safe_fields_without_prompt_leak(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cloud.interview_notes.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_notes.settings.AI_NOTES_MODEL", "gpt-5.4-mini-2026-03-17")
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={
            "error": {
                "message": "Unsupported value: 'minimal' is not supported with this model.",
                "type": "invalid_request_error",
                "param": "reasoning.effort",
                "code": "unsupported_value",
            }
        },
    )
    error = BadRequestError("bad request", response=response, body=response.json())
    client = FakeOpenAIResponsesClient(error=error)
    generator = OpenAIInterviewNotesGenerator(openai_client=client)

    with caplog.at_level(logging.WARNING, logger="cloud_interview_notes"), pytest.raises(ProviderError):
        generator.generate(session=_session(), transcript_entries=[_entry(1, question_text="secret question", answer_text="secret answer")])

    assert "provider=openai" in caplog.text
    assert "model=gpt-5.4-mini-2026-03-17" in caplog.text
    assert "error_type=BadRequestError" in caplog.text
    assert "error_code=unsupported_value" in caplog.text
    assert "error_param=reasoning.effort" in caplog.text
    assert "Unsupported value: 'minimal' is not supported with this model." in caplog.text
    assert "secret question" not in caplog.text
    assert "secret answer" not in caplog.text
    assert "unit-test-key" not in caplog.text
