import React from 'react'
import { WebsiteMounted } from '../../../src/auth/WebsiteRenderFailure.jsx'
import ReactDOM from 'react-dom/client'
import Choice from '../../../src/components/StartupSessionChoiceScreen.jsx'
import '../../../src/index.css'
import '../../../src/styles/glass.css'

// Isolated renderer fixture; real JWT/native transport is owned by its bridge.
window.saiia = {}
window.upgradeCalls = 0
window.electronAPI = {
  getSubscription: async () => {
    const response = await fetch('/api/account/subscription')
    const data = await response.json()
    return response.ok ? { ok: true, plan: data.plan, auto: data.usage.find(x => x.meter === 'auto.authorized_running') } : { ok: false }
  },
  openUpgrade: async () => { window.upgradeCalls++; return { ok: true } },
  closeStartupWindow: async () => ({ ok: true }),
}
export default function Harness() {
  const [email, setEmail] = React.useState('synthetic@example.invalid')
  window.switchAccount = () => {
    window.electronAPI.getSubscription = async () => ({ ok: false })
    setEmail('other@example.invalid')
  }
  return <Choice authenticatedEmail={email} />
}
ReactDOM.createRoot(document.getElementById('root')).render(<WebsiteMounted><Harness /></WebsiteMounted>)
