"""Actual loopback gRPC: quarantine at admission and after an active stream."""

import asyncio
import threading

import grpc
import pytest
from app import grpc_server
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


def test_quarantine_denies_new_and_active_grpc(monkeypatch):
    for flag in (
        "GRPC_STT_ENABLED",
        "GRPC_ANSWER_STREAM_ENABLED",
        "HOSTED_COMMERCIAL_MODE",
    ):
        monkeypatch.setattr(grpc_server.settings, flag, False)
    monkeypatch.setattr(grpc_server.settings, "SUBSCRIPTIONS_ENABLED", "false")
    ready = threading.Event()

    async def exercise():
        server, port = await grpc_server.start_server(port=0, readiness=ready.is_set)
        try:
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                denied = stub.StreamInterview(timeout=5)
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await denied.read()
                assert error.value.code() == grpc.StatusCode.UNAVAILABLE
                ready.set()
                call = stub.StreamInterview(timeout=5)
                await call.write(
                    pb.InterviewClientEvent(
                        session_id="synthetic",
                        start_session=pb.StartSession(mode="manual"),
                    )
                )
                assert (await call.read()).WhichOneof("event") == "ready"
                assert (await call.read()).status.code == "foundation_only"
                ready.clear()
                await call.write(pb.InterviewClientEvent(ping=pb.Empty()))
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await call.read()
                assert error.value.code() == grpc.StatusCode.UNAVAILABLE
        finally:
            await server.stop(0)

    asyncio.run(exercise())
