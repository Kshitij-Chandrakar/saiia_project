import test from 'node:test'
import assert from 'node:assert/strict'
import { buildEnvelope, classifyExtensionScope, collectCodingEvidence, validateEnvelope } from '../schemas/screen-intelligence-schema.js'
import { extractFromHtml } from '../extractors/generic-extractor.js'
import { readFileSync } from 'node:fs'

function fixture(name) {
  return readFileSync(new URL(`../fixtures/${name}`, import.meta.url), 'utf8')
}

const html = fixture('generic-coding-question.html')

function envelopeFor(name) {
  const extracted = extractFromHtml(fixture(name))
  return buildEnvelope({
    operation_id: 'screen_operation_scope123',
    request_id: 'screen_request_scope123',
    browser: { name: 'chrome', extension_id: null, tab_id: null, window_id: null, url_origin: 'https://example.test', page_title: name },
    question: extracted.question,
    extraction: extracted.extraction,
    timingMs: 4,
  })
}

function countKinds(examples = []) {
  return examples.reduce((counts, example) => {
    counts[example.kind] += 1
    return counts
  }, { sample: 0, example: 0, test_case: 0, unknown: 0 })
}

test('extension extraction maps to browser_extension envelope with zero OCR/model metrics', () => {
  const extracted = extractFromHtml(html)
  const envelope = buildEnvelope({
    operation_id: 'screen_operation_12345678',
    request_id: 'screen_request_12345678',
    browser: {
      name: 'chrome',
      extension_id: null,
      tab_id: null,
      window_id: null,
      url_origin: 'https://example.test',
      page_title: 'Array Pair Sum',
    },
    question: extracted.question,
    extraction: extracted.extraction,
    timingMs: 4,
  })

  assert.equal(envelope.schema_version, '1.0')
  assert.equal(envelope.source_type, 'browser_extension')
  assert.equal(envelope.extraction.method, 'generic_dom')
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.questions[0].question.question_type, 'coding')
  assert.equal(typeof envelope.questions[0].question.cleaned_question, 'string')
  assert.equal(envelope.metrics.screenshot_count, 0)
  assert.equal(envelope.metrics.screen_model_request_count, 0)
  assert.equal(envelope.metrics.generation_request_count, 0)
  assert.equal(typeof envelope.extraction.diagnostics.initial_candidate_count, 'number')
  assert.equal(typeof envelope.extraction.diagnostics.selection_strategy, 'string')
  assert.equal(Array.isArray(envelope.extraction.diagnostics.independent_question_evidence), true)
  assert.equal(envelope.operation_id, 'screen_operation_12345678')
  assert.equal(envelope.request_id, 'screen_request_12345678')
  assert.equal(envelope.questions[0].question.answer.text, null)
  assert.equal(envelope.questions[0].question.answer.code, null)
  assert.equal(validateEnvelope(envelope).ok, true)
})

test('safe editor diagnostics survive envelope construction without code content', () => {
  const extracted = extractFromHtml(fixture('full-program-monaco-editor.html'))
  const envelope = buildEnvelope({
    operation_id: 'screen_operation_editor123',
    request_id: 'screen_request_editor123',
    browser: { name: 'chrome', extension_id: null, tab_id: null, window_id: null, url_origin: 'https://example.test', page_title: 'Editor' },
    question: extracted.question,
    extraction: extracted.extraction,
    timingMs: 4,
  })
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.extraction.diagnostics.editor_present, true)
  assert.equal(envelope.extraction.diagnostics.editor_code_available, true)
  assert.equal(envelope.extraction.diagnostics.editor_type, 'monaco')
  assert.equal(envelope.extraction.diagnostics.code_extraction_method, 'monaco_view_lines')
  assert.equal(envelope.extraction.scope.starter_code_present, true)
  assert.doesNotMatch(JSON.stringify(envelope.extraction.diagnostics), /#include|int main/)
})

test('safe example diagnostics survive envelope construction without sample content', () => {
  const envelope = envelopeFor('final-quality-codechef-shape.html')
  assert.equal(envelope.extraction.diagnostics.final_example_count, 2)
  assert.equal(envelope.extraction.diagnostics.unknown_example_count, 0)
  assert.doesNotMatch(JSON.stringify(envelope.extraction.diagnostics), /Two packets|5 4|20/)
})

