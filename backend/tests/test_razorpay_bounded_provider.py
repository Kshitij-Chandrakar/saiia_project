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


def test_cleanup_only_recovers_transient_failure_without_reopening_intake(tmp_path, monkeypatch):
    import razorpay_test_mode_execution as execution
    budget = SessionBudget(tmp_path)
    budget.reserve("gets")
    budget.resource("subscriptions", "sub_synthetic")
    budget.close_intake()
    start = budget.load()["start_utc"]
    class Provider:
        fails = True
        def subscription(self, identifier):
            assert identifier == "sub_synthetic"
            budget.reserve("gets", cleanup=True)
            if self.fails:
                self.fails = False
                raise RuntimeError("synthetic 503")
            return {"status": "cancelled"}
    provider = Provider()
    monkeypatch.setattr(execution, "BoundedProvider", lambda *_: provider)
    credentials = {"RAZORPAY_TEST_KEY_ID": "rzp_test_synthetic", "RAZORPAY_TEST_KEY_SECRET": "synthetic"}
    with pytest.raises(RuntimeError, match="unresolved"):
        execution.cleanup_only(credentials, tmp_path)
    assert budget.load()["status"] == "cleanup"
    with pytest.raises(RuntimeError):
        budget.reserve("plans")
    execution.cleanup_only(credentials, tmp_path)
    assert budget.load()["status"] == "finished" and budget.load()["start_utc"] == start
    assert budget.load()["counts"]["gets"] == 3


def test_pending_lookup_failure_returns_to_remaining_cleanup(tmp_path):
    from razorpay_test_mode_execution import cleanup_pending
    class Service:
        def pending(self):
            raise RuntimeError("private database diagnostic")
    budget = SessionBudget(tmp_path)
    assert cleanup_pending(Service(), budget) is False
    assert budget.load()["events"][-1]["stage"] == "cleanup_pending_lookup_unresolved"
    assert "private database diagnostic" not in budget.path.read_text()


def test_cleanup_pending_retries_every_operation_without_clearing_failure(tmp_path):
    from razorpay_test_mode_execution import cleanup_pending
    calls = []
    class Service:
        fails = True
        def pending(self):
            return [{"account_id": "synthetic", "operation_id": str(i)} for i in range(2)]
        def reconcile(self, account, operation):
            calls.append(operation)
            if self.fails and operation == "0":
                raise RuntimeError("synthetic timeout")
            return {"provider_id": "sub_" + operation}
    service = Service()
    budget = SessionBudget(tmp_path)
    assert not cleanup_pending(service, budget)
    assert calls == ["0", "1"]
    service.fails = False
    assert cleanup_pending(service, budget)
    assert calls == ["0", "1", "0", "1"]
    service.reconcile = lambda *_: {"state": "expired"}
    assert cleanup_pending(service, budget)
