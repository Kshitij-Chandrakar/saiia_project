import test from 'node:test'
import assert from 'node:assert/strict'

import {
  getScreenAnswerText,
  getScreenCode,
  getScreenExtractionStatus,
  getScreenQuestionType,
  getScreenQuestions,
  normalizeQuestionType,
  normalizeScreenResponse,
} from './screen_intelligence_contract.js'

const batchLegacy = {
  ok: true,
  result_mode: 'batch',
  question: 'Q3\nQ4',
  answer: '3. c. Cuttack\n4. b. Nepal',
  question_type: 'mcq',
  items: [
    {
      question_id: 'screen_question_1',
      display_number: '3',
      question: 'The Central Rice Research Station is situated in?',
      question_type: 'mcq',
      answer: 'c. Cuttack',
      confidence: 0.96,
    },
    {
      question_id: 'screen_question_2',
      display_number: '4',
      question: 'Mount Everest is located in?',
      question_type: 'mcq',
      answer: 'b. Nepal',
      confidence: 0.94,
    },
  ],
  question_count: 2,
  incomplete_question_count: 1,
  confidence: 0.95,
  screenshot_count: 1,
  screen_model_request_count: 1,
  generation_request_count: 0,
}

test('new envelope response normalizes without changing legacy answer text', () => {
  const response = {
    ...batchLegacy,
    envelope: {
      schema_version: '1.0',
      request_id: 'request_1',
      operation_id: 'operation_1',
      mode: 'screen',
      source_type: 'screen_capture',
      status: 'ready',
      browser: null,
      selected_question_id: null,
      questions: [
        {
          question_id: 'screen_question_1',
          display_number: '3',
          question: {
            question_type: 'mcq',
            statement: 'The Central Rice Research Station is situated in?',
            answer: { text: 'c. Cuttack', code: null, explanation: null },
          },
          region: null,
        },
      ],
      extraction: { complete: true, confidence: 0.95, missing_sections: [], warnings: [], method: 'screen_vision' },
    },
  }

  const normalized = normalizeScreenResponse(response)

  assert.equal(normalized.envelope.status, 'ready')
  assert.equal(normalized.questions.length, 1)
  assert.equal(getScreenAnswerText(response), batchLegacy.answer)
})

test('legacy single response builds a compatible screen envelope', () => {
  const normalized = normalizeScreenResponse({
    ok: true,
    question: 'What is an array?',
    answer: 'A collection of values.',
    question_type: 'interview',
    confidence: 0.8,
  })

  assert.equal(normalized.envelope.schema_version, '1.0')
  assert.equal(normalized.envelope.source_type, 'screen_capture')
  assert.equal(normalized.envelope.browser, null)
  assert.equal(normalized.envelope.selected_question_id, 'screen_question_1')
  assert.equal(normalized.questions[0].question.question_type, 'general')
})

test('legacy batch response preserves order and operation-level counts', () => {
  const normalized = normalizeScreenResponse(batchLegacy)

  assert.deepEqual(getScreenQuestions(batchLegacy).map((item) => item.display_number), ['3', '4'])
  assert.equal(normalized.envelope.selected_question_id, null)
  assert.equal(normalized.envelope.metrics.screenshot_count, 1)
  assert.equal(normalized.envelope.metrics.screen_model_request_count, 1)
  assert.equal(normalized.envelope.metrics.generation_request_count, 0)
  assert.equal(normalized.envelope.extraction.warnings[0], 'incomplete_questions_ignored')
})

test('malformed optional envelope falls back safely to legacy fields', () => {
  const normalized = normalizeScreenResponse({
    ...batchLegacy,
    envelope: { schema_version: 'bad', questions: 'not-array' },
  })

  assert.equal(normalized.envelope.schema_version, '1.0')
  assert.equal(normalized.questions.length, 2)
  assert.equal(getScreenExtractionStatus(normalized.legacy), 'ready')
})

test('selectors preserve current single, batch, and code rendering inputs', () => {
  const codeResponse = {
    ok: true,
    question: 'Write hello world.',
    answer: '```python\nprint("hello")\n```',
    question_type: 'coding',
    language: 'python',
    code: 'print("hello")',
  }

  assert.equal(getScreenAnswerText(batchLegacy), '3. c. Cuttack\n4. b. Nepal')
  assert.equal(getScreenQuestionType(batchLegacy), 'mcq')
  assert.equal(getScreenQuestionType({ question_type: 'output' }), 'output_prediction')
  assert.equal(getScreenCode(codeResponse), 'print("hello")')
  assert.equal(normalizeQuestionType('visual'), 'diagram')
})

test('failed legacy response becomes failed envelope and creates no questions', () => {
  const normalized = normalizeScreenResponse({
    ok: false,
    error: 'The question could not be read clearly.',
    reason: 'empty response',
  })

  assert.equal(normalized.envelope.status, 'failed')
  assert.equal(normalized.questions.length, 0)
  assert.equal(normalized.envelope.error.code, 'unreadable_screen')
})
