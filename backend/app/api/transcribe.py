import logging
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.services import STTProviderService, STTServiceError

router = APIRouter()
logger = logging.getLogger("transcribe_api")
logging.basicConfig(level=logging.INFO)

stt_provider = STTProviderService()


class TranscribeResponse(BaseModel):
    text: str
    mode: str
    transcription_provider: str
    transcription_model: str
    transcription_ms: float
    upload_ms: float | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    no_speech: bool = False
    reason: str | None = None


@router.get("/config")
def manual_stt_config():
    # Only provider names are public; never expose credentials or the full settings.
    manual = settings.MANUAL_STT_PROVIDER
    return {
        "manual_stt_provider": manual if manual in {"groq", "openai_whisper", "whisper_local", "assemblyai"} else "unsupported",
        "manual_live_stt_provider": "assemblyai_streaming" if (
            settings.MANUAL_LIVE_STT_PROVIDER == "assemblyai_streaming"
            and manual in {"groq", "openai_whisper", "assemblyai"}
        ) else "none",
    }


@router.post("/", response_model=TranscribeResponse)
async def transcribe_audio(request: Request, file: UploadFile = File(...), mode: str = Form("manual")):
    started = time.perf_counter()
    if settings.SUBSCRIPTIONS_ENABLED=='true':
        from app.commercial.subscription_execution import execution_service
        from app.commercial.catalog_store import CatalogStoreError
        from app.commercial.subscription_screen import safe_error
        service,actor=execution_service(request)
        if mode!='manual':
            raise HTTPException(403,detail={'code':'auto_lease_required'})
        try:
            await run_in_threadpool(service.require_unlimited,actor,'audio.transcribe','audio.transcribed')
        except CatalogStoreError as error:raise safe_error(error) from None
    try:
        content = await file.read(25*1024*1024+1)
        if len(content)>25*1024*1024:
            raise HTTPException(413,detail={'code':'audio_input_too_large'})
        result = await run_in_threadpool(
            stt_provider.transcribe_upload,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            mode=mode,
        )
        total_request_ms = round((time.perf_counter() - started) * 1000, 2)
        upload_ms = max(0.0, round(total_request_ms - result.transcription_ms, 2))

        logger.info(
            "Transcribed audio mode=%s provider=%s model=%s fallback_used=%s fallback_reason=%s no_speech=%s upload_ms=%s",
            mode,
            result.transcription_provider,
            result.transcription_model,
            result.fallback_used,
            result.fallback_reason,
            result.no_speech,
            upload_ms,
        )
        return TranscribeResponse(
            text=result.text,
            mode=mode,
            transcription_provider=result.transcription_provider,
            transcription_model=result.transcription_model,
            transcription_ms=result.transcription_ms,
            upload_ms=upload_ms,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
            no_speech=result.no_speech,
            reason=result.reason,
        )
    except STTServiceError as exc:
        logger.warning("Transcription unavailable status=%s", exc.status_code)
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
