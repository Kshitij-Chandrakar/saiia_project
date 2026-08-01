from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status

from app.auth.supabase_auth import CurrentUserDep
from app.cloud.profile_bootstrap import (
    ProfileBootstrapResult,
    SupabaseProfileBootstrapError,
    bootstrap_authenticated_profile,
)
from app.cloud.supabase_config import SupabaseConfigurationError


router = APIRouter()


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
