"""Test-only Subscriptions adapter. No automatic mutation retry."""

import hashlib
import hmac
import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import requests

logger = logging.getLogger(__name__)
network_deadline = ContextVar("billing_network_deadline", default=None)


@contextmanager
def network_budget():
    token = network_deadline.set(time.monotonic() + 25)
    try:
        yield
    finally:
        network_deadline.reset(token)


class PaymentUnavailable(Exception):
    def __str__(self) -> str:
        return "payment unavailable"


def signature(secret: str, body: bytes, supplied: str) -> bool:
    return bool(
        secret
        and re.fullmatch(r"[0-9a-f]{64}", supplied)
        and hmac.compare_digest(
            hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), supplied
        )
    )


class RazorpaySubscriptions:
    def __init__(self, key: str, secret: str):
        if not re.fullmatch(r"rzp_test_[A-Za-z0-9]+", key) or not secret:
            raise PaymentUnavailable()
        self.key, self._secret = key, secret

    def _request(self, method: str, path: str, document=None) -> dict[str, Any]:
        # GETs can be retried by the bounded reconciler. POSTs are sent once.
        try:
            deadline = network_deadline.get()
            remaining = deadline - time.monotonic() if deadline else 11
            if remaining <= 0:
                raise PaymentUnavailable()
            response = requests.request(
                method,
                "https://api.razorpay.com/v1/" + path,
                auth=(self.key, self._secret),
                json=document,
                timeout=(min(3, remaining), min(8, remaining)),
                allow_redirects=False,
            )
            if response.status_code not in (200, 201) or len(response.content) > 262144:
                raise PaymentUnavailable()
            data = response.json()
            if not isinstance(data, dict):
                raise PaymentUnavailable()
            return data
        except Exception:
            logger.exception("billing operation unavailable", exc_info=False)
            raise PaymentUnavailable() from None

    def create(self, operation):
        return self._request(
            "POST",
            "subscriptions",
            {
                "plan_id": operation["provider_plan"],
                "total_count": operation["total_count"],
                "quantity": 1,
                "notes": {"operation_id": operation["operation_id"]},
            },
        )

    def subscription(self, subscription_id):
        if not re.fullmatch(r"sub_[A-Za-z0-9]+", subscription_id):
            raise PaymentUnavailable()
        return self._request("GET", "subscriptions/" + subscription_id)

    def invoices(self, subscription_id):
        # Bounded pagination; incomplete history fails closed for reconciliation.
        items = []
        for skip in range(0, 1000, 100):
            page = self._request(
                "GET",
                "invoices?subscription_id="
                + subscription_id
                + "&count=100&skip="
                + str(skip),
            ).get("items", [])
            items.extend(page)
            if len(page) < 100:
                return items
        raise PaymentUnavailable()

    def payment(self, payment_id):
        if not re.fullmatch(r"pay_[A-Za-z0-9]+", payment_id):
            raise PaymentUnavailable()
        return self._request("GET", "payments/" + payment_id)

    def plan(self, plan_id):
        if not re.fullmatch(r"plan_[A-Za-z0-9]+", plan_id):
            raise PaymentUnavailable()
        return self._request("GET", "plans/" + plan_id)

    def cancel(self, subscription_id):
        self.subscription(subscription_id)
        return self._request(
            "POST",
            "subscriptions/" + subscription_id + "/cancel",
            {"cancel_at_cycle_end": 1},
        )

    def find(self, operation):
        matches = []
        for skip in range(0, 1000, 100):
            page = self._request(
                "GET", "subscriptions?count=100&skip=" + str(skip)
            ).get("items", [])
            matches.extend(
                x
                for x in page
                if x.get("notes", {}).get("operation_id") == operation["operation_id"]
            )
            if len(page) < 100:
                return matches
        raise PaymentUnavailable()  # no absence inference from an incomplete scan

    def callback(self, subscription_id, payment_id, supplied):
        return signature(
            self._secret, (payment_id + "|" + subscription_id).encode(), supplied
        )


def decoded_event(raw: bytes, supplied: str, secrets: tuple[str, ...], merchant: str):
    if len(raw) > 131072 or not any(signature(s, raw, supplied) for s in secrets):
        raise PaymentUnavailable()
    try:
        data = json.loads(raw)
        if data["account_id"] != merchant or data["entity"] != "event":
            raise ValueError()
        return data
    except Exception:
        logger.exception("billing operation unavailable", exc_info=False)
        raise PaymentUnavailable() from None
