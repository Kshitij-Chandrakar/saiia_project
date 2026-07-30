from pathlib import Path
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "scipy.signal" not in sys.modules:
    scipy_stub = types.ModuleType("scipy")
    scipy_signal_stub = types.ModuleType("scipy.signal")
    scipy_signal_stub.resample_poly = lambda data, up, down: data
    scipy_stub.signal = scipy_signal_stub
    sys.modules["scipy"] = scipy_stub
    sys.modules["scipy.signal"] = scipy_signal_stub

from app.nlp import answer_generator as agmod
from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.api import generate as generate_api


READY_QUESTION = """
HackerRank
Task
Read an integer and print it.
Input Format
A single line containing an integer n.
Output Format
Print n.
Sample Input 0
5
Sample Output 0
5
"""


def _primary_result(answer: str) -> dict:
    return {
        "answer": answer,
        "provider": "groq",
        "primary_provider": "groq",
        "primary_model": "qwen/qwen3.6-27b",
        "model": "qwen/qwen3.6-27b",
        "groq_generation_ms": 10.0,
        "fallback_used": False,
        "fallback_enabled": True,
        "fallback_unavailable_reason": None,
        "error": None,
    }


def _non_coding_result(answer: str, category: str = "personal") -> dict:
    result = _primary_result(answer)
    result.update(
        {
            "answer_category": category,
            "generation_ms": 10.0,
            "generation_time_ms": 10.0,
            "prompt_build_ms": 1.0,
            "refinement_provider": "groq",
            "refinement_model": "llama-3.3-70b-versatile",
            "refinement_used": False,
            "refinement_status": "disabled",
            "primary_generation_ms": 9.0,
        }
    )
    return result


def test_first_generation_valid_skips_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)
    monkeypatch.setattr(
        AnswerGenerator,
        "_generate_with_primary_provider",
        lambda self, **kwargs: _primary_result("```python\nn = int(input())\nprint(n)\n```"),
    )
    monkeypatch.setattr(
        agmod,
        "validate_submission_code_against_contract",
        lambda code, contract: {
            "passed": True,
            "errors": [],
            "python_syntax_validation_used": True,
            "python_syntax_valid": True,
            "incomplete_code_detected": False,
            "incomplete_code_errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": True,
            "editor_stub_validation_errors": [],
            "required_stub_preserved": True,
        },
    )
    monkeypatch.setattr(
        agmod,
        "run_python_sample_tests",
        lambda code, tests, contract: {
            "ran": True,
            "passed": True,
            "errors": [],
            "actual_output": "5",
            "expected_output": "5",
            "function_test_harness_used": False,
            "function_test_harness_name": None,
            "class_test_harness_used": False,
            "class_test_harness_name": None,
            "skipped_reason": None,
        },
    )

    generator = AnswerGenerator(include_context=True)
    result = generator.generate_answer(
        question=READY_QUESTION,
        question_type="technical",
        source="screen",
        question_context_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_enabled=False,
    )

    assert result["correction_pass_needed"] is False
    assert result["correction_pass_used"] is False
    assert result["correction_skip_reason"] == "first_generation_valid"
    assert result["submission_ready_code"] is True


def test_context_not_ready_skips_correction_and_marks_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)
    monkeypatch.setattr(
        AnswerGenerator,
        "_generate_with_primary_provider",
        lambda self, **kwargs: _primary_result("```python\nprint(input())\n```"),
    )
    monkeypatch.setattr(
        agmod,
        "validate_submission_code_against_contract",
        lambda code, contract: {
            "passed": True,
            "errors": [],
            "python_syntax_validation_used": True,
            "python_syntax_valid": True,
            "incomplete_code_detected": False,
            "incomplete_code_errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": True,
            "editor_stub_validation_errors": [],
            "required_stub_preserved": True,
        },
    )

    generator = AnswerGenerator(include_context=True)
    result = generator.generate_answer(
        question="HackerRank solve this quickly",
        question_type="technical",
        source="screen",
        question_context_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_enabled=False,
    )

    assert result["hackerrank_context_ready"] is False
    assert result["correction_pass_needed"] is False
    assert result["correction_pass_used"] is False
    assert result["correction_skip_reason"] == "context_not_ready"
    assert result["submission_ready_code"] is False
    assert result["unverified_code_warning"] == "Full HackerRank problem context was not captured."


