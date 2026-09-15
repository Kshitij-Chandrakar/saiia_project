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
