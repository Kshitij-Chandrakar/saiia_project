import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, LogOut } from 'lucide-react'

import { bootstrapProfile, fetchCurrentUser } from './authApi'
import { supabase } from './supabaseClient'
import './auth.css'


const AUTH_CALLBACK_URL = 'http://localhost:5173/auth/callback'
const PASSWORD_RESET_URL = 'http://localhost:5173/auth/reset-password'


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
      <Link to="/">Desktop app</Link>
    </nav>
  )
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
      navigate('/auth/status', { replace: true })
    } catch (verifyError) {
      form.setError(verifyError.message)
    } finally {
      form.setLoading(false)
    }
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
  const [sessionToken, setSessionToken] = useState('')
  const [bootstrapResult, setBootstrapResult] = useState(null)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
        setError(sessionError?.message || 'No active auth session was found.')
        setLoading(false)
        return
      }

      try {
        const currentUser = await fetchCurrentUser(data.session.access_token, { backendUrl })
        if (!ignore) {
          setUser(currentUser)
          setSessionToken(data.session.access_token)
        }
      } catch (verifyError) {
        if (!ignore) {
          setError(verifyError.message)
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
    if (!supabase) {
      return
    }
    setLoading(true)
    setError('')
    await supabase.auth.signOut()
    setUser(null)
    setSessionToken('')
    setBootstrapResult(null)
    setLoading(false)
  }

  async function handleBootstrapProfile() {
    if (!sessionToken) {
      setError('No active auth session was found.')
      return
    }

    setBootstrapLoading(true)
    setError('')
    try {
      const result = await bootstrapProfile(sessionToken, { backendUrl })
      setBootstrapResult(result)
    } catch (bootstrapError) {
      setError(bootstrapError.message)
    } finally {
      setBootstrapLoading(false)
    }
  }

  return (
    <AuthShell title="Account">
      {loading && <p className="auth-message info">Loading...</p>}
      <AuthMessage message={error} tone="error" />
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
          onClick={handleBootstrapProfile}
          disabled={bootstrapLoading}
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
      <button className="auth-secondary-button" type="button" onClick={handleLogout} disabled={!supabase || loading}>
        <LogOut size={18} aria-hidden="true" />
        Logout
      </button>
      <AuthLinks />
    </AuthShell>
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
