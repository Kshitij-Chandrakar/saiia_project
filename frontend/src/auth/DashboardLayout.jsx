import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { LayoutDashboard, LogOut, FileText } from 'lucide-react'
import { supabase } from './supabaseClient'
import { signOutWebsite } from './websiteSessionLoss'
import logo from '../assets/dashboard/logo.svg'
import sidebar from '../assets/dashboard/sidebar.svg'
import userIcon from '../assets/dashboard/user.svg'
import sessions from '../assets/dashboard/sessions.svg'
import resumes from '../assets/dashboard/resumes.svg'
import './dashboard.css'
import { Skeleton } from './WebsiteSkeleton'

export default function DashboardLayout({ user, title, children, onLogout, logoutPending = false, loading = false, description, subscriptionAdmin = false }) {
  const [collapsed, setCollapsed] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [tooltipDismissed, setTooltipDismissed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  useEffect(() => {
    if (window.electronAPI) return
    const previousTitle = document.title
    const favicon = document.querySelector('link[rel="icon"]')
    const parent = favicon?.parentNode, next = favicon?.nextSibling
    document.title = `${title} | Intervucopilot`
    // No approved website favicon exists; hide the development Vite icon here.
    if (favicon?.getAttribute('href') === '/vite.svg') favicon.remove()
    return () => {
      document.title = previousTitle
      if (favicon && !favicon.isConnected) parent.insertBefore(favicon, next?.parentNode === parent ? next : null)
    }
  }, [title])
  async function logout() {
    if (loading) return
    if (onLogout) return onLogout()
    if (pending || !supabase) return
    setPending(true)
    setError('')
    try {
      const result = await signOutWebsite(supabase)
      if (result.error) throw new Error()
      navigate('/auth/login', { replace: true, state: { authMessage: 'Signed out.' } })
    } catch { setError('Sign out failed. Please try again.'); setPending(false) }
  }
  return <div className={`website-dashboard ${collapsed ? 'website-dashboard--collapsed' : ''}`} aria-busy={loading || undefined}>
    {loading && <span className="wd-sr-only" role="status">Loading dashboard…</span>}
    <aside inert={loading || undefined} aria-hidden={loading || undefined} className={`wd-sidebar ${tooltipDismissed ? 'wd-tooltips-dismissed' : ''}`} aria-label="Workspace sidebar" onKeyDown={event => { if (event.key === 'Escape') setTooltipDismissed(true) }} onFocusCapture={() => setTooltipDismissed(false)} onMouseOver={() => setTooltipDismissed(false)}>
      <div className="wd-brand"><span className="wd-logo wd-tooltip-trigger" tabIndex={0} aria-label="Intervucopilot"><img src={logo} alt="" /><span className="wd-nav-tooltip" role="tooltip">Intervucopilot</span></span><strong>Intervucopilot</strong><button type="button" className="wd-tooltip-trigger" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-controls="wd-workspace-navigation" aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><img src={sidebar} alt="" /><span className="wd-nav-tooltip" role="tooltip">{collapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span></button></div>
      <nav id="wd-workspace-navigation" className="wd-navigation" aria-label="Workspace navigation">
        <p>WORKSPACE</p>
        <NavLink to="/auth/dashboard" end aria-label="Dashboard" className="wd-tooltip-trigger"><LayoutDashboard size={16} aria-hidden="true" /><span className="wd-nav-label">Dashboard</span><span className="wd-nav-tooltip" role="tooltip">Dashboard</span></NavLink>
        <NavLink to="/auth/sessions" aria-label="Call Sessions" className="wd-tooltip-trigger"><img src={sessions} alt="" /><span className="wd-nav-label">Call Sessions</span><span className="wd-nav-tooltip" role="tooltip">Call Sessions</span></NavLink>
        <NavLink to="/auth/resume" aria-label="Resumes" className="wd-tooltip-trigger"><img src={resumes} alt="" /><span className="wd-nav-label">Resumes</span><span className="wd-nav-tooltip" role="tooltip">Resumes</span></NavLink>
        {subscriptionAdmin && <NavLink to="/auth/admin/subscriptions" aria-label="Subscription drafts"><FileText size={16} aria-hidden="true" /><span className="wd-nav-label">Subscription drafts</span></NavLink>}
      </nav>
      {loading ? <div className="wd-account"><span className="wd-avatar"><Skeleton width="100%" height="100%" shape="avatar" /></span><div><Skeleton width="85%" height={20} /></div><Skeleton width={36} height={36} shape="icon" /></div> : <div className="wd-account"><span className="wd-avatar"><img src={userIcon} alt="" /></span><div className="wd-account-email"><strong tabIndex={0} title={user.email || 'Your account'}>{user.email || 'Your account'}</strong><span className="wd-email-full" role="tooltip">{user.email || 'Your account'}</span></div><button type="button" className="wd-tooltip-trigger" onClick={logout} disabled={pending || logoutPending} aria-label={pending || logoutPending ? 'Signing out...' : 'Logout'}><LogOut size={18} aria-hidden="true" /><span className="wd-nav-tooltip" role="tooltip">Logout</span></button></div>}
    </aside>
    <div className="wd-main"><header className="wd-header"><div><h1>{title}</h1><p>{loading ? <Skeleton width="min(360px,100%)" height={20} /> : description || (location.pathname === '/auth/sessions' ? 'Review your interview sessions and revisit the conversation.' : location.pathname === '/auth/resume' ? 'Manage the resume used for your interview answers.' : 'Your interview workspace, in one place.')}</p></div></header><main className="wd-content">{error && <p role="alert" className="wd-error">{error}</p>}{children}</main></div>
  </div>
}

export function ResumeEmptyState({ onUpload }) {
  return <section className="wd-resume-empty" aria-label="Resume upload"><span className="wd-empty-icon"><FileText size={26} aria-hidden="true" /></span><h2>No resumes yet</h2><p>Upload your resume to personalize your interview answers.</p><button type="button" className="wd-primary" onClick={onUpload}>Upload Resume</button><small>PDF, DOCX or TXT · Up to 5 MB</small></section>
}
