import { useEffect, useRef } from 'react'
import mascot from '../assets/website-signup/verification-mascot.png'
import './signup-verification-notice.css'

export default function SignupVerificationNotice({ onDismiss, returnFocusRef }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const returnTarget = returnFocusRef.current
    const dialog = dialogRef.current
    const body = document.body
    const overflow = body.style.overflow
    const paddingRight = body.style.paddingRight
    const gutter = window.innerWidth - document.documentElement.clientWidth
    body.style.overflow = 'hidden'
    if (gutter) body.style.paddingRight = `${parseFloat(getComputedStyle(body).paddingRight) + gutter}px`
    dialog.showModal()
    return () => {
      dialog.close()
      body.style.overflow = overflow
      body.style.paddingRight = paddingRight
      if (returnTarget?.isConnected) returnTarget.focus()
    }
  }, [returnFocusRef])

  return <dialog ref={dialogRef} className="signup-verification-notice"
    aria-labelledby="signup-verification-title" aria-describedby="signup-verification-description"
    aria-modal="true" onCancel={event => { event.preventDefault(); onDismiss() }}>
    <div className="signup-verification-notice__content">
      <img src={mascot} alt="" width="112" height="97" />
      <h2 id="signup-verification-title">Check your email</h2>
      <p id="signup-verification-description">Check your email to verify your account.</p>
      <button type="button" autoFocus onClick={onDismiss}>Got it</button>
    </div>
  </dialog>
}
