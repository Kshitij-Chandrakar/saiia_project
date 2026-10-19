"""Synthetic mixer/native/localhost coverage; never opens physical audio."""
import asyncio
import time
import json
import threading

import grpc
import numpy as np
import pytest

from test_grpc_computer_lifecycle import configure, chunk, start, until, NS
from app import grpc_server
from app.grpc_generated import interview_realtime_pb2 as pb, interview_realtime_pb2_grpc as rpc
from app.pcm_mixer import PcmMixer, StreamingResampler
from app.services.system_audio_capture import SystemAudioCaptureService, StreamingLoopbackSession, LoopbackDevice


def test_question_diagnostics_exclude_private_content_without_mutating_intake():
    intake = dict(last_ignored_transcript='private ignored text', utterance_buffer_text='private buffer text',
                  detection_attempts=3, last_ignored_reason='too_short')
    diagnostics = grpc_server.question_intake_diagnostics(intake)
    assert not diagnostics.last_ignored_transcript and not diagnostics.utterance_buffer_text
    assert diagnostics.detection_attempts == 3 and diagnostics.last_ignored_reason == 'too_short'
    assert intake['utterance_buffer_text'] == 'private buffer text'


def test_disconnect_cancels_answer_before_waiting_for_native_release(monkeypatch):
    from app import grpc_answer_pipeline
    reading, release = threading.Event(), threading.Event()
    started, canceled = asyncio.Event(), asyncio.Event()
    class Capture:
        def open_streaming_loopback_session(self, **kwargs): return NS()
        def read_streaming_pcm_chunk(self, session):
            reading.set()
            assert release.wait(5)
            return chunk()
        def close_streaming_loopback_session(self, session): return True
    sockets = configure(monkeypatch, Capture)
    async def answer(text):
        started.set()
        try:
            yield {'type': 'question', 'text': text}
            yield {'type': 'started'}
            await asyncio.Event().wait()
        finally:
            canceled.set()
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', answer)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                call = await start(rpc.InterviewRealtimeServiceStub(channel))
                await until(call, lambda e: e.HasField('ready'))
                assert await asyncio.to_thread(reading.wait, 1)
                await sockets[0].events.put(json.dumps(dict(type='Turn', transcript='Explain dependency injection', turn_order=0, end_of_turn=True)))
                await asyncio.wait_for(started.wait(), 1)
                call.cancel()
                await asyncio.wait_for(canceled.wait(), .5)
                assert not release.is_set()
        finally:
            release.set()
            await server.stop(0)
    asyncio.run(exercise())


def pcm(value, count=1600):
    return np.full(count, value, dtype='<i2').tobytes()


