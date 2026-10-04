"""Experimental loopback-only realtime transport; optional STT, no generation."""
import argparse
import asyncio
import ipaddress
import json
import time

import grpc

from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


class InterviewRealtimeService(rpc.InterviewRealtimeServiceServicer):
    async def StreamInterview(self, request_iterator, context):
        # Bounded output queue lets provider events arrive independently of audio input.
        output = asyncio.Queue(maxsize=32)
        session_id = None
        sequence = 0
        total_chunks = total_audio_bytes = 0
        bridge = socket = receiver = None
        stt_enabled = settings.GRPC_STT_ENABLED
        last_request_id = ""
        provider_started = asyncio.Event()
        final_received = asyncio.Event()
        transcript_received = False
        final_transcript_received = False
        stopping_stt = False
        stt_chunks = stt_bytes = callbacks = non_silent_chunks = 0

        def event(request_id, kind, payload):
            nonlocal sequence
            sequence += 1
            return pb.InterviewServerEvent(
                session_id=session_id or "", request_id=request_id,
                sequence_number=sequence, timestamp_ms=int(time.time() * 1000),
                provider="assemblyai_streaming" if stt_enabled else "none", **{kind: payload})

        async def emit(request_id, kind, payload):
            await output.put(event(request_id, kind, payload))

        async def receive_transcripts():
            nonlocal transcript_received, final_transcript_received, callbacks
            try:
                async for raw in socket:
                    message = json.loads(raw)
                    callbacks += 1
                    kind = message.get("type")
                    if kind == "Begin":
                        provider_started.set()
                    elif kind == "Turn":
                        text = message.get("transcript", "")
                        if isinstance(text, str) and text.strip():
                            transcript_received = True
                            if message.get("end_of_turn"):
                                final_transcript_received = True
                                final_received.set()
                            await emit(last_request_id,
                                "final_transcript" if message.get("end_of_turn") else "partial_transcript",
                                pb.TextEvent(text=text[:65536]))
                    elif kind == "Termination":
                        if not stopping_stt:
                            raise RuntimeError("provider terminated unexpectedly")
                        return
                    elif kind == "Error" or message.get("error"):
                        raise RuntimeError("provider unavailable")
                raise RuntimeError("provider disconnected")
            except asyncio.CancelledError:
                raise
            except Exception:
                await emit(last_request_id, "error", pb.ErrorEvent(
                    code="stt_unavailable", message="Live STT unavailable. Check provider configuration and retry."))
                await output.put(None)

        async def close_stt():
            nonlocal socket, receiver
            if receiver and not receiver.done():
                receiver.cancel()
            if receiver:
                await asyncio.gather(receiver, return_exceptions=True)
            if socket:
                try:
                    await asyncio.wait_for(socket.close(), timeout=2)
                except Exception:
                    pass
            socket = receiver = None

        async def open_stt():
            nonlocal bridge, socket, receiver, transcript_received, final_transcript_received, stopping_stt
            from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
            bridge = AssemblyAIStreamingBridge()
            # G3 PCM is always 16 kHz regardless of the production WS configuration.
            bridge.config.sample_rate = 16000
            socket = await asyncio.wait_for(bridge.connect(), timeout=5)
            provider_started.clear()
            final_received.clear()
            transcript_received = False
            final_transcript_received = False
            stopping_stt = False
            receiver = asyncio.create_task(receive_transcripts())
            # WebSocket upgrade alone is not provider readiness (Begin confirms it).
            await asyncio.wait_for(provider_started.wait(), timeout=3)

        async def process_requests():
            nonlocal session_id, total_chunks, total_audio_bytes, last_request_id, stopping_stt, stt_chunks, stt_bytes, non_silent_chunks
            canceled = False
            try:
                async for request in request_iterator:
                    last_request_id = request.request_id
                    kind = request.WhichOneof("event")
                    if kind == "ping":
                        await emit(request.request_id, "pong", pb.Empty())
                    elif kind in ("cancel", "end_session"):
                        await close_stt()
                        await emit(request.request_id, "status", pb.Status(
                            code="canceled" if kind == "cancel" else "ended", message="Stream closed."))
                        return
                    elif kind == "start_session":
                        if session_id is not None or not request.session_id or len(request.session_id) > 128:
                            await emit(request.request_id, "error", pb.ErrorEvent(
                                code="invalid_session", message="A single valid session is required."))
                            return
                        session_id = request.session_id
                        if stt_enabled:
                            await open_stt()
                        await emit(request.request_id, "ready", pb.Empty())
                        await emit(request.request_id, "status", pb.Status(
                            code="stt_enabled" if stt_enabled else "foundation_only",
                            message="Experimental live STT ready." if stt_enabled else "Transport ready; transcription and generation are not implemented."))
                    elif kind in ("audio_chunk", "manual_stop"):
                        if session_id is None or request.session_id != session_id:
                            await emit(request.request_id, "error", pb.ErrorEvent(
                                code="invalid_session", message="Start the stream session first."))
                            return
                        if kind == "audio_chunk":
                            chunk = request.audio_chunk
                            if not chunk.audio or len(chunk.audio) > 65536 or len(chunk.audio) % 2 or chunk.sample_rate != 16000 or chunk.channels != 1 or chunk.encoding != "linear16":
                                await emit(request.request_id, "error", pb.ErrorEvent(
                                    code="invalid_audio", message="Expected bounded mono 16 kHz linear16 PCM."))
                                return
                            if stt_enabled:
                                if socket is None:
                                    await open_stt()
                                await asyncio.wait_for(socket.send(chunk.audio), timeout=2)
                                stt_chunks += 1
                                stt_bytes += len(chunk.audio)
                                if any(chunk.audio):
                                    non_silent_chunks += 1
                            total_chunks += 1
                            total_audio_bytes += len(chunk.audio)
                        elif stt_enabled and socket:
                            # Terminate drains final events; do not use bridge helpers that log exception details.
                            stopping_stt = True
                            final_received.clear()
                            await asyncio.wait_for(socket.send(json.dumps({"type": "ForceEndpoint"})), timeout=2)
                            try:
                                await asyncio.wait_for(final_received.wait(), timeout=0.7)
                            except asyncio.TimeoutError:
                                pass
                            await asyncio.wait_for(socket.send(json.dumps({"type": "Terminate"})), timeout=2)
                            try:
                                await asyncio.wait_for(asyncio.shield(receiver), timeout=1)
                            except asyncio.TimeoutError:
                                pass
                            await close_stt()
                            if not final_transcript_received:
                                await emit(request.request_id, "error", pb.ErrorEvent(
                                    code="no_transcript", message="No final speech transcript received. Check microphone input and retry."))
                        await emit(request.request_id, "status", pb.Status(
                            code="audio_chunk_received" if kind == "audio_chunk" else "audio_stopped",
                            message="Audio accepted; no answer generation." if stt_enabled else "Audio counted only; transcription and generation are not implemented.",
                            total_chunks=total_chunks, total_audio_bytes=total_audio_bytes,
                            stt_chunks_forwarded=stt_chunks, stt_bytes_forwarded=stt_bytes,
                            stt_bridge_connected=bool(socket and provider_started.is_set()),
                            stt_callback_count=callbacks, non_silent_chunks=non_silent_chunks,
                            stt_status=("stt_no_transcript_yet" if stt_enabled and stt_chunks >= 50 and not transcript_received
                                        else "stt_receiving" if stt_enabled and socket else "idle")))
                    else:
                        await emit(request.request_id, "error", pb.ErrorEvent(
                            code="invalid_event", message="Unsupported client event."))
                        return
            except asyncio.CancelledError:
                canceled = True
                raise
            except Exception:
                await emit(last_request_id, "error", pb.ErrorEvent(
                    code="stt_unavailable", message="Live STT unavailable. Check provider configuration and retry."))
            finally:
                if not canceled:
                    await output.put(None)

        task = asyncio.create_task(process_requests())
        try:
            while True:
                value = await output.get()
                if value is None:
                    break
                yield value
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await close_stt()


