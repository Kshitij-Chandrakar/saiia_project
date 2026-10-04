"""OpenAI Whisper transcription for manual recordings."""

import time
from pathlib import Path

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
)

from app.config import settings
from app.services.stt_provider import STTServiceError, TranscriptionResult


class OpenAISTTService:
    def __init__(self) -> None:
        self.model = settings.OPENAI_STT_MODEL
        self.timeout = settings.OPENAI_STT_TIMEOUT_SECONDS

    def transcribe(self, *, audio_path: str, original_filename: str) -> TranscriptionResult:
        """Transcribe a file, returning safe errors without upstream response details."""
        if not settings.OPENAI_API_KEY:
            raise STTServiceError(
                "OpenAI STT API key is missing.",
                public_message="Set OPENAI_API_KEY to enable OpenAI manual transcription.",
                fallback_reason="openai_stt_api_key_missing",
            )
        started = time.perf_counter()
        try:
            with OpenAI(
                api_key=settings.OPENAI_API_KEY, timeout=self.timeout, max_retries=0
            ) as client:
                with open(audio_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model=self.model,
                        file=(Path(original_filename).name, audio_file),
                        response_format="json",
                    )
        except (AuthenticationError, PermissionDeniedError):
            raise STTServiceError("OpenAI STT authentication failed.", fallback_reason="openai_stt_auth_failed") from None
        except APITimeoutError:
            raise STTServiceError("OpenAI STT timed out.", fallback_reason="openai_stt_timeout") from None
        except BadRequestError:
            raise STTServiceError("OpenAI STT rejected the recording.", status_code=400, fallback_reason="openai_stt_bad_request") from None
        except APIConnectionError:
            raise STTServiceError("OpenAI STT could not connect.", fallback_reason="openai_stt_connection_failed") from None
        except APIError:
            raise STTServiceError("OpenAI STT request failed.", fallback_reason="openai_stt_failed") from None
        text = (response.text or "").strip()
        return TranscriptionResult(
            text=text,
            transcription_provider="openai_whisper",
            transcription_model=self.model,
            transcription_ms=round((time.perf_counter() - started) * 1000, 2),
            no_speech=not bool(text),
            reason="silence_or_no_speech" if not text else None,
        )
