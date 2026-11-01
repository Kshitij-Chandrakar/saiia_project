"""C11.3F4 lifecycle browser -> loopback TestClient bridge -> real JWT/service/native SQL.
Synthetic session source and probe gateway; never remote Supabase acceptance.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import supabase_auth as auth
from app.commercial import admin, admin_access
from test_catalog_store_native import ROOT, ORDINARY, literal
from test_lifecycle_api_native import case as case  # noqa: PLC0414
from test_draft_service_native import database as database  # noqa: PLC0414
from test_draft_api_native import headers, create
from test_lifecycle_api_native import install as install
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install


def test_native_browser(case, monkeypatch):
    db, client, raw, _app, _state = case
    assert create(client, raw).status_code == 200
    before = db.rows("select count(*) as n from catalog_publications")[0]["n"]

    def factory(actor):
        def rpc(name, params):
            user = auth.verify_supabase_token(actor._bearer)
            assert name == admin_access.PROBE_RPC and params == {}
            result = db.run(
                "begin read only;set session authorization authenticator;set role authenticated;"
                + "select set_config('request.jwt.claim.sub',"
                + literal(user.user_id)
                + ",true);"
                + "select jsonb_build_object('result',public."
                + name
                + "());commit;"
            )
            return json.loads(result.strip().splitlines()[-1])["result"]

        return rpc

    monkeypatch.setattr(admin, "probe_transport", factory)

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            response = client.request(
                self.command,
                self.path,
                content=body,
                headers={
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in {"host", "content-length", "connection"}
                },
            )
            self.send_response(response.status_code)
            for k, v in response.headers.items():
                if k.lower() not in {"content-length", "connection"}:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        do_GET = dispatch
        do_POST = dispatch
        do_PATCH = dispatch

    server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(
            os.environ,
            CATALOG_BROWSER_NATIVE=json.dumps(
                {
                    "url": f"http://127.0.0.1:{server.server_port}",
                    "token": headers()["Authorization"][7:],
                    "ordinary_token": headers(ORDINARY)["Authorization"][7:],
                    "ordinary_subject": ORDINARY,
                    "draft_id": raw["draft_id"],
                }
            ),
        )
        result = subprocess.run(
            [
                "cmd",
                "/c",
                "npx",
                "playwright",
                "test",
                "--config",
                "playwright.catalog.config.js",
                "lifecycle.integration.spec.js",
            ],
            cwd=ROOT / "frontend",
            env=env,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0
        assert db.rows("select count(*) as n from catalog_publications")[0]["n"] == before + 2
        plan = literal(raw["plan"]["plan_id"])
        assert db.rows(f"select version,state from catalog_offer_versions o join catalog_visibility v using(offer_version_id) where o.plan_id={plan} order by version") == [
            {"version": 1, "state": "retired"}, {"version": 2, "state": "retired"}]
        assert db.rows(f"select operation,count(*) as n from catalog_admin_actions where resource_id in (select offer_version_id from catalog_offer_versions where plan_id={plan}) group by operation order by operation") == [
            {"operation": "offer.publish", "n": 1},
            {"operation": "offer.replace", "n": 1},
            {"operation": "offer.retire", "n": 2},
            {"operation": "snapshot.archive", "n": 2}]
        first = db.rows(f"select canonical_json::jsonb as snapshot from catalog_offer_versions where plan_id={plan} and version=1")[0]["snapshot"]
        assert first["terms"]["name"] == raw["terms"]["name"]
        assert first["terms"]["prices"][0]["price_id"] == raw["terms"]["prices"][0]["price_id"]

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )
