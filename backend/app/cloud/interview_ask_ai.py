from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import re
import time
from typing import Any
from uuid import uuid4

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

from app.cloud.interview_notes import CloudInterviewNotesService
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
    _normalize_generation_ms,
    _normalize_metadata,
)
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.config import settings
from app.nlp.answer_generator import ProviderError

logger = logging.getLogger("cloud_interview_ask_ai")

SAFE_FAILURE_MESSAGE = "Supabase cloud Ask AI operation failed."
ASK_AI_FAILURE_MESSAGE = "Ask AI is temporarily unavailable."
MAX_QUESTION_CHARS = 2000
MAX_MESSAGE_TEXT_CHARS = 12000
MAX_PROVIDER_CHARS = 80
MAX_MODEL_CHARS = 120
MAX_REQUEST_ID_CHARS = 128
MAX_TRANSCRIPT_ENTRIES = 30
MAX_RECENT_MESSAGES = 12
MAX_ENTRY_QUESTION_CHARS = 500
MAX_ENTRY_ANSWER_CHARS = 1500
MAX_NOTES_CHARS = 4000
MAX_SESSION_FIELD_CHARS = 300
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8
OPENAI_REASONING_EFFORT_FALLBACK = "low"
OPENAI_SUPPORTED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh"}
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
MIN_PROCESSING_STALE_SECONDS = 60


@dataclass(frozen=True)
class CloudInterviewAskAIMessageRecord:
    id: str
    user_id: str
    session_id: str
    role: str
    message_text: str
    turn_index: int
    provider: str | None
    model: str | None
    generation_ms: int | None
    created_at: str | None


@dataclass(frozen=True)
class CloudInterviewAskAIRequestKeyRecord:
    id: str
    user_id: str
    session_id: str
    request_id: str
    status: str
    user_message_id: str | None
    assistant_message_id: str | None
    payload_hash: str | None
    error_code: str | None
    created_at: str | None
    updated_at: str | None
    claim_token: str | None = None


@dataclass(frozen=True)
class InterviewAskAIMessageListPage:
    items: list[CloudInterviewAskAIMessageRecord]
    limit: int
    page: int
    has_more: bool = False
    next_page: int | None = None


@dataclass(frozen=True)
class AskAIContextUsed:
    transcript_entry_count: int
    notes_used: bool
    recent_message_count: int


@dataclass(frozen=True)
class AskAIResult:
    user_message: CloudInterviewAskAIMessageRecord
    assistant_message: CloudInterviewAskAIMessageRecord
    answer_text: str
    provider: str | None
    model: str | None
    generation_ms: int | None
    context_used: AskAIContextUsed


def _normalize_text(value: Any, *, field: str, max_chars: int, required: bool = False) -> str | None:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not text:
        raise CloudInterviewSessionValidationError(f"{field} is required.")
    if len(text) > max_chars:
        raise CloudInterviewSessionValidationError(f"{field} is too long.")
    return text or None


def _normalize_readable_message_text(value: Any, *, field: str, max_chars: int, required: bool = False) -> str | None:
    text = _normalize_text(value, field=field, max_chars=max_chars, required=required)
    if text is None:
        return None
    text = html.unescape(text)
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>])", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "- ", text)
    text = re.sub(r"(?m)^\s*(\d+)\\?\.\s+", r"\1. ", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)", r"\1", text)
    if len(text) > max_chars:
        raise CloudInterviewSessionValidationError(f"{field} is too long.")
    text = text.strip()
    if required and not text:
        raise CloudInterviewSessionValidationError(f"{field} is required.")
    return text or None


def _normalize_request_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > MAX_REQUEST_ID_CHARS or not REQUEST_ID_RE.fullmatch(text):
        raise CloudInterviewSessionValidationError("request_id is invalid.")
    return text


