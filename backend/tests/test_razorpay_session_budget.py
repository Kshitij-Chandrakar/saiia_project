from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from razorpay_session_budget import SessionBudget


def test_clock_starts_only_with_first_external_attempt_and_survives_restart(tmp_path):
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    budget = SessionBudget(tmp_path, lambda: now)
    assert budget.load()["start_utc"] is None
    budget.reserve("tunnels")
    restored = SessionBudget(tmp_path, lambda: now + timedelta(minutes=61))
    assert restored.load()["counts"]["tunnels"] == 1
    with pytest.raises(RuntimeError, match="deadline"):
        restored.reserve("plans")
    restored.reserve("cancellations", cleanup=True)
    assert restored.load()["counts"]["cancellations"] == 1
    assert restored.load()["start_ist"].endswith("+05:30")


def test_concurrent_attempts_never_exceed_limit_and_are_not_reset(tmp_path):
    budget = SessionBudget(tmp_path)

    def attempt(_):
        try:
            budget.reserve("subscriptions")
            return True
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=8) as workers:
        assert sum(workers.map(attempt, range(20))) == 8
    assert SessionBudget(tmp_path).load()["counts"]["subscriptions"] == 8
    budget.close_intake()
    with pytest.raises(RuntimeError):
        budget.reserve("plans")
    budget.reserve("gets", cleanup=True)
    budget.close_intake("finished")
    with pytest.raises(RuntimeError):
        budget.reserve("gets", cleanup=True)


def test_one_authentication_retry_preserves_clock_and_attempts(tmp_path):
    budget = SessionBudget(tmp_path)
    budget.reserve("gets")
    original = budget.load()
    budget.event("provider_http_error", http_status=401)
    budget.close_intake("finished")
    budget.resume_after_authentication_rejection()
    assert budget.load()["start_utc"] == original["start_utc"]
    assert budget.load()["deadline_utc"] == original["deadline_utc"]
    assert budget.load()["counts"]["gets"] == 1
    budget.reserve("gets")
    budget.close_intake("finished")
    with pytest.raises(RuntimeError):
        budget.resume_after_authentication_rejection()


def test_independent_budget_instances_share_the_same_reservation_lock(tmp_path):
    def attempt(_):
        budget = SessionBudget(tmp_path)
        try:
            budget.reserve("subscriptions")
            return True
        except RuntimeError:
            return False

    with ThreadPoolExecutor(8) as workers:
        assert sum(workers.map(attempt, range(20))) == 8
    assert SessionBudget(tmp_path).load()["counts"]["subscriptions"] == 8
