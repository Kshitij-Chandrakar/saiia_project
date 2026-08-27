from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import mimetypes
from pathlib import PurePath
import re
from typing import Any, NoReturn
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter

from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.nlp.answer_generator import ProviderError
from app.services.resume_index_service import ResumeIndexError, ResumeIndexService
from app.services.resume_parser_service import ResumeParserService
from app.services.resume_service import MAX_RESUME_FILE_BYTES, PROFILE_FIELD_ORDER, ResumeExtractionError

logger = logging.getLogger("cloud_resume")

ALLOWED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
RETRY_EXTRACT_STATUSES = {"uploaded", "failed", "timeout", "cancelled", "needs_review", "indexing"}
SAFE_FAILURE_MESSAGE = "Resume processing failed. Please try again."
MAX_CONFIRMED_PROFILE_BYTES = 64 * 1024
CONFIRMED_PROFILE_FIELDS = tuple(field for field in PROFILE_FIELD_ORDER if field != "raw_resume_text")
CLOUD_INDEX_PROFILE_FIELDS = (
    "full_name",
    "current_title",
    "target_role",
    "professional_summary",
    "top_skills",
    "technical_skills",
    "tools_frameworks",
    "skills",
    "projects",
    "experience",
    "work_experience",
    "education",
    "degree",
    "branch",
    "college",
    "college_university",
    "university",
    "graduation_year",
    "achievements",
    "certifications",
)
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_SELECT_ATTEMPT_TIMEOUT = 5
SUPABASE_ACTIVE_CHUNK_PAGE_SIZE = 100
SUPABASE_ACTIVE_CHUNK_HARD_LIMIT = 500
PROJECT_CONTEXT_LIMIT_FLOOR = 4
SPECIFIC_PROJECT_CONTEXT_LIMIT = 6
PROJECT_SECTION_NAMES = {"projects", "project", "experience", "work_experience", "internship"}
PROJECT_INDEX_FIELDS = ("projects", "experience", "work_experience")
PROJECT_KEYWORDS = {
    "project",
    "projects",
    "experience",
    "internship",
    "work",
    "built",
    "build",
    "developed",
    "implemented",
    "created",
    "designed",
    "rag",
    "langchain",
    "fastapi",
    "api",
    "apis",
    "chroma",
    "vector",
    "embedding",
    "embeddings",
    "semantic",
    "search",
    "tensorflow",
    "deployed",
}
PROJECT_INTENT_RE = re.compile(
    r"\b(project|projects|portfolio|resume project|work experience|internship)\b|"
    r"\b(?:your|my)\s+(?:project|projects|portfolio|work experience|internship|experience)\b|"
    r"\bwhat did you build\b|\bwhat have you built\b|\bwhat did you implement\b|\bwhat have you implemented\b|"
    r"\bin (?:your|the) (?:project|projects|internship|work experience)\b",
    re.IGNORECASE,
)
PROJECT_SPECIFIC_LEAD_RE = re.compile(
    r"^(?:explain|tell me about|describe|walk me through|how did you build|what was your role in|why did you use)\s+",
    re.IGNORECASE,
)
PROJECT_TRAILING_FILLER_RE = re.compile(
    r"\b(from my selected resume|from the selected resume|from your resume|in your resume|project|projects)\b",
    re.IGNORECASE,
)
PROJECT_TECH_TERM_RE = re.compile(
    r"\b(faiss|minilm|streamlit|fastapi|langchain|chroma|gemini api|tensorflow|vector retrieval|semantic search|rag)\b",
    re.IGNORECASE,
)
PROJECT_HEADING_PATTERNS = (
    ("projects", re.compile(r"^(projects?|academic projects?|personal projects?)\s*:?\s*$", re.IGNORECASE)),
    ("work_experience", re.compile(r"^(work experience|professional experience|experience|internships?)\s*:?\s*$", re.IGNORECASE)),
)
RESUME_SECTION_STOP_RE = re.compile(
    r"^(skills?|technical skills?|tools|frameworks|education|certifications?|achievements?|summary|professional summary|profile|contact|languages?)\s*:?\s*$",
    re.IGNORECASE,
)


class CloudResumeError(RuntimeError):
    """Raised when a cloud resume operation cannot complete."""


class CloudResumeNotFoundError(CloudResumeError):
    """Raised when the current user cannot access a resume."""


class CloudResumeConflictError(CloudResumeError):
    """Raised when lifecycle preconditions are not met."""


class CloudResumeValidationError(CloudResumeError):
    """Raised when an uploaded file or payload is invalid."""


@dataclass(frozen=True)
class CloudResumeRecord:
    id: str
    user_id: str
    storage_path: str
    original_filename: str
    mime_type: str
    file_size: int
    status: str
    is_active: bool
    extraction_attempt: int
    parser_provider: str = "pending"
    parser_status: str = "pending"
    extraction_status: str = "pending"
    index_status: str = "not_indexed"
    review_required: bool = False
    confirmed_at: str | None = None
    confirmed_profile: dict[str, Any] | None = None
    active_chunk_generation: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    failed_at: str | None = None
    last_error_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class UploadResult:
    resume: CloudResumeRecord


@dataclass(frozen=True)
class ExtractResult:
    resume_id: str
    status: str
    extraction_attempt: int
    parser_provider: str
    fallback_used: bool
    missing_fields: list[str]
    review_required: bool
    profile: dict[str, Any]
    extracted_text_length: int


@dataclass(frozen=True)
class ConfirmResult:
    resume_id: str
    status: str
    extraction_attempt: int
    confirmed_profile_saved: bool
    next_step: str
    chunks_indexed: bool = False
    chunk_count: int = 0
    ready: bool = False
    active: bool = False


@dataclass(frozen=True)
class DeleteResult:
    resume_id: str
    status: str
    is_active: bool
    ready: bool
    message: str


@dataclass(frozen=True)
class RebuildResult:
    resume_id: str
    status: str
    index_status: str
    active_chunk_generation: str
    chunk_count: int
    message: str


@dataclass(frozen=True)
class ResumeReadiness:
    chunk_count: int | None
    can_generate: bool
    readiness_reason: str


