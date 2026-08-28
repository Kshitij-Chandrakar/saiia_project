from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import Any, NoReturn
from urllib.parse import urlparse
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter

from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings

logger = logging.getLogger("cloud_interview_sessions")

SAFE_FAILURE_MESSAGE = "Supabase cloud interview session operation failed."
MAX_TITLE_CHARS = 160
MAX_ROLE_CHARS = 160
MAX_COMPANY_CHARS = 160
MAX_JOB_DESCRIPTION_PREVIEW_CHARS = 240
MAX_IDEMPOTENCY_KEY_CHARS = 80
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8


class CloudInterviewSessionError(RuntimeError):
    """Raised when a cloud interview session operation cannot complete."""


class CloudInterviewSessionNotFoundError(CloudInterviewSessionError):
    """Raised when a session is missing or not owned by the current user."""


class CloudInterviewSessionConflictError(CloudInterviewSessionError):
    """Raised when idempotency or lifecycle state prevents mutation."""


class CloudInterviewSessionValidationError(CloudInterviewSessionError):
    """Raised when a request payload is invalid."""


@dataclass(frozen=True)
class CloudInterviewSessionRecord:
    id: str
    user_id: str
    selected_resume_id: str | None
    job_context_id: str | None
    title: str | None
    target_role: str | None
    company_name: str | None
    job_description_preview: str | None
    status: str
    started_at: str | None
    ended_at: str | None
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class InterviewSessionListPage:
    items: list[CloudInterviewSessionRecord]
    limit: int
    page: int


@dataclass(frozen=True)
class CreateInterviewSessionResult:
    record: CloudInterviewSessionRecord
    replayed: bool


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any, *, field: str, max_chars: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_chars:
        raise CloudInterviewSessionValidationError(f"{field} is too long.")
    return text


