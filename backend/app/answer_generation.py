"""Opt-in answer adapters shared by HTTP and cloud gRPC session routing.

Uses existing Responses/Chat protocols and installed httpx, with no SDK retries.
Attempt-tagged deltas are provisional. Only `result` is eligible for persistence.
"""
import asyncio
import json
import math
import time
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.answer_models import MODEL_CATALOG, FALLBACK_MODEL_KEY, AnswerModel, DISABLED_MODELS
from app.config import settings


class FeatureDisabled(RuntimeError):
    pass


class AttemptFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)  # Never retain raw provider errors/content.


class GenerationFailure(Exception):
    def __init__(self, codes: tuple[str, ...]):
        self.codes = codes
        super().__init__("Unable to generate an answer")


class GenerationStopped(BaseException):
    """Control signal distinct from task cancellation and ordinary provider errors."""


def attempt_models(model):
    fallback = MODEL_CATALOG[FALLBACK_MODEL_KEY]
    return (model,) if (model.provider, model.api_model) == (fallback.provider, fallback.api_model) else (model, fallback)


@dataclass
class GenerationControl:
    stopped: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        """Caller must signal logout, supersession, auth rejection or termination."""
        self.stopped.set()

    def check(self) -> None:
        if self.stopped.is_set():
            raise GenerationStopped()


@dataclass(frozen=True)
class PreparedAnswer:
    instructions: str = field(repr=False)
    text: str = field(repr=False)
    max_output_tokens: int = 2500

    def __post_init__(self):
        if not self.text.strip() or not 1 <= self.max_output_tokens <= 65536:
            raise ValueError("Invalid prepared answer input")


@dataclass(frozen=True)
class Deadlines:
    first_token: float = 6
    idle: float = 4
    overall: float = 25
    fallback_reserve: float = 8

    def __post_init__(self):
        values = (self.first_token, self.idle, self.overall, self.fallback_reserve)
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("Deadlines must be finite and positive")
        if not self.first_token <= self.fallback_reserve < self.overall:
            raise ValueError("Fallback reserve must cover first-token time and fit overall budget")

    @classmethod
    def from_config(cls, config=settings, *, coding=False):
        prefix = "ANSWER_MODEL_CODING_" if coding else "ANSWER_MODEL_"
        return cls(*(getattr(config, prefix + name + "_SECONDS")
                     for name in ("FIRST_TOKEN", "IDLE", "OVERALL", "FALLBACK_RESERVE")))


@dataclass
class GenerationBudget:
    """Create once; reuse for answer-producing corrections and fallback later."""
    limits: Deadlines
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    started: float = field(init=False)

    def __post_init__(self):
        self.started = self.clock()

    @property
    def expires(self):
        return self.started + self.limits.overall

    async def wait(self, operation, control: GenerationControl, *, until: float, code: str):
        """Cancel the active network read on any deadline or lifecycle stop."""
        work = asyncio.ensure_future(operation)
        stop = asyncio.create_task(control.stopped.wait())
        try:
            control.check()
            remaining = min(until, self.expires) - self.clock()
            if remaining <= 0:
                raise AttemptFailure("overall_timeout" if self.clock() >= self.expires else code)
            done, _ = await asyncio.wait((work, stop), timeout=remaining,
                                         return_when=asyncio.FIRST_COMPLETED)
            control.check()
            if work not in done:
                raise AttemptFailure("overall_timeout" if self.clock() >= self.expires else code)
            result = work.result()
            control.check()
            if self.clock() >= min(until, self.expires):
                raise AttemptFailure("overall_timeout" if self.clock() >= self.expires else code)
            return result
        finally:
            for task in (work, stop):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, stop, return_exceptions=True)


def _request(model: AnswerModel, prepared: PreparedAnswer, key: str):
    """Fixed endpoints and model-specific allowlisted parameters only."""
    limit = min(prepared.max_output_tokens, model.output_limit)
    if model.provider == "openai":
        return ("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {key}"},
                dict(model=model.api_model, instructions=prepared.instructions, input=prepared.text,
                     **({"reasoning": {"effort": model.effort}} if model.api_profile == "openai-reasoning" else {}), max_output_tokens=limit,
                     store=False, stream=True))
    if model.provider == "groq":
        return ("https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {key}"},
                dict(model=model.api_model,
                     messages=[{"role": "system", "content": prepared.instructions},
                               {"role": "user", "content": prepared.text}],
                     **({"reasoning_effort": model.effort, "include_reasoning": False} if model.api_profile == "groq-oss" else {}),
                     max_completion_tokens=limit, stream=True))
    return (f"https://generativelanguage.googleapis.com/v1beta/models/{model.api_model}:streamGenerateContent?alt=sse",
            {"x-goog-api-key": key},
            dict(systemInstruction={"parts": [{"text": prepared.instructions}]},
                 contents=[{"role": "user", "parts": [{"text": prepared.text}]}],
                 generationConfig={"maxOutputTokens": limit,
                                   **({"thinkingConfig": {"thinkingLevel": model.effort}} if model.api_profile == "gemini-thinking" else {})}))


async def _sse(response):
    data = []
    size = 0
    async for line in response.aiter_lines():
        size += len(line)
        if size > 1024 * 1024:
            raise AttemptFailure("invalid_response")
        if not line:
            if data:
                yield "\n".join(data)
            data, size = [], 0
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)


