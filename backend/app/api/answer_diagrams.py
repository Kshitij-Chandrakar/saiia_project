"""Narrow authenticated diagram API, separate from answer generation."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.answer_diagrams import DiagramError, diagram_store
from app.config import settings
from app.services.answer_diagram_service import diagram_service

router = APIRouter()


@router.get('/{session_id}/answer-sources')
def resolve_source(session_id: UUID, current_user: CurrentUserDep,
                   transcript_id: UUID | None = None, request_id: str | None = Query(None, min_length=1, max_length=120)):
    if (transcript_id is None) == (request_id is None):
        raise HTTPException(400, detail={'code': 'invalid_source'})
    try:
        descriptor, _ = diagram_store().source(current_user.user_id, str(session_id),
            transcript=str(transcript_id) if transcript_id else None, request=request_id)
        descriptor['generation_enabled'] = settings.DIAGRAM_GENERATION_ENABLED
        return descriptor
    except DiagramError as exc:
        if exc.code in {'schema_unavailable', 'source_pending'}:
            return dict(session_id=str(session_id), transcript_id=str(transcript_id) if transcript_id else None,
                        eligible=False, generation_enabled=False,
                        state='pending' if exc.code == 'source_pending' else 'unavailable', reason=exc.code)
        raise HTTPException(exc.status, detail={'code': exc.code}) from None


class DiagramRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_revision: str = Field(pattern=r'^v1:[a-f0-9]{64}$')
    operation_id: UUID


@router.get('/{session_id}/transcript-entries/{transcript_id}/diagram')
async def read_diagram(session_id: UUID, transcript_id: UUID, current_user: CurrentUserDep,
                       source_revision: str = Query(pattern=r'^v1:[a-f0-9]{64}$')):
    try:
        return await diagram_service().read((current_user.user_id, str(session_id), str(transcript_id), source_revision, None))
    except DiagramError as exc:
        if exc.code == 'schema_unavailable':
            return dict(state='unavailable', reason=exc.code, source_revision=source_revision)
        raise HTTPException(exc.status, detail={'code': exc.code}) from None


@router.post('/{session_id}/transcript-entries/{transcript_id}/diagram')
@router.post('/{session_id}/transcript-entries/{transcript_id}/diagram/{action}')
async def mutate_diagram(session_id: UUID, transcript_id: UUID, payload: DiagramRequest,
                         current_user: CurrentUserDep, action: str = 'generate'):
    if action not in ('generate', 'retry', 'cancel'):
        raise HTTPException(404)
    identity = (current_user.user_id, str(session_id), str(transcript_id), payload.source_revision, str(payload.operation_id))
    try:
        service = diagram_service()
        return await service.cancel(identity) if action == 'cancel' else await service.run(identity, retry=action == 'retry')
    except DiagramError as exc:
        raise HTTPException(exc.status, detail={'code': exc.code}) from None
