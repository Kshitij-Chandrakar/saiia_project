import asyncio
import copy
import json
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import generate as api
from app import session_generation as sg
from app.answer_generation import AttemptFailure, GenerationStopped
from app.answer_models import MODELS

SID='11111111-1111-4111-8111-111111111111'


def test_scoped_generator_method_restore_keeps_copied_receiver_local(monkeypatch):
    class Generator:
        label = 'default'
        def generate_answer(self):
            return self.label
    default = Generator()
    proxy = sg.scoped_generator(default)
    with monkeypatch.context() as patch:
        patch.setattr(proxy, 'generate_answer', lambda: 'temporary')
        assert proxy.generate_answer() == 'temporary'
    local = copy.copy(default)
    local.label = 'request-local'
    assert local.generate_answer() == 'request-local'
    assert proxy.generate_answer() == 'default'


class Store:
    def __init__(self):
        self.rows={}
        self.saves=[]
        self.fail_save=False

    async def operation(self, op, identity, *, token=None, payload=None):
        key=(identity['p_user_id'],identity['p_session_id'],identity['p_request_id'])
        row=self.rows.get(key)
        if op=='recover':
            return dict(payload=copy.deepcopy(row['payload']))
        if op=='claim':
            if row is None or (row['state']=='failed' and identity['p_attempt']==row['attempt']+1):
                row=self.rows[key]=dict(state='processing',token=str(identity['p_attempt']),payload=payload,attempt=identity['p_attempt'])
                return dict(state='claimed',token=row['token'])
            return copy.deepcopy(row)
        if row['token']!=token:
            raise sg.TurnStateError('stale_attempt')
        if op=='check':
            return dict(state=row['state'])
        if op=='checkpoint':
            row.update(state='checkpoint',payload=payload)
        elif op=='complete':
            if self.fail_save:
                raise sg.TurnStateError('persistence_unavailable')
            if row['state']!='completed':
                self.saves.append(copy.deepcopy(row['payload']))
                row['state']='completed'
        elif op=='fail':
            row['state']='failed'
        elif op=='cancel' and row['state']=='processing':
            row['state']='cancelled'
        return dict(state=row['state'])


@pytest.fixture
def setup(monkeypatch):
    from app.cloud import interview_sessions
    monkeypatch.setattr(interview_sessions,'session_model_backend_ready',lambda:True)
    store=Store()
    session=NS(id=SID,user_id='owner',status='active',selected_model_key=MODELS[0].key,
               selected_resume_id=None,target_role='engineer',company_name='company',job_description_preview='authorized JD')
    monkeypatch.setattr(sg,'new_turn_store',lambda:store)
    monkeypatch.setattr(api.settings,'ENABLE_SESSION_ANSWER_MODELS',True)
    monkeypatch.setattr(api.settings,'ENABLE_SEMANTIC_VALIDATION',False)
    monkeypatch.setattr(api.settings,'ENABLE_CONTROLLED_ANSWER_VARIATION',False)
    monkeypatch.setattr(api,'_current_user_for_session_id',lambda *args:NS(user_id='owner'))
    monkeypatch.setattr(api,'_new_cloud_interview_session_service',lambda:NS(get_session=lambda **kwargs:session))
    monkeypatch.setattr(api,'_generation_job_context',lambda *args,**kwargs:{'saved':True,'job_description':'authorized JD','target_role':'engineer'})
    monkeypatch.setattr(api,'_retrieve_resume_context',lambda **kwargs:{'retrieval_used':False,'retrieved_chunks':[],'retrieval_ms':0})
    return session,store


def request():
    return Request({'type':'http','headers':[], 'state':{'grpc_cloud_context_only':True}})


def req(turn='turn-1', **kwargs):
    return api.GenerateRequest(question='What is dependency injection?',category='technical',
        session_id=SID,request_id=turn,profile_context_used=False,**kwargs)


async def events(body, route=api.generate_answer_stream):
    response=await route(body,request())
    return [json.loads(line) async for line in response.body_iterator]


