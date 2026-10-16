import { createClient } from '@supabase/supabase-js'
import { isWebsiteRecoveryEntry } from './passwordRecovery.js'


const viteEnv = import.meta.env || {}


export function getSupabaseAuthConfig(env = viteEnv) {
  return {
    url: String(env.VITE_SUPABASE_URL || '').trim(),
    anonKey: String(env.VITE_SUPABASE_ANON_KEY || '').trim(),
  }
}


export function hasSupabaseAuthConfig(env = viteEnv) {
  const config = getSupabaseAuthConfig(env)
  return Boolean(config.url && config.anonKey)
}


export function createSupabaseBrowserClient(env = viteEnv) {
  const config = getSupabaseAuthConfig(env)
  if (!config.url || !config.anonKey) {
    throw new Error('Supabase auth is not configured for this build.')
  }

  return createClient(config.url, config.anonKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: !(typeof window !== 'undefined' && isWebsiteRecoveryEntry(new URL(window.location.href), Boolean(window.electronAPI))),
      persistSession: true,
    },
  })
}


export const supabase = hasSupabaseAuthConfig()
  ? createSupabaseBrowserClient()
  : null
