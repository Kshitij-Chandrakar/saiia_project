import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import grpc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grpc_server, grpc_answer_pipeline
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from app.services import assemblyai_streaming


@pytest.mark.parametrize('enabled', [False, True])
def test_auto_opt_in_continuous_stream_cooldown_latest_question_and_cleanup(monkeypatch, caplog, enabled):
    monkeypatch.setattr(grpc_server.settings, 'USE_GRPC_AUTO_PIPELINE', enabled)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_ANSWER_STREAM_ENABLED', True)
    monkeypatch.setattr(grpc_server, 'AUTO_COOLDOWN_SECONDS', 0.08)
    calls, forwarded, closed = [], [], []

    class Socket:
        def __init__(self): self.events = asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self, data):
            if isinstance(data, bytes): forwarded.append(data)
        async def close(self): closed.append(True)

    socket = Socket()
    async def connect(self):
        await socket.events.put('{"type":"Begin"}')
        return socket
    async def answer(text):
        calls.append((text, time.monotonic()))
        yield {'type': 'question', 'text': text}
        yield {'type': 'started'}
        yield {'type': 'delta', 'text': 'private streamed answer'}
        yield {'type': 'completed'}
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', answer)

    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='local', start_session=pb.StartSession(mode='auto_pipeline')))
                first = await call.read()
                if not enabled:
                    assert first.error.code == 'auto_unavailable'
                    assert not forwarded
                    call.cancel()
                    return
                assert first.status.code == 'auto_pipeline_ready'
                while (await call.read()).status.code != 'answer_stream_enabled': pass
                pcm = bytes([1, 0]) * 1600
                await call.write(pb.InterviewClientEvent(session_id='local', audio_chunk=pb.AudioChunk(
                    audio=pcm, sample_rate=16000, channels=1, encoding='linear16')))
                while (await call.read()).status.code != 'audio_chunk_received': pass
                assert forwarded == [pcm]
                async def turn(text, order, final=True):
                    await socket.events.put(json.dumps({'type': 'Turn', 'turn_order': order,
                        'end_of_turn': final, 'transcript': text}))
                await turn('Explain private realtime systems', 0, False)
                while not (await call.read()).HasField('partial_transcript'): pass
                assert calls == []
                await turn('Explain private realtime systems', 0)
                events = []
                while True:
                    item = await call.read(); events.append(item.WhichOneof('event'))
                    if item.status.code == 'auto_cooldown': break
                assert events.index('answer_delta') < events.index('answer_completed')
                await turn('Explain private realtime systems', 0)
                await turn('Explain private obsolete question', 1)
                await turn('Explain private latest question', 2)
                await turn('Explain private latest revised question', 2)
                while (await call.read()).status.code != 'auto_cooldown': pass
                assert [x[0] for x in calls] == ['Explain private realtime systems', 'Explain private latest revised question']
                assert calls[1][1] - calls[0][1] >= 0.075
                assert len(closed) == 0  # Still listening after two answers.
                await call.write(pb.InterviewClientEvent(session_id='local', end_session=pb.Empty()))
                while (await call.read()).status.code != 'ended': pass
                assert closed
                call.cancel()
        finally: await server.stop(0)
    with caplog.at_level(logging.DEBUG): asyncio.run(exercise())
    assert 'private realtime' not in caplog.text
    assert 'private streamed answer' not in caplog.text
