import asyncio
import ast
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import grpc_server
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


def test_health_real_rpc_has_no_audio_auth_or_provider_side_effects(monkeypatch):
    monkeypatch.setattr(grpc_server.settings, 'GRPC_STT_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'GRPC_ANSWER_STREAM_ENABLED', True)
    monkeypatch.setattr(grpc_server.settings, 'USE_GRPC_AUTO_PIPELINE', True)
    monkeypatch.setattr(grpc_server.settings, 'USE_GRPC_CLOUD_CONTEXT_PIPELINE', True)
    monkeypatch.setattr(grpc_server.settings, 'ASSEMBLYAI_API_KEY', 'synthetic-not-used')
    monkeypatch.setattr(grpc_server, 'system_capture_available', lambda: True)
    monkeypatch.setattr(grpc_server.InterviewRealtimeService, 'StreamInterview',
                        lambda *args: (_ for _ in ()).throw(AssertionError('health opened interview')))

    async def exercise():
        server, port = await grpc_server.start_server(port=0)
        try:
            async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
                health = await rpc.InterviewRealtimeServiceStub(channel).CheckHealth(pb.Empty(), timeout=1)
                assert health.stt_available and health.answer_stream_available and health.auto_available
                assert health.cloud_context_available and health.system_audio_available and health.combined_audio_available
                monkeypatch.setattr(grpc_server.settings, 'ASSEMBLYAI_API_KEY', '')
                health = await rpc.InterviewRealtimeServiceStub(channel).CheckHealth(pb.Empty(), timeout=1)
                assert not health.stt_available and not health.answer_stream_available and not health.auto_available and not health.system_audio_available and not health.combined_audio_available
        finally:
            await server.stop(0)
    asyncio.run(exercise())


def test_fastapi_owns_opt_in_grpc_and_rest_survives_start_failure(monkeypatch):
    # Execute the actual lifespan without importing unrelated eager Whisper adapters.
    # Other tests deliberately stub scipy; importing the whole app is order-dependent.
    path = Path(__file__).resolve().parents[1] / 'app' / 'main.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'lifespan')
    from app.commercial.catalog_database import CatalogDatabase
    from app.commercial.subscription_database import SubscriptionDatabase
    from starlette.concurrency import run_in_threadpool

    for flag in ('CATALOG_DRAFTS_ENABLED', 'CATALOG_PUBLIC_ENABLED', 'CATALOG_LIFECYCLE_ENABLED',
                 'SUBSCRIPTIONS_ENABLED', 'BILLING_ADMIN_ENABLED',
                 'BILLING_NOTIFICATIONS_ENABLED'):
        monkeypatch.setattr(grpc_server.settings, flag, 'false')
    namespace = {'asynccontextmanager': asynccontextmanager, 'settings': grpc_server.settings, 'logging': logging,
                 'CatalogDatabase': CatalogDatabase, 'SubscriptionDatabase': SubscriptionDatabase,
                 'run_in_threadpool': run_in_threadpool}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    lifespan, app = namespace['lifespan'], SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(grpc_server.settings, 'GRPC_REALTIME_ENABLED', True)
    stop = AsyncMock()
    start = AsyncMock(return_value=(type('Server', (), {'stop': stop})(), 50051))
    monkeypatch.setattr(grpc_server, 'start_server', start)

    async def exercise():
        async with lifespan(app):
            assert start.await_count == 1
            stop.assert_not_awaited()
        stop.assert_awaited_once_with(grace=2)
        start.side_effect = RuntimeError('synthetic bind failure')
        async with lifespan(app):
            pass  # REST app still starts, no privileged or provider calls.
        monkeypatch.setattr(grpc_server.settings, 'GRPC_REALTIME_ENABLED', False)
        start.reset_mock()
        async with lifespan(app):
            pass
        start.assert_not_awaited()
    asyncio.run(exercise())
