from functools import lru_cache
import json
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.cloud_job_context import (
    CloudJobContextConflictError,
    CloudJobContextError,
    CloudJobContextExtractResult,
    CloudJobContextNotFoundError,
    CloudJobContextRateLimitError,
    CloudJobContextRecord,
    CloudJobContextService,
    CloudJobContextValidationError,
    CreateJobContextResult,
    DeleteJobContextResult,
    JobContextListPage,
    MAX_JSON_BODY_BYTES,
    MAX_MULTIPART_BODY_BYTES,
    MAX_RESUME_FILE_BYTES,
    job_description_preview,
    validate_idempotency_key,
)
from app.cloud.supabase_config import SupabaseConfigurationError

router = APIRouter()
logger = logging.getLogger("cloud_job_context_api")


class CloudJobContextCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = ""
    position: str = ""
    job_description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    seniority: str = ""
    domain_keywords: list[str] = Field(default_factory=list)
    location: str = ""
    employment_type: str = ""
    activate: bool = False
    extraction_receipt_id: str | None = None


class CloudJobContextPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str | None = None
    position: str | None = None
    job_description: str | None = None
    required_skills: list[str] | None = None
    responsibilities: list[str] | None = None
    seniority: str | None = None
    domain_keywords: list[str] | None = None
    location: str | None = None
    employment_type: str | None = None
    extraction_receipt_id: str | None = None


class CloudJobContextSummaryResponse(BaseModel):
    id: str
    company: str
    position: str
    job_description_preview: str
    job_description_length: int
    required_skills: list[str]
    responsibilities: list[str]
    seniority: str
    domain_keywords: list[str]
    location: str
    employment_type: str
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


class CloudJobContextDetailResponse(CloudJobContextSummaryResponse):
    job_description: str
    source_file_metadata: dict[str, Any]


class CloudJobContextListResponse(BaseModel):
    items: list[CloudJobContextSummaryResponse]
    active_id: str | None
    limit: int
    next_cursor: str | None


class CloudJobContextCreateResponse(BaseModel):
    job_context: CloudJobContextSummaryResponse
    replayed: bool
    activated: bool


class DeleteJobContextResponse(BaseModel):
    job_context_id: str
    deleted: bool
    active_id: str | None


class ExtractJobContextResponse(BaseModel):
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


@lru_cache(maxsize=1)
def _cached_cloud_job_context_service() -> CloudJobContextService:
    return CloudJobContextService()


def get_cloud_job_context_service() -> CloudJobContextService:
    try:
        return _cached_cloud_job_context_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


CloudJobContextServiceDep = Annotated[CloudJobContextService, Depends(get_cloud_job_context_service)]


