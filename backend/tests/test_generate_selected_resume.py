from typing import Any

import pytest

from app.api import generate as generate_api
from app.auth.supabase_auth import CurrentUser
from app.cloud.cloud_resume import CloudResumeNotFoundError, CloudResumeValidationError, question_has_project_intent
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
    assert response.profile_context_suppressed_by_selected_resume is False
    assert response.selected_resume_strict_mode is True
    assert response.selected_resume_context_used_in_prompt is True
    assert response.generic_fallback_blocked is True
    assert response.profile_fallback_blocked is True
    assert response.final_context_priority == "selected_resume_only"
    assert response.profile_context_used is False
    assert captured["cloud_kwargs"]["user_id"] == "user-a"
    assert captured["cloud_kwargs"]["resume_id"] == SELECTED_RESUME_ID
    assert captured["retrieved_snippets"][0]["text"] == "Selected Resume A"
    assert "Selected Resume A" in captured["profile"]["resume"]
    assert captured["profile"]["full_name"] == "Devanshu Chandrakar"
    assert "Kshitij" not in str(captured["profile"])
    assert "OLD_PROFILE_PROJECT" not in str(captured["profile"])
    assert captured["profile_context_enabled"] is True


@pytest.mark.anyio
async def test_generate_includes_screen_four_job_context_with_selected_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [
                    {
                        "section": "projects",
                        "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
                    }
                ],
                "retrieval_ms": 1.0,
                "project_context_chunks_found": 1,
                "project_context_source": "selected_resume_projects",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(
        generate_api.job_context_service,
        "get_context",
        lambda: (_ for _ in ()).throw(AssertionError("saved local job context should not be loaded")),
    )

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["profile"] = kwargs["profile"]
        captured["job_context"] = kwargs["job_context"]
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        return _result(answer="AI Study Assistant project answer")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="tell me about your projects",
            category="hr",
            profile={"projects": "organizing my space"},
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
            target_role="Generative AI Intern",
            company_name="Test Company",
            job_description="Looking for RAG, LangChain, FastAPI, vector database, and document processing.",
        ),
        request=object(),
    )

    assert response.answer == "AI Study Assistant project answer"
    assert response.selected_resume_strict_mode is True
    assert response.profile_fallback_blocked is True
    assert response.job_context_included is True
    assert response.target_role_included is True
    assert response.project_intent_detected is True
    assert response.project_context_chunks_found == 1
    assert response.project_context_source == "selected_resume_projects"
    assert response.generic_project_fallback_blocked is True
    assert response.final_context_priority == "selected_resume_plus_job_context"
    assert captured["profile"]["selected_resume_authoritative"] is True
    assert "organizing my space" not in str(captured["profile"])
    assert captured["job_context"]["target_role"] == "Generative AI Intern"
    assert captured["job_context"]["company_name"] == "Test Company"
    assert "vector database" in captured["job_context"]["job_description"]
    assert captured["retrieved_snippets"][0]["section"] == "projects"


@pytest.mark.anyio
async def test_job_context_policy_forbidden_skips_session_job_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(
        generate_api.job_context_service,
        "get_context",
        lambda: (_ for _ in ()).throw(AssertionError("saved job context should stay forbidden")),
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: _result(answer="Definition answer", job_context_policy="FORBIDDEN", answer_type="technical_concept"),
    )

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="What is dependency injection?",
            category="technical",
            profile_context_used=True,
            target_role="Backend Developer",
            company_name="Test Company",
            job_description="Looking for dependency injection knowledge.",
        ),
        request=object(),
    )

    assert response.job_context_included is False


def test_shared_project_intent_predicate_matches_generate_and_retrieval_terms() -> None:
    positive = "What did you build in your project?"
    negative = "How is dependency injection implemented?"

    assert question_has_project_intent(positive) is True
    assert generate_api.question_has_project_intent(positive) is True
    assert question_has_project_intent(negative) is False
    assert generate_api.question_has_project_intent(negative) is False


