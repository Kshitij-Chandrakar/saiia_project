import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.followup_resolver import resolve_live_followup


def _ctx(question: str, *, mode: str = "answer", entry_id: str = "e1", answer: str = "", topic: str = "") -> dict:
    return {
        "entry_id": entry_id,
        "mode": mode,
        "original_question": question,
        "resolved_question": question,
        "answer_excerpt": answer,
        "topic": topic,
        "created_at": time.time(),
    }


def test_standalone_question_is_not_resolved() -> None:
    result = resolve_live_followup(
        question="What is supervised learning?",
        mode="answer",
        context_entries=[_ctx("Explain caching.")],
    )

    assert result.resolution_status == "standalone"
    assert result.resolved_question == "What is supervised learning?"
    assert result.follow_up_detected is False


def test_explicit_technical_implementation_question_is_standalone() -> None:
    for question in (
        "How is dependency injection implemented?",
        "How is dependency injection implemented in the backend?",
        "How is authentication implemented?",
        "How is authentication designed in the app?",
        "How is JWT validation implemented?",
        "How is JWT validation implemented in FastAPI?",
        "How is RAG built?",
        "How is vector search implemented?",
        "How does vector search work in your project?",
    ):
        result = resolve_live_followup(
            question=question,
            mode="answer",
            context_entries=[],
        )

        assert result.resolution_status == "standalone"
        assert result.resolved_question == question
        assert result.follow_up_detected is False


def test_active_and_past_tense_technical_subject_questions_are_standalone() -> None:
    for question in (
        "How did you build vector search?",
        "How do you implement dependency injection?",
        "How did you design authentication?",
        "How do you validate JWT?",
        "How did you use FAISS?",
    ):
        result = resolve_live_followup(
            question=question,
            mode="answer",
            context_entries=[],
        )

        assert result.resolution_status == "standalone"
        assert result.follow_up_detected is False


def test_pronoun_followup_uses_same_mode_context() -> None:
    result = resolve_live_followup(
        question="What are its examples?",
        mode="answer",
        context_entries=[_ctx("What is supervised learning?")],
    )

    assert result.resolution_status == "resolved"
    assert result.follow_up_detected is True
    assert "supervised learning" in result.resolved_question.lower()
    assert result.context_entry_ids == ["e1"]


def test_authentication_comparison_followup() -> None:
    result = resolve_live_followup(
        question="How is it different from authorization?",
        mode="answer",
        context_entries=[_ctx("Explain authentication.")],
    )

    assert result.resolution_status == "resolved"
    assert result.resolved_question.lower().startswith("how is authentication different from authorization")


def test_no_context_followup_requests_clarification() -> None:
    result = resolve_live_followup(
        question="Can you give another example?",
        mode="answer",
        context_entries=[],
    )

    assert result.resolution_status == "needs_clarification"
    assert result.clarification_question
    assert result.resolved_question == "Can you give another example?"


def test_explicit_project_subject_is_standalone() -> None:
    result = resolve_live_followup(
        question="What was your role in SAIIA?",
        mode="answer",
        context_entries=[],
    )

    assert result.resolution_status == "standalone"
    assert result.follow_up_detected is False


def test_different_mode_context_is_not_used() -> None:
    result = resolve_live_followup(
        question="What are its benefits?",
        mode="answer",
        context_entries=[_ctx("Explain caching.", mode="screen")],
    )

    assert result.resolution_status == "needs_clarification"
    assert result.context_entry_ids == []


def test_expired_context_is_not_used() -> None:
    old = _ctx("Explain caching.")
    old["created_at"] = time.time() - 7200

    result = resolve_live_followup(
        question="What are the disadvantages?",
        mode="answer",
        context_entries=[old],
        ttl_seconds=1800,
    )

    assert result.resolution_status == "needs_clarification"


def test_latest_chronological_entry_is_used_from_payload_order() -> None:
    result = resolve_live_followup(
        question="What are its disadvantages?",
        mode="answer",
        context_entries=[
            _ctx("Explain caching.", entry_id="latest"),
            _ctx("What is authentication?", entry_id="older"),
        ],
    )

    assert result.context_entry_ids == ["latest"]
    assert "caching" in result.resolved_question.lower()


def test_project_followup_resolves_to_project_context() -> None:
    result = resolve_live_followup(
        question="What was the biggest challenge?",
        mode="answer",
        context_entries=[_ctx("Tell me about your SAIIA project.")],
    )

    assert result.resolution_status == "resolved"
    assert "saiia" in result.resolved_question.lower()
    assert "challenge" in result.resolved_question.lower()


def test_project_build_followup_resolves_with_previous_project_context() -> None:
    result = resolve_live_followup(
        question="How did you build it?",
        mode="answer",
        context_entries=[_ctx("Explain your AI-Powered Medical Insights Platform.")],
    )

    assert result.resolution_status == "resolved"
    assert "ai-powered medical insights platform" in result.resolved_question.lower()


def test_previous_one_followup_does_not_misclassify_as_standalone() -> None:
    result = resolve_live_followup(
        question="How do you implement the previous one?",
        mode="answer",
        context_entries=[_ctx("Explain your AI-Powered Medical Insights Platform.")],
    )

    assert result.resolution_status == "resolved"
    assert result.follow_up_detected is True


def test_explicit_technical_subject_does_not_reuse_stale_project_context() -> None:
    question = "How does vector search work in your project?"
    result = resolve_live_followup(
        question=question,
        mode="answer",
        context_entries=[_ctx("Explain your AI-Powered Medical Insights Platform.")],
    )

    assert result.resolution_status == "standalone"
    assert result.resolved_question == question
    assert result.follow_up_detected is False


def test_coding_followup_preserves_previous_solution_topic() -> None:
    result = resolve_live_followup(
        question="Can you optimize it?",
        mode="answer",
        context_entries=[_ctx("Solve two sum.", topic="two sum")],
    )

    assert result.resolution_status == "resolved"
    assert "previous solution" in result.resolved_question.lower()
    assert "two sum" in result.resolved_question.lower()


def test_ambiguous_reference_requests_clarification() -> None:
    result = resolve_live_followup(
        question="How does it work?",
        mode="answer",
        context_entries=[
            _ctx(
                "Explain authentication and authorization.",
                answer="Authentication checks identity. Authorization checks permissions. Tokens may carry claims.",
            )
        ],
    )

    assert result.resolution_status == "needs_clarification"
    assert result.ambiguity_reason == "multiple_possible_antecedents"


def test_vague_pronoun_questions_remain_followups() -> None:
    for question in (
        "How does it work?",
        "How did you build it?",
        "How do you use this?",
        "Why is this used?",
    ):
        result = resolve_live_followup(
            question=question,
            mode="answer",
            context_entries=[],
        )

        assert result.follow_up_detected is True
