"""Opt-in account integration; no payment verifier or connection on import."""

from collections.abc import Callable
from typing import Any, Literal

from app.commercial import catalog_contract as c
from app.commercial.account_entitlements import (
    AccountEntitlements,
    json_query,
    validated_terms,
)
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_service import Query


class PaymentEvent(c.FrozenDocument):
    """Normalized data only; the injected verifier supplies the proof."""

    account_id: c.Identifier
    event_id: c.Identifier
    offer_version_id: c.Identifier
    price_id: c.Identifier
    paid_until: c.Instant


class PeriodChange(c.FrozenDocument):
    account_id: c.Identifier
    event_id: c.Identifier
    kind: Literal["cancel", "downgrade"]
    expected_revision: c.Positive
    offer_version_id: c.Identifier | None = None
    price_id: c.Identifier | None = None
    paid_until: c.Instant | None = None


class SubscriptionService(AccountEntitlements):
    def require_unlimited(self, actor: VerifiedActor, feature: str, meter: str) -> None:
        subject = self._channel._actor(actor)

        def work(query: Query) -> None:
            record = json_query(
                query, "SELECT public.subscription_current(%s,false)", (subject,)
            )
            snapshot = validated_terms(record, self._models)
            if not any(
                e.feature == feature and e.allowed for e in snapshot.terms.entitlements
            ):
                raise CatalogStoreError(ErrorCode.DENIED)
            if not any(
                a.meter == meter and a.mode == "unlimited"
                for a in getattr(snapshot.terms, "allowances", ())
            ):
                raise CatalogStoreError(ErrorCode.UNAVAILABLE)

        self._channel._transaction(False, work)

    def require_manual_answers(self, actor: VerifiedActor) -> None:
        subject = self._channel._actor(actor)

        def work(query: Query) -> None:
            record = json_query(
                query, "SELECT public.subscription_current(%s,false)", (subject,)
            )
            snapshot = validated_terms(record, self._models)
            if not any(
                e.feature == "answers.generate" and e.allowed
                for e in snapshot.terms.entitlements
            ):
                raise CatalogStoreError(ErrorCode.DENIED)
            if not any(
                a.meter == "answers.completed" and a.mode == "unlimited"
                for a in getattr(snapshot.terms, "allowances", ())
            ):
                raise CatalogStoreError(ErrorCode.UNAVAILABLE)

        self._channel._transaction(False, work)

    def require_feature(self, actor: VerifiedActor, feature: str) -> None:
        subject = self._channel._actor(actor)

        def work(query: Query) -> None:
            record = json_query(
                query, "SELECT public.subscription_current(%s,false)", (subject,)
            )
            snapshot = validated_terms(record, self._models)
            if not any(
                e.feature == feature and e.allowed for e in snapshot.terms.entitlements
            ):
                raise CatalogStoreError(ErrorCode.DENIED)

        self._channel._transaction(False, work)

    def read_clipboard(
        self, actor: VerifiedActor, session_id: str
    ) -> list[dict[str, Any]]:
        from app.commercial.account_entitlements import ID
        from app.commercial.catalog_store import _input

        subject = self._channel._actor(actor)
        session_id = _input(ID, session_id)

        def work(query: Query) -> list[dict[str, Any]]:
            result = query(
                "SELECT public.subscription_clipboard_read(%s,%s)",
                (subject, session_id),
            )
            if not isinstance(result, list) or any(
                not isinstance(row, dict) for row in result
            ):
                raise CatalogStoreError(ErrorCode.STORED_INVALID)
            return result

        return self._channel._transaction(False, work)

    def save_clipboard(
        self, actor: VerifiedActor, session_id: str, key: str, body: str
    ) -> dict[str, Any]:
        from app.commercial.account_entitlements import ID
        from app.commercial.admission import validated_request_key
        from app.commercial.catalog_store import _input

        subject = self._channel._actor(actor)
        session_id = _input(ID, session_id)
        try:
            validated_request_key(key)
        except Exception:
            raise CatalogStoreError(ErrorCode.INVALID) from None
        if type(body) is not str:
            raise CatalogStoreError(ErrorCode.INVALID)
        body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not 1 <= len(body) <= 24000:
            raise CatalogStoreError(ErrorCode.INVALID)

        def work(query: Query) -> dict[str, Any]:
            record = json_query(
                query, "SELECT public.subscription_current(%s,false)", (subject,)
            )
            validated_terms(record, self._models)
            return json_query(
                query,
                "SELECT public.subscription_clipboard_save(%s,%s,%s,%s)",
                (subject, session_id, key, body),
            )

        return self._channel._transaction(True, work)

    def auto(
        self, actor: VerifiedActor, action: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        import json

        from pydantic import BaseModel, ConfigDict, Field

        from app.commercial.catalog_contract import Identifier

        class Start(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            run_id: Identifier
            request_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,120}$")

        class Update(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            run_id: Identifier
            owner_token: Identifier
            fence: int = Field(gt=0, le=2**63 - 1)
            sequence: int = Field(gt=0, le=2**63 - 1)

        class Read(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            run_id: Identifier

        subject = self._channel._actor(actor)
        try:
            if action == "start":
                import hashlib

                data = Start.model_validate(document).model_dump()
                data["semantic_hash"] = hashlib.sha256(
                    c.canonical_json([subject, "auto.start", data["run_id"]]).encode()
                ).hexdigest()
            elif action in ("renew", "stop"):
                data = Update.model_validate(document).model_dump()
            elif action == "status":
                data = Read.model_validate(document).model_dump()
            else:
                raise ValueError()
        except Exception:
            raise CatalogStoreError(ErrorCode.INVALID) from None

        def work(query: Query) -> dict[str, Any]:
            record = json_query(
                query, "SELECT public.subscription_current(%s,false)", (subject,)
            )
            validated_terms(record, self._models)
            return json_query(
                query,
                "SELECT public.subscription_auto_call(%s,%s,%s::jsonb)",
                (subject, action, json.dumps(data)),
            )

        return self._channel._transaction(True, work)

    def current(
        self, actor: VerifiedActor, *, bootstrap: bool = False
    ) -> dict[str, Any]:
        subject = self._channel._actor(actor)

        def work(query: Query) -> dict[str, Any]:
            record = json_query(
                query, "SELECT public.subscription_current(%s,%s)", (subject, bootstrap)
            )
            snapshot = validated_terms(record, self._models)
            query("SELECT public.subscription_auto_reap(%s)", (subject,))
            usage = query("SELECT public.subscription_account_usage(%s)", (subject,))
            capacity = json_query(
                query,
                "SELECT public.subscription_resume_call(%s,'capacity','{}'::jsonb)",
                (subject,),
            )
            for item in usage:
                if item["meter"] == "resume.stored_files":
                    item["used"] = str(capacity["used"])
                    item["reserved"] = str(capacity["reserved"])
            binding = record["binding"]
            return dict(
                contract_version="account.subscription.v1",
                plan=dict(
                    name=snapshot.terms.name,
                    offer_version_id=snapshot.offer_version_id,
                    version=str(snapshot.version),
                    revision=str(binding["revision"]),
                    valid_until=binding["valid_until"],
                ),
                features=[
                    dict(feature=e.feature, allowed=e.allowed)
                    for e in snapshot.terms.entitlements
                ],
                usage=usage,
                server_time=record["at"],
                checkout_ready=False,
            )

        return self._channel._transaction(True, work)


class VerifiedPaymentService(AccountEntitlements):
    """Trusted backend capability, never constructed by production composition.

    C12 must supply its authenticated provider-event verifier. A dict/boolean
    from a customer or admin is not payment evidence. Tests inject a verifier.
    """

    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        verify: Callable[[object], dict[str, Any]] | None = None,
        model_keys: frozenset[str] = frozenset()
    ) -> None:
        super().__init__(connect, model_keys=model_keys)
        self._verify = verify

    def apply(self, evidence: object) -> dict[str, Any]:
        import hashlib

        if self._verify is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            event = PaymentEvent.model_validate(self._verify(evidence)).model_dump(
                mode="json"
            )
            semantic = hashlib.sha256(c.canonical_json(event).encode()).hexdigest()
        except Exception:
            raise CatalogStoreError(ErrorCode.DENIED) from None

        def work(query: Query) -> dict[str, Any]:
            record = json_query(
                query,
                "SELECT public.usage_terms_read(%s)",
                (event["offer_version_id"],),
            )
            validated_terms(record, self._models)
            return json_query(
                query,
                "SELECT public.subscription_payment_apply(%s,%s,%s,%s,%s,%s)",
                (
                    event["account_id"],
                    event["event_id"],
                    event["offer_version_id"],
                    event["price_id"],
                    event["paid_until"],
                    semantic,
                ),
            )

        return self._channel._transaction(True, work)

    def schedule(self, evidence: object) -> dict[str, Any]:
        """C12 must verify cancellation intent or future paid downgrade evidence.

        The SQL binding owns the effective date; callers cannot shorten a paid
        period. No public/admin endpoint or production verifier is installed.
        """
        import hashlib

        if self._verify is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            event = PeriodChange.model_validate(self._verify(evidence)).model_dump(
                mode="json"
            )
            if event["kind"] == "cancel":
                if any(
                    event[k] is not None
                    for k in ("offer_version_id", "price_id", "paid_until")
                ):
                    raise ValueError()
            elif any(
                event[k] is None for k in ("offer_version_id", "price_id", "paid_until")
            ):
                raise ValueError()
            semantic = hashlib.sha256(c.canonical_json(event).encode()).hexdigest()
        except Exception:
            raise CatalogStoreError(ErrorCode.DENIED) from None

        def work(query: Query) -> dict[str, Any]:
            if event["kind"] == "downgrade":
                record = json_query(
                    query,
                    "SELECT public.usage_terms_read(%s)",
                    (event["offer_version_id"],),
                )
                validated_terms(record, self._models)
            return json_query(
                query,
                "SELECT public.subscription_schedule_change(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event["account_id"],
                    event["event_id"],
                    semantic,
                    event["kind"],
                    event["expected_revision"],
                    event["offer_version_id"],
                    event["price_id"],
                    event["paid_until"],
                ),
            )

        return self._channel._transaction(True, work)
