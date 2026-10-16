import { createClient } from '@supabase/supabase-js'

import { getSupabaseAuthConfig } from './supabaseClient'

import { noteRecoveryRateLimit } from './passwordRecovery'



export function createWebsiteRecoveryClient() {

  const {url,anonKey}=getSupabaseAuthConfig()

  if(!url || !anonKey)return null

  return createClient(url,anonKey,{

    auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false,storageKey:`website-recovery-${crypto.randomUUID()}`},

    global:{fetch:async(input,init)=>{

      const response=await fetch(input,{...init,signal:AbortSignal.timeout(15_000)})

      // Retain only a deadline: SDK errors do not expose Retry-After headers.

      if(response.status===429)noteRecoveryRateLimit(response.headers)

      return response

    }},

  })

}
