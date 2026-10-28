import { money } from './pricingMoney.js';
import { useEffect, useState } from 'react';
import { Check, X, UserRound, Zap, Crown, ArrowUpRight, MessageCircle, Network, FileText, Sparkles } from 'lucide-react';
import CatalogFeaturePresentation from '../auth/CatalogFeaturePresentation.jsx';
import './catalog-pricing.css';

const includes = (o,f) => o.entitlements.some(e => e.feature===f && e.allowed);
const allowance = (o,m) => o.allowances?.find(a => a.meter===m);
const period = a => a?.period ? ` / ${a.period.unit}` : '';
const quantity = (a,unit) => !a ? 'Not configured' : a.mode==='unlimited' ? `Unlimited ${unit}` : `${a.amount} ${unit}${period(a)}`;
function autoLabel(a) {
  if(!a) return 'Auto allowance not configured';
  if(a.mode==='unlimited') return 'Unlimited Auto Mode';
  const seconds=BigInt(a.amount);
  const value=seconds%3600n===0n ? `${seconds/3600n} hours` : seconds%60n===0n ? `${seconds/60n} min` : `${seconds} sec`;
  return `${value} Auto Mode${period(a)}`;
}
function clipboardInfo(a) {
  const saves=!a ? 'The save allowance is not configured.' : a.mode==='unlimited' ? 'This plan includes unlimited new saves.' : `This plan includes ${a.amount} new saves per ${a.period.unit}.`;
  return `Clipboard lets you paste and save your own answers, then open them during an interview. ${saves} Once saved, an answer cannot be edited or individually deleted. Reading existing answers does not consume saves.`;
}
export function SharedBenefits({offers}) {
  const all=fn => offers.length>0 && offers.every(fn);
  const unlimited=(o,m)=>allowance(o,m)?.mode==='unlimited';
  const items=[
    [MessageCircle,'Unlimited manual audio & AI answers',all(o=>includes(o,'audio.transcribe') && includes(o,'answers.generate') && unlimited(o,'audio.transcribed') && unlimited(o,'answers.completed'))],
    [Network,'All available AI models',all(o=>includes(o,'answers.generate')&&o.model_selection==='configured_supported_available')],
    [FileText,'History & transcript exports',all(o=>['sessions.history','transcripts.export'].every(f=>includes(o,f)&&o.unmetered_features?.includes(f)))],
    [Sparkles,'Unlimited AI Notes & Ask AI',all(o=>includes(o,'notes.generate')&&includes(o,'session.ask_ai')&&unlimited(o,'notes.generations')&&unlimited(o,'ask_ai.completed'))]
  ].filter(([, ,valid])=>valid);
  return items.length>0 && <section className="cp-shared" aria-label="Included in every plan"><h3>Included in every plan</h3>{items.map(([Icon,label])=><p key={label}><Icon size={18} aria-hidden="true"/><span>{label}{Icon===MessageCircle&&<span className="cp-shared-support">. Unlimited transcription included.</span>}</span></p>)}</section>;
}
export function CatalogPricingCards({offers,yearly,checkoutAvailable=false,checkoutPriceIds=[],payablePrices={}}) {
  return <><div className="cp-cards">{offers.map((o,index)=>{
    const free=o.pricing_mode==='free', month=o.prices.find(p=>p.billing.unit==='month'&&p.billing.count==='1'),year=o.prices.find(p=>p.billing.unit==='year'&&p.billing.count==='1');
    const price=yearly?year:month, quote=price?payablePrices[price.price_id]:null;
    const cap=o.storage_allowances?.find(a=>a.meter==='resume.stored_files')||o.limits.find(a=>a.meter==='resume.stored_files');
    const replacement=allowance(o,'resume.replacements'),clip=allowance(o,'clipboard.new_saves');
    const resume=cap?.mode==='unlimited'&&replacement?.mode==='unlimited' ? 'Unlimited resumes & replacements' : `${cap?.amount ?? 'Unconfigured'} resume${cap?.amount==='1'?'':'s'} \u00b7 ${quantity(replacement,'replacement'+(replacement?.amount==='1'?'':'s')).replace(' / ','/')}`;
    const presentation=feature=>o.presentation?.find(p=>p.feature===feature);
    const sketch=presentation('sketch.generate');
    const rows=[
      ['auto',includes(o,'assistant.auto'),autoLabel(allowance(o,'auto.authorized_running'))],
      ['resume',includes(o,'resume.upload'),resume],
      ['screen',includes(o,'screen.analyze'),quantity(allowance(o,'screen.analyses'),'screen analyses')],
      ['follow',includes(o,'screen.followups'),includes(o,'screen.followups')?'Screen follow-ups included':'Screen follow-ups excluded'],
      ['clipboard',includes(o,'clipboard.saved_answers'),quantity(clip,'Clipboard saves'),clipboardInfo(clip),'Clipboard'],
      ['sketch',includes(o,'sketch.generate'),sketch?.label||'Introducing Sketch',sketch?.information,sketch?.label||'Introducing Sketch']
    ];
    return <article className={`cp-card cp-accent-${index%3}`} key={o.offer_version_id} data-offer-id={o.offer_version_id} data-offer-version={o.version} aria-label={`${o.name} plan`}>
      <div className="cp-plan"><span className="cp-plan-mark" aria-hidden="true">{index%3===0?<UserRound size={26}/>:index%3===1?<Crown size={26}/>:<Zap size={26}/>}</span><h3>{o.name}</h3></div>
      <div className="cp-price"><div><strong>{free?'\u20b90':price?money(price):'Not available'}</strong></div>
      {free?<p>No payment required</p>:<><p className="cp-billing">per {yearly?'year':'month'} + 18% GST</p><p className="cp-payable">{quote?`Total: ${money({currency:quote.currency,exponent:quote.exponent,amount_minor:quote.total_amount_minor})}`:'Total temporarily unavailable'}</p></>}
      </div>
      {free?<a className="cp-cta" href="/auth/signup">Get started<ArrowUpRight size={17} aria-hidden="true"/></a>:checkoutAvailable&&price&&quote&&checkoutPriceIds.includes(price.price_id)?<a className="cp-cta" href={`/auth/checkout?offer=${encodeURIComponent(o.offer_version_id)}&price=${encodeURIComponent(price.price_id)}`}>Review purchase<ArrowUpRight size={17} aria-hidden="true"/></a>:<button className="cp-cta" disabled data-offer-id={o.offer_version_id} data-price-id={price?.price_id}>Checkout coming soon</button>}
      <ul className="cp-features">{rows.map(([key,allowed,label,information,infoLabel])=><li key={key} className={allowed?'':'cp-excluded'}>{allowed?<Check size={17} aria-hidden="true"/>:<X size={17} aria-hidden="true"/>}{information?<CatalogFeaturePresentation label={label} information={information} included={allowed} informationLabel={infoLabel}/>:<span>{key==='sketch'&&!allowed?<s>{label}</s>:label}</span>}</li>)}
      {o.service_benefits?.map(b=><li key={b.key}><Check size={17} aria-hidden="true"/><span>{b.label}{b.availability==='coming_soon'&&<> {'\u00b7'} <span>Coming soon</span></>}</span></li>)}</ul>
    </article>;
  })}</div><SharedBenefits offers={offers}/></>;
}
export default function CatalogPricing() {
  const [checkoutAvailable,setCheckoutAvailable] = useState(false);
  const [checkoutPriceIds,setCheckoutPriceIds] = useState([]);
  useEffect(() => {
    const control = new AbortController();
    fetch('/api/billing/availability',{cache:'no-store',signal:control.signal}).then(r=>r.ok?r.json():null).then(d=>{if(!control.signal.aborted){setCheckoutAvailable(d?.available===true);setCheckoutPriceIds(Array.isArray(d?.price_ids)?d.price_ids:[]);}}).catch(()=>{});
    return ()=>control.abort();
  },[]);
  const [state,setState] = useState({status:'loading',offers:[]}), [yearly,setYearly] = useState(false), [retry,setRetry] = useState(0);
  useEffect(() => {
    let disposed=false, control;
    async function load() {
      control?.abort();control=new AbortController();const active=control;
      const timer=setTimeout(() => active.abort(),10000);
      try {
        const response=await fetch('/api/catalog',{cache:'no-store',signal:active.signal});
        if (!response.ok) throw Error();
        const data=await response.json();
        if (!/^\d+$/.test(data.catalog_revision) || !Array.isArray(data.offers) || data.offers.some(o => !['catalog.v1','catalog.v2','catalog.v3'].includes(o.contract_version) || typeof o.name !== 'string' || !Array.isArray(o.prices) || o.purchasable !== false || o.checkout_state !== 'unavailable')) throw Error();
        if (!disposed && active===control) setState({status:'ready',offers:data.offers,revision:data.catalog_revision,payablePrices:data.payable_prices||{},isolatedDemo:response.headers.get('x-catalog-environment')==='isolated-demo'});
      } catch { if (!disposed && active===control) setState({status:'unavailable',offers:[]}); }
      finally {clearTimeout(timer);}
    }
    load();const refresh=() => {if (document.visibilityState !== 'hidden') load();};
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    const interval=setInterval(refresh,30000);
    return () => {disposed=true;control?.abort();clearInterval(interval);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};
  },[retry]);
  return <section className="catalog-pricing" aria-labelledby="catalog-pricing-title">
    <header><h2 id="catalog-pricing-title">Your next <span>opportunity</span> starts here.</h2><p>Choose the support that fits your preparation.</p></header>
    {state.isolatedDemo && <p role="note">Local test pricing — disposable local offers. Checkout is unavailable.</p>}
    <div className="cp-toggle" role="group" aria-label="Billing interval"><button type="button" aria-pressed={!yearly} onClick={() => setYearly(false)}>Monthly</button><button type="button" aria-pressed={yearly} onClick={() => setYearly(true)}>Yearly</button></div>
    {state.status==='loading' && <p className="cp-state" role="status">Loading published plans…</p>}
    {state.status==='unavailable' && <div className="cp-state" role="status"><p>Plans are temporarily unavailable.</p><button type="button" onClick={() => setRetry(n=>n+1)}>Try again</button></div>}
    {state.status==='ready' && (state.offers.length ? <CatalogPricingCards offers={state.offers} yearly={yearly} checkoutAvailable={checkoutAvailable} checkoutPriceIds={checkoutPriceIds} payablePrices={state.payablePrices} /> : <p className="cp-state" role="status">No published plans are available yet.</p>)}
    {state.offers.length>0 && <footer><p>Auto time includes silence. Daily reset: midnight IST.</p><details><summary>Allowance details</summary><p>Stopped time does not count; combined microphone/system audio counts once. Monthly allowances reset on your original signup day at midnight IST, using the last day of shorter months and restoring the original day afterwards. Annual billing does not change monthly allowances. No rollover. Clipboard resets retain your saved answers; reads do not consume saves. Individual answers cannot be edited or deleted. Operational safeguards still apply.</p></details></footer>}
  </section>;
}
