import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


FOLLOWUP_PRONOUN_RE = re.compile(
    r"\b(it|its|they|them|their|this|that|these|those|same|previous one|second point|second one)\b",
    re.IGNORECASE,
)
FOLLOWUP_PREFIX_RE = re.compile(r"^\s*(and|also|then|so|what about|how about|in that case|based on that)\b", re.I)
STANDALONE_RE = re.compile(
    r"^\s*(what is|what are|explain|describe|define|compare|design|tell me about)\s+"
    r"(authentication|authorization|python|java|caching|rag|rest|graphql|sql|nosql|supervised learning|"
    r"machine learning|context window|self attention|cross attention|saiia|fastapi|database|process|thread)\b",
    re.I,
)


@dataclass
class FollowUpContextEntry:
    entry_id: str
    mode: str
    original_question: str
    resolved_question: str = ""
    answer_excerpt: str = ""
    answer_type: str = ""
    topic: str = ""
    created_at: float = 0.0

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "FollowUpContextEntry":
        return cls(
            entry_id=str(payload.get("entry_id") or payload.get("id") or ""),
            mode=str(payload.get("mode") or "").strip().lower(),
            original_question=str(payload.get("original_question") or payload.get("question") or "").strip(),
            resolved_question=str(payload.get("resolved_question") or "").strip(),
            answer_excerpt=str(payload.get("answer_excerpt") or "").strip()[:1000],
            answer_type=str(payload.get("answer_type") or payload.get("category") or "").strip().lower(),
            topic=str(payload.get("topic") or "").strip(),
            created_at=_coerce_timestamp(payload.get("created_at")),
        )


@dataclass
class FollowUpResolution:
    follow_up_detected: bool
    original_question: str
    resolved_question: str
    resolution_status: str
    resolution_method: str = "deterministic"
    confidence: float = 0.0
    context_entry_ids: List[str] = field(default_factory=list)
    context_mode: str = ""
    topic: Optional[str] = None
    ambiguity_reason: Optional[str] = None
    clarification_question: Optional[str] = None
    resolution_ms: float = 0.0
    reason: str = ""

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "original_question": self.original_question,
            "resolved_question": self.resolved_question,
            "follow_up_detected": self.follow_up_detected,
            "follow_up_confidence": self.confidence,
            "follow_up_resolution_status": self.resolution_status,
            "follow_up_resolution_method": self.resolution_method,
            "follow_up_context_entry_ids": self.context_entry_ids,
            "follow_up_topic": self.topic,
            "follow_up_resolution_ms": self.resolution_ms,
            "clarification_required": self.resolution_status == "needs_clarification",
            "clarification_question": self.clarification_question,
        }


