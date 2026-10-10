import asyncio
import logging
from pathlib import Path
import sys

import grpc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from app.grpc_server import main, start_server


def test_proto_event_contract():
    client = pb.InterviewClientEvent.DESCRIPTOR.oneofs_by_name['event']
    server = pb.InterviewServerEvent.DESCRIPTOR.oneofs_by_name['event']
    assert {f.name for f in client.fields} == {'start_session', 'audio_chunk', 'manual_stop', 'cancel', 'end_session', 'ping'}
    assert {f.name for f in server.fields} == {'ready', 'status', 'partial_transcript', 'final_transcript',
                                            'question_detected', 'answer_delta', 'answer_done', 'error', 'pong',
                                            'answer_started', 'answer_completed', 'answer_error'}
    service = pb.DESCRIPTOR.services_by_name['InterviewRealtimeService']
    method = service.methods_by_name['StreamInterview']
    assert method.client_streaming and method.server_streaming


@pytest.mark.parametrize('close_event', ['cancel', 'end_session'])
def test_real_bidi_ready_ping_audio_and_safe_close(caplog, close_event):
    async def exercise():
        server, port = await start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5,
                    metadata=(('authorization', 'synthetic-private-token'),))
                await call.write(pb.InterviewClientEvent(session_id='local-session', request_id='r1', start_session=pb.StartSession(mode='manual')))
                assert (await call.read()).WhichOneof('event') == 'ready'
                assert (await call.read()).status.code == 'foundation_only'
                await call.write(pb.InterviewClientEvent(request_id='r2', ping=pb.Empty()))
                pong = await call.read()
                assert pong.WhichOneof('event') == 'pong' and pong.request_id == 'r2'
                await call.write(pb.InterviewClientEvent(session_id='local-session', audio_chunk=pb.AudioChunk(audio=b'private-audio-transcript-prompt!', sample_rate=16000, channels=1, encoding='linear16')))
                status = await call.read()
                assert status.status.code == 'audio_chunk_received'
                assert status.status.total_chunks == 1
                assert status.status.total_audio_bytes == 32
                assert status.sequence_number == 4
                await call.write(pb.InterviewClientEvent(session_id='local-session', manual_stop=pb.Empty()))
                assert (await call.read()).status.code == 'audio_stopped'
                await call.write(pb.InterviewClientEvent(**{close_event: pb.Empty()}))
                assert (await call.read()).status.code == ('canceled' if close_event == 'cancel' else 'ended')
                assert await call.read() is grpc.aio.EOF
        finally:
            await server.stop(0)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())
    assert 'synthetic-private-token' not in caplog.text
    assert 'private-audio-transcript-prompt' not in caplog.text


def test_stream_rejects_audio_before_start_and_respects_message_limit():
    async def exercise():
        server, port = await start_server(port=0, max_message_mb=1)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                call = stub.StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(audio_chunk=pb.AudioChunk(audio=b'audio')))
                assert (await call.read()).error.code == 'invalid_session'
                assert await call.read() is grpc.aio.EOF
                call = stub.StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(audio_chunk=pb.AudioChunk(audio=b'x' * (1024 * 1024 + 1))))
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await call.read()
                assert error.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        finally:
            await server.stop(0)
    asyncio.run(exercise())


def test_g1_cannot_bind_external_interfaces():
    with pytest.raises(ValueError, match='loopback'):
        asyncio.run(start_server(host='0.0.0.0', port=0))


