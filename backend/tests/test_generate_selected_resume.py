from typing import Any

import pytest

from app.api import generate as generate_api
from app.auth.supabase_auth import CurrentUser
from app.cloud.cloud_resume import CloudResumeNotFoundError, CloudResumeValidationError
from app.nlp.answer_generator import AnswerGenerator


SELECTED_RESUME_ID = "10000000-0000-4000-8000-000000000001"


def _result(**overrides: Any) -> dict[str, Any]:
    payload = {
        "answer": "Selected resume answer",
        "provider": "openai",
        "model": "gpt-5.4-mini-2026-03-17",
        "fallback_used": False,
        "error": None,
        "generation_ms": 1.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_generate_uses_selected_cloud_resume_for_authenticated_user(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **kwargs: Any) -> dict[str, Any]:
            captured["cloud_kwargs"] = kwargs
            return {
                "retrieval_used": True,
                "retrieved_chunks": [{"section": "summary", "text": "Selected Resume A"}],
                "retrieval_ms": 1.0,
                "selected_resume_candidate_name": "Devanshu Chandrakar",
                "selected_resume_candidate_name_source": "metadata",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(
        generate_api.resume_index_service,
        "retrieve",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("local resume retrieval should not be used")),
    )
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        captured["profile"] = kwargs["profile"]
        captured["profile_context_enabled"] = kwargs["profile_context_enabled"]
        return _result()

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Introduce yourself",
            category="personal",
            profile={
                "full_name": "Kshitij",
                "projects": "OLD_PROFILE_PROJECT",
                "professional_summary": "Old default profile",
            },
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.answer == "Selected resume answer"
    assert response.retrieval_used is True
    assert response.retrieved_chunk_count == 1
    assert response.resume_context_source == "selected_resume"
    assert response.selected_resume_id_used is True
    assert response.selected_resume_chunk_count == 1
    assert response.selected_resume_candidate_name_available is True
    assert response.selected_resume_candidate_name_source == "metadata"
    assert response.profile_context_suppressed_by_selected_resume is True
    assert response.final_context_priority == "selected_resume_first"
    assert captured["cloud_kwargs"]["user_id"] == "user-a"
    assert captured["cloud_kwargs"]["resume_id"] == SELECTED_RESUME_ID
    assert captured["retrieved_snippets"][0]["text"] == "Selected Resume A"
    assert "Selected Resume A" in captured["profile"]["resume"]
    assert captured["profile"]["full_name"] == "Devanshu Chandrakar"
    assert "Kshitij" not in str(captured["profile"])
    assert "OLD_PROFILE_PROJECT" not in str(captured["profile"])
    assert captured["profile_context_enabled"] is True


@pytest.mark.anyio
async def test_generate_rejects_cross_user_selected_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            raise CloudResumeNotFoundError("not owned")

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    with pytest.raises(generate_api.HTTPException) as exc_info:
        await generate_api.generate_answer(
            generate_api.GenerateRequest(
                question="Introduce yourself",
                category="personal",
                profile_context_used=True,
                selected_resume_id=SELECTED_RESUME_ID,
            ),
            request=object(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Selected resume was not found."


@pytest.mark.anyio
async def test_generate_rejects_unready_selected_resume_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            raise CloudResumeValidationError("not ready")

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(
        generate_api.resume_index_service,
        "retrieve",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("selected resume must not fall back")),
    )
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    with pytest.raises(generate_api.HTTPException) as exc_info:
        await generate_api.generate_answer(
            generate_api.GenerateRequest(
                question="Introduce yourself",
                category="personal",
                profile_context_used=True,
                selected_resume_id=SELECTED_RESUME_ID,
            ),
            request=object(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Selected resume is not ready for generation."


@pytest.mark.anyio
async def test_generate_selected_resume_bypasses_old_profile_context_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **kwargs: Any) -> dict[str, Any]:
            captured["cloud_kwargs"] = kwargs
            return {
                "retrieval_used": True,
                "retrieved_chunks": [{"section": "projects", "text": "Selected Resume A project"}],
                "retrieval_ms": 1.0,
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        captured["profile_context_enabled"] = kwargs["profile_context_enabled"]
        return _result(answer="Selected resume answer")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Introduce yourself",
            category="personal",
            profile_context_used=False,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.answer == "Selected resume answer"
    assert response.profile_context_used is False
    assert response.resume_context_source == "selected_resume"
    assert response.selected_resume_id_used is True
    assert response.profile_context_suppressed_by_selected_resume is False
    assert response.final_context_priority == "selected_resume_first"
    assert captured["cloud_kwargs"]["resume_id"] == SELECTED_RESUME_ID
    assert captured["retrieved_snippets"][0]["text"] == "Selected Resume A project"
    assert captured["profile_context_enabled"] is True


@pytest.mark.anyio
async def test_generate_without_selected_resume_preserves_local_resume_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_local_retrieve(**kwargs: Any) -> dict[str, Any]:
        captured["local_kwargs"] = kwargs
        return {
            "retrieval_used": True,
            "retrieved_chunks": [{"section": "summary", "text": "Local active resume"}],
            "retrieval_ms": 1.0,
        }

    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", fake_local_retrieve)
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        return _result(answer="Local resume answer")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Introduce yourself",
            category="personal",
            profile_context_used=True,
        )
    )

    assert response.answer == "Local resume answer"
    assert response.retrieval_used is True
    assert response.resume_context_source == "local_resume"
    assert response.selected_resume_id_used is False
    assert response.selected_resume_chunk_count == 0
    assert response.profile_context_suppressed_by_selected_resume is False
    assert response.final_context_priority == "active_resume_first"
    assert captured["local_kwargs"]["question"] == "Introduce yourself"
    assert captured["retrieved_snippets"][0]["text"] == "Local active resume"


def test_selected_resume_prompt_marks_uploaded_resume_authoritative() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Introduce yourself.",
        "hr",
        profile={
            "selected_resume_authoritative": True,
            "resume": "name: Devanshu\nproject: UNIQUE_SELECTED_RESUME_PROJECT",
            "professional_summary": "Devanshu selected resume summary",
            "projects": "UNIQUE_SELECTED_RESUME_PROJECT",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "name: Devanshu\nproject: UNIQUE_SELECTED_RESUME_PROJECT",
            }
        ],
        profile_context_enabled=True,
    )

    assert "selected uploaded resume is the authoritative candidate context" in prompt
    assert "UNIQUE_SELECTED_RESUME_PROJECT" in prompt
    assert "OLD_PROFILE_PROJECT" not in prompt


