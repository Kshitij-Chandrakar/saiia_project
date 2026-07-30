import hashlib
import json
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.nlp.answer_planner import AnswerPlan


_FILLER_PREFIXES = (
    "can you explain",
    "could you explain",
    "please explain",
    "explain",
    "what is the meaning of",
    "what is",
    "what are",
    "tell me about",
)

_STOP_TOKENS = {"a", "an", "the", "is", "are", "of", "to", "in", "for", "and"}


@dataclass(frozen=True)
class VariationPlan:
    repetition_detected: bool
    repetition_count: int
    variation_enabled: bool
    variation_profile: str
    allowed_dimensions: tuple[str, ...]
    locked_dimensions: tuple[str, ...]
    previous_answers: tuple[str, ...]
    previous_answer_count: int
    similarity_threshold: float
    rewrite_allowed: bool
    reason: str
    normalized_question: str
    context_fingerprint: str

    def as_metadata(self) -> dict[str, Any]:
        return {
            "repetition_detected": self.repetition_detected,
            "repetition_count": self.repetition_count,
            "variation_enabled": self.variation_enabled,
            "variation_profile": self.variation_profile,
            "previous_answer_count": self.previous_answer_count,
            "similarity_threshold": self.similarity_threshold,
            "rewrite_allowed": self.rewrite_allowed,
            "reason": self.reason,
        }


@dataclass
class _HistoryEntry:
    answer_type: str
    normalized_question: str
    context_fingerprint: str
    answer: str
    created_at: float


class AnswerVariationHistory:
    def __init__(self) -> None:
        self._entries: list[_HistoryEntry] = []

    def clear(self) -> None:
        self._entries.clear()

    def find(
        self,
        *,
        answer_type: str,
        normalized_question: str,
        context_fingerprint: str,
        ttl_seconds: int,
    ) -> list[_HistoryEntry]:
        self._purge(ttl_seconds)
        matches: list[_HistoryEntry] = []
        for entry in self._entries:
            if entry.answer_type != answer_type or entry.context_fingerprint != context_fingerprint:
                continue
            if questions_equivalent(entry.normalized_question, normalized_question):
                matches.append(entry)
        return matches

    def add(
        self,
        *,
        answer_type: str,
        normalized_question: str,
        context_fingerprint: str,
        answer: str,
        ttl_seconds: int,
        history_limit: int,
    ) -> None:
        self._purge(ttl_seconds)
        self._entries.append(
            _HistoryEntry(
                answer_type=answer_type,
                normalized_question=normalized_question,
                context_fingerprint=context_fingerprint,
                answer=answer,
                created_at=time.time(),
            )
        )
        scoped = [
            entry
            for entry in self._entries
            if entry.answer_type == answer_type
            and entry.context_fingerprint == context_fingerprint
            and questions_equivalent(entry.normalized_question, normalized_question)
        ]
        overflow = max(0, len(scoped) - history_limit)
        for entry in scoped[:overflow]:
            if entry in self._entries:
                self._entries.remove(entry)

    def _purge(self, ttl_seconds: int) -> None:
        cutoff = time.time() - ttl_seconds
        self._entries = [entry for entry in self._entries if entry.created_at >= cutoff]


def normalize_question_for_repetition(question: str) -> str:
    text = str(question or "").lower().strip()
    text = re.sub(r"\bwhat's\b", "what is", text)
    text = re.sub(r"\bcan't\b", "cannot", text)
    text = re.sub(r"[^a-z0-9+#.\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ?.!,:;")
    for prefix in _FILLER_PREFIXES:
        if text == prefix:
            return text
        if text.startswith(prefix + " "):
            text = text[len(prefix) :].strip()
            break
    return re.sub(r"\s+", " ", text).strip(" ?.!,:;")


def questions_equivalent(left: str, right: str) -> bool:
    if left == right:
        return True
    left_tokens = _meaningful_tokens(left)
    right_tokens = _meaningful_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    return overlap >= 0.82 and SequenceMatcher(None, left, right).ratio() >= 0.78


