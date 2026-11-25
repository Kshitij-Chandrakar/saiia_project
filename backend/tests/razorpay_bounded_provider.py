"""Real adapter transport for the authorized session, with durable attempt limits."""

import re

import requests
from app.commercial.razorpay import PaymentUnavailable, RazorpaySubscriptions


class BoundedProvider(RazorpaySubscriptions):
    def __init__(self, key, secret, budget):
        super().__init__(key, secret)
        self.budget = budget
        self.cleanup = False

    def _request(self, method, path, document=None):
        if method == "GET":
            category = "gets"
        elif method == "POST" and path == "plans":
            category = "plans"
        elif method == "POST" and path == "subscriptions":
            category = "subscriptions"
        elif method == "POST" and re.fullmatch(
            r"subscriptions/sub_[A-Za-z0-9]+/cancel", path
        ):
            category = "cancellations"
        else:
            raise PaymentUnavailable()
        if (
            category == "gets"
            and not self.cleanup
            and self.budget.load()["counts"]["gets"] >= 460
        ):
            self.budget.close_intake()
            raise RuntimeError("Provider read intake stopped with cleanup reserve")
        self.budget.reserve(category, cleanup=self.cleanup)
        try:
            response = requests.request(
                method,
                "https://api.razorpay.com/v1/" + path,
                auth=(self.key, self._secret),
                json=document,
                timeout=(3, 10),
                allow_redirects=False,
            )
            if response.status_code >= 300:
                code = "UNCLASSIFIED"
                try:
                    supplied = response.json().get("error", {}).get("code", "")
                    if isinstance(supplied, str) and re.fullmatch(
                        r"[A-Z_]{1,64}", supplied
                    ):
                        code = supplied
                except ValueError:
                    pass
                self.budget.event(
                    "provider_http_error",
                    category=category,
                    http_status=response.status_code,
                    provider_code=code,
                )
                raise PaymentUnavailable()
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError()
            if category in {"plans", "subscriptions"}:
                prefix = "plan_" if category == "plans" else "sub_"
                resource = data.get("id", "")
                if not isinstance(resource, str) or not re.fullmatch(
                    prefix + r"[A-Za-z0-9]+", resource
                ):
                    raise ValueError()
                self.budget.resource(category, resource)
            self.budget.event(
                "provider_response", category=category, http_status=response.status_code
            )
            return data
        except (requests.RequestException, ValueError, TypeError) as error:
            self.budget.event(
                "provider_transport_or_json_error",
                category=category,
                exception_type=type(error).__name__,
            )
            raise PaymentUnavailable() from None

    def create_plan(self, unit, amount, name):
        if unit not in {"month", "year"} or amount not in {
            47082,
            353882,
            106082,
            766882,
        }:
            raise PaymentUnavailable()
        return self._request(
            "POST",
            "plans",
            {
                "period": "monthly" if unit == "month" else "yearly",
                "interval": 1,
                "item": {"name": name, "amount": amount, "currency": "INR"},
            },
        )