def _coerce_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _clean_question(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _strip_question_prefix(question: str) -> str:
    text = _clean_question(question).strip(" ?.")
    text = re.sub(r"^(what is|what are|explain|describe|define|tell me about|design|compare)\s+", "", text, flags=re.I)
    text = re.sub(r"^(a|an|the)\s+", "", text, flags=re.I)
    return text.strip(" ?.")


def infer_topic(entry: FollowUpContextEntry) -> str:
    if entry.topic:
        return entry.topic
    source = entry.resolved_question or entry.original_question
    lowered = source.lower()
    known = [
        "supervised learning",
        "retrieval-augmented generation",
        "rag",
        "authentication",
        "authorization",
        "rest and graphql",
        "rest",
        "graphql",
        "sql",
        "nosql",
        "process and thread",
        "exception handling",
        "url shortener",
        "saiia project",
        "saiia",
        "fastapi",
        "childhood",
        "difficult bug",
        "angry customer",
        "urgent deadlines",
        "caching",
    ]
    for item in known:
        if item in lowered:
            if item == "saiia":
                return "SAIIA project"
            return item
    return _strip_question_prefix(source)


def _has_clear_subject(question: str) -> bool:
    first_clause = re.split(r"[,:;]|\band\b|\bbut\b", question, maxsplit=1, flags=re.I)[0]
    if STANDALONE_RE.search(question):
        return True
    explicit_technical_subject = re.match(
        r"^\s*how\s+(?:is|are|does|do)\s+(.{1,80}?)\s+"
        r"(implemented|built|validated|designed|used|working|work)"
        r"(?:\s+.{1,80}?)?\s*\??\s*$",
        question,
        re.I,
    )
    if explicit_technical_subject:
        subject = str(explicit_technical_subject.group(1) or "").strip()
        if subject and not FOLLOWUP_PRONOUN_RE.search(subject):
            return True
    active_technical_subject = re.match(
        r"^\s*how\s+(?:do|did)\s+you\s+"
        r"(implement|build|design|validate|use)\s+(.{1,80}?)"
        r"(?=\s+(?:in|with|for|using|via)\b|(?:\s+that\b)|\s*\??\s*$)",
        question,
        re.I,
    )
    if not active_technical_subject:
        active_technical_subject = re.match(
            r"^\s*how\s+(?:do|did)\s+you\s+"
            r"(implement|build|design|validate|use)\s+(.{1,80}?)"
            r"\s*\??\s*$",
            question,
            re.I,
        )
    if active_technical_subject:
        subject = str(active_technical_subject.group(2) or "").strip()
        if subject and not FOLLOWUP_PRONOUN_RE.search(subject):
            return True
    if re.search(r"\b(what was|what is|what are|why did|how did)\b.{0,50}\b(in|for|to|while)\s+[A-Z]?[a-z0-9][\w-]+", question, re.I):
        return True
    if re.search(r"\b(authentication|authorization|python|java|caching|rag|rest|graphql|sql|nosql|supervised learning)\b", question, re.I):
        return not FOLLOWUP_PRONOUN_RE.search(first_clause)
    return False


def _looks_like_followup(question: str) -> bool:
    text = _clean_question(question)
    if FOLLOWUP_PREFIX_RE.search(text) or FOLLOWUP_PRONOUN_RE.search(text):
        return True
    return bool(
        re.match(
            r"^\s*(why|how|what are the (advantages|benefits|disadvantages|limitations|challenges)|"
            r"can you give another example|can you give an example|explain the second point|"
            r"what was (your role|the biggest challenge|the result)|what did you learn|"
            r"which one is better|which happens first|can you optimize it|what is its time complexity)\b",
            text,
            re.I,
        )
    )


def _ambiguous(entry: FollowUpContextEntry, question: str, topic: str) -> bool:
    vague = re.search(r"^\s*(how does it work|why|how|what about it)\??\s*$", question, re.I)
    multi_topic = bool(re.search(r"\b(and|vs|versus)\b|,", topic, re.I))
    answer_has_many_refs = len(set(re.findall(r"\b(authentication|authorization|token|permission|identity)\b", entry.answer_excerpt.lower()))) >= 3
    return bool(vague and (multi_topic or answer_has_many_refs))


def _resolve_with_topic(question: str, entry: FollowUpContextEntry, topic: str) -> tuple[str, str, float]:
    text = _clean_question(question).strip(" ?.")
    lower = text.lower()
    display_topic = "retrieval-augmented generation" if topic.lower() == "rag" else topic

    if re.match(r"what are (its|the)?\s*examples", lower):
        return f"What are examples of {display_topic}?", "examples_pattern", 0.9
    if re.match(r"what are (its|the)?\s*(advantages|benefits|disadvantages|limitations|challenges)", lower):
        noun = re.search(r"(advantages|benefits|disadvantages|limitations|challenges)", lower).group(1)
        return f"What are the {noun} of {display_topic}?", "property_pattern", 0.88
    if "different from" in lower:
        target = re.sub(r"^how is (it|this|that)\s+different from\s+", "", lower, flags=re.I).strip()
        target = target or "the other concept"
        return f"How is {display_topic} different from {target}?", "comparison_pattern", 0.9
    if lower.startswith("and in "):
        language = text[7:].strip()
        base = "exception handling" if "exception" in topic.lower() else display_topic
        return f"How does {base} work in {language}?", "language_transfer_pattern", 0.86
    if lower in {"can you optimize it", "can you optimize this"}:
        return f"Can you optimize the previous solution for {display_topic}?", "coding_optimization_pattern", 0.86
    if "time complexity" in lower:
        return f"What is the time complexity of the previous solution for {display_topic}?", "coding_complexity_pattern", 0.86
    if "another example" in lower:
        return f"Can you give another example of {display_topic}?", "another_example_pattern", 0.84
    if "second point" in lower:
        return f"Can you explain the second point from the previous answer about {display_topic}?", "answer_reference_pattern", 0.82
    if "biggest challenge" in lower:
        return f"What was the biggest challenge you faced while working on {display_topic}?", "project_challenge_pattern", 0.88
    if "your role" in lower or "your contribution" in lower:
        return f"What was your contribution to {display_topic}?", "project_role_pattern", 0.88
    if "why did you choose" in lower:
        return f"Why did you choose {display_topic} for that project?", "choice_pattern", 0.85
    if "what did you learn" in lower:
        return f"What did you learn from the {display_topic} you described?", "learning_pattern", 0.84
    if "influence you" in lower:
        return f"How did your {display_topic} influence you?", "personal_followup_pattern", 0.84
    if lower.startswith("what if"):
        return f"{text} in the previous {display_topic} scenario?", "scenario_followup_pattern", 0.78
    if lower.startswith("what about"):
        subject = text.split(" ", 2)[2] if len(text.split(" ", 2)) > 2 else "that"
        return f"What about {subject} in {display_topic}?", "what_about_pattern", 0.76
    if lower in {"why", "how", "how does that work", "how does it work", "why is it needed"}:
        return f"{text.capitalize()} in {display_topic}?", "short_reference_pattern", 0.72
    return f"{text} in the context of {display_topic}?", "generic_followup_pattern", 0.65


def resolve_live_followup(
    *,
    question: str,
    mode: str,
    context_entries: List[Dict[str, Any]],
    enabled: bool = True,
    history_limit: int = 5,
    ttl_seconds: int = 1800,
    now: Optional[float] = None,
) -> FollowUpResolution:
    started = time.perf_counter()
    original = _clean_question(question)
    context_mode = str(mode or "").strip().lower()

    def done(result: FollowUpResolution) -> FollowUpResolution:
        result.resolution_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    if not enabled:
        return done(FollowUpResolution(False, original, original, "disabled", "none", reason="disabled"))
    if not original:
        return done(FollowUpResolution(False, original, original, "standalone", "none", reason="empty_question"))
    if _has_clear_subject(original):
        return done(FollowUpResolution(False, original, original, "standalone", "none", reason="clear_subject"))
    if not _looks_like_followup(original):
        return done(FollowUpResolution(False, original, original, "standalone", "none", reason="no_followup_indicator"))

    cutoff = (now if now is not None else time.time()) - ttl_seconds
    candidates = [
        FollowUpContextEntry.from_payload(item)
        for item in context_entries[:history_limit]
        if isinstance(item, dict)
    ]
    candidates = [
        item
        for item in candidates
        if item.mode == context_mode
        and item.entry_id
        and (item.resolved_question or item.original_question)
        and (not item.created_at or item.created_at >= cutoff)
    ]
    if not candidates:
        return done(
            FollowUpResolution(
                True,
                original,
                original,
                "needs_clarification",
                confidence=0.35,
                context_mode=context_mode,
                clarification_question="Which earlier topic should I connect this follow-up to?",
                reason="no_recent_same_mode_context",
            )
        )

    anchor = candidates[0]
    topic = infer_topic(anchor)
    if _ambiguous(anchor, original, topic):
        return done(
            FollowUpResolution(
                True,
                original,
                original,
                "needs_clarification",
                confidence=0.42,
                context_entry_ids=[anchor.entry_id],
                context_mode=context_mode,
                topic=topic,
                ambiguity_reason="multiple_possible_antecedents",
                clarification_question=f"When you say that, do you mean {topic} or another point from the previous answer?",
                reason="ambiguous_reference",
            )
        )

    resolved, reason, confidence = _resolve_with_topic(original, anchor, topic)
    return done(
        FollowUpResolution(
            True,
            original,
            resolved,
            "resolved",
            confidence=confidence,
            context_entry_ids=[anchor.entry_id],
            context_mode=context_mode,
            topic=topic,
            reason=reason,
        )
    )
