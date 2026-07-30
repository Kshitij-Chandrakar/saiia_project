import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.nlp.coding_quality_gate import detect_programming_language
from app.nlp.followup_resolver import FollowUpResolution


RequestedAction = Literal[
    "define",
    "explain",
    "implement_example",
    "implement_solution",
    "optimize_existing",
    "convert_language",
    "debug_existing",
    "fix_existing",
    "explain_code",
    "explain_code_section",
    "calculate_complexity",
    "dry_run",
    "analyze_edge_case",
    "compare",
    "give_example",
    "give_another_example",
    "advantages",
    "disadvantages",
    "simplify",
    "expand_point",
    "continue_scenario",
    "discuss_role",
    "discuss_challenge",
    "discuss_learning",
    "general_followup",
    "unknown",
]


class FollowUpIntentPlan(BaseModel):
    follow_up_detected: bool = False
    original_question: str = ""
    resolved_question: str = ""
    reference_status: Literal["not_required", "resolved", "ambiguous", "missing"] = "not_required"
    reference_topic: str | None = None
    reference_entry_ids: list[str] = Field(default_factory=list)
    reference_entities: list[str] = Field(default_factory=list)
    requested_action: RequestedAction = "unknown"
    requested_output: Literal[
        "concept_answer",
        "structured_coding_answer",
        "coding_optimization",
        "code_explanation",
        "complexity_analysis",
        "comparison_answer",
        "practical_answer",
        "behavioral_answer",
        "clarification",
        "general_answer",
    ] = "general_answer"
    programming_language: str | None = None
    platform_mode: Literal[
        "standalone_demo",
        "standalone_program",
        "platform_submission",
        "function_only",
        "existing_code_revision",
        "not_applicable",
    ] = "not_applicable"
    inherited_constraints: dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarification_question: str | None = None
    ambiguity_reason: str | None = None
    resolution_method: Literal["deterministic", "existing_model_assisted", "none"] = "deterministic"
    confidence: float = 0.0
    resolution_ms: float = 0.0

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _latest_context_entry(context_entries: list[dict[str, Any]], mode: str, entry_ids: list[str]) -> dict[str, Any]:
    wanted = set(entry_ids)
    for item in context_entries:
        if not isinstance(item, dict):
            continue
        if str(item.get("mode") or "").strip().lower() != mode:
            continue
        if wanted and str(item.get("entry_id") or item.get("id") or "") not in wanted:
            continue
        if item.get("resolved_question") or item.get("original_question") or item.get("question"):
            return item
    return {}


def _detect_action(question: str) -> RequestedAction:
    q = _clean(question).lower()
    if re.search(r"\b(?:optimi[sz]e|make it faster|reduce (?:the )?space|without extra space|improve (?:the )?complexity)\b", q):
        return "optimize_existing"
    if re.search(r"\b(?:convert|do the same|write it|now)\s+(?:in|to|using)\s+(python|py|java(?!script)|javascript|js|typescript|ts|c\+\+|cpp|c#|c sharp)\b", q):
        return "convert_language"
    if re.search(r"\b(?:time complexity|space complexity|complexity|how efficient)\b", q):
        return "calculate_complexity"
    if re.search(r"\b(?:explain|what does|why did).*\b(?:loop|line|condition|function|method|dictionary|hash map|code)\b", q):
        return "explain_code_section"
    if re.search(r"\b(?:empty input|null|duplicates?|negative values?|zero)\b", q):
        return "analyze_edge_case"
    if re.search(r"\b(?:implement|write a program|code it|show .*code|create .*program|show the implementation|can you implement|can you code)\b", q):
        return "implement_example"
    if re.search(r"\b(?:write the function|complete the method|complete the function|solve it)\b", q):
        return "implement_solution"
    if re.search(r"\b(?:debug|fix)\b", q):
        return "fix_existing"
    if re.search(r"\banother example\b", q):
        return "give_another_example"
    if re.search(r"\b(?:example|give an example)\b", q):
        return "give_example"
    if re.search(r"\b(?:advantages|benefits)\b", q):
        return "advantages"
    if re.search(r"\b(?:disadvantages|limitations|drawbacks)\b", q):
        return "disadvantages"
    if re.search(r"\b(?:role|contribution)\b", q):
        return "discuss_role"
    if re.search(r"\b(?:biggest challenge|challenge)\b", q):
        return "discuss_challenge"
    if re.search(r"\b(?:learn|learned)\b", q):
        return "discuss_learning"
    if re.search(r"\b(?:what if|still refuses|customer)\b", q):
        return "continue_scenario"
    if re.search(r"\b(?:different|compare|versus|vs)\b", q):
        return "compare"
    if re.search(r"\b(?:explain|how does|why)\b", q):
        return "explain"
    return "general_followup"


def _output_for_action(action: RequestedAction) -> str:
    if action in {"implement_example", "implement_solution", "convert_language"}:
        return "structured_coding_answer"
    if action == "optimize_existing":
        return "coding_optimization"
    if action in {"explain_code", "explain_code_section"}:
        return "code_explanation"
    if action == "calculate_complexity":
        return "complexity_analysis"
    if action == "compare":
        return "comparison_answer"
    if action == "continue_scenario":
        return "practical_answer"
    if action in {"discuss_role", "discuss_challenge", "discuss_learning"}:
        return "behavioral_answer"
    if action in {"define", "explain", "advantages", "disadvantages", "give_example", "give_another_example", "simplify", "expand_point"}:
        return "concept_answer"
    return "general_answer"


