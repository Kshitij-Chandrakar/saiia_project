import logging
from typing import Literal

from app.config import settings


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

    def classify_question(self, question: str) -> Literal["hr", "technical", "behavioral", "general"]:
        normalized = question.lower().strip()

        if self.use_zero_shot and self.zero_shot_classifier is not None:
            result = self.zero_shot_classifier(
                sequences=question,
                candidate_labels=["HR", "Technical", "Behavioral", "General"],
                multi_label=False,
            )
            return result["labels"][0].lower()

        behavioral_keywords = [
            "tell me about a time",
            "describe a time",
            "give me an example",
            "situation where",
            "challenge you faced",
            "difficult bug",
            "conflict",
            "deadline",
            "mistake",
            "problem you solved",
        ]
        technical_keywords = [
            "machine learning",
            "api",
            "fastapi",
            "python",
            "react",
            "database",
            "algorithm",
            "data structure",
            "architecture",
            "debug",
            "bug",
            "scaling",
            "backend",
            "frontend",
            "system design",
            "explain how",
            "what is",
            "difference between",
        ]
        hr_keywords = [
            "tell me about yourself",
            "why do you want",
            "why should we hire you",
            "your strengths",
            "your weakness",
            "introduce yourself",
            "career goal",
            "why this company",
            "why this role",
        ]

        if any(keyword in normalized for keyword in behavioral_keywords):
            return "behavioral"
        if any(keyword in normalized for keyword in technical_keywords):
            return "technical"
        if any(keyword in normalized for keyword in hr_keywords):
            return "hr"

        if normalized.startswith(("how ", "what ", "why ", "explain ", "walk me through ")):
            return "technical"
        if normalized.startswith(("tell me about", "tell me something about")):
            if any(keyword in normalized for keyword in ("machine learning", "project", "technology", "system", "api")):
                return "technical"
            return "hr"

        return "general"
