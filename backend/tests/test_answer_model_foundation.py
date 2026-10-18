"""Provider-free checks: every outgoing request uses httpx.MockTransport."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.answer_models import MODELS, MODEL_CATALOG, DEFAULT_MODEL_KEY, model_catalog
from app.answer_generation import (
    AttemptFailure, Deadlines, FeatureDisabled, GenerationBudget, GenerationControl,
    GenerationFailure, GenerationStopped, PreparedAnswer, stream_answer,
)


def config(**overrides):
    values = dict(ENABLE_SESSION_ANSWER_MODELS=True, OPENAI_API_KEY="mock-openai",
                  GROQ_API_KEY="mock-groq", GEMINI_API_KEY="mock-gemini")
    for prefix, limits in (("ANSWER_MODEL_", (6, 4, 25, 8)),
                           ("ANSWER_MODEL_CODING_", (10, 6, 40, 12))):
        values.update({prefix + name + "_SECONDS": value for name, value in zip(
            ("FIRST_TOKEN", "IDLE", "OVERALL", "FALLBACK_RESERVE"), limits)})
    values.update(overrides)
    return SimpleNamespace(**values)


def frame(value):
    return "data: " + (value if isinstance(value, str) else json.dumps(value)) + "\n\n"


def response_events(provider, text="answer", *, complete=True):
    if provider == "openai":
        values = [{"type": "response.reasoning_text.delta", "delta": "PRIVATE"},
                  {"type": "response.output_text.delta", "delta": text}]
        if complete:
            values.append({"type": "response.completed", "response": {"model": "openai-reported", "status": "completed"}})
    elif provider == "groq":
        values = [{"model": "groq-reported", "choices": [{"delta": {"content": text, "reasoning": "PRIVATE"}}]}]
        if complete:
            values.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    else:
        values = [{"modelVersion": "gemini-reported", "candidates": [{
            "content": {"parts": [{"text": "PRIVATE", "thought": True}, {"text": text}]},
            **({"finishReason": "STOP"} if complete else {})}]}]
    return [frame(value) for value in values]


class Wire(httpx.AsyncByteStream):
    def __init__(self, frames):
        self.frames = frames
        self.closed = False

    async def __aiter__(self):
        for item in self.frames:
            if isinstance(item, float):
                await asyncio.sleep(item)
            else:
                # Split bytes as a real transport may, including within UTF-8.
                data = item.encode()
                yield data[:7]
                yield data[7:]

    async def aclose(self):
        self.closed = True


async def collect(key, handler, *, cfg=None, **kwargs):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return [event async for event in stream_answer(
            key, PreparedAnswer("preserve instructions", "question résumé"),
            client=client, config=cfg or config(), **kwargs)]


def test_exact_catalog_and_safe_status():
    assert [(m.display_name, m.provider, m.api_model) for m in MODELS] == [
        ("GPT-5.6 Luna", "openai", "gpt-5.6-luna"),
        ("GPT-5.6 Terra", "openai", "gpt-5.6-terra"),
        ("GPT-OSS 120B", "groq", "openai/gpt-oss-120b"),
        ("Gemini 3.5 Flash-Lite", "gemini", "gemini-3.5-flash-lite"),
        ("Gemini 3.6 Flash", "gemini", "gemini-3.6-flash"),
    ]
    cfg = config()
    cfg.GEMINI_API_KEY = ""
    safe = model_catalog(cfg)
    assert [m["key"] for m in safe if m["default"]] == [DEFAULT_MODEL_KEY]
    assert all(m["selectable"] and m["live_access"] == "not_verified" for m in safe)
    assert not safe[3]["credentials_configured"]
    assert "mock-" not in json.dumps(safe) and "https:" not in json.dumps(safe)
    with pytest.raises(TypeError):
        MODEL_CATALOG["arbitrary"] = MODELS[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.key)
async def test_all_request_profiles_streams_and_reported_versions(model):
    calls = []
    wire = Wire(response_events(model.provider, "héllo"))

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert "temperature" not in body and "top_p" not in body
        if model.provider == "openai":
            assert str(request.url) == "https://api.openai.com/v1/responses"
            assert body == dict(model=model.api_model, instructions="preserve instructions",
                                input="question résumé", reasoning={"effort": "low"},
                                max_output_tokens=2500, stream=True, store=False)
        elif model.provider == "groq":
            assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
            assert body["model"] == model.api_model and body["stream"]
            assert body["max_completion_tokens"] == 2500
            assert body["include_reasoning"] is False and "reasoning_format" not in body
            assert body["reasoning_effort"] in model.supported_efforts
            assert body["messages"][-1]["content"] == "question résumé"
        else:
            assert request.url.host == "generativelanguage.googleapis.com"
            assert model.api_model in request.url.path
            assert request.headers["x-goog-api-key"] == "mock-gemini"
            assert body["generationConfig"] == {"maxOutputTokens": 2500,
                "thinkingConfig": {"thinkingLevel": model.effort}}
            assert body["contents"][-1] == {"role": "user", "parts": [{"text": "question résumé"}]}
            assert "candidateCount" not in body["generationConfig"]
        return httpx.Response(200, stream=wire)

    events = await collect(model.key, handler)
    result = events[-1]["result"]
    assert len(calls) == 1 and result["answer"] == "héllo" and wire.closed
    assert result["actual_api_model"] == model.api_model
    assert result["selected_model_key"] == model.key
    assert result["reported_model"] == model.provider + "-reported"
    assert result["fallback_used"] is False and "PRIVATE" not in str(events)


@pytest.mark.asyncio
async def test_missing_gemini_credentials_immediate_fallback_preserves_selection():
    calls = []
    cfg = config()
    cfg.GEMINI_API_KEY = ""

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.groq.com"
        return httpx.Response(200, stream=Wire(response_events("groq")))

    events = await collect(DEFAULT_MODEL_KEY, handler, cfg=cfg)
    result = events[-1]["result"]
    assert len(calls) == 1
    assert result["selected_api_model"] == DEFAULT_MODEL_KEY
    assert result["actual_api_model"] == "openai/gpt-oss-120b"
    assert result["failure_codes"] == ("missing_credentials",)
    assert [e["type"] for e in events] == ["discard", "replace", "result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
async def test_provider_failure_falls_back_exactly_once(status):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, text="PRIVATE upstream error")
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "preserve instructions"
        assert body["messages"][1]["content"] == "question résumé"
        return httpx.Response(200, stream=Wire(response_events("groq")))

    events = await collect("gpt-5.6-luna", handler)
    assert len(calls) == 2 and events[-1]["result"]["fallback_used"]
    assert "PRIVATE" not in str(events)


@pytest.mark.asyncio
@pytest.mark.parametrize("key,count", [("gpt-5.6-luna", 2), ("gpt-oss-120b", 1)])
async def test_terminal_failure_no_self_fallback(key, count):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(GenerationFailure, match="^Unable to generate an answer$") as failure:
        await collect(key, handler)
    assert len(calls) == count and len(failure.value.codes) == count


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", [response_events("openai", complete=False),
    response_events("openai", ""), [frame("not-json")],
    [frame({"type": "response.incomplete"})], [frame({"type": "response.refusal.delta"})]])
async def test_invalid_or_partial_primary_is_discarded_not_concatenated(primary):
    wires = []

    def handler(request):
        wire = Wire(primary if not wires else response_events("groq", "replacement"))
        wires.append(wire)
        return httpx.Response(200, stream=wire)

    events = await collect("gpt-5.6-terra", handler)
    assert len(wires) == 2 and all(w.closed for w in wires)
    assert events[-1]["result"]["answer"] == "replacement"
    assert next(e for e in events if e["type"] == "replace")["answer"] == "replacement"
    assert all(e["attempt"] == "primary" for e in events if e["type"] == "delta")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["first", "idle", "reserve"])
async def test_deadline_closes_primary_and_falls_back(mode):
    limits = Deadlines(.03, .03, .30, .06)
    now = [0.0]
    budget = GenerationBudget(limits, clock=lambda: now[0])
    wires = []
    prefix = response_events("openai", "partial", complete=False)[-1:]
    frames = {
        "first": [0.08],
        "idle": prefix + [0.08],
        "reserve": [frame({"type": "response.output_text.delta", "delta": "more"})] * 14,
    }[mode]

    class ReserveWire(Wire):
        async def __aiter__(self):
            for i, item in enumerate(self.frames):
                if mode == "reserve":
                    now[0] = .02 * i
                if isinstance(item, float):
                    await asyncio.sleep(item)
                else:
                    yield item.encode()

    def handler(request):
        wire = ReserveWire(frames) if not wires else Wire(response_events("groq"))
        wires.append(wire)
        return httpx.Response(200, stream=wire)

    events = await collect("gpt-5.6-luna", handler, budget=budget)
    expected = {"first": "first_token_timeout", "idle": "idle_timeout", "reserve": "fallback_reserve"}[mode]
    assert events[-1]["result"]["failure_codes"] == (expected,)
    assert len(wires) == 2 and all(w.closed for w in wires)


@pytest.mark.asyncio
async def test_overall_budget_is_not_reset_for_fallback():
    now = [0.0]
    budget = GenerationBudget(Deadlines(1, 1, 3, 1), clock=lambda: now[0])
    calls = []

    def handler(request):
        calls.append(request)
        now[0] = 3
        return httpx.Response(503)

    with pytest.raises(GenerationFailure) as failure:
        await collect("gpt-5.6-luna", handler, budget=budget)
    assert len(calls) == 1 and "overall_timeout" in failure.value.codes
    assert budget.started == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_cancel_during_read_closes_stream_without_fallback(external):
    entered = asyncio.Event()
    control = GenerationControl()
    wires = []

    def handler(request):
        wire = Wire([5.0])
        wires.append(wire)
        entered.set()
        return httpx.Response(200, stream=wire)

    task = asyncio.create_task(collect("gpt-5.6-luna", handler, control=control))
    await asyncio.wait_for(entered.wait(), 1)
    if external:
        task.cancel()
    else:
        control.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(wires) == 1 and wires[0].closed


@pytest.mark.asyncio
async def test_stop_after_primary_failure_prevents_fallback():
    control = GenerationControl()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stream = stream_answer("gpt-5.6-luna", PreparedAnswer("instructions", "question"),
                               client=client, control=control, config=config())
        assert (await stream.__anext__())["type"] == "discard"
        control.cancel()  # logout/supersession/auth failure/session termination
        with pytest.raises(GenerationStopped):
            await stream.__anext__()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_concurrent_models_keep_request_state_separate():
    async def handler(request):
        body = json.loads(request.content)
        await asyncio.sleep(.001)
        return httpx.Response(200, stream=Wire(response_events("openai", body["model"])))

    left, right = await asyncio.gather(collect("gpt-5.6-luna", handler), collect("gpt-5.6-terra", handler))
    assert left[-1]["result"]["answer"] == "gpt-5.6-luna"
    assert right[-1]["result"]["answer"] == "gpt-5.6-terra"


@pytest.mark.asyncio
async def test_disabled_and_invalid_selection_never_dispatch():
    def handler(request):
        pytest.fail("No network allowed")

    cfg = config()
    cfg.ENABLE_SESSION_ANSWER_MODELS = False
    with pytest.raises(FeatureDisabled):
        await collect(DEFAULT_MODEL_KEY, handler, cfg=cfg)
    with pytest.raises(KeyError):
        await collect("https://arbitrary-provider", handler)


def test_runtime_has_no_foundation_imports_and_flag_defaults_off():
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    # Phase 3 integrates the foundation, but still requires the disabled default.
    result = subprocess.run([sys.executable, "-c",
        "import os, dotenv; os.environ.pop('ENABLE_SESSION_ANSWER_MODELS', None); "
        "dotenv.load_dotenv=lambda:None; from app.config import settings; "
        "print(settings.ENABLE_SESSION_ANSWER_MODELS)"], cwd=root, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_deadline_validation_and_config_profiles():
    with pytest.raises(ValueError):
        Deadlines(first_token=6, fallback_reserve=5)
    with pytest.raises(ValueError):
        Deadlines(idle=float("nan"))
    from app.config import settings
    assert Deadlines.from_config(settings).overall > 0
    assert Deadlines.from_config(settings, coding=True).overall > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["heartbeat", "reasoning", "whitespace"])
async def test_non_answer_activity_does_not_extend_first_token_deadline(kind):
    now = [0.0]
    budget = GenerationBudget(Deadlines(1, 1, 5, 2), clock=lambda: now[0])
    calls = []
    activity = {"heartbeat": ": ping\n\n",
                "reasoning": frame({"type": "response.reasoning_text.delta", "delta": "private"}),
                "whitespace": frame({"type": "response.output_text.delta", "delta": " "})}[kind]

    class ActiveWire(Wire):
        async def __aiter__(self):
            yield activity.encode()
            now[0] = 1
            yield frame({"type": "response.output_text.delta", "delta": "too late"}).encode()

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=ActiveWire([]) if len(calls) == 1
                              else Wire(response_events("groq")))

    events = await collect("gpt-5.6-luna", handler, budget=budget)
    assert events[-1]["result"]["failure_codes"] == ("first_token_timeout",)


@pytest.mark.asyncio
async def test_fallback_has_only_remaining_overall_time_and_can_be_cancelled():
    control = GenerationControl()
    entered = asyncio.Event()
    wires = []

    def handler(request):
        wire = Wire([5.0])
        wires.append(wire)
        if len(wires) == 1:
            return httpx.Response(503)
        entered.set()
        return httpx.Response(200, stream=wire)

    task = asyncio.create_task(collect("gpt-5.6-luna", handler, control=control))
    await asyncio.wait_for(entered.wait(), 1)
    control.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(wires) == 2 and wires[-1].closed


@pytest.mark.asyncio
async def test_existing_budget_covers_later_correction_without_reset():
    now = [0.0]
    budget = GenerationBudget(Deadlines(1, 1, 5, 2), clock=lambda: now[0])

    async def correction():
        now[0] = 5
        return "corrected"

    now[0] = 4
    with pytest.raises(AttemptFailure, match="overall_timeout"):
        await budget.wait(correction(), GenerationControl(), until=budget.expires, code="overall_timeout")
    assert budget.started == 0


@pytest.mark.asyncio
async def test_overall_deadline_interrupts_active_fallback():
    now = [0.0]
    budget = GenerationBudget(Deadlines(1, 1, 3, 1), clock=lambda: now[0])
    calls = []
    wire = Wire(response_events("groq"))

    def handler(request):
        calls.append(request)
        now[0] = 1.5 if len(calls) == 1 else 3
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, stream=wire)

    with pytest.raises(GenerationFailure) as failure:
        await collect("gpt-5.6-luna", handler, budget=budget)
    assert len(calls) == 2 and wire.closed
    assert failure.value.codes[-1] == "overall_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["groq", "gemini"])
async def test_non_success_finish_never_commits(provider):
    key = "gpt-oss-120b" if provider == "groq" else DEFAULT_MODEL_KEY
    calls = []

    def handler(request):
        calls.append(request)
        item = {"choices": [{"delta": {"content": "partial"}, "finish_reason": "length"}]} if provider == "groq" else {
            "candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": "MAX_TOKENS"}]}
        return httpx.Response(200, stream=Wire([frame(item)])) if len(calls) == 1 else httpx.Response(503)

    with pytest.raises(GenerationFailure) as failure:
        await collect(key, handler)
    assert failure.value.codes[0] == "invalid_response"


@pytest.mark.asyncio
async def test_network_failure_is_safe_and_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("PRIVATE prompt secret", request=request)

    with pytest.raises(GenerationFailure) as failure:
        await collect("gpt-5.6-luna", handler)
    assert len(calls) == 2 and failure.value.codes == ("provider_unavailable",) * 2
    assert "PRIVATE" not in str(failure.value)


@pytest.mark.asyncio
async def test_already_stopped_request_never_opens_provider():
    control = GenerationControl()
    control.cancel()
    with pytest.raises(GenerationStopped):
        await collect(DEFAULT_MODEL_KEY, lambda request: pytest.fail("unexpected dispatch"), control=control)
