"""Loopback-only subprocess fixture. Configuration is synthetic stdin, never CLI."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    import os
    import socket
    import types

    import dotenv

    config = json.loads(sys.stdin.readline())
    staging = config.get("staging")
    if staging:
        import threading
        from datetime import datetime, timezone

        import smoke_staging_session_pooler as approval

        approval.require_window()
        # Credential expiry alone cannot revoke an established DB connection.
        # Process death at the fixed cutoff closes ALL owned sockets, including
        # checked-out connections; no environment/config input extends this timer.
        stop_timer = threading.Timer(
            max(0, (approval.DEADLINE - datetime.now(timezone.utc)).total_seconds()),
            lambda: os._exit(3),
        )
        stop_timer.daemon = True
        stop_timer.start()
        from app.commercial.executor_connection import (
            STAGING_PROJECT,
            STAGING_SESSION_HOST,
        )

        if (
            staging.get("project") != STAGING_PROJECT
            or staging.get("host") != STAGING_SESSION_HOST
        ):
            raise RuntimeError("unapproved staging target")
    permitted = {"127.0.0.1", "::1", "localhost"}
    if staging:
        # Resolve only pinned hosts; libpq additionally enforces its own host/TLS guard.
        for host in (STAGING_SESSION_HOST, STAGING_PROJECT + ".supabase.co"):
            permitted.add(host)
            permitted.update(row[4][0] for row in socket.getaddrinfo(host, None))

    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False"
    )
    connect_socket = socket.socket.connect
    resolve_socket = socket.getaddrinfo

    def approved_host(host, *args, **kwargs):
        if host not in permitted:
            raise PermissionError("Isolated worker forbids unapproved hostname")
        return resolve_socket(host, *args, **kwargs)

    socket.getaddrinfo = approved_host

    def loopback_only(sock, address):
        if isinstance(address, tuple) and address[0] not in permitted:
            raise PermissionError("Isolated worker forbids outbound network")
        return connect_socket(sock, address)

    socket.socket.connect = loopback_only
    pdf = types.ModuleType("fitz")

    def no_pdf(*_args, **_kwargs):
        raise AssertionError("PDF outside isolated TXT relay acceptance")

    pdf.open = no_pdf
    sys.modules["fitz"] = pdf

    dotenv.load_dotenv = lambda *a, **kw: False
    if config["host"] != "127.0.0.1" or (
        not staging and not isinstance(config["pg_port"], int)
    ):
        raise RuntimeError("Isolated loopback configuration required")
    import uvicorn
    from app.auth import supabase_auth
    from app.commercial.boundary import CommercialBoundaryMiddleware
    from app.commercial.hosted_audio import router
    from app.commercial.subscription_database import SubscriptionDatabase
    from app.config import settings
    from app.services.assemblyai_streaming import AssemblyAIStreamingBridge
    from fastapi import FastAPI

    for name in (
        "HOSTED_COMMERCIAL_MODE",
        "HOSTED_AUDIO_ENABLED",
        "GRPC_STT_ENABLED",
        "GRPC_ANSWER_STREAM_ENABLED",
        "USE_GRPC_AUTO_PIPELINE",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
        "ENABLE_SESSION_ANSWER_MODELS",
    ):
        setattr(settings, name, True)
    settings.SUBSCRIPTIONS_ENABLED = "true"
    settings.HOSTED_AUDIO_ORIGINS = (
        f"https://synthetic.invalid,http://127.0.0.1:{config['http_port']}"
    )
    settings.HOSTED_AUDIO_DEPLOYMENT_ID = "synthetic.relay.v1"
    settings.ASSEMBLYAI_API_KEY = "synthetic-never-sent"
    if staging:
        os.environ.update(
            SAIIA_CLOUD_MODE="cloud",
            SUPABASE_URL="https://" + STAGING_PROJECT + ".supabase.co",
            SUPABASE_ANON_KEY=staging["anon_key"],
            SUPABASE_SERVICE_ROLE_KEY=staging["service_key"],
            SUPABASE_RESUME_BUCKET="resumes",
            SUPABASE_EXPORT_BUCKET="exports",
            SUPABASE_JWT_SECRET_OR_JWKS_CONFIG="https://"
            + STAGING_PROJECT
            + ".supabase.co/auth/v1/.well-known/jwks.json",
        )
        # Real existing verifier/configuration; no synthetic bearer override.
    else:
        if config.get("application"):
            from urllib.parse import urlsplit

            if urlsplit(config["local_auth_url"]).hostname != "127.0.0.1":
                raise RuntimeError("local Auth substitute must be loopback")
            os.environ.update(
                SAIIA_CLOUD_MODE="cloud",
                SUPABASE_URL=config["local_auth_url"],
                SUPABASE_ANON_KEY=config["anon_key"],
            )
        supabase_auth.get_auth_verification_config = (
            lambda: supabase_auth.AuthVerificationConfig(
                "legacy_secret",
                config["jwt_key"],
                "https://synthetic.invalid/auth/v1",
                "authenticated",
            )
        )
    if config.get("answers"):
        from app import grpc_answer_pipeline
        from app.api import generate as generation
        from app.nlp.answer_generator import ProviderResult

        settings.ENABLE_SEMANTIC_VALIDATION = False
        settings.ENABLE_CONTROLLED_ANSWER_VARIATION = False
        settings.ENABLE_INCREMENTAL_ANSWER_STREAMING = False

        def provider(**_kwargs):
            return ProviderResult(
                answer=(
                    "Dependency injection supplies dependencies externally. Synthetic worker "
                    + str(config["http_port"])
                    + "."
                    if config.get("application")
                    else "Synthetic hosted answer"
                ),
                provider="synthetic",
                model="synthetic",
                primary_provider="synthetic",
                primary_model="synthetic",
                fallback_used=False,
                generation_ms=0,
                error=None,
            )

        generation.generator._default._generate_with_primary_provider = provider

        async def detect(*_args, **_kwargs):
            return "What is dependency injection?", ""

        grpc_answer_pipeline.detect_intake_question = detect
    forwarded = 0

    class Socket:
        def __init__(self):
            self.answered = False
            self.events = asyncio.Queue()
            self.events.put_nowait(json.dumps({"type": "Begin"}))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.events.get()

        async def send(self, data):
            nonlocal forwarded
            if isinstance(data, bytes):
                forwarded += 1
                if config.get("answers") and not self.answered:
                    self.answered = True
                    await self.events.put(
                        json.dumps(
                            {
                                "type": "Turn",
                                "transcript": "Explain dependency injection",
                                "turn_order": 0,
                                "end_of_turn": True,
                            }
                        )
                    )

        async def close(self):
            pass

    async def connect(_):
        return Socket()

    AssemblyAIStreamingBridge.connect = connect
    from app.commercial.executor_connection import SessionPooler
    from psycopg.conninfo import make_conninfo

    def dsn(role):
        if staging:
            return make_conninfo(
                host=staging["host"],
                port=5432,
                dbname="postgres",
                user=role + "." + STAGING_PROJECT,
                password=staging["passwords"][role],
                sslmode="verify-full",
                sslrootcert=staging["ca"],
            )
        return make_conninfo(
            host="127.0.0.1",
            port=config["pg_port"],
            dbname="postgres",
            user=role,
            sslmode="disable",
        )

    target = SessionPooler(staging["host"]) if staging else None
    runtime = SubscriptionDatabase("true", dsn("usage_executor"), session_pooler=target)
    runtime.start()
    if runtime._pool is None:
        raise RuntimeError("Isolated database unavailable")
    app = FastAPI()
    app.state.subscriptions = runtime
    app.add_middleware(CommercialBoundaryMiddleware)
    app.include_router(router)
    catalogs = []
    if config.get("application"):
        from app.api.interview_sessions import router as sessions
        from app.commercial.admin import router as admin
        from app.commercial.catalog_database import CatalogDatabase
        from app.commercial.draft_api import router as drafts
        from app.commercial.lifecycle_api import router as lifecycle
        from app.commercial.public_catalog import router as public
        from app.commercial.subscription_api import router as account

        settings.CATALOG_DRAFTS_ENABLED = "true"
        settings.CATALOG_LIFECYCLE_ENABLED = "true"
        settings.CATALOG_PUBLIC_ENABLED = "true"
        for role, attr, options in (
            ("catalog_draft_executor", "catalog_drafts", {"lifecycle_enabled": "true"}),
            ("catalog_public_reader", "catalog_public", {"public_only": True}),
        ):
            pool = CatalogDatabase("true", dsn(role), session_pooler=target, **options)
            catalogs.append(pool)
            pool.start()
            if pool._pool is None:
                raise RuntimeError("application catalog startup unavailable")
            setattr(app.state, attr, pool)
        app.include_router(drafts, prefix="/api/admin/catalog")
        app.include_router(lifecycle, prefix="/api/admin/catalog")
        app.include_router(admin, prefix="/api/commercial")
        app.include_router(public)
        app.include_router(account)
        app.include_router(sessions, prefix="/api/interview-sessions")
        from staging_application_providers import configure

        configure(app, config, staging)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=config["http_port"],
            log_level="critical",
            access_log=False,
            ws_max_size=16384,
            ws_max_queue=8,
        )
    )
    task = asyncio.create_task(server.serve())
    try:

        async def ready():
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)

        await asyncio.wait_for(ready(), 15)
        print(json.dumps({"ready": True}), flush=True)
        await task
    finally:
        runtime.close()
        for pool in catalogs:
            pool.close()
        if staging:
            stop_timer.cancel()


if __name__ == "__main__":
    asyncio.run(main())
