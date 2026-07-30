import time

import pytest

from app.api import generate as generate_api
from app.nlp import answer_generator as agmod
from app.nlp.answer_generator import AnswerGenerator
from app.nlp.answer_planner import build_answer_plan
from app.nlp.answer_variation import (
    AnswerVariationHistory,
    build_variation_plan,
    context_fingerprint,
    normalize_question_for_repetition,
    questions_equivalent,
    similarity_score,
)


def _compact(text: str) -> str:
    return " ".join(str(text or "").split())


VALID_AUTH_ANSWER = (
    "Authentication verifies a user's identity before access is granted. "
    "A login flow checks a credential such as a password or OTP and then creates a session.\n\n"
    "- It answers who the user is.\n\n"
    "- It happens before authorization decisions.\n\n"
    "Real-life example:\n"
    "A website login form checks the submitted password or OTP before starting the user's session."
)


VARIED_AUTH_ANSWER = (
    "Authentication is the identity-check step that happens before an app treats someone as signed in. "
    "The system verifies a login credential, such as a password or OTP, and only then creates the session.\n\n"
    "- It confirms who is making the request.\n\n"
    "- It is separate from deciding what that user can access.\n\n"
    "Real-life example:\n"
    "When a user opens a dashboard, the login endpoint verifies the credential before issuing a session token."
)


@pytest.fixture(autouse=True)
def clear_variation_history(monkeypatch: pytest.MonkeyPatch):
    agmod._ANSWER_VARIATION_HISTORY.clear()
    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")
    monkeypatch.setattr(agmod.settings, "ENABLE_CONTROLLED_ANSWER_VARIATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_VARIATION_REWRITE", True)
    monkeypatch.setattr(agmod.settings, "VARIATION_HISTORY_LIMIT", 3)
    monkeypatch.setattr(agmod.settings, "VARIATION_CACHE_TTL_SECONDS", 7200)
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", False)
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)


def test_repetition_normalization_handles_case_punctuation_and_explain_prefix() -> None:
    assert normalize_question_for_repetition(" What is authentication??? ") == "authentication"
    assert normalize_question_for_repetition("Explain authentication.") == "authentication"
    assert questions_equivalent(
        normalize_question_for_repetition("Can you explain authentication?"),
        normalize_question_for_repetition("what is authentication"),
    )
    assert not questions_equivalent(
        normalize_question_for_repetition("What is authentication?"),
        normalize_question_for_repetition("What is authorization?"),
    )


def test_context_fingerprint_changes_when_resume_or_job_context_changes() -> None:
    first = context_fingerprint(
        profile={"projects": "SAIIA with FastAPI"},
        retrieved_snippets=[{"section": "projects", "text": "FastAPI"}],
        job_context={"target_role": "Backend Engineer"},
        profile_context_enabled=True,
    )
    changed_resume = context_fingerprint(
        profile={"projects": "Portfolio with React"},
        retrieved_snippets=[{"section": "projects", "text": "React"}],
        job_context={"target_role": "Backend Engineer"},
        profile_context_enabled=True,
    )
    changed_job = context_fingerprint(
        profile={"projects": "SAIIA with FastAPI"},
        retrieved_snippets=[{"section": "projects", "text": "FastAPI"}],
        job_context={"target_role": "Frontend Engineer"},
        profile_context_enabled=True,
    )

    assert first != changed_resume
    assert first != changed_job


def test_history_limit_and_ttl_are_enforced() -> None:
    history = AnswerVariationHistory()
    plan = build_answer_plan(question="What is authentication?", category="technical")
    normalized = normalize_question_for_repetition("What is authentication?")
    fingerprint = "ctx"

    history.add(answer_type=plan.answer_type, normalized_question=normalized, context_fingerprint=fingerprint, answer="one", ttl_seconds=7200, history_limit=2)
    history.add(answer_type=plan.answer_type, normalized_question=normalized, context_fingerprint=fingerprint, answer="two", ttl_seconds=7200, history_limit=2)
    history.add(answer_type=plan.answer_type, normalized_question=normalized, context_fingerprint=fingerprint, answer="three", ttl_seconds=7200, history_limit=2)

    current = history.find(answer_type=plan.answer_type, normalized_question=normalized, context_fingerprint=fingerprint, ttl_seconds=7200)
    assert [entry.answer for entry in current] == ["two", "three"]

    for entry in current:
        entry.created_at = time.time() - 10
    assert history.find(answer_type=plan.answer_type, normalized_question=normalized, context_fingerprint=fingerprint, ttl_seconds=1) == []


