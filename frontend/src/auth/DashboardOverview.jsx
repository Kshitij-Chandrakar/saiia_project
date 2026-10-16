import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { fetchCurrentCloudResume, fetchCloudResumeList } from './authApi'
import { supabase } from './supabaseClient'
import sessionIcon from '../assets/dashboard/session-stat.svg'
import { Skeleton } from './WebsiteSkeleton'

export default function DashboardOverview({ user, backendUrl, sessions, loading, failed, children }) {
  const [resume, setResume] = useState(null)
  const [resumeLoading, setResumeLoading] = useState(true)
  const [resumeError, setResumeError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setResumeLoading(true)
      setResumeError(false)
      try {
        if (!supabase) throw new Error('Authentication is unavailable.')
        const { data } = await supabase.auth.getSession()
        if (controller.signal.aborted) return
        if (!data.session?.access_token || data.session.user?.id !== user.user_id) throw new Error()
        const result = await fetchCurrentCloudResume(data.session.access_token, { backendUrl, signal:controller.signal })
        if (!result.ready) {
          const items = await fetchCloudResumeList(data.session.access_token, { backendUrl, signal:controller.signal })
          result.resume = items.find(item => item.is_active) || items[0] || null
        }
        if (!controller.signal.aborted) setResume(result)
      } catch { if (!controller.signal.aborted) setResumeError(true) }
      finally { if (!controller.signal.aborted) setResumeLoading(false) }
    }
    load()
    return () => controller.abort()
  }, [backendUrl, user.user_id, attempt])
  const record = resume?.resume
  const initialResumeLoading = resumeLoading && !resume
  const initialSessionsLoading = loading && !sessions.length
  const state = initialResumeLoading ? 'loading' : resumeError ? 'unavailable' : resume?.ready ? 'ready' : !record ? 'missing' : record.readiness_reason || 'unknown'
  const presentation = {
    loading: ['Loading…', 'Checking your resume status.', 'Please wait while we load the current status.'],
    unavailable: ['Unavailable', 'Resume status is unavailable.', supabase ? 'Try again or visit Resumes to check its status.' : 'Authentication is unavailable. Check the website configuration.'],
    ready: ['Ready', 'Review your resume and recent conversations.', 'Manage your resume or revisit transcripts and AI notes from your sessions.'],
    missing: ['No resume', 'Add your resume to your workspace.', 'Upload and review your resume through the Resumes page.'],
    processing: ['Processing', 'Your resume is processing.', 'Visit Resumes to check extraction and indexing progress.'],
    needs_confirmation: ['Needs confirmation', 'Your resume needs review.', 'Review and confirm the extracted profile on the Resumes page.'],
    failed: ['Needs attention', 'Resume processing needs attention.', 'Visit Resumes to review the failure and available retry actions.'],
    not_indexed: ['Not ready', 'Your resume is not ready yet.', 'Visit Resumes to review its indexing status.'],
    no_chunks: ['Not ready', 'Your resume is not ready yet.', 'Visit Resumes to review its indexing status.'],
    unknown: ['Not ready', 'Review your resume status.', 'Visit Resumes to check the next available action.'],
  }[state] || ['Not ready', 'Review your resume status.', 'Visit Resumes to check the next available action.']
  return <>
    <section className="wd-welcome"><p className="wd-eyebrow">WORKSPACE OVERVIEW</p><h2>Welcome back!</h2><p>Review your recent conversations and keep your resume ready for your next interview.</p></section>
    <div className="wd-stats">
      <section aria-busy={loading} aria-label="Recent sessions summary"><span className="wd-stat-icon"><img src={sessionIcon} alt="" /></span><p>Recent sessions</p>
        <strong>{initialSessionsLoading ? <><span className="wd-sr-only">Loading…</span><Skeleton width="30%" height={42} /></> : failed ? 'Unavailable' : sessions.length}</strong>
        <small>{initialSessionsLoading ? <><span className="wd-sr-only" role="status">Loading your recent sessions.</span><Skeleton width="60%" height={18} /></> : failed ? 'Session history could not be loaded.' : `Showing the latest ${sessions.length} ${sessions.length === 1 ? 'session' : 'sessions'}.`}</small>
      </section>
      <section aria-busy={resumeLoading} aria-label="Resume status summary"><span className="wd-stat-icon"><FileText size={18} aria-hidden="true" /></span><p>{state === 'ready' ? 'Active resume' : 'Resume status'}</p>
        <strong>{initialResumeLoading ? <><span className="wd-sr-only">{presentation[0]}</span><Skeleton width="40%" height={42} /></> : presentation[0]}</strong>
        <small>{initialResumeLoading ? <><span className="wd-sr-only" role="status">Loading resume status.</span><Skeleton width="70%" height={18} /></> : (!resumeError && record?.original_filename) || 'Manage your resume to review its status.'}</small>
      </section>
    </div>
    <section className="wd-banner" aria-label="Resume overview" aria-busy={resumeLoading}><div><h2>{initialResumeLoading ? <><span className="wd-sr-only">{presentation[1]}</span><Skeleton width="80%" height={32} /></> : presentation[1]}</h2><p>{initialResumeLoading ? <Skeleton width="95%" height={21} /> : presentation[2]}</p><Link className="wd-primary" to="/auth/resume">{state === 'missing' ? 'Upload Resume' : 'Manage Resumes'}</Link>{resumeError && supabase && <button type="button" onClick={() => setAttempt(value => value + 1)}>Retry resume status</button>}</div><span className="wd-banner-icon"><FileText size={40} aria-hidden="true" /></span></section>
    <div className="wd-section-heading"><h2>Recent sessions</h2><Link to="/auth/sessions">View All Sessions →</Link></div>{children}
  </>
}
