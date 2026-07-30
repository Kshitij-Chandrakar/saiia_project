from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import generate as generate_api
from app.api.question_detect import QuestionDetectRequest, detect_question, extract_question_candidate
from app.nlp.answer_generator import AnswerGenerator
from app.nlp.answer_planner import build_answer_plan
from app.nlp.coding_quality_gate import detect_code_generation_mode, detect_programming_language
from app.nlp.classifier import QuestionClassifier


def test_coding_implementation_plan_requires_code() -> None:
    plan = build_answer_plan(question="Implement binary search in Python.", category="technical")

    assert plan.answer_type == "coding"
    assert plan.code_required is True
    assert plan.profile_context_policy == "FORBIDDEN"


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Implement binary search in Python.", "python"),
        ("Write this in JavaScript.", "javascript"),
        ("Create an LRU cache in C++.", "cpp"),
        ("Convert this solution to Java.", "java"),
        ("Rewrite it in c sharp.", "csharp"),
    ],
)
def test_requested_language_aliases_are_detected(question: str, language: str) -> None:
    assert detect_programming_language(question) == language


def test_code_generation_prompt_requires_structured_coding_answer() -> None:
    generator = AnswerGenerator(include_context=False)
    contract = {
        **detect_code_generation_mode("Implement binary search in JavaScript."),
        "language": "javascript",
        "mode": "stdin_full_solution",
        "code_generation_mode": "stdin_full_solution",
    }

    prompt = generator._build_code_generation_prompt(
        question="Implement binary search in JavaScript.",
        coding_contract=contract,
    )

    assert "Requested programming language: javascript." in prompt
    assert "### Approach" in prompt
    assert "### Code" in prompt
    assert "### Time Complexity" in prompt
    assert "### Space Complexity" in prompt
    assert "`javascript`" in prompt


@pytest.mark.parametrize(
    "transcript",
    [
        "write a program to print prime numbers in python",
        "implement binary search in python",
        "create a function to reverse a string in javascript",
        "complete the function in java",
        "solve this using c++",
    ],
)
def test_imperative_coding_requests_are_valid_questions(transcript: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    is_question, reason, normalized = classifier.should_process_as_question(transcript)

    assert is_question is True
    assert reason == "matches coding implementation request"
    assert normalized


def test_question_extraction_prefers_latest_coding_command_in_buffer() -> None:
    extracted = extract_question_candidate(
        "difference between an array and string write a program to print prime numbers in python"
    )

    assert extracted["candidate"].lower().startswith("write a program to print prime numbers")


@pytest.mark.asyncio
async def test_question_detect_accepts_prime_number_program_request() -> None:
    response = await detect_question(
        QuestionDetectRequest(
            transcript="write a program to print prime numbers in python",
            combined_transcript=None,
        )
    )

    assert response.is_question is True
    assert response.reason == "matches coding implementation request"
    assert response.normalized_question.lower().startswith("write a program to print prime numbers")


def test_structured_coding_answer_normalizes_malformed_markdown_source() -> None:
    generator = AnswerGenerator(include_context=False)
    raw = (
        "### Approach\nStore values in a list and iterate through them.\n\n"
        "### Code\n```python\n"
        "# Store several numbers in one list.\n"
        "numbers = [10, 20, 30]\n\n"
        "# Print each element by visiting it once.\n"
        "for number in numbers:\n"
        "    print(number)\n"
        "```\n\n"
        "### Time Complexity\nO(n)\n\n"
        "### Space Complexity\nO(n)"
    )

    structured = generator._build_structured_coding_answer(raw, {"language": "python"})
    assert structured is not None
    assert structured["language"] == "python"
    assert "numbers = [10, 20, 30]" in structured["code"]
    assert structured["time_complexity"] == "O(n)"
    assert structured["space_complexity"] == "O(n)"

    rendered = generator._format_structured_coding_answer(structured)
    assert "```python\n" in rendered
    assert "Real-life example" not in rendered


@pytest.mark.asyncio
async def test_generate_route_enables_coding_mode_for_manual_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_generate_answer(**kwargs):
        captured.update(kwargs)
        return {
            "answer": "### Approach\nUse binary search.\n\n### Code\n```python\n# Search sorted values.\ndef binary_search(values, target):\n    return -1\n```\n\n### Time Complexity\nO(log n)\n\n### Space Complexity\nO(1)",
            "provider": "openai",
            "model": "gpt-5.4-mini-2026-03-17",
            "fallback_used": False,
            "error": None,
            "generation_ms": 12.0,
            "answer_type": "coding",
            "plan_confidence": 0.88,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
            "validation_status": "passed",
            "validation_issues_count": 0,
            "correction_status": "skipped",
            "answer_verified": True,
        }

    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Implement binary search in Python.",
            category="technical",
            profile_context_used=True,
        )
    )

    assert captured["coding_answer_mode"] is True
    assert captured["screen_question_type"] == "coding"
    assert response.answer_type == "coding"
    assert response.profile_context_used is False


@pytest.mark.asyncio
async def test_generate_route_uses_compiled_followup_task_for_concept_to_code(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_generate_answer(**kwargs):
        captured.update(kwargs)
        return {
            "answer": "### Approach\nUse a list.\n\n### Code\n```python\n# Store values.\nnums = [1, 2, 3]\nfor n in nums:\n    print(n)\n```\n\n### Time Complexity\nO(n)\n\n### Space Complexity\nO(n)",
            "coding_answer": {
                "approach": "Use a list.",
                "language": "python",
                "code": "# Store values.\nnums = [1, 2, 3]\nfor n in nums:\n    print(n)",
                "time_complexity": "O(n)",
                "space_complexity": "O(n)",
            },
            "coding_validation_status": "structured",
            "provider": "openai",
            "model": "gpt-5.4-mini-2026-03-17",
            "fallback_used": False,
            "error": None,
            "generation_ms": 12.0,
            "answer_type": "coding",
            "plan_confidence": 0.88,
            "profile_context_policy": "FORBIDDEN",
            "job_context_policy": "FORBIDDEN",
            "general_knowledge_policy": "ALLOWED",
            "validation_status": "passed",
            "validation_issues_count": 0,
            "correction_status": "skipped",
            "answer_verified": True,
        }

    monkeypatch.setattr(generate_api.resume_index_service, "retrieve", lambda **_kwargs: {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0})
    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(generate_api.generator, "generate_answer", fake_generate_answer)

    response = await generate_api.generate_answer(
        generate_api.GenerateRequest(
            question="Can you write a program of it?",
            original_question="Can you write a program of it?",
            category="technical",
            followup_mode="answer",
            followup_context=[
                {
                    "entry_id": "a1",
                    "mode": "answer",
                    "original_question": "What is an array?",
                    "resolved_question": "What is an array?",
                    "topic": "array",
                    "created_at": 9999999999,
                }
            ],
            profile_context_used=True,
        )
    )

    assert "demonstrates array" in captured["question"].lower()
    assert "in the context of array" not in captured["question"].lower()
    assert captured["coding_answer_mode"] is True
    assert captured["screen_question_type"] == "coding"
    assert response.original_question == "Can you write a program of it?"
    assert response.reference_topic == "array"
    assert response.requested_action == "implement_example"
    assert response.requested_output == "structured_coding_answer"
    assert response.platform_mode == "standalone_demo"
    assert response.coding_answer and response.coding_answer["code"].startswith("# Store")
