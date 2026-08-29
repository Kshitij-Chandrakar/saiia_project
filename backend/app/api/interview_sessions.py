from functools import lru_cache
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.interview_sessions import (
    CloudInterviewSessionConflictError,
    CloudInterviewSessionError,
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionRecord,
    CloudInterviewSessionService,
    CloudInterviewSessionValidationError,
    CreateInterviewSessionResult,
    InterviewSessionListPage,
)
from app.cloud.supabase_config import SupabaseConfigurationError

router = APIRouter()
logger = logging.getLogger("cloud_interview_session_api")


class InterviewSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    selected_resume_id: str | None = None
    job_context_id: str | None = None
    target_role: str = ""
    company_name: str = ""
    job_description: str = ""


class InterviewSessionResponse(BaseModel):
    id: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    selected_resume_id: str | None = None
    job_context_id: str | None = None
    title: str | None = None
    target_role: str | None = None
    company_name: str | None = None
    job_description_preview: str | None = None


class InterviewSessionListResponse(BaseModel):
    items: list[InterviewSessionResponse]
    limit: int
    page: int


class InterviewSessionCreateResponse(BaseModel):
    session: InterviewSessionResponse
    replayed: bool


@lru_cache(maxsize=1)
def _cached_cloud_interview_session_service() -> CloudInterviewSessionService:
    return CloudInterviewSessionService()


def get_cloud_interview_session_service() -> CloudInterviewSessionService:
    try:
        return _cached_cloud_interview_session_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


CloudInterviewSessionServiceDep = Annotated[CloudInterviewSessionService, Depends(get_cloud_interview_session_service)]


def _session_response(record: CloudInterviewSessionRecord) -> InterviewSessionResponse:
    return InterviewSessionResponse(
        id=record.id,
        status=record.status,
        started_at=record.started_at,
        ended_at=record.ended_at,
        selected_resume_id=record.selected_resume_id,
        job_context_id=record.job_context_id,
        title=record.title,
        target_role=record.target_role,
        company_name=record.company_name,
        job_description_preview=record.job_description_preview,
    )


def _handle_cloud_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SupabaseConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase cloud configuration is not ready.",
        )
    if isinstance(exc, CloudInterviewSessionValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, CloudInterviewSessionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc) or "Interview session was not found.")
    if isinstance(exc, CloudInterviewSessionConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not isinstance(exc, CloudInterviewSessionError):
        logger.exception("Unexpected cloud interview session route failure", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Supabase cloud interview session operation failed.",
    )


@router.get("", response_model=InterviewSessionListResponse)
def list_interview_sessions(
    current_user: CurrentUserDep,
    service: CloudInterviewSessionServiceDep,
    limit: int = 20,
    page: int = 1,
) -> InterviewSessionListResponse:
    try:
        result: InterviewSessionListPage = service.list_sessions(user_id=current_user.user_id, limit=limit, page=page)
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return InterviewSessionListResponse(
        items=[_session_response(record) for record in result.items],
        limit=result.limit,
        page=result.page,
    )


@router.post("", response_model=InterviewSessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_interview_session(
    payload: InterviewSessionCreateRequest,
    current_user: CurrentUserDep,
    service: CloudInterviewSessionServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InterviewSessionCreateResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )
    try:
        result: CreateInterviewSessionResult = service.create_session(
            user_id=current_user.user_id,
            payload=payload.model_dump(exclude_none=True),
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return InterviewSessionCreateResponse(session=_session_response(result.record), replayed=result.replayed)


@router.get("/{session_id}", response_model=InterviewSessionResponse)
def get_interview_session(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewSessionServiceDep,
) -> InterviewSessionResponse:
    try:
        record = service.get_session(user_id=current_user.user_id, session_id=str(session_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _session_response(record)


@router.post("/{session_id}/end", response_model=InterviewSessionResponse)
def end_interview_session(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewSessionServiceDep,
) -> InterviewSessionResponse:
    try:
        record = service.end_session(user_id=current_user.user_id, session_id=str(session_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _session_response(record)
