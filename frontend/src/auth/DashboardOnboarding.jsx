import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { onboardingRequest, onboardingResources, onboardingUpload, onboardingExtractJob, cloudResource } from './onboardingApi'
import './dashboard-onboarding.css'
import DashboardLoading from './DashboardLoading'
import mascot from '../assets/onboarding/beeb2.png'
import back from '../assets/onboarding/eca13.svg'
import upload from '../assets/onboarding/1fa9b.svg'
import arrow from '../assets/onboarding/ec10a.svg'
import documentIcon from '../assets/onboarding/7ac80.svg'
import jobIcon from '../assets/onboarding/9bd1b.svg'
import notesIcon from '../assets/onboarding/15323.svg'
import downloadIcon from '../assets/onboarding/6e357.svg'
import linesLeft from '../assets/onboarding/814a8.svg'
import linesRight from '../assets/onboarding/f5c8f.svg'
import linesLeftDesktop from '../assets/onboarding/7d1f1.svg'
import linesRightLater from '../assets/onboarding/0881d.svg'
import linesRightSession from '../assets/onboarding/0ee6f.svg'
import glowLeft from '../assets/onboarding/b257d.svg'
import glowRight from '../assets/onboarding/e24cf.svg'

const titles = ['Welcome to Intervucopilot', 'Add your CV or Resume', 'Give your preparation more context',
  'Everything starts with an interview session', 'Get the best live-call experience']
const descriptions = ['Your AI interview copilot helps you prepare smarter, practice confidently, and improve your answers with real-time feedback.',
  'Help Intervucopilot understand your experience and tailor interview questions to your background.',
  'Add job descriptions, company research, or project notes to receive more relevant interview guidance.',
  'Choose a role and interview type to begin practicing with your AI copilot. Intervucopilot follows the conversation and suggests answers.',
  'Intervucopilot works in your browser, but the desktop app is recommended for smoother sessions during interviews and calls.']

export function DashboardOnboardingGate({ backendUrl, children }) {
  const [state, setState] = useState(null), [error, setError] = useState(''), [attempt, retry] = useState(0)
  const location = useLocation(), navigate = useNavigate()
  useEffect(() => {
    if (window.electronAPI) return
    let active = true
    const controller = new AbortController()
    setState(null); setError('')
    onboardingRequest(backendUrl, '', undefined, 'GET', controller.signal).then(value => {
      if (!active) return
      setState(value)
      if (!value.onboarding_completed_at && location.pathname !== '/auth/onboarding') navigate('/auth/onboarding', { replace: true })
      if (value.onboarding_completed_at && location.pathname === '/auth/onboarding') navigate('/auth/dashboard', { replace: true })
    }).catch(() => { if (active) setError('Onboarding is unavailable. Please retry. Account setup or the onboarding migration may not be ready.') })
    return () => { active = false; controller.abort() }
  }, [backendUrl, location.pathname, attempt, navigate])
  if (window.electronAPI) return children
  if (error) return <main className="dashboard-onboarding"><section className="ob-card ob-loading"><p role="alert">{error}</p><button onClick={() => retry(v => v + 1)}>Retry onboarding</button></section></main>
  if (!state || (!state.onboarding_completed_at && location.pathname !== '/auth/onboarding')) return <DashboardLoading page={location.pathname === '/auth/resume' ? 'resume' : location.pathname === '/auth/sessions' ? 'sessions' : 'dashboard'} />
  if (state.onboarding_completed_at) return children
  return <DashboardOnboarding key={location.key} backendUrl={backendUrl} initial={state} onComplete={() => { setState(v => ({ ...v, onboarding_completed_at: true })); navigate('/auth/dashboard', { replace: true }) }} />
}

