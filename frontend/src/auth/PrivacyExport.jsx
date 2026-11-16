import { useEffect, useRef, useState } from 'react'

// Explicit default-closed enablement; server composition remains independently required.
export default function PrivacyExport({ user, client, backendUrl = '', enabled = false, operationScope = 'export' }) {
  const exporting = operationScope === 'export'
  const title = exporting ? 'Export your account data' : operationScope === 'history' ? 'Erase all session history' : 'Erase one full session'
  const confirmationWord = exporting ? 'export' : 'delete'
  const prefix = `privacy-${operationScope}`
  const [selected, setSelected] = useState(''), [choices, setChoices] = useState([]), [nextCursor, setNextCursor] = useState(null)
  const [open, setOpen] = useState(false), [text, setText] = useState('')
  const [password, setPassword] = useState(''), [code, setCode] = useState('')
  const [ready, setReady] = useState(false), [sent, setSent] = useState(false)
  const [pending, setPending] = useState(false), [error, setError] = useState('')
  const [status, setStatus] = useState(null), [requestId, setRequestId] = useState(() => {
    try { const id = enabled ? sessionStorage.getItem(`intervucopilot.${operationScope}-request.${user.user_id || user.id}`) : null; return /^[0-9a-f-]{36}$/.test(id || '') ? id : null } catch { return null }
  })
  const dialog = useRef(null), trigger = useRef(null), locked = useRef(false), epoch = useRef(0)
  const requests = useRef(new Set()), notBefore = useRef(0)
  const [google, setGoogle] = useState(false)
  useEffect(() => {
    const lifecycle = epoch
    let alive = true
    function classify(session) {
      if (!alive || session?.user?.id !== (user.user_id || user.id)) return
      const providers = session.user.app_metadata?.providers || []
      setGoogle(providers.includes('google') && !providers.includes('email'))
    }
    void client?.auth.getSession().then(({ data }) => classify(data.session))
    const activeRequests = requests.current
    const subscription = client?.auth.onAuthStateChange((_event, session) => {
      classify(session)
      if (session?.user?.id !== (user.user_id || user.id)) {
        for (const controller of activeRequests) controller.abort()
        activeRequests.clear()
        epoch.current++; setOpen(false); setStatus(null); setRequestId(null); setPassword(''); setCode(''); setReady(false)
      }
    }).data.subscription
    return () => { alive = false; lifecycle.current++; for (const controller of activeRequests) controller.abort(); activeRequests.clear(); subscription?.unsubscribe() }
  }, [user.id, user.user_id, client])
  useEffect(() => {
    if (open) { dialog.current?.showModal(); dialog.current?.querySelector('h2')?.focus() }
    else if (dialog.current?.open) { dialog.current.close(); trigger.current?.focus() }
  }, [open])
  async function call(action, id = requestId, extra = {}) {
    const { data } = await client.auth.getSession()
    if (data.session?.user?.id !== (user.user_id || user.id)) throw new Error('Account changed. Start again.')
    const controller = new AbortController()
    requests.current.add(controller)
    try {
    const response = await fetch(`${backendUrl}/api/privacy/content/${action}`, {
      method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${data.session.access_token}` },
      signal: controller.signal,
      body: JSON.stringify({ request_id: id, operation_scope: operationScope, resource_id: operationScope === 'session' ? selected || null : null, ...extra }),
    })
    if (!response.ok) throw new Error('The operation is unavailable or blocked. No operation completion has been verified.')
    return await (action === 'download' ? response.blob() : response.json())
    } finally { requests.current.delete(controller) }
  }
  async function perform(work) {
    if (locked.current) return
    locked.current = true; setPending(true); setError('')
    const ticket = epoch.current
    const current = () => ticket === epoch.current
    try { await work(current) } catch (e) { if (current()) setError(e.message || 'Outcome unknown. Refresh status before retrying.') }
    finally { locked.current = false; if (current()) setPending(false) }
  }
  function loadSessions(cursor = null) {
    void perform(async current => {
      const result = await call('sessions', crypto.randomUUID(), { cursor })
      if (current()) { setChoices(result.sessions); setNextCursor(result.next_cursor); setSelected('') }
    })
  }
  function start() {
    void perform(async current => {
      const id = crypto.randomUUID()
      const begun = await call('begin', id)
      notBefore.current = Number(begun.not_before || 0) * 1000
      if (current()) { setRequestId(id); try { sessionStorage.setItem(`intervucopilot.${operationScope}-request.${user.user_id || user.id}`, id) } catch { /* In-memory request remains usable. */ } setText(''); setReady(false); setSent(false); setOpen(true) }
    })
  }
  function verify() {
    void perform(async current => {
      if (google) {
        await call('otp_verify', requestId, { code })
      } else {
        await new Promise(resolve => setTimeout(resolve, Math.max(0, notBefore.current - Date.now()) + 50))
        if (!current()) return
        const { error } = await client.auth.signInWithPassword({ email: user.email, password })
        if (error) throw new Error('Password verification failed.')
      }
      if (current()) { setReady(true); setText(''); setPassword(''); setCode('') }
    })
  }
  function confirm() {
    if (!ready || text !== confirmationWord) return
    void perform(async current => {
      await call('confirm', requestId, { confirmation_text: text })
      if (current()) { setOpen(false); setStatus(previous => previous?.state === 'ready' ? previous : { state: 'pending' }) }
    })
  }
  function download() {
    void perform(async current => {
      const { capability } = await call('authorize')
      const blob = await call('download', requestId, { capability })
      if (!current()) return
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      anchor.href = url; anchor.download = 'account-export.zip'; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
  }
  return <section className="privacy-export" aria-labelledby={`${prefix}-title`}>
    <h2 id={`${prefix}-title`}>{title}</h2>
    {exporting ? <p>Download a private copy of your approved account data and original resume files. It expires 24 hours after it is ready.</p> : operationScope === 'history' ? <p>Remove all interview history, including transcripts, answers, notes, Ask AI and saved answers. Reusable resumes, profile and job contexts remain.</p> : <p>Remove one interview and its transcripts, answers, notes, Ask AI and saved answers. Other interviews and reusable profile resources remain.</p>}
    {!enabled && <p role="status">This privacy control is not available yet. Local verification and external acceptance are still required.</p>}
    {operationScope === 'session' && <><button disabled={!enabled || pending} onClick={() => loadSessions()}>Load your sessions</button><label htmlFor={`${prefix}-selection`}>Session to erase</label><select id={`${prefix}-selection`} value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select a session</option>{choices.map(item => <option key={item.id} value={item.id}>{item.title || 'Untitled session'}</option>)}</select>{nextCursor && <button disabled={pending} onClick={() => loadSessions(nextCursor)}>Next sessions</button>}</>}
    <button ref={trigger} disabled={!enabled || pending || (operationScope === 'session' && !selected)} onClick={start}>{exporting ? 'Request account export' : title}</button>
    {requestId && !status && <button disabled={!enabled || pending} onClick={() => perform(async current => { const result = await call('status'); if (current()) setStatus(result) })}>Check export request status</button>}
    {status && <div role="status"><p>{exporting ? 'Export' : 'Erasure'} status: {status.state}. This is not account deletion.</p>
      {status.expires_at && <p>Expires: {new Date(status.expires_at).toLocaleString()}</p>}
      <button disabled={pending} onClick={() => perform(async current => { const result = await call('status'); if (current()) setStatus(result) })}>Refresh export status</button>
      {exporting && <button disabled={pending || status.state !== 'ready'} onClick={download}>Download private archive</button>}
      {exporting && <button disabled={pending || status.state !== 'ready'} onClick={() => perform(async current => { const begun = await call('download_begin'); notBefore.current = Number(begun.not_before || 0) * 1000; if (current()) { setOpen(true); setReady(false); setSent(false); setText('') } })}>Verify identity for download</button>}
    </div>}
    {exporting && <p>Deletion stops new download authorization and further delivery where possible. Files or bytes already delivered cannot be recalled.</p>}
    {error && <p role="alert">{error}</p>}
    <dialog ref={dialog} className="privacy-dialog" aria-labelledby={`${prefix}-dialog-title`} onCancel={event => { if (pending) event.preventDefault(); else setOpen(false) }}>
      <h2 id={`${prefix}-dialog-title`} tabIndex={-1}>{exporting ? 'Confirm your account export' : `Confirm: ${title}`}</h2>
      {exporting ? <p>Only your own allowlisted content is included. Credentials, internal support notes and numeric embeddings are excluded. No archive is emailed.</p> : <p>This privacy erasure includes contained saved answers and cannot be undone after acceptance. Other resources stay available. Acceptance and verified cleanup are separate states.</p>}
      {google ? <><p>Fresh mailbox verification is not Google reauthentication or MFA.</p>
        <button disabled={pending} onClick={() => perform(async current => { await call('otp_start'); if (current()) setSent(true) })}>{sent ? 'Resend mailbox code' : 'Send mailbox code'}</button>
        <label htmlFor={`${prefix}-code`}>Mailbox code</label><input id={`${prefix}-code`} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} />
      </> : <><label htmlFor={`${prefix}-password`}>Verify your password</label><input id={`${prefix}-password`} type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></>}
      <button disabled={pending || (google ? code.length !== 8 : !password)} onClick={verify}>Verify identity</button>
      <label htmlFor={`${prefix}-confirm`}>Type <code>{confirmationWord}</code> to confirm</label><input id={`${prefix}-confirm`} value={text} disabled={!ready || pending} onChange={e => setText(e.target.value)} autoComplete="off" />
      {pending && <p role="status">Request in progress. Completion has not been verified.</p>}
      {error && <p role="alert">{error}</p>}
      <footer><button disabled={pending} onClick={() => setOpen(false)}>Cancel</button><button disabled={pending || !ready || text !== confirmationWord} onClick={confirm}>{exporting ? 'Create private export' : 'Yes, erase selected history'}</button></footer>
    </dialog>
  </section>
}
