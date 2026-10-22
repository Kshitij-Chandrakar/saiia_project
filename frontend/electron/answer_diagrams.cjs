const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const REVISION = /^v1:[a-f0-9]{64}$/
const STATES = new Set(['unavailable', 'absent', 'processing', 'checkpoint', 'ready', 'failed', 'uncertain', 'cancelled', 'insufficient_detail'])
const CODES = new Set(['schema_unavailable', 'source_pending', 'generation_disabled', 'configuration_missing', 'busy', 'unavailable', 'source_not_found', 'ineligible_source', 'stale_source', 'stale_operation', 'provider_failed', 'timeout', 'invalid_graph', 'refused', 'incomplete', 'cancelled', 'uncertain', 'insufficient_detail'])
const keysOnly = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).every(key => keys.includes(key))
const safeText = (text, max) => typeof text === 'string' && text.length > 0 && [...text].length <= max && !/[<>\x00-\x1f]|https?:|javascript:|data:|www\./i.test(text)

function projectGraph(graph) {
  if (!graph || graph.status !== 'ready' || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges) ||
      graph.nodes.length < 2 || graph.nodes.length > 20 || !graph.edges.length || graph.edges.length > 32) throw Error('invalid_graph')
  const nodes = graph.nodes.map(node => {
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(node.id) || !safeText(node.label, 80) ||
        !['client', 'service', 'database', 'queue', 'cache', 'storage', 'external'].includes(node.kind)) throw Error('invalid_graph')
    return { id: node.id, label: node.label, kind: node.kind }
  })
  const ids = new Set(nodes.map(node => node.id)), pairs = new Set()
  if (ids.size !== nodes.length) throw Error('invalid_graph')
  const edges = graph.edges.map(edge => {
    const pair = `${edge.source}:${edge.target}`
    if (!ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target || pairs.has(pair) || !safeText(edge.label, 80)) throw Error('invalid_graph')
    pairs.add(pair)
    return { source: edge.source, target: edge.target, label: edge.label }
  })
  return { status: 'ready', nodes, edges }
}

function project(action, data) {
  if (action === 'resolve') return {
    transcript_id: UUID.test(data.transcript_id) ? data.transcript_id : null,
    session_id: UUID.test(data.session_id) ? data.session_id : null,
    source_revision: REVISION.test(data.source_revision) ? data.source_revision : null,
    eligible: data.eligible === true && data.answer_type === 'system_design' && ['managed_generation', 'server_generation'].includes(data.provenance),
    generation_enabled: data.generation_enabled === true,
    state: ['pending', 'unavailable'].includes(data.state) ? data.state : 'available',
    reason: CODES.has(data.reason) ? data.reason : null,
  }
  if (data.state === 'ready' && data.graph_schema !== 1) throw Error('invalid_graph')
  return { state: STATES.has(data.state) ? data.state : 'uncertain',
    attempt: [1, 2].includes(data.attempt) ? data.attempt : 0,
    operation_id: UUID.test(data.operation_id) ? data.operation_id : null,
    source_revision: REVISION.test(data.source_revision) ? data.source_revision : null,
    retry_allowed: data.state === 'failed' && data.attempt === 1 && data.retry_allowed === true,
    reason: CODES.has(data.reason) ? data.reason : null,
    failure_code: CODES.has(data.failure_code) ? data.failure_code : null,
    graph: data.state === 'ready' ? projectGraph(data.graph) : null }
}

