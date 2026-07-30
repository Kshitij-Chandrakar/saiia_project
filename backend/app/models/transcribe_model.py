from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    text: str
    transcription_provider: str
    transcription_model: str
    transcription_ms: float
    fallback_used: bool = False
    fallback_reason: str | None = None
    no_speech: bool = False
    reason: str | None = None
