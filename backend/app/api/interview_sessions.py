from functools import lru_cache
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

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
from app.cloud.interview_notes import (
    CloudInterviewNotesRecord,
    CloudInterviewNotesService,
    NOTES_GENERATION_FAILURE_MESSAGE,
    SAFE_FAILURE_MESSAGE as NOTES_SAFE_FAILURE_MESSAGE,
)
from app.cloud.interview_ask_ai import (
    ASK_AI_FAILURE_MESSAGE,
    AskAIResult,
    CloudInterviewAskAIMessageRecord,
    CloudInterviewAskAIService,
    InterviewAskAIMessageListPage,
    SAFE_FAILURE_MESSAGE as ASK_AI_SAFE_FAILURE_MESSAGE,
)
from app.cloud.interview_transcripts import (
    CloudInterviewTranscriptEntryRecord,
    CloudInterviewTranscriptService,
    CreateInterviewTranscriptEntryResult,
    InterviewTranscriptEntryListPage,
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


class InterviewTranscriptEntryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    source: str = ""
    question_text: str
    answer_text: str
    category: str = ""
    provider: str = ""
    model: str = ""
    generation_ms: int | None = None
    metadata: dict = Field(default_factory=dict)


class InterviewTranscriptEntryResponse(BaseModel):
    id: str
    session_id: str
    turn_index: int
    source: str | None = None
    question_text: str
    answer_text: str
    category: str | None = None
    provider: str | None = None
    model: str | None = None
    generation_ms: int | None = None
    created_at: str | None = None


class InterviewTranscriptEntryListResponse(BaseModel):
    items: list[InterviewTranscriptEntryResponse]
    limit: int
    page: int


class InterviewSessionNotesGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_regenerate: bool = False


class InterviewSessionNotesResponse(BaseModel):
    id: str
    session_id: str
    status: str
    notes_markdown: str
    summary: str | None = None
    strengths: list[str]
    improvement_areas: list[str]
    technical_topics: list[str]
    key_questions: list[str]
    suggested_followups: list[str]
    provider: str | None = None
    model: str | None = None
    generation_ms: int | None = None
    transcript_entry_count: int
    generated_at: str | None = None


class InterviewSessionAskAIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    request_id: str | None = None
    include_notes: bool = True


class InterviewSessionAskAIMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    message_text: str
    turn_index: int
    provider: str | None = None
    model: str | None = None
    generation_ms: int | None = None
    created_at: str | None = None


class InterviewSessionAskAIContextResponse(BaseModel):
    transcript_entry_count: int
    notes_used: bool
    recent_message_count: int


class InterviewSessionAskAIResponse(BaseModel):
    user_message: InterviewSessionAskAIMessageResponse
    assistant_message: InterviewSessionAskAIMessageResponse
    answer_text: str
    provider: str | None = None
    model: str | None = None
    generation_ms: int | None = None
    context_used: InterviewSessionAskAIContextResponse


class InterviewSessionAskAIMessageListResponse(BaseModel):
    items: list[InterviewSessionAskAIMessageResponse]
    limit: int
    page: int
    has_more: bool = False
    next_page: int | None = None


@lru_cache(maxsize=1)
def _cached_cloud_interview_session_service() -> CloudInterviewSessionService:
    return CloudInterviewSessionService()


@lru_cache(maxsize=1)
def _cached_cloud_interview_transcript_service() -> CloudInterviewTranscriptService:
    return CloudInterviewTranscriptService()


@lru_cache(maxsize=1)
def _cached_cloud_interview_notes_service() -> CloudInterviewNotesService:
    return CloudInterviewNotesService()


@lru_cache(maxsize=1)
def _cached_cloud_interview_ask_ai_service() -> CloudInterviewAskAIService:
    return CloudInterviewAskAIService()


def get_cloud_interview_session_service() -> CloudInterviewSessionService:
    try:
        return _cached_cloud_interview_session_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


def get_cloud_interview_transcript_service() -> CloudInterviewTranscriptService:
    try:
        return _cached_cloud_interview_transcript_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


def get_cloud_interview_notes_service() -> CloudInterviewNotesService:
    try:
        return _cached_cloud_interview_notes_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


def get_cloud_interview_ask_ai_service() -> CloudInterviewAskAIService:
    try:
        return _cached_cloud_interview_ask_ai_service()
    except SupabaseConfigurationError as exc:
        raise _handle_cloud_error(exc) from exc


CloudInterviewSessionServiceDep = Annotated[CloudInterviewSessionService, Depends(get_cloud_interview_session_service)]
CloudInterviewTranscriptServiceDep = Annotated[CloudInterviewTranscriptService, Depends(get_cloud_interview_transcript_service)]
CloudInterviewNotesServiceDep = Annotated[CloudInterviewNotesService, Depends(get_cloud_interview_notes_service)]
CloudInterviewAskAIServiceDep = Annotated[CloudInterviewAskAIService, Depends(get_cloud_interview_ask_ai_service)]


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


def _transcript_entry_response(record: CloudInterviewTranscriptEntryRecord) -> InterviewTranscriptEntryResponse:
    return InterviewTranscriptEntryResponse(
        id=record.id,
        session_id=record.session_id,
        turn_index=record.turn_index,
        source=record.source,
        question_text=record.question_text,
        answer_text=record.answer_text,
        category=record.category,
        provider=record.provider,
        model=record.model,
        generation_ms=record.generation_ms,
        created_at=record.created_at,
    )


def _notes_response(record: CloudInterviewNotesRecord) -> InterviewSessionNotesResponse:
    return InterviewSessionNotesResponse(
        id=record.id,
        session_id=record.session_id,
        status=record.status,
        notes_markdown=record.notes_markdown,
        summary=record.summary,
        strengths=record.strengths,
        improvement_areas=record.improvement_areas,
        technical_topics=record.technical_topics,
        key_questions=record.key_questions,
        suggested_followups=record.suggested_followups,
        provider=record.provider,
        model=record.model,
        generation_ms=record.generation_ms,
        transcript_entry_count=record.transcript_entry_count,
        generated_at=record.generated_at,
    )


def _ask_ai_message_response(record: CloudInterviewAskAIMessageRecord) -> InterviewSessionAskAIMessageResponse:
    return InterviewSessionAskAIMessageResponse(
        id=record.id,
        session_id=record.session_id,
        role=record.role,
        message_text=record.message_text,
        turn_index=record.turn_index,
        provider=record.provider,
        model=record.model,
        generation_ms=record.generation_ms,
        created_at=record.created_at,
    )


def _ask_ai_response(result: AskAIResult) -> InterviewSessionAskAIResponse:
    return InterviewSessionAskAIResponse(
        user_message=_ask_ai_message_response(result.user_message),
        assistant_message=_ask_ai_message_response(result.assistant_message),
        answer_text=result.answer_text,
        provider=result.provider,
        model=result.model,
        generation_ms=result.generation_ms,
        context_used=InterviewSessionAskAIContextResponse(
            transcript_entry_count=result.context_used.transcript_entry_count,
            notes_used=result.context_used.notes_used,
            recent_message_count=result.context_used.recent_message_count,
        ),
    )


def _transcript_filename(format: str) -> str:
    return f'interview-session-transcript.{format}'


def _handle_cloud_error(exc: Exception) -> HTTPException:
    if str(exc) == NOTES_GENERATION_FAILURE_MESSAGE:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=NOTES_GENERATION_FAILURE_MESSAGE,
        )
    if str(exc) == NOTES_SAFE_FAILURE_MESSAGE:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=NOTES_SAFE_FAILURE_MESSAGE,
        )
    if str(exc) == ASK_AI_FAILURE_MESSAGE:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ASK_AI_FAILURE_MESSAGE,
        )
    if str(exc) == ASK_AI_SAFE_FAILURE_MESSAGE:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ASK_AI_SAFE_FAILURE_MESSAGE,
        )
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