@pytest.mark.parametrize('scenario', ['recover', 'empty_timeout', 'malformed', 'computer'])
def test_native_empty_reads_preserve_liveness_accounting_and_cleanup(monkeypatch, scenario):
    from app import pcm_mixer
    mixers, closed, reads = [], [], []
    class Mixer(PcmMixer):
        def __init__(self):
            super().__init__()
            mixers.append(self)
        def push(self, source, data, now, *args):
            assert data  # Empty reads must never reach the mixer.
            return super().push(source, data, now, *args)
    monkeypatch.setattr(pcm_mixer, 'PcmMixer', Mixer)
    class Capture:
        def open_streaming_loopback_session(self, **kwargs): return NS()
        def enable_continuous_resampling(self, session): pass
        def read_streaming_pcm_chunk(self, session):
            time.sleep(.05)
            reads.append(time.monotonic())
            result = chunk()
            if scenario == 'empty_timeout':
                result.pcm_bytes = pcm(8000) if len(reads) == 1 else b''
            elif scenario == 'malformed':
                result.pcm_bytes = b'\x01'
            else:
                result.pcm_bytes = b'' if len(reads) == 1 else pcm(8000)
            return result
        def close_streaming_loopback_session(self, session): closed.append(True); return True
    sockets = configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        feeder = None
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                call = await start(stub, session='empty-test', source='system' if scenario == 'computer' else 'both')
                await until(call, lambda e: e.HasField('ready'))
                async def microphone():
                    while True:
                        await call.write(pb.InterviewClientEvent(session_id='empty-test', audio_chunk=pb.AudioChunk(
                            audio=pcm(12000), sample_rate=16000, channels=1, encoding='linear16')))
                        await asyncio.sleep(.1)
                if scenario != 'computer': feeder = asyncio.create_task(microphone())
                if scenario in ('empty_timeout', 'malformed'):
                    error = await asyncio.wait_for(until(call, lambda e: e.HasField('error')), 4)
                    assert error.error.code == 'system_audio_unavailable'
                    assert await call.read() is grpc.aio.EOF
                    if scenario == 'empty_timeout':
                        assert time.monotonic() - reads[0] >= 1.9
                        assert mixers[0].sources['system']['last'] < reads[1]
                        assert len(reads) > 10
                else:
                    metrics = await asyncio.wait_for(until(call, lambda e: e.status.system_audio.system_chunk_bytes == 3200), 3)
                    assert metrics.status.system_audio.system_dropped_chunks >= 1
                    frames = [data for data in sockets[0].sent if isinstance(data, bytes)]
                    expected = 8000 if scenario == 'computer' else 10000
                    assert any(np.max(np.frombuffer(frame, '<i2')) == expected for frame in frames)
                    if feeder:
                        feeder.cancel(); await asyncio.gather(feeder, return_exceptions=True)
                    await call.write(pb.InterviewClientEvent(session_id='empty-test', request_id='stop', end_session=pb.Empty()))
                    await until(call, lambda e: e.status.code == 'ended')
                    assert await call.read() is grpc.aio.EOF
                assert closed == [True]
                assert all(not np.any(s['data']) for s in mixers[0].sources.values())
                assert (await stub.CheckHealth(pb.Empty())).system_audio_available
        finally:
            if feeder:
                feeder.cancel(); await asyncio.gather(feeder, return_exceptions=True)
            await server.stop(0)
    asyncio.run(exercise())


def test_mix_headroom_silence_bounds_late_and_overflow():
    mixer = PcmMixer()
    mixer.push('microphone', pcm(12000), 0, 1, 10000)
    mixer.push('system', pcm(8000), 0)
    assert np.all(np.frombuffer(mixer.render(), '<i2') == 10000)
    assert not any(mixer.render())  # Underflow is timed silence, not a failure.
    assert not mixer.push('microphone', pcm(100), 1, 1, 11000)
    assert not mixer.push('microphone', pcm(100), 1, 2, 10001)
    mixer.push('microphone', pcm(32767, 16000), 1, 3, 11000)
    mixer.push('system', pcm(32767, 16000), 1)
    assert np.max(np.frombuffer(mixer.render(), '<i2')) == 32767
    assert mixer.dropped >= 4
    assert sum(s['data'].nbytes for s in mixer.sources.values()) == 32000
    mixer.clear()
    assert not any(mixer.render())


def test_long_running_jitter_and_rate_drift_remain_bounded():
    mixer = PcmMixer()
    for tick in range(10000):
        # Irregular chunks, occasional absence and opposing sample-clock drift.
        if tick % 17:
            mixer.push('microphone', pcm(1000, 1601), tick / 10, tick + 1)
        mixer.push('system', pcm(-1000, 1599), tick / 10)
        output = mixer.render()
        assert len(output) == 3200
        assert all(s['end'] <= mixer.position + mixer.capacity for s in mixer.sources.values())
    assert mixer.position == 16000000


@pytest.mark.parametrize('rate', [16000, 44100, 48000])
def test_stateful_resampling_irregular_boundaries(rate):
    data = np.sin(np.arange(rate) * 2 * np.pi * 400 / rate) * 12000
    whole = StreamingResampler(rate).process(data)
    stream = StreamingResampler(rate)
    pieces = []
    offset = 0
    for count in [1, 7, 511, 4096, 13] * 10000:
        if offset >= len(data): break
        pieces.append(stream.process(data[offset:offset + count]))
        offset += count
    split = np.concatenate(pieces)
    assert len(split) == len(whole)
    np.testing.assert_allclose(split, whole, atol=1e-6)
    assert abs(len(split) - 16000) <= 1


