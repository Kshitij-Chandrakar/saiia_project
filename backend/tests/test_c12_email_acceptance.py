"""Acceptance transport boundaries; no network or credentials."""

from datetime import datetime, timedelta, timezone

import pytest
from c12_email_acceptance import BoundedSession
from test_billing_email_provider import Session


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
