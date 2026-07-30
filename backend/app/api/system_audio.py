import asyncio
import logging
import os
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import STTProviderService, STTServiceError
from app.services.system_audio_capture import (
    SystemAudioCaptureError,
    SystemAudioCaptureService,
)


router = APIRouter()
logger = logging.getLogger("system_audio_api")

system_audio_service = SystemAudioCaptureService()
stt_provider = STTProviderService()


class SystemAudioDeviceResponse(BaseModel):
    device_index: int
    name: str
    channels: int
    sample_rate: int
    is_loopback: bool
    is_default: bool = False


class SystemAudioDevicesEnvelope(BaseModel):
    ok: bool
    supported: bool
    devices: list[SystemAudioDeviceResponse]
    default_device_name: str | None = None
    default_device_index: int | None = None


class SystemAudioStartRequest(BaseModel):
    device_index: int | None = None


class SystemAudioStartResponse(BaseModel):
    ok: bool
    recording_id: str
    device_name: str
    sample_rate: int
    channels: int
    status: str


class SystemAudioStopRequest(BaseModel):
    recording_id: str | None = None


class SystemAudioStopResponse(BaseModel):
    ok: bool
    recording_id: str
    transcript: str
    recording_ms: float
    transcription_ms: float
    provider: str
    transcription_model: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    no_speech: bool = False
    reason: str | None = None
    audio_source: str = "system"
    device_name: str
    status: str


class SystemAudioCaptureChunkRequest(BaseModel):
    duration_ms: int = 5000
    device_index: int | None = None


class SystemAudioCaptureChunkResponse(BaseModel):
    ok: bool
    transcript: str
    no_speech: bool = False
    reason: str | None = None
    recording_ms: float
    transcription_ms: float
    audio_source: str = "system"
    provider: str
    transcription_model: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    device_name: str
    status: str


class SystemAudioDebugRecordRequest(BaseModel):
    duration_ms: int = 10000
    device_index: int | None = None


class SystemAudioDebugRecordResponse(BaseModel):
    ok: bool
    file_path: str | None = None
    device_name: str
    input_sample_rate: int
    target_sample_rate: int
    channels: int
    duration_ms: float
    bytes_captured: int
    rms_level: float
    peak_level: float
    clipping_detected: bool
    effective_gain: float


@router.get("/devices", response_model=SystemAudioDevicesEnvelope)
async def get_system_audio_devices():
    try:
        devices = system_audio_service.list_wasapi_loopback_devices()
        default_name = devices[0]["name"] if devices else None
        default_index = devices[0]["device_index"] if devices else None
        return SystemAudioDevicesEnvelope(
            ok=True,
            supported=system_audio_service.is_supported(),
            devices=[SystemAudioDeviceResponse(**device) for device in devices],
            default_device_name=default_name,
            default_device_index=default_index,
        )
    except SystemAudioCaptureError as exc:
        if "PyAudioWPatch" in exc.public_message or "supported on Windows" in exc.public_message:
            return SystemAudioDevicesEnvelope(
                ok=False,
                supported=False,
                devices=[],
                default_device_name=None,
                default_device_index=None,
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.post("/start", response_model=SystemAudioStartResponse)
async def start_system_audio_recording(payload: SystemAudioStartRequest):
    try:
        result = system_audio_service.start_recording(device_index=payload.device_index)
        logger.info(
            "System audio recording started recording_id=%s device=%s sample_rate=%s channels=%s",
            result["recording_id"],
            result["device_name"],
            result["sample_rate"],
            result["channels"],
        )
        return SystemAudioStartResponse(**result)
    except SystemAudioCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.post("/stop", response_model=SystemAudioStopResponse)
async def stop_system_audio_recording(payload: SystemAudioStopRequest):
    audio_path = None
    try:
        stop_result = system_audio_service.stop_recording(recording_id=payload.recording_id)
        audio_path = stop_result["audio_path"]
        transcription_started = time.perf_counter()
        transcription_result = stt_provider.transcribe_file(
            audio_path=audio_path,
            original_filename="system-loopback.wav",
            mode="manual",
        )
        transcription_ms = transcription_result.transcription_ms or round(
            (time.perf_counter() - transcription_started) * 1000,
            2,
        )
        logger.info(
            "System audio recording stopped recording_id=%s device=%s provider=%s no_speech=%s",
            stop_result["recording_id"],
            stop_result["device_name"],
            transcription_result.transcription_provider,
            transcription_result.no_speech,
        )
        return SystemAudioStopResponse(
            ok=True,
            recording_id=stop_result["recording_id"],
            transcript=transcription_result.text,
            recording_ms=stop_result["recording_ms"],
            transcription_ms=transcription_ms,
            provider=transcription_result.transcription_provider,
            transcription_model=transcription_result.transcription_model,
            fallback_used=transcription_result.fallback_used,
            fallback_reason=transcription_result.fallback_reason,
            no_speech=transcription_result.no_speech,
            reason=transcription_result.reason,
            audio_source="system",
            device_name=stop_result["device_name"],
            status="recorded",
        )
    except SystemAudioCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    except STTServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except OSError:
                logger.warning("Could not remove temporary system audio file: %s", audio_path)


@router.post("/capture-chunk", response_model=SystemAudioCaptureChunkResponse)
async def capture_system_audio_chunk(payload: SystemAudioCaptureChunkRequest):
    audio_path = None
    try:
        duration_ms = max(1000, min(10000, int(payload.duration_ms or 5000)))
        start_result = system_audio_service.start_recording(device_index=payload.device_index)
        await asyncio.sleep(duration_ms / 1000)
        stop_result = system_audio_service.stop_recording(recording_id=start_result["recording_id"])
        audio_path = stop_result["audio_path"]
        transcription_result = stt_provider.transcribe_file(
            audio_path=audio_path,
            original_filename="system-loopback.wav",
            mode="manual",
        )
        return SystemAudioCaptureChunkResponse(
            ok=True,
            transcript=transcription_result.text,
            no_speech=transcription_result.no_speech or not str(transcription_result.text or "").strip(),
            reason=transcription_result.reason,
            recording_ms=stop_result["recording_ms"],
            transcription_ms=transcription_result.transcription_ms,
            audio_source="system",
            provider=transcription_result.transcription_provider,
            transcription_model=transcription_result.transcription_model,
            fallback_used=transcription_result.fallback_used,
            fallback_reason=transcription_result.fallback_reason,
            device_name=stop_result["device_name"],
            status="recorded",
        )
    except SystemAudioCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    except STTServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except OSError:
                logger.warning("Could not remove temporary system audio file: %s", audio_path)


@router.post("/debug-record", response_model=SystemAudioDebugRecordResponse)
async def debug_record_system_audio(payload: SystemAudioDebugRecordRequest):
    try:
        result = await asyncio.to_thread(
            system_audio_service.capture_debug_processed_audio,
            duration_ms=max(1000, min(15000, int(payload.duration_ms or 10000))),
            device_index=payload.device_index,
        )
        logger.info(
            "System audio debug capture complete device=%s rms=%s peak=%s bytes=%s gain=%s clipping=%s",
            result["device_name"],
            result["rms_level"],
            result["peak_level"],
            result["bytes_captured"],
            result["effective_gain"],
            result["clipping_detected"],
        )
        return SystemAudioDebugRecordResponse(ok=True, **result)
    except SystemAudioCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
