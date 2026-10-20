"""Negotiated contract tests; Phase 1 remains the old-client characterization."""
import asyncio
import json
from types import SimpleNamespace as NS

import pytest

from test_session_generation import setup, req, request, events
from test_answer_stream_characterization import Probe, Gates, transport, A, B, FALLBACK_A, FALLBACK_B
from app import session_generation as sg, grpc_answer_pipeline as adapter
from app.answer_generation import GenerationControl, GenerationBudget, Deadlines, AttemptFailure, GenerationStopped
from app.answer_streaming import DisplayStream, LegacyRun, incremental_answers, legacy_provider_stream
from app.answer_models import FALLBACK_MODEL_KEY
from app.api import generate as api
from app.grpc_generated import interview_realtime_pb2 as pb


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
@pytest.mark.parametrize('scenario', ['primary', 'fallback', 'canonical', 'disconnect_fallback', 'stop_primary', 'stop_fallback', 'disconnect_primary'])
async def test_negotiated_gated_turn(setup, monkeypatch, source, scenario):
    _, store = setup
    probe = Probe()
    fallback = scenario in ('fallback', 'disconnect_fallback', 'stop_fallback')
    gates = Gates(probe, 'fallback' if fallback else 'primary')
    monkeypatch.setattr(sg, 'provider_stream', gates.provider)
    if scenario == 'canonical':
        # A formatter double at the production generator return boundary.
        generator_type = type(api.generator._default)
        generate = generator_type.generate_answer
        def formatted(self, **kwargs):
            result = generate(self, **kwargs)
            result['answer'] = 'Canonical replacement.'
            return result
        monkeypatch.setattr(generator_type, 'generate_answer', formatted)
    try:
        async with transport(monkeypatch, source, probe, version=1) as call:
            assert probe.payloads('wire_answer_stream_capabilities')[0].answer_stream_capabilities.version == 1
            gates.release['primary_a'].set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 1)
            first = probe.payloads('wire_answer_delta')[0]
            assert first.answer_delta.text == A[:-1]  # existing marker sanitizer retains a tail
            assert first.answer_identity.provider_attempt == first.answer_identity.display_revision == 0
            assert first.answer_identity.accepted_turn == 1 and first.request_id != 'start'
            assert probe.payloads('wire_answer_stream_capabilities')[0].sequence_number < first.sequence_number
            if scenario in ('stop_primary', 'disconnect_primary'):
                if scenario == 'stop_primary':
                    await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='stop', cancel=pb.Empty()))
                    await probe.until(lambda: any(x.status.code == 'canceled' for x in probe.payloads('wire_status')))
                else:
                    call.cancel()
                    await probe.until(lambda: 'primary' in gates.closed)
                assert gates.closed == ['primary'] and len(gates.calls) == 1 and not store.saves
                return
            gates.release['primary_b'].set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 2)
            assert not probe.payloads('wire_answer_completed')
            gates.release['primary_end'].set()
            if fallback:
                await probe.until(lambda: bool(probe.payloads('fallback_a_waiting')))
                await probe.until(lambda: bool(probe.payloads('wire_answer_replaced')))
                reset = probe.payloads('wire_answer_replaced')[-1]
                assert reset.answer_replaced.text == ''
                gates.release['fallback_a'].set()
                await probe.until(lambda: any(x.answer_identity.provider_attempt == 1 for x in probe.payloads('wire_answer_delta')))
                fallback = [x for x in probe.payloads('wire_answer_delta') if x.answer_identity.provider_attempt == 1]
                assert fallback[0].answer_identity.display_revision > first.answer_identity.display_revision
                assert fallback[0].sequence_number > reset.sequence_number
                if scenario == 'disconnect_fallback':
                    call.cancel()
                    await probe.until(lambda: 'fallback' in gates.closed)
                    assert not store.saves and len(gates.calls) == 2
                    return
                if scenario == 'stop_fallback':
                    await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='stop', cancel=pb.Empty()))
                    await probe.until(lambda: any(x.status.code == 'canceled' for x in probe.payloads('wire_status')))
                    assert gates.closed == ['primary', 'fallback'] and len(gates.calls) == 2 and not store.saves
                    return
                gates.release['fallback_b'].set()
                await probe.until(lambda: len([x for x in probe.payloads('wire_answer_delta') if x.answer_identity.provider_attempt == 1]) == 2)
                assert not probe.payloads('wire_answer_completed')
                gates.release['fallback_end'].set()
            await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
            final = probe.payloads('wire_answer_completed')[-1]
            expected = ('Canonical replacement.' if scenario == 'canonical' else
                        FALLBACK_A + FALLBACK_B if scenario == 'fallback' else A + B)
            assert final.answer_completed.text == expected
            assert probe.payloads('wire_answer_replaced')[-1].answer_replaced.text == expected
            assert len(store.saves) == 1 and final.answer_identity.retry_attempt == 0
            answer_events = [value for name, value, _ in probe.events
                             if name.startswith('wire_answer_') and name != 'wire_answer_stream_capabilities']
            assert len({value.request_id for value in answer_events}) == 1
            assert [value.sequence_number for value in answer_events] == sorted({value.sequence_number for value in answer_events})
    finally:
        gates.unblock()


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
async def test_unbound_streams_configured_provider_without_second_preparation(setup, monkeypatch, source):
    session, store = setup
    session.selected_model_key = None
    probe = Probe()
    first, second, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    selected = api.generator._default._select_primary_provider('Explain dependency injection', 'technical')
    calls = []
    async def fake(provider, kwargs, *args):
        calls.append((getattr(provider, 'name', 'ollama').lower(), provider.model, kwargs))
        probe.mark('legacy_entered')
        await first.wait()
        yield A
        await second.wait()
        yield B
        await finish.wait()
    monkeypatch.setattr('app.answer_streaming.legacy_provider_stream', fake)
    # A network double cannot change the generator's configured routing.
    try:
        async with transport(monkeypatch, source, probe, version=1):
            await probe.until(lambda: bool(probe.payloads('legacy_entered')))
            assert calls[0][0] == selected
            configured = getattr(api.generator._default, selected + '_provider').model
            assert calls[0][1] == configured and session.selected_model_key is None
            first.set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 1)
            second.set()
            await probe.until(lambda: len(probe.payloads('wire_answer_delta')) == 2)
            assert not probe.payloads('wire_answer_completed')
            finish.set()
            await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
            assert len(calls) == len(store.saves) == 1
    finally:
        first.set(); second.set(); finish.set()


