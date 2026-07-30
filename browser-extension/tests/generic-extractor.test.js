import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { extractFromHtml } from '../extractors/generic-extractor.js'

function fixture(name) {
  return readFileSync(new URL(`../fixtures/${name}`, import.meta.url), 'utf8')
}

test('generic coding fixture extracts title, statement, sections, constraints, and examples', () => {
  const result = extractFromHtml(fixture('generic-coding-question.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, 'Array Pair Sum')
  assert.match(result.question.statement, /array of integers/)
  assert.match(result.question.input_format, /first line contains n/i)
  assert.match(result.question.output_format, /indices/i)
  assert.ok(result.question.constraints.length >= 1)
  assert.equal(result.question.examples.length, 1)
  assert.equal(result.question.options.length, 0)
  assert.equal(result.extraction.complete, true)
})

test('function and class stubs extract signatures and starter code', () => {
  const fn = extractFromHtml(fixture('function-stub-question.html'))
  assert.equal(fn.question.question_type, 'coding')
  assert.equal(fn.question.code_context.function_signature, 'function normalizeUsername(value)')
  assert.match(fn.question.code_context.starter_code, /normalizeUsername/)
  assert.equal(fn.question.code_context.submission_mode, null)

  const cls = extractFromHtml(fixture('class-stub-question.html'))
  assert.equal(cls.question.code_context.class_name, 'CacheCounter')
  assert.equal(cls.question.code_context.submission_mode, null)
})

test('MCQ fixture extracts options and ignores wrong preselected state', () => {
  const result = extractFromHtml(fixture('mcq-question.html'))
  assert.equal(result.question.question_type, 'mcq')
  assert.equal(result.question.options.length, 4)
  assert.equal(result.question.answer.text, null)
  assert.equal(result.question.answer.code, null)
  assert.ok(!JSON.stringify(result).includes('checked'))
})

test('noisy page ignores navigation, sidebar, and footer', () => {
  const result = extractFromHtml(fixture('noisy-page.html'))
  const serialized = JSON.stringify(result)
  assert.match(result.question.statement, /daily inventory counts/)
  assert.doesNotMatch(serialized, /Billing|Advertisement|Terms Privacy/)
})

test('coding fixture remains complete when optional output format is absent', () => {
  const result = extractFromHtml(fixture('incomplete-question.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.output_format, null)
  assert.equal(result.extraction.complete, true)
  assert.deepEqual(result.extraction.missing_sections, [])
})

test('runtime content script treats input/output sections as coding signals', () => {
  const contentScript = readFileSync(new URL('../content-script.js', import.meta.url), 'utf8')
  assert.match(contentScript, /sectionMap\.input_format/)
  assert.match(contentScript, /sectionMap\.output_format/)
  assert.match(contentScript, /readinessWarnings/)
  assert.match(contentScript, /dynamic_content_may_be_incomplete/)
  assert.match(contentScript, /collectEditorEvidence/)
  assert.match(contentScript, /editor_present/)
  assert.match(contentScript, /monaco_view_lines/)
  assert.match(contentScript, /ace_text_layer/)
  assert.match(contentScript, /codemirror6_lines/)
  assert.match(contentScript, /codemirror5_lines/)
  assert.match(contentScript, /editor_code_unavailable/)
  assert.match(contentScript, /editor_boilerplate_only/)
  assert.match(contentScript, /collectEditorEvidenceWithFallback/)
  assert.match(contentScript, /document_single_editor_fallback/)
  assert.match(contentScript, /editor_scope/)
  assert.doesNotMatch(contentScript, /selected\.editorTextAvailable\)\s*return/)
  assert.match(contentScript, /section_boundary_stop_count/)
  assert.match(contentScript, /editor_section_excluded_count/)
  assert.match(contentScript, /classifyEditorText/)
  assert.match(contentScript, /extractConstraints/)
  assert.match(contentScript, /isConstraintLine/)
  assert.match(contentScript, /parseExampleHeading/)
  assert.match(contentScript, /semanticExampleBlocks/)
  assert.match(contentScript, /groupSemanticExampleBlocks/)
  assert.match(contentScript, /examplesFromTableText/)
  assert.match(contentScript, /kind/)
  assert.match(contentScript, /label/)
  assert.match(contentScript, /index/)
  assert.match(contentScript, /custom input/)
  assert.match(contentScript, /test result/)
})

test('hidden/script/style content and raw HTML are not returned', () => {
  const result = extractFromHtml(fixture('hidden-content.html'))
  const serialized = JSON.stringify(result)
  assert.match(result.question.statement, /input validation/)
  assert.doesNotMatch(serialized, /Hidden solution|must-not-extract|<html|<body|<script|<style/)
})

test('coding without input or output remains ready when statement and starter code are usable', () => {
  const result = extractFromHtml(fixture('coding-no-io.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
  assert.match(result.question.code_context.starter_code, /def rotate/)
  assert.equal(result.extraction.complete, true)
})

test('debugging and output prediction are detected from generic wording plus code', () => {
  const debugging = extractFromHtml(fixture('debugging-question.html'))
  assert.equal(debugging.question.question_type, 'debugging')
  assert.equal(debugging.extraction.complete, true)

  const output = extractFromHtml(fixture('output-prediction-question.html'))
  assert.equal(output.question.question_type, 'output_prediction')
  assert.equal(output.extraction.complete, true)
})

test('MCQ options exclude unrelated buttons and preserve selected-option independence', () => {
  const result = extractFromHtml(fixture('mcq-with-controls.html'))
  assert.equal(result.question.question_type, 'mcq')
  assert.deepEqual(result.question.options.map((option) => option.label), ['a', 'b', 'c', 'd'])
  assert.equal(result.question.answer.text, null)
  assert.doesNotMatch(JSON.stringify(result), /Submit Answer|Previous|Next/)
})

test('technical question and unrelated document title are handled generically', () => {
  const technical = extractFromHtml(fixture('technical-question.html'))
  assert.equal(technical.question.question_type, 'technical')
  assert.match(technical.question.statement, /idempotency keys/)

  const titled = extractFromHtml(fixture('unrelated-title.html'))
  assert.equal(titled.question.title, 'Queue Reconstruction')
  assert.doesNotMatch(titled.question.title, /Training Portal/)
})

test('nested scroll content and generic editor-like code are extracted', () => {
  const nested = extractFromHtml(fixture('nested-scroll-question.html'))
  assert.equal(nested.question.question_type, 'coding')
  assert.match(nested.question.input_format, /single string/)
  assert.match(nested.question.output_format, /integer length/)

  const editor = extractFromHtml(fixture('editor-like-code.html'))
  assert.equal(editor.question.question_type, 'coding')
  assert.match(editor.question.code_context.starter_code, /normalizeEmail/)
  assert.match(editor.question.code_context.function_signature, /function normalizeEmail/)
})

test('editor presence is independent from readable starter code', () => {
  const inaccessible = extractFromHtml(fixture('editor-code-unavailable.html'))
  assert.equal(inaccessible.question.question_type, 'coding')
  assert.equal(inaccessible.question.code_context.editor_present, true)
  assert.equal(inaccessible.question.code_context.starter_code, null)
  assert.equal(inaccessible.question.code_context.code_extraction_warning, 'editor_code_unavailable')
  assert.ok(inaccessible.extraction.warnings.includes('editor_code_unavailable'))

  const statementOnly = extractFromHtml(fixture('coding-statement-no-editor.html'))
  assert.equal(statementOnly.question.code_context.editor_present, false)
  assert.equal(statementOnly.question.code_context.starter_code, null)
  assert.equal(statementOnly.extraction.complete, true)
})

test('boilerplate-only editor text is readable but not starter code', () => {
  const result = extractFromHtml(fixture('full-program-boilerplate-comment-editor.html'))
  const context = result.question.code_context
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.extraction.complete, true)
  assert.equal(context.editor_present, true)
  assert.equal(context.editor_text_available, true)
  assert.equal(context.editor_boilerplate_only, true)
  assert.equal(context.starter_code, null)
  assert.equal(context.function_signature, null)
  assert.equal(context.class_name, null)
  assert.equal(context.code_extraction_warning, 'editor_boilerplate_only')
  assert.ok(!result.extraction.warnings.includes('editor_code_unavailable'))
  assert.ok(result.extraction.warnings.includes('editor_boilerplate_only'))
  assert.deepEqual(result.question.constraints, ['1 <= n <= 100000', '1 <= q <= 100000'])
  assert.equal(result.question.examples.length, 1)
  assert.equal(result.question.examples[0].output, '1\n2')
  assert.doesNotMatch(result.question.examples[0].output, /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(result.question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
  assert.deepEqual(countKinds(result.question.examples), { sample: 1, example: 0, test_case: 0, unknown: 0 })
  assert.equal(result.extraction.diagnostics.unknown_example_count, 0)
  assert.equal(result.extraction.diagnostics.orphan_example_part_count, 0)
})

test('unreadable editor still emits editor_code_unavailable', () => {
  const result = extractFromHtml(fixture('full-program-no-readable-editor-text.html'))
  const context = result.question.code_context
  assert.equal(context.editor_present, true)
  assert.equal(context.editor_text_available, false)
  assert.equal(context.editor_boilerplate_only, false)
  assert.equal(context.starter_code, null)
  assert.equal(context.code_extraction_warning, 'editor_code_unavailable')
  assert.ok(result.extraction.warnings.includes('editor_code_unavailable'))
})

test('real stubs and program skeletons remain starter code despite placeholders', () => {
  const passStub = extractFromHtml(fixture('function-stub-with-pass.html'))
  assert.match(passStub.question.code_context.starter_code, /def solve\(\):\n    pass/)
  assert.equal(passStub.question.code_context.function_signature, 'def solve()')
  assert.equal(passStub.question.code_context.editor_boilerplate_only, false)

  const main = extractFromHtml(fixture('comment-plus-real-main.html'))
  assert.match(main.question.code_context.starter_code, /int main\(\)/)
  assert.equal(main.question.code_context.function_signature, 'int main()')
  assert.equal(main.question.code_context.editor_boilerplate_only, false)

  const commentOnly = extractFromHtml(fixture('comment-only-editor.html'))
  assert.equal(commentOnly.question.code_context.editor_text_available, true)
  assert.equal(commentOnly.question.code_context.editor_boilerplate_only, true)
  assert.equal(commentOnly.question.code_context.starter_code, null)
})

test('common editor line DOM extracts one ordered starter-code candidate', () => {
  const cases = [
    ['full-program-monaco-editor.html', 'monaco', 'int main()'],
    ['full-program-ace-editor.html', 'ace', 'int main()'],
    ['function-codemirror6-editor.html', 'codemirror6', 'function normalizeTitle(value)'],
    ['class-codemirror5-editor.html', 'codemirror5', null],
  ]

  for (const [name, editorType, signature] of cases) {
    const result = extractFromHtml(fixture(name))
    const context = result.question.code_context
    assert.equal(result.question.question_type, 'coding', name)
    assert.equal(context.editor_present, true, name)
    assert.equal(context.editor_type, editorType, name)
    assert.equal(Boolean(context.starter_code), true, name)
    assert.equal(result.extraction.diagnostics.editor_code_available, true, name)
    assert.equal(result.extraction.diagnostics.editor_present, true, name)
    assert.equal(result.extraction.diagnostics.code_line_count >= 3, true, name)
    assert.doesNotMatch(context.starter_code, /Run Code|Submit|testcase/i, name)
    if (signature) assert.equal(context.function_signature, signature, name)
  }

  const monaco = extractFromHtml(fixture('full-program-monaco-editor.html'))
  assert.match(monaco.question.code_context.starter_code, /#include <bits\/stdc\+\+\.h>\nusing namespace std;\n\nint main\(\) \{\n    \/\/ your code goes here\n\}/)
  assert.equal(monaco.question.code_context.class_name, null)
})

test('native textarea and contenteditable editors expose editor_present and code', () => {
  const textarea = extractFromHtml(fixture('editor-only-page.html'))
  assert.equal(textarea.question.code_context.editor_present, true)
  assert.equal(textarea.question.code_context.editor_type, 'native_textarea')
  assert.match(textarea.question.code_context.starter_code, /def helper/)

  const editable = extractFromHtml(fixture('contenteditable-editor.html'))
  assert.equal(editable.question.code_context.editor_present, true)
  assert.equal(editable.question.code_context.editor_type, 'contenteditable')
  assert.match(editable.question.code_context.starter_code, /function slugify/)
})

test('example code without an editor is not promoted to starter code', () => {
  const result = extractFromHtml(fixture('example-code-no-editor.html'))
  assert.equal(result.question.code_context.editor_present, false)
  assert.equal(result.question.code_context.starter_code, null)
})

test('visual-dependent pages are flagged without fabricating visual interpretation', () => {
  const result = extractFromHtml(fixture('visual-question.html'))
  assert.equal(result.question.visual_context.visual_present, true)
  assert.equal(result.question.visual_context.diagram_present, true)
  assert.equal(result.question.visual_context.image_context_required, true)
  assert.ok(result.extraction.warnings.includes('visual_context_required'))
  assert.equal(result.question.answer.text, null)
})

test('decorative SVG and canvas editor do not require image context on coding pages', () => {
  for (const name of ['coding-with-decorative-svg.html', 'coding-with-canvas-editor.html']) {
    const result = extractFromHtml(fixture(name))
    assert.equal(result.question.question_type, 'coding', name)
    assert.equal(result.question.visual_context.visual_present, true, name)
    assert.equal(result.question.visual_context.image_context_required, false, name)
    assert.equal(result.extraction.complete, true, name)
  }
})

test('full-program coding task with decorative image remains coding', () => {
  const result = extractFromHtml(fixture('full-program-with-decorative-image.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.code_context.starter_code, null)
  assert.equal(result.question.visual_context.visual_present, true)
  assert.equal(result.question.visual_context.image_context_required, false)
  assert.equal(result.extraction.complete, true)
})

test('explicit chart-dependent wording requires visual context', () => {
  const result = extractFromHtml(fixture('chart-dependent-question.html'))
  assert.equal(result.question.visual_context.visual_present, true)
  assert.equal(result.question.visual_context.chart_present, true)
  assert.equal(result.question.visual_context.image_context_required, true)
})

test('multiple similar question regions are reported as ambiguous', () => {
  const result = extractFromHtml(fixture('multiple-question-regions.html'))
  assert.equal(result.extraction.status, 'selection_required')
  assert.ok(result.extraction.warnings.includes('multiple_question_regions_detected'))
})

test('noise-only page does not fabricate a ready question', () => {
  const result = extractFromHtml(fixture('no-usable-question.html'))
  assert.equal(result.extraction.complete, false)
  assert.ok(result.extraction.missing_sections.includes('statement'))
})

test('statement plus code is sufficient for coding extraction', () => {
  const result = extractFromHtml(fixture('statement-plus-code.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.match(result.question.code_context.starter_code, /def clamp/)
  assert.equal(result.extraction.complete, true)
})

test('close candidate scores alone do not force selection_required for split coding workspaces', () => {
  const result = extractFromHtml(fixture('split-coding-workspace.html'))
  assert.equal(result.extraction.status, undefined)
  assert.equal(result.extraction.complete, true)
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.extraction.selection_strategy, 'combined_split_coding_workspace')
  assert.equal(result.extraction.diagnostics.combined_split_layout, true)
})

test('problem text and editor regions are combined into one coding question', () => {
  const result = extractFromHtml(fixture('split-coding-workspace.html'))
  assert.match(result.question.statement, /two sorted arrays/i)
  assert.match(result.question.code_context.starter_code, /mergeSorted/)
  assert.equal(result.question.answer.text, null)
  assert.equal(result.question.answer.code, null)
})

test('combined coding workspace remains ready without optional input and output sections', () => {
  const result = extractFromHtml(fixture('split-coding-no-optional-sections.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
  assert.match(result.question.code_context.starter_code, /reverse_words/)
  assert.equal(result.extraction.complete, true)
})

test('split shared workspace excludes navigation and footer text', () => {
  const result = extractFromHtml(fixture('split-coding-workspace.html'))
  const serialized = JSON.stringify(result)
  assert.doesNotMatch(serialized, /Practice Dashboard|Help Center/)
})

test('nested parent and editor candidates do not cause ambiguity', () => {
  const result = extractFromHtml(fixture('nested-editor-candidate.html'))
  assert.equal(result.extraction.status, undefined)
  assert.equal(result.question.question_type, 'coding')
  assert.match(result.question.statement, /clamped between zero and one hundred/i)
  assert.match(result.question.code_context.starter_code, /normalizeScores/)
})

test('visible duplicate responsive copies are deduplicated without ambiguity', () => {
  const result = extractFromHtml(fixture('visible-responsive-duplicate.html'))
  assert.equal(result.extraction.status, undefined)
  assert.equal(result.extraction.diagnostics.collapsed_candidate_count, 1)
  assert.match(result.question.code_context.starter_code, /countVowels/)
})

test('tutorial examples do not become independent questions before the actual task', () => {
  const result = extractFromHtml(fixture('tutorial-plus-task.html'))
  assert.equal(result.extraction.status, undefined)
  assert.equal(result.question.title, 'Last Array Value')
  assert.match(result.question.statement, /last element of an array/i)
  assert.match(result.question.code_context.starter_code, /lastValue/)
})

test('two independent coding tasks still require selection', () => {
  const result = extractFromHtml(fixture('two-independent-coding-tasks.html'))
  assert.equal(result.extraction.status, 'selection_required')
  assert.equal(result.extraction.selection_strategy, 'ambiguous_independent_question_regions')
  assert.ok(result.extraction.diagnostics.independent_question_evidence.includes('multiple_question_blocks'))
})

test('two independent MCQs still require selection', () => {
  const result = extractFromHtml(fixture('two-independent-mcqs.html'))
  assert.equal(result.extraction.status, 'selection_required')
  assert.equal(result.question.question_type, 'mcq')
  assert.ok(result.extraction.diagnostics.independent_question_evidence.includes('multiple_option_groups'))
})

test('generic extraction output does not depend on origin metadata', () => {
  const html = fixture('split-coding-workspace.html')
  const first = extractFromHtml(html, { origin: 'https://alpha.example' })
  const second = extractFromHtml(html, { origin: 'https://beta.example' })
  assert.equal(first.extraction.status, second.extraction.status)
  assert.equal(first.extraction.selection_strategy, second.extraction.selection_strategy)
  assert.equal(first.question.statement, second.question.statement)
  assert.equal(first.question.code_context.starter_code, second.question.code_context.starter_code)
})

test('main problem heading beats explanatory sentence-like heading', () => {
  const result = extractFromHtml(fixture('title-with-explanatory-subheading.html'))
  assert.equal(result.question.title, 'Coin Converter')
  assert.notEqual(result.question.title, 'Think of it as making change for money!')
})

test('numbered problem heading is preserved as title', () => {
  const result = extractFromHtml(fixture('numbered-coding-title.html'))
  assert.equal(result.question.title, '12. Integer to Roman')
})

test('example input and output pairs do not become global format sections', () => {
  const result = extractFromHtml(fixture('example-only-io-pairs.html'))
  assert.equal(result.question.title, '12. Integer to Roman')
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(
    result.question.examples.map((example) => [example.kind, example.label, example.index]),
    [['example', 'Example 1', 1], ['example', 'Example 2', 2], ['example', 'Example 3', 3]]
  )
  assert.equal(result.question.examples[0].input, 'num = 3749')
  assert.equal(result.question.examples[0].output, '"MMMDCCXLIX"')
  assert.equal(result.extraction.complete, true)
})

test('global format sections and example fields can coexist without promotion', () => {
  const result = extractFromHtml(fixture('global-format-plus-example.html'))
  assert.match(result.question.input_format, /first line contains n/i)
  assert.match(result.question.output_format, /integers separated by spaces/i)
  assert.equal(result.question.examples.length, 1)
  assert.equal(result.question.examples[0].kind, 'example')
  assert.equal(result.question.examples[0].label, 'Example')
  assert.equal(result.question.examples[0].index, null)
  assert.equal(result.question.examples[0].input, '3 1 2 3')
  assert.equal(result.question.examples[0].output, '1 2 3')
})

test('sample input and output parts stay in examples with metadata', () => {
  const result = extractFromHtml(fixture('sample-io-pair.html'))
  assert.equal(result.question.examples.length, 1)
  assert.deepEqual(result.question.examples[0], {
    kind: 'sample',
    label: 'Sample',
    index: null,
    input: '3 7',
    output: '21',
    explanation: null,
    text: null,
  })
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
})

test('numbered sample pairs preserve index and do not cross-pair', () => {
  const result = extractFromHtml(fixture('numbered-sample-pairs.html'))
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['sample', 'Sample 1', 1, '3 7', '10'],
    ['sample', 'Sample 2', 2, '7 8', '15'],
  ])
})

test('example block preserves label, index, input, output, and explanation', () => {
  const result = extractFromHtml(fixture('example-with-explanation.html'))
  assert.deepEqual(result.question.examples[0], {
    kind: 'example',
    label: 'Example 1',
    index: 1,
    input: '3 7',
    output: '21',
    explanation: 'The result is the product of the two integers.',
    text: null,
  })
})

test('multiple examples under one heading remain separate in source order', () => {
  const result = extractFromHtml(fixture('multiple-examples-section.html'))
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['example', 'Examples', null, '1 2', '3'],
    ['example', 'Examples', null, '4 5', '9'],
  ])
})

test('mixed sample and example sections share one array with kinds preserved', () => {
  const result = extractFromHtml(fixture('mixed-sample-example.html'))
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['sample', 'Sample', null, '4', '16'],
    ['example', 'Example 2', 2, '5', '25'],
  ])
})

test('orphaned official sample parts are retained without unsafe pairing', () => {
  const result = extractFromHtml(fixture('orphan-sample-parts.html'))
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['sample', 'Sample 3', 3, 'hello', null],
    ['sample', 'Sample 4', 4, null, 'world'],
  ])
})

test('official test case uses test_case kind', () => {
  const result = extractFromHtml(fixture('official-test-case.html'))
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['test_case', 'Test Case 1', 1, '123', '3'],
  ])
})

test('custom input and run output panels are excluded from official examples', () => {
  const result = extractFromHtml(fixture('custom-input-exclusion.html'))
  assert.equal(result.question.examples.length, 1)
  assert.equal(result.question.examples[0].input, '7 3')
  assert.equal(result.question.examples[0].output, '4')
  assert.doesNotMatch(JSON.stringify(result.question.examples), /100 9|91|debug line|Custom Input|Test Result|Console Output/)
})

test('example input and output headings do not overwrite global format fields', () => {
  const result = extractFromHtml(fixture('example-format-separation.html'))
  assert.match(result.question.input_format, /first line contains n/i)
  assert.match(result.question.output_format, /integers separated by spaces/i)
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.index, example.input, example.output]), [
    ['example', 'Example', null, '3 1 2 3', '1 2 3'],
  ])
})

