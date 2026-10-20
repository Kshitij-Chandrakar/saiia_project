import React, { useEffect, useRef, useState } from 'react'
import { screenContextCommandFence } from '../screen_context_events'

export function useScreenContextStatus() {
  const [status, setStatus] = useState(null)
  const latest = useRef(-1)
  useEffect(() => {
    let mounted = true
    const accept = value => {
      if (mounted && value && Number.isSafeInteger(value.sequence) && value.sequence >= latest.current) {
        latest.current = value.sequence; setStatus(value)
      }
    }
    const unsubscribe = window.electronAPI?.onScreenContextEvent?.(accept)
    window.electronAPI?.getScreenContextStatus?.().then(accept).catch(() => {})
    return () => { mounted = false; unsubscribe?.() }
  }, [])
  return status
}

export function ScreenContextChooser({ status, onExecute, onExtension, blocked = false }) {
  const hasContext = Boolean(status?.evidenceCount)
  const [selection, setSelection] = useState(null)
  const matches = selection?.threadId === status?.threadId && selection?.hasContext === hasContext
  const action = matches ? selection.action : hasContext ? '' : 'new'
  const target = matches ? selection.target : ''
  const choose = action => setSelection({ threadId: status?.threadId, hasContext, action, target: '' })
  const admission = useRef(false)
  const busy = ['capturing', 'processing'].includes(status?.phase)
  return <>
    <fieldset className="screen-context-choices">
      <legend>Question context</legend>
      <label><input type="radio" name="screen-context-action" value="continue" checked={action === 'continue'}
        disabled={!hasContext} onChange={() => choose('continue')} /> Continue previous question</label>
      <label><input type="radio" name="screen-context-action" value="new" checked={action === 'new'}
        onChange={() => choose('new')} /> New question</label>
      <label><input type="radio" name="screen-context-action" value="reference" checked={action === 'reference'}
        onChange={() => choose('reference')} /> Passage / Data</label>
    </fieldset>
    {action === 'continue' && status?.priorItems?.length > 1 ? <label className="screen-context-field">Continue which question?
      <select value={target} onChange={event => setSelection(current => ({ ...current, target: event.target.value }))}>
        <option value="">{status.contextKind === 'reference' ? 'Use question in current capture' : 'Choose a question'}</option>
        {status.priorItems.map((item, index) => <option key={item.questionId} value={item.questionId}>Question {index + 1}</option>)}
      </select>
    </label> : null}
    <button type="button" className="topbar-analyze-menu__item no-drag" disabled={blocked || !status || status.status === 'disposed' || !action || (busy && action === 'continue')}
      onClick={async () => {
        if (admission.current) return
        admission.current = true
        try { await onExecute({ action, commandId: crypto.randomUUID(), expected: screenContextCommandFence(status), ...(target ? { targetQuestionId: target } : {}) }) }
        finally { admission.current = false }
      }}>
      <span className="topbar-analyze-menu__title">OCR</span>
      <span className="topbar-analyze-menu__description">Capture the active window using your selected context option.</span>
    </button>
    <button type="button" className="topbar-analyze-menu__item no-drag" onClick={onExtension}>
      <span className="topbar-analyze-menu__title">Extension</span>
      <span className="topbar-analyze-menu__status">Extension setup required</span>
    </button>
  </>
}

const errors = {
  provider_unavailable: 'The Screen provider is unavailable. Check the provider setup or connection, then retry the captured screenshot.',
  provider_timeout: 'The Screen provider timed out. Retry the captured screenshot.',
  provider_rate_limited: 'The Screen provider is busy. Wait briefly, then retry the captured screenshot.',
  provider_configuration: 'The Screen provider configuration needs attention. Check the configured model and credentials before retrying.',
  request_busy: 'Screen analysis is busy. Wait briefly, then retry the captured screenshot.',
  active_window_not_identified: 'Could not identify the passage or question window. Focus that window, then reopen Analyze Screen and choose OCR.',
  upload_limit: 'Screen context exceeds the upload budget. Start a new question or cancel.',
  image_count_limit: 'Screenshot limit reached. Start a new question.',
  memory_limit: 'Screen context is full. Start a new question.',
  auth_required: 'Sign in again and start a session.',
  invalid_response: 'The response could not be validated. Retry the captured screenshot.',
  request_timeout: 'Screen analysis timed out. Retry the captured screenshot.',
}