@pytest.mark.asyncio
@pytest.mark.parametrize('model',MODELS,ids=lambda m:m.key)
async def test_actual_http_routes_selected_model_and_saves_once(setup,monkeypatch,model):
    session,store=setup
    session.selected_model_key=model.key
    calls=[]
    async def provider(client,current,prepared,key):
        calls.append((current,prepared))
        yield 'Dependency injection supplies dependencies from outside a class, making code easier to test.', current.api_model+'-reported',True
    monkeypatch.setattr(sg,'provider_stream',provider)
    items=await events(req())
    assert items[-1]['type']=='done'
    assert [e['sequence'] for e in items]==list(range(len(items)))
    assert any(e['type']=='metadata' for e in items), (items, len(calls), store.rows)
    result=next(e['metadata'] for e in items if e['type']=='metadata')
    assert result['selected_model_key']==model.key
    assert result['actual_api_model']==model.api_model and result['reported_model']==model.api_model+'-reported'
    assert len(calls)==len(store.saves)==1
    replay=await api.generate_answer(req(),request())
    assert replay.answer==result['answer'] and len(calls)==len(store.saves)==1


@pytest.mark.asyncio
async def test_failed_partial_is_replaced_not_mixed(setup,monkeypatch):
    _,store=setup
    calls=[]
    async def provider(client,current,prepared,key):
        calls.append((current,prepared))
        if current.provider=='openai':
            yield 'FAILED PARTIAL',None,False
            raise AttemptFailure('provider_unavailable')
        yield 'Dependency injection supplies dependencies externally, making classes easier to test.', 'groq-version',True
    monkeypatch.setattr(sg,'provider_stream',provider)
    items=await events(req())
    result=next(e['metadata'] for e in items if e['type']=='metadata')
    assert len(calls)==2 and calls[0][1]==calls[1][1]
    assert 'FAILED PARTIAL' not in result['answer']
    assert result['fallback_used'] and result['actual_provider']=='groq'
    assert len(store.saves)==1 and store.saves[0]['result']['answer']==result['answer']
    assert any(e['type']=='replace' and e['answer']=='' for e in items)


@pytest.mark.asyncio
@pytest.mark.parametrize('key,count',[(MODELS[0].key,2),('gpt-oss-120b',1)])
async def test_terminal_failure_and_explicit_retry(setup,monkeypatch,key,count):
    session,store=setup
    session.selected_model_key=key
    calls=[]
    async def provider(*args):
        calls.append(args)
        raise AttemptFailure('rate_limit')
        yield
    monkeypatch.setattr(sg,'provider_stream',provider)
    items=await events(req())
    assert next(e for e in items if e['type']=='error')['error']=='generation_failed'
    assert len(calls)==count and not store.saves
    await events(req(retry_attempt=1,recover_turn=True))
    assert len(calls)==count*2 and len(store.rows)==1


@pytest.mark.asyncio
async def test_persistence_retry_uses_checkpoint_not_provider(setup,monkeypatch):
    _,store=setup
    calls=[]
    async def provider(*args):
        calls.append(args)
        yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    store.fail_save=True
    items=await events(req())
    assert next(e for e in items if e['type']=='error')['error']=='persistence_unavailable'
    store.fail_save=False
    await events(req(recover_turn=True))
    assert len(calls)==1 and len(store.saves)==1


@pytest.mark.asyncio
async def test_duplicate_inflight_and_identical_question_new_turn(setup,monkeypatch):
    _,store=setup
    entered=asyncio.Event()
    release=asyncio.Event()
    calls=[]
    async def provider(*args):
        calls.append(args)
        entered.set()
        await release.wait()
        yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    task=asyncio.create_task(events(req()))
    await asyncio.wait_for(entered.wait(),3)
    with pytest.raises(HTTPException) as pending:
        await events(req())
    assert pending.value.status_code==409
    release.set()
    await task
    await events(req('turn-2'))
    assert len(calls)==len(store.saves)==2


