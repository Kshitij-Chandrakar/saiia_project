import logging
import time
from pathlib import Path

from app.config import settings
from app.services.stt_provider import STTServiceError, TranscriptionResult


class GroqSTTService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.model = settings.GROQ_STT_MODEL
        self.timeout = settings.GROQ_TIMEOUT_SECONDS
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        if not settings.GROQ_API_KEY:
            raise STTServiceError(
                "Groq STT API key is missing.",
                public_message=(
                    "Groq STT is configured but GROQ_API_KEY is missing. "
                    "Set GROQ_API_KEY or switch STT_PROVIDER=whisper_local."
                ),
                status_code=500,
                fallback_reason="groq_api_key_missing",
            )

        try:
            from groq import Groq
        except ModuleNotFoundError as exc:
            raise STTServiceError(
                "Groq SDK is not installed.",
                public_message=(
                    "Groq STT is configured but the groq package is missing. "
                    "Install the groq package or switch STT_PROVIDER=whisper_local."
                ),
                status_code=500,
                fallback_reason="groq_sdk_missing",
            ) from exc

        self._client = Groq(api_key=settings.GROQ_API_KEY, timeout=self.timeout)
        return self._client

    def transcribe(self, *, audio_path: str, original_filename: str) -> TranscriptionResult:
        client = self._get_client()
        started = time.perf_counter()

        try:
            from groq import (
                APIConnectionError,
                APIError,
                APIStatusError,
                APITimeoutError,
                AuthenticationError,
                BadRequestError,
                InternalServerError,
                PermissionDeniedError,
            )
        except ModuleNotFoundError as exc:
            raise STTServiceError(
                "Groq SDK is not installed.",
                public_message=(
                    "Groq STT is configured but the groq package is missing. "
                    "Install the groq package or switch STT_PROVIDER=whisper_local."
                ),
                status_code=500,
                fallback_reason="groq_sdk_missing",
            ) from exc

        try:
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=self.model,
                    file=(Path(original_filename).name, audio_file.read()),
                    response_format="verbose_json",
                    temperature=0,
                )
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise STTServiceError(
                "Groq STT authentication failed.",
                public_message="Groq STT authentication failed. Please update GROQ_API_KEY and try again.",
                status_code=500,
                fallback_reason="groq_api_key_invalid",
            ) from exc
        except APITimeoutError as exc:
            raise STTServiceError(
                "Groq STT timed out.",
                public_message="Groq STT timed out while transcribing the recording. Please try again.",
                status_code=500,
                fallback_reason="groq_stt_timeout",
            ) from exc
        except BadRequestError as exc:
            raise STTServiceError(
                "Groq STT rejected the audio.",
                public_message="Groq STT rejected the recording. Please try a short, supported microphone recording.",
                status_code=400,
                fallback_reason="groq_stt_bad_request",
            ) from exc
        except APIStatusError as exc:
            if getattr(exc, "status_code", None) in {401, 403}:
                raise STTServiceError(
                    "Groq STT authentication failed.",
                    public_message="Groq STT authentication failed. Please update GROQ_API_KEY and try again.",
                    status_code=500,
                    fallback_reason="groq_api_key_invalid",
                ) from exc
            raise STTServiceError(
                "Groq STT returned an API status error.",
                public_message=(
                    "Groq STT could not transcribe the recording right now. "
                    "Please check the API key, internet connection, or Groq service status."
                ),
                status_code=500,
                fallback_reason="groq_stt_failed",
            ) from exc
        except (APIConnectionError, InternalServerError, APIError) as exc:
            raise STTServiceError(
                "Groq STT request failed.",
                public_message=(
                    "Groq STT could not transcribe the recording right now. "
                    "Please check the API key, internet connection, or Groq service status."
                ),
                status_code=500,
                fallback_reason="groq_stt_failed",
            ) from exc

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise STTServiceError(
                "Groq STT returned empty text.",
                public_message="I could not clearly detect a question in that recording. Please try again.",
                status_code=400,
                fallback_reason="groq_stt_empty_text",
            )

        transcription_ms = round((time.perf_counter() - started) * 1000, 2)
        return TranscriptionResult(
            text=text,
            transcription_provider="groq",
            transcription_model=self.model,
            transcription_ms=transcription_ms,
        )
