"""Phase 3 desired contracts, separate from historical Phase 1 captures.

Run through answer_quality_baseline.py --tests so external calls fail closed
before application imports. All evidence and provider responses are synthetic.
"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from app.nlp import answer_generator as ag
from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.nlp.answer_planner import build_answer_plan
from app.nlp.answer_variation import AnswerVariationHistory
from test_session_generation import setup, req, request


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.setattr(ag.settings, 'ANSWER_PROVIDER', 'openai')
    monkeypatch.setattr(ag.settings, 'REFINEMENT_ENABLED', False)
    monkeypatch.setattr(ag.settings, 'ENABLE_SEMANTIC_VALIDATION', False)
    monkeypatch.setattr(ag.settings, 'ENABLE_CONTROLLED_ANSWER_VARIATION', True)
    monkeypatch.setattr(ag.settings, 'ENABLE_VARIATION_REWRITE', True)
    instance = AnswerGenerator()
    instance.variation_history = AnswerVariationHistory()
    return instance


@pytest.mark.parametrize('answer', [
    ' '.join(f'Detail{i}' for i in range(350)) + ' completes the explanation.',
    'Use a queue.\nAlternatively: use synchronous delivery.\nAnother option is polling.\nIn conclusion, choose by latency.',
    '**Tradeoffs**\n\n1. Preserve ordering.\n2. Bound memory.\n\nKeep `max_queue_size` explicit.',
    '```python\nvalue = "**literal**"\n\n\nprint(value)\n```',
    'An incomplete provider sentence ending with and',
    'Compute a - b - c, keeping `max_queue_size` unchanged.',
])
def test_sanitation_preserves_content_and_does_not_fake_sentence_completion(generator, answer):
    assert generator._clean_answer(answer) == answer
    assert generator._clean_answer('[[category:technical]]\n' + answer) == answer


@pytest.mark.parametrize('question,followup', [
    ('In one sentence, explain caching.', False),
    ('Compare SQL and NoSQL in a table.', False),
    ('Explain only its invalidation tradeoff.', True),
    ('Tell me about a conflict you resolved.', False),
])
def test_refinement_uses_same_plan_and_authorized_evidence(generator, question, followup):
    plan = build_answer_plan(question=question, category='behavioral' if 'conflict' in question else 'technical',
                             followup=followup)
    initial = generator._build_prompt(question, plan.source_category,
                                     profile={'projects': 'Synthetic scheduler API.'}, answer_plan=plan)
    prompt = generator._build_refinement_prompt(
        question=question, question_type=plan.source_category, profile={'projects': 'WRONG later context'},
        retrieved_snippets=None, job_context=None, groq_answer='In a hypothetical situation, I would check constraints.',
        answer_plan=plan, policy_context=initial)
    assert initial in prompt and 'WRONG later context' not in prompt
    assert 'not evidence of personal history' in prompt
    assert '100 to 160 words' not in prompt
    assert "Then write 'Real-life example:'" not in prompt
    assert 'Keep explicit hypothetical framing' in prompt
    assert plan.prompt_instructions() in prompt


def test_semantic_correction_carries_request_policy_evidence_and_complete_answer(generator, monkeypatch):
    question = 'Tell me about a difficult bug you solved.'
    plan = build_answer_plan(question=question, category='behavioral')
    policy = generator._build_prompt(question, 'behavioral',
        profile={'projects': 'Synthetic scheduler API; candidate added a uniqueness constraint.'},
        job_context={'job_description': 'Role requires Kubernetes, not candidate experience.'}, answer_plan=plan)
    answer = 'In a hypothetical situation, I would check constraints. ' + 'detail ' * 1000 + 'END_OF_ANSWER'
    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        if kwargs['phase'] == 'semantic_validation':
            return '{"valid":false,"severity":"medium","issues":[{"type":"clarity","claim":"","reason":"unclear","suggested_fix":"clarify"}]}'
        return 'In a hypothetical situation, I would reproduce the fault before choosing a fix.'
    monkeypatch.setattr(generator.openai_provider, 'generate', provider)
    verdict = generator._semantic_validate_with_openai(question=question, answer=answer, plan=plan, policy_context=policy)
    corrected = generator._semantic_correction_with_openai(
        question=question, answer=answer, plan=plan, validation_result=verdict, policy_context=policy)
    assert corrected.startswith('In a hypothetical situation')
    for call in calls:
        assert policy in call['input_text'] and 'END_OF_ANSWER' in call['input_text']
        assert 'Job requirements tailor relevance, never establish candidate achievements' in call['input_text']
        assert 'unsupported claim that I have never done it' in call['input_text']
    assert [c['phase'] for c in calls] == ['semantic_validation', 'semantic_correction']


@pytest.mark.parametrize('failure', ['timeout', 'empty', 'wrong_fact', 'changed_code'])
def test_optional_refinement_failure_retains_valid_primary(generator, monkeypatch, failure):
    monkeypatch.setattr(ag.settings, 'ANSWER_PROVIDER', 'groq')
    monkeypatch.setattr(ag.settings, 'REFINEMENT_ENABLED', True)
    monkeypatch.setattr(ag.settings, 'REFINEMENT_PROVIDER', 'groq')
    primary = 'Authentication verifies identity; authorization checks permission.'
    if failure == 'changed_code':
        primary += '\n\n```python\nprint(1)\n```'
    calls = []
    monkeypatch.setattr(generator.groq_provider, 'generate', lambda **kwargs: primary)
    def refine(**kwargs):
        calls.append(kwargs)
        if failure == 'timeout':
            raise ProviderError('Synthetic timeout', error_type='timeout')
        return {'empty': '', 'wrong_fact': 'Authentication and authorization are identical.',
                'changed_code': primary.replace('print(1)', 'print(2)')}[failure]
    monkeypatch.setattr(generator.groq_refinement_provider, 'generate', refine)
    result = generator.generate_answer('Compare authentication and authorization.', 'technical', profile_context_enabled=False)
    assert result['answer'] == primary
    assert result['refinement_status'] in {'failed', 'timeout'} and not result['refinement_used']
    assert len(calls) == 1
    system = calls[0]['messages'][0]['content']
    assert 'under about' not in system and 'soft word ranges' in system


@pytest.mark.parametrize('question,answer', [
    ('What does HTTP stand for?', 'Hypertext Transfer Protocol.'),
    ('Write Python code to return the integer 1.', '```python\ndef value():\n    return 1\n```'),
    ('Tell me about a conflict you resolved.', 'In a hypothetical situation, I would clarify the disagreement.'),
])
def test_similarity_never_initiates_a_rewrite_that_can_change_facts_or_code(generator, monkeypatch, question, answer):
    calls = []
    def provider(**kwargs):
        calls.append(kwargs['phase'])
        assert kwargs['phase'] == 'primary_generation'
        return answer
    monkeypatch.setattr(generator.openai_provider, 'generate', provider)
    category = 'behavioral' if 'conflict' in question else 'technical'
    first = generator.generate_answer(question, category, profile_context_enabled=False)
    second = generator.generate_answer(question, category, profile_context_enabled=False)
    assert first['answer'] == second['answer'] == answer
    assert calls == ['primary_generation', 'primary_generation']
    assert second['repetition_detected'] and not second['variation_rewrite_used']


def test_explicit_another_example_or_approach_is_answered_in_first_generation(generator, monkeypatch):
    prompts = []
    monkeypatch.setattr(generator.openai_provider, 'generate',
                        lambda **kwargs: prompts.append(kwargs['input_text']) or 'A different general example uses a queue.')
    question = 'Give another example and an alternative approach to caching, with more detail.'
    generator.generate_answer(question, 'technical', profile_context_enabled=False)
    assert len(prompts) == 1 and question in prompts[0]
    assert 'Avoid copying' not in prompts[0]


def test_concurrent_correction_context_is_request_local(generator, monkeypatch):
    captured = []
    def provider(**kwargs):
        captured.append(kwargs['input_text'])
        return 'Hypothetically, I would reproduce the bug.'
    monkeypatch.setattr(generator.openai_provider, 'generate', provider)
    verdict = ag.SemanticValidationResult.model_validate(dict(valid=False, severity='medium', issues=[]))
    def correct(token):
        plan = replace(build_answer_plan(question='Tell me about a bug.', category='behavioral'),
                       minimum_detail=token)
        return generator._semantic_correction_with_openai(question='Tell me about a bug.', answer='Hypothetical.',
                    plan=plan, validation_result=verdict, policy_context=plan.prompt_instructions() + '\nEvidence: ' + token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(correct, ['SYNTHETIC_ALPHA', 'SYNTHETIC_BETA']))
    assert len(captured) == 2
    assert all(('SYNTHETIC_ALPHA' in p) != ('SYNTHETIC_BETA' in p) for p in captured)


@pytest.mark.asyncio
@pytest.mark.parametrize('fallback', [False, True])
async def test_actual_coordinator_buffers_correction_then_publishes_and_saves_canonical_once(setup, monkeypatch, fallback):
    from app import session_generation as sg
    from app.api import generate as api
    from app.answer_generation import AttemptFailure
    from app.answer_models import MODELS
    from app.answer_streaming import incremental_answers
    _, store = setup
    # Use a catalog-selected OpenAI primary; no fixed model identity.
    setup[0].selected_model_key = next(m.key for m in MODELS if m.provider == 'openai')
    monkeypatch.setattr(api.settings, 'ENABLE_SEMANTIC_VALIDATION', True)
    monkeypatch.setattr(api.settings, 'ENABLE_CONDITIONAL_CORRECTION', True)
    entered, release = asyncio.Event(), asyncio.Event()
    calls, observed = [], []
    canonical = 'Authentication checks identity; authorization checks permission.'
    async def provider(client, model, prepared, key):
        calls.append((model.key, prepared))
        if 'Validate the answer' in prepared.text:
            yield '{"valid":false,"severity":"medium","issues":[{"type":"factual_error","claim":"identical","reason":"different","suggested_fix":"distinguish"}]}', None, True
        elif 'Fix only the verified issues' in prepared.text:
            entered.set()
            await release.wait()
            if fallback:
                raise AttemptFailure('provider_unavailable')
            yield canonical, None, True
        else:
            yield canonical if len(calls) > 1 else 'Authentication and authorization are identical.', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async def consume():
        token = incremental_answers.set(True)
        try:
            response = await api.generate_answer_stream(req(), request())
            async for line in response.body_iterator:
                observed.append(json.loads(line))
        finally:
            incremental_answers.reset(token)
    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(entered.wait(), 10)
        assert any(e['type'] == 'delta' for e in observed)
        assert not store.saves and not any(e['type'] == 'metadata' for e in observed)
        release.set()
        await asyncio.wait_for(task, 10)
        assert len(store.saves) == 1
        assert store.saves[0]['result']['answer'] == canonical
        assert observed[-2]['type'] == 'metadata' and observed[-2]['metadata']['answer'] == canonical
        assert observed[-3]['type'] == 'replace' and observed[-3]['answer'] == canonical
        assert len(calls) == (4 if fallback else 3)
        assert calls[0][0] == calls[1][0] == calls[2][0]
        assert calls[0][1].text in calls[1][1].text and calls[0][1].text in calls[2][1].text
        if fallback:
            assert any(e['type'] == 'replace' and e['answer'] == '' for e in observed)
            assert calls[3][1] == calls[0][1]
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('followup', [False, True])
def test_bounded_request_does_not_require_a_broad_concept_explanation(generator, monkeypatch, followup):
    question = 'In one sentence, explain caching.'
    plan = build_answer_plan(question=question, category='technical', followup=followup)
    monkeypatch.setattr(ag.settings, 'ENABLE_SEMANTIC_VALIDATION', True)
    calls = []
    def provider(**kwargs):
        calls.append(kwargs['phase'])
        return 'A cache reuses previously computed results.'
    monkeypatch.setattr(generator.openai_provider, 'generate', provider)
    result = generator.generate_answer(question, 'technical', answer_plan=plan, profile_context_enabled=False)
    assert calls == ['primary_generation'] and result['validation_issues_count'] == 0
    # Brevity does not exempt incorrect factual claims.
    invalid = ag.validate_answer_against_plan('Authentication and authorization are identical.', plan,
                                              profile_context_used=False)
    assert 'misleading_auth_claim' in invalid['validation_issues']


def test_explanation_cannot_change_validated_code(generator, monkeypatch):
    code = 'def value():\n    return 1'
    monkeypatch.setattr(generator.groq_provider, 'generate',
                        lambda **kwargs: '```python\ndef value():\n    return 2\n```')
    with pytest.raises(ProviderError) as failure:
        generator._format_coding_answer_with_explanation_model(
            question='Write Python code to return 1.', code=code, coding_contract={})
    assert failure.value.error_type == 'invalid_refinement'


@pytest.mark.parametrize('code_only', [False, True])
def test_interview_coding_finalization_preserves_explanation_or_explicit_code_only(generator, code_only):
    question = 'Write Python code to print the integer 1.' + (' Return code only.' if code_only else '')
    original = 'Print the required constant.\n\n```python\nprint(1)\n```\n\nAlternatively: return it from a function when composing an API.'
    result = generator.generate_answer(question, 'technical', source='chat', question_context_type='coding',
        coding_answer_mode=True, profile_context_enabled=False,
        primary_result_override=ag.ProviderResult(answer=original, provider='openai', model='synthetic',
                                                primary_provider='openai'))
    assert result['answer'] == ('```python\nprint(1)\n```' if code_only else original)
    assert not result['refinement_used']


def test_interview_code_correction_receives_complete_code_and_request_policy(generator, monkeypatch):
    question = 'Write Python code to print 1. Return code only.'
    plan = build_answer_plan(question=question, category='technical')
    code = '\n'.join(f'# synthetic line {i}' for i in range(160)) + '\nprint(1) # COMPLETE_TAIL'
    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        return '```python\n' + code + '\n```'
    monkeypatch.setattr(generator.openai_provider, 'generate', provider)
    generator._correct_coding_answer_against_contract(question=question, answer='```python\n' + code + '\n```',
        contract={'mode': 'standalone_demo', 'language': 'python'}, validation_errors=['Synthetic contract issue'],
        use_openai=True, answer_plan=plan)
    assert len(calls) == 1 and code in calls[0]['input_text']
    assert plan.prompt_instructions() in calls[0]['input_text']


def test_personal_sanitation_preserves_evidence_and_hypothetical_framing(generator):
    answer = 'As an AI, In a hypothetical situation, I would clarify the disagreement before acting.'
    repaired, errors, used = generator.repair_personal_answer_if_needed(
        question='Tell me about a conflict you resolved.', answer=answer)
    assert used and errors == ['meta_phrase']
    assert repaired == 'In a hypothetical situation, I would clarify the disagreement before acting.'
    assert 'I remember' not in repaired and 'never' not in repaired
    with pytest.raises(ProviderError) as failure:
        generator.repair_personal_answer_if_needed(question='Tell me about yourself.', answer='')
    assert failure.value.error_type == 'invalid_response'


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['stop', 'disconnect'])
async def test_real_grpc_stop_during_actual_correction_closes_producer_without_save(setup, monkeypatch, boundary):
    from app import session_generation as sg
    from app.api import generate as api
    from app.grpc_generated import interview_realtime_pb2 as pb
    from test_answer_stream_characterization import Probe, transport
    _, store = setup
    monkeypatch.setattr(api.settings, 'ENABLE_SEMANTIC_VALIDATION', True)
    monkeypatch.setattr(api.settings, 'ENABLE_CONDITIONAL_CORRECTION', True)
    probe = Probe()
    held, closed = asyncio.Event(), asyncio.Event()
    calls = []
    async def provider(client, model, prepared, key):
        calls.append(prepared)
        if 'Validate the answer' in prepared.text:
            yield '{"valid":false,"severity":"medium","issues":[{"type":"factual_error","claim":"identical","reason":"different","suggested_fix":"distinguish"}]}', None, True
        elif 'Fix only the verified issues' in prepared.text:
            held.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        else:
            yield 'Authentication and authorization are identical.', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    async with transport(monkeypatch, 'microphone', probe, version=1) as call:
        await asyncio.wait_for(held.wait(), 10)
        if boundary == 'stop':
            await call.write(pb.InterviewClientEvent(session_id='synthetic', request_id='stop', cancel=pb.Empty()))
            await probe.until(lambda: any(x.status.code == 'canceled' for x in probe.payloads('wire_status')))
        else:
            call.cancel()
        await asyncio.wait_for(closed.wait(), 10)
        assert len(calls) == 3 and not store.saves
        assert not probe.payloads('wire_answer_completed')


@pytest.mark.asyncio
async def test_correction_obeys_shared_deadline_without_save_or_new_generation(setup, monkeypatch):
    from app import session_generation as sg
    from app.api import generate as api
    from app.answer_generation import GenerationBudget
    from test_session_generation import events
    _, store = setup
    monkeypatch.setattr(api.settings, 'ENABLE_SEMANTIC_VALIDATION', True)
    monkeypatch.setattr(api.settings, 'ENABLE_CONDITIONAL_CORRECTION', True)
    now = [0.0]
    monkeypatch.setattr(sg, 'GenerationBudget', lambda limits: GenerationBudget(limits, clock=lambda: now[0]))
    calls = []
    async def provider(client, model, prepared, key):
        calls.append(prepared)
        if 'Validate the answer' in prepared.text:
            yield '{"valid":false,"severity":"medium","issues":[{"type":"factual_error","claim":"identical","reason":"different","suggested_fix":"distinguish"}]}', None, True
        elif 'Fix only the verified issues' in prepared.text:
            now[0] = 10000.0  # Explicit fake-clock expiry, no sleep or timeout increase.
            yield 'Authentication checks identity; authorization checks permission.', None, True
        else:
            yield 'Authentication and authorization are identical.', None, True
    monkeypatch.setattr(sg, 'provider_stream', provider)
    observed = await events(req())
    assert len(calls) == 3 and not store.saves
    assert any(e['type'] == 'error' and e['error'] == 'generation_failed' for e in observed)
    assert not any(e['type'] == 'metadata' for e in observed)
