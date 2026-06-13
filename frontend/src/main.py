import sys, os, io
import wave
import threading

import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from audio.recorder import AudioRecorder
from ui.overlay import StealthOverlay
from api_client import SAIIAClient
from utils.hotkeys import HotkeyManager

# Helper to wrap PCM into WAV
def make_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

def main():
    app = QApplication(sys.argv)
    overlay = StealthOverlay()
    overlay.hide()

    client = SAIIAClient("http://localhost:8000")
    recorder = AudioRecorder(sample_rate=16000, chunk_size=1024, channels=1)

    # Buffer for PCM while recording
    audio_buffer = []

    # State flag
    is_recording = threading.Event()

    def process_and_display():
        """Called once when user stops recording."""
        pcm = np.concatenate(audio_buffer).tobytes()
        audio_buffer.clear()

        # 1) Transcribe
        wav = make_wav(pcm)
        text = client.transcribe(wav)

        # 2) Classify + Generate
        category = client.classify(text)
        answer   = client.generate(text, category)

        # 3) Show result
        overlay.answerReady.emit(answer)

    def on_hotkey(key, event_type):
        nonlocal is_recording

        if key == Qt.Key.Key_F7:
            if event_type == "down" and not is_recording.is_set():
                # Start recording
                audio_buffer.clear()
                recorder.start_recording()
                is_recording.set()
                print("Recording started…")
            elif event_type == "up" and is_recording.is_set():
                # Stop & process
                recorder.stop_recording()
                is_recording.clear()
                print("Recording stopped; processing…")
                threading.Thread(target=process_and_display, daemon=True).start()

        elif key == Qt.Key.Key_F8:
            # Toggle overlay visibility
            overlay.toggle_visibility()

    # Hotkey listener (F7 down/up, F8 toggle)
    hotkey = HotkeyManager(on_hotkey)
    hotkey.start_listening()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