def test_correction_429_keeps_primary_code_and_returns_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)
    monkeypatch.setattr(
        AnswerGenerator,
        "_generate_with_primary_provider",
        lambda self, **kwargs: _primary_result("```python\nprint('bad')\n```"),
    )
    monkeypatch.setattr(
        agmod,
        "validate_submission_code_against_contract",
        lambda code, contract: {
            "passed": False,
            "errors": ["stdin parsing missing"],
            "python_syntax_validation_used": True,
            "python_syntax_valid": True,
            "incomplete_code_detected": False,
            "incomplete_code_errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": True,
            "editor_stub_validation_errors": [],
            "required_stub_preserved": True,
        },
    )
    monkeypatch.setattr(
        AnswerGenerator,
        "_correct_coding_answer_against_contract",
        lambda self, **kwargs: (_ for _ in ()).throw(
            ProviderError(
                "Groq coding could not generate an answer right now.",
                provider="Groq coding",
                model="qwen/qwen3.6-27b",
                status_code=429,
                error_type="rate_limit_exceeded",
                error_message="TPM exceeded",
                retry_after=14.0,
                phase="correction_pass",
            )
        ),
    )

    generator = AnswerGenerator(include_context=True)
    result = generator.generate_answer(
        question=READY_QUESTION,
        question_type="technical",
        source="screen",
        question_context_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_enabled=False,
    )

    assert result["answer"]
    assert result["submission_ready_code"] is False
    assert result["correction_pass_needed"] is True
    assert result["correction_pass_used"] is True
    assert result["correction_pass_failed"] is True
    assert result["correction_failure_reason"] == "rate_limit"
    assert "Generated code could not be fully verified" in result["unverified_code_warning"]


def test_ollama_unavailable_does_not_append_double_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(agmod.settings, "ENABLE_OLLAMA_FALLBACK", True)
    generator = AnswerGenerator(include_context=True)
    monkeypatch.setattr(
        generator,
        "_generate_with_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderError(
                "Groq coding could not generate an answer right now.",
                provider="Groq coding",
                model="qwen/qwen3.6-27b",
                status_code=429,
                error_type="rate_limit_exceeded",
                error_message="TPM exceeded",
                phase="primary_generation",
            )
        ),
    )
    monkeypatch.setattr(generator.ollama_provider, "availability_status", lambda: (False, "unreachable"))

    with pytest.raises(ProviderError) as exc_info:
        generator._generate_with_groq_then_optional_ollama("prompt", use_coding_primary_versatile=True)

    assert "Ollama fallback also failed" not in str(exc_info.value)
    assert "fallback_unavailable" not in caplog.text


def test_primary_qwen_generation_caps_completion_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "CODING_MAX_TOKENS", 1600)
    generator = AnswerGenerator(include_context=True)
    seen: dict[str, int] = {}

    def fake_generate(*, messages, temperature, max_tokens, phase="primary_generation", retry_on_rate_limit=False):
        seen["max_tokens"] = max_tokens
        seen["phase"] = phase
        return "```python\nprint(input())\n```"

    monkeypatch.setattr(generator.groq_coding_provider, "generate", fake_generate)
    result = generator._generate_with_groq(
        "prompt",
        fallback_used=False,
        primary_provider="groq",
        use_coding_primary_versatile=True,
    )

    assert seen["phase"] == "primary_generation"
    assert seen["max_tokens"] == 1600
    assert result["coding_max_tokens"] == 1600
    assert result["requested_completion_tokens"] == 1600


def test_compact_coding_contract_trims_raw_noise() -> None:
    generator = AnswerGenerator(include_context=True)
    noisy_question = (
        "HackerRank\nTask\nSolve the problem.\n"
        + '{ "is_question": true, "question_type": "coding", "question": "debug dump" }\n'
        + "Input Format\nA single integer n.\nOutput Format\nPrint n.\n"
        + ("Very long filler.\n" * 400)
    )
    contract = {
        "platform": "hackerrank",
        "problem_title": "Sample",
        "code_generation_mode": "stdin_full_solution",
        "input_format": "A single integer n.",
        "output_format": "Print n.",
        "sample_tests": [{"input": "5", "expected_output": "5"}],
    }

    compact = generator._build_compact_coding_context(question=noisy_question, coding_input_contract=contract)

    assert compact["compact_contract_used"] is True
    assert compact["raw_context_trimmed"] is True
    assert "question_type" not in compact["text"]
    assert len(compact["text"]) < len(noisy_question)


@pytest.mark.anyio
async def test_primary_429_returns_controlled_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    req = generate_api.GenerateRequest(
        question=READY_QUESTION,
        category="technical",
        source="screen",
        question_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_used=False,
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: (_ for _ in ()).throw(
            ProviderError(
                "Groq coding could not generate an answer right now.",
                provider="Groq coding",
                model="qwen/qwen3.6-27b",
                status_code=429,
                error_type="tokens",
                error_message="TPM exceeded",
                retry_after=35.0,
                phase="primary_generation",
            )
        ),
    )

    with pytest.raises(generate_api.HTTPException) as exc_info:
        await generate_api.generate_answer(req)

    assert exc_info.value.status_code == 429
    assert "retry after about 35 seconds" in str(exc_info.value.detail).lower()


