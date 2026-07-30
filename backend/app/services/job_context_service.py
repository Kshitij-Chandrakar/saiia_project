import json
import time
from pathlib import Path
from typing import Any

import requests
from requests import RequestException, Timeout

from app.config import settings
from app.nlp.answer_generator import ProviderError
from app.services.resume_service import ResumeService


class JobContextError(Exception):
    """Raised when job context save, delete, or extraction fails."""


class JobContextService:
    def __init__(self) -> None:
        self.context_path = Path(__file__).resolve().parents[3] / "tmp" / "job_context.json"
        self._groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.resume_service = ResumeService()

    def get_context(self) -> dict[str, Any]:
        if not self.context_path.exists():
            return self._empty_context()

        try:
            payload = json.loads(self.context_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise JobContextError("Saved job context is unreadable. Please save it again.") from exc

        context = self._empty_context()
        for key in context:
            if key in payload:
                context[key] = payload[key]
        context["saved"] = any(
            str(context.get(field, "")).strip()
            for field in (
                "target_role",
                "company_name",
                "job_description",
                "required_skills",
                "responsibilities",
                "preferred_qualifications",
                "company_notes",
            )
        )
        return context

    def save_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        if not any(
            normalized[field]
            for field in (
                "target_role",
                "company_name",
                "job_description",
                "required_skills",
                "responsibilities",
                "preferred_qualifications",
                "company_notes",
            )
        ):
            raise JobContextError("Please provide at least one job context field before saving.")

        normalized["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        normalized["saved"] = True
        self.context_path.parent.mkdir(parents=True, exist_ok=True)
        self.context_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return normalized

    def delete_context(self) -> dict[str, Any]:
        if self.context_path.exists():
            self.context_path.unlink()
        return self._empty_context()

    def extract_text(self, *, filename: str, content: bytes) -> str:
        return self.resume_service.extract_text(filename=filename, content=content)

    def build_context_fields(self, raw_text: str) -> dict[str, str]:
        if not settings.GROQ_API_KEY:
            raise ProviderError("Groq API key is missing. Set GROQ_API_KEY to enable job context extraction.")

        prompt = (
            "Convert this job description or company context text into SAIIA job targeting fields.\n"
            "Return valid JSON only with these keys:\n"
            "target_role, company_name, job_description, required_skills, responsibilities, preferred_qualifications, company_notes\n"
            "Rules:\n"
            "- Each value must be a string.\n"
            "- `job_description` should be a concise 2-4 sentence summary.\n"
            "- `required_skills` should be a short comma-separated string.\n"
            "- `responsibilities` should be a concise summary.\n"
            "- `preferred_qualifications` should be concise and optional.\n"
            "- `company_notes` should be empty unless company-specific details are explicitly present.\n"
            "- Do not invent company details or requirements that are not present.\n"
            "- Use empty strings for missing information.\n\n"
            f"Job context text:\n{raw_text}"
        )

        try:
            response = requests.post(
                self._groq_url,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You extract structured job targeting context from job descriptions. "
                                "Return only valid JSON and never invent missing company or role facts."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=settings.GROQ_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Timeout as exc:
            raise ProviderError("Groq timed out while extracting job context. Please try again.") from exc
        except RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                raise ProviderError(
                    "Groq API key is invalid or missing. Please update GROQ_API_KEY and try again."
                ) from exc
            raise ProviderError(
                "Groq could not extract job context right now. Please check your API key, internet connection, or Groq service status."
            ) from exc

        data = response.json()
        raw_content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ProviderError("Groq returned an unexpected job context extraction response.") from exc

        normalized = {}
        for key in (
            "target_role",
            "company_name",
            "job_description",
            "required_skills",
            "responsibilities",
            "preferred_qualifications",
            "company_notes",
        ):
            value = parsed.get(key, "")
            if isinstance(value, list):
                value = ", ".join(str(item).strip() for item in value if str(item).strip())
            elif value is None:
                value = ""
            normalized[key] = str(value).strip()
        return normalized

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = self._empty_context()
        for key in context:
            if key in {"saved", "updated_at"}:
                continue
            context[key] = str(payload.get(key, "") or "").strip()
        return context

    def _empty_context(self) -> dict[str, Any]:
        return {
            "target_role": "",
            "company_name": "",
            "job_description": "",
            "required_skills": "",
            "responsibilities": "",
            "preferred_qualifications": "",
            "company_notes": "",
            "updated_at": None,
            "saved": False,
        }