def test_selected_resume_profile_extracts_clear_candidate_name() -> None:
    profile = generate_api._selected_resume_profile(
        [
            {"section": "full_name", "text": "DEVANSHU CHANDRAKAR"},
            {"section": "professional_summary", "text": "Computer Science undergraduate."},
        ]
    )

    assert profile["full_name"] == "DEVANSHU CHANDRAKAR"
    assert profile["selected_resume_authoritative"] is True


def test_selected_resume_profile_does_not_invent_unclear_name() -> None:
    profile = generate_api._selected_resume_profile(
        [
            {"section": "professional_summary", "text": "Computer Science undergraduate with Python projects."},
            {"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"},
        ]
    )

    assert "full_name" not in profile


def test_selected_resume_intro_prompt_uses_selected_name_over_stale_profile() -> None:
    generator = AnswerGenerator()
    selected_profile = generate_api._selected_resume_profile(
        [
            {"section": "full_name", "text": "DEVANSHU CHANDRAKAR"},
            {"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"},
        ]
    )

    prompt = generator._build_prompt(
        "Introduce yourself",
        "hr",
        profile=selected_profile,
        retrieved_snippets=[{"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"}],
        profile_context_enabled=True,
    )

    assert "Candidate name: DEVANSHU CHANDRAKAR" in prompt
    assert "Use the candidate name from the selected resume naturally" in prompt
    assert "Kshitij" not in prompt


@pytest.mark.anyio
async def test_selected_resume_name_metadata_survives_project_only_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [{"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"}],
                "retrieval_ms": 1.0,
                "selected_resume_candidate_name": "Devanshu Chandrakar",
                "selected_resume_candidate_name_source": "metadata",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["profile"] = kwargs["profile"]
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        return _result()

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Introduce yourself",
            category="hr",
            profile={"full_name": "Kshitij"},
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert captured["profile"]["full_name"] == "Devanshu Chandrakar"
    assert captured["retrieved_snippets"][0]["section"] == "projects"
    assert response.selected_resume_candidate_name_available is True
    assert response.selected_resume_candidate_name_source == "metadata"


def test_selected_resume_name_is_not_forced_into_non_intro_prompt() -> None:
    generator = AnswerGenerator()
    selected_profile = generate_api._selected_resume_profile(
        [
            {"section": "full_name", "text": "DEVANSHU CHANDRAKAR"},
            {"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"},
        ]
    )

    prompt = generator._build_prompt(
        "Explain your main project",
        "hr",
        profile=selected_profile,
        retrieved_snippets=[{"section": "projects", "text": "UNIQUE_SELECTED_RESUME_PROJECT"}],
        profile_context_enabled=True,
    )

    assert "Use the candidate name from the selected resume naturally" not in prompt
