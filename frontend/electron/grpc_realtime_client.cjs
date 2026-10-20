const path = require('path')
const { AnswerStreamState, uint } = require('./answer_stream_state.cjs')
const { randomUUID } = require('crypto')

function createTransport(address, protoPath) {
  const grpc = require('@grpc/grpc-js')
  const loader = require('@grpc/proto-loader')
  const definition = loader.loadSync(protoPath, { keepCase: true, longs: String, oneofs: true })
  const Service = grpc.loadPackageDefinition(definition).intervuai.realtime.v1.InterviewRealtimeService
  return new Service(address, grpc.credentials.createInsecure(), {
    'grpc.max_receive_message_length': 4 * 1024 * 1024,
    'grpc.max_send_message_length': 4 * 1024 * 1024,
  })
}

class GrpcRealtimeClient {
  constructor({ env = process.env, transportFactory = createTransport, timeoutMs = 3000, getCloudAuthorization = async () => { throw Error('auth_unavailable') }, getCloudAuthAvailable = () => false,
    protoPath = path.join(__dirname, 'protos', 'interview_realtime.proto') } = {}) {
    this.enabled = String(env.ELECTRON_GRPC_REALTIME_ENABLED || 'false').toLowerCase() === 'true'
    this.manualPipelineEnabled = String(env.USE_GRPC_MANUAL_PIPELINE || "false").toLowerCase() === "true"
    // Prefer Auto when the deployment explicitly enables transport and audio.
    this.autoPipelineEnabled = String(env.USE_GRPC_AUTO_PIPELINE || 'true').toLowerCase() === 'true'
    this.cloudContextPipelineEnabled = String(env.USE_GRPC_CLOUD_CONTEXT_PIPELINE || 'true').toLowerCase() === 'true'
    this.getCloudAuthAvailable = getCloudAuthAvailable
    this.getCloudAuthorization = getCloudAuthorization
    this.cloudAuthStatus = 'not_started'
    this.cloudSessionVerified = this.cloudContextLoaded = false
    this.cloudAnswerSaveStatus = 'n/a'
    this.cloudBlockedReason = 'none'
    this.cloudStart = null
    this.cloudAuthCurrent = null
    this.autoPipelineReady = false
    this.autoStatus = 'idle'
    this.autoEventVersion = 0
    this.onAutoEvent = () => {}
    this.onManualEvent = () => {}
    this.manualEventVersion = 0
    this.manualRun = 0
    this.manualTimings = {}
    this.manualPipelineReady = false
    this.manualStatus = "idle"
    this.sessionMode = "diagnostics"
    this.audioEnabled = String(env.ELECTRON_GRPC_AUDIO_ENABLED || 'false').toLowerCase() === 'true'
    this.audioChunksSent = this.audioBytesSent = this.backendChunksReceived = this.backendBytesReceived = 0
    this.lastAudioStatus = 'idle'
    this.sttEnabled = false
    this.partialTranscriptCount = this.finalTranscriptCount = 0
    this.lastTranscriptEventType = 'none'
    this.sttProvider = 'none'
    this.currentTranscript = ''
    this.sttChunksForwarded = this.sttBytesForwarded = this.sttCallbackCount = this.nonSilentChunks = 0
    this.sttBridgeConnected = false
    this.sttStatus = 'idle'
    this.systemAudio = {}
    this.questionIntake = {}
    this.pcmDiagnostics = {}
    this.answerStreamEnabled = false
    this.questionsDetectedCount = this.answerStartedCount = this.answerDeltaCount = this.answerCompletedCount = 0
    this.lastAnswerStatus = 'idle'
    this.answerCategory = this.answerProvider = 'none'
    this.currentQuestion = this.currentAnswer = ''
    this.answerRequestId = this.completedAnswerRequestId = this.answerFailureCode = this.answerFailureRequestId = ''
    this.host = env.ELECTRON_GRPC_REALTIME_HOST || '127.0.0.1'
    this.port = Number(env.ELECTRON_GRPC_REALTIME_PORT || 50051)
    this.transportFactory = transportFactory
    this.protoPath = protoPath
    this.timeoutMs = timeoutMs
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    this.pending = new Map()
    this.connectionWaiters = new Set()
    this.answerState = new AnswerStreamState()
    this.autoPublication = null
    this.epoch = 0
    this.health = { grpc_health: 'unknown', grpc_last_health_success: null, grpc_last_health_failure: null,
      grpc_health_failure_reason: 'none', grpc_stt_available: false, grpc_answer_available: false,
      grpc_auto_available: false, grpc_cloud_context_available: false, grpc_system_audio_available: false, grpc_combined_audio_available: false }
    this.generationCommitted = false
    this.questionTransport = this.answerTransport = 'none'
    this.questionStage = 'idle'
    this.lastFailureReason = 'none'
    this.audioEverSent = false
    this.systemCleanup = null
    this.systemCleanupStatus = 'clean'
  }

  publishAuto(coalesce = false) {
    if (coalesce && this.autoPublication !== null) return
    if (!coalesce) { clearTimeout(this.autoPublication); this.autoPublication = null }
    const epoch = this.epoch, identity = this.answerState.snapshot()
    const publish = () => {
      this.autoPublication = null
      if (epoch !== this.epoch || (coalesce && (!identity ||
          ['requestId', 'retry_attempt', 'provider_attempt', 'display_revision', 'accepted_turn', 'terminal'].some(key => identity[key] !== this.answerState.turn?.[key])))) return
      try { this.onAutoEvent(this.getStatus()) } catch { /* Polling remains available. */ }
    }
    if (coalesce) this.autoPublication = setTimeout(publish, 16)
    else publish()
  }

