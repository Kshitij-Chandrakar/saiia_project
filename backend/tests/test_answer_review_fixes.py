"""Confirmed review defects; all content and evidence are synthetic."""
from types import SimpleNamespace as NS
import pytest
from fastapi import HTTPException
from app.api import generate as api
from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.nlp.answer_planner import build_answer_plan
from test_answer_quality_phase4 import cloud, chunks, USER_A, RESUME_ID


def test_selected_resume_no_match_gate_obeys_plan():
    req = api.GenerateRequest(question='What is a deadlock?', category='technical', selected_resume_id=RESUME_ID)
    empty = {'selected_resume_id_used': True, 'retrieved_chunks': []}
    api._require_selected_resume_context(req, empty, plan=build_answer_plan(question=req.question, category=req.category))
    for question in ('Explain your Atlas project.', 'What is your favourite childhood memory?'):
        with pytest.raises(HTTPException) as exc:
            api._require_selected_resume_context(req, empty, plan=build_answer_plan(question=question, category='personal'))
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_general_selected_resume_no_match_reaches_generation(monkeypatch):
    service = cloud(chunks(('education', 'Studied biology.')))
    monkeypatch.setattr(api, '_current_user_for_selected_resume', lambda *args: NS(user_id=USER_A))
    monkeypatch.setattr(api, '_new_cloud_resume_service', lambda: service)
    calls = []
    def generate(**kw):
        calls.append(kw)
        return dict(answer='A deadlock is a cycle of tasks waiting on held resources.', provider='synthetic', model='synthetic', generation_ms=0.0, fallback_used=False, error=None)
    monkeypatch.setattr(api.generator, 'generate_answer', generate)
    result = await api.generate_answer(api.GenerateRequest(question='What is a deadlock?', category='technical', selected_resume_id=RESUME_ID))
    assert result.answer and len(calls) == 1
    assert not calls[0].get('retrieved_chunks')


def test_long_project_continuations_keep_identity_without_mixing_other_project():
    documents = chunks(('projects', 'Atlas Scheduler - ' + 'Scheduler workers coordinate durable booking jobs. ' * 20),
                       ('projects', 'Lunar Dashboard - Built charts.'))
    atlas = [c for c in documents if c.get('project_title') == 'Atlas Scheduler']
    assert len(atlas) > 1
    service = cloud(documents)
    result = service.retrieve_resume_chunks(user_id=USER_A, resume_id=RESUME_ID,
        question='Explain your "Atlas Scheduler" project.', category='resume-based', limit=10)
    assert len(result['retrieved_chunks']) > 1
    assert all(c['chunk_id'] in {item['chunk_id'] for item in atlas} for c in result['retrieved_chunks'])
    ambiguous = cloud(chunks(('projects', 'Atlas Scheduler - Booking tasks.'), ('projects', 'Atlas Dashboard - Charts.')))
    with pytest.raises(Exception, match='not found'):
        ambiguous.retrieve_resume_chunks(user_id=USER_A, resume_id=RESUME_ID,
            question='Explain your "Atlas" project.', category='resume-based')


def test_supported_personal_story_keywords_are_advisory_not_grounding_proof():
    answer = 'My favourite childhood memory is a science project with my grandfather.'
    repaired, warnings, changed = AnswerGenerator().repair_personal_answer_if_needed(
        question='What is your favourite childhood memory?', answer=answer)
    assert repaired == answer and not changed and 'unnecessary_professional_content' in warnings
    with pytest.raises(ProviderError):
        AnswerGenerator().repair_personal_answer_if_needed(question='Favourite memory?', answer='')
    with pytest.raises(ProviderError):
        AnswerGenerator().repair_personal_answer_if_needed(question='Favourite memory?', answer='I respond as an AI to this question.')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['normal', 'resume', 'job'])
async def test_required_personal_failure_has_same_safe_http_error_in_recovery_paths(monkeypatch, failure):
    from app.services.resume_index_service import ResumeIndexError
    from app.services.job_context_service import JobContextError
    monkeypatch.setattr(api.generator, 'generate_answer', lambda **kw: dict(answer='invalid', generation_ms=0,
        provider='synthetic', model='synthetic', fallback_used=False, error=None))
    def reject(**kw):
        raise ProviderError('synthetic required validation failure', error_type='invalid_response', phase='personal_validation')
    monkeypatch.setattr(api.generator, 'repair_personal_answer_if_needed', reject)
    if failure == 'resume':
        monkeypatch.setattr(api, '_retrieve_resume_context', lambda **kw: (_ for _ in ()).throw(ResumeIndexError('synthetic')))
    if failure == 'job':
        monkeypatch.setattr(api, '_generation_job_context', lambda *a, **kw: (_ for _ in ()).throw(JobContextError('synthetic')))
    with pytest.raises(HTTPException) as exc:
        await api.generate_answer(api.GenerateRequest(question='What is your favourite childhood memory?', category='personal'))
    assert exc.value.status_code == 500
    assert exc.value.detail == 'Personal answer failed required validation.'
