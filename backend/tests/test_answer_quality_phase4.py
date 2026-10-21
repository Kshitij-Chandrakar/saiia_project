"""Synthetic evidence-selection contracts; run with the guarded offline runner."""
import asyncio
import json
import threading
from types import SimpleNamespace as NS

import pytest

from app.services.resume_index_service import ResumeIndexService, relevant_excerpt
from app.nlp.answer_generator import AnswerGenerator
from app.nlp.answer_planner import build_answer_plan
from app.nlp.followup_resolver import resolve_live_followup
from app.nlp.followup_intent_compiler import compile_followup_intent
from app.cloud.cloud_resume import CloudResumeService, CloudResumeValidationError
from test_cloud_resume import FakeCloudResumeClient, FakeParser, _record, USER_A, USER_B, RESUME_ID
from test_session_generation import setup, req, request, events


def chunks(*documents):
    return ResumeIndexService().build_chunks_from_documents(
        [dict(section=section, text=text) for section, text in documents])


def cloud(documents):
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status='ready', active_chunk_generation='synthetic-generation')
    for item in documents:
        client.chunks.append(dict(user_id=USER_A, resume_id=RESUME_ID, generation_id='synthetic-generation',
                                 section=item['section'], chunk_text=item['text'], metadata=item))
    return CloudResumeService(client=client, parser=FakeParser())


def entry(**overrides):
    return dict(dict(entry_id='synthetic-turn', mode='answer', question='Implement distinct values.',
        topic='distinct values', created_at=9999999999, status='complete',
        code='def unique(xs):\n    return list(dict.fromkeys(xs))', programming_language='python',
        function_signature='unique(xs)', answer_excerpt='Keep insertion order; inputs must be hashable.'), **overrides)


def compile_context(question, context):
    resolution = resolve_live_followup(question=question, mode='answer', context_entries=context)
    return compile_followup_intent(question=question, mode='answer', context_entries=context, resolution=resolution)


@pytest.mark.parametrize('category', ['technical', 'behavioral', 'resume-based'])
def test_section_boost_is_not_evidence_of_a_match(category):
    result = ResumeIndexService().retrieve_from_chunks(chunks(
        ('projects', 'Weather Console - Displays forecasts.'),
        ('experience', 'Maintained a calendar.')), question='Quantum cryptography expertise?', category=category)
    assert not result['retrieval_used'] and result['retrieved_chunk_count'] == 0


def test_relevance_precedes_unrelated_category_boost_and_duplicates_do_not_displace_facts():
    evidence = chunks(('projects', 'Weather Console - Displays forecasts.'),
                      ('experience', 'Used semaphore coordination for workers.'),
                      ('experience', 'Used semaphore coordination for workers.'),
                      ('experience', 'Semaphore timeout is 40 ms.'))
    selected = ResumeIndexService().retrieve_from_chunks(evidence,
        question='What semaphore coordination and timeout did you use?', category='technical', limit=3)['retrieved_chunks']
    assert len(selected) == 2
    assert {item['text'] for item in selected} == {'Used semaphore coordination for workers.', 'Semaphore timeout is 40 ms.'}
    assert all(item['source'] == 'resume' and item['chunk_id'] for item in selected)


def test_snippet_selection_does_not_restore_irrelevant_first_chunks():
    generator = AnswerGenerator()
    evidence = chunks(*[('projects', f'Unrelated Weather {i} - Displays forecasts.') for i in range(4)],
                      ('experience', 'Used semaphore coordination for workers.'))
    selected = generator._select_retrieved_snippets(question='What semaphore coordination did you use?',
                                                   question_type='technical', retrieved_snippets=evidence)
    assert len(selected) == 1 and 'semaphore' in selected[0]['text']


def test_selected_resume_no_match_is_empty_not_first_chunk_fallback():
    service = cloud(chunks(('education', 'Studied biology.'), ('achievements', 'Won a poetry award.')))
    result = service.retrieve_resume_chunks(user_id=USER_A, resume_id=RESUME_ID,
        question='Quantum cryptography expertise?', category='technical')
    assert not result['retrieval_used'] and result['retrieved_chunks'] == []


