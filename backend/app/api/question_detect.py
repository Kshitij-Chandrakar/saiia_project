import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nlp.classifier import QuestionClassifier

router = APIRouter()
logger = logging.getLogger("question_detect_api")
logging.basicConfig(level=logging.INFO)

classifier = QuestionClassifier()


class QuestionDetectRequest(BaseModel):
    transcript: str
    combined_transcript: str | None = None


class QuestionDetectResponse(BaseModel):
    is_question: bool
    reason: str
    normalized_text: str
    normalized_question: str
    candidate_source: str
    confidence: float
    extracted_candidate: str
    polished_candidate: str


CODING_PROMPT_PATTERNS = [
    "write a program",
    "write program",
    "write a function",
    "write the function",
    "implement",
    "code this",
    "code it",
    "solve this",
    "solve it",
    "create a function",
    "complete the function",
    "complete the method",
    "debug this",
    "fix this code",
]

QUESTION_PROMPT_PATTERNS = [
    *CODING_PROMPT_PATTERNS,
    "what do you mean by",
    "what is meant by",
    "what does",
    "can you define",
    "could you define",
    "can you explain",
    "could you explain",
    "define",
    "tell me something about",
    "tell me about",
    "explain the concept of",
    "explain",
    "describe",
    "walk me through",
    "introduce yourself",
    "why should we hire you",
    "why do you want to join",
    "what is",
    "what are",
    "how do",
    "how would",
    "difference between",
    "talk about",
    "give me an overview of",
]

QUESTION_CONTEXT_PATTERNS = [
    "next question is",
    "the question is",
    "interviewer asks",
    "you may be asked",
    "answer this",
    "how would you answer",
    "common interview question",
]

VIDEO_NOISE_PATTERNS = [
    "welcome back",
    "in this video",
    "lets start",
    "let us start",
    "before we begin",
    "subscribe",
    "like and share",
    "comment below",
]

FILLER_PREFIXES = ["so", "okay", "yeah", "alright", "now", "next", "uh", "um"]
POLISH_REMOVALS = [
    "some of them specifically",
    "yeah",
    "okay",
    "so",
    "like",
    "you know",
    "basically",
    "actually",
    "now",
    "next question is",
    "interviewer asks",
    "can you tell me",
]


