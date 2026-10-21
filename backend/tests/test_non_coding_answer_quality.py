from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp import answer_generator as agmod
from app.nlp.answer_generator import AnswerGenerator


def _prompt(question: str, question_type: str, **kwargs) -> str:
    return AnswerGenerator(include_context=True)._build_prompt(
        question=question,
        question_type=question_type,
        profile={
            "technical_skills": "FastAPI, Python",
            "projects": "Built a FastAPI service with validated endpoints.",
        },
        retrieved_snippets=[
            {"section": "projects", "text": "Built a FastAPI service with validated endpoints."}
        ],
        **kwargs,
    )


def test_phase2_comparison_has_optional_examples_and_neutral_evidence_permissions() -> None:
    prompt = _prompt("Difference between machine learning, deep learning, and reinforcement learning.", "technical")
    assert "technical_comparison" in prompt and "140-230" in prompt
    assert "only when useful" in prompt and "profile=FORBIDDEN" in prompt
    assert "User profile:" not in prompt
    assert "Real-life example:" not in prompt


def test_phase2_technical_definition_uses_general_knowledge_without_resume() -> None:
    prompt = _prompt("What is REST API?", "technical")
    assert "general knowledge=ALLOWED" in prompt
    assert "neutral language" in prompt
    assert "User profile:" not in prompt


def test_phase2_dependency_injection_stays_conceptual() -> None:
    prompt = _prompt("How is dependency injection implemented?", "technical")
    assert "technical_process" in prompt
    assert "personal examples require evidence" in prompt
    assert "User profile:" not in prompt


def test_phase2_conceptual_questions_receive_flexible_depth_contract() -> None:
    for question in ("What is authentication?", "What is an API?", "What is cloud computing?", "Difference between authentication and authorization?"):
        prompt = _prompt(question, "technical")
        assert "ANSWER POLICY:" in prompt and "not a minimum or hard ceiling" in prompt
        assert "Never force an example" in prompt
        assert "display heading is mandatory" not in prompt


def test_demo_mode_does_not_shorten_normal_conceptual_answers() -> None:
    generator = AnswerGenerator(include_context=True)
    prompt = generator._build_prompt(
        question="What is authentication?",
        question_type="technical",
    )
    captured = {}
    original_mode = agmod.settings.PERFORMANCE_MODE

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return (
            "[[category:technical]]\nAuthentication verifies identity before access is granted.\n\n"
            "- It checks credentials.\n\n- It protects private data.\n\n- It blocks unknown users.\n\n"
            "Real-life example:\n\nA login endpoint verifies a password or OTP before issuing an access token."
        )

    try:
        agmod.settings.PERFORMANCE_MODE = "demo"
        generator.groq_provider.generate = fake_generate
        result = generator._generate_with_groq(
            prompt,
            fallback_used=False,
            primary_provider="groq",
        )
    finally:
        agmod.settings.PERFORMANCE_MODE = original_mode

    assert "Performance mode: DEMO" not in prompt
    assert captured["max_tokens"] == 520
    assert result["requested_completion_tokens"] == 520


def test_phase2_missing_experience_allows_hypothesis_not_unsupported_denial() -> None:
    prompt = _prompt("Have you used Kubernetes in production?", "technical")
    assert "explicitly hypothetical approach" in prompt
    assert "unsupported claim that I have never done it" in prompt
    assert "Kubernetes" not in prompt.split("Question:", 1)[0]


def test_phase2_resume_backed_question_preserves_supported_evidence() -> None:
    prompt = _prompt("How did you use FastAPI in your project?", "technical")
    assert "require supplied authorized evidence" in prompt
    assert "Built a FastAPI service with validated endpoints." in prompt


def test_project_question_with_named_technology_uses_resume_context() -> None:
    prompt = _prompt("Tell me about your FastAPI project.", "technical")

    assert "Relevant resume snippets:" in prompt
    assert "Built a FastAPI service with validated endpoints." in prompt


def test_phase2_behavioral_question_has_substance_without_forced_labels() -> None:
    prompt = _prompt("Tell me about a difficult bug you solved.", "behavioral")
    assert "150-230" in prompt
    assert "Never force an example, STAR labels" in prompt
    assert "Do not embellish" in prompt


def test_phase2_behavioral_without_evidence_requires_hypothetical_framing() -> None:
    prompt = AnswerGenerator()._build_prompt("Tell me about a conflict you resolved.", "behavioral")
    assert "Missing evidence permits an explicitly hypothetical approach" in prompt
    assert "never an invented past event" in prompt


def test_phase2_hr_introduction_stays_spoken_and_selective() -> None:
    prompt = _prompt("Tell me about yourself.", "hr")
    assert "100-170" in prompt
    assert "clear, natural spoken language" in prompt
    assert "Return only the answer" in prompt


def test_phase2_planner_resolves_intent_before_model_generation() -> None:
    generator = AnswerGenerator()
    messages = generator._answer_messages(generator._build_prompt("Describe a difficult technical problem you solved.", "technical"))
    assert "Resolved answer type: behavioral" in messages[1]["content"]
    assert "do not independently reclassify" in messages[0]["content"]
    assert "the model may correct it" not in messages[1]["content"]