def test_cli_requires_explicit_enable(monkeypatch, capsys):
    from app import grpc_server
    monkeypatch.setattr(grpc_server.settings, 'GRPC_REALTIME_ENABLED', False)
    monkeypatch.setattr(sys, 'argv', ['grpc_server'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert 'GRPC_REALTIME_ENABLED=true' in capsys.readouterr().err


@pytest.mark.parametrize('failure', [False, True])
@pytest.mark.parametrize('close_event', ['cancel', 'end_session'])
def test_g4_bridge_transcripts_stop_and_safe_failure(monkeypatch, caplog, failure, close_event):
    import json
    from app import grpc_server
    from app.services import assemblyai_streaming
    sockets = []
    class Socket:
        def __init__(self):
            self.messages = asyncio.Queue()
            self.sent = []
            self.closed = False
            sockets.append(self)
        def __aiter__(self): return self
        async def __anext__(self): return await self.messages.get()
        async def send(self, value):
            self.sent.append(value)
            if isinstance(value, bytes):
                if failure:
                    await self.messages.put(json.dumps({'type': 'Error', 'error': 'private-token audio transcript'}))
                else:
                    await self.messages.put(json.dumps({'type': 'Turn', 'transcript': 'sensitive partial', 'end_of_turn': False}))
            elif json.loads(value)['type'] == 'ForceEndpoint':
                await self.messages.put(json.dumps({'type': 'Turn', 'transcript': 'sensitive final', 'end_of_turn': True}))
            elif json.loads(value)['type'] == 'Terminate':
                await self.messages.put(json.dumps({'type': 'Termination'}))
        async def close(self): self.closed = True
    async def connect(self):
        socket = Socket()
        await socket.messages.put(json.dumps({'type': 'Begin'}))
        return socket
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    async def exercise():
        server, port = await start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                async def write(kind, payload):
                    await call.write(pb.InterviewClientEvent(session_id='test', request_id=kind, **{kind: payload}))
                await write('start_session', pb.StartSession())
                assert (await call.read()).HasField('ready')
                started = await call.read()
                assert started.status.code == 'stt_enabled'
                assert started.provider == 'assemblyai_streaming'
                assert len(sockets) == 1
                await write('audio_chunk', pb.AudioChunk(audio=b'1234', sample_rate=16000, channels=1, encoding='linear16'))
                events = [await call.read(), await call.read()]
                assert sockets[0].sent[0] == b'1234'
                assert len(sockets) == 1
                if failure:
                    error = next(e for e in events if e is not grpc.aio.EOF and e.HasField('error'))
                    assert error.error.code == 'stt_unavailable'
                    assert 'private' not in error.error.message
                    assert await call.read() is grpc.aio.EOF
                else:
                    acknowledged = next(e for e in events if e.HasField('status'))
                    assert acknowledged.status.stt_chunks_forwarded == 1
                    assert acknowledged.status.stt_bytes_forwarded == 4
                    assert acknowledged.status.non_silent_chunks == 1
                    assert acknowledged.status.stt_bridge_connected
                    partial = next(e for e in events if e.HasField('partial_transcript'))
                    assert partial.partial_transcript.text == 'sensitive partial'
                    assert partial.provider == 'assemblyai_streaming'
                    await write('manual_stop', pb.Empty())
                    final = await call.read()
                    assert final.final_transcript.text == 'sensitive final'
                    assert (await call.read()).status.code == 'audio_stopped'
                    assert sockets[0].closed
                    # A new mic test gets a fresh provider session; cancel/end cleans it up too.
                    await write('audio_chunk', pb.AudioChunk(audio=b'5678', sample_rate=16000, channels=1, encoding='linear16'))
                    await call.read(); await call.read()
                    await write(close_event, pb.Empty())
                    assert (await call.read()).status.code in ('canceled', 'ended')
                    assert await call.read() is grpc.aio.EOF
        finally:
            await server.stop(0)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())
    assert all(socket.closed for socket in sockets)
    assert not any(value in caplog.text for value in ('sensitive partial', 'sensitive final', 'private-token', '1234'))


@pytest.mark.parametrize("missing_key", [True, False])
def test_g4_missing_provider_configuration_is_safe(monkeypatch, caplog, missing_key):
    from app import grpc_server
    from app.services import assemblyai_streaming
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    async def fail(self): raise RuntimeError('private-api-key transcript audio')
    if missing_key:
        monkeypatch.setattr(assemblyai_streaming.settings, 'ASSEMBLYAI_API_KEY', '')
    else:
        monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', fail)
    async def exercise():
        server, port = await start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='test', start_session=pb.StartSession()))
                result = await call.read()
                assert result.error.code == 'stt_unavailable'
                assert 'private' not in result.error.message
                assert await call.read() is grpc.aio.EOF
        finally: await server.stop(0)
    asyncio.run(exercise())
    assert 'private-api-key' not in caplog.text


def test_g4_provider_termination_before_begin_is_visible(monkeypatch):
    from app import grpc_server
    from app.services import assemblyai_streaming
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    class Socket:
        closed = False
        def __aiter__(self): return self
        async def __anext__(self): return '{"type":"Termination"}'
        async def close(self): self.closed = True
    socket = Socket()
    async def connect(self): return socket
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    async def exercise():
        server, port = await start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='test', start_session=pb.StartSession()))
                result = await call.read()
                assert result.error.code == 'stt_unavailable'
                assert result.provider == 'assemblyai_streaming'
                assert await call.read() is grpc.aio.EOF
        finally: await server.stop(0)
    asyncio.run(exercise())
    assert socket.closed


def test_g4_silence_after_many_forwarded_chunks_is_visible(monkeypatch):
    import json
    from app import grpc_server
    from app.services import assemblyai_streaming
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    class Socket:
        def __init__(self): self.messages = asyncio.Queue(); self.closed = False
        def __aiter__(self): return self
        async def __anext__(self): return await self.messages.get()
        async def send(self, value):
            if isinstance(value, str) and json.loads(value)['type'] == 'Terminate':
                await self.messages.put('{"type":"Termination"}')
        async def close(self): self.closed = True
    socket = Socket()
    async def connect(self):
        await socket.messages.put('{"type":"Begin"}')
        return socket
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    async def exercise():
        server, port = await start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
                await call.write(pb.InterviewClientEvent(session_id='test', start_session=pb.StartSession()))
                await call.read(); await call.read()
                for _ in range(50):
                    await call.write(pb.InterviewClientEvent(session_id='test', audio_chunk=pb.AudioChunk(audio=bytes(1600), sample_rate=16000, channels=1, encoding='linear16')))
                    result = await call.read()
                assert result.status.stt_chunks_forwarded == 50
                assert result.status.stt_bytes_forwarded == 80000
                assert result.status.stt_status == 'stt_no_transcript_yet'
                assert result.status.stt_callback_count == 1
                assert result.status.non_silent_chunks == 0
                await call.write(pb.InterviewClientEvent(session_id='test', manual_stop=pb.Empty()))
                assert (await call.read()).error.code == 'no_transcript'
                assert (await call.read()).status.code == 'audio_stopped'
                call.cancel()
        finally: await server.stop(0)
    asyncio.run(exercise())
    assert socket.closed