@pytest.mark.asyncio
async def test_display_nested_retry_discards_queued_and_late_chunks_without_changing_provider_attempt():
    queue = asyncio.Queue(maxsize=8)
    control = GenerationControl()
    display = DisplayStream(queue, control, GenerationBudget(Deadlines()))
    old = await display.begin(0)
    await display.delta('old', 0, old)
    await display.reset()
    revision = await display.begin(0)  # nested generation call, same outer attempt
    await display.delta('late old', 0, old)
    await display.delta('new', 0, revision)
    values = [queue.get_nowait() for _ in range(queue.qsize())]
    assert values[-1] == dict(type='delta', text='new', attempt=0, revision=revision)
    assert not any(value.get('text') == 'late old' for value in values)
    assert revision > old and display.attempt == 0


@pytest.mark.asyncio
async def test_full_display_queue_is_cancelled_by_control_without_new_provider():
    waiting = asyncio.Event()
    class Queue(asyncio.Queue):
        async def put(self, value):
            if self.full():
                waiting.set()
            await super().put(value)
    queue = Queue(maxsize=1)
    control = GenerationControl()
    display = DisplayStream(queue, control, GenerationBudget(Deadlines()))
    await queue.put('occupied')
    task = asyncio.create_task(display.delta('blocked', 0, 0))
    await asyncio.wait_for(waiting.wait(), 5)
    control.cancel()
    with pytest.raises(GenerationStopped):
        await asyncio.wait_for(task, 5)
    assert queue.get_nowait() == 'occupied' and queue.empty()


@pytest.mark.asyncio
async def test_direct_fallback_selection_has_one_attempt(setup, monkeypatch):
    session, store = setup
    session.selected_model_key = FALLBACK_MODEL_KEY
    calls = []
    async def provider(client, model, *args):
        calls.append(model.key)
        yield A + B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    token = incremental_answers.set(True)
    try:
        items = await events(req())
    finally:
        incremental_answers.reset(token)
    assert calls == [FALLBACK_MODEL_KEY] and len(store.saves) == 1
    assert all(item.get('attempt', 0) == 0 for item in items)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['completed', 'checkpoint', 'processing', 'uncertain'])
