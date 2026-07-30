import logging
import re
from typing import Literal

from app.config import settings


Category = Literal["personal", "hr", "technical", "behavioral", "general"]
PERSONAL_SUBTYPES = {
    "childhood_background",
    "childhood_memory",
    "personal_challenge",
    "difficult_phase",
    "personal_failure",
    "personal_achievement",
    "proud_moment",
    "helping_someone",
    "friendship_family",
    "adaptability_change",
    "fear_overcome",
    "hobbies_interests",
    "books_movies_music",
    "favourite_preferences",
    "role_model_influence",
    "personal_values",
    "personality_self_awareness",
    "travel_memory",
    "funny_embarrassing_memory",
    "creative_imaginative",
    "life_goal_dream",
    "sensitive_personal",
}


_PROFESSIONAL_DOMAIN_PATTERN = re.compile(
    r"\b(work|job|career|role|company|employer|team|client|project|production|professional|"
    r"technical|technology|system|software|code|api|database|cloud|framework|architecture|"
    r"leadership|deadline|conflict|failure|challenge|hire|strength|weakness)\b"
)

_INCOMPLETE_DEFINITION_PROMPTS = {
    "what do you mean",
    "what do you mean by",
    "what is meant by",
    "what do you understand by",
    "what do we understand by",
    "what can you understand by",
    "what is your understanding of",
    "what do you know about",
    "what does mean",
    "can you define",
    "could you define",
    "define",
    "can you explain",
    "could you explain",
    "explain",
    "describe",
    "tell me",
    "tell me about",
    "give me an overview of",
    "briefly explain",
}

_TECHNICAL_DEFINITION_PATTERN = re.compile(
    r"\b(?:ai|artificial intelligence|machine learning|deep learning|llm|rag|api|rest|fastapi|"
    r"python|java(?!script)|javascript|typescript|react|node|sql|nosql|database|algorithm|"
    r"data structure|array|string|tree|graph|stack|queue|hash|sorting|search|binary search|"
    r"architecture|system design|backend|frontend|cloud|docker|kubernetes|authentication|"
    r"authorization|polymorphism|encapsulation|abstraction|inheritance|dependency injection|"
    r"normalization|cache|caching|thread|process|async|microservice|http|tcp|oop)\b|c\+\+|c#",
    flags=re.IGNORECASE,
)


def looks_like_definition_question(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(question or "").strip().lower())
    normalized = re.sub(r"^(?:uh|um|okay|ok|so|yeah|alright|now|next)\s+", "", normalized)
    if not normalized or normalized in _INCOMPLETE_DEFINITION_PROMPTS:
        return False
    patterns = (
        r"^(?:what do you mean by|what is meant by|can you define|could you define|define|can you explain|could you explain|explain|describe|tell me about)\s+(.+)$",
        r"^(?:what do you understand by|what do we understand by|what can you understand by|what is your understanding of|what do you know about|give me an overview of|briefly explain)\s+(.+)$",
        r"^what is\s+(.+)$",
        r"^what does\s+(.+?)\s+mean$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        subject = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", match.group(1))
        if subject and subject not in {"please", "about"}:
            return True
    return False


def looks_like_coding_implementation_request(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(question or "").strip().lower())
    if not normalized:
        return False
    implementation_pattern = (
        r"\b(?:implement|code|write|solve|create|complete|build|optimize|convert|rewrite|fix|debug)\b"
    )
    coding_context_pattern = (
        r"\b(?:program|function|method|class|solution|algorithm|code|python|java(?!script)|javascript|typescript|"
        r"cpp|c sharp|binary search|merge sort|lru cache|array|string|tree|graph|leetcode|hackerrank)\b"
        r"|c\+\+|c#"
    )
    return bool(re.search(implementation_pattern, normalized) and re.search(coding_context_pattern, normalized))


def is_personal_rapport_question(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.lower().strip())
    if classify_personal_subtype(question):
        return True
    off_work_structure = re.search(
        r"\b(?:what do you do (?:for fun|outside (?:of )?work|in your (?:free|spare) time|on weekends?)|"
        r"how do you spend (?:your )?(?:free time|spare time|weekends?)|"
        r"what .+ matters? to you outside (?:of )?work)\b",
        normalized,
    )
    if off_work_structure:
        return True
    if not normalized or _PROFESSIONAL_DOMAIN_PATTERN.search(normalized):
        return False

    personal_structures = (
        r"\b(?:favorite|favourite)\b",
        r"\b(?:do|would) you prefer\b",
        r"\bwould you rather\b",
        r"\bif you (?:could|were|had)\b",
        r"\bwhat do you do (?:for fun|outside (?:of )?work|in your (?:free|spare) time|on weekends?)\b",
        r"\bhow do you spend (?:your )?(?:free time|spare time|weekends?)\b",
        r"\bare you (?:a|an) .+ person\b",
        r"\b(?:what|which)(?: kind| type)? of .+ do you (?:like|love|enjoy|prefer)\b",
        r"\b(?:what|which) .+ do you (?:like|love|enjoy)\b",
        r"\bwhat do you (?:like|love|enjoy)\b",
        r"\b(?:what|which|where|who)(?: .+)? would you (?:like|love|want)\b",
        r"\bwhat is your ideal\b",
        r"\bwho do you (?:admire|look up to)\b",
        r"\bwhat .+ matters? to you outside (?:of )?work\b",
        r"\btell me about your\b",
        r"\b(?:in|about) your (?:life|childhood|family|home|free time)\b",
    )
    return any(re.search(pattern, normalized) for pattern in personal_structures)


