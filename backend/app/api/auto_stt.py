import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from uvicorn.protocols.utils import ClientDisconnected
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from app.config import settings
from app.services.assemblyai_streaming import (
    AssemblyAIStreamingBridge,
    AssemblyAIStreamingError,
)
from app.services.system_audio_capture import (
    SystemAudioCaptureError,
    SystemAudioCaptureService,
)


router = APIRouter()
logger = logging.getLogger("auto_stt_ws")
bridge = AssemblyAIStreamingBridge()
system_audio_service = SystemAudioCaptureService()


def _frontend_websocket_is_closed(websocket: WebSocket) -> bool:
    try:
        return (
            websocket.client_state != WebSocketState.CONNECTED
            or websocket.application_state == WebSocketState.DISCONNECTED
        )
    except Exception:
        return False


async def _send_json(websocket: WebSocket, payload: dict) -> bool:
    if _frontend_websocket_is_closed(websocket):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, ClientDisconnected, ConnectionClosedOK):
        logger.info("Frontend websocket disconnected while sending payload.")
        return False
    except RuntimeError:
        logger.debug("Frontend websocket already closed while sending payload.")
        return False


def _is_expected_disconnect(exc: Exception) -> bool:
    return isinstance(exc, (WebSocketDisconnect, ClientDisconnected, ConnectionClosedOK))


async def _relay_assemblyai_events(websocket: WebSocket, assembly_socket, *, source: str) -> None:
    async for raw_message in assembly_socket:
        if isinstance(raw_message, bytes):
            continue

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON AssemblyAI websocket payload.")
            continue

        event_type = payload.get("type")
        if event_type == "Begin":
            if not await _send_json(
                websocket,
                {
                    "event": "begin",
                    "streaming_connected": True,
                    "provider": "assemblyai_streaming",
                    "source": source,
                    "session_id": payload.get("id"),
                    "expires_at": payload.get("expires_at"),
                },
            ):
                break
            continue

        if event_type == "Turn":
            if not await _send_json(
                websocket,
                {
                    "event": "turn",
                    "streaming_connected": True,
                    "provider": "assemblyai_streaming",
                    "source": source,
                    "transcript": payload.get("transcript", ""),
                    "end_of_turn": bool(payload.get("end_of_turn")),
                    "turn_is_formatted": bool(payload.get("turn_is_formatted")),
                    "turn_order": payload.get("turn_order"),
                    "end_of_turn_confidence": payload.get("end_of_turn_confidence"),
                },
            ):
                break
            continue

        if event_type == "Termination":
            await _send_json(
                websocket,
                {
                    "event": "termination",
                    "streaming_connected": False,
                    "provider": "assemblyai_streaming",
                    "source": source,
                    "audio_duration_seconds": payload.get("audio_duration_seconds"),
                    "session_duration_seconds": payload.get("session_duration_seconds"),
                },
            )
            break

        if event_type == "Error":
            await _send_json(
                websocket,
                {
                    "event": "error",
                    "streaming_connected": False,
                    "provider": "assemblyai_streaming",
                    "source": source,
                    "message": payload.get("error") or payload.get("message") or "AssemblyAI streaming error.",
                },
            )
            break

        if not await _send_json(
            websocket,
            {
                "event": "info",
                "streaming_connected": True,
                "provider": "assemblyai_streaming",
                "source": source,
                "type": event_type,
            },
        ):
            break


async def _relay_frontend_control(websocket: WebSocket, assembly_socket) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect

        binary_payload = message.get("bytes")
        if binary_payload:
            await assembly_socket.send(binary_payload)
            continue

        text_payload = message.get("text")
        if not text_payload:
            continue

        try:
            command = json.loads(text_payload)
        except json.JSONDecodeError:
            continue

        event_type = str(command.get("type") or "").lower()
        if event_type == "terminate":
            await bridge.send_terminate(assembly_socket)
            break
        if event_type == "force_endpoint":
            await bridge.send_force_endpoint(assembly_socket)
            continue
        if event_type == "keepalive":
            try:
                await assembly_socket.send(json.dumps({"type": "KeepAlive"}))
            except Exception:
                logger.debug("AssemblyAI keepalive send failed.", exc_info=True)


