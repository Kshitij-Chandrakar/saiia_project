"""Computer Auto transport tests: synthetic PCM, no native devices or live providers."""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import grpc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import grpc_server
from app.grpc_generated import interview_realtime_pb2 as pb, interview_realtime_pb2_grpc as rpc
from app.services import assemblyai_streaming, system_audio_capture


class Socket:
    def __init__(self):
        self.events = asyncio.Queue()
        self.sent = []
    def __aiter__(self): return self
    async def __anext__(self): return await self.events.get()
    async def send(self, data): self.sent.append(data)
    async def close(self): pass


def configure(monkeypatch, capture):
    for name in ('USE_GRPC_AUTO_PIPELINE', 'GRPC_STT_ENABLED', 'GRPC_ANSWER_STREAM_ENABLED'):
        monkeypatch.setattr(grpc_server.settings, name, True)
    monkeypatch.setattr(grpc_server.settings, 'ASSEMBLYAI_API_KEY', 'synthetic-unused')
    monkeypatch.setattr(grpc_server, 'system_capture_available', lambda: True)
    monkeypatch.setattr(system_audio_capture, 'SystemAudioCaptureService', capture)
    sockets = []
    async def connect(self):
        socket = Socket()
        sockets.append(socket)
        await socket.events.put(json.dumps({'type': 'Begin'}))
        return socket
    monkeypatch.setattr(assemblyai_streaming.AssemblyAIStreamingBridge, 'connect', connect)
    return sockets


def chunk(silent=False):
    return NS(pcm_bytes=(b'\0\0' if silent else b'\0\x10') * 1600,
              rms_level=0 if silent else .125, peak_level=0 if silent else .125,
              input_sample_rate=48000, resample_latency_ms=.1)


async def until(call, predicate):
    while True:
        item = await call.read()
        assert item is not grpc.aio.EOF
        if predicate(item): return item


async def start(stub, session='system', source='system'):
    call = stub.StreamInterview(timeout=12)
    await call.write(pb.InterviewClientEvent(session_id=session, request_id='start',
        start_session=pb.StartSession(mode='auto_pipeline', source=source)))
    return call


@pytest.mark.parametrize('pending', ['open', 'read'])
@pytest.mark.parametrize('source', ['system', 'both'])
def test_cancel_startup_or_native_read_keeps_exclusive_owner_until_cleanup(monkeypatch, pending, source):
    entered, gate, closed = threading.Event(), threading.Event(), threading.Event()
    opens, active, maximum, reading = [], 0, 0, False
    class Capture:
        def enable_continuous_resampling(self, session): pass
        def open_streaming_loopback_session(self, **kwargs):
            nonlocal active, maximum
            opens.append(kwargs)
            active += 1
            maximum = max(maximum, active)
            if len(opens) == 1 and pending == 'open':
                entered.set(); assert gate.wait(5)
            return NS()
        def read_streaming_pcm_chunk(self, session):
            nonlocal reading
            reading = True
            if len(opens) == 1 and pending == 'read':
                entered.set(); assert gate.wait(5)
            time.sleep(.005)
            reading = False
            return chunk()
        def close_streaming_loopback_session(self, session):
            nonlocal active
            assert not reading
            active -= 1
            closed.set()
            return True
    sockets = configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                first = await start(stub, 'old', source)
                assert await asyncio.to_thread(entered.wait, 2)
                first.cancel()
                second = await start(stub, 'new', source)
                await asyncio.sleep(.05)
                assert len(opens) == len(sockets) == 1
                second.cancel()  # A canceled lease waiter must not orphan ownership.
                second = await start(stub, 'new', source)
                gate.set()
                await until(second, lambda e: e.HasField('ready'))
                assert closed.is_set() and len(opens) == len(sockets) == 2
                await second.write(pb.InterviewClientEvent(session_id='new', end_session=pb.Empty()))
                await until(second, lambda e: e.status.code == 'ended')
                second.cancel()
        finally:
            gate.set()
            await server.stop(0)
    asyncio.run(exercise())
    assert maximum == 1 and active == 0


