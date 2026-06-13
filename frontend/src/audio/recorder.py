###
#It should:
#Open your system microphone
#Continuously capture audio
#Send small chunks (e.g., 3–5 seconds) into a queue
# frontend/src/audio/recorder.py

import logging
import queue
from typing import Optional

import numpy as np
import pyaudio


class AudioRecorder:
    """
    Captures audio from the system microphone in real-time and places audio chunks into a queue.
    If no audio arrives within `read_chunk` timeout, returns a zero‐filled buffer (silence).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        max_queue_size: int = 100,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.format = pyaudio.paInt16

        # Queue holds incoming audio chunks
        self.audio_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=max_queue_size)
        self._pyaudio = pyaudio.PyAudio()
        self._stream = None
        self._recording = False

        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO)

    def _callback(self, in_data: bytes, frame_count: int, time_info, status_flags):
        # Convert raw bytes to numpy array
        samples = np.frombuffer(in_data, dtype=np.int16)
        try:
            self.audio_queue.put_nowait(samples)
        except queue.Full:
            self.logger.warning("Audio queue full; dropping frame.")
        return (None, pyaudio.paContinue)

    def start_recording(self) -> None:
        if self._recording:
            return
        self._stream = self._pyaudio.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._callback,
        )
        self._stream.start_stream()
        self._recording = True
        self.logger.info(f"Recording started ({self.sample_rate}Hz, chunk={self.chunk_size}).")

    def stop_recording(self) -> None:
        if not self._recording:
            return
        self._stream.stop_stream()
        self._stream.close()
        self._pyaudio.terminate()
        self._recording = False
        self.logger.info("Recording stopped.")

    def read_chunk(self, timeout: Optional[float] = None) -> np.ndarray:
        """
        Return the next audio chunk from the queue, or a silent buffer if none arrives.
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            # Return silence so main loop can continue gracefully
            total_samples = self.chunk_size * self.channels
            return np.zeros(total_samples, dtype=np.int16)

    def __enter__(self):
        self.start_recording()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_recording()
