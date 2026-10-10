import asyncio
import json
import logging
import sys
from pathlib import Path

import grpc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grpc_server, grpc_answer_pipeline
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from app.services import assemblyai_streaming


@pytest.mark.parametrize('enabled', [False, True])
def test_manual_opt_in_defers_generation_until_stop_and_deduplicates(monkeypatch, caplog, enabled):
    monkeypatch.setattr(grpc_server.settings, 'USE_GRPC_MANUAL_PIPELINE', enabled)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_ANSWER_STREAM_ENABLED', True)
    calls = []

    class Socket:
        def __init__(self): self.events = asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self, data):
            if isinstance(data, bytes):
                for text in ['Explain private systems', 'Explain private realtime systems']:
                    await self.events.put(json.dumps({'type': 'Turn', 'turn_order': 0,
                        'end_of_turn': True, 'transcript': text}))
            elif json.loads(data)['type'] == 'ForceEndpoint':
                await self.events.put(json.dumps({'type': 'Turn', 'turn_order': 0,
                    'end_of_turn': True, 'transcript': 'Explain private realtime systems'}))
            elif json.loads(data)['type'] == 'Terminate':
                await self.events.put('{"type":"Termination"}')
        async def close(self): pass

    socket = Socket()
    async def connect(self):
        calls.append('connect')
        await socket.events.put('{"type":"Begin"}')
        return socket
    async def answer(text):
        calls.append(text)
        yield {'type': 'question', 'text': text}
        yield {'type': 'started'}
        yield {'type': 'delta', 'text': 'private answer'}
        yield {'type': 'completed'}
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', answer)

    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='local', start_session=pb.StartSession(mode='manual_pipeline')))
                first = await call.read()
                if not enabled:
                    assert first.error.code == 'manual_unavailable'
                    assert not calls
                    call.cancel()
                    return
                assert first.status.code == 'manual_pipeline_ready'
                while (await call.read()).status.code != 'answer_stream_enabled': pass
                await call.write(pb.InterviewClientEvent(session_id='local', audio_chunk=pb.AudioChunk(
                    audio=b'\x01\x00' * 1600, sample_rate=16000, channels=1, encoding='linear16')))
                finals = 0
                while finals < 2:
                    item = await call.read()
                    finals += item.HasField('final_transcript')
                assert calls == ['connect']
                await call.write(pb.InterviewClientEvent(session_id='local', manual_stop=pb.Empty()))
                while not (await call.read()).HasField('answer_completed'): pass
                assert calls == ['connect', 'Explain private realtime systems']
                await call.write(pb.InterviewClientEvent(session_id='local', manual_stop=pb.Empty()))
                while (await call.read()).status.code != 'audio_stopped': pass
                assert len(calls) == 2
                call.cancel()
        finally: await server.stop(0)
    with caplog.at_level(logging.DEBUG): asyncio.run(exercise())
    assert 'private realtime' not in caplog.text
    assert 'private answer' not in caplog.text
