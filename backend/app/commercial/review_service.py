"""Closed F1 source review service. No routes, config, factory or publication.

Resolver is trusted infrastructure: verify this draft's policy references and
reviewer rule against current authority, lock that authority in this transaction,
and return explicit validity/model bindings. Omitted resolver fails closed.
The connection must be idle, restricted catalog_draft_executor with bounded
connection/whole-transaction timeouts. No production composition is installed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.commercial import catalog_contract as c
from app.commercial.admin_access import VerifiedActor, validate_bounded_draft
from app.commercial.catalog_store import (
    CatalogStore,
    CatalogStoreError,
    ErrorCode,
    _input,
)
from app.commercial.draft_service import DraftService, Query
from app.commercial.review_contract import (
    OfferReference,
    ReviewAuthority,
    ReviewBasis,
    ReviewEvidence,
    ReviewIntent,
    ReviewReceipt,
    ReviewState,
)

Resolver = Callable[[Query, str, c.CatalogDraft], ReviewAuthority]
_ID = TypeAdapter(c.Identifier)
_REV = TypeAdapter(c.Positive)
_REASON = TypeAdapter(c.Text)


class ReviewService:
    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        resolver: Resolver | None = None,
    ):
        self._drafts = DraftService(connect)
        self._resolver = resolver

    @staticmethod
    def _call(
        query: Query,
        subject: str,
        operation: str,
        target: str,
        key: str | None = None,
        request: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        return query(
            "SELECT public.catalog_review_service_call(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (
                subject,
                operation,
                target,
                key,
                c.canonical_json(request) if request is not None else None,
                c.canonical_json(metadata) if metadata is not None else None,
            ),
        )

    @staticmethod
    def _stored_draft(value: Any) -> c.CatalogDraft:
        try:
            return c.CatalogDraft.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def _authority(
        self, query: Query, subject: str, draft: c.CatalogDraft
    ) -> ReviewAuthority:
        if self._resolver is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            value = self._resolver(query, subject, draft)
            if type(value) is not ReviewAuthority:
                raise ValueError
            value = ReviewAuthority.model_validate(value.model_dump(mode="python"))
            value.binding()
            return value
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    def _context(
        self, query: Query, subject: str, draft_id: str
    ) -> tuple[c.CatalogDraft, dict[str, Any], ReviewAuthority]:
        # Peek only after SQL permission/key lock, resolve/lock authority, then
        # acquire plan/source locks and verify that resolution saw the same draft.
        peek = self._stored_draft(
            self._call(query, subject, "peek", draft_id)["document"]
        )
        authority = self._authority(query, subject, peek)
        context = self._call(query, subject, "context", draft_id)
        draft = self._stored_draft(context["document"])
        if draft != peek:
            raise CatalogStoreError(ErrorCode.CONFLICT)
        return draft, context, authority

    @staticmethod
    def _references(
        context: dict[str, Any],
    ) -> tuple[OfferReference | None, OfferReference | None]:
        try:
            heads = context["heads"]
            if not isinstance(heads, list) or len(heads) > 1:
                raise ValueError
            current = OfferReference.model_validate(heads[0]) if heads else None
            archive = context["archive"]
            archived = (
                OfferReference.model_validate(archive["reference"]) if archive else None
            )
            return current, archived
        except (ValidationError, KeyError, TypeError, ValueError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def _basis(
        self,
        draft: c.CatalogDraft,
        context: dict[str, Any],
        authority: ReviewAuthority,
        intent: ReviewIntent,
        expected: int,
    ) -> ReviewBasis:
        if draft.revision != expected or draft.state != "draft":
            raise CatalogStoreError(ErrorCode.CONFLICT)
        report = validate_bounded_draft(
            draft, model_keys=frozenset(authority.model_keys)
        )
        if not report.publishable:
            raise CatalogStoreError(ErrorCode.INVALID)
        binding = authority.binding()
        now = c._instant(context["now"])
        if not binding.valid_from <= now < binding.valid_until:
            raise CatalogStoreError(ErrorCode.CONFLICT)
        current, archived = self._references(context)
        if (intent.action == "replace") != (current is not None):
            raise CatalogStoreError(ErrorCode.CONFLICT)
        if archived is not None:
            archive = context["archive"]
            if archive["state"] != "hidden":
                raise CatalogStoreError(ErrorCode.CONFLICT)
            stored = CatalogStore(
                model_keys=frozenset(authority.model_keys)
            )._read_snapshot(
                archive["snapshot"],
                archived.offer_version_id,
            )
            candidate = draft.model_dump(mode="python")
            candidate["state"] = "previewed"
            recomputed = c.create_snapshot(
                candidate,
                offer_version_id=stored.offer_version_id,
                version=stored.version,
                model_keys=frozenset(authority.model_keys),
            )
            if recomputed.canonical_json() != stored.canonical_json():
                raise CatalogStoreError(ErrorCode.STORED_INVALID)
        return ReviewBasis(
            contract_version=draft.contract_version, registry_version=draft.registry_version,
            validation_policy_version="catalog.validation.v" + draft.contract_version.rsplit("v", 1)[-1],
            draft_id=draft.draft_id,
            plan_id=draft.plan.plan_id,
            revision=draft.revision,
            source_hash=context["source_hash"],
            terms_fingerprint=c.terms_fingerprint(draft.terms),
            authority=binding,
            intent=intent,
            current_offer=current,
            archived_offer=archived,
        )

    def basis(
        self,
        actor: VerifiedActor,
        draft_id: object,
        *,
        expected_revision: object,
        intent: object,
    ) -> ReviewBasis:
        subject = self._drafts._actor(actor)
        identifier, expected = _input(_ID, draft_id), _input(_REV, expected_revision)
        proposed = _input(TypeAdapter(ReviewIntent), intent)

        def work(query: Query) -> ReviewBasis:
            draft, context, authority = self._context(query, subject, identifier)
            return self._basis(draft, context, authority, proposed, expected)

        return self._drafts._transaction(False, work)

    def _decode(self, envelope: Any) -> ReviewReceipt:
        try:
            if (
                type(envelope) is not dict
                or set(envelope)
                != {"receipt", "intact", "source_document", "source_hash", "now"}
                or envelope["intact"] is not True
            ):
                raise ValueError
            receipt = ReviewReceipt.model_validate(envelope["receipt"])
            source = self._stored_draft(envelope["source_document"])
            basis = receipt.basis
            if (
                source.draft_id != basis.draft_id
                or source.plan.plan_id != basis.plan_id
                or source.revision != basis.revision
                or envelope["source_hash"] != basis.source_hash
                or c.terms_fingerprint(source.terms) != basis.terms_fingerprint
                or not basis.authority.valid_from
                <= receipt.recorded_at
                < basis.authority.valid_until
            ):
                raise ValueError
            return receipt
        except (ValidationError, KeyError, TypeError, ValueError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def _assess(self, query: Query, subject: str, envelope: Any) -> ReviewEvidence:
        receipt = self._decode(envelope)
        basis = receipt.basis
        # Historical evidence remains readable, but is explicitly unusable after
        # change/expiry/authority failure. Nothing consumes or publishes it here.
        peek = self._stored_draft(
            self._call(query, subject, "peek", basis.draft_id)["document"]
        )
        try:
            authority = self._authority(query, subject, peek)
        except CatalogStoreError:
            authority = None
        context = self._call(query, subject, "context", basis.draft_id)
        draft = self._stored_draft(context["document"])
        if draft != peek:
            raise CatalogStoreError(ErrorCode.CONFLICT)
        state: ReviewState = "current"
        if (
            draft.revision != basis.revision
            or context["source_hash"] != basis.source_hash
        ):
            state = "draft_changed"
        elif draft.state != "draft":
            state = "draft_terminal"
        elif (
            not basis.authority.valid_from
            <= c._instant(context["now"])
            < basis.authority.valid_until
        ):
            state = "expired"
        elif authority is None:
            state = "authority_unavailable"
        elif authority.binding() != basis.authority:
            state = "authority_changed"
        elif self._references(context) != (basis.current_offer, basis.archived_offer):
            state = "head_changed"
        else:
            # Same-source corruption or validator drift cannot masquerade as a
            # valid receipt; stored protocol versions are strict in _decode.
            if (
                self._basis(draft, context, authority, basis.intent, basis.revision)
                != basis
            ):
                raise CatalogStoreError(ErrorCode.STORED_INVALID)
        return ReviewEvidence(receipt=receipt, state=state)

    def create(
        self, actor: VerifiedActor, basis: object, *, request_id: object, reason: object
    ) -> ReviewEvidence:
        subject = self._drafts._actor(actor)
        reviewed = _input(TypeAdapter(ReviewBasis), basis)
        key, reason = _input(_ID, request_id), _input(_REASON, reason)
        request = {"basis": reviewed.model_dump(mode="json"), "reason": reason}

        def work(query: Query) -> ReviewEvidence:
            prior = self._call(
                query, subject, "prepare", reviewed.draft_id, key, request
            )
            if prior is not None:
                return self._assess(query, subject, prior)
            draft, context, authority = self._context(query, subject, reviewed.draft_id)
            fresh = self._basis(
                draft, context, authority, reviewed.intent, reviewed.revision
            )
            if fresh != reviewed:
                raise CatalogStoreError(ErrorCode.CONFLICT)
            saved = self._decode(
                self._call(
                    query,
                    subject,
                    "record",
                    reviewed.draft_id,
                    key,
                    request,
                    fresh.model_dump(mode="json"),
                )
            )
            if saved.basis != fresh or saved.reviewer_subject != subject:
                raise CatalogStoreError(ErrorCode.STORED_INVALID)
            return ReviewEvidence(receipt=saved, state="current")

        return self._drafts._transaction(True, work)

    def retrieve(self, actor: VerifiedActor, review_id: object) -> ReviewEvidence:
        subject, identifier = self._drafts._actor(actor), _input(_ID, review_id)
        return self._drafts._transaction(
            False,
            lambda query: self._assess(
                query,
                subject,
                self._call(query, subject, "read", identifier),
            ),
        )
