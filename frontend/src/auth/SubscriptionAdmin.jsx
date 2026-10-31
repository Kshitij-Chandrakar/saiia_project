import { approvedFreeDraft, approvedPaidDraft } from './catalogV2.js';
import CatalogPolicyPreview from './CatalogPolicyPreview.jsx';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useBlocker, useBeforeUnload } from 'react-router-dom';
import { Plus, ArrowRight, Check, LockKeyhole, X } from 'lucide-react';
import { supabase } from './supabaseClient';
import { signOutWebsite } from './websiteSessionLoss';
import DashboardLayout from './DashboardLayout';
import WebsiteNotFound from '../WebsiteNotFound';
import { Skeleton } from './WebsiteSkeleton';
import CatalogDraftFields, { Field } from './CatalogDraftFields';
import CatalogLifecycle from './CatalogLifecycle.jsx';
import SubscriptionReviewModal from './SubscriptionReviewModal.jsx';
import { successor } from './catalogLifecycle.js';
import { catalogRequest, CatalogError, checkedDraft } from './catalogApi.js';
import { FieldError, labels, meterLabels, minorToDecimal, newDraft, sectionFor, serialize, toForm, issueLabel } from './catalogDraft.js';
import draftArt from '../assets/admin/draft-empty.png';
import './subscription-admin.css';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const messages = {
  catalog_invalid_data: 'Some fields were rejected. Review the draft values and feature/limit compatibility; your edits are preserved.',
  catalog_database_unavailable: 'Draft storage is unavailable. Your local edits are still here.',
  catalog_write_uncertain: 'This save is not confirmed. Retry the same save to check its outcome. Do not create another save for these changes.',
  catalog_revision_conflict: 'This draft changed on the server. Your edits are preserved. Review the latest revision before continuing.',
  catalog_request_identity_conflict: 'This save identity was used with different content. Your edits are preserved; reopen the saved draft to review.',
  catalog_not_found: 'No draft with this ID was found.',
  catalog_stored_version_invalid: 'The returned draft could not be safely read. Try opening it again or contact your administrator.'
};
export default function SubscriptionAdmin({
  backendUrl,
  client = supabase
}) {
  const navigate = useNavigate(),
    session = useRef(null),
    probe = useRef(0),
    controller = useRef(null),
    alive = useRef(true),
    privateAccess = useRef(false);
  const [access, setAccess] = useState({
    status: 'loading',
    user: null
  });
  const check = useCallback(async (next, reset = false) => {
    const ticket = ++probe.current;
    controller.current?.abort();
    controller.current = new AbortController();
    if (!next?.access_token || !next.user?.id) {
      privateAccess.current = false;
      session.current = null;
      setAccess({
        status: 'unauthenticated',
        user: null
      });
      return;
    }
    session.current = next;
    if (reset) privateAccess.current = false;
    if (reset) setAccess({
      status: 'loading',
      user: null
    });
    try {
      const data = await catalogRequest(backendUrl, next.access_token, '/api/commercial/admin/me', {
        signal: controller.current.signal
      });
      if (!alive.current || ticket !== probe.current) return;
      if (!Array.isArray(data.permissions) || data.permissions.length > 1 || data.permissions.some(p => p !== 'subscriptions.manage')) throw new CatalogError('catalog_database_unavailable');
      privateAccess.current = data.permissions.includes('subscriptions.manage');
      setAccess({
        status: data.permissions.includes('subscriptions.manage') ? 'allowed' : 'forbidden',
        user: {
          id: next.user.id,
          email: next.user.email
        }
      });
    } catch (error) {
      if (alive.current && ticket === probe.current) {
        privateAccess.current = false;
        setAccess({
          status: error.code === 'unauthenticated' ? 'unauthenticated' : 'unavailable',
          user: null
        });
      }
    }
  }, [backendUrl]);
  useEffect(() => {
    alive.current = true;
    if (!client) {
      setAccess({
        status: 'unavailable',
        user: null
      });
      return () => {
        alive.current = false;
      };
    }
    const initial = probe.current;
    const {
      data
    } = client.auth.onAuthStateChange((event, next) => {
      if (event === 'INITIAL_SESSION') return;
      const same = next?.user?.id && next.user.id === session.current?.user?.id;
      check(next, !same);
    });
    client.auth.getSession().then(result => {
      if (alive.current && initial === probe.current) {
        if (result.error) setAccess({
          status: 'unavailable',
          user: null
        });else check(result.data?.session, true);
      }
    }).catch(() => {
      if (alive.current && initial === probe.current) setAccess({
        status: 'unavailable',
        user: null
      });
    });
    const refresh = () => {
      if (session.current && !document.hidden) check(session.current);
    };
    window.addEventListener('focus', refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => {
      alive.current = false;
      ++probe.current;
      controller.current?.abort();
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      data.subscription.unsubscribe();
    };
  }, [client, check]);
  function denied(code) {
    privateAccess.current = false;
    ++probe.current;
    controller.current?.abort();
    setAccess({
      status: code === 'unauthenticated' ? 'unauthenticated' : 'forbidden',
      user: null
    });
  }
  async function logout() {
    ++probe.current;
    controller.current?.abort();
    privateAccess.current = false;
    session.current = null;
    setAccess({
      status: 'unauthenticated',
      user: null
    });
    try {
      const result = await signOutWebsite(client);
      if (result.error) throw new Error();
      navigate('/auth/login', {
        replace: true
      });
    } catch {
      setAccess({
        status: 'unavailable',
        user: null
      });
    }
  }
  if (['unauthenticated', 'forbidden'].includes(access.status)) return <WebsiteNotFound />;
  return <DashboardLayout user={access.user || {}} title="Subscription drafts" description="Manage private plan drafts and review their requirements." onLogout={logout} loading={access.status === 'loading'} subscriptionAdmin={access.status === 'allowed'}>
    {access.status === 'allowed' ? <DraftWorkspace key={access.user.id} accountId={access.user.id} backendUrl={backendUrl} token={() => session.current?.access_token} mayBlock={() => privateAccess.current && session.current?.user?.id === access.user.id} onDenied={denied} /> : <section className="subscription-admin ca-access" aria-live="polite">
      {access.status === 'loading' ? <><Skeleton width="55%" height={28} /><Skeleton width="80%" height={16} /><p>Checking subscription-admin access...</p></> : <><LockKeyhole size={28} aria-hidden="true" /><h2>{access.status === 'unauthenticated' ? 'Sign in to continue' : access.status === 'forbidden' ? 'Subscription-admin access required' : 'Admin access is unavailable'}</h2><p>{access.status === 'unauthenticated' ? 'Use your website account to check your current permissions.' : access.status === 'forbidden' ? 'Your account does not currently have permission to manage subscription drafts.' : 'Your permissions could not be confirmed. Private drafts are hidden.'}</p>{access.status === 'unauthenticated' ? <Link className="wd-primary" to="/auth/login">Sign in</Link> : <button type="button" onClick={() => client?.auth.getSession().then(r => {
          if (r.error) setAccess({
            status: 'unavailable',
            user: null
          });else check(r.data?.session, true);
        }).catch(() => setAccess({
          status: 'unavailable',
          user: null
        }))}>Check access again</button>}</>}
    </section>}
  </DashboardLayout>;
}
function DraftWorkspace({
  accountId,
  backendUrl,
  token,
  mayBlock,
  onDenied
}) {
  const [form, setFormState] = useState(null),
    [saved, setSaved] = useState(null),
    [section, setSection] = useState('Identity');
  const [openId, setOpenId] = useState(''),
    [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false),
    [pending, setPending] = useState(null),
    [notice, setNotice] = useState(null),
    [errors, setErrors] = useState({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [preview, setPreview] = useState(null),
    [remote, setRemote] = useState(null),
    [confirm, setConfirm] = useState(null);
  const [lifecyclePending, setLifecyclePending] = useState(null), [terminal, setTerminal] = useState(false);
  const [closedSessions, setClosedSessions] = useState(0);
  const importArea = useRef(null);
  const epoch = useRef(0),
    mounted = useRef(true),
    inflight = useRef(false),
    requests = useRef(new Set()),
    noticeRef = useRef(null),
    baseline = useRef(null),
    navigationDialog = useRef(null);
  const dirty = Boolean(form && (JSON.stringify(form) !== JSON.stringify(baseline.current) || reason !== ''));
  const blocker = useBlocker(({
    currentLocation,
    nextLocation
  }) => Boolean(mayBlock() && (dirty || pending || lifecyclePending) && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search)));
  useBeforeUnload(useCallback(event => {
    if (mayBlock() && (dirty || pending || lifecyclePending)) {
      event.preventDefault();
      event.returnValue = '';
    }
  }, [dirty, pending, lifecyclePending, mayBlock]));
  useEffect(() => {
    if (blocker.state === 'blocked') {
      // A save may finish while the prompt is open. Stay on the now-clean draft.
      if (!dirty && !pending && !lifecyclePending) {
        blocker.reset();
        return;
      }
      if (!navigationDialog.current?.open) navigationDialog.current?.showModal();
    } else navigationDialog.current?.close();
  }, [blocker, dirty, pending, lifecyclePending]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      ++epoch.current;
      requests.current.forEach(c => c.abort());
    };
  }, []);
  useEffect(() => {
    if (notice?.kind === 'error') noticeRef.current?.focus();
  }, [notice]);
  useEffect(() => { setPreviewOpen(false); }, [form?.draft_id, saved?.revision, dirty]);
  function setForm(update) {
    setFormState(update);
    setPreview(null);
    setErrors({});
    setNotice(null);
  }
  async function perform(work) {
    if (inflight.current) return;
    inflight.current = true;
    setBusy(true);
    const own = epoch.current,
      control = new AbortController();
    requests.current.add(control);
    const current = () => mounted.current && own === epoch.current;
    try {
      await work((path, options = {}) => catalogRequest(backendUrl, token(), path, {
        ...options,
        signal: control.signal
      }), current);
    } catch (error) {
      if (current()) {
        if (['unauthenticated', 'catalog_permission_denied'].includes(error.code)) onDenied(error.code);else setNotice({
          kind: 'error',
          code: error.code,
          text: messages[error.code] || 'The request could not be completed.'
        });
      }
    } finally {
      requests.current.delete(control);
      inflight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function choose(action) {
    if (pending || busy || lifecyclePending) return;
    if (dirty) {
      setConfirm(() => action);
      return;
    }
    action();
  }
  function adopt(document) {
    const next = toForm(document);
    ++epoch.current;
    baseline.current = next;
    setFormState(next);
    setSaved(document);
    setTerminal(false);
    setReason('');
    setPreview(null);
    setPending(null);
    setRemote(null);
    setErrors({});
    setNotice(null);
    setSection('Identity');
    setOpenId(document.draft_id);
  }
  function importFree(code = 'free') {
    choose(() => {
      let draft;
      try { draft = code === 'free' ? approvedFreeDraft() : approvedPaidDraft(code); } catch { setNotice({kind:'error',text:'The approved reference failed validation. Review its registered allowances and plain-text presentation before importing.'}); return; }
      ++epoch.current; baseline.current = null;
      setFormState(toForm(draft)); setSaved(null); setTerminal(false); setPending(null);
      setPreview(null); setNotice(null); setErrors({}); setRemote(null); setReason(''); setOpenId(''); setSection('Identity');
    });
  }
  function closeDraft() {
    if (inflight.current || busy || pending || lifecyclePending) return;
    const closedEpoch = ++epoch.current;
    requests.current.forEach(control => control.abort());
    baseline.current = null;
    setFormState(null); setSaved(null); setPreview(null); setRemote(null);
    setErrors({}); setNotice(null); setConfirm(null); setReason('');
    setOpenId(''); setSection('Identity'); setTerminal(false);
    setClosedSessions(value => value + 1);
    if (blocker.state === 'blocked') blocker.reset();
    navigationDialog.current?.close();
    requestAnimationFrame(() => {
      if (mounted.current && epoch.current === closedEpoch) {
        importArea.current?.focus();
        importArea.current?.scrollIntoView({block:'center'});
      }
    });
  }
  function start() {
    ++epoch.current;
    baseline.current = toForm(newDraft());
    setFormState(baseline.current);
    setSaved(null);
    setTerminal(false);
    setReason('');
    setPending(null);
    setPreview(null);
    setErrors({});
    setNotice(null);
    setRemote(null);
    setSection('Identity');
  }
  function open(review = false) {
    const id = review ? saved?.draft_id : openId.trim().toLowerCase();
    if (!uuid.test(id || '')) {
      setNotice({
        kind: 'error',
        text: 'Enter a complete draft ID.'
      });
      return;
    }
    perform(async (request, current) => {
      const d = checkedDraft(await request(`/api/admin/catalog/drafts/${id}`));
      if (current()) {
        if (d.draft_id !== id) throw new CatalogError('catalog_stored_version_invalid');
        if (review) setRemote(d);else {
          adopt(d);
          inflight.current = false;
          setBusy(false);
        }
      }
    });
  }
  function save(retry = false) {
    if (inflight.current || lifecyclePending || terminal) return;
    let operation = pending;
    if (!retry) {
      try {
        const document = serialize(form, saved?.revision, reason);
        operation = {
          path: saved ? `/api/admin/catalog/drafts/${document.draft_id}` : `/api/admin/catalog/plans/${document.plan.plan_id}/drafts`,
          method: saved ? 'PATCH' : 'POST',
          body: {
            document,
            reason
          },
          key: crypto.randomUUID(),
          revision: saved?.revision
        };
      } catch (error) {
        if (error instanceof FieldError) {
          setSection(sectionFor(error.path));
          setErrors({
            [error.path]: error.message
          });
          setNotice({
            kind: 'error',
            text: error.message
          });
          requestAnimationFrame(() => document.getElementById(`catalog-${error.path}`)?.focus());
        }
        return;
      }
      setPending(operation);
    }
    if (!operation) return;
    perform(async (request, current) => {
      try {
        const data = await request(operation.path, operation);
        let result;
        try {
          result = checkedDraft(data);
          if (result.draft_id !== operation.body.document.draft_id || result.revision !== operation.body.document.revision) throw new Error();
        } catch {
          throw new CatalogError('catalog_write_uncertain');
        }
        if (current()) {
          setSaved(result);
          setOpenId(result.draft_id);
          baseline.current = toForm(result);
          setFormState(baseline.current);
          setReason('');
          setPending(null);
          setErrors({});
          setPreview(null);
          setNotice({
            kind: 'success',
            text: `Draft saved. Revision ${result.revision}.`
          });
        }
      } catch (error) {
        if (current() && !['catalog_write_uncertain', 'catalog_database_unavailable'].includes(error.code)) setPending(null);
        if (current() && error.code === 'catalog_revision_conflict' && !saved) {
          setNotice({kind:'error',code:error.code,text:`The ${operation.body.document.plan.code} plan code already exists or this candidate is stale. Open the previously saved draft by its ID; importing again does not update that draft. To change a published offer, use Open offer and Create a new draft version.`});
          return;
        }
        throw error;
      }
    });
  }
  function previewSaved() {
    setPreviewOpen(true);
    setNotice(null);
    perform(async (request, current) => {
      const result = await request(`/api/admin/catalog/drafts/${saved.draft_id}/preview`, {
        method: 'POST',
        body: {
          expected_revision: saved.revision,
          contract_version: saved.contract_version
        }
      });
      if (current()) {
        if (result.draft_id !== saved.draft_id || result.revision !== saved.revision || result.validation_scope !== 'structural_only' || result.publication_enabled !== false || !Array.isArray(result.errors) || !Array.isArray(result.pending)) throw new CatalogError('catalog_stored_version_invalid');
        setPreview(result);
        setNotice(null);
      }
    });
  }
  function focusIssue(issue) {
    setPreviewOpen(false);
    const path = issue.path.join('.');
    setSection(sectionFor(path));
    requestAnimationFrame(() => {
      const target = document.getElementById(`catalog-${path}`) || document.querySelector('.ca-editor h2');
      if (target) {
        let parent = target.parentElement;
        while (parent) {
          if (parent.tagName === 'DETAILS') parent.open = true;
          parent = parent.parentElement;
        }
        target.focus();
      }
    });
  }
  function newVersion(source) {
    choose(() => {
      const copy = successor(source);
      ++epoch.current;
      baseline.current = null; // a copied version is unsaved, never a confirmed save
      setFormState(toForm(copy)); setSaved(null); setTerminal(false); setPreview(null);
      setReason(''); setPending(null); setRemote(null); setErrors({}); setSection('Identity');
      setNotice({ kind: 'success', text: 'New draft version copied. Review its terms and save it before publication review. Price and discount version IDs are new.' });
    });
  }
  return <div className="subscription-admin">
    <dialog ref={navigationDialog} className="ca-navigation-dialog" aria-labelledby="ca-navigation-title" aria-describedby="ca-navigation-description" onCancel={event => {
      event.preventDefault();
      blocker.reset?.();
    }}>
      <h2 id="ca-navigation-title">Leave this draft?</h2>
      <p id="ca-navigation-description">{lifecyclePending ? 'This lifecycle action is not confirmed. Keep its operation ID before leaving; leaving does not cancel a request already sent. After reload, explicitly check the operation ID. No write is automatically repeated.' : pending ? 'This save is not confirmed. Leaving discards local edits and the retry identity from this browser tab. It does not cancel a save already sent to the server.' : 'You have unsaved edits. Discarding leaves this page without saving them.'}</p>
      <div className="ca-actions"><button type="button" autoFocus onClick={() => blocker.reset?.()}>Stay</button><button type="button" onClick={() => blocker.proceed?.()}>Discard and leave</button></div>
    </dialog>
    <div className="ca-intro"><div><span className="ca-tag"><LockKeyhole size={13} aria-hidden="true" />Private administration</span><h2>Build the next offer, in draft.</h2><p>Save unfinished work, review exact terms and confirm versioned catalog actions separately.</p></div><button type="button" disabled={busy || Boolean(pending) || Boolean(lifecyclePending)} onClick={() => choose(start)}><Plus size={16} aria-hidden="true" />New draft</button></div>
    <div className="ca-import" ref={importArea} role="region" aria-label="Approved plan imports" tabIndex={-1}><button type="button" disabled={busy || Boolean(pending) || Boolean(lifecyclePending) || Boolean(form)} onClick={() => importFree('free')}>Import approved Free draft</button>{['plus','pro'].map(code => <button key={code} type="button" disabled={busy || Boolean(pending) || Boolean(lifecyclePending) || Boolean(form)} onClick={() => importFree(code)}>Import approved {code === 'plus' ? 'Plus' : 'Pro'} draft</button>)}<p>Loads one unsaved draft. Review and save explicitly. Reopen its ID to edit; importing again creates a separate candidate, never an automatic overwrite. Stable plan codes reject duplicate stored plans.</p></div>
    <div className="ca-checkpoint"><strong>Before real offers</strong><span>Free terms are approved for draft configuration. Plus/Pro prices and allocations are approved. Tax, trials, discounts, review validity and subscriber policies still require explicit decisions before real publication. Publication still requires authoritative policy approval.</span></div>
    <form autoComplete="off" className="ca-open" onSubmit={e => {
      e.preventDefault();
      choose(() => open());
    }}><Field path="open-id" label="Open a draft by ID" value={openId} onChange={setOpenId} placeholder="Paste a saved draft ID" /><button disabled={busy || Boolean(pending) || Boolean(lifecyclePending)} type="submit">Open draft<ArrowRight size={16} aria-hidden="true" /></button><span>No draft listing is available yet.</span></form>
    <CatalogLifecycle key={closedSessions} accountId={accountId} saved={saved} dirty={dirty} ready={Boolean(preview?.publishable && !preview.errors.length && !preview.pending.length)} busy={busy} blocked={Boolean(pending)} locked={terminal} perform={perform} onPending={setLifecyclePending} onCommitted={id => { if (id === saved?.draft_id) setTerminal(true); }} onNewVersion={newVersion} />
    {confirm && <div className="ca-feedback" role="alert"><p>Discard unsaved local edits and continue?</p><button type="button" onClick={() => {
        const action = confirm;
        setConfirm(null);
        action();
      }}>Discard edits and continue</button><button type="button" onClick={() => setConfirm(null)}>Keep editing</button></div>}
    {notice && !previewOpen && <div className={`ca-feedback ca-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'} tabIndex={-1} ref={noticeRef}>{notice.kind === 'success' && <Check size={16} aria-hidden="true" />}<p>{notice.text}</p>{notice.code === 'catalog_revision_conflict' && saved && <button type="button" disabled={busy} onClick={() => open(true)}>Review latest revision</button>}</div>}
    {remote && <section className="ca-review" aria-label="Revision review"><h3>Latest revision {remote.revision}</h3><p>Your local edits are still in the editor. Loading this version will replace them only when you choose.</p><dl><dt>Saved name</dt><dd>{remote.terms.name || 'Not set'}</dd><dt>Saved description</dt><dd>{remote.terms.description || 'Not set'}</dd><dt>Prices / limits / discounts</dt><dd>{remote.terms.prices.length} / {remote.terms.limits.length} / {remote.terms.discounts.length}</dd></dl><details><summary>Review all saved authoring fields</summary><pre>{JSON.stringify(remote, null, 2)}</pre></details><button type="button" disabled={busy || Boolean(pending)} onClick={() => adopt(remote)}>Replace local edits with latest</button><button type="button" onClick={() => setRemote(null)}>Keep local edits</button></section>}
    {!form ? <section className="ca-welcome"><div className="ca-draft-art" aria-hidden="true"><img src={draftArt} alt="" width="160" height="160" /></div><h2>A workspace for unfinished plans</h2><p>Create a blank draft or open one by ID. Draft editing alone never publishes an offer or changes customer access.</p><button className="wd-primary" type="button" disabled={busy || Boolean(pending) || Boolean(lifecyclePending)} onClick={() => choose(start)}>Create a blank draft</button></section> : <div className="ca-workspace"><div className="ca-editor">
      <div className="ca-document-heading"><div><h2>{form.terms.name || 'Untitled draft'}</h2><p>{saved ? terminal ? `Reviewed revision ${saved.revision}; read only` : `Revision ${saved.revision}` : 'Not saved yet'} <span className="ca-dot">·</span> {dirty ? 'Unsaved changes' : saved ? 'All changes saved' : 'No edits yet'}</p></div><div className="ca-document-controls"><span className="ca-tag">{terminal ? 'Published source; read only' : 'Draft'}</span><span className="ca-close-wrap"><button type="button" className="ca-close-draft" aria-label="Close draft" aria-describedby="ca-close-description" disabled={busy || Boolean(pending) || Boolean(lifecyclePending)} onClick={closeDraft}><X size={17} aria-hidden="true" /></button><span id="ca-close-description" role="tooltip">{pending || lifecyclePending ? 'Resolve the unconfirmed operation before closing. Its recovery identity must be retained.' : busy ? 'Wait for the current operation to finish before closing.' : 'Close this editor and discard unsaved changes. Saved records are retained.'}</span></span></div></div>
      {saved && <p className="ca-muted">Saved draft ID: <code>{saved.draft_id}</code></p>}<details className="ca-ids"><summary>Draft ID & plan identity</summary><p>Draft ID <code>{form.draft_id}</code></p><p>Plan ID <code>{form.plan.plan_id}</code></p><small>Keep the draft ID to reopen it. Private drafts are not stored in this browser.</small></details>
      <nav className="ca-tabs" aria-label="Draft sections">{['Identity', 'Prices', 'Features & limits', 'Discounts', ...(['catalog.v2','catalog.v3'].includes(form.contract_version) ? ['Usage & presentation'] : [])].map(name => <button key={name} type="button" aria-current={section === name ? 'page' : undefined} onClick={() => setSection(name)}>{name}</button>)}</nav>
      <form autoComplete="off" onSubmit={e => {
          e.preventDefault();
          save();
        }}>
        <fieldset className="ca-editable" disabled={busy || Boolean(pending) || Boolean(lifecyclePending) || terminal}><CatalogDraftFields form={form} setForm={setForm} section={section} baseRevision={saved?.revision} errors={errors} /><div className="ca-save-reason"><Field path="reason" label="Change reason" value={reason} onChange={v => {
                setReason(v);
              }} error={errors.reason} help="Required for the audit record. Explain this logical save." /></div></fieldset>
        <div className="ca-actions">{pending ? <><button type="button" className="wd-primary" disabled={busy} onClick={() => save(true)}>{busy ? 'Checking save...' : 'Retry same save'}</button>{notice?.code === 'catalog_database_unavailable' && <button type="button" onClick={() => {
                setPending(null);
                setNotice(null);
              }}>Continue editing</button>}</> : <button type="submit" className="wd-primary" disabled={busy || Boolean(lifecyclePending) || terminal || !dirty || notice?.code === 'catalog_revision_conflict'}>{busy ? 'Saving draft...' : saved ? 'Save changes' : 'Save draft'}</button>}<button type="button" disabled={!saved || dirty || busy || Boolean(pending) || Boolean(lifecyclePending) || terminal} onClick={previewSaved}>Preview saved draft</button></div><p className="ca-muted ca-save-help">{dirty ? 'Save changes before previewing.' : 'Preview uses the confirmed saved revision.'}</p>
      </form>
    </div><SubscriptionReviewModal busy={busy} open={previewOpen} onClose={() => setPreviewOpen(false)} identity={`${saved?.terms.name || 'Unnamed plan'} / saved revision ${saved?.revision || 'not saved'}`}><section className="ca-preview" aria-label="Draft preview"><h3>Customer-facing preview</h3>{busy && <p role="status">Loading saved draft preview...</p>}{notice && <div className="ca-feedback ca-error" role="alert">{notice.text}</div>}{preview ? <><span className="ca-tag">Saved revision {preview.revision}</span><h3>{saved.terms.name || 'Name not configured'}</h3><p>{saved.terms.description || 'Description not configured'}</p>{['catalog.v2','catalog.v3'].includes(saved.contract_version) ? <CatalogPolicyPreview terms={saved.terms} /> : <><div className="ca-preview-prices">{saved.terms.prices.map(p => <p key={p.price_id}><strong>{p.amount_minor === null ? 'Amount not configured' : `${p.currency} ${minorToDecimal(p.amount_minor, Number(p.exponent))}`}</strong><span>{p.billing ? ` every ${p.billing.count} ${p.billing.unit}(s)` : ' · Billing not configured'}</span></p>)}</div><ul>{saved.terms.entitlements.filter(e => e.allowed).map(e => <li key={e.feature}>{labels[e.feature]}</li>)}{saved.terms.limits.map(l => <li key={l.meter}>{meterLabels[l.meter]}: {l.amount === null ? 'not configured' : l.meter === 'auto.authorized_running' ? `${BigInt(l.amount) / 60n} min ${BigInt(l.amount) % 60n} sec` : `${l.amount} ${l.unit}`}{l.reset ? ` / ${l.reset.count} ${l.reset.unit}(s) reset` : l.grant_kind === 'one_time' ? ' / one-time' : ''}</li>)}</ul>
      {saved.terms.discounts.length > 0 && <section><h3>Draft discounts</h3>{saved.terms.discounts.map(d => <p key={d.discount_id}>{d.public_label || 'Discount label not configured'}: {d.kind === 'percentage' ? d.basis_points === null ? 'Value not configured' : `${minorToDecimal(d.basis_points, 2)}%` : d.amount_minor === null ? 'Value not configured' : `${d.currency} ${minorToDecimal(d.amount_minor, Number(d.exponent))}`}. Eligibility and application remain subject to configured policies.</p>)}</section>}</>}<div className="ca-readiness"><h3>{preview.pending.length || preview.errors.length ? 'Requirements to resolve' : 'Structural checks complete'}</h3>{[...preview.errors, ...preview.pending].map((issue, i) => <button type="button" key={i} onClick={() => focusIssue(issue)}>{issueLabel(issue)}</button>)}</div></> : <div className="ca-preview-empty"><p>Review the saved customer-facing wording and remaining requirements here.</p><small>Save a draft, then choose Preview saved draft.</small></div>}<p className="ca-preview-note">Structural preview only. A separate review and confirmation is required for publication. Checkout and customer access remain unavailable.</p></section></SubscriptionReviewModal></div>}
  </div>;
}
