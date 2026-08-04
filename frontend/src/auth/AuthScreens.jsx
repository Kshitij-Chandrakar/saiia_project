import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, FileText, LogOut, Upload } from 'lucide-react'

import {
  bootstrapProfile,
  confirmCloudResume,
  extractCloudResume,
  fetchCloudResumeStatus,
  fetchCurrentCloudResume,
  fetchCurrentUser,
  fetchReviewCandidate,
  uploadCloudResume,
} from './authApi'
import { supabase } from './supabaseClient'
import './auth.css'


const AUTH_CALLBACK_URL = 'http://localhost:5173/auth/callback'
const PASSWORD_RESET_URL = 'http://localhost:5173/auth/reset-password'
const DEFAULT_LOGIN_NEXT_ROUTE = '/auth/dashboard'
const SAFE_AUTH_NEXT_ROUTES = new Set(['/auth/dashboard', '/auth/status'])
const LOGIN_REQUIRED_MESSAGE = 'Session expired or signed out. Please log in.'
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


function getSafeAuthNextRoute(value, fallback = DEFAULT_LOGIN_NEXT_ROUTE) {
  const route = String(value || '').trim()
  return SAFE_AUTH_NEXT_ROUTES.has(route) ? route : fallback
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
          navigate(targetRoute, { replace: true })
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

      const result = await bootstrapProfile(data.session.access_token, { backendUrl })
      if (bootstrapOperationRef.current === operationId) {
        setBootstrapResult(result)
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


function AuthLinks({ mode }) {
  return (
    <nav className="auth-links" aria-label="Auth navigation">
      {mode !== 'login' && <Link to="/auth/login">Login</Link>}
      {mode !== 'signup' && <Link to="/auth/signup">Sign up</Link>}
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


export function AuthSignupPage() {
  const form = useAuthForm()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeNextRoute = getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const checkingSession = useRedirectAuthenticatedUser(safeNextRoute)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!supabase) {
      return
    }

    form.setLoading(true)
    form.setError('')
    form.setMessage('')
    const { error } = await supabase.auth.signUp({
      email: form.email,
      password: form.password,
      options: {
        emailRedirectTo: AUTH_CALLBACK_URL,
      },
    })
    form.setLoading(false)

    if (error) {
      form.setError(error.message)
      return
    }

    form.setMessage('Check your email to verify your account.')
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
        <button type="submit" disabled={!supabase || form.loading}>
          {form.loading ? 'Creating...' : 'Sign Up'}
        </button>
      </form>
      <AuthMessage message={form.error} tone="error" />
      <AuthMessage message={form.message} tone="success" />
      <AuthLinks mode="signup" />
    </AuthShell>
  )
}


export function AuthLoginPage({ backendUrl }) {
  const form = useAuthForm()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const safeNextRoute = getSafeAuthNextRoute(searchParams.get('next') || location.state?.next)
  const checkingSession = useRedirectAuthenticatedUser(safeNextRoute)

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
      <AuthMessage message={location.state?.authMessage || ''} tone="info" />
      <AuthMessage message={form.error} tone="error" />
      <AuthMessage message={form.message} tone="success" />
      <AuthLinks mode="login" />
    </AuthShell>
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
  const profileBootstrapDisabled = bootstrapLoading || logoutPending

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
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

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
        setMessage(current.ready ? 'A ready resume exists. C3.4 will connect it to active cloud RAG.' : '')
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
    try {
      const token = await getSessionToken()
      const confirmed = await confirmCloudResume(
        token,
        resumeId,
        extractionAttempt,
        normalizeCloudProfile(draftProfile),
        { backendUrl },
      )
      setPhase('confirmed')
      setMessage(confirmed.confirmed_profile_saved ? 'Resume confirmed. C3.4 will index and activate it.' : 'Resume confirmation finished.')
    } catch (confirmError) {
      setError(confirmError.message || 'Could not confirm the reviewed profile.')
      setMessage('')
    } finally {
      setConfirmPending(false)
    }
  }

  const busy = ['loading', 'uploading', 'extracting'].includes(phase)
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
            </div>
          )}
          <form className="auth-form auth-cloud-resume-form" onSubmit={handleUploadAndExtract}>
            <label>
              Resume file
              <input
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
          {draftProfile && (
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
