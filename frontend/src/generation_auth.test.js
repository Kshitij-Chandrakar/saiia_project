import assert from 'node:assert/strict'
import test from 'node:test'
import { prepareGenerationRequest } from './generation_auth.js'

const available = { getCloudStartupContext: async () => ({ auth: { status: 'connected' }, cloud: { available: true } }) }
const unavailable = { getCloudStartupContext: async () => ({ auth: { status: 'connected' }, cloud: { available: false } }) }

test('unavailable incidental startup session does not block local generation or its REST fallback', async () => {
  const body = { question: 'What is deep learning?', session_id: 'startup-session' }
  const result = await prepareGenerationRequest(body, { activeSessionId: 'startup-session' }, unavailable)
  assert.deepEqual(result, { requestBody: { question: body.question }, authRequired: false })
  assert.equal(body.session_id, 'startup-session')
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