def _explicit_language(question: str) -> str | None:
    language = detect_programming_language(question, None, default="")
    return language or None


def _entry_language(entry: dict[str, Any]) -> str | None:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    coding_answer = metadata.get("codingAnswer") or entry.get("coding_answer") or {}
    if isinstance(coding_answer, dict) and coding_answer.get("language"):
        return str(coding_answer.get("language")).strip().lower()
    return str(entry.get("programming_language") or metadata.get("programmingLanguage") or "").strip().lower() or None


def _demo_detail(topic: str) -> str:
    normalized = topic.lower()
    examples = (
        (("stack",), "using push, pop, and display operations"),
        (("queue",), "using enqueue, dequeue, and display operations"),
        (("dictionary", "map", "hash map"), "by storing key-value pairs and reading one value by key"),
        (("class", "object"), "by defining a small class, creating an object, and calling a method"),
        (("exception",), "with a try/except block that handles an invalid operation safely"),
        (("inheritance",), "by creating a base class and a derived class that overrides behavior"),
        (("array", "list"), "by storing multiple values, iterating over them, and printing the elements"),
    )
    for needles, detail in examples:
        if any(needle in normalized for needle in needles):
            return detail
    return "with a small, clear standalone demonstration"


def _compile_resolved_question(
    *,
    action: RequestedAction,
    topic: str,
    language: str | None,
    fallback_question: str,
) -> tuple[str, str]:
    lang = (language or "python").strip().lower()
    display_lang = {"cpp": "C++", "csharp": "C#", "javascript": "JavaScript"}.get(lang, lang.title())
    clean_topic = _clean(topic) or "the previous topic"
    if action == "implement_example":
        return (
            f"Write a {display_lang} program that demonstrates {clean_topic} {_demo_detail(clean_topic)}. "
            "This is a standalone demonstration with no stdin input contract.",
            "standalone_demo",
        )
    if action == "implement_solution":
        return f"Write a complete {display_lang} solution for {clean_topic}, preserving any previous constraints.", "standalone_program"
    if action == "convert_language":
        return f"Write the previous {clean_topic} implementation in {display_lang}, preserving the same behavior and constraints.", "existing_code_revision"
    if action == "optimize_existing":
        return f"Optimize the previous {clean_topic} solution while preserving behavior, language, and any function or platform contract.", "existing_code_revision"
    if action == "calculate_complexity":
        return f"Explain the time and space complexity of the previous {clean_topic} implementation.", "not_applicable"
    if action == "explain_code_section":
        return f"Explain the referenced part of the previous {clean_topic} code.", "not_applicable"
    if action == "analyze_edge_case":
        return f"Analyze that edge case for {clean_topic}.", "not_applicable"
    return fallback_question, "not_applicable"


def compile_followup_intent(
    *,
    question: str,
    mode: str,
    context_entries: list[dict[str, Any]],
    resolution: FollowUpResolution,
    default_language: str = "python",
) -> FollowUpIntentPlan:
    started = time.perf_counter()
    original = _clean(question)
    context_mode = str(mode or "").strip().lower()
    if not resolution.follow_up_detected:
        return FollowUpIntentPlan(
            follow_up_detected=False,
            original_question=original,
            resolved_question=resolution.resolved_question or original,
            requested_action="unknown",
            requested_output="general_answer",
            resolution_method="none",
            confidence=1.0,
            resolution_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    if resolution.resolution_status == "needs_clarification":
        return FollowUpIntentPlan(
            follow_up_detected=True,
            original_question=original,
            resolved_question=resolution.resolved_question or original,
            reference_status="ambiguous" if resolution.ambiguity_reason else "missing",
            reference_topic=resolution.topic,
            reference_entry_ids=list(resolution.context_entry_ids),
            requested_action=_detect_action(original),
            requested_output="clarification",
            needs_clarification=True,
            clarification_question=resolution.clarification_question,
            ambiguity_reason=resolution.ambiguity_reason or resolution.reason,
            confidence=resolution.confidence,
            resolution_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    entry = _latest_context_entry(context_entries, context_mode, resolution.context_entry_ids)
    topic = _clean(resolution.topic or entry.get("topic") or resolution.resolved_question or original)
    action = _detect_action(original)
    output = _output_for_action(action)
    language = _explicit_language(original) or _entry_language(entry) or default_language
    resolved_question, platform_mode = _compile_resolved_question(
        action=action,
        topic=topic,
        language=language,
        fallback_question=resolution.resolved_question or original,
    )
    constraints = {
        "previous_code_available": bool(entry.get("code") or entry.get("code_present")),
        "previous_language": _entry_language(entry),
        "platform": entry.get("platform") or "",
        "function_signature": entry.get("function_signature") or "",
    }
    return FollowUpIntentPlan(
        follow_up_detected=True,
        original_question=original,
        resolved_question=resolved_question,
        reference_status="resolved",
        reference_topic=topic,
        reference_entry_ids=list(resolution.context_entry_ids),
        reference_entities=[topic] if topic else [],
        requested_action=action,
        requested_output=output,  # type: ignore[arg-type]
        programming_language=language,
        platform_mode=platform_mode,  # type: ignore[arg-type]
        inherited_constraints=constraints,
        confidence=max(resolution.confidence, 0.72 if action != "general_followup" else resolution.confidence),
        resolution_ms=round((time.perf_counter() - started) * 1000, 2),
    )
