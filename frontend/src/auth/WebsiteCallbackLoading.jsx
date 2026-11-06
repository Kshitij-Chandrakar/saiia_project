import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import WebsiteLogin from './WebsiteLogin'
import { ProgressIndicator } from './WebsiteProgress'
import './website-callback-loading.css'

const noop = () => {}
const backgroundForm = { email: '', password: '', loading: false, error: '', message: '', setEmail: noop, setPassword: noop, setError: noop }

export default function WebsiteCallbackLoading({ error, nextRoute, canRetry, onRetry, stalled = false, stage = 'session' }) {
  const dialog = useRef(null)
  const recovery = useRef(null)
  useEffect(() => {
    const node = dialog.current
    const body = document.body, root = document.documentElement
    const previous = body.style.overflow, rootOverflow = root.style.overflow, padding = body.style.paddingRight
    const x = window.scrollX, y = window.scrollY, gutter = window.innerWidth - root.clientWidth
    node.showModal()
    node.focus({ preventScroll: true })
    body.style.overflow = 'hidden'
    root.style.overflow = 'hidden'
    if (gutter) body.style.paddingRight = `${gutter}px`
    return () => {
      node.close()
      body.style.overflow = previous; root.style.overflow = rootOverflow; body.style.paddingRight = padding
      window.scrollTo({ left: x, top: y, behavior: 'instant' })
    }
  }, [])

  return <div className="website-callback website-callback--pending">
    <div inert aria-hidden="true"><WebsiteLogin form={backgroundForm} configured blocked presentationOnly onSubmit={noop} onGoogleLogin={noop} /></div>
    <dialog ref={dialog} className="website-callback__card" tabIndex={-1} aria-labelledby="callback-loading-title" aria-describedby="callback-loading-description" onCancel={event => { event.preventDefault(); recovery.current?.click() }}>
      <span className="website-callback__label">Intervucopilot</span>
      {!error && <ProgressIndicator />}
      <h1 id="callback-loading-title">{error ? 'Unable to finish sign-in' : stalled ? 'Sign-in is taking longer' : 'Signing you in'}</h1>
      <p id="callback-loading-description" role={error ? 'alert' : 'status'} aria-live="polite" aria-atomic="true">{error || (stalled ? 'The result is not confirmed yet. You can keep waiting or return to sign in.' : stage === 'preferences' ? 'Saving your signup preferences.' : stage === 'account' ? 'Checking your account before opening your workspace.' : 'Waiting for secure sign-in to finish.')}</p>
      {error && canRetry && <button type="button" onClick={onRetry}>Retry saving signup preferences</button>}
      <Link ref={recovery} to={`/auth/login?next=${encodeURIComponent(nextRoute)}`}>Back to sign in</Link>
    </dialog>
  </div>
}
