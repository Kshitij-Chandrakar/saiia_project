"""Authenticated account-only projection; no assignment/payment mutation route."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from app.commercial.admin_access import verified_actor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_api import DraftRoute

router = APIRouter(route_class=DraftRoute)
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Authorization"}


@router.get("/api/account/subscription")
def current_subscription(request: Request) -> JSONResponse:
    try:
        actor = verified_actor(request)
        runtime = getattr(request.app.state, "subscriptions", None)
        if runtime is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        result = runtime.service().current(actor, bootstrap=True)
        billing = getattr(request.app.state, "billing", None)
        result["checkout_ready"] = bool(billing and billing.enabled)
        return JSONResponse(result, headers=HEADERS)
    except HTTPException as error:
        return JSONResponse(
            {
                "detail": {
                    "code": (
                        "subscription_auth_required"
                        if error.status_code == 401
                        else "subscription_unavailable"
                    )
                }
            },
            status_code=error.status_code,
            headers=HEADERS,
        )
    except CatalogStoreError as error:
        status = 403 if error.code == ErrorCode.DENIED else 503
        return JSONResponse(
            {
                "detail": {
                    "code": (
                        "subscription_denied"
                        if status == 403
                        else "subscription_unavailable"
                    )
                }
            },
            status_code=status,
            headers=HEADERS,
        )
