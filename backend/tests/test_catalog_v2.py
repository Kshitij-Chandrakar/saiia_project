import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.commercial import catalog_contract as c
from test_catalog_contract import document, snapshot, visibility, AT

def free():
    terms=json.loads((Path(__file__).resolve().parents[2]/'frontend/src/auth/approvedFreeTerms.json').read_text())
    return dict(draft_id=str(uuid4()),plan=dict(plan_id=str(uuid4()),code='free'),revision='1',state='draft',contract_version='catalog.v2',registry_version='catalog.features.v2',terms=terms)

def test_website_v2_registry_matches_domain_units_and_features():
    registry=json.loads((Path(__file__).resolve().parents[2]/'frontend/src/auth/catalogRegistryV2.json').read_text())
    assert registry['version']=='catalog.features.v2' and set(registry['features'])==set(c.V2_FEATURES)
    assert registry['readiness'] == {key: value.hosted_readiness for key, value in c.V2_FEATURES.items()}
    assert registry['meters']=={key:dict(feature=value.feature,kind=value.kind,unit=value.unit) for key,value in c.V2_METERS.items()}

def test_unverified_sketch_cannot_become_publication_ready_by_inclusion_flag():
    d=free();next(e for e in d['terms']['entitlements'] if e['feature']=='sketch.generate')['allowed']=True
    report=c.validate_draft(d)
    assert report.valid and not report.publishable
    assert any(issue.code=='capability_unverified' for issue in report.pending)

def test_approved_terms_and_explicit_unlimited_zero_missing_denied():
    d=free();r=c.validate_draft(d);assert r.valid and not r.publishable
    assert d['terms']['prices']==[]
    allowances={a['meter']:a for a in d['terms']['allowances']}
    assert allowances['answers.completed']['mode']=='unlimited'
    assert allowances['auto.authorized_running']['amount']=='600'
    assert allowances['auto.authorized_running']['period']==dict(unit='day',anchor='calendar',timezone='Asia/Kolkata')
    for meter,n in [('resume.replacements','1'),('screen.analyses','5'),('clipboard.new_saves','5')]:
        assert allowances[meter]['amount']==n
        assert allowances[meter]['period']==dict(unit='month',anchor='account_signup_day',timezone='Asia/Kolkata')
    permissions={x['feature']:x['allowed'] for x in d['terms']['entitlements']}
    assert permissions['clipboard.saved_answers'] and not permissions['sketch.generate'] and not permissions['screen.followups']
    zero=copy.deepcopy(allowances['clipboard.new_saves']);zero['amount']='0';assert c.UsageAllowance.model_validate(zero).amount==0
    missing=copy.deepcopy(zero);missing.pop('amount')
    with pytest.raises(ValidationError):c.UsageAllowance.model_validate(missing)
    invalid=copy.deepcopy(allowances['answers.completed']);invalid['amount']='999'
    with pytest.raises(ValidationError):c.UsageAllowance.model_validate(invalid)
    omitted=free();omitted['terms']['allowances']=[a for a in omitted['terms']['allowances'] if a['meter']!='resume.replacements'];missing_report=c.validate_draft(omitted)
    assert missing_report.valid and any(issue.path[-1]=='resume.replacements' for issue in missing_report.pending)
    d['terms']['entitlements'][0]['allowed']=False
    assert not c.validate_draft(d).valid

def test_version_dispatch_and_legacy_canonical_roundtrip():
    old=snapshot();raw=old.canonical_json()
    assert c.OfferSnapshot.model_validate_json(raw).canonical_json()==raw
    assert old.fingerprint==hashlib.sha256(raw.encode()).hexdigest()
    assert type(old.terms) is c.OfferTerms and 'allowances' not in old.terms.model_dump()
    for changes in [dict(contract_version='catalog.v9'),dict(contract_version='catalog.v1'),dict(registry_version='catalog.features.v1')]:
        d=free();d.update(changes);assert not c.validate_draft(d).valid

def test_fingerprint_binds_allowances_presentation_and_policy():
    d=free();terms=c.validate_draft(d).draft.terms;first=c.terms_fingerprint(terms)
    for target in ['amount','information']:
        changed=copy.deepcopy(d)
        if target=='amount':changed['terms']['allowances'][4]['amount']='599'
        else:changed['terms']['presentation'][0]['information']='Changed reviewed information'
        assert c.terms_fingerprint(c.validate_draft(changed).draft.terms)!=first
    # Complete synthetic policy/price fixture only, never a real Free price decision.
    legacy=document();data=c.validate_draft(d).draft.model_dump(mode='python')
    data['terms'].update(pricing_mode='priced',prices=legacy['terms']['prices'],subscription_policy_ref='synthetic.lifecycle',migration_policy_ref='synthetic.migration')
    data['terms']['limits'][0]['policy_ref']='synthetic.storage'
    data['state']='previewed'
    result=c.create_snapshot(data,offer_version_id=str(uuid4()),version=1)
    assert result.contract_version=='catalog.v2' and c.OfferSnapshot.model_validate_json(result.canonical_json()).fingerprint==result.fingerprint
    public=c.public_projection(result,visibility(offer_version_id=result.offer_version_id),at=AT)
    assert public.contract_version=='catalog.v2' and public.presentation==result.terms.presentation
    assert public.allowances==result.terms.allowances and public.unmetered_features==result.terms.unmetered_features
    assert 'internal_notes' not in public.model_dump() and 'subscription_policy_ref' not in public.model_dump()


@pytest.mark.parametrize("version,model", [("1", c.OfferTerms), ("2", c.OfferTermsV2), ("3", c.OfferTermsV3)])
@pytest.mark.parametrize("omit_terms", [False, True])
def test_empty_or_omitted_versioned_terms_remain_incomplete(version, model, omit_terms):
    data = free()
    data.update(contract_version="catalog.v" + version,
                registry_version="catalog.features.v" + version, terms={})
    if omit_terms:
        data.pop("terms")
    draft = c.CatalogDraft.model_validate(data)
    assert type(draft.terms) is model
    report = c.validate_draft(data)
    assert report.valid and not report.publishable
    with pytest.raises(ValidationError, match="Snapshot requires complete valid catalog terms"):
        c.OfferSnapshot.model_validate(dict(
            contract_version=data["contract_version"], registry_version=data["registry_version"],
            plan=data["plan"], offer_version_id=str(uuid4()), version="1", terms={}))
