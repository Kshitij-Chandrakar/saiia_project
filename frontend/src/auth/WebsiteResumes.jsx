import { useEffect, useRef } from 'react'
import { FileText, Upload, X, CheckCircle2, LoaderCircle, CircleAlert } from 'lucide-react'
import { ResumeEmptyState } from './DashboardLayout'
import './website-resumes.css'
import WebsiteSkeleton from './WebsiteSkeleton'

const sections = [
  ['Personal and career details', ['full_name', 'email', 'phone', 'location', 'current_title', 'target_role']],
  ['Professional summary', ['professional_summary']],
  ['Education', ['education', 'degree', 'branch', 'college', 'graduation_year']],
  ['Skills and tools', ['top_skills', 'technical_skills', 'tools_frameworks']],
  ['Projects and experience', ['projects', 'experience']],
  ['Certifications and achievements', ['certifications', 'achievements']],
]

function ResumeDialog({ title, wide, onClose, returnFocusRef, children }) {
  const ref = useRef(null)
  useEffect(() => {
    const element = ref.current, overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    element.showModal()
    return () => {
      element.close()
      document.body.style.overflow = overflow
      const target = returnFocusRef.current?.isConnected ? returnFocusRef.current : document.querySelector('.website-resumes .wr-page-upload')
      target?.focus({ preventScroll:true })
    }
  }, [returnFocusRef])
  return <dialog ref={ref} className={`website-dashboard wr-dialog ${wide ? 'wr-dialog--wide' : ''}`} aria-modal="true" aria-labelledby="wr-dialog-title" onCancel={event => { event.preventDefault(); onClose() }} onKeyDown={event => {
    if (event.key !== 'Tab') return
    const controls = [...event.currentTarget.querySelectorAll('button,input,textarea,select,a[href],[tabindex="0"]')].filter(element => !element.disabled && element.getClientRects().length)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }} onClick={event => {
    if (event.target !== event.currentTarget) return
    const rect = event.currentTarget.getBoundingClientRect()
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose()
  }}>
    <header className="wr-dialog-header"><h2 id="wr-dialog-title">{title}</h2><button type="button" aria-label={`Close ${title}`} onClick={onClose}><X size={20} aria-hidden="true" /></button></header>
    {children}
  </dialog>
}

function ResumeCard({ record, active, confirmed, children }) {
  return <section className="wr-resume-card" aria-label={active ? 'Active resume' : 'Resume candidate'}><span className="wr-document"><FileText size={24} aria-hidden="true" /></span><div className="wr-record"><h2>{record.original_filename || 'Resume'}</h2><p>{active ? 'Current ready resume' : confirmed ? 'Confirmation received' : 'New candidate'} · <span className="wr-status">{active ? 'Ready' : record.status || 'Unknown'}</span></p>{!active && <small>{confirmed ? 'Refresh to verify its active status.' : 'This candidate does not replace your active resume until confirmation succeeds.'}</small>}</div><div className="wr-card-actions">{children}</div></section>
}

