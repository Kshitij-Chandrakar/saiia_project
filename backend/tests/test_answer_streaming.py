from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import generate as generate_api
from fastapi import HTTPException


async def _collect_stream_events(response) -> list[dict]:
    body = ""
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            body += chunk.decode("utf-8")
        else:
            body += str(chunk)
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def _session_record() -> dict:
    return {
        "id": "30000000-0000-4000-8000-000000000001",
        "user_id": "user-a",
        "status": "active",
        "started_at": "2026-08-29T10:30:00Z",
    }


@pytest.mark.asyncio
async def test_generate_stream_forwards_deltas_before_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_stream_openai_primary_answer(**_kwargs):
        yield {"type": "delta", "text": "System "}
        yield {"type": "delta", "text": "design"}
        yield {
            "type": "primary_result",
            "result": {
                "answer": "System design",
                "provider": "openai",
                "model": "gpt-5.4-mini-2026-03-17",
                "primary_provider": "openai",
                "primary_model": "gpt-5.4-mini-2026-03-17",
                "fallback_used": False,
                "error": None,
                "generation_ms": 10.0,
                "primary_generation_ms": 10.0,
            },
        }

    def fake_generate_answer(**kwargs):
        result = dict(kwargs["primary_result_override"])
        result.update(
            {
                "answer_type": "technical_concept",
                "plan_confidence": 0.9,
                "profile_context_policy": "FORBIDDEN",
                "job_context_policy": "FORBIDDEN",
                "general_knowledge_policy": "ALLOWED",
                "validation_status": "passed",
                "validation_issues_count": 0,
                "reasoning_effort": "low",
                "answer_verified": True,
            }
        )
        return result

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="What is system design?",
            category="technical",
            profile_context_used=True,
        )
    )
    events = await _collect_stream_events(response)

    assert [event["type"] for event in events[:3]] == ["start", "delta", "delta"]
    assert events[-1]["type"] == "done"
    assert "".join(event.get("text", "") for event in events if event["type"] == "delta") == "System design"
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")
    assert metadata["model"] == "gpt-5.4-mini-2026-03-17"
    assert metadata["profile_context_policy"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_generate_stream_sanitizes_split_internal_category_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    clean_answer = (
        "AI, or artificial intelligence, is software that performs tasks that usually "
        "require human intelligence."
    )

    def fake_stream_openai_primary_answer(**_kwargs):
        yield {"type": "delta", "text": "[[cate"}
        yield {"type": "delta", "text": "gory:tech"}
        yield {"type": "delta", "text": f"nical]]\n{clean_answer}"}
        yield {
            "type": "primary_result",
            "result": {
                "answer": f"[[category:technical]]\n{clean_answer}",
                "provider": "openai",
                "model": "gpt-5.4-mini-2026-03-17",
                "primary_provider": "openai",
                "primary_model": "gpt-5.4-mini-2026-03-17",
                "fallback_used": False,
                "error": None,
                "generation_ms": 10.0,
                "primary_generation_ms": 10.0,
            },
        }

    def fake_generate_answer(**kwargs):
        result = dict(kwargs["primary_result_override"])
        result["answer"] = clean_answer
        result["answer_category"] = "technical"
        result["generation_ms"] = 10.0
        return result

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(question="What is AI?", category="technical")
    )
    events = await _collect_stream_events(response)
    streamed_text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert "[[category:technical]]" not in streamed_text
    assert streamed_text == clean_answer
    assert metadata["generate_category"] == "technical"
    assert metadata["internal_marker_removed_count"] == 1
    assert metadata["category_metadata_separated"] is True
    assert not [event for event in events if event["type"] == "replace"]


