"""Local diagnostic adapter to the production detection and generation pipeline."""
import asyncio
import contextvars
import json
import logging
import re

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


def _install_private_log_filter():
    handlers = set(logging.getLogger().handlers)
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    for handler in handlers:
        if not any(isinstance(item, _PrivatePipelineLogs) for item in handler.filters):
            handler.addFilter(_PrivatePipelineLogs())


def looks_like_interview_question(text):
    return bool(re.match(r"^(?:explain|what is|difference between|tell me about|can you explain|define|how does|why|write code for|solve|debug)\s+\S", str(text).strip(), re.I))


async def detect_intake_question(text, allow_topics=False):
    token = _private_pipeline.set(True)
    try:
        from app.api.question_detect import extract_question_candidate, polish_question_candidate, classifier
        _install_private_log_filter()
        extracted = extract_question_candidate(text, None)
        candidate = polish_question_candidate(extracted["candidate"] or text)
        valid, detector_reason, normalized = await run_in_threadpool(classifier.should_process_as_question, candidate)
        question = candidate or normalized
        if len(question.split()) < 2:
            return None, "too_short"
        if not valid and detector_reason in ('low_confidence', 'low confidence'):
            return None, 'low_confidence'
        if not valid and not looks_like_interview_question(question):
            if allow_topics:
                from app.grpc_utterance_buffer import topic_question
                topic = topic_question(text)
                if topic: return topic, 'topic_prompt_accepted'
            return None, "not_question"
        return question, ""
    finally:
        _private_pipeline.reset(token)


async def stream_question_answer(transcript, cloud_context=None):
    # Existing provider error logs may contain upstream content. Suppress records
    # only in this task (and its context-propagating AnyIO workers), never globally.
    token = _private_pipeline.set(True)
    response = None
    try:
        from app.api.question_detect import extract_question_candidate, polish_question_candidate, classifier
        from app.api.generate import GenerateRequest, generate_answer_stream

        question, rejection = await detect_intake_question(transcript)
        if rejection:
            yield {"type": "rejected", "reason": rejection}
            return
        category = await run_in_threadpool(classifier.classify_question, question)
        yield {"type": "question", "text": question, "category": category}
        # Cloud IDs are server-authorized; the transport ID never authorizes a session.
        if cloud_context:
            fields = await asyncio.wait_for(run_in_threadpool(cloud_context.load), timeout=15)
        else:
            fields = {"profile": await run_in_threadpool(_load_local_profile)}
        response = await generate_answer_stream(GenerateRequest(
            question=question, category=category, source="auto" if cloud_context else "audio", **fields),
            **({"request": cloud_context.request} if cloud_context else {}))
        answer = ""
        model = provider = "unknown"
        completed = False
        async for line in response.body_iterator:
            item = json.loads(line)
            kind = item.get("type")
            if kind == "start":
                yield {"type": "started", "category": category, "provider": item.get("provider", "")}
            elif kind == "delta":
                answer += str(item.get("text") or "")
                yield {"type": "delta", "text": item.get("text", ""), "category": category}
            elif kind == "replace":
                answer = str(item.get("answer") or "")
                yield {"type": "replacement", "text": item.get("answer", ""), "category": category}
            elif kind == "metadata":
                metadata = item.get("metadata") or {}
                answer = metadata.get("answer") or answer
                model = metadata.get("model") or model
                provider = metadata.get("provider") or provider
                yield {"type": "result", "text": metadata.get("answer", ""),
                       "category": category, "provider": metadata.get("provider", "")}
            elif kind == "error":
                raise RuntimeError("Answer generation unavailable.")
            elif kind == "done":
                if completed:
                    continue
                if item.get("incomplete"):
                    raise RuntimeError("Answer generation incomplete.")
                completed = True
                if not answer.strip():
                    raise RuntimeError("Answer generation empty.")
                if cloud_context:
                    yield {"type": "save_status", "code": "answer_save_pending"}
                    try:
                        await asyncio.wait_for(run_in_threadpool(cloud_context.save, question, answer, category, provider, model), timeout=20)
                        yield {"type": "save_status", "code": "answer_saved"}
                    except Exception:
                        yield {"type": "save_status", "code": "answer_save_failed"}
                yield {"type": "completed", "category": category}
    finally:
        try:
            if response is not None:
                await response.body_iterator.aclose()
        finally:
            _private_pipeline.reset(token)