def _payload_hash(*, question: str, include_notes: bool) -> str:
    return hashlib.sha256(
        json.dumps(
            {"question": question, "include_notes": bool(include_notes)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _processing_stale_before() -> datetime:
    seconds = max(float(settings.ASK_AI_TIMEOUT_SECONDS or 0) * 2, MIN_PROCESSING_STALE_SECONDS)
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _record_from_payload(payload: dict[str, Any]) -> CloudInterviewAskAIMessageRecord:
    return CloudInterviewAskAIMessageRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        role=str(payload.get("role") or ""),
        message_text=str(payload.get("message_text") or ""),
        turn_index=int(payload.get("turn_index") or 0),
        provider=str(payload.get("provider")).strip() if payload.get("provider") else None,
        model=str(payload.get("model")).strip() if payload.get("model") else None,
        generation_ms=int(payload.get("generation_ms")) if payload.get("generation_ms") is not None else None,
        created_at=payload.get("created_at"),
    )


def _request_key_from_payload(payload: dict[str, Any]) -> CloudInterviewAskAIRequestKeyRecord:
    return CloudInterviewAskAIRequestKeyRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        request_id=str(payload.get("request_id") or ""),
        status=str(payload.get("status") or ""),
        user_message_id=str(payload.get("user_message_id")).strip() if payload.get("user_message_id") else None,
        assistant_message_id=str(payload.get("assistant_message_id")).strip() if payload.get("assistant_message_id") else None,
        payload_hash=str(payload.get("payload_hash")).strip() if payload.get("payload_hash") else None,
        error_code=str(payload.get("error_code")).strip() if payload.get("error_code") else None,
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        claim_token=str(payload.get("claim_token")).strip() if payload.get("claim_token") else None,
    )


class SupabaseInterviewAskAIClient:
    def __init__(self) -> None:
        supabase_settings = get_supabase_settings().require_configured()
        if supabase_settings.service_role_key == supabase_settings.anon_key:
            logger.error("Supabase Ask AI storage is misconfigured: service-role key matches anon key.")
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
        return value[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", value) else "unavailable"

    def _safe_error_text(self, response: requests.Response) -> str:
        value = str(self._safe_error_payload(response).get("message") or "").strip()
        return re.sub(r"\s+", " ", value)[:240] if value else "unavailable"

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase Ask AI failure: target=%s operation=%s status=%s error_code=%s message=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
            self._safe_error_text(response),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> None:
        self._log_failure(target, operation, response)
        if response.status_code in {400, 404, 409} and self._safe_error_code(response) == "P0001":
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")
        if response.status_code in {400, 404, 409} and self._safe_error_code(response) == "P0002":
            raise CloudInterviewSessionConflictError("Ask AI request is no longer active.")
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> None:
        logger.error(
            "Supabase Ask AI failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc

    def claim_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        payload_hash: str,
    ) -> tuple[CloudInterviewAskAIRequestKeyRecord, bool]:
        try:
            response = self._session.post(
                f"{self._rest_url}/interview_session_ask_ai_request_keys",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "request_id": request_id,
                    "payload_hash": payload_hash,
                    "claim_token": str(uuid4()),
                    "status": "processing",
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_request_keys", "claim", exc)
        if response.status_code in {200, 201}:
            data = response.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return _request_key_from_payload(data[0]), True
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        if response.status_code == 409:
            return self.get_request_key(user_id=user_id, session_id=session_id, request_id=request_id), False
        self._raise_response("interview_session_ask_ai_request_keys", "claim", response)
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def get_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
    ) -> CloudInterviewAskAIRequestKeyRecord:
        rows = self._select_request_keys(
            {
                "select": "*",
                "user_id": f"eq.{user_id}",
                "session_id": f"eq.{session_id}",
                "request_id": f"eq.{request_id}",
                "limit": "1",
            }
        )
        if not rows:
            raise CloudInterviewSessionNotFoundError("Ask AI request was not found.")
        return rows[0]

    def complete_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        user_message_id: str,
        assistant_message_id: str,
    ) -> CloudInterviewAskAIRequestKeyRecord:
        return self._patch_request_key(
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            payload={
                "status": "completed",
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "error_code": None,
            },
        )

    def fail_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        claim_token: str,
        error_code: str,
    ) -> CloudInterviewAskAIRequestKeyRecord | None:
        return self._patch_request_key(
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            payload={
                "status": "failed",
                "error_code": error_code[:80],
            },
            filters={
                "status": "eq.processing",
                "claim_token": f"eq.{claim_token}",
            },
            allow_empty=True,
        )

    def reclaim_stale_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        payload_hash: str,
        stale_before: datetime,
    ) -> tuple[CloudInterviewAskAIRequestKeyRecord | None, bool]:
        try:
            response = self._session.patch(
                f"{self._rest_url}/interview_session_ask_ai_request_keys",
                headers={**self._headers, "Prefer": "return=representation"},
                params={
                    "user_id": f"eq.{user_id}",
                    "session_id": f"eq.{session_id}",
                    "request_id": f"eq.{request_id}",
                    "payload_hash": f"eq.{payload_hash}",
                    "status": "eq.processing",
                    "updated_at": f"lt.{stale_before.isoformat().replace('+00:00', 'Z')}",
                },
                json={
                    "status": "processing",
                    "error_code": None,
                    "user_message_id": None,
                    "assistant_message_id": None,
                    "claim_token": str(uuid4()),
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_request_keys", "reclaim", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_request_keys", "reclaim", response)
        data = response.json()
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return _request_key_from_payload(data[0]), True
        return None, False

    def _patch_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        payload: dict[str, Any],
        filters: dict[str, str] | None = None,
        allow_empty: bool = False,
    ) -> CloudInterviewAskAIRequestKeyRecord | None:
        request_filters = {
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "request_id": f"eq.{request_id}",
        }
        if filters:
            request_filters.update(filters)
        try:
            response = self._session.patch(
                f"{self._rest_url}/interview_session_ask_ai_request_keys",
                headers={**self._headers, "Prefer": "return=representation"},
                params=request_filters,
                json=payload,
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_request_keys", "update", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_request_keys", "update", response)
        data = response.json()
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return _request_key_from_payload(data[0])
        if allow_empty:
            return None
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def create_message(
        self,
        *,
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> CloudInterviewAskAIMessageRecord:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/create_interview_session_ask_ai_message",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_session_id": session_id,
                    "p_role": payload["role"],
                    "p_message_text": payload["message_text"],
                    "p_provider": payload["provider"],
                    "p_model": payload["model"],
                    "p_generation_ms": payload["generation_ms"],
                    "p_metadata": payload["metadata"],
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_messages", "create", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_messages", "create", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        message_id = str(data[0].get("ask_ai_message_id") or "")
        if not message_id:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return self.get_message(user_id=user_id, session_id=session_id, message_id=message_id)

    def complete_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        claim_token: str,
        question: str,
        answer: str,
        provider: str | None,
        model: str | None,
        generation_ms: int | None,
        metadata: dict[str, Any],
    ) -> tuple[CloudInterviewAskAIMessageRecord, CloudInterviewAskAIMessageRecord]:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/complete_interview_session_ask_ai_turn",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_session_id": session_id,
                    "p_request_id": request_id,
                    "p_claim_token": claim_token,
                    "p_question": question,
                    "p_answer": answer,
                    "p_provider": provider,
                    "p_model": model,
                    "p_generation_ms": generation_ms,
                    "p_metadata": metadata,
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_turn", "complete", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_turn", "complete", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        user_message_id = str(data[0].get("user_message_id") or "")
        assistant_message_id = str(data[0].get("assistant_message_id") or "")
        if not user_message_id or not assistant_message_id:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return (
            self.get_message(user_id=user_id, session_id=session_id, message_id=user_message_id),
            self.get_message(user_id=user_id, session_id=session_id, message_id=assistant_message_id),
        )

    def get_message(self, *, user_id: str, session_id: str, message_id: str) -> CloudInterviewAskAIMessageRecord:
        rows = self._select_messages(
            {
                "select": "*",
                "id": f"eq.{message_id}",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            }
        )
        if not rows:
            raise CloudInterviewSessionNotFoundError("Ask AI message was not found.")
        return rows[0]

    def list_messages(self, *, user_id: str, session_id: str, limit: int, page: int) -> list[CloudInterviewAskAIMessageRecord]:
        offset = (page - 1) * limit
        return self.list_messages_window(user_id=user_id, session_id=session_id, limit=limit, offset=offset)

    def list_messages_window(self, *, user_id: str, session_id: str, limit: int, offset: int) -> list[CloudInterviewAskAIMessageRecord]:
        return self._select_messages(
            {
                "select": "*",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "order": "turn_index.asc,created_at.asc,id.asc",
                "limit": str(limit),
                "offset": str(offset),
            }
        )

    def list_recent_messages(self, *, user_id: str, session_id: str, limit: int) -> list[CloudInterviewAskAIMessageRecord]:
        rows = self._select_messages(
            {
                "select": "*",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "order": "turn_index.desc,created_at.desc,id.desc",
                "limit": str(limit),
            }
        )
        return list(reversed(rows))

    def _select_messages(self, params: dict[str, str]) -> list[CloudInterviewAskAIMessageRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_session_ask_ai_messages",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_messages", "select", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_messages", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_record_from_payload(item) for item in data if isinstance(item, dict)]

    def _select_request_keys(self, params: dict[str, str]) -> list[CloudInterviewAskAIRequestKeyRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_session_ask_ai_request_keys",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_session_ask_ai_request_keys", "select", exc)
        if response.status_code != 200:
            self._raise_response("interview_session_ask_ai_request_keys", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_request_key_from_payload(item) for item in data if isinstance(item, dict)]


class OpenAIInterviewAskAIGenerator:
    def __init__(self, *, openai_client: Any | None = None) -> None:
        self._client = openai_client

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY and settings.ASK_AI_MODEL)

    def generate(self, *, context: str, question: str) -> dict[str, Any]:
        if not self.is_configured():
            raise ProviderError(
                "Ask AI is not configured.",
                provider="openai",
                model=settings.ASK_AI_MODEL,
                phase="interview_ask_ai",
                error_type="missing_config",
            )
        started = time.perf_counter()
        try:
            response = self._openai_client().responses.create(
                model=settings.ASK_AI_MODEL,
                instructions=self._instructions(),
                input=f"{context}\n\nUser question:\n{question}",
                max_output_tokens=settings.ASK_AI_MAX_OUTPUT_TOKENS,
                reasoning={"effort": self._normalize_reasoning_effort(settings.ASK_AI_REASONING_EFFORT)},
                store=False,
                timeout=settings.ASK_AI_TIMEOUT_SECONDS,
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
            self._log_openai_failure(exc)
            raise ProviderError(
                ASK_AI_FAILURE_MESSAGE,
                provider="openai",
                model=settings.ASK_AI_MODEL,
                phase="interview_ask_ai",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
                error_message=self._safe_error_message(exc),
            ) from exc
        except Exception as exc:
            raise ProviderError(
                ASK_AI_FAILURE_MESSAGE,
                provider="openai",
                model=settings.ASK_AI_MODEL,
                phase="interview_ask_ai",
                error_type=type(exc).__name__,
                error_message=self._safe_error_message(exc),
            ) from exc
        try:
            answer = _normalize_readable_message_text(
                getattr(response, "output_text", ""),
                field="answer_text",
                max_chars=MAX_MESSAGE_TEXT_CHARS,
                required=True,
            )
        except CloudInterviewSessionValidationError as exc:
            raise ProviderError(
                ASK_AI_FAILURE_MESSAGE,
                provider="openai",
                model=settings.ASK_AI_MODEL,
                phase="interview_ask_ai",
                error_type="empty_response",
            ) from exc
        return {
            "answer_text": answer,
            "provider": "openai",
            "model": settings.ASK_AI_MODEL,
            "generation_ms": int(round((time.perf_counter() - started) * 1000)),
        }

    def _openai_client(self) -> Any:
        if self._client is None:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.ASK_AI_TIMEOUT_SECONDS)
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
            "Ask AI generation failed provider=%s model=%s error_type=%s error_code=%s error_param=%s message=%s",
            "openai",
            settings.ASK_AI_MODEL,
            type(exc).__name__,
            self._safe_error_code(exc),
            self._safe_error_param(exc),
            self._safe_error_message(exc),
        )

    def _instructions(self) -> str:
        return (
            "Answer as an interview coach using only the selected session transcript, saved AI notes, "
            "safe session metadata, and recent Ask AI messages provided. Do not use global memory. "
            "Mention when the transcript lacks evidence. Do not make hiring decisions. "
            "Give practical, concise feedback based on this transcript."
        )