@pytest.mark.asyncio
async def test_generate_stream_emits_replace_for_validated_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    monkeypatch.setattr(
        generate_api.generator,
        "stream_openai_primary_answer",
        lambda **_kwargs: iter(
            [
                {"type": "delta", "text": "Primary"},
                {
                    "type": "primary_result",
                    "result": {
                        "answer": "Primary",
                        "provider": "openai",
                        "model": "gpt-5.4-mini-2026-03-17",
                        "primary_provider": "openai",
                        "primary_model": "gpt-5.4-mini-2026-03-17",
                        "fallback_used": False,
                        "error": None,
                        "generation_ms": 10.0,
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: {
            **dict(kwargs["primary_result_override"]),
            "answer": "Corrected primary",
            "provider": "openai",
            "model": "gpt-5.4-mini-2026-03-17",
            "fallback_used": False,
            "generation_ms": 10.0,
            "correction_status": "used",
        },
    )

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(question="What is caching?", category="technical")
    )
    events = await _collect_stream_events(response)

    replace_events = [event for event in events if event["type"] == "replace"]
    assert len(replace_events) == 1
    assert replace_events[0]["answer"] == "Corrected primary"


@pytest.mark.asyncio
async def test_generate_stream_uses_resolved_followup_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    captured = {}

    def fake_stream_openai_primary_answer(**kwargs):
        captured["stream_question"] = kwargs["question"]
        yield {"type": "delta", "text": "Examples"}
        yield {
            "type": "primary_result",
            "result": {
                "answer": "Examples",
                "provider": "openai",
                "model": "gpt-5.4-mini-2026-03-17",
                "fallback_used": False,
                "error": None,
                "generation_ms": 5.0,
            },
        }

    def fake_generate_answer(**kwargs):
        captured["final_question"] = kwargs["question"]
        return {
            **dict(kwargs["primary_result_override"]),
            "answer_type": "technical_concept",
            "plan_confidence": 0.9,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
        }

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="What are its examples?",
            original_question="What are its examples?",
            category="technical",
            followup_mode="answer",
            followup_context=[
                {
                    "entry_id": "a1",
                    "mode": "answer",
                    "original_question": "What is supervised learning?",
                    "resolved_question": "What is supervised learning?",
                    "created_at": __import__("time").time(),
                }
            ],
        )
    )
    events = await _collect_stream_events(response)
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert "supervised learning" in captured["stream_question"].lower()
    assert captured["stream_question"] == captured["final_question"]
    assert metadata["original_question"] == "What are its examples?"
    assert "supervised learning" in metadata["resolved_question"].lower()
    assert metadata["follow_up_detected"] is True


@pytest.mark.asyncio
async def test_generate_stream_clarifies_followup_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)

    def fail_model_call(**_kwargs):
        raise AssertionError("model should not be called for unresolved follow-up")

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fail_model_call)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="Can you give another example?",
            original_question="Can you give another example?",
            category="technical",
            followup_mode="answer",
            followup_context=[],
        )
    )
    events = await _collect_stream_events(response)
    text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert "Which earlier topic" in text
    assert metadata["clarification_required"] is True
    assert metadata["follow_up_resolution_status"] == "needs_clarification"


@pytest.mark.asyncio
async def test_generate_stream_answers_complete_technical_question_without_followup_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    captured = {}

    def fake_stream_openai_primary_answer(**kwargs):
        captured["stream_question"] = kwargs["question"]
        yield {"type": "delta", "text": "Dependency injection means dependencies are passed in."}
        yield {
            "type": "primary_result",
            "result": {
                "answer": "Dependency injection means dependencies are passed in.",
                "provider": "openai",
                "model": "gpt-5.4-mini-2026-03-17",
                "fallback_used": False,
                "error": None,
                "generation_ms": 5.0,
            },
        }

    def fake_generate_answer(**kwargs):
        captured["final_question"] = kwargs["question"]
        return {
            **dict(kwargs["primary_result_override"]),
            "answer_type": "technical_concept",
            "plan_confidence": 0.9,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
        }

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="How is dependency injection implemented?",
            original_question="How is dependency injection implemented?",
            category="technical",
            followup_mode="answer",
            followup_context=[],
        )
    )
    events = await _collect_stream_events(response)
    text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert captured["stream_question"] == "How is dependency injection implemented?"
    assert captured["final_question"] == "How is dependency injection implemented?"
    assert "Which earlier topic should I connect this follow-up to?" not in text
    assert metadata["clarification_required"] is False
    assert metadata["follow_up_detected"] is False


