import React from 'react'
import { createRoot } from 'react-dom/client'
import ResumeAccessSelection from '../../../src/auth/ResumeAccessSelection.jsx'
import '../../../src/auth/website-resumes.css'

export default function Harness() {
  const [user, setUser] = React.useState({ user_id: 'synthetic' })
  const [revision, setRevision] = React.useState(0)
  window.switchResumeAccount = () => setUser({ user_id: 'other' })
  return <ResumeAccessSelection user={user} backendUrl="" refreshKey={revision} onChanged={() => setRevision(x => x + 1)} />
}
createRoot(document.getElementById('root')).render(<Harness />)