def test_phase2_broad_personal_experience_does_not_invent_rapport() -> None:
    prompt = _prompt("What is the most interesting thing you have done in your life?", "hr")
    assert "personal_story" in prompt
    assert "explicitly hypothetical" in prompt
    assert "CREATIVE_PERSONAL" not in prompt
    assert "User profile:" not in prompt and "Relevant resume snippets:" not in prompt


def test_phase2_personal_hypothetical_does_not_force_a_story() -> None:
    prompt = _prompt("If you could spend a month anywhere, where would you go?", "general")
    assert "personal_story" in prompt and "explicitly hypothetical" in prompt
    assert "Use two or three short paragraphs" not in prompt
    assert "User profile:" not in prompt and "Relevant resume snippets:" not in prompt


def test_phase2_childhood_question_forbids_invented_memory() -> None:
    prompt = _prompt("Tell me something about your childhood days.", "hr")
    assert "personal_story" in prompt
    assert "never an invented past event" in prompt
    assert "one clear scene" not in prompt
    assert "User profile:" not in prompt


def test_phase2_preference_does_not_force_length_or_invent_context() -> None:
    prompt = _prompt("What is your favourite colour?", "general")
    assert "not a minimum or hard ceiling" in prompt
    assert "at least two complete sentences" not in prompt
    assert "require supplied authorized evidence" in prompt


def test_phase2_personal_context_follows_existing_forbidden_policy() -> None:
    prompt = AnswerGenerator()._build_prompt("What is your favourite book?", "personal", profile={"technical_skills": "FastAPI", "hobbies": "reading during quiet evenings"})
    assert "profile=FORBIDDEN" in prompt
    assert "FastAPI" not in prompt and "quiet evenings" not in prompt
    assert "HYBRID_PERSONAL" not in prompt


def test_phase2_personal_validator_does_not_pad_short_answers() -> None:
    generator = AnswerGenerator()
    answer = "In a hypothetical situation, I would listen before deciding what to do."
    repaired, errors, used = generator.repair_personal_answer_if_needed(question="Tell me something about your childhood days.", answer=answer)
    assert (repaired, errors, used) == (answer, [], False)


def test_phase2_professional_fit_keeps_candidate_evidence() -> None:
    prompt = _prompt("Why should we hire you?", "hr")
    assert "role_fit" in prompt and "90-160" in prompt
    assert "User profile:" in prompt and "Relevant resume snippets:" in prompt


def test_coding_prompt_and_cleanup_contract_are_unchanged() -> None:
    generator = AnswerGenerator(include_context=True)
    prompt = generator._build_prompt(
        question="Read an integer and print it.",
        question_type="technical",
        source="screen",
        question_context_type="coding",
        screen_question_type="coding",
        coding_answer_mode=True,
        profile_context_enabled=False,
        coding_input_contract={"code_generation_mode": "stdin_full_solution"},
    )
    answer = "Approach:\nRead and print the value.\n\nCode:\n```python\nprint(input())\n```\n\nComplexity:\nO(1)"

    assert "Approach:, Code:, Complexity:" in prompt
    assert "COMPACT CODING CONTRACT:" in prompt
    assert generator._clean_answer(answer) == answer


def test_model_category_marker_is_hidden_from_answer() -> None:
    generator = AnswerGenerator(include_context=True)
    raw_answer = "[[category:technical]]\nReinforcement learning trains an agent through rewards and feedback."

    assert generator._extract_answer_category(raw_answer) == "technical"
    assert generator._clean_answer(raw_answer) == "Reinforcement learning trains an agent through rewards and feedback."


def test_conceptual_answer_cleanup_preserves_bullets_and_spacing() -> None:
    generator = AnswerGenerator(include_context=True)
    raw_answer = (
        "[[category:technical]]\n"
        "Reinforcement learning teaches an agent through feedback.\n\n"
        "- Actions that earn rewards become more likely.\n\n"
        "- Actions that cause penalties become less likely.\n\n"
        "- The agent improves through repeated attempts.\n\n"
        "Real-life example:\n\n"
        "It is like learning a game by gaining points for good moves."
    )

    cleaned = generator._clean_answer(raw_answer)

    assert cleaned.startswith("Reinforcement learning teaches")
    assert "\n\n- Actions that earn rewards" in cleaned
    assert "\n\nReal-life example:\n\n" in cleaned


