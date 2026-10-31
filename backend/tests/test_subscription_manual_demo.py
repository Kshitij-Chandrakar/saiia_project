"""Opt-in, loopback-only manual demo. Reuses disposable native acceptance fixtures.
No remote DSN is accepted. No changes to normal application authentication.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_pricing_native import pricing
from test_catalog_v2_native import upgraded
from test_lifecycle_api_native import case, install
from test_draft_service_native import database, actor
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install
from test_catalog_store_native import ROOT, MANAGER, ORDINARY, literal
from app.auth import supabase_auth as auth
from app.commercial import admin, admin_access

BASE='http://127.0.0.1:5187'

def test_manual_demo(pricing,monkeypatch):
    db,client,app,state=pricing
    # Native() created this directory/loopback cluster, never a supplied DSN.
    assert db.directory.name.startswith('c112d-disposable-')
    connection=app.state.catalog_drafts.connect()
    try:
        actual=connection.execute('select host(inet_server_addr()),inet_server_port(),current_user').fetchone()
        assert actual==('127.0.0.1',db.port,'catalog_draft_executor')
    finally:connection.rollback();connection.close()
    # Accepted F2 migration fixtures include two hidden/retired legacy archives.
    baseline_plans=db.rows('select code from catalog_plans')
    assert all(row['code'].startswith('legacy-') for row in baseline_plans)
    assert client.get('/api/catalog').json()['offers']==[]
    baseline_publications=db.rows('select count(*) as n from catalog_publications')[0]['n']

    def factory(verified):
        def rpc(name,params):
            user=auth.verify_supabase_token(verified._bearer)
            assert name==admin_access.PROBE_RPC and params=={}
            output=db.run("begin read only;set session authorization authenticator;set role authenticated;"
                +"select set_config('request.jwt.claim.sub',"+literal(user.user_id)+",true);"
                +"select jsonb_build_object('result',public.subscription_admin_self_probe());commit;")
            return json.loads(output.strip().splitlines()[-1])['result']
        return rpc
    monkeypatch.setattr(admin,'probe_transport',factory)
    class Bridge(BaseHTTPRequestHandler):
        def log_message(self,*args):pass # No request headers, cookies or tokens.
        def reply(self,status,body,kind='application/json',extra=()):
            payload=body.encode()
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store')
            for k,v in extra:self.send_header(k,v)
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers();self.wfile.write(payload)
        def dispatch(self):
            route=self.path.split('?')[0]
            if route in ('/__demo/as/admin','/__demo/as/ordinary','/__demo/logout'):
                role=route.rsplit('/',1)[-1]
                if role=='logout':role='none'
                return self.reply(303,'',extra=[('Location','/auth/admin/subscriptions'),('Set-Cookie',f'isolated_demo_role={role}; HttpOnly; SameSite=Strict; Path=/')])
            if route=='/__demo/session':
                cookies=self.headers.get('Cookie','').split('; ')
                role='admin' if 'isolated_demo_role=admin' in cookies else 'ordinary' if 'isolated_demo_role=ordinary' in cookies else None
                subject=MANAGER if role=='admin' else ORDINARY
                session=None if not role else {'access_token':actor(subject)._bearer,'user':{'id':subject}}
                return self.reply(200,json.dumps({'session':session}))
            if route=='/__demo':
                return self.reply(200,'<title>Isolated demo</title><main style="max-width:850px;margin:60px auto;font:18px/1.6 system-ui"><h1>Isolated demo</h1><p>Disposable local PostgreSQL. Synthetic identities only. No checkout, payments or AI calls.</p><p><a href="/__demo/as/admin">Enter as synthetic admin</a></p><p><a href="/__demo/as/ordinary">Enter as ordinary synthetic user (404 expected)</a></p><p><a href="/#pricing">Open published pricing</a></p><p>Admin imports stay unsaved until Save. Use a unique test Plan code. Approved test policy references: Subscription policy: <code>synthetic.lifecycle</code>; Subscriber migration policy: <code>synthetic.migration</code>; storage: <code>synthetic.storage</code>; price Tax/Rounding: <code>synthetic.tax</code> / <code>synthetic.rounding</code>. These values exist only in this disposable database.</p><p><a href="/__demo/results">View safe demo IDs/results</a></p></main>','text/html')
            if route=='/__demo/results':
                result=ROOT/'tmp/subscription-demo-results.json'
                return self.reply(200,result.read_text() if result.exists() else '{"state":"verification running"}')
            # Never expose AI, payment, account or unrelated application routes.
            if not (route=='/api/catalog' or route=='/api/commercial/admin/me' or route.startswith('/api/admin/catalog/')):
                return self.reply(404,'{"detail":"Not found"}')
            length=int(self.headers.get('Content-Length','0'))
            if length>262144:return self.reply(413,'{"detail":"Too large"}')
            response=client.request(self.command,self.path,content=self.rfile.read(length),headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','cookie'}})
            self.reply(response.status_code,response.text,extra=[(k,v) for k,v in response.headers.items() if k.lower() in {'etag','pragma','vary','www-authenticate'}])
        do_GET=dispatch
        do_POST=dispatch
        do_PATCH=dispatch
        do_DELETE=dispatch

    server=ThreadingHTTPServer(('127.0.0.1',0),Bridge)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    stop=ROOT/'tmp/subscription-demo.stop'
    initial=stop.stat().st_mtime_ns if stop.exists() else None
    env={**os.environ,'SUBSCRIPTION_DEMO_BRIDGE':f'http://127.0.0.1:{server.server_port}'}
    log=(ROOT/'tmp/subscription-demo-vite.log').open('w')
    vite=None
    try:
        vite=subprocess.Popen(['cmd','/c','npx','vite','--config','tests/catalog/demo.vite.config.js'],cwd=ROOT/'frontend',env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        result=subprocess.run(['node','tests/catalog/demo.verify.mjs'],cwd=ROOT/'frontend',env=env,timeout=240,check=False)
        assert result.returncode==0,'Demo browser acceptance failed'
        offers=client.get('/api/catalog').json()['offers']
        assert sorted(o['name'] for o in offers)==['Free','Plus','Pro']
        assert all(not o['purchasable'] for o in offers)
        # Every fixture write is visible in this newly-created native cluster.
        assert db.rows('select count(*) as n from catalog_plans')[0]['n']==len(baseline_plans)+4
        assert db.rows('select count(*) as n from catalog_publications')[0]['n']==baseline_publications+5
        assert client.post('/api/generate').status_code!=200
        print('ISOLATED DEMO VERIFIED: '+BASE+'/__demo',flush=True)
        print('Task-owned PostgreSQL 17 cluster; restricted application roles; no shared connection.',flush=True)
        (ROOT/'tmp/subscription-demo.ready').write_text(json.dumps({'url':BASE,'pid':os.getpid(),'database':'task-owned disposable native PostgreSQL','verified':True}))
        deadline=time.monotonic()+8*60*60
        while time.monotonic()<deadline:
            if vite.poll() is not None:raise RuntimeError('Demo frontend stopped')
            if stop.exists() and stop.stat().st_mtime_ns!=initial:break
            threading.Event().wait(.5)
    finally:
        if vite is not None:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],capture_output=True,check=False)
        log.close();server.shutdown();server.server_close();thread.join(timeout=5)
        (ROOT/'tmp/subscription-demo.ready').unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True);args=parser.parse_args()
    class Options:
        def pytest_addoption(self,parser):parser.addoption('--catalog-pg-bin',default=args.pg_bin)
    raise SystemExit(pytest.main([__file__,'-q','-s','-p','no:cacheprovider','--tb=short'],plugins=[Options()]))
