from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.cloud import interview_sessions as sessions
from app.api.interview_sessions import InterviewSessionCreateRequest, _session_response
from app.answer_models import MODELS, DEFAULT_MODEL_KEY

SID = "30000000-0000-4000-8000-000000000001"


def record(key=None):
    return sessions._record_from_payload(dict(id=SID, user_id="owner", status="active", selected_model_key=key))


class Store:
    def __init__(self):
        self.rows = record()
        self.calls = []
        self.keys = {}

    def get_session(self, *, user_id, session_id):
        if user_id != self.rows.user_id:
            raise sessions.CloudInterviewSessionNotFoundError()
        return self.rows

    def create_session(self, **kwargs):
        self.calls.append(kwargs)
        key = (kwargs['user_id'], kwargs['idempotency_key'])
        if key in self.keys and self.keys[key] != kwargs['request_hash']:
            raise sessions.CloudInterviewSessionConflictError()
        self.keys[key] = kwargs['request_hash']
        self.rows = replace(record(kwargs['payload'].get('selected_model_key')), user_id=kwargs['user_id'])
        return sessions.CreateInterviewSessionResult(self.rows, False)


@pytest.mark.parametrize('model', MODELS, ids=lambda m: m.key)
def test_future_enabled_selection_and_authoritative_recovery(monkeypatch, model):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', True)
    monkeypatch.setattr(sessions.settings, 'GEMINI_API_KEY', '')
    monkeypatch.setattr(sessions, 'model_admission_status', lambda *args: 'enabled')
    store = Store()
    service = sessions.CloudInterviewSessionService(client=store)
    created = service.create_session(user_id='owner', payload={'title': 'test', 'selected_model_key': model.key}, idempotency_key='key')
    assert created.record.selected_model_key == model.key
    recovered = service.get_session(user_id='owner', session_id=SID, allow_model_bound=True)
    assert _session_response(recovered).selected_model_key == model.key
    assert recovered.model_selection_kind == 'model_bound'
    with pytest.raises(sessions.CloudInterviewSessionNotFoundError):
        service.get_session(user_id='other', session_id=SID, allow_model_bound=True)


@pytest.mark.parametrize('value', ['', 'unknown', 'openai/gpt-oss-120b', 12, {}, False])
def test_invalid_keys_rejected(value):
    with pytest.raises(sessions.CloudInterviewSessionValidationError):
        sessions.normalize_session_payload({'title': 'test', 'selected_model_key': value}, model_enabled=True)


@pytest.mark.parametrize('field', ['provider', 'model', 'api_model', 'provider_url', 'model_selection_kind', 'user_id'])
def test_override_fields_rejected_at_api_and_service(field):
    with pytest.raises(ValidationError):
        InterviewSessionCreateRequest(title='test', **{field: 'arbitrary'})
    with pytest.raises(sessions.CloudInterviewSessionValidationError):
        sessions.normalize_session_payload({'title': 'test', field: 'arbitrary'}, model_enabled=True)


@pytest.mark.parametrize('payload', [{'title': 'test'}, {'title': 'test', 'selected_model_key': None}])
def test_future_default_no_credentials(monkeypatch, payload):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', True)
    monkeypatch.setattr(sessions.settings, 'GEMINI_API_KEY', '')
    monkeypatch.setattr(sessions, 'model_admission_status', lambda *args: 'enabled')
    store = Store()
    result = sessions.CloudInterviewSessionService(client=store).create_session(user_id='owner', payload=payload, idempotency_key='key')
    assert result.record.selected_model_key == DEFAULT_MODEL_KEY


@pytest.mark.parametrize('enabled', [True, False])
def test_no_bound_creation_until_routing_ready(monkeypatch, enabled):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', enabled)
    store = Store()
    service = sessions.CloudInterviewSessionService(client=store)
    with pytest.raises(sessions.CloudInterviewSessionConflictError):
        service.create_session(user_id='owner', payload={'title': 'test', 'selected_model_key': DEFAULT_MODEL_KEY}, idempotency_key='key')
    if enabled:
        with pytest.raises(sessions.CloudInterviewSessionConflictError):
            service.create_session(user_id='owner', payload={'title': 'test'}, idempotency_key='key')
    assert not store.calls


def test_future_idempotency_selection_conflict(monkeypatch):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', True)
    monkeypatch.setattr(sessions, 'model_admission_status', lambda *args: 'enabled')
    service = sessions.CloudInterviewSessionService(client=Store())
    service.create_session(user_id='owner', payload={'title': 'test'}, idempotency_key='same')
    with pytest.raises(sessions.CloudInterviewSessionConflictError):
        service.create_session(user_id='owner', payload={'title': 'test', 'selected_model_key': MODELS[0].key}, idempotency_key='same')


