import asyncio,json,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
import grpc
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import grpc_server,grpc_answer_pipeline
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from app.services import assemblyai_streaming,system_audio_capture


@pytest.mark.parametrize('overloaded',[False,True])
def test_system_gRPC_frames_shared_intake_metrics_and_cleanup(monkeypatch,caplog,overloaded):
    for name in ['USE_GRPC_AUTO_PIPELINE','GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED']: monkeypatch.setattr(grpc_server.settings,name,True)
    monkeypatch.setattr(grpc_server,'STABLE_PARTIAL_SECONDS',.02)
    sent,closed,opened=[],[],[]
    class Capture:
        def open_streaming_loopback_session(self,**kwargs):
            opened.append(kwargs);return NS(sample_rate=48000)
        def read_streaming_pcm_chunk(self,session):
            time.sleep(.02)
            return NS(pcm_bytes=b'\x00\x10'*1600,rms_level=.125,peak_level=.125,input_sample_rate=48000,resample_latency_ms=.3)
        def close_streaming_loopback_session(self,session): closed.append('capture')
    class Socket:
        def __init__(self):self.events=asyncio.Queue()
        def __aiter__(self):return self
        async def __anext__(self):return await self.events.get()
        async def send(self,data):
            sent.append(data)
            if len(sent)==1:await self.events.put(json.dumps({'type':'Turn','transcript':'Explain SQL','turn_order':0,'end_of_turn':False}))
            if overloaded: await asyncio.sleep(.15)
        async def close(self):closed.append('socket')
    socket=Socket()
    async def connect(self):await socket.events.put('{"type":"Begin"}');return socket
    calls=[]
    async def answer(text):
        calls.append(text)
        yield {'type':'question','text':text}
        yield {'type':'started'}
        yield {'type':'delta','text':'private answer'}
        yield {'type':'completed'}
    monkeypatch.setattr(system_audio_capture,'SystemAudioCaptureService',Capture)
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge,'connect',connect)
    monkeypatch.setattr(grpc_answer_pipeline,'stream_question_answer',answer)
    async def exercise():
        server,port=await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='system-test',start_session=pb.StartSession(mode='auto_pipeline',source='system')))
                metrics=[]
                while True:
                    item=await call.read()
                    if item.status.HasField('system_audio'):metrics.append(item.status.system_audio)
                    if item.WhichOneof('event')=='answer_completed':break
                if overloaded:
                    while True:
                        item=await call.read()
                        if item.status.HasField('system_audio'): metrics.append(item.status.system_audio)
                        if item.status.system_audio.system_dropped_chunks > 0: break
                assert sent and all(len(frame)==3200 for frame in sent)
                assert calls==['Explain SQL']
                last=metrics[-1]
                assert last.system_pcm_duration_ms==100
                assert last.system_capture_started_at>0 and last.system_first_pcm_chunk_at>0
                assert last.system_first_stt_partial_at>0 and last.system_first_answer_delta_at>0
                assert last.system_question_to_first_delta_ms>=0
                assert last.system_buffer_queue_depth<=3
                await socket.events.put(json.dumps({'type':'Turn','transcript':'Explain SQL','turn_order':0,'end_of_turn':True}))
                while True:
                    item=await call.read()
                    if item.status.question_intake.last_ignored_reason=='duplicate':break
                assert len(calls)==1
                await call.write(pb.InterviewClientEvent(end_session=pb.Empty()))
                while (await call.read()).status.code!='ended':pass
                call.cancel()
        finally:await server.stop(0)
    asyncio.run(exercise())
    assert opened==[dict(target_sample_rate=16000,chunk_ms=100,debug_save_enabled=False)]
    assert sorted(closed)==['capture','socket']
    assert 'private answer' not in caplog.text and 'Explain SQL' not in caplog.text
