import {useCallback, useEffect, useRef, useState} from 'react';
import {supabase} from './supabaseClient';
import {money} from '../landing/pricingMoney.js';
import './billing-checkout.css';
import './billing-admin.css';
const notificationNames = {billing_payment:'Payment confirmation',billing_renewal:'Renewal confirmation',billing_cancellation:'Cancellation confirmation',billing_access_end:'Paid access ended'};
const actionNames = {reconcile:'Reconciliation',retry_notification:'Notification retry'};

export default function BillingAdmin({backendUrl = '', client = supabase}) {
  const session = useRef(null), generation = useRef(0);
  const [access, setAccess] = useState(null), [account, setAccount] = useState('');
  const [data, setData] = useState(null), [review, setReview] = useState(null);
  const [message, setMessage] = useState('Loading billing permissions…');
  const [busy, setBusy] = useState(false);
  const request = useCallback(async (target, document) => {
    const response = await fetch(`${backendUrl}/api/admin/billing/${encodeURIComponent(target)}`, {
      method: document ? 'POST' : 'GET', cache: 'no-store', signal: AbortSignal.timeout(12000),
      headers: {Authorization: `Bearer ${session.current?.access_token}`, ...(document ? {'Content-Type': 'application/json'} : {})},
      ...(document ? {body: JSON.stringify(document)} : {})
    });
    if (!response.ok) throw Error(response.status === 403 ? 'Billing permission denied.' : response.status === 409 ? 'State changed or action unavailable. Inspect again.' : 'Billing service unavailable.');
    return response.json();
  }, [backendUrl]);
  useEffect(() => {
    let alive = true;
    const epoch = generation;
    async function update(next) {
      const ticket = ++generation.current;
      session.current = next; setData(null); setReview(null); setAccess(null); setAccount(''); setBusy(false);
      if (!next) {setMessage('Sign in to use billing administration.'); return;}
      try {
        const result = await request('access');
        if (alive && ticket === generation.current) {setAccess(result); setMessage(result.read ? '' : 'Billing permission denied.');}
      } catch (error) {if (alive && ticket === generation.current) setMessage(error.message);}
    }
    const subscription = client.auth.onAuthStateChange((_event, next) => {void update(next);}).data.subscription;
    const ticket = generation.current;
    void client.auth.getSession().then(({data: result}) => {if (alive && ticket === generation.current) void update(result.session);});
    return () => {alive = false; epoch.current++; session.current = null; subscription.unsubscribe();};
  }, [client, request]);
  async function act(work) {
    if (busy) return;
    const ticket = generation.current;
    setBusy(true); setMessage('');
    try {await work(ticket);} catch (error) {if (ticket === generation.current) setMessage(error.message);}
    finally {if (ticket === generation.current) setBusy(false);}
  }
  async function inspect() {
    await act(async ticket => {
      const result = await request(account);
      if (ticket === generation.current) {setData(result); setReview(null);}
    });
  }
  async function prepare(action, target) {
    await act(async ticket => {
      const result = await request(account, {review: true, action, target, operation_id: crypto.randomUUID()});
      if (ticket === generation.current) setReview({...result, account});
    });
  }
  return <main className="catalog-pricing billing-checkout billing-admin"><h1>Billing administration</h1><p>Inspect recorded billing state. Inspection does not contact the payment provider.</p>
    <p role="status">{message}</p>{access?.read && <>
      <label>Account ID <input value={account} onChange={event => {generation.current++; setBusy(false); setAccount(event.target.value); setData(null); setReview(null);}} /></label>
      <button disabled={busy || !/^[a-f0-9-]{36}$/.test(account)} onClick={inspect}>Inspect billing</button>
      {data && <><h2>Payments and reconciliation</h2>{data.operations.map(operation => <section key={operation.id}><p>{operation.id} · {money({...operation,exponent:'2'})} · {operation.state}</p><p>Provider: {operation.provider_state || 'unknown'}. Cancellation: {operation.cancellation_state === 'confirmed' ? 'confirmed by provider' : operation.cancel_requested ? 'request recorded; confirmation unknown unless provider evidence confirms' : 'none requested'}.</p>{access.manage && <button disabled={busy} onClick={() => prepare('reconcile', operation.id)}>Review reconciliation request</button>}</section>)}
        <h2>Notifications</h2><p>Accepted means accepted by the email provider. Delivered means the recipient mail server accepted the message; it does not establish inbox placement or reading.</p>{data.notifications.map(notification => <section key={notification.id}><p>{notificationNames[notification.kind] || notification.kind} · {notification.state === 'dry_run' ? 'simulated; no email sent' : notification.state} · attempts {notification.attempts}/3</p>{notification.delivery_events?.map((event, index) => <p key={index}>{event.type}; provider event {event.provider_event_at}; processed {event.processed_at || 'pending'}{event.failure_category ? `; failure: ${event.failure_category}` : ''}</p>)}{access.manage && notification.retryable && <button disabled={busy} onClick={() => prepare('retry_notification', notification.id)}>Review notification retry</button>}</section>)}
        <h2>Requested operations</h2>{data.commands.map(command => <p key={command.id}>{actionNames[command.action] || command.action} · {command.state}</p>)}
      </>}
      {review && <section role="dialog" aria-label="Confirm billing operation"><h2>Confirm billing operation</h2><p>Action: {actionNames[review.action]}</p><p>Account: {review.account}</p><p>Target: {review.target}</p><p>This approval is bound to the displayed target and current recorded state, and expires after five minutes.</p>
        <button disabled={busy} onClick={() => act(async ticket => {
          const {account: targetAccount, ...document} = review;
          const result = await request(targetAccount, {...document, confirm: true});
          if (ticket === generation.current) {setMessage(`Operation ${result.state}. Inspect again for progress.`); setReview(null);}
        })}>Confirm request</button><button disabled={busy} onClick={() => setReview(null)}>Back</button></section>}
      <p>Refunds, discounts, upgrade charges and paid-plan overrides are unavailable. Cancellation actions remain on the existing customer flow; unresolved provider cancellations need evidence review.</p>
    </>}
  </main>;
}
