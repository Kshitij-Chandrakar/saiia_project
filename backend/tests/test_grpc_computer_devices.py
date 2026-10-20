import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.system_audio_capture import SystemAudioCaptureService, SystemAudioCaptureError, LoopbackDevice


def device(index, name):
    return dict(index=index, name=name, maxInputChannels=2, defaultSampleRate=48000, isLoopbackDevice=True)


def test_windows_default_loopback_is_not_first_enumerated(monkeypatch):
    first, default = device(10, 'Other output'), device(22, 'Windows default output')
    closed = []
    class PyAudio:
        def get_loopback_device_info_generator(self): return iter([first, default])
        def get_default_wasapi_loopback(self): return default
        def terminate(self): closed.append(True)
    service = SystemAudioCaptureService()
    monkeypatch.setattr(service, '_get_pyaudio', lambda: NS(PyAudio=PyAudio))
    assert service.get_default_loopback_device().device_index == 22
    assert [d['device_index'] for d in service.list_wasapi_loopback_devices() if d['is_default']] == [22]
    assert len(closed) == 3


def test_missing_default_never_substitutes_first_loopback(monkeypatch):
    class PyAudio:
        def get_loopback_device_info_generator(self): return iter([device(10, 'Not default')])
        def get_default_wasapi_loopback(self): raise LookupError('default unavailable')
        def terminate(self): pass
    service = SystemAudioCaptureService()
    monkeypatch.setattr(service, '_get_pyaudio', lambda: NS(PyAudio=PyAudio))
    with pytest.raises(SystemAudioCaptureError): service.get_default_loopback_device()
    assert not any(d['is_default'] for d in service.list_wasapi_loopback_devices())


def test_output_change_requires_restart_before_another_native_read(monkeypatch):
    service = SystemAudioCaptureService()
    old = LoopbackDevice(10, 'Old output', 2, 48000, True, False)
    new = LoopbackDevice(22, 'New output', 2, 48000, True, False)
    monkeypatch.setattr(service, 'get_default_loopback_device', lambda: new)
    session = NS(monitor_default=True, next_device_check_at=0, device=old, sample_rate=48000, channels=2)
    with pytest.raises(SystemAudioCaptureError, match='restart'):
        service.read_streaming_pcm_chunk(session)


def test_cleanup_attempts_all_handles_and_reports_native_failure():
    calls = []
    def stop(): calls.append('stop'); raise OSError('device lost')
    session = NS(debug_wave_writer=None, stream=NS(stop_stream=stop, close=lambda: calls.append('close')),
                 pyaudio_instance=NS(terminate=lambda: calls.append('terminate')))
    assert SystemAudioCaptureService().close_streaming_loopback_session(session) is False
    assert calls == ['stop', 'close', 'terminate']
