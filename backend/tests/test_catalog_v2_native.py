"""Actual v2 API/pool/storage/review on task-owned native PostgreSQL only."""
import argparse
import copy
import json
import sys
from pathlib import Path
from uuid import uuid4
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_lifecycle_api_native import case, install, write_headers
from test_draft_service_native import database
from test_review_service_native import install as f1_install
from test_lifecycle_service_native import install as f2_install
from test_catalog_store_native import ROOT, MANAGER, ORDINARY, literal
from test_draft_api_native import create, headers, path
from test_catalog_v2 import free
from test_catalog_contract import document

@pytest.fixture
def upgraded(case):
    db,client,_,app,state=case
    # Per disposable database only; migrations need run only once.
    if not db.rows("select 1 from pg_constraint where conname='catalog_review_version_triple'"):
        historical=db.rows('select offer_version_id,canonical_json,fingerprint from catalog_offer_versions order by offer_version_id')
        for name in ['20261023120000_catalog_v2_drafts.sql','20261023130000_catalog_v2_review_binding.sql']:
            db.run((ROOT/'supabase/migrations'/name).read_text())
        assert db.rows('select offer_version_id,canonical_json,fingerprint from catalog_offer_versions order by offer_version_id')==historical
    return db,client,app,state

def test_roundtrip_authority_revision_and_durable_retry(upgraded):
    db,client,app,state=upgraded;raw=free();raw['plan']['code']='synthetic-'+uuid4().hex
    key=str(uuid4());response=create(client,raw,key);assert response.status_code==200,response.text
    saved=response.json();assert saved['terms']['allowances']==raw['terms']['allowances']
    assert saved['terms']['presentation']==raw['terms']['presentation']
    assert create(client,raw,key).json()==saved
    changed=copy.deepcopy(raw);changed['terms']['name']='Conflict'
    assert create(client,changed,key).status_code==409
    assert client.get(path(raw),headers=headers(ORDINARY)).status_code==403
    assert client.get(path(raw),headers=headers()).json()==saved
    saved['revision']='2';saved['terms']['presentation'][0]['label']='Synthetic Sketch'
    edited=client.patch(path(raw),json={'document':saved,'reason':'synthetic edit'},headers=write_headers())
    assert edited.status_code==200,edited.text
    assert client.patch(path(raw),json={'document':saved,'reason':'other stale edit'},headers=write_headers()).status_code==409
    db.run(f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)}")
    assert create(client,raw,key).status_code==403
    assert client.get(path(raw),headers=headers()).status_code==403
    db.run(f"update subscription_admin_permissions set active=true,revision=revision+1 where subject_id={literal(MANAGER)}")
    assert client.get(path(raw),headers=headers()).json()['terms']['presentation'][0]['label']=='Synthetic Sketch'

def test_new_review_binds_v2_and_invalidates_on_metadata_change(upgraded):
    db,client,app,state=upgraded;raw=free();raw['plan']['code']='synthetic-'+uuid4().hex
    legacy=document();raw['terms'].update(pricing_mode='priced',prices=legacy['terms']['prices'],subscription_policy_ref='synthetic.lifecycle',migration_policy_ref='synthetic.migration')
    raw['terms']['limits'][0]['policy_ref']='synthetic.storage'
    assert create(client,raw).status_code==200
    b=client.post(path(raw)+'/preview',json={'scope':'publication_review','expected_revision':'1','contract_version':'catalog.v2','intent':{'action':'publish','valid_from':'2026-01-01T00:00:00Z'}},headers=headers())
    assert b.status_code==200,b.text
    basis=b.json()['basis'];assert basis['contract_version']=='catalog.v2' and basis['validation_policy_version']=='catalog.validation.v2'
    r=client.post(path(raw)+'/publication-reviews',json={'basis':basis,'confirmed':True,'reason':'synthetic v2 review'},headers=write_headers())
    assert r.status_code==200,r.text
    rid=r.json()['receipt']['review_id']
    saved=client.get(path(raw),headers=headers()).json();saved['revision']='2';saved['terms']['presentation'][0]['information']='Changed reviewed copy'
    assert client.patch(path(raw),json={'document':saved,'reason':'synthetic metadata edit'},headers=write_headers()).status_code==200
    read=client.get('/api/admin/catalog/publication-reviews/'+rid,headers=headers())
    assert read.status_code==200 and read.json()['state']=='draft_changed'
    rejected=client.post(path(raw)+'/publish',json={'review_id':rid,'reason':'synthetic stale attempt'},headers=write_headers())
    assert rejected.status_code==409,rejected.text
    assert db.rows('select count(*) as n from catalog_publications')[0]['n']==0

