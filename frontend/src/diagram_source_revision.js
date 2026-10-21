// Mirrors PostgreSQL answer_source_revision v1 (jsonb string-array text).
// This is a display-association check, never an authorization decision.
export async function canonicalRevision(question, answer, normalizeTransport = true) {
  const normalize = text => normalizeTransport ? String(text || '').replace(/\r\n?/g, '\n').trim() : String(text || '')
  const q = normalize(question), a = normalize(answer)
  if (!q || !a || q.length > 8000 || a.length > 48000) throw Error('unverified_source')
  const bytes = new TextEncoder().encode(`[${JSON.stringify(q)}, ${JSON.stringify(a)}]`)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return 'v1:' + Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('')
}

// UI completion alone is not proof of durable storage. Backend resolution still
// verifies ownership, canonical revision and trusted provenance independently.
export function completedDiagramSource(entry, answer, mode, revealing) {
  if (mode === 'screen' || revealing || entry?.status !== 'complete' ||
      entry.metadata?.answerSaved !== true || entry.fullAnswer !== answer ||
      !entry.metadata?.savedSessionId || !entry.metadata?.savedRequestId) return null
  return {session_id:entry.metadata.savedSessionId,request_id:entry.metadata.savedRequestId,
    canonical_question:entry.originalQuestion || entry.question,canonical_answer:entry.fullAnswer,
    ui_revision:entry.completedAt || entry.id}
}
