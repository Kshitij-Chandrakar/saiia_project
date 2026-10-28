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
  return <section className="ca-published-offers" aria-label="Published offers">
    <div className="ca-published-heading"><div><h3>Published offers</h3><p>Currently visible offers from this environment. Open one or create an editable draft version without copying its ID.</p></div><button type="button" disabled={busy || disabled || requested} onClick={()=>setRequested(true)}>Refresh offers</button></div>
    <div aria-live="polite">
      {state.status==='loading' && <p>Loading published offers...</p>}
      {state.status==='unavailable' && <p>Published offers are unavailable. This environment's public catalog must be configured. You can still open a known offer by ID below.</p>}
      {state.status==='ready' && !state.offers.length && <p>No currently visible published offers in this environment.</p>}
      {state.status==='ready' && state.offers.length>0 && <ul>{state.offers.map(o=><li key={o.id}><div><strong>{o.name}</strong><span>Version {o.version} · Published</span><code>{o.id}</code></div><div className="ca-actions"><button type="button" disabled={busy || disabled} aria-label={`Open ${o.name} offer`} onClick={()=>onOpen(o.id,false)}>Open offer</button><button type="button" disabled={busy || disabled} aria-label={`Create draft version for ${o.name}`} onClick={()=>onOpen(o.id,true)}>Create draft version</button></div></li>)}</ul>}
    </div>
    <small>Scheduled, expired and retired versions are excluded here. Use Open an offer by ID for those versions. Import creates a separate plan candidate.</small>
  </section>;
}
