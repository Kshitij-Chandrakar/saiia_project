import React from 'react'
import { createRoot } from 'react-dom/client'
import Setup from '../../src/components/StartupSessionSetupScreen.jsx'
import '../../src/styles/glass.css'
const root = createRoot(document.getElementById('root'))
window.created = []
window.started = []
window.catalogCalls = 0
window.saiia = {
  getCloudStartupContext: async () => ({}),
  listCloudResumes: async () => ({ items: window.fixtureResumes || [] }),
  listAnswerModels: async () => {
    window.catalogCalls++
    const result=structuredClone(window.fixtureCatalog)
    if (window.catalogDelay) await new Promise(resolve => { window.releaseCatalog = resolve })
    return result
  },
  createInterviewSession: async (body,options) => {
    window.created.push({ body, options })
    if (window.creationDelay) await new Promise(resolve => { window.releaseCreation = resolve })
    return window.creationResult || { session: { id: 'test-session', status: 'active', selected_model_key: body.selected_model_key || null,
      model_selection_kind: body.selected_model_key ? 'model_bound' : 'legacy' } }
  },
  endInterviewSession: async () => ({}),
}
window.electronAPI = { completeStartup: async () => ({ ok: true }) }
let key = 0
window.renderSetup = () => root.render(<Setup key={++key} initialConfig={{ company: 'Example', selectedModelKey: 'do-not-remember' }}
  authenticatedEmail="test@example.com" onBack={() => {}} onStartSession={value => window.started.push(value)} />)
window.renderSetup()
