"""Native authority at the existing resume metadata/activation boundaries."""

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from starlette.requests import Request

from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeNotFoundError,
    CloudResumeService,
    _record_from_payload,
)
from app.commercial.account_entitlements import json_query
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.subscription_execution import execution_service


class AccountResumeClient:
    def __init__(self, request: Request, delegate: Any) -> None:
        self.service, self.actor = execution_service(request)
        self.delegate = delegate
        self.request_key: str | None = None
        self.semantic_hash: str | None = None

    def call(self, action: str, **document: Any) -> Any:
        subject = self.service._channel._actor(self.actor)
        try:

            def work(query: Any) -> Any:
                if action not in ("read", "list"):
                    query("SELECT public.subscription_current(%s,false)", (subject,))
                    self.service._read(query, subject)
                return json_query(
                    query,
                    "SELECT public.subscription_resume_call(%s,%s,%s::jsonb)",
                    (subject, action, json.dumps(document)),
                )

            return self.service._channel._transaction(
                action not in ("list", "read"), work
            )
        except CatalogStoreError as error:
            if error.code == ErrorCode.NOT_FOUND:
                raise CloudResumeNotFoundError("Resume was not found.") from None
            if error.code in (ErrorCode.CONFLICT, ErrorCode.IDENTITY_CONFLICT):
                raise CloudResumeConflictError(
                    "Resume state or request identity changed. Refresh before retrying."
                ) from None
            raise

    def __getattr__(self, name: Any) -> Any:
        # Object storage and chunk indexing remain in the accepted service.
        return getattr(self.delegate, name)

    def upload_resume_object(self, path: str, content: Any, mime: str) -> Any:
        from app.cloud.cloud_resume import CloudResumeError

        try:
            self.delegate.upload_resume_object(path, content, mime)
        except CloudResumeError:
            # Same-key storage acknowledgement loss: compare the exact owned
            # object before declaring failure. Never overwrite a different file.
            if self.delegate.download_resume_object(path) != content:
                raise

    def insert_resume_metadata(self, payload: Any) -> Any:
        return _record_from_payload(
            self.call(
                "insert",
                resume_id=payload["id"],
                payload=payload,
                request_key=self.request_key,
                semantic_hash=self.semantic_hash,
            )
        )

    def get_resume(self, resume_id: str, user_id: str) -> Any:
        if user_id != self.actor.subject_id:
            raise CloudResumeNotFoundError("Resume was not found.")
        return _record_from_payload(self.call("read", resume_id=resume_id))

    def list_resumes(self, user_id: str) -> Any:
        if user_id != self.actor.subject_id:
            raise CloudResumeNotFoundError("Resume was not found.")
        return [_record_from_payload(row) for row in self.call("list")["items"]]

    def get_current_resume(self, user_id: str) -> Any:
        return next(
            (
                r
                for r in self.list_resumes(user_id)
                if r.is_active and r.status == "ready"
            ),
            None,
        )

    def get_review_candidate(self, user_id: str) -> Any:
        return next(
            (
                r
                for r in self.list_resumes(user_id)
                if r.status == "needs_review" and not r.confirmed_at
            ),
            None,
        )

    def update_resume(self, resume_id: str, user_id: str, payload: Any) -> Any:
        self.get_resume(resume_id, user_id)
        return _record_from_payload(
            self.call("update", resume_id=resume_id, payload=payload)
        )

    def compare_and_set_resume(
        self,
        resume_id: str,
        user_id: str,
        from_statuses: Any,
        payload: Any,
        *,
        extraction_attempt: int | None = None,
    ) -> Any:
        self.get_resume(resume_id, user_id)
        document = dict(
            resume_id=resume_id, payload=payload, statuses=sorted(from_statuses)
        )
        if extraction_attempt is not None:
            document["attempt"] = extraction_attempt
        return _record_from_payload(self.call("update", **document))

    def activate_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
        extraction_attempt: int,
        generation_id: str,
        confirmed_profile: Any,
    ) -> Any:
        self.get_resume(resume_id, user_id)
        return _record_from_payload(
            self.call(
                "activate",
                resume_id=resume_id,
                attempt=extraction_attempt,
                generation=generation_id,
                profile=confirmed_profile,
            )
        )

    def authorize_use(self, user_id: str, resume_id: str) -> Any:
        self.get_resume(resume_id, user_id)
        return _record_from_payload(self.call("use", resume_id=resume_id))

    def activate_rebuilt_resume_generation(
        self,
        *,
        user_id: str,
        resume_id: str,
        expected_active_generation: str,
        new_generation_id: str,
    ) -> Any:
        self.authorize_use(user_id, resume_id)
        return _record_from_payload(
            self.call(
                "rebuild",
                resume_id=resume_id,
                expected_generation=expected_active_generation,
                generation=new_generation_id,
            )
        )


