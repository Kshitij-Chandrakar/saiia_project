import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { supabase } from './supabaseClient'
import { signOutWebsite } from './websiteSessionLoss'
import { submitMarketingUnsubscribe } from './authApi'
import WebsiteRecovery from './WebsiteRecovery'

export function WebsiteLogout() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState('pending')
  const operation = useRef(null)
  const lock = useRef(true)
  useEffect(() => {
    let active = true
    setState('pending')
    if (operation.current?.attempt !== attempt) {
      operation.current = { attempt, promise: (async () => {
        if (!supabase) throw new Error('unavailable')
        const result = await signOutWebsite(supabase)
        if (result?.error !== null) throw new Error('failed')
      })() }
    }
    operation.current.promise.then(() => {
      if (active) setState('complete')
    }, () => { if (active) setState('error') }).finally(() => { if (active) lock.current = false })
    return () => { active = false }
  }, [attempt])
  function retry() {
    if (lock.current) return
    lock.current = true
    setState('pending')
    setAttempt(value => value + 1)
  }
  return <WebsiteRecovery title={state === 'error' ? 'Sign-out wasn’t confirmed' : state === 'complete' ? 'You’re signed out' : 'Signing you out'}
    message={state === 'error' ? 'We couldn’t confirm that sign-out completed. Try again to check this browser before leaving a shared device.' : state === 'complete' ? 'This browser is signed out. Sign in again when you’re ready to continue.' : 'Please wait while we finish signing you out.'} busy={state === 'pending'}>
    {state === 'error' && <button type="button" onClick={retry}>Retry sign out</button>}
    {state === 'complete' && <a href="/auth/login">Back to sign in</a>}
    {state !== 'pending' && <a href="/">Return home</a>}
  </WebsiteRecovery>
}

const RETRY_WINDOW = 15 * 60 * 1000
const MAX_ATTEMPTS = 3

export function WebsiteUnsubscribe({ backendUrl }) {
  const token = useRef(new URLSearchParams(window.location.search).get('token')?.trim() || '')
  const expires = useRef(Date.now() + RETRY_WINDOW)
  const operation = useRef(null)
  const lock = useRef(true)
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState(token.current ? 'pending' : 'missing')
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (state !== 'pending') return
    setSlow(false)
    const timer = setTimeout(() => setSlow(true), 10000)
    return () => clearTimeout(timer)
  }, [state, attempt])
  useLayoutEffect(() => {
    const url = new URL(window.location.href)
    if (url.searchParams.has('token')) {
      url.searchParams.delete('token')
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
    }
  }, [])
  useEffect(() => {
    const timer = setTimeout(() => {
      token.current = ''
      setState(current => ['error', 'unknown'].includes(current) ? 'missing' : current)
    }, Math.max(0, expires.current - Date.now()))
    return () => clearTimeout(timer)
  }, [])
  useEffect(() => {
    let active = true
    if (!token.current) { lock.current = false; return }
    if (operation.current?.attempt !== attempt) {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 15000)
      operation.current = { attempt, promise: submitMarketingUnsubscribe(token.current, { backendUrl, signal: controller.signal }).finally(() => clearTimeout(timer)) }
    }
    operation.current.promise.then(result => {
      if (!active) return
      token.current = ''
      setState(result.success ? 'complete' : 'invalid')
    }, failure => {
      if (!active) return
      const retryable = token.current && Date.now() < expires.current && attempt + 1 < MAX_ATTEMPTS
      if (!retryable) token.current = ''
      setState(retryable ? failure?.name === 'AbortError' ? 'unknown' : 'error' : 'missing')
    }).finally(() => { if (active) lock.current = false })
    return () => { active = false }
  }, [attempt, backendUrl])
  function retry() {
    if (lock.current) return
    if (!token.current || Date.now() >= expires.current || attempt + 1 >= MAX_ATTEMPTS) {
      token.current = ''
      setState('missing')
      return
    }
    lock.current = true
    setSlow(false)
    setState('pending')
    setAttempt(value => value + 1)
  }
  const messages = {
    pending: 'Please wait while we update your promotional email preference.',
    complete: 'You have been unsubscribed from promotional and discount emails if this link was valid.',
    error: 'We couldn’t confirm your preference update. You can try again on this page.',
    unknown: 'We stopped waiting for a response, but the update may still finish. Its result is not confirmed. You can check by retrying this same preference update.',
    missing: 'Reopen the original unsubscribe link in your email to update your preference. This page no longer has the link needed to continue.',
    invalid: 'This link couldn’t update your preference. Reopen the original email link to try again.',
  }
  return <WebsiteRecovery title={state === 'complete' ? 'Email preference updated' : state === 'pending' ? slow ? 'Still updating your preference' : 'Updating your preference' : 'Email preferences'} message={state === 'pending' && slow ? 'Your update is not confirmed yet. Keep this page open while we wait for a response.' : messages[state]} busy={state === 'pending'} progress={state === 'pending'} focusOnChange={false}
    note="You may still receive important account, security, verification, password reset, and transactional emails.">
    {['error', 'unknown', 'pending'].includes(state) && <button type="button" disabled={state === 'pending'} onClick={retry}>Retry preference update</button>}
    {state !== 'pending' && <a href="/">Return home</a>}
  </WebsiteRecovery>
}
