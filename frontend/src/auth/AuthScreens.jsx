import { DashboardOnboardingGate } from './DashboardOnboarding'
import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, FileText, LogOut, Upload } from 'lucide-react'

import {
  askInterviewSessionAI,
  bootstrapProfile,
  confirmCloudResume,
  createDesktopHandoff,
  deleteCloudResume,
  deleteInterviewTranscriptEntries,
  downloadInterviewTranscript,
  extractCloudResume,
  fetchInterviewAskAIMessages,
  fetchInterviewSessionNotes,
  fetchInterviewTranscriptEntries,
  fetchInterviewSessions,
  fetchCloudResumeStatus,
  fetchCloudResumeList,
  fetchCurrentCloudResume,
  fetchCurrentUser,
  fetchReviewCandidate,
  generateInterviewSessionNotes,
  rebuildCloudResumeIndex,
  submitMarketingUnsubscribe,
  uploadCloudResume,
  verifyAuthEmailAction,
  SAFE_AUTH_NEXT_ROUTES,
} from './authApi'
import authLogo from '../assets/startup-login/login-logo.svg'
import { supabase } from './supabaseClient'
import './auth.css'
import './account-setup-recovery.css'
import DashboardLayout from './DashboardLayout'
import DashboardLoading from './DashboardLoading'
import WebsiteResumes from './WebsiteResumes'
import DashboardOverview from './DashboardOverview'
import WebsiteSessionTable from './WebsiteSessionTable'
import SessionSuggestions, { SessionEmailDraft } from './SessionSuggestions'
import WebsiteSkeleton from './WebsiteSkeleton'
import WebsiteLogin from './WebsiteLogin'
import WebsiteSessionLossDialog from './WebsiteSessionLossDialog'
import WebsiteCallbackLoading from './WebsiteCallbackLoading'
import { signOutWebsite, watchWebsiteLogoutIntent, clearCompletedWebsiteLogout, createWebsiteSessionLoss, validWebsiteSessionLoss } from './websiteSessionLoss'
import WebsiteSignup from './WebsiteSignup'
import WebsiteConfirmLoading from './WebsiteConfirmLoading'
import WebsitePasswordResetPage, { PasswordResetDialog } from './WebsitePasswordReset'
import { isWebsiteRecoveryEntry } from './passwordRecovery'
import { beginGoogleSignupConsent, readGoogleSignupConsent, clearGoogleSignupConsent } from './signup_oauth_consent'


const AUTH_CALLBACK_URL = 'http://localhost:5173/auth/callback'
const PASSWORD_RESET_URL = 'http://localhost:5173/auth/reset-password'
const UNSUBSCRIBE_CONFIRMATION = 'You have been unsubscribed from promotional and discount emails if this link was valid.'
const UNSUBSCRIBE_TRANSACTIONAL_NOTICE = 'You may still receive important account, security, verification, password reset, and transactional emails.'
const UNSUBSCRIBE_MISSING_MESSAGE = 'This unsubscribe link is missing or invalid. Your preferences were not changed.'
const UNSUBSCRIBE_FAILURE_MESSAGE = 'Unable to update your promotional email preference right now. Please try again later.'
const DEFAULT_LOGIN_NEXT_ROUTE = '/auth/dashboard'
const LOGIN_REQUIRED_MESSAGE = 'Please sign in to continue.'
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


