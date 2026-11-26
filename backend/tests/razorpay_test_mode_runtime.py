"""Explicit C12 session; fixture infrastructure is local, provider transport is real."""

import json
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import test_billing_native as fixtures
from app.commercial.billing_database import BillingDatabase
from app.commercial.razorpay import PaymentUnavailable, RazorpaySubscriptions
from fastapi.testclient import TestClient
from razorpay_session_budget import SessionBudget

from scripts import c12_webhook_gateway as gateway

billing = fixtures.billing
integration = fixtures.integration
usage = fixtures.usage
pricing = fixtures.pricing
case = fixtures.case
database = fixtures.database
upgraded = fixtures.upgraded
install = fixtures.install
f1_install = fixtures.f1_install
f2_install = fixtures.f2_install


def preflight(u, directory):
    budget = SessionBudget(directory)
    state = budget.load()
    if state["start_utc"] is not None:
        assert (
            state.get("authentication_retry_used")
            and state["status"] == "running"
            and datetime.now(timezone.utc)
            < datetime.fromisoformat(state["deadline_utc"])
        ), "Existing external session must be reconciled, never restarted"
    for port in (8120, 8121, 5273):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    assert u["db"].directory.name.startswith("c112d-disposable-")
    assert u["db"].rows(
        "select host(inet_server_addr()) as address,inet_server_port() as port"
    )[0] == {"address": "127.0.0.1", "port": u["db"].port}
    connection = u["connect"]("usage_binding_executor")
    try:
        BillingDatabase.check(connection)
    finally:
        connection.close()
    with pytest.raises(PaymentUnavailable):
        RazorpaySubscriptions("rzp_live_synthetic", "synthetic")
    assert (
        u["client"]
        .post(
            "/api/billing/webhook",
            content=b"{}",
            headers={"x-razorpay-signature": "0" * 64},
        )
        .status_code
        == 503
    )
    assert u["provider"].calls == 0
    forwarded = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            forwarded.append(
                (self.path, self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 8120), Upstream)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    previous_port = gateway.UPSTREAM_PORT
    gateway.UPSTREAM_PORT = 8120
    try:
        with TestClient(gateway.app) as client:
            for path in (
                "/",
                "/docs",
                "/openapi.json",
                "/api/account/subscription",
                gateway.PATH + "/",
            ):
                assert client.post(path, follow_redirects=False).status_code == 404
            assert client.get(gateway.PATH).status_code == 405
            assert client.post(gateway.PATH, content=b"{}").status_code == 400
            assert (
                client.post(
                    gateway.PATH,
                    content=b'{ "exact": true }\n',
                    headers={"X-Razorpay-Signature": "a" * 64},
                ).status_code
                == 400
            )
            assert forwarded == [(gateway.PATH, b'{ "exact": true }\n')]
    finally:
        gateway.UPSTREAM_PORT = previous_port
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=2)
    manifest = {
        "status": "local_preflight_passed",
        "database_directory": str(u["db"].directory),
        "database_port": u["db"].port,
        "database_host": "127.0.0.1",
        "billing_role": "usage_binding_executor",
        "auth_issuer": "https://synthetic.invalid/auth/v1",
        "backend_port": 8120,
        "gateway_port": 8121,
        "website_port": 5273,
        "gateway_default_upstream": gateway.UPSTREAM_PORT,
        "migrations": [
            "20261025020000_razorpay_checkout.sql",
            "20261025030000_billing_gst_payable.sql",
        ],
        "provider_calls": 0,
        "actual_loopback_gateway_checked": True,
        "normal_services_modified": False,
    }
    (directory / "preflight.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
