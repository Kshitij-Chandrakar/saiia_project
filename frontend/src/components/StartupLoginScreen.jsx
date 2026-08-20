import React, { useEffect, useRef, useState } from 'react'
import mascotUrl from '../assets/intervu-mascot.svg'
import { DESKTOP_AUTH_STATUSES, getDesktopAuthViewModel } from '../desktop_auth_ui.js'

const LOGIN_VISIBLE_STATUSES = new Set([
  DESKTOP_AUTH_STATUSES.SIGNED_OUT,
  DESKTOP_AUTH_STATUSES.SIGNING_IN,
  DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED,
])

export function shouldShowStartupLogin(authState) {
  return LOGIN_VISIBLE_STATUSES.has(getDesktopAuthViewModel(authState).status)
}

export default function StartupLoginScreen({ onAuthenticated }) {
  const [authState, setAuthState] = useState(() => getDesktopAuthViewModel())
  const [loginPending, setLoginPending] = useState(false)
  const requestIdRef = useRef(0)
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null
  const electronApi = typeof window !== 'undefined' ? window.electronAPI : null

  const closeStartupWindow = () => {
    const closeWindow = saiiaApi?.closeStartupWindow || electronApi?.closeStartupWindow
    closeWindow?.().catch?.(() => {})
  }

  const applyAuthState = (payload, requestId) => {
    if (requestId !== requestIdRef.current) {
      return
    }
    const nextState = getDesktopAuthViewModel(payload)
    setAuthState(nextState)
    if (!shouldShowStartupLogin(nextState)) {
      onAuthenticated?.(nextState)
    }
  }

  useEffect(() => {
    let active = true
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    const loadStartupContext = saiiaApi?.getCloudStartupContext || saiiaApi?.getAuthState
    loadStartupContext?.()
      .then((state) => {
        if (active) {
          applyAuthState(state, requestId)
        }
      })
      .catch(() => {
        if (active) {
          applyAuthState({ status: DESKTOP_AUTH_STATUSES.SIGNED_OUT }, requestId)
        }
      })
    return () => {
      active = false
    }
  }, [saiiaApi])

  useEffect(() => {
    if (authState.status !== DESKTOP_AUTH_STATUSES.SIGNING_IN) {
      return undefined
    }
    const pollId = window.setInterval(() => {
      const requestId = requestIdRef.current + 1
      requestIdRef.current = requestId
      const loadStartupContext = saiiaApi?.getCloudStartupContext || saiiaApi?.getAuthState
      loadStartupContext?.()
        .then((state) => applyAuthState(state, requestId))
        .catch(() => {})
    }, 1000)
    return () => window.clearInterval(pollId)
  }, [authState.status, saiiaApi])

  const handleLogin = async () => {
    if (loginPending || typeof saiiaApi?.startAuthLogin !== 'function') {
      return
    }
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setLoginPending(true)
    setAuthState(getDesktopAuthViewModel({ status: DESKTOP_AUTH_STATUSES.SIGNING_IN }))
    try {
      applyAuthState(await saiiaApi.startAuthLogin(), requestId)
    } catch {
      applyAuthState({
        status: DESKTOP_AUTH_STATUSES.SIGNED_OUT,
        error: 'Login could not be opened. Try again.',
      }, requestId)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoginPending(false)
      }
    }
  }

  const buttonText = loginPending || authState.status === DESKTOP_AUTH_STATUSES.SIGNING_IN
    ? 'Opening login...'
    : 'Login with Intervu AI \u2192'

  const errorDetail = authState.error || ''
  const errorText = getStartupErrorMessage(errorDetail)
  const subtitle = 'Sign in to continue to your Intervu AI workspace.'

  return (
    <div className="startup-login-window" aria-label="Intervu AI startup login">
      <section className="startup-login-card">
        <header className="startup-login-header">
          <div className="startup-login-brand">
            <span className="startup-login-brand__mascot-frame" aria-hidden="true">
              <img className="startup-login-brand__mascot" src={mascotUrl} alt="" />
            </span>
            <h1>Intervu AI</h1>
          </div>
          <button
            className="startup-login-close"
            type="button"
            aria-label="Close startup login"
            onClick={closeStartupWindow}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 3L13 13M13 3L3 13" />
            </svg>
          </button>
        </header>

        <main className={`startup-login-main${errorText ? ' startup-login-main--error' : ''}`}>
          <div className="startup-login-hero">
            <div className="startup-login-mascot-stack">
              <span className="startup-login-mascot-frame">
                <img className="startup-login-mascot" src={mascotUrl} alt="Intervu AI mascot" />
              </span>
              <span className="startup-login-mascot-shadow" aria-hidden="true" />
            </div>
            <div className="startup-login-copy">
              <h2>Intervu AI</h2>
              <p aria-live="polite">{subtitle}</p>
            </div>
          </div>

          {errorText ? (
            <p className="startup-login-error" aria-live="polite" title={errorDetail}>
              {errorText}
            </p>
          ) : null}

          <button
            className="startup-login-button"
            type="button"
            disabled={loginPending || authState.loginDisabled}
            onClick={handleLogin}
          >
            {buttonText}
          </button>

          <div className="startup-login-info" aria-label="Authentication information">
            <span className="startup-login-info__icon" aria-hidden="true">
              <LockScreenIcon />
            </span>
            <p>
              Authentication is securely completed in your browser. You'll return here automatically.
            </p>
          </div>

          <p className="startup-login-help">
            <span>Need Help?</span>
            <a href="#" onClick={(event) => event.preventDefault()}>Contact Support</a>
          </p>
        </main>
      </section>
    </div>
  )
}

function getStartupErrorMessage(error) {
  if (!error) {
    return ''
  }
  if (/Desktop cloud auth is not configured/i.test(error)) {
    return 'Desktop auth is not configured.'
  }
  return 'Login could not be opened. Try again.'
}

function LockScreenIcon() {
  return (
    <svg className="startup-login-feature-icon startup-login-feature-icon--large" viewBox="0 0 25 25" aria-hidden="true">
      <path d="M8 11.5V8.8a4.5 4.5 0 0 1 9 0v2.7" />
      <rect x="5.5" y="11" width="14" height="10" rx="2" />
      <circle cx="12.5" cy="16" r="1" />
      <path d="M12.5 17v2" />
      <circle cx="19.2" cy="5.2" r="2.4" />
    </svg>
  )
}
