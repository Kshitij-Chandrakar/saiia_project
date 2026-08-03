from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeError,
    CloudResumeNotFoundError,
    CloudResumeRecord,
    CloudResumeService,
    CloudResumeValidationError,
)
from app.cloud.supabase_config import SupabaseConfigurationError

router = APIRouter()


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
    failure_code: str | None = None
    failure_message: str | None = None
    failed_at: str | None = None
    last_error_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CurrentResumeResponse(BaseModel):
    ready: bool
    resume: CloudResumeResponse | None = None


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


def get_cloud_resume_service() -> CloudResumeService:
    return CloudResumeService()


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
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        failed_at=record.failed_at,
        last_error_at=record.last_error_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
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
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Supabase cloud resume operation failed.",
    )


@router.post("", response_model=CloudResumeResponse, status_code=status.HTTP_201_CREATED)
async def upload_cloud_resume(current_user: CurrentUserDep, file: UploadFile = File(...)) -> CloudResumeResponse:
    try:
        content = await file.read()
        result = get_cloud_resume_service().upload_resume(
            user_id=current_user.user_id,
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _resume_response(result.resume)


@router.get("/current", response_model=CurrentResumeResponse)
def get_current_cloud_resume(current_user: CurrentUserDep) -> CurrentResumeResponse:
    try:
        record = get_cloud_resume_service().get_current_resume(current_user.user_id)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return CurrentResumeResponse(ready=record is not None, resume=_resume_response(record) if record else None)


@router.get("/review-candidate", response_model=ReviewCandidateResponse)
def get_review_candidate(current_user: CurrentUserDep) -> ReviewCandidateResponse:
    try:
        record = get_cloud_resume_service().get_review_candidate(current_user.user_id)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return ReviewCandidateResponse(has_candidate=record is not None, resume=_resume_response(record) if record else None)


@router.get("/{resume_id}/status", response_model=CloudResumeResponse)
def get_cloud_resume_status(resume_id: str, current_user: CurrentUserDep) -> CloudResumeResponse:
    try:
        record = get_cloud_resume_service().get_status(user_id=current_user.user_id, resume_id=resume_id)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _resume_response(record)


@router.post("/{resume_id}/extract", response_model=ExtractResponse)
def extract_cloud_resume(resume_id: str, current_user: CurrentUserDep) -> ExtractResponse:
    try:
        result = get_cloud_resume_service().extract_resume(user_id=current_user.user_id, resume_id=resume_id)
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
        profile=result.profile,
        extracted_text_length=result.extracted_text_length,
    )


@router.post("/{resume_id}/confirm", response_model=ConfirmResponse)
def confirm_cloud_resume(
    resume_id: str,
    payload: ConfirmRequest,
    current_user: CurrentUserDep,
) -> ConfirmResponse:
    try:
        result = get_cloud_resume_service().confirm_resume(
            user_id=current_user.user_id,
            resume_id=resume_id,
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
    )
