"""Local-only setup boundary checks; no provider, tunnel or database calls."""

import pytest
from fastapi.testclient import TestClient

from scripts import c12_webhook_gateway as gateway


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/docs",
        "/openapi.json",
        "/api/account/subscription",
        gateway.PATH + "/",
        gateway.PATH + "?x=1",
    ],
)
def test_gateway_rejects_other_paths(path):
    with TestClient(gateway.app) as client:
        assert client.post(path, follow_redirects=False).status_code == 404


def test_gateway_preserves_raw_bytes_and_never_acknowledges_failure(monkeypatch):
    raw = b'{ "signed": true }\n'
    calls = []

    def forward(body, signature):
        calls.append((body, signature))
        return 503

    monkeypatch.setattr(gateway, "forward", forward)
    with TestClient(gateway.app) as client:
        assert client.get(gateway.PATH).status_code == 405
        assert client.post(gateway.PATH, content=raw).status_code == 400
        response = client.post(
            gateway.PATH, content=raw, headers={"X-Razorpay-Signature": "a" * 64}
        )
        assert response.status_code == 503 and "received" not in response.json()
        assert calls == [(raw, "a" * 64)]
        assert (
            client.post(
                gateway.PATH,
                content=b"x" * (gateway.LIMIT + 1),
                headers={"X-Razorpay-Signature": "a" * 64},
            ).status_code
            == 413
        )
        assert len(calls) == 1


def test_forward_fixed_loopback_destination_and_response(monkeypatch):
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def request(self, *args, **kwargs):
            calls.append((args, kwargs))

        def getresponse(self):
            return type("Response", (), {"status": 200})()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", Connection)
    assert gateway.forward(b"raw", "b" * 64) == 200
    assert calls[0] == (("127.0.0.1", 8000), {"timeout": 30})
    assert calls[1][0] == ("POST", gateway.PATH)
    assert calls[1][1]["body"] == b"raw" and calls[-1] == "closed"
