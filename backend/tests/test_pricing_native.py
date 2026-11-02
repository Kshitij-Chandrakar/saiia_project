"""C11.4 real JWT/API/pool/policy/native PostgreSQL acceptance. Synthetic only."""
import argparse
import copy
import json
import sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_catalog_v2_native import upgraded
from test_lifecycle_api_native import case,install,write_headers
from test_draft_service_native import database
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install
from test_catalog_store_native import ROOT,MANAGER,ORDINARY,literal
from test_draft_api_native import headers,create,path
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.publication_policy import resolve_policy

@pytest.fixture
def pricing(upgraded):
    db,client,app,state=upgraded
    if not db.rows("select 1 from pg_tables where tablename='catalog_publication_policies'"):
        for name in ['20261023140000_catalog_v3_terms.sql','20261023150000_catalog_policy_public_read.sql']:
            import subprocess
            sql=(ROOT/'supabase/migrations'/name).read_text()
            diagnostic=subprocess.run([*db.args,'-v','VERBOSITY=default'],input=sql,encoding='utf-8',capture_output=True,env=db.env,timeout=25)
            assert diagnostic.returncode==0, name+': '+diagnostic.stderr
        db.run('alter role catalog_public_reader login') # Synthetic disposable provisioning only.
        now=datetime.now(timezone.utc)
        policy=dict(version='1',reviewer_rule_ref='current_subscription_admin',model_registry_version='synthetic.models.v1',valid_from=(now-timedelta(days=1)).isoformat(),valid_until=(now+timedelta(days=1)).isoformat(),allowed_refs=['synthetic.lifecycle','synthetic.migration','synthetic.storage','synthetic.tax','synthetic.rounding'])
        db.run(f"insert into catalog_publication_policies values ('{uuid4()}','synthetic.lifecycle','synthetic.migration',1,true,{literal(json.dumps(policy))})")
    app.state.catalog_drafts._lifecycle._resolver=resolve_policy
    public=CatalogDatabase('true',f'host=127.0.0.1 port={db.port} dbname=postgres user=catalog_public_reader sslmode=disable',public_only=True)
    public.start();assert public._pool is not None
    app.state.catalog_public=public
    try: yield db,client,app,state
    finally: public.close()

def definition(code,complete=True):
    t=json.loads((ROOT/f'frontend/src/auth/approved{code.title()}Terms.json').read_text())
    for p in t['prices']: p['price_id']=str(uuid4())
    if complete:
        t.update(subscription_policy_ref='synthetic.lifecycle',migration_policy_ref='synthetic.migration')
        for l in t['limits']:l['policy_ref']='synthetic.storage'
        for p in t['prices']:p.update(tax_policy_ref='synthetic.tax',rounding_policy_ref='synthetic.rounding')
    version='2' if code=='free' else '3'
    return dict(draft_id=str(uuid4()),plan=dict(plan_id=str(uuid4()),code='synthetic-'+uuid4().hex),revision='1',state='draft',contract_version='catalog.v'+version,registry_version='catalog.features.v'+version,terms=t,internal_notes='PRIVATE NEVER PUBLIC')

def publish(client,raw,action='publish'):
    response=client.post(path(raw)+'/preview',json=dict(scope='publication_review',expected_revision=raw['revision'],contract_version=raw['contract_version'],intent=dict(action=action,valid_from='2026-01-01T00:00:00Z')),headers=headers())
    assert response.status_code==200,response.text
    basis=response.json()['basis']
    r=client.post(path(raw)+'/publication-reviews',json=dict(basis=basis,confirmed=True,reason='Synthetic pricing review'),headers=write_headers(revision=raw['revision']))
    assert r.status_code==200,r.text
    body=dict(review_id=r.json()['receipt']['review_id'],reason='Synthetic pricing publication')
    if action=='replace':body['predecessor']=basis['current_offer']
    key=str(uuid4());h=write_headers(key=key,revision=raw['revision'])
    p=client.post(path(raw)+'/'+action,json=body,headers=h)
    assert p.status_code==200,p.text
    replay=client.post(path(raw)+'/'+action,json=body,headers=h)
    assert replay.status_code==200 and replay.json()['receipt']==p.json()['receipt']
    return p.json()