def classify_personal_subtype(question: str) -> str | None:
    normalized = re.sub(r"\s+", " ", question.lower().strip())
    if not normalized:
        return None

    subtype_patterns = (
        ("sensitive_personal", r"\b(?:religion|caste|politics|political|trauma|abuse|mental health|disease|disability|death|family problem|marital|sexual orientation|legal dispute)\b"),
        ("childhood_memory", r"\b(?:childhood memory|favourite childhood|favorite childhood|memory from childhood|childhood days|as a child|when you were a child|kind of child|memory you will never forget|unforgettable memory)\b"),
        ("childhood_background", r"\b(?:childhood|grew up|growing up|hometown|early life)\b"),
        ("difficult_phase", r"\b(?:difficult phase|difficult time|hard time|tough phase|low point|rough period|challenging phase|difficult period).*\b(?:life|personal|you)\b"),
        ("personal_failure", r"\b(?:personal failure|failure that changed|mistake that changed|failed in life|regret|misunderstood|did incorrectly)\b"),
        ("fear_overcome", r"\b(?:fear|afraid|scared|overcome)\b"),
        ("helping_someone", r"\b(?:helped someone|help someone|kind thing|something kind|support(?:ed)? someone|there for someone)\b"),
        ("personal_achievement", r"\b(?:something amazing|amazing you have done|most interesting thing|personal achievement|accomplished outside|unusual thing you did)\b"),
        ("proud_moment", r"\b(?:proud moment|most proud|proud of outside|made you proud)\b"),
        ("role_model_influence", r"\b(?:role model|influenced you|influence you|admire|look up to|inspired you)\b"),
        ("creative_imaginative", r"\b(?:superpower|fictional character|if your life were|movie title|could be any|imaginary|imagine)\b"),
        ("books_movies_music", r"\b(?:book|movie|film|music|song|album|fictional character|character)\b"),
        ("favourite_preferences", r"\b(?:favourite|favorite|colour|color|food|season|place|prefer|preference)\b"),
        ("hobbies_interests", r"\b(?:hobby|hobbies|free time|spare time|outside work|outside your professional life|weekend|unwind|for fun|enjoy doing)\b"),
        ("travel_memory", r"\b(?:journey|travel|trip|place you visited|vacation)\b"),
        ("friendship_family", r"\b(?:friend|friendship|family|parents|siblings|home)\b"),
        ("adaptability_change", r"\b(?:adapt|adapted|change|new place|adjust|adjusted|moved)\b"),
        ("personal_values", r"\b(?:values|important to you|principles|integrity|kindness|honesty)\b"),
        ("life_goal_dream", r"\b(?:dream|life goal|goal in life|future self|want from life)\b"),
        ("funny_embarrassing_memory", r"\b(?:funny|embarrassing|awkward)\b"),
        ("personality_self_awareness", r"\b(?:personality|what kind of person|unusual about you|interesting about yourself|makes you happy|habit|self-aware|describe yourself|ideal weekend)\b"),
        ("personal_challenge", r"\b(?:personal challenge|challenge in your life|challenging moment)\b"),
    )
    for subtype, pattern in subtype_patterns:
        if re.search(pattern, normalized):
            return subtype
    return None


def personal_question_allows_professional_context(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.lower().strip())
    return bool(
        re.search(
            r"\b(?:career|profession|professional|work|job|role|education|college|project|technical|coding|skill|company)\b",
            normalized,
        )
        and re.search(r"\b(?:influence|connect|shape|help|affect|because|lead|choose|growth)\b", normalized)
    )


