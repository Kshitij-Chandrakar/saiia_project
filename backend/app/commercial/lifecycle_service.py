"""Internal lifecycle transactions; transport/composition is defined separately.

Uses the existing verified actor, safe transaction runner and trusted review
resolver. The connection factory must enforce a whole-transaction budget, as in
F1; SQL also bounds lock/statement waits. Never retries a write automatically.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError, model_validator

from app.commercial import catalog_contract as c
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import (
    CatalogStore,
    CatalogStoreError,
    ErrorCode,
    _input,
)
from app.commercial.draft_service import Query
from app.commercial.review_service import ReviewService
from app.commercial.review_contract import OfferReference


class PublicationPreconditions(c.FrozenDocument):
    draft_id: c.Identifier
    expected_archive_revision: c.Positive | None
    predecessor: OfferReference | None


class LifecycleReceipt(c.FrozenDocument):
    protocol: Literal["catalog.lifecycle.result.v1"]
    request_id: c.Identifier
    actor_subject: c.Identifier
    permission_revision: c.Positive
    operation: Literal["offer.publish", "offer.replace", "offer.retire"]
    offer_version_id: c.Identifier
    review_id: c.Identifier | None
    visibility_revision: c.Positive
    catalog_revision: c.Positive
    recorded_at: c.Instant


class OfferState(c.FrozenDocument):
    offer_version_id: c.Identifier
    revision: c.Positive
    state: Literal["hidden", "visible", "retired"]
    valid_from: c.Instant | None
    valid_until: c.Instant | None
    retired_at: c.Instant | None


class LifecycleResult(c.FrozenDocument):
    """Historical receipt separately from fresh transaction state; no sale permit."""

    receipt: LifecycleReceipt
    current: OfferState
    current_catalog_revision: c.Positive
    publication_enabled: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if (
            self.current.offer_version_id != self.receipt.offer_version_id
            or self.current.revision < self.receipt.visibility_revision
            or self.current_catalog_revision < self.receipt.catalog_revision
            or (self.receipt.operation == "offer.retire")
            != (self.receipt.review_id is None)
        ):
            raise ValueError("Invalid lifecycle result")
        return self


_ID = TypeAdapter(c.Identifier)
_REV = TypeAdapter(c.Positive)
_REASON = TypeAdapter(c.Text)


class LifecycleService(ReviewService):
    @staticmethod
    def _lifecycle(
        query: Query, subject: str, stage: str, request: dict, metadata: object = None
    ):
        return query(
            "SELECT public.catalog_lifecycle_service_call(%s,%s,%s::jsonb,%s::jsonb)",
            (
                subject,
                stage,
                c.canonical_json(request),
                c.canonical_json(metadata) if metadata is not None else None,
            ),
        )

    @staticmethod
    def _result(value: object, subject: str, request: dict) -> LifecycleResult:
        try:
            result = LifecycleResult.model_validate(value)
            receipt = result.receipt
            if (
                receipt.actor_subject != subject
                or receipt.operation != request["operation"]
                or receipt.request_id != request["request_id"]
                or receipt.review_id != request.get("review_id")
                or (
                    receipt.operation == "offer.retire"
                    and receipt.offer_version_id != request["offer_version_id"]
                )
            ):
                raise ValueError("Invalid operation binding")
            return result
        except (ValidationError, ValueError, TypeError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def publish(
        self,
        actor: VerifiedActor,
        review_id: object,
        *,
        expected_revision: object,
        request_id: object,
        reason: object,
        action: Literal["publish", "replace"] = "publish",
        preconditions: PublicationPreconditions | None = None,
    ) -> LifecycleResult:
        subject = self._drafts._actor(actor)
        if action not in ("publish", "replace"):
            raise CatalogStoreError(ErrorCode.INVALID)
        request = dict(
            operation="offer." + action,
            review_id=_input(_ID, review_id),
            expected_revision=_input(_REV, expected_revision),
            request_id=_input(_ID, request_id),
            reason=_input(_REASON, reason),
        )
        bound = (
            _input(TypeAdapter(PublicationPreconditions), preconditions)
            if preconditions is not None
            else None
        )
        checked_revision = False

        def work(query: Query):
            nonlocal checked_revision
            # Durable identity first: changed semantics under a committed key
            # are an identity conflict, even if the new revision is also stale.
            prior = self._lifecycle(query, subject, "prepare", request)
            if bound is not None:
                # Read immutable evidence in THIS transaction before replay. The
                # review ID transitively binds the complete basis in F2's hash.
                receipt = self._decode(
                    self._call(query, subject, "read", request["review_id"])
                )
                basis = receipt.basis
                if basis.draft_id != bound.draft_id:
                    raise CatalogStoreError(ErrorCode.INVALID)
                if basis.revision != request["expected_revision"]:
                    raise CatalogStoreError(ErrorCode.CONFLICT)
                checked_revision = True
                if (
                    basis.current_offer != bound.predecessor
                    or (
                        basis.archived_offer.visibility_revision
                        if basis.archived_offer
                        else None
                    )
                    != bound.expected_archive_revision
                    or basis.intent.action != action
                ):
                    raise CatalogStoreError(ErrorCode.REVIEW_STALE)
            if prior is not None:
                return self._result(prior, subject, request)
            envelope = self._lifecycle(query, subject, "review", request)
            receipt = self._decode(envelope)
            basis = receipt.basis
            if (
                basis.revision != request["expected_revision"]
                or basis.intent.action != action
            ):
                raise CatalogStoreError(ErrorCode.CONFLICT)
            # Authority before plan/draft locks. Resolve against a peek, then
            # require the locked document to be identical before validation.
            peek = self._stored_draft(
                self._lifecycle(query, subject, "peek", request)["document"]
            )
            authority = self._authority(query, subject, peek)
            context = self._lifecycle(query, subject, "context", request)
            draft = self._stored_draft(context["document"])
            if (
                draft != peek
                or self._basis(draft, context, authority, basis.intent, basis.revision)
                != basis
            ):
                raise CatalogStoreError(ErrorCode.CONFLICT)
            archive = context["archive"]
            offer_id = (
                basis.archived_offer.offer_version_id if archive else str(uuid4())
            )
            version = (
                int(archive["snapshot"]["version"])
                if archive
                else int(context["next_version"])
            )
            source = draft.model_dump(mode="python")
            source["state"] = "previewed"
            snapshot = c.create_snapshot(
                source,
                offer_version_id=offer_id,
                version=version,
                model_keys=frozenset(authority.model_keys),
            )
            return self._result(
                self._lifecycle(
                    query,
                    subject,
                    "commit",
                    request,
                    dict(
                        basis=basis.model_dump(mode="json"),
                        canonical_json=snapshot.canonical_json(),
                    ),
                ),
                subject,
                request,
            )

        try:
            return self._drafts._transaction(True, work)
        except CatalogStoreError as error:
            if (
                bound is not None
                and checked_revision
                and error.code == ErrorCode.CONFLICT
            ):
                raise CatalogStoreError(ErrorCode.REVIEW_STALE) from None
            raise

    def retire(
        self,
        actor: VerifiedActor,
        offer_id: object,
        *,
        expected_revision: object,
        request_id: object,
        reason: object,
    ) -> LifecycleResult:
        subject = self._drafts._actor(actor)
        request = dict(
            operation="offer.retire",
            offer_version_id=_input(_ID, offer_id),
            expected_revision=_input(_REV, expected_revision),
            request_id=_input(_ID, request_id),
            reason=_input(_REASON, reason),
        )
        return self._drafts._transaction(
            True,
            lambda query: self._result(
                self._lifecycle(query, subject, "retire", request), subject, request
            ),
        )

    @staticmethod
    def _read(query: Query, subject: str, operation: str, target: str):
        return query(
            "SELECT public.catalog_lifecycle_read_call(%s,%s,%s)",
            (subject, operation, target),
        )

    def operation(self, actor: VerifiedActor, request_id: object):
        subject, key = self._drafts._actor(actor), _input(_ID, request_id)

        def work(query: Query):
            row = self._read(query, subject, "operation", key)
            try:
                if row["kind"] == "review":
                    return self._assess(query, subject, row["review"])
                if row["kind"] != "lifecycle":
                    raise ValueError
                result = LifecycleResult.model_validate(row["result"])
                if (
                    result.receipt.actor_subject != subject
                    or result.receipt.request_id != key
                ):
                    raise ValueError
                return result
            except (ValidationError, KeyError, ValueError, TypeError):
                raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

        return self._drafts._transaction(False, work)

    def offer(
        self, actor: VerifiedActor, offer_id: object, *, model_keys: frozenset[str]
    ):
        subject, identifier = self._drafts._actor(actor), _input(_ID, offer_id)

        def work(query: Query):
            row = self._read(query, subject, "offer", identifier)
            try:
                snapshot = CatalogStore(model_keys=model_keys)._read_snapshot(
                    row["snapshot"], identifier
                )
                current = OfferState.model_validate(row["current"])
                if current.offer_version_id != identifier:
                    raise ValueError
                publication = row["publication"]
                source = (
                    c.CatalogDraft.model_validate(row["source"])
                    if row["source"]
                    else None
                )
                if publication is not None:
                    if (
                        source is None
                        or source.state != "published"
                        or source.draft_id != row["snapshot"]["source_draft_id"]
                        or source.revision != int(publication["terminal_revision"])
                        or source.revision
                        != int(row["snapshot"]["source_revision"]) + 1
                        or source.plan != snapshot.plan
                        or source.terms != snapshot.terms
                        or publication["fingerprint"] != snapshot.fingerprint
                    ):
                        raise ValueError
                elif current.state == "visible" or source is not None:
                    raise ValueError
                return (
                    snapshot,
                    current,
                    publication,
                    source,
                    _input(_REV, row["catalog_revision"]),
                )
            except (ValidationError, KeyError, ValueError, TypeError):
                raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

        return self._drafts._transaction(False, work)