def test_native_stereo_conversion_preserves_state_without_opening_device():
    stereo = np.tile(np.array([12000, 4000], dtype='<i2'), (44100, 1))
    class Stream:
        offset = 0
        def read(self, count, **kwargs):
            data = stereo[self.offset:self.offset + 997].tobytes()
            self.offset += 997
            return data
    device = LoopbackDevice(7, 'synthetic', 2, 44100, True, False)
    session = StreamingLoopbackSession(None, None, Stream(), device, 44100, 2, 16000, 997,
                                      stats_started_at=time.perf_counter())
    service = SystemAudioCaptureService()
    service.enable_continuous_resampling(session)
    result = []
    while session.stream.offset < len(stereo):
        result.append(service.read_streaming_pcm_chunk(session).pcm_bytes)
    samples = np.frombuffer(b''.join(result), '<i2')
    assert len(samples) == 16000
    assert np.all(np.abs(samples.astype(int) - 8000) <= 1)


def test_combined_native_start_failure_releases_lease_and_never_sends_stt_audio(monkeypatch):
    class Capture:
        def open_streaming_loopback_session(self, **kwargs):
            raise OSError('synthetic permission/device rejection')
    sockets = configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                call = await start(stub, source='both')
                error = await until(call, lambda e: e.HasField('error'))
                assert error.error.code == 'system_audio_unavailable'
                assert await call.read() is grpc.aio.EOF
                assert (await stub.CheckHealth(pb.Empty())).combined_audio_available
                assert len(sockets) == 1 and not sockets[0].sent
        finally:
            await server.stop(0)
    asyncio.run(exercise())


@pytest.mark.parametrize('failure', [None, 'microphone', 'system'])
def test_localhost_combined_single_stt_mix_and_owned_cleanup(monkeypatch, failure):
    opened, closed, active = [], [], []
    class Capture:
        def open_streaming_loopback_session(self, **kwargs):
            assert not active
            active.append(True); opened.append(kwargs)
            return NS()
        def enable_continuous_resampling(self, session): pass
        def read_streaming_pcm_chunk(self, session):
            time.sleep(.1)
            if failure == 'system' and len(opened) and len(active) > 1:
                raise RuntimeError('synthetic device loss')
            result = chunk()
            result.pcm_bytes = pcm(8000)
            return result
        def close_streaming_loopback_session(self, session):
            active.clear(); closed.append(True)
            return True
    sockets = configure(monkeypatch, Capture)
    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                assert (await stub.CheckHealth(pb.Empty())).combined_audio_available
                call = await start(stub, session='combined', source='both')
                await until(call, lambda e: e.HasField('ready'))
                assert len(sockets) == len(opened) == 1
                assert not (await stub.CheckHealth(pb.Empty())).combined_audio_available
                for index in range(6):
                    await call.write(pb.InterviewClientEvent(session_id='combined', request_id=f'mic-{index}',
                        sequence_number=index + 1, timestamp_ms=10000 + index * 100,
                        audio_chunk=pb.AudioChunk(audio=pcm(12000), sample_rate=16000, channels=1, encoding='linear16')))
                    await asyncio.sleep(.1)
                frames = [data for data in sockets[0].sent if isinstance(data, bytes)]
                assert len(frames) >= 2 and all(len(data) == 3200 for data in frames)
                assert any(np.max(np.frombuffer(data, '<i2')) == 10000 for data in frames)
                metrics = await until(call, lambda e: e.status.system_audio.system_sample_rate > 0 and e.status.system_audio.system_chunk_bytes > 0)
                assert metrics.status.system_audio.system_sample_rate == 48000
                assert metrics.status.system_audio.system_rms == .125
                assert 0 <= metrics.status.system_audio.system_buffer_queue_depth <= 5
                if failure:
                    if failure == 'system': active.append(True)
                    error = await asyncio.wait_for(until(call, lambda e: e.HasField('error')), 4)
                    assert error.error.code == 'system_audio_unavailable'
                    await call.read()
                else:
                    await call.write(pb.InterviewClientEvent(session_id='combined', request_id='end', end_session=pb.Empty()))
                    await until(call, lambda e: e.status.code == 'ended')
                    await call.read()
                assert closed == [True] and not active
                assert (await stub.CheckHealth(pb.Empty())).combined_audio_available
        finally:
            await server.stop(0)
    asyncio.run(exercise())