async def test_negotiated_recovery_never_regenerates(setup, monkeypatch, state):
    _, store = setup
    calls = []
    async def provider(*args):
        calls.append(True)
        yield A + B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    token = incremental_answers.set(True)
    try:
        await events(req())
        row = next(iter(store.rows.values()))
        row['state'] = state
        before = len(store.saves)
        if state in ('processing', 'uncertain'):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as error:
                await events(req())
            assert error.value.detail['code'] == 'generation_' + state
        else:
            await events(req(recover_turn=True))
        assert len(calls) == 1
        assert len(store.saves) == before + (state == 'checkpoint')
    finally:
        incremental_answers.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize('version', [0, 7])
async def test_absent_or_unknown_capability_keeps_legacy_delivery(setup, monkeypatch, version):
    probe = Probe()
    calls = []
    async def provider(*args):
        calls.append(True)
        if len(calls) == 1:
            yield A, None, False
            raise AttemptFailure('provider_unavailable')
        yield FALLBACK_A + FALLBACK_B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async with transport(monkeypatch, 'microphone', probe, version=version):
        await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
        assert not probe.payloads('wire_answer_stream_capabilities')
        assert not probe.payloads('wire_answer_replaced')
        assert all(not item.HasField('answer_identity') for item in probe.payloads('wire_answer_delta'))
        assert all('passes' not in item.answer_delta.text for item in probe.payloads('wire_answer_delta'))


@pytest.mark.asyncio
async def test_adapter_rejects_duplicate_stale_and_post_terminal_events(setup, monkeypatch):
    from test_session_generation import SID
    async def detect(*args):
        return 'Explain dependency injection', ''
    monkeypatch.setattr(adapter, 'detect_intake_question', detect)
    items = [dict(type='start', sequence=0), dict(type='delta', sequence=1, text='primary'),
             dict(type='replace', sequence=2, answer='', attempt=1, revision=1),
             dict(type='delta', sequence=3, text='late', attempt=0, revision=0),
             dict(type='delta', sequence=4, text='fallback', attempt=1, revision=1),
             dict(type='delta', sequence=4, text='duplicate', attempt=1, revision=1),
             dict(type='metadata', sequence=5, metadata={'answer': 'final'}),
             dict(type='done', sequence=6), dict(type='delta', sequence=7, text='after terminal')]
    async def stream(*args, **kwargs):
        async def body():
            for item in items:
                yield json.dumps(dict(item, request_id='logical'))
        return NS(body_iterator=body())
    monkeypatch.setattr(api, 'generate_answer_stream', stream)
    cloud = NS(session_id=SID, request=request(), load=lambda: {})
    results = [item async for item in adapter.stream_question_answer('synthetic', cloud, 'logical', incremental=True)]
    assert [item['text'] for item in results if item['type'] == 'delta'] == ['primary', 'fallback']
    assert sum(item['type'] == 'completed' for item in results) == 1


def legacy_types():
    """Independent pool with the exact pre-v1 fields, executable on real transport."""
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
    file = descriptor_pb2.FileDescriptorProto()
    pb.DESCRIPTOR.CopyToProto(file)
    for message in list(file.message_type):
        if message.name in ('AnswerIdentity', 'AnswerStreamCapabilities'):
            file.message_type.remove(message)
        elif message.name == 'StartSession':
            for field in list(message.field):
                if field.number == 7:
                    message.field.remove(field)
            assert {f.name: f.number for f in message.field} == dict(mode=1, source=2, active_session_id=3,
                selected_resume_id=4, selected_job_context_id=5, cloud_context_requested=6)
        elif message.name == 'InterviewServerEvent':
            for field in list(message.field):
                if field.number in (6, 22, 23):
                    message.field.remove(field)
            assert [f.number for f in message.field] == [1, 2, 3, 4, 5, *range(10, 22)]
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file)
    return tuple(message_factory.GetMessageClass(pool.FindMessageTypeByName('intervuai.realtime.v1.' + name))
                 for name in ('InterviewClientEvent', 'InterviewServerEvent'))


