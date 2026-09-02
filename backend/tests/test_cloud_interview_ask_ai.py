from datetime import datetime, timedelta, timezone
import logging

import httpx
from openai import BadRequestError
import pytest

from app.cloud.interview_ask_ai import (
    ASK_AI_FAILURE_MESSAGE,
    CloudInterviewAskAIMessageRecord,
    CloudInterviewAskAIRequestKeyRecord,
    CloudInterviewAskAIService,
    InterviewAskAIMessageListPage,
    MAX_RECENT_MESSAGES,
    OpenAIInterviewAskAIGenerator,
    _payload_hash as _payload_hash_for_test,
)
from app.cloud.interview_notes import CloudInterviewNotesRecord
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
        "started_at": "2026-09-01T10:00:00Z",
        "ended_at": "2026-09-01T10:10:00Z",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:10:00Z",
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
        "created_at": "2026-09-01T10:05:00Z",
    }
    payload.update(overrides)
    return CloudInterviewTranscriptEntryRecord(**payload)  # type: ignore[arg-type]


def _notes(**overrides: object) -> CloudInterviewNotesRecord:
    payload = {
        "id": "50000000-0000-4000-8000-000000000001",
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "status": "ready",
        "notes_markdown": "# Interview Notes\n\nImprove specificity.",
        "summary": "Based on this transcript, answers need stronger examples.",
        "strengths": ["Clear structure"],
        "improvement_areas": ["More metrics"],
        "technical_topics": ["FastAPI"],
        "key_questions": ["Question 1"],
        "suggested_followups": ["Practice follow-ups"],
        "provider": "openai",
        "model": "gpt-test",
        "generation_ms": 321,
        "transcript_entry_count": 2,
        "generated_at": "2026-09-01T10:12:00Z",
        "created_at": "2026-09-01T10:12:00Z",
        "updated_at": "2026-09-01T10:12:00Z",
    }
    payload.update(overrides)
    return CloudInterviewNotesRecord(**payload)  # type: ignore[arg-type]


