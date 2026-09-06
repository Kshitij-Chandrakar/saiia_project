import React, { useEffect, useRef, useState } from 'react'
import loginArrowUrl from '../assets/startup-login/login-arrow.svg'
import loginCloseUrl from '../assets/startup-login/login-close.svg'
import loginLogoUrl from '../assets/startup-login/login-logo.svg'
import loginMascotUrl from '../assets/startup-login/login-mascot.png'
import loginOpenBrowserUrl from '../assets/startup-login/login-open-browser.svg'
import loginSecurityUrl from '../assets/startup-login/login-security.svg'
import loginBackgroundEllipseLeftUrl from '../assets/startup-login/login-bg-ellipse-left.svg'
import loginBackgroundEllipseRightUrl from '../assets/startup-login/login-bg-ellipse-right.svg'
import loginBackgroundGroupLeftUrl from '../assets/startup-login/login-bg-group-left.svg'
import loginBackgroundGroupRightUrl from '../assets/startup-login/login-bg-group-right.svg'
import {
  DESKTOP_AUTH_ERROR_CODES,
  DESKTOP_AUTH_STATUSES,
  getDesktopAuthViewModel,
  getDesktopStartupErrorView,
} from '../desktop_auth_ui.js'

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
          applyAuthState({
            status: DESKTOP_AUTH_STATUSES.SIGNED_OUT,
            error: 'Sign-in service unavailable.',
            error_code: DESKTOP_AUTH_ERROR_CODES.SERVICE_UNAVAILABLE,
          }, requestId)
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
        error: 'Sign-in service unavailable.',
        error_code: DESKTOP_AUTH_ERROR_CODES.SERVICE_UNAVAILABLE,
      }, requestId)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoginPending(false)
      }
    }
  }

  const errorView = getDesktopStartupErrorView(authState)
  const buttonText = loginPending || authState.status === DESKTOP_AUTH_STATUSES.SIGNING_IN
    ? 'Opening login...'
    : errorView.actionLabel
  const errorText = errorView.message
  const isOpeningBrowser = loginPending || authState.status === DESKTOP_AUTH_STATUSES.SIGNING_IN
  const subtitle = 'Sign in to continue to your Intervu AI workspace.'

  return (
    <div className="startup-login-window" aria-label="Intervu AI startup login">
      <section className="startup-login-card">
        <div className="startup-login-decorations" aria-hidden="true">
          <div className="startup-login-decoration startup-login-decoration--ellipse-left">
            <div>
              <div>
                <img src={loginBackgroundEllipseLeftUrl} alt="" />
              </div>
            </div>
          </div>
          <div className="startup-login-decoration startup-login-decoration--ellipse-right">
            <div>
              <div>
                <img src={loginBackgroundEllipseRightUrl} alt="" />
              </div>
            </div>
          </div>
          <img className="startup-login-decoration startup-login-decoration--group-left" src={loginBackgroundGroupLeftUrl} alt="" />
          <img className="startup-login-decoration startup-login-decoration--group-right" src={loginBackgroundGroupRightUrl} alt="" />
        </div>
        <header className="startup-login-header">
          <div className="startup-login-brand">
            <span className="startup-login-brand__logo" aria-hidden="true">
              <img src={loginLogoUrl} alt="" />
            </span>
            <h1>Intervu AI</h1>
          </div>
          <button
            className="startup-login-close"
            type="button"
            aria-label="Close startup login"
            onClick={closeStartupWindow}
          >
            <img src={loginCloseUrl} alt="" />
          </button>
        </header>

        <main className={`startup-login-main${errorText ? ' startup-login-main--error' : ''}${isOpeningBrowser ? ' startup-login-main--opening' : ''}`}>
          {isOpeningBrowser ? (
            <div className="startup-login-opening-content">
              <div className="startup-login-opening-mascot">
                <img className="startup-login-opening-mascot__image" src={loginMascotUrl} alt="Intervu AI mascot" />
              </div>
              <div className="startup-login-opening-status-block">
                <div className="startup-login-opening-copy">
                  <h2>Opening Your Browser</h2>
                  <p>We’re securely connecting you to Intervu AI Sign In.</p>
                </div>
                <div className="startup-login-opening-loading" aria-hidden="true">
                  <div className="startup-login-opening-dots">
                    <span className="startup-login-opening-dot" />
                    <span className="startup-login-opening-dot" />
                    <span className="startup-login-opening-dot" />
                  </div>
                </div>
              </div>
              <div className="startup-login-opening-hint">
                <span className="startup-login-opening-hint__icon" aria-hidden="true">
                  <img src={loginOpenBrowserUrl} alt="" />
                </span>
                <p>Your browser will open automatically.</p>
              </div>
              <p className="startup-login-opening-announcement" role="status" aria-live="polite">
                Opening Your Browser. We’re securely connecting you to Intervu AI Sign In.
              </p>
            </div>
          ) : (
            <>
              <div className="startup-login-hero">
                <div className="startup-login-mascot-stack">
                  <span className="startup-login-mascot-frame">
                    <img className="startup-login-mascot" src={loginMascotUrl} alt="Intervu AI mascot" />
                  </span>
                </div>
                <div className="startup-login-copy">
                  <h2>Welcome to Intervu AI</h2>
                  <p aria-live="polite">{subtitle}</p>
                </div>
              </div>

              <div className="startup-login-action-area">
                {errorText ? (
                  <p className="startup-login-error" role="alert">
                    {errorText}
                  </p>
                ) : null}

                <button
                  className="startup-login-button"
                  type="button"
                  disabled={loginPending || authState.loginDisabled}
                  onClick={handleLogin}
                >
                  <span>{buttonText}</span>
                  {buttonText === 'Login with Intervu AI \u2192' ? <img src={loginArrowUrl} alt="" aria-hidden="true" /> : null}
                </button>
              </div>

              <div className="startup-login-info" aria-label="Authentication information">
                <span className="startup-login-info__icon" aria-hidden="true">
                  <img src={loginSecurityUrl} alt="" />
                </span>
                <p>
                  Authentication is securely completed in your browser. You'll return here automatically.
                </p>
              </div>

              <p className="startup-login-help">
                <span>Need Help?</span>
                <a href="#" onClick={(event) => event.preventDefault()}>Contact Support</a>
              </p>
            </>
          )}
        </main>
      </section>
    </div>
  )
}
