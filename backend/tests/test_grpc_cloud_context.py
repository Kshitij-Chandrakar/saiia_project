import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grpc_cloud_context as cloud
from app.grpc_generated import interview_realtime_pb2 as pb

SID='11111111-1111-4111-8111-111111111111'
RID='22222222-2222-4222-8222-222222222222'
JID='33333333-3333-4333-8333-333333333333'

@pytest.fixture
def services(monkeypatch):
    session=NS(id=SID, user_id='owner', status='active', selected_resume_id=RID, job_context_id=JID, target_role='role', company_name='company', job_description_preview='preview')
    calls=[]
    monkeypatch.setattr(cloud, 'get_current_user', lambda request: NS(user_id='owner'))
    def get_session(**kwargs):
        assert kwargs == dict(user_id='owner', session_id=SID)
        return session
    monkeypatch.setattr(cloud,'CloudInterviewSessionService',lambda: NS(get_session=get_session))
    monkeypatch.setattr(cloud,'CloudResumeService',lambda: NS(get_status=lambda **kwargs: calls.append(('resume', kwargs))))
    monkeypatch.setattr(cloud,'CloudJobContextService',lambda: NS(get_context=lambda **kwargs: NS(job_description='authorized job')))
    monkeypatch.setattr(cloud,'CloudInterviewTranscriptService',lambda: NS(create_transcript_entry=lambda **kwargs: calls.append(('save', kwargs))))
    return session,calls

def start(**kwargs):
    return pb.StartSession(active_session_id=SID, selected_resume_id=RID, selected_job_context_id=JID, **kwargs)

def test_missing_invalid_auth_and_session(monkeypatch,services):
    with pytest.raises(cloud.CloudContextRejected,match='auth_unavailable'): cloud.GrpcCloudContext.authorize(start(), [])
    def invalid(request): raise RuntimeError('private token')
    monkeypatch.setattr(cloud,'get_current_user',invalid)
    with pytest.raises(cloud.CloudContextRejected,match='auth_unavailable'): cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock')])

def test_ownership_ended_and_selected_context(monkeypatch,services):
    session,_=services
    session.status='ended'
    with pytest.raises(cloud.CloudContextRejected,match='cloud_session_ended'): cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock')])
    session.status='active'; session.selected_resume_id=JID
    with pytest.raises(cloud.CloudContextRejected,match='selected_context_forbidden'): cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock')])
    def forbidden(**kwargs): raise RuntimeError('other owner')
    monkeypatch.setattr(cloud,'CloudInterviewSessionService',lambda: NS(get_session=forbidden))
    with pytest.raises(cloud.CloudContextRejected,match='cloud_session_invalid'): cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock')])

def test_context_is_server_owned_and_save_uses_stable_idempotency_key(services,caplog):
    _,calls=services
    context=cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock-private-token')])
    fields=context.load()
    assert fields['job_description']=='authorized job'
    assert fields['profile']=={}
    context.save('Private question','Private answer','technical','openai','model')
    context.save('Private question','Private answer','technical','openai','model')
    saves=[value for kind,value in calls if kind=='save']
    assert saves[0]['user_id']=='owner'
    assert saves[0]['payload']['request_id']==saves[1]['payload']['request_id']
    assert 'Private' not in caplog.text and 'mock-private-token' not in caplog.text

@pytest.mark.parametrize('which',['resume','job'])
def test_forbidden_context(monkeypatch,services,which):
    def forbidden(**kwargs): raise RuntimeError('private context')
    monkeypatch.setattr(cloud, 'CloudResumeService' if which=='resume' else 'CloudJobContextService',
        lambda: NS(get_status=forbidden,get_context=forbidden))
    with pytest.raises(cloud.CloudContextRejected,match='selected_context_forbidden'): cloud.GrpcCloudContext.authorize(start(), [('authorization','Bearer mock')])

@pytest.mark.parametrize('failure',[False,True])
def test_cloud_answer_adapter_saves_once_and_keeps_answer_on_save_failure(monkeypatch,caplog,failure):
    import asyncio,json,logging
    from app import grpc_answer_pipeline
    from app.api import generate
    calls,saves=[],[]
    class Context:
        request=NS(state=NS(grpc_cloud_context_only=True))
        def load(self): return dict(selected_resume_id=RID,profile={},profile_context_used=True,job_description='authorized job')
        def save(self,*args):
            saves.append(args)
            if failure: raise RuntimeError('private save details')
    context=Context()
    class Response:
        async def events(self):
            logging.getLogger('generate_api').warning('private prompt')
            for item in [{'type':'start','provider':'openai'},{'type':'delta','text':'private answer'},
                         {'type':'metadata','metadata':{'answer':'private answer','model':'model','provider':'openai'}},{'type':'done'},{'type':'done'}]:
                yield json.dumps(item)
        def __init__(self): self.body_iterator=self.events()
    async def generate_stream(req,request=None,**kwargs):
        assert req.session_id is None  # Transport adapter alone performs the one cloud save.
        assert req.selected_resume_id==RID and req.profile=={}
        assert request is context.request and request.state.grpc_cloud_context_only is True
        calls.append(req); return Response()
    monkeypatch.setattr(generate,'generate_answer_stream',generate_stream)
    async def exercise(): return [item async for item in grpc_answer_pipeline.stream_question_answer('Explain FastAPI realtime systems',context)]
    with caplog.at_level(logging.DEBUG): items=asyncio.run(exercise())
    assert len(calls)==len(saves)==1
    assert [item['code'] for item in items if item['type']=='save_status']==['answer_save_pending','answer_save_failed' if failure else 'answer_saved']
    assert items[-1]['type']=='completed'
    assert sum(item['type']=='completed' for item in items)==1
    assert any(item.get('text')=='private answer' for item in items)
    assert 'private' not in caplog.text


