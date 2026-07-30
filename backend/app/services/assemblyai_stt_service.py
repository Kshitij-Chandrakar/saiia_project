import logging
import time

from app.config import settings
from app.services.stt_provider import STTServiceError, TranscriptionResult


class AssemblyAISTTService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.model = settings.ASSEMBLYAI_STT_MODEL or "best"

    def _get_sdk(self):
        try:
            import assemblyai as aai
        except ModuleNotFoundError as exc:
            raise STTServiceError(
                "AssemblyAI SDK is not installed.",
                public_message=(
                    "AssemblyAI STT is configured but the assemblyai package is missing. "
                    "Install the assemblyai package or use STT_FALLBACK_PROVIDER=whisper_local."
                ),
                status_code=500,
                fallback_reason="assemblyai_sdk_missing",
            ) from exc

        if not settings.ASSEMBLYAI_API_KEY:
            raise STTServiceError(
                "AssemblyAI API key is missing.",
                public_message=(
                    "AssemblyAI STT is configured but ASSEMBLYAI_API_KEY is missing. "
                    "Set ASSEMBLYAI_API_KEY or use STT_FALLBACK_PROVIDER=whisper_local."
                ),
                status_code=500,
                fallback_reason="assemblyai_api_key_missing",
            )

        aai.settings.api_key = settings.ASSEMBLYAI_API_KEY
        return aai

    def transcribe(self, *, audio_path: str) -> TranscriptionResult:
        aai = self._get_sdk()
        started = time.perf_counter()

        try:
            config = aai.TranscriptionConfig(
                speech_model=getattr(aai.SpeechModel, self.model, aai.SpeechModel.best),
            )
            transcript = aai.Transcriber().transcribe(audio_path, config=config)
        except Exception as exc:
            message = str(exc).lower()
            if "401" in message or "403" in message or "authentication" in message or "unauthorized" in message:
                raise STTServiceError(
                    "AssemblyAI authentication failed.",
                    public_message="AssemblyAI STT authentication failed. Please update ASSEMBLYAI_API_KEY and try again.",
                    status_code=500,
                    fallback_reason="assemblyai_api_key_invalid",
                ) from exc
            if "timeout" in message:
                raise STTServiceError(
                    "AssemblyAI timed out.",
                    public_message="AssemblyAI STT timed out while transcribing the recording. Please try again.",
                    status_code=500,
                    fallback_reason="assemblyai_stt_timeout",
                ) from exc
            if "audio" in message and ("empty" in message or "silent" in message or "no speech" in message):
                return TranscriptionResult(
                    text="",
                    transcription_provider="assemblyai",
                    transcription_model=self.model,
                    transcription_ms=round((time.perf_counter() - started) * 1000, 2),
                    no_speech=True,
                    reason="silence_or_no_speech",
                )
            raise STTServiceError(
                "AssemblyAI STT request failed.",
                public_message=(
                    "AssemblyAI STT could not transcribe the recording right now. "
                    "Please check the API key, internet connection, or AssemblyAI service status."
                ),
                status_code=500,
                fallback_reason="assemblyai_failed",
            ) from exc

        if getattr(transcript, "status", None) == aai.TranscriptStatus.error:
            error_message = getattr(transcript, "error", "") or "AssemblyAI transcription failed."
            lowered = error_message.lower()
            if "no speech" in lowered or "silent" in lowered or "empty" in lowered:
                return TranscriptionResult(
                    text="",
                    transcription_provider="assemblyai",
                    transcription_model=self.model,
                    transcription_ms=round((time.perf_counter() - started) * 1000, 2),
                    no_speech=True,
                    reason="silence_or_no_speech",
                )
            raise STTServiceError(
                f"AssemblyAI transcription failed: {error_message}",
                public_message=(
                    "AssemblyAI STT could not transcribe the recording right now. "
                    "Please try a short, clear microphone recording."
                ),
                status_code=500,
                fallback_reason="assemblyai_failed",
            )

        text = (getattr(transcript, "text", "") or "").strip()
        transcription_ms = round((time.perf_counter() - started) * 1000, 2)
        if not text:
            return TranscriptionResult(
                text="",
                transcription_provider="assemblyai",
                transcription_model=self.model,
                transcription_ms=transcription_ms,
                no_speech=True,
                reason="silence_or_no_speech",
            )

        return TranscriptionResult(
            text=text,
            transcription_provider="assemblyai",
            transcription_model=self.model,
            transcription_ms=transcription_ms,
        )
