import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.followup_intent_compiler import compile_followup_intent
from app.nlp.followup_resolver import resolve_live_followup


def _ctx(question: str, *, topic: str = "", mode: str = "answer", entry_id: str = "e1", answer_type: str = "technical") -> dict:
    return {
        "entry_id": entry_id,
        "mode": mode,
        "original_question": question,
        "resolved_question": question,
        "answer_excerpt": "A short safe excerpt.",
        "answer_type": answer_type,
        "topic": topic,
        "created_at": time.time(),
    }


def _compile(question: str, context: list[dict]) -> object:
    resolution = resolve_live_followup(question=question, mode="answer", context_entries=context)
    return compile_followup_intent(
        question=question,
        mode="answer",
        context_entries=context,
        resolution=resolution,
        default_language="python",
    )


def test_array_program_followup_compiles_to_structured_demo_task() -> None:
    plan = _compile("Can you write a program of it?", [_ctx("What is an array?", topic="array")])

    assert plan.follow_up_detected is True
    assert plan.reference_status == "resolved"
    assert plan.reference_topic == "array"
    assert plan.requested_action == "implement_example"
    assert plan.requested_output == "structured_coding_answer"
    assert plan.programming_language == "python"
    assert plan.platform_mode == "standalone_demo"
    assert "in the context of array" not in plan.resolved_question.lower()
    assert "demonstrates array" in plan.resolved_question.lower()
    assert "no stdin input contract" in plan.resolved_question.lower()


def test_stack_followup_uses_concept_appropriate_demo() -> None:
    plan = _compile("Can you implement it?", [_ctx("What is a stack?", topic="stack")])

    assert plan.requested_action == "implement_example"
    assert "push" in plan.resolved_question.lower()
    assert "pop" in plan.resolved_question.lower()


def test_language_conversion_inherits_topic_and_uses_explicit_language() -> None:
    plan = _compile(
        "Now write it in Java.",
        [_ctx("Implement merge sort in Python.", topic="merge sort", answer_type="coding")],
    )

    assert plan.requested_action == "convert_language"
    assert plan.requested_output == "structured_coding_answer"
    assert plan.programming_language == "java"
    assert "merge sort" in plan.resolved_question.lower()
    assert "java" in plan.resolved_question.lower()


def test_complexity_followup_selects_complexity_contract() -> None:
    plan = _compile("What is its complexity?", [_ctx("Write binary search.", topic="binary search", answer_type="coding")])

    assert plan.requested_action == "calculate_complexity"
    assert plan.requested_output == "complexity_analysis"
    assert plan.platform_mode == "not_applicable"


def test_no_context_requests_clarification_without_guessing() -> None:
    resolution = resolve_live_followup(question="Can you implement it?", mode="answer", context_entries=[])
    plan = compile_followup_intent(
        question="Can you implement it?",
        mode="answer",
        context_entries=[],
        resolution=resolution,
        default_language="python",
    )

    assert plan.needs_clarification is True
    assert plan.requested_output == "clarification"
    assert plan.reference_status == "missing"
