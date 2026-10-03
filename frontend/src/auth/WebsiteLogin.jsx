import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import brandMark from '../assets/landing/header-logo-mark.svg'
import mascot from '../assets/website-login/mascot.png'
import background from '../assets/website-login/background.svg'
import guidance from '../assets/website-login/guidance.svg'
import resume from '../assets/website-login/resume.svg'
import targetRole from '../assets/website-login/target-role.svg'
import google from '../assets/website-login/google.svg'
import emailIcon from '../assets/website-login/email.svg'
import lock from '../assets/website-login/lock.svg'
import eye from '../assets/website-login/eye.svg'
import arrow from '../assets/website-login/arrow.svg'
import microphone from '../assets/website-login/microphone.svg'
import rubric from '../assets/website-login/rubric.svg'
import './website-login.css'

function Badge({ className, icon, title, children, position }) {
  return <div className={`website-login__badge ${className}`} style={{ offsetDistance: `${position}%` }}>
    <span className="website-login__badge-icon"><img src={icon} alt="" /></span>
    <span><strong>{title}</strong><span>{children}</span></span>
  </div>
}

export default function WebsiteLogin({ form, checkingSession, configured, onSubmit, onGoogleLogin, authMessage, desktopError = '', blocked = false, signupHref = '/auth/signup' }) {
  const [rotation, setRotation] = useState(0)
  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: no-preference) and (min-width: 901px)')
    let interval
    function syncRotation() {
      clearInterval(interval)
      if (motion.matches) interval = setInterval(() => setRotation((step) => step + 1), 3000)
    }
    syncRotation()
    motion.addEventListener('change', syncRotation)
    return () => {
      clearInterval(interval)
      motion.removeEventListener('change', syncRotation)
    }
  }, [])
  // Increasing distances keep the wrap from bottom-left to top-right clockwise.
  const orbit = [87.5, 112.5, 137.5]
  const position = (start) => orbit[(rotation + start) % 3] + Math.floor((rotation + start) / 3) * 100
  const [rememberedEmail, setRememberedEmail] = useState(() => {
    try { return localStorage.getItem('intervucopilot.login-email') || '' } catch { return '' }
  })
  const [rememberEmail, setRememberEmail] = useState(Boolean(rememberedEmail))
  useEffect(() => {
    if (rememberedEmail) form.setEmail(rememberedEmail)
  }, [rememberedEmail, form.setEmail])
  const [legalNotice, setLegalNotice] = useState('')
  const [visible, setVisible] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const busy = checkingSession || form.loading || googleLoading
  const disabled = !configured || busy || blocked

  function handleSubmit(event) {
    try {
      if (rememberEmail) localStorage.setItem('intervucopilot.login-email', form.email.trim())
      else localStorage.removeItem('intervucopilot.login-email')
    } catch { /* Storage restrictions must not prevent sign-in. */ }
    onSubmit(event)
  }

  async function handleGoogle() {
    setGoogleLoading(true)
    try { await onGoogleLogin() } finally { setGoogleLoading(false) }
  }

  return (
    <main className="website-login" data-node-id="370:6793">
      <aside className="website-login__story" aria-label="Interview preparation with Intervucopilot">
        <img className="website-login__background" src={background} alt="" />
        <div className="website-login__story-content">
          <h2>Your next interview starts with confidence.</h2>
          <p>Your experience, target role, and rehearsal feedback—everything synthesized in one ambient workspace.</p>
          <div className="website-login__stage">
            <div className="website-login__glow" />
            <div className="website-login__ring"><div /></div>
            <div className="website-login__mascot"><img src={mascot} alt="Friendly AI robot with a glowing cyan smile and headset" /></div>
            <Badge className="website-login__guidance" icon={guidance} title="AI Guidance" position={position(0)}>Context-aware prompts</Badge>
            <Badge className="website-login__resume" icon={resume} title="Resume indexed" position={position(2)}>4.2 MB parsed</Badge>
            <Badge className="website-login__target" icon={targetRole} title="Target Role" position={position(1)}>Rubric mapped</Badge>
          </div>
        </div>
      </aside>
      <section className="website-login__credentials" aria-labelledby="website-login-title">
        <div className="website-login__content">
          <Link to="/" className="website-login__brand" aria-label="Intervucopilot home"><span className="website-login__brand-icon"><img src={brandMark} alt="" /></span><span>Intervucopilot</span></Link>
          <header><h1 id="website-login-title">Welcome back!</h1><p>Continue your interview preparation journey with Intervucopilot.</p></header>
          <div className="website-login__messages" aria-live="polite">
            {!configured && <p role="alert">Supabase auth is not configured for this build.</p>}
            {checkingSession && <p role="status">Checking session...</p>}
            {authMessage && <p>{authMessage}</p>}
            {legalNotice && <p role="status">{legalNotice}</p>}
            {desktopError && <p role="alert">{desktopError}</p>}
            {form.error && <p role="alert">{form.error}</p>}
            {form.message && <p role="status">{form.message}</p>}
          </div>
          <button className="website-login__google" type="button" onClick={handleGoogle} disabled={disabled}>
            <img src={google} alt="" />{googleLoading ? 'Connecting to Google...' : 'Sign in with Google'}
          </button>
          <div className="website-login__divider"><span>OR SIGN IN WITH EMAIL</span></div>
          <form className="website-login__form" onSubmit={handleSubmit} aria-busy={busy}>
            <div className="website-login__field">
              <label htmlFor="website-login-email">Email Address</label>
              <div className="website-login__input"><img src={emailIcon} alt="" /><input id="website-login-email" type="email" value={form.email} onChange={(event) => form.setEmail(event.target.value)} autoComplete="email" placeholder="name@work-or-personal.com" required disabled={busy} /></div>
            </div>
            <div className="website-login__field">
              <div className="website-login__password-label"><label htmlFor="website-login-password">Password</label><Link to="/auth/forgot-password">Forgot password?</Link></div>
              <div className="website-login__input"><img src={lock} alt="" /><input id="website-login-password" type={visible ? 'text' : 'password'} value={form.password} onChange={(event) => form.setPassword(event.target.value)} autoComplete="current-password" placeholder="••••••••••••" required disabled={busy} /><button className="website-login__toggle" type="button" onClick={() => setVisible(!visible)} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}><img src={eye} alt="" /></button></div>
            </div>
            <label className="website-login__remember" title="Remember your email on this device. Account session persistence is unchanged."><input type="checkbox" checked={rememberEmail} disabled={busy || blocked} onChange={(event) => {
              setRememberEmail(event.target.checked)
              if (!event.target.checked) {
                setRememberedEmail('')
                try { localStorage.removeItem('intervucopilot.login-email') } catch { /* Storage may be restricted. */ }
              }
            }} />Remember email</label>
            <button className="website-login__submit" type="submit" disabled={disabled}>{form.loading ? 'Checking...' : 'Sign In'}<img src={arrow} alt="" /></button>
          </form>
          <footer className="website-login__footer">
            <p>Don't have an account? <Link to={signupHref}>Create free account</Link></p>
            <nav aria-label="Login information"><button type="button" onClick={() => setLegalNotice("Privacy Policy is not published yet.")}>Privacy Policy</button><span aria-hidden="true">•</span><button type="button" onClick={() => setLegalNotice("Terms of Service is not published yet.")}>Terms of Service</button></nav>
          </footer>
          <div className="website-login__features">
            <div><img src={microphone} alt="" /><span><strong>Voice AI Studio</strong><span>Low latency &lt;180ms</span></span></div>
            <div><img src={rubric} alt="" /><span><strong>Rubric Grading</strong><span>FAANG/Fortune 500</span></span></div>
          </div>
          <Link className="website-login__status" to="/auth/status">System status</Link>
        </div>
      </section>
    </main>
  )
}
