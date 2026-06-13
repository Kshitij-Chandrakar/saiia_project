# src/audio/speech_to_text.py

import threading
import queue
import logging
from typing import Callable, Optional

import numpy as np
import torch
import whisper


class SpeechToText:
    """
    Lightweight real-time speech-to-text using Whisper Tiny with noise filtering.

    Reads raw audio frames, buffers short segments,
    filters out silence, and transcribes using Whisper tiny for speed.
    Outputs via callback or internal queue.
    """

    def __init__(
        self,
        audio_queue: "queue.Queue[np.ndarray]",
        model_name: str = "tiny.en",
        segment_length: float = 1.5,
        sample_rate: int = 16000,
        callback: Optional[Callable[[str], None]] = None,
        timeout: float = 0.2,
        language: str = "en",
        noise_threshold: float = 0.005,
    ) -> None:
        self.audio_queue = audio_queue
        self.segment_length = segment_length
        self.sample_rate = sample_rate
        self.timeout = timeout
        self.callback = callback
        self.language = language
        self.noise_threshold = noise_threshold

        # Fallback internal queue if no callback
        self.transcript_queue: Optional[queue.Queue[str]] = (
            queue.Queue() if callback is None else None
        )

        # Logging
        logging.basicConfig(level=logging.ERROR)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Determine device (use CPU for tiny)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger.info(f"Loading Whisper model '{model_name}' on {self.device}.")

        # Load a small model for speed
        self.model = whisper.load_model(model_name, device=self.device)

        # Thread control
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Begin processing thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop processing thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _process_loop(self) -> None:
        """
        Continuously buffer small segments, drop silent ones,
        and call Whisper for fast transcription.
        """
        seg_samples = int(self.segment_length * self.sample_rate)
        buf: list[np.ndarray] = []

        while not self._stop_event.is_set():
            try:
                chunk = self.audio_queue.get(timeout=self.timeout)
                buf.append(chunk)
                total = sum(b.shape[0] for b in buf)
                if total < seg_samples:
                    continue

                # Prepare audio
                audio = np.concatenate(buf, axis=0).astype(np.float32) / 32768.0
                buf.clear()

                # Noise filter
                if np.sqrt(np.mean(audio**2)) < self.noise_threshold:
                    continue

                # Transcribe (fast tiny model)
                result = self.model.transcribe(audio, language=self.language)
                text = result.get("text", "").strip()
                if not text:
                    continue

                # Deliver output
                if self.callback:
                    self.callback(text)
                elif self.transcript_queue:
                    self.transcript_queue.put(text)

            except queue.Empty:
                continue
            except Exception:
                break