@router.post("/{session_id}/transcript-entries", response_model=InterviewTranscriptEntryResponse, status_code=status.HTTP_201_CREATED)
def create_interview_transcript_entry(
    session_id: UUID,
    payload: InterviewTranscriptEntryCreateRequest,
    current_user: CurrentUserDep,
    service: CloudInterviewTranscriptServiceDep,
) -> InterviewTranscriptEntryResponse:
    try:
        result: CreateInterviewTranscriptEntryResult = service.create_transcript_entry(
            user_id=current_user.user_id,
            session_id=str(session_id),
            payload=payload.model_dump(exclude_none=True),
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _transcript_entry_response(result.record)


@router.get("/{session_id}/transcript-entries", response_model=InterviewTranscriptEntryListResponse)
def list_interview_transcript_entries(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewTranscriptServiceDep,
    limit: int = 100,
    page: int = 1,
) -> InterviewTranscriptEntryListResponse:
    try:
        result: InterviewTranscriptEntryListPage = service.list_transcript_entries(
            user_id=current_user.user_id,
            session_id=str(session_id),
            limit=limit,
            page=page,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return InterviewTranscriptEntryListResponse(
        items=[_transcript_entry_response(record) for record in result.items],
        limit=result.limit,
        page=result.page,
    )


@router.get("/{session_id}/transcript/download", response_class=PlainTextResponse)
def download_interview_transcript(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewTranscriptServiceDep,
    format: str = Query("txt"),
) -> PlainTextResponse:
    try:
        normalized_format = str(format or "").strip().lower()
        content = service.export_transcript(
            user_id=current_user.user_id,
            session_id=str(session_id),
            format=normalized_format,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    media_type = "text/markdown; charset=utf-8" if normalized_format == "md" else "text/plain; charset=utf-8"
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{_transcript_filename(normalized_format)}"'},
    )


@router.get("/{session_id}/notes", response_model=InterviewSessionNotesResponse)
def get_interview_session_notes(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewNotesServiceDep,
) -> InterviewSessionNotesResponse:
    try:
        record = service.get_notes(user_id=current_user.user_id, session_id=str(session_id))
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _notes_response(record)


@router.post("/{session_id}/notes/generate", response_model=InterviewSessionNotesResponse)
def generate_interview_session_notes(
    session_id: UUID,
    payload: InterviewSessionNotesGenerateRequest,
    current_user: CurrentUserDep,
    service: CloudInterviewNotesServiceDep,
) -> InterviewSessionNotesResponse:
    try:
        record = service.generate_notes(
            user_id=current_user.user_id,
            session_id=str(session_id),
            force_regenerate=payload.force_regenerate,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _notes_response(record)


@router.get("/{session_id}/ask-ai/messages", response_model=InterviewSessionAskAIMessageListResponse)
def list_interview_session_ask_ai_messages(
    session_id: UUID,
    current_user: CurrentUserDep,
    service: CloudInterviewAskAIServiceDep,
    limit: int = 50,
    page: int = 1,
) -> InterviewSessionAskAIMessageListResponse:
    try:
        result: InterviewAskAIMessageListPage = service.list_messages(
            user_id=current_user.user_id,
            session_id=str(session_id),
            limit=limit,
            page=page,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return InterviewSessionAskAIMessageListResponse(
        items=[_ask_ai_message_response(record) for record in result.items],
        limit=result.limit,
        page=result.page,
        has_more=result.has_more,
        next_page=result.next_page,
    )


@router.post("/{session_id}/ask-ai", response_model=InterviewSessionAskAIResponse)
def ask_interview_session_ai(
    session_id: UUID,
    payload: InterviewSessionAskAIRequest,
    current_user: CurrentUserDep,
    service: CloudInterviewAskAIServiceDep,
) -> InterviewSessionAskAIResponse:
    try:
        result = service.ask_ai(
            user_id=current_user.user_id,
            session_id=str(session_id),
            question=payload.question,
            request_id=payload.request_id,
            include_notes=payload.include_notes,
        )
    except Exception as exc:
        raise _handle_cloud_error(exc) from exc
    return _ask_ai_response(result)
