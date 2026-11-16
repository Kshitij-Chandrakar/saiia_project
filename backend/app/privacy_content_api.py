"""Default-closed local adapter. No hosted database or Storage composition."""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, StreamingResponse

from app.auth.supabase_auth import _bearer_token_from_request, verify_supabase_token
from app.privacy import HEADERS, recent_presence
from app.privacy_content import ContentBlocked

router = APIRouter()
ACTIONS = frozenset(
    {
        "sessions",
        "begin",
        "download_begin",
        "otp_start",
        "otp_verify",
        "confirm",
        "status",
        "authorize",
        "download",
    }
)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    cursor: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    operation_scope: str = Field(
        default="export", pattern=r"^(export|session|history)$"
    )
    resource_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    confirmation_text: str = Field(default="", max_length=6)
    code: str = Field(default="", max_length=8, pattern=r"^[0-9]*$")
    capability: str = Field(default="", max_length=128, pattern=r"^[A-Za-z0-9_-]*$")


@router.post("/api/privacy/content/{action}")
async def content(request: Request, action: str):
    # Normal composition uses restricted fixed operations. The historical
    # local adapter remains available only to existing isolated fixtures.
    engine = getattr(request.app.state, "privacy_content", None) or getattr(
        request.app.state, "privacy_content_local", None
    )
    if engine is None or action not in ACTIONS or request.url.query:
        return JSONResponse(
            {"detail": {"code": "privacy_unavailable"}}, 404, headers=HEADERS
        )
    try:
        from app.commercial.billing_api import body

        document = Document.model_validate_json(await body(request, 2048))
        job_id = str(UUID(document.request_id))
        user = verify_supabase_token(_bearer_token_from_request(request))
        if user.role != "authenticated":
            raise ContentBlocked("denied")
        account = str(UUID(user.user_id))
        box = getattr(request.app.state, "privacy_export_box", None)
        if action == "sessions":
            result = await run_in_threadpool(engine.sessions, account, document.cursor)
        elif action in {
            "begin",
            "download_begin",
            "otp_start",
            "otp_verify",
            "confirm",
        }:
            if action == "confirm" and document.confirmation_text != (
                "export" if document.operation_scope == "export" else "delete"
            ):
                raise ContentBlocked("type_export_to_confirm")
            result = await run_in_threadpool(
                engine.proof,
                user,
                job_id,
                action,
                box=box,
                code=document.code,
                sender=getattr(request.app.state, "privacy_export_sender", None),
                operation_scope=document.operation_scope,
                resource=document.resource_id,
            )
        elif action == "status":
            result = await run_in_threadpool(engine.status, account, job_id)
        elif action == "authorize":
            # Existing fresh password/TOTP proof; mailbox receipt is separately
            # checked for this same export request, not a deletion receipt.
            try:
                recent_presence(user)
            except HTTPException:
                await run_in_threadpool(engine.download_presence, user, job_id, box)
            result = {
                "capability": await run_in_threadpool(engine.authorize, account, job_id)
            }
        else:
            stream = await run_in_threadpool(
                engine.download, account, job_id, document.capability
            )
            return StreamingResponse(
                stream,
                media_type="application/zip",
                headers={
                    **HEADERS,
                    "Content-Disposition": 'attachment; filename="account-export.zip"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return JSONResponse(jsonable_encoder(result), headers=HEADERS)
    except ContentBlocked as error:
        category = str(error).split(":", 1)[0]
        if not re.fullmatch(r"[a-z_]{1,64}", category):
            category = "scope_unavailable"
        logging.getLogger("privacy").info("Privacy request blocked: %s", category)
        return JSONResponse(
            {"detail": {"code": "privacy_scope_blocked"}}, 409, headers=HEADERS
        )
    except Exception as error:  # noqa: BLE001 -- no credentials, payloads or driver errors in responses
        logging.getLogger("privacy").warning(
            "Privacy outcome unknown: type=%s sqlstate=%s relation=%s column=%s frames=%s",
            type(error).__name__,
            getattr(error, "sqlstate", None),
            getattr(getattr(error, "diag", None), "table_name", None),
            getattr(getattr(error, "diag", None), "column_name", None),
            [
                (t.name, t.lineno)
                for t in __import__("traceback").extract_tb(error.__traceback__)
            ],
        )
        return JSONResponse(
            {"detail": {"code": "privacy_outcome_unknown"}}, 503, headers=HEADERS
        )
