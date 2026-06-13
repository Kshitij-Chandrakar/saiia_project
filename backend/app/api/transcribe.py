import logging
import os
import shutil
import tempfile
from pathlib import Path
from subprocess import CalledProcessError, run

from fastapi import APIRouter, File, HTTPException, UploadFile
import numpy as np
from pydantic import BaseModel
import whisper
import whisper.audio as whisper_audio

router = APIRouter()
logger = logging.getLogger("transcribe_api")
logging.basicConfig(level=logging.INFO)

# Load Whisper once at startup for speed.
model = whisper.load_model("tiny.en")

SUPPORTED_AUDIO_TYPES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
}

SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".webm",
    ".ogg",
    ".mp4",
    ".m4a",
    ".aac",
}


class TranscribeResponse(BaseModel):
    text: str


def _resolve_upload_suffix(file: UploadFile) -> str:
    filename_suffix = Path(file.filename or "").suffix.lower()
    if filename_suffix in SUPPORTED_AUDIO_EXTENSIONS:
        return filename_suffix

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    return SUPPORTED_AUDIO_TYPES.get(content_type, "")


def _configure_ffmpeg() -> str | None:
    configured_path = os.getenv("FFMPEG_PATH", "").strip()
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.is_dir():
            for binary_name in ("ffmpeg.exe", "ffmpeg"):
                binary = candidate / binary_name
                if binary.exists():
                    os.environ["PATH"] = f"{binary.parent}{os.pathsep}{os.environ.get('PATH', '')}"
                    return str(binary)
        elif candidate.exists():
            os.environ["PATH"] = f"{candidate.parent}{os.pathsep}{os.environ.get('PATH', '')}"
            return str(candidate)

    return shutil.which("ffmpeg")


def _decode_audio(audio_path: str, ffmpeg_binary: str) -> np.ndarray:
    cmd = [
        ffmpeg_binary,
        "-nostdin",
        "-threads",
        "0",
        "-i",
        audio_path,
        "-f",
        "s16le",
        "-ac",
        "1",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(whisper_audio.SAMPLE_RATE),
        "-",
    ]

    try:
        output = run(cmd, capture_output=True, check=True).stdout
    except CalledProcessError as exc:
        raise RuntimeError(exc.stderr.decode(errors="ignore")) from exc

    return np.frombuffer(output, np.int16).flatten().astype(np.float32) / 32768.0


@router.post("/", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    suffix = _resolve_upload_suffix(file)
    if not suffix:
        raise HTTPException(
            status_code=400,
            detail="Invalid audio format. Please upload WAV, MP3, M4A, OGG, or WebM audio.",
        )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=400,
                detail="The recording is empty. Please record a short question and try again.",
            )

        ffmpeg_binary = _configure_ffmpeg()
        if not ffmpeg_binary:
            raise HTTPException(
                status_code=500,
                detail="Transcription is unavailable because ffmpeg is missing. Install ffmpeg or set FFMPEG_PATH.",
            )

        temp_path = None

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            temp_path = tmp.name

        audio = _decode_audio(temp_path, ffmpeg_binary)
        if audio.size == 0:
            raise HTTPException(
                status_code=400,
                detail="The recording is empty. Please record a short question and try again.",
            )

        result = model.transcribe(audio)
        text = result.get("text", "").strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="I could not clearly detect a question in that recording. Please try again.",
            )

        logger.info("Transcribed audio to: '%s...'", text[:50])
        return TranscribeResponse(text=text)
    except HTTPException:
        raise
    except RuntimeError as exc:
        error_message = str(exc).lower()
        if "ffmpeg" in error_message or "no such file or directory" in error_message:
            logger.exception("ffmpeg error during transcription")
            raise HTTPException(
                status_code=500,
                detail="Transcription failed because ffmpeg is not available. Install ffmpeg or set FFMPEG_PATH.",
            ) from exc
        logger.exception("Audio decode error during transcription")
        if "invalid data found" in error_message or "error opening input" in error_message:
            raise HTTPException(
                status_code=400,
                detail="Invalid audio format. Please record again and upload a supported microphone recording.",
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="Whisper could not process that recording. Please try again with a short, clear microphone recording.",
        ) from exc
    except Exception as exc:
        logger.exception("Transcription error")
        raise HTTPException(
            status_code=500,
            detail="Whisper failed to transcribe the recording. Please try again with a short, clear microphone recording.",
        ) from exc
    finally:
        if "temp_path" in locals() and temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning("Could not delete temporary audio file: %s", temp_path)
