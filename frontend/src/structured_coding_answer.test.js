import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const panelSource = readFileSync(new URL('./components/AnswerPanel.jsx', import.meta.url), 'utf8')

describe('structured coding answer wiring', () => {
  it('stores backend coding_answer in overlay and history metadata', () => {
    assert.match(appSource, /const \[codingAnswer, setCodingAnswer\] = useState\(null\)/)
    assert.match(appSource, /codingAnswer,\s*\n\s*answerRevealActive/)
    assert.match(appSource, /codingAnswer: generatePayload\.coding_answer \|\| null/)
  })

  it('renders structured code without depending on markdown fences', () => {
    assert.match(panelSource, /overlayState\.codingAnswer/)
    assert.match(panelSource, /renderHighlightedCode\(structuredCodingAnswer\.code/)
    assert.match(panelSource, /copyToClipboard\(structuredCodingAnswer\.code\)/)
    assert.match(panelSource, /Time Complexity/)
    assert.match(panelSource, /Space Complexity/)
  })
})
