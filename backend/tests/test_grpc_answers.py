import asyncio
import json
import logging
from pathlib import Path
import sys

import grpc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grpc_server, grpc_answer_pipeline
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from app.services import assemblyai_streaming


@pytest.mark.parametrize('failure', [False, True, 'eof'])
def test_g5_stop_detects_once_streams_and_sanitizes(monkeypatch, caplog, failure):
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_ANSWER_STREAM_ENABLED', True)
    calls = []
    class Socket:
        def __init__(self): self.events = asyncio.Queue(); self.closed = False
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self, data):
            if isinstance(data, str):
                if json.loads(data)['type'] == 'ForceEndpoint':
                    for _ in range(2):
                        await self.events.put(json.dumps({'type': 'Turn', 'turn_order': 0,
                            'end_of_turn': True, 'transcript': 'Explain FastAPI realtime systems.'}))
                elif json.loads(data)['type'] == 'Terminate':
                    await self.events.put('{"type":"Termination"}')
        async def close(self): self.closed = True
    socket = Socket()
    async def connect(self):
        await socket.events.put('{"type":"Begin"}')
        return socket
    async def generate(text):
        calls.append(text)
        yield {'type': 'question', 'text': text, 'category': 'technical'}
        yield {'type': 'started', 'provider': 'openai'}
        yield {'type': 'delta', 'text': 'private answer'}
        if failure == 'eof': return
        if failure: raise RuntimeError('private token prompt resume')
        yield {'type': 'completed'}
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', generate)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='local', start_session=pb.StartSession()))
                assert (await call.read()).HasField('ready')
                await call.read()
                assert (await call.read()).status.code == 'answer_stream_enabled'
                await call.write(pb.InterviewClientEvent(session_id='local', manual_stop=pb.Empty()))
                kinds = []
                while 'status' not in kinds or ('answer_error' if failure else 'answer_completed') not in kinds:
                    event = await call.read()
                    kind = event.WhichOneof('event')
                    kinds.append(kind)
                    if kind == 'answer_error': assert 'private' not in event.answer_error.message
                assert kinds.count('question_detected') == 1
                assert kinds.count('answer_started') == 1
                assert kinds.count('answer_delta') == 1
                assert len(calls) == 1
                await call.write(pb.InterviewClientEvent(end_session=pb.Empty()))
                assert (await call.read()).status.code == 'ended'
                assert await call.read() is grpc.aio.EOF
        finally: await server.stop(0)
    with caplog.at_level(logging.DEBUG): asyncio.run(exercise())
    assert socket.closed
    assert not any(value in caplog.text for value in ('private answer', 'private token', 'Explain FastAPI realtime systems'))


@pytest.mark.parametrize('close_kind', ['cancel', 'end_session'])
def test_g5_cancel_closes_inflight_answer(monkeypatch, close_kind):
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_ANSWER_STREAM_ENABLED', True)
    closed = []
    class Socket:
        def __init__(self): self.events = asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self, data):
            await self.events.put(json.dumps({'type': 'Turn', 'end_of_turn': True, 'transcript': 'Explain FastAPI realtime systems.'}))
        async def close(self): closed.append('socket')
    socket = Socket()
    async def connect(self):
        await socket.events.put('{"type":"Begin"}')
        return socket
    async def generate(text):
        try:
            yield {'type': 'question', 'text': text}
            yield {'type': 'started'}
            await asyncio.Event().wait()
        finally: closed.append('answer')
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', generate)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='local', start_session=pb.StartSession()))
                await call.read(); await call.read(); await call.read()
                await call.write(pb.InterviewClientEvent(session_id='local', audio_chunk=pb.AudioChunk(audio=bytes(3200), sample_rate=16000, channels=1, encoding='linear16')))
                while not (await call.read()).HasField('answer_started'): pass
                await call.write(pb.InterviewClientEvent(**{close_kind: pb.Empty()}))
                assert (await call.read()).status.code in ('ended', 'canceled')
                assert await call.read() is grpc.aio.EOF
        finally: await server.stop(0)
    asyncio.run(exercise())
    assert 'answer' in closed and 'socket' in closed


@pytest.mark.parametrize('question', ['Thank you for watching.', 'Explain FastAPI realtime systems.'])
def test_adapter_reuses_detector_profile_and_stream_pipeline(monkeypatch, caplog, question):
    from app.api import generate
    calls = []
    class Response:
        async def events(self):
            logging.getLogger('generate_api').error('private prompt token')
            for event in [{'type': 'start', 'provider': 'openai'}, {'type': 'delta', 'text': 'private answer'},
                          {'type': 'metadata', 'metadata': {'answer': 'grounded result'}}, {'type': 'done'}]:
                yield json.dumps(event)
        def __init__(self): self.body_iterator = self.events()
    async def stream(req):
        calls.append(req)
        return Response()
    monkeypatch.setattr(generate, 'generate_answer_stream', stream)
    monkeypatch.setattr(grpc_answer_pipeline, '_load_local_profile', lambda: {'name': 'Local candidate'})
    async def exercise(): return [event async for event in grpc_answer_pipeline.stream_question_answer(question)]
    with caplog.at_level(logging.DEBUG): events = asyncio.run(exercise())
    if question.startswith('Thank'):
        assert not calls and events == [{'type': 'rejected', 'reason': 'not_question'}]
    else:
        assert calls[0].session_id is None and calls[0].selected_resume_id is None and calls[0].job_context_id is None
        assert calls[0].profile == {'name': 'Local candidate'}
        assert [e['type'] for e in events] == ['question', 'started', 'delta', 'result', 'completed']
    assert 'private prompt token' not in caplog.text

@pytest.mark.parametrize('answer', ['', '   ', 'valid answer'])
def test_adapter_done_requires_nonempty_answer_before_cloud_save(monkeypatch, answer):
    from types import SimpleNamespace
    from app.api import generate
    saves, events = [], []
    class Response:
        def __init__(self): self.body_iterator = self.events()
        async def events(self):
            if answer: yield json.dumps({'type': 'delta', 'text': answer})
            yield json.dumps({'type': 'done'})
            yield json.dumps({'type': 'done'})
    async def detect(text): return 'Explain SQL.', ''
    async def stream(req, **kwargs): return Response()
    monkeypatch.setattr(grpc_answer_pipeline, 'detect_intake_question', detect)
    monkeypatch.setattr(generate, 'generate_answer_stream', stream)
    context = SimpleNamespace(request=object(), load=lambda: {'profile': {}},
                              save=lambda *args: saves.append(args))
    async def exercise():
        async for event in grpc_answer_pipeline.stream_question_answer('Explain SQL.', context):
            events.append(event)
    if answer.strip():
        asyncio.run(exercise())
        assert len(saves) == 1
        assert sum(e['type'] == 'completed' for e in events) == 1
    else:
        with pytest.raises(RuntimeError, match='Answer generation empty.'):
            asyncio.run(exercise())
        assert not saves
        assert not any(e['type'] in ('completed', 'save_status') for e in events)
