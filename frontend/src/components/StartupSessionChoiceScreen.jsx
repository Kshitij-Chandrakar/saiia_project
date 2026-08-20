import React, { useState } from 'react'

export default function StartupSessionChoiceScreen({ onCreateSession, onClose }) {
  const [message, setMessage] = useState('')
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null
  const electronApi = typeof window !== 'undefined' ? window.electronAPI : null

  const closeStartupWindow = () => {
    const closeWindow = onClose || saiiaApi?.closeStartupWindow || electronApi?.closeStartupWindow
    const closeResult = closeWindow?.()
    closeResult?.catch?.(() => {})
  }

  const handlePastSessions = () => {
    setMessage('Past sessions will be available in a later phase.')
  }

  return (
    <div className="startup-choice-window" aria-label="Intervu AI startup session choices">
      <section className="startup-choice-card">
        <header className="startup-choice-header">
          <div className="startup-choice-brand">
            <span className="startup-choice-brand__icon" aria-hidden="true">
              <span />
            </span>
            <h1>Intervu AI</h1>
          </div>
          <div className="startup-choice-header__actions" aria-label="Session window controls">
            <span className="startup-choice-time" aria-label="10 of 10 minutes remaining">
              <ClockIcon />
              <span>
                <strong>10</strong> / 10 min
                <small>remaining</small>
              </span>
            </span>
            <button className="startup-choice-icon-button" type="button" aria-label="More options">
              <DotsIcon />
            </button>
            <button className="startup-choice-icon-button" type="button" aria-label="Collapse startup choices">
              <ChevronIcon />
            </button>
            <button
              className="startup-choice-close"
              type="button"
              aria-label="Close startup choices"
              onClick={closeStartupWindow}
            >
              <CloseIcon />
            </button>
          </div>
        </header>

        <main className="startup-choice-main">
          <div className="startup-choice-tabs" role="tablist" aria-label="Startup session mode">
            <button className="startup-choice-tab startup-choice-tab--active" type="button" role="tab" aria-selected="true">
              <StarsIcon />
              <span>Create</span>
            </button>
            <button className="startup-choice-tab" type="button" role="tab" aria-selected="false" onClick={handlePastSessions}>
              <HistoryIcon />
              <span>Past Sessions</span>
            </button>
          </div>

          <section className="startup-choice-intro">
            <h2>Start a New Session</h2>
            <p>Choose how you'd like to continue.</p>
          </section>

          <div className="startup-choice-options">
            <article className="startup-choice-option startup-choice-option--free">
              <SparkleCorner />
              <h3>Free Session</h3>
              <p>10 minutes available</p>
              <button type="button" className="startup-choice-link-button" onClick={onCreateSession}>
                Create New Session
                <span aria-hidden="true">→</span>
              </button>
            </article>

            <article className="startup-choice-option">
              <CreditCorner />
              <h3>Buy Credits</h3>
              <p>Get more session time</p>
              <button type="button" className="startup-choice-link-button" onClick={() => setMessage('Plans will be available in a later phase.')}>
                View Plans
                <span aria-hidden="true">→</span>
              </button>
            </article>
          </div>

          <footer className="startup-choice-footer">
            <span>
              <ShieldIcon />
              Your data is secure and private
            </span>
            <button type="button" onClick={() => setMessage('More details will be available in a later phase.')}>
              Learn More <span aria-hidden="true">›</span>
            </button>
          </footer>

          {message ? (
            <p className="startup-choice-message" aria-live="polite">{message}</p>
          ) : null}
        </main>
      </section>
    </div>
  )
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 21 21" aria-hidden="true">
      <circle cx="10.5" cy="10.5" r="7.5" />
      <path d="M10.5 6.5v4.2l3 1.8" />
    </svg>
  )
}

function DotsIcon() {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="2.5" r="1" />
      <circle cx="6" cy="6" r="1" />
      <circle cx="6" cy="9.5" r="1" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true">
      <path d="M3.5 7.2 6 4.8l2.5 2.4" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  )
}

function StarsIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M6.3 2.7 7 5.2l2.4.8L7 6.8 6.3 9.3 5.6 6.8 3.2 6l2.4-.8.7-2.5ZM11.5 1.8l.4 1.4 1.4.4-1.4.5-.4 1.4-.5-1.4-1.3-.5 1.3-.4.5-1.4ZM11.5 9.7l.5 1.6 1.6.5-1.6.5-.5 1.6-.5-1.6-1.6-.5 1.6-.5.5-1.6Z" />
    </svg>
  )
}

function HistoryIcon() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true">
      <path d="M5.4 5.6H2.9V3.1" />
      <path d="M3.4 8.9a5.4 5.4 0 1 0 1.7-3.9L2.9 7.2" />
      <path d="M9 5.8v3.5l2.4 1.4" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 13 13" aria-hidden="true">
      <path d="M6.5 1.5 10 3v2.7c0 2.2-1.4 4.2-3.5 5-2.1-.8-3.5-2.8-3.5-5V3l3.5-1.5Z" />
      <path d="m4.9 6.4 1 1 2.1-2.2" />
    </svg>
  )
}

function SparkleCorner() {
  return <span className="startup-choice-corner startup-choice-corner--sparkle" aria-hidden="true">✦</span>
}

function CreditCorner() {
  return <span className="startup-choice-corner startup-choice-corner--credit" aria-hidden="true" />
}
