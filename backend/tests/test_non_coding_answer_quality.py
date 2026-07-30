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


def test_general_technical_comparison_uses_spaced_bullets_and_daily_life_example() -> None:
    prompt = _prompt(
        "Difference between machine learning, deep learning, and reinforcement learning.",
        "technical",
    )

    assert "no first-person wording" in prompt
    assert "2 to 4 meaningful markdown bullets" in prompt
    assert "Real-life example:" in prompt
    assert "Real-life example policy" in prompt
    assert "blank line between" in prompt
    assert "Do not default to banking, shopping, phones, or messaging" in prompt
    assert "User profile:" not in prompt
    assert "Relevant resume snippets:" not in prompt


def test_general_technical_definition_uses_general_knowledge_without_resume() -> None:
    prompt = _prompt("What is REST API?", "technical")

    assert "Use accurate general technical knowledge" in prompt
    assert "no first-person wording" in prompt
    assert "User profile:" not in prompt


def test_required_conceptual_questions_receive_complete_format_contract() -> None:
    questions = (
        "What is authentication?",
        "What is an API?",
        "What is cloud computing?",
        "Difference between authentication and authorization?",
    )

    for question in questions:
        prompt = _prompt(question, "technical")
        assert "1 to 2 complete sentences" in prompt
        assert "2 to 4 meaningful markdown bullets" in prompt
        assert "one clear, speakable idea on its own line" in prompt
        assert "Real-life example:" in prompt
        assert "100 to 160 words" in prompt
        assert "Choose an example domain from the question itself" in prompt
        assert "banking, shopping, phones, or messaging" in prompt
        assert "Do not use markdown bullets" not in prompt


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


def test_unsupported_experience_question_requires_an_honest_bridge() -> None:
    prompt = _prompt("Have you used Kubernetes in production?", "technical")

    assert "Only unsupported professional facts require a brief honest gap and bridge" in prompt
    assert "Use first person only for claims directly supported" in prompt
    assert "Kubernetes" not in prompt.split("Question:", 1)[0]


def test_resume_backed_technical_question_allows_grounded_first_person() -> None:
    prompt = _prompt("How did you use FastAPI in your project?", "technical")

    assert "Use first person only for claims directly supported" in prompt
    assert "Built a FastAPI service with validated endpoints." in prompt


def test_project_question_with_named_technology_uses_resume_context() -> None:
    prompt = _prompt("Tell me about your FastAPI project.", "technical")

    assert "Relevant resume snippets:" in prompt
    assert "Built a FastAPI service with validated endpoints." in prompt


def test_behavioral_question_requires_one_grounded_natural_star_story() -> None:
    prompt = _prompt("Tell me about a difficult bug you solved.", "behavioral")

    assert "one supported example" in prompt
    assert "natural STAR-style story without writing STAR labels" in prompt
    assert "do not invent metrics" in prompt.lower()


def test_behavioral_question_without_evidence_requires_honest_bridge() -> None:
    prompt = AnswerGenerator(include_context=True)._build_prompt(
        question="Tell me about a conflict you resolved.",
        question_type="behavioral",
    )

    assert "If no suitable example is supported" in prompt
    assert "honestly" in prompt


def test_hr_introduction_stays_spoken_and_selective() -> None:
    prompt = _prompt("Tell me about yourself.", "hr")

    assert "Do not recite the full resume" in prompt
    assert "warm, conversational" in prompt
    assert "Return only the final answer" in prompt


def test_supplied_category_is_guidance_and_question_intent_wins() -> None:
    generator = AnswerGenerator(include_context=True)
    messages = generator._answer_messages(
        generator._build_prompt(
            question="Describe a difficult technical problem you solved.",
            question_type="technical",
        )
    )

    assert "guidance only" in messages[1]["content"]
    assert "Supplied interview category (guidance only): TECHNICAL" in messages[1]["content"]
    assert "Preliminary rule category (the model may correct it): BEHAVIORAL" in messages[1]["content"]
    assert "specific past situation" in messages[0]["content"]
    assert "stays behavioral when the example is technical" in messages[1]["content"]


