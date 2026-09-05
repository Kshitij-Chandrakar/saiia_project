from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.cloud.supabase_config import SupabaseConfigurationError
from app.email.unsubscribe import (
    MarketingUnsubscribeService,
    MarketingUnsubscribeStorageError,
    build_marketing_unsubscribe_service,
)


router = APIRouter()

UNSUBSCRIBE_MESSAGE = (
    "Your promotional email preference has been updated if the link was valid."
)
UNSUBSCRIBE_FAILURE_MESSAGE = "Unable to update your promotional email preference right now."


class MarketingUnsubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str | None = Field(default=None, max_length=256)


class MarketingUnsubscribeResponse(BaseModel):
    success: bool
    message: str


def get_marketing_unsubscribe_service() -> MarketingUnsubscribeService:
    return build_marketing_unsubscribe_service()


@router.post("/unsubscribe", response_model=MarketingUnsubscribeResponse)
def unsubscribe_marketing_email(
    payload: MarketingUnsubscribeRequest,
    service: Annotated[MarketingUnsubscribeService, Depends(get_marketing_unsubscribe_service)],
) -> MarketingUnsubscribeResponse:
    try:
        service.unsubscribe(raw_token=payload.token or "")
    except (MarketingUnsubscribeStorageError, SupabaseConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNSUBSCRIBE_FAILURE_MESSAGE,
        ) from exc

    return MarketingUnsubscribeResponse(
        success=True,
        message=UNSUBSCRIBE_MESSAGE,
    )