@pytest.mark.asyncio
async def test_real_old_client_codec_against_new_handler(setup, monkeypatch):
    old_client, old_server = legacy_types()
    probe = Probe()
    async def provider(*args):
        yield A + B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async with transport(monkeypatch, 'microphone', probe, legacy_types=(old_client, old_server)):
        await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
        assert probe.payloads('wire_answer_completed')[0].answer_completed.text == A + B
        assert not probe.payloads('wire_answer_replaced')
        assert not probe.payloads('wire_answer_stream_capabilities')


@pytest.mark.asyncio
async def test_new_client_advertisement_against_real_old_codec_server():
    import grpc
    old_client, old_server = legacy_types()
    seen = []
    async def handler(requests, context):
        async for item in requests:
            seen.append(item)
            # Old implementation has no capability field or acknowledgement.
            yield old_server(session_id=item.session_id, request_id='turn', answer_delta={'text': A})
            yield old_server(session_id=item.session_id, request_id='turn', answer_completed={'text': A + B})
            return
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler('intervuai.realtime.v1.InterviewRealtimeService', {
        'StreamInterview': grpc.stream_stream_rpc_method_handler(handler,
            request_deserializer=old_client.FromString, response_serializer=lambda value: value.SerializeToString())}),))
    port = server.add_insecure_port('127.0.0.1:0')
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            from app.grpc_generated import interview_realtime_pb2_grpc as rpc
            call = rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=5)
            await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='start',
                start_session=pb.StartSession(mode='auto_pipeline', source='microphone', answer_stream_version=1)))
            await call.done_writing()
            received = [item async for item in call]
            assert not any(item.HasField('answer_stream_capabilities') for item in received)
            assert not any(item.HasField('answer_identity') for item in received)
            assert received[-1].answer_completed.text == A + B
            assert not hasattr(seen[0].start_session, 'answer_stream_version')
    finally:
        await server.stop(0)


def test_proto_copy_and_regenerated_messages_match(tmp_path):
    from pathlib import Path
    from grpc_tools import protoc
    root = Path(__file__).resolve().parents[2]
    source = root / 'backend/protos/interview_realtime.proto'
    assert source.read_bytes() == (root / 'frontend/electron/protos/interview_realtime.proto').read_bytes()
    assert protoc.main(['protoc', '-I' + str(source.parent), '--python_out=' + str(tmp_path),
                        '--grpc_python_out=' + str(tmp_path), str(source)]) == 0
    # Git may check generated source out with CRLF on Windows. Compare text
    # while still requiring every generated declaration to match exactly.
    assert (tmp_path / 'interview_realtime_pb2.py').read_text() == (root / 'backend/app/grpc_generated/interview_realtime_pb2.py').read_text()
    binding = (tmp_path / 'interview_realtime_pb2_grpc.py').read_text().replace(
        'import interview_realtime_pb2 as', 'from . import interview_realtime_pb2 as')
    assert binding == (root / 'backend/app/grpc_generated/interview_realtime_pb2_grpc.py').read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize('ollama', [False, True])
async def test_legacy_network_stream_preserves_configured_parameters_and_real_chunks(ollama):
    import httpx
    from app.nlp.answer_generator import StreamCancellation
    requested = []
    response_bytes = ([json.dumps(dict(response=A, done=False)), json.dumps(dict(response=B, done=True))] if ollama else
        ['data: ' + json.dumps(dict(choices=[dict(delta={'content': A}, finish_reason=None)])), '',
         'data: ' + json.dumps(dict(choices=[dict(delta={'content': B}, finish_reason='stop')])), ''])
    async def respond(request):
        requested.append(request)
        return httpx.Response(200, text='\n'.join(response_bytes) + '\n')
    provider = (NS(base_url='http://configured.invalid', model='configured-local', timeout=3) if ollama else
                NS(name='groq', url='https://configured.invalid/chat', model='configured-remote', api_key='test', timeout=3))
    kwargs = dict(prompt='synthetic') if ollama else dict(messages=[dict(role='user', content='synthetic')], temperature=.45, max_tokens=420)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        chunks = [text async for text in legacy_provider_stream(provider, kwargs, client, StreamCancellation(), lambda: None)]
    assert chunks == [A, B]
    body = json.loads(requested[0].content)
    assert body == dict(kwargs, model=provider.model, stream=True)