async function persistPendingSignupConsent(session, backendUrl, isCurrent = () => true) {
  if (!CONSENT_FEATURE_ENABLED) return
  const consent = pendingSignupConsentForSession(session)
  if (!consent) return
  await bootstrapProfile(session.access_token, { backendUrl, consent })
  // A different signup may have replaced the record while bootstrap was pending.
  if (isCurrent() && JSON.stringify(pendingSignupConsentForSession(session)) === JSON.stringify(consent)) {
    clearPendingSignupConsent()
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


function getAuthRedirectUrl(desktopState = '', nextRoute = '') {
  const safeDesktopState = getSafeDesktopState(desktopState)
  if (!safeDesktopState && nextRoute) {
    const callback = new URL('/auth/callback', window.location.origin)
    callback.searchParams.set('next', getSafeAuthNextRoute(nextRoute))
    return callback.toString()
  }
  return safeDesktopState ? `${window.location.origin}${desktopLoginRoute(safeDesktopState)}` : AUTH_CALLBACK_URL
}


async function startGoogleLogin(desktopState = '', nextRoute = '', signupAttempt = '') {
  if (!supabase) {
    return { error: new Error('Supabase auth is not configured for this build.') }
  }
  return supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: signupAttempt ? `${getAuthRedirectUrl(desktopState, nextRoute)}&signup_attempt=${encodeURIComponent(signupAttempt)}` : getAuthRedirectUrl(desktopState, nextRoute),
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
  const [verificationNoticeOpen, setVerificationNoticeOpen] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [marketingEmailOptIn, setMarketingEmailOptIn] = useState(null)
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeDesktopState = getSafeDesktopState(desktopState || searchParams.get('desktop_state'))
  const safeNextRoute = safeDesktopState
    ? desktopLoginRoute(safeDesktopState)
    : getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const checkingSession = useRedirectAuthenticatedUser(safeNextRoute)

  function clearWebsiteSignupFields() {
    if (safeDesktopState || window.electronAPI) return
    form.setEmail('')
    form.setPassword('')
    form.setError('')
  }

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
    setVerificationNoticeOpen(false)
    const consent = buildSignupConsent(form.email, marketingEmailOptIn)
    if (!rememberSignupConsent(form.email, marketingEmailOptIn)) {
      form.setLoading(false)
      form.setError('Unable to save signup preferences. Please try again.')
      return
    }
    const { data, error } = await supabase.auth.signUp({
      email: form.email,
      password: form.password,
      options: {
        emailRedirectTo: getAuthRedirectUrl(safeDesktopState, safeDesktopState || window.electronAPI ? '' : safeNextRoute),
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
          clearWebsiteSignupFields()
        }
        return true
      } catch (signupSetupError) {
        form.setError(signupSetupError?.message || 'Account setup could not be completed. Please sign in again.')
      } finally {
        form.setLoading(false)
      }
      return
    }

    form.setLoading(false)

    if (!safeDesktopState && !window.electronAPI) {
      clearWebsiteSignupFields()
      setVerificationNoticeOpen(true)
    } else {
      form.setMessage('Check your email to verify your account.')
    }
    return true
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
    let attempt = ''
    try {
      if (!safeDesktopState && !window.electronAPI) {
        attempt = beginGoogleSignupConsent(buildSignupConsent('', marketingEmailOptIn).consent)
      } else if (!rememberSignupConsent(form.email, marketingEmailOptIn)) {
        throw new Error('Consent storage unavailable')
      }
      const { error } = await startGoogleLogin(safeDesktopState, safeDesktopState || window.electronAPI ? '' : safeNextRoute, attempt)
      if (error) {
        if (attempt) clearGoogleSignupConsent(attempt)
        form.setError(attempt ? 'Google login could not be started. Please try again.' : error.message || 'Google login could not be started.')
      }
    } catch {
      if (attempt) clearGoogleSignupConsent(attempt)
      form.setError('Google login could not be started. Please try again.')
    }
  }

  if (!safeDesktopState && !window.electronAPI) {
    return <WebsiteSignup form={form} checkingSession={checkingSession} configured={Boolean(supabase)}
      termsAccepted={termsAccepted} setTermsAccepted={setTermsAccepted}
      marketingEmailOptIn={marketingEmailOptIn} setMarketingEmailOptIn={setMarketingEmailOptIn}
      onSubmit={handleSubmit} onGoogleLogin={handleGoogleLogin}
      verificationNoticeOpen={verificationNoticeOpen} onDismissVerificationNotice={() => setVerificationNoticeOpen(false)} />
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


export function AuthLoginPage({ backendUrl, desktopState = '', desktopError = '', desktopChecking = false, desktopBlocked = false }) {
  const form = useAuthForm()
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeDesktopState = getSafeDesktopState(desktopState)
  const safeNextRoute = getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const websiteLogin = location.pathname === '/auth/login' && !window.electronAPI
  const emailRef = useRef(null)
  const [sessionLoss, setSessionLoss] = useState(() => websiteLogin ? validWebsiteSessionLoss(location.state?.sessionLoss) : null)
  const checkingSession = useRedirectAuthenticatedUser(safeDesktopState || desktopBlocked || recoveryOpen ? '' : safeNextRoute)

  useEffect(() => {
    const notice = websiteLogin ? validWebsiteSessionLoss(location.state?.sessionLoss) : null
    if (!notice) return
    setSessionLoss(notice)
    const state = { ...location.state }
    delete state.sessionLoss
    // Consume the display-only notice immediately; refresh/back cannot replay it.
    navigate(location.pathname + location.search + location.hash, { replace:true, state })
  }, [location, navigate, websiteLogin])

  useEffect(() => {
    if (!websiteLogin || !supabase) return
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (['SIGNED_IN', 'TOKEN_REFRESHED'].includes(event) && session?.access_token) {
        clearCompletedWebsiteLogout()
        if (sessionLoss) navigate(safeNextRoute, { replace:true })
      }
    })
    return () => data.subscription.unsubscribe()
  }, [websiteLogin, sessionLoss, navigate, safeNextRoute])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase || desktopBlocked || desktopChecking || checkingSession) {
      return
    }

    form.setLoading(true)
    form.setError('')
    form.setMessage('')
    const { data, error } = await supabase.auth.signInWithPassword({
      email: form.email,
      password: form.password,
    }).catch(() => ({ data: {}, error: { message: 'Login could not be completed. Please try again.' } }))

    if (error) {
      form.setLoading(false)
      form.setError(safeDesktopState ? (error.code === 'invalid_credentials' ? 'Invalid email or password.' : 'Desktop sign-in could not be completed. Please try again.') : error.message)
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
      form.setError(safeDesktopState ? 'Desktop login could not be completed. Try logging in again.' : verifyError.message)
    } finally {
      form.setLoading(false)
    }
  }

  async function handleGoogleLogin() {
    if (desktopBlocked || desktopChecking || checkingSession) return
    form.setError('')
    try {
      const { error } = await startGoogleLogin(safeDesktopState, safeDesktopState ? '' : safeNextRoute)
      if (error) {
        form.setError(safeDesktopState ? 'Google login could not be started.' : (error.message || 'Google login could not be started.'))
      }
    } catch {
      form.setError('Google login could not be started.')
    }
  }

  return (
    <>
    <WebsiteLogin
      form={form}
      checkingSession={checkingSession || desktopChecking}
      configured={Boolean(supabase)}
      blocked={desktopBlocked}
      desktopError={desktopError}
      signupHref={safeDesktopState ? desktopSignupRoute(safeDesktopState) : '/auth/signup'}
      onSubmit={handleSubmit}
      onGoogleLogin={handleGoogleLogin}
      authMessage={location.state?.authMessage || ''}
      emailRef={emailRef}
      onForgotPassword={!safeDesktopState && !window.electronAPI ? () => { if (!form.loading && !checkingSession) setRecoveryOpen(true) } : undefined}
    />
    {recoveryOpen && <PasswordResetDialog onClose={() => setRecoveryOpen(false)} />}
    {websiteLogin && sessionLoss && !checkingSession && !recoveryOpen && <WebsiteSessionLossDialog reason={sessionLoss.reason} emailRef={emailRef} onDismiss={() => setSessionLoss(null)} />}
    </>
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

  return (
    <AuthLoginPage
      backendUrl={backendUrl}
      desktopState={state}
      desktopChecking={checking}
      desktopBlocked={!state}
      desktopError={!state ? 'Invalid desktop login request. Start again from the desktop app.' : error}
    />
  )
}


export function AuthForgotPasswordPage() {
  return !window.electronAPI ? <WebsitePasswordResetPage initialStage="request" /> : <DesktopForgotPasswordPage />
}

function DesktopForgotPasswordPage() {
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


export function AuthConfirmPage({ backendUrl }) {
  const [recovery] = useState(() => !window.electronAPI && (isWebsiteRecoveryEntry(new URL(window.location.href)) || (window.history.state?.websiteRecovery === true && !window.location.search)))
  return recovery ? <WebsitePasswordResetPage initialStage="verify" /> : <EmailConfirmationPage backendUrl={backendUrl} />
}

function EmailConfirmationPage({ backendUrl }) {
  const operation = useRef(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    let active = true
    if (!operation.current) {
      const search = window.location.search
      // Scrub before any network work; never persist or display the email token.
      window.history.replaceState(window.history.state, '', '/auth/confirm')
      operation.current = verifyAuthEmailAction(search, supabase,
        (session) => persistPendingSignupConsent(session, backendUrl))
    }
    // Share the pending verification across StrictMode's effect replay.
    operation.current.then((value) => { if (active) setResult(value) })
    return () => { active = false }
  }, [])

  if (!window.electronAPI && (!result || result.status === 'verified' || result.reason === 'email_link_expired')) return <WebsiteConfirmLoading result={result} />
  if (result?.status === 'recovery') return <AuthResetPasswordPage />
  return (
    <AuthShell title={result?.status === 'verified' ? 'Email verified' : result ? 'Secure link unavailable' : 'Checking your secure link…'}>
      <img className="auth-action-logo" src={authLogo} alt="Intervu AI" />
      <div role="status" aria-live="polite">
        <AuthMessage message={result?.message} tone={result?.status === 'error' ? 'error' : 'success'} />
      </div>
      {result && <Link className="auth-action-button" to={result.href} state={result.retrySignupBootstrap ? { retrySignupBootstrap: true } : undefined}>{result.href === '/auth/forgot-password' ? 'Request a new reset link' : result.status === 'verified' ? 'Continue' : result.href === '/auth/dashboard' ? 'Continue to Dashboard' : 'Go to login'}</Link>}
    </AuthShell>
  )
}


export function AuthResetPasswordPage() {
  return !window.electronAPI ? <WebsitePasswordResetPage initialStage="verify" /> : <DesktopResetPasswordPage />
}

function DesktopResetPasswordPage() {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase || loading || message) {
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
      {!message && <form className="auth-form" onSubmit={handleSubmit}>
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
      </form>}
      <AuthMessage message={error} tone="error" />
      <AuthMessage message={message} tone="success" />
      <AuthLinks />
    </AuthShell>
  )
}


