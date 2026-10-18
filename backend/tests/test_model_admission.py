import pytest
from types import SimpleNamespace as NS
from app.cloud import interview_sessions as sessions
from app.api import interview_sessions as api
from app.config import settings
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.auth.supabase_auth import get_current_user


def test_catalog_requires_authentication_before_readiness(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix='/api/interview-sessions')
    monkeypatch.setattr(sessions, 'model_admission_status', lambda: pytest.fail('anonymous readiness probe'))
    assert TestClient(app).get('/api/interview-sessions/answer-models').status_code == 401


def test_admission_closes_only_its_owned_network_client(monkeypatch):
    monkeypatch.setattr(settings, 'ENABLE_SESSION_ANSWER_MODELS', True)
    monkeypatch.setattr(sessions, 'session_model_backend_ready', lambda: True)
    closed = []
    client = NS(_session=NS(post=lambda *a, **k: NS(status_code=200, json=lambda: True),
                            close=lambda: closed.append(True)), _rest_url='http://local', _headers={})
    monkeypatch.setattr(sessions, 'SupabaseInterviewSessionClient', lambda: client)
    assert sessions.model_admission_status() == 'enabled'
    assert closed == [True]
    assert sessions.model_admission_status(client) == 'enabled'
    assert closed == [True]

@pytest.mark.parametrize('flag,python_ready,db_ready,expected',[(False,False,False,'legacy'),(True,False,True,'closed'),(True,True,False,'closed'),(True,True,True,'enabled')])
def test_admission_includes_both_readiness_gates(monkeypatch,flag,python_ready,db_ready,expected):
    monkeypatch.setattr(settings,'ENABLE_SESSION_ANSWER_MODELS',flag)
    monkeypatch.setattr(sessions,'session_model_backend_ready',lambda:python_ready)
    calls=[]
    def post(*args,**kwargs):
        calls.append(args)
        return NS(status_code=200,json=lambda:db_ready)
    monkeypatch.setattr(sessions,'SupabaseInterviewSessionClient',lambda:NS(_session=NS(post=post),_rest_url='http://local',_headers={}))
    assert sessions.model_admission_status()==expected
    assert bool(calls)==bool(flag and python_ready)


def test_admission_database_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(settings,'ENABLE_SESSION_ANSWER_MODELS',True)
    monkeypatch.setattr(sessions,'session_model_backend_ready',lambda:True)
    def unavailable(): raise RuntimeError('private')
    monkeypatch.setattr(sessions,'SupabaseInterviewSessionClient',unavailable)
    assert sessions.model_admission_status()=='closed'


def test_stale_admission_contract_never_creates_unbound_or_defaulted_session(monkeypatch):
    app=FastAPI();app.include_router(api.router,prefix='/api/interview-sessions')
    app.dependency_overrides[get_current_user]=lambda:NS(user_id='owner')
    app.dependency_overrides[api.get_cloud_interview_session_service]=lambda:NS(create_session=lambda **kwargs:pytest.fail('must not create'))
    monkeypatch.setattr(sessions,'model_admission_status',lambda:'enabled')
    with TestClient(app) as client:
        result=client.post('/api/interview-sessions',json={'company_name':'Example'},headers={'Idempotency-Key':'one','X-Session-Model-Admission':'legacy'})
    assert result.status_code==409 and result.json()['detail']['code']=='model_selection_stale'

@pytest.mark.parametrize('ready,target,url,configured,expected',[
    (False,'rbmxfazjbldmkomdpyzl','https://rbmxfazjbldmkomdpyzl.supabase.co',True,False),
    (True,'','https://rbmxfazjbldmkomdpyzl.supabase.co',True,False),
    (True,'other-project','https://other-project.supabase.co',True,False),
    (True,'rbmxfazjbldmkomdpyzl','https://other-project.supabase.co',True,False),
    (True,'rbmxfazjbldmkomdpyzl','http://rbmxfazjbldmkomdpyzl.supabase.co',True,False),
    (True,'rbmxfazjbldmkomdpyzl','https://rbmxfazjbldmkomdpyzl.supabase.co',False,False),
    (True,'rbmxfazjbldmkomdpyzl','https://rbmxfazjbldmkomdpyzl.supabase.co/',True,True),
])
def test_development_readiness_pins_approved_target(monkeypatch,ready,target,url,configured,expected):
    monkeypatch.setattr(settings,'SESSION_ANSWER_MODELS_DEV_READY',ready)
    monkeypatch.setattr(settings,'SESSION_ANSWER_MODELS_DEV_PROJECT_REF',target)
    monkeypatch.setattr(sessions,'get_supabase_settings',lambda:NS(configured=configured,supabase_url=url))
    assert sessions.session_model_backend_ready() is expected
    if ready and not expected:
        with pytest.raises(sessions.SupabaseConfigurationError) as error:
            sessions.validate_session_model_dev_activation()
        assert url not in str(error.value)
    else:
        sessions.validate_session_model_dev_activation()


def test_creation_cannot_bypass_database_admission(monkeypatch):
    from test_session_model_contract import Store
    monkeypatch.setattr(settings,'ENABLE_SESSION_ANSWER_MODELS',True)
    monkeypatch.setattr(sessions,'session_model_backend_ready',lambda:True)
    store=Store()
    store._rest_url='http://local'
    store._headers={}
    store._session=NS(post=lambda *args,**kwargs:NS(status_code=200,json=lambda:False))
    with pytest.raises(sessions.CloudInterviewSessionConflictError):
        sessions.CloudInterviewSessionService(client=store).create_session(user_id='owner',payload={'title':'test'},idempotency_key='one')


def test_database_creation_pause_does_not_relabel_bound_execution(monkeypatch):
    from test_session_model_contract import Store,record,SID
    monkeypatch.setattr(settings,'ENABLE_SESSION_ANSWER_MODELS',True)
    monkeypatch.setattr(sessions,'session_model_backend_ready',lambda:True)
    store=Store();store.rows=record('gpt-5.6-luna')
    service=sessions.CloudInterviewSessionService(client=store)
    assert service.get_session(user_id='owner',session_id=SID).selected_model_key=='gpt-5.6-luna'
    monkeypatch.setattr(sessions,'session_model_backend_ready',lambda:False)
    with pytest.raises(sessions.CloudInterviewSessionConflictError): service.get_session(user_id='owner',session_id=SID)

@pytest.mark.asyncio
async def test_backend_startup_rejects_wrong_development_target(monkeypatch):
    # Test model readiness without initializing independent audio/model services.
    from app.services.stt_provider import STTProviderService
    monkeypatch.setattr(STTProviderService, '__init__', lambda self: None)
    from app.main import lifespan
    monkeypatch.setattr(settings,'SESSION_ANSWER_MODELS_DEV_READY',True)
    monkeypatch.setattr(settings,'SESSION_ANSWER_MODELS_DEV_PROJECT_REF','other-project')
    monkeypatch.setattr(sessions,'get_supabase_settings',lambda:NS(configured=True,supabase_url='https://other-project.supabase.co'))
    with pytest.raises(sessions.SupabaseConfigurationError):
        async with lifespan(None):
            pytest.fail('wrong target must not start')