@pytest.mark.asyncio
async def test_generate_stream_preserves_selected_resume_http_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    monkeypatch.setattr(
        generate_api.job_context_service,
        "get_context",
        lambda: {"saved": False},
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_resume_service",
        lambda: type(
            "FakeCloudResumeService",
            (),
            {
                "retrieve_resume_chunks": staticmethod(
                    lambda **_kwargs: (_ for _ in ()).throw(
                        generate_api.HTTPException(status_code=409, detail="Selected resume is not ready for generation.")
                    )
                )
            },
        )(),
    )

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="Tell me about your projects",
            category="hr",
            profile_context_used=True,
            selected_resume_id="10000000-0000-4000-8000-000000000001",
        ),
        request=object(),
    )
    events = await _collect_stream_events(response)

    assert events[1] == {
        "type": "error",
        "request_id": events[0]["request_id"],
        "error": "http_error",
        "status_code": 409,
        "detail": "Selected resume is not ready for generation.",
        "partial": False,
    }
    assert events[-1]["type"] == "done"
    assert events[-1]["incomplete"] is False


@pytest.mark.asyncio
async def test_generate_stream_primary_success_with_session_id_stores_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    transcript_calls = []

    monkeypatch.setattr(
        generate_api,
        "_new_cloud_interview_session_service",
        lambda: type(
            "FakeInterviewSessionService",
            (),
            {"get_session": staticmethod(lambda **_kwargs: _session_record())},
        )(),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )

    def fake_stream_openai_primary_answer(**_kwargs):
        yield {"type": "delta", "text": "Streaming "}
        yield {"type": "delta", "text": "answer"}
        yield {
            "type": "primary_result",
            "result": {
                "answer": "Streaming answer",
                "provider": "openai",
                "model": "gpt-5.4-mini-2026-03-17",
                "primary_provider": "openai",
                "primary_model": "gpt-5.4-mini-2026-03-17",
                "fallback_used": False,
                "error": None,
                "generation_ms": 10.0,
                "primary_generation_ms": 10.0,
            },
        }

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: {
            **dict(kwargs["primary_result_override"]),
            "answer": "Streaming answer",
            "answer_type": "technical_concept",
            "generate_source": "chat",
            "generate_category": "technical",
            "follow_up_detected": False,
            "follow_up_resolution_status": "standalone",
        },
    )

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="What is streaming?",
            original_question="What is streaming?",
            category="technical",
            source="chat",
            session_id=_session_record()["id"],
            request_id="stream-1",
        ),
        request=object(),
    )
    events = await _collect_stream_events(response)
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert metadata["transcript_entry_stored"] is True
    assert metadata["transcript_store_error"] is None
    assert transcript_calls[0]["payload"]["source"] == "chat"
    assert transcript_calls[0]["payload"]["question_text"] == "What is streaming?"
    assert transcript_calls[0]["payload"]["answer_text"] == "Streaming answer"


@pytest.mark.asyncio
async def test_generate_stream_fallback_success_with_session_id_stores_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.settings, "ENABLE_ANSWER_PROVIDER_FALLBACK", True)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    transcript_calls = []

    monkeypatch.setattr(
        generate_api,
        "_new_cloud_interview_session_service",
        lambda: type(
            "FakeInterviewSessionService",
            (),
            {"get_session": staticmethod(lambda **_kwargs: _session_record())},
        )(),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "stream_openai_primary_answer",
        lambda **_kwargs: (_ for _ in ()).throw(
            generate_api.ProviderError(
                "stream failed",
                provider="openai",
                model="gpt-5.4-mini-2026-03-17",
                error_type="provider_error",
            )
        ),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **_kwargs: {
            "answer": "Fallback answer",
            "provider": "groq",
            "model": "llama-test",
            "primary_provider": "openai",
            "primary_model": "gpt-5.4-mini-2026-03-17",
            "fallback_used": True,
            "error": None,
            "generation_ms": 12.0,
            "generate_source": "answer",
            "generate_category": "technical",
        },
    )

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="Fallback question?",
            original_question="Fallback question?",
            category="technical",
            source="answer",
            session_id=_session_record()["id"],
            request_id="stream-2",
        ),
        request=object(),
    )
    events = await _collect_stream_events(response)
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert metadata["transcript_entry_stored"] is True
    assert transcript_calls[0]["payload"]["source"] == "answer"
    assert transcript_calls[0]["payload"]["answer_text"] == "Fallback answer"


