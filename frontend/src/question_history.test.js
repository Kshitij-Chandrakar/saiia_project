import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  appendQuestionHistoryEntry,
  createQuestionHistoryEntry,
  createQuestionHistoryState,
  getQuestionHistorySummary,
  getSelectedQuestionHistoryEntry,
  selectQuestionHistoryOffset,
  updateQuestionHistoryEntry,
} from './question_history.js'

describe('question history', () => {
  it('appends answer entries and selects the newest result', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(
      state,
      createQuestionHistoryEntry({ id: 'a1', mode: 'answer', question: 'Q1', fullAnswer: 'A1' })
    )
    state = appendQuestionHistoryEntry(
      state,
      createQuestionHistoryEntry({ id: 'a2', mode: 'answer', question: 'Q2', fullAnswer: 'A2' })
    )

    assert.equal(getSelectedQuestionHistoryEntry(state, 'answer').question, 'Q2')
    assert.deepEqual(getQuestionHistorySummary(state, 'answer'), {
      mode: 'answer',
      total: 2,
      currentIndex: 1,
      position: 2,
      canPrevious: true,
      canNext: false,
    })
  })

  it('navigates previous and next without creating entries', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, { id: 'a1', mode: 'answer', question: 'Q1' })
    state = appendQuestionHistoryEntry(state, { id: 'a2', mode: 'answer', question: 'Q2' })

    const previous = selectQuestionHistoryOffset(state, 'answer', -1)
    assert.equal(previous.answer.entries.length, 2)
    assert.equal(getSelectedQuestionHistoryEntry(previous, 'answer').id, 'a1')

    const next = selectQuestionHistoryOffset(previous, 'answer', 1)
    assert.equal(next.answer.entries.length, 2)
    assert.equal(getSelectedQuestionHistoryEntry(next, 'answer').id, 'a2')
  })

  it('keeps answer and screen histories isolated', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, { id: 'a1', mode: 'answer', question: 'Answer Q' })
    state = appendQuestionHistoryEntry(state, { id: 's1', mode: 'screen', question: 'Screen Q' })
    state = selectQuestionHistoryOffset(state, 'screen', -1)

    assert.equal(getSelectedQuestionHistoryEntry(state, 'answer').question, 'Answer Q')
    assert.equal(getSelectedQuestionHistoryEntry(state, 'screen').question, 'Screen Q')
    assert.equal(state.answer.entries.length, 1)
    assert.equal(state.screen.entries.length, 1)
  })

  it('stores original and resolved follow-up questions without changing visible question', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, {
      id: 'a1',
      mode: 'answer',
      question: 'What are its examples?',
      originalQuestion: 'What are its examples?',
      resolvedQuestion: 'What are examples of supervised learning?',
      followUpDetected: true,
      followUpContextEntryIds: ['a0'],
      topic: 'supervised learning',
    })

    const entry = getSelectedQuestionHistoryEntry(state, 'answer')
    assert.equal(entry.question, 'What are its examples?')
    assert.equal(entry.originalQuestion, 'What are its examples?')
    assert.equal(entry.resolvedQuestion, 'What are examples of supervised learning?')
    assert.deepEqual(entry.followUpContextEntryIds, ['a0'])
  })

  it('updates only the matching request for stale-response protection', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, {
      id: 'a1',
      mode: 'answer',
      requestId: 'new',
      question: 'Latest',
      status: 'generating',
    })

    const stale = updateQuestionHistoryEntry(
      state,
      'answer',
      'a1',
      { fullAnswer: 'old answer' },
      { requestId: 'old' }
    )
    assert.equal(getSelectedQuestionHistoryEntry(stale, 'answer').fullAnswer, '')

    const fresh = updateQuestionHistoryEntry(
      stale,
      'answer',
      'a1',
      { fullAnswer: 'new answer', displayedAnswer: 'new answer', status: 'complete' },
      { requestId: 'new' }
    )
    assert.equal(getSelectedQuestionHistoryEntry(fresh, 'answer').fullAnswer, 'new answer')
    assert.equal(getSelectedQuestionHistoryEntry(fresh, 'answer').status, 'complete')
  })

  it('stores clean answers while keeping category separate', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, {
      id: 'a1',
      mode: 'answer',
      question: 'What is AI?',
      fullAnswer: '[[category:technical]]\nAI is software.',
      displayedAnswer: '[[category:technical]]\nAI is software.',
      category: 'technical',
    })

    const entry = getSelectedQuestionHistoryEntry(state, 'answer')
    assert.equal(entry.fullAnswer, 'AI is software.')
    assert.equal(entry.displayedAnswer, 'AI is software.')
    assert.equal(entry.category, 'technical')
  })

  it('reports disabled navigation for a single entry', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, { id: 'a1', mode: 'answer', question: 'Only Q' })

    assert.deepEqual(getQuestionHistorySummary(state, 'answer'), {
      mode: 'answer',
      total: 1,
      currentIndex: 0,
      position: 1,
      canPrevious: false,
      canNext: false,
    })
  })

  it('ignores chat entries so chat remains a separate thread', () => {
    const state = createQuestionHistoryState()
    const next = appendQuestionHistoryEntry(state, { id: 'c1', mode: 'chat', question: 'Chat Q' })

    assert.equal(next, state)
    assert.equal(next.answer.entries.length, 0)
    assert.equal(next.screen.entries.length, 0)
  })

  it('enforces the configured history limit', () => {
    let state = createQuestionHistoryState()
    state = appendQuestionHistoryEntry(state, { id: 'a1', mode: 'answer', question: 'Q1' }, 2)
    state = appendQuestionHistoryEntry(state, { id: 'a2', mode: 'answer', question: 'Q2' }, 2)
    state = appendQuestionHistoryEntry(state, { id: 'a3', mode: 'answer', question: 'Q3' }, 2)

    assert.deepEqual(
      state.answer.entries.map((entry) => entry.id),
      ['a2', 'a3']
    )
    assert.equal(getSelectedQuestionHistoryEntry(state, 'answer').id, 'a3')
  })
})
