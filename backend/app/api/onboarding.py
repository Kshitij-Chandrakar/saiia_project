from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.auth.supabase_auth import CurrentUserDep
from app.cloud.onboarding import OnboardingService, OnboardingUnavailable
from app.cloud.supabase_config import SupabaseConfigurationError

router = APIRouter()
class StepRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_step: int = Field(strict=True, ge=1, le=5)

def service():
    try: return OnboardingService()
    except SupabaseConfigurationError:
        raise HTTPException(503, 'Onboarding is unavailable. Please try again later.') from None

def perform(operation):
    try: return operation()
    except OnboardingUnavailable:
        raise HTTPException(503, 'Onboarding is unavailable. Account setup or the onboarding migration may not be ready.') from None

@router.get('')
def read(user: CurrentUserDep, store=Depends(service)):
    return perform(lambda: store.read(user.user_id))

@router.patch('/step')
def step(body: StepRequest, user: CurrentUserDep, store=Depends(service)):
    return perform(lambda: store.step(user.user_id, body.current_step))

@router.post('/complete')
def complete(user: CurrentUserDep, store=Depends(service)):
    return perform(lambda: store.complete(user.user_id))
