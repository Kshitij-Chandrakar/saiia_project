// Keep incidental cloud session tracking out of local requests when cloud is unavailable.
export async function prepareGenerationRequest(body, startupConfig, api) {
  const selectedResumeId = String(body.selected_resume_id || startupConfig?.selectedResumeId || '').trim()
  const jobContextId = String(body.job_context_id || startupConfig?.jobContextId || '').trim()
  const startupSessionId = String(startupConfig?.activeSessionId || '').trim()
  const requestBody = { ...body }
  if (selectedResumeId) requestBody.selected_resume_id = selectedResumeId
  if (jobContextId) requestBody.job_context_id = jobContextId
  let cloudAvailable = false
  if (typeof api?.getCloudStartupContext === 'function') {
    try {
      const state = await api.getCloudStartupContext()
      cloudAvailable = state?.auth?.status === 'connected' && state?.cloud?.available === true
    } catch { /* Local generation remains available without cloud. */ }
  }
  if (startupSessionId && !selectedResumeId && !jobContextId && !cloudAvailable) {
    if (requestBody.session_id === startupSessionId) delete requestBody.session_id
  } else if (startupSessionId) {
    requestBody.session_id ||= startupSessionId
  }
  const authRequired = Boolean(requestBody.selected_resume_id || requestBody.job_context_id || requestBody.session_id)
  if (authRequired && !cloudAvailable) {
    throw new Error('Cloud generation requires a valid connection. Sign in again or clear cloud selections to generate locally.')
  }
  return { requestBody, authRequired }
}
