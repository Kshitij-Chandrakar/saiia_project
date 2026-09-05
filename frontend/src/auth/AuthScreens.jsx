import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, FileText, LogOut, Upload } from 'lucide-react'

import {
  askInterviewSessionAI,
  bootstrapProfile,
  confirmCloudResume,
  createDesktopHandoff,
  deleteCloudResume,
  downloadInterviewTranscript,
  extractCloudResume,
  fetchInterviewAskAIMessages,
  fetchInterviewSessionNotes,
  fetchInterviewTranscriptEntries,
  fetchInterviewSessions,
  fetchCloudResumeStatus,
  fetchCurrentCloudResume,
  fetchCurrentUser,
  fetchReviewCandidate,
  generateInterviewSessionNotes,
  rebuildCloudResumeIndex,
  submitMarketingUnsubscribe,
  uploadCloudResume,
} from './authApi'
import { supabase } from './supabaseClient'
import './auth.css'


const AUTH_CALLBACK_URL = 'http://localhost:5173/auth/callback'
const PASSWORD_RESET_URL = 'http://localhost:5173/auth/reset-password'
const UNSUBSCRIBE_CONFIRMATION = 'You have been unsubscribed from promotional and discount emails if this link was valid.'
const UNSUBSCRIBE_TRANSACTIONAL_NOTICE = 'You may still receive important account, security, verification, password reset, and transactional emails.'
const UNSUBSCRIBE_MISSING_MESSAGE = 'This unsubscribe link is missing or invalid. Your preferences were not changed.'
const UNSUBSCRIBE_FAILURE_MESSAGE = 'Unable to update your promotional email preference right now. Please try again later.'
const DEFAULT_LOGIN_NEXT_ROUTE = '/auth/dashboard'
const SAFE_AUTH_NEXT_ROUTES = new Set(['/auth/dashboard', '/auth/status'])
const LOGIN_REQUIRED_MESSAGE = 'Session expired or signed out. Please log in.'
const DESKTOP_CALLBACK_URL = 'saiia://auth/callback'
const PENDING_SIGNUP_CONSENT_STORAGE_KEY = 'intervuai.pendingSignupConsent'
const SIGNUP_CONSENT_VERSION = 'c10.6a-v1'
const CONSENT_FEATURE_ENABLED = String(import.meta.env?.VITE_CONSENT_FEATURE_ENABLED || '').toLowerCase() === 'true'
const CONSENT_SETUP_UNAVAILABLE = 'Signup is temporarily unavailable while account consent setup is prepared. Please try again later.'
const DESKTOP_STATE_PATTERN = /^[A-Za-z0-9._~-]{16,256}$/
const MAX_RESUME_FILE_BYTES = 5 * 1024 * 1024
const SUPPORTED_RESUME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
])
const SUPPORTED_RESUME_EXTENSIONS = new Set(['.pdf', '.docx', '.txt'])
const CLOUD_PROFILE_FIELDS = [
  ['full_name', 'Full name', 'input'],
  ['email', 'Email', 'input'],
  ['phone', 'Phone', 'input'],
  ['location', 'Location', 'input'],
  ['current_title', 'Current title', 'input'],
  ['target_role', 'Target role', 'input'],
  ['professional_summary', 'Professional summary', 'textarea'],
  ['education', 'Education', 'textarea'],
  ['degree', 'Degree', 'input'],
  ['branch', 'Branch', 'input'],
  ['college', 'College / university', 'input'],
  ['graduation_year', 'Graduation year', 'input'],
  ['top_skills', 'Top skills', 'textarea'],
  ['technical_skills', 'Technical skills', 'textarea'],
  ['tools_frameworks', 'Tools / frameworks', 'textarea'],
  ['projects', 'Projects', 'textarea'],
  ['experience', 'Experience', 'textarea'],
  ['certifications', 'Certifications', 'textarea'],
  ['achievements', 'Achievements', 'textarea'],
]


function buildSignupConsent(email, marketingEmailOptIn) {
  return {
    email: String(email || '').trim().toLowerCase(),
    consent: {
      terms_accepted: true,
      privacy_accepted: true,
      marketing_email_opt_in: marketingEmailOptIn,
      consent_source: 'signup',
      consent_version: SIGNUP_CONSENT_VERSION,
    },
  }
}


function rememberSignupConsent(email, marketingEmailOptIn) {
  try {
    window.localStorage.setItem(
      PENDING_SIGNUP_CONSENT_STORAGE_KEY,
      JSON.stringify(buildSignupConsent(email, marketingEmailOptIn)),
    )
    return true
  } catch {
    return false
  }
}


function pendingSignupConsentForSession(session) {
  const sessionEmail = String(session?.user?.email || '').trim().toLowerCase()
  if (!sessionEmail) {
    return null
  }
  try {
    const record = JSON.parse(window.localStorage.getItem(PENDING_SIGNUP_CONSENT_STORAGE_KEY) || 'null')
    if (record?.email !== sessionEmail || !record?.consent) {
      return null
    }
    return record.consent
  } catch {
    return null
  }
}


function clearPendingSignupConsent() {
  try {
    window.localStorage.removeItem(PENDING_SIGNUP_CONSENT_STORAGE_KEY)
  } catch {
    // There is no sensitive session data in this best-effort local marker.
  }
}


function getSafeAuthNextRoute(value, fallback = DEFAULT_LOGIN_NEXT_ROUTE) {
  const route = String(value || '').trim()
  return SAFE_AUTH_NEXT_ROUTES.has(route) ? route : fallback
}


function getSafeDesktopState(value) {
  const state = String(value || '').trim()
  return DESKTOP_STATE_PATTERN.test(state) ? state : ''
}


function desktopLoginRoute(state) {
  return `/auth/desktop-login?state=${encodeURIComponent(state)}`
}


function desktopSignupRoute(state) {
  return `/auth/signup?desktop_state=${encodeURIComponent(state)}`
}


async function openDesktopHandoff(session, state, backendUrl) {
  if (!session?.access_token || !session?.refresh_token || !state) {
    throw new Error('Desktop login could not be completed.')
  }
  const handoff = await createDesktopHandoff(session.access_token, session.refresh_token, state, { backendUrl })
  const handoffCode = String(handoff?.handoff_code || '').trim()
  if (!handoffCode) {
    throw new Error('Desktop login could not be completed.')
  }
  const callbackUrl = new URL(DESKTOP_CALLBACK_URL)
  callbackUrl.searchParams.set('handoff_code', handoffCode)
  callbackUrl.searchParams.set('state', state)
  window.location.href = callbackUrl.toString()
}


function useRedirectAuthenticatedUser(targetRoute = DEFAULT_LOGIN_NEXT_ROUTE) {
  const navigate = useNavigate()
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    let ignore = false

    async function checkSession() {
      if (!supabase) {
        setCheckingSession(false)
        return
      }

      try {
        const { data } = await supabase.auth.getSession()
        if (ignore) {
          return
        }
        if (data.session?.access_token) {
          if (targetRoute) {
            navigate(targetRoute, { replace: true })
          }
          setCheckingSession(false)
          return
        }
      } catch {
        // Stay on the public auth form. The explicit login/signup action will surface errors.
      }

      if (!ignore) {
        setCheckingSession(false)
      }
    }

    checkSession()
    return () => {
      ignore = true
    }
  }, [navigate, targetRoute])

  return checkingSession
}


function useProfileBootstrap({ backendUrl, sessionErrorMessage, disabled = false }) {
  const [bootstrapResult, setBootstrapResult] = useState(null)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [error, setError] = useState('')
  const bootstrapOperationRef = useRef(0)

  useEffect(() => {
    return () => {
      bootstrapOperationRef.current += 1
    }
  }, [])

  async function handleBootstrapProfile() {
    if (bootstrapLoading || disabled) {
      return
    }

    const operationId = bootstrapOperationRef.current + 1
    bootstrapOperationRef.current = operationId
    setBootstrapLoading(true)
    setError('')

    try {
      if (!supabase) {
        if (bootstrapOperationRef.current === operationId) {
          setError('Supabase auth is not configured for this build.')
        }
        return
      }

      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        if (bootstrapOperationRef.current === operationId) {
          setError(sessionErrorMessage)
        }
        return
      }

      const pendingConsent = CONSENT_FEATURE_ENABLED
        ? pendingSignupConsentForSession(data.session)
        : null
      const bootstrapOptions = { backendUrl }
      if (pendingConsent) {
        bootstrapOptions.consent = pendingConsent
      }
      const result = await bootstrapProfile(data.session.access_token, bootstrapOptions)
      if (bootstrapOperationRef.current === operationId) {
        setBootstrapResult(result)
        if (pendingConsent) {
          clearPendingSignupConsent()
        }
      }
    } catch (bootstrapError) {
      if (bootstrapOperationRef.current === operationId) {
        setError(bootstrapError.message)
      }
    } finally {
      if (bootstrapOperationRef.current === operationId) {
        setBootstrapLoading(false)
      }
    }
  }

  function invalidateBootstrap() {
    bootstrapOperationRef.current += 1
    setBootstrapLoading(false)
    setBootstrapResult(null)
    setError('')
  }

  return {
    bootstrapResult,
    bootstrapLoading,
    error,
    handleBootstrapProfile,
    invalidateBootstrap,
  }
}


