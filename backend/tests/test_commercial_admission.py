"""C11.0/C11.1 offline ingress/identity coverage; no commercial authority enabled."""
import asyncio
import time
from types import SimpleNamespace as NS
from pathlib import Path
import ast

import grpc
import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from app.config import settings, hosted_commercial_mode
from app.auth import supabase_auth as auth
from app.commercial import admission, admin
from app.commercial.boundary import CommercialBoundaryMiddleware, HOSTED_INGRESS
from app.api import generate as api
from app import session_generation as sg, grpc_server
from app.grpc_generated import interview_realtime_pb2 as pb, interview_realtime_pb2_grpc as rpc
from test_session_generation import setup, req, SID

USER = '10000000-0000-4000-8000-000000000001'
OTHER = '20000000-0000-4000-8000-000000000002'
KEY = 'synthetic-test-signing-key-not-a-real-credential'


@pytest.fixture
def identity(monkeypatch):
    monkeypatch.setattr(settings, 'HOSTED_COMMERCIAL_MODE', True)
    monkeypatch.setattr(settings, 'SUBSCRIPTION_ADMIN_SUBJECTS', '')
    monkeypatch.setattr(auth, 'get_auth_verification_config', lambda: auth.AuthVerificationConfig(
        'legacy_secret', KEY, 'https://synthetic.invalid/auth/v1', 'authenticated'))
    def headers(subject=USER, **claims):
        token = jwt.encode(dict(sub=subject, exp=int(time.time())+300, aud='authenticated',
            iss='https://synthetic.invalid/auth/v1', **claims), KEY, algorithm='HS256')
        return {'Authorization': 'Bearer '+token}
    return headers


def request(headers):
    return Request({'type': 'http', 'headers': [(k.lower().encode(), v.encode()) for k,v in headers.items()], 'state': {}})


@pytest.mark.asyncio
@pytest.mark.parametrize('case,status', [('anonymous',401),('forged_token',401),('missing',400),
    ('invalid_session',422),('forged_owner',404),('inactive',409),('unavailable',503),('denied',403),('authority_error',503),('screen',503)])
async def test_denied_buffered_calls_zero_providers(setup, identity, monkeypatch, case, status):
    session, store = setup
    session.user_id = USER
    calls = []
    async def provider(*args):
        calls.append(True)
        yield 'synthetic', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    body = req()
    headers = identity()
    if case == 'anonymous': headers = {}
    if case == 'forged_token': headers = {'Authorization': 'Bearer forged'}
    if case == 'missing': body.session_id = None
    if case == 'invalid_session': body.session_id = 'not-a-session'
    if case == 'forged_owner': session.user_id = OTHER
    if case == 'inactive': session.status = 'ended'
    if case == 'screen': body.source = 'screen'
    if case in ('denied', 'authority_error'):
        async def authority(context):
            if case == 'authority_error': raise RuntimeError('synthetic-private-error')
            return admission.AdmissionDecision(admission.AdmissionOutcome.DENIED)
        monkeypatch.setattr(admission, 'authority', NS(admit=authority))
    with pytest.raises(Exception) as exc:
        await api.generate_answer(body, request(headers))
    assert exc.value.status_code == status
    assert calls == [] and store.saves == []


@pytest.mark.asyncio
async def test_owned_test_authority_production_buffered_coordinator_once(setup, identity, monkeypatch, application):
    session, store = setup
    session.user_id = USER
    monkeypatch.setattr(api, '_current_user_for_session_id', lambda *args: auth.CurrentUser(USER))
    admissions, providers = [], []
    async def approve(context):
        admissions.append(context)
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    async def provider(client, model, prepared, key):
        providers.append(model.key)
        yield 'Dependency injection supplies dependencies externally and makes classes easy to test.', None, True
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://synthetic') as client:
        response = await client.post('/generate/', json=req().model_dump(), headers=identity())
    assert response.status_code == 200
    assert 'Dependency injection' in response.json()['answer']
    assert len(admissions) == len(providers) == len(store.saves) == 1
    assert admissions[0].user_id == USER and admissions[0].session_id == SID
    assert admissions[0].request_id == 'turn-1'
    assert len(admissions[0].semantics_hash) == 64


