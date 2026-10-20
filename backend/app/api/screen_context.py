"""Additive contextual OCR endpoint; legacy OCR stays unchanged."""
import asyncio
import ipaddress
import logging
import anyio

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from python_multipart.exceptions import MultipartParseError

from app.auth.supabase_auth import get_current_user
from app.cloud.interview_sessions import (
    CloudInterviewSessionService, CloudInterviewSessionError, CloudInterviewSessionNotFoundError,
)
from app.cloud.supabase_config import SupabaseConfigurationError
from app.models.screen_context import (
    MAX_BODY_BYTES, MAX_IMAGE_BYTES, MAX_METADATA_BYTES, ScreenContextRequest, ScreenContextResponse,
)
from app.services.screen_context_service import ScreenContextError, development_diagnostics, diagnostic, validation_fields

router = APIRouter()
# ponytail: two in-flight contextual requests per worker, including upload/decoding;
# measure memory before increasing. No conversation data lives in this gate.
_slots = asyncio.Semaphore(2)


def problem(code, status=422):
    detail = {"code": code}
    if status == 413 or code == "context_field_limit":
        detail["message"] = "Screen context exceeds a size or count limit. Start a new question or reduce the supplied content; nothing was silently discarded."
    return HTTPException(status, detail=detail)


class MemoryMultipartParser(MultiPartParser):
    # Stream is capped below this threshold, so SpooledTemporaryFile never rolls to disk.
    spool_max_size = MAX_BODY_BYTES + 1

    def on_part_begin(self):
        super().on_part_begin()
        self.part_bytes = self.header_bytes = 0

    def on_header_field(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise MultiPartException("header_limit")
        super().on_header_field(data, start, end)

    def on_header_value(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise MultiPartException("header_limit")
        super().on_header_value(data, start, end)

    def on_part_data(self, data, start, end):
        self.part_bytes += end - start
        if self.part_bytes > (MAX_IMAGE_BYTES if self._current_part.file else MAX_METADATA_BYTES):
            raise MultiPartException("part_limit")
        super().on_part_data(data, start, end)

    def on_end(self):
        self.complete = True


async def parse_context(request):
    total = 0

    async def bounded_stream():
        nonlocal total
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise problem("multipart_byte_limit", 413)
            yield chunk

    try:
        if int(request.headers.get("content-length", "0")) > MAX_BODY_BYTES:
            raise problem("multipart_byte_limit", 413)
    except ValueError:
        raise problem("invalid_content_length", 400) from None
    content_type = request.headers.get("content-type", "")
    if len(content_type) > 1024:
        raise problem("multipart_header_limit", 413)
    if not content_type.lower().startswith("multipart/form-data;"):
        raise problem("multipart_required", 415)
    parser = MemoryMultipartParser(request.headers, bounded_stream(), max_files=6, max_fields=1,
                                   max_part_size=MAX_METADATA_BYTES)
    form = None
    try:
        form = await parser.parse()
        if not getattr(parser, "complete", False):
            raise problem("incomplete_multipart", 400)
        pairs = form.multi_items()
        if len({name for name, _ in pairs}) != len(pairs) or not isinstance(form.get("context"), str):
            raise problem("invalid_multipart")
        raw = form["context"]
        if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
            raise problem("context_byte_limit", 413)
        try:
            context = ScreenContextRequest.model_validate_json(raw)
        except ValidationError as exc:
            diagnostic(logging.WARNING, "screen_context validation stage=request code=invalid_context fields=%s", validation_fields(exc))
            # ValidationError includes input values; never return/log it.
            oversized = any(item["type"] in {"string_too_long", "too_long"} for item in exc.errors(include_input=False))
            raise problem("context_field_limit" if oversized else "invalid_context") from None
        files = {}
        for name, item in pairs:
            if name == "context":
                continue
            if not isinstance(item, UploadFile) or item.content_type not in {"image/png", "image/jpeg", "image/webp", "image/bmp"}:
                raise problem("unsupported_image", 415)
            files[name] = await item.read(MAX_IMAGE_BYTES + 1)
        if set(files) != {item.part for item in context.input.images}:
            raise problem("image_parts_mismatch")
        return context, files
    except (MultiPartException, MultipartParseError) as exc:
        code = "multipart_limit" if "limit" in str(exc) or "maximum" in str(exc).lower() else "invalid_multipart"
        raise problem(code, 413 if code == "multipart_limit" else 400) from None
    finally:
        # Starlette only closes parse errors of its own type. Also cover cancellation,
        # disconnect and validation errors; never leave temporary objects retained.
        with anyio.CancelScope(shield=True):
            if form is not None:
                await form.close()
            for file in parser._files_to_close_on_error:
                file.close()


def check_cloud_session(context, user):
    service = None
    try:
        service = CloudInterviewSessionService()
        session = service.get_session(user_id=user.user_id, session_id=context.identity.cloudSessionId,
                                      allow_model_bound=True)
        if session.status != "active" or session.ended_at is not None:
            raise problem("inactive_session", 409)
    except CloudInterviewSessionNotFoundError:
        raise problem("session_not_found", 404) from None
    except (CloudInterviewSessionError, SupabaseConfigurationError):
        raise problem("session_unavailable", 503) from None
    finally:
        close = getattr(getattr(getattr(service, "_client", None), "_session", None), "close", None)
        if close:
            close()


def get_screen_service():
    # Reuse the existing configured direct Screen service, not answer-model routing.
    from app.api.screen_ocr import screen_vision_service
    return screen_vision_service


async def run_until_disconnect(request, awaitable):
    task = asyncio.create_task(awaitable)
    finished = False

    async def disconnected():
        # Starlette's disconnect probe can consume cancellation in its CancelScope.
        # An immediate service outcome must still be able to join this watcher.
        while not finished and not await request.is_disconnected():
            if not finished:
                await asyncio.sleep(0.05)

    watcher = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            raise problem("request_disconnected", 499)
        return await task
    finally:
        finished = True
        task.cancel()
        watcher.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(task, watcher, return_exceptions=True)


@router.post("/analyze-context", response_model=ScreenContextResponse,
             openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
                 "type": "object", "required": ["context", "image_0"], "additionalProperties": False,
                 "properties": {"context": {"type": "string", "description": "ScreenContextRequest contractVersion 1 JSON; see docs/SCREEN_CONTEXT_PHASE2.md"},
                                **{f"image_{i}": {"type": "string", "format": "binary"} for i in range(6)}}}}}}})
