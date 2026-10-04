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
                                            'question_detected', 'answer_delta', 'answer_done', 'error', 'pong'}
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
                await call.write(pb.InterviewClientEvent(session_id='local-session', audio_chunk=pb.AudioChunk(audio=b'private-audio-transcript-prompt')))
                status = await call.read()
                assert status.status.code == 'not_implemented'
                assert status.sequence_number == 4
                await call.write(pb.InterviewClientEvent(session_id='local-session', manual_stop=pb.Empty()))
                assert (await call.read()).status.code == 'not_implemented'
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
