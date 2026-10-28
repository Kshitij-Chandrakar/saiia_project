import { customerWebsiteError } from './customerErrors'
import { useEffect, useRef, useState } from 'react'
import { supabase } from './supabaseClient'
import { fetchCloudResumeList } from './authApi'

// Saved files survive a downgrade. This selects access, never deletes files.
export default function ResumeAccessSelection({ user, backendUrl, refreshKey, onChanged }) {
  const [state, setState] = useState(null), [selected, setSelected] = useState([])
  const [pending, setPending] = useState(false), [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const active = useRef(true), lock = useRef(false), sequence = useRef(0)
  useEffect(() => {
    active.current = true
    const own = ++sequence.current, controller = new AbortController()
    setState(null); setSelected([]); setError('')
    async function load() {
      const session = await supabase?.auth.getSession()
      if (session?.data?.session?.user?.id !== user.user_id) return
      const token = session.data.session.access_token
      const response = await fetch(`${backendUrl}/api/account/subscription`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal, cache: 'no-store' })
      if (!response.ok) return // Account composition remains default-off.
      const account = await response.json()
      const cap = account.usage?.find(x => x.meter === 'resume.stored_files')
      if (cap?.mode !== 'limited' || BigInt(cap.used) <= BigInt(cap.allowance)) return
      const records = await fetchCloudResumeList(token, { backendUrl, signal: controller.signal })
      if (!active.current || own !== sequence.current) return
      setState({ records: records.filter(x => x.status === 'ready'), cap: Number(cap.allowance) })
      setSelected(records.filter(x => x.status === 'ready' && x.can_generate).map(x => x.id))
    }
    load().catch(() => { /* Existing resume status handles backend availability. */ })
    return () => { active.current = false; controller.abort() }
  }, [backendUrl, user.user_id, refreshKey])

  async function save(event) {
    event.preventDefault()
    if (lock.current || !state || !selected.length || selected.length > state.cap) return
    lock.current = true; setPending(true); setError('')
    const own = sequence.current
    try {
      const session = await supabase?.auth.getSession()
      if (!active.current || own !== sequence.current || session?.data?.session?.user?.id !== user.user_id) return
      const response = await fetch(`${backendUrl}/api/resumes/active-set`, { method: 'POST', headers: { Authorization: `Bearer ${session.data.session.access_token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ resume_ids: selected }), cache: 'no-store' })
      if (!active.current || own !== sequence.current) return
      if (!response.ok) throw Error('Could not update resume access. Refresh your plan and try again.')
      setNotice('Resume access updated.')
      onChanged()
    } catch (failure) { if (active.current && own === sequence.current) setError(customerWebsiteError(failure, 'Could not update resume access. Refresh your plan and try again.')) }
    finally { lock.current = false; if (active.current) setPending(false) }
  }
  if (!state) return null
  return <form className="wr-active-set" onSubmit={save}>
    <fieldset disabled={pending}><legend>Choose resumes for your current plan</legend>
      <p>Your saved resumes are kept. Choose up to {state.cap} for interviews. New uploads stay blocked while you have more stored resumes than your plan allows.</p>
      {state.records.map(record => <label key={record.id}><input type="checkbox" checked={selected.includes(record.id)} onChange={event => setSelected(ids => event.target.checked ? [...ids, record.id] : ids.filter(id => id !== record.id))} />{record.original_filename || 'Saved resume'}</label>)}
      <button type="submit" disabled={!selected.length || selected.length > state.cap}>{pending ? 'Saving resume access…' : 'Use selected resumes'}</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </form>
}