def test_conceptual_cleanup_expands_inline_bullets_without_truncating_example() -> None:
    generator = AnswerGenerator(include_context=True)
    raw_answer = (
        "[[category:technical]]\nAuthentication confirms a user's identity before allowing access. "
        "- It checks credentials such as passwords or fingerprints. "
        "- It helps protect accounts and private information. "
        "- It prevents unknown users from entering protected services. "
        "Real-life example: A login form checks a password or OTP before creating an access token for the session."
    )

    cleaned = generator._clean_answer(raw_answer)
    bullet_lines = [line for line in cleaned.splitlines() if line.startswith("- ")]

    assert len(bullet_lines) == 3
    assert all(f"\n\n{line}\n\n" in f"\n\n{cleaned}\n\n" for line in bullet_lines)
    assert "- It checks credentials" in cleaned
    assert "\n\nReal-life example:\n\n" in cleaned
    assert cleaned.endswith("for the session.")


def test_refinement_prompt_uses_same_domain_relevant_example_policy() -> None:
    generator = AnswerGenerator(include_context=True)
    prompt = generator._build_refinement_prompt(
        question="What is semantic HTML?",
        question_type="technical",
        profile=None,
        retrieved_snippets=None,
        job_context=None,
        groq_answer="Semantic HTML uses meaningful tags.",
    )

    assert "personal examples require evidence" in prompt
    assert "never force an example" in prompt.lower()
    assert "2 to 4 meaningful" not in prompt
    assert "100 to 160 words" not in prompt
    assert "semantic HTML" in prompt


def test_technical_example_validator_rejects_html_banking_example() -> None:
    generator = AnswerGenerator(include_context=True)
    issues = generator._validate_technical_real_life_example(
        question="What is semantic HTML?",
        answer=(
            "Semantic HTML uses meaningful elements.\n\n"
            "Real-life example:\n\nA banking app asks for a password before showing account details."
        ),
    )

    assert "html_example_defaulted_to_banking" in issues
    assert "real_life_example_domain_mismatch_html" in issues


def test_technical_example_validator_accepts_required_domains() -> None:
    generator = AnswerGenerator(include_context=True)
    cases = (
        (
            "What is HTML doctype?",
            "Real-life example:\n\nA browser reads the doctype before choosing standards mode instead of quirks mode for a webpage.",
        ),
        (
            "What is semantic HTML?",
            "Real-life example:\n\nA screen reader can use a nav element and headings to explain the webpage structure to a user.",
        ),
        (
            "What is rate limiting?",
            "Real-life example:\n\nAn API server can limit repeated requests from one client so traffic stays controlled.",
        ),
        (
            "What is normalization in databases?",
            "Real-life example:\n\nA customer table stores customer details once, while an order table references that record instead of duplicating names.",
        ),
        (
            "What is caching?",
            "Real-life example:\n\nA server can reuse a stored API response for repeated requests instead of recalculating the same result.",
        ),
        (
            "What is RAG?",
            "Real-life example:\n\nA support assistant retrieves relevant policy documents before drafting an answer for a user question.",
        ),
        (
            "What is authentication?",
            "Real-life example:\n\nA login endpoint checks a password or OTP before issuing an access token for the session.",
        ),
    )

    for question, answer in cases:
        assert generator._validate_technical_real_life_example(question=question, answer=answer) == []


def test_technical_example_validator_requires_non_empty_section() -> None:
    generator = AnswerGenerator(include_context=True)

    assert generator._validate_technical_real_life_example(
        question="What is REST API?",
        answer="REST APIs expose resources over HTTP.",
    ) == []  # Phase 2: examples are conditional; labeled empty examples still fail.
    assert generator._validate_technical_real_life_example(
        question="What is REST API?",
        answer="REST APIs expose resources over HTTP.\n\nReal-life example:\n\n",
    ) == ["empty_real_life_example"]


def test_bare_model_category_line_is_hidden_and_extracted() -> None:
    generator = AnswerGenerator(include_context=True)
    raw_answer = "technical\nReinforcement learning trains an agent through rewards and feedback."

    assert generator._extract_answer_category(raw_answer) == "technical"
    assert generator._clean_answer(raw_answer) == "Reinforcement learning trains an agent through rewards and feedback."


def test_category_label_line_is_hidden_and_extracted() -> None:
    generator = AnswerGenerator(include_context=True)
    raw_answer = "Category: technical\nReinforcement learning uses environmental feedback."

    assert generator._extract_answer_category(raw_answer) == "technical"
    assert generator._clean_answer(raw_answer) == "Reinforcement learning uses environmental feedback."


def test_normal_answer_beginning_with_category_word_is_not_stripped() -> None:
    generator = AnswerGenerator(include_context=True)
    answer = "Technical interviews often test both concepts and practical reasoning."

    assert generator._extract_answer_category(answer) is None
    assert generator._clean_answer(answer) == answer


def test_prompts_do_not_request_visible_category_markers() -> None:
    generator = AnswerGenerator(include_context=True)
    non_coding_prompt = generator._build_prompt(
        question="Explain the concept of reinforcement learning.",
        question_type="general",
    )
    coding_prompt = generator._build_prompt(
        question="Debug this code.",
        question_type="technical",
        source="screen",
        question_context_type="debugging",
        coding_answer_mode=True,
    )

    assert "[[category:" not in non_coding_prompt
    assert "without policy labels" in non_coding_prompt
    assert "[[category:" not in coding_prompt