async def start_server(host="127.0.0.1", port=50051, max_message_mb=4):
    # There is no authentication/TLS integration in G1. Never bind externally.
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise ValueError("G1 gRPC is restricted to loopback hosts.")
    if not 0 <= port <= 65535 or not 1 <= max_message_mb <= 64:
        raise ValueError("Invalid gRPC port or message limit.")
    limit = max_message_mb * 1024 * 1024
    server = grpc.aio.server(options=[("grpc.max_receive_message_length", limit),
                                      ("grpc.max_send_message_length", limit)])
    rpc.add_InterviewRealtimeServiceServicer_to_server(InterviewRealtimeService(), server)
    address = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    bound_port = server.add_insecure_port(address)
    if not bound_port:
        raise RuntimeError("Unable to bind local gRPC server.")
    await server.start()
    return server, bound_port


async def serve(host, port):
    server, _ = await start_server(host, port, settings.GRPC_MAX_MESSAGE_MB)
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=2)


def main():
    parser = argparse.ArgumentParser(description="Experimental local gRPC foundation")
    parser.add_argument("--host", default=settings.GRPC_REALTIME_HOST)
    parser.add_argument("--port", type=int, default=settings.GRPC_REALTIME_PORT)
    args = parser.parse_args()
    if not settings.GRPC_REALTIME_ENABLED:
        parser.error("Set GRPC_REALTIME_ENABLED=true to explicitly enable the standalone server.")
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
