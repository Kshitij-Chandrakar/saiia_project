import re
from dataclasses import dataclass
from typing import Any, Dict, Literal

from app.nlp.classifier import (
    classify_personal_subtype,
    classify_question_by_rules,
    looks_like_coding_implementation_request,
)


ContextPolicy = Literal["REQUIRED", "ALLOWED", "FORBIDDEN"]

ANSWER_TYPES = {
    "hr_introduction",
    "hr_motivation",
    "behavioral",
    "personal_story",
    "resume_overview",
    "resume_project",
    "resume_experience",
    "role_fit",
    "technical_concept",
    "technical_comparison",
    "technical_process",
    "coding",
    "debugging",
    "output_prediction",
    "system_design",
    "mcq",
    "screen_question",
    "general",
    "follow_up",
}


@dataclass(frozen=True)
class AnswerPlan:
    answer_type: str
    source_category: str
    voice_perspective: str
    profile_context_policy: ContextPolicy
    job_context_policy: ContextPolicy
    general_knowledge_policy: ContextPolicy
    preferred_structure: str
    minimum_detail: str
    maximum_words: int
    example_policy: str
    validation_level: str
    correction_allowed: bool
    code_required: bool
    confidence: float
    reason: str

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "answer_type": self.answer_type,
            "plan_confidence": self.confidence,
            "profile_context_policy": self.profile_context_policy,
            "job_context_policy": self.job_context_policy,
            "general_knowledge_policy": self.general_knowledge_policy,
        }


def build_answer_plan(
    *,
    question: str,
    category: str,
    source: str = "",
    screen_question_type: str = "",
) -> AnswerPlan:
    text = re.sub(r"\s+", " ", str(question or "").strip())
    normalized = text.lower()
    source_category = (classify_question_by_rules(text) or category or "general").lower()
    screen_type = str(screen_question_type or "").strip().lower()

    if screen_type == "coding":
        return _plan("coding", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "code", "complete", 900, "edge cases when useful", "deterministic", True, True, 0.92, "screen coding question")
    if screen_type == "debugging":
        return _plan("debugging", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "bug_fix", "complete", 650, "only if useful", "deterministic", True, True, 0.9, "screen debugging question")
    if screen_type == "output":
        return _plan("output_prediction", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "trace", "concise", 450, "for execution trace only", "deterministic", False, False, 0.9, "screen output question")
    if screen_type == "mcq":
        return _plan("mcq", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "option_plus_reason", "concise", 180, "for option clarity only", "deterministic", False, False, 0.88, "screen MCQ")
    if screen_type in {"visual", "architecture"}:
        answer_type = "system_design" if screen_type == "architecture" else "screen_question"
        return _plan(answer_type, source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "direct", "useful", 350, "only from visible screen", "deterministic", False, False, 0.84, "screen visual question")

    if _matches(normalized, ("tell me about yourself", "introduce yourself", "walk me through your background")):
        return _plan("hr_introduction", source_category, "first_person", "REQUIRED", "ALLOWED", "ALLOWED", "spoken_paragraphs", "substantive", 140, "supported project if useful", "deterministic", False, False, 0.9, "introduction needs verified candidate context")
    if _matches(normalized, ("why should we hire", "why do you want this role", "why this role", "why do you want to join", "why this company")):
        return _plan("role_fit", source_category, "first_person", "REQUIRED", "REQUIRED", "ALLOWED", "evidence_to_role", "substantive", 150, "supported overlap only", "deterministic", False, False, 0.88, "role fit question")
    if _matches(normalized, ("main project", "saiia", "your role in", "technologies did you use")) or re.search(
        r"\byour\b.{0,40}\bproject\b", normalized
    ):
        return _plan("resume_project", source_category, "first_person", "REQUIRED", "ALLOWED", "FORBIDDEN", "grounded_summary", "substantive", 160, "verified project detail", "deterministic", False, False, 0.86, "resume/project question")
    if _matches(normalized, ("your experience", "how did you use", "work experience", "your role", "your responsibility")):
        return _plan("resume_experience", source_category, "first_person", "REQUIRED", "ALLOWED", "ALLOWED", "grounded_summary", "substantive", 160, "verified experience detail", "deterministic", False, False, 0.82, "candidate experience question")
    if source_category == "behavioral" or _matches(normalized, ("tell me about a time", "describe a time", "difficult bug", "conflict", "failure", "under pressure")):
        return _plan("behavioral", source_category, "first_person", "REQUIRED", "ALLOWED", "FORBIDDEN", "star_natural", "substantive", 170, "one verified story", "deterministic", False, False, 0.86, "behavioral question")
    if classify_personal_subtype(text):
        return _plan("personal_story", source_category, "first_person", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "natural_story", "substantive", 170, "personal detail only", "deterministic", False, False, 0.88, "personal rapport question")
    if looks_like_coding_implementation_request(text):
        return _plan("coding", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "code", "complete", 900, "edge cases when useful", "deterministic", True, True, 0.88, "coding implementation request")
    if _matches(normalized, ("system design", "design a", "architecture", "url shortener", "notification service", "chat system")):
        return _plan("system_design", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "tradeoffs", "detailed", 280, "practical system example", "deterministic", False, False, 0.82, "system design question")
    if _matches(normalized, (" vs ", " versus ", "difference between", "compare ")):
        return _plan("technical_comparison", source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "direct_then_points", "useful", 180, "only if useful", "deterministic", False, False, 0.88, "technical comparison")
    if source_category == "technical" or _matches(normalized, ("what is", "how does", "benefits of", "rest api", "dependency injection", "normalization", "caching", "race condition", "overfitting")):
        answer_type = "technical_process" if _matches(normalized, ("how does", "process", "steps", "workflow")) else "technical_concept"
        return _plan(answer_type, source_category, "neutral", "FORBIDDEN", "FORBIDDEN", "ALLOWED", "direct_then_optional_points", "useful", 180, "practical example when useful", "deterministic", False, False, 0.86, "general technical question")

    return _plan("general", source_category or "general", "neutral", "ALLOWED", "ALLOWED", "ALLOWED", "direct", "useful", 140, "only if useful", "deterministic", False, False, 0.55, "safe general fallback")