@pytest.mark.anyio
async def test_generate_selected_resume_project_answer_uses_project_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [
                    {
                        "section": "projects",
                        "text": "AI Study Assistant - Built document processing, chunking, embeddings, RAG, Chroma, LangChain, Gemini API, and FastAPI.",
                    }
                ],
                "retrieval_ms": 1.0,
                "project_context_chunks_found": 1,
                "project_context_source": "selected_resume_projects",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        return _result(answer="AI Study Assistant answer")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="tell me something about your project",
            category="hr",
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.project_context_source == "selected_resume_projects"
    assert response.project_context_chunks_found == 1
    assert any("AI Study Assistant" in chunk["text"] for chunk in captured["retrieved_snippets"])


@pytest.mark.anyio
async def test_generate_selected_resume_general_project_question_keeps_project_snippets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [
                    {
                        "section": "projects",
                        "text": "AI Study Assistant - Built document processing, chunking, embeddings, RAG, Chroma, LangChain, Gemini API, and FastAPI.",
                    }
                ],
                "retrieval_ms": 1.0,
                "project_context_chunks_found": 1,
                "project_context_source": "selected_resume_projects",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**kwargs: Any) -> dict[str, Any]:
        captured["retrieved_snippets"] = kwargs["retrieved_snippets"]
        captured["profile"] = kwargs["profile"]
        return _result(answer="AI Study Assistant answer", answer_category="general")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="can you explain your projects from my selected resume?",
            category="general",
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.answer == "AI Study Assistant answer"
    assert response.project_intent_detected is True
    assert response.project_context_source == "selected_resume_projects"
    assert captured["retrieved_snippets"][0]["section"] == "projects"
    assert captured["profile"]["selected_resume_authoritative"] is True


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
async def test_generate_rejects_selected_resume_without_project_details(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            raise CloudResumeValidationError(
                "The selected resume is ready, but it does not contain enough project details to answer this accurately."
            )

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
                question="can you explain your projects",
                category="hr",
                profile_context_used=True,
                selected_resume_id=SELECTED_RESUME_ID,
            ),
            request=object(),
        )

    assert exc_info.value.status_code == 409
    assert "does not contain enough project details" in exc_info.value.detail


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
    assert response.selected_resume_strict_mode is True
    assert response.selected_resume_context_used_in_prompt is True
    assert response.generic_fallback_blocked is True
    assert response.profile_fallback_blocked is True
    assert response.final_context_priority == "selected_resume_only"
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

    assert "STRICT SELECTED-RESUME MODE" in prompt
    assert "only authoritative candidate context" in prompt
    assert "UNIQUE_SELECTED_RESUME_PROJECT" in prompt
    assert "OLD_PROFILE_PROJECT" not in prompt


def test_selected_resume_project_prompt_blocks_generic_lifestyle_projects() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Tell me about your projects",
        "hr",
        profile={
            "selected_resume_authoritative": True,
            "resume": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            "projects": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            }
        ],
        profile_context_enabled=True,
    )

    assert "answer only using the selected resume project context" in prompt
    assert "detailed interview-style answer" in prompt
    assert "tech stack" in prompt
    assert "organizing" in prompt
    assert "recipe" in prompt
    assert "photo-album" in prompt


def test_selected_resume_general_project_prompt_includes_project_snippets() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Can you explain your projects from my selected resume?",
        "general",
        profile={
            "selected_resume_authoritative": True,
            "resume": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            "projects": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            }
        ],
        job_context={
            "saved": True,
            "target_role": "Backend Developer",
            "company_name": "Test Company",
            "job_description": "Looking for RAG, LangChain, FastAPI, vector retrieval, and document processing.",
        },
        source="chat",
        profile_context_enabled=True,
    )

    assert "Relevant resume snippets:" in prompt
    assert "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI." in prompt
    assert "Job and company context:" in prompt


