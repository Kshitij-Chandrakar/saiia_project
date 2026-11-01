import CatalogPolicyPreview from './CatalogPolicyPreview.jsx';
import SubscriptionReviewModal from './SubscriptionReviewModal.jsx';
import PublishedOffers from './PublishedOffers.jsx';
import { useEffect, useRef, useState } from 'react';
import { Field } from './CatalogDraftFields';
import { CatalogError } from './catalogApi.js';
import { labels, meterLabels, minorToDecimal } from './catalogDraft.js';
import { checkedBasis, checkedOffer, checkedResult, checkedReview, isId, same, istToUtc, formatIst } from './catalogLifecycle.js';
const messages = {
  catalog_review_stale: 'The reviewed draft, offer or approval changed. Reopen the saved draft and request a fresh review.',
  catalog_revision_conflict: 'The revision changed. Refresh the offer or reopen the draft before a new action.',
  catalog_not_publishable: 'The saved terms are incomplete. Resolve the saved preview requirements before reviewing.',
  catalog_invalid_data: 'These values or preconditions were rejected. Check the saved revision and review inputs.',
  catalog_request_identity_conflict: 'This operation ID belongs to different request details. Check its recorded outcome; do not automatically submit a new action.',
  catalog_database_unavailable: 'Lifecycle storage or policy approval is unavailable. No completion has been confirmed.',
  commercial_path_unreviewed: 'Lifecycle actions are disabled or unavailable on this server. Your draft remains private.',
  catalog_stored_version_invalid: 'This record could not be safely read. No new action is available from it.',
  catalog_write_uncertain: 'The outcome is unknown. Check this operation or retry exactly the same action. A timeout does not confirm success or failure.',
  catalog_not_found: 'No committed result was found. This does not prove a pending action failed. Keep its operation ID.'
};
export function Terms({
  document
}) {
  const t = document.terms;
  return <section className="ca-terms" aria-label={`Terms for ${t.name || 'unnamed plan'}`}>
    {['catalog.v2','catalog.v3'].includes(document.contract_version) && <CatalogPolicyPreview terms={t} />}<h3>{t.name || 'Name not configured'}</h3><p>{t.description || 'Description not configured'}</p>
    <p className="ca-muted">Plan {document.plan.code}</p>
    <h4>Prices and billing</h4>{t.prices.map(p => <p key={p.price_id}><strong>{p.currency} {minorToDecimal(p.amount_minor, Number(p.exponent))}</strong>{p.billing ? ` every ${p.billing.count} ${p.billing.unit}(s)` : ' — billing not configured'}</p>)}
    <h4>Features and allowances</h4><ul>{t.entitlements.map(e => <li key={e.feature}>{labels[e.feature]}: {e.allowed ? 'Included' : 'Not included'}{e.model_keys.length ? ` · Models: ${e.model_keys.join(', ')}` : ''}{e.audio_sources.length ? ` · Audio: ${e.audio_sources.join(', ')}` : ''}</li>)}
      {t.limits.map(l => <li key={l.meter}>{meterLabels[l.meter]} ({l.kind}): {l.amount === null ? 'Not configured' : l.meter === 'auto.authorized_running' ? `${BigInt(l.amount) / 60n} min ${BigInt(l.amount) % 60n} sec` : `${l.amount} ${l.unit}`}. {l.reset ? `Resets every ${l.reset.count} ${l.reset.unit}(s), ${l.reset.anchor}, ${l.reset.timezone}.` : l.grant_kind === 'one_time' ? 'One-time allowance.' : 'No recurring reset configured.'}</li>)}</ul>
    <p className="ca-muted">Billing frequency and allowance reset cadence are separate. Blank values never mean unlimited.</p>
    {t.discounts.length > 0 && <><h4>Discounts</h4>{t.discounts.map(d => <p key={d.discount_id}>{d.public_label || 'Unnamed discount'}: {d.kind === 'percentage' ? `${minorToDecimal(d.basis_points, 2)}%` : `${d.currency} ${minorToDecimal(d.amount_minor, Number(d.exponent))}`}. {d.duration}; stacking {d.stacking ? 'allowed' : 'not allowed'}.</p>)}</>}
    <details><summary>All terms and policy references</summary><pre>{JSON.stringify(t, null, 2)}</pre></details>
  </section>;
}
export default function CatalogLifecycle({
  saved,
  dirty,
  ready,
  busy,
  blocked,
  locked,
  accountId,
  perform,
  onPending,
  onCommitted,
  onNewVersion
}) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const [action, setAction] = useState('publish'),
    [from, setFrom] = useState(''),
    [until, setUntil] = useState(''),
    [reason, setReason] = useState('');
  const [bundle, setBundle] = useState(null),
    [review, setReview] = useState(null),
    [offer, setOffer] = useState(null),
    [result, setResult] = useState(null);
  const [pending, setPending] = useState(null),
    [notice, setNotice] = useState(null),
    [confirmation, setConfirmation] = useState(null);
  const [offerId, setOfferId] = useState(''),
    [recoveryId, setRecoveryId] = useState('');
  const mounted = useRef(false),
    sequence = useRef(0),
    guard = useRef(false),
    trigger = useRef(null),
    status = useRef(null),
    heading = useRef(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      ++sequence.current;
    };
  }, []);
  useEffect(() => {
    ++sequence.current;
    setBundle(null);
    setReview(null);
    setConfirmation(null);
    setReviewOpen(false);
  }, [saved?.draft_id, saved?.revision, dirty]);
  useEffect(() => {
    if (!pending) {setNotice(null);setResult(null);setOffer(null);}
  }, [saved?.draft_id]);
  useEffect(() => {
    if (notice?.kind === 'error') status.current?.focus();
  }, [notice]);
  const disabled = busy || blocked || Boolean(pending);
  function note(code) {
    setNotice({
      kind: 'error',
      code,
      text: messages[code] || 'The request could not be completed safely.'
    });
  }
  function run(work) {
    if (guard.current || busy) return;
    guard.current = true;
    const own = ++sequence.current;
    return perform(async (request, current) => {
      const valid = () => current() && mounted.current && own === sequence.current;
      try {
        await work(request, valid);
      } catch (error) {
        if (!valid()) return;
        if (['unauthenticated', 'catalog_permission_denied'].includes(error.code)) throw error;
        note(error.code);
        if (['catalog_review_stale', 'catalog_revision_conflict'].includes(error.code)) {
          setReview(null);
          setBundle(null);
        }
      }
    }).finally(() => {
      guard.current = false;
    });
  }
  function change(setter, value) {
    ++sequence.current;
    setter(value);
    setReview(null);
    setBundle(null);
    setNotice(null);
  }
  async function loadOffer(request, id) {
    const value = checkedOffer(await request(`/api/admin/catalog/offers/${id}`));
    if (value.snapshot.offer_version_id !== id) throw new CatalogError('catalog_stored_version_invalid');
    return value;
  }
  function openListedOffer(id,edit=false) {
    let source;
    const own=sequence.current+1;
    const operation=run(async(request,valid)=>{
      const next=await loadOffer(request,id);
      if(!valid())return;
      setOffer(next);setOfferId(id);setResult(null);setNotice(null);
      if(edit && next.source)source=next.source;
      else if(next.source)onCommitted(next.source.draft_id);
    });
    // Release the parent's request slot before its existing local-copy action
    // changes draft identity/epoch; that action also handles unsaved-edit prompts.
    operation?.then(()=>{
      if(source && mounted.current && sequence.current===own)onNewVersion(source);
    });
  }
  function prepareReview() {
    if (!saved || dirty || !ready || disabled || locked) return;
    setReviewOpen(true);
    setNotice(null);
    trigger.current = document.activeElement;
    const start = istToUtc(from), end = until ? istToUtc(until) : null;
    if (!reason.trim() || reason.length > 2000 || !start || until && (!end || Date.parse(end) <= Date.parse(start))) {
      setNotice({
        kind: 'error',
        text: 'Enter a lifecycle reason and a valid offer start time in IST. An optional end must be later than the start.'
      });
      return;
    }
    run(async (request, valid) => {
      const data = await request(`/api/admin/catalog/drafts/${saved.draft_id}/preview`, {
        method: 'POST',
        body: {
          scope: 'publication_review',
          expected_revision: saved.revision,
          contract_version: saved.contract_version,
          intent: {
            action,
            valid_from: start,
            valid_until: end
          }
        }
      });
      const basis = checkedBasis(data.basis, saved);
      if (data.validation_scope !== 'publication_review' || data.publication_enabled !== false || basis.intent.action !== action) throw new CatalogError('catalog_stored_version_invalid');
      const previous = basis.current_offer ? await loadOffer(request, basis.current_offer.offer_version_id) : null;
      if (previous && (previous.current.state !== 'visible' || previous.current.revision !== basis.current_offer.visibility_revision || previous.publication?.fingerprint !== basis.current_offer.fingerprint)) throw new CatalogError('catalog_review_stale');
      if (valid()) {
        const next = {
          basis,
          document: structuredClone(saved),
          previous,
          reason
        };
        setBundle(next);
        setReview(null);
        setNotice(null);
        setConfirmation({
          kind: 'review',
          bundle: next
        });
      }
    });
  }
  function finishPending(value) {
    setPending(value);
    onPending(value);
    if (value) setRecoveryId(value.key);
  }
  async function accept(value, operation, request, valid) {
    if (value.receipt?.storage_version === 'catalog.review.store.v1') {
      const evidence = checkedReview(value);
      if (evidence.receipt.reviewer_subject !== accountId || operation && (operation.kind !== 'review.create' || !same(evidence.receipt.basis, operation.body.basis))) throw new CatalogError('catalog_stored_version_invalid');
      if (!valid()) return;
      if (saved && !dirty && saved.draft_id === evidence.receipt.basis.draft_id && saved.revision === evidence.receipt.basis.revision) {
        const b = evidence.receipt.basis;
        const previous = operation?.reviewBundle?.previous || (b.current_offer ? await loadOffer(request, b.current_offer.offer_version_id) : null);
        if (!valid()) return;
        setBundle({
          basis: b,
          document: structuredClone(saved),
          previous,
          reason: operation?.body.reason || reason
        });
        setReview(evidence);
      }
      finishPending(null);
      setNotice({
        kind: 'success',
        text: evidence.state === 'current' ? `Review recorded for saved revision ${evidence.receipt.basis.revision}. Publication still requires a separate confirmation. If recovering another draft, open that draft and request a fresh review.` : `Review recorded, but it is no longer eligible (${evidence.state.replaceAll('_', ' ')}). Request a fresh review.`
      });
      return;
    }
    const next = checkedResult(value, operation);
    if (next.receipt.actor_subject !== accountId) throw new CatalogError('catalog_stored_version_invalid');
    if (!valid()) return;
    finishPending(null);
    setResult(next);
    setReview(null);
    setBundle(null);
    setOffer(null);
    setOfferId(next.receipt.offer_version_id);
    if (operation?.sourceId && next.receipt.operation !== 'offer.retire') onCommitted(operation.sourceId);
    setNotice({
      kind: 'success',
      text: `${next.receipt.operation === 'offer.replace' ? 'Replacement' : next.receipt.operation === 'offer.retire' ? 'Retirement' : 'Publication'} recorded. Customer payments and access were not changed. Current state at confirmation: ${next.current.state}.`
    });
    try {
      const current = await loadOffer(request, next.receipt.offer_version_id);
      if (valid()) {
        setOffer(current);
        if (current.source) onCommitted(current.source.draft_id);
      }
    } catch (error) {
      if (['unauthenticated', 'catalog_permission_denied'].includes(error.code)) throw error;
      if (valid()) setNotice({
        kind: 'error',
        text: 'The action was confirmed, but the current offer could not be refreshed. Keep the operation ID and refresh the offer.'
      });
    }
  }
  function send(operation) {
    if (guard.current || busy) return;
    run(async (request, valid) => {
      finishPending(operation);
      setNotice(null);
      try {
        const value = await request(operation.path, operation);
        try {
          await accept(value, operation, request, valid);
        } catch (error) {
          if (error.code === 'catalog_stored_version_invalid') throw new CatalogError('catalog_write_uncertain');
          throw error;
        }
      } catch (error) {
        if (valid() && !['catalog_write_uncertain', 'catalog_database_unavailable'].includes(error.code)) finishPending(null);
        throw error;
      }
    });
  }
  function confirmAction() {
    if (guard.current || busy || pending || !confirmation) return;
    const c = confirmation;
    setConfirmation(null);
    if (c.kind !== 'retire' && (dirty || !saved || saved.revision !== c.bundle.basis.revision || saved.draft_id !== c.bundle.basis.draft_id || Date.parse(c.bundle.basis.authority.valid_until) <= Date.now())) {
      note('catalog_review_stale');
      setReview(null);
      return;
    }
    const op = {
      key: crypto.randomUUID(),
      method: 'POST',
      kind: c.kind === 'review' ? 'review.create' : `offer.${c.kind}`
    };
    if (c.kind === 'review') Object.assign(op, {
      path: `/api/admin/catalog/drafts/${saved.draft_id}/publication-reviews`,
      reviewBundle: c.bundle,
      revision: saved.revision,
      body: {
        basis: c.bundle.basis,
        confirmed: true,
        reason: c.bundle.reason
      }
    });else if (c.kind === 'retire') Object.assign(op, {
      path: `/api/admin/catalog/offers/${c.offer.snapshot.offer_version_id}/retire`,
      offerId: c.offer.snapshot.offer_version_id,
      revision: c.offer.current.revision,
      body: {
        reason
      }
    });else Object.assign(op, {
      path: `/api/admin/catalog/drafts/${saved.draft_id}/${c.kind}`,
      sourceId: saved.draft_id,
      revision: c.bundle.basis.revision,
      body: {
        review_id: review.receipt.review_id,
        expected_archive_revision: c.bundle.basis.archived_offer?.visibility_revision || null,
        reason,
        ...(c.kind === 'replace' ? {
          predecessor: c.bundle.basis.current_offer
        } : {})
      }
    });
    send(op);
  }
  function recover() {
    const id = pending?.key || recoveryId.trim().toLowerCase();
    if (!isId(id)) {
      setNotice({
        kind: 'error',
        text: 'Enter a complete operation ID.'
      });
      return;
    }
    run(async (request, valid) => {
      const value = await request(`/api/admin/catalog/operations/${id}`);
      if (value.receipt?.request_id && value.receipt.request_id !== id) throw new CatalogError('catalog_stored_version_invalid');
      await accept(value, pending, request, valid);
    });
  }
  const eligible = review?.state === 'current' && bundle && !dirty && saved?.revision === bundle.basis.revision && saved?.draft_id === bundle.basis.draft_id && !locked;
  const reviewFeedback = <>
{review && <p role="status">Review {review.state === 'current' ? `recorded for revision ${review.receipt.basis.revision}` : `is ${review.state.replaceAll('_', ' ')}`}. Changes require fresh review.</p>}
    {notice && <div ref={status} tabIndex={-1} className={`ca-feedback ca-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><p>{notice.text}</p></div>}
    {(pending || result) && <div className="ca-operation"><Field path="operation-id" label="Operation ID" value={pending?.key || result.receipt.request_id} readOnly onChange={() => {}} /><p>Keep this ID before leaving. No operation details are stored in this browser. After reload, paste the ID below to check its recorded result. Checking never repeats a write.</p>
      {pending && <div className="ca-actions"><button type="button" disabled={busy} onClick={recover}>Check pending operation</button><button type="button" disabled={busy} onClick={() => send(pending)}>Retry same action</button></div>}</div>}
  </>;
  const publicationAction = <>
{eligible && <button className="wd-primary" type="button" disabled={disabled || !reason.trim()} onClick={() => {
        trigger.current = document.activeElement;
        setReviewOpen(false);
        setConfirmation({
          kind: bundle.basis.intent.action,
          bundle
        });
      }}>{bundle.basis.intent.action === 'replace' ? 'Replace reviewed offer' : 'Publish reviewed offer'}</button>}
  </>;
  return <section className="ca-lifecycle" aria-label="Offer lifecycle">
    <PublishedOffers perform={perform} busy={busy} disabled={blocked || Boolean(pending)} refreshKey={result?.current_catalog_revision} onOpen={openListedOffer}/>
    <div className="ca-lifecycle-title"><h2 tabIndex={-1} ref={heading}>Review and publication</h2><span className="ca-tag">Private catalog</span></div>
    <p>Publication records versioned catalog terms and requires server approval. If approval is unavailable, your draft stays private. Public pricing, checkout and customer access remain unavailable.</p>
    <fieldset className="ca-editable" disabled={disabled || locked}>
      <div className="ca-grid"><Field path="lifecycle-action" label="Publication action" value={action} options={[["publish", "Publish a first offer"], ["replace", "Replace current offer"]]} onChange={v => change(setAction, v)} />
        <Field path="lifecycle-from" label="Offer starts at (IST)" type="datetime-local" step="1" value={from} onChange={v => change(setFrom, v)} help="India Standard Time (Asia/Kolkata)." />
        <Field path="lifecycle-until" label="Offer ends at (IST, optional)" type="datetime-local" step="1" value={until} onChange={v => change(setUntil, v)} help="Leave blank unless this offer should expire." /></div>
    </fieldset>
    <Field path="lifecycle-reason" label="Lifecycle reason" value={reason} onChange={v => change(setReason, v)} maxLength={2000} disabled={disabled} help="Required for an intentional review, publication or retirement." />
    <div className="ca-actions"><button type="button" disabled={disabled || locked || !saved || dirty || !ready} onClick={prepareReview}>Review for publication</button>
      {!reviewOpen && publicationAction}</div>
    {(bundle || review || pending || notice) && <button type="button" style={reviewOpen ? {display:'none'} : undefined} onClick={() => setReviewOpen(true)}>Open subscription review</button>}
    {!ready && !locked && <p className="ca-muted">Save the draft and resolve all saved preview requirements before requesting review.</p>}
    {!reviewOpen && reviewFeedback}
    <div className="ca-grid ca-lifecycle-reads"><form onSubmit={e => {
        e.preventDefault();
        if (pending || blocked) return;
        const id = offerId.trim().toLowerCase();
        if (!isId(id)) {
          setNotice({
            kind: 'error',
            text: 'Enter a complete offer ID.'
          });
          return;
        }
        run(async (request, valid) => {
          const next = await loadOffer(request, id);
          if (valid()) {
            setOffer(next);
            setResult(null);
            setNotice(null);
            if (next.source) onCommitted(next.source.draft_id);
          }
        });
      }}><Field path="offer-id" label="Open an offer by ID" value={offerId} onChange={setOfferId} disabled={disabled} /><button type="submit" disabled={disabled}>Open offer</button></form>
      <form onSubmit={e => {
        e.preventDefault();
        if (!blocked) recover();
      }}><Field path="recovery-id" label="Check an operation by ID" value={recoveryId} onChange={setRecoveryId} disabled={disabled} /><button type="submit" disabled={busy || blocked || Boolean(pending)}>Check operation</button></form></div>
    {offer && <section className="ca-terminal" aria-label="Offer details"><h3>{offer.current.state === 'retired' ? 'Retired offer' : offer.current.state === 'visible' ? 'Published offer' : 'Hidden archive'} · version {offer.snapshot.version}</h3><p>Offer <code>{offer.snapshot.offer_version_id}</code>Availability revision {offer.current.revision}. {offer.current.state === 'retired' ? 'Removed from new offers. Historical terms remain; this does not cancel subscriptions or payments.' : 'Stored publication does not enable checkout or grant paid access.'}</p><Terms document={offer.snapshot} />
      <p>Offer starts {formatIst(offer.current.valid_from)}{offer.current.valid_until ? ` and ends ${formatIst(offer.current.valid_until)}` : '; no end scheduled'}.</p>
      <div className="ca-actions">{offer.current.state !== 'retired' && <button type="button" disabled={disabled || !reason.trim()} onClick={() => {
          trigger.current = document.activeElement;
          setConfirmation({
            kind: 'retire',
            offer
          });
        }}>Retire this offer</button>}
        {offer.source && <button type="button" disabled={disabled} onClick={() => onNewVersion(offer.source)}>Create a new draft version</button>}</div></section>}
    <SubscriptionReviewModal busy={busy} open={reviewOpen || Boolean(confirmation && confirmation.kind !== 'review')}
      onClose={() => { setReviewOpen(false); if (confirmation?.kind !== 'review') setConfirmation(null); }}
      title={!confirmation || confirmation.kind === 'review' ? 'Subscription review' : confirmation.kind === 'retire' ? 'Retire this offer?' : confirmation.kind === 'replace' ? 'Replace this offer?' : 'Publish this offer?'}
      identity={`${saved?.terms.name || offer?.snapshot.terms.name || 'Plan'} / saved revision ${saved?.revision || 'not loaded'}`}>
      {reviewOpen && <>{busy && <p role="status">Loading subscription review...</p>}{reviewFeedback}</>}
      {reviewOpen && !confirmation && bundle && <><Terms document={bundle.document}/>{publicationAction}</>}
      {confirmation && <><h3>{confirmation.kind === 'review' ? 'Confirm reviewed terms' : confirmation.kind === 'retire' ? 'Retire this offer?' : confirmation.kind === 'replace' ? 'Replace this offer?' : 'Publish this offer?'}</h3>
        <p id="ca-lifecycle-dialog-help">{confirmation.kind === 'review' ? `Reviewing saved draft revision ${confirmation.bundle.basis.revision} only. Publication needs a separate confirmation.` : confirmation.kind === 'retire' ? 'Remove this exact version from new offers. Historical subscriber terms remain. No payment or subscription cancellation.' : 'Create immutable versioned terms in the private catalog. Customer checkout and access remain unavailable.'}</p>
        {confirmation.bundle?.previous && <section aria-label="Existing offer"><h3>Existing offer · version {confirmation.bundle.previous.snapshot.version}</h3><code>{confirmation.bundle.previous.snapshot.offer_version_id}</code><Terms document={confirmation.bundle.previous.snapshot} /></section>}
        <section aria-label={confirmation.kind === 'retire' ? 'Retirement target' : 'Proposed terms'}>{confirmation.kind === 'retire' ? <><h3>Version {confirmation.offer.snapshot.version}</h3><code>{confirmation.offer.snapshot.offer_version_id}</code><Terms document={confirmation.offer.snapshot} /></> : <><p>Saved revision {confirmation.bundle.basis.revision}. Offer starts {formatIst(confirmation.bundle.basis.intent.valid_from)}{confirmation.bundle.basis.intent.valid_until ? ` and ends ${formatIst(confirmation.bundle.basis.intent.valid_until)}` : '; no end scheduled'}.</p><Terms document={confirmation.bundle.document} /></>}</section>
        <div className="ca-actions"><button type="button" data-cancel onClick={() => {setConfirmation(null);setReviewOpen(false);}}>Cancel</button><button className="wd-primary" type="button" disabled={busy} onClick={confirmAction}>{confirmation.kind === 'review' ? 'Confirm review' : confirmation.kind === 'retire' ? 'Confirm retirement' : confirmation.kind === 'replace' ? 'Confirm replacement' : 'Confirm publication'}</button></div></>}
    </SubscriptionReviewModal>
  </section>;
}
