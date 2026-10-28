"""Subscription-only, caller-scoped read-only admin probe."""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.commercial.admin_access import (
    MANAGE,
    AdminAccess,
    AdminBoundary,
    VerifiedActor,
    http_error,
    probe_transport,
    verified_actor,
)
from app.commercial.catalog_store import CatalogStoreError, ErrorCode

router = APIRouter()
SUBSCRIPTION_MANAGE = MANAGE


def access_for_request(request: Request) -> tuple[VerifiedActor, AdminAccess]:
    actor = verified_actor(request)
    try:
        return actor, AdminBoundary(actor, probe_transport(actor)).access()
    except CatalogStoreError as error:
        raise http_error(error) from None
    except Exception:
        raise http_error(CatalogStoreError(ErrorCode.UNAVAILABLE)) from None


async def require_subscription_admin(request: Request) -> VerifiedActor:
    actor, result = await run_in_threadpool(access_for_request, request)
    if MANAGE not in result.permissions:
        raise http_error(CatalogStoreError(ErrorCode.DENIED))
    return actor


@router.get("/admin/me", response_model=AdminAccess)
async def admin_me(request: Request) -> AdminAccess:
    _, result = await run_in_threadpool(access_for_request, request)
    return result
