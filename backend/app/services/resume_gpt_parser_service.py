import json
import logging
import re
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
)

from app.config import settings
from app.nlp.answer_generator import ProviderError
from app.services.resume_service import ResumeService

logger = logging.getLogger("resume_gpt_parser_service")

GPT_PROFILE_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "current_title",
    "target_role",
    "professional_summary",
    "education",
    "degree",
    "branch",
    "college",
    "college_university",
    "university",
    "graduation_year",
    "top_skills",
    "technical_skills",
    "soft_skills",
    "tools_frameworks",
    "projects",
    "experience",
    "work_experience",
    "certifications",
    "achievements",
    "extraction_confidence",
    "missing_fields",
    "manual_review_required",
    "manual_review_message",
)

LIST_FIELDS = {"missing_fields"}
COMMA_SPACED_FIELDS = {
    "projects",
    "achievements",
    "certifications",
    "top_skills",
    "technical_skills",
    "soft_skills",
    "tools_frameworks",
}
ACHIEVEMENT_SECTION_RE = re.compile(
    r"(?im)^\s*(achievements?|awards?|honou?rs?|accomplishments?)\s*:?\s*$"
)
EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}")
TEXT_LIMITS = {
    "professional_summary": 900,
    "education": 900,
    "projects": 3000,
    "experience": 3000,
    "work_experience": 3000,
    "achievements": 1800,
    "certifications": 1800,
    "technical_skills": 1200,
    "tools_frameworks": 1200,
    "top_skills": 900,
    "soft_skills": 900,
}
DEFAULT_TEXT_LIMIT = 280


