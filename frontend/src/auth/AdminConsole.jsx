import AdminOverview from './AdminOverview';
import AdminCustomerMetadata from './AdminCustomerMetadata';
import AdminAuditTable from './AdminAuditTable';
import AdminCampaigns from './AdminCampaigns';
import AdminMemberships, { MembershipAccountPicker } from './AdminMemberships';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { supabase } from './supabaseClient';
import WebsiteNotFound from '../WebsiteNotFound';
import AdminShell from './AdminShell';
import { containDialogFocus } from './adminFocus';
import { CalendarDays, Globe2, RefreshCw, ShieldCheck, ShieldAlert, X } from 'lucide-react';
import './admin-console.css';

const labels = { overview: 'Overview', campaigns: 'Campaigns', users: 'Customers', memberships: 'Administrators', coupons: 'Coupon drafts', audit: 'Audit history' };
const fields = {
  campaigns: ['name', 'subject', 'state', 'revision'],
  users: ['email', 'registered_at', 'email_verified', 'deletion_restricted'],
  memberships: ['subject_id', 'role', 'status', 'revision'],
  audit: ['timestamp', 'action', 'actor_role_at_action', 'outcome', 'reason_code'],
  coupons: ['code', 'revision', 'redemption_available'],
};
const fieldLabels = { name: 'Name', subject: 'Subject', state: 'State', email: 'Email', registered_at: 'Registered at', email_verified: 'Email verified', deletion_restricted: 'Deletion restricted', subject_id: 'Account ID', role: 'Role', status: 'Status', revision: 'Revision', timestamp: 'Time', action: 'Action', actor_role_at_action: 'Role at action', outcome: 'Outcome', reason_code: 'Reason', user_id: 'Account ID', data_as_of: 'Data as of', code: 'Coupon code', redemption_available: 'Redemption available' };
function display(value) {
  if (value === null || value === undefined) return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

async function fetchAdmin(base, token, path, signal, document) {
  const response = await fetch(base.replace(/\/$/, '') + '/api/admin/' + path, {
    method: document ? 'POST' : 'GET', signal, cache: 'no-store', credentials: 'omit', redirect: 'error',
    headers: { Authorization: `Bearer ${token}`, ...(document ? { 'Content-Type': 'application/json' } : {}) },
    ...(document ? { body: JSON.stringify(document) } : {}),
  });
  if (!response.ok) {
    const error = new Error('Administration request unavailable');
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export default function AdminConsole({ backendUrl, client = supabase }) {
  const [params, setParams] = useSearchParams();
  const section = params.get('view') || 'users';
  const [state, setState] = useState({ phase: 'loading' });
  const [search, setSearch] = useState('');
  const [pager, setPager] = useState({ section, query: '', after: '' });
  const query = pager.section === section ? pager.query : '';
  const after = pager.section === section ? pager.after : '';
  const setQuery = query => setPager(previous => ({ section, after: previous.section === section ? previous.after : '', query }));
  const setAfter = after => setPager(previous => ({ section, query: previous.section === section ? previous.query : '', after }));
  const [reload, setReload] = useState(0);
  const [metricDays,setMetricDays] = useState(30);
  const [metricZone,setMetricZone] = useState('Asia/Calcutta');
  const [detail, setDetail] = useState(null);
  const inspection = useRef(0);
  const [draft, setDraft] = useState(null);
  const [review, setReview] = useState(null);
  const [memberAccount, setMemberAccount] = useState(null);
  const membershipTrigger = useRef(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [code, setCode] = useState('');
  const [coupon, setCoupon] = useState(null);
  const [accessDraft, setAccessDraft] = useState(null);
  const [accessReview, setAccessReview] = useState(null);
  const [successorTarget, setSuccessorTarget] = useState('');
  const [transfer, setTransfer] = useState(null);
  const [lastCommand, setLastCommand] = useState(null);
  const [supportKind, setSupportKind] = useState('access');
  const accessDialog = useRef(null);
  const dialog = useRef(null);
  const ticket = useRef(0);
  const session = useRef(null);
  const active = useRef(null);
  const lastIdentity = useRef(null), accessReady = useRef(false), revalidateSession = useRef(null);
  const submitting = useRef(false);
  const verificationDialog = useRef(null), verificationTrigger = useRef(null);
  const [verificationUntil, setVerificationUntil] = useState(0);
  const [verified, setVerified] = useState(false);
  useEffect(() => {
    const left = verificationUntil - Date.now();
    setVerified(left > 0);
    if (left > 0) { const timer = setTimeout(() => setVerified(false), left); return () => clearTimeout(timer); }
  }, [verificationUntil]);
  function surfaceVerification() { verificationDialog.current?.showModal(); verificationDialog.current?.querySelector('input')?.focus(); }
  const request = useCallback(async (...args) => {
    try { return await fetchAdmin(...args); }
    catch (failure) { if (failure.status === 403) { verificationDialog.current?.showModal(); verificationDialog.current?.querySelector('input')?.focus(); } throw failure; }
  }, []);
  function navigateSection(key) {
    setAfter(''); setQuery(''); setParams(previous => { const next = new URLSearchParams(previous); next.set('view', key); return next; });
  }


  useEffect(() => {
    let alive = true;
    const generation = ticket;
    let authorityVersion = 0, authorityController;
    function updateVerification(next) {
      // Presentation only. Backend authorization and freshness checks remain authoritative.
      try {
        const encoded = next?.access_token?.split('.')[1];
        const claims = encoded ? JSON.parse(atob(encoded.replaceAll('-', '+').replaceAll('_', '/'))) : {};
        const totp = Math.max(0, ...(claims.amr || []).filter(item => item.method === 'totp').map(item => Number(item.timestamp)));
        setVerificationUntil(claims.aal === 'aal2' && claims.c15_auth_method === 'totp' && totp * 1000 <= Date.now() ? Math.min(Number(claims.exp) * 1000, (totp + 300) * 1000) : 0);
      } catch { setVerificationUntil(0); }
    }
    async function revalidate(next) {
      if (!next?.user?.id || next.user.id !== session.current?.user?.id || !lastIdentity.current) return load(next);
      const version = ++authorityVersion;
      authorityController?.abort();
      const controller = new AbortController(); authorityController = controller;
      session.current = next; accessReady.current = false; updateVerification(next);
      setState(previous => ({ ...previous, revalidating: true }));
      try {
        const identity = await request(backendUrl, next.access_token, 'me', controller.signal);
        if (!alive || version !== authorityVersion) return;
        if (!labels[section] || (!['users','campaigns','overview'].includes(section) && identity.role !== 'super_admin')) return load(null);
        lastIdentity.current = identity; accessReady.current = true;
        setState(previous => ({ ...previous, phase: 'ready', identity, user: next.user, revalidating: false }));
      } catch (failure) {
        if (!alive || version !== authorityVersion || controller.signal.aborted) return;
        if ([401,403,404].includes(failure.status)) return load(null);
        setState(previous => ({ ...previous, phase: 'suspended', revalidating: false }));
      }
    }
    revalidateSession.current = revalidate;
    async function load(next) {
      const current = ++ticket.current;
      const changedAccount = Boolean(session.current?.user?.id && session.current.user.id !== next?.user?.id);
      const loadQuery = changedAccount ? '' : query, loadAfter = changedAccount ? '' : after;
      ++authorityVersion; authorityController?.abort();
      lastIdentity.current = null; accessReady.current = false;
      active.current?.abort();
      const controller = new AbortController(); active.current = controller;
      session.current = next;
      if (changedAccount) { setSearch(''); setPager(previous => ({ ...previous, query: '', after: '' })); }
      updateVerification(next);
      setState({ phase: 'loading' }); setDetail(null); setReview(null); setDraft(null); setMemberAccount(null); setCoupon(null); setAccessDraft(null); setAccessReview(null); setLastCommand(null); setCode(''); setTransfer(null); setError('');
      if (!next?.access_token || !client) { setState({ phase: 'denied' }); return; }
      try {
        const identity = await request(backendUrl, next.access_token, 'me', controller.signal);
        if (!labels[section] || (!['users','campaigns','overview'].includes(section) && identity.role !== 'super_admin')) {
          if (alive && current === ticket.current) setState({ phase: 'denied' });
          return;
        }
        const filters = new URLSearchParams();
        if (loadAfter) filters.set('after', loadAfter);
        const data = section === 'overview' ? await request(backendUrl,next.access_token,'metrics',controller.signal,{start:new Date(Date.now()-metricDays*86400000).toISOString(),end:new Date().toISOString(),timezone:metricZone}) : loadQuery && section === 'users'
          ? await request(backendUrl, next.access_token, 'users/search', controller.signal, { search: loadQuery, ...(loadAfter ? { after: loadAfter } : {}) })
          : await request(backendUrl, next.access_token, section + (filters.size ? '?' + filters : ''), controller.signal);
        if (alive && current === ticket.current) { lastIdentity.current = identity; accessReady.current = true; setState({ phase: 'ready', identity, data, user: next.user, section }); }
      } catch (failure) {
        if (alive && current === ticket.current && !controller.signal.aborted)
          setState({ phase: [401, 404].includes(failure.status) ? 'denied' : 'unavailable' });
      }
    }
    if (!client) { setState({ phase: 'unavailable' }); return; }
    const subscription = client.auth.onAuthStateChange((event, next) => {
      if (event !== 'INITIAL_SESSION') void revalidate(next);
    }).data.subscription;
    const initial = ticket.current;
    client.auth.getSession().then(({ data, error: failure }) => {
      if (alive && initial === ticket.current) void load(failure ? null : data.session);
    });
    return () => { alive = false; ++generation.current; ++authorityVersion; accessReady.current = false; authorityController?.abort(); active.current?.abort(); revalidateSession.current = null; subscription.unsubscribe(); };
  }, [backendUrl, client, section, after, query, reload, metricDays, metricZone, request]);

  const authorized = state.phase === 'ready' && !state.revalidating;
  useEffect(() => {
    if (draft && authorized) dialog.current?.showModal();
    else dialog.current?.close();
  }, [draft, authorized]);

  useEffect(() => {
    if (accessDraft && authorized) accessDialog.current?.showModal();
    else accessDialog.current?.close();
  }, [accessDraft, authorized]);

  async function changeAccess(event) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true; setPending(true); setError('');
    const current = ticket.current;
    try {
      const result = await request(backendUrl, session.current.access_token, (supportKind === 'privacy' ? 'privacy-retries/' : supportKind === 'cancel' ? 'cancellations/' : 'access/') + (accessReview ? 'confirm' : 'review'), active.current.signal,
        accessReview ? { review_id: accessReview.review_id, confirm: true } : accessDraft);
      if (current !== ticket.current) return;
      if (accessReview) { setAccessDraft(null); setAccessReview(null); if (supportKind === 'cancel') setLastCommand(result); else setReload(value => value + 1); }
      else setAccessReview(result);
    } catch (failure) {
      if (current === ticket.current) setError(failure.status === 403 ? 'Verify your authenticator before changing customer access.' : 'Outcome not confirmed. Retry this same operation to recover its result.');
    } finally { submitting.current = false; setPending(false); }
  }

  async function inspect(id) {
    const selected = ++inspection.current;
    const current = ticket.current;
    setDetail(null); setLastCommand(null);
    try {
      const [data, privacy, subscription, allowances] = await Promise.all([
        request(backendUrl, session.current.access_token, 'users/' + id, active.current.signal),
        request(backendUrl, session.current.access_token, 'users/' + id + '/privacy', active.current.signal),
        request(backendUrl, session.current.access_token, 'users/' + id + '/subscription', active.current.signal),
        request(backendUrl, session.current.access_token, 'users/' + id + '/allowances', active.current.signal),
      ]);
      if (current === ticket.current && selected === inspection.current) setDetail({ ...data, privacy, subscription, allowances });
    } catch { if (current === ticket.current && selected === inspection.current) setError('Account detail is unavailable. Refresh to check your current access.'); }
  }

  async function verifyAuthenticator(event) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true; setPending(true); setError('');
    try {
      const { data, error: factorError } = await client.auth.mfa.listFactors();
      const factor = data?.totp?.find(item => item.status === 'verified');
      if (factorError || !factor) throw new Error();
      const result = await client.auth.mfa.challengeAndVerify({ factorId: factor.id, code });
      if (result.error) throw new Error();
      setCode(''); verificationDialog.current?.close();
      // Recheck authority without discarding operation identities.
      const next = await client.auth.getSession();
      await revalidateSession.current?.(next.error ? null : next.data.session);
    } catch { setError('Authenticator verification failed or no verified authenticator is configured.'); }
    finally { submitting.current = false; setPending(false); }
  }

  function openMembership(row, trigger) {
    membershipTrigger.current = trigger;
    setError(''); setReview(null);
    setMemberAccount(row ? { user_id: row.subject_id, email: row.email } : null);
    setDraft({ target: row?.subject_id || '', role: row?.role || 'admin', status: row?.status || 'active', reason: 'membership', operation_id: crypto.randomUUID() });
  }

  async function findMember(search) {
    const current = ticket.current;
    const result = await request(backendUrl, session.current.access_token, 'users/search', active.current.signal, { search });
    if (current !== ticket.current) throw new Error('Account changed');
    return result;
  }

  async function membership(event) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true; setPending(true); setError('');
    const current = ticket.current;
    try {
      const result = await request(backendUrl, session.current.access_token, 'memberships/' + (review ? 'confirm' : 'review'), active.current.signal,
        review ? { review_id: review.review_id, confirm: true } : draft);
      if (current !== ticket.current) return;
      if (review) { setDraft(null); setReload(value => value + 1); }
      else setReview(result);
    } catch (failure) {
      if (current === ticket.current) setError(failure.status === 403
        ? 'A recent verified authenticator is required before changing membership.'
        : 'The outcome is not confirmed. Retry this same operation to recover its result; do not create a second request.');
    } finally { submitting.current = false; setPending(false); }
  }

  async function saveCoupon(event) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true; setPending(true); setError('');
    const current = ticket.current;
    try {
      await request(backendUrl, session.current.access_token, 'coupons/' + coupon.id, active.current.signal, {
        code: coupon.code, expected: coupon.expected, operation_id: coupon.operation_id, source_discount_id: coupon.source_discount_id || null,
      });
      if (current === ticket.current) { setCoupon(null); setReload(value => value + 1); }
    } catch (failure) {
      if (current === ticket.current) setError(failure.status === 403 ? 'Verify your authenticator before saving commercial configuration.' : 'Save is not confirmed. Retry this same draft operation to recover its outcome.');
    } finally { submitting.current = false; setPending(false); }
  }

  if (state.phase === 'denied') return <WebsiteNotFound />;
  const identity = authorized ? state.identity : null;
  const busy = state.phase === 'loading';
  return <AdminShell identity={identity} user={state.user} section={section} navigate={navigateSection} title={labels[section] || 'Administration'} subtitle={section === 'overview' ? 'Understand your users and AI usage.' : section === 'memberships' ? 'Choose who can help manage Intervucopilot, and what they can do.' : 'Manage your approved administration workspace.'} controls={<>
{section === 'overview' && <><label className="ac-filter"><span className="ac-sr-only">Rolling window</span><CalendarDays size={17} aria-hidden="true" /><select aria-label="Rolling window" value={metricDays} onChange={event => setMetricDays(Number(event.target.value))}>{[7,30,90].map(days => <option key={days} value={days}>Last {days} days</option>)}</select></label><label className="ac-filter"><span className="ac-sr-only">Chart timezone</span><Globe2 size={17} aria-hidden="true" /><select aria-label="Chart timezone" value={metricZone} onChange={event => setMetricZone(event.target.value)}><option value="Asia/Calcutta">Asia/Kolkata</option><option>UTC</option></select></label><button className="ac-icon-button" aria-label={busy ? 'Refreshing metrics' : 'Refresh metrics'} title="Refresh metrics" disabled={busy} onClick={() => setReload(value => value + 1)}><RefreshCw size={19} aria-hidden="true" /></button></>}
        {identity && <button className="ac-verification-toggle" ref={verificationTrigger} onClick={surfaceVerification}>{verified ? <ShieldCheck size={19} aria-hidden="true" /> : <ShieldAlert size={19} aria-hidden="true" />}{verified ? 'Verified' : 'Verify access'}</button>}
      </>}>
    <main id="admin-content" tabIndex={-1}>
      {section === 'overview' && (state.phase === 'loading' || state.phase === 'unavailable') && <AdminOverview status={state.phase} />}
      {section !== 'overview' && busy && <p role="status" aria-busy="true">Checking live administration access...</p>}
      {['unavailable','suspended'].includes(state.phase) && <section className="ac-error-state">{section !== 'overview' && <h2>Administration unavailable</h2>}<p>No account data is shown while authority or storage cannot be verified.</p><button onClick={() => state.phase === 'suspended' ? revalidateSession.current?.(session.current) : setReload(value => value + 1)}>Retry access check</button></section>}
      {state.revalidating && <p role="status">Checking current administration access...</p>}
      {['ready','suspended'].includes(state.phase) && state.section === section && <div hidden={!authorized} inert={!authorized}>
        {section !== 'overview' && <p>Metadata only. Private customer content is unavailable to both administration roles.</p>}
        {section === 'campaigns' && <AdminCampaigns suspended={!authorized} key={state.identity.subject_id} items={state.data.items} perform={(action, document) => { if (!accessReady.current) return Promise.reject(new Error('Access unverified')); return request(backendUrl, session.current.access_token, 'campaigns/' + action, active.current.signal, document); }} />}
        {section === 'users' && <form onSubmit={event => { event.preventDefault(); setAfter(''); setQuery(search.trim()); }}><label>Exact customer email or account ID<input value={search} maxLength={320} onChange={event => setSearch(event.target.value)} /></label><button>Search</button></form>}
        {section === 'memberships' && <AdminMemberships rows={state.data.items} onAdd={event => openMembership(null, event.currentTarget)} onChange={row => openMembership(row, document.activeElement)}><section aria-label="Advisory successor transfer"><h3>Hand over responsibility safely</h3><p>1. Choose an existing account. 2. Send the offer. 3. Ask the successor to accept and verify their access.</p><p>Your access is not automatically removed. An unfinished transfer does not block your own account deletion.</p><form onSubmit={async event => { event.preventDefault(); if (submitting.current) return; submitting.current = true; setPending(true); const current = ticket.current; try { const result = await request(backendUrl, session.current.access_token, 'successor/offer', active.current.signal, { target: successorTarget, confirm: true }); if (current === ticket.current) setTransfer(result); } catch { if (current === ticket.current) setError('Successor offer was not confirmed. Check verified identity and authenticator.'); } finally { submitting.current = false; setPending(false); } }}><label>Successor Account ID<input required pattern="[0-9a-fA-F-]{36}" value={successorTarget} onChange={e => setSuccessorTarget(e.target.value)} /></label><button disabled={pending}>Send successor offer</button></form>{transfer && <><p>Transfer reference: {transfer.transfer_id}. State: {transfer.state}. Expires: {transfer.expires_at}.</p><p>The successor can accept at /auth/admin/successor using this reference.</p><button onClick={async () => { const current = ticket.current; try { const result = await request(backendUrl, session.current.access_token, 'successor/status', active.current.signal, { transfer_id: transfer.transfer_id }); if (current === ticket.current) setTransfer(result); } catch { if (current === ticket.current) setError('Successor status is unavailable.'); } }}>Verify successor access status</button></>}</section></AdminMemberships>}
        {section === 'coupons' && <section><p>Configuration only. Redemption, checkout/provider application and pricing-card exposure are disabled. Eligibility, stacking, limits, timing/duration and quote/provider terms are unset.</p><p>Use Verify access to verify your existing authenticator before saving.</p><button disabled={pending} onClick={() => setCoupon({ id: crypto.randomUUID(), operation_id: crypto.randomUUID(), expected: '0', code: '', source_discount_id: '' })}>Create inert coupon draft</button>{coupon && <form onSubmit={saveCoupon}><label>Inert coupon code (uppercase)<input disabled={pending} required pattern="[A-Z0-9_-]{1,64}" maxLength={64} value={coupon.code} onChange={event => setCoupon({ ...coupon, code: event.target.value })} /></label><label>Existing Discount ID (optional)<input disabled={pending} value={coupon.source_discount_id} onChange={event => setCoupon({ ...coupon, source_discount_id: event.target.value })} /></label><button disabled={pending}>Save inert draft</button><button className="ac-dismiss" type="button" disabled={pending} onClick={() => setCoupon(null)}>Cancel draft</button></form>}</section>}
        {error && <p role="alert">{error}</p>}
        {section === 'memberships' ? null : section === 'overview' ? <AdminOverview data={state.data} /> : state.data.items.length === 0 ? <p>No matching records.</p> : section === 'audit' ? <AdminAuditTable rows={state.data.items} /> : <div className="ac-table" role="region" aria-label={labels[section] + ' records'} tabIndex={0}><table><thead><tr>{fields[section].map(field => <th key={field} scope="col">{fieldLabels[field]}</th>)}{section === 'users' && <th scope="col">Details</th>}{section === 'coupons' && <th scope="col">Edit draft</th>}</tr></thead><tbody>{state.data.items.map(row => <tr key={row.user_id || row.subject_id || row.event_id || row.campaign_id || row.id}>{fields[section].map(field => <td key={field}>{section === 'users' && field === 'email' ? <div className="ac-audit-actor"><strong>{display(row.email)}</strong><span>Account ID: {row.user_id || 'Unavailable'}</span></div> : display(row[field])}</td>)}{section === 'users' && <td><button onClick={() => inspect(row.user_id)}>Inspect metadata</button></td>}{section === 'coupons' && <td><button disabled={pending} onClick={() => setCoupon({ id: row.id, expected: row.revision, operation_id: crypto.randomUUID(), code: row.code, source_discount_id: row.source_discount_id || '' })}>Edit inert draft</button></td>}</tr>)}</tbody></table></div>}
        {state.data.has_more && <button onClick={() => setAfter(state.data.next_cursor)}>Next page</button>}
        {after && <button onClick={() => setAfter('')}>First page</button>}
        {detail && <AdminCustomerMetadata key={detail.user_id} detail={detail} role={state.identity.role}
          onRestrict={() => { setSupportKind('access'); setAccessReview(null); setAccessDraft({ target: detail.user_id, restricted: true, reason: 'support', operation_id: crypto.randomUUID() }); }}
          onRestore={() => { setSupportKind('access'); setAccessReview(null); setAccessDraft({ target: detail.user_id, restricted: false, reason: 'support', operation_id: crypto.randomUUID() }); }}
          onCancelRenewal={operation => { setSupportKind('cancel'); setAccessReview(null); setAccessDraft({ target: detail.user_id, billing_id: operation.subscription_id, reason: 'support', operation_id: crypto.randomUUID() }); }}
          onRetry={task => { setSupportKind('privacy'); setAccessReview(null); setAccessDraft({ task_id: task.task_id, revision: task.revision, operation_id: crypto.randomUUID(), reason: 'support' }); }}
          lastCommand={lastCommand} onRefreshCancellation={async () => { const current = ticket.current; const selected = inspection.current; try { const result = await request(backendUrl, session.current.access_token, 'cancellations/' + lastCommand.operation_id, active.current.signal); if (current === ticket.current && selected === inspection.current) setLastCommand(result); } catch { if (current === ticket.current && selected === inspection.current) setError('Cancellation status is unavailable; do not assume cancellation succeeded.'); } }} />}

      </div>}
    </main>
    <dialog ref={verificationDialog} className="ac-auth-dialog" aria-labelledby="ac-auth-title" onKeyDown={containDialogFocus} onCancel={event => { if (pending) event.preventDefault(); }} onClose={() => verificationTrigger.current?.focus()}><div className="ac-auth-heading"><h2 id="ac-auth-title">Verify sensitive access</h2><button className="ac-icon-button" disabled={pending} aria-label="Close verification" onClick={() => verificationDialog.current?.close()}><X size={20} aria-hidden="true" /></button></div><p>Use your existing authenticator for sensitive actions. The server checks your current role and proof for every operation.</p><form onSubmit={verifyAuthenticator}><label>Authenticator code<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" value={code} onChange={event => setCode(event.target.value)} required /></label><button disabled={pending}>{pending ? 'Verifying...' : 'Verify authenticator'}</button></form>{error && <p role="alert">{error}</p>}</dialog>
    <dialog ref={accessDialog} aria-labelledby="access-title" onCancel={event => { if (pending) event.preventDefault(); else { setAccessDraft(null); setAccessReview(null); } }}>
      <h2 id="access-title">{supportKind === 'privacy' ? 'Retry existing cleanup task' : supportKind === 'cancel' ? 'Cancel future subscription renewal' : accessDraft?.restricted ? 'Restrict customer product access' : 'Restore staff-restricted access'}</h2>
      <p>{supportKind === 'privacy' ? 'This retries only eligible work for an existing customer-authorized request. It cannot start deletion, expand its scope, bypass holds or mark uncertain work complete.' : supportKind === 'cancel' ? 'This requests cancellation of future renewals. Cancellation is confirmed only by provider evidence. Existing paid access remains until its authoritative expiry. This does not revoke access, delete data or initiate a refund.' : 'This action does not cancel billing, issue a refund or delete account data. Restoration does not clear C15 restrictions or extend paid access.'}</p>
      {accessDraft && <form onSubmit={changeAccess}><p>{supportKind === 'privacy' ? 'Existing task' : 'Account'}: {accessDraft.target || accessDraft.task_id}</p><label>Reason<select disabled={pending || !!accessReview} value={accessDraft.reason} onChange={event => setAccessDraft({ ...accessDraft, reason: event.target.value })}><option value="support">Support</option><option value="security">Security</option></select></label>{accessReview && <p>Confirm this exact change before {accessReview.expires_at}.</p>}{error && <p role="alert">{error}</p>}<button className="ac-dismiss" type="button" disabled={pending} onClick={() => { setAccessDraft(null); setAccessReview(null); }}>Cancel</button><button disabled={pending}>{pending ? 'Checking outcome...' : accessReview ? 'Confirm access change' : 'Review access change'}</button></form>}
    </dialog>
    <dialog ref={dialog} className="am-dialog" onKeyDown={containDialogFocus} onClose={() => membershipTrigger.current?.focus()} onCancel={event => { if (pending) event.preventDefault(); else { setDraft(null); setReview(null); } }} aria-labelledby="membership-title">
      <h2 id="membership-title">{review ? 'Review access change' : state.data?.items?.some(row => row.subject_id === draft?.target) ? 'Change admin access' : 'Add administrator'}</h2>
      <p>{review ? 'Check the account and access below. Nothing changes until you confirm.' : 'Choose an existing account and the access they need. You will review the change before confirming.'}</p>
      <ol className="am-steps" aria-label="Access change steps"><li aria-current={!review ? 'step' : undefined}>1. Choose access</li><li aria-current={review ? 'step' : undefined}>2. Review and confirm</li></ol>
      {draft && <form onSubmit={membership}><fieldset disabled={pending || !!error} style={{ border: 0, padding: 0, minWidth: 0 }}>
        {!draft.target && <MembershipAccountPicker find={findMember} selected={draft.target} disabled={pending} onSelect={user => { setMemberAccount(user); setDraft({ ...draft, target: user?.user_id || '' }); }} />}
        {draft.target && <div className="am-selected"><strong>{memberAccount?.email || 'Selected account'}</strong><span>Account ID: {draft.target}</span>{!review && <button type="button" disabled={pending} onClick={() => { setMemberAccount(null); setDraft({ ...draft, target: '' }); }}>Choose a different user</button>}</div>}
        {review ? <dl className="am-review"><div><dt>Access level</dt><dd>{draft.role === 'super_admin' ? 'Super admin' : 'Admin'}</dd></div><div><dt>Status</dt><dd>{draft.status === 'active' ? 'Active' : draft.status === 'suspended' ? 'Suspended' : 'Revoked'}</dd></div><div><dt>Reason</dt><dd>{draft.reason === 'membership' ? 'Team access change' : draft.reason === 'security' ? 'Security' : 'Support'}</dd></div></dl> : <>
          <label>Access level<select aria-label="Access level" value={draft.role} disabled={pending} onChange={event => setDraft({ ...draft, role: event.target.value })}><option value="admin">Admin</option><option value="super_admin">Super admin</option></select><span className="am-hint">{draft.role === 'super_admin' ? 'Can also manage staff access, commercial settings and audit history.' : 'Can support customers, view metrics and manage campaigns. Cannot manage staff or commercial settings.'}</span></label>
          <label>Access status<select aria-label="Access status" value={draft.status} disabled={pending} onChange={event => setDraft({ ...draft, status: event.target.value })}><option value="active">Active</option><option value="suspended">Suspended</option><option value="revoked">Revoked</option></select><span className="am-hint">{draft.status === 'active' ? 'Allows the selected administration role, subject to verification and account restrictions.' : 'Removes administration access. This does not delete the account or cancel billing.'}</span></label>
          <label>Reason<select value={draft.reason} disabled={pending} onChange={event => setDraft({ ...draft, reason: event.target.value })}><option value="membership">Team access change</option><option value="security">Security</option><option value="support">Support</option></select></label>
        </>}
        {review && <p className="am-hint">This review expires {new Date(review.expires_at).toLocaleString()}. An expired or changed request must be reviewed again.</p>}
        <p className="am-hint">Staff actions cannot remove, suspend or demote the last active Super admin.</p>
        {error && <p role="alert">{error}</p>}
        </fieldset><div className="ac-actions"><button className="ac-dismiss" type="button" disabled={pending} onClick={() => { setDraft(null); setReview(null); }}>Cancel</button><button type="submit" className="am-primary" disabled={pending || !draft.target}>{pending ? 'Checking outcome?' : review ? 'Confirm access change' : 'Review change'}</button></div>
      </form>}
    </dialog>
  </AdminShell>;
}