  checkHealth() {
    if (this.healthChecking) return this.healthChecking
    const task = (async () => {
      let probe
      if (this.systemCleanup) await this.systemCleanup
      this.health.grpc_health = 'checking'
      try {
        if (!this.enabled) throw Error('grpc_unavailable')
        if (!['127.0.0.1', 'localhost', '::1'].includes(this.host) || !Number.isInteger(this.port) || this.port < 1 || this.port > 65535) throw Error('grpc_unavailable')
        const address = this.host === '::1' ? `[::1]:${this.port}` : `${this.host}:${this.port}`
        probe = this.transportFactory(address, this.protoPath)
        const result = await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(Error('grpc_connection_timeout')), this.timeoutMs)
          try {
            probe.CheckHealth({}, { deadline: Date.now() + this.timeoutMs }, (error, response) => {
              clearTimeout(timer)
              if (error) reject(Error('grpc_health_failed')); else resolve(response)
            })
          } catch { clearTimeout(timer); reject(Error('grpc_health_failed')) }
        })
        this.health = { ...this.health, grpc_health: 'healthy', grpc_last_health_success: Date.now(),
          grpc_health_failure_reason: 'none', grpc_stt_available: result.stt_available === true,
          grpc_answer_available: result.answer_stream_available === true, grpc_auto_available: result.auto_available === true,
          grpc_cloud_context_available: result.cloud_context_available === true,
          grpc_system_audio_available: result.system_audio_available === true, grpc_combined_audio_available: result.combined_audio_available === true }
        if (result.system_audio_available === true && !this.stream) this.systemCleanupStatus = 'clean'
      } catch (error) {
        this.health = { ...this.health, grpc_health: 'unavailable', grpc_last_health_failure: Date.now(),
          grpc_health_failure_reason: ['grpc_unavailable', 'grpc_connection_timeout'].includes(error.message) ? error.message : 'grpc_health_failed',
          grpc_stt_available: false, grpc_answer_available: false, grpc_auto_available: false, grpc_cloud_context_available: false, grpc_system_audio_available: false, grpc_combined_audio_available: false }
      } finally { try { probe?.close() } catch { /* Probe owns only its channel. */ } }
      return this.getStatus()
    })()
    this.healthChecking = task
    task.finally(() => { if (this.healthChecking === task) this.healthChecking = null })
    return task
  }

  getStatus() {
    if (this.cloudAuthCurrent && !this.cloudAuthCurrent()) {
      this.fail()
      this.cloudSessionVerified = this.cloudContextLoaded = false
      this.cloudAuthStatus = 'failed'; this.cloudBlockedReason = this.lastFailureReason = 'auth_unavailable'
    }
    return { ...this.health, grpc_audio_sent: this.audioEverSent,
      grpc_last_failure_reason: this.lastFailureReason !== 'none' ? this.lastFailureReason : this.health.grpc_health === 'unavailable' ? this.health.grpc_health_failure_reason : 'none', generation_committed: this.generationCommitted,
      question_transport: this.questionTransport, answer_transport: this.answerTransport, question_stage: this.questionStage,
      systemCleanupStatus: this.systemCleanupStatus, systemAudioPipelineSupported: this.health.grpc_system_audio_available === true, systemAudio: { ...this.systemAudio }, questionIntake: { ...this.questionIntake, low_audio_warning: this.sttStatus === 'mic_audio_too_low', mic_rms_level: this.pcmDiagnostics.rms || 0, mic_peak_level: this.pcmDiagnostics.peak || 0 }, cloudAuthAvailable: Boolean(this.getCloudAuthAvailable()), cloudContextPipelineEnabled: this.cloudContextPipelineEnabled, cloudAuthStatus: this.cloudAuthStatus,
      cloudSessionVerified: this.cloudSessionVerified, cloudContextLoaded: this.cloudContextLoaded,
      cloudAnswerSaveStatus: this.cloudAnswerSaveStatus, cloudBlockedReason: this.cloudBlockedReason, autoPipelineEnabled: this.autoPipelineEnabled, autoPipelineReady: this.autoPipelineReady, autoStatus: this.autoStatus, autoEventVersion: this.autoEventVersion, manualEventVersion: this.manualEventVersion, manualRun: this.manualRun, manualTimings: { ...this.manualTimings }, manualPipelineEnabled: this.manualPipelineEnabled, manualPipelineReady: this.manualPipelineReady, manualStatus: this.manualStatus, enabled: this.enabled, connectionStatus: this.status, lastPingResult: this.lastPing, lastErrorMessage: this.lastError,
      audioEnabled: this.enabled && this.audioEnabled, audioChunksSent: this.audioChunksSent, audioBytesSent: this.audioBytesSent,
      backendChunksReceived: this.backendChunksReceived, backendBytesReceived: this.backendBytesReceived, lastAudioStatus: this.lastAudioStatus, sttEnabled: this.sttEnabled,
      partialTranscriptCount: this.partialTranscriptCount, finalTranscriptCount: this.finalTranscriptCount,
      lastTranscriptEventType: this.lastTranscriptEventType, sttProvider: this.sttProvider, currentTranscript: this.currentTranscript,
      sttChunksForwarded: this.sttChunksForwarded, sttBytesForwarded: this.sttBytesForwarded,
      sttCallbackCount: this.sttCallbackCount, nonSilentChunks: this.nonSilentChunks,
      sttBridgeConnected: this.sttBridgeConnected, sttStatus: this.sttStatus, pcmDiagnostics: this.pcmDiagnostics,
      answerStreamEnabled: this.answerStreamEnabled, questionsDetectedCount: this.questionsDetectedCount,
      answerStartedCount: this.answerStartedCount, answerDeltaCount: this.answerDeltaCount,
      answerCompletedCount: this.answerCompletedCount, lastAnswerStatus: this.lastAnswerStatus,
      answerCategory: this.answerCategory, answerProvider: this.answerProvider,
      answerFailureRequestId: this.answerFailureRequestId || '', answerRequestId: this.answerRequestId || '', answerFailureCode: this.answerFailureCode || '',
      answerStreamVersion: this.answerState.version,
      answerStreamIdentity: this.answerState.snapshot() && { ...this.answerState.snapshot(), run: this.manualRun, epoch: this.epoch, sessionId: this.sessionId, snapshotVersion: this.autoEventVersion },
      currentQuestion: this.currentQuestion, currentAnswer: this.currentAnswer }
  }

  connect() {
    if (!this.enabled || this.status === 'connected') return Promise.resolve(this.getStatus())
    if (this.connecting) return this.connecting
    const epoch = this.epoch
    this.status = 'connecting'
    const task = (async () => {
      let failureReason = 'grpc_connection_timeout'
      try {
        // G2 deliberately provides no external-host override before TLS/auth exists.
        if (!['127.0.0.1', 'localhost', '::1'].includes(this.host) || !Number.isInteger(this.port) || this.port < 1 || this.port > 65535) {
          throw Error('invalid configuration')
        }
        const address = this.host === '::1' ? `[::1]:${this.port}` : `${this.host}:${this.port}`
        this.client = this.transportFactory(address, this.protoPath)
        await this.waitForConnection(done => this.client.waitForReady(Date.now() + this.timeoutMs, done), this.timeoutMs)
        failureReason = 'grpc_start_failed'
        if (epoch !== this.epoch) return this.getStatus()
        let metadata
        if (this.cloudStart?.cloud_context_requested) {
          this.cloudAuthStatus = 'verifying'
          const auth = await this.waitForConnection(done => {
            Promise.resolve().then(() => this.getCloudAuthorization()).then(value => done(null, value), done)
          }, 10000)
          if (epoch !== this.epoch) return this.getStatus()
          if (!auth?.isCurrent?.()) throw Error('auth_unavailable')
          metadata = new (require('@grpc/grpc-js').Metadata)()
          metadata.set('authorization', auth.authorization)
          this.cloudAuthStatus = 'authorized_pending_ready'
          this.cloudAuthCurrent = auth.isCurrent
        }
        const stream = metadata ? this.client.StreamInterview(metadata) : this.client.StreamInterview()
        this.stream = stream
        stream.on('data', (event) => {
          if (epoch !== this.epoch || (event.session_id && event.session_id !== this.sessionId)) return
          if (this.cloudAuthCurrent && !this.cloudAuthCurrent()) { this.fail(); this.cloudSessionVerified = this.cloudContextLoaded = false; this.cloudAuthStatus = 'failed'; this.cloudBlockedReason = 'auth_unavailable'; return }
          const answerKind = ['question_detected', 'answer_started', 'answer_delta', 'answer_replaced', 'answer_completed', 'answer_error'].find(kind => event[kind])
          if (this.sessionMode === 'auto_pipeline' && !this.generationCommitted && event.answer_stream_capabilities && event.session_id === this.sessionId) this.answerState.acknowledge(event)
          if (this.answerState.version && !answerKind && !event.answer_stream_capabilities) {
            const sequence = uint(event.sequence_number)
            if (event.session_id !== this.sessionId || sequence === null || BigInt(sequence) <= this.answerState.sequence) return
            this.answerState.sequence = BigInt(sequence)
          }
          if (event.status?.system_audio) {
            this.systemAudio = { ...event.status.system_audio }
            this.backendChunksReceived = Number(event.status.total_chunks || this.backendChunksReceived)
            this.backendBytesReceived = Number(event.status.total_audio_bytes || this.backendBytesReceived)
          }
          if (event.status?.question_intake) this.questionIntake = Object.fromEntries(Object.entries(event.status.question_intake)
            .filter(([key]) => !['last_ignored_transcript', 'utterance_buffer_text'].includes(key)))
          const code = event.status?.code
          if (this.answerState.version && ['auto_cooldown', 'auto_listening', 'answer_save_pending', 'answer_saved', 'answer_save_failed'].includes(code) &&
              this.answerRequestId && (event.request_id !== this.answerRequestId ||
                (['auto_cooldown', 'auto_listening'].includes(code) && !this.answerState.turn?.terminal))) return
          if (code === 'auth_verified') this.cloudAuthStatus = 'verified'
          if (code === 'cloud_session_verified') this.cloudSessionVerified = true
          if (code === 'cloud_context_loaded') this.cloudContextLoaded = true
          if (['answer_save_pending', 'answer_saved', 'answer_save_failed'].includes(code)) {
            this.cloudAnswerSaveStatus = { answer_save_pending: 'pending', answer_saved: 'saved', answer_save_failed: 'failed' }[code]
            this.questionStage = code === 'answer_saved' ? 'cloud_save_completed' : code === 'answer_save_pending' ? 'cloud_save_started' : this.questionStage
          }
          const cloudAuthCodes = ['auth_unavailable', 'auth_invalid', 'token_expired', 'session_owner_mismatch', 'cloud_session_invalid', 'cloud_session_ended', 'selected_context_forbidden', 'cloud_context_rejected', 'cloud_context_flag_disabled', 'auth_context_required']
          if (this.cloudStart?.cloud_context_requested && cloudAuthCodes.includes(event.error?.code)) {
            this.cloudSessionVerified = this.cloudContextLoaded = false
            this.cloudAuthStatus = 'failed'
            this.cloudBlockedReason = event.error.code
          }
          if (event.provider === 'assemblyai_streaming') this.sttProvider = 'assemblyai_streaming'
          if (event.status?.code === 'auto_pipeline_ready') { this.autoPipelineReady = true; this.sttEnabled = true; this.answerStreamEnabled = true }
          if (['auto_cooldown', 'auto_listening'].includes(event.status?.code)) this.autoStatus = event.status.code
          if (event.status?.code === 'manual_pipeline_ready') this.manualPipelineReady = true
          if (['manual_generation_committed', 'manual_no_question'].includes(event.status?.code)) this.manualStatus = event.status.code
          if (event.status?.code === 'stt_enabled') this.sttEnabled = true
          const transcriptKind = event.final_transcript ? 'final_transcript' : event.partial_transcript ? 'partial_transcript' : null
          if (transcriptKind) {
            this.manualTimings.first_transcript_at ??= Date.now()
            this.sttEnabled = true
            this.sttProvider = event.provider === 'assemblyai_streaming' ? 'assemblyai_streaming' : 'unknown'
            this.lastTranscriptEventType = transcriptKind
            this.currentTranscript = String(event[transcriptKind].text || '').slice(0, 65536)
            if (transcriptKind === 'final_transcript') this.finalTranscriptCount++
            else this.partialTranscriptCount++
          }
          if (event.status && event.status.stt_status) {
            this.sttChunksForwarded = Number(event.status.stt_chunks_forwarded || 0)
            this.sttBytesForwarded = Number(event.status.stt_bytes_forwarded || 0)
            this.sttCallbackCount = Number(event.status.stt_callback_count || 0)
            this.nonSilentChunks = Number(event.status.non_silent_chunks || 0)
            this.sttBridgeConnected = Boolean(event.status.stt_bridge_connected)
            this.sttStatus = ['stt_no_transcript_yet', 'stt_receiving', 'idle'].includes(event.status.stt_status) ? event.status.stt_status : 'unknown'
          }
          if (event.status?.code === 'answer_stream_enabled') this.answerStreamEnabled = true
          if (answerKind === 'answer_replaced' && !this.answerState.version) return
          if (answerKind && this.answerState.version && (event.session_id !== this.sessionId || !this.answerState.accept(event, answerKind))) return
          if (answerKind) {
            if (answerKind !== 'question_detected' && this.answerRequestId && event.request_id && event.request_id !== this.answerRequestId) return
            if (answerKind !== 'question_detected' && event.request_id && this.completedAnswerRequestId === event.request_id) return
            this.generationCommitted = true
            this.questionTransport = 'grpc_realtime'
            if (answerKind !== 'question_detected') this.answerTransport = 'grpc_realtime'
            this.questionStage = { question_detected: 'question_detected', answer_started: 'generation_started', answer_delta: 'first_delta_received', answer_replaced: 'generation_started', answer_completed: 'answer_completed', answer_error: 'generation_failed' }[answerKind]
            const payload = event[answerKind]
            const timing = { question_detected: 'question_detected_at', answer_started: 'answer_started_at', answer_delta: 'first_answer_delta_at', answer_completed: 'answer_completed_at' }[answerKind]
            if (timing) this.manualTimings[timing] ??= Date.now()
            this.lastAnswerStatus = answerKind
            if (this.sessionMode === 'auto_pipeline') this.autoStatus = answerKind === 'answer_completed' ? 'auto_cooldown' : 'generating'
            if (['technical', 'behavioral', 'personal', 'general'].includes(payload.category)) this.answerCategory = payload.category
            if (['openai', 'groq', 'gemini', 'ollama', 'local'].includes(payload.provider)) this.answerProvider = payload.provider
            if (answerKind === 'question_detected') {
              this.answerRequestId = event.request_id || ''
              this.completedAnswerRequestId = ''
              this.answerFailureCode = this.answerFailureRequestId = ''
              this.questionsDetectedCount++
              this.cloudAnswerSaveStatus = 'n/a'
              this.currentQuestion = String(payload.text || '').slice(0, 65536)
              this.currentAnswer = ''
            } else if (answerKind === 'answer_started') this.answerStartedCount++
            else if (answerKind === 'answer_delta') {
              this.answerDeltaCount++
              this.currentAnswer = (this.currentAnswer + String(payload.text || '')).slice(0, 262144)
            } else if (answerKind === 'answer_replaced') {
              this.currentAnswer = String(payload.text || '').slice(0, 262144)
            } else if (answerKind === 'answer_completed') {
              this.completedAnswerRequestId = event.request_id || ''
              this.answerCompletedCount++
              this.currentAnswer = String(payload.text || '').slice(0, 262144)
            } else if (this.answerState.version === 1 || ['generation_failed', 'persistence_unavailable', 'generation_uncertain', 'generation_stopped', 'generation_processing'].includes(payload.code)) {
              this.currentAnswer = ''
              this.answerFailureCode = ['generation_failed', 'persistence_unavailable', 'generation_uncertain', 'generation_stopped', 'generation_processing'].includes(payload.code) ? payload.code : 'generation_uncertain'
              this.answerFailureRequestId = event.request_id || ''
              this.completedAnswerRequestId = event.request_id || ''
              this.autoStatus = 'auto_listening'
            } else this.lastError = 'Experimental answer unavailable. Retry.'
          }
          if (this.sessionMode === 'manual_pipeline' && this.manualPipelineEnabled && (answerKind || transcriptKind)) {
            this.manualEventVersion++
            // Only the bounded, whitelisted renderer snapshot crosses IPC, never raw provider events.
            try { this.onManualEvent(this.getStatus()) } catch { /* Polling remains a safe delivery fallback. */ }
          }
          if (this.sessionMode === 'auto_pipeline' && (answerKind || transcriptKind || ['auto_cooldown', 'auto_listening', 'answer_save_pending', 'answer_saved', 'answer_save_failed', 'question_intake'].includes(event.status?.code))) {
            this.autoEventVersion++
            this.publishAuto(answerKind === 'answer_delta' && this.answerState.version === 1)
          }
          const pending = this.pending.get(event.request_id)
          if (pending && event[pending.kind] !== undefined) {
            clearTimeout(pending.timer)
            this.pending.delete(event.request_id)
            pending.resolve(event)
          } else if (event.error) {
            const emptyManual = this.sessionMode === 'manual_pipeline' && event.error.code === 'no_transcript'
            this.fail()
            if (emptyManual) this.manualStatus = 'manual_no_question'
            if (event.error.code.startsWith('system_')) this.lastFailureReason = event.error.code
            this.lastError = event.error.code.startsWith('system_') ? 'Computer audio unavailable. Stop and restart Auto Mode; restart the local backend if cleanup remains incomplete.' : event.error.code === 'no_transcript'
              ? 'No final speech transcript received. Check microphone input and retry.'
              : cloudAuthCodes.includes(event.error.code)
                ? 'Cloud session unavailable. Sign in again or restart the session.'
                : 'Live STT unavailable. Check AssemblyAI configuration and retry.'
          }
        })
        stream.on('error', () => { if (epoch === this.epoch) this.fail() })
        stream.on('end', () => { if (epoch === this.epoch) this.fail() })
        this.sttEnabled = false
        this.partialTranscriptCount = this.finalTranscriptCount = 0
        this.lastTranscriptEventType = this.sttProvider = 'none'
        this.currentTranscript = ''
        this.systemAudio = {}
        this.questionIntake = {}
        this.pcmDiagnostics = {}
        this.answerStreamEnabled = false
        this.questionsDetectedCount = this.answerStartedCount = this.answerDeltaCount = this.answerCompletedCount = 0
        this.lastAnswerStatus = 'idle'
        this.answerCategory = this.answerProvider = 'none'
        this.currentQuestion = this.currentAnswer = ''
    this.answerRequestId = this.completedAnswerRequestId = this.answerFailureCode = this.answerFailureRequestId = ''
        this.lastPcmAt = null
        this.sttChunksForwarded = this.sttBytesForwarded = this.sttCallbackCount = this.nonSilentChunks = 0
        this.sttBridgeConnected = false
        this.sttStatus = 'idle'
        this.sessionId = randomUUID()
        this.audioChunksSent = this.audioBytesSent = this.backendChunksReceived = this.backendBytesReceived = 0
        await this.startSession()
        if (epoch === this.epoch) { this.status = 'connected'; this.lastError = '' }
      } catch {
        if (epoch === this.epoch) { const authFailed = Boolean(this.cloudStart?.cloud_context_requested) && this.cloudAuthStatus === 'verifying'; this.fail(); if (authFailed) { this.cloudSessionVerified = this.cloudContextLoaded = false; this.cloudAuthStatus = 'failed'; if (this.cloudBlockedReason === 'none') this.cloudBlockedReason = 'auth_unavailable'; this.lastFailureReason = this.cloudBlockedReason } else if (this.cloudAuthStatus !== 'failed') this.lastFailureReason = failureReason }
      }
      return this.getStatus()
    })()
    this.connecting = task
    task.finally(() => { if (this.connecting === task) this.connecting = null })
    return task
  }

  request(payload, kind) {
    if (!this.stream) return Promise.reject(Error('not connected'))
    const requestId = randomUUID()
    return new Promise((resolve, reject) => {
      // Optional provider setup/drain has its own bounded budget beyond the transport handshake.
      const deadlineMs = this.timeoutMs + (this.cloudStart?.cloud_context_requested && kind === 'ready' ? 20000 : kind === 'ready' || this.sttEnabled ? 5000 : 0)
      const timer = setTimeout(() => { this.pending.delete(requestId); reject(Error('timeout')) }, deadlineMs)
      this.pending.set(requestId, { kind, resolve, reject, timer })
      try { this.stream.write({ session_id: this.sessionId, request_id: requestId, ...payload }) }
      catch { clearTimeout(timer); this.pending.delete(requestId); reject(Error('transport unavailable')) }
    })
  }

  waitForConnection(start, timeoutMs) {
    return new Promise((resolve, reject) => {
      let settled = false
      const finish = (error, value) => {
        if (settled) return
        settled = true; clearTimeout(timer); this.connectionWaiters.delete(cancel)
        if (error) reject(Error('unavailable')); else resolve(value)
      }
      const cancel = () => finish(Error('closed'))
      const timer = setTimeout(() => finish(Error('timeout')), timeoutMs)
      this.connectionWaiters.add(cancel)
      try { start(finish) } catch { finish(Error('unavailable')) }
    })
  }

  async connectAuto(context = {}) {
    const keys = ['activeSessionId', 'selectedResumeId', 'jobContextId', 'source']
    if (!context || typeof context !== 'object' || Object.keys(context).some(key => !keys.includes(key))) throw Error('invalid context')
    for (const key of keys.slice(0, 3)) {
      if (context[key] != null && (typeof context[key] !== 'string' || (context[key] && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(context[key])))) throw Error('invalid context')
    }
    if (context.source && !['microphone', 'system', 'both'].includes(context.source)) throw Error('invalid source')
    if (context.source === 'both' && (this.health.grpc_health !== 'healthy' || !this.health.grpc_combined_audio_available)) {
      this.lastFailureReason = 'combined_audio_unavailable'
      return this.getStatus()
    }
    if (context.source === 'system' && (this.health.grpc_health !== 'healthy' || !this.health.grpc_system_audio_available)) {
      this.lastFailureReason = 'system_audio_unavailable'
      return this.getStatus()
    }
    const cloud = Boolean(context.activeSessionId || context.selectedResumeId || context.jobContextId)
    if (cloud && (!this.cloudContextPipelineEnabled || !context.activeSessionId)) {
      if (this.sessionMode === 'auto_pipeline') this.close()
      this.cloudBlockedReason = this.cloudContextPipelineEnabled ? 'cloud_session_invalid' : 'cloud_context_flag_disabled'
      return this.getStatus()
    }
    if (!this.enabled || !this.audioEnabled || !this.autoPipelineEnabled) return this.getStatus()
    if (this.sessionMode === 'auto_pipeline' && ['connecting', 'connected'].includes(this.status) && this.cloudAuthStatus !== 'failed' && (this.cloudStart?.active_session_id || '') === (context.activeSessionId || '') && (this.cloudStart?.selected_resume_id || '') === (context.selectedResumeId || '') && (this.cloudStart?.selected_job_context_id || '') === (context.jobContextId || '') && (this.cloudStart?.source || 'microphone') === (context.source || 'microphone')) return this.connect()
    const cleanup = this.close()
    const openingEpoch = this.epoch
    if (cleanup?.then) {
      const result = await cleanup
      if (openingEpoch !== this.epoch) return { autoPipelineReady: false, connectionStatus: 'disconnected' }
      if (result.systemCleanupStatus !== 'clean') {
        this.lastFailureReason = 'system_cleanup_failed'
        return this.getStatus()
      }
    }
    if (['system', 'both'].includes(context.source) && this.systemCleanupStatus !== 'clean') {
      this.lastFailureReason = 'system_cleanup_failed'
      return this.getStatus()
    }
    this.manualRun++
    this.generationCommitted = false
    this.questionTransport = this.answerTransport = 'none'
    this.questionStage = 'idle'
    this.lastFailureReason = 'none'
    this.autoEventVersion = 0
    this.autoStatus = 'idle'
    this.cloudAuthStatus = 'not_started'
    this.cloudSessionVerified = this.cloudContextLoaded = false
    this.cloudAnswerSaveStatus = 'n/a'
    this.cloudBlockedReason = 'none'
    this.cloudStart = cloud ? { source: context.source || 'microphone', cloud_context_requested: true,
      active_session_id: context.activeSessionId, selected_resume_id: context.selectedResumeId || '', selected_job_context_id: context.jobContextId || '' } : { source: context.source || 'microphone' }
    this.sessionMode = 'auto_pipeline'
    const run = this.manualRun
    const status = await this.connect()
    return run === this.manualRun ? status : { manualRun: run, autoPipelineReady: false, connectionStatus: 'disconnected' }
  }

  async connectManual() {
    if (!this.enabled || !this.audioEnabled || !this.manualPipelineEnabled) return this.getStatus()
    if (this.sessionMode === 'manual_pipeline' && ['connecting', 'connected'].includes(this.status)) return this.connect()
    // Manual capture owns one fresh stream; diagnostic sessions never generate for it.
    this.close()
    this.manualEventVersion = 0
    this.manualRun++
    this.manualTimings = { manual_start_at: Date.now() }
    this.sessionMode = 'manual_pipeline'
    this.manualStatus = 'idle'
    this.manualPipelineReady = false
    return this.connect()
  }

  recordUiTiming(run, field, at) {
    if (run !== this.manualRun || !Number.isInteger(run) || run < 1 ||
      !['first_main_ui_update_at', 'first_overlay_update_at'].includes(field) ||
      !Number.isFinite(at) || at < this.manualTimings.manual_start_at || at > Date.now() + 1000) return false
    if (this.manualTimings[field] != null) return false
    this.manualTimings[field] = at
    return true
  }

  startSession() {
    // Server-side capture may process audio before readiness reaches Electron.
    if (['system', 'both'].includes(this.cloudStart?.source)) this.audioEverSent = true
    return this.request({ start_session: { mode: this.sessionMode, ...this.cloudStart, ...(this.sessionMode === 'auto_pipeline' ? { answer_stream_version: 1 } : {}) } }, 'ready')
  }

  async sendAudioChunk(data, metadata = {}) {
    if (this.cloudStart?.source === 'system') { this.lastAudioStatus = 'unsupported_source'; return this.getStatus() }
    if (this.cloudAuthCurrent && !this.cloudAuthCurrent()) {
      this.fail()
      this.cloudSessionVerified = this.cloudContextLoaded = false
      this.cloudAuthStatus = 'failed'
      this.cloudBlockedReason = 'auth_unavailable'
      return this.getStatus()
    }
    if (!this.enabled || !this.audioEnabled || this.status !== 'connected') return this.getStatus()
    if (!(data instanceof Uint8Array) && !(data instanceof ArrayBuffer)) {
      this.lastAudioStatus = 'invalid_chunk'; if (this.sttEnabled) this.sttStatus = 'invalid_pcm_format'; return this.getStatus()
    }
    if (!data.byteLength || data.byteLength > 65536 || data.byteLength % 2) {
      this.lastAudioStatus = 'invalid_chunk'; if (this.sttEnabled) this.sttStatus = 'invalid_pcm_format'; return this.getStatus()
    }
    // One acknowledged chunk at a time bounds IPC/gRPC buffering.
    if (this.audioPending) { this.lastAudioStatus = 'backpressure'; return this.getStatus() }
    const epoch = this.epoch
    const audio = Buffer.from(data instanceof ArrayBuffer ? data : data.buffer, data instanceof ArrayBuffer ? 0 : data.byteOffset, data.byteLength)
    // Once audio may have reached the server, an unobserved commit is possible.
    this.audioEverSent = true
    if (this.sttEnabled) {
      let min = 32767, max = -32768, sum = 0, zero = 0, clipped = 0
      const count = audio.length / 2
      for (let offset = 0; offset < audio.length; offset += 2) {
        const value = audio.readInt16LE(offset)
        min = Math.min(min, value); max = Math.max(max, value)
        sum += (value / 32768) ** 2
        if (value === 0) zero++
        if (value === -32768 || value === 32767) clipped++
      }
      const now = Date.now()
      this.pcmDiagnostics = { inputSampleRate: Number.isFinite(metadata?.inputSampleRate) ? metadata.inputSampleRate : 0,
        inputChannelCount: Number.isFinite(metadata?.inputChannelCount) ? metadata.inputChannelCount : 0,
        sampleRate: 16000, channels: 1, byteLength: audio.length, durationMs: count / 16,
        min, max, rms: Math.sqrt(sum / count), peak: Math.max(Math.abs(min), Math.abs(max)) / 32768,
        clippedRatio: clipped / count, zeroRatio: zero / count,
        cadenceMs: this.lastPcmAt ? now - this.lastPcmAt : 0, evenByteLength: audio.length % 2 === 0 }
      this.lastPcmAt = now
    }
    const task = (async () => {
      try {
        const capturedAt = this.cloudStart?.source === 'both' && Number.isFinite(metadata?.captureTimestampMs) &&
          metadata.captureTimestampMs > 0 && metadata.captureTimestampMs <= Number.MAX_SAFE_INTEGER ? Math.round(metadata.captureTimestampMs) : Date.now()
        const response = await this.request({ sequence_number: this.audioChunksSent + 1, timestamp_ms: capturedAt, audio_chunk: { audio, sample_rate: 16000, channels: 1, encoding: 'linear16' } }, 'status')
        if (epoch !== this.epoch) return
        if (this.sttEnabled) this.pcmDiagnostics.backendEvenByteLength = response.status.code === 'audio_chunk_received'
        if (this.sttEnabled && this.pcmDiagnostics.rms < 0.005) this.sttStatus = 'mic_audio_too_low'
        this.audioChunksSent++
        this.audioBytesSent += audio.byteLength
        this.backendChunksReceived = Number(response.status.total_chunks || 0)
        this.backendBytesReceived = Number(response.status.total_audio_bytes || 0)
        this.lastAudioStatus = response.status.code === 'audio_chunk_received' ? 'audio_chunk_received' : 'not_implemented'
      } catch { if (epoch === this.epoch) { this.fail(); this.lastAudioStatus = 'failed' } }
    })()
    this.audioPending = task
    try { await task } finally { if (this.audioPending === task) this.audioPending = null }
    return this.getStatus()
  }

  async manualStop() {
    if (this.sessionMode === 'manual_pipeline') this.manualTimings.manual_stop_at ??= Date.now()
    if (!this.enabled || !this.audioEnabled || this.status !== 'connected') return this.getStatus()
    const epoch = this.epoch
    try {
      await this.audioPending
      if (epoch !== this.epoch) return this.getStatus()
      await this.request({ manual_stop: {} }, 'status')
      if (epoch === this.epoch) this.lastAudioStatus = 'audio_stopped'
    } catch { if (epoch === this.epoch) this.fail() }
    return this.getStatus()
  }

  async ping() {
    if (!this.enabled) return this.getStatus()
    if (this.status !== 'connected') { this.lastPing = 'not connected'; return this.getStatus() }
    const epoch = this.epoch
    try { await this.request({ ping: {} }, 'pong'); if (epoch === this.epoch) this.lastPing = 'pong' }
    catch { if (epoch === this.epoch) { this.fail(); this.lastPing = 'failed' } }
    return this.getStatus()
  }

  async finish(kind) {
    if (['system', 'both'].includes(this.cloudStart?.source)) return this.close()
    try { if (this.stream) await this.request({ [kind]: {} }, 'status') } catch { /* Safe local cleanup below. */ }
    return this.close()
  }
  cancel() { return this.finish('cancel') }
  endSession() { return this.finish('end_session') }

  fail() {
    const counters = Object.fromEntries(['questionsDetectedCount', 'answerStartedCount', 'answerDeltaCount', 'answerCompletedCount',
      'audioChunksSent', 'audioBytesSent', 'answerCategory', 'answerProvider', 'sttProvider'].map(key => [key, this[key]]))
    const failure = { audioSent: this.audioEverSent, committed: this.generationCommitted, question: this.currentQuestion, answer: this.currentAnswer,
      cloudAuthStatus: this.cloudAuthStatus, cloudBlockedReason: this.cloudBlockedReason,
      cloudSessionVerified: this.cloudSessionVerified, cloudContextLoaded: this.cloudContextLoaded,
      cloudAnswerSaveStatus: this.cloudAnswerSaveStatus, stage: this.questionStage,
      questionTransport: this.questionTransport, answerTransport: this.answerTransport }
    this.close()
    Object.assign(this, counters)
    this.generationCommitted = failure.committed
    this.audioEverSent = failure.audioSent
    this.currentQuestion = failure.question; this.currentAnswer = failure.answer
    this.cloudAuthStatus = failure.cloudAuthStatus; this.cloudBlockedReason = failure.cloudBlockedReason
    this.cloudSessionVerified = failure.cloudSessionVerified; this.cloudContextLoaded = failure.cloudContextLoaded
    this.cloudAnswerSaveStatus = failure.cloudAnswerSaveStatus
    this.questionStage = failure.stage; this.questionTransport = failure.questionTransport; this.answerTransport = failure.answerTransport
    this.lastFailureReason = failure.cloudAuthStatus === 'failed' ? failure.cloudBlockedReason : 'grpc_connection_failed'
    this.status = 'error'
    // Never forward gRPC details/metadata, which may contain sensitive values.
    this.lastError = 'Local gRPC connection failed. Check configuration and the G1 server.'
  }

  close(run) {
    if (run !== undefined && (!Number.isInteger(run) || run < 1)) throw Error('invalid run')
    if (run !== undefined && run !== this.manualRun) return this.getStatus()
    const system = ['system', 'both'].includes(this.cloudStart?.source)
    this.epoch++
    clearTimeout(this.autoPublication); this.autoPublication = null
    this.answerState = new AnswerStreamState()
    const stream = this.stream, client = this.client, sessionId = this.sessionId
    this.cloudStart = null
    this.cloudAuthCurrent = null
    this.cloudAuthStatus = 'not_started'
    this.cloudSessionVerified = this.cloudContextLoaded = false
    this.cloudAnswerSaveStatus = 'n/a'
    this.cloudBlockedReason = 'none'
    this.generationCommitted = false
    this.questionTransport = this.answerTransport = 'none'
    this.questionStage = 'idle'
    this.lastFailureReason = 'none'
    this.audioPending = null
    this.audioEverSent = false
    this.questionsDetectedCount = this.answerStartedCount = this.answerDeltaCount = this.answerCompletedCount = 0
    this.audioChunksSent = this.audioBytesSent = this.backendChunksReceived = this.backendBytesReceived = 0
    this.partialTranscriptCount = this.finalTranscriptCount = 0
    this.sttChunksForwarded = this.sttBytesForwarded = this.sttCallbackCount = this.nonSilentChunks = 0
    this.sttEnabled = this.answerStreamEnabled = false
    this.autoStatus = this.lastAnswerStatus = this.lastAudioStatus = this.sttStatus = 'idle'
    this.answerCategory = this.answerProvider = this.lastTranscriptEventType = this.sttProvider = 'none'
    this.questionIntake = {}; this.systemAudio = {}; this.pcmDiagnostics = {}
    this.stream = null
    this.client = null
    this.sessionId = null
    this.sttBridgeConnected = false
    this.manualPipelineReady = false
    this.autoPipelineReady = false
    this.sessionMode = "diagnostics"
    this.currentTranscript = ''
    this.currentQuestion = this.currentAnswer = ''
    this.answerRequestId = this.completedAnswerRequestId = this.answerFailureCode = this.answerFailureRequestId = ''
    this.connecting = null
    for (const cancel of this.connectionWaiters) cancel()
    this.connectionWaiters.clear()
    for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(Error('closed')) }
    this.pending.clear()
    if (system && stream) {
      this.systemCleanupStatus = 'cleaning'
      const requestId = randomUUID()
      const cleanup = new Promise(resolve => {
        const finish = clean => {
          clearTimeout(timer)
          stream.removeListener('data', onData); stream.removeListener('end', onEnd); stream.removeListener('error', onEnd)
          try { stream.cancel() } catch { /* Already closed. */ }
          try { client?.close() } catch { /* Already closed. */ }
          this.systemCleanupStatus = clean ? 'clean' : 'failed'
          resolve({ systemCleanupStatus: this.systemCleanupStatus })
        }
        let settled = false
        const settle = clean => { if (!settled) { settled = true; finish(clean) } }
        const onEnd = () => settle(false)
        const onData = event => {
          if (event.session_id === sessionId && event.request_id === requestId &&
              ['ended', 'system_cleanup_pending'].includes(event.status?.code)) settle(event.status.code === 'ended')
        }
        const timer = setTimeout(onEnd, this.timeoutMs + 5000)
        stream.on('data', onData); stream.on('end', onEnd); stream.on('error', onEnd)
        try { stream.write({ session_id: sessionId, request_id: requestId, end_session: {} }) } catch { onEnd() }
      })
      this.systemCleanup = cleanup
      void cleanup.then(() => { if (this.systemCleanup === cleanup) this.systemCleanup = null })
    } else {
      try { stream?.cancel() } catch { /* Already closed. */ }
      try { client?.close() } catch { /* Already closed. */ }
    }
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    return this.systemCleanup || this.getStatus()
  }
}