@pytest.mark.parametrize('scenario', ['silence', 'client_audio', 'invalid', 'close_failure', 'capture_loss', 'open_failure'])
def test_computer_contract_cleanup_and_failure_are_explicit(monkeypatch, scenario):
    opens, closes = [], []
    class Capture:
        def open_streaming_loopback_session(self, **kwargs):
            opens.append(kwargs)
            if scenario == 'open_failure': raise OSError('synthetic open rejected')
            return NS()
        def read_streaming_pcm_chunk(self, session):
            time.sleep(.005)
            if scenario == 'capture_loss': raise OSError('synthetic device lost')
            return chunk(silent=True)
        def close_streaming_loopback_session(self, session):
            closes.append(True)
            return scenario != 'close_failure'
    sockets = configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                call = await start(stub, source='invalid' if scenario == 'invalid' else 'system')
                if scenario == 'invalid':
                    error = await until(call, lambda e: e.HasField('error'))
                    assert error.error.code == 'unsupported_source' and not opens and not sockets
                    return
                if scenario in ('capture_loss', 'open_failure'):
                    error = await until(call, lambda e: e.HasField('error'))
                    assert error.error.code == 'system_audio_unavailable'
                    await call.read()  # EOF waits for server-side cleanup.
                    return
                await until(call, lambda e: e.HasField('ready'))
                if scenario == 'client_audio':
                    await call.write(pb.InterviewClientEvent(session_id='system', audio_chunk=pb.AudioChunk(
                        audio=b'\0\0' * 1600, sample_rate=16000, channels=1, encoding='linear16')))
                    assert (await until(call, lambda e: e.HasField('error'))).error.code == 'unsupported_source'
                    await call.read()
                    return
                metrics = await until(call, lambda e: e.status.total_chunks >= 3)
                assert metrics.status.non_silent_chunks == 0
                await call.write(pb.InterviewClientEvent(session_id='system', request_id='stop', end_session=pb.Empty()))
                stopped = await until(call, lambda e: e.status.code in ('ended', 'system_cleanup_pending'))
                assert stopped.request_id == 'stop'
                assert stopped.status.code == ('system_cleanup_pending' if scenario == 'close_failure' else 'ended')
                if scenario == 'close_failure':
                    health = await stub.CheckHealth(pb.Empty())
                    assert not health.system_audio_available
                    retry = await start(stub, 'retry')
                    assert (await until(retry, lambda e: e.HasField('error'))).error.code == 'system_cleanup_failed'
                    assert len(opens) == len(sockets) == 1
                call.cancel()
        finally:
            await server.stop(0)
    asyncio.run(exercise())
    if scenario not in ('invalid', 'open_failure'): assert closes



def test_stop_acknowledges_pending_cleanup_instead_of_claiming_device_is_released(monkeypatch):
    reading, gate, closed = threading.Event(), threading.Event(), threading.Event()
    class Capture:
        def open_streaming_loopback_session(self, **kwargs): return NS()
        def read_streaming_pcm_chunk(self, session):
            reading.set()
            assert gate.wait(6)
            return chunk()
        def close_streaming_loopback_session(self, session): closed.set(); return True
    configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                call = await start(stub)
                await until(call, lambda e: e.HasField('ready'))
                assert await asyncio.to_thread(reading.wait, 1)
                await call.write(pb.InterviewClientEvent(session_id='system', request_id='stop', end_session=pb.Empty()))
                item = await until(call, lambda e: e.status.code == 'system_cleanup_pending')
                assert item.request_id == 'stop' and not closed.is_set()
                assert not (await stub.CheckHealth(pb.Empty())).system_audio_available
                gate.set()
                assert await asyncio.to_thread(closed.wait, 1)
                assert (await stub.CheckHealth(pb.Empty())).system_audio_available
        finally:
            gate.set()
            await server.stop(0)
    asyncio.run(exercise())