def test_mode_default_and_invalid_configuration(monkeypatch):
    monkeypatch.delenv('HOSTED_COMMERCIAL_MODE', raising=False)
    assert not hosted_commercial_mode()
    monkeypatch.setenv('HOSTED_COMMERCIAL_MODE', 'typo')
    with pytest.raises(ValueError): hosted_commercial_mode()


@pytest.fixture
def application(monkeypatch):
    # Patch heavyweight local adapters before actual app import, not the routing
    # or provider code whose admission is under test. Outbound guard is installed
    # by the existing offline launcher/conftest before any application import.
    import whisper
    monkeypatch.setattr(whisper, 'load_model', lambda *args, **kwargs: NS())
    from app.main import app
    return app


def test_all_registered_unreviewed_routes_and_future_routes_are_denied(application, identity, monkeypatch):
    monkeypatch.setattr(settings, 'DIAGRAM_GENERATION_ENABLED', True)
    monkeypatch.setattr(settings, 'BILLING_ADMIN_ENABLED', 'false')
    monkeypatch.setattr(settings, 'BILLING_NOTIFICATIONS_ENABLED', 'false')
    monkeypatch.setattr(settings, 'HOSTED_AUDIO_ENABLED', False)
    reached = []
    async def provider_endpoint(scope, receive, send):
        reached.append(True)
        raise AssertionError('unreviewed endpoint reached')
    checked = []
    for route in application.routes:
        path = getattr(route, 'path', '')
        methods = getattr(route, 'methods', None)
        if not methods: continue
        for method in methods:
            if (method, path) in HOSTED_INGRESS: continue
            concrete = path
            for name in getattr(route, 'param_convertors', {}): concrete = concrete.replace('{'+name+'}', SID)
            checked.append((method, concrete))
        # Reviewed endpoints retain their production consumers.
        if not any((method, path) in HOSTED_INGRESS for method in methods):
            monkeypatch.setattr(route, 'app', provider_endpoint)
    with TestClient(application) as client:
        for method, path in checked:
            response = client.request(method, path, headers=identity())
            billing_path = path.lower().startswith(('/api/admin/billing', '/api/billing/email/'))
            hidden_path = billing_path or path == '/api/account/audio/capabilities'
            assert response.status_code == (404 if hidden_path else 503), (method,path,response.status_code)
            if method != 'HEAD':
                assert response.json()['detail']['code'] == ('billing_path_unavailable' if billing_path else 'commercial_path_unreviewed')
        assert client.post('/future-company-funded-operation').status_code == 503
    assert len(checked) > 50 and not reached


@pytest.mark.parametrize('path', ['/ws/auto-stt','/ws/system-auto-stt','/ws/manual-stt','/future-stream'])
def test_all_websocket_paths_fail_before_endpoint(application, identity, path):
    with TestClient(application) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(path, headers=identity()): pass
        assert exc.value.code == 1008


@pytest.mark.asyncio
async def test_real_grpc_ignores_local_cloud_manual_auto_flags_in_hosted_mode(identity, monkeypatch):
    # Even permissive legacy transport flags cannot override commercial denial.
    for flag in ('GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED','USE_GRPC_AUTO_PIPELINE',
                 'USE_GRPC_MANUAL_PIPELINE','USE_GRPC_CLOUD_CONTEXT_PIPELINE'):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, 'ASSEMBLYAI_API_KEY', 'synthetic-unused')
    # Actual localhost channel. No capture/STT/auth/provider can run before abort.
    class Forbidden:
        def __init__(self, *args, **kwargs): raise AssertionError('capture opened')
    from app.services import system_audio_capture
    monkeypatch.setattr(system_audio_capture, 'SystemAudioCaptureService', Forbidden)
    server, port = await grpc_server.start_server(port=0)
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            stub = rpc.InterviewRealtimeServiceStub(channel)
            health = await stub.CheckHealth(pb.Empty())
            assert not health.auto_available and not health.answer_stream_available
            for mode, cloud in [('auto_pipeline',True),('auto_pipeline',False),('manual_pipeline',False)]:
                call = stub.StreamInterview(timeout=2)
                await call.write(pb.InterviewClientEvent(session_id='synthetic', start_session=pb.StartSession(
                    mode=mode, source='both', cloud_context_requested=cloud)))
                with pytest.raises(grpc.aio.AioRpcError) as exc: await call.read()
                assert exc.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await server.stop(0)


