import { useCallback, useEffect, useRef, useState } from 'react'
import { TriangleAlert } from 'lucide-react'
import DashboardLayout from './DashboardLayout'
import { supabase } from './supabaseClient'
import { PRIVACY_ENABLED, PRIVACY_EXPORT_ENABLED, newPrivacyRequest, privacyRequest, savePrivacyReceipt, readPrivacyReceipt, clearDeletedBrowserState } from './privacyApi'
import './privacy.css'
import PrivacyExport from './PrivacyExport'
import PrivacyOverview from './PrivacyOverview'
import { publishAccountRestriction } from './accountOwnedCleanup'

export default function WebsiteSettings({ user, backendUrl = '', client = supabase, enabled = PRIVACY_ENABLED, exportEnabled = PRIVACY_EXPORT_ENABLED }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [factor, setFactor] = useState(null)
  const [googleOnly, setGoogleOnly] = useState(false)
  const [emailSent, setEmailSent] = useState(false)
  const [retryProof, setRetryProof] = useState(false)
  const [ready, setReady] = useState(false)
  const [expiresAt, setExpiresAt] = useState(0)
  const [pending, setPending] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef(null), cancel = useRef(null), lock = useRef(false)
  const epoch = useRef(0), session = useRef(null), document = useRef(null)
  const intent = useRef(null), proof = useRef(null)
  const account = user.user_id || user.id
  useEffect(() => {
    let alive = true
    const lifecycle = epoch
    const subscription = client?.auth.onAuthStateChange((_event, next) => {
      if (next?.user?.id === account) { session.current = next; return }
      epoch.current++; session.current = null; document.current = null; intent.current = null; proof.current = null
      if (alive) { setReady(false); setEmailSent(false); setRetryProof(false); setPassword(''); setCode(''); setText(''); setOpen(false) }
    }).data.subscription
    void client?.auth.getSession().then(({ data }) => { if (alive && data.session?.user?.id === account) {
      session.current = data.session
      const providers = data.session.user.app_metadata?.providers || []
      setGoogleOnly(providers.includes('google') && !providers.includes('email'))
    } })
    void client?.auth.mfa?.listFactors().then(({ data }) => { if (alive) setFactor(data?.totp?.find(item => item.status === 'verified')?.id || null) }).catch(() => {})
    return () => { alive = false; lifecycle.current++; session.current = null; subscription?.unsubscribe() }
  }, [client, account])
  useEffect(() => {
    if (!ready) return
    const timer = setTimeout(() => { setReady(false); setEmailSent(false); setRetryProof(false); document.current = null; intent.current = null; proof.current = null; setError('Confirmation expired. Verify your identity again before confirming.') }, Math.max(0, expiresAt - Date.now()))
    return () => clearTimeout(timer)
  }, [ready, expiresAt])
  useEffect(() => {
    if (!open) return
    const node = dialog.current, trigger = globalThis.document.activeElement
    node.showModal(); node.querySelector('#delete-title').focus({ preventScroll: true }); node.scrollTop = 0
    return () => { node.close(); trigger?.focus() }
  }, [open])
  function cancelVerification() { setPassword(''); setCode(''); setOpen(false) }
  async function authenticate() {
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    const ticket = epoch.current
    try {
      const request = document.current || newPrivacyRequest()
      document.current = request
      if (!intent.current) {
        const started = await privacyRequest('begin', request, session.current?.access_token, backendUrl)
        if (ticket !== epoch.current) return
        intent.current = started
      }
      const notBefore = Date.parse(intent.current.not_before)
      if (Number.isFinite(notBefore)) await new Promise(resolve => setTimeout(resolve, Math.max(0, notBefore - Date.now()) + 50))
      if (ticket !== epoch.current) return
      if (googleOnly && !factor) {
        savePrivacyReceipt(request)
        const action = retryProof ? 'otp_ready' : emailSent ? 'otp_verify' : 'otp_start'
        if (action === 'otp_start') setEmailSent(true)
        const result = await privacyRequest(action, { ...request, ...(action === 'otp_verify' ? { code } : {}) }, session.current?.access_token, backendUrl)
        if (ticket !== epoch.current) return
        if (result.state === 'otp_sent') { setEmailSent(true); return }
        if (result.state !== 'awaiting_confirmation') {
          const failure = Error(result.state === 'otp_limited' ? 'Too many code requests. Wait before sending again.' : 'Code was not accepted. Check the code or request another after 60 seconds.')
          failure.definite = true; throw failure
        }
        const expiry = Date.parse(result.expires_at)
        if (!Number.isFinite(expiry) || expiry <= Date.now()) throw Error('Verification expired. Request another code.')
        setExpiresAt(expiry); setText(''); setReady(true); setRetryProof(false)
        return
      }
      let authenticated
      if (proof.current) authenticated = { data: { session: proof.current } }
      else if (googleOnly) {
        if (!factor) throw Error('Secure reauthentication is unavailable for this Google account. No deletion was accepted. You do not need to create a password.')
        const verified = await client.auth.mfa.challengeAndVerify({ factorId: factor, code })
        setCode('')
        if (verified.error) throw Error('Could not verify your authenticator code. No deletion was accepted.')
        authenticated = await client.auth.getSession()
      } else authenticated = await client.auth.signInWithPassword({ email: user.email, password })
      const { data, error: authError } = authenticated
      setPassword(''); setCode('')
      if (authError || data.session?.user?.id !== account) throw Error('Identity verification failed or a different account was returned. No deletion was accepted.')
      if (ticket !== epoch.current) return
      session.current = data.session
      proof.current = data.session; setRetryProof(true)
      savePrivacyReceipt(request)
      const challenge = await privacyRequest('challenge', request, data.session.access_token, backendUrl)
      const expiry = Date.parse(challenge.expires_at)
      if (!Number.isFinite(expiry) || expiry <= Date.now()) throw Error('Confirmation expired. Reauthenticate before confirming.')
      if (ticket === epoch.current) { setExpiresAt(expiry); setReady(true); setRetryProof(false) }
    } catch (failure) { if (ticket === epoch.current) {
      if (googleOnly && !factor && emailSent) setRetryProof(!failure.definite && failure.status !== 403)
      if (Date.parse(intent.current?.expires_at) <= Date.now()) { document.current = null; intent.current = null; proof.current = null; setEmailSent(false); setRetryProof(false) }
      setError(failure.message)
    } }
    finally { lock.current = false; if (ticket === epoch.current) { setPending(false); setPassword(''); setCode('') } }
  }
  async function finish(result, ticket) {
    if (ticket !== epoch.current || result.state !== 'accepted_restricted') throw Error('Deletion acceptance has not been confirmed. Check request status.')
    clearDeletedBrowserState(account, user.email, client.auth.storageKey)
    publishAccountRestriction(account)
    client.auth.stopAutoRefresh?.()
    // Leave the product surface before SDK auth callbacks can rerender old data.
    // Destroy SDK/in-memory state without invalidating the encrypted worker's
    // session credential first. Durable global logout owns the Auth operation.
    globalThis.location.replace('/auth/privacy-status')
  }
  async function confirm() {
    if (lock.current || text !== 'delete' || !ready || Date.now() >= expiresAt) return
    lock.current = true; setPending(true); setError('')
    const ticket = epoch.current
    try {
      const result = await privacyRequest('confirm', { ...document.current, confirmation_text: text, proof_method: googleOnly && !factor ? 'email_otp' : 'reauthentication' }, session.current?.access_token, backendUrl)
      await finish(result, ticket)
    } catch (failure) {
      if (ticket === epoch.current) { setUncertain(true); setError(failure.message) }
    } finally { lock.current = false; if (ticket === epoch.current) setPending(false) }
  }
  async function recover() {
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    const ticket = epoch.current
    try {
      const result = await privacyRequest('status', readPrivacyReceipt(), null, backendUrl)
      if (result.state === 'accepted_restricted') await finish(result, ticket)
      else if (ticket === epoch.current) { setUncertain(false); setError('Final confirmation was not accepted. Reauthenticate if the confirmation expired.') }
    } catch { if (ticket === epoch.current) setError('The request outcome is still unknown. Check again before making another request.') }
    finally { lock.current = false; if (ticket === epoch.current) setPending(false) }
  }
  return <DashboardLayout user={user} backendUrl={backendUrl} title="Settings" description="Manage your account privacy.">
    <PrivacyOverview />
    <PrivacyExport enabled={exportEnabled} key={user.user_id || user.id} user={user} client={client} backendUrl={backendUrl} />
    <PrivacyExport key={`session-${account}`} user={user} client={client} backendUrl={backendUrl} enabled={exportEnabled} operationScope="session" />
    <PrivacyExport key={`history-${account}`} user={user} client={client} backendUrl={backendUrl} enabled={exportEnabled} operationScope="history" />
    <section className="privacy-danger" aria-labelledby="danger-title"><h2 id="danger-title">Danger Zone</h2>
      <p>Deleting your account permanently restricts access. Once final confirmation is accepted, it cannot be undone.</p>
      {!enabled && <p role="status">Account deletion is not available yet. Cleanup and authentication safeguards must be verified before it is enabled.</p>}
      <button className="privacy-delete" disabled={!enabled} onClick={() => { setText(''); setError(''); setOpen(true) }}>Delete Account</button>
    </section>
    {open && <dialog ref={dialog} className="privacy-dialog" aria-labelledby="delete-title" aria-describedby="delete-description" onKeyDown={event => {
      if (event.key !== 'Tab') return
      const controls = [...dialog.current.querySelectorAll('button:not([disabled]),input:not([disabled]),a[href]')]
      const first = controls[0], last = controls.at(-1)
      if (event.shiftKey && globalThis.document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && globalThis.document.activeElement === last) { event.preventDefault(); first?.focus() }
    }} onCancel={event => { if (pending || uncertain) event.preventDefault(); else cancelVerification() }}>
      <div className="privacy-heading"><span className="privacy-warning"><TriangleAlert size={24} aria-hidden="true" /></span><h2 id="delete-title" tabIndex={-1}>Delete your account?</h2></div>
      <div id="delete-description" className="privacy-consequences"><p>You will lose product access immediately after acceptance. There is no undo, and this email address will be permanently blocked from signing up again, including with Google.</p>
        <p>Personal-content cleanup is targeted within 24 hours. Minimized usage records remain for 90 days and security records for 180 days. The restricted email-matching identifier is retained permanently.</p>
        <p>Necessary billing records may remain while cancellation is unresolved. Deleting your account does not confirm cancellation or prevent future charges. Backups and processor copies are not confirmed erased.</p>
        <p>Account deletion does not initiate a refund. The no-refund policy applies except where a refund is required by applicable law.</p></div>
      {!ready && <div className="privacy-reauth">{googleOnly ? <>
        {factor ? <><label htmlFor="privacy-code">Authenticator code</label><input id="privacy-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} disabled={pending} onChange={event => setCode(event.target.value)} /><p>Verify your existing authenticator to continue. Google sign-in alone does not prove recent user presence.</p></> : <><p>A fresh code to your verified account email proves mailbox control. This is not Google reauthentication or MFA. Codes expire within five minutes; final typed confirmation is still required.</p>{emailSent && <><label htmlFor="privacy-email-code">Email confirmation code</label><input id="privacy-email-code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} disabled={pending} onChange={event => setCode(event.target.value)} /><button disabled={pending} onClick={() => { setEmailSent(false); setCode(''); setRetryProof(false) }}>Request another code</button></>}</>}
      </> : <><label htmlFor="privacy-password">Reauthenticate with your password</label><input id="privacy-password" type="password" autoComplete="current-password" value={password} disabled={pending} onChange={event => setPassword(event.target.value)} /><p>Typing delete does not verify your identity.</p></>}
        {retryProof && <p role="status">Verification outcome is unknown. Retry the same identity confirmation; deletion will still require your final confirmation.</p>}
        <button disabled={pending || (!retryProof && (googleOnly ? factor ? !/^\d{6}$/.test(code) : emailSent && !/^\d{8}$/.test(code) : !password))} onClick={authenticate}>{pending ? 'Verifying…' : retryProof ? 'Retry identity confirmation' : googleOnly && !factor ? emailSent ? 'Verify email code' : 'Send email code' : 'Verify identity'}</button></div>}
      {ready && <p role="status">Identity verified. {googleOnly && !factor ? 'Mailbox control only; not Google reauthentication or MFA. ' : ''}Final confirmation expires within five minutes.</p>}
      <label htmlFor="privacy-confirm">Type <code>delete</code> to confirm</label><input id="privacy-confirm" autoComplete="off" value={text} disabled={pending || uncertain} onChange={event => setText(event.target.value)} />
      {error && <p role="alert" className="privacy-error">{error}</p>}
      {uncertain && <button disabled={pending} onClick={recover}>Check request status</button>}
      <footer><button ref={cancel} disabled={pending || uncertain} onClick={cancelVerification}>Cancel</button><button className="privacy-delete" disabled={pending || uncertain || !ready || text !== 'delete'} onClick={confirm}>{pending ? 'Confirming…' : 'Yes, Delete My Account'}</button></footer>
    </dialog>}
  </DashboardLayout>
}

