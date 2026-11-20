"""Only safe measured fields cross the provider boundary."""

import asyncio
from types import SimpleNamespace

from app.admin_telemetry import (
    Attempt,
    context,
    measured_async_call,
    measured_call,
    measured_http,
)


def test_attempts_are_content_free_and_count_real_calls():
    rows = []
    token = context.set(("synthetic-subject", "synthetic-request", rows.append))
    try:

        def provider(**kwargs):
            return SimpleNamespace(
                model="executed-v1",
                usage=SimpleNamespace(input_tokens=3, output_tokens=4),
                text="private response",
            )

        measured_call(
            provider,
            telemetry_provider="openai",
            model="requested",
            input="private prompt",
        )
        try:
            with Attempt("groq", "failed"):
                raise ValueError("private error")
        except ValueError:
            pass
        with Attempt("openai", "aborted"):
            pass
        assert [row["outcome"] for row in rows] == ["completed", "failed", "aborted"]
        assert (
            rows[0]["input_tokens"] == 3 and rows[0]["reported_model"] == "executed-v1"
        )
        assert "private" not in str(rows)
    finally:
        context.reset(token)


def test_missing_usage_is_not_zero_and_bad_usage_rejected():
    rows = []
    token = context.set(("subject", "request", rows.append))
    try:
        with Attempt("openai", "model") as attempt:
            attempt.usage({"usage": {"input_tokens": True, "output_tokens": -1}})
            attempt.outcome = "completed"
        assert rows[0]["input_tokens"] is None and rows[0]["output_tokens"] is None
    finally:
        context.reset(token)


def test_async_call_and_sink_failure_do_not_repeat_provider():
    calls = []

    async def provider(**kwargs):
        calls.append(1)
        return {"usage": {}}

    def unavailable(document):
        raise OSError("private connection")

    token = context.set(("subject", "request", unavailable))
    try:
        asyncio.run(
            measured_async_call(provider, telemetry_provider="openai", model="model")
        )
    finally:
        context.reset(token)
    assert len(calls) == 1


def test_http_failure_records_attempt_without_changing_response():
    response = SimpleNamespace(status_code=429)
    rows = []
    token = context.set(("subject", "request", rows.append))
    try:
        assert (
            measured_http(
                lambda **kwargs: response,
                telemetry_provider="Groq refinement",
                telemetry_model="model",
                url="http://synthetic.invalid",
            )
            is response
        )
    finally:
        context.reset(token)
    assert rows[0]["provider"] == "groq" and rows[0]["outcome"] == "failed"
