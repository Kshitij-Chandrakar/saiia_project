import { test } from 'node:test'
import assert from 'node:assert/strict'
import { resumeConfirmationIsCurrent } from './resumeConfirmation.js'

test('resume confirmation rejects account, target, edits, file and eligibility changes', () => {
  const state = { account: 'owner', currentResume: { id: 'active' }, reviewCandidate: { id: 'draft' }, resumeRecord: { id: 'draft' }, file: {}, draftProfile: { full_name: 'Unsaved' }, phase: 'needs_review', confirmPending: false, deletePending: false, rebuildPending: false }
  assert.equal(resumeConfirmationIsCurrent(state, { ...state }, false), true)
  for (const change of [{ account: 'other-owner' }, { currentResume: { id: 'other-active' } }, { reviewCandidate: { id: 'other-draft' } }, { resumeRecord: null }, { file: {} }, { draftProfile: { full_name: 'Changed' } }, { phase: 'extracting' }, { confirmPending: true }, { deletePending: true }, { rebuildPending: true }]) assert.equal(resumeConfirmationIsCurrent(state, { ...state, ...change }, false), false)
  assert.equal(resumeConfirmationIsCurrent(state, state, true), false)
  assert.equal(resumeConfirmationIsCurrent(state, null, false), false)
})