def test_legacy_history_and_disabled_hash_stay_unchanged(monkeypatch):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    source = dict(id=SID, user_id='owner', status='ended', metadata={'model': 'historical-model'})
    before = dict(source['metadata'])
    normalized = sessions._record_from_payload(source)
    assert normalized.selected_model_key is None and normalized.model_selection_kind == 'legacy'
    assert source['metadata'] == before
    payload = sessions.normalize_session_payload({'title': 'test'})
    assert 'selected_model_key' not in payload
    assert payload == {'title': 'test', 'selected_resume_id': None, 'job_context_id': None,
                       'target_role': None, 'company_name': None, 'job_description_preview': None}
    store = Store()
    result = sessions.CloudInterviewSessionService(client=store).create_session(user_id='owner', payload={'title':'test'}, idempotency_key='key')
    assert _session_response(result.record).model_selection_kind == 'legacy'


def test_restored_bound_session_cannot_enter_old_generation_with_flag_off(monkeypatch):
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    store = Store()
    store.rows = record(DEFAULT_MODEL_KEY)
    service = sessions.CloudInterviewSessionService(client=store)
    with pytest.raises(sessions.CloudInterviewSessionConflictError, match='generation is not available'):
        service.get_session(user_id='owner', session_id=SID)
    assert service.get_session(user_id='owner', session_id=SID, allow_model_bound=True).selected_model_key == DEFAULT_MODEL_KEY


def test_api_real_service_recovery_and_override_rejection(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import interview_sessions as api
    from app.auth.supabase_auth import get_current_user
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    store = Store()
    store.rows = record(DEFAULT_MODEL_KEY)
    service = sessions.CloudInterviewSessionService(client=store)
    app = FastAPI()
    app.include_router(api.router, prefix='/api/interview-sessions')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='owner')
    app.dependency_overrides[api.get_cloud_interview_session_service] = lambda: service
    with TestClient(app) as client:
        response = client.get('/api/interview-sessions/' + SID)
        assert response.status_code == 200
        assert response.json()['selected_model_key'] == DEFAULT_MODEL_KEY
        assert response.json()['model_selection_kind'] == 'model_bound'
        for key in ('unknown', 'openai/gpt-oss-120b'):
            response = client.post('/api/interview-sessions', headers={'Idempotency-Key': 'test'},
                                   json={'title': 'test', 'selected_model_key': key})
            assert response.status_code == 409
            assert response.json()['detail']['code'] == 'model_selection_stale'
        response = client.post('/api/interview-sessions', headers={'Idempotency-Key':'test'},
                               json={'title': 'test', 'provider_url': 'https://arbitrary'})
        assert response.status_code == 422
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='other')
        assert client.get('/api/interview-sessions/' + SID).status_code == 404


def test_future_rest_client_uses_model_rpc_and_preserves_recovered_key():
    from test_cloud_interview_sessions import FakeRestSession, _supabase_client_with_session
    rest = FakeRestSession()
    rest.get_response.json()[0]['selected_model_key'] = DEFAULT_MODEL_KEY
    client = _supabase_client_with_session(rest)
    payload = sessions.normalize_session_payload({'title': 'test'}, model_enabled=True)
    result = client.create_session(user_id='owner', payload=payload, idempotency_key='test', request_hash='hash')
    assert rest.post_calls[0]['url'].endswith('/rpc/create_interview_session_with_binding')
    assert rest.post_calls[0]['json']['p_selected_model_key'] == DEFAULT_MODEL_KEY
    assert rest.post_calls[0]['json']['p_selected_model_binding'] == payload['selected_model_binding']
    assert result.record.selected_model_key == DEFAULT_MODEL_KEY


def test_existing_http_and_grpc_loaders_fail_closed_for_bound_records(monkeypatch):
    from fastapi import HTTPException
    from app.api import generate
    from app import grpc_cloud_context as grpc
    store = Store()
    store.rows = record(DEFAULT_MODEL_KEY)
    service = sessions.CloudInterviewSessionService(client=store)
    monkeypatch.setattr(sessions.settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    monkeypatch.setattr(generate, '_new_cloud_interview_session_service', lambda: service)
    monkeypatch.setattr(generate, '_current_user_for_session_id', lambda *args: SimpleNamespace(user_id='owner'))
    with pytest.raises(HTTPException) as failure:
        generate._authorize_generation_session(generate.GenerateRequest(question='test', category='technical', session_id=SID), None)
    assert failure.value.status_code == 409
    monkeypatch.setattr(grpc, 'get_current_user', lambda request: SimpleNamespace(user_id='owner'))
    monkeypatch.setattr(grpc, 'CloudInterviewSessionService', lambda: service)
    with pytest.raises(grpc.CloudContextRejected):
        grpc.GrpcCloudContext(None, SID, '', '').load()
