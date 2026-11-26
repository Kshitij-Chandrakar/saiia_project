"""Explicit local public-only catalog process; no shared DSN or synthetic login API."""
import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_pricing_native import pricing, definition, publish
from test_catalog_v2_native import upgraded
from test_lifecycle_api_native import case, install
from test_draft_service_native import database
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install
from test_catalog_store_native import ROOT
from test_draft_api_native import create


@pytest.mark.skipif(os.environ.get("CATALOG_MANUAL_WORKBENCH") != "true",
                    reason="Manual catalog preview requires CATALOG_MANUAL_WORKBENCH=true")
def test_local_catalog_preview(pricing):
    db, client, app, _ = pricing
    assert db.directory.name.startswith('c112d-disposable-')
    conn = app.state.catalog_public.connect()
    try:
        assert conn.execute('select host(inet_server_addr()),inet_server_port(),current_user').fetchone() == ('127.0.0.1', db.port, 'catalog_public_reader')
    finally:
        conn.rollback()
        conn.close()
    assert client.get('/api/catalog').json()['offers'] == []
    for code in ('free', 'plus', 'pro'):
        raw = definition(code)
        raw['plan']['code'] = 'local-preview-' + code
        assert create(client, raw).status_code == 200
        publish(client, raw)
    result = client.get('/api/catalog')
    assert result.status_code == 200
    assert sorted(o['name'] for o in result.json()['offers']) == ['Free', 'Plus', 'Pro']
    assert all(not o['purchasable'] for o in result.json()['offers'])

    class PublicOnly(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            # No caller headers, cookies, identity, admin routes or write methods forwarded.
            if self.command == 'GET' and self.path == '/api/catalog':
                response = client.get('/api/catalog')
                status, body = response.status_code, response.content
            else:
                status, body = 404, b'{"detail":{"code":"not_found"}}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = dispatch
        do_POST = dispatch
        do_PATCH = dispatch
        do_DELETE = dispatch
        do_PUT = dispatch
        do_OPTIONS = dispatch

    server = ThreadingHTTPServer(('127.0.0.1', 5188), PublicOnly)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stop = ROOT / 'tmp/catalog-preview.stop'
    initial = stop.stat().st_mtime_ns if stop.exists() else None
    ready = ROOT / 'tmp/catalog-preview.ready'
    try:
        ready.write_text(json.dumps({'pid': os.getpid(), 'port': 5188, 'postgres_port': db.port, 'synthetic': True}))
        print('LOCAL CATALOG READY: http://localhost:5173/#pricing; public-only disposable storage; checkout disabled', flush=True)
        while not stop.exists() or stop.stat().st_mtime_ns == initial:
            threading.Event().wait(.5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        ready.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg-bin', required=True)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption('--catalog-pg-bin', default=args.pg_bin)

    raise SystemExit(pytest.main([__file__, '-q', '-s', '-p', 'no:cacheprovider', '--tb=short'], plugins=[Options()]))
