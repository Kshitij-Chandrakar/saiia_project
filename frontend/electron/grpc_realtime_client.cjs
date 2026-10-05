const path = require('path')
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
  constructor({ env = process.env, transportFactory = createTransport, timeoutMs = 3000,
    protoPath = path.join(__dirname, 'protos', 'interview_realtime.proto') } = {}) {
    this.enabled = String(env.ELECTRON_GRPC_REALTIME_ENABLED || 'false').toLowerCase() === 'true'
    this.manualPipelineEnabled = String(env.USE_GRPC_MANUAL_PIPELINE || "false").toLowerCase() === "true"
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
    this.pcmDiagnostics = {}
    this.answerStreamEnabled = false
    this.questionsDetectedCount = this.answerStartedCount = this.answerDeltaCount = this.answerCompletedCount = 0
    this.lastAnswerStatus = 'idle'
    this.answerCategory = this.answerProvider = 'none'
    this.currentQuestion = this.currentAnswer = ''
    this.host = env.ELECTRON_GRPC_REALTIME_HOST || '127.0.0.1'
    this.port = Number(env.ELECTRON_GRPC_REALTIME_PORT || 50051)
    this.transportFactory = transportFactory
    this.protoPath = protoPath
    this.timeoutMs = timeoutMs
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    this.pending = new Map()
    this.epoch = 0
  }

  getStatus() {
    return { manualEventVersion: this.manualEventVersion, manualRun: this.manualRun, manualTimings: { ...this.manualTimings }, manualPipelineEnabled: this.manualPipelineEnabled, manualPipelineReady: this.manualPipelineReady, manualStatus: this.manualStatus, enabled: this.enabled, connectionStatus: this.status, lastPingResult: this.lastPing, lastErrorMessage: this.lastError,
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
      currentQuestion: this.currentQuestion, currentAnswer: this.currentAnswer }
  }

  connect() {
    if (!this.enabled || this.status === 'connected') return Promise.resolve(this.getStatus())
    if (this.connecting) return this.connecting
    const epoch = this.epoch
    this.status = 'connecting'
    const task = (async () => {
      try {
        // G2 deliberately provides no external-host override before TLS/auth exists.
        if (!['127.0.0.1', 'localhost', '::1'].includes(this.host) || !Number.isInteger(this.port) || this.port < 1 || this.port > 65535) {
          throw Error('invalid configuration')
        }
        const address = this.host === '::1' ? `[::1]:${this.port}` : `${this.host}:${this.port}`
        this.client = this.transportFactory(address, this.protoPath)
        await new Promise((resolve, reject) => this.client.waitForReady(Date.now() + this.timeoutMs, (error) => error ? reject(error) : resolve()))
        if (epoch !== this.epoch) return this.getStatus()
        const stream = this.client.StreamInterview()
        this.stream = stream
        stream.on('data', (event) => {
          if (epoch !== this.epoch) return
          if (event.provider === 'assemblyai_streaming') this.sttProvider = 'assemblyai_streaming'
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
          const answerKind = ['question_detected', 'answer_started', 'answer_delta', 'answer_completed', 'answer_error'].find(kind => event[kind])
          if (answerKind) {
            const payload = event[answerKind]
            const timing = { question_detected: 'question_detected_at', answer_started: 'answer_started_at', answer_delta: 'first_answer_delta_at', answer_completed: 'answer_completed_at' }[answerKind]
            if (timing) this.manualTimings[timing] ??= Date.now()
            this.lastAnswerStatus = answerKind
            if (['technical', 'behavioral', 'personal', 'general'].includes(payload.category)) this.answerCategory = payload.category
            if (['openai', 'groq', 'ollama', 'local'].includes(payload.provider)) this.answerProvider = payload.provider
            if (answerKind === 'question_detected') {
              this.questionsDetectedCount++
              this.currentQuestion = String(payload.text || '').slice(0, 65536)
              this.currentAnswer = ''
            } else if (answerKind === 'answer_started') this.answerStartedCount++
            else if (answerKind === 'answer_delta') {
              this.answerDeltaCount++
              this.currentAnswer = (this.currentAnswer + String(payload.text || '')).slice(0, 262144)
            } else if (answerKind === 'answer_completed') {
              this.answerCompletedCount++
              if (payload.text) this.currentAnswer = String(payload.text).slice(0, 262144)
            } else this.lastError = 'Experimental answer unavailable. Retry.'
          }
          if (this.sessionMode === 'manual_pipeline' && this.manualPipelineEnabled && (answerKind || transcriptKind)) {
            this.manualEventVersion++
            // Only the bounded, whitelisted renderer snapshot crosses IPC, never raw provider events.
            try { this.onManualEvent(this.getStatus()) } catch { /* Polling remains a safe delivery fallback. */ }
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
            this.lastError = event.error.code === 'no_transcript'
              ? 'No final speech transcript received. Check microphone input and retry.'
              : 'Live STT unavailable. Check AssemblyAI configuration and retry.'
          }
        })
        stream.on('error', () => { if (epoch === this.epoch) this.fail() })
        stream.on('end', () => { if (epoch === this.epoch) this.close() })
        this.sttEnabled = false
        this.partialTranscriptCount = this.finalTranscriptCount = 0
        this.lastTranscriptEventType = this.sttProvider = 'none'
        this.currentTranscript = ''
        this.pcmDiagnostics = {}
        this.answerStreamEnabled = false
        this.questionsDetectedCount = this.answerStartedCount = this.answerDeltaCount = this.answerCompletedCount = 0
        this.lastAnswerStatus = 'idle'
        this.answerCategory = this.answerProvider = 'none'
        this.currentQuestion = this.currentAnswer = ''
        this.lastPcmAt = null
        this.sttChunksForwarded = this.sttBytesForwarded = this.sttCallbackCount = this.nonSilentChunks = 0
        this.sttBridgeConnected = false
        this.sttStatus = 'idle'
        this.sessionId = randomUUID()
        this.audioChunksSent = this.audioBytesSent = this.backendChunksReceived = this.backendBytesReceived = 0
        await this.startSession()
        if (epoch === this.epoch) { this.status = 'connected'; this.lastError = '' }
      } catch {
        if (epoch === this.epoch) this.fail()
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
      const deadlineMs = this.timeoutMs + (kind === 'ready' || this.sttEnabled ? 5000 : 0)
      const timer = setTimeout(() => { this.pending.delete(requestId); reject(Error('timeout')) }, deadlineMs)
      this.pending.set(requestId, { kind, resolve, reject, timer })
      try { this.stream.write({ session_id: this.sessionId, request_id: requestId, ...payload }) }
      catch { clearTimeout(timer); this.pending.delete(requestId); reject(Error('transport unavailable')) }
    })
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

  startSession() { return this.request({ start_session: { mode: this.sessionMode } }, 'ready') }

  async sendAudioChunk(data, metadata = {}) {
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
        const response = await this.request({ audio_chunk: { audio, sample_rate: 16000, channels: 1, encoding: 'linear16' } }, 'status')
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
    try { if (this.stream) await this.request({ [kind]: {} }, 'status') } catch { /* Safe local cleanup below. */ }
    return this.close()
  }
  cancel() { return this.finish('cancel') }
  endSession() { return this.finish('end_session') }

  fail() {
    this.close()
    this.status = 'error'
    // Never forward gRPC details/metadata, which may contain sensitive values.
    this.lastError = 'Local gRPC connection failed. Check configuration and the G1 server.'
  }

  close() {
    this.epoch++
    const stream = this.stream, client = this.client
    this.stream = null
    this.client = null
    this.sessionId = null
    this.sttBridgeConnected = false
    this.manualPipelineReady = false
    this.sessionMode = "diagnostics"
    this.currentTranscript = ''
    this.currentQuestion = this.currentAnswer = ''
    this.connecting = null
    for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(Error('closed')) }
    this.pending.clear()
    try { stream?.cancel() } catch { /* Already closed. */ }
    try { client?.close() } catch { /* Already closed. */ }
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    return this.getStatus()
  }
}

function registerGrpcRealtimeIpc(ipcMain, validateSender, client, onUiTiming = () => {}, onManualEvent = () => {}) {
  client.onManualEvent = onManualEvent
  for (const [channel, method] of [['getStatus', 'getStatus'], ['connect', 'connect'], ['connectManual', 'connectManual'], ['ping', 'ping'], ['close', 'close']]) {
    ipcMain.handle(`grpcRealtime:${channel}`, async (event) => { validateSender(event); return client[method]() })
  }
  ipcMain.handle('grpcRealtime:uiTiming', async (event, run, field, at) => { validateSender(event); if (client.recordUiTiming(run, field, at)) onUiTiming({ manualRun: client.manualRun, first_main_ui_update_at: client.manualTimings.first_main_ui_update_at, first_overlay_update_at: client.manualTimings.first_overlay_update_at }) })
  ipcMain.handle('grpcRealtime:audioChunk', async (event, data, metadata) => { validateSender(event); return client.sendAudioChunk(data, metadata) })
  ipcMain.handle('grpcRealtime:manualStop', async (event) => { validateSender(event); return client.manualStop() })
}

module.exports = { GrpcRealtimeClient, registerGrpcRealtimeIpc }
