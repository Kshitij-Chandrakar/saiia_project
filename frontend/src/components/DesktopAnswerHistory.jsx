import React, { useEffect, useRef, useState } from 'react'
import DiagramSection from './DiagramSection.jsx'
import AnswerText from './AnswerText.jsx'

// Desktop-only authenticated history. Canonical text comes from owned storage,
// and eligibility is resolved independently; local history never grants trust.
export default function DesktopAnswerHistory({ sessionId, api = window.electronAPI }) {
  const [page, setPage] = useState(1), [result, setResult] = useState(null), [selected, setSelected] = useState('')
  const generation = useRef(0)
  useEffect(() => {
    const version = ++generation.current
    setResult(null); setSelected('')
    const unsubscribe = api?.onAnswerDiagramInvalidated?.(() => { ++generation.current; setResult({ ok: false }) })
    void api?.answerDiagram('history', { session_id: sessionId, page }).then(value => {
      if (generation.current === version) setResult(value)
    }).catch(() => { if (generation.current === version) setResult({ ok: false }) })
    return () => { ++generation.current; unsubscribe?.() }
  }, [sessionId, page, api])
  const entry = result?.data?.items?.find(item => item.id === selected)
  return <section aria-label="Saved interview answers" style={{ minWidth: 0, maxHeight: '60vh', overflow: 'auto', padding: 12 }}>
    {!result ? <p role="status">Loading saved answers…</p> : !result.ok ? <p role="status">Saved answers unavailable.</p> : <>
      <label>Saved answer <select value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">Select an answer</option>
        {result.data.items.map(item => <option key={item.id} value={item.id}>{item.question_text.slice(0, 100)}</option>)}
      </select></label>
      <button type="button" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous answers</button>
      <button type="button" disabled={result.data.has_more === undefined ? result.data.items.length < 50 : !result.data.has_more} onClick={() => setPage(value => value + 1)}>More answers</button>
      {entry && <article key={entry.id}><p>{entry.question_text}</p><AnswerText text={entry.answer_text} />
        <DiagramSection source={{ session_id: sessionId, transcript_id: entry.id,
          canonical_question: entry.question_text, canonical_answer: entry.answer_text }} api={api} />
      </article>}
    </>}
  </section>
}