def _normalize_uuid(value: Any, *, field: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return str(UUID(raw))
    except ValueError as exc:
        raise CloudInterviewSessionValidationError(f"{field} is invalid.") from exc


def _preview_job_description(value: Any) -> str:
    preview = re.sub(r"\s+", " ", str(value or "")).strip()
    return preview[:MAX_JOB_DESCRIPTION_PREVIEW_CHARS]


def validate_idempotency_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise CloudInterviewSessionValidationError("Idempotency-Key must be 1-80 supported ASCII characters.")
    return key


def normalize_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "user_id" in payload:
        raise CloudInterviewSessionValidationError("user_id is server-derived and cannot be submitted.")
    title = _normalize_text(payload.get("title"), field="title", max_chars=MAX_TITLE_CHARS)
    target_role = _normalize_text(payload.get("target_role"), field="target_role", max_chars=MAX_ROLE_CHARS)
    company_name = _normalize_text(payload.get("company_name"), field="company_name", max_chars=MAX_COMPANY_CHARS)
    job_description_preview = _preview_job_description(payload.get("job_description"))
    if not any((title, target_role, company_name, job_description_preview)):
        raise CloudInterviewSessionValidationError("Please provide at least one session detail before starting.")
    return {
        "selected_resume_id": _normalize_uuid(payload.get("selected_resume_id"), field="selected_resume_id"),
        "job_context_id": _normalize_uuid(payload.get("job_context_id"), field="job_context_id"),
        "title": title or None,
        "target_role": target_role or None,
        "company_name": company_name or None,
        "job_description_preview": job_description_preview or None,
    }


def normalized_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_from_payload(payload: dict[str, Any]) -> CloudInterviewSessionRecord:
    return CloudInterviewSessionRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        selected_resume_id=str(payload.get("selected_resume_id")).strip() if payload.get("selected_resume_id") else None,
        job_context_id=str(payload.get("job_context_id")).strip() if payload.get("job_context_id") else None,
        title=str(payload.get("title")).strip() if payload.get("title") else None,
        target_role=str(payload.get("target_role")).strip() if payload.get("target_role") else None,
        company_name=str(payload.get("company_name")).strip() if payload.get("company_name") else None,
        job_description_preview=str(payload.get("job_description_preview")).strip()
        if payload.get("job_description_preview")
        else None,
        status=str(payload.get("status") or ""),
        started_at=payload.get("started_at"),
        ended_at=payload.get("ended_at"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def _validate_supabase_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme == "https" and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    raise SupabaseConfigurationError("Supabase URL must use HTTPS unless it targets localhost.")


class SupabaseInterviewSessionClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            logger.error("Supabase interview session storage is misconfigured: service-role key matches anon key.")
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

    def _safe_error_code(self, response: requests.Response) -> str:
        payload = self._safe_error_payload(response)
        code = str(payload.get("code") or "").strip()
        return code[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", code) else "unavailable"

    def _safe_error_payload(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _safe_error_text(self, response: requests.Response, key: str) -> str:
        value = str(self._safe_error_payload(response).get(key) or "").strip()
        if not value:
            return "unavailable"
        return re.sub(r"\s+", " ", value)[:240]

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase interview session failure: target=%s operation=%s status=%s error_code=%s message=%s details=%s hint=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
            self._safe_error_text(response, "message"),
            self._safe_error_text(response, "details"),
            self._safe_error_text(response, "hint"),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(target, operation, response)
        if response.status_code in {400, 409} and self._safe_error_code(response) == "P0001":
            raise CloudInterviewSessionConflictError("Interview session state changed. Please retry.")
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> NoReturn:
        logger.error(
            "Supabase interview session failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE) from exc

    def resume_owned_by_user(self, *, user_id: str, resume_id: str) -> bool:
        return self._row_exists("resumes", {"select": "id", "id": f"eq.{resume_id}", "user_id": f"eq.{user_id}", "limit": "1"})

    def job_context_owned_by_user(self, *, user_id: str, job_context_id: str) -> bool:
        return self._row_exists(
            "job_contexts",
            {"select": "id", "id": f"eq.{job_context_id}", "user_id": f"eq.{user_id}", "limit": "1"},
        )

    def list_sessions(self, *, user_id: str, limit: int, page: int) -> list[CloudInterviewSessionRecord]:
        offset = (page - 1) * limit
        return self._select_sessions(
            {
                "select": "*",
                "user_id": f"eq.{user_id}",
                "order": "started_at.desc,id.desc",
                "limit": str(limit),
                "offset": str(offset),
            }
        )

    def get_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        rows = self._select_sessions(
            {"select": "*", "id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "limit": "1"}
        )
        if not rows:
            raise CloudInterviewSessionNotFoundError("Interview session was not found.")
        return rows[0]

    def create_session(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> CreateInterviewSessionResult:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/create_interview_session_with_idempotency",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_request_hash": request_hash,
                    "p_selected_resume_id": payload["selected_resume_id"],
                    "p_job_context_id": payload["job_context_id"],
                    "p_title": payload["title"],
                    "p_target_role": payload["target_role"],
                    "p_company_name": payload["company_name"],
                    "p_job_description_preview": payload["job_description_preview"],
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_sessions", "create", exc)
        if response.status_code != 200:
            self._raise_response("interview_sessions", "create", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        created = data[0]
        session_id = str(created.get("interview_session_id") or "")
        if not session_id:
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return CreateInterviewSessionResult(
            record=self.get_session(user_id=user_id, session_id=session_id),
            replayed=bool(created.get("replayed")),
        )

    def end_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        ended_at = _utc_now_iso()
        try:
            response = self._session.patch(
                f"{self._rest_url}/interview_sessions",
                headers={**self._headers, "Prefer": "return=representation"},
                params={
                    "id": f"eq.{session_id}",
                    "user_id": f"eq.{user_id}",
                    "status": "eq.active",
                    "ended_at": "is.null",
                },
                json={"status": "ended", "ended_at": ended_at},
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_sessions", "end", exc)
        if response.status_code != 200:
            self._raise_response("interview_sessions", "end", response)
        data = response.json()
        if isinstance(data, list) and data:
            return _record_from_payload(data[0])
        existing = self.get_session(user_id=user_id, session_id=session_id)
        if existing.status in {"ended", "abandoned"}:
            return existing
        raise CloudInterviewSessionConflictError("Interview session state changed. Please retry.")

    def abandon_active_sessions(self, *, user_id: str) -> list[CloudInterviewSessionRecord]:
        ended_at = _utc_now_iso()
        try:
            response = self._session.patch(
                f"{self._rest_url}/interview_sessions",
                headers={**self._headers, "Prefer": "return=representation"},
                params={"user_id": f"eq.{user_id}", "status": "eq.active", "ended_at": "is.null"},
                json={"status": "abandoned", "ended_at": ended_at},
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_sessions", "abandon", exc)
        if response.status_code != 200:
            self._raise_response("interview_sessions", "abandon", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_record_from_payload(item) for item in data if isinstance(item, dict)]

    def _row_exists(self, table: str, params: dict[str, str]) -> bool:
        try:
            response = self._session.get(
                f"{self._rest_url}/{table}",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request(table, "exists", exc)
        if response.status_code != 200:
            self._raise_response(table, "exists", response)
        data = response.json()
        return bool(isinstance(data, list) and data)

    def _select_sessions(self, params: dict[str, str]) -> list[CloudInterviewSessionRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/interview_sessions",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("interview_sessions", "select", exc)
        if response.status_code != 200:
            self._raise_response("interview_sessions", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudInterviewSessionError(SAFE_FAILURE_MESSAGE)
        return [_record_from_payload(item) for item in data if isinstance(item, dict)]


class CloudInterviewSessionService:
    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client or SupabaseInterviewSessionClient()

    def list_sessions(self, *, user_id: str, limit: int, page: int) -> InterviewSessionListPage:
        if limit < 1 or limit > 50:
            raise CloudInterviewSessionValidationError("Limit must be between 1 and 50.")
        if page < 1 or page > 1000:
            raise CloudInterviewSessionValidationError("Page must be between 1 and 1000.")
        return InterviewSessionListPage(
            items=self._client.list_sessions(user_id=user_id, limit=limit, page=page),
            limit=limit,
            page=page,
        )

    def get_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        return self._client.get_session(user_id=user_id, session_id=normalized_session_id)

    def create_session(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> CreateInterviewSessionResult:
        validated_key = validate_idempotency_key(idempotency_key)
        normalized = normalize_session_payload(payload)
        if normalized["selected_resume_id"] and not self._client.resume_owned_by_user(
            user_id=user_id,
            resume_id=normalized["selected_resume_id"],
        ):
            raise CloudInterviewSessionNotFoundError("Selected resume was not found.")
        if normalized["job_context_id"] and not self._client.job_context_owned_by_user(
            user_id=user_id,
            job_context_id=normalized["job_context_id"],
        ):
            raise CloudInterviewSessionNotFoundError("Job context was not found.")
        return self._client.create_session(
            user_id=user_id,
            payload=normalized,
            idempotency_key=validated_key,
            request_hash=normalized_payload_hash(normalized),
        )

    def end_session(self, *, user_id: str, session_id: str) -> CloudInterviewSessionRecord:
        normalized_session_id = _normalize_uuid(session_id, field="session_id")
        if normalized_session_id is None:
            raise CloudInterviewSessionValidationError("session_id is invalid.")
        return self._client.end_session(user_id=user_id, session_id=normalized_session_id)

    def abandon_active_session_if_needed(self, *, user_id: str) -> list[CloudInterviewSessionRecord]:
        return self._client.abandon_active_sessions(user_id=user_id)
