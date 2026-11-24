"""Real loopback gRPC transport; deterministic authority and cloud-context boundary."""

import asyncio
from types import SimpleNamespace

import grpc
import pytest
from app import grpc_server
from app.grpc_cloud_context import GrpcCloudContext
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc
from fastapi import HTTPException


@pytest.mark.parametrize("access_status", [403, 503])
def test_staff_restriction_denies_active_stream_and_contextless_reconnect(
    monkeypatch, access_status
):
    for flag in (
        "GRPC_STT_ENABLED",
        "GRPC_ANSWER_STREAM_ENABLED",
        "HOSTED_COMMERCIAL_MODE",
    ):
        monkeypatch.setattr(grpc_server.settings, flag, False)
    monkeypatch.setattr(grpc_server.settings, "SUBSCRIPTIONS_ENABLED", "false")
    monkeypatch.setattr(grpc_server.settings, "GRPC_STT_ENABLED", True)
    monkeypatch.setattr(grpc_server.settings, "GRPC_ANSWER_STREAM_ENABLED", True)
    monkeypatch.setattr(grpc_server.settings, "USE_GRPC_AUTO_PIPELINE", True)
    monkeypatch.setattr(
        grpc_server.settings, "ASSEMBLYAI_API_KEY", "synthetic-not-a-provider-key"
    )
    monkeypatch.setattr(grpc_server.settings, "USE_GRPC_CLOUD_CONTEXT_PIPELINE", True)
    from app.services.assemblyai_streaming import AssemblyAIStreamingBridge

    class Socket:
        started = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.started:
                self.started = True
                return '{"type":"Begin"}'
            await asyncio.Future()

        async def send(self, data):
            pass

        async def close(self):
            pass

    async def connect(self):
        return Socket()

    monkeypatch.setattr(AssemblyAIStreamingBridge, "connect", connect)

    class Authority:
        restricted = False
        checks = 0

        def record_attempt(self, document):
            assert document["account_id"] == "synthetic"

        def product_access(self, subject):
            assert subject == "synthetic"
            self.checks += 1
            if self.restricted:
                raise HTTPException(access_status)

    authority = Authority()

    def authorize(cls, start, metadata, subscriptions=None, administration=None):
        assert administration is authority
        return SimpleNamespace(user_id="synthetic")

    monkeypatch.setattr(GrpcCloudContext, "authorize", classmethod(authorize))

    async def exercise():
        server, port = await grpc_server.start_server(port=0, administration=authority)
        try:
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = rpc.InterviewRealtimeServiceStub(channel)
                denied = stub.StreamInterview(timeout=5)
                await denied.write(
                    pb.InterviewClientEvent(
                        session_id="no-context",
                        start_session=pb.StartSession(mode="manual"),
                    )
                )
                event = await denied.read()
                assert event.error.code == "auth_required"
                call = stub.StreamInterview(timeout=5)
                await call.write(
                    pb.InterviewClientEvent(
                        session_id="synthetic",
                        start_session=pb.StartSession(
                            mode="auto_pipeline",
                            source="microphone",
                            cloud_context_requested=True,
                        ),
                    )
                )
                events = []
                while True:
                    value = await call.read()
                    assert value is not grpc.aio.EOF, events
                    events.append(str(value))
                    if value.WhichOneof("event") == "ready":
                        break
                # Drain startup notifications before changing authority. A
                # queued, already-authorized status is not a restriction leak.
                await call.write(pb.InterviewClientEvent(ping=pb.Empty()))
                while True:
                    value = await call.read()
                    assert value is not grpc.aio.EOF, events
                    if value.WhichOneof("event") == "pong":
                        break
                authority.restricted = True
                await call.write(pb.InterviewClientEvent(ping=pb.Empty()))
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await call.read()
                assert error.value.code() == (
                    grpc.StatusCode.PERMISSION_DENIED
                    if access_status == 403
                    else grpc.StatusCode.UNAVAILABLE
                )
                assert authority.checks > 0
        finally:
            await server.stop(0)

    asyncio.run(exercise())
