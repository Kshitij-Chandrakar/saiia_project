"""Native adapters for the existing owned-session and durable-turn contracts."""

import asyncio
import json
from typing import Any

from fastapi import HTTPException
from starlette.requests import Request

from app.cloud.interview_sessions import CloudInterviewSessionRecord
from app.commercial.account_entitlements import json_query
from app.commercial.admin_access import VerifiedActor, verified_actor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.subscription_service import SubscriptionService


def execution_service(
    request: Request | None,
) -> tuple[SubscriptionService, VerifiedActor]:
    app = request.scope.get("app") if request is not None else None
    runtime = getattr(app.state, "subscriptions", None) if app is not None else None
    if runtime is None:
        raise HTTPException(503, detail={"code": "subscription_unavailable"})
    assert request is not None
    try:
        return runtime.service(), verified_actor(request)
    except CatalogStoreError:
        raise HTTPException(503, detail={"code": "subscription_unavailable"}) from None


class SubscriptionSessions:
    def __init__(self, request: Request) -> None:
        self.service, self.actor = execution_service(request)

    def get_session(
        self, *, user_id: str, session_id: str, allow_model_bound: bool = False
    ) -> CloudInterviewSessionRecord:
        from app.cloud.interview_sessions import (
            CloudInterviewSessionNotFoundError,
            _record_from_payload,
        )

        try:
            subject = self.service._channel._actor(self.actor)
            if subject != user_id:
                raise CatalogStoreError(ErrorCode.NOT_FOUND)
            row = self.service._channel._transaction(
                False,
                lambda q: json_query(
                    q,
                    "SELECT public.subscription_session_read(%s,%s)",
                    (subject, session_id),
                ),
            )
            return _record_from_payload(row)
        except CatalogStoreError as error:
            if error.code == ErrorCode.NOT_FOUND:
                raise CloudInterviewSessionNotFoundError(
                    "Interview session was not found."
                ) from None
            raise HTTPException(
                403 if error.code == ErrorCode.DENIED else 503,
                detail={
                    "code": (
                        "subscription_denied"
                        if error.code == ErrorCode.DENIED
                        else "subscription_unavailable"
                    )
                },
            ) from None


class SubscriptionTurns:
    def __init__(self, request: Request) -> None:
        self.service, self.actor = execution_service(request)
        self.lease = request.scope.get("state", {}).get("_subscription_auto")

    async def operation(
        self,
        action: str,
        identity: dict[str, Any],
        *,
        token: str | None = None,
        payload: Any = None
    ) -> dict[str, Any]:
        from app.session_generation import TurnStateError

        try:
            subject = (
                self.actor.subject_id
                if action in ("cancel", "fail")
                else await asyncio.to_thread(self.service._channel._actor, self.actor)
            )
            if subject != identity["p_user_id"]:
                raise CatalogStoreError(ErrorCode.DENIED)
            params: tuple[Any, ...] = (
                action,
                subject,
                identity["p_session_id"],
                identity["p_request_id"],
                identity["p_hash"],
                identity["p_attempt"],
                identity["p_supersedes"],
                token,
                json.dumps(payload) if payload is not None else None,
            )
            if self.lease is not None:
                from app.commercial.subscription_auto import AccountAutoLease

                if (
                    not isinstance(self.lease, AccountAutoLease)
                    or self.lease.row is None
                    or self.lease.actor.subject_id != subject
                ):
                    raise CatalogStoreError(ErrorCode.DENIED)
                sql = "SELECT public.subscription_auto_turn(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)"
                params += (
                    self.lease.row["run_id"],
                    self.lease.row["owner_token"],
                    self.lease.row["fence"],
                    self.lease.source,
                )
            else:
                sql = "SELECT public.subscription_answer_turn(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)"
            result = await asyncio.to_thread(
                self.service._channel._transaction,
                True,
                lambda q: json_query(
                    q,
                    sql,
                    params,
                ),
            )
            if result.get("error"):
                safe = (
                    result["error"]
                    if result["error"]
                    in {
                        "session_not_found",
                        "session_ended",
                        "generation_unrecoverable",
                        "attempt_conflict",
                        "payload_conflict",
                        "stale_attempt",
                        "invalid_result",
                        "payload_too_large",
                        "invalid_operation",
                    }
                    else "persistence_unavailable"
                )
                raise TurnStateError(safe)
            return result
        except CatalogStoreError as error:
            if error.code == ErrorCode.DENIED:
                raise HTTPException(
                    403, detail={"code": "subscription_denied"}
                ) from None
            raise TurnStateError("persistence_unavailable") from None
