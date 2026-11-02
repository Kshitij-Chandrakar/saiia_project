"""One reviewed hosted operation. Real entitlement/quota authority is absent."""
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import re
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.auth.supabase_auth import get_current_user
from app.cloud.interview_sessions import (
    CloudInterviewSessionError, CloudInterviewSessionNotFoundError,
    CloudInterviewSessionValidationError,
)
from app.cloud.supabase_config import SupabaseConfigurationError


class AdmissionOutcome(str, Enum):
    ALLOWED = 'allowed'
    DENIED = 'denied'
    UNAVAILABLE = 'authority_unavailable'


@dataclass(frozen=True)
class AdmissionDecision:
    # Future entitlement + atomic reservation adapters must both succeed before
    # returning ALLOWED. Reservation settlement/release is not implemented here.
    outcome: AdmissionOutcome

    @property
    def reason_code(self):
        return {
            AdmissionOutcome.ALLOWED: 'commercial_access_allowed',
            AdmissionOutcome.DENIED: 'commercial_access_denied',
            AdmissionOutcome.UNAVAILABLE: 'commercial_authority_unavailable',
        }[self.outcome]


def enforce_decision(decision):
    # No truthy booleans, arbitrary reason strings or upstream exceptions become
    # grants. Safe codes are owned here, never copied from a provider/resolver.
    if not isinstance(decision, AdmissionDecision) or type(decision.outcome) is not AdmissionOutcome:
        decision = AdmissionDecision(AdmissionOutcome.UNAVAILABLE)
    if decision.outcome is not AdmissionOutcome.ALLOWED:
        status = 403 if decision.outcome is AdmissionOutcome.DENIED else 503
        raise HTTPException(status, detail={'code': decision.reason_code})


