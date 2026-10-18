import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app import answer_models as models
from app.answer_generation import PreparedAnswer, _request
from app.api.interview_sessions import router

DEFAULT='gemini:gemini-3.5-flash-lite'
FALLBACK='groq:openai/gpt-oss-120b'
BASE=models.DEFAULT_ENTRIES
EXTRA='groq:example-compatible-model'


def parse(entries=BASE, **kwargs):
    return models.parse_catalog(entries, kwargs.get('default',DEFAULT), kwargs.get('fallback',FALLBACK), kwargs.get('overrides','{}'))


def test_config_only_add_remove_order_labels_and_legacy_keys():
    choices,default,fallback=parse(EXTRA+','+BASE)
    custom=choices[0]
    assert custom.key==EXTRA and custom.provider=='groq'
    assert custom.display_name=='Example Compatible Model'
    assert custom.description=='Text generation via Groq'
    assert [m.key for m in choices[1:]]==list(models.LEGACY_MODELS)
    binding=models.model_binding(custom)
    assert EXTRA not in {m.key for m in parse()[0]}
    assert models.model_binding(models.resolve_binding(custom.key,binding))==binding
    assert default=='gemini-3.5-flash-lite' and fallback=='gpt-oss-120b'


@pytest.mark.parametrize('entries',[BASE+','+EXTRA+','+EXTRA,BASE+',',BASE+',unqualified',BASE+',other:model',BASE+',gemini:../escape',BASE+',openai:',BASE+',gemini:models/name'])
def test_bad_lists_have_secret_free_errors(entries):
    with pytest.raises(models.ModelConfigurationError) as error: parse(entries)
    assert entries not in str(error.value)


@pytest.mark.parametrize('option',['default','fallback'])
def test_invalid_references(option):
    with pytest.raises(models.ModelConfigurationError): parse(**{option:'groq:absent'})


@pytest.mark.parametrize('override',[
    '{"groq:example-compatible-model":{"url":"https://secret"}}',
    '{"groq:example-compatible-model":{"profile":"openai-reasoning"}}',
    '{"groq:example-compatible-model":{"profile":"groq-oss","effort":"impossible"}}',
    '{"groq:example-compatible-model":{"output_limit":true}}',
    '{"groq:example-compatible-model":{"output_limit":0}}',
    '{"groq:example-compatible-model":{"display_name":""}}',
    '{"absent:model":{}}', '[]', '{"x":{},"x":{}}', 'SECRET malformed',
])
def test_bad_overrides_are_safe(override):
    with pytest.raises(models.ModelConfigurationError) as error: parse(BASE+','+EXTRA,overrides=override)
    assert 'SECRET' not in str(error.value)


def test_parameter_profiles_and_overrides():
    choices,_,_=parse(BASE+','+EXTRA,overrides=json.dumps({EXTRA:dict(profile='groq-oss',effort='high',output_limit=1000,display_name='My Groq Model',description='Text generation')}))
    custom=choices[-1]
    _,_,body=_request(custom,PreparedAnswer('system','question',2500),'mock')
    assert body['reasoning_effort']=='high' and body['max_completion_tokens']==1000
    assert models.model_binding(models.resolve_binding(custom.key,models.model_binding(custom)))==models.model_binding(custom)
    for entry in ['openai:compatible-text','groq:compatible-text','gemini:compatible-text']:
        model=parse(BASE+','+entry)[0][-1]
        _,_,body=_request(model,PreparedAnswer('system','question'),'mock')
        assert 'reasoning' not in body and 'reasoning_effort' not in body
        assert 'thinkingConfig' not in body.get('generationConfig',{})


def test_restart_removal_preserves_snapshot_and_frozen_historical_binding():
    env=dict(os.environ,ANSWER_MODELS=BASE+','+EXTRA,ANSWER_DEFAULT_MODEL=DEFAULT,ANSWER_FALLBACK_MODEL=FALLBACK,ANSWER_MODEL_OVERRIDES='{}',ANSWER_DISABLED_MODELS='')
    binding=subprocess.check_output([sys.executable,'-c',"import json;from app.answer_models import *;print(json.dumps(model_binding(MODEL_CATALOG['groq:example-compatible-model'])))"],env=env,text=True,cwd=Path(__file__).resolve().parents[1]).strip()
    env['ANSWER_MODELS']=BASE
    result=subprocess.check_output([sys.executable,'-c',"import json,sys;from app.answer_models import *;assert 'groq:example-compatible-model' not in MODEL_CATALOG;m=resolve_binding('groq:example-compatible-model',json.loads(sys.argv[1]));print(m.api_model)",binding],env=env,text=True,cwd=Path(__file__).resolve().parents[1])
    assert result.strip()=='example-compatible-model'
    frozen=models.resolve_binding('gemini-3.6-flash')
    assert frozen.api_model=='gemini-3.6-flash' and frozen.api_profile=='gemini-thinking'
    with pytest.raises(models.ModelConfigurationError): models.resolve_binding(EXTRA)
    bad=json.loads(binding);bad['api_model']='different'
    with pytest.raises(models.ModelConfigurationError): models.resolve_binding(EXTRA,bad)


def test_safe_catalog_endpoint_no_credentials_profiles_or_remote_assets():
    app=FastAPI();app.include_router(router,prefix='/api/interview-sessions')
    response=TestClient(app).get('/api/interview-sessions/answer-models')
    assert response.status_code==200
    items=response.json()['items']
    assert items[3]['default'] and items[3]['selectable']
    assert set(items[0])=={'key','display_name','provider','logo_key','description','default','selectable','credentials_configured','live_access'}
    assert items[0]['logo_key']=='openai'


def test_removed_choice_rejected_but_binding_still_routes(monkeypatch):
    from app.cloud import interview_sessions as sessions
    choices,_,_=parse(BASE+','+EXTRA)
    monkeypatch.setattr(sessions,'MODEL_CATALOG',{m.key:m for m in choices})
    payload=sessions.normalize_session_payload({'title':'test','selected_model_key':EXTRA},model_enabled=True)
    assert models.resolve_binding(EXTRA,payload['selected_model_binding']).api_model=='example-compatible-model'
    monkeypatch.setattr(sessions,'MODEL_CATALOG',models.MODEL_CATALOG)
    with pytest.raises(sessions.CloudInterviewSessionValidationError):
        sessions.normalize_session_payload({'title':'test','selected_model_key':EXTRA},model_enabled=True)


@pytest.mark.asyncio
async def test_explicit_execution_disable_is_distinct_from_removal(monkeypatch):
    from app import answer_generation as generation
    monkeypatch.setattr(generation,'DISABLED_MODELS',frozenset({DEFAULT}))
    with pytest.raises(generation.AttemptFailure,match='model_disabled'):
        async for _ in generation.provider_stream(None,models.MODEL_CATALOG['gemini-3.5-flash-lite'],PreparedAnswer('system','question'),'mock'):
            pass

def test_known_profile_changes_do_not_remap_pre_snapshot_sessions():
    changed=parse(overrides=json.dumps({'gemini:gemini-3.6-flash':{'effort':'high'}}))[0][-1]
    assert changed.effort=='high'
    assert models.resolve_binding(changed.key).effort=='medium'
    assert models.resolve_binding(changed.key,models.model_binding(changed)).effort=='high'
