# # src/audio/recorder.py
#
# import logging
# import threading
# import queue
# from typing import Optional
#
# import numpy as np
# import pyaudio
#
#
# class AudioRecorder:
#     """
#     Captures audio from the system microphone in real-time and places audio chunks into a queue.
#
#     Attributes:
#         sample_rate: Audio sampling rate in Hz.
#         chunk_size: Number of frames per buffer.
#         channels: Number of audio channels.
#         audio_queue: Queue where each item is a numpy array of int16 samples.
#     """
#
#     def __init__(
#             self,
#             sample_rate: int = 16000,
#             chunk_size: int = 1024,
#             channels: int = 1,
#     ) -> None:
#         self.sample_rate = sample_rate
#         self.chunk_size = chunk_size
#         self.channels = channels
#         self.format = pyaudio.paInt16
#
#         self.audio_queue: "queue.Queue[np.ndarray]" = queue.Queue()
#         self._pyaudio: pyaudio.PyAudio = pyaudio.PyAudio()
#         self._stream: Optional[pyaudio.Stream] = None
#         self._recording: bool = False
#
#         self.logger = logging.getLogger(self.__class__.__name__)
#         logging.basicConfig(level=logging.INFO)
#
#     def _callback(self, in_data: bytes, frame_count: int, time_info, status_flags) -> tuple[None, int]:
#         """
#         PyAudio stream callback: called whenever a new buffer of audio data is available.
#         Converts raw bytes to a numpy array and pushes it to the queue.
#         """
#         # Convert byte data to numpy array of int16 samples
#         audio_array = np.frombuffer(in_data, dtype=np.int16)
#         try:
#             self.audio_queue.put_nowait(audio_array)
#         except queue.Full:
#             self.logger.warning("Audio queue is full; dropping frame.")
#         return (None, pyaudio.paContinue)
#
#     def start_recording(self) -> None:
#         """
#         Opens the microphone stream and begins capturing audio.
#         Safe to call multiple times; subsequent calls are no-ops.
#         """
#         if self._recording:
#             self.logger.warning("Audio recording already in progress.")
#             return
#
#         self._stream = self._pyaudio.open(
#             format=self.format,
#             channels=self.channels,
#             rate=self.sample_rate,
#             input=True,
#             frames_per_buffer=self.chunk_size,
#             stream_callback=self._callback,
#         )
#         self._recording = True
#         self._stream.start_stream()
#         self.logger.info(f"Started audio recording at {self.sample_rate} Hz, chunk size {self.chunk_size}.")
#
#     def stop_recording(self) -> None:
#         """
#         Stops and closes the microphone stream, and terminates the PyAudio instance.
#         Safe to call multiple times; subsequent calls are no-ops.
#         """
#         if not self._recording:
#             self.logger.warning("Audio recording is not in progress.")
#             return
#
#         assert self._stream is not None
#         self._stream.stop_stream()
#         self._stream.close()
#         self._pyaudio.terminate()
#         self._recording = False
#         self.logger.info("Audio recording stopped.")
#
#     def __enter__(self) -> "AudioRecorder":
#         self.start_recording()
#         return self
#
#     def __exit__(self, exc_type, exc_val, exc_tb) -> None:
#         self.stop_recording()
