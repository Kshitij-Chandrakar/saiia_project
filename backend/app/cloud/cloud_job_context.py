from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import binascii
import hashlib
import json
import logging
import mimetypes
import re
import time
from pathlib import PurePath
from typing import Any, NoReturn
from urllib.parse import urlparse
from uuid import UUID, uuid4

import requests
from requests.adapters import HTTPAdapter

from app.cloud.cloud_resume import ALLOWED_MIME_TYPES, sanitize_resume_filename
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.nlp.answer_generator import ProviderError
from app.services.job_context_service import JobContextError, JobContextService
from app.services.resume_service import MAX_RESUME_FILE_BYTES, ResumeExtractionError

logger = logging.getLogger("cloud_job_context")

MAX_COMPANY_CHARS = 160
MAX_POSITION_CHARS = 160
MAX_JOB_DESCRIPTION_CHARS = 100_000
MAX_SENIORITY_CHARS = 80
MAX_LOCATION_CHARS = 160
MAX_EMPLOYMENT_TYPE_CHARS = 80
MAX_JOB_DESCRIPTION_PREVIEW_CHARS = 240
MAX_ARRAY_ITEMS = 50
MAX_ARRAY_ITEM_CHARS = 160
MAX_METADATA_VALUE_CHARS = 256
MAX_METADATA_BYTES = 2_048
MAX_JSON_BODY_BYTES = 128 * 1024
MAX_MULTIPART_BODY_BYTES = 6 * 1024 * 1024
MAX_EXTRACTED_JD_BYTES = 100_000
MAX_IDEMPOTENCY_KEY_CHARS = 80
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_TIMEOUT = 5
SUPABASE_MUTATION_TIMEOUT = 8
EXTRACTION_RECEIPT_TTL_SECONDS = 15 * 60
EXTRACTION_QUOTA_WINDOW_SECONDS = 60 * 60
EXTRACTION_QUOTA_MAX_CALLS = 10
PROVIDER_CIRCUIT_FAILURE_THRESHOLD = 3
PROVIDER_CIRCUIT_COOLDOWN_SECONDS = 60
SAFE_FAILURE_MESSAGE = "Supabase cloud job context operation failed."


class CloudJobContextError(RuntimeError):
    """Raised when a cloud job context operation cannot complete."""


class CloudJobContextNotFoundError(CloudJobContextError):
    """Raised when a context is missing or not owned by the current user."""


class CloudJobContextConflictError(CloudJobContextError):
    """Raised when an idempotency or activation conflict occurs."""


class CloudJobContextValidationError(CloudJobContextError):
    """Raised when a request payload is invalid."""


class CloudJobContextRateLimitError(CloudJobContextError):
    """Raised when extraction quota is exhausted."""


@dataclass(frozen=True)
class CloudJobContextRecord:
    id: str
    user_id: str
    company: str
    position: str
    job_description: str
    required_skills: list[str]
    responsibilities: list[str]
    seniority: str
    domain_keywords: list[str]
    location: str
    employment_type: str
    source_file_metadata: dict[str, Any]
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class JobContextListPage:
    items: list[CloudJobContextRecord]
    active_id: str | None
    limit: int
    next_cursor: str | None


@dataclass(frozen=True)
class CreateJobContextResult:
    record: CloudJobContextRecord
    replayed: bool
    activated: bool


@dataclass(frozen=True)
class DeleteJobContextResult:
    job_context_id: str
    deleted: bool
    active_id: str | None


@dataclass(frozen=True)
class CloudJobContextExtractResult:
    company: str
    position: str
    job_description: str
    job_description_summary: str
    required_skills: list[str]
    responsibilities: list[str]
    seniority: str
    domain_keywords: list[str]
    location: str
    employment_type: str
    source_file_metadata: dict[str, Any]
    extraction_receipt_id: str
    extracted_text_length: int


@dataclass
class ExtractionReceipt:
    user_id: str
    job_description_hash: str
    source_file_metadata: dict[str, Any]
    expires_at: float


