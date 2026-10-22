"""Second review: production paths, synthetic evidence and no external calls."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.api import generate as api
from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.cloud.cloud_resume import CloudResumeValidationError
from test_answer_quality_phase4 import cloud, chunks, USER_A, RESUME_ID


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming', [False, True])
async def test_strict_resume_clarification_needs_auth_but_not_answer_evidence(monkeypatch, streaming):
    monkeypatch.setattr(api.settings, 'ENABLE_TRUE_ANSWER_STREAMING', True)
    monkeypatch.setattr(api.settings, 'ENABLE_LIVE_FOLLOWUP_RESOLUTION', True)
    auth = Mock(return_value=NS(user_id=USER_A))
    monkeypatch.setattr(api, '_current_user_for_selected_resume', auth)
    monkeypatch.setattr(api, '_new_cloud_resume_service', lambda: cloud(chunks(('education', 'Studied biology.'))))
    retrieval = Mock(wraps=api._retrieve_resume_context)
    monkeypatch.setattr(api, '_retrieve_resume_context', retrieval)
    generation = Mock(side_effect=AssertionError('clarification must not generate'))
    monkeypatch.setattr(api.generator, 'generate_answer', generation)
    monkeypatch.setattr(api.generator, 'stream_openai_primary_answer', generation)
    req = api.GenerateRequest(question='Can you give another example?', category='technical', selected_resume_id=RESUME_ID)
    request = Request({'type':'http', 'headers':[]})
    if streaming:
        response = await api.generate_answer_stream(req, request)
        events = [json.loads(item) async for item in response.body_iterator]
        assert not any(e['type'] == 'error' for e in events)
        result = next(e['metadata'] for e in events if e['type'] == 'metadata')
        assert result['provider'] == 'local' and result['retrieval_used'] is False
    else:
        result = await api.generate_answer(req, request)
        assert result.provider == 'local' and result.retrieval_used is False
    assert auth.call_count == 1 and retrieval.call_count == generation.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('code', [401, 404, 409])
async def test_clarification_keeps_auth_session_and_lifecycle_rejection(monkeypatch, streaming, code):
    monkeypatch.setattr(api.settings, 'ENABLE_TRUE_ANSWER_STREAMING', True)
    monkeypatch.setattr(api, '_current_user_for_session_id', lambda *a: NS(user_id=USER_A))
    from app.cloud.interview_sessions import CloudInterviewSessionNotFoundError, CloudInterviewSessionConflictError
    def get_session(**kw):
        assert kw['user_id'] == USER_A
        if code == 404: raise CloudInterviewSessionNotFoundError('synthetic')
        if code == 409: raise CloudInterviewSessionConflictError('synthetic')
        raise HTTPException(status_code=401, detail='synthetic')
    monkeypatch.setattr(api, '_new_cloud_interview_session_service', lambda: NS(get_session=get_session))
    req = api.GenerateRequest(question='Can you give another example?',category='technical',selected_resume_id=RESUME_ID,
        session_id='30000000-0000-4000-8000-000000000001')
    with pytest.raises(HTTPException) as exc:
        await (api.generate_answer_stream if streaming else api.generate_answer)(req, Request({'type':'http','headers':[]}))
    assert exc.value.status_code == code


@pytest.mark.parametrize('wrapper', ['', 'Here is a possible answer: ', 'You can say: '])
def test_conclusion_is_advisory_while_leading_wrappers_are_sanitized(wrapper):
    answer = 'My grandfather helped with my science project; in conclusion, sharing that work made it memorable.'
    repaired, warnings, changed = AnswerGenerator().repair_personal_answer_if_needed(question='Favourite childhood memory?',answer=wrapper+answer)
    assert repaired == answer and 'style_phrase' in warnings
    assert changed == bool(wrapper)
    with pytest.raises(ProviderError):
        AnswerGenerator().repair_personal_answer_if_needed(question='Favourite memory?', answer='')
    with pytest.raises(ProviderError):
        AnswerGenerator().repair_personal_answer_if_needed(question='Favourite memory?', answer='I respond as an AI to this question.')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['normal', 'resume', 'job'])
@pytest.mark.parametrize('empty', [False, True])
async def test_personal_validation_real_helper_across_recovery_handlers(monkeypatch, failure, empty):
    from app.services.resume_index_service import ResumeIndexError
    from app.services.job_context_service import JobContextError
    answer = '' if empty else 'I enjoyed a science project with my grandfather; in conclusion, I remember our shared curiosity.'
    monkeypatch.setattr(api.generator, 'generate_answer', lambda **kw: dict(answer=answer,generation_ms=0,
        provider='synthetic',model='synthetic',fallback_used=False,error=None))
    if failure == 'resume':
        monkeypatch.setattr(api, '_retrieve_resume_context', lambda **kw: (_ for _ in ()).throw(ResumeIndexError('synthetic')))
    if failure == 'job':
        monkeypatch.setattr(api, '_generation_job_context', lambda *a, **kw: (_ for _ in ()).throw(JobContextError('synthetic')))
    req = api.GenerateRequest(question='What is your favourite childhood memory?',category='personal',
        profile={'personal_context':'Science project with grandfather.'},profile_context_used=True)
    if empty:
        with pytest.raises(HTTPException) as exc: await api.generate_answer(req)
        assert exc.value.status_code == 500
    else:
        result = await api.generate_answer(req)
        assert result.answer == answer and 'style_phrase' in result.personal_validation_errors


@pytest.mark.parametrize('section', ['experience','work_experience','internship'])
def test_experience_continuations_preserve_partial_identity_and_reject_ambiguity(section):
    documents = chunks((section,'Atlas Scheduler - '+ 'Booking workers coordinate durable calendar tasks. '*20),
                       (section,'Lunar Dashboard - Built charts.'))
    atlas = [c for c in documents if c.get('project_title') == 'Atlas Scheduler']
    assert len(atlas)>1
    service=cloud(documents)
    result=service.retrieve_resume_chunks(user_id=USER_A,resume_id=RESUME_ID,
        question='Explain your "Atlas Booking" project.',category='resume-based',limit=10)
    assert len(result['retrieved_chunks'])>1
    assert {c['chunk_id'] for c in result['retrieved_chunks']} <= {c['chunk_id'] for c in atlas}
    ambiguous=cloud(chunks((section,'Atlas Scheduler - Booking tasks.'),(section,'Atlas Dashboard - Charts.')))
    with pytest.raises(CloudResumeValidationError,match='not found'):
        ambiguous.retrieve_resume_chunks(user_id=USER_A,resume_id=RESUME_ID,question='Explain your "Atlas" project.',category='resume-based')


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['buffered','stream','job_recovery'])
async def test_repeated_general_no_match_fix_reaches_every_generation_path(monkeypatch,route):
    from app.services.job_context_service import JobContextError
    monkeypatch.setattr(api.settings,'ENABLE_TRUE_ANSWER_STREAMING',True)
    monkeypatch.setattr(api,'_current_user_for_selected_resume',lambda *a:NS(user_id=USER_A))
    monkeypatch.setattr(api,'_new_cloud_resume_service',lambda:cloud(chunks(('education','Studied biology.'))))
    answer='A deadlock is a cycle of tasks waiting on held resources.'
    result=dict(answer=answer,provider='synthetic',model='synthetic',generation_ms=0,fallback_used=False,error=None)
    calls=[]
    def generate(**kw):
        calls.append(kw)
        assert kw['answer_plan'].profile_context_policy=='FORBIDDEN'
        assert not kw['retrieved_snippets']
        return result.copy()
    def stream(**kw):
        yield dict(type='delta',text=answer)
        yield dict(type='primary_result',result=result.copy())
    monkeypatch.setattr(api.generator,'generate_answer',generate)
    monkeypatch.setattr(api.generator,'stream_openai_primary_answer',stream)
    if route=='job_recovery':
        monkeypatch.setattr(api,'_generation_job_context',lambda *a,**kw:(_ for _ in ()).throw(JobContextError('synthetic')))
    req=api.GenerateRequest(question='What is a deadlock?',category='technical',selected_resume_id=RESUME_ID)
    if route=='stream':
        response=await api.generate_answer_stream(req)
        events=[json.loads(item) async for item in response.body_iterator]
        assert not any(e['type']=='error' for e in events)
        assert next(e['metadata']['answer'] for e in events if e['type']=='metadata')==answer
    else:
        assert (await api.generate_answer(req)).answer==answer
    assert len(calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming',[False,True])
async def test_missing_project_keeps_strict_grounding(monkeypatch,streaming):
    monkeypatch.setattr(api.settings,'ENABLE_TRUE_ANSWER_STREAMING',True)
    monkeypatch.setattr(api,'_current_user_for_selected_resume',lambda *a:NS(user_id=USER_A))
    monkeypatch.setattr(api,'_new_cloud_resume_service',lambda:cloud(chunks(('projects','Atlas Scheduler - Booking tasks.'))))
    generation=Mock(side_effect=AssertionError('missing project must not generate'))
    monkeypatch.setattr(api.generator,'generate_answer',generation)
    monkeypatch.setattr(api.generator,'stream_openai_primary_answer',generation)
    req=api.GenerateRequest(question='Explain your "Lunar Rover" project.',category='resume-based',selected_resume_id=RESUME_ID)
    if streaming:
        response=await api.generate_answer_stream(req)
        events=[json.loads(item) async for item in response.body_iterator]
        assert any(e['type']=='error' and e['status_code']==409 for e in events)
    else:
        with pytest.raises(HTTPException) as exc:await api.generate_answer(req)
        assert exc.value.status_code==409
    assert generation.call_count==0