async def analyze_context(request: Request):
    # request.client is the ASGI peer, adjusted only by the server's configured
    # trusted-proxy middleware. Never interpret arbitrary forwarded headers here.
    try:
        loopback = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        loopback = False
    if not loopback and "authorization" not in request.headers:
        raise problem("local_loopback_required", 403)
    if _slots.locked():
        raise problem("screen_context_busy", 429)
    await _slots.acquire()
    files = {}
    diagnostic_token = development_diagnostics.set(loopback and request.headers.get("x-saiia-screen-diagnostics") == "1")
    try:
        with anyio.fail_after(45):
            user = await asyncio.to_thread(get_current_user, request) if "authorization" in request.headers else None
            context, files = await parse_context(request)
            if context.identity.cloudSessionId is not None:
                if user is None:
                    raise problem("cloud_auth_required", 401)
                await asyncio.to_thread(check_cloud_session, context, user)
            else:
                if not loopback:
                    raise problem("local_loopback_required", 403)
            return await run_until_disconnect(request, get_screen_service().answer_context(context, files))
    except ScreenContextError as exc:
        diagnostic(logging.WARNING, "screen_context backend stage=request code=%s", exc.code)
        raise problem(exc.code, exc.status) from None
    except TimeoutError:
        diagnostic(logging.WARNING, "screen_context backend stage=request code=request_timeout")
        raise problem("request_timeout", 504) from None
    finally:
        development_diagnostics.reset(diagnostic_token)
        files.clear()
        _slots.release()
