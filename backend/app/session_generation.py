"""Session execution boundary; legacy provider routing is deliberately retained.

The sync answer planner/validator runs in a worker. Only its request-local provider
objects bridge to cancellable async adapters; no global settings are modified.
"""
import asyncio
import copy
import hashlib
import json
import uuid
from contextlib import aclosing
from contextvars import ContextVar

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from app.answer_generation import (AttemptFailure, Deadlines, GenerationBudget,
    GenerationControl, GenerationFailure, GenerationStopped, PreparedAnswer,
    attempt_models, provider_stream)
from app.answer_models import resolve_binding, ModelConfigurationError
from app.config import settings

_generator = ContextVar("session_answer_generator", default=None)
_prepared = ContextVar("session_prepared_context", default=None)


def scoped_generator(default):
    class Scoped:
        _default = default
        def __getattr__(self, name):
            return getattr(_generator.get() or default, name)
        def __setattr__(self, name, value):
            # Restoring a class method must not pin its bound receiver into copies.
            if (getattr(value, '__self__', None) is default
                    and getattr(type(default), name, None) is getattr(value, '__func__', None)):
                default.__dict__.pop(name, None)
                return
            setattr(default, name, value)
        def __delattr__(self, name):
            delattr(default, name)
    return Scoped()


def cached_context(function):
    def call(*args, **kwargs):
        cache = _prepared.get()
        if cache is None:
            return function(*args, **kwargs)
        key = function.__name__
        if key not in cache:
            cache[key] = function(*args, **kwargs)
        return copy.deepcopy(cache[key])
    return call


class TurnStateError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class TurnStore:
    """Backend-only RPC; no interview content appears in errors or logs."""
    async def operation(self, op, identity, *, token=None, payload=None):
        from app.cloud.supabase_config import get_supabase_settings
        cfg = get_supabase_settings().require_configured()
        body = dict(identity, p_operation=op, p_token=token, p_payload=payload)
        try:
            async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0)) as client:
                response = await client.post(cfg.supabase_url.rstrip('/') + '/rest/v1/rpc/session_generation_turn',
                    headers={"apikey": cfg.service_role_key, "Authorization": "Bearer " + cfg.service_role_key},
                    json=body, timeout=8)
            if response.status_code != 200:
                raise TurnStateError("persistence_unavailable")
            result = response.json()
            if result.get("error"):
                raise TurnStateError(result["error"])
            return result
        except (httpx.HTTPError, ValueError):
            raise TurnStateError("persistence_unavailable") from None


def new_turn_store():
    return TurnStore()


class AttemptProvider:
    """Request-local sync facade for existing correction/validation helpers."""
    last_retry_used = False

    def __init__(self, run):
        self.run = run
        self.name = run.model.provider
        self.model = run.model.api_model

    def generate(self, *, instructions=None, input_text=None, messages=None, **kwargs):
        if messages:
            instructions = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
            input_text = '\n'.join(m['content'] for m in messages if m['role'] != 'system')
        prepared = PreparedAnswer(instructions or '', input_text or '',
                                  min(int(kwargs.get('max_output_tokens') or kwargs.get('max_tokens') or 2500), 65536))
        return self.run.sync_call(prepared, display=False)


