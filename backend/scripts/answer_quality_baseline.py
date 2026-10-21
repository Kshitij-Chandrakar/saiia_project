"""Offline synthetic prompt capture; no live evaluation mode.

Run with --tests [pytest arguments] for guarded regressions, or --output PATH to
export synthetic prompt captures. Application imports happen inside offline().
Never point this harness at personal documents or real interview transcripts.
"""
import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
import json
import ipaddress
import logging
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'tests'))


def forbidden(*args, **kwargs):
    # Deliberately omit arguments: they could contain headers or private input.
    raise AssertionError('Unexpected external boundary in offline quality evaluation')


@contextmanager
def offline(*, capture_boundaries=True):
    """Install before app/pytest startup; restore process state after use."""
    import dotenv
    import httpx
    import requests

    preserved = {k: v for k, v in os.environ.items()
                 if k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC')}
    synthetic = dict(preserved, PYTHONDONTWRITEBYTECODE='1',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', GRPC_STT_ENABLED='false',
        GRPC_ANSWER_STREAM_ENABLED='false', ENABLE_SESSION_ANSWER_MODELS='false',
        OPENAI_API_KEY='synthetic-offline-key', GROQ_API_KEY='synthetic-offline-key',
        GEMINI_API_KEY='synthetic-offline-key', ASSEMBLYAI_API_KEY='',
        SUPABASE_SERVICE_ROLE_KEY='', SUPABASE_ANON_KEY='',
        NODE_OPTIONS='--require "' + (BACKEND.parent / 'frontend/tests/fixtures/loopback_only.cjs').as_posix() + '"')
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, synthetic, clear=True))
        stack.enter_context(patch.object(dotenv, 'load_dotenv', return_value=False))
        # Windows asyncio uses a loopback socket pair for its wakeup pipe.
        # Permit only that transport substrate; all HTTP is still forbidden.
        original_connect = socket.socket.connect
        original_resolve = socket.getaddrinfo

        def local_host(host):
            if host == 'localhost':
                return
            try:
                if ipaddress.ip_address(host).is_loopback:
                    return
            except ValueError:
                pass
            forbidden()

        def local_connect(sock, address):
            local_host(address[0])
            return original_connect(sock, address)

        def local_resolve(host, *args, **kwargs):
            local_host(host)
            return original_resolve(host, *args, **kwargs)

        stack.enter_context(patch.object(socket.socket, 'connect', local_connect))
        stack.enter_context(patch.object(socket, 'getaddrinfo', local_resolve))
        from starlette.testclient import _TestClientTransport
        original_sync_send, original_async_send = httpx.Client.send, httpx.AsyncClient.send
        def mock_transport_send(client, *args, **kwargs):
            if isinstance(client._transport, (httpx.MockTransport, _TestClientTransport)):
                return original_sync_send(client, *args, **kwargs)
            forbidden()
        async def mock_transport_async_send(client, *args, **kwargs):
            if isinstance(client._transport, (httpx.MockTransport, httpx.ASGITransport)):
                return await original_async_send(client, *args, **kwargs)
            forbidden()
        stack.enter_context(patch.object(httpx.Client, 'send', mock_transport_send))
        stack.enter_context(patch.object(httpx.AsyncClient, 'send', mock_transport_async_send))
        for target in ('socket.create_connection', 'socket.socket.connect_ex',
                       'requests.sessions.Session.request'):
            stack.enter_context(patch(target, side_effect=forbidden))
        # Providers and local/cloud retrieval/storage fail closed unless a test
        # explicitly substitutes a synthetic boundary. No FastAPI app/STT startup.
        from app.nlp import answer_generator as ag
        # Also isolate tests collected inside a larger suite where config may
        # already be imported. These are process-local patches, restored on exit.
        for name, value in dict(OPENAI_API_KEY='synthetic-offline-key',
                GROQ_API_KEY='synthetic-offline-key', GEMINI_API_KEY='synthetic-offline-key',
                ENABLE_SESSION_ANSWER_MODELS=False, REFINEMENT_ENABLED=False,
                ENABLE_VARIATION_REWRITE=False).items():
            stack.enter_context(patch.object(ag.settings, name, value))
        from app.services.resume_index_service import ResumeIndexService
        from app.services.job_context_service import JobContextService
        from app.services.refinement_service import RefinementService
        from app.cloud.cloud_resume import CloudResumeService
        from app.cloud.interview_transcripts import CloudInterviewTranscriptService
        original_openai_generate = ag.OpenAIResponsesProvider.generate
        def guarded_openai_generate(provider, **kwargs):
            # A missing-key regression may exercise the production local check;
            # calls with credentials still fail before any provider request.
            if not provider.api_key:
                return original_openai_generate(provider, **kwargs)
            forbidden()
        if capture_boundaries:
            stack.enter_context(patch.object(ag.OpenAIResponsesProvider, 'generate', guarded_openai_generate))
        stack.enter_context(patch.object(ag, 'extract_structured_coding_contract_with_llm', return_value=None))
        for cls, method in (
            (ag.OpenAIResponsesProvider, 'stream_generate'),
            (ag.OpenAICompatibleProvider, 'generate'), (ag.OllamaProvider, 'generate'),
            (RefinementService, 'submit'), (CloudResumeService, 'retrieve_resume_chunks'),
            (CloudInterviewTranscriptService, 'create_transcript_entry'),
        ):
            if capture_boundaries:
                stack.enter_context(patch.object(cls, method, side_effect=forbidden))
        # Existing endpoint regressions that do not test retrieval must still
        # never open the developer's local resume index or saved JD.
        stack.enter_context(patch.object(ResumeIndexService, 'retrieve',
            side_effect=lambda **kwargs: dict(retrieval_used=False, retrieved_chunks=[], retrieval_ms=0.0)))
        stack.enter_context(patch.object(JobContextService, 'get_context', return_value={}))
        yield


