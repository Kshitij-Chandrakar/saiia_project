from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.question_detect import extract_question_candidate
from app.nlp.answer_planner import build_answer_plan
from app.nlp.classifier import QuestionClassifier, looks_like_definition_question


@pytest.mark.parametrize(
    "transcript",
    [
        "what do you mean by authentication",
        "uh what do you mean by authentication",
        "what is meant by dependency injection",
        "what does polymorphism mean",
        "can you explain database normalization",
        "could you define encapsulation",
        "describe abstraction",
        "define inheritance",
    ],
)
def test_definition_phrases_are_valid_questions(transcript: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    is_question, reason, normalized = classifier.should_process_as_question(transcript)

    assert is_question is True
    assert "question phrase" in reason
    assert normalized


@pytest.mark.parametrize(
    "transcript",
    [
        "what do you mean",
        "what do you mean by",
        "what is meant by",
        "what does mean",
        "explain",
        "define",
        "describe",
        "tell me",
    ],
)
def test_incomplete_definition_prompts_are_rejected(transcript: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    is_question, _reason, _normalized = classifier.should_process_as_question(transcript)

    assert is_question is False


def test_followup_that_is_accepted_for_resolver() -> None:
    assert looks_like_definition_question("What do you mean by that?") is True


def test_question_detect_extracts_definition_candidate() -> None:
    extracted = extract_question_candidate("okay can you explain database normalization")

    assert extracted["candidate"].lower().startswith("can you explain database normalization")
    assert extracted["source"] == "interview_prompt"


def test_nontechnical_definition_question_is_not_forced_to_technical() -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    assert classifier.classify_question("What do you mean by teamwork?") != "technical"

    plan = build_answer_plan(
        question="What do you mean by teamwork?",
        category="general",
    )
    assert not plan.answer_type.startswith("technical")
