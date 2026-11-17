import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import brandMark from '../assets/landing/header-logo-mark.svg'
import './website-login.css'
import SignupMascot from './SignupMascot'
import SignupVerificationNotice from './SignupVerificationNotice'
import background from '../assets/website-login/background.svg'
import google from '../assets/website-login/google.svg'
import emailIcon from '../assets/website-login/email.svg'
import lock from '../assets/website-login/lock.svg'
import eye from '../assets/website-login/eye.svg'
import arrow from '../assets/website-login/arrow.svg'
import microphone from '../assets/website-login/microphone.svg'
import rubric from '../assets/website-login/rubric.svg'
import './website-signup.css'

export default function WebsiteSignup({ form, checkingSession, configured, termsAccepted,
  setTermsAccepted, marketingEmailOptIn, setMarketingEmailOptIn, onSubmit, onGoogleLogin, verificationNoticeOpen, onDismissVerificationNotice }) {
  const [visible, setVisible] = useState(false)
  const [notice, setNotice] = useState('')
  const pending = useRef(false)
  const submitRef = useRef(null)
  const busy = checkingSession || form.loading
  const legal = (event, label) => { event.preventDefault(); setNotice(`${label} is not published yet.`) }
  const legalLink = (label) => <a href="#signup-legal-notice" onClick={event => legal(event, label)}>{label}</a>
  async function run(action, event) {
    event?.preventDefault()
    if (pending.current || busy || !configured) return
    pending.current = true
    if (!event) form.setLoading(true)
    try {
      const succeeded = await action(event)
      if (event && succeeded === true) setVisible(false)
    }
    catch { form.setError('Account creation could not be completed. Please try again.'); form.setLoading(false) }
    finally { pending.current = false; if (!event) form.setLoading(false) }
  }
  return <><main className="website-signup" data-node-id="402:5965">
    <aside className="website-signup__hero" aria-label="Interview preparation with Intervucopilot">
      <img className="website-signup__background" src={background} alt="" />
      <div className="website-signup__story">
        <h2>Your next interview starts with confidence.</h2>
        <p>Your experience, target role, and rehearsal feedback{String.fromCharCode(8212)}everything synthesized in one ambient workspace.</p>
        <div className="website-signup__stage"><div className="website-signup__glow" /><div className="website-signup__ring" /><SignupMascot /></div>
      </div>
    </aside>
    <section className="website-signup__credentials" aria-labelledby="signup-title">
      <div className="website-signup__content">
        <Link to="/" className="website-login__brand website-signup__brand" aria-label="Intervucopilot home"><span className="website-login__brand-icon"><img src={brandMark} alt="" /></span><span>Intervucopilot</span></Link>
        <header><h1 id="signup-title">Create your account</h1><p>Start your personalized interview preparation journey with Intervucopilot.</p></header>
        <div className="website-signup__messages" aria-live="polite">
          {!configured && <p role="alert">Sign-in is unavailable right now. Please try again later.</p>}
          {checkingSession && <p role="status">Checking session...</p>}
          {form.error && <p role="alert" id="signup-error">{form.error}</p>}
          {form.message && <p role="status">{form.message}</p>}
        </div>
        <button className="website-signup__google" type="button" disabled={busy || !configured} onClick={() => void run(onGoogleLogin)}><img src={google} alt="" />Sign in with Google</button>
        <div className="website-signup__divider"><span>OR SIGN UP WITH EMAIL</span></div>
        <form onSubmit={event => run(onSubmit, event)} aria-busy={busy}>
          <div className="website-signup__field"><label htmlFor="signup-email">Email</label><div className="website-signup__input"><img src={emailIcon} alt="" /><input id="signup-email" type="email" placeholder="Enter your email" autoComplete="email" required disabled={busy} value={form.email} onChange={event => { form.setEmail(event.target.value); form.setError('') }} aria-invalid={Boolean(form.error)} aria-describedby={form.error ? 'signup-error' : undefined} /></div></div>
          <div className="website-signup__field"><label htmlFor="signup-password">Password</label><div className="website-signup__input"><img src={lock} alt="" /><input id="signup-password" type={visible ? 'text' : 'password'} placeholder="Create a password" autoComplete="new-password" minLength={6} required disabled={busy} value={form.password} onChange={event => { form.setPassword(event.target.value); form.setError('') }} aria-invalid={Boolean(form.error)} aria-describedby={form.error ? 'signup-password-help signup-error' : 'signup-password-help'} /><button type="button" disabled={busy} onClick={() => setVisible(!visible)} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}><img src={eye} alt="" /></button></div><small id="signup-password-help">At least 6 characters.</small></div>
          <div className="website-signup__consents">
            <label><input type="checkbox" required checked={termsAccepted} disabled={busy} onChange={event => { setTermsAccepted(event.target.checked); form.setError('') }} /><span>I agree to the {legalLink('Terms & Conditions')} and {legalLink('Privacy Policy')}.</span></label>
            <label><input type="checkbox" checked={marketingEmailOptIn === true} disabled={busy} onChange={event => setMarketingEmailOptIn(event.target.checked)} /><span>I want to receive promotional, discount, and product emails.</span></label>
          </div>
          <button ref={submitRef} className="website-signup__submit" type="submit" disabled={busy || !configured}>{form.loading ? 'Creating...' : 'Create Account'}<img src={arrow} alt="" /></button>
        </form>
        <footer><p>Already have an account? <Link to="/auth/login">Sign in</Link></p><nav aria-label="Signup information">{legalLink('Privacy Policy')}<span aria-hidden="true">&bull;</span>{legalLink('Terms of Service')}</nav></footer>
        <div className="website-signup__features"><div><img src={microphone} alt="" /><span><strong>Voice AI Studio</strong><span>Low latency &lt;180ms</span></span></div><div><img src={rubric} alt="" /><span><strong>Rubric Grading</strong><span>FAANG/Fortune 500</span></span></div></div>
      </div>
    </section>
    {notice && <div className="website-signup__legal-notice" id="signup-legal-notice" role="status"><span>{notice}</span><button type="button" aria-label="Dismiss notice" onClick={() => setNotice('')}>Close</button></div>}
  </main>
    {verificationNoticeOpen && <SignupVerificationNotice onDismiss={onDismissVerificationNotice} returnFocusRef={submitRef} />}
  </>
}
