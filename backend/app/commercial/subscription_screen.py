"""Account-owned Screen history, durable replay and result-based settlement."""

import asyncio
import hashlib
import json
from typing import Any

from fastapi import HTTPException
from starlette.requests import Request

from app.commercial import catalog_contract as c
from app.commercial.account_entitlements import json_query
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.subscription_execution import execution_service
from app.models.screen_context import ScreenContextResponse


def safe_error(error: CatalogStoreError) -> HTTPException:
    status = {
        ErrorCode.DENIED: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.IDENTITY_CONFLICT: 409,
        ErrorCode.EXHAUSTED: 429,
        ErrorCode.INVALID: 422,
        ErrorCode.UNCERTAIN: 503,
    }.get(error.code, 503)
    return HTTPException(
        status, detail={"code": error.code.value}, headers={"Cache-Control": "no-store"}
    )


class AccountScreen:
    def __init__(self, request: Request) -> None:
        self.service, self.actor = execution_service(request)

    def call(self, action: str, document: Any, *, cleanup: bool = False) -> Any:
        try:
            subject = (
                self.actor.subject_id
                if cleanup
                else self.service._channel._actor(self.actor)
            )

            def work(query: Any) -> Any:
                if action in ("claim", "complete"):
                    query("SELECT public.subscription_current(%s,false)", (subject,))
                    self.service._read(
                        query, subject
                    )  # Existing exact snapshot/version validator.
                return json_query(
                    query,
                    "SELECT public.subscription_screen_call(%s,%s,%s::jsonb)",
                    (subject, action, json.dumps(document)),
                )

            return self.service._channel._transaction(
                action not in ("read", "history", "list"), work
            )
        except CatalogStoreError as error:
            raise safe_error(error) from None

    async def run(
        self, context: Any, files: Any, provider: Any
    ) -> ScreenContextResponse:
        sid = context.identity.cloudSessionId
        if not sid:
            raise HTTPException(422, detail={"code": "subscription_session_required"})
        # Request IDs are transport attempts. The existing controller retains
        # operation/turn identity on retry and on an explicit clarification.
        phase = (
            context.clarificationResponse.requestId
            if context.clarificationResponse
            else "capture"
        )
        key = hashlib.sha256(
            c.canonical_json([context.identity.operationId, phase]).encode()
        ).hexdigest()
        base = dict(
            session_id=sid, thread_key=context.identity.threadId, request_key=key
        )
        await asyncio.to_thread(
            self.service.require_feature, self.actor, "screen.analyze"
        )
        history = (await asyncio.to_thread(self.call, "history", base))["items"]
        # Compare supplied source/answer provenance with actual owned saved
        # responses. Client history cannot manufacture a free "clarification".
        by_turn = {r["turn_key"]: r["response"] for r in history if r.get("response")}
        for evidence in context.input.evidence:
            saved = by_turn.get(evidence.turnId, {})
            delta = saved.get("evidenceDelta")
            if (
                not delta
                or evidence.text != delta["text"]
                or evidence.complete != delta["complete"]
                or evidence.imageHashes
                and evidence.imageHashes != delta["imageHashes"]
            ):
                raise HTTPException(409, detail={"code": "screen_context_stale"})
            if evidence.imageHash not in delta["imageHashes"]:
                raise HTTPException(409, detail={"code": "screen_context_stale"})
        for answer in context.input.answers:
            if by_turn.get(answer.turnId, {}).get("answer") != answer.text:
                raise HTTPException(409, detail={"code": "screen_context_stale"})
        for prior in context.priorItems:
            if not any(
                x["question_id"] == prior.questionId
                for x in by_turn.get(prior.turnId, {}).get("items", [])
            ):
                raise HTTPException(409, detail={"code": "screen_context_stale"})
        if context.clarificationResponse:
            reply = context.clarificationResponse
            if not any(
                r["response"].get("outcome") == "needs_clarification"
                and (
                    r["response"]["identity"]["requestId"] == reply.requestId
                    or reply.requestId in r["request_aliases"]
                )
                and r["turn_key"] == reply.turnId
                for r in history
            ):
                raise HTTPException(409, detail={"code": "screen_clarification_stale"})
        hashes = {
            name: hashlib.sha256(value).hexdigest() for name, value in files.items()
        }
        semantics = context.model_dump(mode="json")
        semantics["identity"].pop("requestId")
        semantic = hashlib.sha256(
            c.canonical_json([semantics, hashes]).encode()
        ).hexdigest()
        document = {
            **base,
            "semantic_hash": semantic,
            "request_id": context.identity.requestId,
            "turn_key": context.identity.turnId,
            "revision": context.identity.baseRevision,
            "intent": context.action,
            "reply_key": (
                context.clarificationResponse.requestId
                if context.clarificationResponse
                else None
            ),
        }
        row = await asyncio.to_thread(self.call, "claim", document)
        if not row.get("claimed"):
            if row["state"] == "completed":
                return ScreenContextResponse.model_validate(row["response"]).model_copy(
                    update={"identity": context.identity}
                )
            raise HTTPException(
                409,
                detail={
                    "code": (
                        "screen_outcome_unresolved"
                        if row["state"] == "processing"
                        else "screen_operation_failed"
                    )
                },
            )
        token = row["token"]
        try:
            response = ScreenContextResponse.model_validate(
                await provider(context, files)
            )
            if response.identity != context.identity:
                raise ValueError("Mismatched result identity")
            result = await asyncio.to_thread(
                self.call,
                "complete",
                {**base, "token": token, "response": response.model_dump(mode="json")},
            )
            return ScreenContextResponse.model_validate(result["response"])
        except (ValueError, TypeError):
            raise HTTPException(502, detail={"code": "screen_result_invalid"}) from None
        finally:
            # Complete + settlement is atomic. If its acknowledgement was lost,
            # fail observes completed and does nothing. Never blindly regenerate.
            cleanup = asyncio.create_task(
                asyncio.to_thread(
                    self.call, "fail", {**base, "token": token}, cleanup=True
                )
            )
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            try:
                cleanup.result()
            except HTTPException:
                pass  # Durable expiry recovery retains fencing.