def _message(index: int, role: str, text: str, **overrides: object) -> CloudInterviewAskAIMessageRecord:
    payload = {
        "id": f"60000000-0000-4000-8000-00000000000{index}",
        "user_id": USER_ID,
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


def _request_key(index: int, **overrides: object) -> CloudInterviewAskAIRequestKeyRecord:
    payload = {
        "id": f"70000000-0000-4000-8000-00000000000{index}",
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "request_id": f"ask-{index}",
        "status": "processing",
        "user_message_id": None,
        "assistant_message_id": None,
        "payload_hash": "hash",
        "error_code": None,
        "created_at": "2026-09-01T10:15:00Z",
        "updated_at": "2026-09-01T10:15:00Z",
        "claim_token": f"claim-{index}",
    }
    payload.update(overrides)
    return CloudInterviewAskAIRequestKeyRecord(**payload)  # type: ignore[arg-type]


class FakeAskAIClient:
    def __init__(self, messages: list[CloudInterviewAskAIMessageRecord] | None = None) -> None:
        self.messages = list(messages or [])
        self.request_keys: dict[tuple[str, str, str], CloudInterviewAskAIRequestKeyRecord] = {}
        self.create_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.recent_calls: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.complete_turn_calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []
        self.reclaim_calls: list[dict[str, object]] = []
        self.fail_create_on_call: int | None = None
        self.fail_complete = False
        self.complete_after_update_fails = False

    def list_messages(self, *, user_id: str, session_id: str, limit: int, page: int):
        self.list_calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "page": page})
        offset = (page - 1) * limit
        return self.list_messages_window(user_id=user_id, session_id=session_id, limit=limit, offset=offset)

    def list_messages_window(self, *, user_id: str, session_id: str, limit: int, offset: int):
        self.list_calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "offset": offset})
        rows = [message for message in self.messages if message.user_id == user_id and message.session_id == session_id]
        return rows[offset : offset + limit]

    def list_recent_messages(self, *, user_id: str, session_id: str, limit: int):
        self.recent_calls.append({"user_id": user_id, "session_id": session_id, "limit": limit})
        rows = [message for message in self.messages if message.user_id == user_id and message.session_id == session_id]
        return rows[-limit:]

    def get_message(self, *, user_id: str, session_id: str, message_id: str):
        for message in self.messages:
            if message.user_id == user_id and message.session_id == session_id and message.id == message_id:
                return message
        raise CloudInterviewSessionNotFoundError("Ask AI message was not found.")

    def claim_request_key(self, *, user_id: str, session_id: str, request_id: str, payload_hash: str):
        self.claim_calls.append({"user_id": user_id, "session_id": session_id, "request_id": request_id, "payload_hash": payload_hash})
        key = (user_id, session_id, request_id)
        existing = self.request_keys.get(key)
        if existing is not None:
            return existing, False
        record = _request_key(
            len(self.request_keys) + 1,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            payload_hash=payload_hash,
        )
        self.request_keys[key] = record
        return record, True

    def complete_turn(self, *, user_id, session_id, request_id, claim_token, question, answer, provider, model, generation_ms, metadata):
        self.complete_turn_calls.append({"request_id": request_id, "claim_token": claim_token})
        user_message = self.create_message(
            user_id=user_id,
            session_id=session_id,
            payload={
                "role": "user",
                "message_text": question,
                "provider": None,
                "model": None,
                "generation_ms": None,
                "metadata": metadata,
            },
        )
        assistant_message = self.create_message(
            user_id=user_id,
            session_id=session_id,
            payload={
                "role": "assistant",
                "message_text": answer,
                "provider": provider,
                "model": model,
                "generation_ms": generation_ms,
                "metadata": metadata,
            },
        )
        self.complete_request_key(
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        )
        return user_message, assistant_message

    def complete_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        user_message_id: str,
        assistant_message_id: str,
    ):
        if self.fail_complete:
            raise RuntimeError("complete failed")
        self.complete_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "request_id": request_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            }
        )
        key = (user_id, session_id, request_id)
        current = self.request_keys[key]
        updated = _request_key(
            1,
            id=current.id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            status="completed",
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            payload_hash=current.payload_hash,
        )
        self.request_keys[key] = updated
        if self.complete_after_update_fails:
            raise RuntimeError("completion response lost")
        return updated

    def get_request_key(self, *, user_id: str, session_id: str, request_id: str):
        return self.request_keys[(user_id, session_id, request_id)]

    def fail_request_key(self, *, user_id: str, session_id: str, request_id: str, error_code: str):
        self.fail_calls.append({"user_id": user_id, "session_id": session_id, "request_id": request_id, "error_code": error_code})
        key = (user_id, session_id, request_id)
        current = self.request_keys[key]
        updated = _request_key(
            1,
            id=current.id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            status="failed",
            payload_hash=current.payload_hash,
            error_code=error_code,
        )
        self.request_keys[key] = updated
        return updated

    def reclaim_stale_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        payload_hash: str,
        stale_before: datetime,
    ):
        self.reclaim_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "request_id": request_id,
                "payload_hash": payload_hash,
                "stale_before": stale_before,
            }
        )
        key = (user_id, session_id, request_id)
        current = self.request_keys.get(key)
        if current is None or current.status != "processing" or current.payload_hash != payload_hash:
            return None, False
        updated_at = datetime.fromisoformat(str(current.updated_at).replace("Z", "+00:00"))
        if updated_at >= stale_before:
            return None, False
        updated = _request_key(
            1,
            id=current.id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            status="processing",
            payload_hash=payload_hash,
            updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            claim_token="reclaimed-claim",
        )
        self.request_keys[key] = updated
        return updated, True

    def create_message(self, *, user_id: str, session_id: str, payload: dict[str, object]):
        if self.fail_create_on_call == len(self.create_calls) + 1:
            raise RuntimeError("persist failed")
        self.create_calls.append({"user_id": user_id, "session_id": session_id, "payload": payload})
        record = _message(
            len(self.messages) + 1,
            str(payload["role"]),
            str(payload["message_text"]),
            user_id=user_id,
            session_id=session_id,
            provider=payload["provider"],
            model=payload["model"],
            generation_ms=payload["generation_ms"],
        )
        self.messages.append(record)
        return record


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.error: Exception | None = None

    def get_session(self, *, user_id: str, session_id: str):
        self.calls.append({"user_id": user_id, "session_id": session_id})
        if self.error is not None:
            raise self.error
        return _session(user_id=user_id, id=session_id)