def capture(item):
    """Exercise real endpoint planning/context filtering and prompt construction.

    Synthetic retrieval is supplied only when production asks for it. Provider
    generation and semantic judgment are doubles; returned prose is NOT a model
    output or a quality measurement. Endpoint timing values are not exported.
    """
    from app.api import generate as api
    from app.nlp import answer_generator as ag
    from app.nlp.answer_variation import AnswerVariationHistory
    from answer_quality_spec import approved_policy

    evidence = item['evidence']
    captured = []
    retrieval_calls = []
    authored = 'This is an authored synthetic provider double, not a measured answer.'
    if item['id'] in ('coding_dedupe', 'coding_repeat'):
        authored = '```python\ndef unique(values):\n    return list(dict.fromkeys(values))\n```'
    elif item['id'] == 'debugging':
        authored = '```python\nfor value in xs:\n    print(value)\n```'

    def retrieve(**kwargs):
        retrieval_calls.append(dict(use_profile_context=kwargs['use_profile_context'],
                                    question=kwargs['question'], category=kwargs['category']))
        selected = evidence['selected_resume']
        chunks = evidence['snippets'] if selected or kwargs['use_profile_context'] else []
        return dict(retrieval_used=bool(chunks), retrieved_chunks=chunks, retrieval_ms=0.0,
                    selected_resume_id_used=selected, selected_resume_chunk_count=len(chunks),
                    resume_context_source='selected_resume' if selected else 'synthetic',
                    selected_resume_candidate_name='Mira Example' if selected else '')

    def primary(self, **kwargs):
        plan = kwargs['answer_plan']
        captured.append(dict(messages=self._answer_messages(kwargs['prompt']),
            plan=asdict(plan), context_type=kwargs['context_qt'],
            requested_output_tokens=self._openai_max_output_tokens(plan, context_qt=kwargs['context_qt']),
            legacy_budget_requests=budget_capture(kwargs['prompt'], plan,
                context_type=kwargs['context_qt'], coding=kwargs['use_coding_primary_versatile'])))
        return ag.ProviderResult(answer=authored, provider='openai', model='synthetic-model',
            primary_provider='openai', primary_model='synthetic-model', fallback_used=False,
            generation_ms=0, error=None)

    request = api.GenerateRequest(question=item['question'], category=item['category'],
        source='chat', profile=evidence['profile'], followup_mode='answer',
        followup_context=[dict(entry, created_at=time.time()) for entry in item['history']],
        selected_resume_id='10000000-0000-4000-8000-000000000001' if evidence['selected_resume'] else None)
    with ExitStack() as stack:
        stack.enter_context(patch.object(api, '_authorize_generation_session', return_value=None))
        stack.enter_context(patch.object(api, '_retrieve_resume_context', side_effect=retrieve))
        stack.enter_context(patch.object(api, '_generation_job_context',
            side_effect=lambda req, use_job_context: dict(evidence['job'], saved=True) if use_job_context and evidence['job'] else {}))
        stack.enter_context(patch.object(api, '_store_transcript_for_response', side_effect=lambda **kwargs: kwargs['response']))
        stack.enter_context(patch.object(api, '_queue_parallel_refinement', return_value=None))
        stack.enter_context(patch.object(ag.AnswerGenerator, '_generate_with_primary_provider', primary))
        stack.enter_context(patch.object(ag.AnswerGenerator, '_semantic_validate_with_openai',
            return_value=ag.SemanticValidationResult(valid=True, severity='none', issues=[])))
        stack.enter_context(patch.object(api.generator._default, 'variation_history', AnswerVariationHistory()))
        response = asyncio.run(api.generate_answer(request)).model_dump()
    # Ambiguous follow-ups can return a deterministic clarification before any
    # provider call. Record that outcome rather than inventing an effective prompt.
    return dict(case_id=item['id'], provenance='synthetic_offline_capture',
                policy_inputs=dict(question=item['question'], category=item['category'],
                                   evidence=evidence, history=item['history']),
                desired_policy=approved_policy(item), primary_calls=captured,
                test_process_overrides=dict(session_models=False, refinement=False, variation_rewrite=False),
                retrieval_calls=retrieval_calls, followup_status=response.get('follow_up_resolution_status'),
                result_model=response.get('model'), authored_double=authored,
                final_double=response['answer'],
                fallback_exercised=False)


