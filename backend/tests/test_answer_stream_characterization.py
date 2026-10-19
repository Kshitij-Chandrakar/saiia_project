"""Phase 1 characterization: buffering assertions are known limitations, not goals.

No providers, devices or cloud storage are contacted. Gates control causality;
timeouts only detect deadlocks. Stage diagnostics contain no payload or identity.
"""
import asyncio
import json
import threading
import time
from contextlib import aclosing, asynccontextmanager
from types import SimpleNamespace as NS

import grpc
import pytest

from test_session_generation import setup, request, SID  # reuse isolated store/auth
from app import grpc_answer_pipeline as pipeline, grpc_server, session_generation as sg
from app.api import generate as api
from app.answer_generation import AttemptFailure
from app.grpc_cloud_context import GrpcCloudContext
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc

TIMEOUT = 10
A = 'Dependency injection '
B = 'supplies dependencies externally.'
FALLBACK_A = 'Dependency injection passes '
FALLBACK_B = 'dependencies to a class.'


class Probe:
    """Test-local, bounded stage ordering and local elapsed time; no cross-clock math."""
    def __init__(self):
        self.started = time.perf_counter()
        self.events = []
        self.changed = asyncio.Event()

    def mark(self, stage, payload=None):
        assert len(self.events) < 256
        self.events.append((stage, payload, time.perf_counter() - self.started))
        self.changed.set()
        self.changed = asyncio.Event()

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await self.changed.wait()
        await asyncio.wait_for(wait(), TIMEOUT)

    def payloads(self, stage):
        return [payload for name, payload, _ in self.events if name == stage]

    def safe_summary(self):
        # Payloads are assertions only; diagnostics never serialize them.
        return [dict(stage=name, local_ms=round(elapsed * 1000, 2))
                for name, _, elapsed in self.events]


class Gates:
    def __init__(self, probe, scenario):
        self.probe, self.scenario = probe, scenario
        self.release = {name: asyncio.Event() for name in
                        ('primary_a', 'primary_b', 'primary_end',
                         'fallback_a', 'fallback_b', 'fallback_end', 'save')}
        self.validation = threading.Event()
        self.calls = []
        self.closed = []

    async def at(self, stage):
        self.probe.mark(stage + '_waiting')
        await asyncio.wait_for(self.release[stage].wait(), TIMEOUT)

    async def provider(self, client, model, prepared, key):
        attempt = 'primary' if not self.calls else 'fallback'
        self.calls.append(model.key)
        try:
            await self.at(attempt + '_a')
            self.probe.mark(attempt + '_first_text')
            yield A if attempt == 'primary' else FALLBACK_A, model.api_model, False
            await self.at(attempt + '_b')
            self.probe.mark(attempt + '_next_text')
            yield B if attempt == 'primary' else FALLBACK_B, model.api_model, False
            await self.at(attempt + '_end')
            self.probe.mark(attempt + '_end')
            if self.scenario == 'terminal' or (self.scenario == 'fallback' and attempt == 'primary'):
                raise AttemptFailure('provider_unavailable')
            yield '', model.api_model, True
        finally:
            self.closed.append(attempt)
            self.probe.mark(attempt + '_closed')

    def unblock(self):
        self.validation.set()
        for event in self.release.values():
            event.set()


