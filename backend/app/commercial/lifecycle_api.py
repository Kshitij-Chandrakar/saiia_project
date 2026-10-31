"""Authenticated F3 transport; no policy approvals, UI or public catalog."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import TypeAdapter, field_validator

from app.commercial import catalog_contract as c
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, _input
from app.commercial.draft_api import Actor, AdminDraft, DraftRoute, Identity
from app.commercial.lifecycle_service import (
    LifecycleResult,
    LifecycleService,
    OfferState,
    PublicationPreconditions,
)
from app.commercial.review_contract import OfferReference, ReviewBasis, ReviewEvidence

router = APIRouter(route_class=DraftRoute)


def lifecycle_service(request: Request) -> LifecycleService:
    runtime = getattr(request.app.state, "catalog_drafts", None)
    if not isinstance(runtime, CatalogDatabase):
        raise CatalogStoreError(ErrorCode.UNAVAILABLE)
    return runtime.lifecycle_service()


Service = Annotated[LifecycleService, Depends(lifecycle_service)]


def revision(value: str) -> int:
    if not re.fullmatch(r'"[1-9][0-9]{0,15}"', value):
        raise CatalogStoreError(ErrorCode.INVALID)
    return _input(TypeAdapter(c.Positive), value[1:-1])


Match = Annotated[str, Header(alias="If-Match")]


class ReviewCreate(c.FrozenDocument):
    basis: ReviewBasis
    confirmed: Literal[True]
    reason: c.Text

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class Publish(c.FrozenDocument):
    review_id: c.Identifier
    expected_archive_revision: c.Positive | None = None
    reason: c.Text


class Replace(Publish):
    predecessor: OfferReference


class Retire(c.FrozenDocument):
    reason: c.Text


class PublishedSource(AdminDraft):
    state: Literal["published"]


class Snapshot(c.FrozenDocument):
    """Explicit admin terms allowlist, populated only after D integrity checks."""

    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"]
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"]
    plan: c.PlanIdentity
    offer_version_id: c.Identifier
    version: c.Positive
    terms: c.OfferTerms | c.OfferTermsV2 | c.OfferTermsV3


class Provenance(c.FrozenDocument):
    review_id: c.Identifier
    source_revision: c.Positive
    terminal_revision: c.Positive
    fingerprint: str
    catalog_revision: c.Positive
    recorded_at: c.Instant


class AdminOffer(c.FrozenDocument):
    snapshot: Snapshot
    current: OfferState
    publication: Provenance | None
    source: PublishedSource | None
    catalog_revision: c.Positive
    publication_enabled: Literal[False] = False
    purchasable: Literal[False] = False


@router.post("/drafts/{draft_id}/publication-reviews", response_model=ReviewEvidence)
def create_review(
    draft_id: c.Identifier,
    body: ReviewCreate,
    key: Identity,
    if_match: Match,
    actor: Actor,
    service: Service,
    response: Response,
):
    if draft_id != body.basis.draft_id:
        raise CatalogStoreError(ErrorCode.INVALID)
    if revision(if_match) != body.basis.revision:
        raise CatalogStoreError(ErrorCode.CONFLICT)
    try:
        result = service.create(actor, body.basis, request_id=key, reason=body.reason)
    except CatalogStoreError as error:
        if error.code == ErrorCode.CONFLICT:
            raise CatalogStoreError(ErrorCode.REVIEW_STALE) from None
        raise
    response.headers["ETag"] = f'"{result.receipt.basis.revision}"'
    return result


@router.get("/publication-reviews/{review_id}", response_model=ReviewEvidence)
def review(review_id: c.Identifier, actor: Actor, service: Service, response: Response):
    result = service.retrieve(actor, review_id)
    response.headers["ETag"] = f'"{result.receipt.basis.revision}"'
    return result


def _publish(draft_id, body, key, if_match, actor, service, response, action):
    result = service.publish(
        actor,
        body.review_id,
        expected_revision=revision(if_match),
        request_id=key,
        reason=body.reason,
        action=action,
        preconditions=PublicationPreconditions(
            draft_id=draft_id,
            expected_archive_revision=body.expected_archive_revision,
            predecessor=body.predecessor if isinstance(body, Replace) else None,
        ),
    )
    response.headers["ETag"] = f'"{result.current.revision}"'
    return result


@router.post("/drafts/{draft_id}/publish", response_model=LifecycleResult)
def publish(
    draft_id: c.Identifier,
    body: Publish,
    key: Identity,
    if_match: Match,
    actor: Actor,
    service: Service,
    response: Response,
):
    return _publish(draft_id, body, key, if_match, actor, service, response, "publish")


@router.post("/drafts/{draft_id}/replace", response_model=LifecycleResult)
def replace(
    draft_id: c.Identifier,
    body: Replace,
    key: Identity,
    if_match: Match,
    actor: Actor,
    service: Service,
    response: Response,
):
    return _publish(draft_id, body, key, if_match, actor, service, response, "replace")


@router.post("/offers/{offer_id}/retire", response_model=LifecycleResult)
def retire(
    offer_id: c.Identifier,
    body: Retire,
    key: Identity,
    if_match: Match,
    actor: Actor,
    service: Service,
    response: Response,
):
    result = service.retire(
        actor,
        offer_id,
        expected_revision=revision(if_match),
        request_id=key,
        reason=body.reason,
    )
    response.headers["ETag"] = f'"{result.current.revision}"'
    return result


@router.get("/offers/{offer_id}", response_model=AdminOffer)
def offer(offer_id: c.Identifier, actor: Actor, service: Service, response: Response):
    from app.answer_models import MODEL_CATALOG

    snapshot, current, provenance, source, epoch = service.offer(
        actor, offer_id, model_keys=frozenset(MODEL_CATALOG)
    )
    response.headers["ETag"] = f'"{current.revision}"'
    return AdminOffer(
        snapshot=Snapshot.model_validate(snapshot.model_dump(mode="python")),
        current=current,
        publication=Provenance.model_validate(provenance) if provenance else None,
        source=(
            PublishedSource.model_validate(source.model_dump(mode="python"))
            if source
            else None
        ),
        catalog_revision=epoch,
    )


@router.get("/operations/{request_id}", response_model=ReviewEvidence | LifecycleResult)
def operation(request_id: c.Identifier, actor: Actor, service: Service):
    return service.operation(actor, request_id)