class AnswerDiagrams {
  constructor(getManager, onInvalidate = () => {}) { this.getManager = getManager; this.onInvalidate = onInvalidate; this.epoch = 0; this.pending = new Map(); this.lookups = new Map(); this.schemaUnavailableGeneration = null }
  async request(action, payload) {
    const baseKeys = ['session_id', 'transcript_id', 'source_revision', 'operation_id']
    if (!['resolve', 'read', 'generate', 'retry', 'cancel', 'history'].includes(action) ||
        !keysOnly(payload, action === 'resolve' ? ['session_id', 'transcript_id', 'request_id'] : action === 'history' ? ['session_id', 'page'] : baseKeys) ||
        !UUID.test(payload.session_id)) throw Error('invalid_diagram_request')
    const base = `/api/interview-sessions/${payload.session_id}`
    let path, method = 'GET', body = null
    if (action === 'resolve') {
      if (Boolean(payload.transcript_id) === Boolean(payload.request_id)) throw Error('invalid_diagram_request')
      if (payload.transcript_id && !UUID.test(payload.transcript_id)) throw Error('invalid_diagram_request')
      if (payload.request_id && (typeof payload.request_id !== 'string' || payload.request_id.length > 120 || !payload.request_id.length)) throw Error('invalid_diagram_request')
      path = `${base}/answer-sources?${new URLSearchParams(payload.transcript_id ? { transcript_id: payload.transcript_id } : { request_id: payload.request_id })}`
    } else if (action === 'history') {
      if (payload.page !== undefined && (!Number.isInteger(payload.page) || payload.page < 1 || payload.page > 10000)) throw Error('invalid_diagram_request')
      path = `${base}/transcript-entries?limit=50&page=${payload.page || 1}`
    } else {
      if (!UUID.test(payload.transcript_id) || !REVISION.test(payload.source_revision)) throw Error('invalid_diagram_request')
      path = `${base}/transcript-entries/${payload.transcript_id}/diagram`
      if (action === 'read') path += `?${new URLSearchParams({ source_revision: payload.source_revision })}`
      else {
        if (!UUID.test(payload.operation_id)) throw Error('invalid_diagram_request')
        if (action !== 'generate') path += `/${action}`
        method = 'POST'; body = { source_revision: payload.source_revision, operation_id: payload.operation_id }
      }
    }
    const manager = this.getManager(), epoch = this.epoch
    const authorization = await manager.getGrpcCloudAuthorization()
    if (epoch !== this.epoch || !authorization.isCurrent()) return { ok: false, error: 'stale_operation' }
    const context = manager.captureCloudRequestContext()
    const authGeneration = `${epoch}:${manager.sessionGeneration}`
    if (action === 'resolve' && this.schemaUnavailableGeneration === authGeneration) return { ok: true, data: {
      session_id: payload.session_id, transcript_id: payload.transcript_id || null,
      eligible: false, generation_enabled: false, state: 'unavailable', reason: 'schema_unavailable' } }
    const key = `${payload.session_id}:${payload.transcript_id}`
    let ownedPending = null
    if (['generate', 'retry'].includes(action)) {
      if (!this.pending.has(key) && this.pending.size >= 16) return { ok: false, error: 'busy' }
      ownedPending = { ...payload }
      this.pending.set(key, ownedPending)
    }
    const lookupKey = `${epoch}:${manager.sessionGeneration}:${path}`
    const perform = async () => {
      let retainPending = false
      const release = () => {
        if (ownedPending && this.pending.get(key) === ownedPending) this.pending.delete(key)
      }
      try {
      const response = await manager._backendJson(path, method, context.session.access_token, body, null, 45000)
      if (epoch !== this.epoch || !manager._cloudRequestStillCurrent(context)) return { ok: false, error: 'stale_operation' }
      if (response.status === 401) { this.cancelAll(); return { ok: false, error: 'unavailable' } }
      if (!response.ok) return { ok: false, error: CODES.has(response.payload?.detail?.code) ? response.payload.detail.code : 'unavailable' }
      if (action === 'history') {
        const entries = response.payload?.items
        if (!Array.isArray(entries)) return { ok: false, error: 'unavailable' }
        const items = entries.slice(0, 50).flatMap(entry => {
          if (!entry || typeof entry !== 'object' || Array.isArray(entry) ||
              typeof entry.id !== 'string' || !UUID.test(entry.id) ||
              typeof entry.question_text !== 'string' || typeof entry.answer_text !== 'string' ||
              !entry.question_text.trim() || !entry.answer_text.trim() ||
              [...entry.question_text].length > 4000 || [...entry.answer_text].length > 24000) return []
          return [{ id: entry.id, session_id: payload.session_id,
            question_text: entry.question_text, answer_text: entry.answer_text }]
        })
        return { ok: true, data: { items, has_more: entries.length >= 50 } }
      }
      try {
        const data = project(action, response.payload)
        if (action === 'resolve' && (data.session_id !== payload.session_id ||
            (payload.transcript_id && data.transcript_id !== payload.transcript_id))) return { ok: false, error: 'stale_source' }
        if (action !== 'resolve' && data.state !== 'absent' && data.source_revision !== payload.source_revision) return { ok: false, error: 'stale_source' }
        if (data.reason === 'schema_unavailable') this.schemaUnavailableGeneration = authGeneration
        const pending = this.pending.get(key)
        const sameOperation = !pending || pending.operation_id === data.operation_id || pending.operation_id === payload.operation_id
        if (sameOperation && ['processing', 'checkpoint'].includes(data.state) && data.operation_id && this.pending.size < 16) {
          this.pending.set(key, { ...payload, operation_id: data.operation_id })
          retainPending = true
        }
        if (!['processing', 'checkpoint'].includes(data.state) && action !== 'resolve') {
          if (sameOperation) this.pending.delete(key)
        }
        return { ok: true, data }
      } catch { return { ok: false, error: 'invalid_graph' } }
      } catch { return { ok: false, error: 'unavailable' } }
      finally { if (!retainPending && ['generate', 'retry'].includes(action)) release() }
    }
    if (action !== 'resolve') return perform()
    let lookup = this.lookups.get(lookupKey)
    if (!lookup) {
      if (this.lookups.size >= 64) this.lookups.delete(this.lookups.keys().next().value)
      lookup = perform(); this.lookups.set(lookupKey, lookup)
    }
    const result = await lookup.catch(() => ({ ok: false, error: 'unavailable' }))
    if ((!result.ok || result.data.state === 'pending') && this.lookups.get(lookupKey) === lookup) this.lookups.delete(lookupKey)
    if (epoch !== this.epoch || !manager._cloudRequestStillCurrent(context)) return { ok: false, error: 'stale_operation' }
    return structuredClone(result)
  }

  cancelAll() {
    this.epoch += 1 // Invalidate delivery before making any cancellation request.
    this.lookups.clear()
    this.schemaUnavailableGeneration = null
    this.onInvalidate()
    const manager = this.getManager(), token = manager?.session?.access_token
    const pending = [...this.pending.values()]; this.pending.clear()
    if (token) for (const item of pending) {
      void manager._backendJson(`/api/interview-sessions/${item.session_id}/transcript-entries/${item.transcript_id}/diagram/cancel`,
        'POST', token, { source_revision: item.source_revision, operation_id: item.operation_id }).catch(() => {})
    }
  }
}

function registerAnswerDiagramIpc(ipcMain, validateMain, bridge) {
  ipcMain.handle('answer-diagram:request', (event, action, payload) => {
    validateMain(event)
    return bridge.request(action, payload)
  })
}
module.exports = { AnswerDiagrams, registerAnswerDiagramIpc, projectGraph }
