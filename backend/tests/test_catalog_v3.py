import copy,json
from pathlib import Path
from uuid import uuid4
import pytest
from app.commercial import catalog_contract as c
from test_catalog_v2 import free
ROOT=Path(__file__).resolve().parents[2]
def paid(code):
    d=free();d.update(contract_version='catalog.v3',registry_version='catalog.features.v3')
    d['terms']=json.loads((ROOT/f'frontend/src/auth/approved{code}Terms.json').read_text())
    for p in d['terms']['prices']:p['price_id']=str(uuid4())
    return d

@pytest.mark.parametrize('code,prices,clipboard,storage',[('Plus',['39900','299900'],'10','limited'),('Pro',['89900','649900'],None,'unlimited')])
def test_approved_prices_periods_and_semantics(code,prices,clipboard,storage):
    d=paid(code);r=c.validate_draft(d);assert r.valid
    assert [p['amount_minor'] for p in d['terms']['prices']]==prices
    assert d['terms']['storage_allowances'][0]['mode']==storage
    allowances={a['meter']:a for a in d['terms']['allowances']}
    assert allowances['clipboard.new_saves']['amount']==clipboard
    if code=='Plus':
        assert allowances['auto.authorized_running']['amount']=='18000'
        assert allowances['auto.authorized_running']['period']==dict(unit='month',anchor='account_signup_day',timezone='Asia/Kolkata')
    else:assert allowances['auto.authorized_running']['mode']=='unlimited'
    assert d['terms']['service_benefits'][0]['availability']=='coming_soon'
    assert all(e['allowed'] for e in d['terms']['entitlements'] if e['feature'] in ['sketch.generate','screen.followups'])
    assert d['terms']['discounts']==[]

def test_v3_versions_contradictions_and_fingerprint_binding():
    d=paid('Pro');base=c.terms_fingerprint(c.CatalogDraft.model_validate(d).terms)
    changed=copy.deepcopy(d);changed['terms']['service_benefits'][0]['label']='Different support'
    assert c.terms_fingerprint(c.CatalogDraft.model_validate(changed).terms)!=base
    for mutate in [lambda x:x.update(contract_version='catalog.v2'),lambda x:x['terms']['storage_allowances'][0].update(amount='0'),lambda x:x['terms']['service_benefits'][0].update(availability='operational')]:
        bad=copy.deepcopy(d);mutate(bad);assert not c.validate_draft(bad).valid
    bad=copy.deepcopy(d);bad['terms']['storage_allowances'].append(bad['terms']['storage_allowances'][0]);assert not c.validate_draft(bad).valid

def test_registry_and_free_compatibility():
    registry=json.loads((ROOT/'frontend/src/auth/catalogRegistryV3.json').read_text())
    assert set(registry['features'])==set(c.V3_FEATURES)
    assert c.validate_draft(free()).draft.contract_version=='catalog.v2'
    assert not c.validate_draft(dict(paid('Plus'),contract_version='catalog.v4')).valid
