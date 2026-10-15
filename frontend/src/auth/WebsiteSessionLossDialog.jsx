import { useEffect, useRef } from 'react'
import historyIcon from '../assets/session-notice/session-history.svg'
import './website-session-loss.css'

const reasons = {
  expired: { label:'SESSION EXPIRED', title:'Session expired', message:'Your session has expired. Please sign in again to continue.' },
  signed_out: { label:'SIGNED OUT', title:'You’ve been signed out', message:'Please sign in again to continue.' },
}

export default function WebsiteSessionLossDialog({ reason, onDismiss, emailRef }) {
  const dialog = useRef(null), action = useRef(null)
  const content = reasons[reason]
  useEffect(() => {
    const element = dialog.current, body = document.body
    const overflow = body.style.overflow, padding = body.style.paddingRight
    const gutter = innerWidth - document.documentElement.clientWidth
    body.style.overflow = 'hidden'
    if (gutter) body.style.paddingRight = `${gutter}px`
    element.showModal(); action.current.focus()
    return () => { element.close(); body.style.overflow = overflow; body.style.paddingRight = padding }
  }, [])
  function dismiss() {
    dialog.current.close()
    onDismiss()
    queueMicrotask(() => emailRef.current?.focus({ preventScroll:true }))
  }
  return <dialog ref={dialog} className="website-session-loss" aria-modal="true" aria-labelledby="website-session-loss-title" aria-describedby="website-session-loss-description"
    onCancel={event => { event.preventDefault(); dismiss() }} onKeyDown={event => { if (event.key === 'Tab') { event.preventDefault(); action.current.focus() } }}>
    <p className="website-session-loss__label" aria-hidden="true">{content.label}</p>
    <div className="website-session-loss__icon-slot"><span><img src={historyIcon} alt="" /></span></div>
    <div className="website-session-loss__copy"><h2 id="website-session-loss-title">{content.title}</h2><p id="website-session-loss-description">{content.message}</p></div>
    <button ref={action} type="button" onClick={dismiss}>Sign in again</button>
  </dialog>
}
