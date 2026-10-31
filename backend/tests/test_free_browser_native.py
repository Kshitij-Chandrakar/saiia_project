"""C11.3D browser -> loopback TestClient bridge -> real JWT/service/native SQL.
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
from test_catalog_store_native import ROOT, literal
from test_draft_api_native import case as case  # noqa: PLC0414
from test_draft_api_native import database as database  # noqa: PLC0414
from test_draft_api_native import headers


def test_native_browser(case, monkeypatch):
    db, client, _raw, _app = case
    db.run((ROOT / "supabase/migrations/20261023120000_catalog_v2_drafts.sql").read_text())

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
                "free.integration.spec.js",
            ],
            cwd=ROOT / "frontend",
            env=env,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0
        rows=db.rows("select document from catalog_drafts")
        assert len(rows)==1
        doc=rows[0]["document"]
        expected=json.loads((ROOT/'frontend/src/auth/approvedFreeTerms.json').read_text())
        expected['entitlements']=sorted(expected['entitlements'],key=lambda e:e['feature'])
        for entitlement in expected['entitlements']:
            entitlement['audio_sources']=sorted(entitlement['audio_sources'])
            entitlement['model_keys']=sorted(entitlement['model_keys'])
        expected['presentation'][1]['label']='Personal Clipboard'
        assert doc['terms']==expected
        assert doc['revision']=='2'
        assert doc["contract_version"]=="catalog.v2" and doc["terms"]["allowances"][4]["amount"]=="600"
        assert doc["terms"]["presentation"][1]["label"]=="Personal Clipboard"
        assert doc["terms"]["prices"]==[]
        assert db.rows("select count(*) as n from catalog_drafts")[0]["n"] == 1
        assert db.rows(
            "select operation,count(*) as n from catalog_admin_actions where operation in ('draft.create','draft.edit') group by operation order by operation"
        ) == [
            {"operation": "draft.create", "n": 1},
            {"operation": "draft.edit", "n": 1},
        ]
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
