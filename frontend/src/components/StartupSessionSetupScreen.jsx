import React, { useEffect, useRef, useState } from 'react'

const EMPTY_SETUP = {
  title: '',
  role: '',
  company: '',
  jobContext: '',
  selectedResumeId: '',
  selectedResumeName: '',
}

const READINESS_LABELS = {
  ready: 'Ready',
  processing: 'Processing',
  not_indexed: 'Needs indexing',
  no_chunks: 'Needs indexing',
  needs_confirmation: 'Needs confirmation',
  failed: 'Failed',
  unknown: 'Not ready',
}

function getResumeReadinessLabel(resume) {
  if (!resume) {
    return ''
  }
  if (resume.can_generate === true) {
    return READINESS_LABELS.ready
  }
  return READINESS_LABELS[resume.readiness_reason] || READINESS_LABELS.unknown
}

export default function StartupSessionSetupScreen({ initialConfig, onBack, onStartSession }) {
  const [draft, setDraft] = useState(() => ({ ...EMPTY_SETUP, ...(initialConfig || {}) }))
  const [resumes, setResumes] = useState([])
  const [resumesLoading, setResumesLoading] = useState(false)
  const [resumeLoadError, setResumeLoadError] = useState('')
  const [resumeMessage, setResumeMessage] = useState('')
  const [message, setMessage] = useState('')
  const [starting, setStarting] = useState(false)
  const startIdempotencyKeyRef = useRef('')
  const electronApi = typeof window !== 'undefined' ? window.electronAPI : null
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null

  const updateDraft = (key) => (event) => {
    setDraft((current) => ({ ...current, [key]: event.target.value }))
  }

  const loadResumes = async (isActive = () => true) => {
    if (typeof saiiaApi?.listCloudResumes !== 'function') {
      if (isActive()) {
        setResumes([])
        setResumeLoadError('Resume selection is unavailable in this desktop build.')
        setResumeMessage('Resume selection is unavailable in this desktop build.')
      }
      return
    }
    setResumesLoading(true)
    setResumeLoadError('')
    setResumeMessage('')
    try {
      const result = await saiiaApi.listCloudResumes()
      if (!isActive()) {
        return
      }
      const items = Array.isArray(result?.items) ? result.items : []
      const nextError = typeof result?.error === 'string' ? result.error.trim() : ''
      setResumes(items)
      setResumeLoadError(nextError)
      setResumeMessage(nextError)
    } catch {
      if (isActive()) {
        setResumes([])
        setResumeLoadError('Unable to load resumes.')
        setResumeMessage('Unable to load resumes.')
      }
    } finally {
      if (isActive()) {
        setResumesLoading(false)
      }
    }
  }

  useEffect(() => {
    let active = true
    loadResumes(() => active)
    return () => {
      active = false
    }
  }, [])

  const updateSelectedResume = (event) => {
    const selectedResumeId = event.target.value
    const selected = resumes.find((resume) => resume.id === selectedResumeId)
    setDraft((current) => ({
      ...current,
      selectedResumeId,
      selectedResumeName: selected?.display_name || '',
    }))
    setMessage('')
  }

  const openDashboard = () => {
    saiiaApi?.openDashboard?.().catch?.(() => {
      setResumeMessage('Unable to open dashboard.')
    })
  }

  const selectedResume = draft.selectedResumeId
    ? resumes.find((resume) => resume.id === draft.selectedResumeId)
    : null
  const cloudSessionStorageUnavailable = resumeLoadError === 'Cloud temporarily unavailable.'
  const selectedResumeMissing = Boolean(draft.selectedResumeId && !selectedResume)
  const selectedResumeBlocked = Boolean(
    draft.selectedResumeId && (resumesLoading || selectedResumeMissing || selectedResume.can_generate !== true)
  )
  const startBlockedByResumeLoad = resumesLoading || Boolean(resumeLoadError)
  const startBlockedByUnavailableStorage = cloudSessionStorageUnavailable
  const startDisabled = Boolean(
    starting ||
    startBlockedByResumeLoad ||
    startBlockedByUnavailableStorage ||
    selectedResumeBlocked
  )
  const startBlockedMessage = cloudSessionStorageUnavailable
    ? 'Cloud session storage is temporarily unavailable. Please restart the backend and try again.'
    : ''

  const handleStartSession = async () => {
    if (startDisabled) {
      if (cloudSessionStorageUnavailable) {
        setMessage('Cloud session storage is temporarily unavailable. Please restart the backend and try again.')
        return
      }
      if (resumesLoading) {
        setMessage('Loading the latest resume readiness before starting your session.')
        return
      }
      if (resumeLoadError) {
        setMessage(resumeLoadError)
        return
      }
    }
    if (starting) {
      return
    }
    if (selectedResumeBlocked) {
      setMessage('This resume is uploaded but not ready for generation yet. Finish extraction/indexing from the dashboard, then refresh.')
      return
    }
    setStarting(true)
    setMessage('')
    const idempotencyKey =
      startIdempotencyKeyRef.current ||
      `desktop-session:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 10)}`
    startIdempotencyKeyRef.current = idempotencyKey
    try {
      if (typeof saiiaApi?.createInterviewSession !== 'function') {
        setMessage('Cloud session creation is unavailable in this desktop build.')
        return
      }
      const created = await saiiaApi.createInterviewSession(
        {
          title: draft.title,
          selected_resume_id: draft.selectedResumeId || undefined,
          target_role: draft.role,
          company_name: draft.company,
          job_description: draft.jobContext,
        },
        { idempotencyKey },
      )
      const session = created?.session
      if (!session?.id) {
        setMessage(created?.error || 'Session could not be created. Check your cloud connection and retry.')
        return
      }
      console.info('Intervu AI active interview session', {
        activeSessionIdExists: true,
        activeSessionIdSuffix: String(session.id).slice(-6),
        sessionStatus: session.status || 'unknown',
      })
      const result = await electronApi?.completeStartup?.()
      if (result?.ok !== true) {
        await saiiaApi.endInterviewSession?.(session.id).catch?.(() => {})
        setMessage('Session could not be started. Log in again and retry.')
        return
      }
      onStartSession?.({
        ...draft,
        activeSessionId: session.id,
        activeSessionStatus: session.status,
        activeSessionStartedAt: session.started_at,
        sessionTitle: draft.title,
        targetRole: draft.role,
        companyName: draft.company,
        jobDescription: draft.jobContext,
      })
    } catch {
      setMessage('Cloud session storage is temporarily unavailable. Please restart the backend and try again.')
    } finally {
      startIdempotencyKeyRef.current = ''
      setStarting(false)
    }
  }

  return (
    <div className="startup-choice-window" aria-label="Intervu AI session setup">
      <section className="startup-setup-card">
        <header className="startup-choice-header">
          <div className="startup-choice-brand">
            <span className="startup-choice-brand__icon" aria-hidden="true">
              <span />
            </span>
            <h1>Intervu AI</h1>
          </div>
          <span className="startup-choice-time" aria-label="10 of 10 minutes remaining">
            <span>
              <strong>10</strong> / 10 min
              <small>remaining</small>
            </span>
          </span>
        </header>

        <main className="startup-setup-main">
          <div className="startup-setup-titlebar">
            <button type="button" className="startup-setup-back" onClick={onBack}>
              ←
            </button>
            <h2>Create New Session</h2>
          </div>

          <section className="startup-setup-intro">
            <h3>Prepare your interview</h3>
            <p>Tell Intervu AI a little about your interview to personalize your experience.</p>
          </section>

          <div className="startup-setup-grid">
            <label>
              <span>Session title</span>
              <input value={draft.title} onChange={updateDraft('title')} placeholder="e.g. Design interview" />
            </label>
            <label>
              <span>Target role</span>
              <input value={draft.role} onChange={updateDraft('role')} placeholder="e.g. UI/UX Designer" />
            </label>
          </div>

          <label className="startup-setup-field">
            <span>Company name <small>Optional</small></span>
            <input value={draft.company} onChange={updateDraft('company')} placeholder="e.g. Google" />
          </label>

          <label className="startup-setup-field">
            <span>Job description / context <small>Optional</small></span>
            <textarea
              value={draft.jobContext}
              onChange={updateDraft('jobContext')}
              placeholder="Paste role notes, job description, or interview context..."
              rows={4}
            />
          </label>

          <section className="startup-setup-resume" aria-label="Resume and reference document">
            <div className="startup-setup-resume__header">
              <strong>Resume / reference document</strong>
              <button type="button" onClick={() => loadResumes()} disabled={resumesLoading}>
                {resumesLoading ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            {resumesLoading ? (
              <p>Loading resumes...</p>
            ) : resumes.length ? (
              <label>
                <span>Select a resume</span>
                <select value={draft.selectedResumeId} onChange={updateSelectedResume}>
                  <option value="">Select a resume</option>
                  {resumes.map((resume) => (
                    <option key={resume.id} value={resume.id}>
                      {resume.display_name || resume.original_filename || 'Uploaded resume'} - {getResumeReadinessLabel(resume)}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <div>
                <p>No uploaded resumes found. Upload a resume from the web dashboard first.</p>
                <button type="button" onClick={openDashboard}>
                  Open dashboard to upload resume
                </button>
              </div>
            )}
            {selectedResumeBlocked ? (
              <div className="startup-setup-resume__message" aria-live="polite">
                <p>
                  {resumesLoading
                    ? 'Loading the latest resume readiness before starting your session.'
                    : selectedResumeMissing
                      ? 'The selected resume could not be found. Refresh your resume list and choose a ready resume again.'
                    : 'This resume is uploaded but not ready for generation yet. Finish extraction/indexing from the dashboard, then refresh.'}
                </p>
                <button type="button" onClick={openDashboard}>
                  Open dashboard to finish resume setup
                </button>
              </div>
            ) : null}
            {resumeMessage ? <p className="startup-setup-resume__message" aria-live="polite">{resumeMessage}</p> : null}
          </section>
        </main>

        <footer className="startup-setup-footer">
          <button type="button" className="startup-setup-back" onClick={onBack}>
            ← Back
          </button>
          <button type="button" className="startup-setup-start" onClick={handleStartSession} disabled={startDisabled}>
            {starting ? 'Starting...' : 'Start Session →'}
          </button>
        </footer>

        {!message && startBlockedMessage ? <p className="startup-choice-message" aria-live="polite">{startBlockedMessage}</p> : null}
        {message ? <p className="startup-choice-message" aria-live="polite">{message}</p> : null}
      </section>
    </div>
  )
}