@pytest.mark.asyncio
async def test_legacy_openai_reuses_existing_sdk_stream_without_buffered_generation():
    import httpx
    from app.nlp.answer_generator import OpenAIResponsesProvider, StreamCancellation
    provider = OpenAIResponsesProvider()
    calls = []
    class Stream:
        def __iter__(self):
            yield NS(type='response.output_text.delta', delta=A)
            yield NS(type='response.output_text.delta', delta=B)
            yield NS(type='response.completed')
        def close(self):
            pass
    def create(**kwargs):
        calls.append(kwargs)
        return Stream()
    provider.api_key = 'test'
    provider.client = NS(responses=NS(create=create))
    provider.model = 'configured-sdk-model'
    async with httpx.AsyncClient() as client:
        chunks = [text async for text in legacy_provider_stream(provider,
            dict(instructions='synthetic', input_text='synthetic', max_output_tokens=111, reasoning_effort='low'),
            client, StreamCancellation(), lambda: None)]
    assert chunks == [A, B]
    assert len(calls) == 1 and calls[0]['stream'] and calls[0]['model'] == provider.model


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
async def test_terminal_failure_then_next_question_same_connection(setup, monkeypatch, source):
    from app import grpc_server
    monkeypatch.setattr(grpc_server, 'AUTO_COOLDOWN_SECONDS', 0)
    _, store = setup
    probe, turns, calls = Probe(), [], []
    async def provider(*args):
        calls.append(True)
        if len(calls) <= 2:
            yield A, None, False
            raise AttemptFailure('provider_unavailable')
        yield A + B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async with transport(monkeypatch, source, probe, version=1, turns=turns):
        await probe.until(lambda: bool(probe.payloads('wire_answer_error')))
        failed = probe.payloads('wire_answer_error')[-1]
        assert failed.answer_error.code == 'generation_failed'
        await turns[0].put(json.dumps(dict(type='Turn', transcript='Explain inversion of control', turn_order=1, end_of_turn=True)))
        await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
        final = probe.payloads('wire_answer_completed')[-1]
        assert failed.request_id != final.request_id
        assert failed.answer_identity.accepted_turn == 1 and final.answer_identity.accepted_turn == 2
        assert len(calls) == 3 and len(store.saves) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('unbound', [False, True])
@pytest.mark.parametrize('boundary', ['stop', 'disconnect'])
async def test_stop_during_validation_never_saves_or_regenerates(setup, monkeypatch, unbound, boundary):
    import threading
    session, store = setup
    if unbound:
        session.selected_model_key = None
    probe = Probe()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []
    operation = store.operation
    async def stored(op, *args, **kwargs):
        result = await operation(op, *args, **kwargs)
        if op == 'cancel':
            probe.mark('store_cancelled')
        return result
    monkeypatch.setattr(store, 'operation', stored)
    async def selected(*args):
        calls.append(True)
        yield A + B, None, True
    async def legacy(*args):
        calls.append(True)
        yield A + B
    monkeypatch.setattr(sg, 'provider_stream', selected)
    monkeypatch.setattr('app.answer_streaming.legacy_provider_stream', legacy)
    generator_type = type(api.generator._default)
    generate = generator_type.generate_answer
    def validated(self, **kwargs):
        result = generate(self, **kwargs)
        loop.call_soon_threadsafe(probe.mark, 'validation_held')
        assert release.wait(10)
        loop.call_soon_threadsafe(probe.mark, 'validation_released')
        return result
    monkeypatch.setattr(generator_type, 'generate_answer', validated)
    try:
        async with transport(monkeypatch, 'microphone', probe, version=1) as call:
            await probe.until(lambda: bool(probe.payloads('validation_held')))
            if boundary == 'stop':
                await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='stop', cancel=pb.Empty()))
                await probe.until(lambda: any(x.status.code == 'canceled' for x in probe.payloads('wire_status')))
            else:
                call.cancel()
                await probe.until(lambda: bool(probe.payloads('store_cancelled')))
            release.set()
            await probe.until(lambda: bool(probe.payloads('validation_released')))
            assert len(calls) == 1 and not store.saves
            assert not probe.payloads('wire_answer_completed')
    finally:
        release.set()