@pytest.mark.asyncio
async def test_selected_no_match_does_not_fall_back_to_conflicting_profile(monkeypatch):
    from app.api import generate as api
    from fastapi import HTTPException
    service = cloud(chunks(('education', 'Studied biology.')))
    monkeypatch.setattr(api, '_current_user_for_selected_resume', lambda *args: NS(user_id=USER_A))
    monkeypatch.setattr(api, '_new_cloud_resume_service', lambda: service)
    monkeypatch.setattr(api.generator, 'generate_answer', lambda **kwargs: pytest.fail('no-match must not generate'))
    with pytest.raises(HTTPException) as failure:
        await api.generate_answer(api.GenerateRequest(question='Quantum cryptography expertise?', category='technical',
            selected_resume_id=RESUME_ID, profile_context_used=True,
            profile={'experience': 'Conflicting profile claims quantum cryptography experience.'}))
    assert failure.value.status_code == 409


@pytest.mark.parametrize('title', ['Atlas Scheduler', 'Atlas Scheduler Analytics'])
def test_exact_project_identity_does_not_mix_similar_projects(title):
    service = cloud(chunks(('projects', 'Atlas Scheduler - Built appointment APIs; reduced duplicate bookings by 12%.'),
                          ('projects', 'Atlas Scheduler Analytics - Built forecast dashboards.'),
                          ('projects', 'Atlas Analytics - Built chart exports.')))
    result = service.retrieve_resume_chunks(user_id=USER_A, resume_id=RESUME_ID,
        question=f'Explain your "{title}" project.', category='general')
    assert result['matched_project_name'] == title
    assert len(result['retrieved_chunks']) == 1
    assert result['retrieved_chunks'][0]['text'].startswith(title + ' - ')


def test_missing_project_does_not_substitute_another_project():
    service = cloud(chunks(('projects', 'Atlas Scheduler - Built appointment APIs.')))
    with pytest.raises(CloudResumeValidationError, match='not found'):
        service.retrieve_resume_chunks(user_id=USER_A, resume_id=RESUME_ID,
            question='Explain your "Lunar Rover" project.', category='general')


@pytest.mark.parametrize('owner', [USER_A, USER_B])
def test_selected_resume_scope_is_owned_and_never_merged(owner):
    service = cloud(chunks(('experience', 'Used semaphore coordination.')))
    if owner == USER_B:
        from app.cloud.cloud_resume import CloudResumeNotFoundError
        with pytest.raises(CloudResumeNotFoundError):
            service.retrieve_resume_chunks(user_id=owner, resume_id=RESUME_ID, question='Semaphore?', category='technical')
    else:
        result = service.retrieve_resume_chunks(user_id=owner, resume_id=RESUME_ID, question='Semaphore?', category='technical')
        assert len(result['retrieved_chunks']) == 1


def test_bounded_excerpts_retain_tail_fact_and_do_not_change_supplied_metric():
    text = 'General introductory material. ' * 40 + 'Sharding reduced query latency by 12%.'
    excerpt = relevant_excerpt(text, 'Explain sharding latency.', 320)
    assert len(excerpt) <= 320 and 'Sharding reduced query latency by 12%.' in excerpt
    assert relevant_excerpt('A supplied short fact.', 'unmatched', 320) == 'A supplied short fact.'


def test_profile_and_jd_tail_evidence_reaches_prompt_without_becoming_experience():
    generator = AnswerGenerator()
    profile = dict(projects='Weather Console - Displays forecasts.\n' + 'Unrelated description. ' * 30
                   + '\nAtlas Scheduler - Added sharding; measured 12% lower query latency.')
    lines = generator._profile_context_lines(profile=profile, question='Explain your Atlas Scheduler sharding project.',
                                             question_type='general')
    assert '12% lower query latency' in '\n'.join(lines)
    question = 'Why should we hire you for sharding?'
    plan = build_answer_plan(question=question, category='hr')
    prompt = generator._build_interview_prompt(question=question, plan=plan, profile=profile,
        job_context={'job_description': 'General company information. ' * 40 + 'Role requires sharding expertise.'})
    assert 'Role requires sharding expertise.' in prompt
    # Reconstruct the source-confirmed old prefix selection, not a model output.
    old_excerpt = ('General company information. ' * 40 + 'Role requires sharding expertise.')[:700]
    assert 'Role requires sharding expertise.' not in old_excerpt
    assert 'Job requirements tailor relevance, never establish candidate achievements' in prompt
    assert len(relevant_excerpt('General company information. ' * 40 + 'Role requires sharding expertise.', question, 700)) <= 700