test('example metadata survives envelope construction', () => {
  const envelope = envelopeFor('numbered-sample-pairs.html')
  const examples = envelope.questions[0].question.examples
  assert.equal(envelope.status, 'ready')
  assert.deepEqual(examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['sample', 'Sample 1', 1, '3 7', '10'],
    ['sample', 'Sample 2', 2, '7 8', '15'],
  ])
  assert.equal(envelope.questions[0].question.answer.text, null)
  assert.equal(envelope.metrics.screenshot_count, 0)
  assert.equal(envelope.metrics.screen_model_request_count, 0)
})

test('LeetCode-style example grouping survives envelope construction without false warnings', () => {
  const envelope = envelopeFor('leetcode-style-three-examples-with-explanations.html')
  const question = envelope.questions[0].question
  const diagnostics = envelope.extraction.diagnostics
  assert.equal(envelope.status, 'ready')
  assert.equal(question.question_type, 'coding')
  assert.equal(question.title, 'Best Time to Buy and Sell Stock III')
  assert.equal(question.examples.length, 3)
  assert.deepEqual(question.examples.map((example) => [example.kind, example.label, example.index, Boolean(example.explanation)]), [
    ['example', 'Example 1', 1, true],
    ['example', 'Example 2', 2, true],
    ['example', 'Example 3', 3, false],
  ])
  assert.equal(question.input_format, null)
  assert.equal(question.output_format, null)
  assert.equal(envelope.extraction.scope.full_program_signals, false)
  assert.equal(envelope.extraction.scope.starter_code_present, true)
  assert.equal(envelope.extraction.scope.editor_present, true)
  assert.equal(diagnostics.final_example_count, 3)
  assert.equal(diagnostics.unknown_example_count, 0)
  assert.equal(diagnostics.orphan_example_part_count, 0)
  assert.ok(diagnostics.raw_example_candidate_count > diagnostics.final_example_count)
  assert.ok(diagnostics.duplicate_example_count > 0)
  assert.deepEqual(envelope.extraction.warnings.filter((warning) => /example|orphan|truncated/.test(warning)), [])
  assert.equal(question.answer.text, null)
  assert.equal(question.answer.code, null)
  assert.equal(question.answer.explanation, null)
  assert.equal(envelope.metrics.screenshot_count, 0)
  assert.equal(envelope.metrics.screen_model_request_count, 0)
  assert.equal(envelope.metrics.generation_request_count, 0)
  assert.equal(validateEnvelope(envelope).ok, true)
})