def test_selected_resume_specific_project_prompt_enforces_detailed_project_mode() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Explain your AI-Powered Medical Insights Platform",
        "general",
        profile={
            "selected_resume_authoritative": True,
            "resume": "AI-Powered Medical Insights Platform using Streamlit, FAISS, and MiniLM.",
            "projects": "AI-Powered Medical Insights Platform using Streamlit, FAISS, and MiniLM.",
            "specific_project_intent_detected": True,
            "matched_project_name": "AI-Powered Medical Insights Platform",
            "project_answer_mode": "detailed_specific_project",
            "project_match_confidence": "exact",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI-Powered Medical Insights Platform - Built semantic search with Streamlit, FAISS, and MiniLM.",
            }
        ],
        job_context={
            "saved": True,
            "target_role": "Backend Developer",
            "company_name": "Test Company",
            "job_description": "Looking for semantic search and backend APIs.",
        },
        source="chat",
        profile_context_enabled=True,
    )

    assert "Focus on the specific selected-resume project 'AI-Powered Medical Insights Platform'" in prompt
    assert "If the question asks how the project was built" in prompt
    assert "If the question asks why a tool such as FAISS, MiniLM, Streamlit" in prompt
    assert "project purpose, tech stack, technical workflow, what you personally implemented or contributed" in prompt
    assert "Use 3 to 5 short interview-style paragraphs" in prompt
    assert "backend or API relevance" in prompt
    assert "Real-life example:" not in prompt


def test_selected_resume_general_project_prompt_skips_concept_example_format() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Tell me about your projects",
        "general",
        profile={
            "selected_resume_authoritative": True,
            "projects": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            }
        ],
        source="chat",
        profile_context_enabled=True,
    )

    assert "For project questions, answer only using the selected resume project context." in prompt
    assert "Real-life example:" not in prompt
    assert "The required daily-life example must be included" not in prompt


def test_selected_resume_project_refinement_prompt_skips_real_life_example_format() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_refinement_prompt(
        question="Explain your AI-Powered Medical Insights Platform",
        question_type="general",
        profile={
            "selected_resume_authoritative": True,
            "projects": "AI-Powered Medical Insights Platform using Streamlit, FAISS, and MiniLM.",
            "specific_project_intent_detected": True,
            "matched_project_name": "AI-Powered Medical Insights Platform",
            "project_answer_mode": "detailed_specific_project",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI-Powered Medical Insights Platform - Built semantic search with Streamlit, FAISS, and MiniLM.",
            }
        ],
        job_context=None,
        groq_answer="It is a project about medical insights.",
        source="chat",
        profile_context_enabled=True,
    )

    assert "Then write 'Real-life example:' on its own line." not in prompt
    assert "For conceptual answers, keep the direct explanation" not in prompt
    assert "Focus on the specific selected-resume project 'AI-Powered Medical Insights Platform'" in prompt


def test_selected_resume_specific_project_prompt_uses_job_context_for_role_relevant_closing() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "Explain your AI-Powered Medical Insights Platform",
        "general",
        profile={
            "selected_resume_authoritative": True,
            "projects": "AI-Powered Medical Insights Platform using Streamlit, FAISS, and MiniLM.",
            "specific_project_intent_detected": True,
            "matched_project_name": "AI-Powered Medical Insights Platform",
            "project_answer_mode": "detailed_specific_project",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI-Powered Medical Insights Platform - Built semantic search with Streamlit, FAISS, and MiniLM.",
            }
        ],
        job_context={
            "saved": True,
            "target_role": "Backend Developer",
            "company_name": "Test Company",
            "job_description": "Looking for backend APIs and semantic search systems.",
        },
        source="chat",
        profile_context_enabled=True,
    )

    assert "Use the target role, company, and job description only to tailor emphasis." in prompt
    assert "short closing that connects the project to the target role or job description" in prompt
    assert "backend or API relevance of your work clearly" in prompt


