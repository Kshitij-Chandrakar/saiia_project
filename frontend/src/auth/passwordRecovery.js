import { verifyAuthEmailAction } from './authApi.js'

export const RESET_COOLDOWN_MS = 60_000

export const RESET_DEADLINE_KEY = 'intervucopilot.reset-resend-deadline'

let deadline = 0

let requestInFlight = null



export function isWebsiteRecoveryEntry(url, desktop = false) {

  if (desktop) return false

  return url.pathname === '/auth/reset-password' || (url.pathname === '/auth/confirm' && (url.searchParams.getAll('type').includes('recovery') || new URLSearchParams(url.hash.slice(1)).get('type') === 'recovery'))

}

export function resetSecondsRemaining(now = Date.now()) {

  try { const saved=Number(localStorage.getItem(RESET_DEADLINE_KEY));if(Number.isFinite(saved) && saved<=now+86400_000)deadline=Math.max(deadline,saved) } catch { /* In-memory cooldown still applies. */ }

  return Math.max(0, Math.ceil((deadline-now)/1000))

}

function cooldown(seconds = 60) {

  deadline=Math.max(deadline,Date.now()+Math.min(86400,Math.max(60,seconds))*1000)

  try { localStorage.setItem(RESET_DEADLINE_KEY,String(deadline)) } catch { /* No identifiers are stored. */ }

}

export function maskResetEmail(email) {

  const [name,domain] = email.trim().split('@')

  return `${name.slice(0,Math.min(2,Math.max(1,name.length-1)))}••••@${domain}`

}

export function recoveryError(error) {

  const rateLimited=error?.status===429 || ['over_email_send_rate_limit','over_request_rate_limit'].includes(error?.code)

  const raw=error?.retryAfter ?? error?.headers?.get?.('retry-after')

  const seconds=Number(raw) || Math.ceil((Date.parse(raw)-Date.now())/1000) || 60

  return {rateLimited,retryAfter:Math.min(86400,Math.max(60,seconds)),message:rateLimited ? 'Too many requests. Please wait before requesting another link.' : 'Unable to send a reset link right now. Please try again.'}

}

export function noteRecoveryRateLimit(headers) { cooldown(recoveryError({status:429,headers}).retryAfter) }

export async function requestResetLink(client, email, origin) {

  if(requestInFlight)return requestInFlight

  if(resetSecondsRemaining())return {ok:false,message:'Please wait before requesting another link.'}

  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))return {ok:false,message:'Enter a valid email address.'}

  // All sends/resends use this guard and the provider's /recover endpoint.

  // This deadline is UX only; Supabase Auth enforces server-side limits.

  cooldown()

  requestInFlight=(async()=>{

    try {

      const {error}=await client.auth.resetPasswordForEmail(email.trim(),{redirectTo:new URL('/auth/reset-password',origin).href})

      if(error){const safe=recoveryError(error);if(safe.rateLimited)cooldown(safe.retryAfter);return {ok:false,message:safe.message}}

      cooldown();return {ok:true}

    } catch {return {ok:false,message:'Unable to send a reset link right now. Please try again.'}}

    finally {requestInFlight=null}

  })()

  return requestInFlight

}



export function createRecoveryFlow(client) {

  let verification = null

  let update = null

  let cleanup = null

  let closed = false

  let verifiedUser = null

  let authenticated = false

  return {

    verify(search) {

      if(closed)return Promise.resolve({status:'error'})

      if(!verification)verification=(async()=>{

        if(new URLSearchParams(search).get('type')!=='recovery')return {status:'error'}

        const result=await verifyAuthEmailAction(search,client)

        if(result.status!=='recovery')return {status:'error'}

        authenticated=true

        const {data,error}=await client.auth.getUser()

        if(error || !data?.user?.id || closed)return {status:'error'}

        verifiedUser=data.user.id

        return {status:'recovery'}

      })().catch(()=>({status:'error'}))

      return verification

    },

    update(password) {

      if(closed || !verifiedUser)return Promise.resolve({ok:false,message:'This recovery link is unavailable. Request a fresh link.'})

      if(update)return update

      update=(async()=>{

        try {

          const {data,error}=await client.auth.getUser()

          if(error || data?.user?.id!==verifiedUser)return {ok:false,message:'This recovery session is unavailable. Request a fresh link.'}

          const {error:failure}=await client.auth.updateUser({password})

          if(failure)return {ok:false,message:failure.code==='weak_password' ? 'Use a stronger password that meets your account’s password policy.' : failure.code==='same_password' ? 'Choose a password different from your current password.' : 'Your password could not be updated. Please try again.'}

          verifiedUser=null

          return {ok:true}

        } catch {verifiedUser=null;return {ok:false,uncertain:true,message:'The password update could not be confirmed. Try signing in with your new password or request a fresh link.'}}

        finally {update=null}

      })()

      return update

    },

    dispose() {

      closed=true;verifiedUser=null

      if(cleanup)return cleanup

      cleanup=(async()=>{

        await Promise.allSettled([verification,update].filter(Boolean))

        if(authenticated){const {error}=await client.auth.signOut({scope:'local'});if(error)throw new Error('Secure sign-out could not finish. Please retry.');authenticated=false}

      })().finally(()=>{cleanup=null})

      return cleanup

    },

  }

}
