"""Experimental loopback-only realtime transport; opt-in STT and answer diagnostics."""
import argparse
import hashlib
import re
from collections import deque
from contextlib import aclosing
import asyncio
import ipaddress
import json
import time

import grpc

from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


AUTO_COOLDOWN_SECONDS = 4.0


class InterviewRealtimeService(rpc.InterviewRealtimeServiceServicer):
    async def StreamInterview(self, request_iterator, context):
        # Bounded output queue lets provider events arrive independently of audio input.
        output = asyncio.Queue(maxsize=32)
        session_id = None
        sequence = 0
        total_chunks = total_audio_bytes = 0
        bridge = socket = receiver = None
        stt_enabled = settings.GRPC_STT_ENABLED
        answer_enabled = stt_enabled and settings.GRPC_ANSWER_STREAM_ENABLED
        questions = asyncio.Queue(maxsize=4)
        seen = deque(maxlen=64)
        seen_turns = deque(maxlen=64)
        auto_mode = False
        auto_cooldown_until = 0.0
        manual_mode = False
        manual_stopped = False
        manual_turns = {}
        provider_epoch = 0
        answer_task = None
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
                provider=(getattr(payload, "provider", "") or ("assemblyai_streaming" if stt_enabled else "none")), **{kind: payload})

        async def emit(request_id, kind, payload):
            await output.put(event(request_id, kind, payload))

        async def answer_worker():
            nonlocal auto_cooldown_until
            from app.grpc_answer_pipeline import stream_question_answer
            while True:
                text, request_id, fingerprint, turn = await questions.get()
                if auto_mode and auto_cooldown_until > time.monotonic():
                    await asyncio.sleep(auto_cooldown_until - time.monotonic())
                    # Keep only the latest question heard during cooldown.
                    while not questions.empty():
                        questions.task_done()
                        text, request_id, fingerprint, turn = questions.get_nowait()
                    await emit(request_id, "status", pb.Status(code="auto_listening"))
                if auto_mode:
                    seen.append(fingerprint)
                    if turn is not None:
                        seen_turns.append(turn)
                async def generate():
                    nonlocal auto_cooldown_until
                    answer = ""
                    category = provider = ""
                    question_seen = completed = False
                    async with aclosing(stream_question_answer(text)) as pipeline:
                        async for item in pipeline:
                            kind = item.get("type")
                            category = item.get("category") or category
                            provider = item.get("provider") or provider
                            if kind == "question":
                                question_seen = True
                                await emit(request_id, "question_detected", pb.TextEvent(text=item["text"], category=category))
                            elif kind == "started":
                                await emit(request_id, "answer_started", pb.TextEvent(category=category, provider=provider))
                            elif kind == "delta":
                                delta = str(item.get("text") or "")
                                answer += delta
                                if len(answer) > 262144:
                                    raise RuntimeError("Answer limit exceeded.")
                                await emit(request_id, "answer_delta", pb.TextEvent(text=delta, category=category, provider=provider))
                            elif kind in ("replacement", "result") and item.get("text"):
                                answer = str(item["text"])
                                if len(answer) > 262144:
                                    raise RuntimeError("Answer limit exceeded.")
                            elif kind == "completed":
                                if not answer.strip():
                                    raise RuntimeError("Empty answer.")
                                completed = True
                                await emit(request_id, "answer_completed", pb.TextEvent(text=answer, category=category, provider=provider))
                                if auto_mode:
                                    auto_cooldown_until = time.monotonic() + AUTO_COOLDOWN_SECONDS
                                    await emit(request_id, "status", pb.Status(code="auto_cooldown"))
                    if question_seen and not completed:
                        raise RuntimeError("Answer stream ended prematurely.")
                    if manual_mode and not question_seen:
                        await emit(request_id, "status", pb.Status(code="manual_no_question", message="No clear question detected."))
                    # A non-question legitimately emits no events; never invent an answer.
                try:
                    await asyncio.wait_for(generate(), timeout=90)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await emit(request_id, "answer_error", pb.ErrorEvent(
                        code="answer_unavailable", message="Experimental answer unavailable or timed out. Retry."))
                finally:
                    questions.task_done()

        async def queue_final(text, turn_order):
            if manual_mode and not manual_stopped:
                key = turn_order if isinstance(turn_order, int) else 0
                if key not in manual_turns and len(manual_turns) >= 64:
                    raise RuntimeError("Manual capture turn limit exceeded.")
                manual_turns[key] = text
                if sum(len(value) for value in manual_turns.values()) > 65536:
                    raise RuntimeError("Manual capture text limit exceeded.")
                return
            if not answer_enabled or len(text.split()) < 3:
                return
            fingerprint = hashlib.sha256(re.sub(r"[^\w]", "", text.casefold()).encode()).digest()
            turn = (provider_epoch, turn_order) if isinstance(turn_order, int) else None
            if fingerprint in seen or (turn is not None and turn in seen_turns):
                return
            try:
                if auto_mode:
                    while not questions.empty():
                        questions.get_nowait()
                        questions.task_done()
                questions.put_nowait((text, last_request_id, fingerprint, turn))
                if not auto_mode:
                    seen.append(fingerprint)
                    if turn is not None:
                        seen_turns.append(turn)
            except asyncio.QueueFull:
                await emit(last_request_id, "answer_error", pb.ErrorEvent(
                    code="answer_busy", message="Experimental answer queue is busy. Retry after the current answer."))

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
                            preview = text[:65536]
                            if manual_mode and not manual_stopped:
                                if message.get("end_of_turn"):
                                    await queue_final(preview, message.get("turn_order"))
                                turns = {**manual_turns, message.get("turn_order", 0): preview}
                                preview = " ".join(turns[key] for key in sorted(turns))[:65536]
                            await emit(last_request_id,
                                "final_transcript" if message.get("end_of_turn") else "partial_transcript",
                                pb.TextEvent(text=preview))
                            if message.get("end_of_turn") and not manual_mode:
                                await queue_final(text[:65536], message.get("turn_order"))
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
            nonlocal bridge, socket, receiver, transcript_received, final_transcript_received, stopping_stt, provider_epoch
            from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
            bridge = AssemblyAIStreamingBridge()
            provider_epoch += 1
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

        async def stop_answers():
            if answer_task:
                answer_task.cancel()
                await asyncio.gather(answer_task, return_exceptions=True)

        async def process_requests():
            nonlocal auto_mode, manual_mode, manual_stopped, session_id, total_chunks, total_audio_bytes, last_request_id, stopping_stt, stt_chunks, stt_bytes, non_silent_chunks
            canceled = False
            try:
                async for request in request_iterator:
                    last_request_id = request.request_id
                    kind = request.WhichOneof("event")
                    if kind == "ping":
                        await emit(request.request_id, "pong", pb.Empty())
                    elif kind in ("cancel", "end_session"):
                        await stop_answers()
                        await close_stt()
                        await emit(request.request_id, "status", pb.Status(
                            code="canceled" if kind == "cancel" else "ended", message="Stream closed."))
                        return
                    elif kind == "start_session":
                        if session_id is not None or not request.session_id or len(request.session_id) > 128:
                            await emit(request.request_id, "error", pb.ErrorEvent(
                                code="invalid_session", message="A single valid session is required."))
                            return
                        auto_mode = request.start_session.mode == "auto_pipeline"
                        if auto_mode and not (settings.USE_GRPC_AUTO_PIPELINE and answer_enabled and stt_enabled):
                            await emit(request.request_id, "error", pb.ErrorEvent(code="auto_unavailable", message="Auto gRPC pipeline is unavailable."))
                            return
                        manual_mode = request.start_session.mode == "manual_pipeline"
                        if manual_mode and not (settings.USE_GRPC_MANUAL_PIPELINE and answer_enabled):
                            await emit(request.request_id, "error", pb.ErrorEvent(code="manual_unavailable", message="Manual gRPC pipeline is unavailable."))
                            return
                        session_id = request.session_id
                        if stt_enabled:
                            await open_stt()
                        if auto_mode:
                            await emit(request.request_id, "status", pb.Status(code="auto_pipeline_ready", message="Experimental Auto pipeline ready."))
                        if manual_mode:
                            await emit(request.request_id, "status", pb.Status(code="manual_pipeline_ready", message="Experimental manual pipeline ready."))
                        await emit(request.request_id, "ready", pb.Empty())
                        await emit(request.request_id, "status", pb.Status(
                            code="stt_enabled" if stt_enabled else "foundation_only",
                            message="Experimental live STT ready." if stt_enabled else "Transport ready; transcription and generation are not implemented."))
                        if answer_enabled:
                            await emit(request.request_id, "status", pb.Status(code="answer_stream_enabled", message="Experimental answer streaming enabled."))
                    elif kind in ("audio_chunk", "manual_stop"):
                        if session_id is None or request.session_id != session_id:
                            await emit(request.request_id, "error", pb.ErrorEvent(
                                code="invalid_session", message="Start the stream session first."))
                            return
                        if kind == "audio_chunk" and manual_mode and manual_stopped:
                            await emit(request.request_id, "error", pb.ErrorEvent(code="manual_stopped", message="Start a new manual capture."))
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
                        if kind == "manual_stop" and manual_mode and not manual_stopped:
                            manual_stopped = True
                            text = " ".join(manual_turns[key] for key in sorted(manual_turns)).strip()
                            if len(text.split()) >= 3:
                                await emit(request.request_id, "status", pb.Status(code="manual_generation_committed", message="Detecting question."))
                                await queue_final(text, None)
                            else:
                                await emit(request.request_id, "status", pb.Status(code="manual_no_question", message="No clear question detected."))
                        await emit(request.request_id, "status", pb.Status(
                            code="audio_chunk_received" if kind == "audio_chunk" else "audio_stopped",
                            message=("Audio accepted; experimental answers enabled." if answer_enabled else "Audio accepted; no answer generation.") if stt_enabled else "Audio counted only; transcription and generation are not implemented.",
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

        if answer_enabled:
            answer_task = asyncio.create_task(answer_worker())
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
            await stop_answers()


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
