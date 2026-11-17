import { useEffect, useRef, useState } from 'react';

export default function AdminCampaigns({ items, perform, suspended = false }) {
  const [draft, setDraft] = useState(null), [preview, setPreview] = useState(null), [review, setReview] = useState(null);
  const [recipient, setRecipient] = useState(''), [status, setStatus] = useState(''), [pending, setPending] = useState(false);
  const opener = useRef(null);
  const dialog = useRef(null), locked = useRef(false), current = useRef(0);
  useEffect(() => () => { ++current.current; }, []);
  useEffect(() => { if (review && !suspended) dialog.current?.showModal(); else { dialog.current?.close(); if (!suspended) opener.current?.focus(); } }, [review, suspended]);
  async function run(action, document) {
    if (locked.current || suspended) return;
    locked.current = true; setPending(true); setStatus(''); const generation = current.current;
    try {
      const result = await perform(action, document);
      if (generation !== current.current) return;
      if (['save', 'read', 'preview'].includes(action)) { setDraft(result); setPreview(action === 'preview' ? result : null); }
      else if (action === 'audience') setReview({ ...result, operation_id: crypto.randomUUID() });
      else if (action === 'confirm') { setReview(null); setStatus('Send requested. Delivery is not yet confirmed. Refresh results to check progress.'); }
      else setStatus('Test requested for the reviewed eligible recipient. This is not delivery confirmation.');
    } catch { if (generation === current.current) setStatus('Outcome not confirmed. Check your authenticator, refresh status, or retry the same confirmation. No delivery success is assumed.'); }
    finally { locked.current = false; setPending(false); }
  }
  function edit(field, value) { setDraft({ ...draft, [field]: value }); setPreview(null); setReview(null); }
  return <section aria-label="Promotional campaign workspace">
    <p>Draft → Preview/test → Audience/count → Confirm send → Results. Only opted-in eligible customers may receive messages. All sends recheck eligibility.</p>
    <button disabled={pending} onClick={() => { setDraft({ campaign_id: crypto.randomUUID(), revision: '0', name: '', subject: '', body: '', state: 'draft' }); setPreview(null); setReview(null); }}>New campaign draft</button>
    <label>Existing campaign<select value="" disabled={pending} onChange={event => { const item = items.find(x => x.campaign_id === event.target.value); if (item) { setDraft(item); setPreview(null); setReview(null); } }}><option value="">Choose a campaign</option>{items.map(item => <option key={item.campaign_id} value={item.campaign_id}>{item.name} · {item.state}</option>)}</select></label>
    {draft && <>
      <form onSubmit={event => { event.preventDefault(); void run('save', { campaign_id: draft.campaign_id, revision: draft.revision, name: draft.name, subject: draft.subject, body: draft.body }); }}>
        <label>Campaign name<input required maxLength={120} value={draft.name} disabled={pending || draft.state !== 'draft'} onChange={e => edit('name', e.target.value)} /></label>
        <label>Email subject<input required maxLength={160} value={draft.subject} disabled={pending || draft.state !== 'draft'} onChange={e => edit('subject', e.target.value)} /></label>
        <label>Plain-text message<textarea required maxLength={10000} rows={8} value={draft.body} disabled={pending || draft.state !== 'draft'} onChange={e => edit('body', e.target.value)} /></label>
        <button disabled={pending || draft.state !== 'draft'}>Save draft</button>
      </form>
      <button disabled={pending || draft.revision === '0'} onClick={() => run('preview', { campaign_id: draft.campaign_id })}>Preview saved revision</button>
      {preview && <section aria-label="Campaign preview"><h3>{preview.subject}</h3><pre>{preview.body}</pre><p>Product-update opt-in notice and an individual unsubscribe link are appended at dispatch. Revision {preview.revision}.</p>
        <label>Eligible test customer UUID<input value={recipient} onChange={e => setRecipient(e.target.value)} /></label><button disabled={pending || !/^[0-9a-f-]{36}$/i.test(recipient)} onClick={() => run('test', { campaign_id: draft.campaign_id, target: recipient, operation_id: crypto.randomUUID() })}>Request controlled test</button>
        <button ref={opener} disabled={pending || draft.state !== 'draft'} onClick={() => run('audience', { campaign_id: draft.campaign_id })}>Review audience and count</button>
      </section>}
      <button disabled={pending || draft.revision === '0'} onClick={() => run('read', { campaign_id: draft.campaign_id })}>Refresh campaign results</button>
      <p role="status">Campaign state: {draft.state}. Provider acceptance and delivery are separate.</p>
      <p>Uncertain deliveries requiring reconciliation: {draft.reconciliation_required ?? 'Unavailable'}. Unknown outcomes are not successful delivery and are never blindly resent.</p><dl>{Object.entries(draft.results || {}).map(([kind, count]) => <div key={kind}><dt>{kind}</dt><dd>{count}</dd></div>)}</dl>
    </>}
    {status && <p role="status">{status}</p>}
    <dialog ref={dialog} aria-labelledby="campaign-confirm-title" onCancel={event => { event.preventDefault(); if (!pending) setReview(null); }}><h2 id="campaign-confirm-title">Confirm promotional campaign</h2>{review && <><p>{review.recipient_count} recipients were eligible as of {review.count_as_of}. Eligibility is rechecked at dispatch; the final count may decrease.</p><p>This sends the saved revision {review.revision}. Review expires {review.expires_at}.</p><button className="ac-dismiss" disabled={pending} onClick={() => setReview(null)}>Cancel</button><button disabled={pending} onClick={() => run('confirm', { review_id: review.review_id, operation_id: review.operation_id, confirm: true })}>{pending ? 'Checking outcome…' : 'Confirm campaign send'}</button></>}</dialog>
  </section>;
}