@pytest.mark.asyncio
async def test_prepared_context_isolated_for_same_question_across_users_and_sessions():
    from app import session_generation as sg
    gate = asyncio.Event()
    calls = []
    @sg.cached_context
    def retrieve(owner, session, question):
        calls.append((owner, session))
        return {'source': [owner, session], 'question': question}
    async def turn(owner, session):
        token = sg._prepared.set({})
        try:
            first = retrieve(owner, session, 'Explain your project.')
            first['source'].append('mutated-return-copy')
            if len(calls) == 3:
                gate.set()
            await asyncio.wait_for(gate.wait(), 10)
            return retrieve(owner, session, 'Explain your project.')
        finally:
            sg._prepared.reset(token)
    result = await asyncio.gather(turn('owner-a', 'session-a'), turn('owner-a', 'session-b'),
                                  turn('owner-b', 'session-c'))
    assert [item['source'] for item in result] == [['owner-a', 'session-a'], ['owner-a', 'session-b'],
                                                 ['owner-b', 'session-c']]
    assert len(calls) == 3 and sg._prepared.get() is None


@pytest.mark.parametrize('question', ['Now write it in Java.', 'Explain that empty input edge case.',
                                      'Explain that loop.', 'Show another approach to it.'])
def test_followup_keeps_exact_request_code_and_constraint_as_conversation_only(question):
    plan = compile_context(question, [entry()])
    assert not plan.needs_clarification
    assert plan.reference_context['code'] == entry()['code']
    assert 'hashable' in plan.reference_context['answer_excerpt']
    assert plan.reference_context['function_signature'] == 'unique(xs)'
    assert entry()['code'] not in plan.resolved_question
    if question.startswith('Now'):
        assert plan.programming_language == 'java' and question in plan.resolved_question
    if 'edge case' in question:
        assert 'empty input' in plan.resolved_question


@pytest.mark.parametrize('state', ['failed', 'provisional', 'discarded', 'generating', 'pending'])
def test_explicit_nonfinal_history_is_not_a_reference(state):
    plan = compile_context('Now write it in Java.', [entry(status=state)])
    assert plan.needs_clarification and not plan.reference_context


def test_history_ttl_mode_limit_and_ambiguity_are_preserved():
    old = entry(created_at=1)
    assert compile_context('Now write it in Java.', [old]).needs_clarification
    assert compile_context('Now write it in Java.', [entry(mode='screen')]).needs_clarification
    assert compile_context('How does it work?', [entry(topic='authentication and authorization')]).needs_clarification
    plan = compile_context('Explain that loop.', [entry(code='x' * 6000, answer_excerpt='z' * 6000)])
    assert len(plan.reference_context['code']) == 4000 and len(plan.reference_context['answer_excerpt']) == 1000


@pytest.mark.asyncio
async def test_endpoint_keeps_followup_context_separate_from_evidence_permissions(monkeypatch):
    from app.api import generate as api
    captured = []
    def generate(**kwargs):
        captured.append(kwargs)
        return dict(answer='An authored synthetic explanation.', provider='openai', model='synthetic',
                    fallback_used=False, error=None, generation_ms=0)
    monkeypatch.setattr(api.generator, 'generate_answer', generate)
    await api.generate_answer(api.GenerateRequest(question='Explain that loop.', category='technical',
        profile_context_used=False, followup_mode='answer', followup_context=[entry(
            answer_excerpt='The previous generated answer claimed I led 50 engineers.')]))
    assert len(captured) == 1
    assert captured[0]['answer_plan'].profile_context_policy == 'FORBIDDEN'
    assert 'led 50 engineers' not in captured[0]['question']
    assert 'led 50 engineers' in captured[0]['conversation_context']['answer_excerpt']


@pytest.mark.asyncio
async def test_selected_primary_fallback_reuses_prepared_evidence_once(setup, monkeypatch):
    from app import session_generation as sg
    from app.api import generate as api
    from app.answer_generation import AttemptFailure
    session, store = setup
    loads, calls = [], []
    # Wrap the production cache rather than mock the preparation path away.
    @sg.cached_context
    def retrieve(**kwargs):
        loads.append(kwargs['question'])
        return dict(retrieval_used=False, retrieved_chunks=[], retrieval_ms=0)
    monkeypatch.setattr(api, '_retrieve_resume_context', retrieve)
    async def provider(client, model, prepared, key):
        calls.append(prepared)
        if len(calls) == 1:
            raise AttemptFailure('provider_unavailable')
        yield 'Dependency injection supplies dependencies externally.', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    result = await events(req())
    assert len(loads) == 1 and len(calls) == 2 and calls[0] == calls[1]
    assert len(store.saves) == 1 and any(e['type'] == 'metadata' for e in result)