export function AuthCallbackPage({ backendUrl }) {
  const operation = useRef(null)
  const verification = useRef(null)
  const websiteCallback = !window.electronAPI
  const callbackError = useRef(new URLSearchParams(window.location.search).has('error') || new URLSearchParams(window.location.hash.slice(1)).has('error'))
  const verifiedAccount = useRef(null)
  const retryAllowed = useRef(false)
  const [retry, setRetry] = useState(0)
  const [canRetry, setCanRetry] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const nextRoute = websiteCallback || searchParams.has('next') ? getSafeAuthNextRoute(searchParams.get('next')) : ''
  const attempt = !window.electronAPI ? searchParams.get('signup_attempt') || '' : ''
  const [status, setStatus] = useState('Finishing sign in...')
  const [error, setError] = useState('')

  function retryPersistence() {
    if (!retryAllowed.current) return
    retryAllowed.current = false
    operation.current = null
    // A failed initial auth check may be retried; successful verification is reused.
    if (!verifiedAccount.current) verification.current = null
    setCanRetry(false)
    setRetry(value => value + 1)
  }

  useEffect(() => {
    let active = true, accountChanged = false, establishedSession = null
    retryAllowed.current = false
    const subscription = supabase?.auth.onAuthStateChange?.((_event, session) => {
      const expectedAccount = verifiedAccount.current || verification.current?.userId
      if (expectedAccount && session?.user?.id !== expectedAccount) {
        accountChanged = true
        retryAllowed.current = false
        if (active) {
          setCanRetry(false)
          setStatus('')
          setError('Sign in could not be verified. Please try again.')
        }
      }
    })?.data?.subscription
    const isCurrent = () => active && !accountChanged
    const authFailure = () => Object.assign(new Error('Authentication recovery required.'), { authRecovery: true })
    async function finishCallback() {
      setCanRetry(false)
      setError('')
      setStatus('Finishing sign in...')
      if (!supabase) {
        if (websiteCallback) { setStatus(''); setError('Sign-in is unavailable. Please return to sign in.') }
        else setStatus('Supabase auth is not configured for this build.')
        return
      }
      try {
        // Cache initial session verification independently from retriable persistence.
        // Supabase owns URL exchange/cleanup; retries never replay an email token/code.
        const verificationKey = `${backendUrl}:${attempt}:${nextRoute}`
        if (verification.current?.key !== verificationKey) {
          verifiedAccount.current = null
          operation.current = null
          verification.current = { key: verificationKey, promise: (async () => {
            if ((websiteCallback && callbackError.current) || (attempt && (searchParams.has('error') || new URLSearchParams(window.location.hash.slice(1)).has('error')))) {
              clearGoogleSignupConsent(attempt)
              throw authFailure()
            }
            const { data, error: sessionError } = await supabase.auth.getSession()
            if (sessionError || !data.session?.access_token) {
              if (attempt) clearGoogleSignupConsent(attempt)
              throw authFailure()
            }
            if (verification.current?.key === verificationKey) {
              verification.current.userId = data.session.user?.id
              verification.current.session = data.session
            }
            const user = await fetchCurrentUser(data.session.access_token, { backendUrl })
            return { user, session: data.session }
          })() }
        }
        const verified = await verification.current.promise
        if (!isCurrent()) return
        const { user } = verified
        establishedSession = verified.session
        if (verifiedAccount.current && verifiedAccount.current !== user.user_id) throw authFailure()
        verifiedAccount.current = user.user_id
        if (attempt || (websiteCallback && CONSENT_FEATURE_ENABLED && pendingSignupConsentForSession(establishedSession))) {
          if (!operation.current) {
            operation.current = { promise: (async () => {
              const { data, error: sessionError } = await supabase.auth.getSession()
              const session = data?.session
              if (!isCurrent() || sessionError || !session?.access_token || session.user?.id !== user.user_id ||
                  (session.expires_at && session.expires_at * 1000 <= Date.now())) throw authFailure()
              if (attempt) {
                if (!CONSENT_FEATURE_ENABLED) throw new Error(CONSENT_SETUP_UNAVAILABLE)
                const pending = readGoogleSignupConsent(attempt)
                if (!pending) throw new Error('expired')
                await bootstrapProfile(session.access_token, { backendUrl, consent: pending.consent })
                if (!isCurrent()) throw authFailure()
                clearGoogleSignupConsent(attempt)
              } else {
                if (!pendingSignupConsentForSession(session)) throw authFailure()
                await persistPendingSignupConsent(session, backendUrl, isCurrent)
              }
              if (!isCurrent()) throw authFailure()
            })() }
          }
          await operation.current.promise
        }
        if (isCurrent()) {
          setStatus(attempt ? 'Your consent preferences were saved.' : `Signed in as ${user.email || user.user_id}.`)
          if (nextRoute) navigate(nextRoute, { replace: true })
        }
      } catch (failure) {
        if (active) {
          const callbackSession = establishedSession || verification.current?.session || null
          const pending = attempt ? readGoogleSignupConsent(attempt) :
            CONSENT_FEATURE_ENABLED && callbackSession && pendingSignupConsentForSession(callbackSession)
          const recoverable = !failure.status || failure.status >= 500 || [408, 429].includes(failure.status)
          const retryable = Boolean(isCurrent() && !failure.authRecovery && ![401, 403].includes(failure.status) &&
            (attempt || recoverable) && pending)
          retryAllowed.current = retryable
          setStatus('')
          setError(retryable ? 'Signup preferences were not saved. Please retry account setup.' :
            attempt ? 'Signup preferences were not saved. Retry account setup or restart signup if this attempt expired or was cancelled.' : 'Sign in could not be verified. Please try again.')
          setCanRetry(retryable)
        }
      }
    }
    void finishCallback()
    return () => { active = false; subscription?.unsubscribe() }
  }, [backendUrl, navigate, nextRoute, attempt, retry, searchParams, websiteCallback])

  if (websiteCallback) return <WebsiteCallbackLoading error={error} nextRoute={nextRoute} canRetry={canRetry}
    onRetry={retryPersistence} />

  return <AuthShell title="Auth Status">
    <AuthMessage message={error} tone="error" />
    {canRetry && <button type="button" onClick={retryPersistence}>Retry saving signup preferences</button>}
    <AuthMessage message={status} tone={error ? 'error' : 'success'} />
    <AuthLinks />
  </AuthShell>
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
  return window.electronAPI ? <DesktopAuthStatusPage backendUrl={backendUrl} /> : <Navigate to="/auth/dashboard" replace />
}

