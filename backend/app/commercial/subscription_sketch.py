"""Verified per-request adapter over the existing Sketch persistence contract."""

import json
from collections.abc import Callable
from typing import Any

from app.cloud.answer_diagrams import DiagramError
from app.commercial.account_entitlements import json_query, validated_terms
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_service import Query
from app.commercial.subscription_service import SubscriptionService


class SubscriptionSketchStore:
    def __init__(self, service: SubscriptionService, actor: VerifiedActor) -> None:
        self.service, self.actor = service, actor

    def _call(
        self, user: str, write: bool, work: Callable[[Query], dict[str, Any]]
    ) -> dict[str, Any]:
        try:
            subject = self.service._channel._actor(self.actor)
            if subject != user:
                raise CatalogStoreError(ErrorCode.DENIED)
            return self.service._channel._transaction(write, work)
        except CatalogStoreError as error:
            code, status = {
                ErrorCode.DENIED: ("subscription_denied", 403),
                ErrorCode.NOT_FOUND: ("source_not_found", 404),
                ErrorCode.INVALID: ("invalid_operation", 422),
                ErrorCode.IDENTITY_CONFLICT: ("operation_conflict", 409),
                ErrorCode.CONFLICT: ("operation_conflict", 409),
            }.get(error.code, ("subscription_unavailable", 503))
            raise DiagramError(code, status) from None

    def source(
        self,
        user: str,
        session: str,
        *,
        transcript: str | None = None,
        request: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        result = self._call(
            user,
            False,
            lambda q: json_query(
                q,
                "SELECT public.subscription_sketch_source(%s,%s,%s,%s)",
                (user, session, transcript, request),
            ),
        )
        return result["descriptor"], result["source"]

    def authorize_generation(self, user: str) -> None:
        if self.actor.subject_id != user:
            raise DiagramError("subscription_denied", 403)
        try:
            self.service.require_feature(self.actor, "sketch.generate")
        except CatalogStoreError as error:
            raise DiagramError(
                (
                    "subscription_denied"
                    if error.code == ErrorCode.DENIED
                    else "subscription_unavailable"
                ),
                403 if error.code == ErrorCode.DENIED else 503,
            ) from None

    def operation(
        self,
        action: str,
        user: str,
        session: str,
        transcript: str,
        revision: str,
        operation_id: str | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        if set(kwargs) - {"token", "graph", "model", "code"}:
            raise DiagramError("invalid_operation", 422)

        def work(query: Query) -> dict[str, Any]:
            if action not in ("read", "cancel", "fail"):
                record = json_query(
                    query, "SELECT public.subscription_current(%s,false)", (user,)
                )
                validated_terms(record, self.service._models)
            return json_query(
                query,
                "SELECT public.subscription_sketch_operation(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
                (
                    user,
                    session,
                    transcript,
                    revision,
                    operation_id,
                    action,
                    kwargs.get("token"),
                    (
                        json.dumps(kwargs["graph"])
                        if kwargs.get("graph") is not None
                        else None
                    ),
                    kwargs.get("model"),
                    kwargs.get("code"),
                ),
            )

        result = self._call(user, True, work)
        if result.get("error"):
            safe = (
                result["error"]
                if result["error"]
                in {
                    "source_not_found",
                    "ineligible_source",
                    "stale_source",
                    "stale_operation",
                    "invalid_operation",
                }
                else "unavailable"
            )
            raise DiagramError(safe, 409)
        return result