@pytest.mark.asyncio
async def test_cancellation_does_not_fallback_or_save(setup,monkeypatch):
    _,store=setup
    entered=asyncio.Event()
    closed=[]
    async def provider(*args):
        try:
            entered.set()
            await asyncio.sleep(10)
            yield '',None,False
        finally:
            closed.append(True)
    monkeypatch.setattr(sg,'provider_stream',provider)
    task=asyncio.create_task(events(req()))
    await asyncio.wait_for(entered.wait(),3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(closed)==1 and not store.saves


@pytest.mark.asyncio
async def test_ended_session_stops_before_provider(setup):
    session,store=setup
    session.status='ended'
    with pytest.raises(HTTPException) as ended:
        await events(req())
    assert ended.value.status_code==409 and not store.rows

@pytest.mark.asyncio
async def test_missing_gemini_key_actual_handler_falls_back(setup,monkeypatch):
    session,store=setup
    session.selected_model_key='gemini-3.5-flash-lite'
    monkeypatch.setattr(api.settings,'GEMINI_API_KEY','')
    calls=[]
    original=sg.provider_stream
    async def provider(client,model,prepared,key):
        calls.append(model.provider)
        if model.provider=='gemini':
            async for event in original(client,model,prepared,key):
                yield event
        else:
            yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    items=await events(req())
    result=next(e['metadata'] for e in items if e['type']=='metadata')
    assert calls==['gemini','groq']
    assert result['selected_model_key']=='gemini-3.5-flash-lite' and result['actual_provider']=='groq'
    assert len(store.saves)==1


@pytest.mark.asyncio
async def test_real_grpc_contract_failure_then_next_turn_and_partial_replacement(setup,monkeypatch):
    import grpc
    from app import grpc_server,grpc_answer_pipeline
    from app.grpc_cloud_context import GrpcCloudContext
    from app.grpc_generated import interview_realtime_pb2 as pb
    from app.grpc_generated import interview_realtime_pb2_grpc as rpc
    from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
    from app.api.question_detect import classifier
    _,store=setup
    for name in ('USE_GRPC_AUTO_PIPELINE','GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED','USE_GRPC_CLOUD_CONTEXT_PIPELINE'):
        monkeypatch.setattr(grpc_server.settings,name,True)
    monkeypatch.setattr(grpc_server,'AUTO_COOLDOWN_SECONDS',.01)
    cloud=NS(session_id=SID,request=request(),load=lambda:dict(profile_context_used=False))
    def forbidden_save(*args):
        raise AssertionError('second persistence owner')
    cloud.save=forbidden_save
    monkeypatch.setattr(GrpcCloudContext,'authorize',lambda *args:cloud)
    async def detect(text, **kwargs): return text,''
    monkeypatch.setattr(grpc_answer_pipeline,'detect_intake_question',detect)
    monkeypatch.setattr(classifier,'classify_question',lambda text:'technical')
    class Socket:
        def __init__(self): self.events=asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self,data): pass
        async def close(self): pass
    socket=Socket()
    async def connect(self):
        await socket.events.put('{"type":"Begin"}')
        return socket
    monkeypatch.setattr(AssemblyAIStreamingBridge,'connect',connect)
    fail=True
    calls=[]
    async def provider(client,model,prepared,key):
        calls.append(model.provider)
        if model.provider=='openai':
            yield 'FAILED PROVISIONAL',None,False
            raise AttemptFailure('provider_unavailable')
        if fail: raise AttemptFailure('rate_limit')
        yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    server,port=await grpc_server.start_server(port=0)
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=10)
            await call.write(pb.InterviewClientEvent(session_id='transport',request_id='start-id',start_session=pb.StartSession(
                mode='auto_pipeline',source='microphone',cloud_context_requested=True,active_session_id=SID)))
            async def until(predicate):
                while True:
                    item=await call.read()
                    assert item is not grpc.aio.EOF
                    if predicate(item): return item
            await until(lambda item:item.status.code=='answer_stream_enabled')
            async def turn(text,order):
                await socket.events.put(json.dumps(dict(type='Turn',transcript=text,turn_order=order,end_of_turn=True)))
            await turn('Explain dependency injection',0)
            failure=await until(lambda item:item.HasField('answer_error'))
            assert failure.answer_error.code=='generation_failed'
            assert failure.request_id and failure.request_id!='start-id'
            await until(lambda item:item.status.code=='auto_listening')
            fail=False
            await turn('Explain inversion of control',1)
            complete=await until(lambda item:item.HasField('answer_completed'))
            assert complete.request_id!=failure.request_id
            assert 'FAILED PROVISIONAL' not in complete.answer_completed.text
            assert 'dependencies' in complete.answer_completed.text
            assert calls==['openai','groq','openai','groq'] and len(store.saves)==1
            assert {key[2] for key in store.rows}=={failure.request_id,complete.request_id}
            # Existing wire contract carries turn identity, but has no retry-attempt field.
            assert 'retry_attempt' not in pb.InterviewClientEvent.DESCRIPTOR.fields_by_name
            await call.write(pb.InterviewClientEvent(session_id='transport',end_session=pb.Empty()))
            await until(lambda item:item.status.code=='ended')
            call.cancel()
    finally:
        await server.stop(0)


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['primary','fallback'])
@pytest.mark.parametrize('stop',['logout','session_end','supersession'])
async def test_lifecycle_monitor_stops_current_provider_without_fallback_or_save(setup,monkeypatch,phase,stop):
    session,store=setup
    entered=asyncio.Event()
    calls=[]
    closed=[]
    async def provider(client,model,prepared,key):
        calls.append(model.provider)
        if phase=='fallback' and model.provider=='openai':
            raise AttemptFailure('provider_unavailable')
        try:
            entered.set()
            await asyncio.sleep(10)
            yield '',None,True
        finally:
            closed.append(model.provider)
    monkeypatch.setattr(sg,'provider_stream',provider)
    task=asyncio.create_task(events(req()))
    await asyncio.wait_for(entered.wait(),3)
    if stop=='logout':
        def reject(*args): raise HTTPException(401)
        monkeypatch.setattr(api,'_current_user_for_session_id',reject)
    elif stop=='session_end': session.status='ended'
    else: next(iter(store.rows.values()))['state']='cancelled'
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task,2)
    assert len(calls)==(2 if phase=='fallback' else 1)
    assert len(closed)==1 and not store.saves