class AttemptRun:
    def __init__(self, model, budget, control, client, queue, loop, index, primary_cache):
        self.model, self.budget, self.control, self.client = model, budget, control, client
        self.queue, self.loop, self.index, self.primary_cache = queue, loop, index, primary_cache
        self.reported = None
        self.end = budget.expires - (budget.limits.fallback_reserve if index == 0 and len(attempt_models(model)) > 1 else 0)
        self.failure = None
        self.active = True
        self.pending = None

    async def call(self, prepared, display):
        text = ''
        deadline = self.budget.clock() + self.budget.limits.first_token
        key = {'openai': settings.OPENAI_API_KEY, 'groq': settings.GROQ_API_KEY, 'gemini': settings.GEMINI_API_KEY}[self.model.provider]
        async with aclosing(provider_stream(self.client, self.model, prepared, key)) as stream:
            while True:
                until = min(deadline, self.end)
                code = 'fallback_reserve' if self.end <= deadline and self.end < self.budget.expires else ('idle_timeout' if text.strip() else 'first_token_timeout')
                try:
                    delta, reported, complete = await self.budget.wait(stream.__anext__(), self.control, until=until, code=code)
                except StopAsyncIteration:
                    raise AttemptFailure('incomplete_response') from None
                self.reported = reported or self.reported
                if delta:
                    text += delta
                    if len(text) > 262144:
                        raise AttemptFailure('answer_too_large')
                    if delta.strip():
                        deadline = self.budget.clock() + self.budget.limits.idle
                    if display and self.index == 0 and self.active:
                        await self.queue.put(dict(type='delta', text=delta, attempt=self.index))
                if complete:
                    if not text.strip():
                        raise AttemptFailure('empty_response')
                    return text

    def sync_call(self, prepared, display=False):
        if not self.active:
            raise GenerationStopped()
        future = asyncio.run_coroutine_threadsafe(self.call(prepared, display), self.loop)
        self.pending = future
        try:
            return future.result()
        except BaseException as exc:
            if isinstance(exc, AttemptFailure) and display:
                self.failure = exc
            if not self.active or isinstance(exc, (GenerationStopped, asyncio.CancelledError)) or self.control.stopped.is_set():
                raise GenerationStopped() from None
            from app.nlp.answer_generator import ProviderError
            raise ProviderError('Answer attempt failed', error_type=getattr(exc, 'code', 'provider_error')) from None

    def primary(self, **kwargs):
        from app.nlp.answer_generator import ProviderResult
        if 'primary' not in self.primary_cache:
            messages = self.instance._answer_messages(kwargs['prompt'])
            self.primary_cache['primary'] = PreparedAnswer(messages[0]['content'], messages[1]['content'],
                self.instance._openai_max_output_tokens(kwargs['answer_plan'], context_qt=kwargs['context_qt']))
        answer = self.sync_call(self.primary_cache['primary'], display=True)
        return ProviderResult(answer=answer, provider=self.model.provider, model=self.model.api_model,
                              primary_provider=self.model.provider, primary_model=self.model.api_model,
                              fallback_used=bool(self.index), generation_ms=0, error=None)