export function PrivacyStatus({ backendUrl = '' }) {
  const [result, setResult] = useState(null), [error, setError] = useState('')
  const sequence = useRef(0), retryTimer = useRef(null)
  const refresh = useCallback(async function load(attempt = 0) {
    const ticket = ++sequence.current
    clearTimeout(retryTimer.current)
    try {
      const receipt = readPrivacyReceipt()
      if (!receipt) throw Error()
      const value = await privacyRequest('status', receipt, null, backendUrl)
      if (ticket === sequence.current) { setResult(value); setError('') }
    } catch {
      if (ticket !== sequence.current) return
      if (attempt < 5) retryTimer.current = setTimeout(() => void load(attempt + 1), 1000)
      else setError('Request status is unavailable. No completion has been verified. Your receipt grants no product access.')
    }
  }, [backendUrl])
  useEffect(() => {
    const lifecycle = sequence
    if (readPrivacyReceipt()) void refresh()
    else setError('No request receipt is available in this browser tab.')
    return () => { lifecycle.current++; clearTimeout(retryTimer.current) }
  }, [refresh])
  return <main className="privacy-status"><h1>Account deletion request</h1>{result?.state === 'accepted_restricted' ? <><h2>Request accepted. Product access is restricted.</h2><p>{result.primary_content_verified ? 'Controlled primary content removal is verified; retained obligations remain pending.' : ({ blocked: 'Personal-content cleanup needs follow-up; completion has not been verified.', failed: 'Personal-content cleanup failed; completion has not been verified.', running: 'Personal-content cleanup is in progress; completion has not been verified.', pending: 'Personal-content cleanup is pending.' })[result.cleanup_state] || 'Personal-content cleanup status is unknown; completion has not been verified.'} Session revocation: {({ succeeded: 'refresh sessions revoked', blocked: 'requires follow-up', running: 'in progress', pending: 'pending' })[result.session_revocation] || 'pending'}. Auth cleanup: {({ succeeded: 'original identity fields removed; a restricted tombstone remains', blocked: result.identity_cleanup_reason === 'billing_contact_required' ? 'retained for billing resolution' : 'requires follow-up', running: 'in progress', pending: 'pending', not_scheduled: 'not scheduled' })[result.identity_cleanup] || 'unverified'}. This does not confirm that all files, backups or processor copies have been erased.</p><p>Subscription cancellation is unverified. Further charges may remain possible while billing resolution is pending.</p></> : <p>No accepted deletion has been verified.</p>}{error && <p role="alert">{error}</p>}<button onClick={() => void refresh()}>Refresh request status</button></main>
}