test('responsive duplicate examples are deduplicated and max examples is enforced', () => {
  const duplicate = extractFromHtml(fixture('responsive-duplicate-examples.html'))
  assert.equal(duplicate.question.examples.length, 1)
  assert.equal(duplicate.question.examples[0].input, '6')

  const many = extractFromHtml(fixture('more-than-max-examples.html'))
  assert.equal(many.question.examples.length, 4)
  assert.deepEqual(many.question.examples.map((example) => example.index), [1, 2, 3, 4])
})

test('coding controls and stray checkbox do not create options', () => {
  const result = extractFromHtml(fixture('coding-with-stray-controls.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.options.length, 0)
  assert.equal(result.extraction.valid_option_count, 0)
  assert.doesNotMatch(JSON.stringify(result.question.options), /Run Code|Submit|JavaScript|custom input/)
})

test('coding page with unrelated lists and labels does not create a valid MCQ group', () => {
  const result = extractFromHtml(fixture('coding-with-unrelated-lists.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.options.length, 0)
  assert.equal(result.extraction.valid_option_count, 0)
  assert.ok(result.extraction.detected_option_count > result.extraction.valid_option_count)
  assert.equal(result.extraction.valid_mcq_group, false)
  assert.equal(result.extraction.complete, true)
})

test('valid grouped radio options are extracted in order and do not populate answer', () => {
  const result = extractFromHtml(fixture('valid-radio-mcq.html'))
  assert.equal(result.question.question_type, 'mcq')
  assert.deepEqual(result.question.options.map((option) => option.label), ['A', 'B', 'C', 'D'])
  assert.deepEqual(result.question.options.map((option) => option.text), ['Stack', 'Queue', 'Tree', 'Graph'])
  assert.equal(result.extraction.valid_option_count, 4)
  assert.equal(result.extraction.valid_mcq_group, true)
  assert.equal(result.question.answer.text, null)
  assert.equal(result.question.answer.code, null)
  assert.doesNotMatch(JSON.stringify(result), /checked/)
})

test('explicit labelled lists are MCQs but ordinary lists are not', () => {
  const mcq = extractFromHtml(fixture('labelled-list-mcq.html'))
  assert.equal(mcq.question.question_type, 'mcq')
  assert.deepEqual(mcq.question.options.map((option) => option.label), ['A', 'B', 'C', 'D'])
  assert.equal(mcq.extraction.valid_mcq_group, true)

  const coding = extractFromHtml(fixture('coding-with-unrelated-lists.html'))
  assert.equal(coding.question.question_type, 'coding')
  assert.equal(coding.question.options.length, 0)
})

test('MCQ inside line-class layout is not mistaken for coding', () => {
  const result = extractFromHtml(fixture('mcq-with-line-class-wrapper.html'))
  assert.equal(result.question.question_type, 'mcq')
  assert.equal(result.question.options.length, 4)
  assert.equal(result.question.code_context.starter_code, null)
})

test('single malformed option candidate is rejected', () => {
  const result = extractFromHtml(fixture('malformed-single-option.html'))
  assert.notEqual(result.question.question_type, 'mcq')
  assert.equal(result.question.options.length, 0)
})

test('coding workspace with leaked choice-like controls remains coding with no options', () => {
  const result = extractFromHtml(fixture('coding-with-leaked-option-groups.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.options.length, 0)
  assert.equal(result.extraction.complete, true)
  assert.match(result.question.code_context.starter_code, /formatInteger/)
})

test('collapsed candidate diagnostics report no effective second score', () => {
  const result = extractFromHtml(fixture('split-coding-workspace.html'))
  assert.equal(result.extraction.diagnostics.collapsed_candidate_count, 1)
  assert.equal(result.extraction.diagnostics.second_score, null)
  assert.equal(typeof result.extraction.diagnostics.initial_top_score, 'number')
  assert.equal(typeof result.extraction.diagnostics.initial_second_score, 'number')
})

test('final HackerRank-shaped extraction keeps official examples only and marks folded editor code partial', () => {
  const result = extractFromHtml(fixture('final-quality-hackerrank-shape.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, 'Merge the Tools!')
  assert.match(result.question.output_format, /Print each subsequence/i)
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(countKinds(result.question.examples), { sample: 1, example: 1, test_case: 0, unknown: 0 })
  assert.equal(result.question.examples[0].input, 'AAABCADDE\n3')
  assert.match(result.question.examples[0].explanation, /duplicate characters/i)
  assert.equal(result.question.code_context.editor_type, 'monaco')
  assert.equal(result.extraction.diagnostics.editor_candidate_count, 1)
  assert.equal(result.question.code_context.code_may_be_partial, true)
  assert.ok(result.extraction.warnings.includes('editor_code_may_be_partial'))
  assert.ok(result.extraction.confidence < 1)
})

test('final LeetCode-shaped extraction has three examples and return wording remains actionable', () => {
  const result = extractFromHtml(fixture('final-quality-leetcode-shape.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, '3Sum')
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.match(result.question.statement, /return all the triplets/i)
  assert.equal(result.question.code_context.editor_type, 'monaco')
  assert.deepEqual(result.question.constraints, [
    '3 <= nums.length <= 3000',
    '-10^5 <= nums[i] <= 10^5',
  ])
  assert.doesNotMatch(JSON.stringify(result.question.constraints), /threeSum|vector|class Solution|public:|int main|return/)
  assert.equal(Boolean(result.question.code_context.starter_code), true)
  assert.match(result.question.code_context.function_signature, /threeSum/)
  assert.equal(result.question.code_context.class_name, 'Solution')
  assert.equal(result.question.output_format, null)
  assert.equal(result.extraction.diagnostics.editor_candidate_count, 1)
  assert.equal(result.question.code_context.code_may_be_partial, false)
  assert.ok(result.extraction.confidence <= 0.99)
})

test('final CodeChef-shaped extraction pairs sample explanations and excludes runtime panels', () => {
  const result = extractFromHtml(fixture('final-quality-codechef-shape.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, 'Chef and Instant Noodles')
  assert.equal(result.question.input_format !== null, true)
  assert.equal(result.question.output_format !== null, true)
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(countKinds(result.question.examples), { sample: 2, example: 0, test_case: 0, unknown: 0 })
  assert.match(result.question.examples[0].explanation, /six servings/i)
  assert.match(result.question.examples[1].explanation, /twenty servings/i)
  assert.doesNotMatch(JSON.stringify(result.question.examples), /Custom Input|Test Result|run-panel/)
  assert.equal(result.question.code_context.editor_type, 'ace')
  assert.equal(result.extraction.diagnostics.editor_candidate_count, 1)
  assert.equal(result.question.code_context.code_may_be_partial, false)
  assert.ok(result.extraction.confidence <= 0.99)
})

test('parent and child example fallback paths emit one structured example', () => {
  const result = extractFromHtml(fixture('parent-child-example-duplicate.html'))
  assert.equal(result.question.examples.length, 1)
  assert.deepEqual(result.question.examples[0], {
    kind: 'example',
    label: 'Example 1',
    index: 1,
    input: '1 2',
    output: '3',
    explanation: 'add both values.',
    text: null,
  })
})

test('prints and returns headings are output contracts, not examples', () => {
  const result = extractFromHtml(fixture('prints-returns-section.html'))
  assert.equal(result.question.examples.length, 0)
  assert.match(result.question.output_format, /formatted value|Print the value/i)
})

test('independent questions keep selection_required with explicit initial-score diagnostics', () => {
  const result = extractFromHtml(fixture('two-independent-mcqs.html'))
  assert.equal(result.extraction.status, 'selection_required')
  assert.equal(result.extraction.diagnostics.second_score, null)
  assert.equal(typeof result.extraction.diagnostics.initial_second_score, 'number')
  assert.ok(result.extraction.diagnostics.independent_question_evidence.length > 0)
})

test('semantic grouping keeps LeetCode-style examples structured without unknown orphans', () => {
  const result = extractFromHtml(fixture('leetcode-style-three-examples.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.deepEqual(result.question.examples.map((example) => example.explanation), [
    'The values sum to zero.',
    'No valid triplet exists.',
    'All values can be used.',
  ])
  assert.equal(result.question.output_format, null)
  assert.equal(result.extraction.diagnostics.unknown_example_count, 0)
  assert.equal(result.extraction.diagnostics.orphan_example_part_count, 0)
})

test('LeetCode-style explanation siblings attach to their parent examples', () => {
  const result = extractFromHtml(fixture('leetcode-style-three-examples-with-explanations.html'))
  const diagnostics = result.extraction.diagnostics
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, 'Best Time to Buy and Sell Stock III')
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.deepEqual(result.question.examples.map((example) => [example.label, example.index, example.input, example.output, example.explanation]), [
    ['Example 1', 1, 'prices = [3,3,5,0,0,3,1,4]', '6', 'Buy on day 4 and sell on day 6, then buy on day 7 and sell on day 8.'],
    ['Example 2', 2, 'prices = [1,2,3,4,5]', '4', 'Buy on day 1 and sell on day 5.'],
    ['Example 3', 3, 'prices = [7,6,4,3,1]', '0', null],
  ])
  assert.equal(diagnostics.final_example_count, 3)
  assert.ok(diagnostics.raw_example_candidate_count > diagnostics.final_example_count)
  assert.ok(diagnostics.duplicate_example_count > 0)
  assert.equal(diagnostics.unknown_example_count, 0)
  assert.equal(diagnostics.orphan_example_part_count, 0)
  assert.ok(!result.extraction.warnings.includes('unknown_examples_detected'))
  assert.ok(!result.extraction.warnings.includes('orphan_example_part'))
  assert.ok(!result.extraction.warnings.includes('examples_truncated'))
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
  assert.equal(result.question.code_context.editor_present, true)
  assert.equal(result.question.code_context.editor_type, 'monaco')
  assert.match(result.question.code_context.starter_code, /maxProfit/)
})

test('standalone explanation blocks attach unless no active example exists', () => {
  const sibling = extractFromHtml(fixture('example-explanation-sibling-blocks.html'))
  assert.equal(sibling.question.examples.length, 2)
  assert.deepEqual(sibling.question.examples.map((example) => example.explanation), [
    'Buy at one and sell at five.',
    'No profitable trade exists.',
  ])
  assert.equal(sibling.extraction.diagnostics.unknown_example_count, 0)
  assert.equal(sibling.extraction.diagnostics.orphan_example_part_count, 0)
  assert.ok(sibling.extraction.diagnostics.raw_example_candidate_count > sibling.extraction.diagnostics.final_example_count)
  assert.ok(sibling.extraction.diagnostics.duplicate_example_count > 0)
  assert.deepEqual(sibling.extraction.warnings, [])

  const orphan = extractFromHtml(fixture('orphan-explanation-no-active-example.html'))
  assert.equal(orphan.question.examples.length, 1)
  assert.equal(orphan.question.examples[0].kind, 'unknown')
  assert.match(orphan.question.examples[0].explanation, /no official example heading/i)
  assert.equal(orphan.extraction.diagnostics.unknown_example_count, 1)
  assert.equal(orphan.extraction.diagnostics.orphan_example_part_count, 1)
  assert.ok(orphan.extraction.warnings.includes('unknown_examples_detected'))
  assert.ok(orphan.extraction.warnings.includes('orphan_example_part'))
})

test('semantic grouping keeps CodeChef-style sample cards paired with explanations', () => {
  const result = extractFromHtml(fixture('codechef-style-two-samples.html'))
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(countKinds(result.question.examples), { sample: 2, example: 0, test_case: 0, unknown: 0 })
  assert.deepEqual(result.question.examples.map((example) => [example.label, example.index, example.input, example.output, example.explanation]), [
    ['Sample 1', 1, '2 3', '6', 'Two packets make six servings.'],
    ['Sample 2', 2, '5 4', '20', 'Five packets make twenty servings.'],
  ])
  assert.doesNotMatch(JSON.stringify(result.question.examples), /Custom Input|Test Result/)
})

test('narrative example and official sample share one examples array in source order', () => {
  const result = extractFromHtml(fixture('hackerrank-style-sample-and-narrative-example.html'))
  assert.equal(result.question.examples.length, 2)
  assert.deepEqual(result.question.examples.map((example) => [example.kind, example.label, example.input, example.output, Boolean(example.text)]), [
    ['example', 'Example', null, null, true],
    ['sample', 'Sample', 'AABCAAADA\n3', 'AB\nCA\nAD', false],
  ])
  assert.match(result.question.output_format, /Print each unique chunk/)
})

test('official example tables normalize without fabricating extra unknown examples', () => {
  const io = extractFromHtml(fixture('input-output-table-examples.html'))
  assert.deepEqual(io.question.examples.map((example) => [example.kind, example.index, example.input, example.output]), [
    ['sample', 1, '3 7', '21'],
    ['sample', 2, '7 8', '56'],
  ])

  const stdin = extractFromHtml(fixture('stdin-function-table.html'))
  assert.equal(stdin.question.examples.length, 1)
  assert.equal(stdin.question.examples[0].input, 'AABCAAADA\n3')
  assert.equal(stdin.question.examples[0].output, 'AB\nCA\nAD')
  assert.equal(stdin.extraction.diagnostics.unknown_example_count, 0)
  assert.equal(stdin.extraction.diagnostics.duplicate_example_count, 0)
})

test('runtime panels and sample output headings stay out of global format fields', () => {
  const custom = extractFromHtml(fixture('custom-input-same-as-sample.html'))
  assert.equal(custom.question.examples.length, 1)
  assert.equal(custom.question.examples[0].input, '3 7')
  assert.equal(custom.question.examples[0].output, '-4')
  assert.doesNotMatch(JSON.stringify(custom.question.examples), /Run Output|Custom Input/)

  const runtime = extractFromHtml(fixture('runtime-output-panel.html'))
  assert.equal(runtime.question.examples.length, 0)

  const sampleOutput = extractFromHtml(fixture('sample-output-section.html'))
  assert.equal(sampleOutput.question.examples[0].output, 'hello')
  assert.equal(sampleOutput.question.output_format, null)
})

test('inline return prose does not become output format or full-program evidence', () => {
  const method = extractFromHtml(fixture('method-return-statement.html'))
  assert.equal(method.question.question_type, 'coding')
  assert.equal(method.question.output_format, null)

  const prose = extractFromHtml(fixture('non-coding-return-prose.html'))
  assert.notEqual(prose.question.question_type, 'coding')
  assert.equal(prose.question.output_format, null)
})

test('generic constraints extract from headings, paragraphs, tables, unicode, and inline text', () => {
  assert.deepEqual(extractFromHtml(fixture('constraints-heading-list.html')).question.constraints, [
    '1 <= N <= 100000',
    '1 <= Q <= 100000',
  ])
  assert.deepEqual(extractFromHtml(fixture('constraints-heading-paragraph.html')).question.constraints, [
    'N is between 1 and 10^5.',
    'The total number of queries does not exceed 2 * 10^5.',
  ])
  assert.deepEqual(extractFromHtml(fixture('constraints-table.html')).question.constraints, [
    '1 <= N <= 10^5',
    '1 <= Q <= 10^5',
  ])
  assert.deepEqual(extractFromHtml(fixture('unicode-constraints.html')).question.constraints, [
    '1 ≤ N ≤ 10^5',
    '0 ≥ L ≥ -10^5',
  ])
  assert.deepEqual(extractFromHtml(fixture('statement-inline-constraints.html')).question.constraints, [
    '1 <= N <= 100000',
    'The sum of N over all test cases does not exceed 2 * 10^5.',
  ])
  assert.deepEqual(extractFromHtml(fixture('constraints-with-mathjax-like-spans.html')).question.constraints, [
    '1 ≤ T ≤ 10',
    '0 ≤ ai ≤ 10^9',
  ])
})

test('constraint extraction avoids sample, editor, and solution false positives', () => {
  assert.deepEqual(extractFromHtml(fixture('sample-values-not-constraints.html')).question.constraints, [])
  assert.deepEqual(extractFromHtml(fixture('editor-code-not-constraints.html')).question.constraints, [])
  assert.deepEqual(extractFromHtml(fixture('solution-complexity-not-constraints.html')).question.constraints, [])
  assert.deepEqual(extractFromHtml(fixture('constraints-before-samples.html')).question.constraints, ['1 <= N <= 50'])
  assert.deepEqual(extractFromHtml(fixture('same-node-constraints.html')).question.constraints, ['1 <= N <= 100000'])
})

test('LeetCode-style regex page keeps prose constraints and three examples', () => {
  const result = extractFromHtml(fixture('leetcode-regex-counts.html'))
  assert.equal(result.question.constraints.length, 5)
  assert.deepEqual(result.question.constraints, [
    '1 <= s.length <= 20',
    '1 <= p.length <= 20',
    's contains only lowercase English letters.',
    "p contains only lowercase English letters, '.', and '*'.",
    "It is guaranteed for each appearance of the character '*', there will be a previous valid character to match.",
  ])
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
})

test('Unicode constraints from HackerRank and CodeChef shaped pages are counted', () => {
  const result = extractFromHtml(`
    <main>
      <section class="problem">
        <h1>Array Manipulation</h1>
        <p>Apply range update queries and print the maximum value.</p>
        <h2>Input Format</h2>
        <p>The first line contains n and q.</p>
        <h2>Constraints</h2>
        <ul>
          <li>3 \u2264 n \u2264 10\u2077</li>
          <li>1 \u2264 m \u2264 2 * 10\u2075</li>
          <li>1 \u2264 a \u2264 b \u2264 n</li>
          <li>0 \u2264 k \u2264 10\u2079</li>
        </ul>
        <h2>Sample Input</h2>
        <pre>5 3</pre>
      </section>
      <section class="code-editor"><pre>int main() { return 0; }</pre></section>
    </main>
  `)
  assert.deepEqual(result.question.constraints, [
    '3 ≤ n ≤ 10^7',
    '1 ≤ m ≤ 2 * 10^5',
    '1 ≤ a ≤ b ≤ n',
    '0 ≤ k ≤ 10^9',
  ])
})

test('hard regression: LeetCode sibling editor layout keeps starter code, examples, and constraints exact', () => {
  const result = extractFromHtml(fixture('leetcode-editor-sibling-layout.html'))
  const diagnostics = result.extraction.diagnostics
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.title, 'Best Time to Buy and Sell Stock III')
  assert.equal(Boolean(result.question.code_context.starter_code), true)
  assert.match(result.question.code_context.function_signature, /maxProfit/)
  assert.equal(result.question.code_context.class_name, 'Solution')
  assert.equal(result.question.code_context.editor_present, true)
  assert.ok(['document_single_editor_fallback', 'selected_root'].includes(result.question.code_context.editor_scope))
  assert.equal(result.question.input_format, null)
  assert.equal(result.question.output_format, null)
  assert.deepEqual(result.question.constraints, [
    '1 <= prices.length <= 10^5',
    '0 <= prices[i] <= 10^5',
  ])
  assert.doesNotMatch(JSON.stringify(result.question.constraints), /class Solution|public|vector|maxProfit/)
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.deepEqual(result.question.examples.map((example) => example.explanation), [
    'Buy on day 4 and sell on day 6, then buy on day 7 and sell on day 8.',
    'Buy on day 1 and sell on day 5.',
    null,
  ])
  assert.equal(diagnostics.orphan_example_part_count, 0)
  assert.ok(!result.extraction.warnings.includes('examples_truncated'))
})

test('hard regression: HackerRank boilerplate editor keeps constraints and clean sample output', () => {
  const result = extractFromHtml(fixture('hackerrank-visible-constraints-boilerplate-editor.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.input_format !== null, true)
  assert.equal(result.question.output_format !== null, true)
  assert.deepEqual(result.question.constraints, [
    '1 <= n <= 100000',
    '1 <= q <= 100000',
  ])
  assert.equal(result.question.examples.length, 1)
  assert.deepEqual(countKinds(result.question.examples), { sample: 1, example: 0, test_case: 0, unknown: 0 })
  assert.equal(result.question.examples[0].output, '1\n2')
  assert.doesNotMatch(result.question.examples[0].output, /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(result.question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
  assert.equal(result.question.code_context.editor_present, true)
  assert.equal(result.question.code_context.editor_text_available, true)
  assert.equal(result.question.code_context.editor_boilerplate_only, true)
  assert.equal(Boolean(result.question.code_context.starter_code), false)
  assert.equal(result.question.code_context.code_extraction_warning, 'editor_boilerplate_only')
  assert.ok(result.extraction.warnings.includes('editor_boilerplate_only'))
  assert.ok(!result.extraction.warnings.includes('editor_code_unavailable'))
})

test('hard regression: constraints, examples, and cleaned question never include editor code', () => {
  const constraints = extractFromHtml(fixture('constraints-code-pollution.html'))
  assert.deepEqual(constraints.question.constraints, [
    '3 <= nums.length <= 3000',
    '-10^5 <= nums[i] <= 10^5',
  ])
  assert.doesNotMatch(JSON.stringify(constraints.question.constraints), /class Solution|vector|threeSum|public/)
  assert.equal(Boolean(constraints.question.code_context.starter_code), true)

  const examples = extractFromHtml(fixture('sample-output-editor-leakage.html'))
  assert.equal(examples.question.examples.length, 1)
  assert.equal(examples.question.examples[0].output, '3')
  assert.doesNotMatch(JSON.stringify(examples.question.examples), /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(examples.question.statement || '', /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(examples.question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
})

test('hard regression: LeetCode explanations attach without unknown examples or truncation', () => {
  const result = extractFromHtml(fixture('leetcode-explanations-no-unknown.html'))
  assert.equal(result.question.examples.length, 3)
  assert.deepEqual(countKinds(result.question.examples), { sample: 0, example: 3, test_case: 0, unknown: 0 })
  assert.equal(result.extraction.diagnostics.orphan_example_part_count, 0)
  assert.deepEqual(result.question.examples.map((example) => example.explanation), [
    'Buy on day 4 and sell on day 6, then buy on day 7 and sell on day 8.',
    'Buy on day 1 and sell on day 5.',
    null,
  ])
  assert.deepEqual(result.extraction.warnings.filter((warning) => /example|orphan|truncated/.test(warning)), [])
})

test('section collection stops before editor blocks', () => {
  const result = extractFromHtml(fixture('sample-output-before-editor.html'))
  assert.equal(result.question.examples[0].output, '1\n2')
  assert.doesNotMatch(result.question.examples[0].output, /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(result.question.cleaned_question, /Enter your code here|STDIN|STDOUT/)
  assert.doesNotMatch(result.question.statement || '', /Enter your code here|STDIN|STDOUT/)
  assert.ok(
    result.extraction.diagnostics.section_boundary_stop_count > 0 ||
    result.extraction.diagnostics.editor_section_excluded_count > 0
  )
})

test('single safe document editor fallback captures split-pane starter code', () => {
  const result = extractFromHtml(fixture('selected-root-misses-editor.html'))
  assert.equal(result.question.question_type, 'coding')
  assert.equal(result.question.code_context.editor_present, true)
  assert.equal(Boolean(result.question.code_context.starter_code), true)
  assert.match(result.question.code_context.function_signature, /threeSum/)
  assert.equal(result.question.code_context.class_name, 'Solution')
  assert.ok(['selected_root', 'document_single_editor_fallback'].includes(result.question.code_context.editor_scope))
})

test('constraint limit is enforced with safe truncation diagnostics', () => {
  const result = extractFromHtml(fixture('more-than-max-constraints.html'))
  assert.equal(result.question.constraints.length, 20)
  assert.ok(result.extraction.warnings.includes('constraints_truncated'))
  assert.equal(result.extraction.diagnostics.constraints_truncated, true)
  assert.ok(result.extraction.diagnostics.constraint_candidate_count > result.extraction.diagnostics.final_constraint_count)
})

function countKinds(examples) {
  return examples.reduce((counts, example) => {
    counts[example.kind] += 1
    return counts
  }, { sample: 0, example: 0, test_case: 0, unknown: 0 })
}