class CloudInterviewAskAIService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        session_service: CloudInterviewSessionService | None = None,
        transcript_service: CloudInterviewTranscriptService | None = None,
        notes_service: CloudInterviewNotesService | None = None,
        generator: Any | None = None,
    ) -> None:
        self._client = client or SupabaseInterviewAskAIClient()
        self._session_service = session_service or CloudInterviewSessionService()
        self._transcript_service = transcript_service or CloudInterviewTranscriptService()
        self._notes_service = notes_service or CloudInterviewNotesService()
        self._generator = generator or OpenAIInterviewAskAIGenerator()

    def list_messages(self, *, user_id: str, session_id: str, limit: int, page: int) -> InterviewAskAIMessageListPage:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        if limit < 1 or limit > 100:
            raise CloudInterviewSessionValidationError("Limit must be between 1 and 100.")
        if page < 1 or page > 1000:
            raise CloudInterviewSessionValidationError("Page must be between 1 and 1000.")
        self._session_service.get_session(user_id=user_id, session_id=normalized_session_id)
        offset = (page - 1) * limit
        rows = self._client.list_messages_window(user_id=user_id, session_id=normalized_session_id, limit=limit + 1, offset=offset)
        return InterviewAskAIMessageListPage(
            items=rows[:limit],
            limit=limit,
            page=page,
            has_more=len(rows) > limit,
            next_page=page + 1 if len(rows) > limit else None,
        )

    def ask_ai(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        request_id: str | None = None,
        include_notes: bool = True,
        force_context_refresh: bool = False,
    ) -> AskAIResult:
        del force_context_refresh
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        normalized_question = _normalize_readable_message_text(question, field="question", max_chars=MAX_QUESTION_CHARS, required=True)
        if normalized_question is None:
            raise CloudInterviewSessionValidationError("question is required.")
        normalized_request_id = _normalize_request_id(request_id)
        normalized_request_id = normalized_request_id or f"server-{uuid4().hex}"
        payload_hash = _payload_hash(question=normalized_question, include_notes=include_notes)
        session = self._session_service.get_session(user_id=user_id, session_id=normalized_session_id)
        transcript_page = self._transcript_service.list_transcript_entries(
            user_id=user_id,
            session_id=normalized_session_id,
            limit=200,
            page=1,
        )
        transcript_entries = transcript_page.items[:MAX_TRANSCRIPT_ENTRIES]
        notes = None
        if include_notes:
            try:
                notes = self._notes_service.get_notes(user_id=user_id, session_id=normalized_session_id)
            except CloudInterviewSessionNotFoundError:
                notes = None
        recent_messages = self._client.list_recent_messages(
            user_id=user_id,
            session_id=normalized_session_id,
            limit=MAX_RECENT_MESSAGES,
        )
        if not transcript_entries and notes is None:
            raise CloudInterviewSessionConflictError("This session does not have transcript or AI notes context yet.")
        context_used = AskAIContextUsed(
            transcript_entry_count=len(transcript_entries),
            notes_used=notes is not None,
            recent_message_count=len(recent_messages),
        )
        request_key, request_claimed = self._client.claim_request_key(
            user_id=user_id,
            session_id=normalized_session_id,
            request_id=normalized_request_id,
            payload_hash=payload_hash,
        )
        if not request_claimed:
            replayed, request_key = self._replay_request_key(
                user_id=user_id,
                session_id=normalized_session_id,
                request_key=request_key,
                payload_hash=payload_hash,
                context_used=context_used,
            )
            if replayed is not None:
                return replayed
        request_key_failure_marked = False
        try:
            context = self.build_context_from_session(
                session=session,
                transcript_entries=transcript_entries,
                notes_markdown=notes.notes_markdown if notes else "",
                recent_messages=recent_messages,
            )
            generated = self._generator.generate(context=context, question=normalized_question)
            provider = _normalize_text(generated.get("provider"), field="provider", max_chars=MAX_PROVIDER_CHARS)
            model = _normalize_text(generated.get("model"), field="model", max_chars=MAX_MODEL_CHARS)
            generation_ms = _normalize_generation_ms(generated.get("generation_ms"))
            answer_text = _normalize_readable_message_text(
                generated.get("answer_text"),
                field="answer_text",
                max_chars=MAX_MESSAGE_TEXT_CHARS,
                required=True,
            )
            assert answer_text is not None
            metadata = _normalize_metadata({"request_id": normalized_request_id} if normalized_request_id else {})
            if not request_key.claim_token:
                raise CloudInterviewSessionConflictError("Ask AI request claim is unavailable.")
            try:
                user_message, assistant_message = self._client.complete_turn(
                    user_id=user_id,
                    session_id=normalized_session_id,
                    request_id=normalized_request_id,
                    claim_token=request_key.claim_token,
                    question=normalized_question,
                    answer=answer_text,
                    provider=provider,
                    model=model,
                    generation_ms=generation_ms,
                    metadata=metadata,
                )
            except Exception as completion_error:
                current_key = self._client.get_request_key(
                    user_id=user_id,
                    session_id=normalized_session_id,
                    request_id=normalized_request_id,
                )
                if current_key.status == "completed":
                    replayed, _ = self._replay_request_key(
                        user_id=user_id,
                        session_id=normalized_session_id,
                        request_key=current_key,
                        payload_hash=payload_hash,
                        context_used=context_used,
                    )
                    if replayed is not None:
                        return replayed
                if current_key.status == "processing":
                    self._mark_request_key_failed(
                        user_id=user_id,
                        session_id=normalized_session_id,
                        request_id=normalized_request_id,
                        claim_token=request_key.claim_token,
                        error_code=type(completion_error).__name__,
                    )
                    request_key_failure_marked = True
                raise
        except ProviderError as exc:
            if not request_key_failure_marked:
                self._mark_request_key_failed(
                    user_id=user_id,
                    session_id=normalized_session_id,
                    request_id=normalized_request_id,
                    claim_token=request_key.claim_token,
                    error_code=type(exc).__name__,
                )
            raise CloudInterviewSessionError(ASK_AI_FAILURE_MESSAGE) from exc
        except Exception as exc:
            if not request_key_failure_marked:
                self._mark_request_key_failed(
                    user_id=user_id,
                    session_id=normalized_session_id,
                    request_id=normalized_request_id,
                    claim_token=request_key.claim_token,
                    error_code=type(exc).__name__,
                )
            raise
        return AskAIResult(
            user_message=user_message,
            assistant_message=assistant_message,
            answer_text=answer_text,
            provider=provider,
            model=model,
            generation_ms=generation_ms,
            context_used=context_used,
        )

    def _replay_request_key(
        self,
        *,
        user_id: str,
        session_id: str,
        request_key: CloudInterviewAskAIRequestKeyRecord,
        payload_hash: str,
        context_used: AskAIContextUsed,
    ) -> tuple[AskAIResult | None, CloudInterviewAskAIRequestKeyRecord]:
        if request_key.payload_hash != payload_hash:
            raise CloudInterviewSessionConflictError("Ask AI request_id was already used with different input.")
        if request_key.status == "processing":
            reclaimed_key, reclaimed = self._client.reclaim_stale_request_key(
                user_id=user_id,
                session_id=session_id,
                request_id=request_key.request_id,
                payload_hash=payload_hash,
                stale_before=_processing_stale_before(),
            )
            if reclaimed and reclaimed_key is not None:
                return None, reclaimed_key
            raise CloudInterviewSessionConflictError("Ask AI request is already processing.")
        if request_key.status == "failed":
            raise CloudInterviewSessionConflictError("Ask AI request previously failed. Please retry with a new request_id.")
        if request_key.status != "completed":
            raise CloudInterviewSessionConflictError("Ask AI request is in an invalid replay state.")
        if not request_key.user_message_id or not request_key.assistant_message_id:
            raise CloudInterviewSessionConflictError("Ask AI request replay is incomplete.")
        user_message = self._client.get_message(user_id=user_id, session_id=session_id, message_id=request_key.user_message_id)
        assistant_message = self._client.get_message(user_id=user_id, session_id=session_id, message_id=request_key.assistant_message_id)
        return AskAIResult(
            user_message=user_message,
            assistant_message=assistant_message,
            answer_text=assistant_message.message_text,
            provider=assistant_message.provider,
            model=assistant_message.model,
            generation_ms=assistant_message.generation_ms,
            context_used=context_used,
        ), request_key

    def _mark_request_key_failed(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str | None,
        claim_token: str | None,
        error_code: str,
    ) -> None:
        if not request_id or not claim_token:
            return
        self._client.fail_request_key(
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            claim_token=claim_token,
            error_code=error_code,
        )

    def build_context_from_session(
        self,
        *,
        session: CloudInterviewSessionRecord,
        transcript_entries: list[CloudInterviewTranscriptEntryRecord],
        notes_markdown: str,
        recent_messages: list[CloudInterviewAskAIMessageRecord],
    ) -> str:
        max_input_chars = settings.ASK_AI_MAX_INPUT_CHARS
        parts = [
            "Session context:",
            f"Title: {_compact(session.title or 'Untitled session', MAX_SESSION_FIELD_CHARS)}",
            f"Target role: {_compact(session.target_role or 'Unknown', MAX_SESSION_FIELD_CHARS)}",
            f"Company: {_compact(session.company_name or 'Unknown', MAX_SESSION_FIELD_CHARS)}",
            f"Job preview: {_compact(session.job_description_preview or 'None', MAX_SESSION_FIELD_CHARS)}",
            "",
            "Transcript entries:",
        ]
        total_chars = sum(len(part) for part in parts)
        notes_text = _compact(notes_markdown, MAX_NOTES_CHARS)
        support_budget = min(
            max(0, max_input_chars - total_chars),
            max(1200, max_input_chars // 3),
        )
        transcript_budget = max(0, max_input_chars - total_chars - support_budget)
        transcript_chars = 0
        for entry in transcript_entries[:MAX_TRANSCRIPT_ENTRIES]:
            block = (
                f"Turn {entry.turn_index}\n"
                f"Question: {entry.question_text[:MAX_ENTRY_QUESTION_CHARS]}\n"
                f"Answer: {entry.answer_text[:MAX_ENTRY_ANSWER_CHARS]}\n"
            )
            if transcript_chars + len(block) > transcript_budget:
                break
            parts.extend(["", block])
            total_chars += len(block)
            transcript_chars += len(block)
        support_chars = 0
        if notes_text:
            notes_text = notes_text[: max(0, support_budget // 2 - 20)].rstrip()
        if notes_text and support_chars + len(notes_text) + 20 <= support_budget:
            parts.extend(["", "Saved AI notes:", notes_text])
            support_chars += len(notes_text) + 20
        if recent_messages:
            parts.extend(["", "Recent Ask AI messages:"])
            support_chars += 24
            recent_budget = max(0, support_budget - support_chars)
            recent_blocks = []
            for message in reversed(recent_messages[-MAX_RECENT_MESSAGES:]):
                block = f"{message.role}: {_compact(message.message_text, 800)}"
                if sum(len(item) for item in recent_blocks) + len(block) > recent_budget:
                    break
                recent_blocks.append(block)
            parts.extend(reversed(recent_blocks))
        return "\n".join(parts).strip()[:max_input_chars]


def _compact(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "..."
