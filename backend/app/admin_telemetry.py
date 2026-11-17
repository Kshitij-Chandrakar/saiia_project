"""Content-free provider attempt observations; callers supply only verified ownership."""

import asyncio
import contextvars
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

context: contextvars.ContextVar[
    tuple[str, str, Callable[[dict[str, object]], None]] | None
] = contextvars.ContextVar("admin_telemetry", default=None)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="admin-telemetry")


def numeric(value):
    return value if type(value) is int and 0 <= value <= 10**12 else None


class Attempt:
    def __init__(self, provider, model):
        self.provider, self.model = str(provider).lower().split()[0], model
        self.id = str(uuid4())
        self.input = self.output = None
        self.reported = None
        self.outcome = "aborted"

    def __enter__(self):
        self.started = time.monotonic()
        return self

    def usage(self, response):
        if context.get() is None:
            return
        if not isinstance(response, dict):
            usage = getattr(response, "usage", None)
            if usage is not None and not isinstance(usage, dict):
                usage = {
                    name: value
                    for name in (
                        "input_tokens",
                        "output_tokens",
                        "prompt_tokens",
                        "completion_tokens",
                    )
                    if (value := getattr(usage, name, None)) is not None
                }
            response = {"model": getattr(response, "model", None), "usage": usage}
        self.reported = (
            response.get("model") or response.get("modelVersion") or self.reported
        )
        usage = (
            response.get("usage")
            or (
                response["response"].get("usage")
                if isinstance(response.get("response"), dict)
                else None
            )
            or (
                response["x_groq"].get("usage")
                if isinstance(response.get("x_groq"), dict)
                else None
            )
            or response.get("usageMetadata")
            or {}
        )
        if not isinstance(usage, dict):
            return
        incoming = numeric(
            usage.get(
                "input_tokens",
                usage.get("prompt_tokens", usage.get("promptTokenCount")),
            )
        )
        outgoing = numeric(
            usage.get(
                "output_tokens",
                usage.get("completion_tokens", usage.get("candidatesTokenCount")),
            )
        )
        if incoming is not None:
            self.input = incoming
        if outgoing is not None:
            self.output = outgoing

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, kind, value, traceback):
        if context.get() is not None:
            await asyncio.get_running_loop().run_in_executor(
                _executor,
                contextvars.copy_context().run,
                self.__exit__,
                kind,
                value,
                traceback,
            )

    def __exit__(self, kind, value, traceback):
        current = context.get()
        if current is None:
            return
        subject, request_id, record = current
        document = {
            "attempt_id": self.id,
            "request_id": request_id,
            "account_id": subject,
            "provider": self.provider,
            "model": self.model,
            "reported_model": self.reported,
            "outcome": (
                "failed" if kind and issubclass(kind, Exception) else self.outcome
            ),
            "input_tokens": self.input,
            "output_tokens": self.output,
            "duration_ms": round((time.monotonic() - self.started) * 1000),
        }
        try:
            record(document)
        except (
            Exception
        ):  # noqa: BLE001 -- telemetry cannot turn a completed provider call into a duplicate retry
            logging.getLogger(__name__).warning("Provider telemetry unavailable")


def measured_call(function, *args, telemetry_provider, telemetry_model=None, **kwargs):
    with Attempt(telemetry_provider, kwargs.get("model") or telemetry_model) as attempt:
        result = function(*args, **kwargs)
        attempt.usage(result)
        attempt.outcome = "completed"
        return result


async def measured_async_call(
    function, *args, telemetry_provider, telemetry_model=None, **kwargs
):
    async with Attempt(
        telemetry_provider, kwargs.get("model") or telemetry_model
    ) as attempt:
        result = await function(*args, **kwargs)
        attempt.usage(result)
        attempt.outcome = "completed"
        return result


class TelemetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not scope["path"].startswith("/api/")
            or scope["path"].startswith("/api/admin/")
        ):
            return await self.app(scope, receive, send)
        application = scope.get("app")
        service = (
            getattr(application.state, "administration", None)
            if application is not None
            else None
        )
        if service is None:
            return await self.app(scope, receive, send)
        from fastapi import HTTPException, Request
        from starlette.concurrency import run_in_threadpool

        from app.auth.supabase_auth import get_current_user

        try:
            user = await run_in_threadpool(get_current_user, Request(scope, receive))
        except HTTPException:
            return await self.app(scope, receive, send)
        token = context.set((str(user.user_id), str(uuid4()), service.record_attempt))
        try:
            return await self.app(scope, receive, send)
        finally:
            context.reset(token)


def measured_http(function, *args, telemetry_provider, telemetry_model, **kwargs):
    with Attempt(telemetry_provider, telemetry_model) as attempt:
        result = function(*args, **kwargs)
        attempt.outcome = "failed" if result.status_code >= 400 else "completed"
        if result.status_code < 400 and context.get() is not None:
            try:
                attempt.usage(result.json())
            except (ValueError, TypeError):
                attempt.outcome = "failed"
        return result


@contextmanager
def owner_scope(subject, record):
    if not subject or record is None:
        yield
        return
    token = context.set((str(subject), str(uuid4()), record))
    try:
        yield
    finally:
        context.reset(token)