function getAuthRedirectUrl(desktopState = '') {
  const safeDesktopState = getSafeDesktopState(desktopState)
  return safeDesktopState ? `${window.location.origin}${desktopLoginRoute(safeDesktopState)}` : AUTH_CALLBACK_URL
}


async function startGoogleLogin(desktopState = '') {
  if (!supabase) {
    return { error: new Error('Supabase auth is not configured for this build.') }
  }
  return supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: getAuthRedirectUrl(desktopState),
    },
  })
}


function AuthShell({ title, children }) {
  return (
    <main className="auth-page">
      <section className="auth-panel">
        <h1>{title}</h1>
        {children}
      </section>
    </main>
  )
}


function ConfigNotice() {
  if (supabase) {
    return null
  }

  return (
    <p className="auth-message error">
      Supabase auth is not configured for this build.
    </p>
  )
}


function AuthMessage({ message, tone = 'info' }) {
  if (!message) {
    return null
  }

  return <p className={`auth-message ${tone}`}>{message}</p>
}


function PasswordInput({
  value,
  onChange,
  autoComplete,
  minLength,
  required = true,
}) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="auth-password-field">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        minLength={minLength}
        required={required}
      />
      <button
        type="button"
        className="auth-password-toggle"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        title={visible ? 'Hide password' : 'Show password'}
      >
        {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
      </button>
    </div>
  )
}


function AuthLinks({ mode, desktopState = '' }) {
  const safeDesktopState = getSafeDesktopState(desktopState)
  return (
    <nav className="auth-links" aria-label="Auth navigation">
      {mode !== 'login' && <Link to={safeDesktopState ? desktopLoginRoute(safeDesktopState) : '/auth/login'}>Login</Link>}
      {mode !== 'signup' && <Link to={safeDesktopState ? desktopSignupRoute(safeDesktopState) : '/auth/signup'}>Sign up</Link>}
      {mode !== 'forgot' && <Link to="/auth/forgot-password">Forgot password</Link>}
      <Link to="/auth/dashboard">Dashboard</Link>
      <Link to="/auth/resume">Cloud resume</Link>
      <Link to="/">Desktop app</Link>
    </nav>
  )
}


function normalizeCloudProfile(profile = {}) {
  return Object.fromEntries(
    CLOUD_PROFILE_FIELDS.map(([field]) => [field, String(profile[field] || '')]),
  )
}


function formatSessionTime(value) {
  const text = String(value || '').trim()
  if (!text) {
    return 'In progress'
  }
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? text : parsed.toLocaleString()
}


function formatSessionContextLine(session) {
  const role = session?.target_role || 'No target role'
  const company = session?.company_name || 'No company'
  return `${role} · ${company}`
}


function formatTranscriptMetaLine(entry) {
  const parts = []
  if (entry?.source) {
    parts.push(`Source: ${entry.source}`)
  }
  if (entry?.category) {
    parts.push(`Category: ${entry.category}`)
  }
  parts.push(`Created: ${formatSessionTime(entry?.created_at)}`)
  return parts.join(' · ')
}


function triggerTextDownload(filename, content, format) {
  const blob = new Blob([content], {
    type: format === 'md' ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8',
  })
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}


function formatSessionDisplayContextLine(session) {
  const role = session?.target_role || 'No target role'
  const company = session?.company_name || 'No company'
  return [role, company].join(' - ')
}


function formatTranscriptDisplayMetaLine(entry) {
  const parts = []
  if (entry?.source) {
    parts.push(`Source: ${entry.source}`)
  }
  if (entry?.category) {
    parts.push(`Category: ${entry.category}`)
  }
  parts.push(`Created: ${formatSessionTime(entry?.created_at)}`)
  return parts.join(' - ')
}


function formatInterviewNotesMetaLine(notes) {
  const parts = []
  if (notes?.provider) {
    parts.push(`Provider: ${notes.provider}`)
  }
  if (notes?.model) {
    parts.push(`Model: ${notes.model}`)
  }
  parts.push(`Entries: ${notes?.transcript_entry_count || 0}`)
  if (notes?.generated_at) {
    parts.push(`Generated: ${formatSessionTime(notes.generated_at)}`)
  }
  return parts.join(' - ')
}


const INTERVIEW_NOTES_SECTIONS = [
  ['summary', 'Summary'],
  ['technical_topics', 'Topics Covered'],
  ['key_questions', 'Key Questions Asked'],
  ['strengths', 'Strong Points'],
  ['improvement_areas', 'Areas to Improve'],
  ['suggested_followups', 'Suggested Follow-up Practice'],
]


const ASK_AI_CONTEXT_MISSING_ERROR = 'This session does not have transcript or AI notes context yet.'
const ASK_AI_CONTEXT_MISSING_MESSAGE = 'This session does not have transcript or AI notes context yet. Record interview questions first, then come back to Ask AI.'


function isAskAIContextMissingError(message) {
  const text = String(message || '')
  return text === ASK_AI_CONTEXT_MISSING_ERROR || text === ASK_AI_CONTEXT_MISSING_MESSAGE
}