@asynccontextmanager
async def transport(monkeypatch, source, probe, version=0, turns=None, legacy_types=None, external_client=None):
    """Real gRPC handler/adapter; mock only auth, STT websocket and native capture."""
    from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
    from app.api.question_detect import classifier
    for name in ('USE_GRPC_AUTO_PIPELINE', 'GRPC_STT_ENABLED',
                 'GRPC_ANSWER_STREAM_ENABLED', 'USE_GRPC_CLOUD_CONTEXT_PIPELINE'):
        monkeypatch.setattr(grpc_server.settings, name, True)
    cloud = NS(session_id=SID, request=request(), load=lambda: dict(profile_context_used=False))
    cloud.save = lambda *args: pytest.fail('managed route must have one save owner')
    monkeypatch.setattr(GrpcCloudContext, 'authorize', lambda *args: cloud)
    async def detect(text, **kwargs):
        return text, ''
    monkeypatch.setattr(pipeline, 'detect_intake_question', detect)
    monkeypatch.setattr(classifier, 'classify_question', lambda text: 'technical')
    class Socket:
        def __init__(self):
            self.events = asyncio.Queue()
        def __aiter__(self):
            return self
        async def __anext__(self):
            return await self.events.get()
        async def send(self, data):
            pass
        async def close(self):
            pass
    socket = Socket()
    if turns is not None:
        turns.append(socket.events)
    async def connect(self):
        await socket.events.put('{"type":"Begin"}')
        return socket
    monkeypatch.setattr(AssemblyAIStreamingBridge, 'connect', connect)
    if source != 'microphone':
        from app.services import system_audio_capture
        # Continuous silence is synthetic; this suite does not retest the mixer.
        class Capture:
            def enable_continuous_resampling(self, session):
                pass
            def open_streaming_loopback_session(self, **kwargs):
                return NS()
            def read_streaming_pcm_chunk(self, session):
                # Model the existing 100 ms native read cadence. This is I/O
                # pacing only; all answer assertions use explicit gates.
                threading.Event().wait(.1)
                return NS(pcm_bytes=b'\0' * 3200, input_sample_rate=16000,
                          rms_level=0, peak_level=0, resample_latency_ms=0)
            def close_streaming_loopback_session(self, session):
                return True
        monkeypatch.setattr(system_audio_capture, 'SystemAudioCaptureService', Capture)
    original = pipeline.stream_question_answer
    async def observed(*args, **kwargs):
        async with aclosing(original(*args, **kwargs)) as stream:
            async for item in stream:
                probe.mark('adapter_' + item['type'], item)
                yield item
    monkeypatch.setattr(pipeline, 'stream_question_answer', observed)
    handler = grpc_server.InterviewRealtimeService.StreamInterview
    async def emitted(self, *args, **kwargs):
        async with aclosing(handler(self, *args, **kwargs)) as stream:
            async for item in stream:
                probe.mark('grpc_' + item.WhichOneof('event') + '_emission')
                yield item
    monkeypatch.setattr(grpc_server.InterviewRealtimeService, 'StreamInterview', emitted)
    server, port = await grpc_server.start_server(port=0)
    if external_client is not None:
        try:
            async with external_client(port) as peer:
                await socket.events.put(json.dumps(dict(type='Turn', transcript='Explain dependency injection',
                                                        turn_order=0, end_of_turn=True)))
                yield peer
        finally:
            await server.stop(0)
        return
    channel = grpc.aio.insecure_channel(f'127.0.0.1:{port}')
    if legacy_types:
        old_client, old_server = legacy_types
        call = channel.stream_stream('/intervuai.realtime.v1.InterviewRealtimeService/StreamInterview',
            request_serializer=lambda item: old_client.FromString(item.SerializeToString()).SerializeToString(),
            response_deserializer=old_server.FromString)(timeout=TIMEOUT * 3)
    else:
        call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=TIMEOUT * 3)
    async def receive():
        async for item in call:
            kind = item.WhichOneof('event')
            probe.mark('wire_' + kind, item)
    reader = asyncio.create_task(receive())
    try:
        await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='start',
            start_session=pb.StartSession(mode='auto_pipeline', source=source,
                cloud_context_requested=True, active_session_id=SID, answer_stream_version=version)))
        await probe.until(lambda: any(x.status.code == 'answer_stream_enabled'
                                     for x in probe.payloads('wire_status')))
        await socket.events.put(json.dumps(dict(type='Turn', transcript='Explain dependency injection',
                                                turn_order=0, end_of_turn=True)))
        yield call
    finally:
        terminated = any(x.status.code in ('ended', 'canceled') for x in probe.payloads('wire_status'))
        if not call.cancelled() and not terminated:
            await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='end', end_session=pb.Empty()))
            await probe.until(lambda: any(x.status.code == 'ended' for x in probe.payloads('wire_status')))
        call.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        await channel.close()
        await server.stop(0)


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
@pytest.mark.parametrize('scenario', ['primary', 'fallback', 'terminal', 'formatting', 'cancel', 'stop'])
async def test_gated_answer_boundaries(setup, monkeypatch, source, scenario, record_property):
    _, store = setup
    probe = Probe()
    gates = Gates(probe, scenario)
    monkeypatch.setattr(sg, 'provider_stream', gates.provider)
    # Hold the completed production planner/validator at its return boundary.
    # Formatting scenario injects an external formatter's canonical result here;
    # it does not claim semantic-correction algorithm coverage.
    generator_type = type(api.generator._default)
    generate = generator_type.generate_answer
    loop = asyncio.get_running_loop()
    def validated(self, **kwargs):
        result = generate(self, **kwargs)
        loop.call_soon_threadsafe(probe.mark, 'validation_waiting')
        assert gates.validation.wait(TIMEOUT), 'validation gate timed out'
        if scenario == 'formatting':
            result['answer'] = 'Canonical formatted answer.'
        loop.call_soon_threadsafe(probe.mark, 'validation_end')
        return result
    monkeypatch.setattr(generator_type, 'generate_answer', validated)
    operation = store.operation
    async def stored(op, *args, **kwargs):
        if op == 'complete':
            await gates.at('save')
        result = await operation(op, *args, **kwargs)
        if op == 'complete':
            probe.mark('durable_end')
        return result
    monkeypatch.setattr(store, 'operation', stored)
    stream_event = api._stream_event
    def coordinator(item):
        probe.mark('coordinator_' + item['type'], item)
        return stream_event(item)
    monkeypatch.setattr(api, '_stream_event', coordinator)
    try:
        async with transport(monkeypatch, source, probe) as call:
            gates.release['primary_a'].set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 1)
            assert probe.payloads('wire_answer_delta')[0].answer_delta.text == A
            stages = [event['stage'] for event in probe.safe_summary()]
            assert stages.index('primary_first_text') < stages.index('coordinator_delta')
            assert stages.index('coordinator_delta') < stages.index('grpc_answer_delta_emission') < stages.index('wire_answer_delta')
            assert not gates.release['primary_end'].is_set()
            assert probe.payloads('coordinator_delta')[0]['attempt'] == 0
            assert 'attempt' not in probe.payloads('adapter_delta')[0]  # known loss
            if scenario in ('cancel', 'stop'):
                if scenario == 'cancel':
                    call.cancel()  # actual disconnect while producer is gated
                else:
                    await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='stop', cancel=pb.Empty()))
                    await probe.until(lambda: any(x.status.code == 'canceled' for x in probe.payloads('wire_status')))
                await probe.until(lambda: 'primary' in gates.closed)
                assert len(gates.calls) == 1 and not store.saves
                return
            gates.release['primary_b'].set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 2)
            assert ''.join(x.answer_delta.text for x in probe.payloads('wire_answer_delta')) == A + B
            assert not probe.payloads('wire_answer_completed')
            gates.release['primary_end'].set()
            if scenario in ('fallback', 'terminal'):
                await probe.until(lambda: bool(probe.payloads('adapter_replacement')))
                assert probe.payloads('adapter_replacement')[0]['text'] == ''
                gates.release['fallback_a'].set()
                await probe.until(lambda: bool(probe.payloads('fallback_b_waiting')))
                gates.release['fallback_b'].set()
                await probe.until(lambda: bool(probe.payloads('fallback_end_waiting')))
                # Known limitation: fallback chunks and the empty reset never cross gRPC.
                assert len(probe.payloads('wire_answer_delta')) == 2
                assert not any(e.get('attempt') == 1 for e in probe.payloads('coordinator_delta'))
                assert not probe.payloads('wire_answer_completed')
                gates.release['fallback_end'].set()
            if scenario == 'terminal':
                await probe.until(lambda: bool(probe.payloads('wire_answer_error')))
                assert probe.payloads('wire_answer_error')[-1].answer_error.code == 'generation_failed'
                assert not store.saves and len(gates.calls) == 2
            else:
                await probe.until(lambda: bool(probe.payloads('validation_waiting')))
                assert not probe.payloads('wire_answer_completed') and not store.saves
                gates.validation.set()
                await probe.until(lambda: bool(probe.payloads('save_waiting')))
                assert not probe.payloads('wire_answer_completed') and not store.saves
                gates.release['save'].set()
                await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
                final = probe.payloads('wire_answer_completed')[-1].answer_completed.text
                expected = ('Canonical formatted answer.' if scenario == 'formatting' else
                            FALLBACK_A + FALLBACK_B if scenario == 'fallback' else A + B)
                assert final == expected and len(store.saves) == 1
                assert len(gates.calls) == (2 if scenario == 'fallback' else 1)
                names = [item['stage'] for item in probe.safe_summary()]
                assert names.index('validation_end') < names.index('durable_end') < names.index('wire_answer_completed')
    finally:
        gates.unblock()
        record_property('stream_stages', json.dumps(probe.safe_summary()))


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
async def test_unbound_session_retains_legacy_routing_and_buffers(setup, monkeypatch, source):
    session, store = setup
    session.selected_model_key = None
    probe = Probe()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    default = api.generator._default
    selected = default._select_primary_provider('What is dependency injection?', 'technical')
    calls = []
    # Mock configured provider I/O, leaving production legacy selection/planning intact.
    def response(**kwargs):
        calls.append(selected)
        loop.call_soon_threadsafe(probe.mark, 'legacy_provider_waiting')
        assert release.wait(TIMEOUT)
        return A + B
    provider = getattr(default, selected + '_provider')
    monkeypatch.setattr(provider, 'generate', response)
    async def forbidden(*args):
        pytest.fail('unbound sessions must not acquire selected-model adapter')
        yield
    monkeypatch.setattr(sg, 'provider_stream', forbidden)
    original = api._stream_event
    def coordinator(item):
        probe.mark('coordinator_' + item['type'], item)
        return original(item)
    monkeypatch.setattr(api, '_stream_event', coordinator)
    try:
        async with transport(monkeypatch, source, probe):
            await probe.until(lambda: bool(probe.payloads('legacy_provider_waiting')))
            assert probe.payloads('coordinator_start')
            assert not probe.payloads('coordinator_delta')
            assert not probe.payloads('wire_answer_delta')
            release.set()
            await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
            assert not probe.payloads('coordinator_delta')  # known limitation
            assert not probe.payloads('adapter_delta') and not probe.payloads('wire_answer_delta')
            assert calls == [selected] and len(store.saves) == 1
    finally:
        release.set()