class FakeTranscriptService:
    def __init__(self, items: list[CloudInterviewTranscriptEntryRecord] | None = None) -> None:
        self.items = [_entry(1), _entry(2)] if items is None else items
        self.calls: list[dict[str, object]] = []

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int):
        self.calls.append({"user_id": user_id, "session_id": session_id, "limit": limit, "page": page})
        return InterviewTranscriptEntryListPage(items=self.items, limit=limit, page=page)


class FakeNotesService:
    def __init__(self, notes: CloudInterviewNotesRecord | None = None, error: Exception | None = None) -> None:
        self.notes = notes if notes is not None else _notes()
        self.error = error
        self.calls: list[dict[str, str]] = []

    def get_notes(self, *, user_id: str, session_id: str):
        self.calls.append({"user_id": user_id, "session_id": session_id})
        if self.error is not None:
            raise self.error
        return self.notes


class FakeGenerator:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.error = error

    def generate(self, *, context: str, question: str):
        self.calls.append({"context": context, "question": question})
        if self.error is not None:
            raise self.error
        return {
            "answer_text": "Based on this transcript, improve specificity and examples.",
            "provider": "openai",
            "model": "gpt-test",
            "generation_ms": 222,
        }


class ExplodingGenerator(FakeGenerator):
    def generate(self, *, context: str, question: str):
        self.calls.append({"context": context, "question": question})
        raise RuntimeError("boom")


class InvalidAnswerGenerator(FakeGenerator):
    def generate(self, *, context: str, question: str):
        self.calls.append({"context": context, "question": question})
        return {"answer_text": "", "provider": "openai", "model": "gpt-test", "generation_ms": 1}


def _service(
    *,
    client: FakeAskAIClient | None = None,
    session_service: FakeSessionService | None = None,
    transcript_service: FakeTranscriptService | None = None,
    notes_service: FakeNotesService | None = None,
    generator: FakeGenerator | None = None,
) -> CloudInterviewAskAIService:
    return CloudInterviewAskAIService(
        client=client or FakeAskAIClient(),
        session_service=session_service or FakeSessionService(),
        transcript_service=transcript_service or FakeTranscriptService(),
        notes_service=notes_service or FakeNotesService(),
        generator=generator or FakeGenerator(),
    )


def test_list_messages_validates_session_and_uses_verified_user() -> None:
    service = _service(client=FakeAskAIClient([_message(1, "user", "What should I improve?")]))

    result = service.list_messages(user_id=USER_ID, session_id=SESSION_ID, limit=10, page=1)

    assert isinstance(result, InterviewAskAIMessageListPage)
    assert result.items[0].message_text == "What should I improve?"
    assert result.has_more is False


def test_list_messages_uses_page_offset_and_reports_more() -> None:
    client = FakeAskAIClient([_message(index, "user", f"Message {index}") for index in range(1, 8)])
    service = _service(client=client)

    page_1 = service.list_messages(user_id=USER_ID, session_id=SESSION_ID, limit=3, page=1)
    page_2 = service.list_messages(user_id=USER_ID, session_id=SESSION_ID, limit=3, page=2)
    page_3 = service.list_messages(user_id=USER_ID, session_id=SESSION_ID, limit=3, page=3)

    assert [message.turn_index for message in page_1.items] == [1, 2, 3]
    assert page_1.has_more is True
    assert page_1.next_page == 2
    assert [message.turn_index for message in page_2.items] == [4, 5, 6]
    assert page_2.has_more is True
    assert page_2.next_page == 3
    assert [message.turn_index for message in page_3.items] == [7]
    assert page_3.has_more is False
    assert page_3.next_page is None
    assert client.list_calls == [
        {"user_id": USER_ID, "session_id": SESSION_ID, "limit": 4, "offset": 0},
        {"user_id": USER_ID, "session_id": SESSION_ID, "limit": 4, "offset": 3},
        {"user_id": USER_ID, "session_id": SESSION_ID, "limit": 4, "offset": 6},
    ]


def test_ask_ai_rejects_empty_and_oversized_questions() -> None:
    service = _service()

    with pytest.raises(CloudInterviewSessionValidationError, match="question is required"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="")

    with pytest.raises(CloudInterviewSessionValidationError, match="question is required"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="###")

    with pytest.raises(CloudInterviewSessionValidationError, match="question is too long"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="x" * 2001)


def test_ask_ai_cross_user_session_is_blocked_before_provider_call() -> None:
    session_service = FakeSessionService()
    session_service.error = CloudInterviewSessionNotFoundError("Interview session was not found.")
    generator = FakeGenerator()
    service = _service(session_service=session_service, generator=generator)

    with pytest.raises(CloudInterviewSessionNotFoundError):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?")

    assert generator.calls == []


