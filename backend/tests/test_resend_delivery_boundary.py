"""No network: strict verification shapes and future gateway isolation."""

import base64
import json
from datetime import datetime, timezone

import pytest
from app.email.delivery import verified_event
from fastapi.testclient import TestClient
from svix.webhooks import Webhook

from scripts import c12_resend_gateway as gateway

SECRET = "whsec_" + base64.b64encode(b"synthetic verifier-only secret").decode()


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b'{"type":"email.delivered","type":"email.failed"}',
        b'{"type":"email.delivered","created_at":null,"data":{}}',
    ],
)
def test_signed_malformed_shape(raw):
    now = datetime.now(timezone.utc)
    headers = {
        "svix-id": "msg_shape",
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": Webhook(SECRET).sign("msg_shape", now, raw.decode()),
    }
    with pytest.raises((ValueError, TypeError)):
        verified_event(raw, headers, SECRET, "synthetic")


def test_gateway_exact_route_counter_deadline_and_raw_forwarding(monkeypatch):
    monkeypatch.setattr(gateway, "attempts", 0)
    observed = []
    monkeypatch.setattr(
        gateway, "forward", lambda raw, headers: observed.append((raw, headers)) or 200
    )
    client = TestClient(gateway.app)
    headers = {
        "svix-id": "msg_raw",
        "svix-timestamp": "123",
        "svix-signature": "v1,opaque",
        "content-type": "application/json",
    }
    raw = json.dumps({"untouched": "  spacing "}).encode()
    assert client.post(gateway.PATH, content=raw, headers=headers).status_code == 200
    assert observed[0][0] == raw and observed[0][1] == headers
    for path in (
        "/docs",
        "/api/admin/billing/access",
        gateway.PATH + "/",
        gateway.PATH + "?x=1",
    ):
        assert client.post(path, content=raw, headers=headers).status_code == 404
    monkeypatch.setattr(gateway, "attempts", 12)
    assert client.post(gateway.PATH, content=raw, headers=headers).status_code == 503
    monkeypatch.setattr(gateway, "attempts", 0)
    monkeypatch.setattr(gateway, "deadline", 0)
    assert client.post(gateway.PATH, content=raw, headers=headers).status_code == 503
    assert len(observed) == 1
