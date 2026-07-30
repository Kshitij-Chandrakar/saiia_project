from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import generate as generate_api
from app.nlp.answer_planner import build_answer_plan, validate_answer_against_plan


def test_pure_technical_plan_forbids_profile_and_job_context() -> None:
    plan = build_answer_plan(question="What are the benefits of RAG?", category="technical")

    assert plan.answer_type == "technical_concept"
    assert plan.profile_context_policy == "FORBIDDEN"
    assert plan.job_context_policy == "FORBIDDEN"


def test_resume_project_plan_requires_verified_profile_context() -> None:
    plan = build_answer_plan(question="What was your role in SAIIA?", category="technical")

    assert plan.answer_type == "resume_project"
    assert plan.profile_context_policy == "REQUIRED"


def test_role_fit_plan_uses_profile_and_job_context() -> None:
    plan = build_answer_plan(question="Why should we hire you?", category="hr")

    assert plan.answer_type == "role_fit"
    assert plan.profile_context_policy == "REQUIRED"
    assert plan.job_context_policy == "REQUIRED"


def test_validation_flags_misleading_rag_absolute_claim() -> None:
    plan = build_answer_plan(question="What are the benefits of RAG?", category="technical")
    result = validate_answer_against_plan(
        "RAG always guarantees current information and eliminates hallucinations.",
        plan,
        profile_context_used=False,
    )

    assert result["validation_status"] == "warning"
    assert "misleading_absolute_claim" in result["validation_issues"]


@pytest.mark.asyncio
async def test_generate_route_skips_resume_rag_for_pure_technical_question(monkeypatch: pytest.MonkeyPatch) -> None:
    retrieve_called = False
    job_called = False

    def fake_retrieve(**_kwargs):
        nonlocal retrieve_called
        retrieve_called = True
        return {"retrieval_used": True, "retrieved_chunks": [{"section": "projects", "text": "Private project"}], "retrieval_ms": 1.0}

    def fake_job_context():
        nonlocal job_called
        job_called = True
        return {"saved": True, "target_role": "Backend Engineer"}

    def fake_generate_answer(**_kwargs):
        return {
            "answer": "Authentication checks who a user is before access is granted.",
            "provider": "groq",
            "model": "test-model",
            "fallback_used": False,
            "error": None,
            "generation_ms": 12.0,
            "answer_type": "technical_concept",
            "plan_confidence": 0.86,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
            "validation_status": "passed",
            "validation_issues_count": 0,
            "correction_status": "skipped",
            "answer_verified": True,
        }

    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", fake_retrieve)
    monkeypatch.setattr(generate_api.job_context_service, "get_context", fake_job_context)
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="What is authentication?",
            category="technical",
            profile={"projects": "Private project"},
            profile_context_used=True,
        )
    )

    assert retrieve_called is False
    assert job_called is False
    assert response.profile_context_used is False
    assert response.answer_type == "technical_concept"
    assert response.validation_status == "passed"


@pytest.mark.asyncio
async def test_generate_route_preserves_profile_context_for_project_question(monkeypatch: pytest.MonkeyPatch) -> None:
    retrieve_called = False

    def fake_retrieve(**_kwargs):
        nonlocal retrieve_called
        retrieve_called = True
        return {"retrieval_used": True, "retrieved_chunks": [{"section": "projects", "text": "Built SAIIA"}], "retrieval_ms": 1.0}

    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", fake_retrieve)
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **_kwargs: {
            "answer": "I worked on SAIIA as an AI interview assistant project.",
            "provider": "groq",
            "model": "test-model",
            "fallback_used": False,
            "error": None,
            "generation_ms": 12.0,
            "answer_type": "resume_project",
            "plan_confidence": 0.86,
            "profile_context_policy": "REQUIRED",
            "job_context_policy": "ALLOWED",
            "general_knowledge_policy": "FORBIDDEN",
            "validation_status": "passed",
            "validation_issues_count": 0,
            "correction_status": "skipped",
            "answer_verified": True,
        },
    )

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="What was your role in SAIIA?",
            category="technical",
            profile={"projects": "Built SAIIA"},
            profile_context_used=True,
        )
    )

    assert retrieve_called is True
    assert response.profile_context_used is True
    assert response.retrieved_chunk_count == 1
    assert response.answer_type == "resume_project"
