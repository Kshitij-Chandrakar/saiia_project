"""Closed durable usage service. No imports connect, no successful admission wiring.

The injected policy is trusted backend code, never request input. No policy is
installed by default. It must classify operation/meter and explicitly authorize
each transition. Policies are approved in SUBSCRIPTION_APPROVED_POLICIES.md;
unwired execution/classification paths remain unavailable until integrated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.commercial import catalog_contract as c
from app.commercial.account_entitlements import ID, AccountEntitlements, json_query
from app.commercial.admin_access import VerifiedActor
from app.commercial.admission import AdmissionContext
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, _input
from app.commercial.draft_service import DraftService, Query

MAX_UNITS = 2**63 - 1
Policy = Callable[[str, dict[str, Any], c.OfferSnapshot | None], bool]


def quantity(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or not (1 if positive else 0) <= value <= MAX_UNITS:
        raise CatalogStoreError(ErrorCode.INVALID)
    return value


class UsageStore(AccountEntitlements):
    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        model_keys: frozenset[str] = frozenset(),
        policy: Policy | None = None,
    ) -> None:
        super().__init__(connect, model_keys=model_keys)
        self._policy = policy

    def _approve(
        self, action: str, document: dict[str, Any], snapshot: c.OfferSnapshot
    ) -> None:
        if self._policy is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            # Copy prevents accidental mutation of the semantic payload.
            allowed = self._policy(action, dict(document), snapshot)
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None
        if allowed is not True:
            raise CatalogStoreError(ErrorCode.DENIED)

    def _run(
        self, actor: VerifiedActor, action: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        subject = self._channel._actor(actor)

        def work(query: Query) -> dict[str, Any]:
            # Same transaction, authoritative row lock retained by SQL. No cache.
            _, snapshot = self._read(query, subject)
            self._approve(action, document, snapshot)
            return json_query(
                query,
                "SELECT public.usage_call(%s,%s,%s::jsonb)",
                (subject, action, json.dumps(document)),
            )

        return self._channel._transaction(action != "read", work)

    def reserve(
        self,
        actor: VerifiedActor,
        context: AdmissionContext,
        *,
        meter: str,
        units: int,
        policy_version: str,
        lease_seconds: int,
    ) -> dict[str, Any]:
        subject = self._channel._actor(actor)
        if type(context) is not AdmissionContext or context.user_id != subject:
            raise CatalogStoreError(ErrorCode.DENIED)
        # Recovery is a read of the existing operation; never an insert path.
        if (
            type(context.recovery) is not bool
            or type(context.retry_attempt) is not int
            or context.recovery
            or context.retry_attempt
            or context.supersedes_request_id is not None
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        _input(ID, context.session_id)
        if (
            type(context.request_id) is not str
            or type(context.semantics_hash) is not str
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", context.request_id)
            or not re.fullmatch(r"[0-9a-f]{64}", context.semantics_hash)
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        for key in (context.operation, meter, policy_version):
            if type(key) is not str or not re.fullmatch(
                r"[a-z][a-z0-9._:-]{0,119}", key
            ):
                raise CatalogStoreError(ErrorCode.INVALID)
        quantity(units, positive=True)
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._run(
            actor,
            "reserve",
            dict(
                operation=context.operation,
                resource_id=context.session_id,
                request_id=context.request_id,
                semantic_hash=context.semantics_hash,
                meter=meter,
                requested=units,
                policy_version=policy_version,
                lease_seconds=lease_seconds,
            ),
        )

    def read(self, actor: VerifiedActor, operation_id: str) -> dict[str, Any]:
        return self._run(actor, "read", {"operation_id": _input(ID, operation_id)})

    def transition(
        self,
        actor: VerifiedActor,
        action: str,
        operation_id: str,
        *,
        fence: int,
        claim_token: str,
        policy_version: str | None = None,
        charged: int | None = None,
        result_ref: str | None = None,
    ) -> dict[str, Any]:
        keys = {
            "dispatch": (),
            "checkpoint": ("result_ref",),
            "uncertain": (),
            "settle": ("charged", "policy_version"),
            "release": ("policy_version",),
            "vacate": ("policy_version",),
        }
        if action not in keys:
            raise CatalogStoreError(ErrorCode.INVALID)
        doc: dict[str, Any] = dict(
            operation_id=_input(ID, operation_id),
            fence=quantity(fence, positive=True),
            claim_token=_input(ID, claim_token),
        )
        values = dict(
            policy_version=policy_version, charged=charged, result_ref=result_ref
        )
        for key in keys[action]:
            value = values[key]
            if key == "charged":
                value = quantity(value)
            elif key == "result_ref":
                value = _input(ID, value)
            elif type(value) is not str or not re.fullmatch(
                r"[a-z][a-z0-9._:-]{0,119}", value
            ):
                raise CatalogStoreError(ErrorCode.INVALID)
            doc[key] = value
        if any(
            value is not None and key not in keys[action]
            for key, value in values.items()
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._run(actor, action, doc)


class UsageReconciler:
    """Separate closed infrastructure capability; no requesting-user replay data.

    Explicit evidence/outcome policy is mandatory, even after lease expiry. This
    can settle existing work after account revocation without granting new work.
    """

    def __init__(
        self, connect: Callable[[], Any] | None = None, *, policy: Policy | None = None
    ) -> None:
        self._channel = DraftService(connect)
        self._policy = policy

    def _call(
        self, account: str, action: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        account = _input(ID, account)
        if self._policy is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            approved = self._policy(action, dict(document), None)
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None
        if approved is not True:
            raise CatalogStoreError(ErrorCode.DENIED)
        return self._channel._transaction(
            action != "audit",
            lambda q: json_query(
                q,
                "SELECT public.usage_call(%s,%s,%s::jsonb)",
                (account, action, json.dumps(document)),
            ),
        )

    def recover(self, account: str, operation_id: str) -> dict[str, Any]:
        return self._call(
            account, "recover", {"operation_id": _input(ID, operation_id)}
        )

    def reconcile(
        self,
        account: str,
        operation_id: str,
        *,
        fence: int,
        charged: int,
        result_ref: str,
        evidence: str,
        policy_version: str,
    ) -> dict[str, Any]:
        if type(policy_version) is not str or not re.fullmatch(
            r"[a-z][a-z0-9._:-]{0,119}", policy_version
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._call(
            account,
            "reconcile",
            dict(
                operation_id=_input(ID, operation_id),
                fence=quantity(fence, positive=True),
                charged=quantity(charged),
                result_ref=_input(ID, result_ref),
                evidence=_input(ID, evidence),
                policy_version=policy_version,
            ),
        )

    def audit(self, account: str, period_id: str) -> dict[str, Any]:
        return self._call(account, "audit", {"period_id": _input(ID, period_id)})

    def rebuild(self, account: str, period_id: str) -> dict[str, Any]:
        return self._call(account, "rebuild", {"period_id": _input(ID, period_id)})

    def release_uncertain(
        self,
        account: str,
        operation_id: str,
        *,
        fence: int,
        evidence: str,
        policy_version: str,
    ) -> dict[str, Any]:
        if type(policy_version) is not str or not re.fullmatch(
            r"[a-z][a-z0-9._:-]{0,119}", policy_version
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._call(
            account,
            "reconcile_release",
            dict(
                operation_id=_input(ID, operation_id),
                fence=quantity(fence, positive=True),
                evidence=_input(ID, evidence),
                policy_version=policy_version,
            ),
        )