test('hard regression envelope: LeetCode sibling editor layout is ready with exact sections and scope', () => {
  const envelope = envelopeFor('leetcode-editor-sibling-layout.html')
  const question = envelope.questions[0].question
  const scope = envelope.extraction.scope
  const diagnostics = envelope.extraction.diagnostics
  assert.equal(envelope.status, 'ready')
  assert.equal(question.title, 'Best Time to Buy and Sell Stock III')
  assert.equal(Boolean(question.code_context.starter_code), true)
  assert.equal(scope.starter_code_present, true)
  assert.equal(scope.function_signature_present, true)
  assert.equal(scope.class_name_present, true)
  assert.equal(scope.editor_present, true)
  assert.equal(question.constraints.length, 2)
  assert.doesNotMatch(JSON.stringify(question.constraints), /class Solution|public|vector|maxProfit/)
  assert.equal(question.examples.length, 3)
  assert.deepEqual(countKinds(question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.equal(diagnostics.orphan_example_part_count, 0)
  assert.ok(!envelope.extraction.warnings.includes('examples_truncated'))
  assert.equal(question.output_format, null)
  assert.equal(scope.full_program_signals, false)
})

test('hard regression envelope: HackerRank boilerplate editor keeps constraints and sample output clean', () => {
  const envelope = envelopeFor('hackerrank-visible-constraints-boilerplate-editor.html')
  const question = envelope.questions[0].question
  const scope = envelope.extraction.scope
  assert.equal(envelope.status, 'ready')
  assert.equal(question.constraints.length, 2)
  assert.deepEqual(question.constraints, [
    '1 <= n <= 100000',
    '1 <= q <= 100000',
  ])
  assert.equal(question.examples.length, 1)
  assert.equal(question.examples[0].output, '1\n2')
  assert.doesNotMatch(question.examples[0].output, /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
  assert.equal(scope.full_program_signals, true)
  assert.equal(scope.editor_text_available, true)
  assert.equal(scope.editor_boilerplate_only, true)
  assert.equal(scope.starter_code_present, false)
  assert.ok(envelope.extraction.warnings.includes('editor_boilerplate_only'))
  assert.ok(!envelope.extraction.warnings.includes('editor_code_unavailable'))
})

test('hard regression envelope: editor code never pollutes constraints, examples, or cleaned question', () => {
  const polluted = envelopeFor('constraints-code-pollution.html')
  assert.equal(polluted.status, 'ready')
  assert.equal(polluted.questions[0].question.constraints.length, 2)
  assert.doesNotMatch(JSON.stringify(polluted.questions[0].question.constraints), /class Solution|vector|threeSum|public/)
  assert.equal(Boolean(polluted.questions[0].question.code_context.starter_code), true)

  const leakage = envelopeFor('sample-output-editor-leakage.html')
  const question = leakage.questions[0].question
  assert.equal(leakage.status, 'ready')
  assert.equal(question.examples.length, 1)
  assert.equal(question.examples[0].output, '3')
  assert.doesNotMatch(JSON.stringify(question.examples), /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
})

test('coding scope classifier accepts only actionable coding extraction', () => {
  const extracted = extractFromHtml(fixture('split-coding-workspace.html'))
  const scope = classifyExtensionScope(extracted)
  assert.equal(scope.supported, true)
  assert.equal(scope.scope, 'coding')
})

test('coding scope accepts LeetCode-style convert tasks with starter code', () => {
  for (const name of ['numbered-coding-title.html', 'example-only-io-pairs.html']) {
    const envelope = envelopeFor(name)
    assert.equal(envelope.status, 'ready', name)
    assert.equal(envelope.questions[0].question.question_type, 'coding', name)
  }
})

test('return wording with editor context sets coding_instruction in scope', () => {
  const envelope = envelopeFor('final-quality-leetcode-shape.html')
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.extraction.scope.coding_instruction, true)
  assert.equal(envelope.extraction.scope.starter_code_present, true)
  assert.equal(envelope.extraction.scope.function_signature_present, true)
  assert.equal(envelope.extraction.scope.class_name_present, true)
  assert.equal(envelope.extraction.scope.editor_present, true)
})

test('method-style return wording does not become full-program evidence', () => {
  const envelope = envelopeFor('method-return-statement.html')
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.extraction.scope.coding_instruction, true)
  assert.equal(envelope.extraction.scope.full_program_signals, false)
  assert.equal(envelope.questions[0].question.output_format, null)
})

test('non-coding return prose remains unsupported', () => {
  const envelope = envelopeFor('non-coding-return-prose.html')
  assert.equal(envelope.status, 'failed')
  assert.equal(envelope.error.code, 'unsupported_page')
  assert.deepEqual(envelope.questions, [])
})

test('coding scope accepts statement-only coding tasks when editor DOM is unavailable', () => {
  const envelope = envelopeFor('coding-statement-no-editor.html')
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.questions[0].question.question_type, 'coding')
  assert.equal(envelope.questions[0].question.code_context.starter_code, null)
})

test('coding evidence uses cleaned_question, statement, and function_description fallbacks', () => {
  for (const question of [
    { question_type: 'coding', cleaned_question: 'Write a function to return the sum.', code_context: { function_signature: 'sum(a, b)' }, answer: { text: null, code: null } },
    { question_type: 'coding', statement: 'Implement a method that reverses a string.', code_context: { class_name: 'Solution' }, answer: { text: null, code: null } },
    { question_type: 'coding', function_description: 'Complete the function rotateMatrix.', code_context: { starter_code: 'function rotateMatrix(grid) {}' }, answer: { text: null, code: null } },
  ]) {
    const scope = classifyExtensionScope({ question, extraction: { complete: true } })
    assert.equal(scope.supported, true, JSON.stringify(question))
  }
})

test('coding evidence recognizes legacy code fields and safe diagnostics', () => {
  const question = {
    question_type: 'coding',
    raw_question: 'Write a program to read input and print output.',
    visible_code: 'def solve():\n    pass',
    answer: { text: null, code: null },
  }
  const evidence = collectCodingEvidence({ question, extraction: { complete: true } })
  const scope = classifyExtensionScope({ question, extraction: { complete: true } })
  assert.equal(evidence.starterCodePresent, true)
  assert.equal(scope.supported, true)
  assert.equal(scope.scope_supported, true)
  assert.equal(scope.starter_code_present, true)
})

test('coding evidence reads explicit editor_present independently from starter code', () => {
  const question = {
    question_type: 'coding',
    cleaned_question: 'Given a string, implement the function to validate bracket pairs.',
    code_context: {
      editor_present: true,
      editor_type: 'generic_editor',
      starter_code: null,
      function_signature: null,
      class_name: null,
    },
    answer: { text: null, code: null },
  }
  const evidence = collectCodingEvidence({ question, extraction: { valid_mcq_group: false } })
  const scope = classifyExtensionScope({ question, extraction: { valid_mcq_group: false } })
  assert.equal(evidence.editorPresent, true)
  assert.equal(evidence.starterCodePresent, false)
  assert.equal(evidence.relevantCodePresent, true)
  assert.equal(scope.supported, true)
  assert.equal(scope.editor_present, true)
  assert.equal(scope.starter_code_present, false)
})

test('full-program boilerplate editor remains supported without pretending starter code exists', () => {
  const envelope = envelopeFor('full-program-boilerplate-comment-editor.html')
  const question = envelope.questions[0].question
  const scope = envelope.extraction.scope
  assert.equal(envelope.status, 'ready')
  assert.equal(question.question_type, 'coding')
  assert.equal(question.code_context.editor_present, true)
  assert.equal(question.code_context.editor_text_available, true)
  assert.equal(question.code_context.editor_boilerplate_only, true)
  assert.equal(question.code_context.starter_code, null)
  assert.equal(question.code_context.function_signature, null)
  assert.equal(question.code_context.code_extraction_warning, 'editor_boilerplate_only')
  assert.equal(scope.supported, true)
  assert.equal(scope.starter_code_present, false)
  assert.equal(scope.editor_present, true)
  assert.equal(scope.editor_text_available, true)
  assert.equal(scope.editor_boilerplate_only, true)
  assert.equal(scope.relevant_code_present, true)
  assert.equal(scope.full_program_signals, true)
  assert.equal(envelope.extraction.diagnostics.editor_text_available, true)
  assert.equal(envelope.extraction.diagnostics.editor_boilerplate_only, true)
  assert.equal(envelope.extraction.diagnostics.editor_code_available, false)
  assert.equal(envelope.extraction.diagnostics.final_constraint_count, 2)
  assert.equal(envelope.metrics.screenshot_count, 0)
  assert.equal(envelope.metrics.screen_model_request_count, 0)
  assert.equal(validateEnvelope(envelope).ok, true)
  assert.doesNotMatch(JSON.stringify(envelope.extraction.diagnostics), /Enter your code here|STDIN|STDOUT/)
})

test('starter code and editor context beat a false visual flag', () => {
  const scope = classifyExtensionScope({
    question: {
      question_type: 'coding',
      cleaned_question: 'Return the longest common prefix from the provided list of strings.',
      code_context: {
        starter_code: 'class Solution { string longestCommonPrefix(vector<string>& words) {} };',
        function_signature: 'string longestCommonPrefix(vector<string>& words)',
        class_name: 'Solution',
        editor_type: 'visible_code_region',
      },
      visual_context: { visual_present: true, image_context_required: true },
      answer: { text: null, code: null },
    },
    extraction: { valid_mcq_group: false },
  })
  assert.equal(scope.supported, true)
  assert.equal(scope.reason, 'coding_workspace_with_code_context')
  assert.equal(scope.visual_context_required, false)
})

test('full-program signals beat a false visual flag without starter code', () => {
  const scope = classifyExtensionScope({
    question: {
      question_type: 'coding',
      cleaned_question: 'Read input from standard input and print the answer to standard output.',
      input_format: 'The first line contains n.',
      output_format: 'Print the result.',
      code_context: { starter_code: null, function_signature: null, class_name: null, editor_type: null },
      visual_context: { visual_present: true, image_context_required: true },
      answer: { text: null, code: null },
    },
    extraction: { valid_mcq_group: false },
  })
  assert.equal(scope.supported, true)
  assert.equal(scope.reason, 'full_program_task')
  assert.equal(scope.valid_mcq_group, false)
})

test('standard MCQ returns unsupported failed envelope with OCR guidance', () => {
  const envelope = envelopeFor('mcq-question.html')
  assert.equal(envelope.status, 'failed')
  assert.equal(envelope.error.code, 'unsupported_page')
  assert.equal(envelope.error.retryable, false)
  assert.match(envelope.error.message, /Use Analyze Screen OCR/i)
  assert.deepEqual(envelope.questions, [])
  assert.equal(envelope.metrics.screenshot_count, 0)
  assert.equal(envelope.metrics.screen_model_request_count, 0)
})

test('code-based MCQ is unsupported even when code is present', () => {
  const envelope = envelopeFor('code-mcq-question.html')
  assert.equal(envelope.status, 'failed')
  assert.equal(envelope.error.code, 'unsupported_page')
  assert.deepEqual(envelope.questions, [])
  assert.equal(envelope.extraction.scope.valid_mcq_group, true)
})

test('scope ignores raw detected option counts for coding pages', () => {
  const question = {
    question_type: 'coding',
    cleaned_question: 'Given two integers, write a program to read input and print output.',
    options: [],
    answer: { text: null, code: null },
  }
  const scope = classifyExtensionScope({
    question,
    extraction: {
      valid_option_count: 4,
      detected_option_count: 6,
      valid_mcq_group: true,
    },
  })
  assert.equal(scope.supported, true)
  assert.equal(scope.valid_mcq_group, false)
})

test('coding envelope reports detected options as diagnostics only', () => {
  const envelope = envelopeFor('coding-with-unrelated-lists.html')
  assert.equal(envelope.status, 'ready')
  assert.equal(envelope.questions[0].question.question_type, 'coding')
  assert.equal(envelope.extraction.valid_option_count, 0)
  assert.ok(envelope.extraction.detected_option_count > 0)
  assert.equal(envelope.extraction.valid_mcq_group, false)
  assert.equal(envelope.extraction.scope.valid_mcq_group, false)
})

test('decorative visuals do not make coding envelopes unsupported', () => {
  for (const name of ['coding-with-decorative-svg.html', 'coding-with-canvas-editor.html', 'full-program-with-decorative-image.html', 'coding-with-false-visual-flag.html']) {
    const envelope = envelopeFor(name)
    assert.equal(envelope.status, 'ready', name)
    assert.equal(envelope.questions[0].question.question_type, 'coding', name)
    assert.equal(envelope.questions[0].question.visual_context.image_context_required, false, name)
    assert.equal(envelope.metrics.screenshot_count, 0, name)
    assert.equal(envelope.metrics.screen_model_request_count, 0, name)
  }
})

test('visual unsupported envelope preserves safe diagnostics only', () => {
  const envelope = envelopeFor('chart-dependent-question.html')
  assert.equal(envelope.status, 'failed')
  assert.equal(envelope.error.code, 'unsupported_page')
  assert.equal(envelope.extraction.candidate_count, 1)
  assert.equal(typeof envelope.extraction.selection_strategy, 'string')
  assert.equal(envelope.extraction.scope.reason, 'visual_question_uses_ocr')
  const serialized = JSON.stringify(envelope)
  assert.doesNotMatch(serialized, /Inspect the chart below/)
  assert.doesNotMatch(serialized, /<html|<body|<img|<figure/)
})

test('output prediction, technical, visual, and editor-only pages are unsupported', () => {
  for (const name of ['output-prediction-question.html', 'technical-question.html', 'visual-question.html', 'editor-only-page.html']) {
    const envelope = envelopeFor(name)
    assert.equal(envelope.status, 'failed', name)
    assert.equal(envelope.error.code, 'unsupported_page', name)
    assert.deepEqual(envelope.questions, [], name)
  }
})

test('browser metadata excludes path, query, fragment, and unsafe IDs by default', () => {
  const extracted = extractFromHtml(html)
  const envelope = buildEnvelope({
    operation_id: 'screen_operation_abcdef12',
    request_id: 'screen_request_abcdef12',
    browser: { name: 'edge', extension_id: null, tab_id: null, window_id: null, url_origin: 'https://example.test', page_title: 'Array Pair Sum' },
    question: extracted.question,
    extraction: extracted.extraction,
  })
  assert.equal(envelope.browser.url_origin, 'https://example.test')
  assert.equal(envelope.browser.tab_id, null)
  assert.equal(envelope.browser.window_id, null)
})