function cleanNotesMarkdownLine(line) {
  return String(line || '')
    .replace(/^\s{0,3}#{1,6}\s*/, '')
    .replace(/^\s*[-*+]\s+/, '')
    .replace(/^\s*\d+\.\s+/, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .trim()
}


function getNotesMarkdownFallbackItems(notes) {
  return String(notes?.notes_markdown || '')
    .split(/\r?\n/)
    .map(cleanNotesMarkdownLine)
    .filter((line) => line && !/^interview notes$/i.test(line))
}


function getStructuredNotesSections(notes) {
  if (!notes) {
    return []
  }
  const sections = INTERVIEW_NOTES_SECTIONS.map(([key, title]) => {
    const value = notes[key]
    const items = Array.isArray(value)
      ? value.map((item) => String(item || '').trim()).filter(Boolean)
      : [String(value || '').trim()].filter(Boolean)
    return { key, title, items }
  }).filter((section) => section.items.length)

  if (sections.length) {
    return sections
  }
  const fallbackItems = getNotesMarkdownFallbackItems(notes)
  return fallbackItems.length ? [{ key: 'notes_markdown', title: 'Overall Feedback', items: fallbackItems }] : []
}


function formatAskAIMessageMetaLine(message) {
  const parts = [`Turn: ${message?.turn_index || 0}`]
  if (message?.provider) {
    parts.push(`Provider: ${message.provider}`)
  }
  if (message?.model) {
    parts.push(`Model: ${message.model}`)
  }
  parts.push(`Created: ${formatSessionTime(message?.created_at)}`)
  return parts.join(' - ')
}


function validateCloudResumeFile(file) {
  if (!file) {
    return 'Choose a resume file first.'
  }
  const lowerName = String(file.name || '').toLowerCase()
  const extension = lowerName.slice(lowerName.lastIndexOf('.'))
  if (!SUPPORTED_RESUME_EXTENSIONS.has(extension)) {
    return 'Upload a PDF, DOCX, or TXT resume.'
  }
  if (file.type && file.type !== 'application/octet-stream' && !SUPPORTED_RESUME_TYPES.has(file.type)) {
    return 'The selected file type does not match PDF, DOCX, or TXT.'
  }
  if (!file.size) {
    return 'The selected resume file is empty.'
  }
  if (file.size > MAX_RESUME_FILE_BYTES) {
    return 'Upload a resume under 5 MB.'
  }
  return ''
}


function useAuthForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  return {
    email,
    password,
    loading,
    message,
    error,
    setEmail,
    setPassword,
    setLoading,
    setMessage,
    setError,
  }
}


export function AuthSignupPage({ backendUrl, desktopState = '' }) {
  const form = useAuthForm()
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [marketingEmailOptIn, setMarketingEmailOptIn] = useState(null)
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeDesktopState = getSafeDesktopState(desktopState || searchParams.get('desktop_state'))
  const safeNextRoute = safeDesktopState
    ? desktopLoginRoute(safeDesktopState)
    : getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const checkingSession = useRedirectAuthenticatedUser(safeNextRoute)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      return
    }
    if (!termsAccepted) {
      form.setError('You must agree to the Terms & Conditions and Privacy Policy before signing up.')
      return
    }
    if (!CONSENT_FEATURE_ENABLED) {
      form.setError(CONSENT_SETUP_UNAVAILABLE)
      return
    }

    form.setLoading(true)
    form.setError('')
    form.setMessage('')
    const consent = buildSignupConsent(form.email, marketingEmailOptIn)
    rememberSignupConsent(form.email, marketingEmailOptIn)
    const { data, error } = await supabase.auth.signUp({
      email: form.email,
      password: form.password,
      options: {
        emailRedirectTo: getAuthRedirectUrl(safeDesktopState),
        data: consent.consent,
      },
    })

    if (error) {
      form.setLoading(false)
      form.setError(error.message)
      return
    }
    if (data.session) {
      try {
        await bootstrapProfile(data.session.access_token, { backendUrl, consent: consent.consent })
        clearPendingSignupConsent()
        if (safeDesktopState) {
          await openDesktopHandoff(data.session, safeDesktopState, backendUrl)
          form.setMessage('Login successful. You can return to intervuAI.')
        } else {
          form.setMessage('Account created. Your consent preferences were saved.')
        }
      } catch (signupSetupError) {
        form.setError(signupSetupError?.message || 'Account setup could not be completed. Please sign in again.')
      } finally {
        form.setLoading(false)
      }
      return
    }

    form.setLoading(false)

    form.setMessage('Check your email to verify your account.')
  }

  async function handleGoogleLogin() {
    form.setError('')
    if (!termsAccepted) {
      form.setError('You must agree to the Terms & Conditions and Privacy Policy before signing up.')
      return
    }
    if (!CONSENT_FEATURE_ENABLED) {
      form.setError(CONSENT_SETUP_UNAVAILABLE)
      return
    }
    if (!rememberSignupConsent(form.email, marketingEmailOptIn)) {
      form.setError('Unable to save signup preferences. Please try again.')
      return
    }
    try {
      const { error } = await startGoogleLogin(safeDesktopState)
      if (error) {
        form.setError(error.message || 'Google login could not be started.')
      }
    } catch {
      form.setError('Google login could not be started.')
    }
  }

  if (checkingSession) {
    return (
      <AuthShell title="Create Account">
        <p className="auth-message info">Checking session...</p>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Create Account">
      <ConfigNotice />
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(event) => form.setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Password
          <PasswordInput
            value={form.password}
            onChange={(event) => form.setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
        </label>
        <label className="auth-consent-row">
          <input
            type="checkbox"
            checked={termsAccepted}
            onChange={(event) => setTermsAccepted(event.target.checked)}
            required
          />
          <span>
            I agree to the <a href="/terms">Terms &amp; Conditions</a> and <a href="/privacy">Privacy Policy</a>.
          </span>
        </label>
        <label className="auth-consent-row">
          <input
            type="checkbox"
            checked={marketingEmailOptIn === true}
            onChange={(event) => setMarketingEmailOptIn(event.target.checked)}
          />
          <span>I want to receive promotional, discount, and product emails.</span>
        </label>
        <button type="submit" disabled={!supabase || form.loading}>
          {form.loading ? 'Creating...' : 'Sign Up'}
        </button>
      </form>
      <button className="auth-secondary-button" type="button" onClick={handleGoogleLogin} disabled={!supabase || form.loading}>
        Continue with Google
      </button>
      <AuthMessage message={form.error} tone="error" />
      <AuthMessage message={form.message} tone="success" />
      <AuthLinks mode="signup" desktopState={safeDesktopState} />
    </AuthShell>
  )
}


export function AuthLoginPage({ backendUrl, desktopState = '', desktopError = '' }) {
  const form = useAuthForm()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeDesktopState = getSafeDesktopState(desktopState)
  const safeNextRoute = getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const checkingSession = useRedirectAuthenticatedUser(safeDesktopState ? '' : safeNextRoute)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      return
    }

    form.setLoading(true)
    form.setError('')
    form.setMessage('')
    const { data, error } = await supabase.auth.signInWithPassword({
      email: form.email,
      password: form.password,
    })

    if (error) {
      form.setLoading(false)
      form.setError(error.message)
      return
    }

    try {
      if (safeDesktopState) {
        await openDesktopHandoff(data.session, safeDesktopState, backendUrl)
        form.setMessage('Login successful. You can return to intervuAI.')
        return
      }
      if (data.session?.access_token) {
        await fetchCurrentUser(data.session.access_token, { backendUrl })
      }
      form.setMessage('Login successful.')
      navigate(safeNextRoute, { replace: true })
    } catch (verifyError) {
      form.setError(verifyError.message)
    } finally {
      form.setLoading(false)
    }
  }

  async function handleGoogleLogin() {
    form.setError('')
    try {
      const { error } = await startGoogleLogin(safeDesktopState)
      if (error) {
        form.setError(error.message || 'Google login could not be started.')
      }
    } catch {
      form.setError('Google login could not be started.')
    }
  }

  if (checkingSession) {
    return (
      <AuthShell title="Login">
        <p className="auth-message info">Checking session...</p>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Login">
      <ConfigNotice />
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(event) => form.setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Password
          <PasswordInput
            value={form.password}
            onChange={(event) => form.setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <button type="submit" disabled={!supabase || form.loading}>
          {form.loading ? 'Checking...' : 'Login'}
        </button>
      </form>
      <button className="auth-secondary-button" type="button" onClick={handleGoogleLogin} disabled={!supabase || form.loading}>
        Continue with Google
      </button>
      <AuthMessage message={location.state?.authMessage || ''} tone="info" />
      <AuthMessage message={desktopError} tone="error" />
      <AuthMessage message={form.error} tone="error" />
      <AuthMessage message={form.message} tone="success" />
      <AuthLinks mode="login" desktopState={safeDesktopState} />
    </AuthShell>
  )
}


export function AuthDesktopLoginPage({ backendUrl }) {
  const [searchParams] = useSearchParams()
  const state = getSafeDesktopState(searchParams.get('state'))
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false

    async function continueDesktopLogin() {
      if (!state || !supabase) {
        setChecking(false)
        return
      }
      try {
        const { data } = await supabase.auth.getSession()
        if (ignore) {
          return
        }
        if (data.session?.access_token && data.session?.refresh_token) {
          await openDesktopHandoff(data.session, state, backendUrl)
          if (!ignore) {
            setError('')
          }
          return
        }
      } catch {
        if (!ignore) {
          setError('Desktop login could not be completed. Try logging in again.')
        }
      }
      if (!ignore) {
        setChecking(false)
      }
    }

    continueDesktopLogin()
    return () => {
      ignore = true
    }
  }, [backendUrl, state])

  if (!state) {
    return (
      <AuthShell title="Desktop Login">
        <AuthMessage message="Invalid desktop login request. Start again from the desktop app." tone="error" />
        <AuthLinks />
      </AuthShell>
    )
  }

  if (checking) {
    return (
      <AuthShell title="Desktop Login">
        <p className="auth-message info">Checking session...</p>
      </AuthShell>
    )
  }

  return (
    <>
      <AuthLoginPage backendUrl={backendUrl} desktopState={state} desktopError={error} />
    </>
  )
}


export function AuthForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      return
    }

    setLoading(true)
    setError('')
    setMessage('')
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: PASSWORD_RESET_URL,
    })
    setLoading(false)

    if (resetError) {
      setError(resetError.message)
      return
    }

    setMessage('If that account exists, a reset link will be sent.')
  }

  return (
    <AuthShell title="Reset Password">
      <ConfigNotice />
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <button type="submit" disabled={!supabase || loading}>
          {loading ? 'Sending...' : 'Send Reset Link'}
        </button>
      </form>
      <AuthMessage message={error} tone="error" />
      <AuthMessage message={message} tone="success" />
      <AuthLinks mode="forgot" />
    </AuthShell>
  )
}


export function AuthResetPasswordPage() {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      return
    }

    setLoading(true)
    setError('')
    setMessage('')
    const { error: updateError } = await supabase.auth.updateUser({ password })
    setLoading(false)

    if (updateError) {
      setError(updateError.message)
      return
    }

    setMessage('Password updated. You can login now.')
  }

  return (
    <AuthShell title="New Password">
      <ConfigNotice />
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          Password
          <PasswordInput
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
        </label>
        <button type="submit" disabled={!supabase || loading}>
          {loading ? 'Updating...' : 'Update Password'}
        </button>
      </form>
      <AuthMessage message={error} tone="error" />
      <AuthMessage message={message} tone="success" />
      <AuthLinks />
    </AuthShell>
  )
}


export function AuthCallbackPage({ backendUrl }) {
  const [status, setStatus] = useState('Finishing sign in...')
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false

    async function finishCallback() {
      if (!supabase) {
        setStatus('Supabase auth is not configured for this build.')
        return
      }

      const { data, error: sessionError } = await supabase.auth.getSession()
      if (ignore) {
        return
      }

      if (sessionError || !data.session?.access_token) {
        setError(sessionError?.message || 'No active auth session was found.')
        setStatus('')
        return
      }

      try {
        const user = await fetchCurrentUser(data.session.access_token, { backendUrl })
        if (!ignore) {
          setStatus(`Signed in as ${user.email || user.user_id}.`)
        }
      } catch (verifyError) {
        if (!ignore) {
          setError(verifyError.message)
          setStatus('')
        }
      }
    }

    finishCallback()
    return () => {
      ignore = true
    }
  }, [backendUrl])

  return (
    <AuthShell title="Auth Status">
      <AuthMessage message={error} tone="error" />
      <AuthMessage message={status} tone={error ? 'error' : 'success'} />
      <AuthLinks />
    </AuthShell>
  )
}


