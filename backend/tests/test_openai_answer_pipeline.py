import pytest

from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.nlp.answer_planner import build_answer_plan


def test_openai_primary_uses_locked_snapshot_and_does_not_call_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)

    generator = AnswerGenerator()
    generator.openai_provider.model = "gpt-5.4-mini-2026-03-17"
    calls: list[dict[str, object]] = []

    def fake_openai_generate(**kwargs):
        calls.append(kwargs)
        return (
            "[[category:technical]]\n"
            "Authentication verifies who a user is before an application gives access.\n\n"
            "Real-life example:\n"
            "On a website login form, the server checks the submitted password or OTP before starting a user session."
        )

    def fail_groq(*args, **kwargs):
        raise AssertionError("Groq should not run after successful OpenAI generation")

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)
    monkeypatch.setattr(generator.groq_provider, "generate", fail_groq)
    monkeypatch.setattr(generator.groq_coding_provider, "generate", fail_groq)

    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5.4-mini-2026-03-17"
    assert result["primary_model"] == "gpt-5.4-mini-2026-03-17"
    assert result["reasoning_effort"] == "low"
    assert result["semantic_validation_used"] is False
    assert result["correction_status"] == "not_needed"
    assert result["refinement_used"] is False
    assert calls[0]["phase"] == "primary_generation"
    assert "gpt-5.4-mini" != result["model"]


def test_openai_generation_validation_and_correction_use_same_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_CONDITIONAL_CORRECTION", True)

    generator = AnswerGenerator()
    generator.openai_provider.model = "gpt-5.4-mini-2026-03-17"
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "primary_generation":
            return "Authentication checks identity."
        if kwargs["phase"] == "semantic_validation":
            return '{"valid": false, "severity": "medium", "issues": [{"type": "missing_example", "claim": "", "reason": "Missing Real-life example", "suggested_fix": "Add relevant example"}]}'
        if kwargs["phase"] == "semantic_correction":
            return (
                "Authentication checks identity before access is granted.\n\n"
                "Real-life example:\n"
                "When a user signs in with a password or OTP, the server verifies the credential before creating the session."
            )
        raise AssertionError(kwargs["phase"])

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "semantic_validation", "semantic_correction"]
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5.4-mini-2026-03-17"
    assert result["correction_status"] == "used"
    assert "Real-life example:" in result["answer"]


def test_openai_failure_uses_groq_fallback_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "ANSWER_FALLBACK_PROVIDER", "groq")
    monkeypatch.setattr(agmod.settings, "ENABLE_ANSWER_PROVIDER_FALLBACK", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", False)
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)

    generator = AnswerGenerator()

    def fail_openai(**kwargs):
        raise ProviderError("rate limited", provider="openai", model="gpt-5.4-mini-2026-03-17", status_code=429, error_type="rate_limit")

    monkeypatch.setattr(generator.openai_provider, "generate", fail_openai)
    monkeypatch.setattr(
        generator.groq_provider,
        "generate",
        lambda **kwargs: (
            "[[category:technical]]\n"
            "Authentication verifies identity.\n\n"
            "Real-life example:\n"
            "A login endpoint checks a password or OTP before returning a session token."
        ),
    )

    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert result["provider"] == "groq"
    assert result["primary_provider"] == "openai"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "rate_limit"


def test_reasoning_effort_routing_avoids_high_by_default() -> None:
    generator = AnswerGenerator()
    cases = [
        ("Tell me about yourself.", "hr", "low"),
        ("What is authentication?", "technical", "low"),
        ("Authentication vs authorization.", "technical", "medium"),
        ("Design a URL shortener.", "technical", "medium"),
    ]

    for question, category, expected in cases:
        plan = build_answer_plan(question=question, category=category)
        assert generator._openai_reasoning_effort(plan) == expected
        assert generator._openai_reasoning_effort(plan) not in {"high", "xhigh"}


