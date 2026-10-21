"""Offline closeout evidence, not a human-quality or real-latency evaluation."""
import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import time

import pytest

from answer_quality_spec import CASES
from app.answer_generation import GenerationBudget, GenerationControl, Deadlines, GenerationStopped
from app.answer_streaming import DisplayStream

spec = importlib.util.spec_from_file_location('review_tool', Path(__file__).parents[1] / 'scripts/answer_quality_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def samples(version):
    return dict(revision=version, sample_origin='authored_fixture', samples=[dict(case_id=case['id'],
        answer=f'Authored {version} fixture; not a measured model output.', model='synthetic-model',
        profile='synthetic-profile', settings={'output_limit': 2500}, input_sha256=review.input_hash(case),
        attempt_role='primary', sample_index=0) for case in CASES])


def test_blinding_is_paired_reproducible_and_discloses_authored_outputs():
    before, after = samples('before'), samples('after')
    pack, key = review.review_pack(before, after, 42)
    assert (pack, key) == review.review_pack(before, after, 42)
    assert len(pack['reviews']) == 24 and not pack['measured_model_outputs']
    assert {item['A'] for item in key['assignments']} == {'baseline', 'candidate'}
    assert all('revision' not in item and 'model' not in item for item in pack['reviews'])
    assert review.review_pack(before, after, 43)[1]['assignments'] != key['assignments']
    assert before == samples('before')  # No shared input mutation.


@pytest.mark.parametrize('change', ['missing', 'budget', 'input', 'duplicate', 'origin'])
def test_review_rejects_unpaired_or_invented_baselines(change):
    before, after = samples('before'), samples('after')
    if change == 'missing': before['samples'][0]['answer'] = ''
    if change == 'budget': after['samples'][0]['settings']['output_limit'] += 1
    if change == 'input': after['samples'][0]['input_sha256'] = 'wrong'
    if change == 'duplicate': after['samples'].append(deepcopy(after['samples'][0]))
    if change == 'origin': before['sample_origin'] = 'unknown'
    with pytest.raises(ValueError): review.review_pack(before, after, 42)


def test_budget_capture_does_not_inherit_shared_coding_cooldown(monkeypatch):
    from answer_quality_baseline import budget_capture
    from app.nlp import answer_generator as ag
    from app.nlp.answer_planner import build_answer_plan
    marker = 'groq::' + ag.settings.CODING_GROQ_MODEL
    monkeypatch.setitem(ag._PRIMARY_RATE_LIMIT_COOLDOWNS, marker, time.time() + 600)
    plan = build_answer_plan(question='Implement distinct values in Python.', category='technical')
    result = budget_capture('Synthetic code prompt', plan, context_type='coding', coding=True)
    assert result['groq']['max_tokens'] == ag.settings.CODING_MAX_TOKENS
    assert ag._PRIMARY_RATE_LIMIT_COOLDOWNS[marker] > time.time()


@pytest.mark.asyncio
async def test_long_display_is_progressive_and_cancel_remains_responsive_under_backpressure(record_property):
    class GatedQueue(asyncio.Queue):
        def __init__(self):
            super().__init__(maxsize=1)
            self.blocked = asyncio.Event()
        async def put(self, item):
            if self.full():
                self.blocked.set()
            await super().put(item)
    queue = GatedQueue()
    control = GenerationControl()
    display = DisplayStream(queue, control, GenerationBudget(Deadlines()))
    start = time.perf_counter()
    revision = await display.begin(0)
    await display.delta('prefix A ', 0, revision)
    first = await queue.get()
    first_ms = (time.perf_counter() - start) * 1000
    await display.delta('prefix B ', 0, revision)
    second = await queue.get()
    assert first['text'] != second['text']
    await display.delta('x' * 23000, 0, revision)
    blocked = asyncio.create_task(display.delta('held final chunk', 0, revision))
    # Explicit gate: provider completion cannot proceed through the full queue.
    await asyncio.wait_for(queue.blocked.wait(), 2)
    assert not blocked.done() and queue.qsize() == 1
    stopped = time.perf_counter(); control.cancel()
    with pytest.raises(GenerationStopped): await asyncio.wait_for(blocked, 2)
    record_property('display_first_delta_local_ms', round(first_ms, 3))
    record_property('cancel_local_ms', round((time.perf_counter() - stopped) * 1000, 3))

@pytest.mark.asyncio
async def test_grpc_stop_wins_completion_cancellation_race(monkeypatch):
    """Force the real wait_for completion/cancel race, without timing sleeps."""
    import grpc
    from app import grpc_server, grpc_answer_pipeline
    from app.grpc_generated import interview_realtime_pb2 as pb
    from app.grpc_generated import interview_realtime_pb2_grpc as rpc
    from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
    for name in ('USE_GRPC_AUTO_PIPELINE','GRPC_STT_ENABLED','GRPC_ANSWER_STREAM_ENABLED'):
        monkeypatch.setattr(grpc_server.settings,name,True)
    release=asyncio.Event(); cancelled=[]; closed=asyncio.Event(); calls=[]
    class Socket:
        def __init__(self): self.events=asyncio.Queue()
        def __aiter__(self): return self
        async def __anext__(self): return await self.events.get()
        async def send(self,data): pass
        async def close(self): closed.set()
    socket=Socket()
    async def connect(self): await socket.events.put('{"type":"Begin"}'); return socket
    async def answer(text):
        calls.append(1)
        yield {'type':'question','text':text}
        yield {'type':'delta','text':'Synthetic complete answer.'}
        yield {'type':'completed'}
        await release.wait()
    original_wait=asyncio.wait_for
    async def force_completion_race(aw,timeout):
        if getattr(getattr(aw,'cr_code',None),'co_name',None)=='generate' and timeout==90:
            owner=asyncio.current_task(); original_cancel=owner.cancel
            def cancel(*args,**kwargs):
                if not cancelled:
                    cancelled.append(1)
                    # Complete inner awaitable in the same loop iteration as Stop.
                    # Python 3.10 wait_for may return its result instead of propagating
                    # the outer cancellation; production must still honor Stop.
                    release.set()
                return original_cancel(*args,**kwargs)
            monkeypatch.setattr(owner,'cancel',cancel)
        return await original_wait(aw,timeout)
    monkeypatch.setattr(AssemblyAIStreamingBridge,'connect',connect)
    monkeypatch.setattr(grpc_answer_pipeline,'stream_question_answer',answer)
    monkeypatch.setattr(grpc_answer_pipeline,'detect_intake_question',lambda *a,**kw:None)
    async def detect(*a,**kw): return 'Explain a synthetic concept.',''
    monkeypatch.setattr(grpc_answer_pipeline,'detect_intake_question',detect)
    monkeypatch.setattr(asyncio,'wait_for',force_completion_race)
    server,port=await grpc_server.start_server(port=0)
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            call=rpc.InterviewRealtimeServiceStub(channel).StreamInterview(timeout=3)
            await call.write(pb.InterviewClientEvent(session_id='synthetic-race',start_session=pb.StartSession(mode='auto_pipeline')))
            async def until(predicate):
                while True:
                    item=await call.read()
                    assert item is not grpc.aio.EOF
                    if predicate(item): return item
            await until(lambda item:item.status.code=='answer_stream_enabled')
            await socket.events.put('{"type":"Turn","transcript":"Explain a synthetic concept.","turn_order":0,"end_of_turn":true}')
            await until(lambda item:item.HasField('answer_completed'))
            await call.write(pb.InterviewClientEvent(session_id='synthetic-race',end_session=pb.Empty()))
            await until(lambda item:item.status.code=='ended')
            assert closed.is_set() and calls==[1] and cancelled==[1]
            call.cancel()
    finally:
        release.set()
        await server.stop(0)
