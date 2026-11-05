import React from 'react';
import {createRoot} from 'react-dom/client';
import BillingCheckout from '../../../src/auth/BillingCheckout.jsx';
import CatalogPricing from '../../../src/landing/CatalogPricing.jsx';

const authClient = {auth:{
  getSession:async()=>({data:{session:window.syntheticSession}}),
  onAuthStateChange:callback=>{window.syntheticLogout=()=>callback('SIGNED_OUT',null);return {data:{subscription:{unsubscribe(){}}}};},
}};
createRoot(document.getElementById('root')).render(window.location.pathname==='/auth/checkout'?<BillingCheckout authClient={authClient}/>:<CatalogPricing/>);
