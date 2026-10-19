"""Request-local opt-in display policy. Durable fences never leave the coordinator."""
import asyncio
import copy
import json
from contextlib import aclosing
from contextvars import ContextVar

import httpx

from app.answer_generation import AttemptFailure, GenerationStopped, _sse, _normalize
from app.nlp.internal_marker_sanitizer import InternalMarkerStreamSanitizer


incremental_answers = ContextVar('incremental_grpc_answers', default=False)


class DisplayStream:
    def __init__(self, queue, control, budget):
        self.queue, self.control, self.budget = queue, control, budget
        self.attempt = self.revision = self.calls = 0

    def identity(self):
        return dict(attempt=self.attempt, revision=self.revision)

    async def put(self, event):
        await self.budget.wait(self.queue.put(event), self.control,
                               until=self.budget.expires, code='overall_timeout')

    async def reset(self):
        self.revision += 1
        await self.put(dict(type='replace', answer='', **self.identity()))

    async def begin(self, attempt):
        self.attempt = attempt
        if self.calls:
            await self.reset()
        self.calls += 1
        return self.revision

    async def delta(self, text, attempt, revision):
        self.control.check()
        if (attempt, revision) == (self.attempt, self.revision) and text:
            await self.put(dict(type='delta', text=text, attempt=attempt, revision=revision))


async def legacy_provider_stream(provider, kwargs, client, cancellation, on_retry):
    """Same configured provider/model/parameters; fallback stays in AnswerGenerator.

    OpenAI reuses its SDK stream. Groq/Ollama retain their configured endpoints
    and request options, adding only streaming. This helper never selects a model
    or starts fallback. Only the existing eligible Groq 429 retry is retained.
    """
    from app.nlp.answer_generator import ProviderError
    if hasattr(provider, 'stream_generate'):
        from app.api.generate import _iterate_sync_stream
        async with aclosing(_iterate_sync_stream(
                lambda: provider.stream_generate(**kwargs, cancellation=cancellation),
                cancellation=cancellation)) as stream:
            async for text in stream:
                yield text
        return
    ollama = hasattr(provider, 'base_url')
    name = 'ollama' if ollama else provider.name
    if not ollama and not provider.api_key:
        raise ProviderError('Provider credentials unavailable.', provider=name,
                            model=provider.model, error_type='missing_api_key')
    url = provider.base_url.rstrip('/') + '/api/generate' if ollama else provider.url
    headers = {} if ollama else {'Authorization': 'Bearer ' + provider.api_key, 'Content-Type': 'application/json'}
    body = (dict(model=provider.model, prompt=kwargs['prompt'], stream=True) if ollama else
            dict(model=provider.model, messages=kwargs['messages'], temperature=kwargs['temperature'],
                 max_tokens=kwargs['max_tokens'], stream=True))
    provider.last_retry_used = False
    retries = 2 if kwargs.get('retry_on_rate_limit') else 1
    for retry in range(retries):
        try:
            async with client.stream('POST', url, headers=headers, json=body, timeout=provider.timeout) as response:
                if response.status_code >= 400:
                    await response.aread()
                    _, _, delay = provider._parse_error_payload(response) if not ollama else (None, None, None)
                    if response.status_code == 429 and retry == 0 and retries == 2 and delay is not None and delay <= 15:
                        provider.last_retry_used = True
                        await on_retry()
                        await asyncio.sleep(max(0, delay))
                        continue
                    raise ProviderError('Provider request failed.', provider=name, model=provider.model,
                                        status_code=response.status_code, retry_after=delay,
                                        error_type='rate_limit' if response.status_code == 429 else 'provider_error')
                completed = False
                source = response.aiter_lines() if ollama else _sse(response)
                async for raw in source:
                    if not raw:
                        continue
                    if len(raw) > 1024 * 1024:
                        raise AttemptFailure('invalid_response')
                    if raw == '[DONE]':
                        break
                    item = json.loads(raw)
                    if ollama:
                        if item.get('error'):
                            raise AttemptFailure('provider_error')
                        text, complete = item.get('response', ''), item.get('done', False)
                    else:
                        text, _, complete = _normalize('groq', item)
                    if not isinstance(text, str):
                        raise AttemptFailure('invalid_response')
                    if text:
                        yield text
                    if complete:
                        completed = True
                        break
                if not completed:
                    raise AttemptFailure('incomplete_response')
                return
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, AttemptFailure) as exc:
            raise ProviderError('Provider stream unavailable.', provider=name, model=provider.model,
                                error_type=getattr(exc, 'code', 'provider_error')) from None


class LegacyProvider:
    def __init__(self, provider, run):
        self.provider, self.run = provider, run

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def generate(self, **kwargs):
        return self.run.sync_call(self.provider, kwargs, display=self.run.primary_active)


class LegacyRun:
    """Publish only primary provider calls, inside the single prepared worker."""
    def __init__(self, display, loop, client):
        from app.nlp.answer_generator import StreamCancellation
        self.display, self.loop, self.client = display, loop, client
        self.cancellation = StreamCancellation()
        self.primary_active = False
        self.active = True
        self.pending = None
        self.calls = 0

    async def call(self, provider, kwargs, display):
        attempt = self.display.attempt
        revision = self.display.revision
        if display:
            attempt = self.calls
            self.calls += 1
            revision = await self.display.begin(attempt)
        sanitizer = InternalMarkerStreamSanitizer()
        text = ''
        async def retry():
            nonlocal revision
            if display:
                await self.display.reset()
                revision = self.display.revision
                sanitizer.reset()
        try:
            async with aclosing(legacy_provider_stream(provider, kwargs, self.client, self.cancellation, retry)) as stream:
                while True:
                    try:
                        delta = await self.display.budget.wait(stream.__anext__(), self.display.control,
                            until=self.display.budget.expires, code='overall_timeout')
                    except StopAsyncIteration:
                        break
                    text += delta
                    if len(text) > 262144:
                        raise AttemptFailure('answer_too_large')
                    if display:
                        await self.display.delta(sanitizer.feed(delta), attempt, revision)
            if display:
                await self.display.delta(sanitizer.flush(), attempt, revision)
            if not text.strip():
                raise AttemptFailure('empty_response')
            return text.strip()
        except Exception:
            if display:
                await self.display.reset()
            raise

    def sync_call(self, provider, kwargs, display):
        from app.nlp.answer_generator import ProviderError
        if not self.active:
            raise GenerationStopped()
        self.pending = asyncio.run_coroutine_threadsafe(self.call(provider, kwargs, display), self.loop)
        try:
            return self.pending.result()
        except BaseException as exc:
            if not self.active or self.display.control.stopped.is_set() or isinstance(exc, (GenerationStopped, asyncio.CancelledError)):
                raise GenerationStopped() from None
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError('Provider stream unavailable.', error_type=getattr(exc, 'code', 'provider_error')) from None

    def install(self, instance):
        for name in ('openai_provider', 'groq_provider', 'groq_coding_provider', 'groq_refinement_provider', 'ollama_provider'):
            setattr(instance, name, LegacyProvider(copy.copy(getattr(instance, name)), self))
        original = instance._generate_with_primary_provider
        def primary(**kwargs):
            self.primary_active = True
            try:
                return original(**kwargs)
            finally:
                self.primary_active = False
        instance._generate_with_primary_provider = primary