export default function DashboardOnboarding({ backendUrl, initial, onComplete }) {
  const [step, setStep] = useState(initial.onboarding_current_step), [resources, setResources] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [editor, setEditor] = useState('')
  const [documentFile, setDocumentFile] = useState(null), [processingConsent, setProcessingConsent] = useState(false)
  const [draft, setDraft] = useState({ company: '', position: '', job_description: '' })
  const [selectedResume, setSelectedResume] = useState(null), [job, setJob] = useState(null), [session, setSession] = useState(null)
  const editorTriggerRef = useRef(null)
  const heading = useRef(null), lock = useRef(false), active = useRef(true), fileInput = useRef(null)
  const jobKey = useRef(crypto.randomUUID()), sessionKey = useRef(crypto.randomUUID())
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function load() {
    const value = await onboardingResources(backendUrl)
    if (!active.current) return
    setResources(value); setSelectedResume(current => current || value.resume)
    setJob(current => current || value.jobs.find(item => item.is_active) || value.jobs[0] || null)
    setSession(value.sessions.find(item => item.status === 'active') || null)
  }
  useEffect(() => {
    const refresh = () => { if (!lock.current) void load().catch(() => { if (active.current) setError('Unable to load your resources. Please retry.') }) }
    refresh(); window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [backendUrl])
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [step])
  async function action(work) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try { await work() } catch { if (active.current) setError('Unable to save. Your previous data has been kept. Please retry.') }
    finally { lock.current = false; if (active.current) setBusy(false) }
  }
  useEffect(() => {
    if (editor || busy || !editorTriggerRef.current) return
    const trigger = editorTriggerRef.current
    editorTriggerRef.current = null
    // The closed render has removed inert; restore the original editor action.
    if (trigger.isConnected && !trigger.disabled && !trigger.closest('[inert]')) trigger.focus()
    else heading.current?.focus({ preventScroll: true })
  }, [editor, busy])
  function changeEditor(next, trigger) {
    if (trigger) editorTriggerRef.current = trigger
    setProcessingConsent(false)
    setDocumentFile(null)
    setEditor(next)
  }
  function move(next) { void action(async () => { const value = await onboardingRequest(backendUrl, '/step', { current_step: next }, 'PATCH'); if (!active.current) return; if (value.onboarding_completed_at) onComplete(); else { setStep(value.onboarding_current_step); changeEditor('') } }) }
  function finish() { void action(async () => { const value = await onboardingRequest(backendUrl, '/complete', {}, 'POST'); if (!value.onboarding_completed_at) throw Error(); if (active.current) onComplete() }) }
  function uploadFile(file) { if (!file) return; void action(async () => { const result = await onboardingUpload(backendUrl, file); if (active.current) { setSelectedResume(result); setNotice('Resume uploaded. Review and confirm it in Resumes before using it for interviews.') } }) }
  function extractJob(event) {
    event.preventDefault()
    if (!documentFile || !processingConsent) return
    void action(async () => {
      const result = await onboardingExtractJob(backendUrl, documentFile)
      if (active.current) {
        const extracted = result.draft || result.context || result.job_context || result
        setDraft({ company: extracted.company || '', position: extracted.position || '', job_description: extracted.job_description || '', extraction_receipt_id: extracted.extraction_receipt_id || null })
        changeEditor('job'); setNotice('Review the extracted context before saving.')
      }
    })
  }
  function saveJob(event) { event.preventDefault(); void action(async () => { const result = await cloudResource(backendUrl, '/api/job-contexts', draft, jobKey.current); if (active.current) { setJob(result.job_context); changeEditor(''); jobKey.current = crypto.randomUUID() } }) }
  function startSession() { if (session?.status === 'active') { setNotice('Your existing session is ready in Call Sessions.'); return }; void action(async () => { const result = await cloudResource(backendUrl, '/api/interview-sessions', { title: draft.position || 'Interview preparation', target_role: draft.position || job?.position || '', company_name: draft.company || job?.company || '', selected_resume_id: selectedResume?.is_active ? selectedResume.id : null, job_context_id: job?.id || null }, sessionKey.current); if (active.current) setSession(result.session) }) }
  return <main className="dashboard-onboarding"><section className="ob-card" aria-label="Dashboard onboarding" aria-busy={busy}>
    <header className="ob-header" inert={editor ? true : undefined}>{step > 1 && <button className="ob-back" type="button" aria-label="Back" disabled={busy} onClick={() => move(step - 1)}><img src={back} alt="" /></button>}
      <ol className="ob-progress" aria-label={`Step ${step} of 5`}>{titles.map((title, index) => <li key={title} aria-current={step === index + 1 ? 'step' : undefined} aria-label={`${index + 1}: ${title}`} />)}</ol>
      <button className="ob-skip" type="button" disabled={busy} onClick={finish}>Skip</button></header>
    <div className="ob-body" inert={editor ? true : undefined}><div className="ob-decoration" aria-hidden="true"><img className="ob-lines-left" src={step === 5 ? linesLeftDesktop : linesLeft} alt="" /><img className="ob-lines-right" src={step === 5 ? linesRightLater : step === 4 ? linesRightSession : linesRight} alt="" /><img className="ob-glow-left" src={glowLeft} alt="" /><img className="ob-glow-right" src={glowRight} alt="" /></div>
      <div className={`ob-step ob-step-${step}`}>
        <div className="ob-graphic">
          {step === 1 && <><div className="ob-mascot"><img src={mascot} alt="Intervucopilot mascot" /></div><div className="ob-proof"><strong>Trusted by more than 1,530,000+ candidates</strong><div><span>{'\u2605 \u2605 \u2605 \u2605 \u2605'}</span> <b>4.9</b><small> \u00b7 340,000+ mock reviews</small></div></div></>}
          {step === 2 && <><button className="ob-upload" type="button" disabled={busy || !resources} onClick={() => fileInput.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) uploadFile(e.dataTransfer.files[0]) }}><span className="ob-upload-icon"><img src={upload} alt="" /></span><strong>{!resources ? 'Loading resumes...' : selectedResume?.original_filename || 'Drop your resume here or click to browse'}</strong><small>{selectedResume ? `Status: ${selectedResume.status}` : 'Supports PDF, DOCX, or TXT up to 5MB'}</small><span className="ob-private">ATS parse-ready &amp; 100% private</span></button><input ref={fileInput} type="file" hidden accept=".pdf,.docx,.txt" onChange={e => { uploadFile(e.target.files[0]); e.target.value = '' }} />{selectedResume && <Link className="ob-manage" to="/auth/resume" target="_blank" rel="noopener noreferrer">Review / manage your resume</Link>}</>}
          {step === 3 && <div className="ob-context"><div className="ob-document"><small>{job ? 'Saved preparation context' : 'Preparation context'}</small><strong>{job ? (job.position || job.company || 'Job description') : 'No job context added yet'}</strong><p>{job ? job.company : 'Add context when you are ready.'}</p></div><button className="ob-chip ob-chip-top" disabled={busy} onClick={event => { changeEditor('upload', event.currentTarget); setNotice('') }}><img src={documentIcon} alt="" />Upload Document</button><button className="ob-chip ob-chip-right" disabled={busy} onClick={event => changeEditor('job', event.currentTarget)}><img src={jobIcon} alt="" />Add Job Description</button><button className="ob-chip ob-chip-bottom" disabled={busy} onClick={event => changeEditor('notes', event.currentTarget)}><img src={notesIcon} alt="" />Add Company Notes</button></div>}
          {step === 4 && <div className="ob-session"><div className="ob-session-ghost" /><small>{session?.started_at ? new Date(session.started_at).toLocaleDateString() : 'INTERVIEW SESSION'}</small><strong>{session?.company_name || job?.company || 'Your interview'}</strong><p>{session?.target_role || job?.position || 'No session created yet'}</p><div className="ob-tags"><span>Interview</span><span>Transcript</span></div><div className="ob-session-bottom"><span>{session ? session.status : 'Ready to Start'}</span><button type="button" disabled={busy || !resources} onClick={startSession}>Start Session</button></div></div>}
          {step === 5 && <div className="ob-live" role="img" aria-label="Illustrative live-call preview"><div className="ob-live-toolbar"><span>{'\u25cf'} LIVE 0:42</span><span>Google Meet</span><b>Answer {'\u2318\u21b5'}</b><span>Screenshot {'\u2318\u21e7\u21b5'}</span></div><div className="ob-live-label">INTERVIEWER ASKED:</div><div className="ob-live-question"> &ldquo;Tell me about a time you resolved a major production incident under pressure.&rdquo;</div><div className="ob-live-answer"><strong>AI Copilot Suggested Answer (STAR Method):</strong><p>&bull; Situation: Payment gateway outage triggered 504 gateway timeouts during Black Friday peak traffic.</p><p>&bull; Task: Lead rapid triage, identify primary bottleneck, and recover transaction throughput with zero data loss.</p><p>&bull; Action: Isolated cascading DB locks, diverted read traffic to read-replicas, and enabled cached payment token fallback.</p><p>&bull; Result: Restored full service within 7 minutes; prevented ~$350K in abandoned checkouts and authored permanent circuit-breaker fix.</p></div></div>}
        </div>
        <h1 tabIndex={-1} ref={heading}>{titles[step - 1]}</h1><p className="ob-description">{descriptions[step - 1]}</p>
        {resources?.failed && <p className="ob-message" role="status">Some resources could not be loaded. <button onClick={() => void action(load)}>Retry resources</button></p>}
        {notice && <p className="ob-message" role="status">{notice}</p>}{error && <p className="ob-message ob-error" role="alert">{error}</p>}
        <footer className="ob-actions">{step < 5 ? <button className="ob-primary" type="button" disabled={busy} onClick={() => move(step + 1)}>{busy ? 'Saving...' : step === 1 ? 'Get Started' : <>Next <img src={arrow} alt="" /></>}</button> : <><button className="ob-secondary" disabled={busy} onClick={finish}>Continue to App</button><button className="ob-primary" disabled={busy} onClick={() => setNotice('Desktop download is not published yet. You can continue to the app in your browser.')}><img src={downloadIcon} alt="" />Download Desktop App</button></>}</footer>
      </div>
    </div>
    {editor && <div className="ob-editor" role="dialog" aria-modal="true" aria-labelledby="ob-editor-title" onKeyDown={e => {
      if (e.key === 'Escape' && !busy) { changeEditor('') }
      if (e.key === 'Tab') {
        const controls = [...e.currentTarget.querySelectorAll('input,textarea,button')].filter(el => !el.disabled)
        const first = controls[0], last = controls[controls.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
      }
    }}><form onSubmit={editor === 'upload' ? extractJob : saveJob}><h2 id="ob-editor-title">{editor === 'upload' ? 'Upload Document' : editor === 'notes' ? 'Add Company Notes' : 'Add Job Description'}</h2>{editor === 'upload' ? <><label>Document<input type="file" accept=".pdf,.docx,.txt" required onChange={e => { setProcessingConsent(false); setDocumentFile(e.target.files[0] || null) }} autoFocus /></label><label className="ob-consent"><input type="checkbox" required checked={processingConsent} onChange={e => setProcessingConsent(e.target.checked)} />I agree to send this document to the configured extraction provider.</label><button type="submit" disabled={busy || !processingConsent || !documentFile}>Extract document</button></> : <><label>Company<input value={draft.company} maxLength={160} onChange={e => setDraft({ ...draft, company: e.target.value })} autoFocus /></label><label>Role<input value={draft.position} maxLength={160} onChange={e => setDraft({ ...draft, position: e.target.value })} /></label><label htmlFor="ob-job-description">Job description</label><textarea id="ob-job-description" value={draft.job_description} maxLength={20000} onChange={e => setDraft({ ...draft, job_description: e.target.value })} />{error && <p role="alert">{error}</p>}<button type="submit" disabled={busy}>Save context</button></>}<button type="button" disabled={busy} onClick={() => changeEditor('')}>Cancel</button></form></div>}
  </section></main>
}