class ResumeGptParserService:
    def __init__(self, *, resume_service: ResumeService | None = None, openai_client: Any | None = None) -> None:
        self._resume_service = resume_service or ResumeService()
        self._client = openai_client

    def is_configured(self) -> bool:
        return bool(settings.RESUME_GPT_PARSER_ENABLED and settings.OPENAI_API_KEY and settings.RESUME_GPT_MODEL)

    def extract_profile(self, resume_text: str) -> dict[str, Any]:
        if not self.is_configured():
            raise ProviderError(
                "GPT resume parser is not configured.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="missing_config",
            )

        bounded_text = str(resume_text or "")[: settings.RESUME_GPT_MAX_INPUT_CHARS]
        if not bounded_text.strip():
            raise ProviderError(
                "Resume text is empty.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="empty_resume_text",
            )

        try:
            response = self._openai_client().responses.create(
                model=settings.RESUME_GPT_MODEL,
                instructions=self._instructions(),
                input=self._input_text(bounded_text),
                text={"format": self._json_schema_format()},
                max_output_tokens=settings.RESUME_GPT_MAX_OUTPUT_TOKENS,
                reasoning={"effort": settings.RESUME_GPT_REASONING_EFFORT},
                store=False,
                timeout=settings.RESUME_GPT_TIMEOUT_SECONDS,
            )
        except (
            APIConnectionError,
            APIError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            PermissionDeniedError,
        ) as exc:
            self._raise_provider_error(exc)
        except Exception as exc:
            self._raise_provider_error(exc)

        parsed = self._parse_response(response)
        self._validate_payload_schema(parsed)
        sanitized = self._sanitize_payload(parsed)
        normalized = self._resume_service.normalize_profile_fields(sanitized, bounded_text)
        normalized["extraction_confidence"] = self._normalize_confidence(
            sanitized.get("extraction_confidence") or normalized.get("extraction_confidence")
        )
        normalized["manual_review_required"] = bool(
            sanitized.get("manual_review_required") or normalized.get("manual_review_required")
        )
        normalized["manual_review_message"] = str(
            sanitized.get("manual_review_message") or normalized.get("manual_review_message") or ""
        )[:300]
        normalized["target_role"] = sanitized.get("target_role", "")
        normalized["achievements"] = (
            sanitized.get("achievements", "") if self._has_explicit_achievements_section(bounded_text) else ""
        )
        self._clean_normalized_profile(normalized)
        normalized["raw_resume_text"] = bounded_text
        return normalized

    def _openai_client(self) -> Any:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.RESUME_GPT_TIMEOUT_SECONDS,
                max_retries=settings.RESUME_GPT_MAX_RETRIES,
            )
        return self._client

    def _raise_provider_error(self, exc: Exception) -> None:
        status_code = getattr(exc, "status_code", None)
        error_type = type(exc).__name__
        if isinstance(exc, AuthenticationError) or status_code == 401:
            error_type = "authentication_failed"
        elif isinstance(exc, PermissionDeniedError) or status_code == 403:
            error_type = "permission_denied"
        elif isinstance(exc, APITimeoutError):
            error_type = "timeout"
        elif isinstance(exc, BadRequestError):
            error_type = "invalid_request"
        elif isinstance(exc, APIConnectionError):
            error_type = "network_error"
        logger.warning(
            "GPT resume parser failed provider=openai model=%s status_code=%s error_type=%s",
            settings.RESUME_GPT_MODEL,
            status_code,
            error_type,
        )
        raise ProviderError(
            "GPT resume parser could not extract structured fields.",
            provider="openai",
            model=settings.RESUME_GPT_MODEL,
            status_code=status_code,
            error_type=error_type,
            error_message=error_type,
            phase="resume_gpt_extract",
        ) from exc

    def _parse_response(self, response: Any) -> dict[str, Any]:
        status = getattr(response, "status", None)
        if status is not None and status != "completed":
            raise ProviderError(
                "GPT resume parser returned an incomplete response.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="incomplete_response",
            )
        try:
            raw_content = str(getattr(response, "output_text", "") or "").strip()
        except Exception as exc:
            raise ProviderError(
                "GPT resume parser returned an invalid response.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="invalid_response",
            ) from exc
        if not raw_content:
            raise ProviderError(
                "GPT resume parser returned an empty response.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="empty_response",
            )
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "GPT resume parser returned invalid JSON.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="invalid_json",
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderError(
                "GPT resume parser returned an invalid schema.",
                provider="openai",
                model=settings.RESUME_GPT_MODEL,
                phase="resume_gpt_extract",
                error_type="invalid_schema",
            )
        return parsed

    def _validate_payload_schema(self, payload: dict[str, Any]) -> None:
        for field in GPT_PROFILE_FIELDS:
            if field not in payload:
                self._raise_invalid_schema()
            value = payload[field]
            if field == "missing_fields":
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    self._raise_invalid_schema()
                continue
            if field == "manual_review_required":
                if not isinstance(value, bool):
                    self._raise_invalid_schema()
                continue
            if not isinstance(value, str):
                self._raise_invalid_schema()

    def _raise_invalid_schema(self) -> None:
        raise ProviderError(
            "GPT resume parser returned an invalid schema.",
            provider="openai",
            model=settings.RESUME_GPT_MODEL,
            phase="resume_gpt_extract",
            error_type="invalid_schema",
        )

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for field in GPT_PROFILE_FIELDS:
            raw_value = payload.get(field, [] if field in LIST_FIELDS else "")
            if field in LIST_FIELDS:
                sanitized[field] = self._sanitize_list(raw_value)
            elif isinstance(raw_value, list):
                sanitized[field] = "\n".join(self._sanitize_list(raw_value))[: self._field_limit(field)]
            else:
                sanitized[field] = self._clean_extracted_text(str(raw_value or ""), field=field)[: self._field_limit(field)]
        sanitized["extraction_confidence"] = self._normalize_confidence(sanitized.get("extraction_confidence"))
        sanitized["manual_review_required"] = bool(payload.get("manual_review_required"))
        return sanitized

    def _clean_normalized_profile(self, profile: dict[str, Any]) -> None:
        for field, value in list(profile.items()):
            if isinstance(value, str):
                profile[field] = self._clean_extracted_text(value, field=field)

    def _sanitize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            value = [value] if value else []
        cleaned = []
        for item in value:
            text = str(item or "").strip()
            if text:
                cleaned.append(self._clean_extracted_text(text)[:180])
            if len(cleaned) >= 30:
                break
        return cleaned

    def _field_limit(self, field: str) -> int:
        return TEXT_LIMITS.get(field, DEFAULT_TEXT_LIMIT)

    def _normalize_confidence(self, value: Any) -> str:
        confidence = str(value or "").strip().lower()
        return confidence if confidence in {"high", "medium", "low"} else "medium"

    def _clean_extracted_text(self, value: str, *, field: str = "") -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        text = self._strip_markdown_link(text)
        if field == "email":
            text = self._clean_email_field(text)
        elif field == "phone":
            text = self._clean_phone_field(text)

        text = re.sub(
            r"\b([A-Za-z0-9]{1,5})\s+-\s+([A-Z][a-z]+|[a-z][A-Za-z0-9]*)\b",
            r"\1-\2",
            text,
        )
        text = re.sub(
            r"\b([A-Za-z0-9]+)\s+-\s+([a-z][A-Za-z0-9]*)\b",
            r"\1-\2",
            text,
        )
        if field in COMMA_SPACED_FIELDS:
            text = "\n".join(
                re.sub(r"\s*,\s*", ", ", line).strip(" ,")
                for line in text.splitlines()
            )
        return text

    def _strip_markdown_link(self, value: str) -> str:
        return re.sub(r"\[([^\]]+)\]\((?:mailto:|tel:)?[^)]*\)", r"\1", value)

    def _clean_email_field(self, value: str) -> str:
        text = re.sub(r"(?i)\bmailto:", "", value).strip()
        match = EMAIL_RE.search(text)
        return match.group(0) if match else text

    def _clean_phone_field(self, value: str) -> str:
        return re.sub(r"(?i)\btel:", "", value).strip()

    def _has_explicit_achievements_section(self, resume_text: str) -> bool:
        return bool(ACHIEVEMENT_SECTION_RE.search(resume_text or ""))

    def _instructions(self) -> str:
        return (
            "You extract structured candidate profile fields from resume text for SAIIA. "
            "Return JSON only. Do not guess or invent facts. If a field is not clearly present, return an empty string. "
            "Keep contact/header/link text out of professional_summary. "
            "Leave target_role empty unless the resume explicitly states a target role, objective, or applied role. "
            "Achievements must only come from an explicit Achievements, Awards, Honors, or Accomplishments section; "
            "do not copy vocational training, internships, projects, education, or summary text into achievements. "
            "Preserve uncertainty and status words from the resume: planning, currently learning, exploring, and "
            "developing must not be rewritten as completed implementation or production work. "
            "professional_summary should summarize the candidate's real profile, experience, skills, and projects. "
            "Use concise strings for prose fields and comma-separated strings for skill lists."
        )

    def _input_text(self, resume_text: str) -> str:
        return (
            "Extract these JSON fields exactly: "
            f"{', '.join(GPT_PROFILE_FIELDS)}.\n"
            "Rules: email and phone must come only from explicit contact details; education must include degree, branch, "
            "college/university, and graduation year when present; experience must contain only jobs/internships; "
            "target_role must be empty unless the resume explicitly states an objective, target role, or applied role; "
            "achievements must be empty unless an explicit Achievements/Awards/Honors section exists; "
            "do not duplicate vocational training, internships, projects, education, or summary lines into achievements; "
            "preserve planned/in-progress wording instead of upgrading it to completed work; "
            "projects, achievements, and certifications must stay separate; missing_fields is a list of absent important fields; "
            "manual_review_required is true when important fields are missing or confidence is low.\n\n"
            f"Resume text:\n{resume_text}"
        )

    def _json_schema_format(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        for field in GPT_PROFILE_FIELDS:
            if field == "missing_fields":
                properties[field] = {"type": "array", "items": {"type": "string"}}
            elif field == "manual_review_required":
                properties[field] = {"type": "boolean"}
            else:
                properties[field] = {"type": "string"}
        return {
            "type": "json_schema",
            "name": "saiia_resume_profile",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": list(GPT_PROFILE_FIELDS),
            },
        }