export function AuthUnsubscribePage({ backendUrl }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')?.trim() || ''
  const [state, setState] = useState(token ? 'loading' : 'missing')
  const [message, setMessage] = useState(token ? '' : UNSUBSCRIBE_MISSING_MESSAGE)

  useEffect(() => {
    const cleanUrl = new URL(window.location.href)
    if (cleanUrl.searchParams.has('token')) {
      cleanUrl.searchParams.delete('token')
      window.history.replaceState(
        window.history.state,
        document.title,
        `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`,
      )
    }

    let ignore = false
    if (!token) {
      return () => {
        ignore = true
      }
    }

    async function submit() {
      try {
        await submitMarketingUnsubscribe(token, { backendUrl })
        if (!ignore) {
          setState('success')
          setMessage(UNSUBSCRIBE_CONFIRMATION)
        }
      } catch {
        if (!ignore) {
          setState('error')
          setMessage(UNSUBSCRIBE_FAILURE_MESSAGE)
        }
      }
    }

    submit()
    return () => {
      ignore = true
    }
  }, [backendUrl, token])

  return (
    <AuthShell title="Email preferences">
      <AuthMessage message={message} tone={state === 'error' ? 'error' : 'success'} />
      <p className="auth-unsubscribe-copy">{UNSUBSCRIBE_TRANSACTIONAL_NOTICE}</p>
      <AuthLinks />
    </AuthShell>
  )
}


