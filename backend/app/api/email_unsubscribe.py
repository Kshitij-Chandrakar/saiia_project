from typing import Annotated
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.cloud.supabase_config import SupabaseConfigurationError
from app.email.unsubscribe import (
    MarketingUnsubscribeService,
    MarketingUnsubscribeStorageError,
    build_marketing_unsubscribe_service,
)


router = APIRouter()


class UnsubscribeAccessLogFilter(logging.Filter):
    """Also redact rejected methods/validation failures before endpoint execution."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            address, method, path, version, code = record.args
            if isinstance(path, str) and path.split("?", 1)[0].rstrip("/") == "/api/email/unsubscribe/one-click":
                record.args = (address, method, path.split("?", 1)[0], version, code)
        return True


logging.getLogger("uvicorn.access").addFilter(UnsubscribeAccessLogFilter())


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


def _one_click_token(request: Request) -> str:
    token = request.query_params.get("token", "")
    # Remove the query before dependency failures or Uvicorn response access logs.
    request.scope["query_string"] = b""
    return token


@router.post("/unsubscribe/one-click")
def unsubscribe_one_click(
    token: Annotated[str, Depends(_one_click_token)],
    service: Annotated[MarketingUnsubscribeService, Depends(get_marketing_unsubscribe_service)],
) -> dict[str, bool]:
    try:
        service.unsubscribe(raw_token=token)
    except (MarketingUnsubscribeStorageError, SupabaseConfigurationError):
        raise HTTPException(status_code=503, detail=UNSUBSCRIBE_FAILURE_MESSAGE) from None
    return {"success": True}
