import json

import pytest

from app.nlp.answer_generator import ProviderError
from app.services import resume_gpt_parser_service as gpt_module
from app.services.resume_gpt_parser_service import ResumeGptParserService
from app.services.resume_parser_service import ResumeParserService

SANITIZED_ANAND_RESUME = """
ANAND VISHWAKARMA
LinkedIn | +91 7011472391 | anandvishwakarma21j@example.com | GitHub | Leetcode

Skills
Python, Machine Learning, Deep Learning, TensorFlow, PyTorch, FastAPI, OpenCV, Streamlit

Experience
AI Engineering Intern - Built computer vision and LLM workflow prototypes for internal automation.
Machine Learning Intern - Improved model evaluation scripts and dataset preparation pipelines.

Projects
Interview Assistant - Built a resume-grounded assistant using FastAPI and retrieval.
Vision Resume Analyzer - Extracted structured candidate details from documents.

Achievements
Finalist in campus innovation challenge.
Solved 400+ coding problems on practice platforms.

Education
B.Tech CSE, O.P. Jindal University, 2026
""".strip()


class FakeOpenAIResponse:
    def __init__(self, payload: object) -> None:
        self.output_text = payload if isinstance(payload, str) else json.dumps(payload)


class FakeResponses:
    def __init__(self, payload: object = None, exc: Exception | None = None) -> None:
        self.payload = payload or {}
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return FakeOpenAIResponse(self.payload)


class FakeOpenAIClient:
    def __init__(self, payload: object = None, exc: Exception | None = None) -> None:
        self.responses = FakeResponses(payload, exc)


