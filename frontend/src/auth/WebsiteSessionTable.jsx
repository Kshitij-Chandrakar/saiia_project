import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import WebsiteSessionViewer from './WebsiteSessionViewer'
import sessionIcon from '../assets/dashboard/session.svg'
import moreIcon from '../assets/dashboard/more.svg'
import searchIcon from '../assets/dashboard/search.svg'
import { SkeletonRows } from './WebsiteSkeleton'

export function sessionDuration(session) {
  if (!session.started_at || !session.ended_at) return 'Unavailable'
  const milliseconds = Date.parse(session.ended_at) - Date.parse(session.started_at)
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return 'Unavailable'
  const seconds = Math.floor(milliseconds / 1000)
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function sessionSubtitle(session) {
  const title = (session.title || session.target_role || session.company_name || '').trim().toLowerCase()
  return [...new Set([session.target_role, session.company_name].filter(Boolean).map(value => value.trim()))]
    .filter(value => value.toLowerCase() !== title).join(' / ')
}

function RowMenu({ trigger, actions, close }) {
  const menu = useRef(null)
  const [position, setPosition] = useState(null)
  useLayoutEffect(() => {
    const updatePosition = () => {
      const rect = trigger.getBoundingClientRect()
      const height = menu.current.getBoundingClientRect().height
      setPosition({ left: Math.max(8, Math.min(rect.right - 220, window.innerWidth - 228)), top: Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - height - 8)) })
    }
    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => { window.removeEventListener('resize', updatePosition); window.removeEventListener('scroll', updatePosition, true) }
  }, [trigger])
  const focused = useRef(false)
  useEffect(() => { if (position && !focused.current) { focused.current = true; menu.current.querySelector('button:not(:disabled)')?.focus({ preventScroll:true }) } }, [position])
  useEffect(() => {
    const outside = (event) => { if (!menu.current?.contains(event.target) && !trigger.contains(event.target)) close(false) }
    document.addEventListener('pointerdown', outside)
    return () => { document.removeEventListener('pointerdown', outside) }
  }, [trigger, close])
  function keyboard(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(true); return }
    if (event.key === 'Tab') { close(true); return }
    const buttons = [...menu.current.querySelectorAll('button:not(:disabled)')]
    let index = buttons.indexOf(document.activeElement)
    if (event.key === 'ArrowDown') index = (index + 1) % buttons.length
    else if (event.key === 'ArrowUp') index = (index - 1 + buttons.length) % buttons.length
    else if (event.key === 'Home') index = 0
    else if (event.key === 'End') index = buttons.length - 1
    else return
    event.preventDefault(); buttons[index]?.focus({ preventScroll:true })
  }
  return createPortal(<div ref={menu} className="website-dashboard wd-row-menu" role="menu" aria-label="Session actions" onKeyDown={keyboard} style={{ position: 'fixed', ...position, visibility: position ? 'visible' : 'hidden' }}>{actions.map((action) => <button key={action.label} role="menuitem" type="button" disabled={action.disabled} onClick={() => { close(true); action.onClick() }}>{action.label}</button>)}</div>, document.body)
}

