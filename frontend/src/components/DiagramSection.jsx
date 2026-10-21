import React, { useEffect, useId, useRef, useState } from 'react'
import { lines } from '../diagram_labels.js'
import { canonicalRevision } from '../diagram_source_revision.js'
import './DiagramSection.css'

const messages = {
  pending: 'Waiting for the saved answer. The answer is unchanged.', unavailable: 'Diagram support is unavailable. The answer is unchanged.',
  absent: 'Generate a diagram from this saved answer.', processing: 'Generating diagram…', checkpoint: 'Saving diagram…',
  failed: 'Diagram generation failed. The answer is unchanged.', uncertain: 'The result could not be confirmed. Automatic regeneration is disabled.',
  cancelled: 'Diagram generation was cancelled.', insufficient_detail: 'This answer does not describe enough connected architecture to diagram.',
}

// Fixed local SVG primitives only; kinds select symbols, never model markup.
function NodeShape({ node }) {
  const { width: w, height: h, kind } = node
  let shape
  if (kind === 'database' || kind === 'storage') {
    shape = <>
      <path d={`M0,10 V${h - 12} C0,${h + 4} ${w},${h + 4} ${w},${h - 12} V10 Z`} />
      <ellipse cx={w / 2} cy="10" rx={w / 2} ry="10" />
      {kind === 'storage' && <path className="diagram-node-detail" d={`M0,${h - 25} C0,${h - 9} ${w},${h - 9} ${w},${h - 25}`} />}
    </>
  } else if (kind === 'client') {
    shape = <>
      <circle cx={w / 2} cy="13" r="12" />
      <path d={`M${w / 2 - 29},51 C${w / 2 - 29},21 ${w / 2 + 29},21 ${w / 2 + 29},51 Z`} />
    </>
  } else if (kind === 'queue') {
    shape = <>
      <rect x="8" width={w - 8} height={h - 8} rx="4" />
      <rect x="4" y="4" width={w - 8} height={h - 8} rx="4" />
      <rect y="8" width={w - 8} height={h - 8} rx="4" />
    </>
  } else if (kind === 'cache') {
    shape = <>
      <path d={`M18,8 H${w - 18} L${w - 10},16 V${h - 16} L${w - 18},${h - 8} H18 L10,${h - 16} V16 Z`} />
      <path className="diagram-node-detail" d={[-20, 0, 20].map(offset =>
        `M${w / 2 + offset},0 v8 M${w / 2 + offset},${h - 8} v8`).join(' ') +
        [-12, 0, 12].map(offset => ` M0,${h / 2 + offset} h10 M${w - 10},${h / 2 + offset} h10`).join('')} />
    </>
  } else if (kind === 'external') {
    shape = <path transform={`scale(${w / 190} ${h / 100})`}
      d="M35,88 C2,88 0,44 28,39 C20,10 65,-2 87,21 C111,1 151,14 151,39 C187,29 201,88 165,88 Z" />
  } else {
    shape = <rect width={w} height={h} rx="8" />
  }
  return <g className="diagram-node-shape" aria-hidden="true" transform={`translate(${node.x - w / 2} ${node.y - h / 2})`}>{shape}</g>
}

