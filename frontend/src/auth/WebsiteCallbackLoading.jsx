import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import WebsiteLogin from './WebsiteLogin'
import spinner from '../assets/website-callback/spinner.svg'
import './website-callback-loading.css'

const noop = () => {}
const backgroundForm = { email: '', password: '', loading: false, error: '', message: '', setEmail: noop, setPassword: noop, setError: noop }

export default function WebsiteCallbackLoading({ error, nextRoute, canRetry, onRetry }) {
  const dialog = useRef(null)
  const recovery = useRef(null)
  useEffect(() => {
    if (error) { recovery.current?.focus(); return }
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
  }, [error])

  return <div className={`website-callback${error ? '' : ' website-callback--pending'}`}>
    <div inert="" aria-hidden="true"><WebsiteLogin form={backgroundForm} configured blocked presentationOnly onSubmit={noop} onGoogleLogin={noop} /></div>
    {error ? <div className="website-callback__recovery">
      <section className="website-callback__card website-callback__error" aria-labelledby="callback-error-title" aria-describedby="callback-error-message">
        <span className="website-callback__label">SIGN-IN UNAVAILABLE</span>
        <h1 id="callback-error-title">Unable to finish sign-in</h1>
        <p id="callback-error-message" role="alert">{error}</p>
        {canRetry && <button type="button" onClick={onRetry}>Retry saving signup preferences</button>}
        <Link ref={recovery} to={`/auth/login?next=${encodeURIComponent(nextRoute)}`}>Back to sign in</Link>
      </section>
    </div> : <dialog ref={dialog} className="website-callback__card" tabIndex={-1} aria-labelledby="callback-loading-title" aria-describedby="callback-loading-description" aria-busy="true" onCancel={event => event.preventDefault()} onKeyDown={event => { if (event.key === 'Tab') { event.preventDefault(); dialog.current.focus() } }}>
      <span className="website-callback__label">LOADING STATE</span>
      <img className="website-callback__spinner" src={spinner} alt="" aria-hidden="true" />
      <h1 id="callback-loading-title" role="status">Signing you in…</h1>
      <p id="callback-loading-description">Please wait</p>
    </dialog>}
  </div>
}
