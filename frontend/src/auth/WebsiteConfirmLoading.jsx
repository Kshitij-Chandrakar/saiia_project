import { Check, LockKeyhole } from 'lucide-react'
import { Link } from 'react-router-dom'
import mascot from '../assets/website-confirm/secure-email-mascot.png'
import unavailableMascot from '../assets/website-confirm/link-unavailable-mascot.png'
import brandMascot from '../assets/website-login/mascot.png'
import './website-confirm-loading.css'

export default function WebsiteConfirmLoading({ result }) {
  const verified = result?.status === 'verified'
  const unavailable = result?.reason === 'email_link_expired'
  return <main className="website-confirm-loading" aria-labelledby="confirm-loading-title">
    <div className="website-confirm-loading__decoration" aria-hidden="true"><span /><span /></div>
    <div className="website-confirm-loading__brand"><img src={brandMascot} alt="" /><span>Intervucopilot</span></div>
    <section className="website-confirm-loading__card" aria-busy={!result}>
      <div className="website-confirm-loading__content">
        <div className="website-confirm-loading__illustration">
          <img className="website-confirm-loading__mascot" src={unavailable ? unavailableMascot : mascot} alt="" width="140" height="140" />
          {verified && <span className="website-confirm-loading__check" aria-hidden="true"><Check size={20} /></span>}
        </div>
        <h1 id="confirm-loading-title">{unavailable ? 'Link unavailable' : verified ? 'Email verified' : 'Checking your secure link…'}</h1>
        <p role={result ? 'status' : undefined} aria-live={result ? 'polite' : undefined}>{unavailable ? 'This link has expired or already been used' : verified ? 'Your Intervucopilot account is ready.' : 'Please wait while we verify your email link.'}</p>
        {unavailable ? <Link className="website-confirm-loading__continue" to="/auth/login">Back to sign in</Link> : verified ? <Link className="website-confirm-loading__continue" to={result.href}>Continue</Link> : <div className="website-confirm-loading__status" role="status" aria-live="polite">
          <span className="website-confirm-loading__spinner" aria-hidden="true" />
          <span>Verifying link</span>
        </div>}
      </div>
      <footer><LockKeyhole size={18} aria-hidden="true" /><span>Secure email verification</span></footer>
    </section>
  </main>
}
