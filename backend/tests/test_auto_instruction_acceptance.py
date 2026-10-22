"""Synthetic transcript acceptance; real HTTP/gRPC consumers, fake boundaries."""
import asyncio
import json
from types import SimpleNamespace as NS

import grpc
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import question_detect as detector
from app import grpc_answer_pipeline as pipeline, grpc_server, session_generation as sg
from app.grpc_cloud_context import GrpcCloudContext
from app.grpc_generated import interview_realtime_pb2 as pb, interview_realtime_pb2_grpc as rpc
from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
from test_session_generation import setup, request, SID

PROMPTS = ['Design a URL shortener','Design a parking lot system','Build a rate limiter',
           'Implement an LRU cache','Explain how you would design a chat application',
           'Explain system design','What is gRPC']
NEGATIVE = ['Yesterday we discussed a URL shortener.','That design looks good.',
            'Yesterday we discussed how to design a URL shortener.',
            'We should build a rate limiter.','design','design a','build a','implement an',
            'Design a URL shortener with','okay','thank you']

@pytest.mark.parametrize('text',PROMPTS)
@pytest.mark.parametrize('punctuation',['','.'])
def test_http_and_grpc_accept_explicit_interview_instructions(text,punctuation):
    app=FastAPI();app.include_router(detector.router,prefix='/api/question-detect')
    with TestClient(app) as client:
        response=client.post('/api/question-detect',json={'transcript':text+punctuation})
    assert response.status_code==200 and response.json()['is_question']
    candidate,reason=asyncio.run(pipeline.detect_intake_question(text+punctuation,allow_topics=True))
    assert candidate and not reason

@pytest.mark.parametrize('text',NEGATIVE)
def test_conversational_mentions_and_incomplete_instructions_stay_filtered(text):
    result=asyncio.run(detector.detect_question(detector.QuestionDetectRequest(transcript=text)))
    assert not result.is_question
    assert asyncio.run(pipeline.detect_intake_question(text,allow_topics=True))[0] is None


def test_instruction_extraction_does_not_mine_conversational_mentions():
    candidate=detector.extract_question_candidate('Yesterday we discussed how to design a URL shortener.')
    assert not candidate['candidate']
    candidate=detector.extract_question_candidate('The question is design a parking lot system')
    assert candidate['candidate'].lower().startswith('design a parking lot system')


def test_split_final_instruction_uses_existing_bounded_utterance_buffer():
    from app.grpc_utterance_buffer import UtteranceBuffer
    clock=[10.0]
    buffer=UtteranceBuffer(clock=lambda:clock[0])
    fragment,_=buffer.assemble('Design a',0)
    assert asyncio.run(pipeline.detect_intake_question(fragment,allow_topics=True))[0] is None
    buffer.hold(fragment)
    clock[0]+=.2
    completed,merged=buffer.assemble('URL shortener',1)
    assert merged
    assert asyncio.run(pipeline.detect_intake_question(completed,allow_topics=True))[0]
    buffer.hold('Design a');clock[0]+=5
    expired,merged=buffer.assemble('URL shortener',2)
    assert not merged and expired=='URL shortener'
    assert asyncio.run(pipeline.detect_intake_question(expired,allow_topics=True))[0] is None


@pytest.mark.asyncio
async def test_final_design_instruction_reaches_real_planning_provider_and_durable_completion(setup,monkeypatch,caplog):
    _,store=setup
    for name in ('USE_GRPC_AUTO_PIPELINE','GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED','USE_GRPC_CLOUD_CONTEXT_PIPELINE'):
        monkeypatch.setattr(grpc_server.settings,name,True)
    cloud=NS(session_id=SID,request=request(),load=lambda:dict(profile_context_used=False))
    cloud.save=lambda *a:pytest.fail('managed coordination owns final persistence')
    monkeypatch.setattr(GrpcCloudContext,'authorize',lambda *a:cloud)
    closed=asyncio.Event();release=asyncio.Event();calls=[]
    class Socket:
        def __init__(self):self.events=asyncio.Queue()
        def __aiter__(self):return self
        async def __anext__(self):return await self.events.get()
        async def send(self,data):pass
        async def close(self):closed.set()
    socket=Socket()
    async def connect(self):await socket.events.put('{"type":"Begin"}');return socket
    monkeypatch.setattr(AssemblyAIStreamingBridge,'connect',connect)
    async def provider(client,model,prepared,key):
        calls.append(prepared)
        assert 'Resolved answer type: system_design' in prepared.text
        yield 'An illustrative URL service uses ',model.api_model,False
        await asyncio.wait_for(release.wait(),5)
        yield 'an API and durable mappings.',model.api_model,True
    monkeypatch.setattr(sg,'provider_stream',provider)
    server,port=await grpc_server.start_server(port=0)
    events=[]
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=10)
            async def until(predicate):
                while True:
                    value=await call.read()
                    assert value is not grpc.aio.EOF
                    events.append(value)
                    if predicate(value):return value
            await call.write(pb.InterviewClientEvent(session_id='synthetic',start_session=pb.StartSession(
                mode='auto_pipeline',source='microphone',cloud_context_requested=True,active_session_id=SID,answer_stream_version=1)))
            await until(lambda v:v.status.code=='answer_stream_enabled')
            async def turn(text,final):await socket.events.put(json.dumps(dict(type='Turn',transcript=text,turn_order=0,end_of_turn=final)))
            await turn('Design a',False)
            await until(lambda v:v.HasField('partial_transcript'))
            assert calls==[]
            await turn('Design a URL shortener.',True)
            final=await until(lambda v:v.HasField('final_transcript'))
            assert final.final_transcript.text=='Design a URL shortener.'
            await until(lambda v:v.HasField('answer_delta'))
            assert len(calls)==1 and not store.saves
            await turn('Design a URL shortener.',True)
            await until(lambda v:v.status.question_intake.last_ignored_reason=='duplicate')
            assert len(calls)==1
            release.set()
            completed=await until(lambda v:v.HasField('answer_completed'))
            assert completed.answer_completed.text=='An illustrative URL service uses an API and durable mappings.'
            assert len(store.saves)==1
            kinds=[v.WhichOneof('event') for v in events]
            assert kinds.index('final_transcript')<kinds.index('question_detected')<kinds.index('answer_delta')<kinds.index('answer_completed')
            await call.write(pb.InterviewClientEvent(end_session=pb.Empty()))
            await until(lambda v:v.status.code=='ended')
            assert closed.is_set()
            call.cancel()
    finally:
        release.set()
        await server.stop(0)
    assert 'Design a URL shortener' not in caplog.text
