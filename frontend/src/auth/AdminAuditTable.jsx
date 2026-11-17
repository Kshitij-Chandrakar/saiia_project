const roles = { super_admin: 'Super admin', admin: 'Admin' };

export default function AdminAuditTable({ rows }) {
  return <>
    <p className="ac-audit-note">Performed by shows the current account email, which may differ from the email used at the time. The recorded account ID and role identify the actor when available.</p>
    <div className="ac-table ac-audit-table" role="region" aria-label="Audit history records" tabIndex={0}>
      <table><colgroup>{[18,29,17,13,11,12].map((width, index) => <col key={index} style={{ width: `${width}%` }} />)}</colgroup>
        <thead><tr>{['Time (UTC)','Performed by','Action','Role at action','Outcome','Reason'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{rows.map(row => {
          const date = row.timestamp ? new Date(row.timestamp) : null;
          return <tr key={row.event_id}>
            <td>{date && Number.isFinite(date.getTime()) ? <time dateTime={row.timestamp}>{new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'UTC' }).format(date)}</time> : 'Unavailable'}</td>
            <td><div className="ac-audit-actor"><strong>{row.actor_email || 'Email unavailable'}</strong><span><span className="ac-sr-only">Recorded account ID: </span>{row.actor_ref || 'Account ID unavailable'}</span></div></td>
            <td>{row.action ?? 'Unavailable'}</td><td>{roles[row.actor_role_at_action] || row.actor_role_at_action || 'Unavailable'}</td><td>{row.outcome ?? 'Unavailable'}</td><td>{row.reason_code ?? 'Not recorded'}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  </>;
}