def _normalize(provider: str, item: dict) -> tuple[str, str | None, bool]:
    """Return answer text, reported model and successful completion marker."""
    if item.get("error"):
        raise AttemptFailure("provider_error")
    if provider == "openai":
        kind = item.get("type")
        if kind in {"error", "response.failed", "response.incomplete", "response.refusal.delta"}:
            raise AttemptFailure("invalid_response")
        response = item.get("response") or {}
        if kind == "response.completed" and response.get("status", "completed") != "completed":
            raise AttemptFailure("invalid_response")
        return (item.get("delta", "") if kind == "response.output_text.delta" else "",
                response.get("model"), kind == "response.completed")
    if provider == "groq":
        choices = item.get("choices") or []
        if not choices:
            return "", item.get("model"), False
        choice = choices[0]
        finish = choice.get("finish_reason")
        if finish and finish != "stop":
            raise AttemptFailure("invalid_response")
        return (choice.get("delta") or {}).get("content") or "", item.get("model"), finish == "stop"
    if (item.get("promptFeedback") or {}).get("blockReason"):
        raise AttemptFailure("invalid_response")
    candidates = item.get("candidates") or []
    if not candidates:
        return "", item.get("modelVersion"), False
    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish and finish != "STOP":
        raise AttemptFailure("invalid_response")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    return text, item.get("modelVersion"), finish == "STOP"


async def provider_stream(client: httpx.AsyncClient, model: AnswerModel,
                          prepared: PreparedAnswer, key: str):
    if f"{model.provider}:{model.api_model}" in DISABLED_MODELS:
        raise AttemptFailure("model_disabled")
    if not key:
        raise AttemptFailure("missing_credentials")
    url, headers, body = _request(model, prepared, key)
    try:
        async with client.stream("POST", url, headers=headers, json=body, timeout=None) as response:
            if response.status_code >= 400:
                # User authorization is checked by the caller; this is upstream auth only.
                code = {401: "provider_auth", 403: "provider_auth", 429: "rate_limit"}.get(
                    response.status_code, "provider_unavailable")
                raise AttemptFailure(code)
            async for data in _sse(response):
                if data == "[DONE]":
                    break
                item = json.loads(data)
                if not isinstance(item, dict):
                    raise AttemptFailure("invalid_response")
                text, reported, complete = _normalize(model.provider, item)
                if not isinstance(text, str) or (reported is not None and not isinstance(reported, str)):
                    raise AttemptFailure("invalid_response")
                yield text, reported, complete
                if complete:
                    return
            raise AttemptFailure("incomplete_response")
    except httpx.TimeoutException:
        raise AttemptFailure("provider_timeout") from None
    except httpx.HTTPError:
        raise AttemptFailure("provider_unavailable") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise AttemptFailure("invalid_response") from None


async def stream_answer(model_key: str, prepared: PreparedAnswer, *, client=None,
                        control=None, budget=None, coding=False, config=settings):
    """Future HTTP/gRPC coordinator. Consumer must close this iterator on disconnect.

    Primary deltas are attempt-tagged; fallback is buffered and replaces them.
    A supplied budget is NEVER reset, including for future correction calls.
    """
    if not config.ENABLE_SESSION_ANSWER_MODELS:
        raise FeatureDisabled("Session model routing is not activated")
    model = MODEL_CATALOG[model_key]  # Unknown keys are validation errors, not fallback.
    control = control or GenerationControl()
    control.check()
    budget = budget or GenerationBudget(Deadlines.from_config(config, coding=coding))
    credentials = {"openai": config.OPENAI_API_KEY, "groq": config.GROQ_API_KEY,
                   "gemini": config.GEMINI_API_KEY}
    if client is None:
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0)) as owned:
            async with aclosing(stream_answer(model_key, prepared, client=owned, control=control,
                                              budget=budget, config=config)) as events:
                async for event in events:
                    yield event
        return
    attempts = attempt_models(model)
    failures = []
    for index, current in enumerate(attempts):
        control.check()
        attempt = "primary" if index == 0 else "fallback"
        end = budget.expires
        end_code = "overall_timeout"
        if index == 0 and len(attempts) == 2:
            end -= budget.limits.fallback_reserve
            end_code = "fallback_reserve"
        text = ""
        reported = None
        token_deadline = budget.clock() + budget.limits.first_token
        try:
            async with aclosing(provider_stream(client, current, prepared,
                                                credentials[current.provider])) as stream:
                while True:
                    deadline = min(token_deadline, end)
                    code = end_code if end <= token_deadline else ("idle_timeout" if text.strip() else "first_token_timeout")
                    try:
                        delta, version, complete = await budget.wait(
                            stream.__anext__(), control, until=deadline, code=code)
                    except StopAsyncIteration:
                        raise AttemptFailure("incomplete_response") from None
                    reported = version or reported
                    if delta:
                        text += delta
                        if len(text) > 262144:
                            raise AttemptFailure("answer_too_large")
                        # Whitespace/reasoning/heartbeats do not buy more first-token time.
                        if delta.strip():
                            token_deadline = budget.clock() + budget.limits.idle
                        if index == 0:
                            yield dict(type="delta", attempt=attempt, text=delta)
                    if complete:
                        if not text.strip():
                            raise AttemptFailure("empty_response")
                        control.check()
                        result = dict(answer=text, selected_model_key=model.key,
                                      selected_provider=model.provider, selected_api_model=model.api_model,
                                      actual_provider=current.provider, actual_api_model=current.api_model,
                                      reported_model=reported, fallback_used=bool(index), attempt=attempt,
                                      failure_codes=tuple(failures))
                        if index:
                            yield dict(type="replace", attempt=attempt, answer=text)
                        control.check()
                        yield dict(type="result", attempt=attempt, result=result)
                        return
        except AttemptFailure as exc:
            control.check()
            failures.append(exc.code)
            yield dict(type="discard", attempt=attempt)
            control.check()
    raise GenerationFailure(tuple(failures))
