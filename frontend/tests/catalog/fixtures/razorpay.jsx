import { BrowserRouter, Routes, Route } from 'react-router-dom';
import React from 'react';
import {createRoot} from 'react-dom/client';
import BillingCheckout from '../../../src/auth/BillingCheckout.jsx';
import CatalogPricing from '../../../src/landing/CatalogPricing.jsx';

const index=new URLSearchParams(location.search).get('case')||'0';
const data=await fetch('/__c12/session?case='+encodeURIComponent(index),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Isolated session unavailable');return r.json();});
const authClient={auth:{getSession:async()=>({data:{session:data.session}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};
if(location.pathname==='/auth/checkout')history.replaceState(null,'',`/auth/checkout?case=${encodeURIComponent(index)}&offer=${encodeURIComponent(data.offer)}&price=${encodeURIComponent(data.price)}`);
createRoot(document.getElementById('root')).render(<BrowserRouter><Routes><Route path="/auth/checkout" element={<BillingCheckout authClient={authClient}/>}/><Route path="*" element={<><p>Isolated Razorpay Test Mode. Synthetic local authentication; actual provider checkout. No real cards.</p><nav aria-label="Acceptance cases">{Array.from({length:8},(_,i)=><a style={{marginRight:12}} key={i} href={'/auth/checkout?case='+i}>Case {i+1}</a>)}</nav><CatalogPricing/></>}/></Routes></BrowserRouter>);
