"""Draft operations and zero-write review basis; commands live in lifecycle_api."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from anyio import fail_after
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import TypeAdapter
from starlette.concurrency import run_in_threadpool

from app.commercial import catalog_contract as c
from app.commercial.admin_access import (
    VerifiedActor,
    bounded_json,
    http_error,
    verified_actor,
)
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, _input
from app.commercial.draft_service import DraftService
from app.commercial.review_contract import ReviewBasis, ReviewIntent


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class DraftRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                if any(
                    len(request.headers.getlist(name)) > 1
                    for name in ("authorization", "idempotency-key", "if-match")
                ):
                    raise CatalogStoreError(ErrorCode.INVALID)
                # Authenticate before collecting/decoding potentially hostile input.
                request.state.catalog_actor = await run_in_threadpool(
                    verified_actor, request
                )
                if request.query_params:
                    raise CatalogStoreError(ErrorCode.INVALID)
                data = bytearray()
                with fail_after(5):
                    async for chunk in request.stream():
                        data.extend(chunk)
                        if len(data) > 131072:
                            raise CatalogStoreError(ErrorCode.INVALID)
                if request.method == "GET":
                    if data:
                        raise CatalogStoreError(ErrorCode.INVALID)
                else:
                    if (
                        request.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                        != "application/json"
                    ):
                        raise CatalogStoreError(ErrorCode.INVALID)
                    decoded = json.loads(data, object_pairs_hook=_unique)
                    bounded_json(decoded)
                    # Reuse the bounded bytes/object for FastAPI typed body parsing.
                    request._body = bytes(data)
                    request._json = decoded
                return await handler(request)
            except HTTPException:
                raise
            except CatalogStoreError as error:
                raise http_error(error) from None
            except (
                RequestValidationError,
                ValueError,
                TypeError,
                RecursionError,
                TimeoutError,
            ):
                raise http_error(CatalogStoreError(ErrorCode.INVALID)) from None
            except Exception:
                raise http_error(CatalogStoreError(ErrorCode.UNAVAILABLE)) from None

        return guarded


router = APIRouter(route_class=DraftRoute)


def actor_context(request: Request) -> VerifiedActor:
    value = request.state.catalog_actor
    if not isinstance(value, VerifiedActor):
        raise CatalogStoreError(ErrorCode.DENIED)
    return value


def draft_service(request: Request) -> DraftService:
    runtime = getattr(request.app.state, "catalog_drafts", None)
    if not isinstance(runtime, CatalogDatabase):
        raise CatalogStoreError(ErrorCode.UNAVAILABLE)
    return runtime.service()


Actor = Annotated[VerifiedActor, Depends(actor_context)]
Service = Annotated[DraftService, Depends(draft_service)]
Identity = Annotated[c.Identifier, Header(alias="Idempotency-Key")]


class DraftWrite(c.FrozenDocument):
    document: c.CatalogDraft
    reason: c.Text


class PreviewRequest(c.FrozenDocument):
    expected_revision: c.Positive
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"]
    scope: Literal["structural_only"] = "structural_only"


class PublicationPreviewRequest(c.FrozenDocument):
    expected_revision: c.Positive
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"]
    scope: Literal["publication_review"]
    intent: ReviewIntent


class PublicationPreview(c.FrozenDocument):
    basis: ReviewBasis
    validation_scope: Literal["publication_review"] = "publication_review"
    publication_enabled: Literal[False] = False


class AdminDraft(c.FrozenDocument):
    """Explicit transport allowlist; never raw storage/audit/permission records."""

    draft_id: c.Identifier
    plan: c.PlanIdentity
    revision: c.Positive
    state: Literal["draft"]
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"]
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"]
    terms: c.OfferTerms | c.OfferTermsV2 | c.OfferTermsV3
    internal_notes: str


class Issue(c.FrozenDocument):
    path: tuple[str | int, ...]
    code: str


class Preview(c.FrozenDocument):
    draft_id: c.Identifier
    revision: c.Positive
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"] = "catalog.v1"
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"] = "catalog.features.v1"
    publishable: bool
    validation_scope: Literal["structural_only"] = "structural_only"
    publication_enabled: Literal[False] = False
    errors: tuple[Issue, ...]
    pending: tuple[Issue, ...]


def _response(draft: c.CatalogDraft, response: Response) -> AdminDraft:
    response.headers["ETag"] = f'"{draft.revision}"'
    return AdminDraft.model_validate(
        {key: getattr(draft, key) for key in AdminDraft.model_fields}
    )


@router.post("/plans/{plan_id}/drafts", response_model=AdminDraft)
def create(
    plan_id: c.Identifier,
    body: DraftWrite,
    key: Identity,
    actor: Actor,
    service: Service,
    response: Response,
) -> AdminDraft:
    if plan_id != body.document.plan.plan_id:
        raise CatalogStoreError(ErrorCode.INVALID)
    return _response(
        service.create(actor, body.document, request_id=key, reason=body.reason),
        response,
    )


@router.get("/drafts/{draft_id}", response_model=AdminDraft)
def retrieve(
    draft_id: c.Identifier, actor: Actor, service: Service, response: Response
) -> AdminDraft:
    return _response(service.retrieve(actor, draft_id), response)


@router.patch("/drafts/{draft_id}", response_model=AdminDraft)
def edit(
    draft_id: c.Identifier,
    body: DraftWrite,
    key: Identity,
    actor: Actor,
    service: Service,
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> AdminDraft:
    if draft_id != body.document.draft_id or not re.fullmatch(
        r'"[1-9][0-9]{0,15}"', if_match
    ):
        raise CatalogStoreError(ErrorCode.INVALID)
    expected = _input(TypeAdapter(c.Positive), if_match[1:-1])
    return _response(
        service.edit(
            actor,
            body.document,
            expected_revision=expected,
            request_id=key,
            reason=body.reason,
        ),
        response,
    )


@router.post("/drafts/{draft_id}/preview", response_model=Preview | PublicationPreview)
def preview(
    draft_id: c.Identifier,
    body: PreviewRequest | PublicationPreviewRequest,
    actor: Actor,
    service: Service,
    response: Response,
    request: Request,
) -> Preview | PublicationPreview:
    if isinstance(body, PublicationPreviewRequest):
        if service.retrieve(actor, draft_id).contract_version != body.contract_version:
            raise CatalogStoreError(ErrorCode.INVALID)
        runtime = getattr(request.app.state, "catalog_drafts", None)
        if not isinstance(runtime, CatalogDatabase):
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            basis = runtime.lifecycle_service().basis(
                actor,
                draft_id,
                expected_revision=body.expected_revision,
                intent=body.intent,
            )
        except CatalogStoreError as error:
            if error.code == ErrorCode.INVALID:
                raise CatalogStoreError(ErrorCode.NOT_PUBLISHABLE) from None
            raise
        response.headers["ETag"] = f'"{basis.revision}"'
        return PublicationPreview(basis=basis)
    report = service.preview(actor, draft_id)
    if report.draft is None:
        raise CatalogStoreError(ErrorCode.STORED_INVALID)
    if report.draft.contract_version != body.contract_version:
        raise CatalogStoreError(ErrorCode.INVALID)
    if report.draft.revision != body.expected_revision:
        raise CatalogStoreError(ErrorCode.CONFLICT)
    response.headers["ETag"] = f'"{report.draft.revision}"'
    return Preview(
        draft_id=draft_id,
        contract_version=report.draft.contract_version, registry_version=report.draft.registry_version,
        revision=report.draft.revision,
        publishable=report.publishable,
        errors=tuple(Issue(path=i.path, code=i.code) for i in report.errors),
        pending=tuple(Issue(path=i.path, code=i.code) for i in report.pending),
    )