export default function WebsiteSessionTable({ sessions, loading = false, preview = false, actionsFor, onTranscript, transcriptDisabled, renderDetails, viewerData, onSection, sectionDisabled, page, onPageChange, pageSize = 20 }) {
  const viewerVersion = useRef(0)
  const [viewer, setViewer] = useState(null)
  const selectedSession = sessions.find(session => session.id === viewer?.id)
  function show(id, section) { viewerVersion.current += 1; setViewer({id, section}) }
  function closeViewer() { viewerVersion.current += 1; setViewer(null) }
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('newest')
  const [open, setOpen] = useState(null)
  const triggerRef = useRef(null)
  const visible = sessions.filter((session) => (!status || session.status === status) && [session.title, session.target_role, session.company_name].filter(Boolean).join(' ').toLowerCase().includes(search.toLowerCase())).toSorted((a, b) => sort === 'title' ? String(a.title || a.target_role || '').localeCompare(String(b.title || b.target_role || '')) : (Date.parse(b.started_at) || 0) - (Date.parse(a.started_at) || 0)).slice(0, preview ? 5 : undefined)
  const close = useCallback((restore) => { setOpen(null); if (restore) triggerRef.current?.focus({ preventScroll:true }) }, [])
  return <section aria-label="Interview session history" aria-busy={loading}>
    {loading && <p className={sessions.length ? 'wd-scope' : 'wd-sr-only'} role="status">{sessions.length ? 'Updating session history...' : 'Loading interview sessions...'}</p>}
    {!preview && <><div className="wd-toolbar"><label className="wd-search"><img src={searchIcon} alt="" /><input aria-label="Search loaded sessions" placeholder="Search by title, role or company" value={search} onChange={(event) => { close(false); setSearch(event.target.value) }} /></label><select aria-label="Filter loaded sessions by state" value={status} onChange={(event) => { close(false); setStatus(event.target.value) }}><option value="">All states</option>{[...new Set(sessions.map(s => s.status).filter(Boolean))].map(value => <option key={value} value={value}>{value}</option>)}</select><select aria-label="Sort loaded sessions" value={sort} onChange={(event) => { close(false); setSort(event.target.value) }}><option value="newest">Newest started</option><option value="title">Session title</option></select></div><p className="wd-scope">{loading && !sessions.length ? 'Search, state filter and sorting apply to the loaded page.' : `Search, state filter and sorting apply to this loaded page of ${sessions.length} sessions.`}</p></>}
    <div className="wd-table-scroll" tabIndex={0} aria-label="Session table"><table className="wd-table"><thead><tr><th scope="col">Session</th><th scope="col">Duration</th><th scope="col">Started</th><th scope="col">State</th><th scope="col"><span className="wd-sr-only">Transcript</span></th><th scope="col"><span className="wd-sr-only">Actions</span></th></tr></thead><tbody>{loading && !sessions.length ? <SkeletonRows count={preview ? 5 : 3} /> : visible.map(session => <tr key={session.id}><td><div className="wd-session-name"><span className="wd-session-icon"><img src={sessionIcon} alt="" /></span><div><strong>{session.title || session.target_role || session.company_name || 'Untitled session'}</strong>{sessionSubtitle(session) && <span>{sessionSubtitle(session)}</span>}</div></div></td><td className="wd-duration">{sessionDuration(session)}</td><td>{session.started_at && Number.isFinite(Date.parse(session.started_at)) ? new Date(session.started_at).toLocaleDateString(undefined, { month:'short', day:'numeric', year:'numeric' }) : 'Unavailable'}</td><td><span className="wd-state">{session.status || 'Unknown'}</span></td><td><button type="button" onClick={() => { show(session.id, 'transcript'); onTranscript(session.id, {reload:true}) }} disabled={transcriptDisabled(session.id)}>View Transcript</button></td><td><button type="button" className="wd-more" aria-label={`Actions for ${session.title || session.target_role || session.id}`} aria-haspopup="menu" aria-expanded={open === session.id} onClick={(event) => { if (open === session.id) close(true); else { triggerRef.current = event.currentTarget; setOpen(session.id) } }} onKeyDown={(event) => { if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); triggerRef.current = event.currentTarget; setOpen(session.id) } }}><img src={moreIcon} alt="" /></button></td></tr>)}</tbody></table></div>
    {!loading && !visible.length && <p className="wd-empty">No sessions match this loaded page.</p>}
    {!preview && <div className="wd-pagination"><span>{loading ? 'Updating sessions...' : `Page ${page} · ${visible.length} shown`}</span><div><button type="button" disabled={loading || page <= 1} onClick={() => { close(false); onPageChange(page - 1) }}>Previous</button><button type="button" disabled={loading || sessions.length < pageSize} onClick={() => { close(false); onPageChange(page + 1) }}>Next</button></div></div>}
    {open && <RowMenu trigger={triggerRef.current} actions={actionsFor(open).map(action => ({...action, onClick: async () => {
      const section = {'Generate AI Notes':'notes', 'View AI Notes':'notes', 'Ask AI':'ask'}[action.label]
      if (section) show(open, section)
      const version = viewerVersion.current
      const result = await action.onClick()
      if (action.label.startsWith('Download') && result === false && version === viewerVersion.current) { show(open, 'transcript'); onTranscript(open, {reload:true}) }
    }}))} close={close} />}
    {selectedSession && <WebsiteSessionViewer key={selectedSession.id} data={viewerData} onDownload={format => actionsFor(selectedSession.id).find(action => action.label === `Download .${format}`)?.onClick()} session={selectedSession} section={viewer.section} sectionDisabled={section => sectionDisabled(selectedSession.id, section)} onClose={closeViewer} onSection={section => { show(selectedSession.id, section); onSection(selectedSession.id, section) }}>{presentation => renderDetails(selectedSession, viewer.section, presentation)}</WebsiteSessionViewer>}
  </section>
}
