"""Unwired private RPC adapter. No config/client creation, retries or authority.

Composition must supply a server-controlled transport bound to verified identity.
No actor UUID, role, email or service key is an authorization input here. SQL
rechecks/locks shared membership per RPC. All shipped RPC EXECUTEs remain closed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.commercial import catalog_contract as c


class ErrorCode(str, Enum):
    NOT_FOUND = "catalog_not_found"
    CONFLICT = "catalog_revision_conflict"
    IDENTITY_CONFLICT = "catalog_request_identity_conflict"
    DENIED = "catalog_permission_denied"
    INVALID = "catalog_invalid_data"
    STORED_INVALID = "catalog_stored_version_invalid"
    UNAVAILABLE = "catalog_database_unavailable"
    UNCERTAIN = "catalog_write_uncertain"
    REVIEW_STALE = "catalog_review_stale"
    NOT_PUBLISHABLE = "catalog_not_publishable"
    EXHAUSTED = "usage_allowance_exhausted"


class CatalogStoreError(RuntimeError):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)


class RpcFailure(Exception):
    """Transport reports only SQLSTATE/dispatch certainty, never raw errors.

    A server SQLSTATE means its atomic RPC failed. No SQLSTATE after dispatch
    means a write may have committed. There is no automatic write replay.
    """

    def __init__(self, sqlstate: str | None = None, *, dispatched: bool = True):
        self.sqlstate = sqlstate
        self.dispatched = dispatched
        super().__init__("catalog_rpc_failure")


_ID = TypeAdapter(c.Identifier)
_QUANTITY = TypeAdapter(c.Quantity)
_POSITIVE = TypeAdapter(c.Positive)
_REASON = TypeAdapter(c.Text)


def _input(adapter: TypeAdapter[Any], value: object) -> Any:
    try:
        return adapter.validate_python(value, strict=True)
    except (ValidationError, ValueError, TypeError):
        raise CatalogStoreError(ErrorCode.INVALID) from None


def _error(failure: RpcFailure, write: bool) -> ErrorCode:
    code = failure.sqlstate
    if code == "P0003":
        return ErrorCode.IDENTITY_CONFLICT
    if code == "P0004":
        return ErrorCode.EXHAUSTED
    if code == "P0002":
        return ErrorCode.NOT_FOUND
    if code in ("40001", "23505"):
        return ErrorCode.CONFLICT
    if code == "42501":
        return ErrorCode.DENIED
    if code and (code.startswith(("22", "23")) or code == "55000"):
        return ErrorCode.INVALID
    if write and failure.dispatched and (not code or code.startswith("08")):
        return ErrorCode.UNCERTAIN
    return ErrorCode.UNAVAILABLE


class CatalogStore:
    """Private B document persistence via narrowly named atomic Supabase RPCs.

    The callable is trusted infrastructure, NOT a client-provided hook or an
    identity verifier. No production factory is installed; omitted transport
    fails closed. Model compatibility comes from a trusted backend registry.
    """

    def __init__(
        self,
        rpc: Callable[[str, dict[str, object]], object] | None = None,
        *,
        model_keys: frozenset[str] = frozenset(),
    ):
        if type(model_keys) is not frozenset or any(
            type(k) is not str for k in model_keys
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        self._rpc = rpc
        self._model_keys = model_keys

    def _call(
        self, name: str, payload: dict[str, object], *, write: bool = False
    ) -> object:
        if self._rpc is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            return self._rpc(name, payload)
        except RpcFailure as exc:
            raise CatalogStoreError(_error(exc, write)) from None
        except Exception:
            # Unknown transport failure cannot prove a dispatched write rolled back.
            raise CatalogStoreError(
                ErrorCode.UNCERTAIN if write else ErrorCode.UNAVAILABLE
            ) from None

    def _draft(self, value: object, *, stored: bool = False) -> c.CatalogDraft:
        try:
            report = c.validate_draft(value, model_keys=self._model_keys)
        except (ValidationError, ValueError, TypeError, RecursionError):
            raise CatalogStoreError(
                ErrorCode.STORED_INVALID if stored else ErrorCode.INVALID
            ) from None
        if not report.valid or report.draft is None or report.draft.state != "draft":
            raise CatalogStoreError(
                ErrorCode.STORED_INVALID if stored else ErrorCode.INVALID
            )
        # A fresh model prevents shared mutable draft inputs/unchecked copies.
        return report.draft

    def _read_draft(self, row: object, draft_id: str) -> c.CatalogDraft:
        try:
            if not isinstance(row, dict) or set(row) != {
                "storage_version",
                "draft_id",
                "plan_id",
                "revision",
                "document",
            }:
                raise ValueError
            if row["storage_version"] != "catalog.store.v1":
                raise ValueError
            draft = self._draft(row["document"], stored=True)
            if (
                draft.draft_id != draft_id
                or row["draft_id"] != draft_id
                or row["plan_id"] != draft.plan.plan_id
                or _POSITIVE.validate_python(row["revision"], strict=True)
                != draft.revision
            ):
                raise ValueError
            return draft
        except (ValidationError, ValueError, TypeError, KeyError, CatalogStoreError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def load_draft(self, draft_id: object) -> c.CatalogDraft:
        identifier = _input(_ID, draft_id)
        return self._read_draft(
            self._call("catalog_adapter_load_draft", {"p_id": identifier}), identifier
        )

    def save_draft(
        self, value: object, *, expected_revision: object, reason: object
    ) -> c.CatalogDraft:
        draft = self._draft(value)
        expected = _input(_QUANTITY, expected_revision)
        reason = _input(_REASON, reason)
        if draft.revision != expected + 1:
            raise CatalogStoreError(ErrorCode.INVALID)
        row = self._call(
            "catalog_adapter_save_draft",
            {
                "p_id": draft.draft_id,
                "p_plan": draft.plan.plan_id,
                "p_expected": str(expected),
                "p_document": draft.model_dump(mode="json"),
                "p_reason": reason,
            },
            write=True,
        )
        try:
            saved = self._read_draft(row, draft.draft_id)
            if saved.model_dump(mode="json") != draft.model_dump(mode="json"):
                raise ValueError
            return saved
        except (CatalogStoreError, ValueError):
            # Malformed/lost acknowledgement after mutation is not failure proof.
            raise CatalogStoreError(ErrorCode.UNCERTAIN) from None

    def _read_snapshot(self, row: object, offer_id: str) -> c.OfferSnapshot:
        try:
            keys = {
                "storage_version",
                "offer_version_id",
                "plan_id",
                "version",
                "source_draft_id",
                "source_revision",
                "canonical_json",
                "fingerprint",
                "prices",
            }
            if (
                not isinstance(row, dict)
                or set(row) != keys
                or row["storage_version"] != "catalog.store.v1"
            ):
                raise ValueError
            raw = json.loads(row["canonical_json"])
            if "eligible_model_keys" in raw:
                raise ValueError
            raw["eligible_model_keys"] = tuple(sorted(self._model_keys))
            snapshot = c.OfferSnapshot.model_validate(raw)
            _ID.validate_python(row["source_draft_id"], strict=True)
            _POSITIVE.validate_python(row["source_revision"], strict=True)
            prices = sorted(row["prices"], key=lambda p: p["price_id"])
            expected_prices = sorted(
                (p.model_dump(mode="json") for p in snapshot.terms.prices),
                key=lambda p: p["price_id"],
            )
            if (
                snapshot.offer_version_id != offer_id
                or row["offer_version_id"] != offer_id
                or row["plan_id"] != snapshot.plan.plan_id
                or _POSITIVE.validate_python(row["version"], strict=True)
                != snapshot.version
                or snapshot.canonical_json() != row["canonical_json"]
                or snapshot.fingerprint != row["fingerprint"]
                or prices != expected_prices
            ):
                raise ValueError
            return snapshot
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
            raise CatalogStoreError(ErrorCode.STORED_INVALID) from None

    def load_snapshot(self, offer_id: object) -> c.OfferSnapshot:
        identifier = _input(_ID, offer_id)
        return self._read_snapshot(
            self._call("catalog_adapter_load_snapshot", {"p_id": identifier}),
            identifier,
        )

    def archive_snapshot(
        self,
        draft_id: object,
        *,
        expected_revision: object,
        offer_id: object,
        version: object,
        reason: object,
    ) -> c.OfferSnapshot:
        identifier = _input(_ID, offer_id)
        number = _input(_POSITIVE, version)
        expected = _input(_POSITIVE, expected_revision)
        reason = _input(_REASON, reason)
        draft = self.load_draft(draft_id)
        if draft.revision != expected:
            raise CatalogStoreError(ErrorCode.CONFLICT)
        # Ephemeral validation candidate only: no persisted preview approval or
        # publication. Recompute from freshly loaded source, never caller hashes.
        candidate = draft.model_dump(mode="python")
        candidate["state"] = "previewed"
        try:
            snapshot = c.create_snapshot(
                candidate,
                offer_version_id=identifier,
                version=number,
                model_keys=self._model_keys,
            )
        except (c.CatalogValidationError, ValidationError, ValueError):
            raise CatalogStoreError(ErrorCode.INVALID) from None
        row = self._call(
            "catalog_adapter_archive_snapshot",
            {
                "p_draft_id": draft.draft_id,
                "p_expected": str(expected),
                "p_offer_id": identifier,
                "p_version": str(number),
                "p_canonical_json": snapshot.canonical_json(),
                "p_reason": reason,
            },
            write=True,
        )
        try:
            saved = self._read_snapshot(row, identifier)
            if not isinstance(row, dict):
                raise ValueError
            if (
                saved.canonical_json() != snapshot.canonical_json()
                or row["source_draft_id"] != draft.draft_id
                or _POSITIVE.validate_python(row["source_revision"], strict=True)
                != expected
            ):
                raise ValueError
            return saved
        except (CatalogStoreError, ValidationError, ValueError):
            raise CatalogStoreError(ErrorCode.UNCERTAIN) from None