def _enable_gpt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpt_module.settings, "RESUME_GPT_PARSER_ENABLED", True)
    monkeypatch.setattr(gpt_module.settings, "OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setattr(gpt_module.settings, "RESUME_GPT_MODEL", "gpt-5-mini")
    monkeypatch.setattr(gpt_module.settings, "RESUME_GPT_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(gpt_module.settings, "RESUME_GPT_MAX_INPUT_CHARS", 30000)


def test_gpt_parser_extracts_sanitized_anand_resume_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "ANAND VISHWAKARMA",
        "email": "anandvishwakarma21j@example.com",
        "phone": "+91 7011472391",
        "location": "",
        "current_title": "AI Engineering Intern",
        "target_role": "AI Engineer",
        "professional_summary": (
            "AI engineering candidate with internship experience building computer vision, "
            "machine learning, and FastAPI-based assistant projects."
        ),
        "education": "B.Tech CSE, O.P. Jindal University, 2026",
        "degree": "B.Tech",
        "branch": "Computer Science and Engineering",
        "college": "O.P. Jindal University",
        "college_university": "O.P. Jindal University",
        "university": "O.P. Jindal University",
        "graduation_year": "2026",
        "top_skills": "Python, Machine Learning, Deep Learning, FastAPI, OpenCV, Streamlit",
        "technical_skills": "Python, TensorFlow, PyTorch, FastAPI, OpenCV",
        "soft_skills": "",
        "tools_frameworks": "FastAPI, Streamlit, TensorFlow, PyTorch",
        "projects": "Interview Assistant\nVision Resume Analyzer",
        "experience": "AI Engineering Intern\nMachine Learning Intern",
        "work_experience": "AI Engineering Intern\nMachine Learning Intern",
        "certifications": "",
        "achievements": "Finalist in campus innovation challenge\nSolved 400+ coding problems",
        "extraction_confidence": "high",
        "missing_fields": ["location", "certifications"],
        "manual_review_required": True,
        "manual_review_message": "Location and certifications were not clearly present.",
    }
    client = FakeOpenAIClient(payload)
    parser = ResumeGptParserService(openai_client=client)

    profile = parser.extract_profile(SANITIZED_ANAND_RESUME)

    assert profile["full_name"] == "Anand Vishwakarma"
    assert profile["email"] == "anandvishwakarma21j@example.com"
    assert profile["phone"] == "+91 7011472391"
    assert "Python" in profile["top_skills"]
    assert "AI Engineering Intern" in profile["experience"]
    assert "Interview Assistant" in profile["projects"]
    assert "O.P. Jindal University" in profile["education"]
    assert "campus innovation challenge" in profile["achievements"]
    assert "anandvishwakarma21j@example.com" not in profile["professional_summary"]
    assert "+91 7011472391" not in profile["professional_summary"]
    assert profile["certifications"] == ""
    assert profile["manual_review_required"] is True
    assert profile["raw_resume_text"] == SANITIZED_ANAND_RESUME
    assert client.responses.calls[0]["model"] == "gpt-5-mini"
    assert client.responses.calls[0]["timeout"] == 20


def test_gpt_parser_keeps_target_role_empty_without_explicit_resume_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "test@example.com",
        "phone": "+91 9999999999",
        "location": "",
        "current_title": "AI Engineering Intern",
        "target_role": "",
        "professional_summary": "AI engineering intern with machine learning project experience.",
        "education": "B.Tech CSE",
        "degree": "B.Tech",
        "branch": "CSE",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Python,FastAPI",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "Resume Assistant",
        "experience": "AI Engineering Intern",
        "work_experience": "AI Engineering Intern",
        "certifications": "",
        "achievements": "",
        "extraction_confidence": "high",
        "missing_fields": [],
        "manual_review_required": False,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile(SANITIZED_ANAND_RESUME)

    assert profile["current_title"] == "AI Engineering Intern"
    assert profile["target_role"] == ""


def test_gpt_parser_cleans_spaced_hyphen_compounds(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Built multi - agent and model - based AI - Powered systems.",
        "education": "",
        "degree": "",
        "branch": "",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Multi - Agent Systems,Model - Based Design",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "AI - Powered Assistant",
        "experience": "",
        "work_experience": "",
        "certifications": "",
        "achievements": "",
        "extraction_confidence": "medium",
        "missing_fields": [],
        "manual_review_required": True,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile(SANITIZED_ANAND_RESUME)

    assert "multi-agent" in profile["professional_summary"]
    assert "model-based" in profile["professional_summary"]
    assert "AI-Powered" in profile["professional_summary"]
    assert "AI-Powered Assistant" in profile["projects"]


def test_gpt_parser_normalizes_comma_spacing_for_list_like_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Built backend and AI projects.",
        "education": "B.Tech CSE",
        "degree": "B.Tech",
        "branch": "CSE",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Python,FastAPI,PostgreSQL",
        "technical_skills": "PyTorch,TensorFlow,OpenCV",
        "soft_skills": "Communication,Teamwork,Mentoring",
        "tools_frameworks": "Git,Docker,Streamlit",
        "projects": "Assistant API,Resume Parser,Cloud Review",
        "experience": "",
        "work_experience": "",
        "certifications": "AWS Basics,Python Certificate",
        "achievements": "Hackathon Finalist,400+ Problems Solved",
        "extraction_confidence": "high",
        "missing_fields": [],
        "manual_review_required": False,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile(SANITIZED_ANAND_RESUME)

    assert profile["top_skills"] == "Python, FastAPI, PostgreSQL"
    assert profile["technical_skills"] == "PyTorch, TensorFlow, OpenCV"
    assert profile["soft_skills"] == "Communication, Teamwork, Mentoring"
    assert profile["tools_frameworks"] == "Git, Docker, Streamlit"
    assert profile["projects"] == "Assistant API, Resume Parser, Cloud Review"
    assert profile["achievements"] == "Hackathon Finalist, 400+ Problems Solved"
    assert profile["certifications"] == "AWS Basics, Python Certificate"


def test_gpt_parser_cleans_markdown_mailto_email(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Devanshu Chandrakar",
        "email": "[devanshu.chandrakarr@gmail.com](mailto:devanshu.chandrakarr@gmail.com)",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Backend developer with AI project experience.",
        "education": "",
        "degree": "",
        "branch": "",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "",
        "experience": "",
        "work_experience": "",
        "certifications": "",
        "achievements": "",
        "extraction_confidence": "high",
        "missing_fields": [],
        "manual_review_required": False,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile("DEVANSHU CHANDRAKAR\nEmail: mailto:devanshu.chandrakarr@gmail.com")

    assert profile["email"] == "devanshu.chandrakarr@gmail.com"
    assert "mailto:" not in profile["email"]
    assert "[" not in profile["email"]


def test_gpt_parser_keeps_achievements_empty_without_explicit_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Student with training and internship experience.",
        "education": "B.Tech CSE",
        "degree": "B.Tech",
        "branch": "CSE",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Python, SQL",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "Portfolio Website",
        "experience": "Vocational training at Steel Authority\nAI Intern",
        "work_experience": "Vocational training at Steel Authority\nAI Intern",
        "certifications": "",
        "achievements": "Vocational training at Steel Authority",
        "extraction_confidence": "medium",
        "missing_fields": [],
        "manual_review_required": True,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))
    resume_without_achievements = """
TEST USER

Experience
Vocational training at Steel Authority
AI Intern

Projects
Portfolio Website
""".strip()

    profile = parser.extract_profile(resume_without_achievements)

    assert profile["achievements"] == ""


def test_gpt_parser_does_not_duplicate_vocational_training_into_achievements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Candidate with vocational training and project experience.",
        "education": "",
        "degree": "",
        "branch": "",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Python, React",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "Dashboard App",
        "experience": "Vocational training at Steel Authority",
        "work_experience": "Vocational training at Steel Authority",
        "certifications": "",
        "achievements": "Vocational training at Steel Authority",
        "extraction_confidence": "medium",
        "missing_fields": [],
        "manual_review_required": True,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile("TEST USER\nExperience\nVocational training at Steel Authority")

    assert "Vocational training" in profile["experience"]
    assert profile["achievements"] == ""


def test_gpt_parser_preserves_planned_project_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    payload = {
        "full_name": "Test User",
        "email": "",
        "phone": "",
        "location": "",
        "current_title": "",
        "target_role": "",
        "professional_summary": "Currently learning LangChain and planning a model-based agent workflow.",
        "education": "",
        "degree": "",
        "branch": "",
        "college": "",
        "college_university": "",
        "university": "",
        "graduation_year": "",
        "top_skills": "Python, LangChain",
        "technical_skills": "",
        "soft_skills": "",
        "tools_frameworks": "",
        "projects": "Planning a multi-agent interview assistant, currently learning retrieval evaluation",
        "experience": "",
        "work_experience": "",
        "certifications": "",
        "achievements": "",
        "extraction_confidence": "medium",
        "missing_fields": [],
        "manual_review_required": True,
        "manual_review_message": "",
    }
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient(payload))

    profile = parser.extract_profile("TEST USER\nProjects\nPlanning a multi-agent interview assistant")
    instructions = parser._instructions() + parser._input_text("Planning a project")

    assert "Planning a multi-agent" in profile["projects"]
    assert "currently learning" in profile["professional_summary"].lower()
    assert "preserve planned/in-progress wording" in instructions
    assert "must not be rewritten as completed implementation" in instructions