export default function WebsiteResumes({ currentResume, candidate, phase, busy, file, error, message, dialog, onClose, onUpload, onManual, onReview, onExtract, onConfirm, onDelete, onRebuild, onRetry, onSubmit, onFile, fileInputRef, returnFocusRef, uploadDisabled, draftProfile, hasCandidateDraft, fields, updateDraftField, confirmPending, deletePending, rebuildPending, manual = false }) {
  const pageCandidate = candidate?.id !== currentResume?.id ? candidate : null
  const serverProcessing = ['extracting', 'indexing'].includes(pageCandidate?.status)
  const refreshCandidate = serverProcessing || phase === 'confirmed'
  const processing = ['uploading', 'extracting'].includes(phase) || confirmPending
  const processingText = confirmPending ? 'Confirming profile and indexing resume.' : phase === 'uploading' ? 'Uploading resume.' : phase === 'extracting' ? 'Extracting profile details.' : error ? 'Resume processing failed.' : draftProfile ? 'Ready for review.' : 'Resume status updated.'
  const feedback = <>{error && <p className="wr-error" role="alert">{error}</p>}{message && !processing && <p className="wr-notice" role="status">{message}</p>}</>
  return <div className="website-resumes">
    <div className="wr-page-actions">{(currentResume || pageCandidate) && <button type="button" className="wd-primary wr-page-upload" onClick={onUpload} disabled={busy}><Upload size={16} aria-hidden="true" />Upload Resume</button>}{processing && <button type="button" onClick={onReview}>View progress</button>}</div>
    {phase === 'loading' && (!currentResume && !pageCandidate ? <WebsiteSkeleton kind="resume" label="Loading resume status..." /> : <p role="status">Refreshing resume status...</p>)}
    {!dialog && feedback}
    {phase === 'failed' && !processing && !dialog && <button type="button" onClick={onRetry}>Retry resume status</button>}
    {phase !== 'loading' && phase !== 'failed' && !currentResume && !pageCandidate && <ResumeEmptyState onUpload={onUpload} />}
    {currentResume && <ResumeCard record={currentResume} active><button type="button" onClick={onRebuild} disabled={busy || !currentResume.is_active}>{rebuildPending ? 'Rebuilding index...' : 'Rebuild Index'}</button><button type="button" className="wr-danger" onClick={() => onDelete(currentResume)} disabled={busy}>{deletePending ? 'Deleting resume...' : 'Delete Resume'}</button></ResumeCard>}
    {pageCandidate && <ResumeCard record={pageCandidate} confirmed={phase === 'confirmed'}><button type="button" onClick={hasCandidateDraft ? onReview : refreshCandidate ? onRetry : onExtract} disabled={busy}>{hasCandidateDraft ? 'Review Profile' : refreshCandidate ? 'Refresh status' : 'Extract Again'}</button><button type="button" className="wr-danger" onClick={() => onDelete(pageCandidate)} disabled={busy || serverProcessing}>Delete Resume</button>{!hasCandidateDraft && <small>{refreshCandidate ? 'Refresh to check the current resume status.' : 'Extract again to recover the editable profile.'}</small>}</ResumeCard>}
    {dialog === 'upload' && <ResumeDialog title="Upload Resume" onClose={onClose} returnFocusRef={returnFocusRef}>
      <form className="wr-upload-form" onSubmit={onSubmit}><div className="wr-dialog-body">
        <div className="wr-dropzone" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy) onFile(event.dataTransfer.files?.[0] || null) }}>
          <input ref={fileInputRef} id="wr-resume-file" type="file" aria-label="Resume file" accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={event => onFile(event.target.files?.[0] || null)} disabled={busy} />
          <label htmlFor="wr-resume-file"><Upload size={36} aria-hidden="true" /><span><strong>Click to upload</strong> or drag and drop</span><small>PDF, DOCX or TXT · Maximum 5 MB</small></label>
        </div>
        {file && <p className="wr-selected-file"><FileText size={18} aria-hidden="true" />{file.name}</p>}{feedback}
        <div className="wr-divider"><span>OR</span></div><button className="wr-manual" type="button" onClick={onManual} disabled={busy}>Input Manually</button>
      </div><footer className="wr-dialog-footer"><button type="button" onClick={onClose}>Cancel</button><button type="submit" className="wd-primary" disabled={uploadDisabled}>Upload and Extract</button></footer></form>
    </ResumeDialog>}
    {dialog === 'processing' && <ResumeDialog title={confirmPending ? 'Confirm Reviewed Profile' : 'Upload Resume'} onClose={onClose} returnFocusRef={returnFocusRef}><div className="wr-dialog-body wr-processing" aria-live="polite" aria-busy={processing}>{processing ? <LoaderCircle className="wr-spinner" size={32} aria-hidden="true" /> : error ? <CircleAlert size={32} aria-hidden="true" /> : <CheckCircle2 size={32} aria-hidden="true" />}<h3>{processingText}</h3><p>{processing ? 'You can close this dialog. Closing does not cancel the server operation.' : 'Check the result below before continuing.'}</p>{processing && <div className="wr-indeterminate" role="progressbar" aria-label={processingText} />}{feedback}{!processing && error && <button type="button" className="wd-primary" onClick={onRetry}>Retry processing</button>}</div></ResumeDialog>}
    {dialog === 'review' && draftProfile && <ResumeDialog title={manual ? 'Enter Profile Manually' : 'Review Extracted Profile'} wide onClose={onClose} returnFocusRef={returnFocusRef}>
      <form className="wr-review-form" onSubmit={onConfirm}><div className="wr-dialog-body"><p className="wr-instruction">Check and correct the details before confirming. Closing keeps your unconfirmed edits for this visit.</p>{manual && <p className="wr-notice">Manual entries are an unsaved draft. Saving without an uploaded resume is not currently supported.</p>}{feedback}
        {sections.map(([name, keys]) => <fieldset key={name}><legend>{name}</legend><div className="wr-fields">{fields.filter(([field]) => keys.includes(field)).map(([field, label, kind]) => <label key={field} className={kind === 'textarea' ? 'wr-long-field' : ''}>{label}{kind === 'textarea' ? <textarea aria-label={label} rows={3} value={draftProfile[field] || ''} onChange={event => updateDraftField(field,event.target.value)} disabled={busy} /> : <input aria-label={label} type={field === 'email' ? 'email' : 'text'} value={draftProfile[field] || ''} onChange={event => updateDraftField(field,event.target.value)} disabled={busy} />}</label>)}</div></fieldset>)}
      </div><footer className="wr-dialog-footer">{!manual && <button type="button" className="wr-danger" onClick={() => onDelete(candidate)} disabled={busy}>Delete Resume</button>}<button type="button" onClick={onClose}>Close</button><button type="submit" className="wd-primary" disabled={busy || manual}>Confirm Reviewed Profile</button></footer></form>
    </ResumeDialog>}
  </div>
}
