import { useEffect, useRef, useState } from 'react';
import { supabase } from './supabaseClient';
import { money } from '../landing/pricingMoney.js';
import '../landing/catalog-pricing.css';
import './billing-checkout.css';
import WebsiteProgress from './WebsiteProgress';

const labels = {
  prepared: 'Review your purchase', creating: 'Preparing secure checkout',
  uncertain: 'Checkout is being recovered. Please do not start another payment.',
  ready: 'Ready for checkout', confirmed: 'Payment confirmed. Your account plan has been updated.',
  expired: 'Payment recorded. This paid access period has ended.',
  pending: 'Payment verification pending. Paid access starts only after a verified subscription charge.',
};
let checkoutScript;
function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (!checkoutScript) checkoutScript = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = resolve;
    script.onerror = () => { checkoutScript = null; script.remove(); reject(Error()); };
    document.head.append(script);
  });
  return checkoutScript;
}

export default function BillingCheckout({backendUrl = '', authClient = supabase}) {
  const [session,setSession] = useState(null), [loaded,setLoaded] = useState(false);
  const [operation,setOperation] = useState(null), [busy,setBusy] = useState(false), [message,setMessage] = useState('');
  const [consent,setConsent] = useState(false);
  const [accountPlan,setAccountPlan] = useState(null);
  const [restoring,setRestoring] = useState(false), [restoreIssue,setRestoreIssue] = useState(false);
  const recoveryRead = useRef(null), readSequence = useRef(0);
  const generation = useRef(0), checkout = useRef(null), pending = useRef(false);
  useEffect(() => {
    let active = true, previousAccount;
    const epoch = generation;
    const recoveryEpoch = readSequence;
    const changed = value => {
      if (!value && previousAccount) sessionStorage.removeItem('billing.operation.'+previousAccount);
      previousAccount = value?.user.id;
      setConsent(false);
      setAccountPlan(null);
      generation.current++;
      recoveryRead.current?.abort(); recoveryRead.current = null; readSequence.current++;
      setRestoring(false); setRestoreIssue(false);
      checkout.current?.close(); checkout.current = null;
      pending.current = false;
      setSession(value); setLoaded(true); setOperation(null); setMessage(''); setBusy(false);
    };
    const initialEpoch = generation.current;
    authClient?.auth.getSession().then(({data}) => {if(active&&generation.current===initialEpoch) changed(data.session);});
    const listener = authClient?.auth.onAuthStateChange((_event,value) => {if(active) changed(value);});
    if (!authClient) setLoaded(true);
    return () => {active=false; epoch.current++; recoveryRead.current?.abort(); recoveryEpoch.current++; checkout.current?.close(); listener?.data.subscription.unsubscribe();};
  },[authClient]);

  useEffect(() => {
    if (!session) return;
    const control = new AbortController(), current = generation.current;
    const timer = setTimeout(()=>{control.abort();if(current===generation.current){setRestoreIssue(true);setMessage('We stopped waiting for checkout details. This does not confirm whether a payment completed.');}},12000);
    const params = new URLSearchParams(window.location.search);
    const storageKey = 'billing.operation.'+session.user.id;
    const saved = sessionStorage.getItem(storageKey);
    async function restore() {
      try {
        let response;
        response = await fetch(`${backendUrl}/api/billing/${saved?`status?operation_id=${encodeURIComponent(saved)}`:'current'}`,{headers:{Authorization:`Bearer ${session.access_token}`},cache:'no-store',signal:control.signal});
        if (!response.ok) throw Error(response.status===409?'terms':'unavailable');
        const existing = await response.json();
        if (existing && (existing.state!=='expired'||!params.get('offer'))) {
          if(current===generation.current&&!control.signal.aborted) {sessionStorage.setItem(storageKey,existing.operation_id);setOperation(existing);}
          return;
        }
        response = await fetch(`${backendUrl}/api/billing/checkout`,{method:'POST',headers:{Authorization:`Bearer ${session.access_token}`,'Content-Type':'application/json'},
          body:JSON.stringify({operation_id:crypto.randomUUID(),offer_version_id:params.get('offer'),price_id:params.get('price')}),signal:control.signal});
        if (!response.ok) throw Error(response.status===409?'terms':'unavailable');
        const data = await response.json();
        if (current===generation.current && !control.signal.aborted) {
          sessionStorage.setItem(storageKey,data.operation_id); setOperation(data);
        }
      } catch (error) {if(current===generation.current && !control.signal.aborted){setRestoreIssue(true);setMessage(error.message==='terms'?'This offer or its payable terms are no longer available. Return to pricing to review available plans.':'Checkout details are unavailable. Your payment status has not been confirmed.');}}
      finally {clearTimeout(timer);}
    }
    restore();
    return () => {clearTimeout(timer);control.abort();};
  },[session,backendUrl]);

  useEffect(()=>{
    if(!session||operation?.state!=='confirmed') return;
    const control=new AbortController(),current=generation.current;
    const timer=setTimeout(()=>control.abort(),12000);
    fetch(`${backendUrl}/api/account/subscription`,{headers:{Authorization:`Bearer ${session.access_token}`},cache:'no-store',signal:control.signal})
      .then(r=>{if(!r.ok)throw Error();return r.json();})
      .then(data=>{if(current===generation.current&&!control.signal.aborted)setAccountPlan(typeof data?.plan?.name==='string'?data.plan.name:null);})
      .catch(()=>{if(current===generation.current)setAccountPlan('');}).finally(()=>clearTimeout(timer));
    return ()=>{clearTimeout(timer);control.abort();};
  },[session,backendUrl,operation?.state,operation?.operation_id]);

  async function request(action, data) {
    const control = new AbortController(), timer = setTimeout(()=>control.abort(),12000);
    try {
      const response = await fetch(`${backendUrl}/api/billing/${action}`,{
        method:data?'POST':'GET',cache:'no-store',headers:{Authorization:`Bearer ${session.access_token}`,'Content-Type':'application/json'},
        body:data?JSON.stringify(data):undefined,signal:control.signal});
      if (!response.ok) throw Error();
      return await response.json();
    } finally {clearTimeout(timer);}
  }
  async function refresh() {
    if (recoveryRead.current || !session) return;
    const control = new AbortController(), sequence = ++readSequence.current;
    recoveryRead.current = control; setRestoring(true); setMessage('Checking your existing checkout. No new payment will be started.');
    const timer = setTimeout(()=>control.abort(),12000);
    const current = generation.current;
    try {
      const saved = operation?.operation_id || sessionStorage.getItem('billing.operation.'+session.user.id);
      const response = await fetch(`${backendUrl}/api/billing/${saved?`status?operation_id=${encodeURIComponent(saved)}`:'current'}`,{headers:{Authorization:`Bearer ${session.access_token}`},cache:'no-store',signal:control.signal});
      if (!response.ok) throw Error();
      const result = await response.json();
      if (current===generation.current && sequence===readSequence.current && !control.signal.aborted) {
        if (result?.operation_id) {sessionStorage.setItem('billing.operation.'+session.user.id,result.operation_id);setOperation(result);setRestoreIssue(false);setMessage('');}
        else {setRestoreIssue(true);setMessage('No existing checkout was found for this account. Return to pricing to review your options.');}
      }
    } catch {if(current===generation.current && sequence===readSequence.current) {setRestoreIssue(true);setMessage('Checkout status is still unconfirmed. You can check again. Do not start another payment while its status is uncertain.');}}
    finally {clearTimeout(timer);if(current===generation.current && sequence===readSequence.current) {recoveryRead.current=null;setRestoring(false);}}
  }
  async function pay() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setMessage('');
    const current = generation.current;
    try {
      const result = await request('start',{operation_id:operation.operation_id,consent,quote_id:operation.quote_id||'legacy.accepted'});
      if (current!==generation.current) return;
      setOperation(result);
      if (result.state!=='ready') return;
      await loadCheckout();
      if (current!==generation.current) return;
      checkout.current = new window.Razorpay({key:result.key_id,subscription_id:result.provider_id,name:'Intervucopilot',
        handler: async proof => {
          if (current!==generation.current) return;
          setMessage('Payment received by checkout. Verifying your payment…');
          try {
            const verified = await request('verify',{operation_id:result.operation_id,...proof});
            if(current===generation.current) {setOperation(verified);setMessage('');}
          } catch {if(current===generation.current) setMessage('Payment verification is pending. Use Check payment status to recover it.');}
        },
        modal:{ondismiss:()=>{if(current===generation.current) setMessage('Checkout closed. Your payment status can still be checked below.');}},
      });
      checkout.current.on('payment.failed',()=>{if(current===generation.current) setMessage('Payment failed. Paid access has not been confirmed. Check status before trying again.');});
      checkout.current.open();
    } catch {if(current===generation.current) setMessage('Checkout is unavailable. Check payment status before trying again.');}
    finally {if(current===generation.current) {pending.current=false;setBusy(false);}}
  }

  return <main className="catalog-pricing billing-checkout"><a href="/#pricing">Back to pricing</a><h1>Secure checkout</h1>
    {!loaded?<p role="status">Loading your account…</p>:!session?<p><a href="/auth/login">Sign in to review your purchase</a>, then return to pricing to select your plan.</p>:<>
      {operation&&<><h2>{operation.name}</h2><dl>{operation.payable&&<><dt>Base price</dt><dd>{money({currency:operation.currency,exponent:'2',amount_minor:operation.payable.base_amount_minor})}</dd><dt>GST (18%)</dt><dd>{money({currency:operation.currency,exponent:'2',amount_minor:operation.payable.tax_amount_minor})}</dd></>}<dt>Recurring total</dt><dd>{money({...operation,exponent:'2'})}</dd><dt>Billing interval</dt><dd>Every {operation.interval}</dd><dt>Maximum term</dt><dd>{operation.total_count} billing cycles</dd></dl>
        <p>Renews automatically every {operation.interval} for up to {operation.total_count} charges of {money({...operation,exponent:'2'})}. Cancel renewal to stop future charges. Paid access continues through the verified paid-period end. Fresh consent is required after the final cycle; otherwise your account returns to Free.</p>
        <p>Monthly allowances follow your signup anniversary, including on yearly purchases.</p><p role="status">{labels[operation.state]||'Payment verification pending'}</p>
        {operation.state==='confirmed'&&<p role="status">{accountPlan?`Current account plan: ${accountPlan}`:accountPlan===null?'Refreshing authoritative account access…':'Current account access is temporarily unavailable. Open your account to retry.'}</p>}
        {!operation.review_required&&['prepared','ready'].includes(operation.state)&&<><label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I agree to the recurring amount, interval and maximum term shown above.</label><button className="cp-cta" onClick={pay} disabled={busy||!consent}>{busy?'Opening checkout…':'Accept terms and pay'}</button></>}
        {operation.review_required&&<><p>GST pricing has changed. Review the updated total and give fresh consent before checkout.</p><button onClick={async()=>{const epoch=generation.current;try{const data=await request('checkout',{operation_id:crypto.randomUUID(),offer_version_id:operation.offer_version_id,price_id:operation.price_id});if(epoch===generation.current){setConsent(false);sessionStorage.setItem('billing.operation.'+session.user.id,data.operation_id);setOperation(data);}}catch{if(epoch===generation.current)setMessage('Updated terms are unavailable. Please return to pricing.');}}}>Review updated terms</button></>}
        {operation.state==='confirmed'&&!operation.cancel_requested&&<button onClick={async()=>{const epoch=generation.current;try{const data=await request('cancel',{operation_id:operation.operation_id,confirm:true});if(epoch===generation.current)setOperation(data);}catch{if(epoch===generation.current)setMessage('Cancellation status is pending. Check payment status before retrying.');}}}>Cancel future renewal</button>}
        {operation.cancel_requested&&<p>Renewal cancellation requested. Provider status: {operation.provider_state}. Paid access ends at the verified paid-period end.</p>}
        <button onClick={refresh} disabled={busy||restoring}>Check payment status</button>
        {operation.state==='confirmed'&&<a href="/auth/dashboard">View your account</a>}
      </>}
      {!operation && (restoreIssue || restoring) ? <WebsiteProgress pending={restoring} title={restoring?'Checking your checkout':'Checkout status is not confirmed'} message={message}>
        <button type="button" onClick={refresh} disabled={restoring}>{restoring?'Checking existing checkout…':'Recover existing checkout'}</button>
      </WebsiteProgress> : <p role="status">{message||(!operation?'Loading accepted terms…':'')}</p>}
    </>}
  </main>;
}
