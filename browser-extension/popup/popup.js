import { createPrototypeIds } from '../core/ids.js'
import { createMessage, MESSAGE_TYPES } from '../core/messages.js'
import { requestPrototypeHostPermissions } from '../core/permissions.js'

const permissionState = document.querySelector('#permission-state')
const statusNode = document.querySelector('#status')
const preview = document.querySelector('#preview')

document.querySelector('#grant').addEventListener('click', grantPermission)
document.querySelector('#check').addEventListener('click', refreshStatus)
document.querySelector('#test').addEventListener('click', testExtraction)

refreshStatus()

async function refreshStatus() {
  setStatus('Checking permission')
  const response = await chrome.runtime.sendMessage(createMessage(MESSAGE_TYPES.checkPermission))
  permissionState.textContent = response?.permission_granted ? 'Granted' : 'Not granted'
  setStatus(response?.ok ? 'Ready for prototype test' : response?.error?.code || 'Permission check failed')
}

async function grantPermission() {
  setStatus('Waiting for browser permission prompt')
  const granted = await requestPrototypeHostPermissions(chrome)
  permissionState.textContent = granted ? 'Granted' : 'Not granted'
  setStatus(granted ? 'Permission granted' : 'Permission not granted')
}

async function testExtraction() {
  preview.textContent = ''
  setStatus('Extracting active tab')
  const ids = createPrototypeIds()
  const response = await chrome.runtime.sendMessage(
    createMessage(MESSAGE_TYPES.testActiveTab, {
      ...ids,
      requested_source: 'browser_extension',
    })
  )
  const envelope = response?.envelope
  setStatus(envelope?.error?.code === 'unsupported_page' ? 'unsupported' : envelope?.status || response?.error?.code || 'Extraction failed')
  preview.textContent = JSON.stringify(summarizeEnvelope(envelope), null, 2)
}

function summarizeEnvelope(envelope) {
  if (!envelope) {
    return { status: 'no_result' }
  }
  const question = envelope.questions?.[0]?.question
  return {
    status: envelope.error?.code === 'unsupported_page' ? 'unsupported' : envelope.status,
    source_type: envelope.source_type,
    method: envelope.extraction?.method,
    error: envelope.error ? {
      code: envelope.error.code,
      message: envelope.error.message,
      retryable: envelope.error.retryable,
    } : null,
    scope: envelope.extraction?.scope || null,
    question_type: question?.question_type,
    title: question?.title,
    sections: {
      statement: Boolean(question?.statement),
      input_format: Boolean(question?.input_format),
      output_format: Boolean(question?.output_format),
      constraints: Array.isArray(question?.constraints) ? question.constraints.length : null,
      examples: question?.examples?.length || 0,
      options: question?.options?.length || 0,
      starter_code: Boolean(question?.code_context?.starter_code),
      editor_present: Boolean(question?.code_context?.editor_present),
    },
    example_kinds: countExampleKinds(question?.examples),
    example_diagnostics: {
      raw_candidates: envelope.extraction?.diagnostics?.raw_example_candidate_count ?? null,
      final_count: envelope.extraction?.diagnostics?.final_example_count ?? null,
      duplicates_removed: envelope.extraction?.diagnostics?.duplicate_example_count ?? null,
      runtime_panels_excluded: envelope.extraction?.diagnostics?.runtime_test_panel_excluded_count ?? null,
    },
    editor: {
      type: question?.code_context?.editor_type || envelope.extraction?.diagnostics?.editor_type || null,
      code_available: Boolean(question?.code_context?.starter_code || envelope.extraction?.diagnostics?.editor_code_available),
      text_available: Boolean(question?.code_context?.editor_text_available || envelope.extraction?.diagnostics?.editor_text_available),
      boilerplate_only: Boolean(question?.code_context?.editor_boilerplate_only || envelope.extraction?.diagnostics?.editor_boilerplate_only),
      extraction_method: question?.code_context?.code_extraction_method || envelope.extraction?.diagnostics?.code_extraction_method || null,
      line_count: envelope.extraction?.diagnostics?.code_line_count ?? null,
      code_may_be_partial: Boolean(question?.code_context?.code_may_be_partial || envelope.extraction?.diagnostics?.code_may_be_partial),
      warning: question?.code_context?.code_extraction_warning || envelope.extraction?.diagnostics?.code_extraction_warning || null,
    },
    confidence: envelope.extraction?.confidence,
    warnings: envelope.extraction?.warnings || [],
    diagnostics: {
      candidate_count: envelope.extraction?.candidate_count ?? null,
      selected_candidate_score: envelope.extraction?.selected_candidate_score ?? null,
      selection_strategy: envelope.extraction?.selection_strategy ?? null,
      constraint_candidate_count: envelope.extraction?.diagnostics?.constraint_candidate_count ?? null,
      final_constraint_count: envelope.extraction?.diagnostics?.final_constraint_count ?? null,
      constraints_truncated: Boolean(envelope.extraction?.diagnostics?.constraints_truncated),
      ...(envelope.extraction?.diagnostics || {}),
    },
    payload_bytes: new TextEncoder().encode(JSON.stringify(envelope)).length,
  }
}

function countExampleKinds(examples = []) {
  return examples.reduce((counts, example) => {
    const kind = ['sample', 'example', 'test_case', 'unknown'].includes(example?.kind) ? example.kind : 'unknown'
    counts[kind] += 1
    return counts
  }, { sample: 0, example: 0, test_case: 0, unknown: 0 })
}

function setStatus(value) {
  statusNode.textContent = String(value || 'Idle')
}
