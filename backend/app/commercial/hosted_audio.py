"""Default-off client PCM relay. No server-side microphone/loopback capture."""

import asyncio
import json
import time
from collections import deque
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from google.protobuf.json_format import MessageToDict
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from app.commercial.admin_access import verified_actor
from app.commercial.catalog_contract import Identifier
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.hosted_coordination import HostedCoordination
from app.commercial.subscription_auto import AccountAutoLease
from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb

router = APIRouter()
PATH = "/api/account/audio/stream"


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stream_id: Identifier
    session_id: Identifier
    source: Literal["microphone", "system", "both"]
    selected_resume_id: Identifier | None = None
    selected_job_context_id: Identifier | None = None


@router.get("/api/account/audio/capabilities")
async def capabilities(request: Request):
    headers = {"Cache-Control": "no-store"}
    if not (
        settings.HOSTED_AUDIO_ENABLED
        and settings.HOSTED_AUDIO_DEPLOYMENT_ID
        and settings.SUBSCRIPTIONS_ENABLED == "true"
        and settings.USE_GRPC_AUTO_PIPELINE
        and settings.GRPC_STT_ENABLED
        and settings.GRPC_ANSWER_STREAM_ENABLED
        and settings.ENABLE_SESSION_ANSWER_MODELS
        and settings.ASSEMBLYAI_API_KEY
    ):
        return JSONResponse(
            {"error": "subscription_unavailable"}, status_code=503, headers=headers
        )
    try:
        actor = await asyncio.to_thread(verified_actor, request)
        service = request.app.state.subscriptions.service()
        resolved = await asyncio.to_thread(service.resolve, actor)
        entitlement = next(
            (
                item
                for item in resolved["snapshot"].terms.entitlements
                if item.feature == "assistant.auto" and item.allowed
            ),
            None,
        )
        if entitlement is None:
            return JSONResponse(
                {"error": "subscription_denied"}, status_code=403, headers=headers
            )
        sources = entitlement.audio_sources
        return JSONResponse(
            {
                "protocol_version": 1,
                "deployment_id": settings.HOSTED_AUDIO_DEPLOYMENT_ID,
                "stt_available": True,
                "answer_stream_available": True,
                "auto_available": True,
                "cloud_context_available": True,
                "system_audio_available": "system" in sources,
                "combined_audio_available": "both" in sources,
            },
            headers=headers,
        )
    except HTTPException as error:
        return JSONResponse(
            {"error": "auth_invalid"}, status_code=error.status_code, headers=headers
        )
    except CatalogStoreError as error:
        return JSONResponse(
            {
                "error": (
                    "subscription_denied"
                    if error.code == ErrorCode.DENIED
                    else "subscription_unavailable"
                )
            },
            status_code=403 if error.code == ErrorCode.DENIED else 503,
            headers=headers,
        )


class Relay:
    def __init__(self, service, start: Start):
        self.coordination = HostedCoordination(service)
        self.stream_id, self.session_id = start.stream_id, start.session_id
        self.lease: AccountAutoLease | None = None
        self.arrivals: deque[float] = deque(maxlen=21)

    async def accept(self, sequence: int, data: bytes) -> bool:
        if self.lease is None:
            raise PermissionError("Authorization required")
        self.arrivals.append(time.monotonic())
        if len(self.arrivals) == 21 and self.arrivals[-1] - self.arrivals[0] < 1:
            raise ValueError("Audio packet rate exceeded")
        await self.lease.authorize()
        return await asyncio.to_thread(
            self.coordination.frame, self.lease, self.session_id, sequence, data
        )

    async def wait_for_end(self) -> str:
        # Recheck an idle socket too: no client ping is needed to observe a
        # deletion/permission barrier. Authorization checks never renew the lease.
        assert self.lease is not None
        while not self.lease.stopped and self.lease.remaining() > 0:
            await asyncio.sleep(min(0.5, self.lease.remaining()))
            try:
                await self.lease.authorize()
            except PermissionError:
                return "subscription_auto_expired"
            except CatalogStoreError as error:
                return (
                    "subscription_auto_expired"
                    if self.lease.remaining() <= 0
                    else (
                        "subscription_denied"
                        if error.code == ErrorCode.DENIED
                        else "subscription_unavailable"
                    )
                )
        return "subscription_auto_expired"


