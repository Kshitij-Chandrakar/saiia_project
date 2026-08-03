from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import mimetypes
from pathlib import PurePath
import re
from typing import Any, NoReturn
from uuid import uuid4

import requests

from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.nlp.answer_generator import ProviderError
from app.services.resume_parser_service import ResumeParserService
from app.services.resume_service import MAX_RESUME_FILE_BYTES, ResumeExtractionError

logger = logging.getLogger("cloud_resume")

ALLOWED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
RETRY_EXTRACT_STATUSES = {"uploaded", "failed", "timeout", "cancelled", "needs_review"}
SAFE_FAILURE_MESSAGE = "Resume processing failed. Please try again."


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
        failure_code=payload.get("failure_code"),
        failure_message=payload.get("failure_message"),
        failed_at=payload.get("failed_at"),
        last_error_at=payload.get("last_error_at"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_resume_filename(filename: str) -> str:
    basename = PurePath(str(filename or "").replace("\\", "/")).name.strip()
    basename = re.sub(r"[\x00-\x1f\x7f]+", "", basename)
    basename = re.sub(r"[^A-Za-z0-9._ -]+", "_", basename)
    basename = re.sub(r"\s+", " ", basename).strip(" .")
    if not basename or basename in {".", ".."}:
        raise CloudResumeValidationError("Invalid resume filename.")
    if PurePath(basename).suffix.lower() not in ALLOWED_MIME_TYPES:
        raise CloudResumeValidationError("Unsupported resume file type. Please upload a PDF, DOCX, or TXT resume.")
    return basename[:120]


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
        self._headers = {
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_body(self, response: requests.Response) -> str:
        return response.text[:500].replace(self._service_role_key, "[redacted]")

    def _log_failure(self, target: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase cloud resume failure: target=%s operation=%s status=%s body=%s",
            target,
            operation,
            response.status_code,
            self._safe_body(response),
        )

    def _raise_response(self, target: str, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(target, operation, response)
        raise CloudResumeError("Supabase cloud resume operation failed.")

    def _raise_request(self, target: str, operation: str, exc: requests.RequestException) -> NoReturn:
        logger.error(
            "Supabase cloud resume failure: target=%s operation=%s status=request_error body=%s",
            target,
            operation,
            str(exc)[:500].replace(self._service_role_key, "[redacted]"),
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

    def get_review_candidate(self, user_id: str) -> CloudResumeRecord | None:
        rows = self._select_resumes(
            {
                "user_id": f"eq.{user_id}",
                "status": "eq.needs_review",
                "order": "updated_at.desc",
                "limit": "1",
            }
        )
        return rows[0] if rows else None

    def _select_resumes(self, params: dict[str, str]) -> list[CloudResumeRecord]:
        try:
            response = self._session.get(
                f"{self._rest_url}/resumes",
                headers=self._headers,
                params={"select": "*", **params},
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_request("resumes", "select", exc)
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


class CloudResumeService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        parser: ResumeParserService | None = None,
    ) -> None:
        self._client = client or SupabaseCloudResumeClient()
        self._parser = parser or ResumeParserService()

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

    def get_review_candidate(self, user_id: str) -> CloudResumeRecord | None:
        return self._client.get_review_candidate(user_id)

    def get_status(self, *, user_id: str, resume_id: str) -> CloudResumeRecord:
        return self._client.get_resume(resume_id, user_id)

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
            parsed = self._parser.extract_profile(filename=extracting.original_filename, content=content)
        except (ResumeExtractionError, ProviderError, CloudResumeError) as exc:
            self._mark_failed(
                resume_id=resume_id,
                user_id=user_id,
                code="extraction_failed",
                message=SAFE_FAILURE_MESSAGE,
                extraction_attempt=attempt,
            )
            raise CloudResumeError(SAFE_FAILURE_MESSAGE) from exc

        profile = dict(parsed.get("profile") or {})
        updated = self._client.compare_and_set_resume(
            resume_id,
            user_id,
            {"extracting"},
            {
                "status": "needs_review",
                "extraction_status": "needs_review",
                "parser_status": "completed",
                "parser_provider": parsed.get("parser_provider") or "local",
                "review_required": bool(parsed.get("review_required")),
            },
            extraction_attempt=attempt,
        )
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
        if not isinstance(confirmed_profile, dict) or not confirmed_profile:
            raise CloudResumeValidationError("Confirmed profile is required.")
        updated = self._client.compare_and_set_resume(
            resume_id,
            user_id,
            {"needs_review"},
            {
                "confirmed_profile": confirmed_profile,
                "confirmed_at": _utc_now_iso(),
                "review_required": False,
            },
            extraction_attempt=extraction_attempt,
        )
        return ConfirmResult(
            resume_id=updated.id,
            status=updated.status,
            extraction_attempt=updated.extraction_attempt,
            confirmed_profile_saved=True,
            next_step="index_resume",
        )

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
