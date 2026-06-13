import logging
import re
import time
from typing import Any, Dict, Optional

import requests
from requests import RequestException, Timeout

from app.config import settings


class ProviderError(Exception):
    pass


class ProviderResult(Dict[str, Any]):
    pass


class GroqProvider:
    def __init__(self) -> None:
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.timeout = settings.GROQ_TIMEOUT_SECONDS
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, *, prompt: str) -> str:
        if not self.api_key:
            raise ProviderError("Groq API key is missing. Set GROQ_API_KEY to enable Groq generation.")

        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.4,
                    "max_tokens": 300,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are SAIIA, an interview answer assistant. Generate concise, natural answer "
                                "suggestions for the candidate. Use only the provided user profile. Do not invent "
                                "experience, projects, jobs, education, or skills. Keep the answer easy to speak aloud. "
                                "Do not write long essays. Match the answer style to the interview category."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Timeout as exc:
            raise ProviderError(
                "Groq timed out while generating an answer. Please try again."
            ) from exc
        except RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                raise ProviderError(
                    "Groq API key is invalid or missing. Please update GROQ_API_KEY and try again."
                ) from exc
            raise ProviderError(
                "Groq could not generate an answer right now. Please check your API key, internet connection, or Groq service status."
            ) from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq returned an unexpected response.") from exc


class OllamaProvider:
    def __init__(self) -> None:
        self.model = settings.OLLAMA_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    def generate(self, *, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Timeout as exc:
            raise ProviderError(
                "Ollama fallback timed out while generating an answer."
            ) from exc
        except RequestException as exc:
            raise ProviderError(
                "Ollama fallback is unavailable. Please start Ollama or disable fallback."
            ) from exc

        data = response.json()
        answer = data.get("response", "").strip()
        if not answer:
            raise ProviderError("Ollama fallback returned an empty answer.")
        return answer


class AnswerGenerator:
    def __init__(self, include_context: bool = True) -> None:
        self.include_context = include_context
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.groq_provider = GroqProvider()
        self.ollama_provider = OllamaProvider()

    def generate_answer(
        self,
        question: str,
        question_type: str,
        profile: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        prompt = self._build_prompt(question, question_type, profile)
        configured_provider = settings.LLM_PROVIDER

        if configured_provider == "groq":
            return self._generate_with_groq_then_optional_ollama(prompt)
        if configured_provider == "ollama":
            return self._generate_with_ollama(prompt, fallback_used=False)

        raise ProviderError(
            f"Unsupported LLM provider '{configured_provider}'. Use LLM_PROVIDER=groq or LLM_PROVIDER=ollama."
        )

    def _generate_with_groq_then_optional_ollama(self, prompt: str) -> ProviderResult:
        try:
            return self._generate_with_groq(prompt)
        except ProviderError as groq_error:
            self.logger.warning("Groq generation failed: %s", groq_error)
            if not settings.ENABLE_OLLAMA_FALLBACK:
                raise groq_error

            try:
                return self._generate_with_ollama(prompt, fallback_used=True)
            except ProviderError as ollama_error:
                self.logger.warning("Ollama fallback failed: %s", ollama_error)
                raise ProviderError(
                    f"{groq_error} Ollama fallback also failed: {ollama_error}"
                ) from ollama_error

    def _generate_with_groq(self, prompt: str) -> ProviderResult:
        started = time.perf_counter()
        raw_answer = self.groq_provider.generate(prompt=prompt)
        answer = self._clean_answer(raw_answer)
        return ProviderResult(
            answer=answer,
            provider="groq",
            model=self.groq_provider.model,
            fallback_used=False,
            error=None,
            generation_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def _generate_with_ollama(self, prompt: str, fallback_used: bool) -> ProviderResult:
        started = time.perf_counter()
        raw_answer = self.ollama_provider.generate(prompt=prompt)
        answer = self._clean_answer(raw_answer)
        return ProviderResult(
            answer=answer,
            provider="ollama",
            model=self.ollama_provider.model,
            fallback_used=fallback_used,
            error=None,
            generation_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def _build_prompt(
        self,
        question: str,
        question_type: str,
        profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        qt = question_type.lower().strip()
        parts = [
            "Interview category: " + qt.upper(),
            "You are generating text for a live interview overlay.",
            "Return only the final answer content.",
            "Do not include any introduction, label, explanation, or meta-commentary.",
            "Do not say phrases like 'Here's a possible answer', 'Alternatively', 'Here are bullets', or 'You can say'.",
            "Use only the user profile provided below.",
            "Do not invent fake experience, projects, jobs, education, or skills.",
            "Keep the answer concise, natural, and easy to speak aloud.",
        ]

        if qt == "hr":
            parts.append("Format: one short confident professional paragraph.")
        elif qt == "technical":
            parts.append("Format: either one short paragraph or 3 short bullets.")
            parts.append("Style: direct and technically accurate.")
        elif qt == "behavioral":
            parts.append("Format: compact STAR answer in one short paragraph.")
            parts.append("Style: situation, task, action, and result, but keep it concise.")
        else:
            parts.append("Format: one short natural paragraph.")

        if self.include_context and profile:
            profile_lines = []
            if profile.get("resume"):
                resume = str(profile["resume"]).strip()
                profile_lines.append(f"Resume/background: {resume[:500]}{'...' if len(resume) > 500 else ''}")
            if profile.get("role"):
                profile_lines.append(f"Target role: {profile['role']}")
            if profile.get("company"):
                profile_lines.append(f"Company: {profile['company']}")
            if profile.get("skills"):
                profile_lines.append(f"Skills: {profile['skills']}")
            if profile.get("experience"):
                profile_lines.append(f"Experience/projects: {profile['experience']}")
            if profile.get("projects"):
                profile_lines.append(f"Projects: {profile['projects']}")

            if profile_lines:
                parts.append("")
                parts.append("User profile:")
                parts.extend(profile_lines)

        parts.append("")
        parts.append(f"Question: {question.strip()}")
        parts.append("Final rule: output only the answer that should appear in the overlay.")

        return "\n".join(parts)

    def _clean_answer(self, answer: str) -> str:
        cleaned = answer.strip()
        meta_patterns = [
            r"^\s*here(?:'s| is)\s+(?:a\s+)?possible answer:?\s*",
            r"^\s*here(?:'s| is)\s+(?:a\s+)?concise answer:?\s*",
            r"^\s*alternatively[:,]?\s*",
            r"^\s*you can say:?\s*",
            r"^\s*possible answer:?\s*",
            r"^\s*answer:?\s*",
            r"^\s*here(?:'s| is)\s+(?:3|three|3 to 6|three to six)\s+(?:short\s+)?bullets:?\s*",
            r"^\s*here(?:'s| is)\s+(?:a\s+)?short answer:?\s*",
        ]

        for pattern in meta_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(
            r"\n\s*(alternatively|or, alternatively|another option)[:\s].*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned
