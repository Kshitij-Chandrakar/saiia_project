import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings


logger = logging.getLogger("assemblyai_streaming")


class AssemblyAIStreamingError(Exception):
    def __init__(self, message: str, *, public_message: str | None = None) -> None:
        super().__init__(message)
        self.public_message = public_message or message


@dataclass
class AssemblyAIStreamingConfig:
    url: str
    sample_rate: int
    speech_model: str
    api_key: str


class AssemblyAIStreamingBridge:
    def __init__(self) -> None:
        self.config = AssemblyAIStreamingConfig(
            url=settings.ASSEMBLYAI_STREAMING_URL,
            sample_rate=settings.ASSEMBLYAI_STREAMING_SAMPLE_RATE,
            speech_model=settings.ASSEMBLYAI_STREAMING_SPEECH_MODEL,
            api_key=settings.ASSEMBLYAI_API_KEY,
        )

    def validate(self) -> None:
        if not self.config.api_key:
            raise AssemblyAIStreamingError(
                "AssemblyAI API key missing for streaming.",
                public_message="AssemblyAI streaming is not configured. Add ASSEMBLYAI_API_KEY.",
            )
        if not self.config.url:
            raise AssemblyAIStreamingError(
                "AssemblyAI streaming URL missing.",
                public_message="AssemblyAI streaming URL is not configured.",
            )
        if not self.config.sample_rate:
            raise AssemblyAIStreamingError(
                "AssemblyAI streaming sample rate missing.",
                public_message="AssemblyAI streaming sample rate is not configured.",
            )

    def build_websocket_url(self) -> str:
        query = urlencode(
            {
                "sample_rate": self.config.sample_rate,
                "speech_model": self.config.speech_model,
            }
        )
        return f"{self.config.url}?{query}"

    async def connect(self):
        self.validate()
        url = self.build_websocket_url()
        logger.info(
            "Connecting to AssemblyAI streaming speech_model=%s sample_rate=%s",
            self.config.speech_model,
            self.config.sample_rate,
        )
        try:
            return await websockets.connect(
                url,
                additional_headers={"Authorization": self.config.api_key},
                max_size=None,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            raise AssemblyAIStreamingError(
                f"AssemblyAI streaming connection failed: {exc}",
                public_message="AssemblyAI streaming could not connect.",
            ) from exc

    async def send_terminate(self, socket) -> None:
        try:
            await socket.send(json.dumps({"type": "Terminate"}))
        except Exception:
            logger.debug("AssemblyAI terminate message failed.", exc_info=True)

    async def send_force_endpoint(self, socket) -> None:
        try:
            await socket.send(json.dumps({"type": "ForceEndpoint"}))
        except Exception:
            logger.debug("AssemblyAI force endpoint message failed.", exc_info=True)

    async def close(self, socket) -> None:
        if socket is None:
            return
        try:
            await self.send_terminate(socket)
            await socket.close()
        except ConnectionClosed:
            return
        except Exception:
            logger.debug("AssemblyAI websocket close failed.", exc_info=True)
