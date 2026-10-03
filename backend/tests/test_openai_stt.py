from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, BadRequestError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import openai_stt_service as module
from app.services.stt_provider import STTProviderService, STTServiceError, TranscriptionResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module.settings, "OPENAI_API_KEY", "test-key")
    factory = MagicMock()
    sdk = factory.return_value.__enter__.return_value
    monkeypatch.setattr(module, "OpenAI", factory)
    return factory, sdk


@pytest.mark.parametrize("text, expected, silent", [(" hello ", "hello", False), (" ", "", True)])
def test_transcript(client, tmp_path, text, expected, silent):
    factory, sdk = client
    sdk.audio.transcriptions.create.return_value = SimpleNamespace(text=text)
    audio = tmp_path / "clip.webm"
    audio.write_bytes(b"audio")
    result = module.OpenAISTTService().transcribe(audio_path=str(audio), original_filename="clip.webm")
    assert result.text == expected
    assert result.no_speech is silent
    assert result.transcription_provider == "openai_whisper"
    assert result.transcription_model == module.settings.OPENAI_STT_MODEL
    assert factory.call_args.kwargs["max_retries"] == 0
    assert sdk.audio.transcriptions.create.call_args.kwargs["file"][1].closed


@pytest.mark.parametrize("kind, reason, status", [
    ("auth", "openai_stt_auth_failed", 500),
    ("timeout", "openai_stt_timeout", 500),
    ("connection", "openai_stt_connection_failed", 500),
    ("bad_request", "openai_stt_bad_request", 400),
    ("api", "openai_stt_failed", 500),
])
def test_error_mapping(client, tmp_path, kind, reason, status):
    _, sdk = client
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(401 if kind == "auth" else 400, request=request)
    errors = {
        "auth": AuthenticationError("upstream-secret", response=response, body=None),
        "timeout": APITimeoutError(request=request),
        "connection": APIConnectionError(request=request),
        "bad_request": BadRequestError("upstream-secret", response=response, body=None),
        "api": APIError("upstream-secret", request=request, body=None),
    }
    sdk.audio.transcriptions.create.side_effect = errors[kind]
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"audio")
    with pytest.raises(STTServiceError) as caught:
        module.OpenAISTTService().transcribe(audio_path=str(audio), original_filename="clip.wav")
    assert caught.value.fallback_reason == reason
    assert caught.value.status_code == status
    assert "upstream-secret" not in str(caught.value)


def test_missing_key(monkeypatch):
    monkeypatch.setattr(module.settings, "OPENAI_API_KEY", "")
    with pytest.raises(STTServiceError, match="key is missing"):
        module.OpenAISTTService().transcribe(audio_path="unused", original_filename="clip.wav")


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(module.settings, "MANUAL_STT_PROVIDER", "openai_whisper")
    service = STTProviderService.__new__(STTProviderService)
    service.openai_service = MagicMock()
    service.whisper_service = MagicMock()
    service.openai_service.transcribe.return_value = TranscriptionResult("hello", "openai_whisper", "whisper-1", 1)
    return service


def test_manual_routing_and_cleanup(provider):
    result = provider.transcribe_upload(filename="clip.webm", content_type="audio/webm", content=b"audio")
    assert result.transcription_provider == "openai_whisper"
    path = provider.openai_service.transcribe.call_args.kwargs["audio_path"]
    assert not Path(path).exists()
    provider.whisper_service.transcribe.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
def test_fallback(provider, monkeypatch, enabled):
    monkeypatch.setattr(module.settings, "STT_FALLBACK_PROVIDER", "whisper_local" if enabled else "none")
    provider.openai_service.transcribe.side_effect = STTServiceError("timeout", fallback_reason="openai_stt_timeout")
    provider.whisper_service.transcribe.return_value = TranscriptionResult("local", "whisper_local", "tiny.en", 1)
    if enabled:
        result = provider.transcribe_upload(filename="clip.wav", content_type="audio/wav", content=b"audio")
        assert result.text == "local"
        assert result.fallback_used is True
        assert result.fallback_reason == "openai_stt_timeout"
    else:
        with pytest.raises(STTServiceError):
            provider.transcribe_upload(filename="clip.wav", content_type="audio/wav", content=b"audio")
        provider.whisper_service.transcribe.assert_not_called()
    assert not Path(provider.openai_service.transcribe.call_args.kwargs["audio_path"]).exists()


@pytest.mark.parametrize("mode, setting", [("auto", "STT_PROVIDER"), ("auto_fallback", "AUTO_STT_FALLBACK_PROVIDER")])
def test_nonmanual_routing_unchanged(provider, monkeypatch, mode, setting):
    monkeypatch.setattr(module.settings, setting, "whisper_local")
    provider.whisper_service.transcribe.return_value = TranscriptionResult("local", "whisper_local", "tiny.en", 1)
    result = provider.transcribe_upload(filename="clip.wav", content_type="audio/wav", content=b"audio", mode=mode)
    assert result.transcription_provider == "whisper_local"
    provider.openai_service.transcribe.assert_not_called()


def test_response_shape(provider, monkeypatch):
    monkeypatch.setattr(STTProviderService, "__init__", lambda self: None)
    from app.api import transcribe

    monkeypatch.setattr(transcribe, "stt_provider", provider)
    app = FastAPI()
    app.include_router(transcribe.router, prefix="/transcribe")
    with TestClient(app) as client:
        response = client.post("/transcribe/", files={"file": ("clip.webm", b"audio", "audio/webm")}, data={"mode": "manual"})
    assert response.status_code == 200
    assert response.json() == {
        "text": "hello", "mode": "manual", "transcription_provider": "openai_whisper",
        "transcription_model": "whisper-1", "transcription_ms": 1.0,
        "upload_ms": response.json()["upload_ms"], "fallback_used": False,
        "fallback_reason": None, "no_speech": False, "reason": None,
    }