@pytest.mark.asyncio
async def test_corrections_use_attempt_model_and_common_deadline(setup,monkeypatch):
    from app.answer_generation import PreparedAnswer
    session,_=setup
    session.selected_model_key='gemini-3.6-flash'
    calls=[]
    original=sg.AttemptRun.primary
    def with_correction(self,**kwargs):
        result=original(self,**kwargs)
        # Exercise the same facade installed on all existing rewrite helpers.
        self.instance.openai_provider.generate(instructions='correct',input_text='same answer')
        return result
    monkeypatch.setattr(sg.AttemptRun,'primary',with_correction)
    async def provider(client,model,prepared,key):
        calls.append((model.key,prepared.instructions))
        yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    await events(req())
    assert len(calls)==2 and all(key=='gemini-3.6-flash' for key,_ in calls)
    assert calls[-1][1]=='correct'


def test_request_rejects_client_model_provider_overrides():
    from pydantic import ValidationError
    for field in ('model','provider','selected_model_key','provider_url'):
        with pytest.raises(ValidationError): req(**{field:'arbitrary'})

@pytest.mark.asyncio
async def test_handler_deadline_closes_primary_and_fallback_uses_remaining_budget(setup,monkeypatch):
    _,store=setup
    for name,value in [('FIRST_TOKEN',.03),('IDLE',.02),('OVERALL',.2),('FALLBACK_RESERVE',.06)]:
        monkeypatch.setattr(api.settings,'ANSWER_MODEL_'+name+'_SECONDS',value)
    calls=[]
    closed=[]
    async def provider(client,model,prepared,key):
        calls.append(model.provider)
        try:
            if model.provider=='openai': await asyncio.sleep(1)
            yield 'Dependency injection supplies dependencies externally.',None,True
        finally: closed.append(model.provider)
    monkeypatch.setattr(sg,'provider_stream',provider)
    items=await events(req())
    assert calls==closed==['openai','groq'] and len(store.saves)==1
    assert any(e['type']=='metadata' for e in items)


def test_variation_history_fingerprint_is_user_and_session_scoped():
    from app.nlp.answer_variation import variation_scope,context_fingerprint
    keys=[]
    for scope in [('one','session-a'),('two','session-a'),('one','session-b')]:
        token=variation_scope.set(scope)
        try:
            keys.append(context_fingerprint(profile={},retrieved_snippets=[],job_context={},profile_context_enabled=False))
        finally: variation_scope.reset(token)
    assert len(set(keys))==3

@pytest.mark.asyncio
async def test_persisted_custom_binding_routes_after_removal(setup,monkeypatch):
    from app.answer_models import parse_catalog,DEFAULT_ENTRIES,model_binding,MODEL_CATALOG
    session,store=setup
    choices,_,_=parse_catalog(DEFAULT_ENTRIES+',groq:example-compatible-model',
        'gemini:gemini-3.5-flash-lite','groq:openai/gpt-oss-120b')
    selected=choices[-1]
    assert selected.key not in MODEL_CATALOG
    session.selected_model_key=selected.key
    session.selected_model_binding=model_binding(selected)
    calls=[]
    async def provider(client,model,prepared,key):
        calls.append((model.provider,model.api_model,model.api_profile))
        yield 'Dependency injection supplies dependencies externally.',None,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    result=next(e['metadata'] for e in await events(req()) if e['type']=='metadata')
    assert calls==[('groq','example-compatible-model','groq-chat')]
    assert result['selected_model_key']==selected.key and result['actual_api_model']==selected.api_model
    assert len(store.saves)==1
