"""Opt-in loopback physical-device setup. No live STT, LLM or shared storage."""

import asyncio
import json
import threading
from contextlib import contextmanager


@contextmanager
def hosted_workers(u, *, answers=True):
    import os
    import queue
    import socket
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    from test_draft_service_native import KEY

    workers, ports = [], []
    try:
        for _ in range(2):
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            env = {
                key: value
                for key, value in os.environ.items()
                if key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONUTF8")
            }
            env["PYTHONPATH"] = str(Path(tempfile.gettempdir()) / "c113c-db-driver")
            worker = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(Path(__file__).with_name("hosted_subscription_worker.py")),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
            )
            workers.append(worker)
            ports.append(port)
            worker.stdin.write(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "http_port": port,
                        "pg_port": u["db"].port,
                        "jwt_key": KEY,
                        "answers": answers,
                    }
                )
                + "\n"
            )
            worker.stdin.flush()
            ready = queue.Queue()
            threading.Thread(
                target=lambda queue=ready, proc=worker: queue.put(
                    proc.stdout.readline()
                ),
                daemon=True,
            ).start()
            if ready.get(timeout=30).strip() != '{"ready": true}':
                raise RuntimeError(
                    "Isolated hosted worker startup failed; no raw diagnostics exposed"
                )
        yield {
            "url": f"http://127.0.0.1:{ports[0]}",
            "secondUrl": f"http://127.0.0.1:{ports[1]}",
            "deployment": "synthetic.relay.v1",
            "workers": [worker.pid for worker in workers],
        }
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
            for handle in (worker.stdin, worker.stdout, worker.stderr):
                handle.close()


@contextmanager
def physical_workers(u, monkeypatch):
    from app import grpc_answer_pipeline, grpc_server
    from app.config import settings
    from app.services import assemblyai_streaming
    from test_grpc_computer_lifecycle import Socket

    for name in (
        "USE_GRPC_AUTO_PIPELINE",
        "GRPC_STT_ENABLED",
        "GRPC_ANSWER_STREAM_ENABLED",
        "USE_GRPC_CLOUD_CONTEXT_PIPELINE",
    ):
        monkeypatch.setattr(settings, name, True)
    monkeypatch.setattr(settings, "HOSTED_COMMERCIAL_MODE", False)
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "synthetic-never-sent")

    async def connect(self):
        class DiscardSocket(Socket):
            async def send(self, data):
                pass  # Do not retain PCM even in the synthetic socket's sent list.

        socket = DiscardSocket()
        await socket.events.put(json.dumps({"type": "Begin"}))
        return socket

    async def detect(*_, **__):
        return "What is dependency injection?", ""

    # Raw captured audio is discarded, never saved/transcribed or sent outbound.
    monkeypatch.setattr(
        assemblyai_streaming.AssemblyAIStreamingBridge, "connect", connect
    )
    monkeypatch.setattr(grpc_answer_pipeline, "detect_intake_question", detect)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    async def start():
        return await grpc_server.start_server(
            port=0, subscriptions=u["client"].app.state.subscriptions
        )

    server, port = asyncio.run_coroutine_threadsafe(start(), loop).result(15)
    try:
        yield port
    finally:

        async def shutdown():
            await server.stop(0)
            await grpc_server.shutdown_cleanup()

        asyncio.run_coroutine_threadsafe(shutdown(), loop).result(15)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        loop.close()
