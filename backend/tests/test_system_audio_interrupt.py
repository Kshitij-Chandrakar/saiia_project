"""A silent WASAPI read must yield ownership to Stop without a forced close."""

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from app.services.system_audio_capture import (
    StreamingLoopbackSession,
    SystemAudioCaptureError,
    SystemAudioCaptureService,
)


def test_silent_native_read_is_interruptible_before_stream_close():
    entered = threading.Event()

    class SilentStream:
        def get_read_available(self):
            entered.set()
            return 0

        def read(self, *_args, **_kwargs):
            raise AssertionError(
                "An empty native buffer must never enter a blocking read"
            )

    session = StreamingLoopbackSession(
        None, None, SilentStream(), None, 48000, 2, 16000, 4800
    )
    service = SystemAudioCaptureService()
    with ThreadPoolExecutor(1) as pool:
        reading = pool.submit(service.read_streaming_pcm_chunk, session)
        try:
            assert entered.wait(2)
        finally:
            session.stop_requested.set()
        with pytest.raises(SystemAudioCaptureError, match="stopped"):
            reading.result(timeout=1)


def test_default_device_change_is_detected_while_output_is_silent(monkeypatch):
    stream = SimpleNamespace(get_read_available=lambda: 0)
    old = SimpleNamespace(device_index=1, name="old", sample_rate=48000, channels=2)
    changed = SimpleNamespace(device_index=2, name="new", sample_rate=48000, channels=2)
    session = StreamingLoopbackSession(
        None, None, stream, old, 48000, 2, 16000, 4800, monitor_default=True
    )
    service = SystemAudioCaptureService()
    monkeypatch.setattr(service, "get_default_loopback_device", lambda: changed)
    with pytest.raises(SystemAudioCaptureError, match="Default output changed"):
        service.read_streaming_pcm_chunk(session)