def test_cloud_grpc_missing_auth_rejected_before_stt(monkeypatch):
    import asyncio,grpc
    from app import grpc_server
    from app.grpc_generated import interview_realtime_pb2_grpc as rpc
    monkeypatch.setattr(grpc_server.settings,'USE_GRPC_CLOUD_CONTEXT_PIPELINE',True)
    monkeypatch.setattr(grpc_server.settings,'USE_GRPC_AUTO_PIPELINE',True)
    monkeypatch.setattr(grpc_server.settings,'GRPC_STT_ENABLED',True)
    monkeypatch.setattr(grpc_server.settings,'GRPC_ANSWER_STREAM_ENABLED',True)
    async def exercise():
        server,port=await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='transport',start_session=start(mode='auto_pipeline',source='microphone',cloud_context_requested=True)))
                assert (await call.read()).status.code=='auth_verifying'
                assert (await call.read()).error.code=='auth_unavailable'
                call.cancel()
        finally: await server.stop(0)
    asyncio.run(exercise())

@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('question',['Explain FastAPI realtime systems','supervised learning'])
@pytest.mark.parametrize('source',['microphone','system'])
def test_g8_cloud_stream_handshake_answer_and_once_only_save(monkeypatch,services,enabled,question,source):
    import asyncio,grpc,json
    from app import grpc_server
    from app.api import generate
    from app.services import assemblyai_streaming
    from app.grpc_generated import interview_realtime_pb2_grpc as rpc
    for name in ['USE_GRPC_AUTO_PIPELINE','GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED']:
        monkeypatch.setattr(grpc_server.settings,name,True)
    monkeypatch.setattr(grpc_server.settings,'USE_GRPC_CLOUD_CONTEXT_PIPELINE',enabled)
    class Socket:
        def __init__(self): self.events=asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self,data): pass
        async def close(self): pass
    socket=Socket()
    if source == 'system':
        import time
        from app.services import system_audio_capture
        class Capture:
            def open_streaming_loopback_session(self,**kwargs): return NS(sample_rate=48000)
            def read_streaming_pcm_chunk(self,session):
                time.sleep(.1)
                return NS(pcm_bytes=b'\x00\x10'*1600,rms_level=.125,peak_level=.125,input_sample_rate=48000,resample_latency_ms=.1)
            def close_streaming_loopback_session(self,session): pass
        monkeypatch.setattr(system_audio_capture,'SystemAudioCaptureService',Capture)
    async def connect(self):
        await socket.events.put('{"type":"Begin"}'); return socket
    class Response:
        async def events(self):
            for item in [{'type':'start','provider':'openai'},{'type':'delta','text':'mock answer'},
                         {'type':'metadata','metadata':{'answer':'mock answer','model':'model','provider':'openai'}},{'type':'done'}]: yield json.dumps(item)
        def __init__(self): self.body_iterator=self.events()
    async def generate_stream(req,request=None):
        assert req.selected_resume_id==RID and req.job_description=='authorized job'
        assert request.state.grpc_cloud_context_only
        return Response()
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge,'connect',connect)
    monkeypatch.setattr(generate,'generate_answer_stream',generate_stream)
    async def exercise():
        server,port=await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(metadata=[('authorization','Bearer mock')],timeout=10)
                await call.write(pb.InterviewClientEvent(session_id='transport',start_session=start(mode='auto_pipeline',source=source,cloud_context_requested=True)))
                if not enabled:
                    assert (await call.read()).error.code=='cloud_context_flag_disabled';call.cancel();return
                codes=[]
                while True:
                    item=await call.read();codes.append(item.status.code)
                    if item.status.code=='answer_stream_enabled': break
                assert {'auth_verified','cloud_session_verified','cloud_context_loaded'} <= set(codes)
                event=json.dumps({'type':'Turn','transcript':question,'turn_order':0,'end_of_turn':True})
                await socket.events.put(event);await socket.events.put(event)
                kinds=[]
                while True:
                    item=await call.read();codes.append(item.status.code);kinds.append(item.WhichOneof('event'))
                    if item.status.code=='auto_cooldown':break
                assert 'answer_saved' in codes
                assert kinds.index('answer_delta') < kinds.index('answer_completed')
                assert len([entry for kind,entry in services[1] if kind=='save'])==1
                await call.write(pb.InterviewClientEvent(end_session=pb.Empty()))
                while (await call.read()).status.code!='ended': pass
                call.cancel()
        finally: await server.stop(0)
    asyncio.run(exercise())

@pytest.mark.parametrize('expired,code', [(False, 'auth_invalid'), (True, 'token_expired')])
def test_safe_auth_failure_reason(monkeypatch, services, expired, code):
    from fastapi import HTTPException
    from jwt.exceptions import ExpiredSignatureError
    def reject(request):
        if expired:
            try: raise ExpiredSignatureError('private')
            except ExpiredSignatureError as cause: raise HTTPException(401) from cause
        raise HTTPException(401)
    monkeypatch.setattr(cloud, 'get_current_user', reject)
    with pytest.raises(cloud.CloudContextRejected, match=code):
        cloud.GrpcCloudContext.authorize(start(), [('authorization', 'Bearer mock')])

def test_wrong_returned_session_identity_is_rejected(services):
    session, _ = services
    session.user_id = 'different-owner'
    with pytest.raises(cloud.CloudContextRejected, match='session_owner_mismatch'):
        cloud.GrpcCloudContext.authorize(start(), [('authorization', 'Bearer mock')])
    session.user_id = 'owner'; session.id = RID
    with pytest.raises(cloud.CloudContextRejected, match='cloud_session_invalid'):
        cloud.GrpcCloudContext.authorize(start(), [('authorization', 'Bearer mock')])
