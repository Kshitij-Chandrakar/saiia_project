from functools import lru_cache
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeError,
    CloudResumeNotFoundError,
    CloudResumeRecord,
    ResumeReadiness,
    CloudResumeService,
    CloudResumeValidationError,
)
from app.cloud.supabase_config import SupabaseConfigurationError
from app.services.resume_service import MAX_RESUME_FILE_BYTES

router = APIRouter()
logger = logging.getLogger("cloud_resume_api")


class CloudResumeResponse(BaseModel):
    id: str
    storage_path: str
    original_filename: str
    mime_type: str
    file_size: int
    status: str
    is_active: bool
    extraction_attempt: int
    parser_provider: str
    parser_status: str
    extraction_status: str
    index_status: str
    review_required: bool
    confirmed_at: str | None = None
    active_chunk_generation: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    failed_at: str | None = None
    last_error_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CurrentResumeResponse(BaseModel):
    ready: bool
    resume: CloudResumeResponse | None = None


class CloudResumeListItem(BaseModel):
    id: str
    display_name: str
    original_filename: str
    status: str
    index_status: str
    is_active: bool
    created_at: str | None = None
    uploaded_at: str | None = None
    updated_at: str | None = None
    chunk_count: int | None = None
    can_generate: bool = False
    readiness_reason: str = "unknown"


class CloudResumeListResponse(BaseModel):
    items: list[CloudResumeListItem]


class ReviewCandidateResponse(BaseModel):
    has_candidate: bool
    resume: CloudResumeResponse | None = None


class ExtractResponse(BaseModel):
    resume_id: str
    status: str
    extraction_attempt: int
    parser_provider: str
    fallback_used: bool
    missing_fields: list[str]
    review_required: bool
    profile: dict[str, Any]
    extracted_text_length: int


class ConfirmRequest(BaseModel):
    extraction_attempt: int
    profile: dict[str, Any]


class ConfirmResponse(BaseModel):
    resume_id: str
    status: str
    extraction_attempt: int
    confirmed_profile_saved: bool
    next_step: str
    chunks_indexed: bool = False
    chunk_count: int = 0
    ready: bool = False
    active: bool = False


class DeleteResumeResponse(BaseModel):
    resume_id: str
    status: str
    is_active: bool
    ready: bool
    message: str


class RebuildIndexResponse(BaseModel):
    resume_id: str
    status: str
    index_status: str
    active_chunk_generation: str
    chunk_count: int
    message: str


@lru_cache(maxsize=1)
def _cached_cloud_resume_service() -> CloudResumeService:
    return CloudResumeService()


def get_cloud_resume_service() -> CloudResumeService:
    try:
        return _cached_cloud_resume_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


CloudResumeServiceDep = Annotated[CloudResumeService, Depends(get_cloud_resume_service)]