@router.websocket(PATH)
async def hosted_audio(websocket: WebSocket):
    # This route has its own explicit composition. It never opens legacy ingress.
    if not (
        settings.HOSTED_AUDIO_ENABLED
        and settings.HOSTED_AUDIO_DEPLOYMENT_ID
        and settings.SUBSCRIPTIONS_ENABLED == "true"
        and settings.USE_GRPC_AUTO_PIPELINE
        and settings.GRPC_STT_ENABLED
        and settings.GRPC_ANSWER_STREAM_ENABLED
        and settings.ENABLE_SESSION_ANSWER_MODELS
    ):
        await websocket.close(code=1008)
        return
    origins = {
        value.strip()
        for value in settings.HOSTED_AUDIO_ORIGINS.split(",")
        if value.strip()
    }
    if (
        not origins
        or websocket.headers.get("origin") not in origins
        or websocket.scope.get("query_string")
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept(headers=[(b"cache-control", b"no-store")])
    stream = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), 5)
        if len(raw.encode()) > 16384:
            raise ValueError("Oversize start")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise TypeError("Start must be an object")
        # Browser WebSocket cannot set Authorization. A first-frame bearer is
        # accepted only on this exact route, never a URL/query/cookie identity.
        token = document.pop("bearer", None)
        scope = {**websocket.scope, "type": "http"}
        if token is not None:
            if (
                websocket.headers.get("authorization")
                or not isinstance(token, str)
                or len(token) > 8192
            ):
                raise ValueError("Ambiguous authentication")
            scope["headers"] = [
                *scope["headers"],
                (b"authorization", ("Bearer " + token).encode()),
            ]
        if sum(key.lower() == b"authorization" for key, _ in scope["headers"]) != 1:
            raise HTTPException(401)
        start = Start.model_validate(document)
        runtime = websocket.app.state.subscriptions
        actor = await asyncio.to_thread(verified_actor, Request(scope))
        relay = Relay(runtime.service(), start)
        await asyncio.to_thread(
            relay.coordination.claim_stream, actor, start.stream_id, start.session_id
        )
        metadata = (("authorization", "Bearer " + actor._bearer),)

        async def abort(*_):
            raise PermissionError("Relay unavailable")

        context = SimpleNamespace(invocation_metadata=lambda: metadata, abort=abort)

        async def requests():
            yield pb.InterviewClientEvent(
                session_id=start.stream_id,
                request_id="relay-start",
                start_session=pb.StartSession(
                    mode="auto_pipeline",
                    source=start.source,
                    active_session_id=start.session_id,
                    cloud_context_requested=True,
                    answer_stream_version=1,
                    selected_resume_id=start.selected_resume_id or "",
                    selected_job_context_id=start.selected_job_context_id or "",
                ),
            )
            while True:
                frame = await asyncio.wait_for(websocket.receive(), 20)
                if frame["type"] == "websocket.disconnect":
                    return
                data = frame.get("bytes")
                if data is not None:
                    if not 10 <= len(data) <= 6408 or len(data) % 2:
                        raise ValueError("Invalid PCM frame")
                    sequence = int.from_bytes(data[:8], "big")
                    yield pb.InterviewClientEvent(
                        session_id=start.stream_id,
                        request_id="relay-pcm",
                        sequence_number=sequence,
                        audio_chunk=pb.AudioChunk(
                            audio=data[8:],
                            sample_rate=16000,
                            channels=1,
                            encoding="linear16",
                        ),
                    )
                else:
                    text = frame.get("text", "")
                    if len(text) > 128 or text not in ("ping", "stop"):
                        raise ValueError("Invalid relay control")
                    yield pb.InterviewClientEvent(
                        session_id=start.stream_id,
                        request_id="relay-" + text,
                        **(
                            {"ping": pb.Empty()}
                            if text == "ping"
                            else {"end_session": pb.Empty()}
                        )
                    )
                    if text == "stop":
                        return

        from app.grpc_server import InterviewRealtimeService

        stream = InterviewRealtimeService(runtime, client_relay=relay).StreamInterview(
            requests(), context
        )
        async for event in stream:
            # Same existing owned durable answer DTO, no run owner capability.
            await asyncio.wait_for(
                websocket.send_json(
                    MessageToDict(event, preserving_proto_field_name=True)
                ),
                2,
            )
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except (
        HTTPException,
        CatalogStoreError,
        ValueError,
        TypeError,
        asyncio.TimeoutError,
        RuntimeError,
        OSError,
    ) as error:
        # No raw exception, audio, bearer or provider details escape this boundary.
        try:
            code = (
                (
                    "auth_invalid"
                    if error.status_code == 401
                    else (
                        "subscription_denied"
                        if error.status_code == 403
                        else "subscription_relay_unavailable"
                    )
                )
                if isinstance(error, HTTPException)
                else "subscription_relay_unavailable"
            )
            if isinstance(error, CatalogStoreError):
                if error.code == ErrorCode.IDENTITY_CONFLICT:
                    code = "subscription_relay_replay"
                elif error.code == ErrorCode.DENIED:
                    code = "subscription_denied"
            await websocket.send_json({"error": {"code": code}})
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        if stream is not None:
            await stream.aclose()
        try:
            await websocket.close(code=1000)
        except (WebSocketDisconnect, RuntimeError):
            pass
