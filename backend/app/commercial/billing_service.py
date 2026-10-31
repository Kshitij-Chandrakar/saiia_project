"""Durable recurring checkout. Authority stays in existing C13 transactions.


Automatic renewal requires explicit stored consent. No browser grants access.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict

from app.commercial import catalog_contract as c
from app.commercial.account_entitlements import validated_terms
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_service import DraftService
from app.commercial.payable import payable
from app.commercial.razorpay import PaymentUnavailable, decoded_event, network_budget

logger = logging.getLogger(__name__)


class Checkout(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: c.Identifier
    offer_version_id: c.Identifier
    price_id: c.Identifier


class BillingService:
    def __init__(
        self,
        connect,
        provider,
        *,
        merchant: str,
        webhook_secrets: tuple[str, ...],
        renewal: str = "",
        enabled: bool = False,
        total_policy_ref: str = "",
        plan_mappings=None,
        model_keys=frozenset(),
    ):
        self.channel = DraftService(connect, model_keys=model_keys)
        self.provider, self.merchant, self.secrets = provider, merchant, webhook_secrets
        self.enabled = (
            enabled
            and renewal == "automatic"
            and bool(merchant and webhook_secrets)
            and provider.key.startswith("rzp_test_")
        )
        self.models = model_keys
        self.total_policy_ref = total_policy_ref
        self.plan_mappings = plan_mappings or {}

    def _call(self, account, action, operation, document=None):
        if not self.enabled:
            raise PaymentUnavailable()
        return self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_call(%s,%s,%s,%s::jsonb)",
                (account, action, operation, json.dumps(document or {})),
            ),
        )

    def _operation(self, account, operation):
        record = self._call(account, "read", operation)
        if record["mode"] != "test" or record["merchant"] != self.merchant:
            raise PaymentUnavailable()
        raw = json.loads(record["snapshot"])
        snapshot = validated_terms(
            {
                "snapshot": record["snapshot"],
                "fingerprint": record["fingerprint"],
                "offer_version_id": raw["offer_version_id"],
                "plan_id": raw["plan"]["plan_id"],
                "version": int(raw["version"]),
            },
            self.models,
        )
        if record.get("payable") is not None and record["payable"] != payable(
            snapshot, record["price_id"]
        ):
            raise PaymentUnavailable()
        if record.get("payable") is not None and (
            record["amount"] != int(record["payable"]["total_amount_minor"])
            or record["currency"] != record["payable"]["currency"]
            or snapshot.offer_version_id != record["offer_version_id"]
        ):
            raise PaymentUnavailable()
        return record

    def view(self, operation):
        raw = json.loads(operation["snapshot"])
        return {
            "operation_id": operation["operation_id"],
            "state": operation["state"],
            "name": raw["terms"]["name"],
            "offer_version_id": operation["offer_version_id"],
            "fingerprint": operation["fingerprint"],
            "price_id": operation["price_id"],
            "amount_minor": str(operation["amount"]),
            "currency": operation["currency"],
            "interval": operation["interval_unit"],
            "renewal": "automatic",
            "total_count": operation["total_count"],
            "cancel_requested": operation["cancel_requested"],
            "provider_state": operation["provider_state"],
            "provider_id": operation["provider_id"],
            "key_id": self.provider.key if operation["state"] == "ready" else None,
            "payable": operation.get("payable"),
            "quote_id": operation.get("quote_id"),
            "review_required": operation.get("payable") is None
            and operation["state"] == "prepared",
        }

    def prepare(self, actor, document):
        account = self.channel._actor(actor)
        data = Checkout.model_validate(document).model_dump()
        mapping = self.plan_mappings.get(data["price_id"])
        if (
            not mapping
            or set(mapping) != {"provider_plan", "total_count"}
            or type(mapping["total_count"]) is not int
            or mapping["total_count"] < 1
        ):
            raise PaymentUnavailable()
        record = self._call(
            account,
            "prepare",
            data.pop("operation_id"),
            {
                **data,
                **mapping,
                "merchant": self.merchant,
                "total_policy_ref": self.total_policy_ref,
            },
        )
        return self.view(self._operation(account, record["operation_id"]))

    def start(self, actor, operation, consent=False, quote_id=None):
        account = self.channel._actor(actor)
        record = self._operation(account, operation)
        if (
            record.get("payable") is None
            and record["state"] == "prepared"
            and not record["provider_id"]
        ):
            raise CatalogStoreError(ErrorCode.IDENTITY_CONFLICT)
        self._validate_plan(record)
        claim = self._call(
            account, "claim", operation, {"consent": consent, "quote_id": quote_id}
        )
        if claim.get("dispatch"):
            try:
                order = self.provider.create(record)
                self._validate_subscription(record, order)
                self._call(account, "attach", operation, {"provider_id": order["id"]})
            except Exception:
                logger.exception("billing operation unavailable", exc_info=False)
                self._call(account, "uncertain", operation)
        return self.status(actor, operation)

    def _validate_plan(self, op):
        plan = self.provider.plan(op["provider_plan"])
        item = plan.get("item", {})
        if (
            plan.get("id") != op["provider_plan"]
            or plan.get("entity") != "plan"
            or plan.get("period")
            != ("monthly" if op["interval_unit"] == "month" else "yearly")
            or plan.get("interval") != 1
            or item.get("amount") != op["amount"]
            or type(item.get("amount")) is not int
            or item.get("currency") != op["currency"]
            or (
                op.get("payable") is not None
                and any(
                    item.get(k) not in (None, [], 0)
                    for k in ("tax_id", "tax_group_id", "tax_rate", "taxes")
                )
            )
        ):
            raise PaymentUnavailable()

    def _validate_subscription(self, op, subscription):
        if (
            subscription.get("entity") != "subscription"
            or subscription.get("plan_id") != op["provider_plan"]
            or subscription.get("quantity") != 1
            or subscription.get("total_count") != op["total_count"]
            or subscription.get("offer_id") is not None
            or subscription.get("notes", {}).get("operation_id") != op["operation_id"]
        ):
            raise PaymentUnavailable()
        self._validate_plan(op)

    def reconcile(self, account, operation, expected_payment_id=None):
        with network_budget():
            return self._reconcile(account, operation, expected_payment_id)

    def _reconcile(self, account, operation, expected_payment_id=None):
        op = self._operation(account, operation)
        op = self._call(account, "recover", operation)
        if op["state"] == "expired":
            return op
        if not op["provider_id"]:
            if op["state"] not in ("creating", "uncertain"):
                return op
            matches = self.provider.find(op)
            if len(matches) != 1:
                return op
            self._validate_subscription(op, matches[0])
            self._call(account, "attach", operation, {"provider_id": matches[0]["id"]})
            op = self._operation(account, operation)
        subscription = self.provider.subscription(op["provider_id"])
        self._validate_subscription(op, subscription)
        invoices = sorted(
            self.provider.invoices(op["provider_id"]),
            key=lambda i: i.get("billing_end") or 0,
        )
        matched = expected_payment_id is None
        for invoice in invoices:
            if invoice.get("status") != "paid":
                continue
            payment = self.provider.payment(invoice["payment_id"])
            if expected_payment_id == payment.get("id"):
                matched = True
            if (
                invoice.get("entity") != "invoice"
                or type(invoice.get("amount")) is not int
                or type(payment.get("amount")) is not int
                or invoice.get("subscription_id") != op["provider_id"]
                or invoice.get("currency") != op["currency"]
                or invoice.get("amount") != op["amount"]
                or invoice.get("amount_paid") != op["amount"]
                or invoice.get("amount_due") != 0
                or invoice.get("partial_payment") is not False
                or payment.get("entity") != "payment"
                or payment.get("status") != "captured"
                or payment.get("captured") is not True
                or payment.get("order_id") != invoice.get("order_id")
                or not invoice.get("order_id")
                or payment.get("invoice_id") != invoice["id"]
                or payment.get("amount") != op["amount"]
                or payment.get("currency") != op["currency"]
                or payment.get("amount_refunded") != 0
                or type(invoice.get("billing_start")) is not int
                or type(invoice.get("billing_end")) is not int
                or invoice["billing_end"] <= invoice["billing_start"]
                or len(invoice.get("line_items", [])) != 1
                or invoice["line_items"][0].get("type") != "plan"
                or invoice["line_items"][0].get("quantity") != 1
                or (
                    op.get("payable") is not None
                    and (
                        invoice.get("tax_amount", 0) != 0
                        or invoice["line_items"][0].get("tax_amount", 0) != 0
                        or invoice["line_items"][0].get("taxes") not in (None, [])
                        or invoice["line_items"][0].get("amount") != op["amount"]
                    )
                )
            ):
                raise PaymentUnavailable()
            # Exact provider invoice period, independent of signup allowance resets.
            until = datetime.fromtimestamp(invoice["billing_end"], timezone.utc)
            evidence = {
                "provider_id": op["provider_id"],
                "payment_id": payment["id"],
                "invoice_id": invoice["id"],
                "event_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        "razorpay:test:" + self.merchant + ":" + invoice["id"],
                    )
                ),
                "paid_until": until.isoformat(),
            }
            evidence["evidence_hash"] = hashlib.sha256(
                c.canonical_json(evidence).encode()
            ).hexdigest()
            self._call(account, "record", operation, evidence)
        if not matched:
            # Authorization-only callbacks are pending, never an access grant.
            return self._call(
                account, "provider_state", operation, {"status": subscription["status"]}
            )
        op = self._call(account, "apply", operation)
        return self._call(
            account, "provider_state", operation, {"status": subscription["status"]}
        )

    def cancel(self, actor, operation):
        account = self.channel._actor(actor)
        op = self._operation(account, operation)
        if not op["provider_id"]:
            raise PaymentUnavailable()
        claim = self._call(account, "cancel_claim", operation)
        if claim.get("dispatch"):
            try:
                self.provider.cancel(op["provider_id"])
            except Exception:
                logger.exception("billing operation unavailable", exc_info=False)
                # Read/reconcile only after an uncertain mutation.
        return self.view(self.reconcile(account, operation))

    def status(self, actor, operation):
        account = self.channel._actor(actor)
        return self.view(self.reconcile(account, operation))

    def current(self, actor):
        account = self.channel._actor(actor)
        if not self.enabled:
            raise PaymentUnavailable()
        operation = self.channel._transaction(
            False, lambda q: q("SELECT public.billing_current(%s)", (account,))
        )
        return self.view(self.reconcile(account, str(operation))) if operation else None

    def callback(self, actor, operation, document):
        account = self.channel._actor(actor)
        op = self._operation(account, operation)
        if (
            set(document)
            != {"razorpay_subscription_id", "razorpay_payment_id", "razorpay_signature"}
            or document["razorpay_subscription_id"] != op["provider_id"]
            or not self.provider.callback(
                op["provider_id"],
                document["razorpay_payment_id"],
                document["razorpay_signature"],
            )
        ):
            raise PaymentUnavailable()
        return self.view(
            self.reconcile(account, operation, document["razorpay_payment_id"])
        )

    def pending(self):
        if not self.enabled:
            raise PaymentUnavailable()
        return self.channel._transaction(
            False, lambda q: q("SELECT public.billing_pending()", ())
        )

    def sweep(self):
        import time

        deadline = time.monotonic() + 20
        result = {"checked": 0, "pending": 0, "unavailable": 0}
        for op in self.pending()[:5]:
            if time.monotonic() > deadline:
                break
            if op["merchant"] != self.merchant:
                continue
            try:
                updated = self.reconcile(op["account_id"], op["operation_id"])
                result["checked"] += 1
                result["pending"] += updated["state"] != "confirmed"
            except Exception:
                logger.exception("billing operation unavailable", exc_info=False)
                result["unavailable"] += 1
        return result

    def webhook(self, raw, supplied):
        if not self.enabled:
            raise PaymentUnavailable()
        event = decoded_event(raw, supplied, self.secrets, self.merchant)
        if event.get("event") not in (
            "subscription.charged",
            "subscription.authenticated",
            "subscription.activated",
            "subscription.pending",
            "subscription.halted",
            "subscription.cancelled",
            "subscription.completed",
            "subscription.updated",
        ):
            raise PaymentUnavailable()
        entity = event["payload"]["subscription"]["entity"]
        order_id = entity["id"]
        self.channel._transaction(
            True,
            lambda q: q(
                "SELECT public.billing_event(%s,%s,%s,%s)",
                (
                    hashlib.sha256(raw).hexdigest(),
                    self.merchant,
                    order_id,
                    event["event"],
                ),
            ),
        )
        op = self.channel._transaction(
            False, lambda q: q("SELECT public.billing_lookup(%s)", (order_id,))
        )
        if op and op["merchant"] == self.merchant:
            result = self.reconcile(op["account_id"], op["operation_id"])
            if result["state"] == "confirmed":
                return
        # Unknown/uncertain orders are durably recorded; sweep recovers the
        # accepted receipt without ever creating another provider object.
