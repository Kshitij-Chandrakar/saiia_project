import test from 'node:test'
import assert from 'node:assert/strict'

import {
  extractCopyableCode,
  getScreenAnalysisActionLabel,
  hasCopyableCode,
  hasSavedScreenResult,
  isScreenAnalysisRunning,
  shouldStartInitialScreenAnalysis,
} from './screen_mode_state.js'

test('first Analyze Screen action starts only when screen state is idle and empty', () => {
  assert.equal(shouldStartInitialScreenAnalysis({}), true)
  assert.equal(shouldStartInitialScreenAnalysis({ ocrProcessing: true }), false)
  assert.equal(shouldStartInitialScreenAnalysis({ screenAnswerGenerated: true }), false)
  assert.equal(shouldStartInitialScreenAnalysis({ screenError: 'capture failed' }), false)
})

test('saved screen result is recognized from extracted text or generated answer', () => {
  assert.equal(hasSavedScreenResult({ ocrText: 'What is React?' }), true)
  assert.equal(hasSavedScreenResult({ screenAnswerText: 'React is a UI library.' }), true)
  assert.equal(hasSavedScreenResult({ screenAnswerGenerated: true }), true)
  assert.equal(hasSavedScreenResult({}), false)
})

test('screen analysis running covers capture and answer generation phases', () => {
  assert.equal(isScreenAnalysisRunning({ ocrProcessing: true }), true)
  assert.equal(isScreenAnalysisRunning({ screenAnswerLoading: true }), true)
  assert.equal(isScreenAnalysisRunning({}), false)
})

test('screen panel action labels match execution state', () => {
  assert.equal(getScreenAnalysisActionLabel({}), 'Analyze Screen')
  assert.equal(getScreenAnalysisActionLabel({ ocrProcessing: true }), 'Analyzing...')
  assert.equal(getScreenAnalysisActionLabel({ screenError: 'failed' }), 'Analyze Screen')
  assert.equal(getScreenAnalysisActionLabel({ screenAnswerText: 'answer' }), 'Analyze Screen')
})

test('copyable screen code requires structured code or a fenced code block', () => {
  assert.equal(hasCopyableCode({ screenAnswerText: '3. c. Cuttack' }), false)
  assert.equal(hasCopyableCode({ screenAnswerText: 'Authentication verifies `identity`.' }), false)
  assert.equal(hasCopyableCode({ screenCodeAnswer: 'print("ok")' }), true)
  assert.equal(
    hasCopyableCode({
      screenAnswerText: 'Approach\n```python\nprint("ok")\n```',
    }),
    true
  )
  assert.equal(hasCopyableCode({ screenCodeAnswer: '   ', screenAnswerText: 'No code here.' }), false)
})

test('copyable screen code extracts only code text', () => {
  const structured = extractCopyableCode({ screenCodeAnswer: 'const answer = 42\nconsole.log(answer)' })
  assert.equal(structured.code, 'const answer = 42\nconsole.log(answer)')

  const fenced = extractCopyableCode({
    screenAnswerText: 'Explanation\n```js\nconst answer = 42\nconsole.log(answer)\n```\nDone',
  })
  assert.equal(fenced.language, 'js')
  assert.equal(fenced.code, 'const answer = 42\nconsole.log(answer)')
})

test('copyable code follows the selected screen history entry data', () => {
  const mcqEntry = {
    fullAnswer: '3. c. Cuttack',
    metadata: { screenCodeAnswer: '' },
  }
  const codingEntry = {
    fullAnswer: 'Approach\n```python\nprint("ok")\n```',
    metadata: { screenCodeAnswer: 'print("ok")' },
  }

  assert.equal(hasCopyableCode(mcqEntry), false)
  assert.equal(hasCopyableCode(codingEntry), true)
})