def _resume_response(record: CloudResumeRecord) -> CloudResumeResponse:
    return CloudResumeResponse(
        id=record.id,
        storage_path=record.storage_path,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        file_size=record.file_size,
        status=record.status,
        is_active=record.is_active,
        extraction_attempt=record.extraction_attempt,
        parser_provider=record.parser_provider,
        parser_status=record.parser_status,
        extraction_status=record.extraction_status,
        index_status=record.index_status,
        review_required=record.review_required,
        confirmed_at=record.confirmed_at,
        active_chunk_generation=record.active_chunk_generation,
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        failed_at=record.failed_at,
        last_error_at=record.last_error_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _resume_list_item(record: CloudResumeRecord, readiness: ResumeReadiness | None = None) -> CloudResumeListItem:
    display_name = record.original_filename.strip() or "Uploaded resume"
    return CloudResumeListItem(
        id=record.id,
        display_name=display_name,
        original_filename=record.original_filename,
        status=record.status,
        index_status=record.index_status,
        is_active=record.is_active,
        created_at=record.created_at,
        uploaded_at=record.created_at,
        updated_at=record.updated_at,
        chunk_count=readiness.chunk_count if readiness else None,
        can_generate=bool(readiness.can_generate) if readiness else False,
        readiness_reason=readiness.readiness_reason if readiness else "unknown",
    )


def _handle_cloud_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SupabaseConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase cloud configuration is not ready.",
        )
    if isinstance(exc, CloudResumeValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, CloudResumeNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume was not found.")
    if isinstance(exc, CloudResumeConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not isinstance(exc, CloudResumeError):
        logger.exception("Unexpected cloud resume route failure", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Supabase cloud resume operation failed.",
    )


def _safe_profile_response(profile: dict[str, Any]) -> dict[str, Any]:
    safe_profile = dict(profile)
    safe_profile.pop("raw_resume_text", None)
    return safe_profile


@router.post("", response_model=CloudResumeResponse, status_code=status.HTTP_201_CREATED)
def upload_cloud_resume(
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
    file: UploadFile = File(...),
) -> CloudResumeResponse:
    try:
        if file.size is not None and file.size > MAX_RESUME_FILE_BYTES:
            raise CloudResumeValidationError("Resume file is too large. Please upload a file under 5 MB.")
        content = file.file.read(MAX_RESUME_FILE_BYTES + 1)
        result = service.upload_resume(
            user_id=current_user.user_id,
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _resume_response(result.resume)


@router.get("", response_model=CloudResumeListResponse)
def list_cloud_resumes(current_user: CurrentUserDep, service: CloudResumeServiceDep) -> CloudResumeListResponse:
    try:
        records = service.list_resumes(current_user.user_id)
        items = [
            _resume_list_item(
                record,
                service.get_resume_readiness(user_id=current_user.user_id, record=record),
            )
            for record in records
        ]
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return CloudResumeListResponse(items=items)


@router.get("/current", response_model=CurrentResumeResponse)
def get_current_cloud_resume(current_user: CurrentUserDep, service: CloudResumeServiceDep) -> CurrentResumeResponse:
    try:
        record = service.get_current_resume(current_user.user_id)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return CurrentResumeResponse(ready=record is not None, resume=_resume_response(record) if record else None)


@router.get("/review-candidate", response_model=ReviewCandidateResponse)
def get_review_candidate(current_user: CurrentUserDep, service: CloudResumeServiceDep) -> ReviewCandidateResponse:
    try:
        record = service.get_review_candidate(current_user.user_id)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return ReviewCandidateResponse(has_candidate=record is not None, resume=_resume_response(record) if record else None)


@router.get("/{resume_id}/status", response_model=CloudResumeResponse)
def get_cloud_resume_status(
    resume_id: UUID,
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
) -> CloudResumeResponse:
    try:
        record = service.get_status(user_id=current_user.user_id, resume_id=str(resume_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _resume_response(record)


@router.delete("/{resume_id}", response_model=DeleteResumeResponse)
def delete_cloud_resume(
    resume_id: UUID,
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
) -> DeleteResumeResponse:
    try:
        result = service.delete_resume(user_id=current_user.user_id, resume_id=str(resume_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return DeleteResumeResponse(
        resume_id=result.resume_id,
        status=result.status,
        is_active=result.is_active,
        ready=result.ready,
        message=result.message,
    )


@router.post("/{resume_id}/rebuild-index", response_model=RebuildIndexResponse)
def rebuild_cloud_resume_index(
    resume_id: UUID,
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
) -> RebuildIndexResponse:
    try:
        result = service.rebuild_resume_index(user_id=current_user.user_id, resume_id=str(resume_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return RebuildIndexResponse(
        resume_id=result.resume_id,
        status=result.status,
        index_status=result.index_status,
        active_chunk_generation=result.active_chunk_generation,
        chunk_count=result.chunk_count,
        message=result.message,
    )


@router.post("/{resume_id}/extract", response_model=ExtractResponse)
def extract_cloud_resume(
    resume_id: UUID,
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
) -> ExtractResponse:
    try:
        result = service.extract_resume(user_id=current_user.user_id, resume_id=str(resume_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return ExtractResponse(
        resume_id=result.resume_id,
        status=result.status,
        extraction_attempt=result.extraction_attempt,
        parser_provider=result.parser_provider,
        fallback_used=result.fallback_used,
        missing_fields=result.missing_fields,
        review_required=result.review_required,
        profile=_safe_profile_response(result.profile),
        extracted_text_length=result.extracted_text_length,
    )


@router.post("/{resume_id}/confirm", response_model=ConfirmResponse)
def confirm_cloud_resume(
    resume_id: UUID,
    payload: ConfirmRequest,
    current_user: CurrentUserDep,
    service: CloudResumeServiceDep,
) -> ConfirmResponse:
    try:
        result = service.confirm_resume(
            user_id=current_user.user_id,
            resume_id=str(resume_id),
            extraction_attempt=payload.extraction_attempt,
            confirmed_profile=payload.profile,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return ConfirmResponse(
        resume_id=result.resume_id,
        status=result.status,
        extraction_attempt=result.extraction_attempt,
        confirmed_profile_saved=result.confirmed_profile_saved,
        next_step=result.next_step,
        chunks_indexed=result.chunks_indexed,
        chunk_count=result.chunk_count,
        ready=result.ready,
        active=result.active,
    )
