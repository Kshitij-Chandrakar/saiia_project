"""Opt-in local backend trace launcher; normal app startup is unaffected.

Run with --serve --output tmp/manual-chat-backend.jsonl. Use an already
authenticated desktop session. No login/session/resume is created by this tool.
Only /generate/ is traced; this is not renderer paint instrumentation.
"""
import argparse
from contextvars import ContextVar
from functools import wraps
import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
trace = ContextVar("manual_chat_audit", default=None)


def mark(stage, **safe):
    current = trace.get()
    if current is not None:
        current["events"].append({"stage": stage, "at_ms": round((time.perf_counter()-current["start"])*1000, 3), **safe})


def instrument(owner, name):
    original = getattr(owner, name)

    @wraps(original)
    def timed(*args, **kwargs):
        mark(name + ".start")
        try:
            return original(*args, **kwargs)
        finally:
            mark(name + ".end")
    setattr(owner, name, timed)


def build_app(output):
    from app.main import app
    from app.api import generate as api
    from app.cloud.cloud_resume import SupabaseCloudResumeClient
    from app.cloud.interview_transcripts import SupabaseInterviewTranscriptClient
    from app.cloud.interview_sessions import SupabaseInterviewSessionClient
    from app.nlp.answer_generator import AnswerGenerator

    for name in ("_authorize_generation_session", "get_current_user", "_resolve_request_followup",
                 "_compile_request_followup_intent", "_generation_job_context", "_retrieve_resume_context",
                 "_generation_profile", "_store_transcript_for_response", "_queue_parallel_refinement"):
        instrument(api, name)
    for name in ("generate_answer", "_build_prompt", "_generate_with_openai", "_clean_answer",
                 "_semantic_validate_with_openai", "_semantic_correction_with_openai", "_apply_controlled_variation"):
        instrument(AnswerGenerator, name)
    for owner, names in ((SupabaseCloudResumeClient, ("get_resume", "get_active_resume_chunks")),
                         (SupabaseInterviewSessionClient, ("get_session",)),
                         (SupabaseInterviewTranscriptClient, ("create_transcript_entry",))):
        for name in names:
            instrument(owner, name)

    provider = api.generator.openai_provider
    original_generate = provider.generate

    def provider_generate(**kwargs):
        current = trace.get()
        if current is None:
            return original_generate(**kwargs)
        current["call_id"] += 1
        current["attempt"] = 0
        mark("provider_call.start", call_id=current["call_id"], phase=kwargs.get("phase"),
             model=provider.model, input_characters=len(kwargs.get("input_text", "")),
             max_output_tokens=kwargs.get("max_output_tokens"), reasoning_effort=kwargs.get("reasoning_effort"))
        try:
            return original_generate(**kwargs)
        finally:
            mark("provider_call.end", call_id=current["call_id"])
    provider.generate = provider_generate
    if provider.client:
        def dispatched(request):
            current = trace.get()
            if current is not None:
                current["attempt"] += 1
                mark("provider_http.dispatch", call_id=current["call_id"], attempt=current["attempt"])

        def headers(response):
            current = trace.get()
            if current is not None:
                mark("provider_http.headers", call_id=current["call_id"], attempt=current["attempt"], status=response.status_code)
        provider.client._client.event_hooks["request"].append(dispatched)
        provider.client._client.event_hooks["response"].append(headers)

    for route in app.routes:
        if getattr(route, "path", None) == "/generate/":
            original_endpoint = route.dependant.call

            @wraps(original_endpoint)
            async def endpoint(req, request=None):
                current = trace.get()
                request_id = str(req.request_id or "")
                if current is not None and re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", request_id):
                    current["request_id"] = request_id
                mark("endpoint.entry")
                try:
                    return await original_endpoint(req=req, request=request)
                finally:
                    mark("endpoint.exit")
            route.dependant.call = endpoint

    class AuditASGI:
        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or scope.get("path") != "/generate/":
                return await app(scope, receive, send)
            current = {"request_id": "audit-" + uuid.uuid4().hex, "start": time.perf_counter(),
                       "call_id": 0, "attempt": 0, "events": []}
            token = trace.set(current)
            mark("backend.request_entry")

            async def observed_send(message):
                if message["type"] == "http.response.start":
                    mark("backend.response_ready", status=message["status"])
                if message["type"] == "http.response.body":
                    mark("backend.response_body", bytes=len(message.get("body", b"")), final=not message.get("more_body", False))
                await send(message)
            try:
                await app(scope, receive, observed_send)
            finally:
                mark("backend.request_end")
                trace.reset(token)
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("a", encoding="utf-8") as target:
                    target.write(json.dumps({k: v for k, v in current.items() if k != "start"}) + "\n")
    return AuditASGI()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(build_app(args.output), host="127.0.0.1", port=args.port)
