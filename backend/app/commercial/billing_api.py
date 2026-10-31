"""Website-only checkout boundary. Composition is default off."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.commercial.account_entitlements import ID
from app.commercial.admin_access import verified_actor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.razorpay import PaymentUnavailable

logger = logging.getLogger(__name__)


router = APIRouter()
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Authorization"}


async def body(request, limit):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(413)
    return bytes(raw)


@router.api_route("/api/billing/{action}", methods=["POST", "GET"])
async def billing(request: Request, action: str):
    try:
        service = getattr(request.app.state, "billing", None)
        if action == "availability" and request.method == "GET":
            return JSONResponse(
                {
                    "available": bool(service and service.enabled),
                    "price_ids": sorted(service.plan_mappings)
                    if service and service.enabled
                    else [],
                },
                headers=HEADERS,
            )
        if service is None or not service.enabled:
            raise PaymentUnavailable()
        if action == "webhook" and request.method == "POST":
            raw = await body(request, 131072)
            await run_in_threadpool(
                service.webhook, raw, request.headers.get("x-razorpay-signature", "")
            )
            return JSONResponse({"received": True}, headers=HEADERS)
        actor = verified_actor(request)
        import json

        if request.method == "POST":
            data = json.loads(await body(request, 4096))
            if action == "checkout":
                result = await run_in_threadpool(service.prepare, actor, data)
            elif action in ("start", "verify", "cancel"):
                operation = ID.validate_python(data.pop("operation_id"), strict=True)
                if action == "start":
                    if (
                        set(data) != {"consent", "quote_id"}
                        or data["consent"] is not True
                        or not isinstance(data["quote_id"], str)
                    ):
                        raise ValueError()
                    result = await run_in_threadpool(
                        service.start, actor, operation, True, data["quote_id"]
                    )
                elif action == "cancel":
                    if data != {"confirm": True}:
                        raise ValueError()
                    result = await run_in_threadpool(service.cancel, actor, operation)
                else:
                    result = await run_in_threadpool(
                        service.callback, actor, operation, data
                    )
            else:
                raise HTTPException(404)
        elif action == "current" and not request.query_params:
            result = await run_in_threadpool(service.current, actor)
        elif action == "status" and set(request.query_params) == {"operation_id"}:
            operation = ID.validate_python(
                request.query_params["operation_id"], strict=True
            )
            result = await run_in_threadpool(service.status, actor, operation)
        else:
            raise HTTPException(404)
        return JSONResponse(result, headers=HEADERS)
    except HTTPException as error:
        status = error.status_code
    except (ValueError, KeyError, TypeError, ValidationError):
        status = 400
    except CatalogStoreError as error:
        status = {
            ErrorCode.DENIED: 403,
            ErrorCode.INVALID: 409,
            ErrorCode.CONFLICT: 409,
            ErrorCode.IDENTITY_CONFLICT: 409,
        }.get(error.code, 503)
    except Exception:
        logger.exception("billing operation unavailable", exc_info=False)
        status = 503
    return JSONResponse(
        {
            "detail": {
                "code": "billing_unavailable"
                if status == 503
                else "billing_terms_unavailable"
                if status == 409
                else "billing_rejected"
            }
        },
        status_code=status,
        headers=HEADERS,
    )
