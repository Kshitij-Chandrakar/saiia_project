from typing import Any

import pytest

from app.cloud.interview_sessions import CloudInterviewSessionValidationError
from app.cloud.interview_transcripts import (
    CloudInterviewTranscriptEntryRecord,
    CloudInterviewTranscriptService,
    CreateInterviewTranscriptEntryResult,
)


USER_ID = "00000000-0000-4000-8000-000000000001"
SESSION_ID = "30000000-0000-4000-8000-000000000001"


def _entry(**overrides: Any) -> CloudInterviewTranscriptEntryRecord:
    payload = {
        "id": "40000000-0000-4000-8000-000000000001",
        "user_id": USER_ID,
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
    return CloudInterviewTranscriptEntryRecord(**payload)


class FakeTranscriptClient:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.pages: dict[int, list[CloudInterviewTranscriptEntryRecord]] = {
            1: [_entry(turn_index=1), _entry(id="40000000-0000-4000-8000-000000000002", turn_index=2)],
            2: [],
        }

    def create_transcript_entry(self, *, user_id: str, session_id: str, payload: dict[str, Any]) -> CreateInterviewTranscriptEntryResult:
        self.create_calls.append({"user_id": user_id, "session_id": session_id, "payload": payload})
        return CreateInterviewTranscriptEntryResult(record=_entry(), replayed=bool(payload.get("request_id")))

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int) -> list[CloudInterviewTranscriptEntryRecord]:
        self.list_calls.append(
            {"user_id": user_id, "session_id": session_id, "limit": limit, "page": page}
        )
        return list(self.pages.get(page, []))


def test_create_transcript_entry_normalizes_payload_and_keeps_user_server_derived() -> None:
    client = FakeTranscriptClient()
    service = CloudInterviewTranscriptService(client=client)

    result = service.create_transcript_entry(
        user_id=USER_ID,
        session_id=SESSION_ID,
        payload={
            "request_id": "turn-1",
            "source": " chat ",
            "question_text": " What is FastAPI authentication? ",
            "answer_text": " It uses dependency-based auth checks. ",
            "category": " technical ",
            "provider": " openai ",
            "model": " gpt-test ",
            "generation_ms": 123.4,
            "metadata": {"follow_up_detected": False, "unsafe": {"nested": "ok"}},
        },
    )

    assert result.record.turn_index == 1
    assert result.replayed is True
    assert client.create_calls == [
        {
            "user_id": USER_ID,
            "session_id": SESSION_ID,
            "payload": {
                "request_id": "turn-1",
                "source": "chat",
                "question_text": "What is FastAPI authentication?",
                "answer_text": "It uses dependency-based auth checks.",
                "category": "technical",
                "provider": "openai",
                "model": "gpt-test",
                "generation_ms": 123,
                "metadata": {"follow_up_detected": False, "unsafe": {"nested": "ok"}},
            },
        }
    ]


def test_create_transcript_entry_rejects_client_supplied_user_id() -> None:
    service = CloudInterviewTranscriptService(client=FakeTranscriptClient())

    with pytest.raises(CloudInterviewSessionValidationError, match="user_id is server-derived"):
        service.create_transcript_entry(
            user_id=USER_ID,
            session_id=SESSION_ID,
            payload={
                "user_id": "different-user",
                "question_text": "Question",
                "answer_text": "Answer",
            },
        )


def test_export_transcript_paginates_and_omits_session_id() -> None:
    client = FakeTranscriptClient()
    client.pages[1] = [
        _entry(id=f"40000000-0000-4000-8000-{index:012d}", turn_index=index)
        for index in range(1, 201)
    ]
    client.pages[2] = [_entry(
        id="40000000-0000-4000-8000-000000000201",
        turn_index=201,
        question_text="How does transcript export work?",
        answer_text="It walks paginated entries.",
    )]
    service = CloudInterviewTranscriptService(client=client)

    markdown = service.export_transcript(user_id=USER_ID, session_id=SESSION_ID, format="md")
    text = service.export_transcript(user_id=USER_ID, session_id=SESSION_ID, format="txt")

    assert "# Interview Transcript" in markdown
    assert "## Turn 201" in markdown
    assert "Session ID:" not in markdown
    assert "Interview Transcript" in text
    assert "Turn 201" in text
    assert "Session ID:" not in text
    assert client.list_calls[0]["page"] == 1
    assert any(call["page"] == 2 for call in client.list_calls)


def test_export_transcript_rejects_invalid_format() -> None:
    service = CloudInterviewTranscriptService(client=FakeTranscriptClient())

    with pytest.raises(CloudInterviewSessionValidationError, match="format must be txt or md"):
        service.export_transcript(user_id=USER_ID, session_id=SESSION_ID, format="pdf")
