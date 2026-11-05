import React from 'react';
import {createRoot} from 'react-dom/client';
import BillingAdmin from '../../../src/auth/BillingAdmin.jsx';
let listener;
const session={user:{id:'10000000-0000-4000-8000-000000000001'},access_token:'synthetic-ui-only'};
const client={auth:{getSession:async()=>({data:{session}}),onAuthStateChange(callback){listener=callback;return {data:{subscription:{unsubscribe(){}}}};}}};
window.syntheticBillingLogout=()=>listener('SIGNED_OUT',null);
createRoot(document.getElementById('root')).render(<BillingAdmin client={client}/>);