function DesktopAuthStatusPage({ backendUrl }) {
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
    let hadSession = false
    const stopLogoutWatch = window.electronAPI ? () => {} : watchWebsiteLogoutIntent()

    function notifySessionLoss(sessionError = null) {
      if (ignore || window.electronAPI) return false
      const sessionLoss = createWebsiteSessionLoss(hadSession, sessionError)
      if (!hadSession && !sessionLoss) return false
      ignore = true
      setUser(null)
      navigate('/auth/login?next=%2Fauth%2Fstatus', { replace:true, state:{ next:'/auth/status', sessionLoss, authMessage:sessionLoss ? '' : 'Signed out.' } })
      return true
    }

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
        if (notifySessionLoss(sessionError)) return
        setUserError(sessionError?.message || 'No active auth session was found.')
        setLoading(false)
        return
      }

      hadSession = true
      if (!window.electronAPI) clearCompletedWebsiteLogout()

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
    const subscription = window.electronAPI ? null : supabase?.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_OUT') notifySessionLoss()
    })
    return () => {
      ignore = true
      subscription?.data.subscription.unsubscribe()
      stopLogoutWatch()
    }
  }, [backendUrl, navigate])

  async function handleLogout() {
    if (!supabase || logoutPending) {
      return
    }
    setLogoutPending(true)
    setLoading(true)
    setUserError('')
    try {
      const { error: signOutError } = await signOutWebsite(supabase)
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
      {loading && !user && !logoutPending && <WebsiteSkeleton kind="account" label="Loading account details..." />}
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


function WebsiteAccountSetupRecovery({ onRetry }) {
  const navigate = useNavigate()
  const [pending, setPending] = useState(false), [error, setError] = useState('')
  const lock = useRef(false), active = useRef(true), heading = useRef(null)
  useEffect(() => { active.current = true; heading.current?.focus(); return () => { active.current = false } }, [])
  async function logout() {
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    try {
      const { error: failure } = await signOutWebsite(supabase)
      if (failure) throw failure
      if (active.current) navigate('/auth/login', { replace: true })
    } catch {
      if (active.current) setError('Sign out failed. Please try again.')
    } finally {
      lock.current = false
      if (active.current) setPending(false)
    }
  }
  return <DashboardLayout user={{}} title="Account setup" onLogout={logout} logoutPending={pending}>
    <section className="account-setup-recovery" aria-labelledby="account-setup-title">
      <img src={authLogo} alt="" />
      <h1 id="account-setup-title" ref={heading} tabIndex={-1}>Account setup couldn't be completed</h1>
      <p>We couldn't finish preparing your account. Please try again.</p>
      {error && <p role="alert">{error}</p>}
      <div><button type="button" onClick={onRetry} disabled={pending}>Retry</button>
        <button type="button" onClick={logout} disabled={pending}>{pending ? 'Signing out...' : 'Logout'}</button></div>
    </section>
  </DashboardLayout>
}

function RequireAuth({ backendUrl, children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [signedOut, setSignedOut] = useState(false)
  const [sessionLoss, setSessionLoss] = useState(null)
  const [setupFailed, setSetupFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState('')
  const location = useLocation()

  useEffect(() => {
    let ignore = false
    let operation = 0
    let accountId = null
    let hadSession = false
    let checkingSession = false
    let signedOutWhileChecking = false
    const stopLogoutWatch = watchWebsiteLogoutIntent()

    function loseSession(sessionError = null) {
      const notice = createWebsiteSessionLoss(hadSession, sessionError)
      setSessionLoss(current => current || notice)
      setUser(null)
      setSignedOut(true)
      setLoading(false)
    }

    async function loadUser() {
      const currentOperation = ++operation
      let bootstrapping = false
      setSetupFailed(false)
      setError('')
      if (!supabase) {
        setError('Supabase auth is not configured for this build.')
        setLoading(false)
        return
      }

      checkingSession = true
      const { data, error: sessionError } = await supabase.auth.getSession().catch(() => ({ data: { session: null }, error: true }))
      if (ignore || currentOperation !== operation) {
        return
      }
      checkingSession = false

      if (sessionError && !['session_expired', 'refresh_token_not_found', 'refresh_token_already_used', 'session_not_found'].includes(sessionError.code) && !signedOutWhileChecking) {
        setError('Could not verify your session. Please try again.')
        setLoading(false)
        return
      }

      if (sessionError || !data.session?.access_token) {
        loseSession(signedOutWhileChecking && sessionError?.code !== 'session_expired' ? null : sessionError)
        return
      }
      hadSession = true
      if (signedOutWhileChecking) { loseSession(); return }
      clearCompletedWebsiteLogout()

      try {
        accountId = data.session.user?.id || null
        const currentUser = await fetchCurrentUser(data.session.access_token, { backendUrl })
        if (ignore || currentOperation !== operation) return
        // Website entry must ensure settings exist before the onboarding gate reads them.
        // Ordinary entry preserves preferences; explicit verification recovery reuses pending consent.
        if (!window.electronAPI) {
          bootstrapping = true
          // Recovery hint only: consent must still match this verified session.
          if (location.state?.retrySignupBootstrap && CONSENT_FEATURE_ENABLED && pendingSignupConsentForSession(data.session)) {
            await persistPendingSignupConsent(data.session, backendUrl, () => !ignore && currentOperation === operation)
          } else {
            await bootstrapProfile(data.session.access_token, { backendUrl })
          }
        }
        if (!ignore && currentOperation === operation) {
          setUser(currentUser)
          setSignedOut(false)
        }
      } catch (verifyError) {
        if (!ignore && currentOperation === operation) {
          if (bootstrapping) setSetupFailed(true)
          else setError(verifyError.message)
        }
      } finally {
        if (!ignore && currentOperation === operation) {
          setLoading(false)
        }
      }
    }

    loadUser()
    const subscription = supabase?.auth.onAuthStateChange((event, session) => {
      if (ignore) return
      if (event === 'SIGNED_OUT' || !session?.access_token) {
        // INITIAL_SESSION null must not outrun getSession's refresh/recovery.
        if (checkingSession) { if (event === 'SIGNED_OUT') signedOutWhileChecking = true; return }
        if (event !== 'SIGNED_OUT' && event !== 'INITIAL_SESSION') return
        operation += 1
        accountId = null
        loseSession()
      } else if (session.user?.id !== accountId) {
        hadSession = true
        signedOutWhileChecking = false
        if (event === 'SIGNED_IN') clearCompletedWebsiteLogout()
        operation += 1
        accountId = session.user?.id
        setUser(null)
        setLoading(true)
        setError('')
        // Avoid awaiting Supabase auth APIs inside its auth-state callback.
        queueMicrotask(loadUser)
      }
    })
    return () => {
      ignore = true
      operation += 1
      subscription?.data.subscription.unsubscribe()
      stopLogoutWatch()
    }
  }, [backendUrl, attempt, location.state?.retrySignupBootstrap])

  if (loading) {
    if (location.pathname === '/auth/dashboard' && !window.electronAPI) return <DashboardLoading />
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
        state={{ authMessage: sessionLoss ? '' : LOGIN_REQUIRED_MESSAGE, next: nextRoute, sessionLoss }}
      />
    )
  }

  if (setupFailed && !window.electronAPI) return <WebsiteAccountSetupRecovery onRetry={() => { setLoading(true); setAttempt(value => value + 1) }} />

  if (error) {
    return (
      <AuthShell title="Account">
        <AuthMessage message={error} tone="error" />
        <button type="button" className="auth-secondary-button" onClick={() => { setLoading(true); setAttempt(value => value + 1) }}>Retry session check</button>
        <AuthLinks />
      </AuthShell>
    )
  }

  return children(user)
}


export function AuthDashboardPage({ backendUrl, page = 'dashboard' }) {
  return <RequireAuth backendUrl={backendUrl}>{(user) => <DashboardOnboardingGate key={user.user_id} backendUrl={backendUrl}><WebsiteDashboardContent key={user.user_id + page} user={user} backendUrl={backendUrl} page={page} /></DashboardOnboardingGate>}</RequireAuth>
}

function WebsiteDashboardContent({ backendUrl, user, page }) {
  const [sessionPage, setSessionPage] = useState(1)
  const activeRef = useRef(false)
  useEffect(() => { activeRef.current = true; return () => { activeRef.current = false } }, [])

  const [logoutPending, setLogoutPending] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const [sessionHistory, setSessionHistory] = useState([])
  const [sessionHistoryLoading, setSessionHistoryLoading] = useState(true)
  const [sessionHistoryError, setSessionHistoryError] = useState('')
  const [openTranscriptSessionId, setOpenTranscriptSessionId] = useState('')
  const transcriptRequest = useRef(0)
  const transcriptDeletion = useRef(false)
  const transcriptEpoch = useRef(0)
  const notesRequest = useRef(0)
  const [transcriptEntries, setTranscriptEntries] = useState([])
  const [loadedTranscriptSessionId, setLoadedTranscriptSessionId] = useState('')
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [transcriptError, setTranscriptError] = useState('')
  const [transcriptDeletedSessionId, setTranscriptDeletedSessionId] = useState('')
  const [transcriptDownloadKey, setTranscriptDownloadKey] = useState('')
  const [transcriptDownloadError, setTranscriptDownloadError] = useState(null)
  const [openNotesSessionId, setOpenNotesSessionId] = useState('')
  const [sessionNotes, setSessionNotes] = useState(null)
  const [notesLoading, setNotesLoading] = useState(false)
  const [notesError, setNotesError] = useState('')
  const [notesGenerateKey, setNotesGenerateKey] = useState('')
  const [openAskAISessionId, setOpenAskAISessionId] = useState('')
  const [askAIMessages, setAskAIMessages] = useState([])
  const [askAIMessagesNextPage, setAskAIMessagesNextPage] = useState(null)
  const askAIInput = useRef(null)
  const [emailDrafts, setEmailDrafts] = useState({})
  const [askAIDrafts, setAskAIDrafts] = useState({})
  const [askAIRequestIds, setAskAIRequestIds] = useState({})
  const [askAILoading, setAskAILoading] = useState(false)
  const [askAIHistoryLoading, setAskAIHistoryLoading] = useState(false)
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
    setAskAIHistoryLoading(false)
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
          page: sessionPage,
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
  }, [backendUrl, sessionPage])

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
        page: sessionPage,
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

  async function handleTranscriptToggle(sessionId, { reload = false } = {}) {
    if (transcriptDeletion.current) return
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId) {
      return
    }
    if (openTranscriptSessionId === normalizedSessionId && !reload) {
      setOpenTranscriptSessionId('')
      setTranscriptEntries([])
      setTranscriptError('')
      return
    }
    setOpenTranscriptSessionId(normalizedSessionId)
    if (openTranscriptSessionId !== normalizedSessionId) setTranscriptEntries([])
    setTranscriptLoading(true)
    setTranscriptError('')
    const request = ++transcriptRequest.current
    try {
      if (!supabase) {
        setOpenTranscriptSessionId(normalizedSessionId)
        setTranscriptEntries([])
        setTranscriptError('Transcript access is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (!activeRef.current || request !== transcriptRequest.current) return
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
      if (!activeRef.current || request !== transcriptRequest.current) return
      if (result.items.some(entry => entry.session_id !== normalizedSessionId)) throw new Error('Transcript session mismatch.')
      setOpenTranscriptSessionId(normalizedSessionId)
      setTranscriptEntries(result.items)
      setLoadedTranscriptSessionId(normalizedSessionId)
    } catch {
      if (!activeRef.current || request !== transcriptRequest.current) return
      setOpenTranscriptSessionId(normalizedSessionId)
      setTranscriptEntries([])
      setTranscriptError('Could not load transcript entries. Please try again.')
    } finally {
      if (activeRef.current && request === transcriptRequest.current) setTranscriptLoading(false)
    }
  }

  async function handleTranscriptDownload(sessionId, format) {
    if (transcriptDeletion.current) return false
    const epoch = transcriptEpoch.current
    const normalizedSessionId = String(sessionId || '').trim()
    const normalizedFormat = String(format || '').trim().toLowerCase()
    if (!normalizedSessionId || !normalizedFormat || transcriptDownloadKey) {
      return
    }
    setTranscriptDownloadKey(`${normalizedSessionId}:${normalizedFormat}`)
    setTranscriptDownloadError(null)
    const downloadError = message => { if (activeRef.current && epoch === transcriptEpoch.current) setTranscriptDownloadError({ sessionId:normalizedSessionId, message }) }
    try {
      if (!supabase) {
        downloadError('Transcript download is unavailable until auth is ready.')
        return false
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (!activeRef.current) return false
      if (sessionError || !data.session?.access_token) {
        downloadError('Could not verify transcript download access. Please sign in again.')
        return false
      }
      const download = await downloadInterviewTranscript(data.session.access_token, normalizedSessionId, normalizedFormat, {
        backendUrl,
      })
      if (activeRef.current && epoch === transcriptEpoch.current) triggerTextDownload(download.filename, download.content, download.format)
      return true
    } catch {
      if (!activeRef.current || epoch !== transcriptEpoch.current) return false
      downloadError('Could not download the transcript. Please try again.')
      return false
    } finally {
      if (activeRef.current && epoch === transcriptEpoch.current) setTranscriptDownloadKey('')
    }
  }

  async function handleTranscriptDelete(sessionId) {
    if (transcriptDeletion.current) throw new Error('Transcript deletion is already pending.')
    if (sessionId !== openTranscriptSessionId || sessionId !== loadedTranscriptSessionId || !transcriptEntries.length || transcriptEntries.some(entry => entry.session_id !== sessionId)) {
      throw new Error('Load the selected session transcript before deleting it.')
    }
    transcriptDeletion.current = true
    // Fence all previously started transcript reads and downloads before mutation.
    transcriptRequest.current += 1
    transcriptEpoch.current += 1
    setTranscriptLoading(false)
    setTranscriptDownloadKey('')
    setTranscriptDownloadError(null)
    try {
      if (!supabase) throw new Error('Authentication is unavailable. Please sign in again.')
      const { data, error } = await supabase.auth.getSession()
      if (error || !data.session?.access_token) throw new Error('Please sign in again before deleting the transcript.')
      await deleteInterviewTranscriptEntries(data.session.access_token, sessionId, { backendUrl })
      if (!activeRef.current) return
      setOpenTranscriptSessionId(sessionId)
      setTranscriptEntries([])
      setTranscriptError('')
      setTranscriptDeletedSessionId(sessionId)
    } finally {
      transcriptDeletion.current = false
    }
  }

  async function handleNotesToggle(sessionId, { reload = false } = {}) {
    const normalizedSessionId = String(sessionId || '').trim()
    if (!normalizedSessionId || notesGenerateKey) {
      return
    }
    if (openNotesSessionId === normalizedSessionId && !reload) {
      setOpenNotesSessionId('')
      setSessionNotes(null)
      setNotesError('')
      return
    }
    setOpenNotesSessionId(normalizedSessionId)
    setSessionNotes(null)
    setNotesError('')
    setNotesLoading(true)
    const request = ++notesRequest.current
    try {
      if (!supabase) {
        setNotesError('AI notes access is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (!activeRef.current || request !== notesRequest.current) return
      if (sessionError || !data.session?.access_token) {
        setNotesError('Could not verify AI notes access. Please sign in again.')
        return
      }
      const result = await fetchInterviewSessionNotes(data.session.access_token, normalizedSessionId, {
        backendUrl,
      })
      if (!activeRef.current || request !== notesRequest.current) return
      setSessionNotes(result)
    } catch (loadError) {
      if (!activeRef.current || request !== notesRequest.current) return
      if (String(loadError?.message || '').includes('were not found')) {
        setNotesError('No AI notes yet. Generate AI Notes to create them.')
      } else {
        setNotesError('Could not load AI notes. Please try again.')
      }
    } finally {
      if (activeRef.current && request === notesRequest.current) setNotesLoading(false)
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
    const request = ++notesRequest.current
    try {
      if (!supabase) {
        setNotesError('AI notes generation is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (!activeRef.current || request !== notesRequest.current) return
      if (sessionError || !data.session?.access_token) {
        setNotesError('Could not verify AI notes generation access. Please sign in again.')
        return
      }
      const result = await generateInterviewSessionNotes(data.session.access_token, normalizedSessionId, {
        backendUrl,
        forceRegenerate,
      })
      if (!activeRef.current || request !== notesRequest.current) return
      setSessionNotes(result)
    } catch (generateError) {
      if (!activeRef.current || request !== notesRequest.current) return
      setNotesError(String(generateError?.message || '').trim() || 'Could not generate AI notes. Please try again.')
    } finally {
      if (activeRef.current && request === notesRequest.current) { setNotesLoading(false); setNotesGenerateKey('') }
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
    setAskAIHistoryLoading(true)
    try {
      if (!supabase) {
        setAskAIError('Ask AI is unavailable until auth is ready.')
        return
      }
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (controller.signal.aborted || !activeRef.current) return
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
        setAskAIHistoryLoading(false)
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
      if (controller.signal.aborted || !activeRef.current) return
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
      if (controller.signal.aborted || !activeRef.current) return
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
      const { error: signOutError } = await signOutWebsite(supabase)
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
        <DashboardLayout user={user} title={page === 'sessions' ? 'Call Sessions' : 'Dashboard'} onLogout={handleLogout} logoutPending={logoutPending}>
          <AuthMessage message={logoutError || error} tone="error" />
          {bootstrapResult && (
            <div className="auth-user-summary">
              <p>Profile ready</p>
              <span>
                Your account profile and settings are ready.
              </span>
            </div>
          )}
          {page === 'dashboard' && <DashboardOverview user={user} backendUrl={backendUrl} sessions={sessionHistory} loading={sessionHistoryLoading} failed={Boolean(sessionHistoryError)} />}
          {sessionHistoryError ? (
            <div>
              <p className="auth-message error">{sessionHistoryError}</p>
              <button className="auth-secondary-button" type="button" onClick={handleSessionHistoryRetry}>
                Retry session history
              </button>
            </div>
          ) : sessionHistoryLoading || sessionHistory.length ? (
            <WebsiteSessionTable
              sessions={sessionHistory}
              loading={sessionHistoryLoading}
              preview={page === 'dashboard'}
              page={sessionPage}
              onPageChange={setSessionPage}
              viewerData={{transcriptSessionId:loadedTranscriptSessionId,entries:transcriptEntries,transcriptLoading,askSessionId:openAskAISessionId,messages:askAIMessages,askLoading:askAILoading,downloadLoading:Boolean(transcriptDownloadKey),onDeleteTranscript:handleTranscriptDelete}}
              onTranscript={handleTranscriptToggle}
              transcriptDisabled={() => false}
              sectionDisabled={(id, section) => section === 'notes' && Boolean(notesGenerateKey) && openNotesSessionId !== id}
              onSection={(id, section) => {
                if (section === 'transcript' && openTranscriptSessionId !== id) handleTranscriptToggle(id, {reload:true})
                if (section === 'notes' && openNotesSessionId !== id) handleNotesToggle(id, {reload:true})
                if (section === 'ask' && openAskAISessionId !== id) handleAskAIToggle(id, {reload:true})
              }}
              actionsFor={(id) => [
                { label: 'Generate AI Notes', onClick: () => handleNotesGenerate(id), disabled: Boolean(notesGenerateKey) || notesLoading },
                { label: 'View AI Notes', onClick: () => { if (openNotesSessionId !== id) handleNotesToggle(id, {reload:true}) }, disabled: notesLoading },
                { label: 'Ask AI', onClick: () => { if (openAskAISessionId !== id) handleAskAIToggle(id, {reload:true}) }, disabled: askAILoading },
                { label: 'Download .txt', onClick: () => handleTranscriptDownload(id, 'txt'), disabled: Boolean(transcriptDownloadKey) },
                { label: 'Download .md', onClick: () => handleTranscriptDownload(id, 'md'), disabled: Boolean(transcriptDownloadKey) },
              ]}
              renderDetails={(session, viewerSection, presentation) => (
                <article key={session.id} className="auth-session-history__item">
                  {viewerSection === 'details' && <>
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
                  </>}
                  {viewerSection === 'transcript' && transcriptDownloadError?.sessionId === session.id && <p role="alert" className="auth-message error">{transcriptDownloadError.message}</p>}
                  {viewerSection === 'transcript' && openTranscriptSessionId === session.id ? (
                    <div className="auth-session-history__transcript" aria-busy={transcriptLoading}>
                      {transcriptDeletedSessionId === session.id && <p role="status">Transcript deleted.</p>}
                      {transcriptLoading && Boolean(transcriptEntries.length) && <p role="status">Refreshing transcript...</p>}
                      {transcriptLoading && !transcriptEntries.length ? (
                        <WebsiteSkeleton label="Loading transcript..." />
                      ) : transcriptError ? (
                        <div><p className="auth-message error" role="alert">{transcriptError}</p><button type="button" onClick={() => handleTranscriptToggle(session.id, { reload: true })}>Retry transcript</button></div>
                      ) : presentation.visibleEntries.length ? (
                        presentation.visibleEntries.map((entry) => (
                          <section key={entry.id} className="auth-session-history__transcript-entry">
                            <p className="auth-session-history__line"><strong>Question:</strong> {entry.question_text}</p>
                            <p className="auth-session-history__line"><strong>Answer:</strong> {entry.answer_text}</p>
                            <p className="auth-session-history__meta">{formatTranscriptDisplayMetaLine(entry)}</p>
                          </section>
                        ))
                      ) : (
                        <p className="auth-session-history__line">No transcript available.</p>
                      )}
                    </div>
                  ) : null}
                  {viewerSection === 'notes' && openNotesSessionId === session.id ? (
                    <div className="auth-session-history__notes" aria-busy={notesLoading}>
                      {notesLoading ? (
                        notesGenerateKey ? <p className="auth-session-history__line" role="status">Generating AI notes...</p> : <WebsiteSkeleton kind="notes" label="Loading AI notes..." />
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
                  {viewerSection === 'ask' && openAskAISessionId === session.id ? (
                    <div className="auth-session-history__ask-ai wa-panel" aria-busy={askAILoading}>
                      <div className="wa-conversation">
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
                      {askAIHistoryLoading && !askAIMessages.length ? (
                        <WebsiteSkeleton label="Loading Ask AI messages..." />
                      ) : null}
                      {presentation.hiddenMessages.size > 0 && <div className="wa-cleared" role="status"><p>Chat cleared from this view. Saved messages will return when you reopen this popup.</p><small>New questions can still use the saved conversation as context.</small></div>}
                      {presentation.visibleMessages.length ? (
                        <div className="auth-session-history__ask-ai-messages">
                          {presentation.visibleMessages.map((message) => (
                            <section key={message.id} className="auth-session-history__ask-ai-message">
                              {message.role === 'assistant' && (/^Subject:.*thank you/im.test(message.message_text) || /follow[ -]up email/i.test(askAIMessages[askAIMessages.findIndex(item=>item.id===message.id)-1]?.message_text || '')) ? <SessionEmailDraft text={message.message_text} value={emailDrafts[`${session.id}:${message.id}`]} onChange={value=>setEmailDrafts(current=>({...current,[`${session.id}:${message.id}`]:value}))} /> : <p className="auth-session-history__line"><strong>{message.role === 'user' ? 'You' : 'AI'}:</strong> {message.message_text}</p>}
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
                        <div className="wa-intro"><p>Ask a question about this session, or start with a suggestion below.</p><SessionSuggestions draft={askAIDrafts[session.id] || ''} disabled={askAILoading} inputRef={askAIInput} onChange={value=>{setAskAIDrafts(current=>({...current,[session.id]:value}));setAskAIRequestIds(current=>{if(current[session.id]?.question===value.trim())return current;const next={...current};delete next[session.id];return next})}} /><small>These entries are stored questions and generated answers, not a complete spoken conversation. Assessments are limited to the available text.</small></div>
                      ) : null}
                      </div>
                      {!isAskAIContextMissingError(askAIError) ? (
                        <form className="auth-session-history__ask-ai-form" onSubmit={(event) => handleAskAISubmit(event, session.id)}>
                          <label>
                            <span className="wd-sr-only">Ask about this session</span>
                            <textarea ref={askAIInput}
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
                              placeholder="Type your question here…"
                            />
                          </label>
                          <button
                            className="auth-session-history__action"
                            type="submit"
                            disabled={askAILoading || !String(askAIDrafts[session.id] || '').trim()}
                          >
                            {askAILoading ? 'Asking AI...' : 'Send'}
                          </button>
                        </form>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              )}
            />
          ) : (
            <div><p className="auth-message info">No interview sessions yet.</p>{sessionPage > 1 && <button type="button" onClick={() => setSessionPage(sessionPage - 1)}>Previous page</button>}</div>
          )}
          <details className="wd-account-tools"><summary>Account setup</summary>
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
          </details>
        </DashboardLayout>
  )
}


export function AuthResumePage({ backendUrl }) {
  return <RequireAuth backendUrl={backendUrl}>{(user) => <WebsiteResumeContent key={user.user_id} user={user} backendUrl={backendUrl} />}</RequireAuth>
}

function WebsiteResumeContent({ backendUrl, user }) {
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
  const returnFocusRef = useRef(null)
  const operationRef = useRef(null)
  const [dialog, setDialog] = useState(null)
  const [manual, setManual] = useState(false)
  const [manualDraft, setManualDraft] = useState(null)
  const [statusAttempt, setStatusAttempt] = useState(0)

  useEffect(() => {
    return () => {
      confirmControllerRef.current?.abort()
      operationRef.current?.abort()
    }
  }, [])

  async function getSessionToken(sessionErrorMessage = 'Session expired or signed out. Please log in again.') {
    if (!supabase) {
      throw new Error('Supabase auth is not configured for this build.')
    }
    const { data, error: sessionError } = await supabase.auth.getSession()
    if (sessionError || !data.session?.access_token || data.session.user?.id !== user.user_id) {
      throw new Error(sessionErrorMessage)
    }
    return data.session.access_token
  }

  function beginResumeOperation() {
    if (operationRef.current) return null
    const controller = new AbortController()
    operationRef.current = controller
    return controller
  }

  function finishResumeOperation(controller) {
    if (operationRef.current === controller) operationRef.current = null
  }

  function openUpload(event) {
    if (busy) return
    returnFocusRef.current = event?.currentTarget || returnFocusRef.current
    setError('')
    setDialog('upload')
  }

  function openReview() {
    setManual(false)
    setDialog(['uploading', 'extracting'].includes(phase) || confirmPending ? 'processing' : 'review')
  }

  function openManual() {
    if (busy) return
    setManualDraft(current => current || normalizeCloudProfile({}))
    setManual(true)
    setError('')
    setMessage('')
    setDialog('review')
  }

  async function loadCloudResumeState(signal) {
    const token = await getSessionToken()
    const [current, candidate, items] = await Promise.all([
      fetchCurrentCloudResume(token, { backendUrl, signal }),
      fetchReviewCandidate(token, { backendUrl, signal }),
      fetchCloudResumeList(token, { backendUrl, signal }),
    ])
    const pending = items.find(item => item.id !== current.resume?.id && ['uploaded', 'extracting', 'needs_review', 'indexing', 'failed', 'timeout', 'cancelled'].includes(item.status))
    return { current, candidate, pending }
  }

  useEffect(() => {
    let ignore = false
    const controller = new AbortController()

    async function guardedLoad() {
      setPhase('loading')
      setError('')
      setMessage('')
      try {
        const { current, candidate, pending } = await loadCloudResumeState(controller.signal)
        if (ignore) {
          return
        }
        setCurrentResume(current.ready ? current.resume : null)
        if (ignore) {
          return
        }
        setReviewCandidate(candidate.has_candidate ? candidate.resume : pending || null)
        if (ignore) {
          return
        }
        setResumeRecord(candidate.has_candidate ? candidate.resume : pending || current.resume)
        if (ignore) {
          return
        }
        setPhase(candidate.has_candidate ? 'needs_review' : 'idle')
        if (ignore) {
          return
        }
        setMessage('')
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
  }, [backendUrl, statusAttempt])

  function handleFileChange(selectedFile) {
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
    if (['loading', 'uploading', 'extracting'].includes(phase) || confirmPending || deletePending || rebuildPending) return
    const validationError = validateCloudResumeFile(file)
    if (validationError) {
      setError(validationError)
      return
    }

    if (draftProfile && !window.confirm('Uploading another resume replaces your unconfirmed draft. Continue?')) return
    const controller = beginResumeOperation()
    if (!controller) return
    setManual(false)
    setDialog('processing')
    setError('')
    setMessage('Uploading resume...')
    setPhase('uploading')
    setDraftProfile(null)
    setExtractionAttempt(null)

    try {
      const token = await getSessionToken()
      const uploaded = await uploadCloudResume(token, file, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      setResumeRecord(uploaded)
      setReviewCandidate(uploaded)
      setMessage('Resume uploaded. Starting extraction...')
      const uploadedStatus = await fetchCloudResumeStatus(token, uploaded.id, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      setResumeRecord(uploadedStatus)
      if (uploadedStatus.status !== 'uploaded') {
        setPhase(uploadedStatus.status || 'idle')
        setMessage('Resume is not ready for extraction yet. Refresh or upload another file.')
        return
      }
      setPhase('extracting')
      setMessage('Analyzing resume...')
      const extracted = await extractCloudResume(token, uploaded.id, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      setDialog('review')
      setResumeRecord({ ...uploaded, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      setDraftProfile(normalizeCloudProfile(extracted.profile))
      setExtractionAttempt(extracted.extraction_attempt)
      setReviewCandidate({ ...uploaded, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      clearSelectedResumeFile()
      setPhase('needs_review')
      setMessage(extracted.review_required ? 'Some fields need manual review.' : 'Review extracted profile.')
    } catch (resumeError) {
      if (controller.signal.aborted || resumeError.name === 'AbortError') return
      setPhase('failed')
      setError(resumeError.message || 'Extraction failed. Try again or upload another file.')
      setMessage('')
    } finally { finishResumeOperation(controller) }
  }

  async function handleExtractCandidate() {
    if (!reviewCandidate?.id || busy || operationRef.current) {
      return
    }
    if (draftProfile && !window.confirm('Extracting again replaces your unconfirmed edits. Continue?')) return
    const controller = beginResumeOperation()
    if (!controller) return
    setManual(false)
    setDialog('processing')
    setError('')
    setMessage('Analyzing resume...')
    setPhase('extracting')
    try {
      const token = await getSessionToken()
      const extracted = await extractCloudResume(token, reviewCandidate.id, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      setDialog('review')
      setDraftProfile(normalizeCloudProfile(extracted.profile))
      setExtractionAttempt(extracted.extraction_attempt)
      setResumeRecord({ ...reviewCandidate, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      setReviewCandidate({ ...reviewCandidate, status: extracted.status, extraction_attempt: extracted.extraction_attempt })
      setPhase('needs_review')
      setMessage(extracted.review_required ? 'Some fields need manual review.' : 'Review extracted profile.')
    } catch (resumeError) {
      if (controller.signal.aborted || resumeError.name === 'AbortError') return
      setPhase('failed')
      setError(resumeError.message || 'Extraction failed. Try again or upload another file.')
      setMessage('')
    } finally { finishResumeOperation(controller) }
  }

  async function handleConfirmProfile(event) {
    event.preventDefault()
    if (manual) return
    if (confirmPending || operationRef.current) {
      return
    }
    const resumeId = resumeRecord?.id || reviewCandidate?.id
    if (!resumeId || !extractionAttempt || !draftProfile) {
      setError('Run extraction before confirming the profile.')
      return
    }

    const operationController = beginResumeOperation()
    if (!operationController) return
    setDialog('processing')
    setError('')
    setMessage('Saving reviewed profile...')
    setConfirmPending(true)
    confirmControllerRef.current?.abort()
    const confirmController = operationController
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
      setDialog(null)
      setManualDraft(null)
      setPhase('confirmed')
      setReviewCandidate(null)
      setDraftProfile(null)
      setExtractionAttempt(null)
      clearSelectedResumeFile()
      try {
        const current = await fetchCurrentCloudResume(token, { backendUrl, signal: confirmController.signal })
        if (confirmController.signal.aborted) {
          return
        }
        setCurrentResume(current.ready ? current.resume : null)
        setResumeRecord((currentRecord) => (
          current.ready && current.resume?.id === resumeId ? current.resume : { ...(currentRecord || {}), id: resumeId, status: confirmed.status }
        ))
        setMessage(
          confirmed.ready && current.ready && current.resume?.id === resumeId
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
      setDialog('review')
      setError(confirmError.message || 'Could not confirm the reviewed profile.')
      setMessage('')
    } finally {
      if (!confirmController.signal.aborted) {
        setConfirmPending(false)
      }
      finishResumeOperation(confirmController)
      if (confirmControllerRef.current === confirmController) {
        confirmControllerRef.current = null
      }
    }
  }

  async function handleDeleteResume(targetResumeArg = null) {
    const targetResume = targetResumeArg || currentResume || reviewCandidate || resumeRecord
    if (!targetResume?.id || operationRef.current || deletePending || rebuildPending || confirmPending || ['uploading', 'extracting'].includes(phase)) {
      return
    }
    const resumeLabel = [targetResume.original_filename, targetResume.status].filter(Boolean).join(' - ')
    const confirmMessage = resumeLabel
      ? `Delete this cloud resume (${resumeLabel})?`
      : 'Delete this cloud resume?'
    if (!window.confirm(confirmMessage)) {
      return
    }

    const controller = beginResumeOperation()
    if (!controller) return
    setDeletePending(true)
    setError('')
    setMessage('Deleting resume...')
    try {
      const token = await getSessionToken()
      await deleteCloudResume(token, targetResume.id, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
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
        setDialog(null)
      }
      setPhase('idle')
      setManualDraft(null)
      setMessage('Resume deleted.')
    } catch (deleteError) {
      if (controller.signal.aborted || deleteError.name === 'AbortError') return
      setError(deleteError.message || 'Could not delete the resume. Try again.')
      setMessage('')
    } finally {
      if (!controller.signal.aborted) setDeletePending(false)
      finishResumeOperation(controller)
    }
  }

  async function handleRebuildIndex() {
    if (!currentResume?.id || operationRef.current || rebuildPending || deletePending || confirmPending || ['uploading', 'extracting'].includes(phase)) {
      return
    }

    const controller = beginResumeOperation()
    if (!controller) return
    setRebuildPending(true)
    setError('')
    setMessage('Rebuilding resume index...')
    try {
      const token = await getSessionToken()
      await rebuildCloudResumeIndex(token, currentResume.id, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      const current = await fetchCurrentCloudResume(token, { backendUrl, signal: controller.signal })
      if (controller.signal.aborted) return
      setCurrentResume(current.ready ? current.resume : null)
      setResumeRecord((currentRecord) => (!reviewCandidate && current.ready ? current.resume : currentRecord))
      setPhase('idle')
      setMessage('Resume index rebuilt.')
    } catch (rebuildError) {
      if (controller.signal.aborted || rebuildError.name === 'AbortError') return
      setError(rebuildError.message || 'Could not rebuild the resume index. Try again.')
      setMessage('')
    } finally {
      if (!controller.signal.aborted) setRebuildPending(false)
      finishResumeOperation(controller)
    }
  }

  const busy = ['loading', 'uploading', 'extracting'].includes(phase) || confirmPending || deletePending || rebuildPending
  const uploadDisabled = busy || !file || Boolean(validateCloudResumeFile(file))

  function retryResumeOperation() {
    if (busy) return
    if (['extracting', 'indexing'].includes(reviewCandidate?.status)) { setStatusAttempt(value => value + 1); return }
    if (reviewCandidate?.id) { handleExtractCandidate(); return }
    if (file) { handleUploadAndExtract({ preventDefault() {} }); return }
    setStatusAttempt(value => value + 1)
  }

  return <DashboardLayout user={user} title="Resumes">
    <WebsiteResumes currentResume={currentResume} candidate={reviewCandidate || resumeRecord}
      phase={phase} busy={busy} file={file} error={error} message={message}
      dialog={dialog} onClose={() => setDialog(null)} onUpload={openUpload}
      onManual={openManual} onReview={openReview} onExtract={handleExtractCandidate}
      onConfirm={handleConfirmProfile} onDelete={handleDeleteResume} onRebuild={handleRebuildIndex}
      onRetry={retryResumeOperation} onSubmit={handleUploadAndExtract} onFile={handleFileChange}
      fileInputRef={fileInputRef} returnFocusRef={returnFocusRef} uploadDisabled={uploadDisabled}
      draftProfile={manual ? manualDraft : draftProfile} hasCandidateDraft={Boolean(draftProfile)} manual={manual} fields={CLOUD_PROFILE_FIELDS}
      updateDraftField={manual ? (field, value) => setManualDraft(current => ({...current, [field]:value})) : updateDraftField}
      confirmPending={confirmPending} deletePending={deletePending} rebuildPending={rebuildPending} />
  </DashboardLayout>
}


export function AuthLogoutPage() {
  const [message, setMessage] = useState('Signing out...')

  useEffect(() => {
    let ignore = false

    async function logout() {
      if (supabase) {
        await signOutWebsite(supabase)
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
