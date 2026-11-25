import { BrowserRouter, Routes, Route } from 'react-router-dom';
import React from 'react';
import { WebsiteMounted } from '../../../src/auth/WebsiteRenderFailure.jsx';
import {createRoot} from 'react-dom/client';
import BillingCheckout from '../../../src/auth/BillingCheckout.jsx';
import CatalogPricing from '../../../src/landing/CatalogPricing.jsx';

const authClient = {auth:{
  getSession:async()=>({data:{session:window.syntheticSession}}),
  onAuthStateChange:callback=>{window.syntheticLogout=()=>callback('SIGNED_OUT',null);return {data:{subscription:{unsubscribe(){}}}};},
}};
createRoot(document.getElementById('root')).render(<BrowserRouter><WebsiteMounted><Routes><Route path="/auth/checkout" element={<BillingCheckout authClient={authClient}/>}/><Route path="*" element={<CatalogPricing/>}/></Routes></WebsiteMounted></BrowserRouter>);
