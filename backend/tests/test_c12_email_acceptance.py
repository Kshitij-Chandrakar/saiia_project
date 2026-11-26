"""Acceptance transport boundaries; no network or credentials."""

from datetime import datetime, timedelta, timezone

import pytest
from c12_email_acceptance import BoundedSession
from test_billing_email_provider import Session


def test_admin_matrix_requires_all_selected_call_reports():
    from c12_admin_acceptance import RequiredCalls
    from types import SimpleNamespace

    required = RequiredCalls()
    assert required.exit_code(0) == 1
    required.pytest_collection_modifyitems([SimpleNamespace(nodeid="one"), SimpleNamespace(nodeid="two")])
    required.pytest_runtest_logreport(SimpleNamespace(nodeid="one", when="call", passed=True))
    assert required.exit_code(0) == 1
    required.pytest_runtest_logreport(SimpleNamespace(nodeid="two", when="setup", passed=True))
    assert required.exit_code(0) == 1
    required.pytest_runtest_logreport(SimpleNamespace(nodeid="two", when="call", passed=True))
    assert required.exit_code(0) == 0 and required.exit_code(5) == 5


@pytest.mark.parametrize("live", [False, True])
def test_uncertain_callback_send_reserves_one_attempt_without_http_response(tmp_path, live):
    from c12_resend_callback_acceptance import OneSend, SENDER

    journal = OneSend(tmp_path, Session(error=TimeoutError), live=live)
    options = arguments()
    options["json"].update({"from": SENDER, "to": [journal.recipient], "text": "synthetic", "html": "synthetic"})
    with pytest.raises(TimeoutError):
        journal.post("https://api.resend.com/emails", **options)
    assert journal.state["attempts"] == 1
    assert journal.state["real_send_attempt_reservations"] == int(live)
    assert journal.state["real_provider_calls"] == 0


def test_callback_deadline_does_not_wait_forever_or_claim_cleanup(tmp_path):
    from c12_resend_callback_acceptance import OneSend, await_provider_disable, forwarding_exhausted, completion_stage

    journal = OneSend(tmp_path, Session())
    assert not await_provider_disable(journal, tmp_path)
    assert journal.state["provider_webhook_disable"] == "unconfirmed_cleanup_required"
    (tmp_path / "webhook-disabled.confirmed").touch()
    assert await_provider_disable(journal, tmp_path)
    rows = [{"status": 200}] * 11 + [{"status": "reserved"}]
    assert not forwarding_exhausted(rows)
    rows[-1]["status"] = 200
    assert forwarding_exhausted(rows)
    state = {"result": "verified", "cleanup": {"tunnel_stopped": True}, "provider_webhook_disable": "owner_confirmed_disabled"}
    assert completion_stage(state) == "finished"
    assert completion_stage({**state, "error_type": "TimeoutError"}) == "stopped"
    assert completion_stage({**state, "cleanup": {"tunnel_stopped": False}}) == "stopped"


def test_callback_snapshot_stays_reserved_when_final_forward_settles():
    import threading
    from types import SimpleNamespace
    from c12_resend_callback_acceptance import callback_snapshot, forwarding_exhausted
    journal = SimpleNamespace(lock=threading.Lock(), state={"forwarded_callbacks": [{"status": 200}] * 11 + [{"status": "reserved"}]})
    _, rows = callback_snapshot(journal)
    with journal.lock:
        journal.state["forwarded_callbacks"][-1]["status"] = 200
    assert not forwarding_exhausted(rows)
    assert forwarding_exhausted(callback_snapshot(journal)[1])


def test_callback_incomplete_cleanup_cannot_return_success():
    from c12_resend_callback_acceptance import completion_stage, finished_result
    state = {"result": "verified", "cleanup": {"database_removed": True},
             "provider_webhook_disable": "owner_confirmed_disabled"}
    for changes in ({"cleanup_error_type": "TimeoutError"}, {"provider_webhook_disable": "unconfirmed_cleanup_required"}):
        stopped = {**state, **changes}
        stopped["stage"] = completion_stage(stopped)
        with pytest.raises(RuntimeError, match="cleanup incomplete"):
            finished_result(stopped)
        assert stopped["result"] == "verified"
    state["stage"] = completion_stage(state)
    assert finished_result(state) is state


def arguments():
    return {
        "headers": {
            "Idempotency-Key": "billing:synthetic",
            "Authorization": "Bearer synthetic-credential-never-record",
        },
        "json": {
            "from": "billing@example.invalid",
            "to": ["test@example.invalid"],
            "subject": "[SYNTHETIC C12 TEST] payment",
        },
        "timeout": (3, 10),
        "allow_redirects": False,
    }


def test_budget_is_durable_and_restart_cannot_reset(tmp_path):
    journal = BoundedSession(
        tmp_path, "billing@example.invalid", "test@example.invalid", Session()
    )
    for _ in range(2):
        journal.post("https://api.resend.com/emails", **arguments())
    with pytest.raises(ValueError, match="limit"):
        journal.post("https://api.resend.com/emails", **arguments())
    with pytest.raises(FileExistsError):
        BoundedSession(
            tmp_path, "billing@example.invalid", "test@example.invalid", Session()
        )
    assert journal.state["attempts"] == 2
    assert "synthetic-credential-never-record" not in journal.path.read_text()
    assert "test@example.invalid" not in journal.path.read_text()


def test_unknown_result_counts_and_allowlist_blocks(tmp_path):
    journal = BoundedSession(
        tmp_path,
        "billing@example.invalid",
        "test@example.invalid",
        Session(error=TimeoutError),
    )
    changed = arguments()
    changed["json"]["to"] = ["other@example.invalid"]
    with pytest.raises(ValueError, match="boundary"):
        journal.post("https://api.resend.com/emails", **changed)
    assert journal.state["attempts"] == 0
    with pytest.raises(TimeoutError):
        journal.post("https://api.resend.com/emails", **arguments())
    assert journal.state["attempts"] == 1
    assert journal.state["observations"][0]["outcome"] == "unknown_transport_result"
    journal.state["deadline_utc"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValueError, match="limit"):
        journal.post("https://api.resend.com/emails", **arguments())
    assert journal.state["attempts"] == 1