def _normalize_text(value: Any, *, max_chars: int, field: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_chars:
        raise CloudJobContextValidationError(f"{field} is too long.")
    return text


def _normalize_array(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r",|\n|;", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raise CloudJobContextValidationError(f"{field} must be a list of strings.")

    items: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = str(raw_item or "").strip()
        if not item:
            continue
        if len(item) > MAX_ARRAY_ITEM_CHARS:
            raise CloudJobContextValidationError(f"{field} contains an item that is too long.")
        key = re.sub(r"\s+", " ", item).casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) > MAX_ARRAY_ITEMS:
            raise CloudJobContextValidationError(f"{field} contains too many items.")
    return items


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", str(key)):
            raise CloudJobContextValidationError("Source file metadata contains an unsupported key.")
        if isinstance(value, (dict, list)):
            raise CloudJobContextValidationError("Source file metadata contains an unsupported value.")
        text = str(value or "")[:MAX_METADATA_VALUE_CHARS]
        normalized[str(key)] = text
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(serialized) > MAX_METADATA_BYTES:
        raise CloudJobContextValidationError("Source file metadata is too large.")
    return normalized


def normalize_job_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "source_file_metadata" in payload:
        raise CloudJobContextValidationError("Source file metadata is server-derived and cannot be submitted.")

    normalized = {
        "company": _normalize_text(payload.get("company"), max_chars=MAX_COMPANY_CHARS, field="company"),
        "position": _normalize_text(payload.get("position"), max_chars=MAX_POSITION_CHARS, field="position"),
        "job_description": _normalize_text(
            payload.get("job_description"),
            max_chars=MAX_JOB_DESCRIPTION_CHARS,
            field="job_description",
        ),
        "required_skills": _normalize_array(payload.get("required_skills"), field="required_skills"),
        "responsibilities": _normalize_array(payload.get("responsibilities"), field="responsibilities"),
        "seniority": _normalize_text(payload.get("seniority"), max_chars=MAX_SENIORITY_CHARS, field="seniority"),
        "domain_keywords": _normalize_array(payload.get("domain_keywords"), field="domain_keywords"),
        "location": _normalize_text(payload.get("location"), max_chars=MAX_LOCATION_CHARS, field="location"),
        "employment_type": _normalize_text(
            payload.get("employment_type"),
            max_chars=MAX_EMPLOYMENT_TYPE_CHARS,
            field="employment_type",
        ),
        "activate": bool(payload.get("activate")),
        "extraction_receipt_id": str(payload.get("extraction_receipt_id") or "").strip(),
    }
    if not any(
        normalized[field]
        for field in (
            "company",
            "position",
            "job_description",
            "required_skills",
            "responsibilities",
            "seniority",
            "domain_keywords",
            "location",
            "employment_type",
        )
    ):
        raise CloudJobContextValidationError("Please provide at least one job context field before saving.")
    return normalized


def normalize_job_context_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "source_file_metadata" in payload:
        raise CloudJobContextValidationError("Source file metadata is server-derived and cannot be submitted.")
    field_specs: dict[str, tuple[int, str]] = {
        "company": (MAX_COMPANY_CHARS, "company"),
        "position": (MAX_POSITION_CHARS, "position"),
        "job_description": (MAX_JOB_DESCRIPTION_CHARS, "job_description"),
        "seniority": (MAX_SENIORITY_CHARS, "seniority"),
        "location": (MAX_LOCATION_CHARS, "location"),
        "employment_type": (MAX_EMPLOYMENT_TYPE_CHARS, "employment_type"),
    }
    normalized: dict[str, Any] = {}
    for key, (max_chars, field) in field_specs.items():
        if key in payload:
            normalized[key] = _normalize_text(payload.get(key), max_chars=max_chars, field=field)
    for key in ("required_skills", "responsibilities", "domain_keywords"):
        if key in payload:
            normalized[key] = _normalize_array(payload.get(key), field=key)
    if "extraction_receipt_id" in payload:
        normalized["extraction_receipt_id"] = str(payload.get("extraction_receipt_id") or "").strip()
    if not normalized:
        raise CloudJobContextValidationError("Please provide at least one job context field to update.")
    return normalized


def validate_idempotency_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise CloudJobContextValidationError("Idempotency-Key must be 1-80 supported ASCII characters.")
    return key


def normalized_payload_hash(payload: dict[str, Any], source_file_metadata: dict[str, Any]) -> str:
    safe_payload = {key: value for key, value in payload.items() if key != "extraction_receipt_id"}
    safe_payload["source_file_metadata"] = source_file_metadata
    encoded = json.dumps(safe_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def encode_cursor(updated_at: str, row_id: str) -> str:
    raw = json.dumps({"updated_at": updated_at, "id": row_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise CloudJobContextValidationError("Invalid pagination cursor.") from exc
    if not isinstance(payload, dict):
        raise CloudJobContextValidationError("Invalid pagination cursor.")
    updated_at = str(payload.get("updated_at") or "").strip()
    row_id = str(payload.get("id") or "").strip()
    if not updated_at or not row_id:
        raise CloudJobContextValidationError("Invalid pagination cursor.")
    try:
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        UUID(row_id)
    except ValueError as exc:
        raise CloudJobContextValidationError("Invalid pagination cursor.") from exc
    return updated_at, row_id


def job_description_preview(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:MAX_JOB_DESCRIPTION_PREVIEW_CHARS]


def _record_from_payload(payload: dict[str, Any]) -> CloudJobContextRecord:
    return CloudJobContextRecord(
        id=str(payload.get("id", "")),
        user_id=str(payload.get("user_id", "")),
        company=str(payload.get("company") or ""),
        position=str(payload.get("position") or ""),
        job_description=str(payload.get("job_description") or ""),
        required_skills=_normalize_array(payload.get("required_skills"), field="required_skills"),
        responsibilities=_normalize_array(payload.get("responsibilities"), field="responsibilities"),
        seniority=str(payload.get("seniority") or ""),
        domain_keywords=_normalize_array(payload.get("domain_keywords"), field="domain_keywords"),
        location=str(payload.get("location") or ""),
        employment_type=str(payload.get("employment_type") or ""),
        source_file_metadata=payload.get("source_file_metadata") if isinstance(payload.get("source_file_metadata"), dict) else {},
        is_active=bool(payload.get("is_active")),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def sanitize_job_description_filename(filename: str) -> str:
    try:
        return sanitize_resume_filename(filename)
    except Exception as exc:
        raise CloudJobContextValidationError("Unsupported job description file type. Please upload a PDF, DOCX, or TXT file.") from exc


def build_source_file_metadata(*, filename: str, content: bytes, content_type: str | None, source: str) -> dict[str, Any]:
    safe_filename = sanitize_job_description_filename(filename)
    suffix = PurePath(safe_filename).suffix.lower()
    expected_mime = ALLOWED_MIME_TYPES[suffix]
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type and normalized_content_type != "application/octet-stream" and normalized_content_type != expected_mime:
        raise CloudJobContextValidationError("Job description MIME type does not match the uploaded file extension.")
    detected_mime = normalized_content_type or mimetypes.guess_type(safe_filename)[0] or expected_mime
    return _normalize_metadata(
        {
            "filename": safe_filename,
            "mime_type": detected_mime,
            "byte_size": str(len(content)),
            "source": source,
        }
    )


def _validate_supabase_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme == "https" and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    raise SupabaseConfigurationError("Supabase URL must use HTTPS unless it targets localhost.")


class ExtractionReceiptStore:
    def __init__(self) -> None:
        self._receipts: dict[str, ExtractionReceipt] = {}

    def create(self, *, user_id: str, job_description: str, source_file_metadata: dict[str, Any]) -> str:
        self._prune()
        receipt_id = str(uuid4())
        self._receipts[receipt_id] = ExtractionReceipt(
            user_id=user_id,
            job_description_hash=self._hash_job_description(job_description),
            source_file_metadata=_normalize_metadata(source_file_metadata),
            expires_at=time.time() + EXTRACTION_RECEIPT_TTL_SECONDS,
        )
        return receipt_id

    def resolve(self, *, user_id: str, receipt_id: str, job_description: str) -> dict[str, Any]:
        self._prune()
        receipt = self._receipts.get(receipt_id)
        if receipt is None or receipt.expires_at < time.time() or receipt.user_id != user_id:
            raise CloudJobContextValidationError("Extraction receipt is invalid or expired.")
        if receipt.job_description_hash != self._hash_job_description(job_description):
            raise CloudJobContextValidationError("Extraction receipt does not match the saved job description.")
        return dict(receipt.source_file_metadata)

    def _prune(self) -> None:
        now = time.time()
        expired = [key for key, receipt in self._receipts.items() if receipt.expires_at < now]
        for key in expired:
            self._receipts.pop(key, None)

    def _hash_job_description(self, value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


class ExtractionLimiter:
    """Process-local extraction limiter.

    This protects a single backend process. A shared store such as Redis or a
    Supabase-backed counter should replace it before multi-worker production
    enforcement is required.
    """

    def __init__(self, *, max_calls: int = EXTRACTION_QUOTA_MAX_CALLS, window_seconds: int = EXTRACTION_QUOTA_WINDOW_SECONDS) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: dict[str, list[float]] = {}

    def consume(self, user_id: str) -> None:
        now = time.time()
        self._prune(now)
        calls = list(self._calls.get(user_id, []))
        if len(calls) >= self.max_calls:
            self._calls[user_id] = calls
            raise CloudJobContextRateLimitError("Job description extraction quota exceeded.")
        calls.append(now)
        self._calls[user_id] = calls

    def _prune(self, now: float | None = None) -> None:
        cutoff_now = time.time() if now is None else now
        for key in list(self._calls):
            active = [stamp for stamp in self._calls[key] if cutoff_now - stamp < self.window_seconds]
            if active:
                self._calls[key] = active
            else:
                del self._calls[key]


class ProviderCircuitBreaker:
    def __init__(self) -> None:
        self._failure_count = 0
        self._opened_at: float | None = None

    def ensure_available(self) -> None:
        if self._opened_at is None:
            return
        if time.time() - self._opened_at >= PROVIDER_CIRCUIT_COOLDOWN_SECONDS:
            self._opened_at = None
            self._failure_count = 0
            return
        raise CloudJobContextConflictError("Job description extraction is temporarily unavailable. Please try again later.")

    def record_success(self) -> None:
        self._failure_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= PROVIDER_CIRCUIT_FAILURE_THRESHOLD:
            self._opened_at = time.time()


class SupabaseCloudJobContextClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            logger.error("Supabase cloud job context is misconfigured: service-role key matches anon key.")
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
        self._headers = {
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_error_code(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return "unavailable"
        if not isinstance(payload, dict):
            return "unavailable"
        code = str(payload.get("code") or "").strip()
        return code[:80] if re.fullmatch(r"[A-Za-z0-9_.-]+", code) else "unavailable"

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase cloud job context failure: target=%s operation=%s status=%s error_code=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(target, operation, response)
        if response.status_code in {400, 409} and self._safe_error_code(response) == "P0001":
            raise CloudJobContextConflictError("Job context state changed. Please refresh and try again.")
        raise CloudJobContextError(SAFE_FAILURE_MESSAGE)

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> NoReturn:
        logger.error(
            "Supabase cloud job context failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudJobContextError(SAFE_FAILURE_MESSAGE) from exc

    def list_contexts(self, *, user_id: str, limit: int, cursor: str | None) -> list[CloudJobContextRecord]:
        params = {
            "select": "*",
            "user_id": f"eq.{user_id}",
            "order": "updated_at.desc,id.desc",
            "limit": str(limit + 1),
        }
        if cursor:
            updated_at, row_id = decode_cursor(cursor)
            params["or"] = f"(updated_at.lt.{updated_at},and(updated_at.eq.{updated_at},id.lt.{row_id}))"
        return self._select_contexts(params)

    def get_context(self, *, user_id: str, job_context_id: str) -> CloudJobContextRecord:
        rows = self._select_contexts(
            {"select": "*", "id": f"eq.{job_context_id}", "user_id": f"eq.{user_id}", "limit": "1"}
        )
        if not rows:
            raise CloudJobContextNotFoundError("Job context was not found.")
        return rows[0]

    def get_active_context(self, *, user_id: str) -> CloudJobContextRecord | None:
        rows = self._select_contexts(
            {
                "select": "*",
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "limit": "1",
            }
        )
        return rows[0] if rows else None

    def create_context(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        source_file_metadata: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> CreateJobContextResult:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/create_job_context_with_idempotency",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_request_hash": request_hash,
                    "p_company": payload["company"],
                    "p_position": payload["position"],
                    "p_job_description": payload["job_description"],
                    "p_required_skills": payload["required_skills"],
                    "p_responsibilities": payload["responsibilities"],
                    "p_seniority": payload["seniority"],
                    "p_domain_keywords": payload["domain_keywords"],
                    "p_location": payload["location"],
                    "p_employment_type": payload["employment_type"],
                    "p_source_file_metadata": source_file_metadata,
                    "p_activate": payload["activate"],
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("job_contexts", "create", exc)
        if response.status_code != 200:
            self._raise_response("job_contexts", "create", response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CloudJobContextError(SAFE_FAILURE_MESSAGE)
        created = data[0]
        if str(created.get("status") or "") == "gone":
            raise CloudJobContextNotFoundError("Job context was not found.")
        context_id = str(created.get("job_context_id") or "")
        if not context_id:
            raise CloudJobContextError(SAFE_FAILURE_MESSAGE)
        return CreateJobContextResult(
            record=self.get_context(user_id=user_id, job_context_id=context_id),
            replayed=bool(created.get("replayed")),
            activated=bool(created.get("activated")),
        )

    def update_context(self, *, user_id: str, job_context_id: str, payload: dict[str, Any]) -> CloudJobContextRecord:
        update_payload = {key: value for key, value in payload.items() if key not in {"activate", "extraction_receipt_id"}}
        try:
            response = self._session.patch(
                f"{self._rest_url}/job_contexts",
                headers={**self._headers, "Prefer": "return=representation"},
                params={"id": f"eq.{job_context_id}", "user_id": f"eq.{user_id}"},
                json=update_payload,
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("job_contexts", "update", exc)
        if response.status_code != 200:
            self._raise_response("job_contexts", "update", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudJobContextNotFoundError("Job context was not found.")
        return _record_from_payload(data[0])

    def delete_context(self, *, user_id: str, job_context_id: str) -> None:
        try:
            response = self._session.delete(
                f"{self._rest_url}/job_contexts",
                headers={**self._headers, "Prefer": "return=representation"},
                params={"id": f"eq.{job_context_id}", "user_id": f"eq.{user_id}"},
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("job_contexts", "delete", exc)
        if response.status_code != 200:
            self._raise_response("job_contexts", "delete", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudJobContextNotFoundError("Job context was not found.")

    def activate_context(self, *, user_id: str, job_context_id: str) -> CloudJobContextRecord:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/activate_job_context",
                headers={**self._headers, "Prefer": "return=representation"},
                json={"p_user_id": user_id, "p_job_context_id": job_context_id},
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("job_contexts", "activate", exc)
        if response.status_code != 200:
            self._raise_response("job_contexts", "activate", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudJobContextConflictError("Job context state changed. Please refresh and try again.")
        return _record_from_payload(data[0])

    def _select_contexts(self, params: dict[str, str]) -> list[CloudJobContextRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/job_contexts",
                headers=self._headers,
                params=params,
                timeout=SUPABASE_SELECT_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("job_contexts", "select", exc)
        if response.status_code != 200:
            self._raise_response("job_contexts", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudJobContextError(SAFE_FAILURE_MESSAGE)
        return [_record_from_payload(item) for item in data if isinstance(item, dict)]


class CloudJobContextService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        local_job_context: JobContextService | None = None,
        receipt_store: ExtractionReceiptStore | None = None,
        limiter: ExtractionLimiter | None = None,
        circuit_breaker: ProviderCircuitBreaker | None = None,
    ) -> None:
        self._client = client or SupabaseCloudJobContextClient()
        self._local_job_context = local_job_context or JobContextService()
        self._receipts = receipt_store or ExtractionReceiptStore()
        self._limiter = limiter or ExtractionLimiter()
        self._circuit_breaker = circuit_breaker or ProviderCircuitBreaker()

    def list_contexts(self, *, user_id: str, limit: int, cursor: str | None) -> JobContextListPage:
        if limit < 1 or limit > 50:
            raise CloudJobContextValidationError("Limit must be between 1 and 50.")
        rows = self._client.list_contexts(user_id=user_id, limit=limit, cursor=cursor)
        page_rows = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page_rows:
            last = page_rows[-1]
            next_cursor = encode_cursor(last.updated_at or "", last.id)
        active_context = self.get_active_context(user_id=user_id)
        active_id = active_context.id if active_context else None
        return JobContextListPage(items=page_rows, active_id=active_id, limit=limit, next_cursor=next_cursor)

    def get_context(self, *, user_id: str, job_context_id: str) -> CloudJobContextRecord:
        return self._client.get_context(user_id=user_id, job_context_id=job_context_id)

    def create_context(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> CreateJobContextResult:
        idempotency_key = validate_idempotency_key(idempotency_key)
        normalized = normalize_job_context_payload(payload)
        source_file_metadata: dict[str, Any] = {}
        if normalized["extraction_receipt_id"]:
            source_file_metadata = self._receipts.resolve(
                user_id=user_id,
                receipt_id=normalized["extraction_receipt_id"],
                job_description=normalized["job_description"],
            )
        request_hash = normalized_payload_hash(normalized, source_file_metadata)
        return self._client.create_context(
            user_id=user_id,
            payload=normalized,
            source_file_metadata=source_file_metadata,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

    def update_context(self, *, user_id: str, job_context_id: str, payload: dict[str, Any]) -> CloudJobContextRecord:
        normalized = normalize_job_context_update_payload(payload)
        source_file_metadata = None
        if normalized.get("extraction_receipt_id"):
            if "job_description" not in normalized:
                raise CloudJobContextValidationError("Job description is required when using an extraction receipt.")
            source_file_metadata = self._receipts.resolve(
                user_id=user_id,
                receipt_id=normalized["extraction_receipt_id"],
                job_description=normalized["job_description"],
            )
        if source_file_metadata is not None:
            normalized["source_file_metadata"] = source_file_metadata
        return self._client.update_context(user_id=user_id, job_context_id=job_context_id, payload=normalized)

    def delete_context(self, *, user_id: str, job_context_id: str) -> DeleteJobContextResult:
        self._client.delete_context(user_id=user_id, job_context_id=job_context_id)
        current = self.get_active_context(user_id=user_id)
        return DeleteJobContextResult(
            job_context_id=job_context_id,
            deleted=True,
            active_id=current.id if current else None,
        )

    def activate_context(self, *, user_id: str, job_context_id: str) -> CloudJobContextRecord:
        return self._client.activate_context(user_id=user_id, job_context_id=job_context_id)

    def get_active_context(self, *, user_id: str) -> CloudJobContextRecord | None:
        if hasattr(self._client, "get_active_context"):
            return self._client.get_active_context(user_id=user_id)
        rows = self._client.list_contexts(user_id=user_id, limit=50, cursor=None)
        return next((row for row in rows if row.is_active), None)

    def extract_from_text(self, *, user_id: str, job_description_text: str) -> CloudJobContextExtractResult:
        raw_text = str(job_description_text or "").strip()
        self._validate_extracted_text(raw_text)
        return self._extract(user_id=user_id, raw_text=raw_text, source_file_metadata={"source": "paste"})

    def extract_from_file(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> CloudJobContextExtractResult:
        if len(content) > MAX_RESUME_FILE_BYTES:
            raise CloudJobContextValidationError("Job description file is too large. Please upload a file under 5 MB.")
        metadata = build_source_file_metadata(
            filename=filename,
            content=content,
            content_type=content_type,
            source="upload",
        )
        try:
            raw_text = self._local_job_context.extract_text(filename=filename, content=content)
        except ResumeExtractionError as exc:
            raise CloudJobContextValidationError(str(exc).replace("resume", "job description")) from exc
        self._validate_extracted_text(raw_text)
        return self._extract(user_id=user_id, raw_text=raw_text, source_file_metadata=metadata)

    def _extract(
        self,
        *,
        user_id: str,
        raw_text: str,
        source_file_metadata: dict[str, Any],
    ) -> CloudJobContextExtractResult:
        self._circuit_breaker.ensure_available()
        self._limiter.consume(user_id)
        try:
            local_fields = self._local_job_context.build_context_fields(raw_text)
        except (JobContextError, ProviderError):
            self._circuit_breaker.record_failure()
            raise
        except Exception as exc:
            self._circuit_breaker.record_failure()
            raise CloudJobContextError("Job context extraction failed. Please try again.") from exc
        self._circuit_breaker.record_success()

        summary = str(local_fields.get("job_description") or "").strip()
        result = CloudJobContextExtractResult(
            company=str(local_fields.get("company_name") or "").strip(),
            position=str(local_fields.get("target_role") or "").strip(),
            job_description=raw_text,
            job_description_summary=summary,
            required_skills=_normalize_array(local_fields.get("required_skills"), field="required_skills"),
            responsibilities=_normalize_array(local_fields.get("responsibilities"), field="responsibilities"),
            seniority="",
            domain_keywords=[],
            location="",
            employment_type="",
            source_file_metadata=_normalize_metadata(source_file_metadata),
            extraction_receipt_id="",
            extracted_text_length=len(raw_text),
        )
        receipt_id = self._receipts.create(
            user_id=user_id,
            job_description=raw_text,
            source_file_metadata=result.source_file_metadata,
        )
        return CloudJobContextExtractResult(**{**result.__dict__, "extraction_receipt_id": receipt_id})

    def _validate_extracted_text(self, value: str) -> None:
        if not value:
            raise CloudJobContextValidationError("Job description text is required.")
        if len(value.encode("utf-8")) > MAX_EXTRACTED_JD_BYTES:
            raise CloudJobContextValidationError("Job description text is too large.")