export function AuthStatusPage({ backendUrl }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [userError, setUserError] = useState('')
  const [logoutPending, setLogoutPending] = useState(false)
  const navigate = useNavigate()
  const {
    bootstrapResult,
    bootstrapLoading,
    error: bootstrapError,
    handleBootstrapProfile,
    invalidateBootstrap,
  } = useProfileBootstrap({
    backendUrl,
    sessionErrorMessage: 'No active auth session was found.',
    disabled: logoutPending,
  })
  const profileBootstrapDisabled = bootstrapLoading || logoutPending

  useEffect(() => {
    let ignore = false

    async function loadUser() {
      if (!supabase) {
        setUserError('Supabase auth is not configured for this build.')
        setLoading(false)
        return
      }

      const { data, error: sessionError } = await supabase.auth.getSession()
      if (ignore) {
        return
      }

      if (sessionError || !data.session?.access_token) {
        setUserError(sessionError?.message || 'No active auth session was found.')
        setLoading(false)
        return
      }

      try {
        const currentUser = await fetchCurrentUser(data.session.access_token, { backendUrl })
        if (!ignore) {
          setUser(currentUser)
        }
      } catch (verifyError) {
        if (!ignore) {
          setUserError(verifyError.message)
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    loadUser()
    return () => {
      ignore = true
    }
  }, [backendUrl])

  async function handleLogout() {
    if (!supabase || logoutPending) {
      return
    }
    setLogoutPending(true)
    setLoading(true)
    setUserError('')
    try {
      const { error: signOutError } = await supabase.auth.signOut()
      if (signOutError) {
        setUserError('Sign out failed. Please try again.')
        setLoading(false)
        setLogoutPending(false)
        return
      }

      invalidateBootstrap()
      setUser(null)
      navigate('/auth/login', {
        replace: true,
        state: { authMessage: 'Signed out.' },
      })
    } catch {
      setUserError('Sign out failed. Please try again.')
      setLoading(false)
      setLogoutPending(false)
    }
  }

  return (
    <AuthShell title="Account">
      {loading && <p className="auth-message info">Loading...</p>}
      <AuthMessage message={userError || bootstrapError} tone="error" />
      {user && (
        <div className="auth-user-summary">
          <p>{user.email || user.user_id}</p>
          {user.role && <span>{user.role}</span>}
        </div>
      )}
      {user && (
        <button
          className="auth-secondary-button"
          type="button"
          onClick={() => {
            if (!profileBootstrapDisabled) {
              handleBootstrapProfile()
            }
          }}
          disabled={bootstrapLoading || logoutPending}
        >
          {bootstrapLoading ? 'Preparing...' : 'Prepare Profile'}
        </button>
      )}
      {bootstrapResult && (
        <div className="auth-user-summary">
          <p>Profile ready</p>
          <span>
            profile {bootstrapResult.profile_created ? 'created' : 'found'} - settings {bootstrapResult.settings_created ? 'created' : 'found'}
          </span>
        </div>
      )}
      <button className="auth-secondary-button" type="button" onClick={handleLogout} disabled={!supabase || loading || logoutPending}>
        <LogOut size={18} aria-hidden="true" />
        {logoutPending ? 'Signing out...' : 'Logout'}
      </button>
      <AuthLinks />
    </AuthShell>
  )
}


function RequireAuth({ backendUrl, children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [signedOut, setSignedOut] = useState(false)
  const [error, setError] = useState('')
  const location = useLocation()

  useEffect(() => {
    let ignore = false

    async function loadUser() {
      if (!supabase) {
        setError('Supabase auth is not configured for this build.')
        setLoading(false)
        return
      }

      const { data, error: sessionError } = await supabase.auth.getSession()
      if (ignore) {
        return
      }

      if (sessionError || !data.session?.access_token) {
        setSignedOut(true)
        setLoading(false)
        return
      }

      try {
        const currentUser = await fetchCurrentUser(data.session.access_token, { backendUrl })
        if (!ignore) {
          setUser(currentUser)
        }
      } catch (verifyError) {
        if (!ignore) {
          setError(verifyError.message)
          setSignedOut(true)
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    loadUser()
    return () => {
      ignore = true
    }
  }, [backendUrl])

  if (loading) {
    return (
      <AuthShell title="Account">
        <p className="auth-message info">Checking session...</p>
      </AuthShell>
    )
  }

  if (signedOut) {
    const nextRoute = getSafeAuthNextRoute(location.pathname)
    return (
      <Navigate
        to={`/auth/login?next=${encodeURIComponent(nextRoute)}`}
        replace
        state={{ authMessage: LOGIN_REQUIRED_MESSAGE, next: nextRoute }}
      />
    )
  }

  if (error) {
    return (
      <AuthShell title="Account">
        <AuthMessage message={error} tone="error" />
        <AuthLinks />
      </AuthShell>
    )
  }

  return children(user)
}


export function AuthDashboardPage({ backendUrl }) {
  const [logoutPending, setLogoutPending] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const [sessionHistory, setSessionHistory] = useState([])
  const [sessionHistoryLoading, setSessionHistoryLoading] = useState(true)
  const [sessionHistoryError, setSessionHistoryError] = useState('')
  const [openTranscriptSessionId, setOpenTranscriptSessionId] = useState('')
  const [transcriptEntries, setTranscriptEntries] = useState([])
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [transcriptError, setTranscriptError] = useState('')
  const [transcriptDownloadKey, setTranscriptDownloadKey] = useState('')
  const [openNotesSessionId, setOpenNotesSessionId] = useState('')
  const [sessionNotes, setSessionNotes] = useState(null)
  const [notesLoading, setNotesLoading] = useState(false)
  const [notesError, setNotesError] = useState('')
  const [notesGenerateKey, setNotesGenerateKey] = useState('')
  const [openAskAISessionId, setOpenAskAISessionId] = useState('')
  const [askAIMessages, setAskAIMessages] = useState([])
  const [askAIMessagesNextPage, setAskAIMessagesNextPage] = useState(null)
  const [askAIDrafts, setAskAIDrafts] = useState({})
  const [askAIRequestIds, setAskAIRequestIds] = useState({})
  const [askAILoading, setAskAILoading] = useState(false)
  const [askAIError, setAskAIError] = useState('')
  const askAIMessagesControllerRef = useRef(null)
  const askAISubmitControllerRef = useRef(null)
  const navigate = useNavigate()
  const {
    bootstrapResult,
    bootstrapLoading,
    error,
    handleBootstrapProfile,
    invalidateBootstrap,
  } = useProfileBootstrap({
    backendUrl,
    sessionErrorMessage: 'Session expired or signed out. Please log in again.',
    disabled: logoutPending,
  })

  function resetAskAIState() {
    askAIMessagesControllerRef.current?.abort()
    askAISubmitControllerRef.current?.abort()
    askAIMessagesControllerRef.current = null
    askAISubmitControllerRef.current = null
    setOpenAskAISessionId('')
    setAskAIMessages([])
    setAskAIMessagesNextPage(null)
    setAskAIError('')
    setAskAILoading(false)
  }

  useEffect(() => () => {
    resetAskAIState()
  }, [])
  const profileBootstrapDisabled = bootstrapLoading || logoutPending

  useEffect(() => {
    let ignore = false
    const controller = new AbortController()

    async function loadSessionHistory(signal = controller.signal) {
      setSessionHistoryLoading(true)
      setSessionHistoryError('')
      try {
        if (!supabase) {
          if (!ignore) {
            setSessionHistory([])
            setSessionHistoryError('Cloud session history is unavailable until auth is ready.')
          }
          return
        }
        const { data, error: sessionError } = await supabase.auth.getSession()
        if (ignore || sessionError || !data.session?.access_token) {
          if (!ignore) {
            setSessionHistory([])
            setSessionHistoryError('Could not verify your session history access. Please sign in again.')
          }
          return
        }
        const result = await fetchInterviewSessions(data.session.access_token, {
          backendUrl,
          limit: 20,
          page: 1,
          signal,
        })
        if (!ignore) {
          setSessionHistory(result.items)
          setOpenTranscriptSessionId('')
          setTranscriptEntries([])
          setTranscriptError('')
          setOpenNotesSessionId('')
          setSessionNotes(null)
          setNotesError('')
          resetAskAIState()
        }
      } catch {
        if (!ignore) {
          setSessionHistory([])
          setSessionHistoryError('Could not load interview sessions. Please try again.')
          setOpenTranscriptSessionId('')
          setTranscriptEntries([])
          setTranscriptError('')
          setOpenNotesSessionId('')
          setSessionNotes(null)
          setNotesError('')
          resetAskAIState()
        }
      } finally {
        if (!ignore) {
          setSessionHistoryLoading(false)
        }
      }
    }

    loadSessionHistory()
    return () => {
      ignore = true
      controller.abort()
    }
  }, [backendUrl])

  async function handleSessionHistoryRetry() {
    if (sessionHistoryLoading) {
      return
    }
    setSessionHistoryLoading(true)
    setSessionHistoryError('')
    try {
      if (!supabase) {
        setSessionHistory([])
        setSessionHistoryError('Cloud session history is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setSessionHistory([])
        setSessionHistoryError('Could not verify your session history access. Please sign in again.')
        return
      }
      const result = await fetchInterviewSessions(data.session.access_token, {
        backendUrl,
        limit: 20,
        page: 1,
      })
      setSessionHistory(result.items)
      setOpenTranscriptSessionId('')
      setTranscriptEntries([])
      setTranscriptError('')
      setOpenNotesSessionId('')
      setSessionNotes(null)
      setNotesError('')
      resetAskAIState()
    } catch {
      setSessionHistory([])
      setSessionHistoryError('Could not load interview sessions. Please try again.')
      setOpenTranscriptSessionId('')
      setTranscriptEntries([])
      setTranscriptError('')
      setOpenNotesSessionId('')
      setSessionNotes(null)
      setNotesError('')
      resetAskAIState()
    } finally {
      setSessionHistoryLoading(false)
    }
  }

  async function handleTranscriptToggle(sessionId) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId || transcriptLoading) {
      return
    }
    if (openTranscriptSessionId === normalizedSessionId) {
      setOpenTranscriptSessionId('')
      setTranscriptEntries([])
      setTranscriptError('')
      return
    }
    setTranscriptLoading(true)
    setTranscriptError('')
    try {
      if (!supabase) {
        setOpenTranscriptSessionId(normalizedSessionId)
        setTranscriptEntries([])
        setTranscriptError('Transcript access is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setOpenTranscriptSessionId(normalizedSessionId)
        setTranscriptEntries([])
        setTranscriptError('Could not verify transcript access. Please sign in again.')
        return
      }
      const result = await fetchInterviewTranscriptEntries(data.session.access_token, normalizedSessionId, {
        backendUrl,
        limit: 100,
        page: 1,
      })
      setOpenTranscriptSessionId(normalizedSessionId)
      setTranscriptEntries(result.items)
    } catch {
      setOpenTranscriptSessionId(normalizedSessionId)
      setTranscriptEntries([])
      setTranscriptError('Could not load transcript entries. Please try again.')
    } finally {
      setTranscriptLoading(false)
    }
  }

  async function handleTranscriptDownload(sessionId, format) {
    const normalizedSessionId = String(sessionId || '').trim()
    const normalizedFormat = String(format || '').trim().toLowerCase()
    if (!normalizedSessionId || !normalizedFormat || transcriptDownloadKey) {
      return
    }
    setTranscriptDownloadKey(`${normalizedSessionId}:${normalizedFormat}`)
    setTranscriptError('')
    try {
      if (!supabase) {
        setTranscriptError('Transcript download is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setTranscriptError('Could not verify transcript download access. Please sign in again.')
        return
      }
      const download = await downloadInterviewTranscript(data.session.access_token, normalizedSessionId, normalizedFormat, {
        backendUrl,
      })
      triggerTextDownload(download.filename, download.content, download.format)
    } catch {
      setTranscriptError('Could not download the transcript. Please try again.')
    } finally {
      setTranscriptDownloadKey('')
    }
  }

  async function handleNotesToggle(sessionId) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId || notesLoading) {
      return
    }
    if (openNotesSessionId === normalizedSessionId) {
      setOpenNotesSessionId('')
      setSessionNotes(null)
      setNotesError('')
      return
    }
    setOpenNotesSessionId(normalizedSessionId)
    setSessionNotes(null)
    setNotesError('')
    setNotesLoading(true)
    try {
      if (!supabase) {
        setNotesError('AI notes access is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setNotesError('Could not verify AI notes access. Please sign in again.')
        return
      }
      const result = await fetchInterviewSessionNotes(data.session.access_token, normalizedSessionId, {
        backendUrl,
      })
      setSessionNotes(result)
    } catch (loadError) {
      if (String(loadError?.message || '').includes('were not found')) {
        setNotesError('No AI notes yet. Generate AI Notes to create them.')
      } else {
        setNotesError('Could not load AI notes. Please try again.')
      }
    } finally {
      setNotesLoading(false)
    }
  }

  async function handleNotesGenerate(sessionId, forceRegenerate = false) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId || notesLoading || notesGenerateKey) {
      return
    }
    setNotesGenerateKey(normalizedSessionId)
    setOpenNotesSessionId(normalizedSessionId)
    setSessionNotes(null)
    setNotesError('')
    setNotesLoading(true)
    try {
      if (!supabase) {
        setNotesError('AI notes generation is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setNotesError('Could not verify AI notes generation access. Please sign in again.')
        return
      }
      const result = await generateInterviewSessionNotes(data.session.access_token, normalizedSessionId, {
        backendUrl,
        forceRegenerate,
      })
      setSessionNotes(result)
    } catch (generateError) {
      setNotesError(String(generateError?.message || '').trim() || 'Could not generate AI notes. Please try again.')
    } finally {
      setNotesLoading(false)
      setNotesGenerateKey('')
    }
  }

  async function handleAskAIToggle(sessionId, { reload = false } = {}) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId) {
      return
    }
    if (openAskAISessionId === normalizedSessionId && !reload) {
      resetAskAIState()
      return
    }
    resetAskAIState()
    const controller = new AbortController()
    askAIMessagesControllerRef.current = controller
    setOpenAskAISessionId(normalizedSessionId)
    setAskAIMessages([])
    setAskAIMessagesNextPage(null)
    setAskAIError('')
    setAskAILoading(true)
    try {
      if (!supabase) {
        setAskAIError('Ask AI is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setAskAIError('Could not verify Ask AI access. Please sign in again.')
        return
      }
      const result = await fetchInterviewAskAIMessages(data.session.access_token, normalizedSessionId, {
        backendUrl,
        limit: 50,
        page: 1,
        signal: controller.signal,
      })
      if (controller.signal.aborted || askAIMessagesControllerRef.current !== controller) {
        return
      }
      setAskAIMessages(result.items)
      setAskAIMessagesNextPage(result.next_page)
    } catch (loadError) {
      if (controller.signal.aborted || loadError?.name === 'AbortError') {
        return
      }
      setAskAIError('Could not load Ask AI messages. Please try again.')
    } finally {
      if (askAIMessagesControllerRef.current === controller) {
        askAIMessagesControllerRef.current = null
        setAskAILoading(false)
      }
    }
  }

  async function handleAskAILoadMore(sessionId) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId || askAILoading || !askAIMessagesNextPage) {
      return
    }
    askAIMessagesControllerRef.current?.abort()
    const controller = new AbortController()
    askAIMessagesControllerRef.current = controller
    setAskAIError('')
    setAskAILoading(true)
    try {
      if (!supabase) {
        setAskAIError('Ask AI is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setAskAIError('Could not verify Ask AI access. Please sign in again.')
        return
      }
      const result = await fetchInterviewAskAIMessages(data.session.access_token, normalizedSessionId, {
        backendUrl,
        limit: 50,
        page: askAIMessagesNextPage,
        signal: controller.signal,
      })
      if (controller.signal.aborted || askAIMessagesControllerRef.current !== controller || openAskAISessionId !== normalizedSessionId) {
        return
      }
      setAskAIMessages((current) => {
        const seen = new Set(current.map((message) => message.id))
        return [...current, ...result.items.filter((message) => !seen.has(message.id))]
      })
      setAskAIMessagesNextPage(result.next_page)
    } catch (loadError) {
      if (controller.signal.aborted || loadError?.name === 'AbortError') {
        return
      }
      setAskAIError('Could not load Ask AI messages. Please try again.')
    } finally {
      if (askAIMessagesControllerRef.current === controller) {
        askAIMessagesControllerRef.current = null
        setAskAILoading(false)
      }
    }
  }

  async function handleAskAISubmit(event, sessionId) {
    event.preventDefault()
    const normalizedSessionId = String(sessionId || '').trim()
    const question = String(askAIDrafts[normalizedSessionId] || '').trim()
    if (!normalizedSessionId || !question || askAILoading) {
      return
    }
    askAISubmitControllerRef.current?.abort()
    const controller = new AbortController()
    askAISubmitControllerRef.current = controller
    const requestState = askAIRequestIds[normalizedSessionId]
    const requestId = requestState?.question === question
      ? requestState.requestId
      : `ask-ai-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    setAskAIRequestIds((current) => ({
      ...current,
      [normalizedSessionId]: { question, requestId },
    }))
    setOpenAskAISessionId(normalizedSessionId)
    setAskAIError('')
    setAskAILoading(true)
    try {
      if (!supabase) {
        setAskAIError('Ask AI is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !data.session?.access_token) {
        setAskAIError('Could not verify Ask AI access. Please sign in again.')
        return
      }
      const result = await askInterviewSessionAI(data.session.access_token, normalizedSessionId, question, {
        backendUrl,
        requestId,
        includeNotes: true,
        signal: controller.signal,
      })
      if (controller.signal.aborted || askAISubmitControllerRef.current !== controller || openAskAISessionId !== normalizedSessionId) {
        return
      }
      setAskAIMessages((current) => [
        ...current,
        result.user_message,
        result.assistant_message,
      ].filter(Boolean))
      setAskAIDrafts((current) => ({
        ...current,
        [normalizedSessionId]: '',
      }))
      setAskAIRequestIds((current) => {
        const next = { ...current }
        delete next[normalizedSessionId]
        return next
      })
    } catch (askError) {
      if (controller.signal.aborted || askError?.name === 'AbortError' || askAISubmitControllerRef.current !== controller || openAskAISessionId !== normalizedSessionId) {
        return
      }
      const message = String(askError?.message || '').trim()
      if (isAskAIContextMissingError(message)) {
        setAskAIError(ASK_AI_CONTEXT_MISSING_MESSAGE)
        setAskAIDrafts((current) => ({
          ...current,
          [normalizedSessionId]: '',
        }))
      } else {
        setAskAIError(message || 'Could not ask AI about this session. Please try again.')
      }
    } finally {
      if (askAISubmitControllerRef.current === controller) {
        askAISubmitControllerRef.current = null
        setAskAILoading(false)
      }
    }
  }

  async function handleLogout() {
    if (!supabase || logoutPending) {
      return
    }
    setLogoutPending(true)
    setLogoutError('')
    try {
      const { error: signOutError } = await supabase.auth.signOut()
      if (signOutError) {
        setLogoutError('Sign out failed. Please try again.')
        setLogoutPending(false)
        return
      }

      invalidateBootstrap()
      navigate('/auth/login', {
        replace: true,
        state: { authMessage: 'Signed out.' },
      })
    } catch {
      setLogoutError('Sign out failed. Please try again.')
      setLogoutPending(false)
    }
  }

  return (
    <RequireAuth backendUrl={backendUrl}>
      {(user) => (
        <AuthShell title="Dashboard">
          <div className="auth-user-summary">
            <p>{user.email || user.user_id}</p>
            {user.role && <span>{user.role}</span>}
          </div>
          <AuthMessage message={logoutError || error} tone="error" />
          {bootstrapResult && (
            <div className="auth-user-summary">
              <p>Profile ready</p>
              <span>
                profile {bootstrapResult.profile_created ? 'created' : 'found'} - settings {bootstrapResult.settings_created ? 'created' : 'found'}
              </span>
            </div>
          )}
          <div className="auth-user-summary">
            <p>Interview sessions</p>
            <span>Basic cloud session history from C6.3.</span>
          </div>
          {sessionHistoryLoading ? (
            <p className="auth-message info">Loading interview sessions...</p>
          ) : sessionHistoryError ? (
            <div>
              <p className="auth-message error">{sessionHistoryError}</p>
              <button className="auth-secondary-button" type="button" onClick={handleSessionHistoryRetry}>
                Retry session history
              </button>
            </div>
          ) : sessionHistory.length ? (
            <div className="auth-session-history" aria-label="Interview session history">
              {sessionHistory.map((session) => (
                <article key={session.id} className="auth-session-history__item">
                  <strong className="auth-session-history__title">
                    {session.title || session.target_role || session.company_name || 'Untitled session'}
                  </strong>
                  <p className="auth-session-history__meta">{formatSessionDisplayContextLine(session)}</p>
                  {session.job_description_preview ? (
                    <p className="auth-session-history__line">Context: {session.job_description_preview}</p>
                  ) : null}
                  <p className="auth-session-history__line">Status: {session.status || 'unknown'}</p>
                  <p className="auth-session-history__line">Started: {formatSessionTime(session.started_at)}</p>
                  <p className="auth-session-history__line">
                    Ended: {session.ended_at ? formatSessionTime(session.ended_at) : 'Not ended yet'}
                  </p>
                  <div className="auth-session-history__actions">
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleTranscriptToggle(session.id)}
                      disabled={transcriptLoading && openTranscriptSessionId !== session.id}
                    >
                      {openTranscriptSessionId === session.id ? 'Hide transcript' : 'View transcript'}
                    </button>
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleNotesGenerate(session.id)}
                      disabled={Boolean(notesGenerateKey) || notesLoading}
                    >
                      {notesGenerateKey === session.id ? 'Generating AI Notes...' : 'Generate AI Notes'}
                    </button>
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleNotesToggle(session.id)}
                      disabled={notesLoading && openNotesSessionId !== session.id}
                    >
                      {openNotesSessionId === session.id ? 'Hide AI Notes' : 'View AI Notes'}
                    </button>
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleAskAIToggle(session.id)}
                      disabled={askAILoading && openAskAISessionId !== session.id}
                    >
                      {openAskAISessionId === session.id ? 'Hide Ask AI' : 'Ask AI'}
                    </button>
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleTranscriptDownload(session.id, 'txt')}
                      disabled={Boolean(transcriptDownloadKey)}
                    >
                      Download .txt
                    </button>
                    <button
                      className="auth-session-history__action"
                      type="button"
                      onClick={() => handleTranscriptDownload(session.id, 'md')}
                      disabled={Boolean(transcriptDownloadKey)}
                    >
                      Download .md
                    </button>
                  </div>
                  {openTranscriptSessionId === session.id ? (
                    <div className="auth-session-history__transcript">
                      {transcriptLoading ? (
                        <p className="auth-session-history__line">Loading transcript...</p>
                      ) : transcriptError ? (
                        <p className="auth-message error">{transcriptError}</p>
                      ) : transcriptEntries.length ? (
                        transcriptEntries.map((entry) => (
                          <section key={entry.id} className="auth-session-history__transcript-entry">
                            <p className="auth-session-history__line"><strong>Question:</strong> {entry.question_text}</p>
                            <p className="auth-session-history__line"><strong>Answer:</strong> {entry.answer_text}</p>
                            <p className="auth-session-history__meta">{formatTranscriptDisplayMetaLine(entry)}</p>
                          </section>
                        ))
                      ) : (
                        <p className="auth-session-history__line">No transcript entries yet.</p>
                      )}
                    </div>
                  ) : null}
                  {openNotesSessionId === session.id ? (
                    <div className="auth-session-history__notes">
                      {notesLoading ? (
                        <p className="auth-session-history__line">Loading AI notes...</p>
                      ) : notesError ? (
                        <div>
                          <p className="auth-message error">{notesError}</p>
                          <button
                            className="auth-session-history__action"
                            type="button"
                            onClick={() => handleNotesGenerate(session.id, true)}
                            disabled={Boolean(notesGenerateKey)}
                          >
                            Retry AI Notes
                          </button>
                        </div>
                      ) : sessionNotes ? (
                        <section className="auth-session-history__notes-card">
                          <p className="auth-session-history__meta">{formatInterviewNotesMetaLine(sessionNotes)}</p>
                          <div className="auth-session-history__notes-sections">
                            {getStructuredNotesSections(sessionNotes).map((section) => (
                              <section key={section.key} className="auth-session-history__notes-section">
                                <h4>{section.title}</h4>
                                {section.items.length === 1 && section.key === 'summary' ? (
                                  <p>{section.items[0]}</p>
                                ) : (
                                  <ul>
                                    {section.items.map((item, index) => (
                                      <li key={`${section.key}-${index}`}>{item}</li>
                                    ))}
                                  </ul>
                                )}
                              </section>
                            ))}
                          </div>
                          <button
                            className="auth-session-history__action"
                            type="button"
                            onClick={() => handleNotesGenerate(session.id, true)}
                            disabled={Boolean(notesGenerateKey)}
                          >
                            Regenerate AI Notes
                          </button>
                        </section>
                      ) : (
                        <p className="auth-session-history__line">No AI notes yet. Generate AI Notes to create them.</p>
                      )}
                    </div>
                  ) : null}
                  {openAskAISessionId === session.id ? (
                    <div className="auth-session-history__ask-ai">
                      {askAIError ? (
                        <div>
                          <p className="auth-message error">{askAIError}</p>
                          {!isAskAIContextMissingError(askAIError) ? (
                            <button
                              className="auth-session-history__action"
                              type="button"
                              onClick={() => handleAskAIToggle(session.id, { reload: true })}
                              disabled={askAILoading}
                            >
                              Retry Ask AI
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                      {askAILoading && !askAIMessages.length ? (
                        <p className="auth-session-history__line">Loading Ask AI...</p>
                      ) : null}
                      {askAIMessages.length ? (
                        <div className="auth-session-history__ask-ai-messages">
                          {askAIMessages.map((message) => (
                            <section key={message.id} className="auth-session-history__ask-ai-message">
                              <p className="auth-session-history__line"><strong>{message.role === 'user' ? 'You' : 'AI'}:</strong> {message.message_text}</p>
                              <p className="auth-session-history__meta">{formatAskAIMessageMetaLine(message)}</p>
                            </section>
                          ))}
                          {askAIMessagesNextPage ? (
                            <button
                              className="auth-session-history__action"
                              type="button"
                              onClick={() => handleAskAILoadMore(session.id)}
                              disabled={askAILoading}
                            >
                              {askAILoading ? 'Loading more messages...' : 'Load more messages'}
                            </button>
                          ) : null}
                        </div>
                      ) : !askAILoading && !askAIError ? (
                        <p className="auth-session-history__line">No Ask AI messages yet.</p>
                      ) : null}
                      {!isAskAIContextMissingError(askAIError) ? (
                        <form className="auth-session-history__ask-ai-form" onSubmit={(event) => handleAskAISubmit(event, session.id)}>
                          <label>
                            Ask about this session
                            <textarea
                              value={askAIDrafts[session.id] || ''}
                              onChange={(event) => {
                                setAskAIDrafts((current) => ({
                                  ...current,
                                  [session.id]: event.target.value,
                                }))
                                const value = event.target.value
                                setAskAIRequestIds((current) => {
                                  const requestState = current[session.id]
                                  if (!requestState || requestState.question === value.trim()) {
                                    return current
                                  }
                                  const next = { ...current }
                                  delete next[session.id]
                                  return next
                                })
                              }}
                              disabled={askAILoading}
                              spellCheck={false}
                              autoCorrect="off"
                              autoComplete="off"
                              placeholder="Ask what to improve, rewrite an answer, or practice follow-ups..."
                            />
                          </label>
                          <button
                            className="auth-session-history__action"
                            type="submit"
                            disabled={askAILoading || !String(askAIDrafts[session.id] || '').trim()}
                          >
                            {askAILoading ? 'Asking AI...' : 'Send Ask AI'}
                          </button>
                        </form>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="auth-message info">No interview sessions yet.</p>
          )}
          <button
            className="auth-secondary-button"
            type="button"
            onClick={() => {
              if (!profileBootstrapDisabled) {
                handleBootstrapProfile()
              }
            }}
            disabled={bootstrapLoading || logoutPending}
          >
            {bootstrapLoading ? 'Preparing...' : 'Prepare Profile'}
          </button>
          <button className="auth-secondary-button" type="button" onClick={handleLogout} disabled={!supabase || logoutPending}>
            <LogOut size={18} aria-hidden="true" />
            {logoutPending ? 'Signing out...' : 'Logout'}
          </button>
          <nav className="auth-links" aria-label="Account navigation">
            <Link to="/auth/status">Auth status</Link>
            <Link to="/auth/resume">Cloud resume</Link>
            <Link to="/">Desktop app</Link>
          </nav>
        </AuthShell>
      )}
    </RequireAuth>
  )
}


export function AuthResumePage({ backendUrl }) {
  const [file, setFile] = useState(null)
  const [currentResume, setCurrentResume] = useState(null)
  const [reviewCandidate, setReviewCandidate] = useState(null)
  const [resumeRecord, setResumeRecord] = useState(null)
  const [draftProfile, setDraftProfile] = useState(null)
  const [extractionAttempt, setExtractionAttempt] = useState(null)
  const [phase, setPhase] = useState('loading')
  const [confirmPending, setConfirmPending] = useState(false)
  const [deletePending, setDeletePending] = useState(false)
  const [rebuildPending, setRebuildPending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const confirmControllerRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    return () => {
      confirmControllerRef.current?.abort()
    }
  }, [])

  async function getSessionToken(sessionErrorMessage = 'Session expired or signed out. Please log in again.') {
    if (!supabase) {
      throw new Error('Supabase auth is not configured for this build.')
    }
    const { data, error: sessionError } = await supabase.auth.getSession()
    if (sessionError || !data.session?.access_token) {
      throw new Error(sessionErrorMessage)
    }
    return data.session.access_token
  }

  async function loadCloudResumeState(signal) {
    const token = await getSessionToken()
    const [current, candidate] = await Promise.all([
      fetchCurrentCloudResume(token, { backendUrl, signal }),
      fetchReviewCandidate(token, { backendUrl, signal }),
    ])
    return { current, candidate }
  }

  useEffect(() => {
    let ignore = false
    const controller = new AbortController()

    async function guardedLoad() {
      setPhase('loading')
      setError('')
      setMessage('')
      try {
        const { current, candidate } = await loadCloudResumeState(controller.signal)
        if (ignore) {
          return
        }
        setCurrentResume(current.ready ? current.resume : null)
        if (ignore) {
          return
        }
        setReviewCandidate(candidate.has_candidate ? candidate.resume : null)
        if (ignore) {
          return
        }
        setResumeRecord(candidate.has_candidate ? candidate.resume : current.resume)
        if (ignore) {
          return
        }
        setPhase(candidate.has_candidate ? 'needs_review' : 'idle')
        if (ignore) {
          return
        }
        setMessage(current.ready ? 'A ready resume is active for cloud answers.' : '')
      } catch (stateError) {
        if (ignore || stateError.name === 'AbortError') {
          return
        }
        setPhase('failed')
        setError(stateError.message || 'Could not load cloud resume state.')
      }
    }

    guardedLoad()
    return () => {
      ignore = true
      controller.abort()
    }
  }, [backendUrl])

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0] || null
    setFile(selectedFile)
    setError(selectedFile ? validateCloudResumeFile(selectedFile) : '')
    setMessage('')
  }

  function clearSelectedResumeFile() {
    setFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  function updateDraftField(field, value) {
    setDraftProfile((current) => ({
      ...normalizeCloudProfile(current || {}),
      [field]: value,
    }))
  }

  async function handleUploadAndExtract(event) {
    event.preventDefault()
    const validationError = validateCloudResumeFile(file)
    if (validationError) {
      setError(validationError)
      return
    }

    setError('')
    setMessage('Uploading resume...')
    setPhase('uploading')
    setDraftProfile(null)
    setExtractionAttempt(null)

    try {
      const token = await getSessionToken()
      const uploaded = await uploadCloudResume(token, file, { backendUrl })
      setResumeRecord(uploaded)
      setMessage('Resume uploaded. Starting extraction...')
      const uploadedStatus = await fetchCloudResumeStatus(token, uploaded.id, { backendUrl })
      setResumeRecord(uploadedStatus)
      if (uploadedStatus.status !== 'uploaded') {
        setPhase(uploadedStatus.status || 'idle')
        setMessage('Resume is not ready for extraction yet. Refresh or upload another file.')
        return
      }
      setPhase('extracting')
      setMessage('Analyzing resume...')
      const extracted = await extractCloudResume(token, uploaded.id, { backendUrl })
      setResumeRecord({ ...uploaded, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      setDraftProfile(normalizeCloudProfile(extracted.profile))
      setExtractionAttempt(extracted.extraction_attempt)
      setReviewCandidate({ ...uploaded, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      clearSelectedResumeFile()
      setPhase('needs_review')
      setMessage(extracted.review_required ? 'Some fields need manual review.' : 'Review extracted profile.')
    } catch (resumeError) {
      setPhase('failed')
      setError(resumeError.message || 'Extraction failed. Try again or upload another file.')
      setMessage('')
    }
  }

  async function handleExtractCandidate() {
    if (!reviewCandidate?.id) {
      return
    }
    setError('')
    setMessage('Analyzing resume...')
    setPhase('extracting')
    try {
      const token = await getSessionToken()
      const extracted = await extractCloudResume(token, reviewCandidate.id, { backendUrl })
      setDraftProfile(normalizeCloudProfile(extracted.profile))
      setExtractionAttempt(extracted.extraction_attempt)
      setResumeRecord({ ...reviewCandidate, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      setPhase('needs_review')
      setMessage(extracted.review_required ? 'Some fields need manual review.' : 'Review extracted profile.')
    } catch (resumeError) {
      setPhase('failed')
      setError(resumeError.message || 'Extraction failed. Try again or upload another file.')
      setMessage('')
    }
  }

  async function handleConfirmProfile(event) {
    event.preventDefault()
    if (confirmPending) {
      return
    }
    const resumeId = resumeRecord?.id || reviewCandidate?.id
    if (!resumeId || !extractionAttempt || !draftProfile) {
      setError('Run extraction before confirming the profile.')
      return
    }

    setError('')
    setMessage('Saving reviewed profile...')
    setConfirmPending(true)
    confirmControllerRef.current?.abort()
    const confirmController = new AbortController()
    confirmControllerRef.current = confirmController
    try {
      const token = await getSessionToken()
      const confirmed = await confirmCloudResume(
        token,
        resumeId,
        extractionAttempt,
        normalizeCloudProfile(draftProfile),
        { backendUrl, signal: confirmController.signal },
      )
      if (confirmController.signal.aborted) {
        return
      }
      setPhase('confirmed')
      setReviewCandidate(null)
      try {
        const current = await fetchCurrentCloudResume(token, { backendUrl, signal: confirmController.signal })
        if (confirmController.signal.aborted) {
          return
        }
        setCurrentResume(current.ready ? current.resume : null)
        setResumeRecord((currentRecord) => (
          current.ready ? current.resume : { ...(currentRecord || {}), id: resumeId, status: confirmed.status }
        ))
        setMessage(
          confirmed.ready && current.ready
            ? 'Resume confirmed and activated.'
            : 'Resume confirmed. Active resume is not ready yet.',
        )
      } catch (refreshError) {
        if (confirmController.signal.aborted || refreshError.name === 'AbortError') {
          return
        }
        setResumeRecord((currentRecord) => ({ ...(currentRecord || {}), id: resumeId, status: confirmed.status }))
        setMessage('Resume confirmed. Refresh to load active resume status.')
      }
    } catch (confirmError) {
      if (confirmController.signal.aborted || confirmError.name === 'AbortError') {
        return
      }
      setError(confirmError.message || 'Could not confirm the reviewed profile.')
      setMessage('')
    } finally {
      if (!confirmController.signal.aborted) {
        setConfirmPending(false)
      }
      if (confirmControllerRef.current === confirmController) {
        confirmControllerRef.current = null
      }
    }
  }

  async function handleDeleteResume(targetResumeArg = null) {
    const targetResume = targetResumeArg || currentResume || reviewCandidate || resumeRecord
    if (!targetResume?.id || deletePending || rebuildPending || confirmPending || ['uploading', 'extracting'].includes(phase)) {
      return
    }
    const resumeLabel = [targetResume.original_filename, targetResume.status].filter(Boolean).join(' - ')
    const confirmMessage = resumeLabel
      ? `Delete this cloud resume (${resumeLabel})?`
      : 'Delete this cloud resume?'
    if (!window.confirm(confirmMessage)) {
      return
    }

    setDeletePending(true)
    setError('')
    setMessage('Deleting resume...')
    try {
      const token = await getSessionToken()
      await deleteCloudResume(token, targetResume.id, { backendUrl })
      if (currentResume?.id === targetResume.id) {
        setCurrentResume(null)
      }
      if (reviewCandidate?.id === targetResume.id) {
        setReviewCandidate(null)
      }
      if (resumeRecord?.id === targetResume.id) {
        setResumeRecord(null)
        clearSelectedResumeFile()
      }
      if ((reviewCandidate?.id === targetResume.id) || (resumeRecord?.id === targetResume.id)) {
        setDraftProfile(null)
        setExtractionAttempt(null)
      }
      setPhase('idle')
      setMessage('Resume deleted.')
    } catch (deleteError) {
      setError(deleteError.message || 'Could not delete the resume. Try again.')
      setMessage('')
    } finally {
      setDeletePending(false)
    }
  }

  async function handleRebuildIndex() {
    if (!currentResume?.id || rebuildPending || deletePending || confirmPending || ['uploading', 'extracting'].includes(phase)) {
      return
    }

    setRebuildPending(true)
    setError('')
    setMessage('Rebuilding resume index...')
    try {
      const token = await getSessionToken()
      await rebuildCloudResumeIndex(token, currentResume.id, { backendUrl })
      const current = await fetchCurrentCloudResume(token, { backendUrl })
      setCurrentResume(current.ready ? current.resume : null)
      setResumeRecord((currentRecord) => (current.ready ? current.resume : currentRecord))
      setPhase('idle')
      setMessage('Resume index rebuilt.')
    } catch (rebuildError) {
      setError(rebuildError.message || 'Could not rebuild the resume index. Try again.')
      setMessage('')
    } finally {
      setRebuildPending(false)
    }
  }

  const busy = ['loading', 'uploading', 'extracting'].includes(phase) || confirmPending || deletePending || rebuildPending
  const uploadDisabled = busy || !file || Boolean(validateCloudResumeFile(file))

  return (
    <RequireAuth backendUrl={backendUrl}>
      {(user) => (
        <AuthShell title="Cloud Resume">
          <div className="auth-user-summary">
            <p>{user.email || user.user_id}</p>
            <span>Authenticated cloud resume setup</span>
          </div>
          <AuthMessage message={error} tone="error" />
          <AuthMessage message={message} tone={phase === 'failed' ? 'error' : 'info'} />
          {currentResume ? (
            <div className="auth-user-summary">
              <p>Current ready resume</p>
              <span>{currentResume.original_filename} - {currentResume.status}</span>
              <button className="auth-secondary-button" type="button" onClick={handleRebuildIndex} disabled={busy || !currentResume.is_active}>
                {rebuildPending ? 'Rebuilding index...' : 'Rebuild Index'}
              </button>
              <button className="auth-secondary-button" type="button" onClick={() => handleDeleteResume(currentResume)} disabled={busy}>
                {deletePending ? 'Deleting resume...' : 'Delete Resume'}
              </button>
            </div>
          ) : (
            <p className="auth-message info">No active ready resume yet.</p>
          )}
          {reviewCandidate && !draftProfile && (
            <div className="auth-user-summary">
              <p>Review candidate found</p>
              <span>{reviewCandidate.original_filename} - re-run extraction if the draft was lost.</span>
              <button className="auth-secondary-button" type="button" onClick={handleExtractCandidate} disabled={busy}>
                {phase === 'extracting' ? 'Analyzing resume...' : 'Extract Again'}
              </button>
              <button className="auth-secondary-button" type="button" onClick={() => handleDeleteResume(reviewCandidate)} disabled={busy}>
                {deletePending ? 'Deleting resume...' : 'Delete Resume'}
              </button>
            </div>
          )}
          <form className="auth-form auth-cloud-resume-form" onSubmit={handleUploadAndExtract}>
            <label>
              Resume file
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                onChange={handleFileChange}
                disabled={busy}
              />
            </label>
            <button type="submit" disabled={uploadDisabled}>
              <Upload size={18} aria-hidden="true" />
              {phase === 'uploading' ? 'Uploading resume...' : phase === 'extracting' ? 'Analyzing resume...' : 'Upload and Extract'}
            </button>
          </form>
          {draftProfile && phase !== 'confirmed' && (
            <form className="auth-form auth-review-form" onSubmit={handleConfirmProfile}>
              <div className="auth-section-heading">
                <FileText size={18} aria-hidden="true" />
                <h2>Review extracted profile</h2>
              </div>
              {CLOUD_PROFILE_FIELDS.map(([field, label, kind]) => (
                <label key={field}>
                  {label}
                  {kind === 'textarea' ? (
                    <textarea
                      value={draftProfile[field] || ''}
                      onChange={(event) => updateDraftField(field, event.target.value)}
                    />
                  ) : (
                    <input
                      type={field === 'email' ? 'email' : 'text'}
                      value={draftProfile[field] || ''}
                      onChange={(event) => updateDraftField(field, event.target.value)}
                    />
                  )}
                </label>
              ))}
              <button type="submit" disabled={confirmPending || phase === 'confirmed'}>
                {phase === 'confirmed' ? 'Resume confirmed' : confirmPending ? 'Saving reviewed profile...' : 'Confirm Reviewed Profile'}
              </button>
              <button className="auth-secondary-button" type="button" onClick={() => handleDeleteResume(resumeRecord || reviewCandidate)} disabled={busy}>
                {deletePending ? 'Deleting resume...' : 'Delete Resume'}
              </button>
            </form>
          )}
          <nav className="auth-links" aria-label="Resume navigation">
            <Link to="/auth/dashboard">Dashboard</Link>
            <Link to="/auth/status">Auth status</Link>
            <Link to="/">Desktop app</Link>
          </nav>
        </AuthShell>
      )}
    </RequireAuth>
  )
}


export function AuthLogoutPage() {
  const [message, setMessage] = useState('Signing out...')

  useEffect(() => {
    let ignore = false

    async function logout() {
      if (supabase) {
        await supabase.auth.signOut()
      }
      if (!ignore) {
        setMessage('Signed out.')
      }
    }

    logout()
    return () => {
      ignore = true
    }
  }, [])

  return (
    <AuthShell title="Logout">
      <AuthMessage message={message} tone="success" />
      <AuthLinks />
    </AuthShell>
  )
}
