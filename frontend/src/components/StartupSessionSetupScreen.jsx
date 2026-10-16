import React, { useEffect, useRef, useState } from 'react'
import './startup-session-setup.css'
import StartupAccountMenu from './StartupAccountMenu'
import brand from '../assets/startup-setup/imgContainer.svg'
import clock from '../assets/startup-setup/imgMdiClockOutline.svg'
import collapse from '../assets/startup-setup/imgContainer2.svg'
import close from '../assets/startup-setup/imgContainer3.svg'
import back from '../assets/startup-setup/imgContainer4.svg'
import navClose from '../assets/startup-setup/imgContainer5.svg'
import arrow from '../assets/startup-setup/imgContainer12.svg'
import mascot from '../assets/startup-login/login-mascot.png'


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

export default function StartupSessionSetupScreen({ initialConfig, onBack, onStartSession, onSignedOut, authenticatedEmail = '', remainingMinutes = null, totalMinutes = null }) {
  const [quotaLoading, setQuotaLoading] = useState(true)
  const quotaPendingRef = useRef(false)
  const mountedRef = useRef(false)
  const [draft, setDraft] = useState(() => ({ ...EMPTY_SETUP, ...(initialConfig || {}) }))
  const [resumes, setResumes] = useState([])
  const [resumesLoading, setResumesLoading] = useState(false)
  const [resumeLoadError, setResumeLoadError] = useState('')
  const [resumeMessage, setResumeMessage] = useState('')
  const [message, setMessage] = useState('')
  const [starting, setStarting] = useState(false)
  const [companyError, setCompanyError] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const companyRef = useRef(null)
  const presentationBusyRef = useRef(false)
  const startingRef = useRef(false)
  const startIdempotencyKeyRef = useRef('')
  const electronApi = typeof window !== 'undefined' ? window.electronAPI : null
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null

  const hasTimeBalance = remainingMinutes !== null && totalMinutes !== null &&
    Number.isFinite(remainingMinutes) && Number.isFinite(totalMinutes) && remainingMinutes >= 0 && totalMinutes >= 0
  const checkQuotaAvailability = async (refresh = false) => {
    if (quotaPendingRef.current || hasTimeBalance) return
    quotaPendingRef.current = true
    setQuotaLoading(true)
    try {
      const load = refresh ? saiiaApi?.refreshCloudStartupContext : saiiaApi?.getCloudStartupContext
      await load?.()
      // The current safe startup contract contains no time balance. Never infer one from cloud readiness.
    } catch {
      // Render a generic unavailable state; provider details do not belong in the header.
    } finally {
      quotaPendingRef.current = false
      if (mountedRef.current) setQuotaLoading(false)
    }
  }
  useEffect(() => {
    mountedRef.current = true
    if (hasTimeBalance) setQuotaLoading(false)
    else void checkQuotaAvailability()
    return () => { mountedRef.current = false }
  }, [hasTimeBalance, authenticatedEmail])

  const updateDraft = (key) => (event) => {
    setDraft((current) => ({ ...current, [key]: event.target.value }))
    if (key === 'company') setCompanyError('')
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
    if (startingRef.current) {
      return
    }
    if (selectedResumeBlocked) {
      setMessage('This resume is uploaded but not ready for generation yet. Finish extraction/indexing from the dashboard, then refresh.')
      return
    }
    if (!draft.company.trim()) {
      setCompanyError('Enter a company name.')
      companyRef.current?.focus()
      return
    }
    startingRef.current = true
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
          company_name: draft.company.trim(),
          job_description: draft.jobContext,
        },
        { idempotencyKey },
      )
      const session = created?.session
      if (!session?.id) {
        setMessage(created?.error || 'Session could not be created. Check your cloud connection and retry.')
        return
      }
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
      startingRef.current = false
      setStarting(false)
    }
  }

  useEffect(() => {
    if (collapsed) document.documentElement.dataset.startupMascot = 'true'
    else delete document.documentElement.dataset.startupMascot
    return () => { delete document.documentElement.dataset.startupMascot }
  }, [collapsed])

  const setPresentation = async (next) => {
    if (presentationBusyRef.current) return
    presentationBusyRef.current = true
    try {
      const result = await (next ? electronApi?.collapseStartupWindow?.() : electronApi?.restoreStartupWindow?.())
      if (result?.ok) setCollapsed(next)
      else setMessage('Unable to change window presentation.')
    } catch { setMessage('Unable to change window presentation.') }
    finally { presentationBusyRef.current = false }
  }
  if (collapsed) return <button className="startup-setup-mascot" aria-label="Restore session setup" onClick={() => void setPresentation(false)}><img src={mascot} alt="" /></button>
  return (
    <div className="startup-choice-window startup-session-setup" aria-label="Intervucopilot session setup">
      <section className="startup-setup-card">
        <header className="startup-choice-header">
          <div className="startup-choice-brand"><span className="startup-choice-brand__icon"><img src={brand} alt="" /></span><h1>Intervucopilot</h1></div>
          <span className="startup-choice-time" role="status" aria-live="polite"><img src={clock} alt="" /><span>{hasTimeBalance ? <><strong>{remainingMinutes}</strong> / {totalMinutes} min<small>remaining</small></> : quotaLoading ? 'Checking…' : <>Time unavailable<button type="button" className="startup-setup-quota-retry" onClick={() => void checkQuotaAvailability(true)}>Retry</button></>}</span></span>
          <StartupAccountMenu key={authenticatedEmail} authenticatedEmail={authenticatedEmail} onSignedOut={onSignedOut} disabled={starting} />
          <button type="button" className="startup-setup-control" aria-label="Collapse session setup" disabled={starting} onClick={() => void setPresentation(true)}><img src={collapse} alt="" /></button>
          <button type="button" className="startup-setup-control startup-setup-close" aria-label="Close window" onClick={() => electronApi?.closeStartupWindow?.()?.catch?.(() => {})}><img src={close} alt="" /></button>
        </header>
        <nav className="startup-setup-titlebar" aria-label="Session setup navigation">
          <button type="button" aria-label="Back to session choices" onClick={onBack} disabled={starting}><img src={back} alt="" /></button><h2>Create New Session</h2>
          <button type="button" aria-label="Cancel session setup" onClick={onBack} disabled={starting}><img src={navClose} alt="" /></button>
        </nav>
        <main className="startup-setup-main">
          <section className="startup-setup-intro"><h3>Prepare your interview</h3><p>Tell Intervucopilot a little about your interview to personalize your experience.</p></section>
          <div className="startup-setup-grid">
            <label><span>Company<span className="startup-setup-required" aria-hidden="true">*</span></span><input ref={companyRef} required aria-invalid={Boolean(companyError)} aria-describedby={companyError ? 'setup-company-error' : undefined} value={draft.company} onChange={updateDraft('company')} placeholder="e.g. Google" />{companyError && <p id="setup-company-error" role="alert">{companyError}</p>}</label>
            <label><span>Position</span><input value={draft.role} onChange={updateDraft('role')} placeholder="e.g. UI/UX Designer" /></label>
          </div>
          <div className="startup-setup-grid">
            <label><span>Session title</span><input value={draft.title} onChange={updateDraft('title')} placeholder="e.g. Design interview" /></label>
            <label><span>AI Model</span><select aria-describedby="setup-model-description" defaultValue="runtime"><option value="runtime">Automatic</option></select></label>
          </div>
          <p id="setup-model-description" className="startup-setup-model-description">Uses configured model routing and provider fallback.</p>
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
                <span className="startup-setup-select-label">Select a resume</span>
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
            {selectedResume && <p className="startup-setup-resume-summary">{selectedResume.display_name || selectedResume.original_filename || 'Uploaded resume'} - {getResumeReadinessLabel(selectedResume)}</p>}
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
          <label className="startup-setup-field"><span>Job description / context <small>Optional</small></span><textarea value={draft.jobContext} onChange={updateDraft('jobContext')} placeholder="Paste role notes, job description, or interview context..." rows={4} /></label>
          {(message || startBlockedMessage) && <p className="startup-choice-message" role="status">{message || startBlockedMessage}</p>}
        </main>
        <footer className="startup-setup-footer">
          <button type="button" className="startup-setup-back" onClick={onBack} disabled={starting}><img src={back} alt="" />Back</button>
          <button type="button" className="startup-setup-start" onClick={handleStartSession} disabled={startDisabled}>{starting ? 'Starting...' : <>Start Session<img src={arrow} alt="" /></>}</button>
        </footer>
      </section>
    </div>
  )
}
