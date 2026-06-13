# src/nlp/answer_generator.py

import logging
import requests
from typing import Optional, Dict, Any


class AnswerGenerator:
    """
    Generates interview answers using a local Ollama LLM via HTTP API.
    Supports both minimal and contextual prompts for relevance vs. performance.
    """

    def __init__(
        self,
        model_name: str = "llama3:8b",
        ollama_url: str = "http://localhost:11434",
        timeout: float = 10.0,
        include_context: bool = True,
    ) -> None:
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip('/')
        self.timeout = timeout
        self.include_context = include_context

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_answer(
        self,
        question: str,
        question_type: str,
        profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate an answer for the given interview question.

        :param question: Full text of the interview question.
        :param question_type: One of 'hr', 'technical', 'behavioral', 'general'.
        :param profile: Optional context (job_role, company, experience, skills).
        :returns: Generated answer text.
        """
        prompt = self._build_prompt(question, question_type, profile)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except Exception as e:
            self.logger.exception(f"Error generating answer: {e}")
            return "I'm sorry, I couldn't generate an answer at this time."

    def _build_prompt(
        self,
        question: str,
        qtype: str,
        profile: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build prompt based on question type and optional context.
        """
        qt = qtype.lower()
        base = f"Question: {question}\n"

        # Add context if desired
        if self.include_context and profile:
            context_parts = []
            for key in ["job_role", "company", "experience", "skills"]:
                if profile.get(key):
                    context_parts.append(f"{key.replace('_', ' ').title()}: {profile[key]}")
            if context_parts:
                base = "".join(["Context:\n" + "\n".join(context_parts) + "\n\n", base])

        # Templates
        if qt == 'hr':
            return base + "Answer briefly and professionally."
        elif qt == 'technical':
            return base + "Answer with clear technical details and examples."
        elif qt == 'behavioral':
            return base + "Use the STAR method (Situation, Task, Action, Result) in your answer."
        else:
            return base + "Provide a concise, polite response."