def budget_capture(prompt, plan, *, context_type='', coding=False):
    """Capture legacy requests at the provider boundary, with authored responses."""
    from app.nlp.answer_generator import AnswerGenerator
    from app.answer_generation import PreparedAnswer, _request
    from app.answer_models import MODEL_CATALOG
    generator = AnswerGenerator()
    result = {}
    for route in ('openai', 'groq'):
        provider = generator.groq_coding_provider if route == 'groq' and coding else getattr(generator, route + '_provider')
        # Budget characterization uses mocked providers, not process-global live
        # cooldown state left by other tests. Keep this isolation instance-local.
        with patch.object(provider, 'generate', return_value='Synthetic authored answer.') as mock, \
                patch.object(generator, '_get_active_cooldown_seconds', return_value=None):
            if route == 'openai':
                generator._generate_with_openai(prompt, fallback_used=False,
                    primary_provider=route, answer_plan=plan, context_qt=context_type)
            else:
                generator._generate_with_groq(prompt, fallback_used=False, primary_provider=route,
                                              use_coding_primary_versatile=coding)
            result[route] = {k: v for k, v in mock.call_args.kwargs.items()
                             if k in ('max_tokens', 'max_output_tokens', 'timeout', 'temperature', 'reasoning_effort')}
    messages = generator._answer_messages(prompt)
    prepared = PreparedAnswer(messages[0]['content'], messages[1]['content'],
        generator._openai_max_output_tokens(plan, context_qt=context_type))
    result['selected_profiles'] = []
    for model in MODEL_CATALOG.values():
        _, _, body = _request(model, prepared, 'synthetic-offline-key')
        result['selected_profiles'].append(dict(profile=model.api_profile,
            requested=prepared.max_output_tokens,
            effective=body.get('max_output_tokens', body.get('max_completion_tokens',
                               body.get('generationConfig', {}).get('maxOutputTokens')))))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Write synthetic prompt captures, never live outputs')
    parser.add_argument('--tests', nargs=argparse.REMAINDER, help='Run offline pytest with explicit async plugins')
    args = parser.parse_args()
    with offline(capture_boundaries=args.tests is None):
        if args.tests is not None:
            import pytest
            return pytest.main(['-p', 'pytest_asyncio.plugin', '-p', 'anyio.pytest_plugin',
                                '-p', 'no:cacheprovider', *args.tests])
        from answer_quality_spec import CASES
        # Suppress routine application logs; exports contain synthetic inputs only.
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            records = [capture(item) for item in CASES]
        finally:
            logging.disable(previous)
        if args.output:
            args.output.write_text(json.dumps(records, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
        print(json.dumps(dict(cases=len(records), provider_calls='mocked',
                              live_calls=0, quality_scores='not_measured')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
