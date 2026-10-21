import React, { useEffect, useRef, useState } from 'react'
import StartupAccountMenu from './StartupAccountMenu'
import DesktopAnswerHistory from './DesktopAnswerHistory.jsx'
import loginMascotUrl from '../assets/startup-login/login-mascot.png'
import choiceArrowUrl from '../assets/startup-choice/choice-arrow.svg'
import choiceBrandUrl from '../assets/startup-choice/choice-brand.svg'
import choiceCardArrowUrl from '../assets/startup-choice/choice-card-arrow.svg'
import choiceClockUrl from '../assets/startup-choice/choice-clock.svg'
import choiceCloseUrl from '../assets/startup-choice/choice-close.svg'
import choiceCollapseUrl from '../assets/startup-choice/choice-collapse.svg'
import choiceFreeStarsUrl from '../assets/startup-choice/choice-free-stars.svg'
import choiceHistoryUrl from '../assets/startup-choice/choice-history.svg'
import choicePastHistoryUrl from '../assets/startup-choice/choice-past-history.svg'
import choicePastStarsUrl from '../assets/startup-choice/choice-past-stars.svg'
import choicePastViewAllArrowUrl from '../assets/startup-choice/choice-past-view-all-arrow.svg'
import choiceShieldUrl from '../assets/startup-choice/choice-shield.svg'
import choiceStarsUrl from '../assets/startup-choice/choice-stars.svg'
import choiceWalletUrl from '../assets/startup-choice/choice-wallet.svg'

const PAST_SESSION_STATUSES = new Set(['ended', 'abandoned'])

function getCompanyInitial(companyName) {
  const initial = String(companyName || '').trim().charAt(0)
  return initial ? initial.toUpperCase() : '?'
}