def _summary_response(record: CloudJobContextRecord) -> CloudJobContextSummaryResponse:
    return CloudJobContextSummaryResponse(
        id=record.id,
        company=record.company,
        position=record.position,
        job_description_preview=job_description_preview(record.job_description),
        job_description_length=len(record.job_description),
        required_skills=record.required_skills,
        responsibilities=record.responsibilities,
        seniority=record.seniority,
        domain_keywords=record.domain_keywords,
        location=record.location,
        employment_type=record.employment_type,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _detail_response(record: CloudJobContextRecord) -> CloudJobContextDetailResponse:
    return CloudJobContextDetailResponse(
        **_summary_response(record).model_dump(),
        job_description=record.job_description,
        source_file_metadata=record.source_file_metadata,
    )


def _extract_response(result: CloudJobContextExtractResult) -> ExtractJobContextResponse:
    return ExtractJobContextResponse(**result.__dict__)


def _handle_cloud_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SupabaseConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase cloud configuration is not ready.",
        )
    if isinstance(exc, CloudJobContextValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, CloudJobContextNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job context was not found.")
    if isinstance(exc, CloudJobContextRateLimitError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Job description extraction quota exceeded.")
    if isinstance(exc, CloudJobContextConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not isinstance(exc, CloudJobContextError):
        logger.exception("Unexpected cloud job context route failure", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Supabase cloud job context operation failed.",
    )


def _enforce_json_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    try:
        if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
            raise CloudJobContextValidationError("Request body is too large.")
    except ValueError as exc:
        raise CloudJobContextValidationError("Invalid Content-Length header.") from exc


def _enforce_multipart_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    try:
        if content_length and int(content_length) > MAX_MULTIPART_BODY_BYTES:
            raise CloudJobContextValidationError("Multipart request body is too large.")
    except ValueError as exc:
        raise CloudJobContextValidationError("Invalid Content-Length header.") from exc


@router.get("", response_model=CloudJobContextListResponse)
def list_job_contexts(
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
    limit: int = 20,
    cursor: str | None = None,
) -> CloudJobContextListResponse:
    try:
        page: JobContextListPage = service.list_contexts(user_id=current_user.user_id, limit=limit, cursor=cursor)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return CloudJobContextListResponse(
        items=[_summary_response(record) for record in page.items],
        active_id=page.active_id,
        limit=page.limit,
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=CloudJobContextCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job_context(
    request: Request,
    payload: CloudJobContextCreateRequest,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
    _body_size_guard: Annotated[None, Depends(_enforce_json_size)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CloudJobContextCreateResponse:
    try:
        validated_key = validate_idempotency_key(idempotency_key)
        result: CreateJobContextResult = service.create_context(
            user_id=current_user.user_id,
            payload=payload.model_dump(exclude_none=True),
            idempotency_key=validated_key,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return CloudJobContextCreateResponse(
        job_context=_summary_response(result.record),
        replayed=result.replayed,
        activated=result.activated,
    )


@router.post("/extract", response_model=ExtractJobContextResponse)
async def extract_job_context(
    request: Request,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
    _body_size_guard: Annotated[None, Depends(_enforce_multipart_size)],
    job_description_text: str = Form(""),
    provider_processing_consent: bool = Form(False),
    source_file_metadata: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> ExtractJobContextResponse:
    try:
        if not provider_processing_consent:
            raise CloudJobContextValidationError("Provider-processing consent is required for extraction.")
        if source_file_metadata is not None:
            raise CloudJobContextValidationError("Source file metadata is server-derived and cannot be submitted.")
        if file is not None and job_description_text.strip():
            raise CloudJobContextValidationError("Provide either a file or job_description_text, not both.")
        if file is None and not job_description_text.strip():
            raise CloudJobContextValidationError("Job description text or file is required.")
        if file is not None:
            if file.size is not None and file.size > MAX_RESUME_FILE_BYTES:
                raise CloudJobContextValidationError("Job description file is too large. Please upload a file under 5 MB.")
            content = await file.read(MAX_RESUME_FILE_BYTES + 1)
            result = service.extract_from_file(
                user_id=current_user.user_id,
                filename=file.filename or "",
                content=content,
                content_type=file.content_type,
            )
        else:
            result = service.extract_from_text(
                user_id=current_user.user_id,
                job_description_text=job_description_text,
            )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    response = _extract_response(result)
    json.dumps(response.model_dump(), ensure_ascii=False)
    return response


@router.get("/{job_context_id}", response_model=CloudJobContextDetailResponse)
def get_job_context(
    job_context_id: UUID,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
) -> CloudJobContextDetailResponse:
    try:
        record = service.get_context(user_id=current_user.user_id, job_context_id=str(job_context_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _detail_response(record)


@router.patch("/{job_context_id}", response_model=CloudJobContextSummaryResponse)
async def update_job_context(
    request: Request,
    job_context_id: UUID,
    payload: CloudJobContextPatchRequest,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
    _body_size_guard: Annotated[None, Depends(_enforce_json_size)],
) -> CloudJobContextSummaryResponse:
    try:
        record = service.update_context(
            user_id=current_user.user_id,
            job_context_id=str(job_context_id),
            payload=payload.model_dump(exclude_none=True),
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _summary_response(record)


@router.delete("/{job_context_id}", response_model=DeleteJobContextResponse)
def delete_job_context(
    job_context_id: UUID,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
) -> DeleteJobContextResponse:
    try:
        result: DeleteJobContextResult = service.delete_context(
            user_id=current_user.user_id,
            job_context_id=str(job_context_id),
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return DeleteJobContextResponse(**result.__dict__)


@router.post("/{job_context_id}/activate", response_model=CloudJobContextSummaryResponse)
def activate_job_context(
    job_context_id: UUID,
    current_user: CurrentUserDep,
    service: CloudJobContextServiceDep,
) -> CloudJobContextSummaryResponse:
    try:
        record = service.activate_context(user_id=current_user.user_id, job_context_id=str(job_context_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _summary_response(record)
