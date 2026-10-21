"""Known limitations characterize CURRENT code; approved policy is separate.

Use scripts/answer_quality_baseline.py --tests for guarded collection/startup.
No assertion here claims an authored provider double has conversational quality.
"""
import ast
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_quality_baseline import capture, offline
from answer_quality_spec import CASES, DEPTH, approved_policy


@pytest.fixture
def isolated():
    with offline():
        yield


def test_case_inventory_and_approved_policy_are_complete():
    assert len(CASES) == len({item['id'] for item in CASES}) == 24
    assert set(DEPTH) <= {item['expected_intent'] for item in CASES}
    tags = {tag for item in CASES for tag in item['tags']}
    assert {'missing_evidence', 'sparse_evidence', 'conflicting_evidence', 'jd_not_experience',
            'irrelevant_retrieval', 'repeated_coding', 'repeated_fact', 'narrow_followup',
            'ambiguous_followup', 'explicit_short', 'explicit_detailed', 'long_answer', 'fallback'} <= tags
    for item in CASES:
        assert all(item[key] for key in ('question', 'expected_intent', 'essential_content',
                                        'prohibited_inferences', 'critical_failures', 'human_review'))
        assert set(item['evidence']) == {'profile', 'snippets', 'job', 'selected_resume'}
        assert set(item['examples']) == {'useful', 'unnecessary'}
        policy = approved_policy(item)
        assert policy['suggested_words'] == list(DEPTH[item['expected_intent']])
        assert policy['mandatory_minimum'] is False
        assert policy['default_range_is_binding'] is False
        assert policy['code_excluded_from_word_count'] is True
        assert policy['explicit_constraints'] == item['explicit_constraints']
        assert policy['precedence'].index('explicit_question_constraints') < policy['precedence'].index('question_type_guidance')
        assert 'no_positive_or_negative_history' in policy['missing_evidence']
    assert next(item for item in CASES if item['id'] == 'explicit_short')['explicit_constraints'] == {'max_sentences': 1}


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['id'])
def test_real_endpoint_capture_is_synthetic_and_desired_spec_stays_separate(isolated, item):
    result = capture(item)
    assert result['provenance'] == 'synthetic_offline_capture'
    assert result['desired_policy'] == approved_policy(item)
    assert result['fallback_exercised'] is False  # no claim of end-to-end fallback quality
    if result['primary_calls']:
        call = result['primary_calls'][0]
        assert [message['role'] for message in call['messages']] == ['system', 'user']
        assert call['messages'][1]['content']
        assert call['requested_output_tokens'] > 0
        assert call['legacy_budget_requests']['openai']['max_output_tokens'] > 0
        assert call['legacy_budget_requests']['groq']['max_tokens'] > 0
        assert all(0 < budget['effective'] <= budget['requested']
                   for budget in call['legacy_budget_requests']['selected_profiles'])
    else:
        assert 'resolver' in result['result_model']  # actual early clarification, no invented prompt
        assert result['followup_status'] == 'needs_clarification'
        assert item['id'] in {'motivation', 'debugging', 'followup_ambiguous', 'jd_only'}
    assert 'synthetic-offline-key' not in json.dumps(result)


def test_selected_resume_and_technical_context_filtering(isolated):
    selected = capture(next(item for item in CASES if item['id'] == 'selected_conflict'))
    prompt = selected['primary_calls'][0]['messages'][1]['content']
    assert 'Mira implemented API endpoints' in prompt
    assert 'Led 20 engineers' not in prompt
    technical = capture(next(item for item in CASES if item['id'] == 'retrieval_irrelevant'))
    assert technical['retrieval_calls'][0]['use_profile_context'] is False
    assert 'watercolor' not in technical['primary_calls'][0]['messages'][1]['content']


def test_phase2_conceptual_instructions_are_conditional(isolated):
    result = capture(next(item for item in CASES if item['id'] == 'concept_cache'))
    prompt = result['primary_calls'][0]['messages'][1]['content']
    assert "only when useful" in prompt
    assert "display heading is mandatory" not in prompt
    assert '100-200' in prompt  # Phase 2 desired policy; Phase 1 export is historical