def classify_question_by_rules(question: str) -> Category | None:
    normalized = question.lower().strip()
    if is_personal_rapport_question(question):
        return "personal"
    if looks_like_coding_implementation_request(question):
        return "technical"
    rules = (
        ("hr", (
            "tell me about yourself", "introduce yourself", "strength", "weakness",
            "interest", "motivat", "career goal", "personal background",
            "most interesting thing", "achievement are you most proud",
            "achievement you are most proud", "greatest achievement",
            "why should we hire you", "why do you want to work here",
            "why do you want to join", "why this company", "why this role",
        )),
        ("behavioral", (
            "tell me about a time", "describe a time", "give me an example",
            "situation where", "challenge you faced", "difficult technical problem you solved",
            "difficult bug", "conflict", "failure", "failed", "leadership", "teamwork",
            "under pressure", "deadline", "mistake", "problem you solved",
        )),
        ("technical", (
            "machine learning", "api", "fastapi", "python", "react", "database",
            "algorithm", "data structure", "architecture", "debug", "bug", "scaling",
            "backend", "frontend", "system design", "explain how",
            "difference between", "how does", "how did you use", "implement",
            "authentication", "authorization", "polymorphism", "encapsulation",
            "abstraction", "inheritance", "dependency injection", "normalization",
        )),
    )
    for category, keywords in rules:
        if any(keyword in normalized for keyword in keywords):
            return category
    if looks_like_definition_question(question):
        return "technical" if _TECHNICAL_DEFINITION_PATTERN.search(normalized) else "general"
    return None


class QuestionClassifier:
    def __init__(self) -> None:
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.use_zero_shot = settings.USE_ZERO_SHOT_CLASSIFIER
        self.zero_shot_classifier = None

        if self.use_zero_shot:
            self.logger.info("Zero-shot classifier enabled by USE_ZERO_SHOT_CLASSIFIER=true.")
            self._load_zero_shot()
        else:
            self.logger.info("Using lightweight rule-based classifier for MVP latency.")

    def _load_zero_shot(self) -> None:
        import torch
        from transformers import pipeline

        device = 0 if torch.cuda.is_available() else -1
        self.zero_shot_classifier = pipeline(
            task="zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=device,
        )

    def classify_question(self, question: str) -> Category:
        rule_category = classify_question_by_rules(question)
        if rule_category:
            return rule_category

        if self.use_zero_shot and self.zero_shot_classifier is not None:
            result = self.zero_shot_classifier(
                sequences=question,
                candidate_labels=["Personal", "HR", "Technical", "Behavioral", "General"],
                multi_label=False,
            )
            return result["labels"][0].lower()

        return "general"

    def should_process_as_question(self, transcript: str) -> tuple[bool, str, str]:
        normalized = self.normalize_transcript(transcript)
        if not normalized:
            return False, "empty transcript", normalized

        words = normalized.split()
        filler_phrases = {
            "okay",
            "okay yes",
            "ok",
            "ok yes",
            "yes",
            "yeah",
            "yep",
            "hmm",
            "hmm okay",
            "thank you",
            "thanks",
            "one second",
            "just a second",
            "hold on",
            "right",
            "sure",
        }
        if normalized in filler_phrases:
            return False, "filler phrase", normalized
        if normalized in _INCOMPLETE_DEFINITION_PROMPTS:
            return False, "incomplete definition prompt", normalized

        repeated_fillers = {"okay", "ok", "yes", "yeah", "hmm", "uh", "um", "thanks", "thank"}
        unique_words = {word for word in words}
        if unique_words and unique_words.issubset(repeated_fillers):
            return False, "filler phrase", normalized

        if looks_like_coding_implementation_request(normalized):
            return True, "matches coding implementation request", normalized

        question_starts = (
            "tell me",
            "tell me something about",
            "explain",
            "explain the concept of",
            "describe",
            "what is",
            "what are",
            "what do you understand by",
            "what do we understand by",
            "what can you understand by",
            "what is your understanding of",
            "what do you know about",
            "why",
            "how",
            "how do",
            "how would",
            "can you",
            "could you",
            "have you",
            "do you",
            "walk me through",
            "introduce yourself",
            "tell me about",
            "difference between",
            "talk about",
            "give me an overview of",
            "project",
            "experience",
            "what did you build",
        )
        explicit_prompts = (
            "tell me about yourself",
            "tell me something about",
            "tell me about your project",
            "explain your project",
            "explain the concept of",
            "what did you build",
            "what are your skills",
            "introduce yourself",
            "why should we hire you",
            "why do you want to join",
            "walk me through your resume",
        )
        has_question_phrase = normalized.startswith(question_starts) or any(
            phrase in normalized for phrase in explicit_prompts
        ) or looks_like_definition_question(normalized)

        if len(words) < 4 and not has_question_phrase:
            return False, "too short", normalized

        if "?" in transcript and len(words) >= 4:
            return True, "contains question mark", normalized
        if has_question_phrase:
            return True, "matches interview question phrase", normalized
        if "difference between" in normalized:
            return True, "matches interview question phrase", normalized

        return False, "does not look like an interview question", normalized

    def normalize_transcript(self, transcript: str) -> str:
        text = re.sub(r"\s+", " ", str(transcript or "").strip().lower())
        text = re.sub(r"[^\w\s?+#-]", "", text)
        return re.sub(r"\s+", " ", text).strip()
