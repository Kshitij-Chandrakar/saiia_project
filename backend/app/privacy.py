"""Closed C15 confirmation/status boundary. No purge or provider execution."""

import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.auth.supabase_auth import (
    CurrentUser,
    SupabaseAuthConfigurationError,
    SupabaseAuthError,
    _bearer_token_from_request,
    verify_supabase_token,
)
from app.commercial.account_entitlements import json_query
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_service import DraftService

POLICY = "c15.2026-10-29.v1"
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
router = APIRouter()


class Challenge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    confirmation_token: str = Field(
        min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    status_token: str = Field(
        min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    policy_version: str = Field(pattern=r"^c15\.2026-10-29\.v1$")
    scope: str = Field(pattern=r"^whole_account$")


class Confirmation(Challenge):
    proof_method: str = Field(
        default="reauthentication", pattern=r"^(reauthentication|email_otp)$"
    )
    confirmation_text: str = Field(pattern=r"^delete$")


class EmailCode(Challenge):
    code: str = Field(pattern=r"^[0-9]{8}$")


class Status(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    status_token: str = Field(
        min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def recent_presence(user: CurrentUser) -> tuple[str, str]:
    """Only Auth-signed AMR/session/issuance method, never iat or client claims.

    OAuth alone can reuse provider SSO and is deliberately NOT user-presence proof.
    Existing Google users need verified TOTP or a separately reviewed reauth path.
    """
    claims = user.claims or {}
    try:
        session = str(UUID(claims["session_id"]))
        method = claims["c15_auth_method"]
        if method not in {"password", "totp"}:
            raise ValueError()
        stamps = [
            item["timestamp"]
            for item in claims.get("amr", [])
            if isinstance(item, dict)
            and item.get("method") == method
            and type(item.get("timestamp")) is int
        ]
        timestamp = max(stamps)
        if not 0 <= time.time() - timestamp <= 300:
            raise ValueError()
        if method == "totp" and claims.get("aal") != "aal2":
            raise ValueError()
        return session, datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(
            403, detail={"code": "privacy_reauthentication_required"}
        ) from None


class PrivacyService:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self.channel = DraftService(connect)

    def call(
        self, actor: VerifiedActor, action: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        subject = self.channel._actor(actor)
        if action == "confirm":
            from app.privacy_credentials import CredentialBox, CredentialUnavailable

            try:
                identity = verify_supabase_token(actor._bearer)
                envelope = CredentialBox.configured().seal(
                    actor._bearer,
                    subject,
                    document["request_id"],
                    int((identity.claims or {})["exp"]),
                )
                document = {**document, "revocation_credential": envelope}
            except (CredentialUnavailable, ValueError, KeyError):
                # Accepted replays still recover through SQL. New acceptance
                # fails closed without an envelope in the required protocol.
                pass

        def execute(query: Any) -> dict[str, Any]:
            if (
                action == "confirm"
                and query("SELECT public.privacy_credential_protocol()", ()) != 1
            ):
                raise CatalogStoreError(ErrorCode.UNAVAILABLE)
            return json_query(
                query,
                "SELECT public.privacy_request_call(%s,%s,%s::jsonb)",
                (subject, action, json.dumps(document)),
            )

        return self.channel._transaction(
            action != "status",
            execute,
        )

    def status(self, document: dict[str, Any]) -> dict[str, Any]:
        def execute(query: Any) -> dict[str, Any]:
            result = json_query(
                query,
                "SELECT public.privacy_request_call(null,'status',%s::jsonb)",
                (json.dumps(document),),
            )
            # Validate the existing scoped receipt before reading new progress.
            if query(
                "SELECT to_regprocedure('public.privacy_content_status(uuid)') is not null",
                (),
            ):
                result.update(
                    json_query(
                        query,
                        "SELECT public.privacy_content_status(%s::uuid)",
                        (document["request_id"],),
                    )
                )
            return result

        return self.channel._transaction(
            False,
            execute,
        )


@router.post("/api/privacy/deletion/{action}")
async def deletion(request: Request, action: str) -> JSONResponse:
    from app.config import settings

    if (
        getattr(settings, "C15_RESTRICTIONS_REQUIRED", "false") != "true"
        or settings.SUBSCRIPTIONS_ENABLED != "true"
        or (action != "status" and getattr(settings, "C15_ENABLED", "false") != "true")
    ):
        return JSONResponse(
            {"detail": {"code": "privacy_unavailable"}}, 404, headers=HEADERS
        )
    if (
        action
        not in {
            "begin",
            "challenge",
            "confirm",
            "status",
            "otp_start",
            "otp_verify",
            "otp_ready",
        }
        or request.url.query
    ):
        return JSONResponse(
            {"detail": {"code": "privacy_unavailable"}}, 404, headers=HEADERS
        )
    try:
        # This narrow identity-only path intentionally bypasses product access
        # checks so a restricted subject can recover its own accepted status.
        from app.commercial.billing_api import body

        raw = await body(request, 4096)
        model = (
            Status
            if action == "status"
            else (
                Confirmation
                if action == "confirm"
                else EmailCode if action == "otp_verify" else Challenge
            )
        )
        doc = model.model_validate_json(raw).model_dump()
        doc["request_id"] = str(UUID(doc["request_id"]))
        if action != "status":
            token = _bearer_token_from_request(request)
            user = await run_in_threadpool(verify_supabase_token, token)
            if user.role != "authenticated":
                raise SupabaseAuthError()
            if action in {"begin", "otp_start", "otp_verify", "otp_ready"}:
                doc["session_id"] = str(UUID((user.claims or {})["session_id"]))
            elif action == "confirm" and doc.get("proof_method") == "email_otp":
                # Explicitly select the operation-bound mailbox receipt. A
                # still-fresh older password AMR must not override that proof.
                doc["session_id"] = str(UUID((user.claims or {})["session_id"]))
            else:
                try:
                    session, at = recent_presence(user)
                    doc.update(session_id=session, reauthenticated_at=at)
                    doc["proof_method"] = (user.claims or {})["c15_auth_method"]
                except HTTPException:
                    if action != "confirm":
                        raise
                    doc.update(
                        session_id=str(UUID((user.claims or {})["session_id"])),
                        proof_method="email_otp",
                    )
            doc["verified_email"] = user.email
            doc["confirmation_hash"] = digest(doc.pop("confirmation_token"))
        doc["status_hash"] = digest(doc.pop("status_token"))
        runtime = getattr(request.app.state, "subscriptions", None)
        if runtime is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)

        service = PrivacyService(runtime.connect)
        if (
            action in {"otp_start", "otp_verify", "otp_ready"}
            or doc.get("proof_method") == "email_otp"
        ):
            from app.privacy_credentials import CredentialBox
            from app.privacy_otp import matches, reserve

            providers = (user.claims or {}).get("app_metadata", {}).get("providers", [])
            if "google" not in providers or "email" in providers:
                raise HTTPException(403)
            box = CredentialBox.configured()
            if action == "otp_start":
                sender = getattr(request.app.state, "privacy_otp_sender", None)
                if sender is None:
                    raise CatalogStoreError(ErrorCode.UNAVAILABLE)
                code, doc = reserve(box, user.user_id, doc)
            else:
                doc.update(matches(box, user.user_id, doc, doc.pop("code", "")))
        if action == "status":
            result = await run_in_threadpool(service.status, doc)
        else:
            result = await run_in_threadpool(
                service.call, VerifiedActor(user.user_id, token), action, doc
            )
        if action == "otp_start" and result.get("state") == "otp_reserved":
            if not callable(sender) or user.email is None:
                raise CatalogStoreError(ErrorCode.UNAVAILABLE)
            await run_in_threadpool(sender, user.email, code)
            result["state"] = "otp_sent"
        return JSONResponse(result, headers=HEADERS)
    except (SupabaseAuthError, SupabaseAuthConfigurationError):
        return JSONResponse(
            {"detail": {"code": "privacy_auth_required"}}, 401, headers=HEADERS
        )
    except HTTPException as error:
        return JSONResponse(
            {"detail": {"code": "privacy_reauthentication_required"}},
            error.status_code,
            headers=HEADERS,
        )
    except (ValueError, TypeError):
        return JSONResponse(
            {"detail": {"code": "privacy_invalid_request"}}, 422, headers=HEADERS
        )
    except CatalogStoreError as error:
        code = (
            "privacy_denied"
            if error.code == ErrorCode.DENIED
            else "privacy_outcome_unknown"
        )
        return JSONResponse(
            {"detail": {"code": code}},
            403 if code == "privacy_denied" else 503,
            headers=HEADERS,
        )
    except (
        Exception
    ):  # noqa: BLE001 -- closed security boundary, never expose driver/body errors
        # Never format request bodies, email, SQL, driver errors or capabilities.
        return JSONResponse(
            {"detail": {"code": "privacy_outcome_unknown"}}, 503, headers=HEADERS
        )