@pytest.mark.asyncio
async def test_handler_fences_stale_attempts_duplicate_replacements_and_post_terminal(setup, monkeypatch):
    async def pipeline(*args, **kwargs):
        yield dict(type='question', text='synthetic')
        yield dict(type='started', attempt=0, revision=0)
        yield dict(type='delta', text='old', attempt=0, revision=0)
        yield dict(type='replacement', text='', attempt=1, revision=2)
        yield dict(type='delta', text='stale', attempt=0, revision=0)
        yield dict(type='replacement', text='duplicate', attempt=1, revision=2)
        yield dict(type='delta', text='new', attempt=1, revision=2)
        yield dict(type='completed', attempt=1, revision=2)
        yield dict(type='delta', text='after terminal', attempt=1, revision=2)
    monkeypatch.setattr(adapter, 'stream_question_answer', pipeline)
    probe = Probe()
    async with transport(monkeypatch, 'microphone', probe, version=1):
        await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
        assert [x.answer_delta.text for x in probe.payloads('wire_answer_delta')] == ['old', 'new']
        assert [x.answer_replaced.text for x in probe.payloads('wire_answer_replaced')] == ['']
        assert probe.payloads('wire_answer_completed')[-1].answer_completed.text == 'new'


@pytest.mark.asyncio
async def test_coordinator_drops_queued_chunks_from_invalidated_revision(setup, monkeypatch):
    original = DisplayStream.reset
    async def reset(self):
        old = self.identity()
        await original(self)
        await self.put(dict(type='delta', text='POISON', **old))
    monkeypatch.setattr(DisplayStream, 'reset', reset)
    calls = []
    async def provider(*args):
        calls.append(True)
        if len(calls) == 1:
            raise AttemptFailure('provider_unavailable')
        yield A + B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    token = incremental_answers.set(True)
    try:
        items = await events(req())
    finally:
        incremental_answers.reset(token)
    assert not any(item.get('text') == 'POISON' for item in items)
    assert any(item['type'] == 'metadata' for item in items)


@pytest.mark.asyncio
async def test_legacy_rate_limit_retry_advances_revision_not_provider_attempt():
    import httpx
    requests = []
    async def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, json={'error': {'type': 'rate_limit'}})
        return httpx.Response(200, text='data: ' + json.dumps(dict(choices=[dict(delta={'content': A + B}, finish_reason='stop')])) + '\n\n')
    provider = NS(name='groq', url='https://configured.invalid/chat', model='configured', api_key='test', timeout=3,
                  _parse_error_payload=lambda response: ('rate_limit', None, 0))
    queue = asyncio.Queue(maxsize=8)
    display = DisplayStream(queue, GenerationControl(), GenerationBudget(Deadlines()))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        run = LegacyRun(display, asyncio.get_running_loop(), client)
        result = await run.call(provider, dict(messages=[], temperature=.45, max_tokens=420, retry_on_rate_limit=True), True)
    items = [queue.get_nowait() for _ in range(queue.qsize())]
    assert result == A + B and len(requests) == 2 and provider.last_retry_used
    assert items[0] == dict(type='replace', answer='', attempt=0, revision=1)
    assert all(item['attempt'] == 0 and item['revision'] == 1 for item in items)


@pytest.mark.asyncio
async def test_unbound_buffered_correction_has_no_display_chunks(monkeypatch):
    import httpx
    queue = asyncio.Queue(maxsize=8)
    display = DisplayStream(queue, GenerationControl(), GenerationBudget(Deadlines()))
    await display.begin(0)
    async def provider(*args):
        yield 'Correction '
        yield 'output.'
    monkeypatch.setattr('app.answer_streaming.legacy_provider_stream', provider)
    async with httpx.AsyncClient() as client:
        run = LegacyRun(display, asyncio.get_running_loop(), client)
        result = await run.call(NS(), {}, False)
    assert result == 'Correction output.' and queue.empty()
    assert display.revision == 0 and run.calls == 0


