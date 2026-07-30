import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings


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


@dataclass
class TranscriptionResult:
    text: str
    transcription_provider: str
    transcription_model: str
    transcription_ms: float
    fallback_used: bool = False
    fallback_reason: str | None = None
    no_speech: bool = False
    reason: str | None = None


class STTServiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        public_message: str | None = None,
        status_code: int = 500,
        fallback_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public_message = public_message or message
        self.status_code = status_code
        self.fallback_reason = fallback_reason


def resolve_upload_suffix(*, filename: str | None, content_type: str | None) -> str:
    filename_suffix = Path(filename or "").suffix.lower()
    if filename_suffix in SUPPORTED_AUDIO_EXTENSIONS:
        return filename_suffix

    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    return SUPPORTED_AUDIO_TYPES.get(normalized_content_type, "")


class STTProviderService:
    def __init__(self) -> None:
        from app.services.assemblyai_stt_service import AssemblyAISTTService
        from app.services.groq_stt_service import GroqSTTService
        from app.services.whisper_stt_service import WhisperSTTService

        self.logger = logging.getLogger("stt_provider")
        self.assemblyai_service = AssemblyAISTTService()
        self.groq_service = GroqSTTService()
        self.whisper_service = WhisperSTTService()

    def transcribe_upload(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        content: bytes,
        mode: str = "manual",
    ) -> TranscriptionResult:
        suffix = resolve_upload_suffix(filename=filename, content_type=content_type)
        if not suffix:
            raise STTServiceError(
                "Invalid audio format.",
                public_message="Invalid audio format. Please upload WAV, MP3, M4A, OGG, or WebM audio.",
                status_code=400,
            )

        if not content:
            raise STTServiceError(
                "The recording is empty.",
                public_message="The recording is empty. Please record a short question and try again.",
                status_code=400,
            )

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp.flush()
                temp_path = tmp.name

            return self._transcribe_path(
                audio_path=temp_path,
                original_filename=filename or f"recording{suffix}",
                mode=mode,
            )
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    self.logger.warning("Could not delete temporary audio file: %s", temp_path)

    def transcribe_file(
        self,
        *,
        audio_path: str,
        original_filename: str,
        mode: str = "manual",
    ) -> TranscriptionResult:
        suffix = Path(original_filename or audio_path).suffix.lower()
        if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
            raise STTServiceError(
                "Invalid audio format.",
                public_message="Invalid audio format. Please upload WAV, MP3, M4A, OGG, or WebM audio.",
                status_code=400,
            )

        if not Path(audio_path).exists():
            raise STTServiceError(
                "Audio file not found.",
                public_message="The recorded audio could not be found. Please try again.",
                status_code=400,
            )

        return self._transcribe_path(
            audio_path=audio_path,
            original_filename=original_filename,
            mode=mode,
        )

    def _transcribe_path(self, *, audio_path: str, original_filename: str, mode: str) -> TranscriptionResult:
        if mode == "manual":
            provider = settings.MANUAL_STT_PROVIDER
        elif mode == "auto_fallback":
            provider = settings.AUTO_STT_FALLBACK_PROVIDER
        else:
            provider = settings.STT_PROVIDER

        if provider == "assemblyai":
            return self._transcribe_with_assemblyai_then_optional_whisper(
                audio_path=audio_path,
                original_filename=original_filename,
            )

        if provider == "groq":
            return self._transcribe_with_groq_then_optional_whisper(
                audio_path=audio_path,
                original_filename=original_filename,
            )

        if provider == "whisper_local":
            return self.whisper_service.transcribe(audio_path=audio_path)

        raise STTServiceError(
            f"Unsupported STT provider '{provider}'.",
            public_message=(
                "Unsupported STT provider. Use STT_PROVIDER=assemblyai, STT_PROVIDER=groq, "
                "STT_PROVIDER=whisper_local, or AUTO_STT_FALLBACK_PROVIDER=whisper_local."
            ),
            status_code=500,
        )

    def _transcribe_with_assemblyai_then_optional_whisper(
        self,
        *,
        audio_path: str,
        original_filename: str,
    ) -> TranscriptionResult:
        try:
            return self.assemblyai_service.transcribe(audio_path=audio_path)
        except STTServiceError as assemblyai_error:
            self.logger.warning("AssemblyAI STT failed: %s", assemblyai_error)
            if settings.STT_FALLBACK_PROVIDER != "whisper_local":
                raise assemblyai_error

            fallback_result = self.whisper_service.transcribe(audio_path=audio_path)
            fallback_result.fallback_used = True
            fallback_result.fallback_reason = assemblyai_error.fallback_reason or "assemblyai_failed"
            self.logger.info(
                "STT fallback activated provider=%s reason=%s model=%s",
                fallback_result.transcription_provider,
                fallback_result.fallback_reason,
                fallback_result.transcription_model,
            )
            return fallback_result

    def _transcribe_with_groq_then_optional_whisper(
        self,
        *,
        audio_path: str,
        original_filename: str,
    ) -> TranscriptionResult:
        try:
            return self.groq_service.transcribe(
                audio_path=audio_path,
                original_filename=original_filename,
            )
        except STTServiceError as groq_error:
            self.logger.warning("Groq STT failed: %s", groq_error)
            if settings.STT_FALLBACK_PROVIDER != "whisper_local":
                raise groq_error

            fallback_result = self.whisper_service.transcribe(audio_path=audio_path)
            fallback_result.fallback_used = True
            fallback_result.fallback_reason = groq_error.fallback_reason or "groq_stt_failed"
            self.logger.info(
                "STT fallback activated provider=%s reason=%s model=%s",
                fallback_result.transcription_provider,
                fallback_result.fallback_reason,
                fallback_result.transcription_model,
            )
            return fallback_result
