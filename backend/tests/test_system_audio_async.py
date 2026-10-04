import asyncio
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.mark.parametrize("chunk", [False, True])
def test_system_audio_transcription_runs_off_event_loop(monkeypatch, tmp_path, chunk):
    # The boundary test needs no Whisper model or external provider client.
    with patch('app.services.STTProviderService'):
        from app.api import system_audio as module
    audio = tmp_path / "capture.wav"
    audio.write_bytes(b"test")
    loop_thread = threading.get_ident()
    calls = []

    def transcribe(**kwargs):
        calls.append(kwargs)
        assert threading.get_ident() != loop_thread
        return SimpleNamespace(text="Question?", transcription_ms=12, transcription_provider="openai_whisper",
                               transcription_model="whisper-1", fallback_used=False, fallback_reason=None,
                               no_speech=False, reason=None)

    monkeypatch.setattr(module.stt_provider, "transcribe_file", transcribe)
    monkeypatch.setattr(module.system_audio_service, "start_recording", lambda **_: {"recording_id": "test"})
    monkeypatch.setattr(module.system_audio_service, "stop_recording", lambda **_: {
        "audio_path": str(audio), "recording_id": "test", "recording_ms": 1000, "device_name": "test",
    })
    if chunk:
        async def no_wait(_):
            pass
        monkeypatch.setattr(module.asyncio, "sleep", no_wait)
        response = asyncio.run(module.capture_system_audio_chunk(module.SystemAudioCaptureChunkRequest(duration_ms=1000)))
    else:
        response = asyncio.run(module.stop_system_audio_recording(module.SystemAudioStopRequest(recording_id="test")))
    assert response.transcript == "Question?"
    assert calls == [{"audio_path": str(audio), "original_filename": "system-loopback.wav", "mode": "manual"}]
    assert not audio.exists()
