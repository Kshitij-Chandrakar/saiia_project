import json

import pytest
import requests
from app.commercial.razorpay import PaymentUnavailable
from razorpay_bounded_provider import BoundedProvider
from razorpay_session_budget import SessionBudget


def test_attempt_count_commits_before_uncertain_network_outcome(tmp_path, monkeypatch):
    budget = SessionBudget(tmp_path)
    provider = BoundedProvider("rzp_test_synthetic", "synthetic-secret", budget)

    def fail(*args, **kwargs):
        assert budget.load()["counts"]["plans"] == 1
        raise requests.Timeout("sensitive synthetic transport description")

    monkeypatch.setattr(requests, "request", fail)
    with pytest.raises(PaymentUnavailable):
        provider.create_plan("month", 47082, "C12 synthetic")
    state = budget.load()
    assert state["counts"]["plans"] == 1
    assert state["events"][-1]["exception_type"] == "Timeout"
    assert "sensitive" not in json.dumps(state)


def test_provider_error_records_code_and_status_without_description(
    tmp_path, monkeypatch
):
    budget = SessionBudget(tmp_path)
    provider = BoundedProvider("rzp_test_synthetic", "synthetic-secret", budget)

    class Response:
        status_code = 401

        def json(self):
            return {
                "error": {"code": "BAD_REQUEST_ERROR", "description": "private text"}
            }

    monkeypatch.setattr(requests, "request", lambda *a, **k: Response())
    with pytest.raises(PaymentUnavailable):
        provider.plan("plan_synthetic")
    state = budget.load()
    assert state["counts"]["gets"] == 1
    assert state["events"][-1]["http_status"] == 401
    assert "private text" not in json.dumps(state)
