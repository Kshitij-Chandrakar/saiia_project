import { useEffect, useRef } from 'react'
import { Eraser } from 'lucide-react'

export default function SessionConfirmation({ title, message, keep, confirm, onCancel, onConfirm, pending = false, error = '' }) {
  const dialog = useRef(null), cancel = useRef(null)
  useEffect(() => {
    const node = dialog.current, trigger = document.activeElement
    node.showModal(); cancel.current.focus({preventScroll:true})
    return () => { node.close(); if (trigger?.isConnected) trigger.focus({preventScroll:true}) }
  }, [])
  // The main viewer owns the scroll lock; this top-layer dialog only owns focus.
  return <dialog ref={dialog} className="website-dashboard ws-confirm" aria-modal="true" aria-busy={pending} aria-labelledby="ws-confirm-title" aria-describedby="ws-confirm-description" onCancel={event=>{event.preventDefault();event.stopPropagation();if (!pending) onCancel()}}>
    <span className="ws-confirm__icon"><Eraser size={28} aria-hidden="true" /></span>
    <h2 id="ws-confirm-title">{title}</h2><p id="ws-confirm-description">{message}</p>
    {error && <p role="alert">{error}</p>}
    {pending && <p role="status">Deleting transcript…</p>}
    <div><button ref={cancel} disabled={pending} type="button" onClick={onCancel}>{keep}</button><button disabled={pending} type="button" className="wd-primary" onClick={onConfirm}>{pending ? 'Deleting…' : confirm}</button></div>
  </dialog>
}
