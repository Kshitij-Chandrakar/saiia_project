"""Closed account authority. No routes, connection factory or enrollment defaults.

Provisioning requires a separate trusted infrastructure principal; catalog admin
permission is deliberately insufficient. The retained bearer is verified by the
existing actor boundary, never by an editable role or account payload field.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter

from app.commercial import catalog_contract as c
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, _input
from app.commercial.draft_service import DraftService, Query

ID = TypeAdapter(c.Identifier)


def json_query(query: Query, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    result = query(sql, params)
    if not isinstance(result, dict):
        raise CatalogStoreError(ErrorCode.STORED_INVALID)
    return result


def validated_terms(record: dict[str, Any], models: frozenset[str]) -> c.OfferSnapshot:
    """Recompute canonical bytes/hash; never trust a supplied fingerprint alone."""
    try:
        raw = json.loads(record["snapshot"])
        # Use the accepted snapshot decoder; domain normalization is not copied.
        raw["eligible_model_keys"] = tuple(sorted(models))
        snapshot = c.OfferSnapshot.model_validate(raw)
        if (
            snapshot.canonical_json() != record["snapshot"]
            or snapshot.fingerprint != record["fingerprint"]
        ):
            raise ValueError()
        if (
            snapshot.offer_version_id != record["offer_version_id"]
            or snapshot.plan.plan_id != record["plan_id"]
            or snapshot.version != record["version"]
        ):
            raise ValueError()
        return snapshot
    except Exception:
        raise CatalogStoreError(ErrorCode.STORED_INVALID) from None


class AccountEntitlements:
    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        model_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._channel = DraftService(connect, model_keys=model_keys)
        self._models = model_keys

    def _read(
        self, query: Query, subject: str
    ) -> tuple[dict[str, Any], c.OfferSnapshot]:
        record = json_query(query, "SELECT public.usage_account_read(%s)", (subject,))
        snapshot = validated_terms(record, self._models)
        return record, snapshot

    def resolve(self, actor: VerifiedActor) -> dict[str, Any]:
        subject = self._channel._actor(actor)

        def work(query: Query) -> dict[str, Any]:
            record, snapshot = self._read(query, subject)
            return {
                "binding": record["binding"],
                "snapshot": snapshot,
                "server_time": record["at"],
            }

        return self._channel._transaction(False, work)


class BindingDocument(c.FrozenDocument):
    binding_id: c.Identifier
    offer_version_id: c.Identifier
    price_id: c.Identifier | None = None
    valid_from: c.Instant
    valid_until: c.Instant
    source_ref: c.Key
    policy_version: c.Key


class BindingProvisioner:
    """Backend-only maintenance capability, not an admin/user service.

    The SQL NOLOGIN principal has no members and is never composed in production.
    C13.2/C12 must supply an approved authoritative assignment source before any
    real provisioning. No human role or subscriptions.manage fallback is added.
    """

    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        model_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._channel = DraftService(connect, model_keys=model_keys)
        self._models = model_keys

    def assign(self, account_id: str, document: Any) -> dict[str, Any]:
        account_id = _input(ID, account_id)
        try:
            data = BindingDocument.model_validate_json(json.dumps(document))
            if (
                data.valid_from.tzinfo is None
                or data.valid_until.tzinfo is None
                or data.valid_until <= data.valid_from
            ):
                raise ValueError()
        except Exception:
            raise CatalogStoreError(ErrorCode.INVALID) from None

        def work(query: Query) -> dict[str, Any]:
            stored = json_query(
                query, "SELECT public.usage_terms_read(%s)", (data.offer_version_id,)
            )
            validated_terms(stored, self._models)
            return json_query(
                query,
                "SELECT public.usage_binding_call(%s,%s,%s::jsonb)",
                (account_id, "assign", data.model_dump_json()),
            )

        return self._channel._transaction(True, work)

    def status(
        self, account_id: str, expected_revision: int, *, active: bool
    ) -> dict[str, Any]:
        account_id = _input(ID, account_id)
        if (
            type(active) is not bool
            or type(expected_revision) is not int
            or expected_revision < 1
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._channel._transaction(
            True,
            lambda query: json_query(
                query,
                "SELECT public.usage_binding_call(%s,%s,%s::jsonb)",
                (
                    account_id,
                    "status",
                    json.dumps(
                        {"expected_revision": expected_revision, "active": active}
                    ),
                ),
            ),
        )
