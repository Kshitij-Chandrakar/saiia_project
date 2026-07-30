from __future__ import annotations

import logging
import platform
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from app.config import settings


logger = logging.getLogger("system_audio_capture")


class SystemAudioCaptureError(Exception):
    def __init__(self, message: str, *, public_message: str | None = None, status_code: int = 400) -> None:
        super().__init__(message)
        self.public_message = public_message or message
        self.status_code = status_code


@dataclass
class LoopbackDevice:
    device_index: int
    name: str
    channels: int
    sample_rate: int
    is_loopback: bool
    use_as_loopback: bool


@dataclass
class RecordingSession:
    recording_id: str
    started_at: float
    output_wav_path: str
    stop_event: threading.Event
    thread: threading.Thread
    sample_rate: int
    channels: int
    device_name: str
    device_index: int
    source_label: str = "system"


@dataclass
class StreamingLoopbackSession:
    pyaudio_module: Any
    pyaudio_instance: Any
    stream: Any
    device: LoopbackDevice
    sample_rate: int
    channels: int
    target_sample_rate: int
    frames_per_buffer: int
    debug_save_enabled: bool = False
    debug_wav_path: str | None = None
    debug_wave_writer: Any | None = None
    debug_bytes_written: int = 0
    stats_started_at: float = 0.0
    stats_chunk_count: int = 0
    stats_bytes_sent: int = 0
    stats_dropped_chunks: int = 0
    stats_peak_max: float = 0.0
    stats_rms_accumulator: float = 0.0
    stats_effective_gain_max: float = 0.0
    stats_clipping_detected: bool = False


@dataclass
class StreamingChunkResult:
    pcm_bytes: bytes
    rms_level: float
    peak_level: float
    clipping_detected: bool
    effective_gain: float
    chunk_bytes_sent: int
    dropped_silence: bool
    input_sample_rate: int
    target_sample_rate: int
    input_channels: int
    quality_event: dict[str, Any] | None = None