def validate_answer_against_plan(answer: str, plan: AnswerPlan, *, profile_context_used: bool) -> Dict[str, Any]:
    text = str(answer or "").strip()
    normalized = text.lower()
    issues: list[str] = []
    if not text:
        issues.append("empty_answer")
    if re.search(r"\b(you can say|as an ai|here is a possible answer|the candidate should say)\b", normalized):
        issues.append("meta_phrase")
    if plan.profile_context_policy == "FORBIDDEN" and profile_context_used:
        issues.append("profile_context_forbidden")
    if plan.code_required and "```" not in text and not re.search(r"(?m)^\s*(def|class|import|from)\s+", text):
        issues.append("missing_code")
    if plan.answer_type.startswith("technical") and re.search(r"\brag\b", normalized):
        if re.search(r"\b(always|guarantees|eliminates hallucinations|makes inference faster|makes the model smaller)\b", normalized):
            issues.append("misleading_absolute_claim")
    if plan.answer_type.startswith("technical") and re.search(r"authentication.*authorization|authorization.*authentication", normalized):
        if re.search(r"\b(same|identical|interchangeable)\b", normalized):
            issues.append("misleading_auth_claim")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) != len(set(paragraphs)):
        issues.append("duplicate_paragraph")

    return {
        "validation_status": "passed" if not issues else "warning",
        "validation_issues": issues,
        "validation_issues_count": len(issues),
        "answer_verified": not issues,
    }


def _matches(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _plan(
    answer_type: str,
    source_category: str,
    voice_perspective: str,
    profile_policy: ContextPolicy,
    job_policy: ContextPolicy,
    knowledge_policy: ContextPolicy,
    structure: str,
    minimum_detail: str,
    maximum_words: int,
    example_policy: str,
    validation_level: str,
    correction_allowed: bool,
    code_required: bool,
    confidence: float,
    reason: str,
) -> AnswerPlan:
    if answer_type not in ANSWER_TYPES:
        answer_type = "general"
    return AnswerPlan(
        answer_type=answer_type,
        source_category=source_category,
        voice_perspective=voice_perspective,
        profile_context_policy=profile_policy,
        job_context_policy=job_policy,
        general_knowledge_policy=knowledge_policy,
        preferred_structure=structure,
        minimum_detail=minimum_detail,
        maximum_words=maximum_words,
        example_policy=example_policy,
        validation_level=validation_level,
        correction_allowed=correction_allowed,
        code_required=code_required,
        confidence=max(0.0, min(1.0, confidence)),
        reason=reason,
    )