class AccountResumeService(CloudResumeService):
    request: Request
    _client: AccountResumeClient

    def list_resume_readiness(self, *, user_id: str, records: Any) -> Any:
        from app.cloud.cloud_resume import ResumeReadiness

        result = super().list_resume_readiness(user_id=user_id, records=records)
        for record in records:
            if not result[record.id].can_generate:
                continue
            try:
                self._client.authorize_use(user_id, record.id)
            except CatalogStoreError as error:
                if error.code != ErrorCode.DENIED:
                    raise
                result[record.id] = ResumeReadiness(
                    chunk_count=result[record.id].chunk_count,
                    can_generate=False,
                    readiness_reason="subscription_access_denied",
                )
        return result

    def confirm_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
        extraction_attempt: int,
        confirmed_profile: Any,
    ) -> Any:
        from app.cloud.cloud_resume import ConfirmResult, validate_confirmed_profile

        current = self._client.get_resume(resume_id, user_id)
        profile = validate_confirmed_profile(confirmed_profile)
        if current.status == "ready":
            if not current.active_chunk_generation:
                raise CatalogStoreError(ErrorCode.STORED_INVALID)
            # Recover an activation whose commit acknowledgement was lost. The
            # same SQL checks current permission and exact saved review identity.
            row = self._client.activate_resume(
                user_id=user_id,
                resume_id=resume_id,
                extraction_attempt=extraction_attempt,
                generation_id=current.active_chunk_generation,
                confirmed_profile=profile,
            )
            count = self._client.get_active_resume_chunk_counts(
                user_id=user_id, records=[row]
            ).get((row.id, row.active_chunk_generation), 0)
            return ConfirmResult(
                resume_id=row.id,
                status=row.status,
                extraction_attempt=row.extraction_attempt,
                confirmed_profile_saved=True,
                next_step="resume_ready",
                chunks_indexed=True,
                chunk_count=count,
                ready=True,
                active=row.is_active,
            )
        return super().confirm_resume(
            user_id=user_id,
            resume_id=resume_id,
            extraction_attempt=extraction_attempt,
            confirmed_profile=profile,
        )

    def upload_resume(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None,
        resume_id: str | None = None,
    ) -> Any:
        # HTTP key is validated once; identical transport retries address the
        # same existing metadata/object, never a fresh stored slot.
        from app.commercial.admission import validated_request_key

        try:
            key = validated_request_key(self.request.headers.get("Idempotency-Key"))
        except Exception:
            raise CatalogStoreError(ErrorCode.INVALID) from None
        self._client.request_key = key
        self._client.semantic_hash = hashlib.sha256(
            json.dumps(
                [filename, content_type, hashlib.sha256(content).hexdigest()]
            ).encode()
        ).hexdigest()
        identifier = str(uuid5(NAMESPACE_URL, f"subscription.resume:{user_id}:{key}"))
        return super().upload_resume(
            user_id=user_id,
            filename=filename,
            content=content,
            content_type=content_type,
            resume_id=identifier,
        )

    def retrieve_resume_chunks(
        self, *, user_id: str, resume_id: str, **kwargs: Any
    ) -> Any:
        self._client.authorize_use(user_id, resume_id)
        return super().retrieve_resume_chunks(
            user_id=user_id, resume_id=resume_id, **kwargs
        )

    def retrieve_active_resume_chunks(self, *, user_id: str, **kwargs: Any) -> Any:
        current = self._client.get_current_resume(user_id)
        if current:
            self._client.authorize_use(user_id, current.id)
        return super().retrieve_active_resume_chunks(user_id=user_id, **kwargs)


def account_resume_service(request: Request, existing: Any) -> Any:
    service = AccountResumeService(
        client=AccountResumeClient(request, existing._client),
        parser=existing._parser,
        indexer=existing._indexer,
    )
    service.request = request
    return service
