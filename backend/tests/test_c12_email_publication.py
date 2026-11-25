"""Deterministic publication/no-overwrite/uncertain-outcome boundary checks."""

from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests
from c12_email_acceptance import BoundedSession
from c12_email_publication import ASSETS, Publication, existing_journal
from test_billing_email_provider import Session


class Storage:
    def __init__(self, existing=False, uncertain=False):
        self.existing, self.uncertain = existing, uncertain
        self.calls = []

    def request(self, method, url, **kwargs):
        path = urlsplit(url).path
        self.calls.append((method, path))
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == (3, 10)
        if "/public/" in path:
            assert "Authorization" not in kwargs["headers"]
            asset = next(asset for asset in ASSETS if path.endswith(asset[1]))
            return Response(
                content=(
                    Path("frontend/public/email-assets/billing") / asset[0]
                ).read_bytes(),
                mime=asset[2],
            )
        if path.endswith("/bucket/email-assets"):
            return Response(payload={"id": "email-assets", "public": True})
        if path.endswith("/list/email-assets"):
            return Response(payload=[{"name": ASSETS[0][1]}] if self.existing else [])
        assert kwargs["headers"]["x-upsert"] == "false"
        if self.uncertain:
            self.uncertain = False
            raise requests.Timeout()
        return Response(status=201)


class Response:
    def __init__(self, payload=None, content=b"", mime="image/jpeg", status=200):
        self.payload, self.content, self.status_code = payload, content, status
        self.headers = {"content-type": mime}

    def json(self):
        return self.payload


@pytest.mark.parametrize("uncertain", [False, True])
def test_publish_three_exact_objects_and_reconcile_without_retry(tmp_path, uncertain):
    journal = BoundedSession(
        tmp_path, "billing@example.invalid", "test@example.invalid", Session()
    )
    storage = Storage(uncertain=uncertain)
    Publication(journal, storage, "synthetic").publish()
    assert journal.state["upload_attempts"] == 3
    assert journal.state["storage_read_attempts"] == 5
    assert len(journal.state["published_assets"]) == 3
    assert journal.state["attempts"] == 0
    assert all(asset["verified"] for asset in journal.state["published_assets"])
    assert journal.state["started_utc"] is not None


def test_existing_object_stops_without_overwrite(tmp_path):
    journal = BoundedSession(
        tmp_path, "billing@example.invalid", "test@example.invalid", Session()
    )
    publication = Publication(journal, Storage(existing=True), "synthetic")
    with pytest.raises(ValueError, match="already exists"):
        publication.publish()
    assert journal.state["upload_attempts"] == 0
    assert journal.state["attempts"] == 0
    journal.state["storage_read_attempts"] = 12
    with pytest.raises(ValueError, match="limit"):
        publication.call("GET", "/storage/v1/bucket/email-assets")


def test_manual_continuation_preserves_original_clock_and_counters(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    journal = BoundedSession(
        Path("tmp/c12-email-redesign-01"),
        "billing@intervucopilot.in",
        "acceptance-recipient@example.invalid",
        Session(),
    )
    journal.start_window()
    journal.state.update(upload_attempts=1, storage_read_attempts=3, status="stopped")
    journal.save()
    restored = existing_journal()
    assert restored.state["started_utc"] == journal.state["started_utc"]
    assert restored.state["deadline_utc"] == journal.state["deadline_utc"]
    assert restored.state["upload_attempts"] == 1
    assert restored.state["storage_read_attempts"] == 3
    assert restored.state["attempts"] == 0
    restored.transport.close()
