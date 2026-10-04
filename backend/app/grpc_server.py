"""Experimental loopback-only transport skeleton; no auth, STT or generation integration."""
import argparse
import asyncio
import ipaddress
import time

import grpc

from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


class InterviewRealtimeService(rpc.InterviewRealtimeServiceServicer):
    async def StreamInterview(self, request_iterator, context):
        session_id = None
        sequence = 0

        def event(request, kind, payload):
            nonlocal sequence
            sequence += 1
            return pb.InterviewServerEvent(
                session_id=session_id or "", request_id=request.request_id,
                sequence_number=sequence, timestamp_ms=int(time.time() * 1000),
                provider="none", **{kind: payload},
            )

        async for request in request_iterator:
            kind = request.WhichOneof("event")
            if kind == "ping":
                yield event(request, "pong", pb.Empty())
            elif kind in ("cancel", "end_session"):
                yield event(request, "status", pb.Status(code="canceled" if kind == "cancel" else "ended",
                                                         message="Stream closed."))
                return
            elif kind == "start_session":
                if session_id is not None or not request.session_id or len(request.session_id) > 128:
                    yield event(request, "error", pb.ErrorEvent(code="invalid_session", message="A single valid session is required."))
                    return
                session_id = request.session_id
                yield event(request, "ready", pb.Empty())
                yield event(request, "status", pb.Status(code="foundation_only", message="Transport ready; transcription and generation are not implemented."))
            elif kind in ("audio_chunk", "manual_stop"):
                if session_id is None or request.session_id != session_id:
                    yield event(request, "error", pb.ErrorEvent(code="invalid_session", message="Start the stream session first."))
                    return
                yield event(request, "status", pb.Status(code="not_implemented", message="Transcription and generation are not implemented."))
            else:
                yield event(request, "error", pb.ErrorEvent(code="invalid_event", message="Unsupported client event."))
                return


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
