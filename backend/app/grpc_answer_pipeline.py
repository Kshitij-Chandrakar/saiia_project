"""Local diagnostic adapter to the production detection and generation pipeline."""
import contextvars
import json
import logging

from starlette.concurrency import run_in_threadpool


_private_pipeline = contextvars.ContextVar("grpc_private_pipeline", default=False)


class _PrivatePipelineLogs(logging.Filter):
    def filter(self, record):
        return not _private_pipeline.get()


def _load_local_profile():
    from app.config import settings
    # Do not import the FastAPI application: that initializes unrelated STT
    # adapters. Read the same local profile file without cloud-resource IDs.
    try:
        if settings.PROFILE_PATH.stat().st_size > 1024 * 1024:
            return {}
        value = json.loads(settings.PROFILE_PATH.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


async def stream_question_answer(transcript):
    # Existing provider error logs may contain upstream content. Suppress records
    # only in this task (and its context-propagating AnyIO workers), never globally.
    token = _private_pipeline.set(True)
    response = None
    try:
        from app.api.question_detect import extract_question_candidate, polish_question_candidate, classifier
        from app.api.generate import GenerateRequest, generate_answer_stream
        handlers = set(logging.getLogger().handlers)
        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                handlers.update(logger.handlers)
        for handler in handlers:
            if not any(isinstance(item, _PrivatePipelineLogs) for item in handler.filters):
                handler.addFilter(_PrivatePipelineLogs())

        extracted = extract_question_candidate(transcript, None)
        candidate = polish_question_candidate(extracted["candidate"] or transcript)
        valid, _, normalized = await run_in_threadpool(classifier.should_process_as_question, candidate)
        if not valid or len(normalized.split()) < 3:
            return
        question = candidate or normalized
        category = await run_in_threadpool(classifier.classify_question, question)
        yield {"type": "question", "text": question, "category": category}
        # No cloud IDs are accepted by the G5 diagnostic protocol. Keep its
        # transport session ID separate from authenticated interview sessions.
        response = await generate_answer_stream(GenerateRequest(
            question=question, category=category, source="audio", profile=await run_in_threadpool(_load_local_profile)))
        async for line in response.body_iterator:
            item = json.loads(line)
            kind = item.get("type")
            if kind == "start":
                yield {"type": "started", "category": category, "provider": item.get("provider", "")}
            elif kind == "delta":
                yield {"type": "delta", "text": item.get("text", ""), "category": category}
            elif kind == "replace":
                yield {"type": "replacement", "text": item.get("answer", ""), "category": category}
            elif kind == "metadata":
                metadata = item.get("metadata") or {}
                yield {"type": "result", "text": metadata.get("answer", ""),
                       "category": category, "provider": metadata.get("provider", "")}
            elif kind == "error":
                raise RuntimeError("Answer generation unavailable.")
            elif kind == "done":
                if item.get("incomplete"):
                    raise RuntimeError("Answer generation incomplete.")
                yield {"type": "completed", "category": category}
    finally:
        try:
            if response is not None:
                await response.body_iterator.aclose()
        finally:
            _private_pipeline.reset(token)
