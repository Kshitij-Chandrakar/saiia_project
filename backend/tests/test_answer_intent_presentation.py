"""Task intent contracts; mocked prompts are not measured model quality."""
import pytest

from app.nlp.answer_generator import AnswerGenerator, SemanticValidationResult
from app.nlp.answer_planner import build_answer_plan
from app.nlp.followup_resolver import resolve_live_followup
from app.nlp.followup_intent_compiler import compile_followup_intent

MATRIX = [
    ('Explain system design.', 'technical_concept'),
    ('What is system design?', 'technical_concept'),
    ('How do you approach system design interviews?', 'technical_process'),
    ('Explain the design of a URL shortener.', 'system_design'),
    ('Design a URL shortener.', 'system_design'),
    ('Explain caching in system design.', 'technical_concept'),
    ('Design a cache for a product catalog.', 'system_design'),
    ('Explain the system design of my project.', 'system_design'),
    ('What is event-driven architecture?', 'technical_concept'),
    ('How would you design an order processing service?', 'system_design'),
    ('What does it mean to design a system?', 'technical_concept'),
]

@pytest.mark.parametrize('question,expected', MATRIX)
def test_task_not_topic_controls_effective_prompt(question, expected, monkeypatch):
    plan = build_answer_plan(question=question, category='technical')
    assert plan.answer_type == expected
    generator = AnswerGenerator()
    prompt = generator._build_prompt(question, 'technical', answer_plan=plan,
        profile={'projects':'Synthetic catalog: API writes to PostgreSQL.'})
    messages = generator._answer_messages(prompt)
    assert f'Resolved answer type: {expected}' in messages[1]['content']
    if expected != 'system_design':
        assert 'state assumptions, trace the main flow' not in prompt
        assert 'an example, not an inferred requirement' in prompt
        assert (plan.minimum_words, plan.maximum_words) == (100, 200)
    else:
        assert 'explicitly labeled assumptions' in prompt
    if 'my project' in question:
        assert plan.profile_context_policy == 'REQUIRED'
        assert 'Synthetic catalog' in prompt
    # Both legacy primary assembly and request-scoped correction consume policy.
    seen = []
    monkeypatch.setattr(generator.openai_provider, 'generate', lambda **kw: seen.append(kw) or 'Synthetic corrected answer.')
    generator._semantic_correction_with_openai(question=question, answer='Synthetic draft.',
        plan=plan, validation_result=SemanticValidationResult(valid=False, severity='medium', issues=[]), policy_context=prompt)
    assert f'Resolved answer type: {expected}' in seen[0]['input_text']


def entry(topic, answer_type='technical_concept'):
    return dict(entry_id='synthetic-anchor', mode='answer', question='Explain '+topic,
        topic=topic, answer_type=answer_type, answer_excerpt='Synthetic completed context.')

@pytest.mark.parametrize('question,anchor,expected', [
    ('Now design one', entry('a URL shortener'), 'system_design'),
    ('Explain that component', entry('the cache component'), 'technical_concept'),
])
def test_resolved_followup_preserves_task_and_scope(question, anchor, expected):
    resolution = resolve_live_followup(question=question, mode='answer', context_entries=[anchor])
    assert resolution.resolution_status == 'resolved'
    compiled = compile_followup_intent(question=question, mode='answer', resolution=resolution, context_entries=[anchor])
    plan = build_answer_plan(question=compiled.resolved_question, original_question=question,
                             category='technical', followup=True)
    assert plan.answer_type == expected
    assert (plan.minimum_words,plan.maximum_words) == ((220,400) if expected=='system_design' else (30,110))

@pytest.mark.parametrize('question,anchor', [
    ('Now design one', entry('system design')),
    ('Explain that component', entry('a URL shortener','system_design')),
    ('Now design one', None),
])
def test_ambiguous_references_remain_clarifications(question, anchor):
    resolution = resolve_live_followup(question=question,mode='answer',context_entries=[anchor] if anchor else [])
    assert resolution.resolution_status == 'needs_clarification'


def test_interview_approach_has_standalone_subject():
    resolution=resolve_live_followup(question=MATRIX[2][0],mode='answer',context_entries=[])
    assert resolution.resolution_status == 'standalone'

@pytest.mark.parametrize('question', [MATRIX[0][0],MATRIX[4][0]])
def test_selected_primary_fallback_reuse_resolved_policy(question,monkeypatch):
    from app.answer_generation import AttemptFailure, Deadlines, GenerationBudget, GenerationControl
    from app.answer_models import MODEL_CATALOG, FALLBACK_MODEL_KEY
    from app.session_generation import AttemptRun
    plan=build_answer_plan(question=question,category='technical')
    generator=AnswerGenerator();prompt=generator._build_prompt(question,'technical',answer_plan=plan)
    cache={};calls=[]
    for index,model in enumerate((next(iter(MODEL_CATALOG.values())),MODEL_CATALOG[FALLBACK_MODEL_KEY])):
        run=AttemptRun(model,GenerationBudget(Deadlines()),GenerationControl(),None,None,None,index,cache)
        run.instance=generator
        def provider(request,display=False):
            calls.append(request)
            if index==0:raise AttemptFailure('synthetic')
            return 'Synthetic fallback.'
        monkeypatch.setattr(run,'sync_call',provider)
        if index==0:
            with pytest.raises(AttemptFailure):run.primary(prompt=prompt,answer_plan=plan,context_qt='')
        else:run.primary(prompt='must reuse original',answer_plan=plan,context_qt='')
    assert calls[0] is calls[1]
    assert f'Resolved answer type: {plan.answer_type}' in calls[1].text


def test_cleanup_does_not_compress_provider_numbered_steps():
    text='**Main considerations**\n\n1. Requirements.\n2. Tradeoffs.\n\nAn illustrative example.'
    assert AnswerGenerator()._clean_answer(text)==text


@pytest.mark.parametrize('question,expected', MATRIX)
def test_actual_http_endpoint_prompt_has_resolved_intent(question,expected,monkeypatch):
    from copy import deepcopy
    from answer_quality_baseline import capture
    from answer_quality_spec import CASES
    from app.api import generate as api
    original=api.generate_answer
    completed_types=[]
    async def observed(request):
        response=await original(request)
        completed_types.append(response.answer_type)
        return response
    monkeypatch.setattr(api,'generate_answer',observed)
    item=deepcopy(next(case for case in CASES if case['expected_intent']=='technical_concept'))
    item.update(id='synthetic-intent',question=question,history=[],
                expected_intent='system_design' if expected=='system_design' else 'technical_concept')
    result=capture(item)
    assert result['primary_calls'], result['followup_status']
    call=result['primary_calls'][0]
    assert call['plan']['answer_type']==expected
    assert f'Resolved answer type: {expected}' in call['messages'][1]['content']
    assert completed_types==[expected]