def _normalize_candidate_spacing(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    normalized = re.sub(r"\.{2,}", ".", normalized)
    return normalized.strip(" -,.")


def _clean_transcript_for_extraction(text: str) -> str:
    cleaned = _normalize_candidate_spacing(text)
    lowered = cleaned.lower()

    for phrase in VIDEO_NOISE_PATTERNS:
        lowered = lowered.replace(phrase, " ")

    cleaned = lowered
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^[\W_]+", "", cleaned)

    for prefix in FILLER_PREFIXES:
        cleaned = re.sub(rf"^(?:{re.escape(prefix)})[\s,.:;-]+", "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return _normalize_candidate_spacing(cleaned)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[?.!])\s+|\s+(?=(?:write a program|write program|write a function|write the function|implement|code this|code it|solve this|solve it|create a function|complete the function|complete the method|debug this|fix this code|what do you mean by|what is meant by|what does|can you define|could you define|can you explain|could you explain|define|tell me|explain|describe|walk me through|introduce yourself|why should|why do you|what is|what are|how do|how would|difference between|talk about|give me an overview of)\b)", text, flags=re.IGNORECASE)
    return [_normalize_candidate_spacing(part) for part in parts if _normalize_candidate_spacing(part)]


def _ensure_question_punctuation(candidate: str) -> str:
    text = _normalize_candidate_spacing(candidate)
    if not text:
        return ""
    if text.endswith("?"):
        return text[0].upper() + text[1:]
    lowered = text.lower()
    if any(lowered.startswith(prefix) for prefix in QUESTION_PROMPT_PATTERNS):
        return f"{text[0].upper() + text[1:]}" + ("" if text.endswith((".", "!", "?")) else ".")
    return text[0].upper() + text[1:]


def _repair_domain_question(candidate: str) -> tuple[str, str]:
    lowered = candidate.lower()
    if (
        "root node" in lowered
        and ("decision tree" in lowered or re.search(r"\btree\b", lowered))
    ) or (
        "root node" in lowered
        and any(keyword in lowered for keyword in ("gini", "entropy", "information gain"))
    ):
        return "How do we choose the root node in a decision tree?", "domain_repair_decision_tree_root"

    if "choose root node" in lowered and ("decision tree" in lowered or re.search(r"\btree\b", lowered)):
        return "How do we choose the root node in a decision tree?", "domain_repair_decision_tree_root"

    return candidate, ""


def polish_question_candidate(candidate: str) -> str:
    polished = _normalize_candidate_spacing(candidate)
    if not polished:
        return ""

    lowered = polished.lower()

    for phrase in POLISH_REMOVALS:
        lowered = re.sub(rf"\b{re.escape(phrase)}\b", " ", lowered, flags=re.IGNORECASE)

    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.-")

    if lowered.startswith("tell me about the differences between"):
        lowered = re.sub(
            r"^tell me about the differences between",
            "explain the difference between",
            lowered,
            flags=re.IGNORECASE,
        )

    lowered = re.sub(
        r"batch gradient descent mini batch gradient descent and stochastic gradient descent",
        "batch gradient descent, mini-batch gradient descent, and stochastic gradient descent",
        lowered,
        flags=re.IGNORECASE,
    )

    lowered = re.sub(
        r"\bmini batch gradient descent\b",
        "mini-batch gradient descent",
        lowered,
        flags=re.IGNORECASE,
    )

    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.-")
    polished = lowered[0].upper() + lowered[1:] if lowered else ""

    if polished.startswith("Explain the difference between") and not polished.endswith("?"):
        return polished + "."

    return _ensure_question_punctuation(polished)


def extract_question_candidate(transcript: str, combined_transcript: str | None = None) -> dict:
    latest_clean = _clean_transcript_for_extraction(transcript)
    combined_clean = _clean_transcript_for_extraction(combined_transcript or "")

    def extract_from_text(text: str, source_hint: str) -> dict:
        if not text:
            return {"candidate": "", "source": "none", "confidence": 0.0, "reason": "empty transcript"}

        sentences = _split_sentences(text)

        question_sentences = [sentence for sentence in sentences if "?" in sentence]
        if question_sentences:
            candidate = _ensure_question_punctuation(question_sentences[-1])
            return {
                "candidate": _repair_domain_question(candidate)[0],
                "source": "question_mark" if source_hint == "latest" else "combined_buffer",
                "confidence": 0.95,
                "reason": _repair_domain_question(candidate)[1] or "latest question-mark sentence extracted",
            }

        lowered = text.lower()
        for context in QUESTION_CONTEXT_PATTERNS:
            match = re.search(rf"{re.escape(context)}\s+(.*)", lowered, flags=re.IGNORECASE)
            if match:
                tail = _normalize_candidate_spacing(match.group(1))
                if tail:
                    for prompt in QUESTION_PROMPT_PATTERNS:
                        prompt_match = re.search(rf"({re.escape(prompt)}.*)", tail, flags=re.IGNORECASE)
                        if prompt_match:
                            candidate = _ensure_question_punctuation(prompt_match.group(1))
                            repaired_candidate, repair_reason = _repair_domain_question(candidate)
                            return {
                                "candidate": repaired_candidate,
                                "source": "interview_prompt",
                                "confidence": 0.92,
                                "reason": repair_reason or f"question extracted after context phrase '{context}'",
                            }

        latest_coding_index = -1
        latest_coding_prompt = ""
        for prompt in CODING_PROMPT_PATTERNS:
            prompt_index = lowered.rfind(prompt)
            if prompt_index > latest_coding_index:
                latest_coding_index = prompt_index
                latest_coding_prompt = prompt
        if latest_coding_index >= 0:
            candidate = _ensure_question_punctuation(text[latest_coding_index:])
            repaired_candidate, repair_reason = _repair_domain_question(candidate)
            return {
                "candidate": repaired_candidate,
                "source": "interview_prompt" if source_hint == "latest" else "combined_buffer",
                "confidence": 0.9,
                "reason": repair_reason or f"question extracted from coding phrase '{latest_coding_prompt}'",
            }

        for prompt in QUESTION_PROMPT_PATTERNS:
            if re.match(rf"^{re.escape(prompt)}(?:\s+|$)", lowered, flags=re.IGNORECASE):
                candidate = _ensure_question_punctuation(text)
                repaired_candidate, repair_reason = _repair_domain_question(candidate)
                return {
                    "candidate": repaired_candidate,
                    "source": "interview_prompt" if source_hint == "latest" else "combined_buffer",
                    "confidence": 0.9,
                    "reason": repair_reason or f"question extracted from prompt phrase '{prompt}'",
                }

        for sentence in reversed(sentences):
            sentence_lower = sentence.lower()
            for prompt in QUESTION_PROMPT_PATTERNS:
                prompt_index = sentence_lower.find(prompt)
                if prompt_index >= 0:
                    candidate = _ensure_question_punctuation(sentence[prompt_index:])
                    repaired_candidate, repair_reason = _repair_domain_question(candidate)
                    return {
                        "candidate": repaired_candidate,
                        "source": "interview_prompt" if source_hint == "latest" else "combined_buffer",
                        "confidence": 0.9,
                        "reason": repair_reason or f"question extracted from prompt phrase '{prompt}'",
                    }

        return {
            "candidate": "",
            "source": "none",
            "confidence": 0.0,
            "reason": "no_candidate",
        }

    latest_result = extract_from_text(latest_clean, "latest")
    if latest_result["candidate"]:
        return latest_result

    if combined_clean and combined_clean != latest_clean:
        combined_result = extract_from_text(combined_clean, "combined")
        if combined_result["candidate"]:
            return combined_result

    return latest_result


@router.post("", response_model=QuestionDetectResponse)
async def detect_question(req: QuestionDetectRequest):
    if req.transcript is None:
        raise HTTPException(status_code=400, detail="`transcript` field is required.")

    try:
        extracted = extract_question_candidate(req.transcript, req.combined_transcript)
        polished_candidate = polish_question_candidate(extracted["candidate"] or req.transcript)
        candidate = polished_candidate or extracted["candidate"] or req.transcript
        is_question, reason, normalized_text = classifier.should_process_as_question(candidate)
        normalized_question = _ensure_question_punctuation(polished_candidate or extracted["candidate"] or normalized_text)
        if not extracted["candidate"] and not is_question:
            reason = extracted["reason"] or reason
        logger.info(
            "Question detection completed is_question=%s reason=%s text_len=%s candidate_source=%s candidate_len=%s",
            is_question,
            reason,
            len((req.transcript or "").strip()),
            extracted["source"],
            len((extracted["candidate"] or "").strip()),
        )
        return QuestionDetectResponse(
            is_question=is_question,
            reason=reason,
            normalized_text=normalized_text,
            normalized_question=normalized_question,
            candidate_source=extracted["source"],
            confidence=float(extracted["confidence"]),
            extracted_candidate=extracted["candidate"],
            polished_candidate=polished_candidate,
        )
    except Exception as exc:
        logger.exception("Question detection error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error during question detection.",
        ) from exc
