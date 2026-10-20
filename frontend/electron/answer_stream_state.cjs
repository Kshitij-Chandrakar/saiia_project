// Wire uint64 values stay decimal strings across IPC; comparisons never lose precision.
function uint(value, bits = 64) {
  if (value === undefined) value = 0
  if (typeof value === 'number' && (!Number.isSafeInteger(value) || value < 0)) return null
  if (!/^(0|[1-9][0-9]*)$/.test(String(value))) return null
  const result = BigInt(value)
  return result < (1n << BigInt(bits)) ? result.toString() : null
}
class AnswerStreamState {
  constructor() { this.version = 0; this.sequence = -1n; this.turn = null }
  acknowledge(event) {
    if (this.version || event.answer_stream_capabilities?.version !== 1 || this.turn) return
    const sequence = uint(event.sequence_number)
    if (sequence === null) return
    this.version = 1; this.sequence = BigInt(sequence)
  }
  accept(event, kind) {
    const sequence = uint(event.sequence_number), raw = event.answer_identity
    if (sequence === null || BigInt(sequence) <= this.sequence || !raw || !event.request_id) return false
    const identity = Object.fromEntries(['accepted_turn', 'display_revision', 'retry_attempt', 'provider_attempt']
      .map(key => [key, uint(raw[key], key.endsWith('attempt') ? 32 : 64)]))
    if (Object.values(identity).includes(null) || identity.accepted_turn === '0') return false
    const current = this.turn
    if (kind === 'question_detected') {
      if (current && (BigInt(identity.accepted_turn) <= BigInt(current.accepted_turn) || event.request_id === current.requestId)) return false
      this.turn = { ...identity, requestId: event.request_id, terminal: false, started: false }
    } else {
      if (!current || current.terminal || event.request_id !== current.requestId || identity.accepted_turn !== current.accepted_turn || identity.retry_attempt !== current.retry_attempt) return false
      if (kind === 'answer_replaced') {
        if (BigInt(identity.display_revision) <= BigInt(current.display_revision) || BigInt(identity.provider_attempt) < BigInt(current.provider_attempt)) return false
        Object.assign(current, identity)
      } else if (identity.provider_attempt !== current.provider_attempt || identity.display_revision !== current.display_revision) return false
      if (kind === 'answer_started') { if (current.started) return false; current.started = true }
      if (['answer_completed', 'answer_error'].includes(kind)) current.terminal = true
    }
    this.sequence = BigInt(sequence)
    return true
  }
  snapshot() {
    if (!this.version || !this.turn) return null
    const { started, ...identity } = this.turn
    return identity
  }
}
// Strip only stale answer content; unrelated Screen/toolbar controls still merge.
function fenceOverlayAnswer(next, current, live) {
  const incoming = next.grpcAnswerIdentity
  if (!incoming || (next.answerDisplayMode && next.answerDisplayMode !== 'answer')) return next
  const previous = current.grpcAnswerIdentity
  const stale = !live || ['run', 'epoch', 'sessionId', 'requestId', 'accepted_turn', 'retry_attempt', 'provider_attempt', 'display_revision', 'terminal']
    .some(key => incoming[key] !== live[key]) ||
    (previous?.epoch === incoming.epoch && previous?.run === incoming.run && previous.snapshotVersion > incoming.snapshotVersion)
  if (!stale) return next
  const safe = { ...next }
  for (const key of ['answer', 'fullAnswer', 'codingAnswer', 'answerRevealActive', 'answerFullAvailable', 'transcript', 'provider', 'category', 'grpcAnswerIdentity', 'questionHistory', 'answerDisplayMode', 'autoProcessing', 'generationStarted', 'answerPipelineState', 'autoModeStatus', 'status', 'error', 'generationDiagnostics']) delete safe[key]
  return safe
}
module.exports = { AnswerStreamState, uint, fenceOverlayAnswer }