function formatPastSessionDate(value) {
  if (!value) {
    return 'Date not available'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Date not available'
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function StartupSessionChoiceScreen({
  onCreateSession,
  onShowCreate,
  onShowPastSessions,
  onSessionExpired,
  onSignedOut,
  onClose,
  authenticatedEmail = '',
  remainingMinutes = null,
  totalMinutes = null,
}) {
  const [activeTab, setActiveTab] = useState('create')
  const [answerHistorySession, setAnswerHistorySession] = useState('')
  const [message, setMessage] = useState('')
  const [pastSessions, setPastSessions] = useState([])
  const [pastSessionsLoading, setPastSessionsLoading] = useState(false)
  const [pastSessionsError, setPastSessionsError] = useState('')
  const [isMascotCollapsed, setIsMascotCollapsed] = useState(false)
  const [presentationBusy, setPresentationBusy] = useState(false)
  const historyRequestIdRef = useRef(0)
  const historyLoadingRef = useRef(false)
  const mountedRef = useRef(true)
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null
  const electronApi = typeof window !== 'undefined' ? window.electronAPI : null
  const normalizedRemainingMinutes = Number(remainingMinutes)
  const normalizedTotalMinutes = Number(totalMinutes)
  const hasTimeBalance =
    remainingMinutes !== null &&
    remainingMinutes !== undefined &&
    totalMinutes !== null &&
    totalMinutes !== undefined &&
    Number.isFinite(normalizedRemainingMinutes) &&
    Number.isFinite(normalizedTotalMinutes)
  const timeAriaLabel = hasTimeBalance
    ? `${normalizedRemainingMinutes} of ${normalizedTotalMinutes} minutes remaining`
    : 'Time availability unavailable'
  const freeSessionLabel = hasTimeBalance
    ? `${normalizedRemainingMinutes} minutes available`
    : 'Time availability unavailable'
  const safeAuthenticatedEmail = typeof authenticatedEmail === 'string' ? authenticatedEmail.trim() : ''

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      historyRequestIdRef.current += 1
    }
  }, [])

  useEffect(() => {
    if (typeof document === 'undefined') {
      return undefined
    }
    if (isMascotCollapsed) {
      document.documentElement.dataset.startupMascot = 'true'
    } else {
      delete document.documentElement.dataset.startupMascot
    }
    return () => {
      delete document.documentElement.dataset.startupMascot
    }
  }, [isMascotCollapsed])

  const closeStartupWindow = () => {
    const closeWindow = onClose || saiiaApi?.closeStartupWindow || electronApi?.closeStartupWindow
    const closeResult = closeWindow?.()
    closeResult?.catch?.(() => {})
  }

  const handleCollapse = async () => {
    const collapseWindow = saiiaApi?.collapseStartupWindow || electronApi?.collapseStartupWindow
    if (presentationBusy || typeof collapseWindow !== 'function') {
      return
    }
    setPresentationBusy(true)
    try {
      const result = await collapseWindow()
      if (result?.ok) {
        setIsMascotCollapsed(true)
      }
    } catch {
      // Keep the expanded presentation available if native bounds cannot change.
    } finally {
      setPresentationBusy(false)
    }
  }

  const handleRestore = async () => {
    const restoreWindow = saiiaApi?.restoreStartupWindow || electronApi?.restoreStartupWindow
    if (presentationBusy || typeof restoreWindow !== 'function') {
      return
    }
    setPresentationBusy(true)
    try {
      const result = await restoreWindow()
      if (result?.ok) {
        setIsMascotCollapsed(false)
      }
    } catch {
      // Keep the mascot available for another restore attempt.
    } finally {
      setPresentationBusy(false)
    }
  }

  const loadPastSessions = async ({ force = false } = {}) => {
    if (!saiiaApi?.listInterviewSessions || historyLoadingRef.current) {
      return
    }
    if (!force && activeTab !== 'past') {
      return
    }
    historyLoadingRef.current = true
    const requestId = historyRequestIdRef.current + 1
    historyRequestIdRef.current = requestId
    setPastSessionsLoading(true)
    setPastSessionsError('')
    try {
      const result = await saiiaApi.listInterviewSessions({
        limit: 3,
        page: 1,
        status: 'ended,abandoned',
      })
      if (!mountedRef.current || historyRequestIdRef.current !== requestId) {
        return
      }
      const error = typeof result?.error === 'string' ? result.error : ''
      if (error) {
        if (/session expired/i.test(error)) {
          onSessionExpired?.()
          return
        }
        setPastSessions([])
        setPastSessionsError('We could not load your past sessions. Please try again.')
        return
      }
      const items = Array.isArray(result?.items) ? result.items : []
      setPastSessions(items.filter((session) => PAST_SESSION_STATUSES.has(session?.status)).slice(0, 3))
    } catch {
      if (mountedRef.current && historyRequestIdRef.current === requestId) {
        setPastSessions([])
        setPastSessionsError('We could not load your past sessions. Please try again.')
      }
    } finally {
      historyLoadingRef.current = false
      if (mountedRef.current && historyRequestIdRef.current === requestId) {
        setPastSessionsLoading(false)
      }
    }
  }

  const handleCreateTab = () => {
    setActiveTab('create')
    setMessage('')
    onShowCreate?.()
  }

  const handlePastSessions = () => {
    setActiveTab('past')
    setMessage('')
    onShowPastSessions?.()
    void loadPastSessions({ force: true })
  }

  const handleViewAllSessions = async () => {
    const openDashboard = saiiaApi?.openDashboard || electronApi?.openDashboard
    if (typeof openDashboard !== 'function') {
      return
    }
    try {
      await openDashboard()
    } catch {
      setMessage('We could not open the dashboard. Please try again.')
    }
  }

  const renderPastSessions = () => {
    if (pastSessionsLoading) {
      return <p className="startup-choice-history-status" role="status">Loading past sessions...</p>
    }
    if (pastSessionsError) {
      return (
        <div className="startup-choice-history-status startup-choice-history-status--error" role="alert">
          <p>{pastSessionsError}</p>
          <button type="button" onClick={() => void loadPastSessions({ force: true })}>Try again</button>
        </div>
      )
    }
    if (!pastSessions.length) {
      return <p className="startup-choice-history-status">No past sessions yet. Start a session from the Create tab.</p>
    }
    return (
      <div className="startup-choice-history-list" aria-label="Past interview sessions">
        {pastSessions.map((session) => {
          const companyName = String(session?.company_name || '').trim() || 'Company not specified'
          const targetRole = String(session?.target_role || '').trim() || 'Role not specified'
          return (
            <article className="startup-choice-history-row" key={session.id}>
              <div className="startup-choice-history-row__identity">
                <span className="startup-choice-history-avatar" aria-hidden="true">
                  {getCompanyInitial(session?.company_name)}
                </span>
                <span className="startup-choice-history-row__details">
                  <strong title={companyName}>{companyName}</strong>
                  <span title={targetRole}>{targetRole}</span>
                </span>
              </div>
              <time dateTime={session?.started_at || undefined}>{formatPastSessionDate(session?.started_at)}</time>
              {electronApi?.answerDiagram && <button type="button" onClick={() => setAnswerHistorySession(session.id)}>View answers</button>}
            </article>
          )
        })}
        {answerHistorySession && <DesktopAnswerHistory key={answerHistorySession} sessionId={answerHistorySession} api={electronApi} />}
      </div>
    )
  }

  if (isMascotCollapsed) {
    return (
      <div className="startup-choice-window startup-choice-window--mascot" aria-label="Intervucopilot mascot">
        <button
          className="startup-choice-mascot-button"
          type="button"
          aria-label="Restore Intervucopilot"
          disabled={presentationBusy}
          onClick={() => void handleRestore()}
        >
          <img src={loginMascotUrl} alt="" aria-hidden="true" />
        </button>
      </div>
    )
  }

  const isPast = activeTab === 'past'
  return (
    <div
      className={`startup-choice-window ${isPast ? 'startup-choice-window--history' : 'startup-choice-window--home'}`}
      aria-label="Intervucopilot startup session choices"
    >
      <section className="startup-choice-card">
        <header className="startup-choice-header">
          <div className="startup-choice-brand">
            <span className="startup-choice-brand__icon" aria-hidden="true">
              <img src={choiceBrandUrl} alt="" />
            </span>
            <h1>Intervucopilot</h1>
          </div>
          <div className="startup-choice-header__actions" aria-label="Session window controls">
            <span className="startup-choice-time" aria-label={timeAriaLabel}>
              <img src={choiceClockUrl} alt="" aria-hidden="true" />
              <span className="startup-choice-time__copy">
                <span className="startup-choice-time__value">
                  <strong>{hasTimeBalance ? normalizedRemainingMinutes : '--'}</strong> / {hasTimeBalance ? normalizedTotalMinutes : '--'} min
                </span>
                <small>remaining</small>
              </span>
            </span>
            <StartupAccountMenu key={`${safeAuthenticatedEmail}:${activeTab}`} authenticatedEmail={safeAuthenticatedEmail} onSignedOut={onSignedOut} />
            <button
              className="startup-choice-icon-button startup-choice-collapse-button"
              type="button"
              aria-label="Collapse startup choices"
              disabled={presentationBusy}
              onClick={() => void handleCollapse()}
            >
              <img src={choiceCollapseUrl} alt="" aria-hidden="true" />
            </button>
            <button
              className="startup-choice-close"
              type="button"
              aria-label="Close startup choices"
              onClick={closeStartupWindow}
            >
              <img src={choiceCloseUrl} alt="" aria-hidden="true" />
            </button>
          </div>
        </header>

        <main className="startup-choice-main">
          <div className="startup-choice-tabs" role="tablist" aria-label="Startup session mode">
            <button
              className={`startup-choice-tab ${!isPast ? 'startup-choice-tab--active' : ''}`}
              type="button"
              role="tab"
              aria-selected={!isPast}
              onClick={handleCreateTab}
            >
              <img src={isPast ? choicePastStarsUrl : choiceStarsUrl} alt="" aria-hidden="true" />
              <span>Create</span>
            </button>
            <button
              className={`startup-choice-tab ${isPast ? 'startup-choice-tab--active' : ''}`}
              type="button"
              role="tab"
              aria-selected={isPast}
              onClick={handlePastSessions}
            >
              <img src={isPast ? choicePastHistoryUrl : choiceHistoryUrl} alt="" aria-hidden="true" />
              <span>Past Sessions</span>
            </button>
          </div>

          {isPast ? (
            <>
              <section className="startup-choice-history-intro">
                <h2>Past Session :</h2>
              </section>
              <section className="startup-choice-history-content">{renderPastSessions()}</section>
              <button className="startup-choice-history-view-all" type="button" onClick={handleViewAllSessions}>
                View All Sessions
                <img src={choicePastViewAllArrowUrl} alt="" aria-hidden="true" />
              </button>
            </>
          ) : (
            <>
              <section className="startup-choice-intro">
                <h2>Start a New Session</h2>
                <p>Choose how you'd like to continue.</p>
              </section>

              <div className="startup-choice-options">
                <article className="startup-choice-option startup-choice-option--free">
                  <img className="startup-choice-corner startup-choice-corner--sparkle" src={choiceFreeStarsUrl} alt="" aria-hidden="true" />
                  <h3>Free Session</h3>
                  <p>{freeSessionLabel}</p>
                  <button type="button" className="startup-choice-link-button" onClick={onCreateSession}>
                    Start Session
                    <img src={choiceCardArrowUrl} alt="" aria-hidden="true" />
                  </button>
                </article>

                <article className="startup-choice-option">
                  <img className="startup-choice-corner startup-choice-corner--credit" src={choiceWalletUrl} alt="" aria-hidden="true" />
                  <h3>Buy Credits</h3>
                  <p>Get more session time</p>
                  <button type="button" className="startup-choice-link-button" onClick={() => setMessage('Plans will be available in a later phase.')}>
                    View Plans
                    <img src={choiceCardArrowUrl} alt="" aria-hidden="true" />
                  </button>
                </article>
              </div>

              <footer className="startup-choice-footer">
                <span>
                  <img src={choiceShieldUrl} alt="" aria-hidden="true" />
                  Your data is secure and private
                </span>
                <button type="button" onClick={() => setMessage('More details will be available in a later phase.')}>
                  Learn More <img src={choiceArrowUrl} alt="" aria-hidden="true" />
                </button>
              </footer>
            </>
          )}

          {message ? (
            <p className="startup-choice-message" aria-live="polite">{message}</p>
          ) : null}
        </main>
      </section>
    </div>
  )
}
