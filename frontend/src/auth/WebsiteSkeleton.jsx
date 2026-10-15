import './website-skeleton.css'

export function Skeleton({ width = '100%', height = 16, shape = 'line' }) {
  return <span className={`ws-shape ws-shape--${shape}`} style={{ width, height }} aria-hidden="true" />
}

export default function WebsiteSkeleton({ label, kind = 'detail' }) {
  return <div className={`website-skeleton ws-${kind}`} role="status" aria-label={label} aria-busy="true">
    <span className="ws-sr-only">{label}</span>
    <div aria-hidden="true">
      {kind === 'resume' ? <div className="wr-resume-card"><Skeleton width={48} height={48} shape="icon" /><div className="ws-fill"><Skeleton width="62%" height={24} /><Skeleton width="40%" height={18} /><Skeleton width="80%" height={16} /></div></div>
        : kind === 'account' ? <div className="auth-user-summary"><Skeleton width="65%" height={21} /><Skeleton width="30%" height={18} /></div>
          : <div className="ws-detail-content">{Array.from({ length:kind === 'notes' ? 3 : 2 }, (_, index) => <section key={index}><Skeleton width="28%" height={18} /><Skeleton width="94%" /><Skeleton width="82%" /><Skeleton width="66%" /></section>)}</div>}
    </div>
  </div>
}

export function SkeletonRows({ count = 3 }) {
  return Array.from({ length:count }, (_, index) => <tr key={index} aria-hidden="true" className="ws-table-row">
    <td><div className="wd-session-name"><Skeleton width={32} height={32} shape="icon" /><div className="ws-fill"><Skeleton width="75%" height={18} /><Skeleton width="55%" height={15} /></div></div></td>
    <td><Skeleton width={54} height={12} /></td><td><Skeleton width={86} height={14} /></td><td><Skeleton width={60} height={20} shape="pill" /></td><td><Skeleton width={120} height={36} shape="icon" /></td><td><Skeleton width={16} height={20} /></td>
  </tr>)
}
