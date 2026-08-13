import hashlib
import secrets
import time

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request, status

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.profile_bootstrap import (
    ProfileBootstrapResult,
    SupabaseProfileBootstrapError,
    bootstrap_authenticated_profile,
)
from app.cloud.supabase_config import SupabaseConfigurationError


router = APIRouter()


DESKTOP_HANDOFF_TTL_SECONDS = 5 * 60
DESKTOP_HANDOFF_CODE_BYTES = 32
DESKTOP_HANDOFF_ERROR = "Invalid or expired desktop handoff."
_desktop_handoffs: dict[str, dict[str, object]] = {}


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
    current_time = time.time() if now is None else now
    expired = [
        code_hash
        for code_hash, record in _desktop_handoffs.items()
        if float(record.get("expires_at", 0)) <= current_time
    ]
    for code_hash in expired:
        _desktop_handoffs.pop(code_hash, None)


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
    return _profile_bootstrap_response(result)


@router.post("/desktop-handoff", response_model=DesktopHandoffCreateResponse)
def create_desktop_handoff(
    payload: DesktopHandoffCreateRequest,
    request: Request,
    current_user: CurrentUserDep,
) -> DesktopHandoffCreateResponse:
    _prune_desktop_handoffs()
    code = secrets.token_urlsafe(DESKTOP_HANDOFF_CODE_BYTES)
    _desktop_handoffs[_hash_handoff_code(code)] = {
        "user_id": current_user.user_id,
        "state": payload.state,
        "access_token": _bearer_token_from_request(request),
        "refresh_token": payload.refresh_token,
        "expires_at": time.time() + DESKTOP_HANDOFF_TTL_SECONDS,
    }
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