def test_primary_429_skips_ollama_even_if_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "ENABLE_OLLAMA_FALLBACK", True)
    generator = AnswerGenerator(include_context=True)
    called = {"ollama_checked": False}

    monkeypatch.setattr(
        generator,
        "_generate_with_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderError(
                "Groq coding could not generate an answer right now.",
                provider="Groq coding",
                model="qwen/qwen3.6-27b",
                status_code=429,
                error_type="tokens",
                error_message="TPM exceeded",
                retry_after=35.0,
                phase="primary_generation",
            )
        ),
    )
    monkeypatch.setattr(
        generator.ollama_provider,
        "availability_status",
        lambda: called.__setitem__("ollama_checked", True) or (True, None),
    )

    with pytest.raises(ProviderError):
        generator._generate_with_groq_then_optional_ollama("prompt", use_coding_primary_versatile=True)

    assert called["ollama_checked"] is False


def test_primary_rate_limit_sets_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "CODING_MAX_TOKENS", 1600)
    generator = AnswerGenerator(include_context=True)
    key = generator._cooldown_key(generator.groq_coding_provider.name, generator.groq_coding_provider.model)
    agmod._PRIMARY_RATE_LIMIT_COOLDOWNS.pop(key, None)

    def fail_generate(*, messages, temperature, max_tokens, phase="primary_generation", retry_on_rate_limit=False):
        raise ProviderError(
            "Groq coding could not generate an answer right now.",
            provider="Groq coding",
            model="qwen/qwen3.6-27b",
            status_code=429,
            error_type="tokens",
            error_message="TPM exceeded",
            retry_after=35.0,
            phase="primary_generation",
        )

    monkeypatch.setattr(generator.groq_coding_provider, "generate", fail_generate)

    with pytest.raises(ProviderError):
        generator._generate_with_groq("prompt", fallback_used=False, primary_provider="groq", use_coding_primary_versatile=True)

    remaining = generator._get_active_cooldown_seconds(generator.groq_coding_provider.name, generator.groq_coding_provider.model)
    assert remaining is not None


def test_coding_primary_uses_qwen_and_explanation_uses_primary_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "REFINEMENT_ENABLED", False)
    monkeypatch.setattr(
        AnswerGenerator,
        "_generate_with_primary_provider",
        lambda self, **kwargs: _primary_result("```python\nn = int(input())\nprint(n)\n```"),
    )
    monkeypatch.setattr(
        agmod,
        "validate_submission_code_against_contract",
        lambda code, contract: {
            "passed": True,
            "errors": [],
            "python_syntax_validation_used": True,
            "python_syntax_valid": True,
            "incomplete_code_detected": False,
            "incomplete_code_errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": True,
            "editor_stub_validation_errors": [],
            "required_stub_preserved": True,
        },
    )
    monkeypatch.setattr(
        agmod,
        "run_python_sample_tests",
        lambda code, tests, contract: {
            "ran": True,
            "passed": True,
            "errors": [],
            "actual_output": "5",
            "expected_output": "5",
            "function_test_harness_used": False,
            "function_test_harness_name": None,
            "class_test_harness_used": False,
            "class_test_harness_name": None,
            "skipped_reason": None,
        },
    )
    monkeypatch.setattr(
        AnswerGenerator,
        "_format_coding_answer_with_explanation_model",
        lambda self, **kwargs: {
            "answer": "Approach:\nRead and print.\n\nCode:\n```python\nn = int(input())\nprint(n)\n```\n\nComplexity:\nO(1)",
            "model": "openai/gpt-oss-20b",
            "prompt_len": 123,
        },
    )

    generator = AnswerGenerator(include_context=True)
    result = generator.generate_answer(
        question=READY_QUESTION,
        question_type="technical",
        source="screen",
        question_context_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_enabled=False,
    )

    assert result["primary_model"] == "qwen/qwen3.6-27b"
    assert result["model"] == "openai/gpt-oss-20b"
    assert "### Approach" in result["answer"]
    assert "### Code" in result["answer"]
    assert "### Time Complexity" in result["answer"]
    assert "### Space Complexity" in result["answer"]
    assert result["coding_answer"]["code"].strip() == "n = int(input())\nprint(n)"