class SystemAudioCaptureService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session: RecordingSession | None = None

    def is_supported(self) -> bool:
        return platform.system().lower() == "windows"

    def _get_pyaudio(self):
        if not self.is_supported():
            raise SystemAudioCaptureError(
                "System audio capture is only supported on Windows in this mode.",
                status_code=400,
            )

        try:
            import pyaudiowpatch as pyaudio  # type: ignore
        except ImportError as exc:
            raise SystemAudioCaptureError(
                "PyAudioWPatch is not installed.",
                public_message="PyAudioWPatch is not installed. Run pip install PyAudioWPatch.",
                status_code=500,
            ) from exc

        return pyaudio

    def _list_devices_internal(self) -> list[LoopbackDevice]:
        pyaudio = self._get_pyaudio()
        pa = pyaudio.PyAudio()
        devices: list[LoopbackDevice] = []
        try:
            seen_indexes: set[int] = set()

            if hasattr(pa, "get_loopback_device_info_generator"):
                for info in pa.get_loopback_device_info_generator():
                    if not isinstance(info, dict):
                        continue
                    device_index = int(info.get("index", -1))
                    if device_index < 0 or device_index in seen_indexes:
                        continue
                    seen_indexes.add(device_index)
                    devices.append(
                        LoopbackDevice(
                            device_index=device_index,
                            name=str(info.get("name", "Loopback Device")).strip(),
                            channels=max(1, int(info.get("maxInputChannels", 2) or 2)),
                            sample_rate=int(info.get("defaultSampleRate", 48000) or 48000),
                            is_loopback=bool(info.get("isLoopbackDevice", True)),
                            use_as_loopback=False,
                        )
                    )

            if devices:
                return devices

            host_api_type = getattr(pyaudio, "paWASAPI", None)
            if host_api_type is None:
                return []

            wasapi_info = pa.get_host_api_info_by_type(host_api_type)
            default_output_index = int(wasapi_info.get("defaultOutputDevice", -1))
            if default_output_index < 0:
                return []

            default_output = pa.get_device_info_by_index(default_output_index)
            return [
                LoopbackDevice(
                    device_index=default_output_index,
                    name=str(default_output.get("name", "Default Speakers")).strip(),
                    channels=max(1, int(default_output.get("maxInputChannels", 2) or 2)),
                    sample_rate=int(default_output.get("defaultSampleRate", 48000) or 48000),
                    is_loopback=False,
                    use_as_loopback=True,
                )
            ]
        finally:
            pa.terminate()

    def list_wasapi_loopback_devices(self) -> list[dict[str, Any]]:
        devices = self._list_devices_internal()
        default_index = devices[0].device_index if devices else None
        return [
            {
                "device_index": device.device_index,
                "name": device.name,
                "channels": device.channels,
                "sample_rate": device.sample_rate,
                "is_loopback": device.is_loopback,
                "is_default": device.device_index == default_index,
            }
            for device in devices
        ]

    def get_default_loopback_device(self) -> LoopbackDevice:
        devices = self._list_devices_internal()
        if not devices:
            raise SystemAudioCaptureError(
                "No WASAPI loopback device found.",
                public_message="No WASAPI loopback device found.",
                status_code=400,
            )
        return devices[0]

    def _find_device_by_index(self, device_index: int) -> LoopbackDevice:
        for device in self._list_devices_internal():
            if device.device_index == device_index:
                return device
        raise SystemAudioCaptureError(
            "No WASAPI loopback device found.",
            public_message="No WASAPI loopback device found.",
            status_code=400,
        )

    def start_recording(self, *, device_index: int | None = None) -> dict[str, Any]:
        with self._lock:
            if self._session is not None:
                raise SystemAudioCaptureError(
                    "System audio recording is already in progress.",
                    public_message="System audio recording is already running.",
                    status_code=409,
                )

            device = self._find_device_by_index(device_index) if device_index is not None else self.get_default_loopback_device()
            output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            output_path = output_file.name
            output_file.close()

            stop_event = threading.Event()
            recording_id = f"system-{int(time.time() * 1000)}"
            thread = threading.Thread(
                target=self._record_loopback,
                kwargs={
                    "device": device,
                    "output_path": output_path,
                    "stop_event": stop_event,
                },
                daemon=True,
                name=f"system-audio-{recording_id}",
            )
            session = RecordingSession(
                recording_id=recording_id,
                started_at=time.perf_counter(),
                output_wav_path=output_path,
                stop_event=stop_event,
                thread=thread,
                sample_rate=device.sample_rate,
                channels=device.channels,
                device_name=device.name,
                device_index=device.device_index,
            )
            self._session = session
            thread.start()

        return {
            "ok": True,
            "recording_id": recording_id,
            "device_name": device.name,
            "sample_rate": device.sample_rate,
            "channels": device.channels,
            "status": "recording",
        }

    def stop_recording(self, *, recording_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            session = self._session
            if session is None:
                raise SystemAudioCaptureError(
                    "System audio recording is not active.",
                    public_message="Stop was requested before system audio recording started.",
                    status_code=400,
                )
            if recording_id and session.recording_id != recording_id:
                raise SystemAudioCaptureError(
                    "System audio recording id does not match the active session.",
                    public_message="The active system audio recording changed. Please start again.",
                    status_code=409,
                )
            self._session = None

        session.stop_event.set()
        session.thread.join(timeout=10)
        if session.thread.is_alive():
            raise SystemAudioCaptureError(
                "System audio recording failed to stop cleanly.",
                public_message="System audio recording failed to stop.",
                status_code=500,
            )

        wav_path = Path(session.output_wav_path)
        if not wav_path.exists() or wav_path.stat().st_size <= 44:
            raise SystemAudioCaptureError(
                "No system audio was captured.",
                public_message="No system audio was captured. Make sure audio is playing.",
                status_code=400,
            )

        return {
            "ok": True,
            "recording_id": session.recording_id,
            "audio_path": session.output_wav_path,
            "recording_ms": round((time.perf_counter() - session.started_at) * 1000, 2),
            "device_name": session.device_name,
            "sample_rate": session.sample_rate,
            "channels": session.channels,
            "status": "recorded",
        }

    def _record_loopback(
        self,
        *,
        device: LoopbackDevice,
        output_path: str,
        stop_event: threading.Event,
    ) -> None:
        pyaudio = self._get_pyaudio()
        pa = pyaudio.PyAudio()
        stream = None
        wf = None
        sample_width = 2
        frames_per_buffer = 1024
        try:
            wf = wave.open(output_path, "wb")
            wf.setnchannels(device.channels)
            sample_width = pa.get_sample_size(pyaudio.paInt16)
            wf.setsampwidth(sample_width)
            wf.setframerate(device.sample_rate)

            open_kwargs = {
                "format": pyaudio.paInt16,
                "channels": device.channels,
                "rate": device.sample_rate,
                "input": True,
                "frames_per_buffer": frames_per_buffer,
                "input_device_index": device.device_index,
            }
            if device.use_as_loopback:
                open_kwargs["as_loopback"] = True

            stream = pa.open(**open_kwargs)

            while not stop_event.is_set():
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                if data:
                    wf.writeframes(data)
        except Exception:
            logger.exception("System audio recording failed to start or capture.")
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                except Exception:
                    logger.exception("Failed to stop system audio stream.")
                try:
                    stream.close()
                except Exception:
                    logger.exception("Failed to close system audio stream.")
            if wf is not None:
                try:
                    wf.close()
                except Exception:
                    logger.exception("Failed to close system audio WAV file.")
            pa.terminate()

    def open_streaming_loopback_session(
        self,
        *,
        device_index: int | None = None,
        target_sample_rate: int = 16000,
        chunk_ms: int = 100,
        debug_save_enabled: bool | None = None,
    ) -> StreamingLoopbackSession:
        device = self._find_device_by_index(device_index) if device_index is not None else self.get_default_loopback_device()
        pyaudio = self._get_pyaudio()
        pa = pyaudio.PyAudio()
        frames_per_buffer = max(256, int(device.sample_rate * (max(20, chunk_ms) / 1000)))

        open_kwargs = {
            "format": pyaudio.paInt16,
            "channels": device.channels,
            "rate": device.sample_rate,
            "input": True,
            "frames_per_buffer": frames_per_buffer,
            "input_device_index": device.device_index,
        }
        if device.use_as_loopback:
            open_kwargs["as_loopback"] = True

        try:
            stream = pa.open(**open_kwargs)
        except Exception as exc:
            pa.terminate()
            raise SystemAudioCaptureError(
                "System audio streaming failed to start.",
                public_message="System audio streaming failed.",
                status_code=500,
            ) from exc

        should_debug_save = settings.SYSTEM_AUDIO_DEBUG_SAVE if debug_save_enabled is None else bool(debug_save_enabled)
        debug_wav_path, debug_wave_writer = self._open_debug_wave_if_enabled(
            target_sample_rate,
            enabled=should_debug_save,
        )

        return StreamingLoopbackSession(
            pyaudio_module=pyaudio,
            pyaudio_instance=pa,
            stream=stream,
            device=device,
            sample_rate=device.sample_rate,
            channels=device.channels,
            target_sample_rate=target_sample_rate,
            frames_per_buffer=frames_per_buffer,
            debug_save_enabled=should_debug_save,
            stats_started_at=time.perf_counter(),
            debug_wav_path=debug_wav_path,
            debug_wave_writer=debug_wave_writer,
        )

    def _open_debug_wave_if_enabled(
        self,
        target_sample_rate: int,
        *,
        enabled: bool,
    ) -> tuple[str | None, Any | None]:
        if not enabled:
            return None, None

        debug_dir = Path(__file__).resolve().parents[2] / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / "system_stream_sample.wav"
        wf = wave.open(str(debug_path), "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sample_rate)
        return str(debug_path), wf

    def close_streaming_loopback_session(self, session: StreamingLoopbackSession | None) -> None:
        if session is None:
            return
        if session.debug_wave_writer is not None:
            try:
                session.debug_wave_writer.close()
            except Exception:
                logger.debug("Failed to close debug system stream WAV.", exc_info=True)
        try:
            session.stream.stop_stream()
        except Exception:
            logger.debug("Failed to stop streaming loopback stream.", exc_info=True)
        try:
            session.stream.close()
        except Exception:
            logger.debug("Failed to close streaming loopback stream.", exc_info=True)
        try:
            session.pyaudio_instance.terminate()
        except Exception:
            logger.debug("Failed to terminate PyAudio streaming session.", exc_info=True)

    def read_streaming_pcm_chunk(self, session: StreamingLoopbackSession) -> StreamingChunkResult:
        raw_bytes = session.stream.read(session.frames_per_buffer, exception_on_overflow=False)
        pcm_bytes, rms_level, peak_level, clipping_detected, effective_gain = self._convert_loopback_bytes_to_pcm16_mono(
            raw_bytes,
            source_channels=session.channels,
            source_sample_rate=session.sample_rate,
            target_sample_rate=session.target_sample_rate,
        )
        dropped_silence = False
        if not pcm_bytes:
            session.stats_dropped_chunks += 1

        chunk_bytes_sent = len(pcm_bytes)
        session.stats_chunk_count += 1
        session.stats_bytes_sent += chunk_bytes_sent
        session.stats_peak_max = max(session.stats_peak_max, peak_level)
        session.stats_rms_accumulator += rms_level
        session.stats_effective_gain_max = max(session.stats_effective_gain_max, effective_gain)
        session.stats_clipping_detected = session.stats_clipping_detected or clipping_detected

        if session.debug_wave_writer is not None and pcm_bytes and session.debug_bytes_written < session.target_sample_rate * 2 * 10:
            remaining = (session.target_sample_rate * 2 * 10) - session.debug_bytes_written
            debug_slice = pcm_bytes[:remaining]
            session.debug_wave_writer.writeframes(debug_slice)
            session.debug_bytes_written += len(debug_slice)

        quality_event = None
        elapsed = time.perf_counter() - session.stats_started_at
        if elapsed >= 1.0:
            avg_rms = session.stats_rms_accumulator / max(1, session.stats_chunk_count)
            bytes_sent_per_second = int(round(session.stats_bytes_sent / max(elapsed, 0.001)))
            warning = ""
            if avg_rms < 0.003:
                warning = "System audio is very quiet. Increase speaker/video volume."
            elif session.stats_peak_max >= 0.98 or session.stats_clipping_detected:
                warning = "System audio is clipping. Lower volume."

            quality_event = {
                "input_sample_rate": session.sample_rate,
                "target_sample_rate": session.target_sample_rate,
                "input_channels": session.channels,
                "rms_level": round(avg_rms, 5),
                "peak_level": round(session.stats_peak_max, 5),
                "effective_gain": round(session.stats_effective_gain_max or settings.SYSTEM_AUDIO_GAIN, 3),
                "chunk_bytes_sent": session.stats_bytes_sent,
                "bytes_sent_per_second": bytes_sent_per_second,
                "dropped_silence_chunks": session.stats_dropped_chunks,
                "clipping_detected": session.stats_clipping_detected,
                "warning": warning,
                "debug_wav_path": session.debug_wav_path if session.debug_save_enabled else None,
                "selected_device_name": session.device.name,
            }
            session.stats_started_at = time.perf_counter()
            session.stats_chunk_count = 0
            session.stats_bytes_sent = 0
            session.stats_dropped_chunks = 0
            session.stats_peak_max = 0.0
            session.stats_rms_accumulator = 0.0
            session.stats_effective_gain_max = 0.0
            session.stats_clipping_detected = False

        return StreamingChunkResult(
            pcm_bytes=pcm_bytes,
            rms_level=rms_level,
            peak_level=peak_level,
            clipping_detected=clipping_detected,
            effective_gain=effective_gain,
            chunk_bytes_sent=chunk_bytes_sent,
            dropped_silence=dropped_silence,
            input_sample_rate=session.sample_rate,
            target_sample_rate=session.target_sample_rate,
            input_channels=session.channels,
            quality_event=quality_event,
        )

    def _convert_loopback_bytes_to_pcm16_mono(
        self,
        raw_bytes: bytes,
        *,
        source_channels: int,
        source_sample_rate: int,
        target_sample_rate: int,
    ) -> tuple[bytes, float, float, bool, float]:
        if not raw_bytes:
            return b"", 0.0, 0.0, False, settings.SYSTEM_AUDIO_GAIN

        audio = np.frombuffer(raw_bytes, dtype=np.int16)
        if audio.size == 0:
            return b"", 0.0, 0.0, False, settings.SYSTEM_AUDIO_GAIN

        audio = audio.astype(np.float32) / 32768.0

        if source_channels > 1:
            usable = (audio.size // source_channels) * source_channels
            if usable == 0:
                return b"", 0.0, 0.0, False, settings.SYSTEM_AUDIO_GAIN
            audio = audio[:usable].reshape(-1, source_channels)
            audio = np.mean(audio, axis=1)

        if source_sample_rate != target_sample_rate and audio.size > 1:
            ratio = Fraction(target_sample_rate, source_sample_rate).limit_denominator()
            audio = resample_poly(audio, ratio.numerator, ratio.denominator)

        rms_before_gain = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        effective_gain = max(1.0, settings.SYSTEM_AUDIO_GAIN)
        max_gain = max(effective_gain, settings.SYSTEM_AUDIO_MAX_GAIN)

        if 0.0 < rms_before_gain < 0.08:
            target_rms = 0.08
            effective_gain = min(max_gain, max(effective_gain, target_rms / max(rms_before_gain, 1e-6)))

        amplified = audio * effective_gain
        clipping_detected = bool(np.any(np.abs(amplified) > 1.0))
        amplified = np.clip(amplified, -1.0, 1.0)
        peak_level = float(np.max(np.abs(amplified))) if amplified.size else 0.0
        rms_level = float(np.sqrt(np.mean(np.square(amplified)))) if amplified.size else 0.0

        pcm16 = np.clip(amplified * 32767.0, -32768.0, 32767.0).astype(np.int16)
        return pcm16.tobytes(), rms_level, peak_level, clipping_detected, effective_gain

    def capture_debug_processed_audio(
        self,
        *,
        duration_ms: int = 10000,
        device_index: int | None = None,
        target_sample_rate: int = 16000,
    ) -> dict[str, Any]:
        session = self.open_streaming_loopback_session(
            device_index=device_index,
            target_sample_rate=target_sample_rate,
            chunk_ms=80,
            debug_save_enabled=True,
        )
        started = time.perf_counter()
        total_bytes = 0
        peak_level = 0.0
        rms_accumulator = 0.0
        chunk_count = 0
        clipping_detected = False
        effective_gain = settings.SYSTEM_AUDIO_GAIN

        try:
            deadline = started + (max(1000, int(duration_ms or 10000)) / 1000)
            while time.perf_counter() < deadline:
                chunk = self.read_streaming_pcm_chunk(session)
                if chunk.pcm_bytes:
                    total_bytes += len(chunk.pcm_bytes)
                    peak_level = max(peak_level, chunk.peak_level)
                    rms_accumulator += chunk.rms_level
                    chunk_count += 1
                    clipping_detected = clipping_detected or chunk.clipping_detected
                    effective_gain = max(effective_gain, chunk.effective_gain)
        finally:
            self.close_streaming_loopback_session(session)

        average_rms = rms_accumulator / max(1, chunk_count)
        return {
            "file_path": session.debug_wav_path,
            "device_name": session.device.name,
            "input_sample_rate": session.sample_rate,
            "target_sample_rate": session.target_sample_rate,
            "channels": session.channels,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "bytes_captured": total_bytes,
            "rms_level": round(average_rms, 5),
            "peak_level": round(peak_level, 5),
            "clipping_detected": clipping_detected,
            "effective_gain": round(effective_gain, 3),
        }