def test_ask_ai_empty_transcript_and_missing_notes_returns_409() -> None:
    service = _service(
        transcript_service=FakeTranscriptService(items=[]),
        notes_service=FakeNotesService(error=CloudInterviewSessionNotFoundError("Interview session notes were not found.")),
    )

    with pytest.raises(CloudInterviewSessionConflictError, match="does not have transcript or AI notes context yet"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?")


def test_ask_ai_stores_user_and_assistant_messages_with_context() -> None:
    client = FakeAskAIClient([_message(1, "user", "Earlier question")])
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)

    result = service.ask_ai(
        user_id=USER_ID,
        session_id=SESSION_ID,
        question="Give me a better answer for question 2.",
        request_id="ask-1",
    )

    assert result.answer_text.startswith("Based on this transcript")
    assert result.context_used.transcript_entry_count == 2
    assert result.context_used.notes_used is True
    assert result.context_used.recent_message_count == 1
    assert [call["payload"]["role"] for call in client.create_calls] == ["user", "assistant"]
    assert client.create_calls[0]["payload"]["metadata"] == {"request_id": "ask-1"}
    assert client.complete_turn_calls[0]["request_id"] == "ask-1"
    assert client.messages[-2].turn_index == 2
    assert client.messages[-1].turn_index == 3
    assert "Question 2" in generator.calls[0]["context"]
    assert "Saved AI notes" in generator.calls[0]["context"]
    assert "Earlier question" in generator.calls[0]["context"]


def test_ask_ai_request_id_replay_returns_same_messages_without_provider_call() -> None:
    client = FakeAskAIClient([_message(1, "user", "Earlier question")])
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)

    first = service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-1")
    second = service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-1")

    assert len(generator.calls) == 1
    assert len(client.create_calls) == 2
    assert first.user_message.id == second.user_message.id
    assert first.assistant_message.id == second.assistant_message.id
    assert second.answer_text == first.answer_text
    assert second.context_used.transcript_entry_count == 2
    assert second.context_used.notes_used is True
    assert second.context_used.recent_message_count == 3


