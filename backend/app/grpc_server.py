"""Experimental loopback-only realtime transport; opt-in STT and answer diagnostics."""
import argparse
import hashlib
import re
from collections import deque
from contextlib import aclosing
import asyncio
import ipaddress
import importlib.util
import platform
import json
import logging
import time
import uuid
from app.answer_generation import GenerationStopped

import grpc

from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


AUTO_COOLDOWN_SECONDS = 4.0
STABLE_PARTIAL_SECONDS = 1.2


RPC_CLEANUP_JOIN_TIMEOUT_SECONDS = 5.0
GRPC_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS = 5.0
_system_cleanup_tasks = set()
_rpc_cleanup_tasks = set()
_cleanup_logger = logging.getLogger("realtime")


def _track_cleanup(coroutine, registry):
    task = asyncio.create_task(coroutine)
    registry.add(task)
    def finished(done):
        try:
            if not done.cancelled() and done.exception() is not None:
                # Neither exception text nor traceback is safe diagnostic content.
                _cleanup_logger.warning("gRPC background cleanup failed.")
        finally:
            registry.discard(done)
    task.add_done_callback(finished)
    return task


async def _join_cleanup(tasks, deadline, *, clock=None):
    """Bound only this waiter; asyncio.wait never cancels the owned children."""
    cancelled = False
    pending = {task for task in tasks if not task.done()}
    clock = clock or asyncio.get_running_loop().time
    while pending and clock() < deadline:
        try:
            _, pending = await asyncio.wait(pending, timeout=max(0, deadline - clock()))
        except asyncio.CancelledError:
            cancelled = True
    return cancelled


