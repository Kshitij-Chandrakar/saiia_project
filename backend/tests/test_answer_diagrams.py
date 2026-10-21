"""Offline diagram contracts; synthetic data only."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import answer_diagrams as api
from app.auth.supabase_auth import get_current_user
from app.cloud.answer_diagrams import DiagramStore, DiagramError


@pytest.fixture(autouse=True)
def isolated_config_caches():
    from app.cloud.supabase_config import get_supabase_settings
    from app.auth.supabase_auth import get_auth_verification_config
    from app.cloud.answer_diagrams import diagram_store
    for cached in (get_supabase_settings, get_auth_verification_config, diagram_store):
        cached.cache_clear()
    yield
    for cached in (get_supabase_settings, get_auth_verification_config, diagram_store):
        cached.cache_clear()


def test_source_does_not_trust_metadata():
    store = DiagramStore.__new__(DiagramStore)
    store.request = Mock(side_effect=[[dict(id='t', source='answer', question_text='synthetic', answer_text='synthetic',
                                           metadata={'answer_type': 'system_design'})], []])
    descriptor, _ = store.source('owner', 'session', request='request')
    assert descriptor['eligible'] is False
    assert store.request.call_args_list[0].kwargs['params']['user_id'] == 'eq.owner'
    assert 'metadata' not in descriptor


def test_source_descriptor_is_narrow():
    store = DiagramStore.__new__(DiagramStore)
    store.request = Mock(side_effect=[[dict(id='t', source='auto', question_text='synthetic', answer_text='synthetic')],
        [dict(source_revision='v1:hash', answer_type='system_design', provenance='managed_generation')]])
    descriptor, _ = store.source('owner', 'session', transcript='t')
    assert descriptor['eligible']
    assert not {'question_text', 'answer_text', 'token', 'metadata'} & descriptor.keys()


def test_missing_source_and_migration_stamp_compatibility(monkeypatch):
    store = DiagramStore.__new__(DiagramStore)
    store.request = Mock(return_value=[])
    with pytest.raises(DiagramError, match='source_not_found'):
        store.source('owner', 'session', transcript='t')
    from app.cloud.interview_transcripts import SupabaseInterviewTranscriptClient
    import requests
    client = SupabaseInterviewTranscriptClient.__new__(SupabaseInterviewTranscriptClient)
    client._session = Mock(); client._rest_url = 'https://synthetic.invalid'; client._headers = {}
    client._session.post.return_value.status_code = 404
    client.stamp_generated_answer('owner', 'session', 't', 'synthetic', 'synthetic', 'system_design')
    client._session.post.side_effect = requests.RequestException('synthetic')
    client.stamp_generated_answer('owner', 'session', 't', 'synthetic', 'synthetic', 'system_design')

import asyncio
import copy
import json
import httpx
from app.services.answer_diagram_service import validate_graph, generate_graph, DiagramService
from app.config import settings

ANSWER = 'API sends tasks to Queue. Queue sends tasks to API.'
def graph():
    return dict(status='ready', nodes=[dict(id='api', label='API', kind='service', evidence_quote='API'),
        dict(id='queue', label='Queue', kind='queue', evidence_quote='Queue')],
        edges=[dict(source='api', target='queue', label='tasks', evidence_quote='API sends tasks to Queue.')])

@pytest.mark.parametrize('mutation', [
    lambda g:g.update(extra='no'), lambda g:g['nodes'][0].update(x=2),
    lambda g:g['nodes'][0].update(label='<script>'), lambda g:g['nodes'][0].update(label='https://example.invalid'),
    lambda g:g['nodes'][0].update(id='bad id'), lambda g:g['nodes'][0].update(kind='svg'),
    lambda g:g['nodes'][1].update(id='api'), lambda g:g['edges'][0].update(target='missing'),
    lambda g:g['edges'].append(copy.deepcopy(g['edges'][0])), lambda g:g['nodes'][0].update(evidence_quote='invented'),
    lambda g:g['nodes'][0].update(label='x'*81), lambda g:g['nodes'][0].update(evidence_quote='x'*241),
    lambda g:g.update(nodes=g['nodes']*11), lambda g:g.update(edges=g['edges']*33),
    lambda g:g.update(status='insufficient_detail'), lambda g:g.update(edges=[]),
])
def test_graph_rejects_invalid_or_unsupported(mutation):
    payload=graph(); mutation(payload)
    with pytest.raises(DiagramError,match='invalid_graph'): validate_graph(payload,ANSWER)


def test_cycles_and_insufficient_detail():
    payload=graph(); payload['edges'].append(dict(source='queue',target='api',label='return',evidence_quote='Queue sends tasks to API.'))
    assert len(validate_graph(payload,ANSWER)['edges'])==2
    assert validate_graph(dict(status='insufficient_detail',nodes=[],edges=[]),ANSWER)['status']=='insufficient_detail'

@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected',[('ok',None),('refusal','refused'),('incomplete','incomplete'),
    ('malformed','provider_failed'),('large','invalid_graph'),('http','provider_failed'),('timeout','timeout')])
async def test_provider_single_bounded_call(monkeypatch,caplog,mode,expected):
    monkeypatch.setattr(settings,'OPENAI_API_KEY','synthetic-diagram-key')
    monkeypatch.setattr(settings,'DIAGRAM_MODEL','gpt-4.1-mini')
    calls=[]
    async def handler(request):
        calls.append(request)
        body=json.loads(request.content)
        assert body['store'] is False and body['model']=='gpt-4.1-mini'
        assert body['text']['format']['strict'] is True
        assert not {'tools','reasoning','previous_response_id'} & body.keys()
        if mode=='timeout': raise httpx.ReadTimeout('synthetic')
        if mode=='http': return httpx.Response(503,json={'error':'DO NOT EXPOSE'})
        if mode=='large': return httpx.Response(200,content=b' '*131073)
        if mode=='malformed': return httpx.Response(200,content=b'invalid')
        contents=[dict(type='refusal',refusal='DO NOT EXPOSE')] if mode=='refusal' else [dict(type='output_text',text=json.dumps(graph()))]
        return httpx.Response(200,json=dict(status='incomplete' if mode=='incomplete' else 'completed',model='gpt-4.1-mini-2025-04-14',output=[dict(content=contents)]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if expected:
            with pytest.raises(DiagramError,match=expected) as exc: await generate_graph('synthetic',ANSWER,client=client)
            assert 'DO NOT EXPOSE' not in str(exc.value)
        else: assert (await generate_graph('synthetic',ANSWER,client=client))[0]==graph()
    assert len(calls)==1
    assert 'synthetic-diagram-key' not in caplog.text and ANSWER not in caplog.text

class MemoryStore:
    def __init__(self): self.row={'state':'absent'}; self.ops=[]
    def source(self,*args,**kwargs): return dict(eligible=True,source_revision='revision'),dict(question_text='synthetic',answer_text=ANSWER)
    def operation(self,op,*identity,**kw):
        self.ops.append(op)
        if op in ('claim','retry'):
            if self.row['state']=='absent' or (op=='retry' and self.row['state']=='failed' and self.row['attempt']==1):
                self.row=dict(state='processing',attempt=self.row.get('attempt',0)+1,token='private',operation_id=identity[4],source_revision='revision')
                return dict(self.row,claimed=True)
        if op=='checkpoint': self.row.update(state='checkpoint',graph=kw['graph'])
        if op=='finalize': self.row.update(state='ready')
        if op=='fail': self.row.update(state='failed',failure_code=kw['code'])
        if op=='cancel': self.row.update(state='cancelled',graph=None)
        return dict(self.row)

@pytest.mark.asyncio
async def test_gated_concurrent_saved_replay_and_disabled_reads(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    store=MemoryStore(); started=asyncio.Event(); release=asyncio.Event(); calls=[]
    async def provider(*args): calls.append(1); started.set(); await release.wait(); return graph(),'gpt-4.1-mini'
    service=DiagramService(store,provider); identity=('owner','session','transcript','revision','operation')
    task=asyncio.create_task(service.run(identity))
    await asyncio.wait_for(started.wait(),2)
    assert (await service.run((*identity[:4],'other')))['state']=='processing'
    release.set(); result=await asyncio.wait_for(task,2)
    assert result['state']=='ready' and result['graph']==graph() and 'token' not in result
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',False)
    assert (await service.run(identity))['state']=='ready' and calls==[1]
    assert (await service.read(identity))['state']=='ready'

@pytest.mark.asyncio
async def test_checkpoint_recovery_disabled_zero_generation(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',False)
    store=MemoryStore(); store.row=dict(state='checkpoint',graph=graph(),token='private',operation_id='operation')
    service=DiagramService(store,Mock(side_effect=AssertionError('no generation')))
    assert (await service.run(('owner','session','t','revision','operation')))['state']=='ready'

@pytest.mark.asyncio
async def test_cancel_awaits_producer(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    store=MemoryStore(); started=asyncio.Event(); terminated=asyncio.Event()
    async def provider(*args):
        started.set()
        try: await asyncio.Event().wait()
        finally: terminated.set()
    service=DiagramService(store,provider); identity=('owner','session','t','revision','operation')
    task=asyncio.create_task(service.run(identity)); await asyncio.wait_for(started.wait(),2)
    assert (await service.cancel(identity))['state']=='cancelled'
    await asyncio.gather(task,return_exceptions=True)
    assert terminated.is_set() and not service.tasks
    assert 'checkpoint' not in store.ops

@pytest.mark.asyncio
async def test_explicit_retry_only_and_uncertain_no_call(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    store=MemoryStore(); calls=[]
    async def provider(*args): calls.append(1); raise DiagramError('refused')
    service=DiagramService(store,provider); identity=('owner','session','t','revision','first')
    assert (await service.run(identity))['retry_allowed']
    assert (await service.run(identity))['state']=='failed' and len(calls)==1
    assert not (await service.run((*identity[:4],'retry'),retry=True))['retry_allowed']
    assert len(calls)==2
    store.row['state']='uncertain'
    assert (await service.run(identity,retry=True))['state']=='uncertain' and len(calls)==2

def test_authenticated_route_and_narrow_request(monkeypatch):
    app=FastAPI(); app.include_router(api.router,prefix='/api/interview-sessions')
    app.dependency_overrides[get_current_user]=lambda: SimpleNamespace(user_id='owner')
    store=Mock(); store.source.return_value=({'eligible':True}, {})
    monkeypatch.setattr(api,'diagram_store',lambda:store)
    sid='30000000-0000-4000-8000-000000000001'; tid='40000000-0000-4000-8000-000000000001'
    with TestClient(app) as client:
        assert client.get(f'/api/interview-sessions/{sid}/answer-sources?transcript_id={tid}').status_code==200
        assert store.source.call_args.args==('owner',sid)
        assert client.get(f'/api/interview-sessions/{sid}/answer-sources').status_code==400
        for key in ('answer_text','user_id','model','metadata'):
            result=client.post(f'/api/interview-sessions/{sid}/transcript-entries/{tid}/diagram',json=dict(
                source_revision='v1:'+'a'*64,operation_id=tid,**{key:'forged'}))
            assert result.status_code==422
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.get(f'/api/interview-sessions/{sid}/answer-sources?transcript_id={tid}').status_code in (401,503)

@pytest.mark.asyncio
async def test_total_deadline_and_content_free_diagnostics(monkeypatch,caplog):
    monkeypatch.setattr(settings,'OPENAI_API_KEY','synthetic-authorization-must-not-log')
    monkeypatch.setattr(settings,'DIAGRAM_TIMEOUT_SECONDS',0.02)
    finished=asyncio.Event(); calls=[]
    async def handler(request):
        calls.append(1)
        try: await asyncio.Event().wait()
        finally: finished.set()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DiagramError,match='timeout'):
            await generate_graph('synthetic private question',ANSWER,client=client)
    assert finished.is_set() and len(calls)==1
    assert 'synthetic-authorization-must-not-log' not in caplog.text and ANSWER not in caplog.text

@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['checkpoint','finalize'])
async def test_lost_ack_reconciles_without_new_provider(monkeypatch,stage):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    store=MemoryStore(); original=store.operation; lost=[False]; calls=[]
    def operation(op,*args,**kwargs):
        result=original(op,*args,**kwargs)
        if op==stage and not lost[0]:
            lost[0]=True
            raise DiagramError()
        return result
    store.operation=operation
    async def provider(*args): calls.append(1); return graph(),'gpt-4.1-mini'
    service=DiagramService(store,provider); identity=('owner','session','t','revision','operation')
    assert (await service.run(identity))['state']=='ready'
    assert (await service.run(identity))['state']=='ready' and calls==[1]

@pytest.mark.asyncio
async def test_claim_lost_ack_does_not_generate_or_retry(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    store=MemoryStore(); original=store.operation
    def operation(op,*args,**kwargs):
        result=original(op,*args,**kwargs)
        if op=='claim': raise DiagramError()
        return result
    store.operation=operation
    service=DiagramService(store,Mock(side_effect=AssertionError('must not generate')))
    identity=('owner','session','t','revision','operation')
    with pytest.raises(DiagramError): await service.run(identity)
    assert (await service.run(identity))['state']=='processing'

@pytest.mark.asyncio
async def test_disabled_or_missing_config_never_claims(monkeypatch):
    store=MemoryStore(); service=DiagramService(store,Mock(side_effect=AssertionError('no generation')))
    identity=('owner','session','t','revision','operation')
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',False)
    with pytest.raises(DiagramError,match='generation_disabled'): await service.run(identity)
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True); monkeypatch.setattr(settings,'OPENAI_API_KEY','')
    with pytest.raises(DiagramError,match='configuration_missing'): await service.run(identity)
    assert store.ops==['read','read']

def test_utf8_serialized_graph_bound():
    quote='\U0001f600'*240
    payload=dict(status='ready',nodes=[dict(id=f'n{i}',label='\U0001f600'*80,kind='service',evidence_quote=quote) for i in range(20)],edges=[])
    for i in range(20):
        for j in range(20):
            if i!=j and len(payload['edges'])<32:
                payload['edges'].append(dict(source=f'n{i}',target=f'n{j}',label='\U0001f600'*80,evidence_quote=quote))
    with pytest.raises(DiagramError,match='invalid_graph'): validate_graph(payload,quote)

@pytest.mark.parametrize('replayed,internal',[(False,False),(True,False),(False,True)])
def test_unmanaged_trusted_stamp_only_after_new_server_save(monkeypatch,replayed,internal):
    from app.api import generate as generation
    from starlette.requests import Request
    service=Mock()
    service.create_transcript_entry.return_value=SimpleNamespace(replayed=replayed,record=SimpleNamespace(id='transcript'))
    monkeypatch.setattr(generation,'_new_cloud_transcript_service',lambda:service)
    monkeypatch.setattr(generation,'_current_user_for_session_id',lambda *args:SimpleNamespace(user_id='owner'))
    req=generation.GenerateRequest(question='Design a queue',category='technical',session_id='30000000-0000-4000-8000-000000000001')
    response=generation.GenerateResponse(answer=ANSWER,provider='synthetic',model='synthetic',fallback_used=False,generation_ms=1,answer_type='system_design')
    request=Request({'type':'http','headers':[],'state':{'session_generation_internal':internal}})
    result=generation._store_transcript_for_response(req=req,request=request,response=response,source='answer',screen_question_type=None)
    assert result.transcript_entry_stored
    assert service.create_transcript_entry.call_count==int(not internal)
    assert service.stamp_generated_answer.call_count==int(not replayed and not internal)
    if not replayed and not internal:
        assert service.stamp_generated_answer.call_args.args[-1]=='system_design'

@pytest.mark.asyncio
async def test_capacity_and_shutdown_await_all_producers(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',True)
    class SeparateStore(MemoryStore):
        def __init__(self): self.stores={}
        def operation(self,op,*identity,**kwargs):
            store=self.stores.setdefault(identity[2],MemoryStore())
            return store.operation(op,*identity,**kwargs)
    store=SeparateStore(); begun=asyncio.Event(); calls=[]; ended=[]
    async def provider(*args):
        calls.append(1)
        if len(calls)==4: begun.set()
        try: await asyncio.Event().wait()
        finally: ended.append(1)
    service=DiagramService(store,provider)
    tasks=[asyncio.create_task(service.run(('owner','session',f't{i}','revision',f'op{i}'))) for i in range(4)]
    await asyncio.wait_for(begun.wait(),2)
    # Four diagram calls are gated at the provider boundary. Real answer display
    # and a synthetic STT/control packet must still progress on this event loop.
    from app.answer_generation import GenerationControl, GenerationBudget, Deadlines
    from app.answer_streaming import DisplayStream
    answer_queue=asyncio.Queue(maxsize=1); packet_queue=asyncio.Queue(maxsize=1)
    display=DisplayStream(answer_queue,GenerationControl(),GenerationBudget(Deadlines()))
    revision=await display.begin(0)
    await asyncio.wait_for(display.delta('synthetic live prefix',0,revision),2)
    await packet_queue.put('synthetic control packet')
    assert (await asyncio.wait_for(answer_queue.get(),2))['text']=='synthetic live prefix'
    assert await asyncio.wait_for(packet_queue.get(),2)=='synthetic control packet'
    assert len(ended)==0
    with pytest.raises(DiagramError,match='busy'):
        await service.run(('owner','session','t5','revision','op5'))
    await service.shutdown(); await asyncio.gather(*tasks,return_exceptions=True)
    assert len(calls)==4 and len(ended)==4 and not service.tasks
    assert all(value.row['state']=='cancelled' for key,value in store.stores.items() if key!='t5')


@pytest.mark.parametrize('question,eligible', [('Explain system design.',False),('Design a URL shortener.',True)])
def test_future_trusted_task_intent_controls_diagram_eligibility(question,eligible):
    from app.nlp.answer_planner import build_answer_plan
    plan=build_answer_plan(question=question,category='technical')
    store=DiagramStore.__new__(DiagramStore)
    store.request=Mock(side_effect=[[
        dict(id='synthetic',source='auto',question_text=question,answer_text='Canonical synthetic answer.')],
        [dict(source_revision='v1:synthetic',answer_type=plan.as_metadata()['answer_type'],provenance='managed_generation')]])
    descriptor,_=store.source('synthetic-owner','synthetic-session',transcript='synthetic')
    assert descriptor['eligible'] is eligible


@pytest.mark.parametrize('db_code,http_status,expected', [('PGRST205',404,'schema_unavailable'),('42P01',400,'schema_unavailable'),('42501',403,'unavailable'),('other',500,'unavailable')])
def test_storage_errors_are_distinct_and_content_free(monkeypatch,caplog,db_code,http_status,expected):
    import requests
    store=DiagramStore.__new__(DiagramStore);store.url='https://synthetic.invalid';store.headers={'Authorization':'synthetic-secret-must-not-log'}
    response=Mock(status_code=http_status)
    response.json.return_value={'code':db_code,'message':'SYNTHETIC_INTERVIEW_CONTENT_MUST_NOT_LOG'}
    monkeypatch.setattr(requests,'request',lambda *a,**kw:response)
    with pytest.raises(DiagramError,match=expected):store.request('GET','/interview_answer_sources')
    assert 'SYNTHETIC_INTERVIEW' not in caplog.text and 'synthetic-secret' not in caplog.text
    assert 'stage=source_provenance' in caplog.text

@pytest.mark.parametrize('failure,state,status', [('schema_unavailable','unavailable',200),('source_pending','pending',200),('unavailable',None,503),('configuration_missing',None,503)])
def test_resolve_expected_states_do_not_mask_service_errors(monkeypatch,failure,state,status):
    app=FastAPI();app.include_router(api.router,prefix='/api/interview-sessions')
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(user_id='synthetic-owner')
    store=Mock();store.source.side_effect=DiagramError(failure)
    monkeypatch.setattr(api,'diagram_store',lambda:store)
    with TestClient(app) as client:
        response=client.get('/api/interview-sessions/30000000-0000-4000-8000-000000000001/answer-sources?request_id=synthetic-request')
    assert response.status_code==status
    if state:
        assert response.json()['state']==state and response.json()['eligible'] is False
    else:assert response.json()['detail']['code']==failure


def test_pending_request_is_not_a_missing_transcript():
    store=DiagramStore.__new__(DiagramStore);store.request=Mock(return_value=[])
    with pytest.raises(DiagramError,match='source_pending'):store.source('owner','session',request='synthetic')
    with pytest.raises(DiagramError,match='source_not_found'):store.source('owner','session',transcript='synthetic')


def test_disabled_generation_still_resolves_saved_sources(monkeypatch):
    monkeypatch.setattr(settings,'DIAGRAM_GENERATION_ENABLED',False)
    store=Mock();store.source.return_value=({'eligible':True,'source_revision':'synthetic'}, {})
    monkeypatch.setattr(api,'diagram_store',lambda:store)
    result=api.resolve_source(__import__('uuid').UUID('30000000-0000-4000-8000-000000000001'),SimpleNamespace(user_id='owner'),request_id='saved')
    assert result['eligible'] and result['generation_enabled'] is False
    assert store.source.call_count==1
