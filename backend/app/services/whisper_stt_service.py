import logging
import os
import shutil
import time
from pathlib import Path
from subprocess import CalledProcessError, run

import numpy as np
import whisper
import whisper.audio as whisper_audio

from app.config import settings
from app.services.stt_provider import STTServiceError, TranscriptionResult


class WhisperSTTService:
    _model = None
    _model_name = None

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.model_name = settings.WHISPER_MODEL

    def _get_model(self):
        if self.__class__._model is None or self.__class__._model_name != self.model_name:
            self.__class__._model = whisper.load_model(self.model_name)
            self.__class__._model_name = self.model_name
        return self.__class__._model

    def _configure_ffmpeg(self) -> str:
        configured_path = settings.FFMPEG_PATH.strip()
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

        ffmpeg_binary = shutil.which("ffmpeg")
        if not ffmpeg_binary:
            raise STTServiceError(
                "ffmpeg is missing.",
                public_message="Transcription is unavailable because ffmpeg is missing. Install ffmpeg or set FFMPEG_PATH.",
                status_code=500,
                fallback_reason="whisper_ffmpeg_missing",
            )

        return ffmpeg_binary

    def _decode_audio(self, *, audio_path: str, ffmpeg_binary: str) -> np.ndarray:
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
            error_message = exc.stderr.decode(errors="ignore")
            lowered = error_message.lower()
            if "invalid data found" in lowered or "error opening input" in lowered:
                raise STTServiceError(
                    "Invalid audio format.",
                    public_message=(
                        "Invalid audio format. Please record again and upload a supported microphone recording."
                    ),
                    status_code=400,
                    fallback_reason="whisper_invalid_audio_format",
                ) from exc
            raise STTServiceError(
                "Whisper audio decode failed.",
                public_message=(
                    "Whisper could not process that recording. Please try again with a short, clear microphone recording."
                ),
                status_code=500,
                fallback_reason="whisper_decode_failed",
            ) from exc

        return np.frombuffer(output, np.int16).flatten().astype(np.float32) / 32768.0

    def transcribe(self, *, audio_path: str) -> TranscriptionResult:
        started = time.perf_counter()
        ffmpeg_binary = self._configure_ffmpeg()
        audio = self._decode_audio(audio_path=audio_path, ffmpeg_binary=ffmpeg_binary)

        if audio.size == 0:
            raise STTServiceError(
                "The recording is empty.",
                public_message="The recording is empty. Please record a short question and try again.",
                status_code=400,
                fallback_reason="whisper_empty_audio",
            )

        result = self._get_model().transcribe(audio)
        text = result.get("text", "").strip()
        if not text:
            transcription_ms = round((time.perf_counter() - started) * 1000, 2)
            return TranscriptionResult(
                text="",
                transcription_provider="whisper_local",
                transcription_model=self.model_name,
                transcription_ms=transcription_ms,
                no_speech=True,
                reason="silence_or_no_speech",
            )

        transcription_ms = round((time.perf_counter() - started) * 1000, 2)
        return TranscriptionResult(
            text=text,
            transcription_provider="whisper_local",
            transcription_model=self.model_name,
            transcription_ms=transcription_ms,
        )