@pytest.mark.asyncio
@pytest.mark.parametrize('unbound', [False, True])
async def test_late_context_preparation_after_cancellation_cannot_generate_or_save(setup, monkeypatch, unbound):
    from app import session_generation as sg
    from app.api import generate as api
    from test_answer_stream_characterization import Probe
    probe = Probe()
    loop = asyncio.get_running_loop()
    gate = threading.Event()
    finished = threading.Event()
    session, store = setup
    if unbound:
        session.selected_model_key = None
    monkeypatch.setattr(api.settings, 'ANSWER_PROVIDER', 'openai')
    calls = []
    @sg.cached_context
    def retrieve(**kwargs):
        loop.call_soon_threadsafe(probe.mark, 'retrieval_held')
        try:
            assert gate.wait(10)
            return dict(retrieval_used=False, retrieved_chunks=[], retrieval_ms=0)
        finally:
            finished.set()
    monkeypatch.setattr(api, '_retrieve_resume_context', retrieve)
    async def provider(*args):
        calls.append(True)
        yield 'Must not generate.', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    def legacy_provider(**kwargs):
        calls.append(True)
        return 'Dependency injection supplies dependencies externally.'
    monkeypatch.setattr(api.generator._default.openai_provider, 'generate', legacy_provider)
    original = api.generate_answer
    async def generated(*args, **kwargs):
        try:
            return await original(*args, **kwargs)
        finally:
            loop.call_soon_threadsafe(probe.mark, 'worker_finished')
    monkeypatch.setattr(api, 'generate_answer', generated)
    task = asyncio.create_task(events(req()))
    try:
        await probe.until(lambda: bool(probe.payloads('retrieval_held')))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        gate.set()
        assert await asyncio.to_thread(finished.wait, 10)
        await probe.until(lambda: bool(probe.payloads('worker_finished')))
        # Thread-owned provider facade sees run.active=False before any network work.
        assert not calls and not store.saves
    finally:
        gate.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal_failure', [False, True])
async def test_grpc_uses_latest_completed_anchor_and_keeps_connection_histories_separate(monkeypatch, terminal_failure):
    from app import grpc_answer_pipeline as adapter
    from app.api import generate as api
    from app.api.question_detect import classifier
    from starlette.responses import StreamingResponse
    received = []
    async def detect(text):
        return text, ''
    async def response(body, request=None):
        received.append(body.followup_context)
        async def lines():
            ending = [dict(type='error', error='generation_failed')] if terminal_failure else [
                dict(type='metadata', metadata={'transcript_entry_stored': True}), dict(type='done')]
            for event in [dict(type='delta', text='```python\nprint(1)\n```'), *ending]:
                yield json.dumps(event) + '\n'
        return StreamingResponse(lines())
    monkeypatch.setattr(adapter, 'detect_intake_question', detect)
    monkeypatch.setattr(classifier, 'classify_question', lambda text: 'technical')
    monkeypatch.setattr(api, 'generate_answer_stream', response)
    monkeypatch.setattr(api.settings, 'ENABLE_SESSION_ANSWER_MODELS', True)
    first = NS(session_id='synthetic-one', request=request(), load=lambda: {'profile_context_used': False},
               _answer_history=[entry(entry_id='older', topic='queue'), entry(entry_id='newer', topic='stack')])
    second = NS(session_id='synthetic-two', request=request(), load=lambda: {'profile_context_used': False})
    for context in [first, second]:
        if terminal_failure:
            from app.answer_generation import GenerationFailure
            with pytest.raises(GenerationFailure):
                [event async for event in adapter.stream_question_answer('Explain that loop.', context, 'new-turn')]
        else:
            result = [event async for event in adapter.stream_question_answer('Explain that loop.', context, 'new-turn')]
            assert result[-1]['type'] == 'completed'
    assert [item['entry_id'] for item in received[0]] == ['newer', 'older']
    assert received[1] == []
    if terminal_failure:
        assert [item['entry_id'] for item in first._answer_history] == ['older', 'newer']
        assert not getattr(second, '_answer_history', [])
    else:
        assert first._answer_history[-1]['status'] == 'complete'
        assert first._answer_history[-1]['code'] == 'print(1)\n'
        assert first._answer_history[-1]['programming_language'] == 'python'