@pytest.mark.anyio
async def test_generate_specific_project_question_surfaces_project_match_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [
                    {
                        "section": "projects",
                        "text": "AI-Powered Medical Insights Platform - Built semantic search with Streamlit, FAISS, and MiniLM.",
                    }
                ],
                "retrieval_ms": 1.0,
                "project_context_chunks_found": 1,
                "project_context_source": "selected_resume_projects",
                "specific_project_intent_detected": True,
                "matched_project_name": "AI-Powered Medical Insights Platform",
                "project_match_confidence": "exact",
                "project_answer_mode": "detailed_specific_project",
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **_kwargs: _result(answer="Detailed project answer", answer_category="general"),
    )

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Explain your AI-Powered Medical Insights Platform",
            category="general",
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.specific_project_intent_detected is True
    assert response.matched_project_name == "AI-Powered Medical Insights Platform"
    assert response.project_match_confidence == "exact"
    assert response.project_answer_mode == "detailed_specific_project"


@pytest.mark.anyio
async def test_generate_specific_project_question_rejects_missing_project_without_inventing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            raise CloudResumeValidationError("That specific project was not found in the selected resume.")

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    with pytest.raises(generate_api.HTTPException) as exc_info:
        await generate_api.generate_answer(
            generate_api.GenerateRequest(
                question="Explain your Smart Product Scanning System",
                category="general",
                profile_context_used=True,
                selected_resume_id=SELECTED_RESUME_ID,
            ),
            request=object(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "That specific project was not found in the selected resume."


def test_selected_resume_prompt_includes_job_context_as_targeting_only() -> None:
    generator = AnswerGenerator()

    prompt = generator._build_prompt(
        "tell me about your projects",
        "hr",
        profile={
            "selected_resume_authoritative": True,
            "resume": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            "projects": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
        },
        retrieved_snippets=[
            {
                "section": "projects",
                "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
            }
        ],
        job_context={
            "saved": True,
            "target_role": "Generative AI Intern",
            "company_name": "Test Company",
            "job_description": "Looking for RAG, LangChain, FastAPI, vector database, and document processing.",
        },
        profile_context_enabled=True,
    )

    assert "Target role context: Generative AI Intern" in prompt
    assert "Target company context: Test Company" in prompt
    assert "Job description summary: Looking for RAG" in prompt
    assert "Do not treat job-description text as candidate experience" in prompt


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


@pytest.mark.anyio
async def test_selected_resume_strict_mode_skips_generic_personal_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCloudResumeService:
        def retrieve_resume_chunks(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "retrieval_used": True,
                "retrieved_chunks": [
                    {
                        "section": "projects",
                        "text": "AI Study Assistant using LangChain, Gemini API, RAG, Chroma, and FastAPI.",
                    }
                ],
                "retrieval_ms": 1.0,
            }

    monkeypatch.setattr(generate_api, "get_current_user", lambda _request: CurrentUser(user_id="user-a"))
    monkeypatch.setattr(generate_api, "_new_cloud_resume_service", lambda: FakeCloudResumeService())
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})

    def fake_generate_answer(**_kwargs: Any) -> dict[str, Any]:
        return _result(answer="AI Study Assistant project answer", answer_category="personal")

    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        generate_api.generator,
        "repair_personal_answer_if_needed",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("generic personal repair should not run")),
    )

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="tell me about your projects",
            category="personal",
            profile={"projects": "organizing my space"},
            profile_context_used=True,
            selected_resume_id=SELECTED_RESUME_ID,
        ),
        request=object(),
    )

    assert response.answer == "AI Study Assistant project answer"
    assert response.selected_resume_strict_mode is True
    assert response.generic_fallback_blocked is True
    assert response.profile_fallback_blocked is True
    assert response.final_context_priority == "selected_resume_only"


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