def test_corrupt_v2_read_fails_safely_and_invalid_payload_writes_nothing(upgraded):
    db,client,app,state=upgraded;raw=free();raw['plan']['code']='synthetic-'+uuid4().hex
    before=db.rows('select count(*) as n from catalog_drafts')[0]['n']
    bad=copy.deepcopy(raw);bad['terms']['allowances'][4]['amount']='1.5'
    assert create(client,bad).status_code==400
    assert db.rows('select count(*) as n from catalog_drafts')[0]['n']==before
    assert create(client,raw).status_code==200
    # Disposable schema owner fault injection only. Ordinary application roles
    # cannot disable guards or mutate these tables.
    def inject(value):
        db.run(f"begin;alter table catalog_drafts disable trigger user;update catalog_drafts set document=jsonb_set(document,'{{terms,model_selection}}',{literal(json.dumps(value))}) where draft_id={literal(raw['draft_id'])};alter table catalog_drafts enable trigger user;commit;")
    try:
        inject('unsupported_future_selector')
        response=client.get(path(raw),headers=headers())
        assert response.status_code==503 and response.json()['detail']['code']=='catalog_stored_version_invalid'
        assert 'unsupported_future_selector' not in response.text
    finally:
        inject('configured_supported_available')

def test_synthetic_free_snapshot_roundtrip_without_currency(upgraded):
    db,client,app,state=upgraded;raw=free();raw['plan']['code']='synthetic-'+uuid4().hex
    raw['terms'].update(subscription_policy_ref='synthetic.lifecycle',migration_policy_ref='synthetic.migration')
    raw['terms']['limits'][0]['policy_ref']='synthetic.storage'
    assert create(client,raw).status_code==200
    response=client.post(path(raw)+'/preview',json={'scope':'publication_review','expected_revision':'1','contract_version':'catalog.v2','intent':{'action':'publish','valid_from':'2026-01-01T00:00:00Z'}},headers=headers())
    assert response.status_code==200,response.text
    review=client.post(path(raw)+'/publication-reviews',json={'basis':response.json()['basis'],'confirmed':True,'reason':'synthetic no-currency review'},headers=write_headers())
    assert review.status_code==200,review.text
    published=client.post(path(raw)+'/publish',json={'review_id':review.json()['receipt']['review_id'],'reason':'synthetic local snapshot test'},headers=write_headers())
    assert published.status_code==200,published.text
    offer=client.get('/api/admin/catalog/offers/'+published.json()['receipt']['offer_version_id'],headers=headers())
    assert offer.status_code==200,offer.text
    snapshot=offer.json()['snapshot'];assert snapshot['contract_version']=='catalog.v2'
    assert snapshot['terms']['pricing_mode']=='free' and snapshot['terms']['prices']==[]
    assert snapshot['terms']['presentation']==raw['terms']['presentation']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True);args=parser.parse_args()
    class Options:
        def pytest_addoption(self,parser):parser.addoption('--catalog-pg-bin',default=args.pg_bin)
    raise SystemExit(pytest.main([__file__,'-q','-s','-p','no:cacheprovider','--tb=short'],plugins=[Options()]))
