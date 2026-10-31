import {useEffect,useId,useRef} from 'react';
import {X} from 'lucide-react';

// Native modal/inert behavior and scroll restoration match WebsiteSessionViewer.
// Closing controls presentation only; callers retain requests and retry state.
export default function SubscriptionReviewModal({open,onClose,title='Subscription review',identity,busy=false,children}) {
  const dialog=useRef(null),close=useRef(null),dismiss=useRef(onClose),restore=useRef(null),id=useId();
  dismiss.current=onClose;
  useEffect(()=>{
    if(!open)return;
    const node=dialog.current,trigger=document.activeElement,body=document.body,root=document.documentElement;
    restore.current=trigger;
    const overflow=body.style.overflow,rootOverflow=root.style.overflow,padding=body.style.paddingRight;
    const x=window.scrollX,y=window.scrollY,gutter=innerWidth-root.clientWidth;
    node.showModal();close.current.focus({preventScroll:true});
    body.style.overflow='hidden';root.style.overflow='hidden';
    if(gutter)body.style.paddingRight=`${gutter}px`;
    return ()=>{
      node.close();body.style.overflow=overflow;root.style.overflow=rootOverflow;body.style.paddingRight=padding;
      window.scrollTo({left:x,top:y,behavior:'instant'});
      if(trigger?.isConnected && !trigger.disabled){trigger.focus({preventScroll:true});restore.current=null;}
    };
  },[open]);
  useEffect(()=>{
    if(!open && !busy && restore.current?.isConnected && !restore.current.disabled){restore.current.focus({preventScroll:true});restore.current=null;}
  },[open,busy]);
  useEffect(()=>{
    if(open)dialog.current?.querySelector('[data-cancel]')?.focus({preventScroll:true});
  },[open,title]);
  return <dialog ref={dialog} className="ca-subscription-modal" aria-modal="true" aria-labelledby={id} onCancel={event=>{event.preventDefault();dismiss.current();}} onKeyDown={event=>{
    if(event.key!=='Tab')return;
    const controls=[...dialog.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex]:not([tabindex="-1"])')].filter(node=>node.getClientRects().length);
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
  }}>
    <header className="ca-subscription-modal-header"><div><h2 id={id}>{title}</h2>{identity&&<p>{identity}</p>}</div><button ref={close} type="button" aria-label="Close subscription review" onClick={onClose}><X size={20} aria-hidden="true"/></button></header>
    <div className="ca-subscription-modal-body" tabIndex={0}>{children}</div>
  </dialog>;
}
