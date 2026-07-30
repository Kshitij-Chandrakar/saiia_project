import test from 'node:test'
import assert from 'node:assert/strict'

import {
  getAutoFocusedTabForAnswer,
  getPanelOverlayState,
  getPanelOwner,
  getTabForAnswerMode,
  snapshotOverlayState,
} from './overlay_mode_state.js'

test('toolbar tabs map to isolated mode owners', () => {
  assert.equal(getPanelOwner('aiHelp'), 'answer')
  assert.equal(getPanelOwner('chat'), 'chat')
  assert.equal(getPanelOwner('analyzeScreen'), 'screen')
  assert.equal(getPanelOwner(null), 'answer')
})

test('answer display mode restores the originating tab', () => {
  assert.equal(getTabForAnswerMode('answer'), 'aiHelp')
  assert.equal(getTabForAnswerMode('chat'), 'chat')
  assert.equal(getTabForAnswerMode('screen'), 'analyzeScreen')
  assert.equal(getTabForAnswerMode('unknown'), 'aiHelp')
})

test('snapshots preserve mode-owned answer without mutating source state', () => {
  const source = {
    answerDisplayMode: 'chat',
    transcript: 'Explain APIs.',
    answer: 'APIs connect clients and servers.',
  }
  const snapshot = snapshotOverlayState(source)

  source.answer = 'Different answer'

  assert.equal(snapshot.answerDisplayMode, 'chat')
  assert.equal(snapshot.transcript, 'Explain APIs.')
  assert.equal(snapshot.answer, 'APIs connect clients and servers.')
})

test('active tab uses live state while its answer mode is streaming', () => {
  const staleAnswerSnapshot = snapshotOverlayState({
    answerDisplayMode: 'answer',
    transcript: '',
    answer: '',
  })
  const liveAnswerState = {
    answerDisplayMode: 'answer',
    transcript: 'What is self-attention?',
    answer: 'Self-attention lets each token compare itself with other tokens.',
  }

  const panelState = getPanelOverlayState({
    activeTab: 'aiHelp',
    overlayState: liveAnswerState,
    modeSnapshots: {
      answer: staleAnswerSnapshot,
      chat: snapshotOverlayState({ answerDisplayMode: 'chat', answer: 'old chat answer' }),
      screen: snapshotOverlayState({ answerDisplayMode: 'screen', answer: 'old screen answer' }),
    },
  })

  assert.equal(panelState, liveAnswerState)
  assert.equal(panelState.answer, 'Self-attention lets each token compare itself with other tokens.')
})

test('inactive tab can still show its saved snapshot', () => {
  const chatSnapshot = snapshotOverlayState({
    answerDisplayMode: 'chat',
    transcript: 'Explain closures.',
    answer: 'Closures keep access to outer scope.',
  })
  const liveAnswerState = {
    answerDisplayMode: 'answer',
    transcript: 'What is self-attention?',
    answer: 'Self-attention lets each token compare itself with other tokens.',
  }

  const panelState = getPanelOverlayState({
    activeTab: 'chat',
    overlayState: liveAnswerState,
    modeSnapshots: {
      answer: snapshotOverlayState(liveAnswerState),
      chat: chatSnapshot,
      screen: snapshotOverlayState({ answerDisplayMode: 'screen', answer: '' }),
    },
  })

  assert.equal(panelState, chatSnapshot)
  assert.equal(panelState.answer, 'Closures keep access to outer scope.')
})

test('new generated answers focus their owning tab', () => {
  assert.equal(
    getAutoFocusedTabForAnswer({
      activeTab: 'analyzeScreen',
      answerDisplayMode: 'answer',
      answer: 'Use dynamic programming.',
    }),
    'aiHelp'
  )
  assert.equal(
    getAutoFocusedTabForAnswer({
      activeTab: 'aiHelp',
      answerDisplayMode: 'screen',
      answer: 'Screen answer.',
    }),
    'analyzeScreen'
  )
  assert.equal(
    getAutoFocusedTabForAnswer({
      activeTab: 'aiHelp',
      answerDisplayMode: 'answer',
      answer: 'Already here.',
    }),
    null
  )
  assert.equal(
    getAutoFocusedTabForAnswer({
      activeTab: 'chat',
      answerDisplayMode: 'chat',
      answer: 'Chat response.',
    }),
    null
  )
})