@pytest.mark.asyncio
async def test_generate_stream_clarification_with_session_id_stores_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    transcript_calls = []

    monkeypatch.setattr(
        generate_api,
        "_new_cloud_interview_session_service",
        lambda: type(
            "FakeInterviewSessionService",
            (),
            {"get_session": staticmethod(lambda **_kwargs: _session_record())},
        )(),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "stream_openai_primary_answer",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model should not be called")),
    )

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="Can you give another example?",
            original_question="Can you give another example?",
            category="technical",
            followup_mode="answer",
            followup_context=[],
            source="chat",
            session_id=_session_record()["id"],
            request_id="stream-3",
        ),
        request=object(),
    )
    events = await _collect_stream_events(response)
    metadata = next(event["metadata"] for event in events if event["type"] == "metadata")

    assert metadata["transcript_entry_stored"] is True
    assert transcript_calls[0]["payload"]["source"] == "chat"
    assert "Which earlier topic" in transcript_calls[0]["payload"]["answer_text"]


@pytest.mark.asyncio
async def test_generate_stream_incomplete_failure_does_not_store_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api.settings, "ENABLE_ANSWER_PROVIDER_FALLBACK", False)
    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    transcript_calls = []

    monkeypatch.setattr(
        generate_api,
        "_new_cloud_interview_session_service",
        lambda: type(
            "FakeInterviewSessionService",
            (),
            {"get_session": staticmethod(lambda **_kwargs: _session_record())},
        )(),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )

    def fake_stream_openai_primary_answer(**_kwargs):
        yield {"type": "delta", "text": "partial"}
        raise generate_api.ProviderError(
            "stream failed",
            provider="openai",
            model="gpt-5.4-mini-2026-03-17",
            error_type="provider_error",
        )

    monkeypatch.setattr(generate_api.generator, "stream_openai_primary_answer", fake_stream_openai_primary_answer)

    response = await generate_api.generate_answer_stream(
        generate_api.GenerateRequest(
            question="Explain caching.",
            category="technical",
            source="chat",
            session_id=_session_record()["id"],
            request_id="stream-4",
        ),
        request=object(),
    )
    events = await _collect_stream_events(response)

    assert events[-1]["type"] == "done"
    assert events[-1]["incomplete"] is True
    assert transcript_calls == []


@pytest.mark.asyncio
async def test_generate_stream_rejects_malformed_session_id_before_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    transcript_calls = []
    generator_called = {"value": False}

    monkeypatch.setattr(
        generate_api.generator,
        "stream_openai_primary_answer",
        lambda **_kwargs: generator_called.__setitem__("value", True),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )

    with pytest.raises(HTTPException, match="Interview session id is invalid."):
        await generate_api.generate_answer_stream(
            generate_api.GenerateRequest(
                question="Bad session?",
                category="technical",
                session_id="not-a-uuid",
            )
        )

    assert generator_called["value"] is False
    assert transcript_calls == []


@pytest.mark.asyncio
async def test_generate_stream_rejects_cross_user_session_id_before_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_api.settings, "ENABLE_TRUE_ANSWER_STREAMING", True)
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: type("CurrentUser", (), {"user_id": "user-a"})())
    transcript_calls = []
    generator_called = {"value": False}

    monkeypatch.setattr(
        generate_api,
        "_new_cloud_interview_session_service",
        lambda: type(
            "FakeInterviewSessionService",
            (),
            {
                "get_session": staticmethod(
                    lambda **_kwargs: (_ for _ in ()).throw(
                        generate_api.CloudInterviewSessionNotFoundError("Interview session was not found.")
                    )
                )
            },
        )(),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "stream_openai_primary_answer",
        lambda **_kwargs: generator_called.__setitem__("value", True),
    )
    monkeypatch.setattr(
        generate_api,
        "_new_cloud_transcript_service",
        lambda: type(
            "FakeTranscriptService",
            (),
            {
                "create_transcript_entry": staticmethod(
                    lambda **kwargs: transcript_calls.append(kwargs)
                )
            },
        )(),
    )

    with pytest.raises(HTTPException, match="Interview session was not found."):
        await generate_api.generate_answer_stream(
            generate_api.GenerateRequest(
                question="Cross-user?",
                category="technical",
                session_id=_session_record()["id"],
            ),
            request=object(),
        )

    assert generator_called["value"] is False
    assert transcript_calls == []
