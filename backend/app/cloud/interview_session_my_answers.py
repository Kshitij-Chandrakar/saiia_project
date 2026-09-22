from dataclasses import dataclass
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from app.cloud.interview_sessions import (
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionValidationError,
    _normalize_uuid,
    _validate_supabase_url,
)
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings

logger = logging.getLogger("cloud_interview_session_my_answers")

SAFE_FAILURE_MESSAGE = "Supabase cloud interview My Answers operation failed."
MIGRATION_FAILURE_MESSAGE = "My Answers database migration is not applied."
MAX_BODY_CHARS = 24000
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8


@dataclass(frozen=True)
class CloudInterviewMyAnswerRecord:
    id: str
    user_id: str
    session_id: str
    body: str
    position: int
    created_at: str | None


def _normalize_body(value: Any) -> str:
    body = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        raise CloudInterviewSessionValidationError("Answer body is required.")
    if len(body) > MAX_BODY_CHARS:
        raise CloudInterviewSessionValidationError("Answer body is too long.")
    return body


def _record_from_payload(payload: dict[str, Any]) -> CloudInterviewMyAnswerRecord:
    return CloudInterviewMyAnswerRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        body=str(payload.get("body") or ""),
        position=int(payload.get("position") or 0),
        created_at=str(payload.get("created_at")) if payload.get("created_at") else None,
    )


class SupabaseInterviewSessionMyAnswersClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        supabase_url = _validate_supabase_url(settings.supabase_url)
        self._rest_url = f"{supabase_url}/rest/v1"
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=SUPABASE_HTTP_POOL_SIZE, pool_maxsize=SUPABASE_HTTP_POOL_SIZE, pool_block=True)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._headers = {
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _raise(self, operation: str, response: requests.Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = str(payload.get("code") or "") if isinstance(payload, dict) else ""
        message = str(payload.get("message") or "unavailable") if isinstance(payload, dict) else "unavailable"
        logger.error("Supabase My Answers failure operation=%s status=%s error_code=%s message=%s", operation, response.status_code, code[:80], message[:240])
        if response.status_code in {400, 404} and code == "P0001":
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")
        if code in {"42P01", "42883", "PGRST202", "PGRST205"} or any(
            phrase in message.lower()
            for phrase in ("does not exist", "could not find the function", "schema cache")
        ):
            raise CloudInterviewSessionError(MIGRATION_FAILURE_MESSAGE)
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def list_answers(self, *, user_id: str, session_id: str) -> list[CloudInterviewMyAnswerRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_session_my_answers",
                headers=self._headers,
                params={"select": "id,user_id,session_id,body,position,created_at", "user_id": f"eq.{user_id}", "session_id": f"eq.{session_id}", "order": "position.asc,created_at.asc,id.asc"},
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc
        if response.status_code != 200:
            self._raise("list", response)
        payload = response.json()
        if not isinstance(payload, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_record_from_payload(item) for item in payload if isinstance(item, dict)]

    def create_answer(self, *, user_id: str, session_id: str, body: str) -> CloudInterviewMyAnswerRecord:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/create_interview_session_my_answer",
                headers={**self._headers, "Prefer": "return=representation"},
                json={"p_user_id": user_id, "p_session_id": session_id, "p_body": body},
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc
        if response.status_code != 200:
            self._raise("create", response)
        payload = response.json()
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return _record_from_payload(payload[0])
        if isinstance(payload, dict):
            return _record_from_payload(payload)
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)


class CloudInterviewMyAnswersService:
    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client or SupabaseInterviewSessionMyAnswersClient()

    def list_answers(self, *, user_id: str, session_id: str) -> list[CloudInterviewMyAnswerRecord]:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        return self._client.list_answers(user_id=user_id, session_id=normalized_session_id)

    def create_answer(self, *, user_id: str, session_id: str, body: Any) -> CloudInterviewMyAnswerRecord:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        return self._client.create_answer(
            user_id=user_id,
            session_id=normalized_session_id,
            body=_normalize_body(body),
        )