@pytest.mark.asyncio
async def test_unmanaged_route_declines_capability_but_has_unique_answer_identity(setup, monkeypatch):
    monkeypatch.setattr(api.settings, 'ENABLE_SESSION_ANSWER_MODELS', False)
    async def pipeline(*args, **kwargs):
        yield dict(type='question', text='synthetic')
        yield dict(type='delta', text=A + B)
        yield dict(type='completed')
    monkeypatch.setattr(adapter, 'stream_question_answer', pipeline)
    probe = Probe()
    async with transport(monkeypatch, 'microphone', probe, version=1):
        await probe.until(lambda: bool(probe.payloads('wire_answer_completed')))
        assert not probe.payloads('wire_answer_stream_capabilities')
        final = probe.payloads('wire_answer_completed')[-1]
        assert final.request_id != 'start' and not final.HasField('answer_identity')


@pytest.mark.asyncio
@pytest.mark.parametrize('selected', ['openai', 'groq', 'ollama'])
async def test_unbound_keeps_each_configured_legacy_route(setup, monkeypatch, selected):
    session, store = setup
    session.selected_model_key = None
    monkeypatch.setattr(api.generator._default, '_select_primary_provider', lambda *args: selected)
    calls = []
    async def provider(current, kwargs, *args):
        calls.append((getattr(current, 'name', 'ollama').lower(), current.model))
        yield A + B
    monkeypatch.setattr('app.answer_streaming.legacy_provider_stream', provider)
    token = incremental_answers.set(True)
    try:
        items = await events(req())
    finally:
        incremental_answers.reset(token)
    assert calls == [(selected, getattr(api.generator._default, selected + '_provider').model)]
    assert len(store.saves) == 1 and session.selected_model_key is None
    assert any(item['type'] == 'delta' for item in items)
    final = next(item['metadata'] for item in items if item['type'] == 'metadata')
    assert final['provider'] == selected and final['model'] == calls[0][1]


@pytest.mark.asyncio
async def test_unbound_fallback_is_owned_by_existing_generator(setup, monkeypatch):
    from app.nlp.answer_generator import ProviderError
    session, store = setup
    session.selected_model_key = None
    monkeypatch.setattr(api.generator._default, '_select_primary_provider', lambda *args: 'openai')
    monkeypatch.setattr(api.settings, 'ENABLE_ANSWER_PROVIDER_FALLBACK', True)
    monkeypatch.setattr(api.settings, 'ANSWER_FALLBACK_PROVIDER', 'groq')
    calls = []
    async def provider(current, kwargs, *args):
        calls.append(current.name.lower())
        if current.name == 'openai':
            yield 'Failed provisional.'
            raise ProviderError('synthetic failure', provider='openai', error_type='unavailable')
        yield A + B
    monkeypatch.setattr('app.answer_streaming.legacy_provider_stream', provider)
    token = incremental_answers.set(True)
    try:
        items = await events(req())
    finally:
        incremental_answers.reset(token)
    assert calls == ['openai', 'groq'] and len(store.saves) == 1
    fallback = next(index for index, item in enumerate(items) if item['type'] == 'delta' and item['attempt'] == 1)
    assert any(item['type'] == 'replace' and item['answer'] == '' for item in items[:fallback])
    assert next(item['metadata'] for item in items if item['type'] == 'metadata')['fallback_used']


@pytest.mark.asyncio
async def test_concurrent_http_and_capable_policy_do_not_bleed(setup, monkeypatch):
    _, store = setup
    async def provider(client, model, *args):
        if model.key != FALLBACK_MODEL_KEY:
            yield A, None, False
            raise AttemptFailure('provider_unavailable')
        yield FALLBACK_A + FALLBACK_B, None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async def consume(capable, turn):
        token = incremental_answers.set(capable)
        try:
            return await events(req(turn=turn))
        finally:
            incremental_answers.reset(token)
    capable, http = await asyncio.gather(consume(True, 'capable'), consume(False, 'http'))
    assert any(item['type'] == 'delta' and item['attempt'] == 1 for item in capable)
    assert not any(item['type'] == 'delta' and item.get('attempt') == 1 for item in http)
    assert all('revision' in item for item in capable)
    assert all('revision' not in item for item in http)
    assert len(store.saves) == 2 and not incremental_answers.get()