def test_missing_openai_key_is_controlled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = AnswerGenerator()
    generator.openai_provider.api_key = ""
    generator.openai_provider.client = None

    with pytest.raises(ProviderError) as exc_info:
        generator.openai_provider.generate(
            instructions="x",
            input_text="x",
            reasoning_effort="low",
            max_output_tokens=10,
        )

    assert exc_info.value.error_type == "missing_api_key"
    assert exc_info.value.model == "gpt-5.4-mini-2026-03-17"


def test_shallow_technical_process_triggers_conditional_semantic_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_CONDITIONAL_CORRECTION", False)

    generator = AnswerGenerator()
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "primary_generation":
            return (
                "The main challenge is that retrieval can be hard to combine with generation.\n\n"
                "Real-life example:\n"
                "A support assistant may retrieve a document before writing an answer."
            )
        if kwargs["phase"] == "semantic_validation":
            return '{"valid": false, "severity": "medium", "issues": [{"type": "too_shallow", "claim": "", "reason": "Missing retrieval-quality and latency concerns", "suggested_fix": "Add core challenge dimensions"}]}'
        raise AssertionError(kwargs["phase"])

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    result = generator.generate_answer(
        "What are the challenges of combining retrieved information with LLM generation?",
        "technical",
        profile_context_enabled=False,
    )

    assert phases == ["primary_generation", "semantic_validation"]
    assert result["semantic_validation_used"] is True
    assert result["validation_issues_count"] >= 1


def test_false_superiority_comparison_triggers_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_CONDITIONAL_CORRECTION", False)

    generator = AnswerGenerator()
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "primary_generation":
            return (
                "GraphQL is always better and more advanced than REST.\n\n"
                "Real-life example:\n"
                "A client sends a query to a server endpoint and receives data."
            )
        if kwargs["phase"] == "semantic_validation":
            return '{"valid": false, "severity": "medium", "issues": [{"type": "false_superiority", "claim": "always better", "reason": "GraphQL is not universally better than REST", "suggested_fix": "Qualify trade-offs"}]}'
        raise AssertionError(kwargs["phase"])

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    result = generator.generate_answer("REST vs GraphQL.", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "semantic_validation"]
    assert result["semantic_validation_used"] is True
    assert result["validation_issues_count"] >= 1


def test_malformed_semantic_validator_output_preserves_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_CONDITIONAL_CORRECTION", True)

    generator = AnswerGenerator()
    primary = "Authentication verifies identity before access."
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "primary_generation":
            return primary
        if kwargs["phase"] == "semantic_validation":
            return "not json"
        raise AssertionError("correction should not run after malformed validation")

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "semantic_validation"]
    assert result["answer"] == primary
    assert result["semantic_validation_status"] == "failed"
    assert result["correction_status"] == "not_needed"


def test_failed_correction_revalidation_keeps_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.nlp.answer_generator as agmod

    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", "openai")
    monkeypatch.setattr(agmod.settings, "ENABLE_SEMANTIC_VALIDATION", True)
    monkeypatch.setattr(agmod.settings, "ENABLE_CONDITIONAL_CORRECTION", True)

    generator = AnswerGenerator()
    primary = "Authentication verifies identity before access."
    phases: list[str] = []

    def fake_openai_generate(**kwargs):
        phases.append(kwargs["phase"])
        if kwargs["phase"] == "primary_generation":
            return primary
        if kwargs["phase"] == "semantic_validation":
            return '{"valid": false, "severity": "medium", "issues": [{"type": "missing_example", "claim": "", "reason": "Missing required example", "suggested_fix": "Add example"}]}'
        if kwargs["phase"] == "semantic_correction":
            return "Authentication verifies identity."
        raise AssertionError(kwargs["phase"])

    monkeypatch.setattr(generator.openai_provider, "generate", fake_openai_generate)

    result = generator.generate_answer("What is authentication?", "technical", profile_context_enabled=False)

    assert phases == ["primary_generation", "semantic_validation", "semantic_correction"]
    assert result["answer"] == primary
    assert result["correction_status"] == "failed_validation"