def test_gpt_parser_removes_unknown_fields_and_bounds_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    monkeypatch.setattr(gpt_module.settings, "RESUME_GPT_MAX_INPUT_CHARS", 20)
    client = FakeOpenAIClient(
        {
            "full_name": "Test User",
            "email": "",
            "phone": "",
            "location": "",
            "current_title": "",
            "target_role": "",
            "professional_summary": "",
            "education": "",
            "degree": "",
            "branch": "",
            "college": "",
            "college_university": "",
            "university": "",
            "graduation_year": "",
            "top_skills": "",
            "technical_skills": "",
            "soft_skills": "",
            "tools_frameworks": "",
            "projects": "",
            "experience": "",
            "work_experience": "",
            "certifications": "",
            "achievements": "",
            "extraction_confidence": "low",
            "missing_fields": ["education"],
            "manual_review_required": True,
            "manual_review_message": "Review needed.",
            "unexpected_secret": "drop me",
        }
    )
    parser = ResumeGptParserService(openai_client=client)

    profile = parser.extract_profile("A" * 80)

    assert "unexpected_secret" not in profile
    assert profile["raw_resume_text"] == "A" * 20


def test_gpt_parser_invalid_json_raises_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_gpt(monkeypatch)
    parser = ResumeGptParserService(openai_client=FakeOpenAIClient("{not-json"))

    with pytest.raises(ProviderError):
        parser.extract_profile(SANITIZED_ANAND_RESUME)


def test_gpt_parser_provider_error_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpt_module.settings, "RESUME_PARSER_PROVIDER", "gpt")
    monkeypatch.setattr(gpt_module.settings, "RESUME_PARSER_FALLBACK", "local")
    parser = ResumeParserService()
    monkeypatch.setattr(
        parser.gpt_parser,
        "extract_profile",
        lambda _: (_ for _ in ()).throw(
            ProviderError("bad json", provider="openai", model="gpt-5-mini", error_type="invalid_json")
        ),
    )

    result = parser.extract_profile(filename="resume.txt", content=SANITIZED_ANAND_RESUME.encode("utf-8"))

    assert result["parser_provider"] == "local"
    assert result["fallback_used"] is True
    assert result["profile"]["full_name"] == "Anand Vishwakarma"