def test_policy_public_projection_replace_retire_and_security(pricing):
    db,client,app,state=pricing
    empty=client.get('/api/catalog');assert empty.status_code==200 and empty.json()['offers']==[]
    raw=definition('plus',False)
    assert create(client,raw).status_code==200
    assert client.get('/api/catalog').json()['offers']==[]
    incomplete=client.post(path(raw)+'/preview',json=dict(scope='publication_review',expected_revision='1',contract_version='catalog.v3',intent=dict(action='publish',valid_from='2026-01-01T00:00:00Z')),headers=headers())
    assert incomplete.status_code==503 # No authoritative policy mapping.
    saved=client.get(path(raw),headers=headers()).json();saved['revision']='2'
    complete=definition('plus')['terms'];complete['prices']=saved['terms']['prices']
    for p in complete['prices']:p.update(tax_policy_ref='synthetic.tax',rounding_policy_ref='synthetic.rounding')
    saved['terms']=complete
    edited=client.patch(path(raw),json=dict(document=saved,reason='Synthetic complete policies'),headers=write_headers())
    assert edited.status_code==200,edited.text
    raw=edited.json();result=publish(client,raw)
    first=client.get('/api/catalog');assert first.status_code==200,first.text
    offer=first.json()['offers'][0];assert offer['prices'][0]['currency']=='INR'
    assert sorted(p['amount_minor'] for p in offer['prices'])==['299900','39900']
    expected = next(a for a in definition('plus')['terms']['allowances'] if a['meter'] == 'auto.authorized_running')
    actual = next(a for a in offer['allowances'] if a['meter'] == expected['meter'])
    assert actual['mode'] == expected['mode'] == 'limited'
    assert actual['amount'] == expected['amount'] == '18000'
    assert offer['service_benefits'][0]['availability']=='coming_soon'
    assert 'PRIVATE' not in first.text and 'synthetic.tax' not in first.text and 'subscription_policy_ref' not in first.text
    assert first.headers['cache-control']=='no-store' and offer['purchasable'] is False
    old=db.rows("select canonical_json,fingerprint from catalog_offer_versions where offer_version_id="+literal(result["receipt"]["offer_version_id"]))
    successor=copy.deepcopy(raw);successor.update(draft_id=str(uuid4()),revision='1',state='draft');successor['terms']['name']='Plus replacement'
    for p in successor['terms']['prices']:p['price_id']=str(uuid4())
    assert create(client,successor).status_code==200
    replaced=publish(client,successor,'replace')
    after=client.get('/api/catalog').json();assert int(after['catalog_revision'])>int(first.json()['catalog_revision'])
    assert [o['name'] for o in after['offers']]==['Plus replacement']
    assert db.rows("select canonical_json,fingerprint from catalog_offer_versions where offer_version_id="+literal(result['receipt']['offer_version_id']))==[old[0]]
    rid=replaced['receipt']['offer_version_id']
    retired=client.post('/api/admin/catalog/offers/'+rid+'/retire',json=dict(reason='Synthetic retirement'),headers=write_headers(revision=replaced['current']['revision']))
    assert retired.status_code==200,retired.text
    assert client.get('/api/catalog').json()['offers']==[]
    for verb,url in [('POST','/api/catalog'),('GET','/api/catalog/'),('GET','/api/%63atalog')]:
        assert client.request(verb,url).status_code!=200
    conn=app.state.catalog_public.connect()
    try:
        with pytest.raises(Exception):conn.execute('update public.catalog_public_state set revision=revision+1')
    finally:conn.rollback();conn.close()
    db.run(f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)}")
    assert client.get(path(raw),headers=headers()).status_code==403
    assert client.get('/api/catalog').status_code==200
    db.run(f"update subscription_admin_permissions set active=true,revision=revision+1 where subject_id={literal(MANAGER)}")

def test_pro_save_read_and_unavailable_public(pricing):
    db,client,app,state=pricing;raw=definition('pro');r=create(client,raw);assert r.status_code==200,r.text
    read=client.get(path(raw),headers=headers()).json();assert read['terms']['storage_allowances'][0]['mode']=='unlimited'
    assert next(a for a in read['terms']['allowances'] if a['meter']=='clipboard.new_saves')['mode']=='unlimited'
    assert client.get(path(raw),headers=headers(ORDINARY)).status_code==403
    public=app.state.catalog_public;public.close();unavailable=client.get('/api/catalog');assert unavailable.status_code==503 and unavailable.json()=={'detail':{'code':'catalog_unavailable'}}


def test_policy_lock_revocation_and_failed_approval_are_authoritative(pricing):
    import psycopg
    db,client,app,state=pricing
    raw=definition('pro');assert create(client,raw).status_code==200
    conn=app.state.catalog_drafts.connect()
    try:
        # Function holds the current grant and policy rows until this transaction
        # completes. A separate owner connection cannot revoke during that order.
        resolved=conn.execute("select public.catalog_policy_resolve(%s,%s,%s)",(MANAGER,'synthetic.lifecycle','synthetic.migration')).fetchone()[0]
        assert resolved['approval_revision']=='1'
        with psycopg.connect(host='127.0.0.1',port=db.port,dbname='postgres',user='catalog_test_owner') as other:
            other.execute("set local lock_timeout='100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute("update catalog_publication_policies set active=false,revision=revision+1")
        conn.commit()
    finally:conn.rollback();conn.close()
    db.run("update catalog_publication_policies set active=false,revision=revision+1")
    unavailable=client.post(path(raw)+'/preview',json=dict(scope='publication_review',expected_revision='1',contract_version='catalog.v3',intent=dict(action='publish',valid_from='2026-01-01T00:00:00Z')),headers=headers())
    assert unavailable.status_code==503
    db.run("update catalog_publication_policies set active=true,revision=revision+1")
    with pytest.raises(Exception):db.run("update catalog_publication_policies set active=false")
    conn=app.state.catalog_public.connect()
    try:
        with pytest.raises(Exception):conn.execute("select public.catalog_policy_resolve(%s,%s,%s)",(MANAGER,'synthetic.lifecycle','synthetic.migration'))
    finally:conn.rollback();conn.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True);args=parser.parse_args()
    class Options:
        def pytest_addoption(self,parser):parser.addoption('--catalog-pg-bin',default=args.pg_bin)
    raise SystemExit(pytest.main([__file__,'-q','-s','-p','no:cacheprovider','--tb=short'],plugins=[Options()]))