async def dispatch_session_generation(req, request, *, buffered):
    if request is not None and getattr(getattr(request, 'state', None), 'session_generation_internal', False):
        return None
    if not req.session_id or not settings.ENABLE_SESSION_ANSWER_MODELS:
        return None  # Existing shared loader still rejects a binding while disabled.
    from app.api import generate as api
    # Reuse the existing auth/error mapping before accessing the authoritative row.
    user = await asyncio.to_thread(api._authorize_generation_session, req, request)
    session = await asyncio.to_thread(api._new_cloud_interview_session_service().get_session,
        user_id=user.user_id, session_id=req.session_id, allow_model_bound=True)
    if session.status != 'active':
        raise HTTPException(409, 'Interview session is not active.')
    if req.job_context_id or (req.selected_resume_id and req.selected_resume_id != session.selected_resume_id):
        raise HTTPException(400, 'Session context override is not allowed.')
    key = getattr(session, 'selected_model_key', None)
    from app.cloud.interview_sessions import session_model_backend_ready
    if key and not session_model_backend_ready():
        raise HTTPException(409, 'Session model development execution is not ready for this target.')
    try:
        selected_model = resolve_binding(key, getattr(session, 'selected_model_binding', None)) if key else None
    except ModelConfigurationError:
        raise HTTPException(409, 'Stored session model binding is unsupported.') from None
    store = new_turn_store()
    if req.recover_turn:
        recovery_identity = dict(p_user_id=user.user_id, p_session_id=session.id,
            p_request_id=req.request_id, p_hash='', p_attempt=req.retry_attempt, p_supersedes=None)
        try:
            saved = await store.operation('recover', recovery_identity)
            request_payload = saved['payload']['request']
        except (TurnStateError, KeyError, TypeError):
            raise HTTPException(409, dict(code='generation_unrecoverable')) from None
        req = api.GenerateRequest(**dict(request_payload, retry_attempt=req.retry_attempt, recover_turn=False))
    req.selected_resume_id = session.selected_resume_id
    req.target_role = session.target_role
    req.company_name = session.company_name
    req.job_description = session.job_description_preview
    req.request_id = api._stream_request_id(req.request_id or str(uuid.uuid4()))
    identity = dict(p_user_id=user.user_id, p_session_id=session.id, p_request_id=req.request_id,
                    p_hash=hashlib.sha256(json.dumps(req.model_dump(exclude={'request_id','retry_attempt','supersedes_request_id','recover_turn'}), sort_keys=True).encode()).hexdigest(),
                    p_attempt=req.retry_attempt, p_supersedes=req.supersedes_request_id)
    try:
        claim = await store.operation('claim', identity, payload={'request': req.model_dump(exclude={'recover_turn'})})
    except TurnStateError as exc:
        raise HTTPException(503 if exc.code == 'persistence_unavailable' else 409,
            dict(code=exc.code, message='Answer storage is unavailable.' if exc.code == 'persistence_unavailable' else 'Answer request cannot be resumed.')) from None
    if claim['state'] not in ('claimed','checkpoint','completed'):
        raise HTTPException(409, dict(code='generation_' + claim['state'], request_id=req.request_id))
    control = GenerationControl()

    async def events():
        token = claim.get('token')
        queue = asyncio.Queue(maxsize=8)
        result = None
        failures = []
        preserve_checkpoint = False
        pending_variation = []

        async def monitor_session():
            while True:
                await asyncio.sleep(.25)
                if key and (not settings.ENABLE_SESSION_ANSWER_MODELS or not session_model_backend_ready()):
                    control.cancel()
                    return
                verified = await asyncio.to_thread(api._current_user_for_session_id, req, request)
                if verified.user_id != user.user_id:
                    control.cancel()
                    return
                if request is not None and request.scope.get('type') == 'http' and 'grpc_cloud_context_only' not in request.scope.get('state', {}):
                    if await request.is_disconnected():
                        control.cancel()
                        return
                current = await asyncio.to_thread(api._new_cloud_interview_session_service().get_session,
                    user_id=user.user_id, session_id=session.id, allow_model_bound=True)
                if current.status != 'active':
                    control.cancel()
                    return
                check = await store.operation('check', identity, token=token)
                if check['state'] not in ('processing','checkpoint','completed'):
                    control.cancel()
                    return

        async def alive():
            try:
                await monitor_session()
            except asyncio.CancelledError:
                raise
            except Exception:
                control.cancel()

        async def produce():
            nonlocal result, pending_variation
            if claim['state'] in ('checkpoint','completed'):
                result = claim['payload']
                return
            from app.nlp.answer_variation import variation_scope
            primary_cache = {}
            context_cache = {}
            models = attempt_models(selected_model) if key else (None,)
            budget = GenerationBudget(Deadlines.from_config(settings, coding=bool(req.coding_answer_mode or req.screen_question_type in ('coding','debugging','output'))))
            loop = asyncio.get_running_loop()
            async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0)) as client:
                for index, model in enumerate(models):
                    control.check()
                    run = AttemptRun(model, budget, control, client, queue, loop, index, primary_cache) if model else None
                    def worker():
                        # All planner, prompt, grounding and validation logic remains in
                        # the existing endpoint; only the request-local providers differ.
                        from app.grpc_answer_pipeline import _private_pipeline, _install_private_log_filter
                        private = _private_pipeline.set(True)
                        _install_private_log_filter()
                        scope_token = variation_scope.set((user.user_id, session.id))
                        cache_token = _prepared.set(context_cache)
                        gen_token = None
                        try:
                            if run:
                                instance = copy.copy(api.generator._default)
                                run.instance = instance
                                provider = AttemptProvider(run)
                                for attr in ('openai_provider','groq_provider','groq_coding_provider','groq_refinement_provider'):
                                    setattr(instance, attr, provider)
                                instance._generate_with_primary_provider = run.primary
                                instance._select_primary_provider = lambda *args: 'openai'
                                # Stage variation changes until the final result commits.
                                instance.variation_history = copy.deepcopy(instance.variation_history)
                                run.history_before = list(instance.variation_history._entries)
                                gen_token = _generator.set(instance)
                            scope = dict(request.scope if request else {'type':'http','headers':[]})
                            scope['state'] = dict(scope.get('state',{}), session_generation_internal=True)
                            return asyncio.run(api.generate_answer(req, Request(scope)))
                        finally:
                            if gen_token is not None:
                                _generator.reset(gen_token)
                            _prepared.reset(cache_token)
                            variation_scope.reset(scope_token)
                            _private_pipeline.reset(private)
                    try:
                        response = await budget.wait(asyncio.to_thread(worker), control,
                            until=run.end if run else budget.expires, code='fallback_reserve' if run and index == 0 and len(models)>1 else 'overall_timeout')
                        if run and run.failure:
                            raise run.failure
                        control.check()
                        result = response.model_dump()
                        if run:
                            pending_variation = [entry for entry in run.instance.variation_history._entries
                                                 if entry not in run.history_before]
                        if not result.get('answer','').strip():
                            raise AttemptFailure('empty_response')
                        result.update(request_id=req.request_id, retry_attempt=req.retry_attempt,
                            selected_model_key=key, selected_provider=selected_model.provider if key else None,
                            selected_api_model=selected_model.api_model if key else None,
                            actual_provider=model.provider if model else result.get('provider'),
                            actual_api_model=model.api_model if model else result.get('model'),
                            reported_model=run.reported if run else None, fallback_used=bool(index),
                            transcript_entry_stored=True)
                        if model:
                            result.update(provider=model.provider, model=model.api_model)
                        if result.get('code_validation_used') and result.get('code_validation_passed') is False:
                            raise AttemptFailure('invalid_response')
                        checkpoint = {'question': req.original_question or req.question, 'result': result,
                                      'request': req.model_dump(exclude={'recover_turn'})}
                        await store.operation('checkpoint', identity, token=token, payload=checkpoint)
                        result = checkpoint
                        return
                    except (AttemptFailure, HTTPException) as exc:
                        if isinstance(exc, HTTPException) and (not run or exc.status_code not in (500,502,503,504)):
                            raise
                        control.check()
                        failures.append(getattr(exc,'code','provider_error'))
                        await queue.put(dict(type='discard', attempt=index))
                    finally:
                        if run:
                            run.active = False
                            if run.pending:
                                run.pending.cancel()
                await store.operation('fail', identity, token=token)
                raise GenerationFailure(tuple(failures))

        task = asyncio.create_task(produce())
        monitor = asyncio.create_task(alive()) if claim['state']=='claimed' else None
        accepted_attempt = 0
        try:
            yield api._stream_event(dict(type='start', request_id=req.request_id))
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), .05)
                    control.check()
                    if event['type']=='discard':
                        accepted_attempt = event['attempt'] + 1
                        yield api._stream_event(dict(type='replace', answer='', attempt=accepted_attempt, request_id=req.request_id))
                    else:
                        if event.get('attempt',0) >= accepted_attempt:
                            yield api._stream_event(dict(event, request_id=req.request_id))
                except asyncio.TimeoutError:
                    pass
            await task
            control.check()
            if claim['state'] != 'completed':
                await store.operation('complete', identity, token=token)
            control.check()
            final = result['result']
            for entry in pending_variation:
                api.generator._default.variation_history.add(answer_type=entry.answer_type,
                    normalized_question=entry.normalized_question, context_fingerprint=entry.context_fingerprint,
                    answer=entry.answer, ttl_seconds=settings.VARIATION_CACHE_TTL_SECONDS,
                    history_limit=settings.VARIATION_HISTORY_LIMIT)
            yield api._stream_event(dict(type='replace', request_id=req.request_id, answer=final['answer']))
            yield api._stream_event(dict(type='metadata', request_id=req.request_id, metadata=final))
            yield api._stream_event(dict(type='done', request_id=req.request_id))
        except GenerationFailure:
            yield api._stream_event(dict(type='replace', request_id=req.request_id, answer=''))
            yield api._stream_event(dict(type='error', request_id=req.request_id, error='generation_failed', message='Unable to generate an answer', retry_attempt=req.retry_attempt))
            yield api._stream_event(dict(type='done', request_id=req.request_id, incomplete=True))
        except TurnStateError as exc:
            preserve_checkpoint = True
            yield api._stream_event(dict(type='replace', request_id=req.request_id, answer=''))
            yield api._stream_event(dict(type='error', request_id=req.request_id, error=exc.code, message='Answer saving is pending. Retry to recover.'))
            yield api._stream_event(dict(type='done', request_id=req.request_id, incomplete=True))
        except HTTPException:
            # Revoked authorization/session validity is terminal, never fallback.
            yield api._stream_event(dict(type='replace', request_id=req.request_id, answer=''))
            yield api._stream_event(dict(type='error', request_id=req.request_id, error='generation_stopped', message='Generation stopped.'))
            yield api._stream_event(dict(type='done', request_id=req.request_id, incomplete=True))
        finally:
            control.cancel()
            task.cancel()
            if monitor:
                monitor.cancel()
            await asyncio.gather(task, *([monitor] if monitor else []), return_exceptions=True)
            # Checkpoint/completed states are intentionally retained on cancellation.
            if not preserve_checkpoint:
                try:
                    await store.operation('cancel', identity, token=token)
                except TurnStateError:
                    pass
    async def sequenced_events():
        async with aclosing(events()) as stream:
            sequence = 0
            async for line in stream:
                event = json.loads(line)
                event['sequence'] = sequence
                sequence += 1
                yield api._stream_event(event)
    response = StreamingResponse(sequenced_events(), media_type='application/x-ndjson')
    if not buffered:
        return response
    final = None
    async for line in response.body_iterator:
        event = json.loads(line)
        if event['type']=='metadata':
            final = event['metadata']
        if event['type']=='error':
            raise HTTPException(502, dict(code=event['error'], message=event.get('message'), request_id=req.request_id))
    if final is None:
        raise HTTPException(409, 'Generation stopped.')
    return api.GenerateResponse(**final)
