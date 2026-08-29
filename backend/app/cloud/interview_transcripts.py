from dataclasses import dataclass
import json
import logging
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionValidationError,
    _normalize_uuid,
    _validate_supabase_url,
)
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings

logger = logging.getLogger("cloud_interview_transcripts")

SAFE_FAILURE_MESSAGE = "Supabase cloud interview transcript operation failed."
MAX_REQUEST_ID_CHARS = 120
MAX_SOURCE_CHARS = 40
MAX_CATEGORY_CHARS = 40
MAX_PROVIDER_CHARS = 80
MAX_MODEL_CHARS = 120
MAX_QUESTION_TEXT_CHARS = 4000
MAX_ANSWER_TEXT_CHARS = 24000
MAX_METADATA_KEYS = 16
MAX_METADATA_JSON_CHARS = 4000
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8


@dataclass(frozen=True)
class CloudInterviewTranscriptEntryRecord:
    id: str
    user_id: str
    session_id: str
    turn_index: int
    source: str | None
    question_text: str
    answer_text: str
    category: str | None
    provider: str | None
    model: str | None
    generation_ms: int | None
    created_at: str | None


@dataclass(frozen=True)
class InterviewTranscriptEntryListPage:
    items: list[CloudInterviewTranscriptEntryRecord]
    limit: int
    page: int


@dataclass(frozen=True)
class CreateInterviewTranscriptEntryResult:
    record: CloudInterviewTranscriptEntryRecord
    replayed: bool


def _normalize_text(value: Any, *, field: str, max_chars: int, required: bool = False) -> str | None:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not text:
        raise CloudInterviewSessionValidationError(f"{field} is required.")
    if len(text) > max_chars:
        raise CloudInterviewSessionValidationError(f"{field} is too long.")
    return text or None


def _normalize_request_id(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not REQUEST_ID_RE.fullmatch(raw):
        raise CloudInterviewSessionValidationError("request_id must be 1-120 supported ASCII characters.")
    return raw


def _normalize_generation_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError, OverflowError) as exc:
        raise CloudInterviewSessionValidationError("generation_ms is invalid.") from exc
    if numeric < 0 or numeric > 3_600_000:
        raise CloudInterviewSessionValidationError("generation_ms is invalid.")
    return numeric


def _sanitize_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[:240]
    if isinstance(value, list):
        return [_sanitize_metadata_value(item, depth=depth + 1) for item in value[:10]]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in list(value.items())[:MAX_METADATA_KEYS]:
            clean_key = str(key or "").strip()[:64]
            if not clean_key:
                continue
            sanitized[clean_key] = _sanitize_metadata_value(item, depth=depth + 1)
        return sanitized
    return str(value).strip()[:240]


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CloudInterviewSessionValidationError("metadata must be an object.")
    sanitized = _sanitize_metadata_value(value)
    if not isinstance(sanitized, dict):
        raise CloudInterviewSessionValidationError("metadata must be an object.")
    if len(sanitized) > MAX_METADATA_KEYS:
        raise CloudInterviewSessionValidationError("metadata is too large.")
    encoded = json.dumps(sanitized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_METADATA_JSON_CHARS:
        raise CloudInterviewSessionValidationError("metadata is too large.")
    return sanitized


def normalize_transcript_entry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "user_id" in payload:
        raise CloudInterviewSessionValidationError("user_id is server-derived and cannot be submitted.")
    return {
        "request_id": _normalize_request_id(payload.get("request_id")),
        "source": _normalize_text(payload.get("source"), field="source", max_chars=MAX_SOURCE_CHARS),
        "question_text": _normalize_text(
            payload.get("question_text"),
            field="question_text",
            max_chars=MAX_QUESTION_TEXT_CHARS,
            required=True,
        ),
        "answer_text": _normalize_text(
            payload.get("answer_text"),
            field="answer_text",
            max_chars=MAX_ANSWER_TEXT_CHARS,
            required=True,
        ),
        "category": _normalize_text(payload.get("category"), field="category", max_chars=MAX_CATEGORY_CHARS),
        "provider": _normalize_text(payload.get("provider"), field="provider", max_chars=MAX_PROVIDER_CHARS),
        "model": _normalize_text(payload.get("model"), field="model", max_chars=MAX_MODEL_CHARS),
        "generation_ms": _normalize_generation_ms(payload.get("generation_ms")),
        "metadata": _normalize_metadata(payload.get("metadata")),
    }


def _entry_from_payload(payload: dict[str, Any]) -> CloudInterviewTranscriptEntryRecord:
    return CloudInterviewTranscriptEntryRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        turn_index=int(payload.get("turn_index") or 0),
        source=str(payload.get("source")).strip() if payload.get("source") else None,
        question_text=str(payload.get("question_text") or ""),
        answer_text=str(payload.get("answer_text") or ""),
        category=str(payload.get("category")).strip() if payload.get("category") else None,
        provider=str(payload.get("provider")).strip() if payload.get("provider") else None,
        model=str(payload.get("model")).strip() if payload.get("model") else None,
        generation_ms=int(payload.get("generation_ms")) if payload.get("generation_ms") is not None else None,
        created_at=payload.get("created_at"),
    )


class SupabaseInterviewTranscriptClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            logger.error("Supabase interview transcript storage is misconfigured: service-role key matches anon key.")
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        supabase_url = _validate_supabase_url(settings.supabase_url)
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
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_error_payload(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _safe_error_code(self, response: requests.Response) -> str:
        code = str(self._safe_error_payload(response).get("code") or "").strip()
        return code[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", code) else "unavailable"

    def _safe_error_text(self, response: requests.Response, key: str) -> str:
        value = str(self._safe_error_payload(response).get(key) or "").strip()
        return re.sub(r"\s+", " ", value)[:240] if value else "unavailable"

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase interview transcript failure: target=%s operation=%s status=%s error_code=%s message=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
            self._safe_error_text(response, "message"),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> None:
        self._log_failure(target, operation, response)
        if response.status_code in {400, 404, 409} and self._safe_error_code(response) == "P0001":
            message = self._safe_error_text(response, "message")
            if "not found" in message:
                raise CloudInterviewSessionNotFoundError("Interview session was not found.")
            raise CloudInterviewSessionConflictError("Interview transcript state changed. Please retry.")
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> None:
        logger.error(
            "Supabase interview transcript failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc

    def create_transcript_entry(
        self,
        *,
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> CreateInterviewTranscriptEntryResult:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/create_interview_session_transcript_entry",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_session_id": session_id,
                    "p_request_id": payload["request_id"],
                    "p_source": payload["source"],
                    "p_question_text": payload["question_text"],
                    "p_answer_text": payload["answer_text"],
                    "p_category": payload["category"],
                    "p_provider": payload["provider"],
                    "p_model": payload["model"],
                    "p_generation_ms": payload["generation_ms"],
                    "p_metadata": payload["metadata"],
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_transcript_entries", "create", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_transcript_entries", "create", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        created = data[0]
        entry_id = str(created.get("transcript_entry_id") or "")
        if not entry_id:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return CreateInterviewTranscriptEntryResult(
            record=self.get_transcript_entry(user_id=user_id, session_id=session_id, entry_id=entry_id),
            replayed=bool(created.get("replayed")),
        )

    def get_transcript_entry(self, *, user_id: str, session_id: str, entry_id: str) -> CloudInterviewTranscriptEntryRecord:
        rows = self._select_entries(
            {
                "select": "*",
                "id": f"eq.{entry_id}",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            }
        )
        if not rows:
            raise CloudInterviewSessionNotFoundError("Interview transcript entry was not found.")
        return rows[0]

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int) -> list[CloudInterviewTranscriptEntryRecord]:
        offset = (page - 1) * limit
        return self._select_entries(
            {
                "select": "*",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "order": "turn_index.asc,created_at.asc,id.asc",
                "limit": str(limit),
                "offset": str(offset),
            }
        )

    def _select_entries(self, params: dict[str, str]) -> list[CloudInterviewTranscriptEntryRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_session_transcript_entries",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_transcript_entries", "select", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_transcript_entries", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_entry_from_payload(item) for item in data if isinstance(item, dict)]


class CloudInterviewTranscriptService:
    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client or SupabaseInterviewTranscriptClient()

    def create_transcript_entry(
        self,
        *,
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> CreateInterviewTranscriptEntryResult:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        return self._client.create_transcript_entry(
            user_id=user_id,
            session_id=normalized_session_id,
            payload=normalize_transcript_entry_payload(payload),
        )

    def list_transcript_entries(self, *, user_id: str, session_id: str, limit: int, page: int) -> InterviewTranscriptEntryListPage:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        if limit < 1 or limit > 200:
            raise CloudInterviewSessionValidationError("Limit must be between 1 and 200.")
        if page < 1 or page > 1000:
            raise CloudInterviewSessionValidationError("Page must be between 1 and 1000.")
        return InterviewTranscriptEntryListPage(
            items=self._client.list_transcript_entries(
                user_id=user_id,
                session_id=normalized_session_id,
                limit=limit,
                page=page,
            ),
            limit=limit,
            page=page,
        )

    def export_transcript(self, *, user_id: str, session_id: str, format: str) -> str:
        normalized_format = str(format or "").strip().lower()
        if normalized_format not in {"txt", "md"}:
            raise CloudInterviewSessionValidationError("format must be txt or md.")
        items: list[CloudInterviewTranscriptEntryRecord] = []
        page_number = 1
        while True:
            page = self.list_transcript_entries(user_id=user_id, session_id=session_id, limit=200, page=page_number)
            items.extend(page.items)
            if len(page.items) < page.limit:
                break
            page_number += 1
        if normalized_format == "md":
            parts = ["# Interview Transcript\n"]
            for entry in items:
                parts.extend(
                    [
                        f"## Turn {entry.turn_index}\n",
                        f"- Source: {entry.source or 'unknown'}\n",
                        f"- Category: {entry.category or 'unknown'}\n",
                        f"- Created: {entry.created_at or 'unknown'}\n",
                        "\n",
                        f"**Question**\n{entry.question_text}\n\n",
                        f"**Answer**\n{entry.answer_text}\n",
                    ]
                )
            return "\n".join(parts).strip() + "\n"

        lines = ["Interview Transcript", ""]
        for entry in items:
            lines.extend(
                [
                    f"Turn {entry.turn_index}",
                    f"Source: {entry.source or 'unknown'}",
                    f"Category: {entry.category or 'unknown'}",
                    f"Created: {entry.created_at or 'unknown'}",
                    f"Question: {entry.question_text}",
                    f"Answer: {entry.answer_text}",
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"
