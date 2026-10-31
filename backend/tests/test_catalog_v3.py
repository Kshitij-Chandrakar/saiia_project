import copy,json
from pathlib import Path
from uuid import uuid4
import pytest
from app.commercial import catalog_contract as c
from test_catalog_v2 import free
from test_catalog_contract import AT, visibility
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
    assert registry['readiness'] == {key: value.hosted_readiness for key, value in c.V3_FEATURES.items()}
    assert registry['meters'] == {key: dict(feature=value.feature, kind=value.kind, unit=value.unit) for key, value in c.V2_METERS.items()}
    assert c.validate_draft(free()).draft.contract_version=='catalog.v2'
    assert not c.validate_draft(dict(paid('Plus'),contract_version='catalog.v4')).valid


@pytest.mark.parametrize("code", ["Plus", "Pro"])
def test_v3_public_projection_preserves_storage_and_service_benefits(code):
    data = paid(code)
    data["state"] = "previewed"
    data["terms"].update(subscription_policy_ref="synthetic.lifecycle",
                         migration_policy_ref="synthetic.migration")
    for price in data["terms"]["prices"]:
        price.update(tax_policy_ref="synthetic.tax", rounding_policy_ref="synthetic.rounding")
    for limit in data["terms"]["limits"]:
        limit["policy_ref"] = "synthetic.storage"
    snapshot = c.create_snapshot(data, offer_version_id=str(uuid4()), version=1)
    assert isinstance(snapshot.terms, c.OfferTermsV3)
    assert snapshot.terms.storage_allowances and snapshot.terms.service_benefits
    public = c.public_projection(snapshot, visibility(offer_version_id=snapshot.offer_version_id), at=AT)
    assert public.contract_version == "catalog.v3"
    assert public.storage_allowances == snapshot.terms.storage_allowances
    assert public.service_benefits == snapshot.terms.service_benefits
    wire = public.model_dump(mode="json")
    expected = snapshot.terms.model_dump(mode="json")
    assert wire["storage_allowances"] == expected["storage_allowances"]
    assert wire["service_benefits"] == expected["service_benefits"]