@dataclass(frozen=True)
class AdmissionContext:
    user_id: str
    session_id: str
    request_id: str
    semantics_hash: str
    retry_attempt: int
    recovery: bool
    supersedes_request_id: str | None = None
    operation: str = 'answers.generate'

    @property
    def operation_id(self):
        # No raw client key alone can collide across accounts/resources/types.
        return hashlib.sha256(json.dumps([
            self.user_id, self.operation, self.session_id, self.request_id,
        ], separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class _RequestGrant:
    context: AdmissionContext
    request_body: object


_KEY = re.compile(r'[A-Za-z0-9._:-]{1,120}', re.ASCII)


def validated_request_key(value: object) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise HTTPException(422, detail={'code': 'commercial_request_id_invalid'})
    return value


class AdmissionAuthority(Protocol):
    async def admit(self, context: AdmissionContext) -> AdmissionDecision: ...


class ClosedAuthority:
    async def admit(self, context):
        return AdmissionDecision(AdmissionOutcome.UNAVAILABLE)


# No configuration or request field can install a successful authority. Until
# entitlements AND atomic reservations exist, production remains closed.
authority: AdmissionAuthority = ClosedAuthority()


async def admit_buffered_answer(req, request):
    if not settings.HOSTED_COMMERCIAL_MODE and settings.SUBSCRIPTIONS_ENABLED != 'true':
        return
    if request is None:
        raise HTTPException(401, detail={'code': 'commercial_auth_required'})
    source = str(req.source or '').strip().lower()
    lease = request.scope.get('state',{}).get('_subscription_auto')
    if source == 'auto' and settings.SUBSCRIPTIONS_ENABLED == 'true':
        from app.commercial.subscription_auto import AccountAutoLease
        if not isinstance(lease,AccountAutoLease):
            raise HTTPException(503, detail={'code':'commercial_path_unreviewed'})
        await lease.authorize()
    elif source not in ('', 'typed', 'manual', 'chat'):
        raise HTTPException(503, detail={'code': 'commercial_path_unreviewed'})
    session_id = str(req.session_id or '').strip()
    if not session_id:
        raise HTTPException(400, detail={'code': 'commercial_session_required'})
    try:
        session_id = str(UUID(session_id))
    except (ValueError, AttributeError):
        raise HTTPException(422, detail={'code': 'commercial_session_invalid'}) from None
    user = await run_in_threadpool(get_current_user, request)
    from app.api.generate import _generation_session_service
    from app.session_generation import owned_session, generation_request_hash
    try:
        session = await run_in_threadpool(owned_session, lambda: _generation_session_service(request),
            user_id=user.user_id, session_id=session_id, allow_model_bound=True)
    except CloudInterviewSessionNotFoundError:
        raise HTTPException(404, detail={'code': 'commercial_session_not_found'}) from None
    except CloudInterviewSessionValidationError:
        raise HTTPException(400, detail={'code': 'commercial_session_invalid'}) from None
    except (CloudInterviewSessionError, SupabaseConfigurationError):
        raise HTTPException(503, detail={'code': 'commercial_ownership_unavailable'}) from None
    if session.user_id != user.user_id or session.id != session_id:
        raise HTTPException(404, detail={'code': 'commercial_session_not_found'})
    if session.status != 'active':
        raise HTTPException(409, detail={'code': 'commercial_session_inactive'})
    if req.job_context_id or (req.selected_resume_id and req.selected_resume_id != session.selected_resume_id):
        raise HTTPException(400, detail={'code': 'commercial_context_override'})
    # Use the same canonical session fields and fingerprint as the durable turn
    # claim. Never mutate session selection or trust client context overrides.
    req.session_id = session_id
    if req.request_id is None and not req.recover_turn:
        req.request_id = str(uuid4())
    validated_request_key(req.request_id)
    if req.supersedes_request_id is not None:
        validated_request_key(req.supersedes_request_id)
    canonical = req.model_copy(update={
        'selected_resume_id': session.selected_resume_id,
        'target_role': session.target_role, 'company_name': session.company_name,
        'job_description': session.job_description_preview,
    })
    context = AdmissionContext(user.user_id, session_id, req.request_id,
        generation_request_hash(canonical), req.retry_attempt, req.recover_turn, req.supersedes_request_id)
    if not settings.ENABLE_SESSION_ANSWER_MODELS:
        raise HTTPException(503, detail={'code': 'commercial_coordination_unavailable'})
    granted = getattr(request.state, '_commercial_admission', None)
    if isinstance(granted, _RequestGrant):
        if granted.context != context or granted.request_body is not req:
            raise HTTPException(409, detail={'code': 'commercial_operation_conflict'})
        return
    # Only the existing coordinated path can enforce durable conflicting reuse.
    # Do not grant the unmanaged path merely because a future adapter says yes.
    try:
        if settings.SUBSCRIPTIONS_ENABLED == 'true':
            from app.commercial.subscription_execution import execution_service
            service, actor = execution_service(request)
            await run_in_threadpool(service.require_manual_answers, actor)
            approved = AdmissionDecision(AdmissionOutcome.ALLOWED)
        else:
            approved = await authority.admit(context)
    except HTTPException:
        raise
    except Exception as error:
        from app.commercial.catalog_store import CatalogStoreError, ErrorCode
        if isinstance(error, CatalogStoreError) and error.code == ErrorCode.DENIED:
            raise HTTPException(403, detail={'code': 'subscription_denied'}) from None
        raise HTTPException(503, detail={'code': 'commercial_authority_unavailable'}) from None
    enforce_decision(approved)
    request.state._commercial_admission = _RequestGrant(context, req)


def bind_recovered_admission(req, request, *, user_id, session_id):
    """Only the coordinator calls this after owned durable payload recovery.

    The recovered request replaces renderer text; its grant remains the same
    logical operation, not a second admission or generation authorization.
    """
    if not settings.HOSTED_COMMERCIAL_MODE and settings.SUBSCRIPTIONS_ENABLED != 'true':
        return
    granted = getattr(request.state, '_commercial_admission', None)
    if not isinstance(granted, _RequestGrant) or not granted.context.recovery:
        raise HTTPException(409, detail={'code': 'commercial_operation_conflict'})
    context = granted.context
    if (context.user_id, context.session_id, context.request_id, context.retry_attempt) != (
            user_id, session_id, req.request_id, req.retry_attempt):
        raise HTTPException(409, detail={'code': 'commercial_operation_conflict'})
    from app.session_generation import generation_request_hash
    request.state._commercial_admission = _RequestGrant(replace(context,
        semantics_hash=generation_request_hash(req), recovery=False,
        supersedes_request_id=req.supersedes_request_id), req)