def context_fingerprint(
    *,
    profile: dict[str, Any] | None,
    retrieved_snippets: list[dict[str, Any]] | None,
    job_context: dict[str, Any] | None,
    profile_context_enabled: bool,
) -> str:
    payload = {
        "profile": profile if profile_context_enabled else {},
        "snippets": retrieved_snippets or [],
        "job": job_context or {},
    }
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_variation_plan(
    *,
    answer_plan: AnswerPlan,
    question: str,
    profile: dict[str, Any] | None,
    retrieved_snippets: list[dict[str, Any]] | None,
    job_context: dict[str, Any] | None,
    profile_context_enabled: bool,
    history: AnswerVariationHistory,
    enabled: bool,
    rewrite_enabled: bool,
    ttl_seconds: int,
    history_limit: int,
) -> VariationPlan:
    normalized_question = normalize_question_for_repetition(question)
    fingerprint = context_fingerprint(
        profile=profile,
        retrieved_snippets=retrieved_snippets,
        job_context=job_context,
        profile_context_enabled=profile_context_enabled,
    )
    if not enabled:
        return _plan(
            answer_plan=answer_plan,
            normalized_question=normalized_question,
            context_fingerprint=fingerprint,
            previous_answers=(),
            enabled=False,
            rewrite_allowed=False,
            reason="disabled",
        )
    previous = history.find(
        answer_type=answer_plan.answer_type,
        normalized_question=normalized_question,
        context_fingerprint=fingerprint,
        ttl_seconds=ttl_seconds,
    )
    previous_answers = tuple(_bound_answer(entry.answer) for entry in previous[-history_limit:])
    repetition_count = len(previous_answers) + 1
    rewrite_allowed = rewrite_enabled and answer_plan.answer_type not in {
        "coding",
        "debugging",
        "output_prediction",
        "mcq",
    }
    return _plan(
        answer_plan=answer_plan,
        normalized_question=normalized_question,
        context_fingerprint=fingerprint,
        previous_answers=previous_answers,
        enabled=enabled,
        rewrite_allowed=rewrite_allowed,
        reason="recent_equivalent_question" if previous_answers else "first_occurrence",
        repetition_count=repetition_count,
    )


def similarity_score(current: str, previous_answers: tuple[str, ...], *, answer_type: str) -> float:
    if not previous_answers:
        return 0.0
    current_norm = _normalize_answer_for_similarity(current, answer_type=answer_type)
    if not current_norm:
        return 0.0
    scores = []
    current_tokens = set(current_norm.split())
    for previous in previous_answers:
        previous_norm = _normalize_answer_for_similarity(previous, answer_type=answer_type)
        if not previous_norm:
            continue
        previous_tokens = set(previous_norm.split())
        token_score = len(current_tokens & previous_tokens) / max(len(current_tokens | previous_tokens), 1)
        scores.append(max(SequenceMatcher(None, current_norm, previous_norm).ratio(), token_score))
    return round(max(scores or [0.0]), 4)


def variation_instruction(plan: VariationPlan) -> str:
    if not plan.repetition_detected or not plan.variation_enabled:
        return ""
    previous = "\n\n---\n\n".join(plan.previous_answers[-2:])
    return (
        "\n\nControlled variation for repeated question:\n"
        "This is a repeated or substantially equivalent question. Generate a fresh answer without saying it is repeated.\n"
        f"Variation profile: {plan.variation_profile}.\n"
        f"You may vary: {', '.join(plan.allowed_dimensions)}.\n"
        f"You must preserve: {', '.join(plan.locked_dimensions)}.\n"
        "Avoid copying the recent wording, opening, transitions, bullet phrasing, and example scenario.\n"
        "Return only the final answer.\n\n"
        f"Recent answer excerpt:\n{previous}"
    )