def test_phase2_plan_detail_fields_control_prompt(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    generator = AnswerGenerator()
    plan = build_answer_plan(question='What is caching?', category='technical')
    altered = replace(plan, maximum_words=999, minimum_detail='synthetic-detail-marker',
                      preferred_structure='synthetic-structure-marker', example_policy='synthetic-example-marker')
    kwargs = dict(question='What is caching?', question_type='technical')
    assert generator._build_prompt(**kwargs, answer_plan=plan) != generator._build_prompt(**kwargs, answer_plan=altered)
    assert asdict(plan) != asdict(altered)


def test_phase3_cleanup_preserves_prose_code_and_conceptual(isolated):
    from app.nlp.answer_generator import AnswerGenerator, settings
    generator = AnswerGenerator()
    prose = ' '.join('detail' for _ in range(settings.ANSWER_MAX_WORDS + 30))
    assert generator._clean_answer(prose) == prose
    code = '```python\n# ' + prose + '\n```'
    assert generator._clean_answer(code) == code
    conceptual = '[[category:technical]]\nDefinition.\n\n- ' + prose + '\n\nReal-life example:\n\nA general example.'
    assert len(generator._clean_answer(conceptual).split()) > settings.ANSWER_MAX_WORDS


@pytest.mark.parametrize('separator', [':', ' ', ','])
def test_phase3_alternative_section_is_retained(isolated, separator):
    from app.nlp.answer_generator import AnswerGenerator
    answer = 'Use a queue for asynchronous work.\nAlternatively' + separator + ' use synchronous delivery when latency matters.'
    cleaned = AnswerGenerator()._clean_answer(answer)
    assert cleaned == answer


def test_phase2_personal_prompt_and_repair_do_not_invent_history(isolated):
    from app.nlp.answer_generator import AnswerGenerator
    generator = AnswerGenerator()
    prompt = generator._build_prompt('Tell me about a childhood memory.', 'personal')
    assert 'creatively complete low-risk details' not in prompt
    repaired, errors, used = generator.repair_personal_answer_if_needed(
        question='Tell me about a childhood memory.', answer='Short.')
    assert not used and not errors and repaired == 'Short.'
    # Phase 2 removes invented-story repair; this is not claim-level verification.
    assert next(item for item in CASES if item['id'] == 'personal_missing')['permitted_personal_facts'] == []


def test_selected_primary_fallback_facade_reuses_prompt_and_preserves_raw_text(isolated):
    from app.answer_generation import Deadlines, GenerationBudget, GenerationControl
    from app.answer_models import MODEL_CATALOG, FALLBACK_MODEL_KEY
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    from app.session_generation import AttemptRun
    cache, requests = {}, []
    plan = build_answer_plan(question='Design a notification service.', category='technical')
    raw = ' '.join(['detail'] * 190)
    for index, model in enumerate((next(iter(MODEL_CATALOG.values())), MODEL_CATALOG[FALLBACK_MODEL_KEY])):
        run = AttemptRun(model, GenerationBudget(Deadlines()), GenerationControl(), None, None, None, index, cache)
        run.instance = AnswerGenerator()
        def fake(prepared, display=False):
            requests.append(prepared)
            return raw
        with patch.object(run, 'sync_call', side_effect=fake):
            result = run.primary(prompt='Synthetic policy input', answer_plan=plan, context_qt='')
        assert result['answer'] == raw  # known route difference: no legacy prose cleaner
        assert result['fallback_used'] is bool(index)
    assert requests[0] is requests[1]
    assert requests[0].instructions and requests[0].max_output_tokens > 0


def test_adapter_profiles_cap_budget_without_universal_parameters(isolated):
    from app.answer_generation import PreparedAnswer, _request
    from app.answer_models import AnswerModel, PROFILES
    for profile, (provider, efforts) in PROFILES.items():
        model = AnswerModel('synthetic', 'Synthetic', provider, 'synthetic-model', '',
                            efforts[0] if efforts else '', efforts, 1000, profile)
        _, _, body = _request(model, PreparedAnswer('Synthetic instructions', 'Synthetic question', 2000), 'synthetic-offline-key')
        if provider == 'openai':
            assert body['max_output_tokens'] == 1000
            assert ('reasoning' in body) == bool(efforts)
        elif provider == 'groq':
            assert body['max_completion_tokens'] == 1000
            assert ('reasoning_effort' in body) == bool(efforts)
        else:
            assert body['generationConfig']['maxOutputTokens'] == 1000
            assert ('thinkingConfig' in body['generationConfig']) == bool(efforts)
        assert 'temperature' not in body


def test_offline_boundary_errors_do_not_echo_credentials(isolated, capsys):
    import httpx
    import requests
    secret = 'synthetic-credential-do-not-echo'
    operations = [lambda: requests.get('https://example.invalid', headers={'Authorization': secret}),
                  lambda: httpx.get('https://example.invalid', headers={'Authorization': secret}),
                  lambda: socket.getaddrinfo('example.invalid', 443)]
    for operation in operations:
        with pytest.raises(AssertionError, match='Unexpected external boundary') as caught:
            operation()
        assert secret not in str(caught.value)
    assert secret not in ''.join(capsys.readouterr())


def test_fresh_process_ignores_parent_credentials_and_exports_no_secret():
    import os
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'answer_quality_baseline.py'
    sentinel = 'synthetic-parent-credential-must-not-be-loaded'
    result = subprocess.run([sys.executable, '-B', str(script)],
        env=dict(os.environ, OPENAI_API_KEY=sentinel, GROQ_API_KEY=sentinel,
                 ANSWER_MAX_WORDS='not-a-number'),
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, 'Offline child failed; inspect synthetic harness separately'
    assert json.loads(result.stdout)['cases'] == 24
    assert sentinel not in result.stdout + result.stderr


def test_spec_is_not_imported_by_production():
    root = Path(__file__).resolve().parents[1] / 'app'
    for path in root.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert 'answer_quality_spec' not in (node.module or '')
            elif isinstance(node, ast.Import):
                assert all('answer_quality_spec' not in name.name for name in node.names)
