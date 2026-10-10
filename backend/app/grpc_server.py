"""Experimental loopback-only realtime transport; opt-in STT and answer diagnostics."""
import argparse
import hashlib
import re
from collections import deque
from contextlib import aclosing
import asyncio
import ipaddress
import json
import time

import grpc

from app.config import settings
from app.grpc_generated import interview_realtime_pb2 as pb
from app.grpc_generated import interview_realtime_pb2_grpc as rpc


AUTO_COOLDOWN_SECONDS = 4.0
STABLE_PARTIAL_SECONDS = 1.2


_system_cleanup_tasks = set()

class InterviewRealtimeService(rpc.InterviewRealtimeServiceServicer):
    async def StreamInterview(self, request_iterator, context):
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
        system_queue = asyncio.Queue(maxsize=3)
        cloud_context = None
        auto_mode = False
        auto_cooldown_until = 0.0
        manual_mode = False
        manual_stopped = False
        manual_turns = {}
        provider_epoch = 0
        answer_task = None
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

        def event(request_id, kind, payload):
            nonlocal sequence
            sequence += 1
            return pb.InterviewServerEvent(
                session_id=session_id or "", request_id=request_id,
                sequence_number=sequence, timestamp_ms=int(time.time() * 1000),
                provider=(getattr(payload, "provider", "") or ("assemblyai_streaming" if stt_enabled else "none")), **{kind: payload})

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
                await emit(last_request_id, 'status', pb.Status(code='question_intake', question_intake=pb.QuestionIntake(**intake)))

        async def ignored(text, reason, final=True):
            if final: intake['final_transcripts_ignored'] += 1
            intake['last_ignored_transcript'] = text[:256]
            intake['last_ignored_reason'] = reason
            field = {'duplicate': 'dedupe_rejections', 'too_short': 'too_short_rejections'}.get(reason)
            if field: intake[field] += 1
            await intake_status()

        async def answer_worker():
            nonlocal auto_cooldown_until, generation_active
            from app.grpc_answer_pipeline import stream_question_answer
            while True:
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
                    async with aclosing(stream_question_answer(text, cloud_context=cloud_context) if cloud_context else stream_question_answer(text)) as pipeline:
                        async for item in pipeline:
                            kind = item.get("type")
                            category = item.get("category") or category
                            provider = item.get("provider") or provider
                            if kind == "rejected":
                                intake['detection_rejections'] += 1
                                await ignored(text, item.get('reason') or 'not_question', is_final)
                            elif kind == "save_status":
                                await emit(request_id, "status", pb.Status(code=item["code"]))
                            elif kind == "question":
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
                            elif kind in ("replacement", "result") and item.get("text"):
                                answer = str(item["text"])
                                if len(answer) > 262144:
                                    raise RuntimeError("Answer limit exceeded.")
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
                    await emit(request_id, "answer_error", pb.ErrorEvent(
                        code="answer_unavailable", message="Experimental answer unavailable or timed out. Retry."))
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
            nonlocal system_capture, system_session, system_reader, system_sender
            from app.services.system_audio_capture import SystemAudioCaptureService
            from starlette.concurrency import run_in_threadpool
            system_capture = SystemAudioCaptureService()
            system_metrics.update(system_capture_started_at=time.time()*1000, active_audio_source='system', transcript_source='system', question_source='system', answer_source_audio='system', system_target_rate=16000, system_dropped_chunks=0)
            system_session = await run_in_threadpool(system_capture.open_streaming_loopback_session, target_sample_rate=16000, chunk_ms=100, debug_save_enabled=False)
            async def capture():
                nonlocal read_future
                tail = b''
                try:
                    while True:
                        read_future = asyncio.ensure_future(run_in_threadpool(system_capture.read_streaming_pcm_chunk, system_session))
                        chunk = await asyncio.wait_for(asyncio.shield(read_future), timeout=2)
                        now = time.time()*1000
                        if not system_metrics.get('system_first_pcm_chunk_at'): system_metrics['system_first_pcm_chunk_at'] = now
                        if chunk.rms_level > .005 and not system_metrics.get('system_first_non_silent_chunk_at'): system_metrics['system_first_non_silent_chunk_at'] = now
                        if not chunk.pcm_bytes: system_metrics['system_dropped_chunks'] += 1
                        if len(chunk.pcm_bytes) % 2: raise RuntimeError('invalid PCM')
                        tail += chunk.pcm_bytes
                        system_metrics.update(system_sample_rate=chunk.input_sample_rate, system_rms=chunk.rms_level, system_peak=chunk.peak_level,
                            system_resample_latency_ms=chunk.resample_latency_ms)
                        while len(tail) >= 3200:
                            frame, tail = tail[:3200], tail[3200:]
                            if system_queue.full():
                                system_queue.get_nowait()
                                system_metrics['system_dropped_chunks'] += 1
                            system_queue.put_nowait(frame)
                        if len(tail) > 65536: raise RuntimeError('capture buffer exceeded')
                except asyncio.CancelledError: raise
                except Exception:
                    await emit(last_request_id,'error',pb.ErrorEvent(code='system_audio_unavailable',message='System audio capture unavailable. Stop and retry the existing flow.'))
                    await output.put(None)
            async def send():
                nonlocal total_chunks, total_audio_bytes, stt_chunks, stt_bytes, non_silent_chunks
                try:
                    while True:
                        frame = await system_queue.get()
                        system_metrics.update(system_chunk_bytes=len(frame),system_pcm_duration_ms=len(frame)/32,system_buffer_queue_depth=system_queue.qsize(),
                            system_silence_ratio=sum(frame[i:i+2] == b'\0\0' for i in range(0,len(frame),2))/(len(frame)//2))
                        if not system_metrics.get('system_first_chunk_sent_to_grpc_at'): system_metrics['system_first_chunk_sent_to_grpc_at'] = time.time()*1000
                        await asyncio.wait_for(socket.send(frame),timeout=2)
                        total_chunks += 1; total_audio_bytes += len(frame); stt_chunks += 1; stt_bytes += len(frame)
                        if any(frame): non_silent_chunks += 1
                        await emit(last_request_id,'status',pb.Status(code='system_audio_metrics',total_chunks=total_chunks,total_audio_bytes=total_audio_bytes,
                            stt_chunks_forwarded=stt_chunks,stt_bytes_forwarded=stt_bytes,stt_bridge_connected=True,
                            system_audio=pb.SystemAudioDiagnostics(**system_metrics),question_intake=pb.QuestionIntake(**{**intake,**utterance.snapshot()})))
                except asyncio.CancelledError: raise
                except Exception:
                    await emit(last_request_id,'error',pb.ErrorEvent(code='system_audio_unavailable',message='System audio stream unavailable. Stop and retry.'))
                    await output.put(None)
            system_reader = asyncio.create_task(capture())
            system_sender = asyncio.create_task(send())
            await emit(last_request_id,'status',pb.Status(code='system_audio_metrics',system_audio=pb.SystemAudioDiagnostics(**system_metrics)))

        async def close_system_capture():
            nonlocal system_session
            for task in (system_reader, system_sender):
                if task: task.cancel()
            await asyncio.gather(*(task for task in (system_reader,system_sender) if task),return_exceptions=True)
            if read_future and not read_future.done():
                await asyncio.wait({read_future}, timeout=1)
            if system_session:
                from starlette.concurrency import run_in_threadpool
                session = system_session
                system_session = None
                if read_future and not read_future.done():
                    # A timed-out native read still owns the device. Defer close,
                    # rather than race it or block RPC shutdown indefinitely.
                    async def deferred_close():
                        await asyncio.gather(read_future, return_exceptions=True)
                        await run_in_threadpool(system_capture.close_streaming_loopback_session, session)
                    task = asyncio.create_task(deferred_close())
                    _system_cleanup_tasks.add(task)
                    task.add_done_callback(_system_cleanup_tasks.discard)
                else:
                    if read_future: await asyncio.gather(read_future, return_exceptions=True)
                    await run_in_threadpool(system_capture.close_streaming_loopback_session, session)

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
            if answer_task:
                answer_task.cancel()
                await asyncio.gather(answer_task, return_exceptions=True)

        async def process_requests():
            nonlocal audio_source, cloud_context, auto_mode, manual_mode, manual_stopped, session_id, total_chunks, total_audio_bytes, last_request_id, stopping_stt, stt_chunks, stt_bytes, non_silent_chunks
            canceled = False
            try:
                async for request in request_iterator:
                    last_request_id = request.request_id
                    kind = request.WhichOneof("event")
                    if kind == "ping":
                        await emit(request.request_id, "pong", pb.Empty())
                    elif kind in ("cancel", "end_session"):
                        await stop_answers()
                        await close_system_capture()
                        await close_stt()
                        await emit(request.request_id, "status", pb.Status(
                            code="canceled" if kind == "cancel" else "ended", message="Stream closed."))
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
                        if manual_mode and not (settings.USE_GRPC_MANUAL_PIPELINE and answer_enabled):
                            await emit(request.request_id, "error", pb.ErrorEvent(code="manual_unavailable", message="Manual gRPC pipeline is unavailable."))
                            return
                        session_id = request.session_id
                        start = request.start_session
                        audio_source = start.source or 'microphone'
                        if audio_source not in ('microphone','system') or (audio_source == 'system' and not auto_mode):
                            await emit(request.request_id,'error',pb.ErrorEvent(code='unsupported_source',message='Audio source is unavailable.'))
                            return
                        if start.cloud_context_requested:
                            if not settings.USE_GRPC_CLOUD_CONTEXT_PIPELINE or not auto_mode or start.source not in ("microphone", "system"):
                                await emit(request.request_id, "error", pb.ErrorEvent(code="cloud_context_flag_disabled", message="Cloud realtime context unavailable."))
                                return
                            from app.grpc_cloud_context import GrpcCloudContext, CloudContextRejected
                            from starlette.concurrency import run_in_threadpool
                            await emit(request.request_id, "status", pb.Status(code="auth_verifying"))
                            try:
                                cloud_context = await asyncio.wait_for(run_in_threadpool(
                                    GrpcCloudContext.authorize, start, context.invocation_metadata()), timeout=15)
                            except Exception as exc:
                                code = exc.code if isinstance(exc, CloudContextRejected) else "cloud_context_rejected"
                                await emit(request.request_id, "error", pb.ErrorEvent(code=code, message="Cloud realtime context could not be verified. Use the authenticated fallback."))
                                return
                            for code in ("auth_verified", "cloud_session_verified", "cloud_context_loaded"):
                                await emit(request.request_id, "status", pb.Status(code=code))
                        elif start.active_session_id or start.selected_resume_id or start.selected_job_context_id:
                            await emit(request.request_id, "error", pb.ErrorEvent(code="auth_context_required", message="Cloud context requires verified authentication."))
                            return
                        if stt_enabled:
                            await open_stt()
                        if audio_source == 'system': await open_system_capture()
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
                            if audio_source == 'system':
                                await emit(request.request_id,'error',pb.ErrorEvent(code='unsupported_source',message='System capture owns the audio stream.'))
                                return
                            chunk = request.audio_chunk
                            if not chunk.audio or len(chunk.audio) > 65536 or len(chunk.audio) % 2 or chunk.sample_rate != 16000 or chunk.channels != 1 or chunk.encoding != "linear16":
                                await emit(request.request_id, "error", pb.ErrorEvent(
                                    code="invalid_audio", message="Expected bounded mono 16 kHz linear16 PCM."))
                                return
                            if stt_enabled:
                                if socket is None:
                                    await open_stt()
                                await asyncio.wait_for(socket.send(chunk.audio), timeout=2)
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
                            question_intake=pb.QuestionIntake(**{**intake, **utterance.snapshot()}) if auto_mode else None,
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
            except Exception:
                await emit(last_request_id, "error", pb.ErrorEvent(
                    code="stt_unavailable", message="Live STT unavailable. Check provider configuration and retry."))
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
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await close_system_capture()
            await close_stt()
            await stop_answers()


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
