import hashlib
import logging
import secrets
import time

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request, status

from app.auth.supabase_auth import CurrentUser, CurrentUserDep
from app.cloud.profile_bootstrap import (
    ProfileBootstrapResult,
    SupabaseProfileBootstrapError,
    bootstrap_authenticated_profile,
)
from app.cloud.supabase_config import SupabaseConfigurationError
from app.email.event_store import build_outbound_email_event_service
from app.email.provider import mask_recipient_email
from app.email.service import build_email_service, send_welcome_email_dry_run


router = APIRouter()
logger = logging.getLogger("auth_api")


DESKTOP_HANDOFF_TTL_SECONDS = 5 * 60
DESKTOP_HANDOFF_CODE_BYTES = 32
DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER = 3
DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS = 5
DESKTOP_HANDOFF_ERROR = "Invalid or expired desktop handoff."
DESKTOP_HANDOFF_RATE_LIMIT_ERROR = "Too many desktop handoff requests."
# C6.2A dev/local handoff store. It is short-lived, per-user bounded, rate-limited,
# one-time-use, and keyed by SHA-256 handoff-code hashes, but it is process memory
# and is not safe for multi-worker/multi-instance production deployment. Production
# hardening must replace it with a Redis/Supabase TTL-backed atomic shared store.
_desktop_handoffs: dict[str, dict[str, object]] = {}
_desktop_handoff_create_timestamps: dict[str, float] = {}


def _now() -> float:
    return time.time()


class CurrentUserResponse(BaseModel):
    user_id: str
    email: str | None = None
    role: str | None = None


class ProfileBootstrapResponse(BaseModel):
    user_id: str
    profile_exists: bool
    profile_created: bool
    settings_exists: bool
    settings_created: bool
    next_step: str


class DesktopHandoffCreateRequest(BaseModel):
    state: str = Field(min_length=16, max_length=256, pattern=r"^[A-Za-z0-9._~-]+$")
    refresh_token: str = Field(min_length=1, max_length=8192)


class DesktopHandoffCreateResponse(BaseModel):
    handoff_code: str
    expires_in: int


class DesktopHandoffExchangeRequest(BaseModel):
    handoff_code: str = Field(min_length=32, max_length=256, pattern=r"^[A-Za-z0-9._~-]+$")
    state: str = Field(min_length=16, max_length=256, pattern=r"^[A-Za-z0-9._~-]+$")


class DesktopHandoffExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str


def _hash_handoff_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _prune_desktop_handoffs(now: float | None = None) -> None:
    current_time = _now() if now is None else now
    expired = [
        code_hash
        for code_hash, record in _desktop_handoffs.items()
        if float(record.get("expires_at", 0)) <= current_time
    ]
    for code_hash in expired:
        _desktop_handoffs.pop(code_hash, None)
    active_user_ids = {str(record.get("user_id") or "") for record in _desktop_handoffs.values()}
    stale_users = [
        user_id
        for user_id, created_at in _desktop_handoff_create_timestamps.items()
        if user_id not in active_user_ids
        and current_time - float(created_at) >= DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS
    ]
    for user_id in stale_users:
        _desktop_handoff_create_timestamps.pop(user_id, None)


def _active_desktop_handoff_count_for_user(user_id: str) -> int:
    return sum(1 for record in _desktop_handoffs.values() if record.get("user_id") == user_id)


def _enforce_desktop_handoff_creation_limits(user_id: str, now: float) -> None:
    if _active_desktop_handoff_count_for_user(user_id) >= DESKTOP_HANDOFF_MAX_ACTIVE_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=DESKTOP_HANDOFF_RATE_LIMIT_ERROR,
        )
    last_created_at = _desktop_handoff_create_timestamps.get(user_id)
    if (
        last_created_at is not None
        and now - float(last_created_at) < DESKTOP_HANDOFF_CREATE_MIN_INTERVAL_SECONDS
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=DESKTOP_HANDOFF_RATE_LIMIT_ERROR,
        )


def _bearer_token_from_request(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def _profile_bootstrap_response(result: ProfileBootstrapResult) -> ProfileBootstrapResponse:
    return ProfileBootstrapResponse(
        user_id=result.user_id,
        profile_exists=result.profile_exists,
        profile_created=result.profile_created,
        settings_exists=result.settings_exists,
        settings_created=result.settings_created,
        next_step=result.next_step,
    )


def _trigger_welcome_email(current_user: CurrentUser) -> None:
    """Best-effort dry-run welcome event after account setup succeeds."""

    if not current_user.email:
        logger.info("welcome_email_dry_run status=skipped reason=missing_email")
        return
    try:
        email_service = build_email_service(
            event_store=build_outbound_email_event_service(),
        )
        result = send_welcome_email_dry_run(
            email_service=email_service,
            user_id=current_user.user_id,
            recipient_email=current_user.email,
        )
        logger.info(
            "welcome_email_dry_run status=%s event_status=%s replayed=%s recipient=%s",
            result.status,
            result.event_status or "unknown",
            result.replayed,
            mask_recipient_email(current_user.email),
        )
    except Exception as error:
        logger.warning(
            "welcome_email_dry_run status=failed error_type=%s",
            type(error).__name__,
        )


@router.get("/me", response_model=CurrentUserResponse)
async def get_authenticated_user(current_user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
    )


@router.post("/profile/bootstrap", response_model=ProfileBootstrapResponse)
def bootstrap_profile(current_user: CurrentUserDep) -> ProfileBootstrapResponse:
    try:
        result = bootstrap_authenticated_profile(current_user.user_id)
    except SupabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase cloud configuration is not ready.",
        ) from exc
    except SupabaseProfileBootstrapError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase profile bootstrap failed.",
        ) from exc
    _trigger_welcome_email(current_user)
    return _profile_bootstrap_response(result)


@router.post("/desktop-handoff", response_model=DesktopHandoffCreateResponse)
def create_desktop_handoff(
    payload: DesktopHandoffCreateRequest,
    request: Request,
    current_user: CurrentUserDep,
) -> DesktopHandoffCreateResponse:
    now = _now()
    user_id = current_user.user_id
    _prune_desktop_handoffs(now)
    _enforce_desktop_handoff_creation_limits(user_id, now)
    code = secrets.token_urlsafe(DESKTOP_HANDOFF_CODE_BYTES)
    _desktop_handoffs[_hash_handoff_code(code)] = {
        "user_id": user_id,
        "state": payload.state,
        "access_token": _bearer_token_from_request(request),
        "refresh_token": payload.refresh_token,
        "expires_at": now + DESKTOP_HANDOFF_TTL_SECONDS,
        "created_at": now,
    }
    _desktop_handoff_create_timestamps[user_id] = now
    return DesktopHandoffCreateResponse(
        handoff_code=code,
        expires_in=DESKTOP_HANDOFF_TTL_SECONDS,
    )


@router.post("/desktop-handoff/exchange", response_model=DesktopHandoffExchangeResponse)
def exchange_desktop_handoff(payload: DesktopHandoffExchangeRequest) -> DesktopHandoffExchangeResponse:
    _prune_desktop_handoffs()
    record = _desktop_handoffs.pop(_hash_handoff_code(payload.handoff_code), None)
    if not record or record.get("state") != payload.state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=DESKTOP_HANDOFF_ERROR,
        )
    return DesktopHandoffExchangeResponse(
        access_token=str(record.get("access_token") or ""),
        refresh_token=str(record.get("refresh_token") or ""),
    )
