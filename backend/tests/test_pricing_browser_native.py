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
from test_pricing_native import pricing as pricing
from test_catalog_v2_native import upgraded as upgraded
from test_lifecycle_api_native import case as case  # noqa: PLC0414
from test_draft_service_native import database as database  # noqa: PLC0414
from test_draft_api_native import headers, create
from test_lifecycle_api_native import install as install
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install


def test_native_browser(pricing, monkeypatch):
    db, client, _app, _state = pricing
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
        if os.environ.get("CATALOG_MANUAL_WORKBENCH") == "1":
            from test_pricing_native import definition, publish
            for code in ("free", "plus", "pro"):
                draft = definition(code)
                draft["plan"]["code"] = code
                assert create(client, draft).status_code == 200
                publish(client, draft)
            env = dict(os.environ, CATALOG_DEV_PROXY_TARGET=f"http://127.0.0.1:{server.server_port}")
            stop = ROOT / "tmp/catalog-manual.stop"
            initial = stop.stat().st_mtime_ns if stop.exists() else None
            log = (ROOT / "tmp/catalog-manual-vite.log").open("w")
            vite = subprocess.Popen(["cmd", "/c", "npx", "vite", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],cwd=ROOT/"frontend",env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                print("Synthetic catalog ready: http://127.0.0.1:5173/#pricing ; stop: create/update tmp/catalog-manual.stop",flush=True)
                for _ in range(7200):
                    if vite.poll() is not None:
                        raise RuntimeError("Manual Vite stopped; inspect tmp/catalog-manual-vite.log")
                    if stop.exists() and stop.stat().st_mtime_ns != initial:
                        break
                    threading.Event().wait(0.5)
            finally:
                subprocess.run(["taskkill", "/PID", str(vite.pid), "/T", "/F"],capture_output=True,check=False)
                log.close()
            pytest.skip("Manual workbench session ended; automated browser assertions were not run")
        env = dict(
            os.environ,
            CATALOG_BROWSER_NATIVE=json.dumps(
                {
                    "url": f"http://127.0.0.1:{server.server_port}",
                    "token": headers()["Authorization"][7:],
                    "ordinary_token": headers(ORDINARY)["Authorization"][7:],
                    "ordinary_subject": ORDINARY,
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
                "pricing.integration.spec.js",
            ],
            cwd=ROOT / "frontend",
            env=env,
            timeout=240,
            check=False,
        )
        assert result.returncode == 0
        assert db.rows("select count(*) as n from catalog_publications")[0]["n"] == before + 4
        assert db.rows("select count(*) as n from catalog_plans where code in ('free','plus','pro')")[0]['n']==3
        assert db.rows("select count(*) as n from catalog_visibility where state='visible'")[0]['n']==2
        assert client.get('/api/catalog').status_code==200

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