def test_admin_cannot_be_promoted_by_claims_body_or_headers(application, identity, monkeypatch):
    # Authoritative probe result, never startup lists or editable JWT metadata.
    def ordinary(actor):
        return lambda *args: dict(contract_version='admin.access.v1', subject_id=actor.subject_id,
            permissions=[], permission_revision=None)
    monkeypatch.setattr(admin, 'probe_transport', ordinary)
    with TestClient(application) as client:
        headers = identity(role='admin', user_metadata={'role':'owner'}, app_metadata={'permissions':['subscriptions.manage']})
        for configured in ('', OTHER, USER, 'invalid'):
            monkeypatch.setattr(settings, 'SUBSCRIPTION_ADMIN_SUBJECTS', configured)
            result = client.get('/api/commercial/admin/me', headers=headers)
            assert result.status_code == 200 and result.json() == {'permissions': []}
        assert client.post('/api/commercial/admin/me', json={'user_id':USER,'role':'owner'}, headers=headers).status_code == 503
        result = client.get('/api/commercial/admin/me', headers=identity(OTHER, user_metadata={'user_id':USER,'role':'admin'}))
        assert result.status_code == 200 and result.json() == {'permissions': []}
        def granted(actor):
            return lambda *args: dict(contract_version='admin.access.v1', subject_id=actor.subject_id,
                permissions=['subscriptions.manage'] if actor.subject_id == OTHER else [],
                permission_revision='1' if actor.subject_id == OTHER else None)
        monkeypatch.setattr(admin, 'probe_transport', granted)
        assert client.get('/api/commercial/admin/me', headers=identity(OTHER)).json() == {'permissions':['subscriptions.manage']}
        assert client.get('/api/commercial/admin/me', headers=headers).json() == {'permissions': []}


def test_local_boundary_preserves_existing_routing(monkeypatch):
    monkeypatch.setattr(settings, 'HOSTED_COMMERCIAL_MODE', False)
    app = FastAPI()
    app.add_middleware(CommercialBoundaryMiddleware)
    @app.post('/previous-local-path')
    def local(): return {'local':True}
    with TestClient(app) as client: assert client.post('/previous-local-path').json() == {'local':True}


@pytest.mark.parametrize('case,status', [('anonymous',401),('forged',401),('missing',400),('wrong_owner',404),('unavailable',503)])
def test_actual_buffered_http_admission_denials(setup, application, identity, case, status):
    session, store = setup
    session.user_id = OTHER if case == 'wrong_owner' else USER
    body, headers = req().model_dump(), identity()
    if case == 'anonymous': headers = {}
    if case == 'forged': headers = {'Authorization':'Bearer forged'}
    if case == 'missing': body['session_id'] = None
    with TestClient(application) as client:
        response = client.post('/generate/', json=body, headers=headers)
    assert response.status_code == status
    assert not store.rows and not store.saves


@pytest.mark.parametrize('outcome,status,code', [
    (admission.AdmissionOutcome.ALLOWED, None, 'commercial_access_allowed'),
    (admission.AdmissionOutcome.DENIED, 403, 'commercial_access_denied'),
    (admission.AdmissionOutcome.UNAVAILABLE, 503, 'commercial_authority_unavailable'),
])
def test_explicit_decisions_and_safe_mapping(outcome, status, code):
    decision = admission.AdmissionDecision(outcome)
    assert decision.reason_code == code
    if status is None:
        admission.enforce_decision(decision)
    else:
        with pytest.raises(Exception) as exc:
            admission.enforce_decision(decision)
        assert exc.value.status_code == status and exc.value.detail == {'code': code}


