from dataclasses import dataclass
import json
import logging
import re
import threading
import time
from typing import Any

import requests
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
from requests.adapters import HTTPAdapter

from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionRecord,
    CloudInterviewSessionService,
    CloudInterviewSessionValidationError,
    _normalize_uuid,
    _validate_supabase_url,
)
from app.cloud.interview_transcripts import (
    CloudInterviewTranscriptEntryRecord,
    CloudInterviewTranscriptService,
)
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.config import settings
from app.nlp.answer_generator import ProviderError

logger = logging.getLogger("cloud_interview_notes")

SAFE_FAILURE_MESSAGE = "Supabase cloud interview notes operation failed."
NOTES_GENERATION_FAILURE_MESSAGE = "AI notes generation is temporarily unavailable."
MAX_NOTES_MARKDOWN_CHARS = 24_000
MAX_SUMMARY_CHARS = 1_200
MAX_LIST_ITEMS = 12
MAX_LIST_ITEM_CHARS = 240
MAX_TRANSCRIPT_ENTRIES = 30
MAX_ENTRY_QUESTION_CHARS = 500
MAX_ENTRY_ANSWER_CHARS = 1_500
MAX_SESSION_CONTEXT_TOTAL_CHARS = 1_200
MAX_SESSION_TITLE_CHARS = 200
MAX_SESSION_ROLE_CHARS = 200
MAX_SESSION_COMPANY_CHARS = 200
MAX_SESSION_PREVIEW_CHARS = 480
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8
OPENAI_REASONING_EFFORT_FALLBACK = "low"
OPENAI_SUPPORTED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh"}
_NOTES_GENERATION_LOCKS: dict[str, threading.Lock] = {}
_NOTES_GENERATION_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class CloudInterviewNotesRecord:
    id: str
    user_id: str
    session_id: str
    status: str
    notes_markdown: str
    summary: str | None
    strengths: list[str]
    improvement_areas: list[str]
    technical_topics: list[str]
    key_questions: list[str]
    suggested_followups: list[str]
    provider: str | None
    model: str | None
    generation_ms: int | None
    transcript_entry_count: int
    generated_at: str | None
    created_at: str | None
    updated_at: str | None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            cleaned.append(text[:MAX_LIST_ITEM_CHARS])
        if len(cleaned) >= MAX_LIST_ITEMS:
            break
    return cleaned


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _truncate_text(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


def _acquire_generation_lock(session_id: str) -> Any | None:
    with _NOTES_GENERATION_LOCKS_GUARD:
        lock = _NOTES_GENERATION_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _NOTES_GENERATION_LOCKS[session_id] = lock
        if not lock.acquire(blocking=False):
            return None
        return lock


def _release_generation_lock(session_id: str, lock: Any) -> None:
    with _NOTES_GENERATION_LOCKS_GUARD:
        if _NOTES_GENERATION_LOCKS.get(session_id) is lock:
            _NOTES_GENERATION_LOCKS.pop(session_id, None)
        lock.release()


def _record_from_payload(payload: dict[str, Any]) -> CloudInterviewNotesRecord:
    return CloudInterviewNotesRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        status=str(payload.get("status") or ""),
        notes_markdown=str(payload.get("notes_markdown") or ""),
        summary=str(payload.get("summary")).strip() if payload.get("summary") else None,
        strengths=_normalize_string_list(payload.get("strengths")),
        improvement_areas=_normalize_string_list(payload.get("improvement_areas")),
        technical_topics=_normalize_string_list(payload.get("technical_topics")),
        key_questions=_normalize_string_list(payload.get("key_questions")),
        suggested_followups=_normalize_string_list(payload.get("suggested_followups")),
        provider=str(payload.get("provider")).strip() if payload.get("provider") else None,
        model=str(payload.get("model")).strip() if payload.get("model") else None,
        generation_ms=int(payload.get("generation_ms")) if payload.get("generation_ms") is not None else None,
        transcript_entry_count=max(0, int(payload.get("transcript_entry_count") or 0)),
        generated_at=payload.get("generated_at"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


class SupabaseInterviewNotesClient:
    def __init__(self) -> None:
        supabase_settings = get_supabase_settings().require_configured()
        if supabase_settings.service_role_key == supabase_settings.anon_key:
            logger.error("Supabase interview notes storage is misconfigured: service-role key matches anon key.")
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        supabase_url = _validate_supabase_url(supabase_settings.supabase_url)
        self._rest_url = f"{supabase_url}/rest/v1"
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=SUPABASE_HTTP_POOL_SIZE,
            pool_maxsize=SUPABASE_HTTP_POOL_SIZE,
            pool_block=True,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._headers = {
            "apikey": supabase_settings.service_role_key,
            "Authorization": f"Bearer {supabase_settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_error_payload(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _safe_error_code(self, response: requests.Response) -> str:
        value = str(self._safe_error_payload(response).get("code") or "").strip()
        return value[:80] if value else "unavailable"

    def _safe_error_text(self, response: requests.Response) -> str:
        value = str(self._safe_error_payload(response).get("message") or "").strip()
        return value[:240] if value else "unavailable"

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase interview notes failure: target=%s operation=%s status=%s error_code=%s message=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
            self._safe_error_text(response),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> None:
        self._log_failure(target, operation, response)
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> None:
        logger.error(
            "Supabase interview notes failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc

    def get_notes(self, *, user_id: str, session_id: str) -> CloudInterviewNotesRecord:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_session_ai_notes",
                headers=self._headers,
                params={
                    "select": "*",
                    "user_id": f"eq.{user_id}",
                    "session_id": f"eq.{session_id}",
                    "limit": "1",
                },
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ai_notes", "select", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ai_notes", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        if not data:
            raise CloudInterviewSessionNotFoundError("Interview session notes were not found.")
        item = data[0]
        if not isinstance(item, dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return _record_from_payload(item)

    def upsert_notes(self, *, user_id: str, session_id: str, payload: dict[str, Any]) -> CloudInterviewNotesRecord:
        body = {"user_id": user_id, "session_id": session_id, **payload}
        try:
            response = self._session.post(
                f"{self._rest_url}/interview_session_ai_notes",
                headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=representation"},
                params={"on_conflict": "session_id"},
                json=body,
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ai_notes", "upsert", exc)
        if response.status_code not in {200, 201}:
            self._raise_response("interview_session_ai_notes", "upsert", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return _record_from_payload(data[0])


class OpenAIInterviewNotesGenerator:
    def __init__(self, *, openai_client: Any | None = None) -> None:
        self._client = openai_client

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY and settings.AI_NOTES_MODEL)

    def generate(
        self,
        *,
        session: CloudInterviewSessionRecord,
        transcript_entries: list[CloudInterviewTranscriptEntryRecord],
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise ProviderError(
                "AI notes generation is not configured.",
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type="missing_config",
            )
        prompt = self._build_input(session=session, transcript_entries=transcript_entries)
        started = time.perf_counter()
        reasoning_effort = self._normalize_reasoning_effort(settings.AI_NOTES_REASONING_EFFORT)
        try:
            response = self._openai_client().responses.create(
                model=settings.AI_NOTES_MODEL,
                instructions=self._instructions(),
                input=prompt,
                text={"format": self._json_schema_format()},
                max_output_tokens=settings.AI_NOTES_MAX_OUTPUT_TOKENS,
                reasoning={"effort": reasoning_effort},
                store=False,
                timeout=settings.AI_NOTES_TIMEOUT_SECONDS,
            )
        except (
            APIConnectionError,
            APIError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            PermissionDeniedError,
        ) as exc:
            self._log_openai_failure(exc)
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
                error_message=self._safe_error_message(exc),
            ) from exc
        except BadRequestError as exc:
            self._log_openai_failure(exc)
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
                error_message=self._safe_error_message(exc),
            ) from exc
        except Exception as exc:
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type=type(exc).__name__,
                error_message=self._safe_error_message(exc),
            ) from exc

        raw_content = str(getattr(response, "output_text", "") or "").strip()
        if not raw_content:
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type="empty_response",
            )
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type="invalid_json",
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderError(
                NOTES_GENERATION_FAILURE_MESSAGE,
                provider="openai",
                model=settings.AI_NOTES_MODEL,
                phase="interview_notes_generate",
                error_type="invalid_schema",
            )

        result = _sanitize_generated_notes(parsed)
        result["provider"] = "openai"
        result["model"] = settings.AI_NOTES_MODEL
        result["generation_ms"] = int(round((time.perf_counter() - started) * 1000))
        return result

    def _openai_client(self) -> Any:
        if self._client is None:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.AI_NOTES_TIMEOUT_SECONDS)
        return self._client

    def _normalize_reasoning_effort(self, value: Any) -> str:
        effort = str(value or "").strip().lower()
        if effort == "minimal":
            return OPENAI_REASONING_EFFORT_FALLBACK
        if effort in OPENAI_SUPPORTED_REASONING_EFFORTS:
            return effort
        return OPENAI_REASONING_EFFORT_FALLBACK

    def _safe_error_payload(self, exc: Exception) -> dict[str, Any]:
        response = getattr(exc, "response", None)
        if response is None:
            return {}
        try:
            payload = response.json()
        except Exception:
            return {}
        if isinstance(payload, dict):
            error = payload.get("error")
            return error if isinstance(error, dict) else payload
        return {}

    def _safe_error_code(self, exc: Exception) -> str:
        value = str(self._safe_error_payload(exc).get("code") or "").strip()
        return value[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", value) else "unavailable"

    def _safe_error_param(self, exc: Exception) -> str:
        value = str(self._safe_error_payload(exc).get("param") or "").strip()
        return value[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", value) else "unavailable"

    def _safe_error_message(self, exc: Exception) -> str:
        value = str(self._safe_error_payload(exc).get("message") or str(exc) or "").strip()
        return re.sub(r"\s+", " ", value)[:240] if value else "unavailable"

    def _log_openai_failure(self, exc: Exception) -> None:
        logger.warning(
            "AI notes generation failed provider=%s model=%s error_type=%s error_code=%s error_param=%s message=%s",
            "openai",
            settings.AI_NOTES_MODEL,
            type(exc).__name__,
            self._safe_error_code(exc),
            self._safe_error_param(exc),
            self._safe_error_message(exc),
        )

    def _instructions(self) -> str:
        return (
            "You generate structured interview coaching notes from a stored transcript. "
            "Base every statement only on the transcript content and safe session context provided. "
            "Do not make hiring decisions. Do not claim certainty. "
            "Use careful language such as 'Based on this transcript'. Return JSON only."
        )

    def _build_input(
        self,
        *,
        session: CloudInterviewSessionRecord,
        transcript_entries: list[CloudInterviewTranscriptEntryRecord],
    ) -> str:
        parts = self._session_context_parts(session)
        parts.extend(["", "Transcript entries:"])
        total_chars = sum(len(part) for part in parts)
        for entry in transcript_entries[:MAX_TRANSCRIPT_ENTRIES]:
            question = entry.question_text[:MAX_ENTRY_QUESTION_CHARS]
            answer = entry.answer_text[:MAX_ENTRY_ANSWER_CHARS]
            block = (
                f"Turn {entry.turn_index}\n"
                f"Source: {entry.source or 'unknown'}\n"
                f"Question: {question}\n"
                f"Answer: {answer}\n"
            )
            if total_chars + len(block) > settings.AI_NOTES_MAX_INPUT_CHARS:
                break
            parts.extend(["", block])
            total_chars += len(block)
        return "\n".join(parts).strip()[: settings.AI_NOTES_MAX_INPUT_CHARS]

    def _session_context_parts(self, session: CloudInterviewSessionRecord) -> list[str]:
        budget = min(
            MAX_SESSION_CONTEXT_TOTAL_CHARS,
            max(200, settings.AI_NOTES_MAX_INPUT_CHARS // 2),
        )
        parts = ["Session context:"]
        remaining = max(0, budget - len(parts[0]))

        def add_line(label: str, value: Any, fallback: str, max_chars: int) -> None:
            nonlocal remaining
            if remaining <= 0:
                return
            prefix = f"{label}: "
            allowed = max(0, min(max_chars, remaining - len(prefix)))
            text = fallback if allowed <= 0 else (_truncate_text(value, allowed) or fallback)
            line = f"{prefix}{text}"
            if len(line) > remaining:
                trim_allowed = max(0, remaining - len(prefix))
                text = fallback if trim_allowed <= 0 else (_truncate_text(text, trim_allowed) or fallback)
                line = f"{prefix}{text}"
            parts.append(line)
            remaining -= len(line)

        add_line("Title", session.title, "Untitled session", MAX_SESSION_TITLE_CHARS)
        add_line("Target role", session.target_role, "Unknown", MAX_SESSION_ROLE_CHARS)
        add_line("Company", session.company_name, "Unknown", MAX_SESSION_COMPANY_CHARS)
        add_line("Job context preview", session.job_description_preview, "None", MAX_SESSION_PREVIEW_CHARS)
        return parts

    def _json_schema_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": "saiia_interview_notes",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "technical_topics": {"type": "array", "items": {"type": "string"}},
                    "key_questions": {"type": "array", "items": {"type": "string"}},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "improvement_areas": {"type": "array", "items": {"type": "string"}},
                    "suggested_followups": {"type": "array", "items": {"type": "string"}},
                    "overall_feedback": {"type": "string"},
                },
                "required": [
                    "summary",
                    "technical_topics",
                    "key_questions",
                    "strengths",
                    "improvement_areas",
                    "suggested_followups",
                    "overall_feedback",
                ],
            },
        }


def _sanitize_generated_notes(payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("summary") or "").strip()[:MAX_SUMMARY_CHARS]
    overall_feedback = str(payload.get("overall_feedback") or "").strip()[:2000]
    strengths = _normalize_string_list(payload.get("strengths"))
    improvement_areas = _normalize_string_list(payload.get("improvement_areas"))
    technical_topics = _normalize_string_list(payload.get("technical_topics"))
    key_questions = _normalize_string_list(payload.get("key_questions"))
    suggested_followups = _normalize_string_list(payload.get("suggested_followups"))
    notes_markdown = _build_notes_markdown(
        summary=summary,
        technical_topics=technical_topics,
        key_questions=key_questions,
        strengths=strengths,
        improvement_areas=improvement_areas,
        suggested_followups=suggested_followups,
        overall_feedback=overall_feedback,
    )
    return {
        "status": "ready",
        "notes_markdown": notes_markdown,
        "summary": summary or None,
        "strengths": strengths,
        "improvement_areas": improvement_areas,
        "technical_topics": technical_topics,
        "key_questions": key_questions,
        "suggested_followups": suggested_followups,
    }


def _build_notes_markdown(
    *,
    summary: str,
    technical_topics: list[str],
    key_questions: list[str],
    strengths: list[str],
    improvement_areas: list[str],
    suggested_followups: list[str],
    overall_feedback: str,
) -> str:
    sections = ["# Interview Notes", "", "## Summary", "", summary or "Based on this transcript, no summary was generated yet."]
    for title, items in (
        ("Topics Covered", technical_topics),
        ("Key Questions Asked", key_questions),
        ("Strong Points", strengths),
        ("Areas to Improve", improvement_areas),
        ("Suggested Follow-up Practice", suggested_followups),
    ):
        sections.extend(["", f"## {title}", ""])
        sections.extend([f"- {item}" for item in items] or ["- None noted."])
    sections.extend(["", "## Overall Feedback", "", overall_feedback or "Based on this transcript, keep practicing complete and specific answers."])
    markdown = "\n".join(sections).strip()
    return markdown[:MAX_NOTES_MARKDOWN_CHARS]


class CloudInterviewNotesService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        session_service: CloudInterviewSessionService | None = None,
        transcript_service: CloudInterviewTranscriptService | None = None,
        generator: Any | None = None,
    ) -> None:
        self._client = client or SupabaseInterviewNotesClient()
        self._session_service = session_service or CloudInterviewSessionService()
        self._transcript_service = transcript_service or CloudInterviewTranscriptService()
        self._generator = generator or OpenAIInterviewNotesGenerator()

    def get_notes(self, *, user_id: str, session_id: str) -> CloudInterviewNotesRecord:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        self._session_service.get_session(user_id=user_id, session_id=normalized_session_id)
        return self._client.get_notes(user_id=user_id, session_id=normalized_session_id)

    def generate_notes(
        self,
        *,
        user_id: str,
        session_id: str,
        force_regenerate: bool = False,
    ) -> CloudInterviewNotesRecord:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        lock = _acquire_generation_lock(normalized_session_id)
        if lock is None:
            raise CloudInterviewSessionConflictError("AI notes generation is already in progress.")
        try:
            if not force_regenerate:
                try:
                    return self.get_notes(user_id=user_id, session_id=normalized_session_id)
                except CloudInterviewSessionNotFoundError:
                    pass
            session = self._session_service.get_session(user_id=user_id, session_id=normalized_session_id)
            transcript_page = self._transcript_service.list_transcript_entries(
                user_id=user_id,
                session_id=normalized_session_id,
                limit=200,
                page=1,
            )
            transcript_entries = transcript_page.items[:MAX_TRANSCRIPT_ENTRIES]
            if not transcript_entries:
                raise CloudInterviewSessionConflictError("This session does not have transcript entries yet.")
            try:
                generated = self._generator.generate(session=session, transcript_entries=transcript_entries)
            except ProviderError as exc:
                raise CloudInterviewSessionError(NOTES_GENERATION_FAILURE_MESSAGE) from exc
            payload = {
                "status": generated.get("status") or "ready",
                "notes_markdown": str(generated.get("notes_markdown") or "").strip()[:MAX_NOTES_MARKDOWN_CHARS],
                "summary": str(generated.get("summary") or "").strip()[:MAX_SUMMARY_CHARS] or None,
                "strengths": _normalize_string_list(generated.get("strengths")),
                "improvement_areas": _normalize_string_list(generated.get("improvement_areas")),
                "technical_topics": _normalize_string_list(generated.get("technical_topics")),
                "key_questions": _normalize_string_list(generated.get("key_questions")),
                "suggested_followups": _normalize_string_list(generated.get("suggested_followups")),
                "provider": str(generated.get("provider") or "").strip()[:80] or None,
                "model": str(generated.get("model") or "").strip()[:120] or None,
                "generation_ms": int(generated.get("generation_ms") or 0),
                "transcript_entry_count": len(transcript_entries),
                "generated_at": _utc_now_iso(),
            }
            if not payload["notes_markdown"]:
                raise CloudInterviewSessionValidationError("Generated notes were empty.")
            return self._client.upsert_notes(user_id=user_id, session_id=session.id, payload=payload)
        finally:
            _release_generation_lock(normalized_session_id, lock)