def _record_from_payload(payload: dict[str, Any]) -> CloudResumeRecord:
    return CloudResumeRecord(
        id=str(payload.get("id", "")),
        user_id=str(payload.get("user_id", "")),
        storage_path=str(payload.get("storage_path", "")),
        original_filename=str(payload.get("original_filename", "")),
        mime_type=str(payload.get("mime_type", "")),
        file_size=int(payload.get("file_size") or 0),
        status=str(payload.get("status", "")),
        is_active=bool(payload.get("is_active")),
        extraction_attempt=int(payload.get("extraction_attempt") or 0),
        parser_provider=str(payload.get("parser_provider") or "pending"),
        parser_status=str(payload.get("parser_status") or "pending"),
        extraction_status=str(payload.get("extraction_status") or "pending"),
        index_status=str(payload.get("index_status") or "not_indexed"),
        review_required=bool(payload.get("review_required")),
        confirmed_at=payload.get("confirmed_at"),
        confirmed_profile=payload.get("confirmed_profile") if isinstance(payload.get("confirmed_profile"), dict) else None,
        active_chunk_generation=payload.get("active_chunk_generation"),
        failure_code=payload.get("failure_code"),
        failure_message=payload.get("failure_message"),
        failed_at=payload.get("failed_at"),
        last_error_at=payload.get("last_error_at"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def question_has_project_intent(question: str) -> bool:
    return bool(PROJECT_INTENT_RE.search(str(question or "")))


def sanitize_resume_filename(filename: str) -> str:
    basename = PurePath(str(filename or "").replace("\\", "/")).name.strip()
    basename = re.sub(r"[\x00-\x1f\x7f]+", "", basename)
    basename = re.sub(r"[^A-Za-z0-9._ -]+", "_", basename)
    basename = re.sub(r"\s+", " ", basename).strip(" .")
    if not basename or basename in {".", ".."}:
        raise CloudResumeValidationError("Invalid resume filename.")
    suffix = PurePath(basename).suffix.lower()
    if suffix not in ALLOWED_MIME_TYPES:
        raise CloudResumeValidationError("Unsupported resume file type. Please upload a PDF, DOCX, or TXT resume.")
    stem = basename[: -len(suffix)].rstrip(" .")
    return f"{stem[: 120 - len(suffix)]}{suffix}"


def validate_confirmed_profile(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise CloudResumeValidationError("Confirmed profile is required.")
    unknown_fields = sorted(set(payload) - set(CONFIRMED_PROFILE_FIELDS))
    if unknown_fields:
        raise CloudResumeValidationError("Confirmed profile contains unsupported fields.")
    normalized = {field: payload[field] for field in CONFIRMED_PROFILE_FIELDS if field in payload}
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(serialized) > MAX_CONFIRMED_PROFILE_BYTES:
        raise CloudResumeValidationError("Confirmed profile is too large.")
    return normalized


def validate_resume_upload(*, filename: str, content: bytes, content_type: str | None) -> tuple[str, str]:
    safe_filename = sanitize_resume_filename(filename)
    suffix = PurePath(safe_filename).suffix.lower()
    expected_mime = ALLOWED_MIME_TYPES[suffix]
    if not content:
        raise CloudResumeValidationError("The uploaded resume is empty. Please choose a valid file.")
    if len(content) > MAX_RESUME_FILE_BYTES:
        raise CloudResumeValidationError("Resume file is too large. Please upload a file under 5 MB.")
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    guessed_mime = mimetypes.guess_type(safe_filename)[0]
    if normalized_content_type and normalized_content_type != "application/octet-stream":
        if normalized_content_type != expected_mime:
            raise CloudResumeValidationError("Resume MIME type does not match the uploaded file extension.")
    return safe_filename, normalized_content_type or guessed_mime or expected_mime


class SupabaseCloudResumeClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            logger.error("Supabase cloud resume is misconfigured: service-role key matches anon key.")
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        self._rest_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self._storage_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._resume_bucket = settings.resume_bucket
        self._service_role_key = settings.service_role_key
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
            "Supabase cloud resume failure: target=%s operation=%s status=%s error_code=%s",
            target,
            operation,
            response.status_code,
            self._safe_error_code(response),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(target, operation, response)
        raise CloudResumeError("Supabase cloud resume operation failed.")

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> NoReturn:
        logger.error(
            "Supabase cloud resume failure: target=%s operation=%s status=request_error error_type=%s",
            target,
            operation,
            type(exc).__name__,
        )
        raise CloudResumeError("Supabase cloud resume operation failed.") from exc

    def insert_resume_metadata(self, payload: dict[str, Any]) -> CloudResumeRecord:
        try:
            response = self._session.post(
                f"{self._rest_url}/resumes",
                headers={**self._headers, "Prefer": "return=representation"},
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "insert", exc)
        if response.status_code not in {200, 201}:
            self._raise_response("resumes", "insert", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudResumeError("Supabase cloud resume operation failed.")
        return _record_from_payload(data[0])

    def update_resume(self, resume_id: str, user_id: str, payload: dict[str, Any]) -> CloudResumeRecord:
        try:
            response = self._session.patch(
                f"{self._rest_url}/resumes",
                headers={**self._headers, "Prefer": "return=representation"},
                params={"id": f"eq.{resume_id}", "user_id": f"eq.{user_id}"},
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "update", exc)
        if response.status_code != 200:
            self._raise_response("resumes", "update", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudResumeNotFoundError("Resume was not found.")
        return _record_from_payload(data[0])

    def compare_and_set_resume(
        self,
        resume_id: str,
        user_id: str,
        from_statuses: set[str],
        payload: dict[str, Any],
        *,
        extraction_attempt: int | None = None,
    ) -> CloudResumeRecord:
        params = {
            "id": f"eq.{resume_id}",
            "user_id": f"eq.{user_id}",
            "status": f"in.({','.join(sorted(from_statuses))})",
        }
        if extraction_attempt is not None:
            params["extraction_attempt"] = f"eq.{extraction_attempt}"
        try:
            response = self._session.patch(
                f"{self._rest_url}/resumes",
                headers={**self._headers, "Prefer": "return=representation"},
                params=params,
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "compare_and_set", exc)
        if response.status_code != 200:
            self._raise_response("resumes", "compare_and_set", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        return _record_from_payload(data[0])

    def activate_rebuilt_resume_generation(
        self,
        *,
        user_id: str,
        resume_id: str,
        expected_active_generation: str,
        new_generation_id: str,
    ) -> CloudResumeRecord:
        try:
            response = self._session.patch(
                f"{self._rest_url}/resumes",
                headers={**self._headers, "Prefer": "return=representation"},
                params={
                    "id": f"eq.{resume_id}",
                    "user_id": f"eq.{user_id}",
                    "status": "eq.ready",
                    "is_active": "eq.true",
                    "active_chunk_generation": f"eq.{expected_active_generation}",
                },
                json={
                    "index_status": "indexed",
                    "active_chunk_generation": new_generation_id,
                    "failure_code": None,
                    "failure_message": None,
                    "failed_at": None,
                    "last_error_at": None,
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "rebuild_activate", exc)
        if response.status_code != 200:
            self._raise_response("resumes", "rebuild_activate", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        return _record_from_payload(data[0])

    def get_resume(self, resume_id: str, user_id: str) -> CloudResumeRecord:
        rows = self._select_resumes(
            {"id": f"eq.{resume_id}", "user_id": f"eq.{user_id}", "limit": "1"}
        )
        if not rows:
            raise CloudResumeNotFoundError("Resume was not found.")
        return rows[0]

    def get_current_resume(self, user_id: str) -> CloudResumeRecord | None:
        rows = self._select_resumes(
            {
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "status": "eq.ready",
                "order": "updated_at.desc",
                "limit": "1",
            }
        )
        return rows[0] if rows else None

    def list_resumes(self, user_id: str) -> list[CloudResumeRecord]:
        return self._select_resumes(
            {
                "user_id": f"eq.{user_id}",
                "status": "neq.deleted",
                "order": "updated_at.desc.nullslast,created_at.desc.nullslast",
                "limit": "50",
            }
        )

    def get_review_candidate(self, user_id: str) -> CloudResumeRecord | None:
        rows = self._select_resumes(
            {
                "user_id": f"eq.{user_id}",
                "status": "eq.needs_review",
                "confirmed_at": "is.null",
                "order": "updated_at.desc",
                "limit": "1",
            }
        )
        return rows[0] if rows else None

    def _select_resumes(self, params: dict[str, str]) -> list[CloudResumeRecord]:
        query = {"select": "*", **params}
        for attempt in (1, 2):
            try:
                response = self._session.get(
                    f"{self._rest_url}/resumes",
                    headers=self._headers,
                    params=query,
                    timeout=SUPABASE_SELECT_ATTEMPT_TIMEOUT,
                )
                break
            except requests.RequestException as exc:
                if attempt == 1:
                    logger.warning(
                        "Supabase cloud resume select retry: target=resumes operation=select stage=request_retry error_type=%s",
                        type(exc).__name__,
                    )
                    continue
                self._raise_request("resumes", "select", exc)
        else:
            raise CloudResumeError("Supabase cloud resume operation failed.")
        if response.status_code != 200:
            self._raise_response("resumes", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudResumeError("Supabase cloud resume operation failed.")
        return [_record_from_payload(item) for item in data if isinstance(item, dict)]

    def upload_resume_object(self, storage_path: str, content: bytes, mime_type: str) -> None:
        try:
            response = self._session.post(
                f"{self._storage_url}/object/{self._resume_bucket}/{storage_path}",
                headers={
                    "apikey": self._service_role_key,
                    "Authorization": f"Bearer {self._service_role_key}",
                    "Content-Type": mime_type,
                    "x-upsert": "false",
                },
                data=content,
                timeout=20,
            )
        except requests.RequestException as exc:
            self._raise_request("storage.objects", "upload", exc)
        if response.status_code not in {200, 201}:
            self._raise_response("storage.objects", "upload", response)

    def download_resume_object(self, storage_path: str) -> bytes:
        try:
            response = self._session.get(
                f"{self._storage_url}/object/{self._resume_bucket}/{storage_path}",
                headers={
                    "apikey": self._service_role_key,
                    "Authorization": f"Bearer {self._service_role_key}",
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            self._raise_request("storage.objects", "download", exc)
        if response.status_code != 200:
            self._raise_response("storage.objects", "download", response)
        return response.content

    def delete_resume_object(self, storage_path: str) -> None:
        try:
            response = self._session.delete(
                f"{self._storage_url}/object/{self._resume_bucket}/{storage_path}",
                headers={
                    "apikey": self._service_role_key,
                    "Authorization": f"Bearer {self._service_role_key}",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("storage.objects", "delete", exc)
        if response.status_code not in {200, 204, 404}:
            self._raise_response("storage.objects", "delete", response)

    def insert_resume_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            raise CloudResumeError("Supabase cloud resume operation failed.")
        try:
            response = self._session.post(
                f"{self._rest_url}/resume_chunks",
                headers={**self._headers, "Prefer": "return=minimal"},
                json=chunks,
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resume_chunks", "insert", exc)
        if response.status_code not in {200, 201, 204}:
            self._raise_response("resume_chunks", "insert", response)

    def delete_resume_chunks(self, *, user_id: str, resume_id: str, generation_id: str | None = None) -> None:
        params = {
            "user_id": f"eq.{user_id}",
            "resume_id": f"eq.{resume_id}",
        }
        if generation_id is not None:
            params["generation_id"] = f"eq.{generation_id}"
        try:
            response = self._session.delete(
                f"{self._rest_url}/resume_chunks",
                headers={**self._headers, "Prefer": "return=minimal"},
                params=params,
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resume_chunks", "delete", exc)
        if response.status_code not in {200, 204}:
            self._raise_response("resume_chunks", "delete", response)

    def delete_inactive_resume_chunks(self, *, user_id: str, resume_id: str, active_generation_id: str) -> None:
        try:
            response = self._session.delete(
                f"{self._rest_url}/resume_chunks",
                headers={**self._headers, "Prefer": "return=minimal"},
                params={
                    "user_id": f"eq.{user_id}",
                    "resume_id": f"eq.{resume_id}",
                    "or": f"(generation_id.is.null,generation_id.neq.{active_generation_id})",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resume_chunks", "delete_inactive", exc)
        if response.status_code not in {200, 204}:
            self._raise_response("resume_chunks", "delete_inactive", response)

    def activate_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
        extraction_attempt: int,
        generation_id: str,
        confirmed_profile: dict[str, Any],
    ) -> CloudResumeRecord:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/activate_cloud_resume",
                headers={**self._headers, "Prefer": "return=representation"},
                json={
                    "p_user_id": user_id,
                    "p_resume_id": resume_id,
                    "p_extraction_attempt": extraction_attempt,
                    "p_generation_id": generation_id,
                    "p_profile": confirmed_profile,
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "activate", exc)
        if response.status_code != 200:
            if response.status_code in {400, 409} and self._safe_error_code(response) == "P0001":
                self._log_failure("resumes", "activate", response)
                raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
            self._raise_response("resumes", "activate", response)
        data = response.json()
        if not isinstance(data, list) or not data:
            raise CloudResumeConflictError("Resume activation failed. Please refresh and try again.")
        return _record_from_payload(data[0])

    def get_active_resume_chunks(
        self,
        *,
        user_id: str,
        resume_id: str,
        generation_id: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < SUPABASE_ACTIVE_CHUNK_HARD_LIMIT:
            page = self._select_resume_chunk_page(
                user_id=user_id,
                resume_id=resume_id,
                generation_id=generation_id,
                offset=offset,
            )
            rows.extend(page)
            if len(page) < SUPABASE_ACTIVE_CHUNK_PAGE_SIZE:
                return rows
            offset += SUPABASE_ACTIVE_CHUNK_PAGE_SIZE
        logger.warning(
            "Supabase cloud resume chunk retrieval bounded: target=resume_chunks operation=select status=chunk_limit_reached"
        )
        return rows

    def get_active_resume_chunk_counts(
        self,
        *,
        user_id: str,
        records: list["CloudResumeRecord"],
    ) -> dict[tuple[str, str], int]:
        active_pairs = [
            (record.id, str(record.active_chunk_generation or ""))
            for record in records
            if record.active_chunk_generation
        ]
        if not active_pairs:
            return {}
        resume_ids = sorted({resume_id for resume_id, _ in active_pairs})
        generation_ids = sorted({generation_id for _, generation_id in active_pairs if generation_id})
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < SUPABASE_ACTIVE_CHUNK_HARD_LIMIT:
            page = self._select_resume_chunk_count_page(
                user_id=user_id,
                resume_ids=resume_ids,
                generation_ids=generation_ids,
                offset=offset,
            )
            rows.extend(page)
            if len(page) < SUPABASE_ACTIVE_CHUNK_PAGE_SIZE:
                break
            offset += SUPABASE_ACTIVE_CHUNK_PAGE_SIZE
        counts: dict[tuple[str, str], int] = {}
        allowed_pairs = set(active_pairs)
        for row in rows:
            key = (str(row.get("resume_id") or ""), str(row.get("generation_id") or ""))
            if key not in allowed_pairs:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _select_resume_chunk_page(
        self,
        *,
        user_id: str,
        resume_id: str,
        generation_id: str,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = {
            "select": "id,resume_id,section,chunk_text,metadata,generation_id",
            "user_id": f"eq.{user_id}",
            "resume_id": f"eq.{resume_id}",
            "generation_id": f"eq.{generation_id}",
            "order": "created_at.asc",
            "limit": str(SUPABASE_ACTIVE_CHUNK_PAGE_SIZE),
            "offset": str(offset),
        }
        for attempt in (1, 2):
            try:
                response = self._session.get(
                    f"{self._rest_url}/resume_chunks",
                    headers=self._headers,
                    params=query,
                    timeout=SUPABASE_SELECT_ATTEMPT_TIMEOUT,
                )
                break
            except requests.RequestException as exc:
                if attempt == 1:
                    logger.warning(
                        "Supabase cloud resume chunk select retry: target=resume_chunks operation=select stage=request_retry error_type=%s",
                        type(exc).__name__,
                    )
                    continue
                self._raise_request("resume_chunks", "select", exc)
        else:
            raise CloudResumeError("Supabase cloud resume operation failed.")
        if response.status_code != 200:
            self._raise_response("resume_chunks", "select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudResumeError("Supabase cloud resume operation failed.")
        return [item for item in data if isinstance(item, dict)]

    def _select_resume_chunk_count_page(
        self,
        *,
        user_id: str,
        resume_ids: list[str],
        generation_ids: list[str],
        offset: int,
    ) -> list[dict[str, Any]]:
        query = {
            "select": "resume_id,generation_id",
            "user_id": f"eq.{user_id}",
            "resume_id": f"in.({','.join(resume_ids)})",
            "generation_id": f"in.({','.join(generation_ids)})",
            "limit": str(SUPABASE_ACTIVE_CHUNK_PAGE_SIZE),
            "offset": str(offset),
        }
        for attempt in (1, 2):
            try:
                response = self._session.get(
                    f"{self._rest_url}/resume_chunks",
                    headers=self._headers,
                    params=query,
                    timeout=SUPABASE_SELECT_ATTEMPT_TIMEOUT,
                )
                break
            except requests.RequestException as exc:
                if attempt == 1:
                    logger.warning(
                        "Supabase cloud resume chunk count select retry: target=resume_chunks operation=count_select stage=request_retry error_type=%s",
                        type(exc).__name__,
                    )
                    continue
                self._raise_request("resume_chunks", "count_select", exc)
        else:
            raise CloudResumeError("Supabase cloud resume operation failed.")
        if response.status_code != 200:
            self._raise_response("resume_chunks", "count_select", response)
        data = response.json()
        if not isinstance(data, list):
            raise CloudResumeError("Supabase cloud resume operation failed.")
        return [item for item in data if isinstance(item, dict)]


class CloudResumeService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        parser: ResumeParserService | None = None,
        indexer: ResumeIndexService | None = None,
    ) -> None:
        self._client = client or SupabaseCloudResumeClient()
        self._parser = parser or ResumeParserService()
        self._indexer = indexer or ResumeIndexService()

    def upload_resume(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> UploadResult:
        safe_filename, mime_type = validate_resume_upload(
            filename=filename,
            content=content,
            content_type=content_type,
        )
        resume_id = str(uuid4())
        storage_path = f"{user_id}/{resume_id}/{safe_filename}"
        resume = self._client.insert_resume_metadata(
            {
                "id": resume_id,
                "user_id": user_id,
                "storage_path": storage_path,
                "original_filename": safe_filename,
                "mime_type": mime_type,
                "file_size": len(content),
                "status": "uploaded",
                "is_active": False,
                "parser_provider": "pending",
                "parser_status": "pending",
                "extraction_status": "pending",
                "index_status": "not_indexed",
                "review_required": False,
                "extraction_attempt": 0,
            }
        )
        try:
            self._client.upload_resume_object(storage_path, content, mime_type)
        except CloudResumeError:
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="storage_upload_failed",
                message="Resume upload failed. Please try again.",
            )
            raise
        return UploadResult(resume=resume)

    def get_current_resume(self, user_id: str) -> CloudResumeRecord | None:
        return self._client.get_current_resume(user_id)

    def list_resumes(self, user_id: str) -> list[CloudResumeRecord]:
        return self._client.list_resumes(user_id)

    def list_resume_readiness(self, *, user_id: str, records: list[CloudResumeRecord]) -> dict[str, ResumeReadiness]:
        readiness: dict[str, ResumeReadiness] = {}
        unknown_records: list[CloudResumeRecord] = []
        for record in records:
            reason = self._readiness_reason(record, chunk_count=None)
            if reason != "unknown":
                readiness[record.id] = ResumeReadiness(chunk_count=None, can_generate=False, readiness_reason=reason)
                continue
            unknown_records.append(record)
        if not unknown_records:
            return readiness
        chunk_counts = self._client.get_active_resume_chunk_counts(user_id=user_id, records=unknown_records)
        for record in unknown_records:
            chunk_count = chunk_counts.get((record.id, str(record.active_chunk_generation or "")), 0)
            reason = self._readiness_reason(record, chunk_count=chunk_count)
            readiness[record.id] = ResumeReadiness(
                chunk_count=chunk_count,
                can_generate=reason == "ready",
                readiness_reason=reason,
            )
        return readiness

    def get_resume_readiness(self, *, user_id: str, record: CloudResumeRecord) -> ResumeReadiness:
        return self.list_resume_readiness(user_id=user_id, records=[record])[record.id]

    @staticmethod
    def _readiness_reason(record: CloudResumeRecord, *, chunk_count: int | None) -> str:
        status_value = str(record.status or "").strip().lower()
        parser_status = str(record.parser_status or "").strip().lower()
        extraction_status = str(record.extraction_status or "").strip().lower()
        index_status = str(record.index_status or "").strip().lower()
        if (
            status_value == "failed"
            or parser_status == "failed"
            or extraction_status == "failed"
            or index_status == "failed"
            or record.failure_code
        ):
            return "failed"
        if status_value in {"extracting", "indexing"} or "processing" in {parser_status, extraction_status, index_status}:
            return "processing"
        if status_value == "needs_review" or record.review_required:
            return "needs_confirmation"
        if status_value != "ready" or index_status != "indexed" or not record.active_chunk_generation:
            return "not_indexed"
        if chunk_count is None:
            return "unknown"
        if chunk_count <= 0:
            return "no_chunks"
        return "ready"

    def get_review_candidate(self, user_id: str) -> CloudResumeRecord | None:
        return self._client.get_review_candidate(user_id)

    def get_status(self, *, user_id: str, resume_id: str) -> CloudResumeRecord:
        return self._client.get_resume(resume_id, user_id)

    def delete_resume(self, *, user_id: str, resume_id: str) -> DeleteResult:
        current = self._client.get_resume(resume_id, user_id)
        if current.status != "deleted" or current.is_active or current.active_chunk_generation:
            self._client.update_resume(
                resume_id,
                user_id,
                {
                    "status": "deleted",
                    "is_active": False,
                    "active_chunk_generation": None,
                    "index_status": "not_indexed",
                    "review_required": False,
                    "failure_code": None,
                    "failure_message": None,
                    "last_error_at": None,
                },
            )
        self._client.delete_resume_chunks(user_id=user_id, resume_id=resume_id)
        try:
            self._client.delete_resume_object(current.storage_path)
        except CloudResumeError as exc:
            logger.warning(
                "Cloud resume storage cleanup failed stage=delete_storage error_type=%s resume_id=%s user_id=%s",
                type(exc).__name__,
                resume_id,
                user_id,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc
        return DeleteResult(
            resume_id=resume_id,
            status="deleted",
            is_active=False,
            ready=False,
            message="Resume deleted.",
        )

    def rebuild_resume_index(self, *, user_id: str, resume_id: str) -> RebuildResult:
        current = self._client.get_resume(resume_id, user_id)
        if current.status != "ready" or not current.is_active or not current.confirmed_profile or not current.active_chunk_generation:
            raise CloudResumeConflictError("Resume is not ready for index rebuild.")
        expected_generation = current.active_chunk_generation

        generation_id = str(uuid4())
        inserted_generation = False
        try:
            chunks = self._build_resume_chunks(
                user_id=user_id,
                resume_id=resume_id,
                generation_id=generation_id,
                confirmed_profile=current.confirmed_profile,
                extra_documents=self._supplemental_project_documents(
                    record=current,
                    confirmed_profile=current.confirmed_profile,
                ),
            )
            self._client.insert_resume_chunks(chunks)
            inserted_generation = True
            updated = self._client.activate_rebuilt_resume_generation(
                user_id=user_id,
                resume_id=resume_id,
                expected_active_generation=expected_generation,
                new_generation_id=generation_id,
            )
            self._prune_inactive_generations(user_id=user_id, resume_id=resume_id, active_generation_id=generation_id)
        except CloudResumeConflictError as exc:
            self._log_index_failure("rebuild_activate", exc)
            if inserted_generation:
                self._discard_generation(user_id=user_id, resume_id=resume_id, generation_id=generation_id)
            raise
        except (CloudResumeError, ResumeIndexError) as exc:
            self._log_index_failure("rebuild_index", exc)
            if inserted_generation:
                self._discard_generation(user_id=user_id, resume_id=resume_id, generation_id=generation_id)
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc

        return RebuildResult(
            resume_id=updated.id,
            status=updated.status,
            index_status=updated.index_status,
            active_chunk_generation=updated.active_chunk_generation or generation_id,
            chunk_count=len(chunks),
            message="Resume index rebuilt.",
        )

    def extract_resume(self, *, user_id: str, resume_id: str) -> ExtractResult:
        current = self._client.get_resume(resume_id, user_id)
        attempt = current.extraction_attempt + 1
        extracting = self._client.compare_and_set_resume(
            resume_id,
            user_id,
            RETRY_EXTRACT_STATUSES,
            {
                "status": "extracting",
                "extraction_status": "processing",
                "parser_status": "processing",
                "extraction_attempt": attempt,
                "failure_code": None,
                "failure_message": None,
                "failed_at": None,
                "last_error_at": None,
            },
        )
        try:
            content = self._client.download_resume_object(extracting.storage_path)
        except CloudResumeError as exc:
            self._log_extract_failure("storage_download", exc)
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="extraction_failed",
                message=SAFE_FAILURE_MESSAGE,
                extraction_attempt=attempt,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc

        try:
            parsed = self._parser.extract_profile(filename=extracting.original_filename, content=content)
        except (ResumeExtractionError, ProviderError, CloudResumeError, Exception) as exc:
            self._log_extract_failure("local_parse", exc)
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="extraction_failed",
                message=SAFE_FAILURE_MESSAGE,
                extraction_attempt=attempt,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc

        try:
            profile = dict(parsed.get("profile") or {})
            profile.pop("raw_resume_text", None)
        except (AttributeError, TypeError, ValueError) as exc:
            self._log_extract_failure("normalize_draft", exc)
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="extraction_failed",
                message=SAFE_FAILURE_MESSAGE,
                extraction_attempt=attempt,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc
        try:
            updated = self._client.compare_and_set_resume(
                resume_id,
                user_id,
                {"extracting"},
                {
                    "status": "needs_review",
                    "extraction_status": "completed",
                    "parser_status": "completed",
                    "parser_provider": parsed.get("parser_provider") or "local",
                    "review_required": bool(parsed.get("review_required")),
                },
                extraction_attempt=attempt,
            )
        except CloudResumeError as exc:
            self._log_extract_failure("status_update", exc)
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="extraction_state_write_failed",
                message=SAFE_FAILURE_MESSAGE,
                extraction_attempt=attempt,
            )
            raise
        return ExtractResult(
            resume_id=updated.id,
            status=updated.status,
            extraction_attempt=attempt,
            parser_provider=str(parsed.get("parser_provider") or "local"),
            fallback_used=bool(parsed.get("fallback_used")),
            missing_fields=list(parsed.get("missing_fields") or []),
            review_required=bool(parsed.get("review_required")),
            profile=profile,
            extracted_text_length=int(parsed.get("extracted_text_length") or 0),
        )

    def confirm_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
        extraction_attempt: int,
        confirmed_profile: dict[str, Any],
    ) -> ConfirmResult:
        current = self._client.get_resume(resume_id, user_id)
        normalized_profile = validate_confirmed_profile(confirmed_profile)
        self._client.compare_and_set_resume(
            resume_id,
            user_id,
            {"needs_review"},
            {
                "status": "indexing",
                "confirmed_profile": normalized_profile,
                "confirmed_at": _utc_now_iso(),
                "review_required": False,
                "index_status": "pending",
                "failure_code": None,
                "failure_message": None,
                "failed_at": None,
                "last_error_at": None,
            },
            extraction_attempt=extraction_attempt,
        )
        generation_id = str(uuid4())
        stage = "build_chunks"
        inserted_generation = False
        try:
            chunks = self._build_resume_chunks(
                user_id=user_id,
                resume_id=resume_id,
                generation_id=generation_id,
                confirmed_profile=normalized_profile,
                extra_documents=self._supplemental_project_documents(
                    record=current,
                    confirmed_profile=normalized_profile,
                ),
            )
            stage = "insert_chunks"
            self._client.insert_resume_chunks(chunks)
            inserted_generation = True
            stage = "activate_resume"
            updated = self._client.activate_resume(
                user_id=user_id,
                resume_id=resume_id,
                extraction_attempt=extraction_attempt,
                generation_id=generation_id,
                confirmed_profile=normalized_profile,
            )
            self._prune_inactive_generations(user_id=user_id, resume_id=resume_id, active_generation_id=generation_id)
        except CloudResumeConflictError as exc:
            self._log_index_failure(stage, exc)
            if inserted_generation:
                self._discard_generation(user_id=user_id, resume_id=resume_id, generation_id=generation_id)
            raise
        except (CloudResumeError, ResumeIndexError) as exc:
            self._log_index_failure(stage, exc)
            if inserted_generation:
                self._discard_generation(user_id=user_id, resume_id=resume_id, generation_id=generation_id)
            self._mark_index_failed(
                resume_id=resume_id,
                user_id=user_id,
                extraction_attempt=extraction_attempt,
                code="indexing_failed",
                message=SAFE_FAILURE_MESSAGE,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc
        return ConfirmResult(
            resume_id=updated.id,
            status=updated.status,
            extraction_attempt=updated.extraction_attempt,
            confirmed_profile_saved=True,
            next_step="resume_ready",
            chunks_indexed=True,
            chunk_count=len(chunks),
            ready=updated.status == "ready",
            active=updated.is_active,
        )

    def retrieve_active_resume_chunks(
        self,
        *,
        user_id: str,
        question: str,
        category: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        current = self._client.get_current_resume(user_id)
        if not current or not current.active_chunk_generation:
            return {
                "retrieval_used": False,
                "retrieved_chunk_count": 0,
                "retrieved_chunks": [],
                "retrieval_ms": 0.0,
            }
        rows = self._client.get_active_resume_chunks(
            user_id=user_id,
            resume_id=current.id,
            generation_id=current.active_chunk_generation,
        )
        chunks = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            text = str(row.get("chunk_text") or "")
            chunks.append(
                {
                    "chunk_id": str(metadata.get("chunk_id") or row.get("id") or ""),
                    "source": str(metadata.get("source") or "cloud_resume"),
                    "section": str(row.get("section") or metadata.get("section") or ""),
                    "text": text,
                    "preview": str(metadata.get("preview") or text[:120]),
                    "tokens": list(metadata.get("tokens") or []),
                }
        )
        return self._indexer.retrieve_from_chunks(chunks, question=question, category=category, limit=limit)

    def retrieve_resume_chunks(
        self,
        *,
        user_id: str,
        resume_id: str,
        question: str,
        category: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        selected = self._client.get_resume(resume_id, user_id)
        if selected.status != "ready" or not selected.active_chunk_generation:
            raise CloudResumeValidationError("Selected resume is not ready for generation.")
        rows = self._client.get_active_resume_chunks(
            user_id=user_id,
            resume_id=selected.id,
            generation_id=selected.active_chunk_generation,
        )
        chunks = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            text = str(row.get("chunk_text") or "")
            chunks.append(
                {
                    "chunk_id": str(metadata.get("chunk_id") or row.get("id") or ""),
                    "source": str(metadata.get("source") or "cloud_resume"),
                    "section": str(row.get("section") or metadata.get("section") or ""),
                    "text": text,
                    "preview": str(metadata.get("preview") or text[:120]),
                    "tokens": list(metadata.get("tokens") or []),
                }
            )
        if not chunks:
            raise CloudResumeValidationError("Selected resume has no indexed chunks.")
        candidate_name, candidate_name_source = self._selected_resume_candidate_name(selected, chunks)
        specific_project_name = self._specific_project_name_from_question(question)
        project_intent = self._project_intent_detected(question) or bool(specific_project_name)
        if project_intent:
            project_focus = self._project_focus_chunks(
                chunks,
                question=question,
                limit=max(
                    int(limit or 1),
                    SPECIFIC_PROJECT_CONTEXT_LIMIT if specific_project_name else PROJECT_CONTEXT_LIMIT_FLOOR,
                ),
                specific_project_name=specific_project_name,
            )
            project_chunks = project_focus["chunks"]
            if not project_chunks:
                if specific_project_name:
                    raise CloudResumeValidationError("That specific project was not found in the selected resume.")
                raise CloudResumeValidationError(
                    "The selected resume is ready, but it does not contain enough project details to answer this accurately."
                )
            return {
                "retrieval_used": True,
                "retrieved_chunk_count": len(project_chunks),
                "retrieved_chunks": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "source": chunk["source"],
                        "section": chunk["section"],
                        "text": chunk["text"],
                        "preview": chunk["preview"],
                    }
                    for chunk in project_chunks
                ],
                "retrieval_ms": 0.0,
                "selected_resume_candidate_name": candidate_name,
                "selected_resume_candidate_name_source": candidate_name_source,
                "project_context_chunks_found": len(project_chunks),
                "project_context_source": str(project_focus.get("context_source") or "selected_resume_projects"),
                "specific_project_intent_detected": bool(project_focus.get("specific_project_intent_detected")),
                "matched_project_name": str(project_focus.get("matched_project_name") or ""),
                "project_match_confidence": str(project_focus.get("project_match_confidence") or "general"),
                "project_answer_mode": str(project_focus.get("project_answer_mode") or "general_projects"),
            }
        retrieval = self._indexer.retrieve_from_chunks(chunks, question=question, category=category, limit=limit)
        if retrieval.get("retrieved_chunks"):
            retrieval["selected_resume_candidate_name"] = candidate_name
            retrieval["selected_resume_candidate_name_source"] = candidate_name_source
            retrieval["project_context_chunks_found"] = 0
            retrieval["project_context_source"] = "selected_resume_general"
            retrieval["specific_project_intent_detected"] = False
            retrieval["matched_project_name"] = ""
            retrieval["project_match_confidence"] = "none"
            retrieval["project_answer_mode"] = "none"
            return retrieval
        fallback_chunks = chunks[: max(1, int(limit or 1))]
        return {
            "retrieval_used": True,
            "retrieved_chunk_count": len(fallback_chunks),
            "retrieved_chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "source": chunk["source"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "preview": chunk["preview"],
                }
                for chunk in fallback_chunks
            ],
            "retrieval_ms": retrieval.get("retrieval_ms", 0.0),
            "selected_resume_candidate_name": candidate_name,
            "selected_resume_candidate_name_source": candidate_name_source,
            "project_context_chunks_found": 0,
            "project_context_source": "selected_resume_general",
            "specific_project_intent_detected": False,
            "matched_project_name": "",
            "project_match_confidence": "none",
            "project_answer_mode": "none",
        }

    @staticmethod
    def _project_intent_detected(question: str) -> bool:
        return question_has_project_intent(question)

    def _project_focus_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        question: str,
        limit: int,
        specific_project_name: str = "",
    ) -> dict[str, Any]:
        query_tokens = set(re.findall(r"[a-z0-9]+", str(question or "").lower()))
        specific_normalized = self._normalize_project_name(specific_project_name)
        best_title = ""
        best_confidence = "none"
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for chunk in chunks:
            section = str(chunk.get("section") or "").strip().lower()
            text = str(chunk.get("text") or "")
            text_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
            all_tokens = text_tokens | {str(token).lower() for token in list(chunk.get("tokens") or [])}
            section_match = section in PROJECT_SECTION_NAMES
            keyword_hits = len(all_tokens & PROJECT_KEYWORDS)
            query_hits = len(all_tokens & query_tokens)
            if not section_match and keyword_hits <= 0:
                continue
            project_title = self._project_title_from_chunk(text)
            project_title_normalized = self._normalize_project_name(project_title)
            exact_match = bool(
                specific_normalized
                and project_title_normalized
                and (
                    project_title_normalized == specific_normalized
                    or specific_normalized in project_title_normalized
                    or project_title_normalized in specific_normalized
                )
            )
            partial_match = bool(
                specific_normalized
                and not exact_match
                and (
                    self._project_term_overlap(project_title_normalized, specific_normalized) >= 2
                    or self._project_term_overlap(self._normalize_project_name(text[:220]), specific_normalized) >= 2
                )
            )
            tech_match = bool(
                specific_normalized
                and not exact_match
                and not partial_match
                and self._project_term_overlap(self._normalize_project_name(text), specific_normalized) >= 1
            )
            score = (100 if section_match else 0) + (keyword_hits * 5) + query_hits
            if exact_match:
                score += 500
            elif partial_match:
                score += 250
            elif tech_match:
                score += 120
            confidence = "exact" if exact_match else "partial" if partial_match or tech_match else "general"
            if confidence in {"exact", "partial"} and project_title:
                if best_confidence not in {"exact", "partial"} or confidence == "exact":
                    best_title = project_title
                    best_confidence = confidence
            scored.append((score, confidence, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        if specific_normalized:
            matched_scored = [item for item in scored if item[1] in {"exact", "partial"}]
            if not matched_scored:
                return {
                    "chunks": [],
                    "specific_project_intent_detected": True,
                    "matched_project_name": "",
                    "project_match_confidence": "none",
                    "project_answer_mode": "insufficient_context",
                    "context_source": "insufficient",
                }
            selected_chunks = [chunk for _, _, chunk in matched_scored[: max(1, int(limit or 1))]]
            return {
                "chunks": selected_chunks,
                "specific_project_intent_detected": True,
                "matched_project_name": best_title or specific_project_name,
                "project_match_confidence": best_confidence if best_confidence in {"exact", "partial"} else "partial",
                "project_answer_mode": "detailed_specific_project",
                "context_source": "selected_resume_projects",
            }
        selected_chunks = [chunk for _, _, chunk in scored[: max(1, int(limit or 1))]]
        return {
            "chunks": selected_chunks,
            "specific_project_intent_detected": False,
            "matched_project_name": "",
            "project_match_confidence": "general" if selected_chunks else "none",
            "project_answer_mode": "general_projects" if selected_chunks else "insufficient_context",
            "context_source": "selected_resume_projects" if selected_chunks else "insufficient",
        }

    @staticmethod
    def _normalize_project_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    @staticmethod
    def _project_term_overlap(left: str, right: str) -> int:
        if not left or not right:
            return 0
        left_terms = {term for term in left.split() if len(term) > 2}
        right_terms = {term for term in right.split() if len(term) > 2}
        return len(left_terms & right_terms)

    @staticmethod
    def _project_title_from_chunk(text: str) -> str:
        first_line = str(text or "").splitlines()[0].strip(" \t:-|,")
        if not first_line:
            return ""
        if " - " in first_line:
            first_line = first_line.split(" - ", 1)[0].strip()
        if ":" in first_line and len(first_line.split(":", 1)[0].split()) <= 6:
            first_line = first_line.split(":", 1)[0].strip()
        return first_line[:120]

    def _specific_project_name_from_question(self, question: str) -> str:
        raw = str(question or "").strip()
        if not raw:
            return ""
        lead_match = PROJECT_SPECIFIC_LEAD_RE.match(raw)
        if not lead_match:
            return ""
        quoted = re.search(r'"([^"\r\n]{4,120})"|[\u201C]([^\u201D\r\n]{4,120})[\u201D]', raw)
        if quoted:
            return str(quoted.group(1) or quoted.group(2) or "").strip()
        trimmed = PROJECT_SPECIFIC_LEAD_RE.sub("", raw).strip(" ?!.,")
        trimmed = PROJECT_TRAILING_FILLER_RE.sub("", trimmed).strip(" ?!.,")
        if not trimmed:
            return ""
        if PROJECT_TECH_TERM_RE.search(trimmed) and len(trimmed.split()) <= 4:
            return ""
        if re.search(r"\b(it|this|that|them|those)\b", trimmed.lower()):
            return ""
        if len(trimmed.split()) >= 2 and re.search(r"[A-Z]", trimmed):
            return trimmed[:120]
        return ""
    def _selected_resume_candidate_name(
        self,
        selected: CloudResumeRecord,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, str]:
        metadata_name = str((selected.confirmed_profile or {}).get("full_name") or "").strip()
        if self._looks_like_candidate_name(metadata_name):
            return metadata_name, "metadata"
        for chunk in chunks:
            if str(chunk.get("section") or "").strip().lower() == "full_name":
                chunk_name = str(chunk.get("text") or "").strip()
                if self._looks_like_candidate_name(chunk_name):
                    return chunk_name, "metadata"
        for chunk in chunks[:2]:
            for line in str(chunk.get("text") or "").splitlines()[:2]:
                header_name = line.strip(" \t:-|,")
                if self._looks_like_candidate_name(header_name):
                    return header_name, "header"
        return "", "none"

    @staticmethod
    def _looks_like_candidate_name(value: str) -> bool:
        candidate = re.sub(r"\s+", " ", str(value or "").strip())
        if not 3 <= len(candidate) <= 80 or any(char.isdigit() for char in candidate):
            return False
        lowered = candidate.lower()
        if any(word in lowered for word in ("resume", "curriculum", "developer", "engineer", "student", "skills")):
            return False
        words = candidate.split()
        if not 2 <= len(words) <= 5:
            return False
        return all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", word) for word in words)

    def _discard_generation(self, *, user_id: str, resume_id: str, generation_id: str) -> None:
        try:
            self._client.delete_resume_chunks(user_id=user_id, resume_id=resume_id, generation_id=generation_id)
        except CloudResumeError:
            logger.warning(
                "Could not discard inactive cloud resume chunk generation: user_id=%s resume_id=%s generation_id=%s",
                user_id,
                resume_id,
                generation_id,
            )

    def _prune_inactive_generations(self, *, user_id: str, resume_id: str, active_generation_id: str) -> None:
        try:
            self._client.delete_inactive_resume_chunks(
                user_id=user_id,
                resume_id=resume_id,
                active_generation_id=active_generation_id,
            )
        except CloudResumeError:
            logger.warning(
                "Could not prune inactive cloud resume chunk generations: user_id=%s resume_id=%s active_generation_id=%s",
                user_id,
                resume_id,
                active_generation_id,
            )

    def _build_resume_chunks(
        self,
        *,
        user_id: str,
        resume_id: str,
        generation_id: str,
        confirmed_profile: dict[str, Any],
        extra_documents: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        documents = []
        for field in CLOUD_INDEX_PROFILE_FIELDS:
            value = str(confirmed_profile.get(field) or "").strip()
            if value:
                documents.append({"section": field, "text": value})
        for document in extra_documents or []:
            section = str(document.get("section") or "").strip()
            text = str(document.get("text") or "").strip()
            if section and text:
                documents.append({"section": section, "text": text})
        chunks = self._indexer.build_chunks_from_documents(documents)
        if not chunks:
            raise ResumeIndexError("Could not build cloud resume chunks from the confirmed profile.")
        rows = []
        for chunk in chunks:
            rows.append(
                {
                    "user_id": user_id,
                    "resume_id": resume_id,
                    "section": chunk["section"],
                    "chunk_text": chunk["text"],
                    "embedding": None,
                    "generation_id": generation_id,
                    "metadata": {
                        "chunk_id": chunk["chunk_id"],
                        "source": "cloud_resume",
                        "section": chunk["section"],
                        "preview": chunk["preview"],
                        "tokens": chunk.get("tokens", []),
                    },
                }
            )
        return rows

    def _supplemental_project_documents(
        self,
        *,
        record: CloudResumeRecord,
        confirmed_profile: dict[str, Any],
    ) -> list[dict[str, str]]:
        raw_text = self._load_resume_text_for_index(record)
        if not raw_text:
            return []
        existing_lines = {
            re.sub(r"\s+", " ", line.strip().lower())
            for field in PROJECT_INDEX_FIELDS
            for line in str(confirmed_profile.get(field) or "").splitlines()
            if line.strip()
        }
        documents: list[dict[str, str]] = []
        for section, text in self._project_documents_from_resume_text(raw_text).items():
            lines = []
            for line in text.splitlines():
                normalized = re.sub(r"\s+", " ", line.strip().lower())
                if not normalized or normalized in existing_lines:
                    continue
                existing_lines.add(normalized)
                lines.append(line.strip())
            if lines:
                documents.append({"section": section, "text": "\n".join(lines)})
        return documents

    def _load_resume_text_for_index(self, record: CloudResumeRecord) -> str:
        try:
            content = self._client.download_resume_object(record.storage_path)
        except CloudResumeError as exc:
            logger.warning(
                "Could not load resume text for index enrichment resume_id=%s user_id=%s error_type=%s",
                record.id,
                record.user_id,
                type(exc).__name__,
            )
            return ""
        resume_service = getattr(self._parser, "resume_service", None)
        if resume_service is not None and hasattr(resume_service, "extract_text"):
            try:
                return str(resume_service.extract_text(filename=record.original_filename, content=content) or "")
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning(
                    "Could not extract resume text for index enrichment resume_id=%s user_id=%s error_type=%s",
                    record.id,
                    record.user_id,
                    type(exc).__name__,
                )
                return ""
        try:
            parsed = self._parser.extract_profile(filename=record.original_filename, content=content)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "Could not parse resume for index enrichment resume_id=%s user_id=%s error_type=%s",
                record.id,
                record.user_id,
                type(exc).__name__,
            )
            return ""
        profile = parsed.get("profile") if isinstance(parsed, dict) else {}
        return str((profile or {}).get("raw_resume_text") or "")

    def _project_documents_from_resume_text(self, raw_text: str) -> dict[str, str]:
        buffers: dict[str, list[str]] = {"projects": [], "work_experience": []}
        current_section = ""
        for raw_line in str(raw_text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line.strip())
            if not line:
                continue
            matched_section = next(
                (section for section, pattern in PROJECT_HEADING_PATTERNS if pattern.fullmatch(line)),
                "",
            )
            if matched_section:
                current_section = matched_section
                continue
            if RESUME_SECTION_STOP_RE.fullmatch(line):
                current_section = ""
                continue
            if current_section:
                buffers[current_section].append(line)
                continue
            if re.search(r"\b(project|projects?)\b", line, re.IGNORECASE) and re.search(
                r"\b(built|developed|implemented|created|designed|rag|langchain|fastapi|api|chroma|embedding|vector)\b",
                line,
                re.IGNORECASE,
            ):
                buffers["projects"].append(line)
        return {section: "\n".join(lines[:8]) for section, lines in buffers.items() if lines}

    def _mark_failed(
        self,
        *,
        resume_id: str,
        user_id: str,
        code: str,
        message: str,
        extraction_attempt: int | None = None,
    ) -> None:
        payload = {
            "status": "failed",
            "is_active": False,
            "parser_status": "failed",
            "extraction_status": "failed",
            "failure_code": code,
            "failure_message": message,
            "failed_at": _utc_now_iso(),
            "last_error_at": _utc_now_iso(),
        }
        try:
            if extraction_attempt is None:
                self._client.update_resume(resume_id, user_id, payload)
            else:
                self._client.compare_and_set_resume(
                    resume_id,
                    user_id,
                    {"extracting"},
                    payload,
                    extraction_attempt=extraction_attempt,
                )
        except CloudResumeError:
            logger.warning(
                "Could not persist safe cloud resume failure state resume_id=%s user_id=%s code=%s",
                resume_id,
                user_id,
                code,
            )

    def _mark_index_failed(
        self,
        *,
        resume_id: str,
        user_id: str,
        extraction_attempt: int,
        code: str,
        message: str,
    ) -> None:
        payload = {
            "status": "failed",
            "is_active": False,
            "index_status": "failed",
            "failure_code": code,
            "failure_message": message,
            "failed_at": _utc_now_iso(),
            "last_error_at": _utc_now_iso(),
        }
        try:
            self._client.compare_and_set_resume(
                resume_id,
                user_id,
                {"indexing"},
                payload,
                extraction_attempt=extraction_attempt,
            )
        except CloudResumeError:
            logger.warning(
                "Could not persist safe cloud resume indexing failure state resume_id=%s user_id=%s code=%s",
                resume_id,
                user_id,
                code,
            )

    def _log_extract_failure(self, stage: str, exc: Exception) -> None:
        logger.warning("Cloud resume extraction failed stage=%s error_type=%s", stage, type(exc).__name__)

    def _log_index_failure(self, stage: str, exc: Exception) -> None:
        logger.warning("Cloud resume indexing failed stage=%s error_type=%s", stage, type(exc).__name__)