def test_coding_generation_prompt_requests_structured_code_answer() -> None:
    generator = AnswerGenerator(include_context=True)
    prompt = generator._build_code_generation_prompt(
        question=READY_QUESTION,
        coding_contract={
            "platform": "hackerrank",
            "problem_title": "Sample",
            "code_generation_mode": "stdin_full_solution",
            "input_format": "A single line containing an integer n.",
            "output_format": "Print n.",
            "sample_tests": [{"input": "5", "expected_output": "5"}],
        },
    )

    assert "Requested programming language: python." in prompt
    assert "### Approach" in prompt
    assert "### Code" in prompt
    assert "### Time Complexity" in prompt
    assert "### Space Complexity" in prompt
    assert "Do not include <think> or reasoning text." in prompt
    assert "Return only one final Python code block." not in prompt


def test_correction_prompt_is_compact_and_token_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agmod.settings, "CODING_MAX_TOKENS", 1600)
    generator = AnswerGenerator(include_context=True)
    captured: dict[str, object] = {}

    def fake_generate(*, messages, temperature, max_tokens, phase="correction_pass", retry_on_rate_limit=False):
        captured["prompt"] = messages[-1]["content"]
        captured["max_tokens"] = max_tokens
        captured["phase"] = phase
        return "```python\nprint(input())\n```"

    monkeypatch.setattr(generator.groq_coding_provider, "generate", fake_generate)

    result = generator._correct_coding_answer_against_contract(
        question=READY_QUESTION + ("\nVery long filler." * 400),
        answer="```python\nprint('bad')\n```",
        contract={
            "platform": "hackerrank",
            "mode": "stdin_full_solution",
            "code_generation_mode": "editor_stub_completion",
            "input_format": "A single line containing an integer n.",
            "output_format": "Print n.",
            "editor_stub_used": True,
            "editor_stub_mode": "generic_stdin",
            "editor_required_symbols": ["solve"],
            "editor_required_functions": ["solve"],
            "editor_required_classes": [],
            "editor_runner_detected": True,
            "editor_stub": "def solve():\n    pass\n" + ("# filler\n" * 200),
            "sample_tests": [{"input": "5", "expected_output": "5"}],
        },
        validation_errors=["stdin parsing missing", "sample output mismatch", "another error"],
        sample_test_result={"sample_input": "5", "expected_output": "5", "actual_output": "bad"},
    )

    assert captured["phase"] == "correction_pass"
    assert captured["max_tokens"] == 400
    assert "Problem excerpt:" not in str(captured["prompt"])
    assert "Compact coding context:" in str(captured["prompt"])
    assert result["prompt_len"] < 2600


@pytest.mark.anyio
async def test_personal_generate_route_skips_resume_rag_and_repairs_short_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = generate_api.GenerateRequest(
        question="Tell me something about your childhood days.",
        category="hr",
        profile={
            "technical_skills": "FastAPI, Python",
            "projects": "Built a FastAPI project.",
        },
    )
    retrieval_called = {"value": False}

    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(
        generate_api.resume_index_service,
        "retrieve",
        lambda **kwargs: retrieval_called.__setitem__("value", True)
        or {"retrieval_used": True, "retrieved_chunks": [{"section": "projects", "text": "FastAPI"}], "retrieval_ms": 1.0},
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: _non_coding_result("I played outside with friends and learned teamwork.", "personal"),
    )

    response = await generate_api.generate_answer(req)

    assert retrieval_called["value"] is False
    assert response.generate_category == "personal"
    assert response.answer_mode == "CREATIVE_PERSONAL"
    assert response.personal_subtype == "childhood_memory"
    assert response.creative_generation_used is True
    assert response.personal_answer_repaired is True
    assert response.retrieval_used is False
    assert "FastAPI" not in response.answer
    assert len(response.answer.split()) >= 110


@pytest.mark.anyio
async def test_professional_generate_route_still_uses_resume_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = generate_api.GenerateRequest(
        question="Tell me about your FastAPI project.",
        category="technical",
        profile={"technical_skills": "FastAPI, Python"},
    )
    retrieval_called = {"value": False}

    monkeypatch.setattr(generate_api.job_context_service, "get_context", lambda: {"saved": False})
    monkeypatch.setattr(
        generate_api.resume_index_service,
        "retrieve",
        lambda **kwargs: retrieval_called.__setitem__("value", True)
        or {"retrieval_used": True, "retrieved_chunks": [{"section": "projects", "text": "FastAPI"}], "retrieval_ms": 1.0},
    )
    monkeypatch.setattr(
        generate_api.generator,
        "generate_answer",
        lambda **kwargs: _non_coding_result("I used FastAPI to build validated backend endpoints.", "technical"),
    )

    response = await generate_api.generate_answer(req)

    assert retrieval_called["value"] is True
    assert response.generate_category == "technical"
    assert response.retrieval_used is True
    assert response.retrieved_chunk_count == 1
    assert response.answer_mode == "GROUNDED_PROFESSIONAL"
