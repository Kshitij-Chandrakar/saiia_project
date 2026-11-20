import {useEffect,useRef,useState} from 'react';
import {isId} from './catalogLifecycle.js';

// Discover through the same backend's existing public projection. Opening or
// editing still uses its protected, integrity-checked offer read; no new API.
export default function PublishedOffers({perform,busy,disabled,refreshKey,onOpen}) {
  const [state,setState]=useState({status:'loading',offers:[]});
  const [requested,setRequested]=useState(true);
  const sequence=useRef(0),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;++sequence.current;};},[]);
  useEffect(()=>{if(refreshKey)setRequested(true);},[refreshKey]);
  useEffect(()=>{
    if(!requested || busy || disabled)return;
    // Start after the committed mount. StrictMode's discarded effect must not
    // reserve the parent workspace's single in-flight operation slot.
    let cancelled=false;
    queueMicrotask(()=>{
    if(cancelled)return;
    setRequested(false);setState({status:'loading',offers:[]});
    const own=++sequence.current;
    perform(async(request,current)=>{
      const valid=()=>current() && mounted.current && own===sequence.current;
      try {
        const data=await request('/api/catalog');
        if(!/^\d+$/.test(data.catalog_revision) || !Array.isArray(data.offers) || data.offers.some(o=>!isId(o.offer_version_id) || typeof o.name!=='string' || !o.name.trim() || o.name.length>2000 || !/^[1-9]\d*$/.test(o.version)) || new Set(data.offers.map(o=>o.offer_version_id)).size!==data.offers.length)throw Error('Invalid catalog');
        if(valid())setState({status:'ready',offers:data.offers.map(o=>({id:o.offer_version_id,name:o.name,version:o.version}))});
      }catch(error){
        if(['unauthenticated','catalog_permission_denied'].includes(error.code))throw error;
        if(valid())setState({status:'unavailable',offers:[]});
      }
    });
    });
    return ()=>{cancelled=true;};
  },[requested,busy,disabled,perform]);
  return <section className="ca-published-offers" aria-label="Published plans">
    <div className="ca-published-heading"><div><h3>Published plans</h3><p>View a currently offered plan or start an updated version.</p></div><button type="button" disabled={busy || disabled || requested} onClick={()=>setRequested(true)}>Refresh plans</button></div>
    <div aria-live="polite">
      {state.status==='loading' && <p>Loading published plans...</p>}
      {state.status==='unavailable' && <p>Published plans are unavailable. Try refreshing, or open a known plan version under Troubleshooting.</p>}
      {state.status==='ready' && !state.offers.length && <p>No currently visible published plans in this environment.</p>}
      {state.status==='ready' && state.offers.length>0 && <ul>{state.offers.map(o=><li key={o.id}><div><strong>{o.name}</strong><span>Version {o.version} · Published</span><details><summary>Plan reference</summary><code>{o.id}</code></details></div><div className="ca-actions"><button type="button" disabled={busy || disabled} aria-label={`View ${o.name} plan`} onClick={()=>onOpen(o.id,false)}>View plan</button><button type="button" disabled={busy || disabled} aria-label={`Create updated version for ${o.name}`} onClick={()=>onOpen(o.id,true)}>Create updated version</button></div></li>)}</ul>}
    </div>
    <details className="ca-list-help"><summary>Which plans appear here?</summary><p>Only currently visible versions are listed. Scheduled, expired and stopped versions can be opened by ID under Troubleshooting.</p></details>
  </section>;
}
