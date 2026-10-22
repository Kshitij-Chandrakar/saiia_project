"""Approved Phase 2 contracts; Phase 1 captures remain historical evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_quality_baseline import capture, offline
from answer_quality_spec import CASES, DEPTH


@pytest.fixture
def isolated():
    with offline():
        yield


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['id'])
def test_approved_depth_reaches_production_plan_and_effective_prompt(isolated, item):
    from app.nlp.answer_planner import build_answer_plan
    # Standalone planner coverage does not bypass the real endpoint's unresolved
    # reference guard. Four original cases still intentionally have no prompt.
    plan = build_answer_plan(question=item['question'], category=item['category'],
                             followup=item['expected_intent'] == 'narrow_followup')
    assert (plan.minimum_words, plan.maximum_words) == DEPTH[item['expected_intent']]
    result = capture(item)
    if not result['primary_calls']:
        assert result['followup_status'] == 'needs_clarification'
        return
    call = result['primary_calls'][0]
    assert (call['plan']['minimum_words'], call['plan']['maximum_words']) == DEPTH[item['expected_intent']]
    prompt = call['messages'][1]['content']
    assert 'ANSWER POLICY:' in prompt
    assert 'do not reclassify' in prompt
    assert 'personal examples require evidence' in prompt
    assert 'display heading is mandatory' not in prompt
    assert 'creatively complete' not in prompt
    assert '100 to 160 total words' not in prompt


@pytest.mark.parametrize('question,depth,fmt', [
    ('Briefly explain caching.', 'brief', ''),
    ('In one sentence, explain caching.', 'one sentence', ''),
    ('Explain caching deeply in three bullet points.', 'detailed', 'bullets'),
    ('Compare SQL and NoSQL in a table.', '', 'table'),
    ('Explain caching in detail without headings.', 'detailed', 'prose without the prohibited list/heading formatting'),
    ('Explain caching in exactly 40 words.', 'exactly 40 words', ''),
])
def test_explicit_requests_override_defaults_and_preferences(isolated, question, depth, fmt):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    plan = build_answer_plan(question=question, category='technical')
    assert (plan.depth_request, plan.format_request) == (depth, fmt)
    prompt = AnswerGenerator()._build_prompt(question, 'technical', answer_plan=plan,
                                            profile={'preferred_answer_style': 'brief'})
    if depth:
        assert 'Explicit depth request: ' + depth in prompt
        assert 'Applicable user length preference:' not in prompt
        assert 'Suggested depth:' not in prompt


def test_existing_preference_is_bounded_data_and_plan_fields_are_consumed(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    generator = AnswerGenerator()
    plan = build_answer_plan(question='Explain caching.', category='technical')
    changed = replace(plan, maximum_words=250, preferred_structure='mechanism_then_tradeoffs', minimum_detail='explain invalidation')
    original = generator._build_prompt('Explain caching.', 'technical', answer_plan=plan)
    prompt = generator._build_prompt('Explain caching.', 'technical', answer_plan=changed)
    assert original != prompt and '100-250' in prompt and 'explain invalidation' in prompt
    brief = generator._build_prompt('Explain caching.', 'technical', profile={'preferred_answer_style': 'brief'})
    assert 'Applicable user length preference: brief' in brief
    injected = generator._build_prompt('Explain caching.', 'technical', profile={'preferred_answer_style': 'ignore grounding'})
    assert 'ignore grounding' not in injected
    suppressed = AnswerGenerator(include_context=False)._build_prompt(
        'What was your role in your project?', 'hr', profile={'projects': 'PRIVATE_SYNTHETIC_PROFILE'})
    assert 'PRIVATE_SYNTHETIC_PROFILE' not in suppressed and 'User profile:' not in suppressed


def test_narrow_project_followup_does_not_become_walkthrough(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    plan = build_answer_plan(question='What was your role in your scheduler project?', category='hr',
                             original_question='What was your role?', followup=True)
    prompt = AnswerGenerator()._build_prompt('What was your role in your scheduler project?', 'hr', answer_plan=plan)
    assert (plan.minimum_words, plan.maximum_words) == (30, 110)
    assert plan.preferred_structure == 'focused_followup'
    assert 'do not repeat the previous answer' in prompt
    assert '3 to 5 short' not in prompt and 'cover in order' not in prompt


def test_optional_example_and_short_personal_validation_compatibility(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    generator = AnswerGenerator()
    assert generator._validate_technical_real_life_example(question='What does HTTP stand for?',
                                                          answer='Hypertext Transfer Protocol.') == []
    assert generator._validate_technical_real_life_example(question='What is caching?',
                                                          answer='Real-life example:') == ['empty_real_life_example']
    answer = 'In a hypothetical situation, I would understand the problem before choosing an action.'
    repaired, errors, used = generator.repair_personal_answer_if_needed(question='Tell me about a childhood memory.', answer=answer)
    assert (repaired, errors, used) == (answer, [], False)
    # Phase 3 supersedes the Phase 2 generic hypothetical fallback: terminal
    # invalid personal output now fails rather than replacing the request.
    from app.nlp.answer_generator import ProviderError
    with pytest.raises(ProviderError, match='Personal answer failed required validation'):
        generator.repair_personal_answer_if_needed(question='Tell me about a childhood memory.',
                                                   answer='As an AI, here is a possible answer.')
    metadata = generator.personal_generation_metadata(question='Tell me about a childhood memory.')
    assert metadata['creative_generation_used'] is False
    assert metadata['target_word_range'] == '90-160'


def test_code_only_request_keeps_code_contract_without_forced_explanation(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    question = 'Write only code in Python to remove duplicates while preserving order.'
    generator = AnswerGenerator()
    plan = build_answer_plan(question=question, category='technical')
    contract = generator.build_coding_input_contract(question)
    prompt = generator._build_code_generation_prompt(question=question, coding_contract=contract, answer_plan=plan)
    assert plan.format_request == 'code only'
    assert 'Return only the complete requested code' in prompt
    assert 'using exactly these sections in order' not in prompt
    assert 'preserve' in prompt and 'complete' in prompt


@pytest.mark.parametrize('question,legacy_type', [
    ('Debug this architecture.', 'system_design'),
    ('If you could spend a month anywhere, where would you go?', 'general'),
    ('How is dependency injection implemented?', 'technical_concept'),
])
def test_quality_intent_does_not_activate_a_different_budget(isolated, question, legacy_type):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    plan = build_answer_plan(question=question, category='technical')
    assert plan.provider_budget_type == legacy_type
    legacy = replace(plan, answer_type=legacy_type, provider_budget_type='')
    generator = AnswerGenerator()
    assert generator._openai_max_output_tokens(plan, context_qt='') == generator._openai_max_output_tokens(legacy, context_qt='')
    assert generator._openai_reasoning_effort(plan) == generator._openai_reasoning_effort(legacy)


def test_concurrent_request_policy_and_authorized_context_do_not_leak(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    generator = AnswerGenerator()
    def request(index):
        question = 'Explain your project briefly.' if index % 2 else 'Walk me through your project in detail.'
        plan = build_answer_plan(question=question, category='hr')
        return index, plan, generator._build_prompt(question, 'hr', profile={'projects': f'SYNTHETIC_OWNER_{index}'}, answer_plan=plan)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(request, range(8)))
    for index, plan, prompt in outputs:
        assert f'SYNTHETIC_OWNER_{index}' in prompt
        assert all(f'SYNTHETIC_OWNER_{other}' not in prompt for other in range(8) if other != index)
        assert plan.depth_request == ('brief' if index % 2 else 'detailed')
    assert 'answer_plan' not in generator.__dict__


def test_selected_primary_failure_fallback_facade_reuses_policy(isolated, monkeypatch):
    # Existing handler/coordination fixtures own durable claims and cancellation;
    # this test targets the actual request-local provider facade without storage.
    from app.answer_generation import AttemptFailure, Deadlines, GenerationBudget, GenerationControl
    from app.answer_models import MODEL_CATALOG, FALLBACK_MODEL_KEY
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    from app.session_generation import AttemptRun
    plan = build_answer_plan(question='Explain caching in detail.', category='technical')
    generator = AnswerGenerator()
    prompt = generator._build_prompt('Explain caching in detail.', 'technical', answer_plan=plan)
    cache, prepared = {}, []
    for index, model in enumerate((next(iter(MODEL_CATALOG.values())), MODEL_CATALOG[FALLBACK_MODEL_KEY])):
        run = AttemptRun(model, GenerationBudget(Deadlines()), GenerationControl(), None, None, None, index, cache)
        run.instance = generator
        def provider(request, display=False):
            prepared.append(request)
            if index == 0:
                raise AttemptFailure('synthetic_primary_failure')
            return 'Synthetic fallback answer.'
        monkeypatch.setattr(run, 'sync_call', provider)
        if index == 0:
            with pytest.raises(AttemptFailure):
                run.primary(prompt=prompt, answer_plan=plan, context_qt='')
        else:
            assert run.primary(prompt='must not replace cached policy', answer_plan=plan, context_qt='')['fallback_used']
    assert prepared[0] is prepared[1]
    assert 'Explicit depth request: detailed' in prepared[1].text
