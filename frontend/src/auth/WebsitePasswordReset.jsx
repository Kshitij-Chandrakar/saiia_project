import { useEffect, useRef, useState } from 'react'

import { useNavigate } from 'react-router-dom'

import WebsiteLogin from './WebsiteLogin'

import { createWebsiteRecoveryClient } from './supabaseRecoveryClient'

import { createRecoveryFlow, requestResetLink, resetSecondsRemaining, maskResetEmail } from './passwordRecovery'

import back from '../assets/password-reset/stage-1-asset-0.svg'

import lock from '../assets/password-reset/stage-1-asset-1.svg'

import envelope from '../assets/password-reset/stage-2-asset-2.svg'

import envelopeCheck from '../assets/password-reset/stage-2-asset-1.svg'
import envelopeTick from '../assets/password-reset/stage-2-asset-3.svg'

import eye from '../assets/password-reset/stage-3-asset-1.svg'

import info from '../assets/password-reset/stage-3-asset-2.svg'

import check from '../assets/password-reset/stage-4-asset-0.svg'

import './password-reset.css'



function PasswordField({label,id,value,setValue,disabled,error,helper}) {

 const [visible,setVisible]=useState(false)

 return <div className="reset-field"><label htmlFor={id}>{label}</label><span className="reset-password-input"><input id={id} type={visible?'text':'password'} autoComplete="new-password" required minLength={6} value={value} disabled={disabled} onChange={e=>setValue(e.target.value)} aria-invalid={Boolean(error)} aria-describedby={error?'reset-error':helper?'reset-policy':undefined}/><button type="button" aria-label={`${visible?'Hide':'Show'} ${label.toLowerCase()}`} aria-pressed={visible} disabled={disabled} onClick={()=>setVisible(v=>!v)}><img src={eye} alt=""/></button></span>{helper&&<small id="reset-policy"><img src={info} alt=""/>At least 6 characters. Your account’s password policy also applies.</small>}</div>

}