def test_variation_plan_uses_answer_type_and_context_scope() -> None:
    history = AnswerVariationHistory()
    technical_plan = build_answer_plan(question="What is authentication?", category="technical")
    normalized = normalize_question_for_repetition("What is authentication?")
    fingerprint = context_fingerprint(profile=None, retrieved_snippets=None, job_context=None, profile_context_enabled=False)
    history.add(
        answer_type=technical_plan.answer_type,
        normalized_question=normalized,
        context_fingerprint=fingerprint,
        answer=VALID_AUTH_ANSWER,
        ttl_seconds=7200,
        history_limit=3,
    )

    repeated = build_variation_plan(
        answer_plan=technical_plan,
        question="Explain authentication.",
        profile=None,
        retrieved_snippets=None,
        job_context=None,
        profile_context_enabled=False,
        history=history,
        enabled=True,
        rewrite_enabled=True,
        ttl_seconds=7200,
        history_limit=3,
    )
    different_type = build_variation_plan(
        answer_plan=build_answer_plan(question="Tell me about yourself.", category="hr"),
        question="Explain authentication.",
        profile=None,
        retrieved_snippets=None,
        job_context=None,
        profile_context_enabled=False,
        history=history,
        enabled=True,
        rewrite_enabled=True,
        ttl_seconds=7200,
        history_limit=3,
    )

    assert repeated.repetition_detected is True
    assert repeated.repetition_count == 2
    assert repeated.variation_profile
    assert different_type.repetition_detected is False


def test_repeated_question_adds_variation_instruction_to_primary_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = AnswerGenerator()
    prompts: list[str] = []

    def fake_openai_generate(**kwargs):
        prompts.append(kwargs["input_text"])
        return VALID_AUTH_ANSWER if len(prompts) == 1 else VARIED_AUTH_ANSWER

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    first = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)
    second = generator.generate_answer("Explain authentication.", "technical", profile_context_enabled=False)

    assert first["repetition_detected"] is False
    assert second["repetition_detected"] is True
    assert second["repetition_count"] == 2
    assert "Controlled variation for repeated question" not in prompts[0]
    assert "Controlled variation for repeated question" in prompts[1]
    assert _compact(second["answer"]) == _compact(VARIED_AUTH_ANSWER)


def test_exact_duplicate_triggers_one_openai_variation_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = AnswerGenerator()
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "variation_rewrite":
            return VARIED_AUTH_ANSWER
        return VALID_AUTH_ANSWER

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)
    result = generator.generate_answer("what is authentication", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "primary_generation", "variation_rewrite"]
    assert result["variation_rewrite_used"] is True
    assert result["variation_status"] == "rewrite_accepted"
    assert _compact(result["answer"]) == _compact(VARIED_AUTH_ANSWER)
    assert result["similarity_score"] < 1.0


def test_sufficiently_different_repeated_answer_skips_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = AnswerGenerator()
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        return VALID_AUTH_ANSWER if len(phases) == 1 else VARIED_AUTH_ANSWER

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)
    result = generator.generate_answer("Can you explain authentication?", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "primary_generation"]
    assert result["variation_rewrite_used"] is False
    assert result["variation_status"] == "accepted"


def test_rewrite_failure_preserves_valid_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = AnswerGenerator()
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "variation_rewrite":
            return "Authentication is useful."
        return VALID_AUTH_ANSWER

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)
    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "primary_generation", "variation_rewrite"]
    assert _compact(result["answer"]) == _compact(VALID_AUTH_ANSWER)
    assert result["variation_rewrite_used"] is False
    assert result["variation_status"] == "failed_validation"


def test_controlled_variation_disabled_restores_problem1_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "ENABLE_CONTROLLED_ANSWER_VARIATION", False)
    generator = AnswerGenerator()
    calls: list[str] = []

    def fake_openai_generate(**kwargs):
        calls.append(kwargs["phase"])
        return VALID_AUTH_ANSWER

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    first = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)
    second = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert calls == ["primary_generation", "primary_generation"]
    assert first["variation_status"] == "disabled"
    assert second["variation_status"] == "disabled"
    assert second["repetition_detected"] is False


def test_similarity_excludes_identical_correct_code() -> None:
    previous = (
        "Approach:\nRead n and print it.\n\n"
        "Code:\n```python\nn = int(input())\nprint(n)\n```\n\n"
        "Complexity:\nO(1)"
    )
    current = (
        "Approach:\nThe solution reads the integer and outputs it directly.\n\n"
        "Code:\n```python\nn = int(input())\nprint(n)\n```\n\n"
        "Complexity:\nConstant time and space."
    )

    assert similarity_score(current, (previous,), answer_type="coding") < 0.97


@pytest.mark.asyncio
async def test_generate_route_returns_safe_variation_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **_kwargs: {
            "answer": VALID_AUTH_ANSWER,
            "provider": "openai",
            "model": "gpt-5.4-mini-2026-03-17",
            "fallback_used": False,
            "error": None,
            "generation_ms": 10.0,
            "answer_type": "technical_concept",
            "plan_confidence": 0.86,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
            "validation_status": "passed",
            "validation_issues_count": 0,
            "correction_status": "not_needed",
            "answer_verified": True,
            "repetition_detected": True,
            "repetition_count": 2,
            "variation_enabled": True,
            "variation_profile": "alternative_opening",
            "variation_applied": True,
            "variation_rewrite_used": False,
            "variation_status": "accepted",
            "similarity_score": 0.42,
            "previous_answer_count": 1,
            "variation_ms": 0.3,
        },
    )

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="What is authentication?",
            category="technical",
            profile_context_used=False,
        )
    )

    assert response.repetition_detected is True
    assert response.repetition_count == 2
    assert response.variation_status == "accepted"
    assert response.previous_answer_count == 1