def test_ask_ai_request_id_processing_and_failed_states_are_explicit() -> None:
    client = FakeAskAIClient()
    service = _service(client=client)
    service_hash = _payload_hash_for_test(question="What should I improve?", include_notes=True)
    client.request_keys[(USER_ID, SESSION_ID, "ask-processing")] = _request_key(
        1,
        request_id="ask-processing",
        payload_hash=service_hash,
        status="processing",
        updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    client.request_keys[(USER_ID, SESSION_ID, "ask-failed")] = _request_key(
        2,
        request_id="ask-failed",
        payload_hash=service_hash,
        status="failed",
    )

    with pytest.raises(CloudInterviewSessionConflictError, match="already processing"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-processing")

    with pytest.raises(CloudInterviewSessionConflictError, match="previously failed"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-failed")


def test_ask_ai_stale_processing_request_id_is_reclaimed() -> None:
    client = FakeAskAIClient()
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)
    service_hash = _payload_hash_for_test(question="What should I improve?", include_notes=True)
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    client.request_keys[(USER_ID, SESSION_ID, "ask-stale")] = _request_key(
        1,
        request_id="ask-stale",
        payload_hash=service_hash,
        status="processing",
        updated_at=stale_time,
    )

    result = service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-stale")

    assert result.answer_text.startswith("Based on this transcript")
    assert len(generator.calls) == 1
    assert client.reclaim_calls[0]["request_id"] == "ask-stale"
    assert client.request_keys[(USER_ID, SESSION_ID, "ask-stale")].status == "completed"
    assert client.complete_turn_calls[0]["claim_token"] == "reclaimed-claim"


def test_ask_ai_provider_failure_marks_request_key_failed() -> None:
    client = FakeAskAIClient()
    service = _service(
        client=client,
        generator=FakeGenerator(
            error=ProviderError(
                "provider failed",
                provider="openai",
                model="gpt-test",
                phase="interview_ask_ai",
                error_type="timeout",
            )
        ),
    )

    with pytest.raises(CloudInterviewSessionError, match=ASK_AI_FAILURE_MESSAGE):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-fail")

    assert client.fail_calls[-1]["request_id"] == "ask-fail"
    assert client.request_keys[(USER_ID, SESSION_ID, "ask-fail")].status == "failed"


def test_ask_ai_non_provider_failure_marks_request_key_failed() -> None:
    client = FakeAskAIClient()
    service = _service(client=client, generator=ExplodingGenerator())

    with pytest.raises(RuntimeError, match="boom"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-boom")

    assert client.fail_calls[-1]["request_id"] == "ask-boom"
    assert client.request_keys[(USER_ID, SESSION_ID, "ask-boom")].status == "failed"


@pytest.mark.parametrize("failure", ["normalize", "first_message", "second_message", "complete"])
def test_ask_ai_post_generation_failures_mark_request_key_failed(failure: str) -> None:
    client = FakeAskAIClient()
    client.fail_create_on_call = {"first_message": 1, "second_message": 2}.get(failure)
    client.fail_complete = failure == "complete"
    service = _service(client=client, generator=InvalidAnswerGenerator() if failure == "normalize" else FakeGenerator())
    request_id = f"ask-post-failure-{failure}"

    with pytest.raises(CloudInterviewSessionError if failure == "normalize" else RuntimeError):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id=request_id)

    assert client.fail_calls[-1]["request_id"] == request_id
    assert client.request_keys[(USER_ID, SESSION_ID, request_id)].status == "failed"


def test_ask_ai_completion_response_failure_replays_completed_turn() -> None:
    client = FakeAskAIClient()
    client.complete_after_update_fails = True
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)

    result = service.ask_ai(
        user_id=USER_ID,
        session_id=SESSION_ID,
        question="What should I improve?",
        request_id="ask-complete-response-lost",
    )

    key = client.request_keys[(USER_ID, SESSION_ID, "ask-complete-response-lost")]
    assert key.status == "completed"
    assert client.fail_calls == []
    assert len(generator.calls) == 1
    assert result.user_message.id == key.user_message_id
    assert result.assistant_message.id == key.assistant_message_id


def test_ask_ai_request_id_rejects_different_payload() -> None:
    client = FakeAskAIClient()
    service = _service(client=client)

    service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-1")

    with pytest.raises(CloudInterviewSessionConflictError, match="different input"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="Which answer was weak?", request_id="ask-1")


def test_ask_ai_same_request_id_is_scoped_to_user_and_session() -> None:
    other_session_id = "30000000-0000-4000-8000-000000000002"
    other_user_id = "00000000-0000-4000-8000-000000000002"
    client = FakeAskAIClient()
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)

    service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="ask-1")
    service.ask_ai(user_id=USER_ID, session_id=other_session_id, question="What should I improve?", request_id="ask-1")
    service.ask_ai(user_id=other_user_id, session_id=SESSION_ID, question="What should I improve?", request_id="ask-1")

    assert len(generator.calls) == 3
    assert len(client.request_keys) == 3


def test_ask_ai_rejects_invalid_request_id_before_provider_call() -> None:
    generator = FakeGenerator()
    service = _service(generator=generator)

    with pytest.raises(CloudInterviewSessionValidationError, match="request_id is invalid"):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?", request_id="../bad")

    assert generator.calls == []


def test_ask_ai_context_uses_newest_recent_messages() -> None:
    messages = [_message(index, "user" if index % 2 else "assistant", f"Prior turn {index}") for index in range(1, 21)]
    client = FakeAskAIClient(messages)
    generator = FakeGenerator()
    service = _service(client=client, generator=generator)

    service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="Use recent context.")

    context = generator.calls[0]["context"]
    assert f"Prior turn {20}" in context
    assert f"Prior turn {20 - MAX_RECENT_MESSAGES}" not in context
    assert client.recent_calls == [{"user_id": USER_ID, "session_id": SESSION_ID, "limit": MAX_RECENT_MESSAGES}]


def test_ask_ai_stores_readable_text_without_escaped_markdown_or_entities() -> None:
    class EscapedGenerator(FakeGenerator):
        def generate(self, *, context: str, question: str):
            return {
                "answer_text": r"\### What you&#x2019;re doing well\n\n\- \*\*depth\*\*\n1\. Add examples&#x20;",
                "provider": "openai",
                "model": "gpt-test",
                "generation_ms": 222,
            }

    client = FakeAskAIClient()
    service = _service(client=client, generator=EscapedGenerator())

    result = service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?")

    assert "###" not in result.answer_text
    assert r"\*\*" not in result.answer_text
    assert "&#x20;" not in result.answer_text
    assert "What you\u2019re doing well" in result.answer_text
    assert "- depth" in result.answer_text
    assert "1. Add examples" in result.answer_text
    assert client.create_calls[1]["payload"]["message_text"] == result.answer_text


