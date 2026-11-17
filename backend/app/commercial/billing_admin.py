"""Billing-only admin reads and state-bound queued commands; no paid overrides."""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.commercial.admin_access import verified_actor
from app.commercial.billing_api import HEADERS, body
from app.commercial.draft_service import DraftService
from app.email.delivery import DeliveryConflict, configuration

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/billing/email/events")
async def billing_delivery(request: Request):
    from app.config import settings

    service = getattr(request.app.state, "billing_notifications", None)
    if service is None or not settings.RESEND_BILLING_WEBHOOK_SECRET:
        raise HTTPException(503)
    try:
        configuration(
            settings.RESEND_BILLING_WEBHOOK_SECRET,
            settings.RESEND_BILLING_WEBHOOK_SCOPE,
        )
        if (
            request.headers.get("content-type", "").split(";")[0].strip()
            != "application/json"
            or request.headers.get("content-encoding", "identity") != "identity"
        ):
            raise HTTPException(415)
        for name in ("svix-id", "svix-timestamp", "svix-signature"):
            if len(request.headers.getlist(name)) != 1:
                raise ValueError()
        raw = await asyncio.wait_for(body(request, 131072), timeout=10)
        result = await asyncio.wait_for(
            run_in_threadpool(
                service.delivery,
                raw,
                request.headers,
                settings.RESEND_BILLING_WEBHOOK_SECRET,
            ),
            timeout=15,
        )
        return result
    except DeliveryConflict:
        raise HTTPException(409) from None
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(400) from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("Billing delivery unavailable", exc_info=False)
        raise HTTPException(503) from None


class BillingAdmin:
    def __init__(self, connect, billing, notifications):
        self.channel = DraftService(connect)
        self.billing = billing
        self.notifications = notifications

    def call(self, actor, action, account=None, document=None):
        subject = self.channel._actor(actor)
        account = str(UUID(account)) if account else None
        return self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_admin_call(%s,%s,%s,%s::jsonb)",
                (subject, action, account, json.dumps(document or {})),
            ),
        )

    def run(self):
        command = self.channel._transaction(
            True, lambda q: q("SELECT public.billing_admin_work()", ())
        )
        if not command:
            return
        outcome = "confirmed"
        try:
            if command["action"] == "reconcile":
                self.billing.reconcile(command["account_id"], command["target"])
            else:
                self.notifications.run()
        except Exception:
            logger.exception("Billing command result unknown", exc_info=False)
            outcome = "unknown"
        self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_admin_work(%s,%s)", (command["id"], outcome)
            ),
        )


@router.api_route("/api/admin/billing/{account}", methods=["GET", "POST"])
async def billing_admin(request: Request, account: str):
    actor = verified_actor(request)
    service = getattr(request.app.state, "billing_admin", None)
    if service is None:
        raise HTTPException(503)
    try:
        if request.method == "GET":
            result = await run_in_threadpool(
                service.call,
                actor,
                "access" if account == "access" else "inspect",
                None if account == "access" else account,
            )
        else:
            document = json.loads(
                await asyncio.wait_for(body(request, 4096), timeout=10)
            )
            review = document.get("review") is True
            expected = (
                {"action", "operation_id", "target", "review"}
                if review
                else {
                    "action",
                    "operation_id",
                    "target",
                    "revision",
                    "review_id",
                    "confirm",
                }
            )
            if (
                set(document) != expected
                or document["action"] not in ("reconcile", "retry_notification")
                or (not review and document["confirm"] is not True)
            ):
                raise ValueError()
            for key in ("operation_id", "target"):
                document[key] = str(UUID(document[key]))
            if review:
                document.pop("review")
                action = "review"
            else:
                document["review_id"] = str(UUID(document["review_id"]))
                action = document.pop("action")
            result = await run_in_threadpool(
                service.call, actor, action, account, document
            )
        from starlette.responses import JSONResponse

        status = {"denied": 403, "conflict": 409}.get(result.get("error"), 200)
        return JSONResponse(result, status_code=status, headers=HEADERS)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400) from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("Billing administration unavailable", exc_info=False)
        raise HTTPException(503) from None
