from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.classifier import QuestionClassifier, classify_personal_subtype, looks_like_definition_question


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the most interesting thing you have done in your life?", "personal"),
        ("What achievement are you most proud of?", "personal"),
        ("Tell me about a time you resolved a conflict.", "behavioral"),
        ("Describe a difficult technical problem you solved.", "behavioral"),
        ("How does a REST API work?", "technical"),
        ("How did you use FastAPI in your project?", "technical"),
        ("Why do you want to work here?", "hr"),
        ("Tell me something about your childhood days.", "personal"),
        ("Describe a difficult time in your life.", "personal"),
        ("What movie has influenced you the most?", "personal"),
        ("Which colour represents your personality?", "personal"),
        ("Tell me about something kind you did.", "personal"),
        ("What is a memory you will never forget?", "personal"),
        ("What do you enjoy outside your professional life?", "personal"),
        ("Who has influenced you as a person?", "personal"),
        ("What is something unusual about you?", "personal"),
        ("Describe your ideal weekend.", "personal"),
    ],
)
def test_question_category_precedence(question: str, expected: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    assert classifier.classify_question(question) == expected


def test_technical_context_cannot_change_a_personal_question_category() -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False
    question = "What is the most interesting thing you have done in your life?"

    assert classifier.classify_question(question) == "personal"


@pytest.mark.parametrize(
    "question",
    [
        "Which season do you prefer, summer or winter?",
        "Are you a morning person or a night person?",
        "What skill would you like to learn next?",
        "What is your ideal weekend?",
        "Where would you like to travel if time were unlimited?",
        "What's your favorite way to unwind?",
        "If you could live anywhere for a year, where would it be?",
        "What do you do for fun outside work?",
        "Which kind of food do you enjoy most?",
        "Who do you admire outside your family?",
        "Do you prefer sunny or rainy weather?",
        "Tell me about your hometown.",
        "What kind of music do you enjoy?",
        "Would you rather read a novel or watch a film?",
        "What do you enjoy doing on a quiet weekend?",
    ],
)
def test_novel_rapport_structures_are_personal(question: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    assert classifier.classify_question(question) == "personal"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why should we hire you?", "hr"),
        ("Tell me about a time you missed a deadline.", "behavioral"),
        ("What is database normalization?", "technical"),
        ("How did you use FastAPI in your project?", "technical"),
    ],
)
def test_professional_categories_are_unchanged(question: str, expected: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    assert classifier.classify_question(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is mitochondria.", "general"),
        ("What do you understand by mitochondria?", "general"),
        ("What do we understand by photosynthesis?", "general"),
        ("What is your understanding of gravity?", "general"),
        ("What do you know about the water cycle?", "general"),
        ("Give me an overview of cell division.", "general"),
        ("Briefly explain osmosis.", "general"),
        ("What is authentication?", "technical"),
        ("What do you understand by REST API?", "technical"),
        ("What is artificial intelligence?", "technical"),
    ],
)
def test_definition_questions_route_by_subject_domain(question: str, expected: str) -> None:
    classifier = QuestionClassifier()
    classifier.use_zero_shot = False

    assert looks_like_definition_question(question) is True
    assert classifier.classify_question(question) == expected


@pytest.mark.parametrize(
    ("question", "expected_subtype"),
    [
        ("Tell me something about your childhood days.", "childhood_memory"),
        ("Tell me about a difficult phase in your life.", "difficult_phase"),
        ("What is your favourite book?", "books_movies_music"),
        ("What is your favourite movie?", "books_movies_music"),
        ("What is your favourite colour?", "favourite_preferences"),
        ("Tell me about something amazing you have done.", "personal_achievement"),
        ("Who is your role model?", "role_model_influence"),
        ("What do you do in your free time?", "hobbies_interests"),
        ("Tell me about a time you helped someone.", "helping_someone"),
        ("Which fictional character are you most similar to?", "creative_imaginative"),
    ],
)
def test_personal_subtypes_are_detected(question: str, expected_subtype: str) -> None:
    assert classify_personal_subtype(question) == expected_subtype