function GraphView({ graph, identity }) {
  const [result, setResult] = useState(null)
  const marker = useId().replace(/[^a-zA-Z0-9]/g, '')
  useEffect(() => {
    let active = true
    setResult(null)
    const worker = new Worker(new URL('../diagram_layout.worker.js', import.meta.url), { type: 'module' })
    const stop = () => worker.terminate()
    const timeout = setTimeout(() => { if (active) setResult({ error: true }); stop() }, 2000)
    worker.onmessage = event => {
      if (!active || event.data.identity !== identity) return
      clearTimeout(timeout); stop(); setResult(event.data)
    }
    worker.onerror = () => { if (active) setResult({ error: true }); clearTimeout(timeout); stop() }
    worker.postMessage({ identity, graph })
    return () => { active = false; clearTimeout(timeout); stop() }
  }, [graph, identity])
  const layout = result?.layout
  return <>
    {!result && <p role="status">Arranging diagram…</p>}
    {result?.error && <p role="status">Visual layout unavailable. The component and relationship list is below.</p>}
    {layout && <div className="diagram-scroll" tabIndex={0} aria-label="Architecture diagram, scroll to view">
      <svg width={layout.width} height={layout.height} role="img" aria-labelledby={`${marker}title ${marker}desc`}>
        <title id={`${marker}title`}>Architecture from the completed answer</title>
        <desc id={`${marker}desc`}>Components connected by labeled arrows. A text alternative follows.</desc>
        <defs><marker id={marker} markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="currentColor" /></marker></defs>
        {layout.edges.map((edge, index) => <g key={index} className="diagram-edge">
          <path d={edge.points.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ')} fill="none" stroke="currentColor" markerEnd={`url(#${marker})`} />
          <text x={edge.x} y={edge.y} textAnchor="middle">{lines(edge.label).map((line, i) => <tspan key={i} x={edge.x} dy={i ? 18 : 0}>{line}</tspan>)}</text>
        </g>)}
        {layout.nodes.map(node => <g key={node.id} className="diagram-node" data-kind={node.kind}>
          <NodeShape node={node} />
          <text x={node.x} y={node.y - (lines(node.label).length - 1) * 9 + 5 +
            (node.kind === 'client' ? 25 : node.kind === 'external' ? 8 : node.kind === 'queue' ? 4 : 0)} textAnchor="middle">{lines(node.label).map((line, i) => <tspan key={i} x={node.x} dy={i ? 18 : 0}>{line}</tspan>)}</text>
        </g>)}
      </svg>
    </div>}
    {layout && <div className="diagram-legend" aria-label="Component colors">
      <span data-kind="client">Clients &amp; external</span>
      <span data-kind="service">Services</span>
      <span data-kind="database">Data stores</span>
      <span data-kind="queue">Queues &amp; caches</span>
    </div>}
    <details><summary>Components and relationships (text alternative)</summary>
      <ul>{graph.nodes.map(node => <li key={node.id}>{node.label} ({node.kind})</li>)}</ul>
      <ul>{graph.edges.map((edge, index) => <li key={index}>{graph.nodes.find(n => n.id === edge.source)?.label} → {graph.nodes.find(n => n.id === edge.target)?.label}: {edge.label}</li>)}</ul>
    </details>
  </>
}

export default function DiagramSection({ source, api = window.electronAPI }) {
  const identity = source ? `${source.session_id}:${source.transcript_id || source.request_id}` : ''
  return <DiagramContent key={`${identity}:${source?.ui_revision || ''}`} source={source} api={api} />
}

function DiagramContent({ source, api }) {
  const [view, setView] = useState({ state: 'loading' })
  const generation = useRef(0), timer = useRef(null), busy = useRef(false)
  const identity = source ? `${source.session_id}:${source.transcript_id || source.request_id}` : ''
  const current = useRef(identity); current.current = identity
  const descriptor = useRef(null)
  const clearTimer = () => { clearTimeout(timer.current); timer.current = null }
  const apply = async (result, version, key, count = 0) => {
    if (generation.current !== version || current.current !== key) return
    busy.current = false
    if (!result?.ok) { setView({ state: 'unavailable', error: result?.error || 'unavailable' }); return }
    setView(result.data)
    if (['processing', 'checkpoint'].includes(result.data.state) && count < 100) {
      clearTimer()
      timer.current = setTimeout(async () => {
        if (generation.current !== version || current.current !== key) return
        try {
          const payload = { ...descriptor.current }; delete payload.generationEnabled
          await apply(await api.answerDiagram('read', payload), version, key, count + 1)
        }
        catch { await apply({ ok: false }, version, key) }
      }, 1000)
    }
  }
  useEffect(() => {
    const version = ++generation.current, key = identity
    clearTimer(); busy.current = false; descriptor.current = null; setView({ state: 'loading' })
    const invalidate = () => { ++generation.current; clearTimer(); descriptor.current = null; busy.current = false; setView({ state: 'unavailable' }) }
    const unsubscribe = api?.onAnswerDiagramInvalidated?.(invalidate)
    if (!source || !api?.answerDiagram) { setView({ state: 'ineligible' }); return unsubscribe }
    void (async () => {
      try {
        // Managed storage retains exact completed text; unmanaged saves normalize
        // transport line endings/outer whitespace. Accept only those two forms.
        const expectedRevisions = await Promise.all([true, false].map(normalize =>
          canonicalRevision(source.canonical_question, source.canonical_answer, normalize)))
        const lookup = { session_id: source.session_id, ...(source.transcript_id ? { transcript_id: source.transcript_id } : { request_id: source.request_id }) }
        const result = await api.answerDiagram('resolve', lookup)
        if (generation.current !== version || current.current !== key) return
        if (!result?.ok) { setView({ state: 'unavailable', error: result?.error }); return }
        if (['pending', 'unavailable'].includes(result.data.state)) { setView(result.data); return }
        if (!result.data.eligible || !expectedRevisions.includes(result.data.source_revision)) { setView({ state: 'ineligible' }); return }
        descriptor.current = { session_id: result.data.session_id, transcript_id: result.data.transcript_id, source_revision: result.data.source_revision }
        descriptor.current.generationEnabled = result.data.generation_enabled
        const readPayload = { ...descriptor.current }; delete readPayload.generationEnabled
        await apply(await api.answerDiagram('read', readPayload), version, key)
      } catch { if (generation.current === version) setView({ state: 'unavailable' }) }
    })()
    return () => { ++generation.current; clearTimer(); unsubscribe?.() }
  }, [identity, api])
  const submit = async action => {
    if (busy.current || !descriptor.current) return
    busy.current = true; clearTimer()
    const version = ++generation.current, key = identity
    const payload = { ...descriptor.current, operation_id: crypto.randomUUID() }; delete payload.generationEnabled
    setView({ state: 'processing' })
    try { await apply(await api.answerDiagram(action, payload), version, key) }
    catch { await apply({ ok: false }, version, key) }
  }
  const enabled = descriptor.current?.generationEnabled
  return <section className="answer-diagram" aria-label="Answer architecture diagram">
    <h3>Architecture diagram</h3>
    {view.state !== 'ready' && <p role="status">{view.state === 'ineligible' ? 'Available for verified saved system-design interview answers.' :
      view.state === 'loading' ? 'Checking saved answer…' : view.state === 'unavailable' ? 'Diagram unavailable. The answer is unchanged.' : messages[view.state]}</p>}
    {view.state === 'absent' && enabled && <button type="button" onClick={() => submit('generate')}>Generate diagram</button>}
    {view.state === 'absent' && !enabled && <p>Diagram generation is disabled.</p>}
    {view.state === 'failed' && view.retry_allowed && enabled && <button type="button" onClick={() => submit('retry')}>Retry diagram</button>}
    {view.state === 'ready' && view.graph && <GraphView key={identity} identity={`${identity}:${descriptor.current?.source_revision}`} graph={view.graph} />}
  </section>
}
