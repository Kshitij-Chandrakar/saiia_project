"""Actual Python coordinator/localhost gRPC -> Electron -> IPC/preload -> Auto consumer."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from test_session_generation import setup
from test_answer_stream_characterization import Probe, Gates, transport, A, B, FALLBACK_A, FALLBACK_B
from app import session_generation as sg


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['microphone', 'system', 'both'])
async def test_actual_electron_preload_receives_gated_primary_and_fallback(setup, monkeypatch, source, caplog):
    _, store = setup
    probe = Probe()
    gates = Gates(probe, 'fallback')
    monkeypatch.setattr(sg, 'provider_stream', gates.provider)
    messages = []
    changed = asyncio.Event()

    async def until(predicate):
        async def wait():
            while not predicate():
                changed.clear()
                await changed.wait()
        await asyncio.wait_for(wait(), 15)

    @asynccontextmanager
    async def node(port):
        script = Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/answer_stream_localhost.mjs'
        proc = await asyncio.create_subprocess_exec('node', str(script), str(port), source,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def read():
            async for line in proc.stdout:
                # Only synthetic answer fixtures cross this local test pipe.
                messages.append(json.loads(line))
                changed.set()
        reader = asyncio.create_task(read())
        try:
            await until(lambda: any(x['stage'] == 'ready' for x in messages))
            yield proc
            proc.stdin.write(b'close\n')
            await proc.stdin.drain()
            await asyncio.wait_for(proc.wait(), 15)
            stderr = await proc.stderr.read()
            assert proc.returncode == 0
            assert b'Authorization' not in stderr and b'synthetic-test-only' not in stderr
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            await asyncio.gather(reader, return_exceptions=True)

    def entries():
        return [x['entry'] for x in messages if x['stage'] == 'answer']

    try:
        async with transport(monkeypatch, source, probe, version=1, external_client=node):
            gates.release['primary_a'].set()
            await until(lambda: any(x['answer'] == A[:-1] for x in entries()))
            assert not store.saves
            gates.release['primary_b'].set()
            await until(lambda: any(len(x['answer']) > len(A) for x in entries()))
            assert not any(x['status'] == 'complete' for x in entries())
            gates.release['primary_end'].set()
            await probe.until(lambda: bool(probe.payloads('fallback_a_waiting')))
            await until(lambda: bool(entries()) and entries()[-1]['answer'] == '')
            gates.release['fallback_a'].set()
            await until(lambda: any(x['answer'] == FALLBACK_A[:-1] for x in entries()))
            gates.release['fallback_b'].set()
            await until(lambda: any(x['answer'].startswith(FALLBACK_A) and len(x['answer']) > len(FALLBACK_A) for x in entries()))
            assert not store.saves and not any(x['status'] == 'complete' for x in entries())
            gates.release['fallback_end'].set()
            await until(lambda: any(x['status'] == 'complete' for x in entries()))
            assert entries()[-1]['answer'] == FALLBACK_A + FALLBACK_B
            assert len(store.saves) == len([x for x in entries() if x['status'] == 'complete']) == 1
            assert not any(x['stage'] == 'error' for x in messages)
            assert 'synthetic-test-only' not in caplog.text
            assert 'Authorization:' not in caplog.text
    finally:
        gates.unblock()


def test_safe_runner_blocks_external_tcp_and_dns_before_connecting():
    import subprocess
    import sys
    runner = Path(__file__).resolve().parents[1] / 'scripts/verify_answer_streaming.py'
    script = "import runpy,socket; runpy.run_path(" + repr(str(runner)) + ",run_name='stream_test_guard'); "
    script += "\nfor attempt in (lambda: socket.getaddrinfo('example.invalid',443), lambda: socket.socket().connect(('203.0.113.1',443))):\n try: attempt()\n except AssertionError: pass\n else: raise AssertionError('Network guard did not block')"
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, timeout=10)
    assert result.returncode == 0
    assert not result.stdout and not result.stderr