def test_ask_ai_provider_failure_is_safe_and_does_not_store_messages() -> None:
    client = FakeAskAIClient()
    service = _service(
        client=client,
        generator=FakeGenerator(
            error=ProviderError(
                "provider failed",
                provider="openai",
                model="gpt-test",
                phase="interview_ask_ai",
                error_type="timeout",
            )
        ),
    )

    with pytest.raises(CloudInterviewSessionError, match=ASK_AI_FAILURE_MESSAGE):
        service.ask_ai(user_id=USER_ID, session_id=SESSION_ID, question="What should I improve?")

    assert client.create_calls == []


def test_build_context_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.ASK_AI_MAX_INPUT_CHARS", 800)
    service = _service()

    context = service.build_context_from_session(
        session=_session(title="T" * 5000, job_description_preview="J" * 5000),
        transcript_entries=[_entry(1, question_text="Q" * 2000, answer_text="A" * 5000)],
        notes_markdown="N" * 5000,
        recent_messages=[_message(1, "user", "M" * 5000)],
    )

    assert len(context) <= 800
    assert "T" * 500 not in context
    assert "J" * 500 not in context


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


def test_openai_ask_ai_generator_uses_plain_text_responses_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.ASK_AI_MODEL", "gpt-test")
    client = FakeOpenAIResponsesClient(response=type("Response", (), {"output_text": "Based on this transcript, practice examples."})())
    generator = OpenAIInterviewAskAIGenerator(openai_client=client)

    result = generator.generate(context="Transcript entries:\nQuestion: Q\nAnswer: A", question="What should I improve?")

    assert result["answer_text"].startswith("Based on this transcript")
    assert client.calls[0]["model"] == "gpt-test"
    assert "text" not in client.calls[0]
    assert client.calls[0]["store"] is False


def test_openai_ask_ai_generator_cleans_escaped_markdown_and_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.ASK_AI_MODEL", "gpt-test")
    client = FakeOpenAIResponsesClient(
        response=type(
            "Response",
            (),
            {"output_text": r"\### Focus\n\n\- \*\*depth\*\*\n1\. Improve examples&#x20;"},
        )()
    )
    generator = OpenAIInterviewAskAIGenerator(openai_client=client)

    result = generator.generate(context="Transcript entries:\nQuestion: Q\nAnswer: A", question="What should I improve?")

    assert result["answer_text"] == "Focus\n- depth\n1. Improve examples"
    assert r"\*" not in result["answer_text"]
    assert "&#x20;" not in result["answer_text"]


def test_openai_ask_ai_generator_empty_output_is_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.ASK_AI_MODEL", "gpt-test")
    client = FakeOpenAIResponsesClient(response=type("Response", (), {"output_text": ""})())
    generator = OpenAIInterviewAskAIGenerator(openai_client=client)

    with pytest.raises(ProviderError) as error:
        generator.generate(context="Transcript entries:\nQuestion: Q\nAnswer: A", question="What should I improve?")

    assert error.value.provider == "openai"
    assert error.value.model == "gpt-test"
    assert error.value.error_type == "empty_response"


def test_openai_ask_ai_bad_request_logs_safe_fields_without_prompt_leak(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr("app.cloud.interview_ask_ai.settings.ASK_AI_MODEL", "gpt-test")
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "Bad field", "param": "input", "code": "invalid_request_error"}},
    )
    client = FakeOpenAIResponsesClient(error=BadRequestError("bad request", response=response, body=response.json()))
    generator = OpenAIInterviewAskAIGenerator(openai_client=client)

    with caplog.at_level(logging.WARNING, logger="cloud_interview_ask_ai"), pytest.raises(ProviderError):
        generator.generate(context="secret transcript", question="secret question")

    assert "provider=openai" in caplog.text
    assert "error_type=BadRequestError" in caplog.text
    assert "error_code=invalid_request_error" in caplog.text
    assert "error_param=input" in caplog.text
    assert "secret transcript" not in caplog.text
    assert "secret question" not in caplog.text
    assert "unit-test-key" not in caplog.text
