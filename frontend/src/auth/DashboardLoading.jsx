import DashboardLayout from './DashboardLayout'
import WebsiteSessionTable from './WebsiteSessionTable'
import WebsiteSkeleton, { Skeleton } from './WebsiteSkeleton'

// Presentation only: no authenticated user, data hooks or protected requests.
export default function DashboardLoading({ page = 'dashboard' }) {
  if (page === 'resume' || page === 'sessions') return <DashboardLayout title={page === 'resume' ? 'Resumes' : 'Call Sessions'} loading>
    <div className="wd-loading-content" aria-hidden="true" inert>
      {page === 'resume' ? <WebsiteSkeleton kind="resume" label="Loading resumes..." /> : <WebsiteSessionTable sessions={[]} loading />}
    </div>
  </DashboardLayout>
  return <DashboardLayout title="Dashboard" loading>
    <div className="wd-loading-content" aria-hidden="true" inert>
      <section className="wd-welcome"><p className="wd-eyebrow">WORKSPACE OVERVIEW</p><h2><Skeleton width="min(300px,85%)" height={44} /></h2><p>Review your recent conversations and keep your resume ready for your next interview.</p></section>
      <div className="wd-stats">{['Recent sessions','Resume status'].map(label=><section key={label}><span className="wd-stat-icon"><Skeleton width={18} height={18} shape="icon" /></span><p>{label}</p><strong><Skeleton width="40%" height={42} /></strong><small><Skeleton width="70%" height={18} /></small></section>)}</div>
      <section className="wd-banner"><div><h2><Skeleton width="80%" height={32} /></h2><p><Skeleton height={21} /></p><Skeleton width={153} height={41} shape="icon" /></div><span className="wd-banner-icon"><Skeleton width={40} height={40} shape="icon" /></span></section>
      <div className="wd-section-heading"><h2>Recent sessions</h2><Skeleton width={147} height={36} shape="icon" /></div>
      <WebsiteSessionTable sessions={[]} loading preview />
      <div className="wd-account-tools"><Skeleton width={104} height={18} /></div>
    </div>
  </DashboardLayout>
}