@router.websocket("/ws/auto-stt")
async def auto_stt_websocket(websocket: WebSocket):
    await websocket.accept()

    if settings.AUTO_STT_PROVIDER != "assemblyai_streaming":
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "message": "Auto STT provider is not set to assemblyai_streaming.",
                "provider": settings.AUTO_STT_PROVIDER,
            },
        )
        await websocket.close(code=1008)
        return

    try:
        assembly_socket = await bridge.connect()
    except AssemblyAIStreamingError as exc:
        logger.warning("AssemblyAI streaming bridge failed to connect: %s", exc)
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "message": exc.public_message,
                "provider": "assemblyai_streaming",
                "fallback_provider": settings.AUTO_STT_FALLBACK_PROVIDER,
            },
        )
        await websocket.close(code=1011)
        return

    logger.info("Auto STT websocket connected provider=assemblyai_streaming")

    try:
        await asyncio.gather(
            _relay_frontend_control(websocket, assembly_socket),
            _relay_assemblyai_events(websocket, assembly_socket, source="microphone"),
        )
    except (WebSocketDisconnect, ClientDisconnected, ConnectionClosedOK):
        logger.info("Frontend auto STT websocket disconnected.")
    except ConnectionClosed as exc:
        logger.warning("AssemblyAI streaming websocket closed: code=%s reason=%s", exc.code, exc.reason)
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "provider": "assemblyai_streaming",
                "message": "AssemblyAI streaming session closed unexpectedly.",
                "fallback_provider": settings.AUTO_STT_FALLBACK_PROVIDER,
            },
        )
    except Exception as exc:
        logger.exception("Auto STT websocket bridge failed.")
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "provider": "assemblyai_streaming",
                "message": f"Auto STT bridge failed: {exc}",
                "fallback_provider": settings.AUTO_STT_FALLBACK_PROVIDER,
            },
        )
    finally:
        await bridge.close(assembly_socket)
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.websocket("/ws/system-auto-stt")
async def system_auto_stt_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        assembly_socket = await bridge.connect()
    except AssemblyAIStreamingError as exc:
        logger.warning("System Auto STT bridge failed to connect: %s", exc)
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "provider": "assemblyai_streaming",
                "source": "system",
                "message": exc.public_message,
            },
        )
        await websocket.close(code=1011)
        return

    loopback_session = None
    stop_event = asyncio.Event()

    try:
        loopback_session = system_audio_service.open_streaming_loopback_session(
            target_sample_rate=settings.ASSEMBLYAI_STREAMING_SAMPLE_RATE,
            chunk_ms=80,
        )
        await _send_json(
            websocket,
            {
                "event": "system_stream_ready",
                "streaming_connected": True,
                "provider": "assemblyai_streaming",
                "source": "system",
                "device_name": loopback_session.device.name,
                "sample_rate": loopback_session.target_sample_rate,
                "input_sample_rate": loopback_session.sample_rate,
                "channels": loopback_session.channels,
            },
        )
        logger.info(
            "System Auto STT websocket connected device=%s input_sample_rate=%s target_sample_rate=%s",
            loopback_session.device.name,
            loopback_session.sample_rate,
            loopback_session.target_sample_rate,
        )
    except SystemAudioCaptureError as exc:
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "provider": "assemblyai_streaming",
                "source": "system",
                "message": exc.public_message,
            },
        )
        await bridge.close(assembly_socket)
        await websocket.close(code=1011)
        return

    async def relay_system_audio() -> None:
        try:
            while not stop_event.is_set():
                pcm_chunk = await asyncio.to_thread(
                    system_audio_service.read_streaming_pcm_chunk,
                    loopback_session,
                )
                if pcm_chunk.quality_event:
                    if not await _send_json(
                        websocket,
                        {
                            "event": "quality",
                            "streaming_connected": True,
                            "provider": "assemblyai_streaming",
                            "source": "system",
                            **pcm_chunk.quality_event,
                        },
                    ):
                        stop_event.set()
                        logger.info("Frontend system auto STT websocket disconnected.")
                        return
                if pcm_chunk.pcm_bytes:
                    await assembly_socket.send(pcm_chunk.pcm_bytes)
        except (WebSocketDisconnect, ClientDisconnected, ConnectionClosedOK):
            logger.info("Frontend system auto STT websocket disconnected.")
            stop_event.set()
            return
        except Exception as exc:
            if _is_expected_disconnect(exc):
                logger.info("Frontend system auto STT websocket disconnected.")
                stop_event.set()
                return
            logger.exception("System audio streaming relay failed.")
            await _send_json(
                websocket,
                {
                    "event": "error",
                    "streaming_connected": False,
                    "provider": "assemblyai_streaming",
                    "source": "system",
                    "message": f"System audio streaming failed: {exc}",
                },
            )
            stop_event.set()
            raise

    async def relay_system_frontend_control() -> None:
        try:
            await _relay_frontend_control(websocket, assembly_socket)
        finally:
            stop_event.set()

    try:
        await asyncio.gather(
            relay_system_audio(),
            relay_system_frontend_control(),
            _relay_assemblyai_events(websocket, assembly_socket, source="system"),
        )
    except (WebSocketDisconnect, ClientDisconnected, ConnectionClosedOK):
        logger.info("Frontend system auto STT websocket disconnected.")
    except ConnectionClosed as exc:
        logger.warning("AssemblyAI system streaming websocket closed: code=%s reason=%s", exc.code, exc.reason)
        await _send_json(
            websocket,
            {
                "event": "error",
                "streaming_connected": False,
                "provider": "assemblyai_streaming",
                "source": "system",
                "message": "AssemblyAI streaming session closed unexpectedly.",
            },
        )
    except Exception:
        logger.exception("System auto STT websocket bridge failed.")
    finally:
        stop_event.set()
        system_audio_service.close_streaming_loopback_session(loopback_session)
        await bridge.close(assembly_socket)
        try:
            await websocket.close()
        except RuntimeError:
            pass