def test_broad_personal_experience_uses_short_rapport_answer() -> None:
    prompt = _prompt("What is the most interesting thing you have done in your life?", "hr")

    assert "Preliminary rule category (the model may correct it): PERSONAL" in prompt
    assert "Personal subtype: personal_achievement" in prompt
    assert "Generation mode: CREATIVE_PERSONAL" in prompt
    assert "Target length: 110 to 170 words" in prompt
    assert "User profile:" not in prompt
    assert "Relevant resume snippets:" not in prompt


def test_personal_prompt_is_confident_spoken_and_has_no_resume_pitch() -> None:
    prompt = _prompt("If you could spend a month anywhere, where would you go?", "general")

    assert "Preliminary rule category (the model may correct it): PERSONAL" in prompt
    assert "Generation mode: CREATIVE_PERSONAL" in prompt
    assert "Do not use bullets, headings, STAR labels" in prompt
    assert "Do not mention projects, coding, education, technical skills" in prompt
    assert "Use two or three short paragraphs" in prompt
    assert "User profile:" not in prompt
    assert "Relevant resume snippets:" not in prompt


def test_childhood_question_gets_full_personal_narrative_contract() -> None:
    prompt = _prompt("Tell me something about your childhood days.", "hr")

    assert "Personal subtype: childhood_memory" in prompt
    assert "Target length: 110 to 170 words" in prompt
    assert "one clear scene" in prompt
    assert "Do not mention projects, coding, education, technical skills" in prompt
    assert "User profile:" not in prompt
    assert "Relevant resume snippets:" not in prompt


def test_favourite_colour_gets_more_than_one_sentence_contract() -> None:
    prompt = _prompt("What is your favourite colour?", "general")

    assert "Personal subtype: favourite_preferences" in prompt
    assert "Target length: 55 to 90 words" in prompt
    assert "at least two complete sentences" in prompt


def test_hybrid_personal_uses_safe_preference_context_only() -> None:
    prompt = AnswerGenerator(include_context=True)._build_prompt(
        question="What is your favourite book?",
        question_type="personal",
        profile={
            "technical_skills": "FastAPI, Python",
            "projects": "Built a FastAPI project.",
            "hobbies": "reading during quiet evenings",
        },
        retrieved_snippets=[{"section": "projects", "text": "Built a FastAPI project."}],
    )

    assert "Generation mode: HYBRID_PERSONAL" in prompt
    assert "hobbies: reading during quiet evenings" in prompt
    assert "FastAPI" not in prompt
    assert "Relevant resume snippets:" not in prompt


def test_personal_validator_repairs_one_sentence_generic_answer() -> None:
    generator = AnswerGenerator(include_context=True)
    repaired, errors, repaired_used = generator.repair_personal_answer_if_needed(
        question="Tell me something about your childhood days.",
        answer="I played soccer with friends and learned teamwork.",
    )

    assert repaired_used is True
    assert "below_minimum_words" in errors
    assert "one_sentence" in errors
    assert len(repaired.split()) >= 110
    assert "FastAPI" not in repaired


def test_professional_fit_question_keeps_candidate_context() -> None:
    prompt = _prompt("Why should we hire you?", "hr")

    assert "Preliminary rule category (the model may correct it): HR" in prompt
    assert "User profile:" in prompt
    assert "Relevant resume snippets:" in prompt


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

    assert "2 to 4 meaningful '- ' bullets" in prompt
    assert "exactly 4 meaningful" not in prompt
    assert "Choose an example domain from the question itself" in prompt
    assert "Do not default to banking, shopping, phones, or messaging" in prompt


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
    ) == ["missing_real_life_example"]
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
    assert "Do not include category, type, mode, or intent markers." in non_coding_prompt
    assert "[[category:" not in coding_prompt
