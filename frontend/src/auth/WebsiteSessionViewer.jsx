import { useEffect, useRef, useState } from 'react'
import { FileText, MessagesSquare, Sparkles, Info, X, Eraser } from 'lucide-react'
import SessionConfirmation from './SessionConfirmation'
import sessionReviewMascot from '../assets/session-review-mascot.png'
import './website-session-viewer.css'

const sections = [['transcript', 'Transcript', MessagesSquare], ['notes', 'AI Notes', FileText], ['ask', 'Ask AI', Sparkles], ['details', 'Call Details', Info]]

export default function WebsiteSessionViewer({ session, section, onSection, sectionDisabled, onClose, data, onDownload, children }) {
  const [deletePending, setDeletePending] = useState(false)
  const deleteInFlight = useRef(false)
  const [deleteError, setDeleteError] = useState('')
  const [hiddenMessages, setHiddenMessages] = useState(new Set())
  const [confirmation, setConfirmation] = useState(null)
  const transcriptMatches = data.transcriptSessionId === session.id && data.entries.every(entry => entry.session_id === session.id)
  const entries = transcriptMatches ? data.entries : []
  const messages = data.askSessionId === session.id ? data.messages : []
  const visibleEntries = entries
  const deleteEligible = transcriptMatches && ['ended', 'abandoned'].includes(session.status) && Number.isFinite(Date.parse(session.ended_at)) && Date.parse(session.ended_at) + 300000 <= Date.now()
  const visibleMessages = messages.filter(message=>!hiddenMessages.has(message.id))
  const dialog = useRef(null)
  const close = useRef(null)
  const exit = useRef(null)
  function dismiss() {
    if (exit.current) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { onClose(); return }
    exit.current = dialog.current.animate([{ opacity:1, transform:'translateY(0)' }, { opacity:0, transform:'translateY(6px)' }], { duration:160, easing:'ease-in', fill:'forwards' })
    exit.current.finished.then(onClose, () => {})
  }
  const title = session.title || session.target_role || session.company_name || 'Untitled session'
  const heading = sections.find(item => item[0] === section)?.[1]
  useEffect(() => {
    const node = dialog.current, trigger = document.activeElement
    const body = document.body, root = document.documentElement
    const overflow = body.style.overflow, rootOverflow = root.style.overflow, padding = body.style.paddingRight
    const x = window.scrollX, y = window.scrollY, gutter = innerWidth - root.clientWidth
    node.showModal(); close.current.focus({ preventScroll: true })
    body.style.overflow = 'hidden'; root.style.overflow = 'hidden'
    if (gutter) body.style.paddingRight = `${gutter}px`
    return () => {
      exit.current?.cancel()
      node.close(); body.style.overflow = overflow; root.style.overflow = rootOverflow; body.style.paddingRight = padding
      window.scrollTo({ left: x, top: y, behavior: 'instant' })
      if (trigger?.isConnected) trigger.focus({ preventScroll: true })
    }
  }, [])

  return <dialog ref={dialog} className={`website-dashboard ws-viewer${section === 'ask' ? ' ws-viewer--ask' : ''}`} aria-modal="true" aria-labelledby="ws-viewer-title" onCancel={event => { event.preventDefault(); if (!confirmation) dismiss() }} onClick={event => {
    if (event.target !== event.currentTarget) return
    const rect = event.currentTarget.getBoundingClientRect()
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dismiss()
  }}>
    <aside className="ws-viewer__sidebar">
      <div className="ws-viewer__identity"><span>SESSION REVIEW</span><h2 id="ws-viewer-title" title={title}>{title}</h2>{[session.target_role, session.company_name].filter(value => value && value !== title).length > 0 && <p>{[session.target_role, session.company_name].filter(value => value && value !== title).join(' · ')}</p>}</div>
      <nav aria-label="Session sections">{sections.map(([key, label, Icon]) => <button key={key} type="button" disabled={sectionDisabled(key)} aria-current={key === section ? 'page' : undefined} onClick={() => onSection(key)}><Icon size={18} aria-hidden="true" />{label}</button>)}</nav>
      <img className="ws-viewer__mascot" src={sessionReviewMascot} alt="" aria-hidden="true" width="576" height="576" />
    </aside>
    <div className="ws-viewer__main">
      <header><h2>{heading}</h2><div className="ws-viewer__header-actions">
        {section === 'ask' && <button className="ws-clear" type="button" disabled={data.askLoading || !visibleMessages.length} onClick={()=>setConfirmation('Chat')}><Eraser size={16} aria-hidden="true" />Clear Chat</button>}
        {section === 'transcript' && <><button className="ws-clear" type="button" title={!deleteEligible ? 'Available five minutes after the session ends.' : undefined} disabled={!visibleEntries.length || !deleteEligible} onClick={()=>setConfirmation('Transcript')}><Eraser size={16} aria-hidden="true" />Clear Transcript</button>{['txt','md'].map(format=><button className="ws-download" key={format} type="button" disabled={data.downloadLoading || data.transcriptLoading} onClick={()=>onDownload(format)}>Download .{format}</button>)}</>}
        <button ref={close} type="button" aria-label="Close session viewer" onClick={dismiss}><X size={20} aria-hidden="true" /></button>
      </div></header>
      <div className="ws-viewer__body" key={section} tabIndex={0} aria-label={`${heading} content`}>
        {section === 'transcript' && visibleEntries.length > 0 && !deleteEligible && <p className="auth-session-history__meta">Transcript deletion is available five minutes after the session ends.</p>}
        {children({hiddenMessages,visibleEntries,visibleMessages})}
      </div>
    </div>
    {confirmation && <SessionConfirmation title={`Clear ${confirmation}?`} message={confirmation === 'Chat' ? 'Clear the chat from this view? Your saved conversation will reappear when you close and reopen this popup.' : 'This will permanently delete the saved transcript for this session. Your session, AI Notes, and Ask AI chat will remain. This action cannot be undone.'} keep={`Keep ${confirmation}`} confirm={confirmation === 'Transcript' ? 'Delete Transcript' : 'Clear Chat'} pending={deletePending} error={deleteError} onCancel={()=>{setConfirmation(null);setDeleteError('')}} onConfirm={async ()=>{
      if (deleteInFlight.current) return
      if(confirmation === 'Chat') { setHiddenMessages(current=>new Set([...current,...messages.map(message=>message.id)]));setConfirmation(null);return }
      deleteInFlight.current = true
      setDeletePending(true);setDeleteError('')
      try {
        await data.onDeleteTranscript(session.id)
        onSection('transcript')
        setConfirmation(null)
      } catch (error) {
        setDeleteError(error.message === 'Transcript deletion is available five minutes after the session ends.' ? error.message : 'Could not delete the transcript. Your displayed transcript is unchanged. Please try again.')
      } finally { deleteInFlight.current = false;setDeletePending(false) }
    }} />}
  </dialog>
}
