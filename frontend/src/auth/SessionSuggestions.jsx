import { useRef, useState } from 'react'
import SessionConfirmation from './SessionConfirmation'

const sessionSuggestions = [
  ['Follow-up Email', 'Draft a professional follow-up email for this interview using the selected session’s role, company, and supported discussion highlights.'],
  ['Grade the call', 'Review this interview session based on the available transcript. Explain strengths, areas for improvement, and any limits in the available evidence.'],
  ['How was the vibe?', 'Describe the tone of this interview based on the available text. Explain what supports your assessment and what cannot be determined from the transcript.'],
]

export default function SessionSuggestions({ draft, onChange, disabled, inputRef }) {
  const [replacement, setReplacement] = useState(null)
  function fill(text) { onChange(text); queueMicrotask(()=>inputRef.current?.focus({preventScroll:true})) }
  return <><div className="wa-suggestions">{sessionSuggestions.map(([label,text])=><button key={label} type="button" disabled={disabled} onClick={()=>{if(draft.trim())setReplacement(text);else fill(text)}}>{label}</button>)}</div>
    {replacement && <SessionConfirmation title="Replace your draft?" message="You have an unsent question. Replace it with this suggestion?" keep="Keep Draft" confirm="Replace Draft" onCancel={()=>setReplacement(null)} onConfirm={()=>{const text=replacement;setReplacement(null);fill(text)}} />}
  </>
}

export function SessionEmailDraft({ text, value, onChange }) {
  const input = useRef(null)
  const [status, setStatus] = useState('')
  return <section className="wa-email"><label>Follow-up email draft<textarea ref={input} value={value ?? text} onChange={event=>onChange(event.target.value)} spellCheck autoComplete="off" /></label>
    <div><span>Editable draft · Review before using</span><button type="button" onClick={async()=>{try{await navigator.clipboard.writeText(value ?? text);setStatus('Email draft copied.')}catch{input.current?.focus();input.current?.select();setStatus('Copy is unavailable. Select and copy the draft manually.')}}}>Copy Email</button></div><p role="status">{status}</p>
  </section>
}
