import logging
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

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


@router.post("/", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...), mode: str = Form("manual")):
    started = time.perf_counter()
    try:
        content = await file.read()
        result = stt_provider.transcribe_upload(
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            mode=mode,
        )
        total_request_ms = round((time.perf_counter() - started) * 1000, 2)
        upload_ms = max(0.0, round(total_request_ms - result.transcription_ms, 2))

        logger.info(
            "Transcribed audio mode=%s provider=%s model=%s fallback_used=%s fallback_reason=%s no_speech=%s upload_ms=%s text='%s...'",
            mode,
            result.transcription_provider,
            result.transcription_model,
            result.fallback_used,
            result.fallback_reason,
            result.no_speech,
            upload_ms,
            result.text[:50],
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
        logger.exception("Transcription error")
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
