import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'

const panelSource = readFileSync(new URL('./components/AnswerPanel.jsx', import.meta.url), 'utf8')
const overlaySource = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
const mainSource = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
const notesSource = readFileSync(new URL('../electron/desktop_auth_session.cjs', import.meta.url), 'utf8')
const stylesSource = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')

describe('My Answers Chat section', () => {
  it('opens in Chat view with an internal My Answers switch', () => {
    assert.match(panelSource, /const \[chatPanelView, setChatPanelView\] = useState\('chat'\)/)
    assert.match(panelSource, /mode === 'chat' && chatPanelView === 'chat'/)
    assert.match(panelSource, /topbar-chat-panel__helper-row/)
    assert.match(panelSource, /topbar-chat-panel__view-button/)
    assert.match(panelSource, /topbar-chat-panel__hint[\s\S]*Enter to submit\.[\s\S]*topbar-chat-panel__view-button[\s\S]*My Answers/)
    assert.doesNotMatch(panelSource, /topbar-chat-panel__view-switch">[\s\S]*My Answers/)
    assert.match(panelSource, /hidden=\{!visible\}/)
    assert.match(overlaySource, /const \[chatOpenVersion, setChatOpenVersion\] = useState\(0\)/)
    assert.match(overlaySource, /setChatOpenVersion\(\(version\) => version \+ 1\)/)
    assert.match(overlaySource, /chatOpenVersion=\{chatOpenVersion\}/)
  })

  it('replaces Chat content with My Answers and provides a return button', () => {
    assert.match(panelSource, /mode === 'chat' && chatPanelView === 'myAnswers'/)
    assert.match(panelSource, /onBackToChat=\{handleReturnToChat\}/)
    assert.match(panelSource, /onClick=\{onBackToChat\}/)
    assert.match(panelSource, /setChatPanelView\('chat'\)/)
    assert.match(panelSource, /visible=\{chatPanelView === 'myAnswers'\}/)
    assert.match(panelSource, /mode === 'chat' && chatPanelView === 'myAnswers' \? null/)
  })

  it('keeps saved content read-only', () => {
    assert.match(panelSource, /readOnly=\{activeIndex !== null\}/)
    assert.match(panelSource, /window\.saiia\.saveMyAnswer\(effectiveSessionId, body\)/)
    assert.doesNotMatch(panelSource, /Answer \$\{|Answer 1\/3|title=.*My Answer/)
  })

  it('supports save, new draft, arrow navigation, and unsaved-discard confirmation', () => {
    assert.match(panelSource, /const \[savedAnswers, setSavedAnswers\]/)
    assert.match(panelSource, /const \[activeIndex, setActiveIndex\]/)
    assert.match(panelSource, /const \[draftText, setDraftText\]/)
    assert.match(panelSource, /window\.confirm\('Discard this unsaved answer\?'\)/)
    assert.match(panelSource, /aria-label="New My Answer"/)
    assert.match(panelSource, /aria-label="Previous saved answer"/)
    assert.match(panelSource, /aria-label="Next saved answer"/)
  })

  it('keeps the section visible and disables Save without an active session', () => {
    assert.match(appSource, /applyStartupSessionConfig\(null\)/)
    assert.match(panelSource, /Start an interview session to save My Answers\./)
    assert.doesNotMatch(panelSource, /if \(!sessionId\) return null/)
    assert.match(panelSource, /disabled=\{loading \|\| saving \|\| !effectiveSessionId/)
  })

  it('uses the available panel height for the editable answer area', () => {
    assert.match(panelSource, /topbar-answer-panel__body--my-answers/)
    assert.match(panelSource, /onBackToChat=\{handleReturnToChat\}/)
    assert.match(stylesSource, /\.topbar-answer-panel__body--my-answers\s*\{[\s\S]*display:\s*flex[\s\S]*flex-direction:\s*column/)
    assert.match(stylesSource, /\.topbar-my-answers__textarea\s*\{[\s\S]*flex:\s*1[\s\S]*min-height:\s*0[\s\S]*overflow-y:\s*auto/)
    assert.match(stylesSource, /\.topbar-my-answers__save-row\s*\{[\s\S]*display:\s*flex[\s\S]*align-items:\s*center/)
    assert.match(stylesSource, /\.topbar-my-answers\[hidden\]\s*\{[\s\S]*display:\s*none\s*!important/)
  })

  it('keeps the active session handoff safe and recoverable', () => {
    assert.match(appSource, /activeSessionId: String\(startupSessionConfig\?\.activeSessionId \|\| ''\)/)
    assert.match(panelSource, /authState\?\.activeInterviewSessionId/)
    assert.match(preloadSource, /getAuthState: \(\) => ipcRenderer\.invoke\('auth:get-state'\)/)
    assert.match(notesSource, /activeInterviewSessionId: this\.activeInterviewSession\?\.id \|\| null/)
    assert.match(panelSource, /saveMyAnswer\(effectiveSessionId, body\)/)
  })

  it('surfaces an unapplied My Answers migration as a clear error', () => {
    assert.match(mainSource, /cloud:save-my-answer/)
    assert.match(readFileSync(new URL('../../backend/app/cloud/interview_session_my_answers.py', import.meta.url), 'utf8'), /MIGRATION_FAILURE_MESSAGE/)
    assert.match(readFileSync(new URL('../../backend/app/api/interview_sessions.py', import.meta.url), 'utf8'), /MY_ANSWERS_MIGRATION_FAILURE_MESSAGE/)
  })

  it('keeps the Electron bridge narrow and token-free', () => {
    assert.match(preloadSource, /listMyAnswers: \(sessionId\)/)
    assert.match(preloadSource, /saveMyAnswer: \(sessionId, body\)/)
    assert.match(mainSource, /ipcMain\.handle\('cloud:list-my-answers',[\s\S]*?validateTrustedRendererIpc\(event\)/)
    assert.match(mainSource, /ipcMain\.handle\('cloud:save-my-answer',[\s\S]*?validateTrustedRendererIpc\(event\)/)
    assert.doesNotMatch(preloadSource, /access_token|refresh_token|generic fetch/i)
  })

  it('does not add My Answers to the AI answer, notes, or transcript pipelines', () => {
    assert.doesNotMatch(appSource, /my_answers|my-answers|listMyAnswers|saveMyAnswer/)
    assert.doesNotMatch(notesSource, /transcript.*my-answers|notes.*my-answers/i)
  })
})

// Execute the component's pre-JSX logic with deterministic hook scheduling.
// This exercises pending promises and session effects without adding a DOM dependency.
function mountMyAnswers(saiia, initialSession = 'A', confirm = () => true) {
  const slots = []
  let cursor = 0
  let dirty = true
  let sessionId = initialSession
  let state
  let effects = []
  let layouts = []
  const useState = (initial) => {
    const index = cursor++
    if (!(index in slots)) slots[index] = initial
    return [slots[index], (next) => {
      const value = typeof next === 'function' ? next(slots[index]) : next
      if (!Object.is(value, slots[index])) { slots[index] = value; dirty = true }
    }]
  }
  const useRef = (initial) => {
    const index = cursor++
    return slots[index] ||= { current: initial }
  }
  const effect = (queue, callback, deps) => {
    const index = cursor++
    const previous = slots[index]
    if (!previous || deps.some((value, i) => !Object.is(value, previous.deps[i]))) {
      queue.push(() => {
        previous?.cleanup?.()
        slots[index] = { deps, cleanup: callback() }
      })
    }
  }
  const source = panelSource.slice(panelSource.indexOf('function MyAnswersSection('), panelSource.indexOf('    <section className="topbar-my-answers"'))
  const logic = source.slice(0, source.lastIndexOf('  return ('))
  const render = new Function('useState', 'useRef', 'useEffect', 'useLayoutEffect', 'window', `${logic}
    return { savedAnswers, activeIndex, draftText, loading, saving, error, handleSave, handleNew, handlePrevious, handleNext, setDraftText, pendingSavedAnswerId }
  }; return MyAnswersSection`)(useState, useRef, (fn, deps) => effect(effects, fn, deps), (fn, deps) => effect(layouts, fn, deps), { saiia, confirm })
  const flush = () => {
    for (let pass = 0; dirty; pass++) {
      assert.ok(pass < 30, 'component effects must settle')
      dirty = false; cursor = 0; effects = []; layouts = []
      state = render({ sessionId })
      layouts.forEach((run) => run())
      effects.forEach((run) => run())
    }
    return state
  }
  return {
    flush,
    switchSession(next) { sessionId = next; dirty = true; return flush() },
    unmount() { slots.forEach((slot) => slot?.cleanup?.()) },
  }
}

for (const staleResult of ['success', 'error', 'rejection']) {
  it(`discards session A save ${staleResult} after switching to B`, async () => {
    let resolveSave
    let rejectSave
    const calls = []
    const mounted = mountMyAnswers({
      listMyAnswers: async () => ({ items: [] }),
      saveMyAnswer: (sessionId, body) => {
        calls.push({ sessionId, body })
        return new Promise((resolve, reject) => { resolveSave = resolve; rejectSave = reject })
      },
    })
    mounted.flush()
    await Promise.resolve()
    mounted.flush().setDraftText('answer A')
    const pending = mounted.flush().handleSave()
    mounted.switchSession('B')
    await Promise.resolve()
    mounted.flush().setDraftText('draft B')
    mounted.flush()
    if (staleResult === 'rejection') rejectSave(new Error('offline'))
    else resolveSave(staleResult === 'success' ? { answer: { id: 'answer-A', body: 'answer A' } } : { error: 'offline' })
    await pending
    const current = mounted.flush()
    assert.deepEqual(calls, [{ sessionId: 'A', body: 'answer A' }])
    assert.deepEqual(current.savedAnswers, [])
    assert.equal(current.activeIndex, null)
    assert.equal(current.pendingSavedAnswerId.current, null)
    assert.equal(current.draftText, 'draft B')
    assert.equal(current.error, '')
    mounted.unmount()
  })
}

it('saves and selects a read-only answer for the current session', async () => {
  const mounted = mountMyAnswers({
    listMyAnswers: async () => ({ items: [] }),
    saveMyAnswer: async (sessionId, body) => ({ answer: { id: 'saved', session_id: sessionId, body } }),
  })
  mounted.flush()
  await Promise.resolve()
  mounted.flush().setDraftText('  current answer  ')
  await mounted.flush().handleSave()
  const current = mounted.flush()
  assert.deepEqual(current.savedAnswers, [{ id: 'saved', session_id: 'A', body: 'current answer' }])
  assert.equal(current.activeIndex, 0)
  assert.equal(current.draftText, 'current answer')
  assert.equal(current.saving, false)
  assert.equal(current.error, '')
  mounted.unmount()
})

it('loads saved answers, navigates with arrows, and creates a blank draft', async () => {
  const items = [{ id: 'first', body: 'First answer' }, { id: 'second', body: 'Second answer' }]
  const mounted = mountMyAnswers({ listMyAnswers: async () => ({ items }) })
  assert.equal(mounted.flush().loading, true)
  await Promise.resolve()
  assert.equal(mounted.flush().loading, false)
  assert.equal(mounted.flush().draftText, 'First answer')
  mounted.flush().handleNext()
  assert.equal(mounted.flush().activeIndex, 1)
  assert.equal(mounted.flush().draftText, 'Second answer')
  mounted.flush().handlePrevious()
  assert.equal(mounted.flush().activeIndex, 0)
  assert.equal(mounted.flush().draftText, 'First answer')
  mounted.flush().handleNew()
  assert.equal(mounted.flush().activeIndex, null)
  assert.equal(mounted.flush().draftText, '')
  assert.deepEqual(mounted.flush().savedAnswers, items)
  mounted.unmount()
})

for (const action of ['handleNew', 'handlePrevious', 'handleNext']) {
  it(`${action} preserves an unsaved draft unless discard is confirmed`, async () => {
    let discard = false
    const mounted = mountMyAnswers({
      listMyAnswers: async () => ({ items: [{ id: 'saved', body: 'Saved answer' }] }),
    }, 'A', (message) => {
      assert.equal(message, 'Discard this unsaved answer?')
      return discard
    })
    mounted.flush()
    await Promise.resolve()
    mounted.flush().handleNew()
    mounted.flush().setDraftText('Unsaved draft')
    mounted.flush()[action]()
    assert.equal(mounted.flush().draftText, 'Unsaved draft')
    assert.equal(mounted.flush().activeIndex, null)
    discard = true
    mounted.flush()[action]()
    assert.equal(mounted.flush().draftText, action === 'handleNew' ? '' : 'Saved answer')
    assert.equal(mounted.flush().activeIndex, action === 'handleNew' ? null : 0)
    mounted.unmount()
  })
}