def _plan(
    *,
    answer_plan: AnswerPlan,
    normalized_question: str,
    context_fingerprint: str,
    previous_answers: tuple[str, ...],
    enabled: bool,
    rewrite_allowed: bool,
    reason: str,
    repetition_count: int = 1,
) -> VariationPlan:
    profile = _profile_for_answer_type(answer_plan.answer_type, repetition_count)
    return VariationPlan(
        repetition_detected=bool(previous_answers),
        repetition_count=repetition_count,
        variation_enabled=enabled,
        variation_profile=profile,
        allowed_dimensions=_allowed_dimensions(answer_plan.answer_type),
        locked_dimensions=_locked_dimensions(answer_plan.answer_type),
        previous_answers=previous_answers,
        previous_answer_count=len(previous_answers),
        similarity_threshold=_threshold(answer_plan.answer_type),
        rewrite_allowed=rewrite_allowed,
        reason=reason,
        normalized_question=normalized_question,
        context_fingerprint=context_fingerprint,
    )


def _profile_for_answer_type(answer_type: str, repetition_count: int) -> str:
    profiles = {
        "technical_concept": ("alternative_opening", "point_order_shift", "alternate_example"),
        "technical_comparison": ("define_other_side_first", "tradeoff_order_shift", "alternate_example"),
        "technical_process": ("mechanism_first", "challenge_first", "alternate_example"),
        "hr_introduction": ("strengths_first", "project_first", "motivation_first"),
        "hr_motivation": ("motivation_first", "fit_first", "growth_first"),
        "role_fit": ("skills_first", "role_overlap_first", "motivation_first"),
        "behavioral": ("action_emphasis", "learning_emphasis", "challenge_emphasis"),
        "personal_story": ("scene_led", "reflective_opening", "alternate_safe_detail"),
        "resume_project": ("contribution_led", "architecture_led", "challenge_led"),
        "resume_experience": ("contribution_led", "learning_led", "technology_led"),
        "system_design": ("component_order_shift", "tradeoff_emphasis", "request_flow_first"),
    }.get(answer_type, ("alternative_opening", "order_shift", "concise_variant"))
    return profiles[(max(repetition_count, 2) - 2) % len(profiles)]


def _allowed_dimensions(answer_type: str) -> tuple[str, ...]:
    if answer_type in {"coding", "debugging", "output_prediction", "mcq"}:
        return ("explanation wording", "supporting detail order")
    if answer_type == "personal_story":
        return ("opening style", "safe low-risk scene detail", "reflection emphasis", "closing sentence")
    if answer_type in {"resume_project", "resume_experience", "role_fit", "behavioral"}:
        return ("opening sentence", "verified detail order", "emphasis", "transitions")
    if answer_type.startswith("technical") or answer_type == "system_design":
        return ("opening sentence", "point order", "transitions", "equally relevant example scenario")
    return ("opening sentence", "sentence construction", "transitions", "closing sentence")


def _locked_dimensions(answer_type: str) -> tuple[str, ...]:
    base = (
        "answer type",
        "context policies",
        "verified facts",
        "technical correctness",
        "required formatting",
    )
    if answer_type in {"coding", "debugging", "output_prediction"}:
        return base + ("code behavior", "function signatures", "final output")
    if answer_type == "mcq":
        return base + ("correct option",)
    if answer_type.startswith("technical"):
        return base + ("Real-life example: heading", "technical qualifications")
    return base


def _threshold(answer_type: str) -> float:
    if answer_type in {"coding", "debugging", "output_prediction", "mcq"}:
        return 0.97
    if answer_type in {"resume_project", "resume_experience", "role_fit", "behavioral"}:
        return 0.9
    return 0.86


def _meaningful_tokens(text: str) -> set[str]:
    return {token for token in str(text or "").split() if token not in _STOP_TOKENS}


def _normalize_answer_for_similarity(answer: str, *, answer_type: str) -> str:
    text = str(answer or "")
    if answer_type in {"coding", "debugging", "output_prediction"}:
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = text.lower()
    text = re.sub(r"[^a-z0-9+#\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _bound_answer(answer: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(answer or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."