export function PasswordResetDialog({initialStage='request',onClose}) {

 const triggerRef=useRef(null)

 const dialog=useRef(null),flow=useRef(null),client=useRef(null),operation=useRef(null),lease=useRef(0),busyRef=useRef(false),alive=useRef(true)

 const [stage,setStage]=useState(initialStage==='verify'?'verifying':'request')

 const [email,setEmail]=useState(''),[masked,setMasked]=useState(''),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState('')

 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[seconds,setSeconds]=useState(resetSecondsRemaining),[updated,setUpdated]=useState(false)

 const title={request:'Forgot your password?',sent:'Reset link sent!',verifying:'Checking your reset link…',new:'Create new password',success:'Password reset successful!',unavailable:'Reset link unavailable',cleanup:'Finish secure sign-out'}[stage]

 useEffect(()=>{

  const current=++lease.current;alive.current=true

  if(!triggerRef.current)triggerRef.current=document.activeElement

  const root=document.documentElement,body=document.body

  const overflow=body.style.overflow,padding=body.style.paddingRight,gutter=window.innerWidth-root.clientWidth

  body.style.overflow='hidden';if(gutter)body.style.paddingRight=`${gutter}px`

  const dialogElement=dialog.current
  if(!dialogElement.open)dialogElement.showModal()

  if(!client.current){client.current=createWebsiteRecoveryClient();if(client.current)flow.current=createRecoveryFlow(client.current)}

  let active=true

  if(initialStage==='verify'){

   if(!operation.current){

    const search=window.location.search

    // This marker controls presentation on refresh, never authorization.

    window.history.replaceState({...window.history.state,websiteRecovery:true},'',window.location.pathname)

    operation.current=flow.current?flow.current.verify(search):Promise.resolve({status:'error'})

   }

   operation.current.then(result=>{if(active){setStage(result.status==='recovery'?'new':'unavailable');if(result.status!=='recovery')setError('This reset link is missing, expired, invalid, or already used. Request a fresh link.')}})

  }

  const interval=setInterval(()=>{if(active)setSeconds(resetSecondsRemaining())},1000)

  const sync=()=>setSeconds(resetSecondsRemaining());window.addEventListener('storage',sync)

  return ()=>{

   active=false;alive.current=false;clearInterval(interval);window.removeEventListener('storage',sync)

   dialogElement?.close();body.style.overflow=overflow;body.style.paddingRight=padding



   // StrictMode's immediate effect replay takes a new lease before this runs.

   queueMicrotask(()=>{if(lease.current===current){if(triggerRef.current?.isConnected)triggerRef.current.focus();void flow.current?.dispose().catch(()=>{})}})

  }

 },[initialStage])

 async function close(){

  if(busyRef.current || stage==='verifying'){setError('Please wait for this operation to finish before leaving.');return}

  busyRef.current=true;setBusy(true);setError('');setPassword('');setConfirmation('')

  try{await flow.current?.dispose();if(alive.current)onClose()}

  catch{if(alive.current){setStage('cleanup');setError(updated?'Your password was updated, but secure sign-out could not finish. Please retry.':'Secure sign-out could not finish. Please retry before leaving.')}}

  finally{busyRef.current=false;if(alive.current)setBusy(false)}

 }

 async function send(event){

  event?.preventDefault();if(busyRef.current || seconds)return

  if(!client.current){setError('Password reset is not configured for this build.');return}

  busyRef.current=true;setBusy(true);setError('')

  const submitted=email.trim()

  try{const result=await requestResetLink(client.current,submitted,window.location.origin);if(alive.current){setSeconds(resetSecondsRemaining());if(result.ok){setMasked(maskResetEmail(submitted));setStage('sent')}else setError(result.message)}}

  finally{busyRef.current=false;if(alive.current)setBusy(false)}

 }

 async function update(event){

  event.preventDefault();if(busyRef.current || stage!=='new')return

  if(password!==confirmation){setError('Passwords do not match.');return}

  busyRef.current=true;setBusy(true);setError('')

  try{

   const result=await flow.current.update(password)

   if(!alive.current)return

   if(!result.ok){setError(result.message);if(result.uncertain){setPassword('');setConfirmation('');setStage('unavailable')}return}

   setPassword('');setConfirmation('');setUpdated(true)

   try{await flow.current.dispose();if(alive.current)setStage('success')}

   catch{if(alive.current){setStage('cleanup');setError('Your password was updated, but secure sign-out could not finish. Please retry.')}}

  }finally{busyRef.current=false;if(alive.current)setBusy(false)}

 }

 async function retryCleanup(){

  if(busyRef.current)return;busyRef.current=true;setBusy(true)

  try{await flow.current.dispose();if(alive.current){setError('');if(updated)setStage('success');else onClose()}}

  catch{if(alive.current)setError('Secure sign-out could not finish. Please retry.')}

  finally{busyRef.current=false;if(alive.current)setBusy(false)}

 }

 async function fresh(){

  if(busyRef.current)return;busyRef.current=true;setBusy(true)

  try{await flow.current?.dispose();if(!alive.current)return;client.current=createWebsiteRecoveryClient();flow.current=client.current?createRecoveryFlow(client.current):null;setError('');setStage('request')}

  catch{setStage('cleanup');setError('Secure sign-out could not finish. Please retry.')}

  finally{busyRef.current=false;if(alive.current)setBusy(false)}

 }

 return <dialog ref={dialog} className={`password-reset-dialog reset-${stage}`} aria-labelledby="reset-title" aria-modal="true" onCancel={e=>{e.preventDefault();void close()}}>

  <div className="reset-card" aria-busy={busy||stage==='verifying'}>

   {stage!=='success'&&<button className="reset-back" type="button" onClick={()=>void close()} disabled={busy||stage==='verifying'}><img src={back} alt=""/>Back to sign in</button>}

   {['request','sent','new'].includes(stage)&&<div className="reset-progress" aria-label={`Password reset step ${stage==='request'?1:stage==='sent'?2:3} of 3`}>{[1,2,3].map(n=><span key={n} className={n===(stage==='request'?1:stage==='sent'?2:3)?'active':''}/>)}</div>}

   {stage==='sent'&&<div className="reset-envelope" aria-hidden="true"><img src={envelope} alt=""/><img src={envelopeCheck} alt=""/><img src={envelopeTick} alt=""/></div>}

   {stage==='success'&&<div className="reset-success-art" aria-hidden="true"><i/><i/><i/><span><img src={check} alt=""/></span></div>}

   <h2 id="reset-title" tabIndex={-1}>{title}</h2>

   {error&&<p className="reset-error" id="reset-error" role="alert">{error}</p>}

   {stage==='request'&&<><p>No worries. Enter your email and we’ll send you a reset link to regain access.</p><form onSubmit={send}><label className="reset-field" htmlFor="reset-email">Email address<input id="reset-email" type="email" autoComplete="email" required placeholder="you@example.com" value={email} disabled={busy} onChange={e=>{setEmail(e.target.value);setError('')}} aria-invalid={Boolean(error)} aria-describedby={error?'reset-error':undefined}/></label><button className="reset-primary" disabled={busy||seconds>0}>{busy?'Sending…':seconds?`Send reset link (${seconds}s)`:'Send reset link'}</button></form></>}

   {stage==='sent'&&<><p>If an account exists for this email, you’ll receive a password reset link.</p><strong className="reset-masked">{masked}</strong><p className="reset-expiry">For your security, this link expires. Request a new one if needed.</p><div className="reset-resend"><p>Didn’t receive the email? Check your spam folder.</p><button type="button" disabled={busy||seconds>0} onClick={()=>void send()}>{busy?'Sending…':seconds?`Resend in ${seconds}s`:'Resend'}</button></div></>}

   {stage==='verifying'&&<p role="status">Verifying your secure reset link. Please wait.</p>}

   {stage==='unavailable'&&<button className="reset-primary" type="button" onClick={()=>void fresh()} disabled={busy}>Request a fresh reset link</button>}

   {stage==='new'&&<><p>Enter your new password.</p><form onSubmit={update}><PasswordField label="New password" id="reset-password" value={password} setValue={v=>{setPassword(v);setError('')}} disabled={busy} error={error} helper/><PasswordField label="Confirm new password" id="reset-confirm" value={confirmation} setValue={v=>{setConfirmation(v);setError('')}} disabled={busy} error={error}/><button className="reset-primary" disabled={busy}>{busy?'Updating…':'Reset password'}</button></form></>}

   {stage==='success'&&<><p>Your password has been updated. You can now sign in with your new password.</p><button className="reset-primary" type="button" onClick={()=>void close()} disabled={busy}>Back to sign in</button></>}

   {stage==='cleanup'&&<button className="reset-primary" type="button" disabled={busy} onClick={()=>void retryCleanup()}>{busy?'Signing out…':'Retry secure sign-out'}</button>}

   <footer><img src={lock} alt=""/>Secure password reset</footer>

  </div>

 </dialog>

}



export default function WebsitePasswordResetPage({initialStage}) {

 const navigate=useNavigate();const [email,setEmail]=useState(''),[password,setPassword]=useState('')

 const form={email,password,setEmail,setPassword,setError:()=>{},error:'',message:'',loading:false}

 return <><WebsiteLogin form={form} configured={true} checkingSession={false} onSubmit={e=>e.preventDefault()} onGoogleLogin={()=>{}}/><PasswordResetDialog initialStage={initialStage} onClose={()=>navigate('/auth/login',{replace:true})}/></>

}