@pytest.mark.parametrize('bad', [True, False, None, {'allowed': True}, admission.AdmissionDecision('allowed')])
def test_invalid_authority_contract_is_unavailable_not_granted(bad):
    with pytest.raises(Exception) as exc:
        admission.enforce_decision(bad)
    assert exc.value.status_code == 503
    assert exc.value.detail == {'code': 'commercial_authority_unavailable'}


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ['', ' spaces ', 'x'*121, 'slash/key', 'line\n', '\u00e9'])
async def test_invalid_idempotency_keys_never_reach_authority_or_provider(setup, identity, monkeypatch, key):
    session, store = setup
    session.user_id = USER
    async def forbidden(context): raise AssertionError('authority reached')
    monkeypatch.setattr(admission, 'authority', NS(admit=forbidden))
    with pytest.raises(Exception) as exc:
        await api.generate_answer(req(key), request(identity()))
    assert exc.value.status_code == 422
    assert exc.value.detail['code'] == 'commercial_request_id_invalid'
    assert not store.rows and not store.saves


@pytest.mark.asyncio
async def test_context_matches_durable_hash_and_is_account_resource_operation_scoped(setup, identity, monkeypatch):
    from dataclasses import replace
    session, _ = setup
    session.user_id = USER
    contexts = []
    async def approve(context):
        contexts.append(context)
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    body = req()
    await admission.admit_buffered_answer(body, request(identity()))
    expected = body.model_copy(update=dict(selected_resume_id=session.selected_resume_id,
        target_role=session.target_role, company_name=session.company_name,
        job_description=session.job_description_preview))
    context = contexts[0]
    assert context.semantics_hash == sg.generation_request_hash(expected)
    for changed in [replace(context, user_id=OTHER), replace(context, session_id=OTHER),
                    replace(context, operation='other')]:
        assert changed.operation_id != context.operation_id
    assert replace(context, retry_attempt=1).operation_id == context.operation_id
    assert replace(context, recovery=True).operation_id == context.operation_id
    other = req(); other.question = 'What is a deadlock?'
    await admission.admit_buffered_answer(other, request(identity()))
    assert contexts[1].operation_id == context.operation_id
    assert contexts[1].semantics_hash != context.semantics_hash


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['question', 'request_id', 'retry_attempt', 'account', 'session', 'copy'])
async def test_request_grant_cannot_be_reused_for_different_identity_or_semantics(setup, identity, monkeypatch, change):
    session, store = setup
    session.user_id = USER
    admissions = []
    async def approve(context):
        admissions.append(context)
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    body, scope = req(), request(identity())
    await admission.admit_buffered_answer(body, scope)
    await admission.admit_buffered_answer(body, scope)
    assert len(admissions) == 1
    if change == 'question': body.question = 'What is a deadlock?'
    if change == 'request_id': body.request_id = 'different'
    if change == 'retry_attempt': body.retry_attempt = 1
    if change == 'account':
        switched = request(identity(OTHER))
        switched.scope['state'] = scope.scope['state']
        scope = switched
        session.user_id = OTHER
    if change == 'session':
        body.session_id = OTHER
        session.id = OTHER
    if change == 'copy': body = body.model_copy()
    with pytest.raises(Exception) as exc:
        await admission.admit_buffered_answer(body, scope)
    assert exc.value.status_code == 409
    assert exc.value.detail['code'] == 'commercial_operation_conflict'
    assert len(admissions) == 1 and not store.rows


@pytest.mark.asyncio
async def test_test_authority_still_requires_existing_durable_coordinator(setup, identity, monkeypatch):
    session, store = setup
    session.user_id = USER
    monkeypatch.setattr(settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    with pytest.raises(Exception) as exc:
        await api.generate_answer(req(), request(identity()))
    assert exc.value.status_code == 503
    assert exc.value.detail['code'] == 'commercial_coordination_unavailable'
    assert not store.rows


def test_admin_removal_switching_accounts_and_failed_authority(application, identity, monkeypatch):
    grants = {USER}
    def source(actor):
        return lambda *args: dict(contract_version='admin.access.v1', subject_id=actor.subject_id,
            permissions=['subscriptions.manage'] if actor.subject_id in grants else [],
            permission_revision='1' if actor.subject_id in grants else None)
    monkeypatch.setattr(admin, 'probe_transport', source)
    with TestClient(application) as client:
        monkeypatch.setattr(settings, 'SUBSCRIPTION_ADMIN_SUBJECTS', 'broken-ignored-legacy-list')
        assert client.get('/api/commercial/admin/me', headers=identity()).json() == {'permissions':['subscriptions.manage']}
        forged = identity(OTHER, role='admin', email='operator@synthetic.invalid',
            user_metadata={'sub':USER}, app_metadata={'permissions':['subscriptions.manage']})
        assert client.get('/api/commercial/admin/me', headers=forged).json() == {'permissions': []}
        grants.clear()
        assert client.get('/api/commercial/admin/me', headers=identity()).json() == {'permissions': []}
        def failed(actor): raise RuntimeError('private backend failure')
        monkeypatch.setattr(admin, 'probe_transport', failed)
        response = client.get('/api/commercial/admin/me', headers=identity())
        assert response.status_code == 503
        assert response.json() == {'detail':{'code':'catalog_database_unavailable'}}
        assert client.get('/api/commercial/admin/me').status_code == 401


@pytest.mark.parametrize('path', ['/generate', '/generate//', '//generate/', '/GENERATE/',
    '/generate%2f%2f', '/generate/%2e%2e/generate-other/', '/api/auth/me/',
    '/api/commercial/admin/me%2f', '/generate/other', '/%67enerate-other/'])
def test_boundary_aliases_never_redirect_or_dispatch(application, identity, path):
    with TestClient(application) as client:
        response = client.post(path, headers=dict(identity(), **{'X-HTTP-Method-Override':'GET'}), follow_redirects=False)
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'commercial_path_unreviewed'


@pytest.mark.asyncio
async def test_real_turn_store_conflict_mapping_blocks_generation(setup, identity, monkeypatch):
    # Exercise the production RPC adapter, not a replacement admission/handler.
    # Isolated SQL suite separately verifies the actual payload-conflict rule.
    session, store = setup
    session.user_id = USER
    monkeypatch.setattr(api, '_current_user_for_session_id', lambda *args: auth.CurrentUser(USER))
    async def approve(context):
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    from app.cloud import supabase_config
    monkeypatch.setattr(supabase_config, 'get_supabase_settings', lambda: NS(
        require_configured=lambda: NS(supabase_url='https://synthetic.invalid', service_role_key=KEY)))
    observed = []
    async def fake_post(self, url, **kwargs):
        observed.append(kwargs['json'])
        return httpx.Response(200, json={'error':'payload_conflict'})
    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    monkeypatch.setattr(sg, 'new_turn_store', sg.TurnStore)
    async def forbidden(*args):
        raise AssertionError('provider reached')
        yield
    monkeypatch.setattr(sg, 'provider_stream', forbidden)
    with pytest.raises(Exception) as exc:
        await api.generate_answer(req(), request(identity()))
    assert exc.value.status_code == 409 and exc.value.detail['code'] == 'payload_conflict'
    assert len(observed) == 1 and observed[0]['p_operation'] == 'claim'
    assert observed[0]['p_user_id'] == USER and observed[0]['p_request_id'] == 'turn-1'
    assert not store.saves


def test_hash_extraction_preserves_existing_persisted_serialization():
    import hashlib
    import json
    body = req()
    previous = hashlib.sha256(json.dumps(body.model_dump(exclude={
        'request_id','retry_attempt','supersedes_request_id','recover_turn'}), sort_keys=True).encode()).hexdigest()
    assert sg.generation_request_hash(body) == previous


@pytest.mark.asyncio
@pytest.mark.parametrize('recover', [False, True])
async def test_fake_authority_retry_and_recovery_reuse_turn_without_duplicate_save(setup, identity, monkeypatch, recover):
    session, store = setup
    session.user_id = USER
    monkeypatch.setattr(api, '_current_user_for_session_id', lambda *args: auth.CurrentUser(USER))
    admissions, providers = [], []
    async def approve(context):
        admissions.append(context)
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    async def provider(*args):
        providers.append(True)
        yield 'Dependency injection supplies dependencies externally and makes classes easy to test.', None, True
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    monkeypatch.setattr(sg, 'provider_stream', provider)
    first = await api.generate_answer(req(), request(identity()))
    # Fresh requests must recheck authority; completed/recovery claims replay.
    second = await api.generate_answer(req(recover_turn=recover), request(identity()))
    assert first.answer == second.answer
    assert len(providers) == len(store.saves) == 1 and len(admissions) == 2
    assert admissions[0].operation_id == admissions[1].operation_id


@pytest.mark.asyncio
async def test_granted_request_cannot_fall_through_when_coordinator_disabled(setup, identity, monkeypatch):
    session, _ = setup
    session.user_id = USER
    async def approve(context):
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    body, scope = req(), request(identity())
    await admission.admit_buffered_answer(body, scope)
    monkeypatch.setattr(settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    with pytest.raises(Exception) as exc:
        await admission.admit_buffered_answer(body, scope)
    assert exc.value.detail['code'] == 'commercial_coordination_unavailable'


def test_admin_probe_does_not_use_startup_or_environment_subjects(application, identity, monkeypatch):
    monkeypatch.setattr(settings, 'SUBSCRIPTION_ADMIN_SUBJECTS', USER)
    monkeypatch.setenv('SUBSCRIPTION_ADMIN_SUBJECTS', OTHER)
    def no_grants(actor):
        return lambda *args: dict(contract_version='admin.access.v1', subject_id=actor.subject_id,
            permissions=[], permission_revision=None)
    monkeypatch.setattr(admin, 'probe_transport', no_grants)
    with TestClient(application) as client:
        for subject in (USER, OTHER):
            response = client.get('/api/commercial/admin/me', headers=identity(subject))
            assert response.status_code == 200 and response.json() == {'permissions': []}


@pytest.mark.asyncio
async def test_failed_turn_explicit_recovery_retry_keeps_logical_identity(setup, identity, monkeypatch):
    session, store = setup
    session.user_id = USER
    monkeypatch.setattr(api, '_current_user_for_session_id', lambda *args: auth.CurrentUser(USER))
    contexts, calls = [], []
    async def approve(context):
        contexts.append(context)
        return admission.AdmissionDecision(admission.AdmissionOutcome.ALLOWED)
    failing = True
    async def provider(*args):
        calls.append(True)
        if failing:
            raise sg.AttemptFailure('provider_error')
        yield 'Dependency injection supplies dependencies externally and makes classes easy to test.', None, True
    monkeypatch.setattr(admission, 'authority', NS(admit=approve))
    monkeypatch.setattr(sg, 'provider_stream', provider)
    with pytest.raises(Exception) as exc:
        await api.generate_answer(req(), request(identity()))
    assert exc.value.status_code == 502
    before = len(calls)
    assert before == 2 and not store.saves
    failing = False
    await api.generate_answer(req(retry_attempt=1, recover_turn=True), request(identity()))
    assert len(calls) == before+1 and len(store.saves) == 1
    assert len(contexts) == 2 and contexts[0].operation_id == contexts[1].operation_id
    assert contexts[1].retry_attempt == 1 and contexts[1].recovery


@pytest.mark.parametrize('path', ['/%67enerate/', '/generate/?path=/generate/stream'])
def test_normalized_reviewed_path_still_requires_authority(setup, application, identity, path):
    session, store = setup
    session.user_id = USER
    with TestClient(application) as client:
        response = client.post(path, json=req().model_dump(), headers=identity(), follow_redirects=False)
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'commercial_authority_unavailable'
    assert not store.rows and not store.saves