export function ScreenContextStatus({ status, displayedThreadId }) {
  const [error, setError] = useState('')
  const [text, setText] = useState('')
  const [target, setTarget] = useState('')
  const [replacements, setReplacements] = useState([])
  const admission = useRef(false)
  useEffect(() => { setText(''); setTarget(''); setReplacements([]); setError('') }, [status?.clarificationRequestId])
  if (!status) return null
  const busy = ['capturing', 'processing'].includes(status.phase)
  const call = async (method, payload) => {
    if (admission.current) return
    admission.current = true; setError('')
    try { await window.electronAPI?.[method]?.({ ...payload, expected: screenContextCommandFence(status) }) }
    catch { setError('Screen action unavailable. Reopen Analyze Screen and try again.') }
    finally { admission.current = false }
  }
  return <div className="screen-context-status">
    <div role="status" aria-live="polite">
      {status.threadId ? `${status.contextKind === 'reference' ? 'Reference context' : 'Active question'} ${status.threadId.slice(0, 8)}` : 'No active screen question'}
      {` · ${status.acceptedImageCount} / ${status.limits.maxImages} screenshots`}
      {busy ? ` · ${status.phase === 'capturing' ? 'Capturing…' : 'Analyzing…'}` : ''}
    </div>
    {displayedThreadId && displayedThreadId !== status.threadId ? <p>Displayed answer belongs to an earlier question.</p> : null}
    {status.phase === 'reference_accepted' ? <p>Reference saved. Capture your question using Continue previous question.</p> : null}
    {status.phase === 'needs_more_content' ? <><strong>More content needed</strong><ul>{status.missingDetails.map((detail, index) => <li key={index}>{detail}</li>)}</ul></> : null}
    {status.phase === 'failed' ? <p role="alert">{errors[status.errorCode] || 'Screen analysis failed. Retry the captured screenshot or start a new question.'}</p> : null}
    {status.clarificationRequestId ? <form onSubmit={event => {
      event.preventDefault()
      void call('resolveScreenClarification', { requestId: status.clarificationRequestId, text,
        targetQuestionId: target || null, replacesTurnIds: replacements })
    }}>
      <strong>Clarification needed</strong><p>{status.clarification}</p>
      {status.conflicts?.length ? <ul>{status.conflicts.map((conflict, index) => <li key={index}>{conflict}</li>)}</ul> : null}
      {status.priorItems.length > 1 ? <label className="screen-context-field">Question to continue
        <select value={target} onChange={event => setTarget(event.target.value)} required={status.contextKind !== 'reference'}>
          <option value="">Choose a question</option>
          {status.priorItems.map((item, index) => <option key={item.questionId} value={item.questionId}>Question {index + 1}</option>)}
        </select></label> : null}
      {status.sourceTurns.length ? <fieldset><legend>Replace earlier source only if this screenshot supersedes it</legend>
        {status.sourceTurns.map(turn => <label key={turn.turnId}><input type="checkbox" checked={replacements.includes(turn.turnId)} onChange={event => setReplacements(current => event.target.checked ? [...current, turn.turnId] : current.filter(id => id !== turn.turnId))} /> Screenshot turn {turn.number}</label>)}
      </fieldset> : null}
      <label className="screen-context-field">Your clarification
        <textarea maxLength={2000} value={text} onChange={event => setText(event.target.value)} /></label>
      <button type="submit" disabled={!text.trim() && !target && !replacements.length}>Resolve and retry captured screenshot</button>
    </form> : null}
    {status.retryAvailable && !status.clarificationRequestId ? <button type="button" onClick={() => call('retryScreenContext')}>Retry captured screenshot</button> : null}
    {busy || status.retryAvailable ? <button type="button" onClick={() => call('cancelScreenContext')}>Cancel screen analysis</button> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>
}
