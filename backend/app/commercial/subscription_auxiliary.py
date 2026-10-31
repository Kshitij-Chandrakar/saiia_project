"""Existing history/Notes/Ask AI services using the reviewed native authority."""

import hashlib
import json
from typing import Any, cast

from starlette.requests import Request

from app.cloud import interview_ask_ai as ask
from app.cloud import interview_notes as notes
from app.cloud import interview_transcripts as transcripts
from app.cloud.interview_sessions import (
    CloudInterviewSessionNotFoundError,
    CloudInterviewSessionService,
)
from app.commercial.account_entitlements import json_query
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.subscription_execution import (
    SubscriptionSessions,
    execution_service,
)


class Auxiliary:
    def __init__(self, request: Request) -> None:
        self.service, self.actor = execution_service(request)
        self.request = request

    def call(self, action: str, **document: Any) -> Any:
        subject = self.service._channel._actor(self.actor)
        if document.pop("user_id", subject) != subject:
            raise CloudInterviewSessionNotFoundError("Resource was not found.")
        try:

            def work(q: Any) -> Any:
                q("SELECT public.subscription_current(%s,false)", (subject,))
                self.service._read(q, subject)
                return json_query(
                    q,
                    "SELECT public.subscription_aux_call(%s,%s,%s::jsonb)",
                    (subject, action, json.dumps(document)),
                )

            return self.service._channel._transaction(True, work)
        except CatalogStoreError as error:
            if error.code == ErrorCode.NOT_FOUND:
                raise CloudInterviewSessionNotFoundError(
                    "Resource was not found."
                ) from None
            raise


class Sessions(SubscriptionSessions):
    def __init__(self, request: Request, legacy: Any) -> None:
        super().__init__(request)
        self.native = Auxiliary(request)
        self.legacy = legacy

    def list_sessions(
        self, *, user_id: str, limit: int, page: int, statuses: Any = None
    ) -> Any:
        from fastapi import HTTPException

        from app.cloud.interview_sessions import (
            InterviewSessionListPage,
            _record_from_payload,
        )

        if not 1 <= limit <= 100 or not 1 <= page <= 1000:
            raise HTTPException(422, detail={"code": "invalid_pagination"})
        doc = dict(user_id=user_id, limit=limit, offset=(page - 1) * limit)
        if statuses is not None:
            doc["statuses"] = list(statuses)
        rows = self.native.call("sessions", **doc)["items"]
        return InterviewSessionListPage(
            items=[_record_from_payload(r) for r in rows], limit=limit, page=page
        )

    def create_session(self, **kw: Any) -> Any:
        self.service.require_feature(self.actor, "answers.generate")
        return self.legacy().create_session(**kw)

    def end_session(self, **kw: Any) -> Any:
        self.get_session(user_id=kw["user_id"], session_id=kw["session_id"])
        return self.legacy().end_session(**kw)


class TranscriptsClient(Auxiliary):
    def delete_transcript_entries(self, *, user_id: str, session_id: str) -> Any:
        return self.call("transcripts.clear", user_id=user_id, session_id=session_id)[
            "deleted_count"
        ]

    def list_transcript_entries(
        self, *, user_id: str, session_id: str, limit: int, page: int
    ) -> Any:
        rows = self.call(
            "transcripts",
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            offset=(page - 1) * limit,
        )["items"]
        return [transcripts._entry_from_payload(row) for row in rows]


class NotesClient(Auxiliary):
    claim: Any = None

    def get_notes(self, *, user_id: str, session_id: str) -> Any:
        return notes._record_from_payload(
            self.call("notes.read", user_id=user_id, session_id=session_id)
        )

    def upsert_notes(self, *, user_id: str, session_id: str, payload: Any) -> Any:
        return notes._record_from_payload(
            self.call(
                "notes.complete",
                user_id=user_id,
                session_id=session_id,
                payload=payload,
                **self.claim
            )
        )


class NotesService(notes.CloudInterviewNotesService):
    _client: NotesClient

    def generate_notes(
        self, *, user_id: str, session_id: str, force_regenerate: bool = False
    ) -> Any:
        from app.commercial.admission import validated_request_key

        key = validated_request_key(self._client.request.headers.get("Idempotency-Key"))
        semantic = hashlib.sha256(
            json.dumps([session_id, force_regenerate]).encode()
        ).hexdigest()
        claim = self._client.call(
            "notes.claim",
            user_id=user_id,
            session_id=session_id,
            request_id=key,
            semantic_hash=semantic,
        )
        if claim.get("failed"):
            from fastapi import HTTPException

            raise HTTPException(409, detail={"code": "notes_operation_failed"})
        if not claim.get("claimed"):
            return notes._record_from_payload(claim["result"])
        self._client.claim = {
            k: claim[k] for k in ("operation_id", "claim_token", "fence")
        }
        try:
            # Explicit new generation; durable same-key replay was resolved above.
            return super().generate_notes(
                user_id=user_id, session_id=session_id, force_regenerate=True
            )
        finally:
            try:
                self._client.call(
                    "notes.fail",
                    user_id=user_id,
                    session_id=session_id,
                    **self._client.claim
                )
            except (CatalogStoreError, CloudInterviewSessionNotFoundError):
                pass


class AskClient(Auxiliary):
    def claim_request_key(self, **kw: Any) -> Any:
        r = self.call("ask.claim", **kw)
        return ask._request_key_from_payload(r), r["claimed"]

    def get_request_key(self, **kw: Any) -> Any:
        return ask._request_key_from_payload(self.call("ask.key", **kw))

    def fail_request_key(self, **kw: Any) -> Any:
        return ask._request_key_from_payload(self.call("ask.fail", **kw))

    def reclaim_stale_request_key(self, **kw: Any) -> Any:
        kw["stale_before"] = kw["stale_before"].isoformat()
        self.call("ask.expire", **kw)
        return None, False  # Never redispatch an uncertain generation.

    def get_message(self, **kw: Any) -> Any:
        return ask._record_from_payload(self.call("ask.message", **kw))

    def complete_turn(self, **kw: Any) -> Any:
        row = self.call("ask.complete", **kw)
        common = {k: kw[k] for k in ("user_id", "session_id")}
        return self.get_message(
            **common, message_id=row["user_message_id"]
        ), self.get_message(**common, message_id=row["assistant_message_id"])

    def list_messages_window(self, **kw: Any) -> Any:
        rows = self.call("ask.messages", **kw)["items"]
        return [ask._record_from_payload(r) for r in reversed(rows)]

    def list_recent_messages(self, **kw: Any) -> Any:
        return self.list_messages_window(**kw, offset=0)


def transcript_service(request: Request) -> Any:
    return transcripts.CloudInterviewTranscriptService(
        client=TranscriptsClient(request)
    )


def notes_service(request: Request, existing: Any) -> Any:
    return NotesService(
        client=NotesClient(request),
        session_service=cast(
            CloudInterviewSessionService, SubscriptionSessions(request)
        ),
        transcript_service=transcript_service(request),
        generator=existing._generator,
    )


def ask_service(request: Request, existing: Any, notes_existing: Any) -> Any:
    return ask.CloudInterviewAskAIService(
        client=AskClient(request),
        session_service=cast(
            CloudInterviewSessionService, SubscriptionSessions(request)
        ),
        transcript_service=transcript_service(request),
        notes_service=notes_service(request, notes_existing),
        generator=existing._generator,
    )