function registerGrpcRealtimeIpc(ipcMain, validateSender, client, onUiTiming = () => {}, onManualEvent = () => {}, onAutoEvent = () => {}) {
  client.onManualEvent = onManualEvent
  client.onAutoEvent = onAutoEvent
  for (const [channel, method] of [['checkHealth', 'checkHealth'], ['getStatus', 'getStatus'], ['connect', 'connect'], ['connectManual', 'connectManual'], ['connectAuto', 'connectAuto'], ['ping', 'ping'], ['close', 'close']]) {
    ipcMain.handle(`grpcRealtime:${channel}`, async (event, context) => { validateSender(event); return ['connectAuto', 'close'].includes(method) ? client[method](context) : client[method]() })
  }
  ipcMain.handle('grpcRealtime:uiTiming', async (event, run, field, at) => { validateSender(event); if (client.recordUiTiming(run, field, at)) onUiTiming({ manualRun: client.manualRun, first_main_ui_update_at: client.manualTimings.first_main_ui_update_at, first_overlay_update_at: client.manualTimings.first_overlay_update_at }) })
  ipcMain.handle('grpcRealtime:audioChunk', async (event, data, metadata) => { validateSender(event); return client.sendAudioChunk(data, metadata) })
  ipcMain.handle('grpcRealtime:manualStop', async (event) => { validateSender(event); return client.manualStop() })
}

module.exports = { GrpcRealtimeClient, registerGrpcRealtimeIpc }
