"""Owned, bounded gRPC teardown; synthetic resources and no external services."""
import asyncio
import gc
import threading
import weakref

import pytest

from app import grpc_server, grpc_answer_pipeline
from app.grpc_generated import interview_realtime_pb2 as pb
from test_grpc_computer_lifecycle import configure, chunk, NS


@pytest.mark.asyncio
async def test_expired_join_retains_task_and_retrieves_safe_exception(caplog):
    entered, release = asyncio.Event(), asyncio.Event()
    registry = set()
    async def cleanup():
        entered.set()
        await release.wait()
        raise RuntimeError('synthetic-private-exception-content')
    task = grpc_server._track_cleanup(cleanup(), registry)
    ref = weakref.ref(task)
    await entered.wait()
    assert not await grpc_server._join_cleanup({task}, asyncio.get_running_loop().time())
    assert not task.done() and task in registry
    del task
    gc.collect()
    assert ref() is not None  # registry owns unfinished work after RPC detaches
    done = asyncio.Event()
    ref().add_done_callback(lambda _: done.set())
    task = ref()
    release.set()
    await asyncio.wait_for(done.wait(), 1)
    assert not registry
    assert not task._log_traceback  # exception() was retrieved by ownership callback
    assert 'gRPC background cleanup failed.' in caplog.text
    assert 'synthetic-private-exception-content' not in caplog.text


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_restart_join_deadline(monkeypatch):
    release, entered = asyncio.Event(), asyncio.Queue()
    child = asyncio.create_task(release.wait())
    original_wait = asyncio.wait
    async def observed_wait(tasks, *, timeout):
        entered.put_nowait(timeout)
        return await original_wait(tasks, timeout=timeout)
    monkeypatch.setattr(asyncio, 'wait', observed_wait)
    now = [10.0]
    joining = asyncio.create_task(grpc_server._join_cleanup({child}, 20.0, clock=lambda: now[0]))
    timeouts = []
    try:
        for tick in (13.0, 16.0, 20.0):
            timeouts.append(await asyncio.wait_for(entered.get(), 1))
            now[0] = tick
            joining.cancel()
        assert await asyncio.wait_for(joining, 1)
        assert timeouts == [10.0, 7.0, 4.0]
        assert not child.done()
    finally:
        release.set()
        await child
        await joining


@pytest.mark.asyncio
@pytest.mark.parametrize('termination', ['disconnect', 'end_session'])
async def test_rpc_detaches_blocked_answer_but_finishes_independent_audio(monkeypatch, termination):
    monkeypatch.setattr(grpc_server, 'RPC_CLEANUP_JOIN_TIMEOUT_SECONDS', 0)
    native_release = threading.Event()
    capture_closed = asyncio.Event()
    loop = asyncio.get_running_loop()
    class Capture:
        def open_streaming_loopback_session(self, **kwargs): return NS()
        def read_streaming_pcm_chunk(self, session):
            assert native_release.wait(3)
            return chunk()
        def close_streaming_loopback_session(self, session):
            loop.call_soon_threadsafe(capture_closed.set)
            return True
    sockets = configure(monkeypatch, Capture)
    answer_entered, answer_release, answer_finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    socket_closed, started, ended = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def close(): socket_closed.set()
    from test_grpc_computer_lifecycle import Socket
    monkeypatch.setattr(Socket, 'close', lambda self: close())
    async def answer(text):
        yield {'type': 'question', 'text': text}
        yield {'type': 'started'}
        try:
            await asyncio.Event().wait()
        finally:
            answer_entered.set()
            await answer_release.wait()
            answer_finished.set()
    monkeypatch.setattr(grpc_answer_pipeline, 'stream_question_answer', answer)
    async def requests():
        yield pb.InterviewClientEvent(session_id='synthetic', start_session=pb.StartSession(mode='auto_pipeline', source='system'))
        await ended.wait()
        yield pb.InterviewClientEvent(session_id='synthetic', end_session=pb.Empty())
    service = grpc_server.InterviewRealtimeService()
    before = set(grpc_server._rpc_cleanup_tasks)
    statuses = []
    async def consume():
        async for event in service.StreamInterview(requests(), NS()):
            if event.HasField('ready'):
                await sockets[0].events.put('{"type":"Turn","end_of_turn":true,"transcript":"Explain dependency injection","turn_order":0}')
            if event.HasField('answer_started'): started.set()
            if event.HasField('status'): statuses.append(event.status.code)
    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(started.wait(), 1)
        if termination == 'disconnect': task.cancel()
        else: ended.set()
        result = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
        if termination == 'disconnect': assert isinstance(result[0], asyncio.CancelledError)
        else:
            assert result == [None]
            assert 'system_cleanup_pending' in statuses and 'ended' not in statuses
        await asyncio.wait_for(answer_entered.wait(), 1)
        native_release.set()
        await asyncio.wait_for(capture_closed.wait(), 1)
        await asyncio.wait_for(socket_closed.wait(), 1)
        assert not answer_finished.is_set()
        owned = grpc_server._rpc_cleanup_tasks - before
        assert owned and any(not t.done() for t in owned)
        answer_release.set()
        await asyncio.wait_for(asyncio.gather(*owned), 1)
        assert answer_finished.is_set()
        assert not (grpc_server._rpc_cleanup_tasks - before)
    finally:
        native_release.set()
        answer_release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        pending = grpc_server._rpc_cleanup_tasks - before
        if pending: await asyncio.wait_for(asyncio.gather(*pending), 1)


@pytest.mark.asyncio
async def test_shutdown_deadline_keeps_cleanup_owned_then_drains(monkeypatch, caplog):
    entered, release = asyncio.Event(), asyncio.Event()
    async def cleanup():
        entered.set()
        await release.wait()
    task = grpc_server._track_cleanup(cleanup(), grpc_server._rpc_cleanup_tasks)
    await entered.wait()
    monkeypatch.setattr(grpc_server, 'GRPC_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS', 0)
    await grpc_server.shutdown_cleanup()
    assert not task.done() and task in grpc_server._rpc_cleanup_tasks
    assert 'gRPC cleanup remains pending at shutdown.' in caplog.text
    release.set()
    monkeypatch.setattr(grpc_server, 'GRPC_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS', 1)
    await grpc_server.shutdown_cleanup()
    assert task.done() and task not in grpc_server._rpc_cleanup_tasks


@pytest.mark.asyncio
async def test_standalone_shutdown_drains_even_if_server_stop_fails(monkeypatch):
    calls = []
    async def wait(): pass
    async def stop(**kwargs):
        calls.append('stop')
        raise RuntimeError('synthetic stop failure')
    async def start(*args): return NS(wait_for_termination=wait, stop=stop), 0
    async def drain(): calls.append('drain')
    monkeypatch.setattr(grpc_server, 'start_server', start)
    monkeypatch.setattr(grpc_server, 'shutdown_cleanup', drain)
    with pytest.raises(RuntimeError, match='synthetic stop failure'):
        await grpc_server.serve('127.0.0.1', 0)
    assert calls == ['stop', 'drain']