async def shutdown_cleanup():
    """Give retained RPC/native cleanup a bounded drain during application shutdown."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + GRPC_SHUTDOWN_CLEANUP_TIMEOUT_SECONDS
    cancelled = False
    while loop.time() < deadline:
        tasks = {task for task in _rpc_cleanup_tasks | _system_cleanup_tasks
                 if task.get_loop() is loop and not task.done()}
        if not tasks:
            break
        cancelled |= await _join_cleanup(tasks, deadline)
    if any(not task.done() and task.get_loop() is loop
           for task in _rpc_cleanup_tasks | _system_cleanup_tasks):
        _cleanup_logger.warning("gRPC cleanup remains pending at shutdown.")
    if cancelled:
        raise asyncio.CancelledError()

def question_intake_diagnostics(values):
    # Transcript content belongs in explicit UI events, not diagnostics.
    return pb.QuestionIntake(**{key: value for key, value in values.items()
                               if key not in ('last_ignored_transcript', 'utterance_buffer_text')})

def system_capture_available():
    # Capability only: no PyAudio instance, device enumeration or provider calls.
    return platform.system() == "Windows" and importlib.util.find_spec("pyaudiowpatch") is not None


class InterviewRealtimeService(rpc.InterviewRealtimeServiceServicer):
    def __init__(self, subscriptions=None, *, client_relay=None):
        self._system_owner = asyncio.Lock()
        self._system_cleanup_failed = False
        self._subscriptions = subscriptions
        # Internal ASGI adapter only; standalone gRPC never sets this capability.
        self._client_relay = client_relay

    async def CheckHealth(self, request, context):
        if (settings.HOSTED_COMMERCIAL_MODE and self._client_relay is None) or (settings.SUBSCRIPTIONS_ENABLED == 'true' and self._subscriptions is None):
            return pb.RealtimeHealth()
        # Configuration readiness only: never open capture, STT, auth or an LLM.
        stt = settings.GRPC_STT_ENABLED and bool(settings.ASSEMBLYAI_API_KEY)
        answer = stt and settings.GRPC_ANSWER_STREAM_ENABLED
        return pb.RealtimeHealth(stt_available=stt, answer_stream_available=answer,
                                 auto_available=answer and settings.USE_GRPC_AUTO_PIPELINE,
                                 cloud_context_available=settings.USE_GRPC_CLOUD_CONTEXT_PIPELINE,
                                 combined_audio_available=answer and settings.USE_GRPC_AUTO_PIPELINE and system_capture_available()
                                 and not self._system_owner.locked() and not self._system_cleanup_failed,
                                 system_audio_available=answer and settings.USE_GRPC_AUTO_PIPELINE and system_capture_available()
                                 and not self._system_owner.locked() and not self._system_cleanup_failed)

    async def StreamInterview(self, request_iterator, context):
        if (settings.HOSTED_COMMERCIAL_MODE and self._client_relay is None) or (settings.SUBSCRIPTIONS_ENABLED == 'true' and self._subscriptions is None):
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Hosted commercial gRPC is not admitted.")
            return
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
        audio_source = 'microphone'
        system_capture = system_session = system_reader = system_sender = read_future = None
        system_metrics = {}
        system_owned = False
        system_stopping = False
        resource_cleanup = cleanup_deadline = None
        system_open_future = system_cleanup = None
        system_queue = asyncio.Queue(maxsize=3)
        from app.pcm_mixer import PcmMixer
        mixer = PcmMixer()
        mixed_started = False
        cloud_context = None
        auto_mode = False
        auto_cooldown_until = 0.0
        manual_mode = False
        manual_stopped = False
        manual_turns = {}
        provider_epoch = 0
        answer_task = None
        answers_stopping = False
        last_request_id = ""
        provider_started = asyncio.Event()
        final_received = asyncio.Event()
        transcript_received = False
        final_transcript_received = False
        stopping_stt = False
        stt_chunks = stt_bytes = callbacks = non_silent_chunks = 0
        intake = {key: 0 for key in ('final_transcripts_received', 'final_transcripts_ignored', 'detection_attempts', 'detection_successes', 'detection_rejections', 'cooldown_rejections', 'dedupe_rejections', 'too_short_rejections')}
        intake.update(last_ignored_transcript='', last_ignored_reason='', pending_question=False, pending_reason='')
        from app.grpc_utterance_buffer import UtteranceBuffer, ENDPOINT_SECONDS
        utterance = UtteranceBuffer()
        endpoint_task = None
        for key in ('merged_final_count', 'topic_prompt_accepted_count', 'buffered_transcripts_count', 'incomplete_final_wait_count', 'completed_from_buffer_count'): intake[key] = 0
        intake.update(last_buffer_action='', last_detection_source='')
        queued_fingerprints = set()
        generation_active = False
        stable_partial = None
        stable_partial_key = None
        answer_version = 0
        accepted_turn = 0
        current_answer_request = ''
        answer_identity = {}
        account_lease = None
        lease_watcher = None

        async def watch_lease():
            if self._client_relay:
                code = await self._client_relay.wait_for_end()
            else:
                await account_lease.expired()
                code = 'subscription_auto_expired'
            if not account_lease.stopped:
                await emit(last_request_id,'error',pb.ErrorEvent(code=code,message='Auto authorization ended. Stop and check your available allowance.'))
                await output.put(None)
                start_resource_cleanup()

        def event(request_id, kind, payload):
            nonlocal sequence
            sequence += 1
            return pb.InterviewServerEvent(
                session_id=session_id or "", request_id=request_id,
                sequence_number=sequence, timestamp_ms=int(time.time() * 1000),
                provider=(getattr(payload, "provider", "") or ("assemblyai_streaming" if stt_enabled else "none")),
                **({'answer_identity': pb.AnswerIdentity(**answer_identity)}
                   if answer_version and request_id == current_answer_request and
                   kind in ('question_detected', 'answer_started', 'answer_delta', 'answer_replaced', 'answer_completed', 'answer_error') else {}),
                **{kind: payload})

        async def emit(request_id, kind, payload):
            if audio_source == 'system':
                field = {'partial_transcript': 'system_first_stt_partial_at', 'final_transcript': 'system_first_stt_final_at', 'question_detected': 'system_question_detected_at', 'answer_started': 'system_answer_started_at', 'answer_delta': 'system_first_answer_delta_at'}.get(kind)
                if field and not system_metrics.get(field):
                    system_metrics[field] = time.time() * 1000
                    for target, end, start in (
                        ('system_capture_to_partial_ms','system_first_stt_partial_at','system_capture_started_at'),
                        ('system_partial_to_question_ms','system_question_detected_at','system_first_stt_partial_at'),
                        ('system_question_to_first_delta_ms','system_first_answer_delta_at','system_question_detected_at'),
                        ('system_total_question_to_answer_ms','system_first_answer_delta_at','system_first_stt_partial_at')):
                        if system_metrics.get(end) and system_metrics.get(start): system_metrics[target] = max(0, system_metrics[end]-system_metrics[start])
                    await output.put(event(request_id, 'status', pb.Status(code='system_audio_metrics', system_audio=pb.SystemAudioDiagnostics(**system_metrics))))
            await output.put(event(request_id, kind, payload))

        async def intake_status():
            if auto_mode:
                intake.update(utterance.snapshot())
                await emit(last_request_id, 'status', pb.Status(code='question_intake', question_intake=question_intake_diagnostics(intake)))

        async def ignored(text, reason, final=True):
            if final: intake['final_transcripts_ignored'] += 1
            intake['last_ignored_transcript'] = text[:256]
            intake['last_ignored_reason'] = reason
            field = {'duplicate': 'dedupe_rejections', 'too_short': 'too_short_rejections'}.get(reason)
            if field: intake[field] += 1
            await intake_status()

        async def answer_worker():
            nonlocal auto_cooldown_until, generation_active, accepted_turn, current_answer_request, answer_identity
            from app.grpc_answer_pipeline import stream_question_answer
            while not answers_stopping:
                text, request_id, fingerprint, turn, is_final = await questions.get()
                if auto_mode and auto_cooldown_until > time.monotonic():
                    await asyncio.sleep(auto_cooldown_until - time.monotonic())
                    # Keep only the latest question heard during cooldown.
                    while not questions.empty():
                        await ignored(text, 'cooldown_active', is_final)
                        queued_fingerprints.discard(fingerprint)
                        questions.task_done()
                        text, request_id, fingerprint, turn, is_final = questions.get_nowait()
                    await emit(request_id, "status", pb.Status(code="auto_listening"))
                logical_turn_id = str(uuid.uuid4())
                request_id = current_answer_request = logical_turn_id
                accepted_turn += 1
                answer_identity = dict(retry_attempt=0, provider_attempt=0, display_revision=0, accepted_turn=accepted_turn)
                generation_active = True
                intake['pending_question'] = False
                intake['pending_reason'] = ''
                await intake_status()
                if auto_mode:
                    seen.append(fingerprint)
                    if turn is not None:
                        seen_turns.append(turn)
                async def generate():
                    nonlocal auto_cooldown_until
                    answer = ""
                    category = provider = ""
                    question_seen = completed = False
                    if account_lease:
                        await account_lease.authorize()
                    pipeline_call = (stream_question_answer(text, cloud_context=cloud_context, logical_turn_id=logical_turn_id, incremental=True)
                        if answer_version else stream_question_answer(text, cloud_context=cloud_context, logical_turn_id=logical_turn_id)
                        if cloud_context and settings.ENABLE_SESSION_ANSWER_MODELS else
                        stream_question_answer(text, cloud_context=cloud_context) if cloud_context else stream_question_answer(text))
                    async with aclosing(pipeline_call) as pipeline:
                        async for item in pipeline:
                            kind = item.get("type")
                            if completed:
                                continue
                            if answer_version:
                                attempt = item.get('attempt', answer_identity['provider_attempt'])
                                revision = item.get('revision', answer_identity['display_revision'])
                                retry = item.get('retry_attempt', answer_identity['retry_attempt'])
                                if (retry != answer_identity['retry_attempt'] or
                                    attempt < answer_identity['provider_attempt'] or revision < answer_identity['display_revision']):
                                    continue
                                if kind == 'delta' and (attempt, revision) != (answer_identity['provider_attempt'], answer_identity['display_revision']):
                                    continue  # only replacement opens another display revision
                                if kind == 'replacement' and revision <= answer_identity['display_revision']:
                                    continue
                                answer_identity.update(provider_attempt=attempt, display_revision=revision)
                            category = item.get("category") or category
                            provider = item.get("provider") or provider
                            if kind == "rejected":
                                intake['detection_rejections'] += 1
                                await ignored(text, item.get('reason') or 'not_question', is_final)
                            elif kind == "save_status":
                                await emit(request_id, "status", pb.Status(code=item["code"]))
                            elif kind == "question":
                                if question_seen:
                                    continue
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
                            elif kind in ("replacement", "result") and (answer_version or item.get("text")):
                                answer = str(item.get("text") or '')
                                if len(answer) > 262144:
                                    raise RuntimeError("Answer limit exceeded.")
                                if answer_version and kind == 'replacement':
                                    await emit(request_id, 'answer_replaced', pb.TextEvent(text=answer, category=category, provider=provider))
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
                except GenerationStopped:
                    await emit(request_id, 'answer_error', pb.ErrorEvent(code='generation_stopped', message='Generation stopped.'))
                    if auto_mode:
                        await emit(request_id, 'status', pb.Status(code='auto_listening'))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    from app.grpc_cloud_context import CloudContextRejected
                    if cloud_context and isinstance(exc, CloudContextRejected):
                        await ignored(text, 'blocked_by_auth', is_final)
                        await emit(request_id, "error", pb.ErrorEvent(code=exc.code, message="Cloud context is no longer available. Stop and reconnect."))
                        await output.put(None)
                        return
                    await ignored(text, 'unknown', is_final)
                    from app.answer_generation import GenerationFailure
                    from app.session_generation import TurnStateError
                    terminal = isinstance(exc, GenerationFailure)
                    recoverable = isinstance(exc, TurnStateError)
                    await emit(request_id, "answer_error", pb.ErrorEvent(
                        code="generation_failed" if terminal else exc.code if recoverable else "answer_unavailable",
                        message="Unable to generate an answer" if terminal or recoverable else "Experimental answer unavailable or timed out. Retry."))
                    if (terminal or recoverable) and auto_mode:
                        await emit(request_id, 'status', pb.Status(code='auto_listening'))
                finally:
                    generation_active = False
                    queued_fingerprints.discard(fingerprint)
                    questions.task_done()

        async def queue_final(text, turn_order, final=True, endpoint=False):
            nonlocal endpoint_task
            if manual_mode and not manual_stopped:
                key = turn_order if isinstance(turn_order, int) else 0
                if key not in manual_turns and len(manual_turns) >= 64:
                    raise RuntimeError("Manual capture turn limit exceeded.")
                manual_turns[key] = text
                if sum(len(value) for value in manual_turns.values()) > 65536:
                    raise RuntimeError("Manual capture text limit exceeded.")
                return
            if not answer_enabled:
                return
            if auto_mode:
                if final and not endpoint: intake['final_transcripts_received'] += 1
                if not text.strip():
                    await ignored(text, 'empty_final', final)
                    return
                from app.grpc_answer_pipeline import detect_intake_question
                if endpoint_task and not endpoint:
                    endpoint_task.cancel()
                    endpoint_task = None
                merged = False
                if not endpoint:
                    text, merged = utterance.assemble(text, turn_order)
                    intake['last_detection_source'] = 'merged_buffer' if merged else 'final' if final else 'stable_partial'
                    if merged:
                        if final: intake['merged_final_count'] += 1
                        intake['last_buffer_action'] = 'merged_short_final'
                intake['detection_attempts'] += 1
                try:
                    question, reason = await detect_intake_question(text, allow_topics=True)
                except Exception:
                    question, reason = None, 'unknown'
                topic_accepted = reason == 'topic_prompt_accepted'
                if topic_accepted:
                    intake['last_buffer_action'] = reason
                    intake['last_detection_source'] = 'topic_prompt'
                    text = question
                    reason = ''
                if reason and not endpoint and reason in ('too_short', 'not_question') and len(text.split()) <= 8:
                    from app.grpc_utterance_buffer import NOISE
                    if not NOISE.search(text):
                        utterance.hold(text)
                        intake['buffered_transcripts_count'] += 1
                        intake['incomplete_final_wait_count'] += 1
                        intake['last_buffer_action'] = 'buffered_until_complete'
                        async def finish_fragment(value=text, turn=turn_order):
                            await asyncio.sleep(ENDPOINT_SECONDS)
                            utterance.pending = ''
                            await queue_final(value, turn, final=final, endpoint=True)
                        endpoint_task = asyncio.create_task(finish_fragment())
                        await intake_status()
                        return
                if reason:
                    intake['detection_rejections'] += 1
                    await ignored(text, reason, final)
                    return
                utterance.pending_at = 0
                if merged: intake['completed_from_buffer_count'] += 1
                intake['detection_successes'] += 1
            elif len(text.split()) < 3:
                return
            fingerprint = hashlib.sha256(re.sub(r"[^\w]", "", text.casefold()).encode()).digest()
            turn = (provider_epoch, turn_order) if isinstance(turn_order, int) else None
            if fingerprint in seen or fingerprint in queued_fingerprints or (turn is not None and turn in seen_turns):
                await ignored(text, 'duplicate', final)
                return
            try:
                if auto_mode:
                    if topic_accepted: intake['topic_prompt_accepted_count'] += 1
                    if generation_active or auto_cooldown_until > time.monotonic():
                        intake['pending_question'] = True
                        intake['pending_reason'] = 'generation_in_progress' if generation_active else 'cooldown_active'
                        if auto_cooldown_until > time.monotonic(): intake['cooldown_rejections'] += 1
                    while not questions.empty():
                        old = questions.get_nowait()
                        await ignored(old[0], 'generation_in_progress' if generation_active else 'cooldown_active', old[4])
                        queued_fingerprints.discard(old[2])
                        questions.task_done()
                questions.put_nowait((text, last_request_id, fingerprint, turn, final))
                queued_fingerprints.add(fingerprint)
                await intake_status()
                if not auto_mode:
                    seen.append(fingerprint)
                    if turn is not None:
                        seen_turns.append(turn)
            except asyncio.QueueFull:
                await emit(last_request_id, "answer_error", pb.ErrorEvent(
                    code="answer_busy", message="Experimental answer queue is busy. Retry after the current answer."))

        async def receive_transcripts():
            nonlocal transcript_received, final_transcript_received, callbacks, stable_partial, stable_partial_key
            try:
                async for raw in socket:
                    message = json.loads(raw)
                    callbacks += 1
                    kind = message.get("type")
                    if kind == "Begin":
                        provider_started.set()
                    elif kind == "Turn":
                        text = message.get("transcript", "")
                        partial_key = (str(text or '')[:65536], message.get('turn_order'))
                        if message.get('end_of_turn') or partial_key != stable_partial_key:
                            if stable_partial: stable_partial.cancel()
                            stable_partial = None
                            stable_partial_key = partial_key
                        if message.get('end_of_turn') and auto_mode and not str(text or '').strip():
                            await queue_final('', message.get('turn_order'))
                        if auto_mode and isinstance(text, str) and text.strip() and not message.get('end_of_turn'):
                            utterance.partial_update(text, message.get('turn_order'))
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
                            elif auto_mode and not generation_active:
                                from app.grpc_answer_pipeline import looks_like_interview_question
                                if stable_partial is None and looks_like_interview_question(text):
                                    async def stable_question(value=text[:65536], turn=message.get('turn_order')):
                                        await asyncio.sleep(STABLE_PARTIAL_SECONDS)
                                        if not generation_active and not stopping_stt:
                                            await queue_final(value, turn, final=False)
                                    stable_partial = asyncio.create_task(stable_question())
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

        async def open_system_capture():
            nonlocal system_capture, system_session, system_reader, system_sender, system_open_future
            empty_native_chunks = 0
            from app.services.system_audio_capture import SystemAudioCaptureService
            from starlette.concurrency import run_in_threadpool
            system_capture = SystemAudioCaptureService()
            system_metrics.update(system_capture_started_at=time.time()*1000, active_audio_source=audio_source, transcript_source=audio_source, question_source=audio_source, answer_source_audio=audio_source, system_target_rate=16000, system_dropped_chunks=0)
            system_open_future = asyncio.ensure_future(run_in_threadpool(system_capture.open_streaming_loopback_session,
                target_sample_rate=16000, chunk_ms=100, debug_save_enabled=False, monitor_default=True))
            system_session = await asyncio.shield(system_open_future)
            if audio_source == 'both':
                system_capture.enable_continuous_resampling(system_session)
            async def capture():
                nonlocal read_future, empty_native_chunks
                tail = b''
                try:
                    while not system_stopping:
                        read_future = asyncio.ensure_future(run_in_threadpool(system_capture.read_streaming_pcm_chunk, system_session))
                        chunk = await asyncio.wait_for(asyncio.shield(read_future), timeout=2)
                        if system_stopping:
                            break
                        now = time.time()*1000
                        if not system_metrics.get('system_first_pcm_chunk_at'): system_metrics['system_first_pcm_chunk_at'] = now
                        if chunk.rms_level > .005 and not system_metrics.get('system_first_non_silent_chunk_at'): system_metrics['system_first_non_silent_chunk_at'] = now
                        if not chunk.pcm_bytes:
                            empty_native_chunks += 1
                            system_metrics['system_dropped_chunks'] += 1
                        if len(chunk.pcm_bytes) % 2: raise RuntimeError('invalid PCM')
                        system_metrics.update(system_sample_rate=chunk.input_sample_rate, system_rms=chunk.rms_level, system_peak=chunk.peak_level,
                            system_resample_latency_ms=chunk.resample_latency_ms)
                        if audio_source == 'both':
                            if chunk.pcm_bytes:
                                mixer.push('system', chunk.pcm_bytes, time.monotonic())
                            continue
                        tail += chunk.pcm_bytes
                        while len(tail) >= 3200:
                            frame, tail = tail[:3200], tail[3200:]
                            if system_queue.full():
                                system_queue.get_nowait()
                                system_metrics['system_dropped_chunks'] += 1
                            system_queue.put_nowait(frame)
                        if len(tail) > 65536: raise RuntimeError('capture buffer exceeded')
                except asyncio.CancelledError: raise
                except Exception:
                    await emit(last_request_id,'error',pb.ErrorEvent(code='system_audio_unavailable',message='Computer audio capture lost. Stop and restart Auto Mode.'))
                    await output.put(None)
            async def send():
                nonlocal total_chunks, total_audio_bytes, stt_chunks, stt_bytes, non_silent_chunks, mixed_started
                deadline = time.monotonic() + .3
                startup_deadline = time.monotonic() + 5
                try:
                    while not system_stopping:
                        if audio_source == 'both':
                            now = time.monotonic()
                            if not mixed_started:
                                if not all(s['seen'] for s in mixer.sources.values()):
                                    if now > startup_deadline: raise RuntimeError('Required source did not start')
                                    await asyncio.sleep(.01)
                                    continue
                                mixed_started = True
                                deadline = now + .2
                            await asyncio.sleep(max(0, deadline - now))
                            now = time.monotonic()
                            if any(now - s['last'] > 2 for s in mixer.sources.values()):
                                raise RuntimeError('Required source lost')
                            if now - deadline > .3:
                                raise RuntimeError('Mixer stalled; explicit restart required')
                            frame = mixer.render()
                            system_metrics.update(system_dropped_chunks=mixer.dropped + empty_native_chunks,
                                system_buffer_queue_depth=max(max(0, s['end'] - mixer.position) for s in mixer.sources.values()) / mixer.frame_samples)
                            deadline += .1
                        else:
                            frame = await system_queue.get()
                        system_metrics.update(system_chunk_bytes=len(frame),system_pcm_duration_ms=len(frame)/32,
                            system_silence_ratio=sum(frame[i:i+2] == b'\0\0' for i in range(0,len(frame),2))/(len(frame)//2))
                        if audio_source == 'system': system_metrics['system_buffer_queue_depth'] = system_queue.qsize()
                        if not system_metrics.get('system_first_chunk_sent_to_grpc_at'): system_metrics['system_first_chunk_sent_to_grpc_at'] = time.time()*1000
                        if account_lease and account_lease.remaining()<=0:
                            raise PermissionError('Auto authorization expired')
                        await asyncio.wait_for(socket.send(frame),timeout=min(2,account_lease.remaining()) if account_lease else 2)
                        total_chunks += 1; total_audio_bytes += len(frame); stt_chunks += 1; stt_bytes += len(frame)
                        if any(frame): non_silent_chunks += 1
                        await emit(last_request_id,'status',pb.Status(code='system_audio_metrics',total_chunks=total_chunks,total_audio_bytes=total_audio_bytes,
                            stt_chunks_forwarded=stt_chunks,stt_bytes_forwarded=stt_bytes,stt_bridge_connected=True,
                            system_audio=pb.SystemAudioDiagnostics(**system_metrics),question_intake=question_intake_diagnostics({**intake,**utterance.snapshot()})))
                except asyncio.CancelledError: raise
                except Exception:
                    await emit(last_request_id,'error',pb.ErrorEvent(code='subscription_auto_expired' if account_lease and account_lease.remaining()<=0 else 'system_audio_unavailable',message='Audio authorization ended or the stream is unavailable. Stop and check your account.'))
                    await output.put(None)
            system_reader = asyncio.create_task(capture())
            system_sender = asyncio.create_task(send())
            await emit(last_request_id,'status',pb.Status(code='system_audio_metrics',system_audio=pb.SystemAudioDiagnostics(**system_metrics)))

        async def close_system_capture():
            nonlocal system_session, system_cleanup, system_stopping
            # wait_for can return a completed child despite concurrent cancellation
            # on Python 3.10/3.11. Fence both loops before canceling either task.
            system_stopping = True
            mixer.clear()
            if not system_owned:
                return True
            if system_cleanup is None:
                async def release():
                    nonlocal system_session
                    try:
                        if system_session is not None and hasattr(system_session, 'stop_requested'):
                            system_session.stop_requested.set()
                        for task in (system_reader, system_sender):
                            if task: task.cancel()
                        await asyncio.gather(*(t for t in (system_reader, system_sender) if t), return_exceptions=True)
                        # Native open/read cannot be canceled safely. Keep ownership until both settle.
                        if system_open_future:
                            try:
                                system_session = await asyncio.shield(system_open_future)
                            except Exception:
                                pass  # An unsuccessful open has no device handle to close.
                        if system_session is not None and hasattr(system_session, 'stop_requested'):
                            system_session.stop_requested.set()
                        if read_future:
                            await asyncio.gather(read_future, return_exceptions=True)
                        if system_session:
                            from starlette.concurrency import run_in_threadpool
                            if await run_in_threadpool(system_capture.close_streaming_loopback_session, system_session) is False:
                                raise RuntimeError("Native capture cleanup failed")
                            system_session = None
                        self._system_owner.release()
                        return True
                    except Exception:
                        # Unknown native ownership must not permit a second open. Backend restart required.
                        self._system_cleanup_failed = True
                        return False
                system_cleanup = _track_cleanup(release(), _system_cleanup_tasks)
            done, _ = await asyncio.wait({system_cleanup}, timeout=3)
            return bool(done and system_cleanup.result())

        async def close_stt():
            nonlocal socket, receiver, stable_partial, endpoint_task
            if receiver and not receiver.done():
                receiver.cancel()
            if receiver:
                await asyncio.gather(receiver, return_exceptions=True)
            if stable_partial:
                stable_partial.cancel()
                await asyncio.gather(stable_partial, return_exceptions=True)
                stable_partial = None
            if endpoint_task:
                endpoint_task.cancel()
                await asyncio.gather(endpoint_task, return_exceptions=True)
                endpoint_task = None
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
            nonlocal answers_stopping
            # Python 3.10 wait_for can lose cancellation when generation finishes
            # concurrently. Stop must still prevent another queue wait.
            answers_stopping = True
            if answer_task:
                answer_task.cancel()
                await asyncio.gather(answer_task, return_exceptions=True)

        def start_resource_cleanup():
            nonlocal resource_cleanup, cleanup_deadline
            if resource_cleanup is None:
                cleanup_deadline = asyncio.get_running_loop().time() + RPC_CLEANUP_JOIN_TIMEOUT_SECONDS
                async def audio():
                    # Stop system senders before closing their STT socket.
                    try:
                        return await close_system_capture()
                    finally:
                        await close_stt()
                async def release():
                    async def stop_lease():
                        if lease_watcher and lease_watcher is not asyncio.current_task():
                            lease_watcher.cancel()
                        if account_lease:
                            try:
                                await account_lease.stop()
                            except Exception:
                                pass # Durable lease expiry/reaper settles an uncertain cleanup.
                    results = await asyncio.gather(stop_answers(), audio(), stop_lease(), return_exceptions=True)
                    # Independent resources finish even when another branch fails.
                    for result in results:
                        if isinstance(result, BaseException):
                            raise result
                    return results[1]
                resource_cleanup = _track_cleanup(release(), _rpc_cleanup_tasks)
            return resource_cleanup

        async def process_requests():
            nonlocal account_lease, lease_watcher
            nonlocal system_owned, audio_source, cloud_context, auto_mode, manual_mode, manual_stopped, session_id, total_chunks, total_audio_bytes, last_request_id, stopping_stt, stt_chunks, stt_bytes, non_silent_chunks, answer_version
            canceled = False
            try:
                async for request in request_iterator:
                    last_request_id = request.request_id
                    kind = request.WhichOneof("event")
                    if kind == "ping":
                        if account_lease:
                            await account_lease.heartbeat()
                        await emit(request.request_id, "pong", pb.Empty())
                    elif kind in ("cancel", "end_session"):
                        resources = start_resource_cleanup()
                        if await _join_cleanup({resources}, cleanup_deadline):
                            raise asyncio.CancelledError()
                        cleaned = (resources.done() and not resources.cancelled() and
                                   resources.exception() is None and resources.result())
                        await emit(request.request_id, "status", pb.Status(
                            code=("canceled" if kind == "cancel" else "ended") if cleaned else "system_cleanup_pending",
                            message="Stream closed." if cleaned else "Stream cleanup is still running. Wait before restarting."))
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
                        if settings.SUBSCRIPTIONS_ENABLED=='true' and (not auto_mode or not request.start_session.cloud_context_requested):
                            await emit(request.request_id,'error',pb.ErrorEvent(code='subscription_auto_required',message='Authenticated Auto session required.'))
                            return
                        if manual_mode and not (settings.USE_GRPC_MANUAL_PIPELINE and answer_enabled):
                            await emit(request.request_id, "error", pb.ErrorEvent(code="manual_unavailable", message="Manual gRPC pipeline is unavailable."))
                            return
                        session_id = request.session_id
                        start = request.start_session
                        audio_source = start.source or 'microphone'
                        if audio_source not in ('microphone','system','both') or (audio_source in ('system','both') and not auto_mode):
                            await emit(request.request_id,'error',pb.ErrorEvent(code='unsupported_source',message='Audio source is unavailable.'))
                            return
                        if start.cloud_context_requested:
                            if not settings.USE_GRPC_CLOUD_CONTEXT_PIPELINE or not auto_mode or start.source not in ("microphone", "system", "both"):
                                await emit(request.request_id, "error", pb.ErrorEvent(code="cloud_context_flag_disabled", message="Cloud realtime context unavailable."))
                                return
                            from app.grpc_cloud_context import GrpcCloudContext, CloudContextRejected
                            from starlette.concurrency import run_in_threadpool
                            await emit(request.request_id, "status", pb.Status(code="auth_verifying"))
                            try:
                                args = (start,context.invocation_metadata(),self._subscriptions) if settings.SUBSCRIPTIONS_ENABLED=='true' else (start,context.invocation_metadata())
                                cloud_context = await asyncio.wait_for(run_in_threadpool(
                                    GrpcCloudContext.authorize, *args), timeout=15)
                            except Exception as exc:
                                code = exc.code if isinstance(exc, CloudContextRejected) else "cloud_context_rejected"
                                await emit(request.request_id, "error", pb.ErrorEvent(code=code, message="Cloud realtime context could not be verified. Use the authenticated fallback."))
                                return
                            for code in ("auth_verified", "cloud_session_verified", "cloud_context_loaded"):
                                await emit(request.request_id, "status", pb.Status(code=code))
                        elif start.active_session_id or start.selected_resume_id or start.selected_job_context_id:
                            await emit(request.request_id, "error", pb.ErrorEvent(code="auth_context_required", message="Cloud context requires verified authentication."))
                            return
                        if settings.SUBSCRIPTIONS_ENABLED=='true':
                            from app.commercial.admin_access import verified_actor
                            from app.commercial.subscription_auto import AccountAutoLease
                            account_lease=AccountAutoLease(self._subscriptions.service(),verified_actor(cloud_context.request),audio_source,
                                run_id=self._client_relay.stream_id if self._client_relay else None)
                            await account_lease.start()
                            if self._client_relay:
                                self._client_relay.lease = account_lease
                            cloud_context.request.state._subscription_auto=account_lease
                            lease_watcher=asyncio.create_task(watch_lease())
                        if audio_source in ('system', 'both') and self._client_relay is None:
                            if self._system_cleanup_failed:
                                await emit(request.request_id, "error", pb.ErrorEvent(code="system_cleanup_failed", message="Restart the local backend before Computer Auto."))
                                return
                            # Await in this RPC task: canceling a wait_for child after it acquired
                            # the lock can orphan ownership before system_owned is set.
                            # Electron bounds startup and cancels this wait on Stop/disconnect.
                            await self._system_owner.acquire()
                            system_owned = True
                        # Negotiate before opening STT: a provider can immediately
                        # publish a question during startup. Ack must precede it.
                        answer_version = 1 if (start.answer_stream_version == 1 and answer_enabled and
                                               cloud_context and settings.ENABLE_SESSION_ANSWER_MODELS) else 0
                        if answer_version:
                            await emit(request.request_id, 'answer_stream_capabilities', pb.AnswerStreamCapabilities(version=answer_version))
                        if stt_enabled:
                            await open_stt()
                        if audio_source in ('system', 'both') and self._client_relay is None:
                            try:
                                await open_system_capture()
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                await emit(request.request_id, 'error', pb.ErrorEvent(code='system_audio_unavailable',
                                    message='Computer capture could not start. Check Windows default output and restart Auto Mode.'))
                                return
                        if auto_mode:
                            await emit(request.request_id, "status", pb.Status(code="auto_pipeline_ready", message="Experimental Auto pipeline ready.", system_audio=pb.SystemAudioDiagnostics(active_audio_source=audio_source, transcript_source=audio_source, question_source=audio_source, answer_source_audio=audio_source)))
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
                            if audio_source == 'system' and self._client_relay is None:
                                await emit(request.request_id,'error',pb.ErrorEvent(code='unsupported_source',message='System capture owns the audio stream.'))
                                return
                            chunk = request.audio_chunk
                            if not chunk.audio or len(chunk.audio) > 65536 or len(chunk.audio) % 2 or chunk.sample_rate != 16000 or chunk.channels != 1 or chunk.encoding != "linear16":
                                await emit(request.request_id, "error", pb.ErrorEvent(
                                    code="invalid_audio", message="Expected bounded mono 16 kHz linear16 PCM."))
                                return
                            if self._client_relay:
                                if not await self._client_relay.accept(request.sequence_number, chunk.audio):
                                    continue
                            if audio_source == 'both' and self._client_relay is None:
                                mixer.push('microphone', chunk.audio, time.monotonic(), request.sequence_number, request.timestamp_ms)
                            elif stt_enabled:
                                if socket is None:
                                    await open_stt()
                                if account_lease and account_lease.remaining()<=0:
                                    raise PermissionError('Auto authorization expired')
                                await asyncio.wait_for(socket.send(chunk.audio), timeout=min(2,account_lease.remaining()) if account_lease else 2)
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
                            question_intake=question_intake_diagnostics({**intake, **utterance.snapshot()}) if auto_mode else None,
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
            except Exception as error:
                from app.commercial.catalog_store import CatalogStoreError, ErrorCode
                code = ({ErrorCode.EXHAUSTED:'subscription_auto_exhausted',ErrorCode.CONFLICT:'subscription_auto_busy',ErrorCode.DENIED:'subscription_denied'}.get(error.code,'subscription_unavailable')
                        if isinstance(error,CatalogStoreError) else 'subscription_denied' if isinstance(error,PermissionError) else 'stt_unavailable')
                await emit(last_request_id, "error", pb.ErrorEvent(
                    code=code, message="Auto authorization or transport is unavailable. Check your account and retry."))
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
            resources = start_resource_cleanup()
            async def cleanup():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await resources
            # Strong registry ownership outlives this RPC's bounded wait. The same
            # absolute deadline also covers an earlier explicit Stop/end join.
            closing = _track_cleanup(cleanup(), _rpc_cleanup_tasks)
            if await _join_cleanup({closing}, cleanup_deadline):
                raise asyncio.CancelledError()


async def start_server(host="127.0.0.1", port=50051, max_message_mb=4, subscriptions=None):
    # There is no authentication/TLS integration in G1. Never bind externally.
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise ValueError("G1 gRPC is restricted to loopback hosts.")
    if not 0 <= port <= 65535 or not 1 <= max_message_mb <= 64:
        raise ValueError("Invalid gRPC port or message limit.")
    limit = max_message_mb * 1024 * 1024
    server = grpc.aio.server(options=[("grpc.max_receive_message_length", limit),
                                      ("grpc.max_send_message_length", limit)])
    rpc.add_InterviewRealtimeServiceServicer_to_server(InterviewRealtimeService(subscriptions), server)
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
        try:
            await server.stop(grace=2)
        finally:
            await shutdown_cleanup()


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
