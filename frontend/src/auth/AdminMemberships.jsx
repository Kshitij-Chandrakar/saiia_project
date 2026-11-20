import { useEffect, useRef, useState } from 'react';

const roles = { admin: 'Admin', super_admin: 'Super admin' };
const statuses = { active: 'Active', suspended: 'Suspended', revoked: 'Revoked' };

export function MembershipAccountPicker({ find, selected, onSelect, disabled }) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  useEffect(() => () => { ++sequence.current; }, []);
  async function search() {
    const current = ++sequence.current;
    setLoading(true); setResult(null); onSelect(null);
    try {
      const data = await find(query.trim());
      if (current === sequence.current) setResult({ items: data.items || [] });
    } catch {
      if (current === sequence.current) setResult({ error: true });
    } finally { if (current === sequence.current) setLoading(false); }
  }
  return <div className="am-account-picker">
    <label>Find an existing user<span className="am-hint">Enter their exact email or Account ID. This does not create an account.</span><div className="am-search"><input aria-label="User email or Account ID" type="search" maxLength={320} value={query} disabled={disabled || loading} onChange={event => { ++sequence.current; setQuery(event.target.value); setResult(null); onSelect(null); }} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); if (query.trim() && !loading && !disabled) void search(); } }} /><button type="button" disabled={disabled || loading || !query.trim()} onClick={search}>{loading ? 'Finding…' : 'Find user'}</button></div></label>
    {result?.error && <p role="alert">Could not find accounts right now. Try again; no access has changed.</p>}
    {result && !result.error && !result.items.length && <p role="status">No matching account. Check the email or Account ID, or ask the person to register first.</p>}
    {result?.items?.map(user => <button className="am-user-result" type="button" disabled={disabled || user.deletion_restricted} key={user.user_id} aria-pressed={selected === user.user_id} onClick={() => onSelect(user)}><strong>{user.email || 'Email unavailable'}</strong><span>Account ID: {user.user_id}</span><span>{user.deletion_restricted ? 'Deletion restricted — access cannot be granted' : selected === user.user_id ? 'Selected' : 'Select this account'}</span></button>)}
  </div>;
}

export default function AdminMemberships({ rows, onAdd, onChange, children }) {
  return <div className="am-workspace">
    <section className="am-members" aria-labelledby="am-members-title">
      <div className="am-heading"><div><h2 id="am-members-title">People with admin access</h2><p>Add an existing user or change a team member’s access. Every change is reviewed before it takes effect.</p></div><button type="button" className="am-primary" onClick={onAdd}>Add administrator</button></div>
      <div className="am-role-guide"><p><strong>Admin</strong><span>Customer support, dashboard metrics and campaigns.</span></p><p><strong>Super admin</strong><span>Everything Admin can do, plus staff access, commercial settings and audit history.</span></p></div>
      {!rows.length ? <p>No administrators are available in this view.</p> : <div className="ac-table am-table" role="region" aria-label="Administrators records" tabIndex={0}><table><thead><tr><th scope="col">Account</th><th scope="col">Access level</th><th scope="col">Status</th><th scope="col">Manage</th></tr></thead><tbody>{rows.map(row => <tr key={row.subject_id}><td><div className="ac-audit-actor"><strong>{row.email || 'Account ID'}</strong><span>{row.subject_id}</span></div></td><td>{roles[row.role] || 'Unavailable'}</td><td><span className={'am-status am-status-' + row.status}>{statuses[row.status] || 'Unavailable'}</span></td><td><button type="button" onClick={() => onChange(row)} aria-label={'Change access for ' + (row.email || row.subject_id)}>Change access</button><details className="am-record-details"><summary>Record details</summary><span>Revision: {row.revision}</span></details></td></tr>)}</tbody></table></div>}
      <p className="am-safeguard">The last active Super admin is protected from staff removal, suspension or demotion. Your own account-deletion rights remain separate.</p>
    </section>
    <details className="am-secondary"><summary>Appoint a successor<span>For handing over responsibility</span></summary>{children}</details>
    <details className="am-secondary"><summary>Recovery and safeguards</summary><p>Emergency recovery is unavailable until independent attestors and the operator procedure are configured and tested.</p><p>No recovery is performed from this page. Neither role can view private customer content or bypass account-deletion safeguards.</p></details>
  </div>;
}
