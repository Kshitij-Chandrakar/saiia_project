import io
import wave
import logging
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger("SAIIAClient")
logging.basicConfig(level=logging.INFO)


class SAIIAClient:
    def __init__(self, base_url: str):
        # Ensure no trailing slash
        self.base_url = base_url.rstrip("/")

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        Wrap raw PCM (int16) into a WAV container and send to /transcribe/.
        Returns the transcribed text.
        """
        # Build an in-memory WAV file
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)           # mono
            wf.setsampwidth(2)           # 16-bit = 2 bytes
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        buf.seek(0)

        files = {
            "file": ("audio.wav", buf.read(), "audio/wav")
        }
        url = f"{self.base_url}/transcribe/"
        logger.info(f"Transcribing audio via {url}")
        resp = requests.post(url, files=files, timeout=30.0)
        resp.raise_for_status()
        return resp.json()["text"]

    def classify(self, text: str) -> str:
        """
        Send a piece of text to /classify/ and return the predicted category.
        """
        url = f"{self.base_url}/classify/"
        payload = {"text": text}
        logger.info(f"Classifying text via {url}: {text!r}")
        resp = requests.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return resp.json()["category"]

    def generate(
        self,
        question: str,
        category: str,
        profile: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send question+category (and optional profile) to /generate/ and return the LLM's answer.
        """
        url = f"{self.base_url}/generate/"
        payload: Dict[str, Any] = {
            "question": question,
            "category": category
        }
        if profile:
            payload["profile"] = profile

        logger.info(f"Generating answer via {url}: {question!r} ({category})")
        resp = requests.post(url, json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()["answer"]
