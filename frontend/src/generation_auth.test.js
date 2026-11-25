import assert from 'node:assert/strict'
import test from 'node:test'
import { prepareGenerationRequest } from './generation_auth.js'

const available = { getCloudStartupContext: async () => ({ auth: { status: 'connected' }, cloud: { available: true } }) }
const unavailable = { getCloudStartupContext: async () => ({ auth: { status: 'connected' }, cloud: { available: false } }) }

test('generation refreshes unavailable cached cloud state once and preserves session context', async () => {
  let refreshes = 0
  const api = { ...unavailable, refreshCloudStartupContext: async () => {
    refreshes += 1
    return available.getCloudStartupContext()
  } }
  let diagnostics
  const result = await prepareGenerationRequest({ question: 'Question' },
    { activeSessionId: 'session', selectedResumeId: 'resume' }, api, value => { diagnostics = value })
  assert.equal(refreshes, 1)
  assert.equal(result.requestBody.session_id, 'session')
  assert.equal(result.requestBody.selected_resume_id, 'resume')
  assert.equal(result.authRequired, true)
  assert.equal(diagnostics.generationRequestBlocked, false)
})

for (const outcome of ['unavailable', 'expired', 'throws']) test(`cloud refresh ${outcome} keeps generation blocked`, async () => {
  let refreshes = 0
  const body = { question: 'Question', session_id: 'session', selected_resume_id: 'resume' }
  const api = { ...unavailable, refreshCloudStartupContext: async () => {
    refreshes += 1
    if (outcome === 'throws') throw new Error('Unavailable')
    return { auth: { status: outcome === 'expired' ? 'token-expired' : 'connected' }, cloud: { available: outcome === 'expired' } }
  } }
  await assert.rejects(prepareGenerationRequest(body, {}, api), /Sign in again/)
  assert.equal(refreshes, 1)
  assert.equal(body.session_id, 'session')
  assert.equal(body.selected_resume_id, 'resume')
})

test('healthy and explicitly local generation skip the cloud refresh', async () => {
  let refreshes = 0
  const refreshCloudStartupContext = async () => { refreshes += 1 }
  await prepareGenerationRequest({}, { activeSessionId: 'session' }, { ...available, refreshCloudStartupContext })
  await prepareGenerationRequest({}, { activeSessionId: 'session' }, { ...unavailable, refreshCloudStartupContext }, undefined, { localWithoutSaving: true })
  await prepareGenerationRequest({}, {}, { ...unavailable, refreshCloudStartupContext })
  assert.equal(refreshes, 0)
})

test('unavailable active startup session rejects instead of detaching session persistence', async () => {
  const body = { question: 'What is deep learning?', session_id: 'startup-session' }
  await assert.rejects(prepareGenerationRequest(body, { activeSessionId: 'startup-session' }, unavailable), /Sign in again/)
  assert.equal(body.session_id, 'startup-session')
  await assert.rejects(prepareGenerationRequest({ question: 'Q' }, { activeSessionId: 'startup-session' }, unavailable), /active session/)
})

test('healthy session-only generation requires the authenticated desktop transport', async () => {
  const result = await prepareGenerationRequest({ question: 'Question' }, { activeSessionId: 'session' }, available)
  assert.equal(result.authRequired, true)
  assert.equal(result.requestBody.session_id, 'session')
})
for (const field of ['selected_resume_id', 'job_context_id', 'session_id']) {
  test(`unavailable explicit ${field} fails without silently removing cloud context`, async () => {
    await assert.rejects(prepareGenerationRequest({ [field]: 'selected' }, {}, unavailable), /Sign in again/)
  })
}
test('local generation needs neither cloud bridge nor bearer token', async () => {
  assert.deepEqual(await prepareGenerationRequest({ question: 'Question' }, {}, undefined), {
    requestBody: { question: 'Question' }, authRequired: false,
  })
})

for (const api of [undefined, { getCloudStartupContext: async () => { throw new Error('unavailable') } },
  { getCloudStartupContext: async () => ({ auth: { status: 'expired' }, cloud: { available: true } }) }]) {
  test('missing, failed or expired cloud auth rejects active sessions', async () => {
    await assert.rejects(prepareGenerationRequest({}, { activeSessionId: 'session' }, api), /Sign in again/)
  })
}
for (const field of ['selectedResumeId', 'jobContextId']) {
  test(`startup ${field} requires auth`, async () => {
    await assert.rejects(prepareGenerationRequest({}, { [field]: 'selected' }, unavailable), /Sign in again/)
    assert.equal((await prepareGenerationRequest({}, { [field]: 'selected' }, available)).authRequired, true)
  })
}
test('unavailable cloud still permits genuinely local generation', async () => {
  assert.equal((await prepareGenerationRequest({ question: 'Q' }, {}, unavailable)).authRequired, false)
})

const ended = { getCloudStartupContext: async () => ({ auth: { status: 'expired', activeInterviewSessionId: null, endedInterviewSessionIds: ['ended-session'] }, cloud: { available: false } }) }
test('confirmed ended session is cleared and permits local generation without cloud', async () => {
  let diagnostics
  const body = { question: 'Q', session_id: 'ended-session' }
  const result = await prepareGenerationRequest(body, { activeSessionId: 'ended-session' }, ended, (value) => { diagnostics = value })
  assert.equal(result.authRequired, false)
  assert.equal(result.requestBody.session_id, undefined)
  assert.equal(diagnostics.activeSessionEnded, true)
  assert.equal(diagnostics.startupSessionEnded, true)
  assert.equal(diagnostics.generationRequestBlocked, false)
  assert.equal(body.session_id, 'ended-session')
})
test('ended session does not bypass selected cloud context or a different active startup session', async () => {
  await assert.rejects(prepareGenerationRequest({ session_id: 'ended-session', selected_resume_id: 'resume' }, {}, ended), /Sign in again/)
  await assert.rejects(prepareGenerationRequest({ session_id: 'ended-session' }, { activeSessionId: 'active-session' }, ended), /Sign in again/)
})
test('missing active ID alone never proves a session ended', async () => {
  const state = { getCloudStartupContext: async () => ({ auth: { status: 'expired', activeInterviewSessionId: null }, cloud: { available: false } }) }
  await assert.rejects(prepareGenerationRequest({}, { activeSessionId: 'unknown-session' }, state), /Sign in again/)
})


test('explicit local-without-saving omits all cloud resource IDs only for this request', async () => {
  const config = { activeSessionId: 'active-1', selectedResumeId: 'resume-1', jobContextId: 'job-1' }
  const body = { question: 'Explain CI/CD', session_id: 'active-1', selected_resume_id: 'resume-1', job_context_id: 'job-1' }
  let diagnostics
  const result = await prepareGenerationRequest(body, config, { getCloudStartupContext: async () => ({ auth: { status: 'expired' }, cloud: { available: false } }) }, (value) => { diagnostics = value }, { localWithoutSaving: true })
  assert.deepEqual(result.requestBody, { question: 'Explain CI/CD' })
  assert.equal(result.authRequired, false)
  assert.equal(config.activeSessionId, 'active-1')
  assert.equal(body.session_id, 'active-1')
  assert.equal(diagnostics.localWithoutSaving, true)
  assert.equal(diagnostics.generationRequestBlocked, false)
  assert.equal(diagnostics.generateStreamRequestSent, false)
  assert.equal(diagnostics.generateFallbackRequestSent, false)
})
